"""Adattatore di presentazione Textual — l'UNICO modulo che importa Textual (nodo C).

Importa **solo `contracts` + Textual** (C-2b): mai `esper` / `World` / `Processor` /
`motore`. Tutto ciò che sta di là dalla membrana arriva **iniettato** come *porta*
(callable/coroutine tipizzate sui DTO di `contracts`); il cablaggio col motore vive nel
*composition root* (`src/main.py`), non qui.

Ruolo (IC §2.3, §2.4): **consumatore read-only di eventi di dominio + produttore di
intenti**, lo showrunner (FNC §8) scalato a UI intera.
  - **motore → vista:** si sottoscrive agli eventi di dominio sul **bus** e li traduce in
    righe di log (mai accede al `World`).
  - **vista → motore:** i widget emettono **intenti tipizzati** (`PlayerChoseOption`) su
    una **porta** (la coda lato motore), **mai** keystroke grezzi, **mai** mutano il
    `World` né chiamano l'LLM (C-7).

Concorrenza (IC §6, C-6): la narrazione (chiamata LLM, async) gira in un **worker
sottile** `@work(exclusive=True, group="narrazione")` che fa solo `await` della
coroutine host-agnostica iniettata. `exclusive` **cancella la richiesta superata** se il
giocatore va avanti mentre il dungeon "pensa" → la UI **non si blocca mai** (C-6).

Lo **snapshot di stato** (`SnapshotVista`) è un *input di rendering* sostituito in blocco
(C-4): la vista non accumula né diffa.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, OptionList, RichLog, Static

from contracts import (
    AnomalyTriggered,
    BusEventi,
    CombatResolved,
    DiscesaPiano,
    EncounterStarted,
    Intento,
    MortePersonaggio,
    OpzioneVista,
    PlayerChoseOption,
    SnapshotVista,
)

# Tipi delle porte iniettate (confine vista→motore, espresso sui DTO di `contracts`).
PortaNarrazione = Callable[[], Awaitable[SnapshotVista]]  # coroutine host-agnostica (worker)
PortaAvanza = Callable[[], SnapshotVista]                  # drena la coda + processa il turno
PortaAccoda = Callable[[Intento], None]                    # accoda un intento tipizzato
PortaSalva = Callable[[], str]                             # salva, ritorna un messaggio


class GiocoApp(App):
    """L'app TUI della v1. Quattro superfici (IC §7, niente creep): scroll della
    narrazione, menù a opzioni discrete, pannello di stato, comando salva."""

    CSS = """
    #narrazione { width: 2fr; border: round $accent; padding: 0 1; }
    #lato { width: 1fr; }
    #stato { border: round $accent; padding: 0 1; height: auto; }
    #menu { border: round $accent; }
    """

    BINDINGS = [
        # Selezione a opzioni discrete per tasti numerici (oltre al click/Invio).
        Binding("1", "scegli(0)", "Opz 1"),
        Binding("2", "scegli(1)", "Opz 2"),
        Binding("3", "scegli(2)", "Opz 3"),
        Binding("4", "scegli(3)", "Opz 4"),
        Binding("s", "salva", "Salva"),
        Binding("q", "quit", "Esci"),
    ]

    def __init__(
        self,
        *,
        bus: BusEventi,
        prossima_narrazione: PortaNarrazione,
        avanza: PortaAvanza,
        accoda_intento: PortaAccoda,
        salva: PortaSalva,
        snapshot_iniziale: SnapshotVista | None = None,
    ) -> None:
        super().__init__()
        self._bus = bus
        self._prossima_narrazione = prossima_narrazione
        self._avanza = avanza
        self._accoda_intento = accoda_intento
        self._salva = salva
        self._snapshot = snapshot_iniziale or SnapshotVista()
        self._opzioni_correnti: tuple[OpzioneVista, ...] = ()
        # Sottoscrizioni in-run da deregistrare al teardown (il bus è process-global).
        self._coppie_bus: list[tuple[type, object]] = []

    # --- Composizione delle quattro superfici v1 ------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            yield RichLog(id="narrazione", wrap=True, markup=True, highlight=False)
            with Vertical(id="lato"):
                yield Static(id="stato")
                yield OptionList(id="menu")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Dungeon Crawler — fetta verticale"
        self._registra_eventi()
        self._mostra(self._snapshot)
        self._forse_chiedi_narrazione(self._snapshot)  # primo turno: il dungeon "pensa"

    def on_unmount(self) -> None:
        # Il bus sopravvive all'app (process-global): si deregistrano gli handler in-run.
        for tipo, handler in self._coppie_bus:
            self._bus.deregistra(tipo, handler)
        self._coppie_bus = []

    # --- motore → vista: eventi di dominio sul bus → righe di log (read-only) --

    def _registra_eventi(self) -> None:
        narrazioni: list[tuple[type, Callable[[object], str]]] = [
            (EncounterStarted, lambda _e: "[b red]Lo scontro ha inizio.[/]"),
            (CombatResolved, lambda e: (
                "[b green]Hai vinto lo scontro.[/]" if getattr(e, "vittoria", False)
                else "[b yellow]Lo scontro si chiude.[/]"
            )),
            (MortePersonaggio, lambda e: f"[b red]Sei morto: {getattr(e, 'causa', '')}.[/]"),
            (AnomalyTriggered, lambda _e: "[b magenta]Il dungeon ride: qualcosa è fuori scala…[/]"),
            (DiscesaPiano, lambda e: f"[b cyan]Scendi: piano {getattr(e, 'piano', '?')}.[/]"),
        ]
        for tipo, formatta in narrazioni:
            handler = self._fai_handler(formatta)
            self._bus.registra(tipo, handler)
            self._coppie_bus.append((tipo, handler))

    def _fai_handler(self, formatta: Callable[[object], str]) -> Callable[[object], None]:
        def handler(evento: object) -> None:
            self._scrivi(formatta(evento))
        return handler

    # --- vista → motore: scelta del giocatore = intento tipizzato (C-7/C-8) ----

    def action_scegli(self, indice: int) -> None:
        self._seleziona(indice)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._seleziona(event.option_index)

    def _seleziona(self, indice: int) -> None:
        if not (0 <= indice < len(self._opzioni_correnti)):
            return
        # Il widget emette un INTENTO tipizzato sulla coda lato motore: non muta il World,
        # non chiama l'LLM (C-7). Poi chiede al motore di processare il turno.
        self._accoda_intento(PlayerChoseOption(indice))
        snap = self._avanza()
        self._mostra(snap)
        self._forse_chiedi_narrazione(snap)  # tornati alla narrazione ⇒ nuovo turno

    def action_salva(self) -> None:
        self._scrivi(f"[dim]{self._salva()}[/]")

    # --- Rendering dello snapshot (sostituito in blocco, C-4) ------------------

    def _mostra(self, snapshot: SnapshotVista) -> None:
        """Rende lo snapshot (sostituito in blocco, C-4). Solo rendering: la decisione
        di chiedere un nuovo turno di narrazione è esplicita (`_forse_chiedi_narrazione`),
        NON un effetto collaterale del render — così il risultato del worker non rilancia
        sé stesso."""
        self._snapshot = snapshot
        if snapshot.prosa:
            self._scrivi(snapshot.prosa)
        self._aggiorna_stato(snapshot)
        self._aggiorna_menu(snapshot)

    def _forse_chiedi_narrazione(self, snapshot: SnapshotVista) -> None:
        """Fase di narrazione senza opzioni ⇒ serve un nuovo turno: lancia il worker."""
        if snapshot.fase == "narrazione" and not snapshot.opzioni:
            self._carica_narrazione()

    def _aggiorna_stato(self, snapshot: SnapshotVista) -> None:
        stato = ", ".join(snapshot.stato) if snapshot.stato else "—"
        self.query_one("#stato", Static).update(
            f"[b]Fase:[/] {snapshot.fase}\n[b]Stato:[/] {stato}"
        )

    def _aggiorna_menu(self, snapshot: SnapshotVista) -> None:
        self._opzioni_correnti = snapshot.opzioni
        menu = self.query_one("#menu", OptionList)
        menu.clear_options()
        for opz in snapshot.opzioni:
            menu.add_option(f"{opz.indice + 1}. {opz.etichetta}")

    def _scrivi(self, testo: str) -> None:
        self.query_one("#narrazione", RichLog).write(testo)

    # --- Worker: la narrazione (LLM) gira async, la UI non si blocca (C-6) -----

    @work(exclusive=True, group="narrazione")
    async def _carica_narrazione(self) -> None:
        """Fa solo `await` della coroutine host-agnostica iniettata (IC §6). `exclusive`
        cancella un worker precedente ancora in volo: una `genera` superata viene
        abortita (CancelledError al primo `await`) e la UI resta viva (C-6)."""
        self._scrivi("[dim]…il dungeon pensa…[/]")
        snapshot = await self._prossima_narrazione()
        self._mostra(snapshot)
