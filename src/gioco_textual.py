"""UI di gioco **Textual** (host, fuori dal motore): pilota il motore SOLO via le porte.

Non è presentazione dentro il motore: è un *host* che sta al posto del driver headless di
`main.py`. Parla al game engine attraverso `SessioneGioco` (le porte: `prossima_narrazione`
async, coda degli intenti, snapshot) e il **bus** tipizzato — tutto su DTO di `contracts`,
mai sul `World`. Importa `main` (il composition root) e `contracts`; **non** importa `motore`
né esper: la membrana resta a tenuta (C-2a/C-2b). Textual è importato **lazy** dentro
`_costruisci_app` e resta un host opt-in: non è una dipendenza del motore (C-5).

Flusso (interattivo, sulla mappa del piano — il menu è la SCENA composta dal motore):
    narrazione della stanza (await) → Combatti/Scappi se c'è un nemico → combattimento a
    turni (Attacca) → "Vai: stanza N" / "Scendi la scala" (solo dove la mappa la mette)
    → discesa = vittoria del piano (MVP).
Gli eventi di dominio (inizio scontro, esito, permadeath, anomalia, discesa) arrivano dal
bus via `CronacaBus` e finiscono nel log. Permadeath = terminale di run (`MortePersonaggio`).
"""

from __future__ import annotations

import sys

from contracts import MortePersonaggio, PlayerChoseOption
from main import CronacaBus, costruisci_sessione


def _costruisci_app(sessione):
    """Costruisce l'app Textual sopra una `SessioneGioco`. Import locale: la TUI è opt-in."""
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal
    from textual.widgets import Button, Footer, Header, Input, ProgressBar, RichLog, Static

    class Gioco(App):
        TITLE = "Dungeon Crawler — fetta verticale"
        CSS = """
        #prosa { padding: 1 2; border: round $accent; height: auto; min-height: 3; }
        #stato { padding: 0 2; }
        #log { height: 1fr; border: round $primary; padding: 0 1; margin: 1 0; }
        #menu { height: auto; padding: 0 2 1 2; }
        #azione { dock: bottom; display: none; }
        #azione.attiva { display: block; }
        #attesa { height: auto; padding: 0 2; display: none; }
        #attesa.attiva { display: block; }
        #attesa-barra { width: 1fr; }
        Button { margin: 0 1 0 0; }
        """
        BINDINGS = [
            Binding("a", "azione", "Azione libera"),
            Binding("s", "salva", "Salva"),
            Binding("q", "quit", "Esci"),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.sessione = sessione
            self.cronaca = None
            self._morto = False
            self.fase_corrente = ""   # ultimo `fase` visto (comodo per i test headless)
            self.prosa_corrente = ""  # ultima prosa mostrata
            self._in_conferma = False  # finestra di conferma dell'azione libera
            self._occupato = False     # il GM sta lavorando: input sospeso

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            yield Static("", id="prosa")
            yield Static("", id="stato")
            yield RichLog(id="log", wrap=True, markup=True)
            with Horizontal(id="attesa"):
                yield Static("", id="attesa-testo")
                yield ProgressBar(id="attesa-barra", total=100, show_eta=False)
            yield Horizontal(id="menu")
            yield Input(id="azione", placeholder="Cosa fai? (vuoto = annulla)")
            yield Footer()

        async def on_mount(self) -> None:
            self.cronaca = CronacaBus(self.sessione.bus)
            self.sessione.bus.registra(MortePersonaggio, self._on_morte)
            # La pipeline racconta i suoi stadi: la barra dà riferimenti al giocatore.
            self.sessione.on_avanzamento = self._su_avanzamento
            snap = await self._con_attesa(self.sessione.prossima_narrazione())
            await self._mostra(snap, [])

        # --- Barra di attesa graduale (riferimenti durante la latenza del GM) ---

        def _su_avanzamento(self, etichetta: str, frazione: float) -> None:
            self.query_one("#attesa-testo", Static).update(etichetta)
            self.query_one("#attesa-barra", ProgressBar).update(progress=frazione * 100)

        async def _con_attesa(self, coroutine):
            """Esegue una porta async mostrando la barra e SOSPENDENDO l'input:
            niente doppi click mentre il GM lavora (il World non si tocca in corsa)."""
            self._occupato = True
            attesa = self.query_one("#attesa")
            self._su_avanzamento("Il GM sta preparando la scena…", 0.02)
            attesa.add_class("attiva")
            try:
                return await coroutine
            finally:
                attesa.remove_class("attiva")
                self._occupato = False

        def _on_morte(self, _ev: object) -> None:
            self._morto = True  # permadeath: terminale di run (non "sconfitta")

        async def on_button_pressed(self, event: Button.Pressed) -> None:
            if self._occupato:
                return  # il GM sta lavorando: l'input riprende a barra spenta
            bid = event.button.id or ""
            if bid == "esci":
                self.exit()
            elif bid.startswith("opz-"):
                await self._agisci(int(bid.split("-", 1)[1]))

        async def _agisci(self, indice: int) -> None:
            # host→motore: intento tipizzato in coda, poi il turno del motore (C-7).
            self.sessione.coda.accoda(PlayerChoseOption(indice))
            snap = self.sessione.avanza()
            righe = self.cronaca.preleva()
            if not self._morto and not snap.opzioni:
                # menu vuoto ⇒ tornati in attesa: si chiede un nuovo turno di narrazione.
                snap = await self._con_attesa(self.sessione.prossima_narrazione())
            await self._mostra(snap, righe)

        def action_azione(self) -> None:
            """Apre l'input dell'azione libera (solo in narrazione, da vivi)."""
            if self._morto or self._occupato or self.fase_corrente != "narrazione":
                return
            self._in_conferma = False
            campo = self.query_one("#azione", Input)
            campo.value = ""
            campo.placeholder = "Cosa fai? (vuoto = annulla)"
            campo.add_class("attiva")
            campo.focus()

        async def on_input_submitted(self, event) -> None:
            if self._occupato:
                return
            campo = self.query_one("#azione", Input)
            testo = event.value.strip()
            rl = self.query_one("#log", RichLog)
            if not testo:  # vuoto = annulla (in entrambe le fasi della finestra)
                campo.remove_class("attiva")
                self._in_conferma = False
                return
            if not self._in_conferma:
                # FINESTRA DI CONFERMA (editabile): riepilogo + stima deterministica.
                riepilogo = self.sessione.riepiloga_azione(testo)
                stima = riepilogo.stima
                rl.write(f"[b]Stai per:[/b] {testo} — corretto? ({riepilogo.contesto})")
                rl.write(
                    f"[i]Questa azione ti prenderà {stima.forbice} "
                    f"(~{stima.tick} tick). Invio per confermare, modifica per correggere, "
                    f"vuoto per annullare.[/i]"
                )
                self._in_conferma = True
                campo.value = testo  # editabile prima dell'immissione
                campo.placeholder = "Conferma o modifica l'azione"
                campo.focus()
                return
            # IMMISSIONE: il testo (eventualmente editato) entra nel turno GM.
            campo.remove_class("attiva")
            self._in_conferma = False
            riepilogo = self.sessione.riepiloga_azione(testo)
            snap = await self._con_attesa(self.sessione.esegui_azione(riepilogo))
            await self._mostra(snap, self.cronaca.preleva())

        async def _mostra(self, snap, righe) -> None:
            self.fase_corrente = snap.fase
            if snap.prosa:
                self.prosa_corrente = snap.prosa
                self.query_one("#prosa", Static).update(snap.prosa)
            stato = "  ·  ".join(snap.stato) if snap.stato else "—"
            self.query_one("#stato", Static).update(f"[b]\\[{snap.fase}][/b]  {stato}")
            rl = self.query_one("#log", RichLog)
            for r in righe:
                rl.write(r)
            menu = self.query_one("#menu", Horizontal)
            await menu.remove_children()
            if self._morto:
                rl.write("[b red]💀 Sei morto — permadeath, run terminata.[/]")
                await menu.mount(Button("Esci (Q)", id="esci", variant="error"))
                return
            bottoni = [
                Button(o.etichetta, id=f"opz-{o.indice}", variant="primary")
                for o in snap.opzioni
            ]
            if bottoni:
                await menu.mount(*bottoni)

        def action_salva(self) -> None:
            self.query_one("#log", RichLog).write(f"[green]{self.sessione.salva()}[/]")

        def on_unmount(self) -> None:
            if self.cronaca is not None:
                self.cronaca.chiudi()
            try:
                self.sessione.bus.deregistra(MortePersonaggio, self._on_morte)
            except ValueError:
                pass

    return Gioco()


def _scegli_provider(argv: list[str]) -> tuple[object | None, str]:
    """Seleziona il provider del GM. Ritorna `(provider, etichetta)`; `None` = fake.

    Politica (PLK §4 + best practice chiavi API):
      - la chiave vive SOLO nell'ambiente (`ANTHROPIC_API_KEY`): qui se ne controlla
        la PRESENZA, mai il valore — lo legge esclusivamente l'SDK;
      - mai la chiave in argv/URL/log; nessun degrado silenzioso: se il live non è
        possibile lo si DICE (niente fallback muto che maschera un errore di setup);
      - `--fake` forza l'offline; `--live` esige il live (errore chiaro se manca
        chiave o SDK); default: live se la chiave c'è, altrimenti offline.
    """
    from provider import (
        AnthropicBackend,
        MODELLO_DEFAULT,
        MODELLO_VELOCE,
        ProviderPerSchema,
        chiave_presente,
        sdk_disponibile,
    )

    if "--fake" in argv:
        return None, "GM offline (contenuto scriptato)"
    presente, sdk = chiave_presente(), sdk_disponibile()
    if "--live" in argv:
        if not presente:
            raise SystemExit(
                "[gioca] --live richiede ANTHROPIC_API_KEY nell'ambiente (o in .env: "
                "copia .env.example → .env e compila). La chiave non va MAI in argv o nel repo."
            )
        if not sdk:
            raise SystemExit(
                "[gioca] --live richiede l'SDK: .venv\\Scripts\\pip install anthropic"
            )
    if not presente:
        return None, "GM offline (nessuna ANTHROPIC_API_KEY: vedi .env.example)"
    if not sdk:
        return None, "GM offline (SDK anthropic non installato)"
    # Latenza: il modello FORTE serve solo la chiamata gating (il turno); gli stadi
    # ancillari non-gating (ideazione/limatura/distillazione) vanno sul VELOCE.
    from contracts import TurnoNarrazione

    forte = AnthropicBackend()
    # Corsia veloce: output brevi per contratto (ideazione/limatura/distillazione),
    # quindi max_tokens stretto (fallisce presto invece di generare a vuoto) e
    # timeout corto — gli stadi non-gating degradano, non bloccano.
    veloce = AnthropicBackend(modello=MODELLO_VELOCE, max_tokens=512, timeout=15.0)
    provider = ProviderPerSchema({TurnoNarrazione: forte}, predefinito=veloce)
    return provider, f"GM live — {MODELLO_DEFAULT} (turni) + {MODELLO_VELOCE} (rifiniture)"


def main(argv: list[str] | None = None) -> int:  # pragma: no cover (entry point)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    seed = 1
    if "--seed" in argv:
        seed = int(argv[argv.index("--seed") + 1])
    provider, etichetta = _scegli_provider(argv)
    print(f"[gioca] {etichetta}")
    sessione = costruisci_sessione(seed=seed, provider=provider)
    app = _costruisci_app(sessione)
    app.sub_title = etichetta  # il giocatore VEDE con quale GM sta giocando
    app.run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
