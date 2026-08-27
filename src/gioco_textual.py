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
            Binding("k", "skill", "Skill"),
            Binding("b", "bacheca", "Bacheca"),
            Binding("o", "obiettivi", "Obiettivi"),
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
            # (l'epitaffio non ha più un flag di host: la sua unicità è del motore,
            #  che dichiara il battito una volta sola — vedi `_segna_prosa`.)
            self._menu_zaino = False   # il menu mostra l'inventario invece della scena
            self._in_scena = False     # scena sociale aperta: l'input raccoglie BATTUTE

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
            # Le notifiche-obiettivo ARRETRATE (fase O4, §O-5): sblocchi di
            # sessioni passate mai mostrati — si scrivono al boot come appena
            # accaduti, poi la coda è vuota (il live passa dalla cronaca).
            rl = self.query_one("#log", RichLog)
            for notifica in self.sessione.drena_notifiche_obiettivi():
                rl.write(
                    f"[b]★ Nuovo obiettivo: {notifica.titolo}![/b] "
                    f"{notifica.testo} Ricompensa: {notifica.ricompensa_testo}"
                )
            await self._mostra(snap, [])
            # Anche il PRIMO turno può aprire uno scontro (imboscata del dado-evento):
            # il trailer è dovuto già qui, non solo dopo una scelta del giocatore.
            await self._drena_prosa()

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

        async def _drena_prosa(self) -> None:
            """Svuota la coda dei battiti fuori-banda del motore (`prossima_prosa`).

            L'host non decide più QUANDO un trailer, una vestizione o un epitaffio
            siano dovuti — lo dichiara il motore. Qui resta solo il REGISTRO
            tipografico: la vestizione del premio porta il suo ✦, il resto è
            corsivo. Mai bloccante: la cronaca deterministica è già a video."""
            from contracts import TipoProsa

            while True:
                prosa = await self.sessione.prossima_prosa()
                if prosa is None:
                    return
                if prosa.tipo is TipoProsa.PREMIO:
                    self._chat_flavor(f"✦ {prosa.testo}")
                else:
                    self._chat_flavor(prosa.testo)

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
            await self._drena_prosa()
            # Drenaggio SILENZIOSO delle notifiche-obiettivo: il live è appena
            # passato dalla cronaca (★); qui si svuota la coda così un load
            # futuro mostra solo il mai-visto (§O-5).
            if not self._morto:
                self.sessione.drena_notifiche_obiettivi()
            if snap.scena_aperta and not self._in_scena:
                # PARLAMENTA riuscito: la scena è aperta — l'input raccoglie
                # BATTUTE finché il motore non la chiude (o il giocatore tronca).
                self._entra_in_scena()
            elif self._in_scena and not snap.scena_aperta:
                # L'USCITA speculare (caccia-2, 2026-08-16): un'azione di menu a
                # scena aperta (Combatti, Scappi, Muovi…) la ABBANDONA nel
                # motore — senza questo ramo la TUI restava in modo-scena con
                # l'input-battute attivo, e l'Invio successivo finiva su
                # `battuta_parlamento` senza scena: RuntimeError, panic Textual,
                # sessione persa. La sincronia dei modi è dell'host.
                self._in_scena = False
                campo = self.query_one("#azione", Input)
                campo.value = ""
                campo.remove_class("attiva")

        def _entra_in_scena(self) -> None:
            self._in_scena = True
            campo = self.query_one("#azione", Input)
            campo.value = ""
            campo.placeholder = "Cosa dici? (vuoto = tronchi la conversazione)"
            campo.add_class("attiva")
            campo.focus()

        # --- Zaino ed equip: la demo del canale loot→zaino→indosso (porte vere) ---

        async def action_zaino(self) -> None:
            """Apre l'inventario nel menu (solo in narrazione, da vivi): un bottone
            per fonte posseduta — Indossa/Togli passano dalle porte della sessione,
            il phase-gate resta del motore."""
            if self._morto or self._occupato or self.fase_corrente != "narrazione":
                return
            self._menu_zaino = True
            await self._monta_zaino()

        @staticmethod
        def _decora_riga_zaino(riga) -> str:
            """La vestizione del dato tipato (§B-4): tacca di fattura (l'onesto
            tace), grado in coda — l'host mostra, mai deduce dal nome."""
            tacca = {"pregiato": "✦ ", "scarto": "▽ "}.get(riga.qualita, "")
            grado = f" [{riga.grado}]" if riga.grado else ""
            return f"{tacca}{etichetta_oggetto(riga.fonte)}{grado}"

        async def _monta_zaino(self) -> None:
            menu = self.query_one("#menu", Horizontal)
            await menu.remove_children()
            righe = self.sessione.zaino_vista()
            bottoni = []
            for riga in righe:
                if riga.tipo == "consumabile":
                    # Il canale B in TUI: il consumabile si USA, mai si indossa
                    # (il motore rifiuterebbe il toggle con un click muto).
                    bottoni.append(Button(
                        "Usa " + self._decora_riga_zaino(riga),
                        id=f"zaino-{riga.fonte}", variant="primary",
                    ))
                else:
                    bottoni.append(Button(
                        ("Togli " if riga.indossato else "Indossa ")
                        + self._decora_riga_zaino(riga),
                        id=f"zaino-{riga.fonte}",
                        variant="warning" if riga.indossato else "success",
                    ))
            bottoni.append(Button("Torna alla scena", id="zaino-chiudi"))
            await menu.mount(*bottoni)
            if not righe:
                self.query_one("#log", RichLog).write(
                    "[dim]Zaino vuoto: il bottino arriva dagli scontri vinti.[/]"
                )

        async def _toggle_equip(self, fonte: str) -> None:
            rl = self.query_one("#log", RichLog)
            righe = {r.fonte: r for r in self.sessione.zaino_vista()}
            riga = righe.get(fonte)
            if riga is not None and riga.tipo == "consumabile":
                snap = self.sessione.usa(fonte)
                consumato = fonte not in {
                    r.fonte for r in self.sessione.zaino_vista()
                }
                if consumato:
                    # Il dettaglio («+12 HP») è già passato dalla cronaca tipata.
                    rl.write(f"Usi {etichetta_oggetto(fonte)}.")
                else:
                    rl.write(
                        f"[dim]{etichetta_oggetto(fonte)} resta chiuso: "
                        "non ne hai bisogno adesso.[/]"
                    )
            elif fonte in set(self.sessione.fonti_indossate()):
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
                livello = f" · Lv {sk.livello}" if sk.livello > 1 else ""
                rl.write(f"  • {sk.etichetta} — {pronta}{costo}{livello}")
            indosso = ", ".join(
                etichetta_oggetto(f) for f in self.sessione.fonti_indossate()
            ) or "niente"
            zaino = ", ".join(etichetta_oggetto(f) for f in s.zaino) or "vuoto"
            rl.write(f"Indosso: {indosso}  ·  Zaino: {zaino}  [dim](Z per gestirlo)[/]")

        def action_skill(self) -> None:
            """Il registro delle competenze nel log (nodo S): il sistema conta
            tutto, e il menu lo elenca tutto — junk compreso, che è metà del
            tono. Livello e usi li deriva il motore, qui si mostrano."""
            if self._occupato:
                return
            rl = self.query_one("#log", RichLog)
            righe = self.sessione.skill_vista()
            if not righe:
                rl.write("[dim]Nessuna skill in catalogo per questa run.[/]")
                return
            rl.write(f"[b]— SKILL {len(righe)} —[/b]")
            for r in sorted(righe, key=lambda r: (-r.livello, r.nome)):
                dominio = f" [dim]({r.dominio})[/]" if r.dominio else ""
                usi = f" · usi {r.usi}" if r.usi else ""
                rl.write(f"  • [b]Lv {r.livello}[/b] {r.nome}{dominio}{usi}")

        def action_obiettivi(self) -> None:
            """L'elenco obiettivi nel log (fase O4): sbloccati in chiaro,
            chiusi velati — e il promemoria delle box in coda."""
            if self._occupato:
                return
            rl = self.query_one("#log", RichLog)
            elenco = self.sessione.obiettivi_vista()
            if not elenco:
                rl.write("[dim]Nessun obiettivo in catalogo per questa run.[/]")
                return
            fatti = sum(1 for v in elenco if v.sbloccato)
            rl.write(f"[b]— OBIETTIVI {fatti}/{len(elenco)} —[/b]")
            for vista in elenco:
                if vista.sbloccato:
                    rl.write(f"  ✓ [b]{vista.titolo}[/b] — {vista.testo}")
                else:
                    rl.write(f"  · {vista.titolo} [dim](ancora velato)[/]")
            box = self.sessione.box_in_coda()
            if box:
                rl.write(f"[dim]Box in coda: {box} — si aprono in safe room.[/]")

        def action_bacheca(self) -> None:
            """La bacheca dei caduti (sovra-run B) nel log: i necrologi
            proiettati dal ledger — leggibili anche in TUI, come nel web."""
            if self._occupato:
                return
            from main import DIRECTORY_SALVATAGGI, bacheca

            rl = self.query_one("#log", RichLog)
            post = bacheca(DIRECTORY_SALVATAGGI)
            if not post:
                rl.write("[dim]La bacheca è vuota: il dungeon attende i suoi "
                         "primi caduti (o vincitori).[/]")
                return
            rl.write("[b]— LA BACHECA DEI CADUTI —[/b]")
            for necrologio in reversed(post[-6:]):  # gli ultimi, i più recenti prima
                rl.write(f"[b]{necrologio.titolo}[/b]")
                for riga in necrologio.corpo.splitlines():
                    rl.write(f"  {riga}")

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
            if self._in_scena:
                # MODALITÀ SCENA (2026-08-16): il testo è una BATTUTA, non
                # un'azione — va alla porta di scena, mai al turno GM (la mina
                # del menu-vuoto). Vuoto = il giocatore tronca la conversazione.
                campo.value = ""
                if not testo:
                    self.sessione.abbandona_parlamento()
                    self._in_scena = False
                    campo.remove_class("attiva")
                    await self._mostra(self.sessione.avanza(), [])
                    return
                self._chat_narrazione(f"— «{testo}»")
                prosa = await self._con_attesa(self.sessione.battuta_parlamento(testo))
                self._chat_narrazione(prosa)
                snap = self.sessione.avanza()
                if not snap.scena_aperta:
                    self._in_scena = False
                    campo.remove_class("attiva")
                    await self._mostra(snap, self.cronaca.preleva())
                else:
                    campo.placeholder = "Cosa rispondi? (vuoto = tronchi)"
                    campo.focus()
                return
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
            # L'azione libera spende tempo: può far scattare l'imboscata (e quindi
            # dovere un trailer) esattamente come una scelta di menu.
            await self._drena_prosa()

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
                Button(
                    # Il livello della skill che governa la mossa (nodo S) è
                    # DATO sull'opzione: la vestizione è dell'host, mai una
                    # concatenazione dentro l'etichetta del contratto.
                    o.etichetta + (
                        f"  [Lv {o.livello}]"
                        if getattr(o, "livello", 1) > 1 else ""
                    ),
                    id=f"opz-{o.indice}", variant="primary",
                )
                for o in snap.opzioni
            ]
            if bottoni:
                await menu.mount(*bottoni)

        def action_salva(self) -> None:
            # Il motore possiede il fatto (l'eccezione tipizzata col messaggio
            # per il giocatore); l'host lo RENDE invece di morirci sopra —
            # prima, S a scontro aperto (o sul death screen, dove la fase resta
            # combattimento per disegno G-11) faceva panic dell'app Textual:
            # sessione persa per un tasto (caccia 2026-08-16).
            from main import RunConclusa, SalvataggioInCombattimento

            rl = self.query_one("#log", RichLog)
            try:
                esito = self.sessione.salva()
            except (RunConclusa, SalvataggioInCombattimento) as e:
                rl.write(f"[yellow italic]✋ {e}[/]")
                return
            rl.write(f"[green]{esito}[/]")

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
    if "--daily" in argv:
        # RUN DEL GIORNO (sovra-run C): il seed lo detta la DATA, lato host —
        # il motore non guarda mai l'orologio (J). La TUI gioca la stagione
        # default (numero 1), come il web senza slug esplicito.
        from datetime import date

        from contracts import seed_del_giorno

        seed = seed_del_giorno(date.today().isoformat(), 1)
        print(f"[gioca] run del giorno {date.today().isoformat()}: seed {seed}")
    fantasmi = ()
    if "--infestata" in argv:
        # DUNGEON INFESTATO (sovra-run D): le sconfitte del ledger locale come
        # fantasmi-lore. Opt-in esplicito, come nel web.
        from main import fantasmi_locali

        fantasmi = fantasmi_locali(directory)
        print(f"[gioca] dungeon infestato: {len(fantasmi)} tracce dal ledger")
    return costruisci_sessione(
        seed=seed, provider=provider, directory=directory, fantasmi=fantasmi
    )


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
    # Il tally PER ROTTA (registro C, chiuso): il totale dice quanto si è speso,
    # queste righe dicono DOVE — e quali rotte degradano (trasporto a parte).
    try:
        rotte = sessione.tally_rotte()
    except Exception:
        rotte = {}
    for nome, (chiamate, degradi) in sorted(rotte.items()):
        deg = f", {degradi} degradi" if degradi else ""
        print(f"[gioca]   {nome}: {chiamate} chiamate{deg}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
