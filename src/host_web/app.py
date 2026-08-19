"""L'API HTTP di gioco (FastAPI) — host opt-in FUORI dal motore.

Mappa 1:1 le porte di `SessioneGioco` (src/main.py) su endpoint: nessuna logica di
gioco qui, solo trasporto + guardie. Regole:
  - una partita per processo (World esper process-global): `POST /api/partita` una volta;
  - il motore NON è rientrante: lock non-bloccante, seconda richiesta → 409
    `motore_occupato` (mai accodamento silenzioso che riordini i turni);
  - versione-turno anti-stale: gli indici opzione valgono solo per lo snapshot
    corrente → body con `versione`, stantia → 409 `turno_stantio`;
  - drenaggio SOLO dentro la richiesta (`accoda → avanza()`), mai da un timer (IC §7.1);
  - permadeath: a `MortePersonaggio` le POST di gioco rispondono 410 `run_terminata`;
  - la chiave LLM resta env-only: il client sceglie solo `"fake"|"live"`, qui se ne
    verifica la PRESENZA (mai il valore) — PLK §4.
Importa SOLO `main` + `contracts` (e `provider` lazy, come `gioco_textual`): mai
`motore`, mai esper — membrana verificata in tests/test_membrana_vista.py. La
calibrazione passa dal backend del calibratore (`calibratore_web`, host-tool peer):
è LUI a parlare con `motore.calibrazione`, qui solo trasporto.
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

import calibratore_web

from contracts import PlayerChoseOption
from main import (
    MODELLI_ASSET,
    STAGIONE_DEFAULT,
    SalvataggioInCombattimento,
    affini,
    bacheca,
    carica_asset,
    carica_sessione,
    costruisci_sessione,
    elenca_asset,
    elenca_crawler,
    elimina_asset_locale,
    elimina_crawler,
    etichetta_oggetto,
    fantasmi_locali,
    risolvi_stagione,
    salva_asset_locale,
    vocabolario,
)

# Le collezioni della libreria e i loro modelli di authoring: UNA mappa, quella
# del composition root (prima era duplicata qui — audit 2026-08).
_MODELLI_CONTENUTI = MODELLI_ASSET

from .sse import flusso_eventi
from .stato import PostThread, StatoHost


class ErroreApi(Exception):
    """Errore applicativo uniforme: `{codice, dettaglio, ...}` con status HTTP."""

    def __init__(self, status: int, codice: str, dettaglio: str, **extra: object) -> None:
        super().__init__(dettaglio)
        self.status = status
        self.codice = codice
        self.dettaglio = dettaglio
        self.extra = extra


# --- Body delle richieste (validati da FastAPI/Pydantic) -----------------------

class NuovoCrawler(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str = Field(min_length=1, max_length=40)
    seed: int = 0
    stagione: str | None = None  # slug della stagione; None = quella di default
    # RUN DEL GIORNO (sovra-run C): il seed diventa `seed_del_giorno(oggi,
    # stagione)` — stessa data, stesso dungeon per chiunque. La DATA la mette
    # l'HOST (qui): il motore non guarda mai l'orologio (J).
    daily: bool = False
    # DUNGEON INFESTATO (sovra-run D): le sconfitte del ledger locale entrano
    # come fantasmi-lore. Opt-in esplicito: senza flag, run storica identica.
    infestata: bool = False


class CaricaCrawler(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uuid: str = Field(min_length=1)


class RichiestaPartita(BaseModel):
    """Apertura di una run: ESATTAMENTE una tra `nuovo` (nasce un crawler) e
    `carica` (si riapre uno slot sospeso)."""

    model_config = ConfigDict(extra="forbid")
    gm: Literal["fake", "live"] = "fake"
    nuovo: NuovoCrawler | None = None
    carica: CaricaCrawler | None = None

    @model_validator(mode="after")
    def _uno_solo(self) -> "RichiestaPartita":
        if (self.nuovo is None) == (self.carica is None):
            raise ValueError("indica esattamente uno tra 'nuovo' e 'carica'")
        return self


class RichiestaVersione(BaseModel):
    model_config = ConfigDict(extra="forbid")
    versione: int


class RichiestaOpzione(BaseModel):
    model_config = ConfigDict(extra="forbid")
    indice: int
    versione: int


class RichiestaAnteprima(BaseModel):
    model_config = ConfigDict(extra="forbid")
    testo: str


class RichiestaAzione(BaseModel):
    model_config = ConfigDict(extra="forbid")
    testo: str
    versione: int


class RichiestaEquip(BaseModel):
    """Indossa/togli per FONTE (ADR-1: rimozione per fonte, mai operazione
    inversa). La fonte deve stare nello zaino: il resto lo arbitra il motore."""

    model_config = ConfigDict(extra="forbid")
    fonte: str = Field(min_length=1)
    versione: int


class RichiestaBattuta(BaseModel):
    """Una battuta nella scena sociale aperta. Testo VUOTO = il giocatore
    tronca la conversazione (stessa semantica della TUI)."""

    model_config = ConfigDict(extra="forbid")
    testo: str
    versione: int


async def _drena_prosa(sessione) -> list:
    """Svuota la coda dei battiti fuori banda del motore (`prossima_prosa`):
    trailer d'apertura, vestizione del premio, epitaffio. La porta è unica e
    l'host la DRENA e basta — quando un battito è dovuto lo decide il motore
    (la TUI fa lo stesso; senza questo drenaggio il forum perdeva metà della
    narrazione)."""
    prose = []
    while True:
        battito = await sessione.prossima_prosa()
        if battito is None:
            return prose
        prose.append(battito)


class RichiestaCalibrazioneValore(BaseModel):
    """Il valore GREZZO di un override: coerce e validazione (int/float/scelta)
    vivono nel catalogo (`calibrazione._coerce`), mai qui."""

    model_config = ConfigDict(extra="forbid")
    valore: int | float | str


class RichiestaCalibrazioneAnteprima(BaseModel):
    model_config = ConfigDict(extra="forbid")
    archetipo: str
    grado: str
    livello: int = Field(default=1, ge=1)


def _provider_live(stato: StatoHost) -> tuple[object, str]:
    """Il GM live, stessa politica di `gioco_textual._scegli_provider` (PLK §4):
    presenza della chiave, mai il valore; nessun degrado muto — se il live non è
    possibile lo si DICE (503). Import lazy: `provider` non è un requisito
    dell'host quando si gioca offline."""
    if stato.live_vietato:
        raise ErroreApi(
            503, "live_non_disponibile",
            "L'host è stato avviato con --fake: il GM live è disabilitato.",
        )
    from provider import (
        AnthropicBackend,
        MODELLO_DEFAULT,
        MODELLO_VELOCE,
        ProviderPerSchema,
        chiave_presente,
        sdk_disponibile,
    )

    if not chiave_presente():
        raise ErroreApi(
            503, "live_non_disponibile",
            "ANTHROPIC_API_KEY assente dall'ambiente (copia .env.example → .env e "
            "compila). La chiave non passa MAI per URL, body o log.",
        )
    if not sdk_disponibile():
        raise ErroreApi(
            503, "live_non_disponibile",
            "SDK anthropic non installato: .venv\\Scripts\\pip install anthropic",
        )
    from contracts import TurnoNarrazione

    # Il modello FORTE serve solo la chiamata gating (il turno); gli stadi ancillari
    # non-gating vanno sul VELOCE (stessa corsia della TUI).
    forte = AnthropicBackend()
    veloce = AnthropicBackend(modello=MODELLO_VELOCE, max_tokens=512, timeout=15.0)
    provider = ProviderPerSchema({TurnoNarrazione: forte}, predefinito=veloce)
    return provider, f"GM live — {MODELLO_DEFAULT} (turni) + {MODELLO_VELOCE} (rifiniture)"


def crea_app(stato: StatoHost) -> FastAPI:
    """Costruisce l'app FastAPI sopra uno `StatoHost` (factory: testabile per-test)."""
    app = FastAPI(title="DCC — host web", version="0.1")

    @app.exception_handler(ErroreApi)
    async def _su_errore(_richiesta: Request, err: ErroreApi) -> JSONResponse:
        return JSONResponse(
            {"codice": err.codice, "dettaglio": err.dettaglio, **err.extra},
            status_code=err.status,
        )

    # --- Guardie ------------------------------------------------------------

    def _sessione():
        if stato.sessione is None:
            raise ErroreApi(404, "partita_assente", "Nessuna partita: POST /api/partita.")
        return stato.sessione

    def _guardie_di_gioco(versione: int) -> None:
        """Ordine: terminata (410) → occupato (409) → versione stantia (409). Tra
        il check del lock e l'acquisizione non c'è alcun await: niente corse."""
        if stato.morto or stato.vittoria:
            raise ErroreApi(
                410, "run_terminata",
                "La run è terminata (permadeath o discesa): chiudila con "
                "POST /api/partita/chiudi.",
            )
        if stato.lock.locked():
            raise ErroreApi(409, "motore_occupato", "Il GM sta lavorando: riprova.")
        if versione != stato.versione:
            raise ErroreApi(
                409, "turno_stantio",
                "Lo snapshot è cambiato: risincronizza.",
                versione_corrente=stato.versione,
            )

    # --- Risposte -----------------------------------------------------------

    def _stato_partita() -> dict:
        snap = stato.snapshot
        return {
            "versione": stato.versione,
            "fase": snap.fase if snap is not None else "narrazione",
            "occupato": stato.lock.locked(),
            "morto": stato.morto,
            "vittoria": stato.vittoria,
            "crawler": stato.crawler,
            "snapshot": snap.model_dump(mode="json") if snap is not None else None,
            "gm": stato.gm_etichetta,
        }

    def _risposta_turno(nuovi: list[PostThread]) -> dict:
        return {**_stato_partita(), "post": [p.model_dump(mode="json") for p in nuovi]}

    # --- Ciclo di vita della partita -----------------------------------------

    # --- Libreria dei contenuti (GM mode): stagioni/piani/mob -----------------
    # Nessuna guardia di sessione: l'authoring non tocca le run in corso (la
    # stagione è CONGELATA nel World alla creazione). Gli asset ufficiali sono
    # read-only: si duplicano; i locali si creano/modificano/eliminano.

    def _dirs() -> dict:
        return {
            "ufficiali": stato.contenuti_ufficiali,
            "locali": stato.contenuti_locali,
        }

    def _collezione_valida(tipo: str) -> None:
        if tipo not in _MODELLI_CONTENUTI:
            raise ErroreApi(404, "collezione_sconosciuta", f"collezione: {tipo!r}")

    def _valida_corpo(tipo: str, corpo: dict):
        try:
            return _MODELLI_CONTENUTI[tipo].model_validate(corpo)
        except ValueError as errore:
            raise ErroreApi(
                422, "contenuto_non_valido", str(errore)
            ) from errore

    @app.get("/api/vocabolario")
    async def vocabolario_api() -> dict:
        """Il vocabolario per gli editor e gli agenti: enum del contratto, mosse,
        archetipi noti, chiavi delle tabelle gear — una sola fonte, mai duplicati
        cablati nel client."""
        return vocabolario(**_dirs())

    @app.get("/api/contenuti/affini")
    async def contenuti_affini(tipo: str, tags: str, k: int = 5) -> dict:
        """Affinity matching deterministico sui tag (il riuso degli asset)."""
        _collezione_valida(tipo)
        richiesti = [t for t in tags.split(",") if t.strip()]
        return {
            "affini": [
                v.model_dump(mode="json")
                for v in affini(richiesti, tipo=tipo, k=k, **_dirs())
            ]
        }

    @app.get("/api/contenuti/{tipo}")
    async def elenca_contenuti(tipo: str) -> dict:
        _collezione_valida(tipo)
        return {"asset": [v.model_dump(mode="json") for v in elenca_asset(tipo, **_dirs())]}

    @app.post("/api/contenuti/{tipo}", status_code=201)
    async def crea_contenuto(tipo: str, corpo: dict) -> dict:
        _collezione_valida(tipo)
        asset = _valida_corpo(tipo, corpo)
        try:
            salva_asset_locale(asset, **_dirs())
        except ValueError as errore:
            # Conflitto di slug (riservato/duplicato) → 409; ogni altro lint → 422.
            conflitto = str(errore).startswith(("slug riservato", "slug già esistente"))
            codice = "slug_esistente" if conflitto else "contenuto_non_valido"
            raise ErroreApi(409 if conflitto else 422, codice, str(errore))
        return asset.model_dump(mode="json")

    @app.get("/api/contenuti/{tipo}/{slug}")
    async def leggi_contenuto(tipo: str, slug: str) -> dict:
        _collezione_valida(tipo)
        asset = carica_asset(tipo, slug, **_dirs())
        if asset is None:
            raise ErroreApi(404, "asset_assente", f"{tipo}/{slug} assente o corrotto.")
        return asset.model_dump(mode="json")

    @app.put("/api/contenuti/{tipo}/{slug}")
    async def aggiorna_contenuto(tipo: str, slug: str, corpo: dict) -> dict:
        _collezione_valida(tipo)
        asset = _valida_corpo(tipo, corpo)
        if asset.slug != slug:
            raise ErroreApi(422, "contenuto_non_valido", "slug del body ≠ slug del path")
        origini = {v.slug: v.origine for v in elenca_asset(tipo, **_dirs())}
        if origini.get(slug) == "ufficiale":
            raise ErroreApi(403, "asset_ufficiale", "gli asset ufficiali si duplicano, non si modificano")
        if slug not in origini:
            raise ErroreApi(404, "asset_assente", f"{tipo}/{slug} non esiste")
        try:
            salva_asset_locale(asset, sovrascrivi=True, **_dirs())
        except ValueError as errore:
            raise ErroreApi(422, "contenuto_non_valido", str(errore))
        return asset.model_dump(mode="json")

    @app.delete("/api/contenuti/{tipo}/{slug}")
    async def elimina_contenuto(tipo: str, slug: str) -> dict:
        _collezione_valida(tipo)
        origini = {v.slug: v.origine for v in elenca_asset(tipo, **_dirs())}
        if origini.get(slug) == "ufficiale":
            raise ErroreApi(403, "asset_ufficiale", "gli asset ufficiali non si eliminano")
        if not elimina_asset_locale(tipo, slug, locali=stato.contenuti_locali):
            raise ErroreApi(404, "asset_assente", f"{tipo}/{slug} non esiste")
        return {"eliminato": slug}

    @app.get("/api/contenuti/stagioni/{slug}/risolto")
    async def stagione_risolta(slug: str) -> dict:
        """La stagione coi riferimenti SCIOLTI (o gli errori di risoluzione):
        è la prova del GM mode prima di giocarci."""
        try:
            risolta = risolvi_stagione(slug, **_dirs())
        except ValueError as errore:
            raise ErroreApi(422, "stagione_non_risolvibile", str(errore))
        return risolta.model_dump(mode="json")

    # --- Calibrazione (GM mode): il catalogo §11 + gli override ----------------
    # Nessuna guardia di sessione: come l'authoring, la calibrazione non tocca la
    # run in corso — le costanti pubbliche del motore sono derivate all'IMPORT,
    # quindi gli override valgono dal prossimo avvio dell'host; l'ANTEPRIMA invece
    # rilegge i valori freschi (è il banco di prova del bilanciamento).

    @app.get("/api/calibrazione")
    async def calibrazione_vista() -> dict:
        return calibratore_web.costruisci_vista()

    @app.put("/api/calibrazione/voci/{chiave}")
    async def calibrazione_imposta(chiave: str, ric: RichiestaCalibrazioneValore) -> dict:
        if not calibratore_web.esiste(chiave):
            raise ErroreApi(404, "parametro_sconosciuto", f"parametro: {chiave!r}")
        esito = calibratore_web.applica(chiave, ric.valore)
        if not esito["ok"]:
            raise ErroreApi(422, "valore_non_valido", esito["errore"])
        return {"chiave": chiave, "valore": esito["valore"], "override": esito["override"]}

    @app.delete("/api/calibrazione/voci/{chiave}")
    async def calibrazione_azzera(chiave: str) -> dict:
        if not calibratore_web.esiste(chiave):
            raise ErroreApi(404, "parametro_sconosciuto", f"parametro: {chiave!r}")
        esito = calibratore_web.azzera(chiave)
        return {"chiave": chiave, "valore": esito["valore"], "override": False}

    @app.post("/api/calibrazione/salva")
    async def calibrazione_salva() -> dict:
        esito = calibratore_web.salva()
        return {"percorso": esito["percorso"], "n": esito["n"]}

    @app.post("/api/calibrazione/anteprima")
    async def calibrazione_anteprima(ric: RichiestaCalibrazioneAnteprima) -> dict:
        # Entità usa-e-getta nel World corrente, creata ed eliminata nello stesso
        # tratto sincrono: nessun interleaving con i turni (asyncio, zero await).
        try:
            return calibratore_web.anteprima(ric.archetipo, ric.grado, ric.livello)
        except ValueError as errore:
            raise ErroreApi(422, "anteprima_non_valida", str(errore))

    @app.get("/api/bacheca")
    async def bacheca_crawler() -> dict:
        """La BACHECA sovra-run: i necrologi PROIETTATI dal ledger degli esiti
        (Fase B). Nessuna guardia di sessione: è storia, si legge anche a hub
        spento — e un ledger sabotato è una bacheca vuota, mai un crash."""
        return {
            "necrologi": [
                p.model_dump(mode="json") for p in bacheca(stato.directory)
            ]
        }

    @app.get("/api/crawlers")
    async def crawlers() -> dict:
        """L'elenco degli slot (slot = crawler, H §1): la vista dell'hub. Nessuna
        guardia di sessione: si consulta anche a run aperta."""
        return {
            "crawlers": [c.model_dump(mode="json") for c in elenca_crawler(stato.directory)],
            "attiva": stato.crawler,
        }

    @app.delete("/api/crawlers/{uuid}")
    async def elimina_slot(uuid: str) -> dict:
        """Elimina un crawler PASSATO dall'hub (anche gli slot corrotti: è il
        caso d'uso principale). Vietato a run aperta: l'uscita riscriverebbe il
        save appena cancellato. Non è un terminale di run (H-20 intatto)."""
        if stato.sessione is not None:
            raise ErroreApi(
                409, "partita_esistente",
                "C'è una run aperta: chiudila prima di eliminare slot.",
            )
        try:
            trovato = elimina_crawler(uuid, directory=stato.directory)
        except ValueError as errore:
            raise ErroreApi(422, "uuid_non_valido", str(errore))
        if not trovato:
            raise ErroreApi(404, "crawler_assente", f"nessuno slot per {uuid!r}")
        return {"eliminato": uuid}

    @app.post("/api/partita", status_code=201)
    async def apri_partita(ric: RichiestaPartita) -> dict:
        if stato.sessione is not None:
            raise ErroreApi(
                409, "partita_esistente",
                "Una run è già aperta (una per processo): chiudila con "
                "POST /api/partita/esci prima di aprirne un'altra.",
            )
        if ric.gm == "live":
            provider, etichetta = _provider_live(stato)
        else:
            provider, etichetta = None, "GM offline (contenuto scriptato)"
        # provider=None ⇒ FakeProvider: il default resta SICURO, il live è esplicito.
        if ric.nuovo is not None:
            # La stagione si RISOLVE prima di creare la run: gli errori di
            # authoring muoiono qui, mai a partita aperta.
            try:
                risolta = risolvi_stagione(
                    ric.nuovo.stagione or STAGIONE_DEFAULT, **_dirs()
                )
            except ValueError as errore:
                raise ErroreApi(422, "stagione_non_risolvibile", str(errore))
            seed = ric.nuovo.seed
            if ric.nuovo.daily:
                from datetime import date

                from contracts import seed_del_giorno

                seed = seed_del_giorno(date.today().isoformat(), risolta.numero)
            fantasmi = (
                fantasmi_locali(stato.directory) if ric.nuovo.infestata else ()
            )
            sessione = costruisci_sessione(
                nome=ric.nuovo.nome, seed=seed,
                directory=stato.directory, provider=provider, stagione=risolta,
                fantasmi=fantasmi,
            )
        else:
            sessione = carica_sessione(
                uuid=ric.carica.uuid, directory=stato.directory, provider=provider
            )
            if sessione is None:
                raise ErroreApi(
                    404, "salvataggio_illeggibile",
                    "Il salvataggio non esiste o non è leggibile.",
                )
        crawler = {"uuid": sessione.uuid, "nome": sessione.etichetta}
        if ric.nuovo is not None:
            # Il seed EFFETTIVO (post-daily): la UI può dire «run del giorno,
            # seed N» e la verifica futura della classifica è proprio questo
            # numero (esito.seed == seed_del_giorno(data)).
            crawler["seed"] = seed
        stato.adotta(sessione, etichetta, crawler=crawler)
        if ric.carica is not None:
            # Il forum della run riparte dai turni GM congelati (H §11).
            stato.ricostruisci_thread(sessione.ricostruisci_thread())
        # Un turno del motore (sync, zero LLM) riallinea scena/menu e produce il
        # primo snapshot; da qui in poi vale il protocollo di versione.
        snap = sessione.avanza()
        stato.registra_turno(
            snap, righe=stato.cronaca.preleva() if stato.cronaca else [], messaggio=None
        )
        return _stato_partita()

    @app.post("/api/partita/esci")
    async def esci_partita(ric: RichiestaVersione) -> dict:
        """Salva-ed-esci (terminale 6c): la run si chiude, si torna all'hub. Da
        run terminata (morte/vittoria) si usa POST /api/partita/chiudi."""
        sessione = _sessione()
        _guardie_di_gioco(ric.versione)
        async with stato.lock:
            try:
                messaggio = sessione.esci()
            except SalvataggioInCombattimento as errore:
                raise ErroreApi(409, "fase_non_valida", str(errore))
            stato.azzera_run()
        return {"messaggio": messaggio}

    @app.post("/api/partita/chiudi")
    async def chiudi_partita() -> dict:
        """Chiusura della run TERMINATA: hand-off del terminale (invalida il save,
        permadeath H-20) e ritorno all'hub."""
        sessione = _sessione()
        if not (stato.morto or stato.vittoria):
            raise ErroreApi(
                409, "run_non_terminata",
                "La run è ancora in corso: per lasciarla usa POST /api/partita/esci.",
            )
        if stato.lock.locked():
            raise ErroreApi(409, "motore_occupato", "Il GM sta lavorando: riprova.")
        async with stato.lock:
            messaggio = sessione.chiudi_terminale()
            stato.azzera_run()
        return {"messaggio": messaggio}

    @app.get("/api/partita/scheda")
    async def scheda_party() -> dict:
        """Il party per la UI (oggi: il solo protagonista — la lista è il seam)."""
        sessione = _sessione()
        return {"party": [sessione.scheda().model_dump(mode="json")]}

    @app.get("/api/partita/zaino")
    async def zaino() -> dict:
        """L'inventario per la UI: fonte + etichetta diegetica (la vestizione
        del Guardaroba vince sul catalogo) + stato indossata. Sola lettura."""
        sessione = _sessione()
        indossate = set(sessione.fonti_indossate())
        return {
            "fonti": [
                {
                    "fonte": fonte,
                    "etichetta": etichetta_oggetto(fonte),
                    "indossata": fonte in indossate,
                }
                for fonte in sessione.scheda().zaino
            ]
        }

    def _guardia_equip(ric: RichiestaEquip):
        """Guardie comuni di Indossa/Togli: run viva, versione fresca, fase di
        narrazione (in scontro l'intento resterebbe in coda non servita:
        meglio un rifiuto detto che un click muto), fonte davvero posseduta."""
        sessione = _sessione()
        _guardie_di_gioco(ric.versione)
        if stato.snapshot is not None and stato.snapshot.fase != "narrazione":
            raise ErroreApi(
                409, "fase_non_valida",
                "L'equipaggiamento si cambia in narrazione, non in scontro.",
            )
        if ric.fonte not in sessione.scheda().zaino:
            raise ErroreApi(
                422, "fonte_assente", f"{ric.fonte!r} non è nello zaino."
            )
        return sessione

    @app.post("/api/partita/equipaggia")
    async def equipaggia(ric: RichiestaEquip) -> dict:
        sessione = _guardia_equip(ric)
        async with stato.lock:
            snap = sessione.equipaggia(ric.fonte)
            righe = stato.cronaca.preleva() if stato.cronaca else []
            nuovi = stato.registra_turno(snap, righe=righe, messaggio=None)
        return _risposta_turno(nuovi)

    @app.post("/api/partita/togli")
    async def togli(ric: RichiestaEquip) -> dict:
        sessione = _guardia_equip(ric)
        async with stato.lock:
            snap = sessione.togli(ric.fonte)
            righe = stato.cronaca.preleva() if stato.cronaca else []
            nuovi = stato.registra_turno(snap, righe=righe, messaggio=None)
        return _risposta_turno(nuovi)

    @app.get("/api/partita")
    async def leggi_partita() -> dict:
        _sessione()
        return _stato_partita()

    @app.get("/api/partita/thread")
    async def leggi_thread() -> dict:
        _sessione()
        return {
            "versione": stato.versione,
            "post": [p.model_dump(mode="json") for p in stato.thread],
        }

    # --- Il turno (ogni ingresso nel motore vive DENTRO una richiesta) --------

    @app.post("/api/partita/narrazione")
    async def turno_narrazione(ric: RichiestaVersione) -> dict:
        sessione = _sessione()
        _guardie_di_gioco(ric.versione)
        async with stato.lock:
            snap = await sessione.prossima_narrazione()
            righe = stato.cronaca.preleva() if stato.cronaca else []
            prose = await _drena_prosa(sessione)
            nuovi = stato.registra_turno(
                snap, righe=righe, messaggio=sessione.ultimo_messaggio, prose=prose
            )
        return _risposta_turno(nuovi)

    @app.post("/api/partita/opzioni")
    async def scegli_opzione(ric: RichiestaOpzione) -> dict:
        sessione = _sessione()
        _guardie_di_gioco(ric.versione)
        corrente = stato.snapshot
        if corrente is None or not any(o.indice == ric.indice for o in corrente.opzioni):
            raise ErroreApi(
                422, "opzione_invalida",
                f"L'indice {ric.indice} non è nel menu corrente.",
            )
        async with stato.lock:
            # host→motore: intento tipizzato in coda, poi IL turno del motore (C-7).
            sessione.coda.accoda(PlayerChoseOption(ric.indice))
            snap = sessione.avanza()
            righe = stato.cronaca.preleva() if stato.cronaca else []
            messaggio = None
            if not stato.morto and not snap.opzioni and snap.fase == "narrazione":
                # Menu vuoto ⇒ in attesa: si chiede subito il turno di narrazione
                # (il client segue il progresso via SSE, non orchestra il doppio passo).
                snap = await sessione.prossima_narrazione()
                righe += stato.cronaca.preleva() if stato.cronaca else []
                messaggio = sessione.ultimo_messaggio
            prose = await _drena_prosa(sessione)
            nuovi = stato.registra_turno(
                snap, righe=righe, messaggio=messaggio, prose=prose
            )
        return _risposta_turno(nuovi)

    @app.post("/api/partita/azione/anteprima")
    async def anteprima_azione(ric: RichiestaAnteprima) -> dict:
        sessione = _sessione()
        _guardie_di_gioco(stato.versione)  # guardie senza consumo di versione
        if stato.snapshot is not None and stato.snapshot.fase != "narrazione":
            raise ErroreApi(
                409, "fase_non_valida", "L'azione libera esiste solo in narrazione."
            )
        # Finestra di conferma EDITABILE: deterministica, zero LLM, zero versione.
        riepilogo = sessione.riepiloga_azione(ric.testo)
        return {
            "versione": stato.versione,
            "riepilogo": riepilogo.model_dump(mode="json"),
        }

    @app.post("/api/partita/azione")
    async def esegui_azione(ric: RichiestaAzione) -> dict:
        sessione = _sessione()
        _guardie_di_gioco(ric.versione)
        if stato.snapshot is not None and stato.snapshot.fase != "narrazione":
            raise ErroreApi(
                409, "fase_non_valida", "L'azione libera esiste solo in narrazione."
            )
        async with stato.lock:
            # Il riepilogo si RICALCOLA server-side: il testo può essere stato
            # editato nella finestra di conferma (stessa sequenza della TUI).
            riepilogo = sessione.riepiloga_azione(ric.testo)
            snap = await sessione.esegui_azione(riepilogo)
            righe = stato.cronaca.preleva() if stato.cronaca else []
            prose = await _drena_prosa(sessione)
            nuovi = stato.registra_turno(
                snap, righe=righe, messaggio=sessione.ultimo_messaggio, prose=prose
            )
        return _risposta_turno(nuovi)

    @app.post("/api/partita/scena/battuta")
    async def battuta_scena(ric: RichiestaBattuta) -> dict:
        """UNA battuta nella scena sociale aperta (S1): il testo va alla PORTA
        DI SCENA (`battuta_parlamento`), mai al turno GM — la stessa
        separazione della TUI in modo-scena. Vuoto = tronca la conversazione
        (`abbandona_parlamento`). L'esito della scena rientra dal fascicolo
        del turno GM successivo, non da qui."""
        sessione = _sessione()
        _guardie_di_gioco(ric.versione)
        corrente = stato.snapshot
        if corrente is None or not corrente.scena_aperta:
            raise ErroreApi(
                409, "scena_assente",
                "Nessuna scena aperta: la battuta non ha interlocutore "
                "(apri il dialogo con l'opzione Parlamenta).",
            )
        async with stato.lock:
            testo = ric.testo.strip()
            scambio: list[str] = []
            if not testo:
                sessione.abbandona_parlamento()
                scambio.append("Il crawler tronca la conversazione.")
            else:
                risposta = await sessione.battuta_parlamento(testo)
                scambio.extend((f"«{testo}»", risposta))
            snap = sessione.avanza()
            righe = stato.cronaca.preleva() if stato.cronaca else []
            prose = await _drena_prosa(sessione)
            nuovi = stato.registra_turno(
                snap, righe=righe, messaggio=None, prose=prose, scena=scambio
            )
        return _risposta_turno(nuovi)

    @app.post("/api/partita/salva")
    async def salva(ric: RichiestaVersione) -> dict:
        sessione = _sessione()
        _guardie_di_gioco(ric.versione)
        try:
            return {"messaggio": sessione.salva()}
        except SalvataggioInCombattimento as errore:
            # A scontro aperto il save produrrebbe un soft-lock (audit 2026-08).
            raise ErroreApi(409, "fase_non_valida", str(errore))

    # --- SSE ------------------------------------------------------------------

    @app.get("/api/partita/eventi")
    async def eventi() -> StreamingResponse:
        _sessione()
        return StreamingResponse(
            flusso_eventi(stato),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app
