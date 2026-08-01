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
    from textual.widgets import Button, Footer, Header, RichLog, Static

    class Gioco(App):
        TITLE = "Dungeon Crawler — fetta verticale"
        CSS = """
        #prosa { padding: 1 2; border: round $accent; height: auto; min-height: 3; }
        #stato { padding: 0 2; }
        #log { height: 1fr; border: round $primary; padding: 0 1; margin: 1 0; }
        #menu { height: auto; padding: 0 2 1 2; }
        Button { margin: 0 1 0 0; }
        """
        BINDINGS = [
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

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            yield Static("", id="prosa")
            yield Static("", id="stato")
            yield RichLog(id="log", wrap=True, markup=True)
            yield Horizontal(id="menu")
            yield Footer()

        async def on_mount(self) -> None:
            self.cronaca = CronacaBus(self.sessione.bus)
            self.sessione.bus.registra(MortePersonaggio, self._on_morte)
            snap = await self.sessione.prossima_narrazione()  # porta async (C-6)
            await self._mostra(snap, [])

        def _on_morte(self, _ev: object) -> None:
            self._morto = True  # permadeath: terminale di run (non "sconfitta")

        async def on_button_pressed(self, event: Button.Pressed) -> None:
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
                snap = await self.sessione.prossima_narrazione()
            await self._mostra(snap, righe)

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


def main(argv: list[str] | None = None) -> int:  # pragma: no cover (entry point)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    seed = 1
    if "--seed" in argv:
        seed = int(argv[argv.index("--seed") + 1])
    sessione = costruisci_sessione(seed=seed)
    _costruisci_app(sessione).run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
