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
    AssetVista,
    Blocco,
    BusEventi,
    ClasseProva,
    ColpoInferto,
    CombatResolved,
    EffettoStatus,
    StatusApplicato,
    TurnoSaltato,
    CrawlerVista,
    MobAsset,
    PianoAsset,
    PianoRisolto,
    SchedaVista,
    Stagione,
    StagioneRisolta,
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
    MobAttivo,
    PianoAttivo,
    StagioneAttiva,
    design_piano_corrente,
    lint_registry,
    nemici_in_scontro,
    prossimo_attivo_e_protagonista,
    richiedi_fuga,
    stagione_corrente,
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
_MENU_COMBATTIMENTO = (
    OpzioneVista(indice=0, etichetta="Attacca", tipo=TipoAzione.COMBATTI),
    OpzioneVista(indice=1, etichetta="Fuggi", tipo=TipoAzione.SCAPPA),
)

# La cartella dei crawler salvati (slot = crawler, H §1). I doc non fissano il
# percorso: default = `salvataggi/` alla radice del repo (gitignored), override
# con la variabile d'ambiente DCC_SAVE_DIR. L'elenco è uno scan delle intestazioni
# (H §5), mai un registro.
_RADICE_REPO = Path(__file__).resolve().parent.parent
DIRECTORY_SALVATAGGI = Path(os.environ.get("DCC_SAVE_DIR") or _RADICE_REPO / "salvataggi")

# --- La LIBRERIA dei contenuti dello show (stagioni/piani/mob) -------------------
#
# Asset normalizzati e riusabili (riferimenti per slug, tag per l'affinità):
# gli UFFICIALI sono versionati nel repo (`contenuti/`), i LOCALI — creati dal
# GM mode — vivono in una cartella gitignored (lo "stato di guscio persistente"
# di H §12). In lettura l'ufficiale vince sullo slug; le ufficiali sono
# read-only per l'authoring (si duplicano). Il runtime NON legge mai la
# libreria: consuma la stagione RISOLTA e congelata nel World alla creazione.
DIRECTORY_CONTENUTI = Path(os.environ.get("DCC_CONTENUTI_DIR") or _RADICE_REPO / "contenuti")
DIRECTORY_CONTENUTI_LOCALI = Path(
    os.environ.get("DCC_CONTENUTI_LOCALI_DIR") or _RADICE_REPO / "contenuti_locali"
)
STAGIONE_DEFAULT = "stagione-1"

TipoAsset = str  # "stagioni" | "piani" | "mob" (le tre collezioni della libreria)
_MODELLI_ASSET: dict[str, type] = {"stagioni": Stagione, "piani": PianoAsset, "mob": MobAsset}


def _etichetta_asset(tipo: str, asset) -> str:
    return asset.nome if tipo == "mob" else asset.titolo


def _tipo_vista(tipo: str) -> str:
    return {"stagioni": "stagione", "piani": "piano", "mob": "mob"}[tipo]


def _scandisci_collezione(
    tipo: str, cartella: Path, origine: str
) -> dict[str, tuple[object | None, AssetVista]]:
    """Una collezione da disco, LASCA (H-22): file non conforme → voce
    `valido=False`, mostrata ma inutilizzabile — mai un crash di scan."""
    modello = _MODELLI_ASSET[tipo]
    voci: dict[str, tuple[object | None, AssetVista]] = {}
    base = cartella / tipo
    if not base.exists():
        return voci
    for percorso in sorted(base.glob("*.json")):
        try:
            asset = modello.model_validate_json(percorso.read_text(encoding="utf-8"))
            vista = AssetVista(
                slug=asset.slug,
                tipo=_tipo_vista(tipo),
                etichetta=_etichetta_asset(tipo, asset),
                tags=asset.tags,
                origine=origine,
                valido=True,
            )
            voci[asset.slug] = (asset, vista)
        except (OSError, ValueError) as _errore:  # ValidationError è un ValueError
            slug = percorso.stem
            voci.setdefault(
                slug,
                (
                    None,
                    AssetVista(
                        slug=slug, tipo=_tipo_vista(tipo), etichetta="«corrotto»",
                        origine=origine, valido=False,
                    ),
                ),
            )
    return voci


def _collezione(
    tipo: str, ufficiali: Path | None = None, locali: Path | None = None
) -> dict[str, tuple[object | None, AssetVista]]:
    """Fusione locali+ufficiali: sull'ombreggiatura di slug l'UFFICIALE vince."""
    fuse = _scandisci_collezione(tipo, locali or DIRECTORY_CONTENUTI_LOCALI, "locale")
    fuse.update(_scandisci_collezione(tipo, ufficiali or DIRECTORY_CONTENUTI, "ufficiale"))
    return fuse


def elenca_asset(
    tipo: str, *, ufficiali: Path | None = None, locali: Path | None = None
) -> list[AssetVista]:
    return [
        vista
        for _slug, (_asset, vista) in sorted(_collezione(tipo, ufficiali, locali).items())
    ]


def carica_asset(
    tipo: str, slug: str, *, ufficiali: Path | None = None, locali: Path | None = None
):
    """L'asset per slug (ufficiale vince), `None` se assente o corrotto."""
    voce = _collezione(tipo, ufficiali, locali).get(slug)
    return voce[0] if voce else None


def salva_asset_locale(
    asset, *, sovrascrivi: bool = False,
    ufficiali: Path | None = None, locali: Path | None = None,
) -> None:
    """Scrive un asset nella libreria LOCALE (authoring): lint del registry
    (F-6), slug mai in conflitto con un ufficiale, scrittura atomica."""
    tipo = next(t for t, m in _MODELLI_ASSET.items() if isinstance(asset, m))
    if tipo == "mob":
        errori = lint_registry([asset.archetipo], asset.blocchi)
    elif tipo == "piani":
        errori = lint_registry(asset.budget.archetipi, asset.budget.blocchi)
    else:
        errori = []
    if errori:
        raise ValueError("; ".join(errori))
    if _scandisci_collezione(tipo, ufficiali or DIRECTORY_CONTENUTI, "ufficiale").get(asset.slug):
        raise ValueError(f"slug riservato a un asset ufficiale: {asset.slug}")
    cartella = (locali or DIRECTORY_CONTENUTI_LOCALI) / tipo
    percorso = cartella / f"{asset.slug}.json"
    if percorso.exists() and not sovrascrivi:
        raise ValueError(f"slug già esistente in libreria locale: {asset.slug}")
    cartella.mkdir(parents=True, exist_ok=True)
    temporaneo = percorso.with_suffix(".json.tmp")
    temporaneo.write_text(asset.model_dump_json(indent=2), encoding="utf-8")
    os.replace(temporaneo, percorso)


def elimina_asset_locale(
    tipo: str, slug: str, *, locali: Path | None = None
) -> bool:
    percorso = (locali or DIRECTORY_CONTENUTI_LOCALI) / tipo / f"{slug}.json"
    if not percorso.exists():
        return False
    percorso.unlink()
    return True


def risolvi_stagione(
    stagione: Stagione | str,
    *, ufficiali: Path | None = None, locali: Path | None = None,
) -> StagioneRisolta:
    """Scioglie i riferimenti dell'aggregato (piani → mob) e IMPONE la coerenza:
    slug pendenti, cast fuori budget e categorie senza binding (F-6) sono errori
    di authoring sollevati QUI — mai degradi a runtime. Il risultato è pronto
    per il freeze nel World."""
    if isinstance(stagione, str):
        caricata = carica_asset("stagioni", stagione, ufficiali=ufficiali, locali=locali)
        if caricata is None:
            raise ValueError(f"stagione assente o corrotta: {stagione}")
        stagione = caricata
    errori: list[str] = []
    piani_risolti: list[PianoRisolto] = []
    for slug_piano in stagione.piani:
        piano = carica_asset("piani", slug_piano, ufficiali=ufficiali, locali=locali)
        if piano is None:
            errori.append(f"piano riferito ma assente: {slug_piano}")
            continue
        cast: list[MobAsset] = []
        mancanti = False
        for slug_mob in piano.cast:
            mob = carica_asset("mob", slug_mob, ufficiali=ufficiali, locali=locali)
            if mob is None:
                errori.append(f"mob riferito ma assente: {slug_mob} (piano {slug_piano})")
                mancanti = True
            else:
                cast.append(mob)
        if mancanti:
            continue
        try:
            piani_risolti.append(
                PianoRisolto(
                    slug=piano.slug, versione=piano.versione, tags=piano.tags,
                    titolo=piano.titolo, tema=piano.tema, stile=piano.stile,
                    lore=piano.lore, budget=piano.budget, cast=cast, stanze=piano.stanze,
                )
            )
        except ValueError as errore:  # cast⊆budget imposto dal validator
            errori.append(f"piano {slug_piano}: {errore}")
        else:
            errori.extend(lint_registry(piano.budget.archetipi, piano.budget.blocchi))
    if errori:
        raise ValueError("stagione non risolvibile:\n- " + "\n- ".join(errori))
    return StagioneRisolta(
        slug=stagione.slug, versione=stagione.versione, tags=stagione.tags,
        numero=stagione.numero, titolo=stagione.titolo, tagline=stagione.tagline,
        mondo=stagione.mondo, stile=stagione.stile, lore=stagione.lore,
        piani=piani_risolti,
    )


# --- Affinity matching: il riuso degli asset (gli architetti del dungeon) --------
#
# Scoring DETERMINISTICO sui tag: espliciti + impliciti (le categorie contano
# come tag). Zero LLM, zero costo. Questa firma è la PORTA dietro cui, post-MVP,
# si innesta il recupero semantico via embeddings ("prima pesca, poi genera",
# G): richiede un'estensione del contratto Provider (PLK: oggi un solo verbo
# `genera`) — decisione di spec futura, qui solo annotata.

def _tags_asset(tipo: str, asset) -> set[str]:
    tags = set(asset.tags)
    if tipo == "mob":
        tags |= {asset.archetipo.value, asset.grado.value}
        tags |= {b.value for b in asset.blocchi}
    elif tipo == "piani":
        tags |= {a.value for a in asset.budget.archetipi}
        tags |= {g.value for g in asset.budget.gradi}
    return tags


def affini(
    tags: list[str], *, tipo: str, k: int = 5, escludi: tuple[str, ...] = (),
    ufficiali: Path | None = None, locali: Path | None = None,
) -> list[AssetVista]:
    """Gli asset della collezione più affini ai tag dati, ordinati per punteggio
    (sovrapposizione, poi Jaccard, poi slug — stabile e riproducibile)."""
    richiesti = {t.strip().lower() for t in tags if t.strip()}
    if not richiesti:
        return []
    classifica: list[tuple[float, float, str, AssetVista]] = []
    for slug, (asset, vista) in _collezione(tipo, ufficiali, locali).items():
        if asset is None or slug in escludi:
            continue
        propri = _tags_asset(tipo, asset)
        sovrapposizione = len(richiesti & propri)
        if sovrapposizione == 0:
            continue
        jaccard = sovrapposizione / len(richiesti | propri)
        classifica.append((-sovrapposizione, -jaccard, slug, vista))
    classifica.sort()
    return [vista for *_resto, vista in classifica[:k]]


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
        self._fuga = False
        self._coppie = [(CombatResolved, self._su_resolved), (MortePersonaggio, self._su_morte)]
        for tipo, handler in self._coppie:
            bus.registra(tipo, handler)

    def _su_resolved(self, evento: CombatResolved) -> None:
        self._conclusa = True
        self._vittoria = bool(getattr(evento, "vittoria", False))
        self._fuga = bool(getattr(evento, "fuga", False))

    def _su_morte(self, _evento: MortePersonaggio) -> None:
        self._conclusa = True  # permadeath: lo scontro non si chiude, la run sì

    @property
    def opzioni(self) -> tuple[OpzioneVista, ...]:
        return _MENU_COMBATTIMENTO

    def agisci(self, indice: int) -> None:
        """Un comando del giocatore = il SUO turno + le risposte dei nemici, in un
        colpo solo (feel: il click non "esegue il turno del mob" in silenzio).
        `indice=1` (Fuggi) marca il turno come tentativo di disimpegno (FNC §4):
        la prova la tira il MOTORE dentro il suo sistema-turno."""
        if self._conclusa or not (0 <= indice < len(self.opzioni)):
            return
        if indice == 1:
            richiedi_fuga()
        tick()  # il turno del protagonista (attacco, o tentativo di fuga)
        self._turni += 1
        # Il giro dei nemici, fino a tornare al protagonista (guardia difensiva).
        guardia = 0
        while (
            not self._conclusa
            and in_combattimento()
            and not prossimo_attivo_e_protagonista()
            and guardia < 16
        ):
            tick()
            guardia += 1

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
            fuga=self._fuga,
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
        stagione: StagioneAttiva | None = None,
    ) -> "SessioneGioco":
        """Nuova run: il protagonista NASCE al confine guscio→run. L'uuid identifica
        lo slot di save (slot = crawler, H §1); il nome ne è l'etichetta.
        `stagione` è il design RISOLTO e convertito: congelato nel World."""
        sessione = cls(provider, directory=directory, seed=seed)
        sessione.uuid = uuid4().hex[:8]
        sessione.etichetta = nome
        sessione.guscio.nuova_partita(
            uuid=sessione.uuid, destrezza=10, hp=30, seed=seed,
            n_stanze=n_stanze, stagione=stagione,
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
        if sessione.provider is None:
            # Offline: il copione si deriva dalla stagione CONGELATA nel save
            # (design_piano_corrente; save legacy → Falsa Idra), mai dalla libreria.
            sessione.provider = _fake_da_piano(design_piano_corrente())
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
        if in_combattimento():
            # Il giocatore VEDE chi affronta e quanto gli resta (feel G §5.6).
            for nome, attuali, massimi in nemici_in_scontro():
                extra.append(f"{nome}: {attuali}/{massimi}")
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
def _riga_colpo(e: object) -> str:
    attaccante = getattr(e, "attaccante", "")
    bersaglio = getattr(e, "bersaglio", "")
    danno = getattr(e, "danno", 0)
    hp = f"({getattr(e, 'hp_rimasti', 0)}/{getattr(e, 'hp_max', 0)})"
    pesante = " — COLPO PESANTE" if getattr(e, "mossa", "") == "attacco_pesante" else ""
    if attaccante == "":  # il protagonista colpisce
        return f"Colpisci {bersaglio or 'il nemico'}: {danno} danni {hp}{pesante}."
    return f"{attaccante} ti colpisce: {danno} danni {hp}{pesante}."


def _riga_status_applicato(e: object) -> str:
    chi = getattr(e, "bersaglio", "")
    status = getattr(e, "status", "")
    if chi == "":
        return f"Sei {_participio_status(status)}!"
    return f"{chi} è {_participio_status(status)}."


def _participio_status(status: str) -> str:
    return {
        "veleno": "avvelenato", "brucia": "in fiamme",
        "stordito": "stordito", "rigenerazione": "in rigenerazione",
    }.get(status, status)


def _riga_effetto_status(e: object) -> str:
    chi = getattr(e, "bersaglio", "")
    delta = getattr(e, "delta_hp", 0)
    nome_status = getattr(e, "status", "")
    if delta < 0:
        soggetto = "Il veleno" if nome_status == "veleno" else (
            "Le fiamme" if nome_status == "brucia" else nome_status.capitalize()
        )
        vittima = "ti" if chi == "" else chi
        return f"{soggetto} {'morde' if nome_status == 'veleno' else 'mordono'} {vittima}: {delta} HP."
    chi_bene = "Recuperi" if chi == "" else f"{chi} rigenera"
    return f"{chi_bene} {delta} HP."


def _riga_turno_saltato(e: object) -> str:
    if getattr(e, "causa", "") == "fuga_fallita":
        return "Tenti la fuga: FALLITA. Il nemico ne approfitta."
    nome = getattr(e, "nome", "")
    return "Sei stordito: salti il turno!" if nome == "" else f"{nome} è stordito: salta il turno."


def _riga_risolto(e: object) -> str:
    if getattr(e, "fuga", False):
        return "Ti disimpegni: fuga riuscita, lo scontro si dissolve."
    if getattr(e, "vittoria", False):
        return "Hai vinto lo scontro."
    return "Lo scontro si chiude."


_MAPPA_EVENTI: tuple[tuple[type, Callable[[object], str]], ...] = (
    (EncounterStarted, lambda _e: "Lo scontro ha inizio."),
    (ColpoInferto, _riga_colpo),
    (StatusApplicato, _riga_status_applicato),
    (EffettoStatus, _riga_effetto_status),
    (TurnoSaltato, _riga_turno_saltato),
    (CombatResolved, _riga_risolto),
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


# --- Freeze: dal DTO risolto all'aggregato ATTIVO del motore ---------------------

def _stagione_a_attiva(risolta: StagioneRisolta) -> StagioneAttiva:
    """Conversione DTO→dataclass al confine (la colla vive nel composition root)."""
    return StagioneAttiva(
        slug=risolta.slug,
        versione=risolta.versione,
        numero=risolta.numero,
        titolo=risolta.titolo,
        tagline=risolta.tagline,
        mondo=risolta.mondo,
        stile=list(risolta.stile),
        lore=risolta.lore,
        piani=[
            PianoAttivo(
                slug=piano.slug,
                titolo=piano.titolo,
                tema=piano.tema,
                stile=list(piano.stile),
                lore=piano.lore,
                gradi=list(piano.budget.gradi),
                blocchi=list(piano.budget.blocchi),
                archetipi=list(piano.budget.archetipi),
                cast=[
                    MobAttivo(
                        slug=mob.slug, nome=mob.nome, archetipo=mob.archetipo,
                        grado=mob.grado, blocchi=list(mob.blocchi),
                        descrizione=mob.descrizione, prosa_stanza=mob.prosa_stanza,
                        durata=mob.durata, tags=list(mob.tags),
                    )
                    for mob in piano.cast
                ],
                stanze=piano.stanze,
                tags=list(piano.tags),
            )
            for piano in risolta.piani
        ],
        tags=list(risolta.tags),
    )


def turni_da_piano(piano) -> list[TurnoNarrazione]:
    """Il copione offline DERIVATO dal cast del piano (una stanza per voce, in
    ordine). Accetta sia il DTO `PianoRisolto` sia il dataclass `PianoAttivo`
    (stessi campi sul cast: duck-typed). Esauriti i turni, l'orchestrazione
    degrada al fallback deterministico: il gioco non si blocca mai."""
    combatti_o_scappa = [
        Opzione(tipo=TipoAzione.COMBATTI, etichetta="Combatti"),
        Opzione(tipo=TipoAzione.SCAPPA, etichetta="Scappi"),
    ]
    return [
        TurnoNarrazione(
            prosa=mob.prosa_stanza,
            entita=EntitaGenerata(
                archetipo=mob.archetipo,
                grado=mob.grado,
                blocchi=list(mob.blocchi),
                nome=mob.nome,
                descrizione=mob.descrizione,
            ),
            opzioni=combatti_o_scappa,
            durata=mob.durata,
        )
        for mob in piano.cast
    ]


def _turni_scriptati() -> list[TurnoNarrazione]:
    """RETRO-COMPAT: il copione della stagione di default (la Falsa Idra), oggi
    DERIVATO dalla libreria (`contenuti/`) — non più hardcoded."""
    return turni_da_piano(risolvi_stagione(STAGIONE_DEFAULT).piani[0])


def _fake_da_piano(piano) -> FakeProvider:
    """Il **FakeProvider scriptato** (offline): FIFO per chiamata — la pipeline GM
    fa (fino a) 4 chiamate per turno, quindi il copione scripta gli stadi in
    ordine: ideazione degradata (`None`), IL turno gating, limatura e
    distillazione degradate. `piano=None` (save legacy) → la Falsa Idra."""
    if piano is None:
        piano = risolvi_stagione(STAGIONE_DEFAULT).piani[0]
    risposte: list[object] = []
    for turno in turni_da_piano(piano):
        risposte += [None, turno.model_dump(), None, None]
    return FakeProvider(risposte)


def costruisci_sessione(
    *,
    nome: str = "Carl",
    seed: int = 0,
    directory: Path | None = None,
    provider=None,
    stagione: Stagione | StagioneRisolta | str | None = None,
) -> SessioneGioco:
    """Cabla contenuto+provider → `SessioneGioco.nuova`. Senza `directory` la run
    vive in una tempdir usa-e-getta (demo/test).

    `stagione` (slug, DTO o risolta; default `stagione-1`) viene RISOLTA e
    congelata nella run. Offline (`provider=None`, default SICURO: mai rete
    implicita): il copione del FakeProvider e la scala del piano derivano dal
    piano 1 della stagione. Live: la scala è quella autorata (`stanze`) o la
    calibrazione (`MAPPA_STANZE`); il backend si INIETTA esplicitamente."""
    directory = directory or Path(tempfile.mkdtemp(prefix="dcc-"))
    if isinstance(stagione, StagioneRisolta):
        risolta = stagione
    else:
        risolta = risolvi_stagione(stagione if stagione is not None else STAGIONE_DEFAULT)
    piano1 = risolta.piani[0]
    if provider is None:
        n_stanze = piano1.n_stanze  # il copione copre tutte le stanze
        provider = _fake_da_piano(piano1)
    else:
        n_stanze = piano1.stanze  # scala autorata; None → MAPPA_STANZE
    return SessioneGioco.nuova(
        provider,
        directory=directory,
        nome=nome,
        seed=seed,
        n_stanze=n_stanze,
        stagione=_stagione_a_attiva(risolta),
    )


def carica_sessione(
    *, uuid: str, directory: Path | None = None, provider=None
) -> SessioneGioco | None:
    """Riapre un crawler sospeso (`None` se illeggibile). Il provider offline si
    deriva DOPO il load, dalla stagione congelata nel save (mai dalla libreria:
    le run non vedono le modifiche di authoring)."""
    directory = directory or DIRECTORY_SALVATAGGI
    return SessioneGioco.da_salvataggio(provider, directory=directory, uuid=uuid)


_RE_UUID_CRAWLER = r"^[a-z0-9][a-z0-9-]{0,63}$"


def elimina_crawler(uuid: str, *, directory: Path | None = None) -> bool:
    """Elimina uno slot-crawler dall'hub: stato + sidecar Archivio + i backup
    `.bak` (pulizia completa: è la scelta volontaria del giocatore, non un
    terminale di run — H-20 intatto; H §10.4: nessun DRM contro il giocatore).
    L'uuid è validato (niente separatori di percorso). `False` se non c'era nulla."""
    import re

    if not re.fullmatch(_RE_UUID_CRAWLER, uuid):
        raise ValueError(f"uuid di crawler non valido: {uuid!r}")
    directory = directory or DIRECTORY_SALVATAGGI
    nomi = (
        f"{uuid}.stato.json",
        f"{uuid}.archivio.gz",
        f"{uuid}.bak.stato.json",
        f"{uuid}.bak.archivio.gz",
    )
    trovato = False
    for nome in nomi:
        percorso = directory / nome
        if percorso.exists():
            percorso.unlink()
            trovato = True
    return trovato


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
