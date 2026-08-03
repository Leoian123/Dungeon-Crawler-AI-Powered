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
`motore`, mai esper — membrana verificata in tests/test_membrana_vista.py.
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts import PlayerChoseOption
from main import carica_sessione, costruisci_sessione, elenca_crawler

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

    @app.get("/api/crawlers")
    async def crawlers() -> dict:
        """L'elenco degli slot (slot = crawler, H §1): la vista dell'hub. Nessuna
        guardia di sessione: si consulta anche a run aperta."""
        return {
            "crawlers": [c.model_dump(mode="json") for c in elenca_crawler(stato.directory)],
            "attiva": stato.crawler,
        }

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
            sessione = costruisci_sessione(
                nome=ric.nuovo.nome, seed=ric.nuovo.seed,
                directory=stato.directory, provider=provider,
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
        stato.adotta(
            sessione, etichetta,
            crawler={"uuid": sessione.uuid, "nome": sessione.etichetta},
        )
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
            messaggio = sessione.esci()
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
            nuovi = stato.registra_turno(
                snap, righe=righe, messaggio=sessione.ultimo_messaggio
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
            nuovi = stato.registra_turno(snap, righe=righe, messaggio=messaggio)
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
            nuovi = stato.registra_turno(
                snap, righe=righe, messaggio=sessione.ultimo_messaggio
            )
        return _risposta_turno(nuovi)

    @app.post("/api/partita/salva")
    async def salva(ric: RichiestaVersione) -> dict:
        sessione = _sessione()
        _guardie_di_gioco(ric.versione)
        return {"messaggio": sessione.salva()}

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
