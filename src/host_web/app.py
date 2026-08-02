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
from pydantic import BaseModel, ConfigDict

from contracts import PlayerChoseOption
from main import costruisci_sessione

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

class RichiestaPartita(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seed: int = 0
    gm: Literal["fake", "live"] = "fake"


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
        """Ordine: morto (410) → occupato (409) → versione stantia (409). Tra il
        check del lock e l'acquisizione non c'è alcun await: niente corse."""
        if stato.morto:
            raise ErroreApi(410, "run_terminata", "Permadeath: la run è terminata.")
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
            "snapshot": snap.model_dump(mode="json") if snap is not None else None,
            "gm": stato.gm_etichetta,
        }

    def _risposta_turno(nuovi: list[PostThread]) -> dict:
        return {**_stato_partita(), "post": [p.model_dump(mode="json") for p in nuovi]}

    # --- Ciclo di vita della partita -----------------------------------------

    @app.post("/api/partita", status_code=201)
    async def crea_partita(ric: RichiestaPartita) -> dict:
        if stato.sessione is not None:
            raise ErroreApi(
                409, "partita_esistente",
                "Una partita è già in corso (una per processo): riavvia l'host per "
                "ricominciare.",
            )
        if ric.gm == "live":
            provider, etichetta = _provider_live(stato)
        else:
            provider, etichetta = None, "GM offline (contenuto scriptato)"
        # provider=None ⇒ FakeProvider: il default resta SICURO, il live è esplicito.
        sessione = costruisci_sessione(seed=ric.seed, provider=provider)
        stato.adotta(sessione, etichetta)
        return _stato_partita()

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
