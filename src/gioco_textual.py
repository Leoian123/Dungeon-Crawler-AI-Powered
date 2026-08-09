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
from main import CronacaBus, _riga_terminale, costruisci_sessione, etichetta_oggetto


def _costruisci_app(sessione):
    """Costruisce l'app Textual sopra una `SessioneGioco`. Import locale: la TUI è opt-in."""
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal
    from textual.widgets import Button, Footer, Header, Input, ProgressBar, RichLog, Static

    class Gioco(App):
        TITLE = "Dungeon Crawler — fetta verticale"
        # UNA finestra-chat (decisione 2026-08-09): narrazione, cronaca di scontro
        # e messaggi di sistema scorrono nello stesso log, distinti dal REGISTRO
        # tipografico (stili Rich: il "font" del terminale) — vedi _chat_*.
        CSS = """
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
            Binding("z", "zaino", "Zaino"),
            Binding("c", "scheda", "Scheda"),
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
            self._msg_visto = None     # ultimo MessaggioGM già considerato (dedup avvisi)
            self._avvisi_fallback = 0  # quanti turni degradati sono stati segnalati
            self._terminale_annunciato = False  # la riga di chiusura si scrive UNA volta
            self._epitaffio_scritto = False     # l'epitaffio si chiede UNA volta
            self._menu_zaino = False   # il menu mostra l'inventario invece della scena

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
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

        # --- La chat unica: tre registri tipografici -------------------------
        # Il "font diverso" del terminale è lo stile Rich: la narrazione del GM
        # scorre piena (registro di default, con un respiro sopra), la cronaca
        # meccanica (colpi, eventi) è gialla e marcata ⚔, i messaggi di sistema
        # (avvisi, prove, salvataggi) corsivi/colorati. Un solo widget: #log.

        def _log(self):
            return self.query_one("#log", RichLog)

        def _chat_narrazione(self, testo: str) -> None:
            from rich.markup import escape

            rl = self._log()
            rl.write("")
            rl.write("[dim]─── il GM ───────────────────────────────[/]")
            rl.write(escape(testo))

        def _chat_cronaca(self, riga: str) -> None:
            from rich.markup import escape

            self._log().write(f"[yellow]⚔ {escape(riga)}[/]")

        def _chat_flavor(self, testo: str) -> None:
            """Prosa breve non-gating (apertura scontro, epitaffio): corsiva."""
            from rich.markup import escape

            self._log().write(f"[italic]{escape(testo)}[/]")

        async def on_button_pressed(self, event: Button.Pressed) -> None:
            if self._occupato:
                return  # il GM sta lavorando: l'input riprende a barra spenta
            bid = event.button.id or ""
            if bid == "esci":
                self.exit()
            elif bid == "zaino-chiudi":
                self._menu_zaino = False
                await self._mostra(self.sessione.avanza(), self.cronaca.preleva())
            elif bid.startswith("zaino-"):
                await self._toggle_equip(bid[len("zaino-"):])
            elif bid.startswith("opz-"):
                await self._agisci(int(bid.split("-", 1)[1]))

        async def _agisci(self, indice: int) -> None:
            # host→motore: intento tipizzato in coda, poi il turno del motore (C-7).
            fase_prima = self.fase_corrente
            self.sessione.coda.accoda(PlayerChoseOption(indice))
            snap = self.sessione.avanza()
            righe = self.cronaca.preleva()
            if not self._morto and (
                not snap.opzioni
                or (snap.fase == "narrazione" and fase_prima == "combattimento")
            ):
                # Menu vuoto ⇒ nuovo turno di narrazione; scontro appena chiuso ⇒
                # il RESOCONTO narrativo dei fatti (Fase 5 — il feedback che prima
                # mancava: nemico sconfitto, fuga o vittoria raccontati).
                snap = await self._con_attesa(self.sessione.prossima_narrazione())
            await self._mostra(snap, righe)
            if snap.fase == "combattimento" and fase_prima != "combattimento":
                # APERTURA cinematografica IN CODA al feedback deterministico: la
                # riga «Lo scontro ha inizio.» è già nel log e lo scontro è già
                # giocabile — questa prosa arriva quando arriva (mai bloccante).
                testo = await self.sessione.prosa_apertura_scontro()
                if testo:
                    self._chat_flavor(testo)
            if self._morto and not self._epitaffio_scritto:
                self._epitaffio_scritto = True
                testo = await self.sessione.epitaffio()
                if testo:
                    self._chat_flavor(testo)

        # --- Zaino ed equip: la demo del canale loot→zaino→indosso (porte vere) ---

        async def action_zaino(self) -> None:
            """Apre l'inventario nel menu (solo in narrazione, da vivi): un bottone
            per fonte posseduta — Indossa/Togli passano dalle porte della sessione,
            il phase-gate resta del motore."""
            if self._morto or self._occupato or self.fase_corrente != "narrazione":
                return
            self._menu_zaino = True
            await self._monta_zaino()

        async def _monta_zaino(self) -> None:
            menu = self.query_one("#menu", Horizontal)
            await menu.remove_children()
            fonti = self.sessione.scheda().zaino
            indossate = set(self.sessione.fonti_indossate())
            bottoni = [
                Button(
                    ("Togli " if f in indossate else "Indossa ") + etichetta_oggetto(f),
                    id=f"zaino-{f}",
                    variant="warning" if f in indossate else "success",
                )
                for f in fonti
            ]
            bottoni.append(Button("Torna alla scena", id="zaino-chiudi"))
            await menu.mount(*bottoni)
            if not fonti:
                self.query_one("#log", RichLog).write(
                    "[dim]Zaino vuoto: il bottino arriva dagli scontri vinti.[/]"
                )

        async def _toggle_equip(self, fonte: str) -> None:
            rl = self.query_one("#log", RichLog)
            if fonte in set(self.sessione.fonti_indossate()):
                snap = self.sessione.togli(fonte)
                rl.write(f"Togli {etichetta_oggetto(fonte)}: i suoi effetti svaniscono.")
            else:
                snap = self.sessione.equipaggia(fonte)
                rl.write(
                    f"Indossi {etichetta_oggetto(fonte)}: modificatori e mosse "
                    f"concesse sono attivi."
                )
            stato = "  ·  ".join(snap.stato) if snap.stato else "—"
            self.query_one("#stato", Static).update(f"[b]\\[{snap.fase}][/b]  {stato}")
            await self._monta_zaino()          # il menu resta sull'inventario

        # --- Scheda: la proiezione completa del contratto, nel log ---------------

        def action_scheda(self) -> None:
            if self._occupato:
                return
            s = self.sessione.scheda()
            rl = self.query_one("#log", RichLog)
            rl.write(f"[b]— SCHEDA di {s.nome} —[/b]  piano {s.livello} · tick {s.tick_piano}")
            rl.write(f"HP {s.hp}/{s.hp_max} · mana {s.mana}/{s.mana_max}")
            primarie = "  ".join(f"{k} {v}" for k, v in s.primarie.items())
            occulte = ", ".join(s.primarie_occulte) or "—"
            rl.write(f"Primarie: {primarie}  [dim](occulte: {occulte})[/]")
            rl.write("Derivate: " + "  ".join(f"{k} {v}" for k, v in s.derivate.items()))
            for sk in s.skills:
                pronta = "pronta" if sk.pronta else f"in ricarica ({sk.cd_residuo})"
                costo = f" · {sk.costo_mana} mana" if sk.costo_mana else ""
                rl.write(f"  • {sk.etichetta} — {pronta}{costo}")
            indosso = ", ".join(
                etichetta_oggetto(f) for f in self.sessione.fonti_indossate()
            ) or "niente"
            zaino = ", ".join(etichetta_oggetto(f) for f in s.zaino) or "vuoto"
            rl.write(f"Indosso: {indosso}  ·  Zaino: {zaino}  [dim](Z per gestirlo)[/]")

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
            stato = "  ·  ".join(snap.stato) if snap.stato else "—"
            self.query_one("#stato", Static).update(f"[b]\\[{snap.fase}][/b]  {stato}")
            rl = self.query_one("#log", RichLog)
            # La cronaca meccanica PRIMA della prosa: i fatti (colpi, eventi) si
            # leggono nell'ordine in cui il motore li ha risolti, poi il GM narra.
            for r in righe:
                self._chat_cronaca(r)
            # Un click rifiutato in combattimento non resta mai muto: il motivo
            # (mossa non pagabile, scontro concluso) arriva dalla sessione.
            rifiuto = getattr(self.sessione, "ultimo_rifiuto", None)
            if rifiuto:
                from rich.markup import escape

                rl.write(f"[yellow italic]✋ {escape(rifiuto)}[/]")
            if snap.prosa:
                self.prosa_corrente = snap.prosa
                self._chat_narrazione(snap.prosa)
            # Il degrado non resta muto (audit 2026-08-07): se il turno è il pacchetto
            # neutro di fallback, il giocatore lo LEGGE — prima lo si scopriva solo
            # riconoscendo a occhio «Sagoma indistinta».
            msg = getattr(self.sessione, "ultimo_messaggio", None)
            if msg is not None and msg is not self._msg_visto:
                self._msg_visto = msg
                if getattr(msg, "fallback", False):
                    self._avvisi_fallback += 1
                    rl.write(
                        "[yellow]⚠ Il GM non ha risposto (rete, refusal o proposta "
                        "respinta dal gate): turno neutro di ripiego. Il consumo "
                        "dettagliato appare all'uscita.[/]"
                    )
                # La PROVA diventa parole: classe, stat, esito e margine — la
                # texture «di un soffio» che il contratto porta e nessuna
                # superficie mostrava (giro 2026-08-07).
                prova = getattr(msg, "prova", None)
                if prova is not None:
                    if prova.esito is None:
                        esito = "inquadrata"
                    else:
                        esito = "RIUSCITA" if prova.esito else "FALLITA"
                    grado = getattr(getattr(prova, "grado", None), "value", "") or ""
                    coda = f" — margine {prova.margine}" if prova.margine is not None else ""
                    if grado:
                        coda += f", {grado.replace('_', ' ')}"
                    rl.write(
                        f"[cyan]🎲 Prova di {prova.stat} (classe {prova.classe}): "
                        f"{esito}{coda}.[/]"
                    )
            self._menu_zaino = False           # la scena riprende sempre il menu
            menu = self.query_one("#menu", Horizontal)
            await menu.remove_children()
            if self._morto:
                rl.write("[b red]💀 Sei morto — permadeath, run terminata.[/]")
                await menu.mount(Button("Esci (Q)", id="esci", variant="error"))
                return
            # Il TERMINALE si verbalizza (giro 2026-08-07): la vittoria della run
            # era completamente muta — l'ultima riga letta era una discesa verso
            # un piano inesistente.
            if snap.terminale is not None:
                if not self._terminale_annunciato:
                    self._terminale_annunciato = True
                    rl.write(f"[b green]{_riga_terminale(snap.terminale)}[/b green]")
                await menu.mount(Button("Esci (Q)", id="esci", variant="success"))
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
    """Delega al composition root del pacchetto provider (`provider.root`): la
    politica fake/live, il cablaggio forte+veloce e il tally condiviso non sono
    più affare dell'host TUI — questo alias sopravvive per compat coi chiamanti."""
    from provider import scegli_provider

    return scegli_provider(argv)


def _scegli_sessione(argv: list[str], provider, directory=None):
    """Nuova partita, o RIPRESA con `--riprendi [uuid]` (senza uuid: l'ultimo save).

    Due buchi chiusi qui (giro 2026-08-07): il tasto Salva scriveva in una
    tempdir usa-e-getta (il default di `costruisci_sessione` è una cartella
    demo) e NESSUN host chiamava mai `carica_sessione` — la persistenza era
    raggiungibile solo in scrittura. `directory` None → la cartella salvataggi
    vera dell'installazione."""
    from main import DIRECTORY_SALVATAGGI, carica_sessione, elenca_crawler

    directory = directory or DIRECTORY_SALVATAGGI
    if "--riprendi" in argv:
        indice = argv.index("--riprendi")
        uuid = None
        if len(argv) > indice + 1 and not argv[indice + 1].startswith("-"):
            uuid = argv[indice + 1]
        if uuid is None:
            vive = [v for v in elenca_crawler(directory) if not v.corrotta]
            if not vive:
                raise SystemExit(
                    "[gioca] nessuna partita da riprendere: la cartella salvataggi è vuota"
                )
            uuid = max(vive, key=lambda v: v.timestamp).uuid
        sessione = carica_sessione(uuid=uuid, directory=directory, provider=provider)
        if sessione is None:
            raise SystemExit(f"[gioca] save illeggibile o corrotto: {uuid}")
        print(f"[gioca] ripresa: {sessione.etichetta} — piano "
              f"{sessione.scheda().livello}")
        return sessione
    seed = 1
    if "--seed" in argv:
        seed = int(argv[argv.index("--seed") + 1])
    return costruisci_sessione(seed=seed, provider=provider, directory=directory)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover (entry point)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    provider, etichetta = _scegli_provider(argv)
    print(f"[gioca] {etichetta}")
    sessione = _scegli_sessione(argv, provider)
    app = _costruisci_app(sessione)
    app.sub_title = etichetta  # il giocatore VEDE con quale GM sta giocando
    app.run()
    # Il tally non si butta più via: una riga a fine sessione dice quanto si è
    # speso e PERCHÉ eventuali turni sono degradati (trasporto vs generazione).
    consumo = getattr(provider, "consumo", None)
    if consumo is not None:
        print(f"[gioca] {consumo.riassunto()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
