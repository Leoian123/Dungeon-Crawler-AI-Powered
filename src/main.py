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
import os
import random
import tempfile
import time
from pathlib import Path
from typing import Callable
from uuid import uuid4

from contracts import (
    AnomalyTriggered,
    Archetipo,
    Blocco,
    BusEventi,
    ClasseProva,
    CombatResolved,
    CrawlerVista,
    SchedaVista,
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
    acc_eff,
    atk_eff,
    attacco,
    carica_archivio,
    componi_opzioni_scena,
    consuma_messaggi,
    def_eff,
    dissolvi_mob,
    esegui_turno_gm,
    eva_eff,
    in_combattimento,
    indice_crawler,
    ingaggia_combattimento,
    iniziativa,
    livello_corrente,
    mappa_corrente,
    mappa_to_dict,
    master_seed,
    max_hp,
    messaggi_da_archivio,
    messaggi_pendenti,
    mob_corrente,
    prepara_riepilogo,
    proietta_scheda,
    protagonista,
    salva_run,
    stat_eff,
    tempo_piano_corrente,
    tenta_disimpegno,
    tick,
    travasa,
)
from provider import FakeProvider

# Menu di combattimento (MVP). Il menu di NARRAZIONE non è più cablato qui: lo compone
# il MOTORE dalla scena (`componi_opzioni_scena` sulla mappa) — la mappa dispone.
_MENU_COMBATTIMENTO = (OpzioneVista(indice=0, etichetta="Attacca", tipo=TipoAzione.COMBATTI),)

# La cartella dei crawler salvati (slot = crawler, H §1). I doc non fissano il
# percorso: default = `salvataggi/` alla radice del repo (gitignored), override
# con la variabile d'ambiente DCC_SAVE_DIR. L'elenco è uno scan delle intestazioni
# (H §5), mai un registro.
DIRECTORY_SALVATAGGI = Path(
    os.environ.get("DCC_SAVE_DIR") or Path(__file__).resolve().parent.parent / "salvataggi"
)


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
        # Cablaggio comune: il costruttore NON entra in run — lo fanno i factory
        # `nuova` (il protagonista nasce) e `da_salvataggio` (si deserializza),
        # al confine guscio→run (E-5).
        self.provider = provider
        self.rng = random.Random(seed)
        self.guscio = Guscio(directory)
        self.bus = self.guscio.bus
        self.coda = None  # CodaIntenti: nasce all'ingresso in run (dai factory)
        self.archivio: Archivio | None = None
        self.memoria: MemoriaTurni | None = None
        self.uuid = ""
        self.etichetta = ""  # il nome del crawler: etichetta dello slot di save
        self.ultimo_messaggio: MessaggioGM | None = None
        # Callback (etichetta, frazione 0..1) per la barra di attesa dell'host: la
        # pipeline la chiama a ogni stadio; l'host la imposta, il motore non sa di UI.
        self.on_avanzamento = None
        self._chiusa = False  # run conclusa (esci/terminale): le porte si spengono
        self._opzioni: tuple[OpzioneVista, ...] = ()
        self._scena: tuple[OpzioneScena, ...] = ()  # binding indice→azione di scena
        self._istanza: IstanzaCombattimento | None = None
        self._fatti_scontro: FattiScontro | None = None  # handoff scontro→GM
        self._nome_mob = ""

    @classmethod
    def nuova(
        cls,
        provider,
        *,
        directory: Path,
        nome: str = "Carl",
        seed: int = 0,
        n_stanze: int | None = None,
    ) -> "SessioneGioco":
        """Nuova run: il protagonista NASCE al confine guscio→run. L'uuid identifica
        lo slot di save (slot = crawler, H §1); il nome ne è l'etichetta."""
        sessione = cls(provider, directory=directory, seed=seed)
        sessione.uuid = uuid4().hex[:8]
        sessione.etichetta = nome
        sessione.guscio.nuova_partita(
            uuid=sessione.uuid, destrezza=10, hp=30, seed=seed, n_stanze=n_stanze
        )
        sessione.coda = sessione.guscio.coda
        # La pipeline GM: l'Archivio (firma→record) e la memoria di run FRESCHI.
        sessione.archivio = Archivio(master_seed=master_seed(), model_id=MODEL_ID_DEFAULT)
        sessione.memoria = MemoriaTurni()
        return sessione

    @classmethod
    def da_salvataggio(
        cls, provider, *, directory: Path, uuid: str, seed: int = 0
    ) -> "SessioneGioco | None":
        """Riapre una run sospesa. `None` se il save è illeggibile (MENU intatto,
        H-12). L'Archivio di sessione RIPARTE dal sidecar: la cache firma→turno
        resta intatta (stanze già narrate RILETTE, la storia non si riscrive) e la
        memoria GM si RIDERIVA (la chat non si salva mai — H §11)."""
        sessione = cls(provider, directory=directory, seed=seed)
        if not sessione.guscio.carica(uuid):
            return None
        sessione.uuid = uuid
        sessione.coda = sessione.guscio.coda
        sidecar = carica_archivio(directory, uuid)
        sessione.archivio = sidecar or Archivio(
            master_seed=master_seed(), model_id=MODEL_ID_DEFAULT
        )
        sessione.memoria = MemoriaTurni.ricostruisci(sessione.archivio)
        sessione.etichetta = next(
            (v.etichetta for v in indice_crawler(directory) if v.uuid == uuid), uuid
        )
        messaggi = sessione.ricostruisci_thread()
        if messaggi:
            sessione.ultimo_messaggio = messaggi[-1]
        sessione._sincronizza_scena()
        return sessione

    # --- Porte verso l'host ---------------------------------------------------

    async def prossima_narrazione(self) -> SnapshotVista:
        """Coroutine host-agnostica (un worker UI o `asyncio.run` la `await`-a, C-6).

        Il turno passa dalla PIPELINE GM (`esegui_turno_gm`): fascicolo → ideazione →
        composizione (gating+gate) → limatura → scrittura (materializza al reveal,
        spesa tempo, memoria, Archivio). La stanza già visitata RILEGGE il suo turno
        congelato (firma, zero chiamate). I fatti di uno scontro appena chiuso entrano
        nel fascicolo (risolvi prima, narra dopo)."""
        self._guardia_aperta()
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
        self._guardia_aperta()
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
        self._guardia_aperta()
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
        GM congelati) viaggia nel sidecar — non viene più azzerato. Etichetta e
        timestamp alimentano l'indice dell'hub (H §5)."""
        self._guardia_aperta()
        salva_run(
            self.guscio.directory,
            archivio=self.archivio,
            model_id=MODEL_ID_DEFAULT,
            etichetta=self.etichetta,
            timestamp=time.time(),
            esplorazione=mappa_to_dict(),
        )
        return "Partita salvata."

    # --- Ciclo di vita della run (hub): scheda, thread, uscita, terminale -------

    def _guardia_aperta(self) -> None:
        if self._chiusa:
            raise RuntimeError("sessione chiusa: la run è già stata conclusa")

    def ricostruisci_thread(self) -> list[MessaggioGM]:
        """Il thread dei turni GM congelati (per l'host, al caricamento): la chat
        non si salva, si RIDERIVA dall'Archivio (H §11)."""
        return messaggi_da_archivio(self.archivio)

    def scheda(self) -> SchedaVista:
        """La scheda del protagonista per la UI del giocatore: numeri PALESI ammessi
        (a differenza della proiezione per l'AI). Visibilità applicata a monte:
        `primarie` = solo PALESI (effettive), occulte per nome, fortuna MAI."""
        self._guardia_aperta()
        pent, marker, scheda = protagonista()
        proiezione = proietta_scheda(pent)
        return SchedaVista(
            uuid=marker.id_dominio,
            nome=self.etichetta,
            vivo=scheda.vivo,
            hp=scheda.punti_vita,
            hp_max=max_hp(pent),
            descrittori=proiezione.descrittori,
            primarie=dict(proiezione.primarie),
            primarie_occulte=proiezione.primarie_occulte,
            derivate={
                "attacco": attacco(pent),
                "iniziativa": iniziativa(pent),
                "colpo": atk_eff(pent),
                "difesa": def_eff(pent),
                # Evasione/accuratezza sono GRANDEZZE (stat × coefficiente di
                # geometria, §5.3-§5.4), non probabilità: si mostrano arrotondate.
                "evasione": int(round(eva_eff(pent))),
                "accuratezza": int(round(acc_eff(pent))),
            },
            livello=livello_corrente(),
            tick_piano=tempo_piano_corrente(),
        )

    def esci(self) -> str:
        """Salva-ed-esci (terminale 6c): l'Archivio di SESSIONE va nel sidecar
        (mai il fallback del guscio), con etichetta e timestamp per l'indice.
        Dopo, la sessione è chiusa: run-World smontato, porte spente."""
        self._guardia_aperta()
        self.guscio.esci_volontariamente()
        self.guscio.concludi(
            archivio=self.archivio, etichetta=self.etichetta, timestamp=time.time()
        )
        self._chiusa = True
        return "Partita salvata: puoi riprenderla dall'hub."

    def chiudi_terminale(self) -> str:
        """Chiusura della run TERMINATA (morte 6a / piano completato 6b): il guscio
        ha già rilevato il terminale sul bus; qui l'hand-off — che INVALIDA il save
        (permadeath, H-20) — e il teardown."""
        self._guardia_aperta()
        self.guscio.concludi()
        self._chiusa = True
        return "Run conclusa: lo slot è stato ritirato."

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
    """Contenuto scriptato per il provider fake (offline) — SOLO offline: il GM live
    genera il suo. Esauriti i turni, l'orchestrazione degrada al fallback
    deterministico (turno neutro): il gioco non si blocca mai.

    IL GIRO DELLA FALSA IDRA (piano 1, otto stanze, un turno per stanza in ordine
    di visita): i manifesti promettono "L'IDRA DEL PRIMO PIANO — TERRORE A NOVE
    TESTE", ma ogni stanza rivela un'altra testa FINTA della truffa. Ogni turno
    arruola un mob DIVERSO (archetipo × grado × blocchi → profilo calibrato dal
    motore): è anche il banco di prova del reclutamento per-stanza."""
    combatti_o_scappa = [
        Opzione(tipo=TipoAzione.COMBATTI, etichetta="Combatti"),
        Opzione(tipo=TipoAzione.SCAPPA, etichetta="Scappi"),
    ]
    voci: list[tuple[str, Archetipo, Grado, list[Blocco], str, str, Durata]] = [
        (
            "Un corridoio umido gocciola luce verde su un manifesto: «L'IDRA DEL "
            "PRIMO PIANO — TERRORE A NOVE TESTE». Sotto il manifesto, uno Slime "
            "Mangiascarti ribolle tra rifiuti e un Rolex digerito.",
            Archetipo.SLIME, Grado.BRONZO, [Blocco.VELENO],
            "Slime Mangiascarti",
            "Verde, acido, vagamente offeso dalla tua presenza.",
            Durata.TURNO,
        ),
        (
            "Un bancone di ossa e nastro adesivo: «BIGLIETTI PER L'IDRA — PAURA "
            "GARANTITA O NIENTE RIMBORSO». Il goblin dietro il bancone ti squadra "
            "e raddoppia il prezzo.",
            Archetipo.GOBLIN, Grado.BRONZO, [],
            "Goblin Bigliettaio",
            "Cappellino da giostraio, sorriso a ventiquattro denti, tutti in affitto.",
            Durata.UN_ATTIMO,
        ),
        (
            "Fili, aghi, cartapesta. Uno scheletro cuce la QUARTA testa dell'idra "
            "canticchiando: le altre tre pendono dal soffitto, ancora senza occhi.",
            Archetipo.SCHELETRO, Grado.BRONZO, [Blocco.RIGENERAZIONE],
            "Scheletro Sarto",
            "Ditale d'ottone sul metacarpo, pessimo gusto in fatto di bottoni.",
            Durata.TURNO,
        ),
        (
            "Due slime impilati in un impermeabile fingono di essere un'idra a due "
            "teste. Il travestimento regge finché quello sopra non sbadiglia.",
            Archetipo.SLIME, Grado.ARGENTO, [Blocco.VELENO, Blocco.RIGENERAZIONE],
            "Gemelli nel Trench",
            "Uno fa la voce grossa, l'altro fa la voce piccola. Nessuno fa l'idra.",
            Durata.UN_POCHINO,
        ),
        (
            "Un teatrino di bastoni e carrucole: teste d'idra di pezza ruggiscono "
            "in playback mentre un goblin suda dietro le quinte, sei corde in mano.",
            Archetipo.GOBLIN, Grado.ARGENTO, [Blocco.RIGENERAZIONE],
            "Goblin Burattinaio",
            "Artista incompreso: lo spettacolo continua, si rialza sempre.",
            Durata.TURNO,
        ),
        (
            "Tre scheletri su una pedana provano IL RUGGITO in canone a tre voci, "
            "sollevando nuvole di polvere d'osso che pizzica in gola. Il basso è "
            "stonato e gli altri due fingono di non conoscerlo.",
            Archetipo.SCHELETRO, Grado.ARGENTO, [Blocco.VELENO],
            "Coro delle Ossa",
            "Fanno anche matrimoni e funerali. Soprattutto funerali.",
            Durata.UN_ATTIMO,
        ),
        (
            "Una vasca gorgogliante dove le «teste di ricambio» crescono come "
            "lievito madre. Lo slime enorme sul fondo ti guarda con orgoglio "
            "materno e zero rimorsi.",
            Archetipo.SLIME, Grado.ARGENTO, [Blocco.VELENO],
            "Slime Madre",
            "Ogni testa finta del piano è farina del suo sacco. Letteralmente.",
            Durata.TURNO,
        ),
        (
            "Il gran finale: un costume da idra a nove teste, corna dipinte d'oro, "
            "e dentro un goblin col megafono. «Lo spettacolo DEVE continuare», "
            "ringhia. Il mito del piano era tutto qui.",
            Archetipo.GOBLIN, Grado.ARGENTO, [Blocco.VELENO, Blocco.RIGENERAZIONE],
            "Il Regista",
            "Ha truffato interi piani. L'oro sulle corna è vernice da cantiere.",
            Durata.UN_POCHINO,
        ),
    ]
    return [
        TurnoNarrazione(
            prosa=prosa,
            entita=EntitaGenerata(
                archetipo=archetipo,
                grado=grado,
                blocchi=blocchi,
                nome=nome,
                descrizione=descrizione,
            ),
            opzioni=combatti_o_scappa,
            durata=durata,
        )
        for prosa, archetipo, grado, blocchi, nome, descrizione, durata in voci
    ]


def _provider_o_fake(provider):
    """`provider=None` ⇒ **FakeProvider scriptato** (offline): il default è SICURO —
    mai una chiamata di rete implicita (test inclusi). Il backend live si INIETTA
    esplicitamente (è l'host a sceglierlo dall'ambiente).

    Il FakeProvider è FIFO **per chiamata**: la pipeline GM fa (fino a) 4 chiamate per
    turno, quindi il copione scripta gli stadi in ordine — ideazione degradata (`None`),
    IL turno gating, limatura e distillazione degradate. Esaurita la coda, ogni stadio
    riceve `None`: gli ancillari degradano, la gating cade sul fallback atomico."""
    if provider is not None:
        return provider
    risposte: list[object] = []
    for turno in _turni_scriptati():
        risposte += [None, turno.model_dump(), None, None]
    return FakeProvider(risposte)


def costruisci_sessione(
    *, nome: str = "Carl", seed: int = 0, directory: Path | None = None, provider=None
) -> SessioneGioco:
    """Cabla il provider → `SessioneGioco.nuova` (la porta del motore vista dall'host).
    Senza `directory` la run vive in una tempdir usa-e-getta (demo/test).

    SOLO offline (provider=None → FakeProvider): il piano ha tante stanze quanti
    sono i turni del copione — il giro della Falsa Idra copre tutte le stanze.
    Col GM live la topologia resta quella di calibrazione (`MAPPA_STANZE`)."""
    directory = directory or Path(tempfile.mkdtemp(prefix="dcc-"))
    n_stanze = len(_turni_scriptati()) if provider is None else None
    return SessioneGioco.nuova(
        _provider_o_fake(provider),
        directory=directory,
        nome=nome,
        seed=seed,
        n_stanze=n_stanze,
    )


def carica_sessione(
    *, uuid: str, directory: Path | None = None, provider=None
) -> SessioneGioco | None:
    """Riapre un crawler sospeso dalla cartella dei salvataggi (`None` se
    illeggibile). Stessa politica provider di `costruisci_sessione`."""
    directory = directory or DIRECTORY_SALVATAGGI
    return SessioneGioco.da_salvataggio(
        _provider_o_fake(provider), directory=directory, uuid=uuid
    )


def elenca_crawler(directory: Path | None = None) -> list[CrawlerVista]:
    """L'elenco dei crawler salvati come DTO di membrana (per l'host, che non può
    toccare il motore). Scan delle sole intestazioni (H §5); voce corrotta =
    mostrata ma non caricabile (H-22)."""
    directory = directory or DIRECTORY_SALVATAGGI
    if not directory.exists():
        return []
    return [
        CrawlerVista(
            uuid=v.uuid,
            etichetta=v.etichetta,
            profondita=v.profondita,
            timestamp=v.timestamp,
            corrotta=v.corrotta,
        )
        for v in indice_crawler(directory)
    ]


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
