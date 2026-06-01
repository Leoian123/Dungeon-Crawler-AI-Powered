"""Composition root della v1 — **headless**: cabla il motore e lo pilota senza UI.

Il game engine è indipendente dalla presentazione: una UI futura (web, Electron, TUI…)
si innesterà su questo stesso strato attraverso le **porte** di `SessioneGioco` e gli
eventi tipizzati del **bus** — tutto espresso sui DTO di `contracts`, mai sul `World`.
Qui non c'è nessuna dipendenza di presentazione: il motore resta ignaro dell'host (C-2a)
e nessun layer importa Textual (C-5). Questo modulo è la *colla* + un driver headless di
riferimento, non un layer con membrana.

`SessioneGioco` è la **porta** verso il motore vista da un qualunque host: produce la
narrazione (coroutine host-agnostica, `await`-abile da un worker UI o da `asyncio.run`),
drena gli intenti del giocatore sul turno e ricostruisce lo `SnapshotVista` da
renderizzare. Il giocatore gioca un incontro completo: narrazione → scelta →
combattimento deterministico → ritorno alla narrazione.

Nell'MVP il provider è il **FakeProvider** (offline, scriptato); il backend Anthropic
reale (fase 5) si innesta dietro la stessa interfaccia `genera`.
"""

from __future__ import annotations

import asyncio
import random
import tempfile
from pathlib import Path
from typing import Callable

from contracts import (
    AnomalyTriggered,
    Archetipo,
    Blocco,
    BusEventi,
    ClasseProva,
    CombatResolved,
    DiscesaPiano,
    Durata,
    EncounterStarted,
    EntitaGenerata,
    MortePersonaggio,
    Opzione,
    OpzioneVista,
    PlayerChoseOption,
    Rarita,
    SnapshotVista,
    TipoAzione,
    TurnoNarrazione,
)
from guscio import Guscio
from motore import (
    MODEL_ID_DEFAULT,
    SpecNemico,
    esegui_turno_narrazione,
    in_combattimento,
    ingaggia_combattimento,
    livello_corrente,
    materializza_turno,
    proietta_scheda,
    protagonista,
    salva_run,
    tenta_disimpegno,
    tick,
)
from provider import FakeProvider

# Menu di narrazione (MVP): il terzetto noto ridotto a Combatti/Scappi (IC §7, niente creep).
_MENU_NARRAZIONE = (
    OpzioneVista(indice=0, etichetta="Combatti", tipo=TipoAzione.COMBATTI),
    OpzioneVista(indice=1, etichetta="Scappi", tipo=TipoAzione.SCAPPA),
)
_MENU_COMBATTIMENTO = (OpzioneVista(indice=0, etichetta="Attacca", tipo=TipoAzione.COMBATTI),)


class SessioneGioco:
    """La porta motore↔host per la v1: narrazione async, intenti sul turno, snapshot.

    Possiede il run-World (via `Guscio`), il provider e una piccola macchina di modo
    (attesa-narrazione / scelta-narrazione / combattimento). Vive nel composition root:
    può importare il motore — l'host (UI o driver headless) no, vi parla solo via porte.
    """

    def __init__(self, provider, *, directory: Path, seed: int = 0) -> None:
        self.provider = provider
        self.rng = random.Random(seed)
        self.guscio = Guscio(directory)
        self.guscio.nuova_partita(uuid="carl", destrezza=10, hp=30, seed=seed)
        self.bus = self.guscio.bus
        self.coda = self.guscio.coda  # CodaIntenti: l'host vi accoda gli intenti
        self._modo = "attesa_narrazione"
        self._opzioni: tuple[OpzioneVista, ...] = ()

    # --- Porte verso l'host ---------------------------------------------------

    async def prossima_narrazione(self) -> SnapshotVista:
        """Coroutine host-agnostica (un worker UI o `asyncio.run` la `await`-a, C-6):
        prepara il contesto, chiama l'AI (1 `genera`, gate, fallback) e materializza
        l'entità. Ritorna lo snapshot con prosa + menu di narrazione."""
        pent, _marker, _scheda = protagonista()
        proiezione = proietta_scheda(pent)
        risultato = await esegui_turno_narrazione(
            self.provider, livello=livello_corrente(), proiezione=proiezione, rng=self.rng
        )
        materializza_turno(risultato, self.bus)  # può pubblicare AnomalyTriggered (reveal)
        self._modo = "scelta_narrazione"
        self._opzioni = _MENU_NARRAZIONE
        return SnapshotVista(
            prosa=risultato.turno.prosa,
            opzioni=self._opzioni,
            stato=self._descrittori(),
            fase="narrazione",
        )

    def avanza(self) -> SnapshotVista:
        """Il **turno del motore** per l'host: drena la coda degli intenti (host→motore,
        IC §7.1) e li serve nella fase corrente, poi ricostruisce lo snapshot. Gli
        intenti stanno nella coda tra l'emissione dell'host e questo turno (mai nel bus)."""
        for intento in self.coda.preleva_tutti():
            if isinstance(intento, PlayerChoseOption):
                self._agisci(intento.opzione)
        return self._snapshot_corrente()

    def salva(self) -> str:
        """Salvataggio a mano, in-run (H-6): il World sopravvive, scrittura prima di
        ogni teardown. Ritorna il messaggio da mostrare."""
        salva_run(self.guscio.directory, model_id=MODEL_ID_DEFAULT)
        return "Partita salvata."

    # --- Macchina di modo (interpretazione delle scelte) ----------------------

    def _agisci(self, indice: int) -> None:
        if not (0 <= indice < len(self._opzioni)):
            return
        if self._modo == "scelta_narrazione":
            self._agisci_narrazione(self._opzioni[indice])
        elif self._modo == "combattimento":
            self._agisci_combattimento()

    def _agisci_narrazione(self, opzione: OpzioneVista) -> None:
        if opzione.tipo is TipoAzione.SCAPPA:
            # Disimpegno: prova su stat PRIMA di ingaggiare (FNC §5.3, tirata dal motore).
            _p, _m, scheda = protagonista()
            if tenta_disimpegno(scheda.destrezza, ClasseProva.BRONZO, self.rng):
                self._attendi_narrazione()  # fuga riuscita → nuovo turno
                return
        # Combatti (o disimpegno fallito): si compone l'incontro e si ingaggia a confine.
        ingaggia_combattimento(
            self.bus,
            nemici=[SpecNemico(destrezza=5, punti_vita=3)],
            seed=self.rng.randint(0, 10**9),
        )
        self._modo = "combattimento"
        self._opzioni = _MENU_COMBATTIMENTO

    def _agisci_combattimento(self) -> None:
        tick()  # un turno di combattimento risolto (deterministico, seeded)
        if not in_combattimento():  # CombatResolved ha riportato in NARRAZIONE
            self._attendi_narrazione()

    def _attendi_narrazione(self) -> None:
        self._modo = "attesa_narrazione"
        self._opzioni = ()  # menu vuoto ⇒ l'host chiede un nuovo turno di narrazione

    # --- Costruzione dello snapshot dal World corrente ------------------------

    def _snapshot_corrente(self) -> SnapshotVista:
        return SnapshotVista(
            prosa="",  # la prosa di transizione arriva via eventi sul bus
            opzioni=self._opzioni,
            stato=self._descrittori(),
            fase="combattimento" if in_combattimento() else "narrazione",
        )

    def _descrittori(self) -> tuple[str, ...]:
        pent, _marker, scheda = protagonista()
        hp = f"HP {scheda.punti_vita}/{scheda.punti_vita_max}"
        return (hp, *proietta_scheda(pent).descrittori)


# --- Cronaca del bus: eventi di dominio → righe di testo (headless, read-only) ----
#
# Lo stesso ruolo "consumatore read-only di eventi" che avrà una Ui (IC §2.3), qui
# ridotto a testo: l'host headless si sottoscrive al bus e raccoglie ciò che il motore
# emette. Una UI futura sostituirà questo collettore senza toccare il motore.
_MAPPA_EVENTI: tuple[tuple[type, Callable[[object], str]], ...] = (
    (EncounterStarted, lambda _e: "Lo scontro ha inizio."),
    (CombatResolved, lambda e: (
        "Hai vinto lo scontro." if getattr(e, "vittoria", False) else "Lo scontro si chiude."
    )),
    (MortePersonaggio, lambda e: f"Sei morto: {getattr(e, 'causa', '')}."),
    (AnomalyTriggered, lambda _e: "Il dungeon ride: qualcosa è fuori scala…"),
    (DiscesaPiano, lambda e: f"Scendi: piano {getattr(e, 'piano', '?')}."),
)


class CronacaBus:
    """Raccoglie gli eventi di dominio dal bus e li rende come righe (host headless)."""

    def __init__(self, bus: BusEventi) -> None:
        self._bus = bus
        self._righe: list[str] = []
        self._coppie: list[tuple[type, Callable[[object], None]]] = []
        for tipo, formatta in _MAPPA_EVENTI:
            handler = self._fai_handler(formatta)
            bus.registra(tipo, handler)
            self._coppie.append((tipo, handler))

    def _fai_handler(self, formatta: Callable[[object], str]) -> Callable[[object], None]:
        def handler(evento: object) -> None:
            self._righe.append(formatta(evento))
        return handler

    def preleva(self) -> list[str]:
        """Restituisce e svuota le righe accumulate dall'ultima chiamata."""
        righe, self._righe = self._righe, []
        return righe

    def chiudi(self) -> None:
        """Deregistra gli handler: il bus è process-global, sopravvive all'host."""
        for tipo, handler in self._coppie:
            self._bus.deregistra(tipo, handler)
        self._coppie = []


def _turni_scriptati() -> list[TurnoNarrazione]:
    """Contenuto scriptato per il provider fake (offline). Esauriti, l'orchestrazione
    degrada al fallback deterministico (turno neutro): il gioco non si blocca mai."""
    return [
        TurnoNarrazione(
            prosa="Un corridoio umido gocciola luce verde. Uno Slime Mangiascarti ribolle "
            "tra rifiuti e un Rolex digerito.",
            entita=EntitaGenerata(
                archetipo=Archetipo.SLIME,
                rarita=Rarita.COMUNE,
                blocchi=[Blocco.VELENO],
                nome="Slime Mangiascarti",
                descrizione="Verde, acido, vagamente offeso dalla tua presenza.",
            ),
            opzioni=[
                Opzione(tipo=TipoAzione.COMBATTI, etichetta="Combatti"),
                Opzione(tipo=TipoAzione.SCAPPA, etichetta="Scappi"),
            ],
            durata=Durata.TURNO,
        ),
    ]


def costruisci_sessione(*, seed: int = 0, directory: Path | None = None) -> SessioneGioco:
    """Cabla provider fake → `SessioneGioco` (la porta del motore vista dall'host)."""
    directory = directory or Path(tempfile.mkdtemp(prefix="dcc-"))
    provider = FakeProvider([t.model_dump() for t in _turni_scriptati()])
    return SessioneGioco(provider, directory=directory, seed=seed)


def _rendi(snapshot: SnapshotVista, stampa: Callable[[str], None]) -> None:
    """Rende uno snapshot come testo (sostituito in blocco, C-4)."""
    if snapshot.prosa:
        stampa(snapshot.prosa)
    stato = ", ".join(snapshot.stato) if snapshot.stato else "—"
    stampa(f"[{snapshot.fase}] {stato}")
    for opz in snapshot.opzioni:
        stampa(f"  {opz.indice + 1}. {opz.etichetta}")


def _passo(
    sessione: SessioneGioco, indice: int, cronaca: CronacaBus, stampa: Callable[[str], None]
) -> SnapshotVista:
    """Un passo dell'host: accoda un intento tipizzato (host→motore, C-7), avanza il
    turno, drena la cronaca del bus e rende lo snapshot risultante."""
    sessione.coda.accoda(PlayerChoseOption(indice))
    snapshot = sessione.avanza()
    for riga in cronaca.preleva():
        stampa(riga)
    _rendi(snapshot, stampa)
    return snapshot


async def gioca_un_incontro(
    sessione: SessioneGioco,
    *,
    stampa: Callable[[str], None] = print,
    limite: int = 100,
) -> SnapshotVista:
    """Driver headless di riferimento: gioca un incontro completo via le sole porte.

    Narrazione (await della coroutine) → "Combatti" → "Attacca" finché lo scontro non si
    chiude e si torna alla narrazione. È la prova che il game engine gira end-to-end
    senza alcuna UI: una presentazione reale farebbe gli stessi passi via i suoi widget.
    """
    cronaca = CronacaBus(sessione.bus)
    try:
        snapshot = await sessione.prossima_narrazione()
        _rendi(snapshot, stampa)
        snapshot = _passo(sessione, 0, cronaca, stampa)  # "Combatti" → ingaggia
        guardia = 0
        while snapshot.fase == "combattimento" and guardia < limite:
            snapshot = _passo(sessione, 0, cronaca, stampa)  # "Attacca"
            guardia += 1
        return snapshot
    finally:
        cronaca.chiudi()


def main() -> None:  # pragma: no cover (entry point)
    sessione = costruisci_sessione(seed=1)
    asyncio.run(gioca_un_incontro(sessione))


if __name__ == "__main__":  # pragma: no cover
    main()
