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
    FattiScontro,
    IntentoEsplorazione,
    MessaggioGM,
    MortePersonaggio,
    PlayerDiscende,
    PlayerSiMuove,
    Opzione,
    OpzioneVista,
    PlayerChoseOption,
    Grado,
    RiepilogoAzione,
    SnapshotVista,
    StatId,
    TipoAzione,
    TurnoNarrazione,
)
from guscio import Guscio
from motore import (
    MODEL_ID_DEFAULT,
    Archivio,
    MemoriaTurni,
    OpzioneScena,
    SpecNemico,
    componi_opzioni_scena,
    consuma_messaggi,
    dissolvi_mob,
    esegui_turno_gm,
    in_combattimento,
    ingaggia_combattimento,
    mappa_corrente,
    mappa_to_dict,
    master_seed,
    max_hp,
    messaggi_pendenti,
    mob_corrente,
    prepara_riepilogo,
    proietta_scheda,
    protagonista,
    salva_run,
    stat_eff,
    tenta_disimpegno,
    tick,
    travasa,
)
from provider import FakeProvider

# Menu di combattimento (MVP). Il menu di NARRAZIONE non è più cablato qui: lo compone
# il MOTORE dalla scena (`componi_opzioni_scena` sulla mappa) — la mappa dispone.
_MENU_COMBATTIMENTO = (OpzioneVista(indice=0, etichetta="Attacca", tipo=TipoAzione.COMBATTI),)


class IstanzaCombattimento:
    """L'istanza SEPARATA del combattimento: il modello deterministico con le SUE
    interazioni (FNC §5.2 — la pipeline GM qui non gira mai, G-4).

    Nasce all'ingaggio, pilota il loop deterministico (un `tick` per azione), ascolta
    il bus e **raccoglie i fatti** dello scontro; alla chiusura i `FattiScontro`
    rientrano nel fascicolo del primo turno GM successivo (risolvi prima, narra dopo).
    Le interazioni sono un seam: oggi "Attacca", domani mosse/fuga.
    """

    def __init__(self, bus, *, nemico: str = "") -> None:
        self.bus = bus
        self.nemico = nemico
        self._turni = 0
        self._hp_iniziali = protagonista()[2].punti_vita
        self._conclusa = False
        self._vittoria = False
        self._coppie = [(CombatResolved, self._su_resolved), (MortePersonaggio, self._su_morte)]
        for tipo, handler in self._coppie:
            bus.registra(tipo, handler)

    def _su_resolved(self, evento: CombatResolved) -> None:
        self._conclusa = True
        self._vittoria = bool(getattr(evento, "vittoria", False))

    def _su_morte(self, _evento: MortePersonaggio) -> None:
        self._conclusa = True  # permadeath: lo scontro non si chiude, la run sì

    @property
    def opzioni(self) -> tuple[OpzioneVista, ...]:
        return _MENU_COMBATTIMENTO

    def agisci(self, indice: int) -> None:
        """Un'azione di combattimento = un turno del motore, deterministico e seeded."""
        if not self._conclusa and 0 <= indice < len(self.opzioni):
            tick()
            self._turni += 1

    @property
    def conclusa(self) -> bool:
        return self._conclusa

    def fatti(self) -> FattiScontro:
        """I FATTI dello scontro per il GM (selezione, mai stat vive)."""
        hp_ora = protagonista()[2].punti_vita
        return FattiScontro(
            vittoria=self._vittoria,
            turni=self._turni,
            hp_persi=max(0, self._hp_iniziali - hp_ora),
            nemico=self.nemico,
        )

    def chiudi(self) -> None:
        for tipo, handler in self._coppie:
            try:
                self.bus.deregistra(tipo, handler)
            except ValueError:
                pass
        self._coppie = []


class SessioneGioco:
    """La porta motore↔host per la v1: narrazione async, intenti sul turno, snapshot.

    Possiede il run-World (via `Guscio`) e il provider. Non tiene una macchina di
    modo propria: il "modo" è la verità del motore (`in_combattimento()` + la scena
    composta dalla mappa). Vive nel composition root: può importare il motore —
    l'host (UI o driver headless) no, vi parla solo via porte.
    """

    def __init__(self, provider, *, directory: Path, seed: int = 0) -> None:
        self.provider = provider
        self.rng = random.Random(seed)
        self.guscio = Guscio(directory)
        self.guscio.nuova_partita(uuid="carl", destrezza=10, hp=30, seed=seed)
        self.bus = self.guscio.bus
        self.coda = self.guscio.coda  # CodaIntenti: l'host vi accoda gli intenti
        # La pipeline GM: l'Archivio (firma→record, e il sidecar NON si azzera più al
        # save) e la memoria di run (derivata, mai persistita come chat — H §11).
        self.archivio = Archivio(master_seed=master_seed(), model_id=MODEL_ID_DEFAULT)
        self.memoria = MemoriaTurni()
        self.ultimo_messaggio: MessaggioGM | None = None
        # Callback (etichetta, frazione 0..1) per la barra di attesa dell'host: la
        # pipeline la chiama a ogni stadio; l'host la imposta, il motore non sa di UI.
        self.on_avanzamento = None
        self._opzioni: tuple[OpzioneVista, ...] = ()
        self._scena: tuple[OpzioneScena, ...] = ()  # binding indice→azione di scena
        self._istanza: IstanzaCombattimento | None = None
        self._fatti_scontro: FattiScontro | None = None  # handoff scontro→GM
        self._nome_mob = ""

    # --- Porte verso l'host ---------------------------------------------------

    async def prossima_narrazione(self) -> SnapshotVista:
        """Coroutine host-agnostica (un worker UI o `asyncio.run` la `await`-a, C-6).

        Il turno passa dalla PIPELINE GM (`esegui_turno_gm`): fascicolo → ideazione →
        composizione (gating+gate) → limatura → scrittura (materializza al reveal,
        spesa tempo, memoria, Archivio). La stanza già visitata RILEGGE il suo turno
        congelato (firma, zero chiamate). I fatti di uno scontro appena chiuso entrano
        nel fascicolo (risolvi prima, narra dopo)."""
        if in_combattimento():  # la pipeline GM non gira nello scontro (istanza a parte)
            return self._snapshot_corrente()
        esito = await esegui_turno_gm(
            self.provider,
            archivio=self.archivio,
            memoria=self.memoria,
            rng=self.rng,
            bus=self.bus,
            esito_scontro=self._fatti_scontro,
            avanzamento=self.on_avanzamento,
        )
        if not esito.da_cache:  # un turno riletto non consuma i fatti: li narrerà il prossimo
            self._fatti_scontro = None
        self.ultimo_messaggio = esito.messaggio
        if esito.risultato is not None:
            self._nome_mob = esito.risultato.turno.entita.nome
        self._sincronizza_scena()
        return SnapshotVista(
            prosa=esito.messaggio.prosa,
            opzioni=self._opzioni,
            stato=self._descrittori(),
            fase="narrazione",
        )

    def riepiloga_azione(self, testo: str, tipo: TipoAzione = TipoAzione.ALTRO) -> RiepilogoAzione:
        """La finestra di conferma EDITABILE: 'Stai per…, corretto? Ti prenderà …'.
        Deterministica (calcolatore del tempo + seam skill), zero LLM."""
        return prepara_riepilogo(testo, tipo, self.memoria)

    async def esegui_azione(self, riepilogo: RiepilogoAzione) -> SnapshotVista:
        """Immissione: il testo (eventualmente editato) diventa l'azione del fascicolo
        e il turno GM risponde. Il testo libero NON tocca mai lo stato: viaggia solo
        nel prompt; l'unico ritorno meccanico è il turno gated (enum+budget)."""
        if in_combattimento():
            return self._snapshot_corrente()
        esito = await esegui_turno_gm(
            self.provider,
            archivio=self.archivio,
            memoria=self.memoria,
            rng=self.rng,
            bus=self.bus,
            azione=riepilogo.testo_proposto,
            esito_scontro=self._fatti_scontro,
            avanzamento=self.on_avanzamento,
        )
        if not esito.da_cache:
            self._fatti_scontro = None
        self.ultimo_messaggio = esito.messaggio
        self._sincronizza_scena()
        return SnapshotVista(
            prosa=esito.messaggio.prosa,
            opzioni=self._opzioni,
            stato=self._descrittori(),
            fase="narrazione",
        )

    def avanza(self) -> SnapshotVista:
        """Il **turno del motore** per l'host (IC §7.1) — drenaggio UNIFICATO:

        1. `travasa` (Canale A, l'unico travaso coda→World): il port NON preleva più
           dalla coda in proprio e NON scarta nulla;
        2. consuma SOLO gli intenti di menu (`PlayerChoseOption`) e li interpreta
           sulla fase corrente del motore e sulla scena mostrata;
        3. gli intenti di DOMINIO restano nel World per i sistemi phase-gated: quelli
           di esplorazione si servono su un turno del motore in NARRAZIONE (qui sotto);
           in COMBATTIMENTO attendono la fine dello scontro — la separazione
           esplorazione/combattimento è il phase-gate, non un filtro del port."""
        travasa(self.coda)
        for intento in consuma_messaggi(PlayerChoseOption):
            self._agisci(intento.opzione)
        travasa(self.coda)  # le scelte di scena possono aver accodato intenti di dominio
        if not in_combattimento() and messaggi_pendenti(IntentoEsplorazione):
            tick()  # un atto di esplorazione = un turno del motore (movimento, discesa)
        if self._istanza is not None and self._istanza.conclusa:
            # Chiusura dell'istanza di combattimento: i FATTI passano al prossimo
            # turno GM (risolvi prima, narra dopo — FNC §5.2).
            self._fatti_scontro = self._istanza.fatti()
            self._istanza.chiudi()
            self._istanza = None
        self._sincronizza_scena()
        return self._snapshot_corrente()

    def salva(self) -> str:
        """Salvataggio a mano, in-run (H-6): il World sopravvive, scrittura prima di
        ogni teardown. La mappa viaggia nello slot `esplorazione`; l'Archivio (i turni
        GM congelati) viaggia nel sidecar — non viene più azzerato."""
        salva_run(
            self.guscio.directory,
            archivio=self.archivio,
            model_id=MODEL_ID_DEFAULT,
            esplorazione=mappa_to_dict(),
        )
        return "Partita salvata."

    # --- Interpretazione delle scelte (sulla verità del motore, non su un modo) -

    def _agisci(self, indice: int) -> None:
        if in_combattimento():
            self._agisci_combattimento(indice)
        elif 0 <= indice < len(self._scena):
            self._agisci_narrazione(self._scena[indice])

    def _agisci_narrazione(self, azione: OpzioneScena) -> None:
        if azione.tipo is TipoAzione.SCENDI:
            self.coda.accoda(PlayerDiscende())  # la serve SistemaDiscesa (gate: scala)
            return
        if azione.tipo is TipoAzione.MUOVI and azione.stanza is not None:
            self.coda.accoda(PlayerSiMuove(azione.stanza))  # la serve SistemaMovimento
            return
        if azione.tipo is TipoAzione.SCAPPA:
            # Disimpegno: prova su stat PRIMA di ingaggiare (FNC §5.3, tirata dal motore).
            # La destrezza passa dal fold (GR2-3), non da un campo della scheda.
            pent, _m, _scheda = protagonista()
            if tenta_disimpegno(stat_eff(pent, StatId.DESTREZZA), ClasseProva.BRONZO, self.rng):
                dissolvi_mob()  # fuga riuscita: l'incontro si dissolve, la scena si riapre
                return
        # Combatti (o disimpegno fallito): l'incontro è il nemico DELLA STANZA, arruolato
        # col suo profilo calibrato (Primarie/Corredo/Resistenze). Il fallback per scalari
        # resta solo per robustezza (scena senza mob registrato). Lo scontro è pilotato
        # da un'ISTANZA a parte, creata PRIMA dell'ingaggio (snapshot HP pre-scontro).
        mob = mob_corrente()
        self._istanza = IstanzaCombattimento(self.bus, nemico=self._nome_mob)
        ingaggia_combattimento(
            self.bus,
            nemici=None if mob is not None else [SpecNemico(destrezza=5, punti_vita=3)],
            arruolate=[mob] if mob is not None else None,
            seed=self.rng.randint(0, 10**9),
        )

    def _agisci_combattimento(self, indice: int) -> None:
        if self._istanza is not None:
            self._istanza.agisci(indice)  # l'istanza deterministica possiede lo scontro
        elif 0 <= indice < len(_MENU_COMBATTIMENTO):
            tick()  # difesa: scontro aperto fuori dal port (test/harness)

    def _sincronizza_scena(self) -> None:
        """Riallinea il menu alla verità del motore: in combattimento il menu di
        combattimento; altrimenti la SCENA composta dalla mappa. Scena vuota = stanza
        mai narrata ⇒ menu vuoto ⇒ l'host chiede un turno di narrazione."""
        if in_combattimento():
            self._scena = ()
            self._opzioni = _MENU_COMBATTIMENTO
            return
        self._scena = componi_opzioni_scena()
        self._opzioni = tuple(
            OpzioneVista(indice=i, etichetta=az.etichetta, tipo=az.tipo)
            for i, az in enumerate(self._scena)
        )

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
        hp = f"HP {scheda.punti_vita}/{max_hp(pent)}"  # massimo DERIVATO (§5)
        extra: list[str] = []
        trovata = mappa_corrente()
        if trovata is not None:
            extra.append(f"stanza {trovata[1].stanza_corrente}")
        if self.ultimo_messaggio is not None:
            extra.append(f"tempo: {self.ultimo_messaggio.tempo.etichetta} "
                         f"(t{self.ultimo_messaggio.tempo.tick_correnti})")
        return (hp, *proietta_scheda(pent).descrittori, *extra)


# --- Cronaca del bus: eventi di dominio → righe di testo (headless, read-only) ----
#
# Lo stesso ruolo "consumatore read-only di eventi" che avrà una UI (IC §2.3), qui
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
                grado=Grado.BRONZO,
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


def costruisci_sessione(
    *, seed: int = 0, directory: Path | None = None, provider=None
) -> SessioneGioco:
    """Cabla il provider → `SessioneGioco` (la porta del motore vista dall'host).

    `provider=None` ⇒ **FakeProvider scriptato** (offline): il default è SICURO — mai
    una chiamata di rete implicita (test inclusi). Il backend live si INIETTA
    esplicitamente (è l'host, es. `gioco_textual`, a sceglierlo dall'ambiente).

    Il FakeProvider è FIFO **per chiamata**: la pipeline GM fa (fino a) 4 chiamate per
    turno, quindi il copione scripta gli stadi in ordine — ideazione degradata (`None`),
    IL turno gating, limatura e distillazione degradate. Esaurita la coda, ogni stadio
    riceve `None`: gli ancillari degradano, la gating cade sul fallback atomico."""
    directory = directory or Path(tempfile.mkdtemp(prefix="dcc-"))
    if provider is None:
        risposte: list[object] = []
        for turno in _turni_scriptati():
            risposte += [None, turno.model_dump(), None, None]
        provider = FakeProvider(risposte)
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
