"""Livello save/load: l'**UNICA autorità su `esper.current_world`** (ESP §0.1, H §7/§9/§10).

H **possiede il meccanismo** del cambio di contesto World: `switch_world`/`delete_world`
vivono **solo qui** (ESP §0.1: "il livello di save/load è l'unica autorità su
`current_world`; nessun altro modulo cambia contesto"). Il **guscio orchestra** — decide
*quando* entrare/uscire dalla run — ma lo fa **chiamando** le operazioni di confine di
questo modulo (ACV §0: "H possiede il *come*, il guscio è dove `current_world` cambia").
**Mai** un `switch_world` dentro un Processor, un handler di dominio o la logica di fase
(E-2), né dentro un `process()` in volo (E-4).

Operazioni di confine guscio↔run (le chiama il guscio):
  - **entra_run_nuova** — nuova partita (ACV 3a): contesto `"run"` fresco; il guscio poi
    fa nascere il protagonista (E-5).
  - **carica_crawler** — caricamento (ACV 3b): valida **prima** (niente switch su
    fallimento → `current_world` intatto, H-12), poi `"run"` fresco e `applica_stato`.
  - **teardown_run** — teardown (ACV 7): `switch_world(default)` **poi**
    `delete_world("run")` (E-6); mai delete del contesto attivo (ESP §0.1).
  - **parcheggia_default** — boot/parcheggio: il default è il contesto residente del
    guscio (ACV §7.1).

Operazioni su disco / World corrente (nessuno switch):
  - **salva_run** — scrittura a evento/comando (H-6), **in-run** (World vivo): precede il
    teardown, mai dentro un `process()` (H-7); durabilità sidecar→stato (§10.2); backup
    della coppia coerente (§10.3).
  - **carica_da_disco** — load valida-e-degrada (§9), **senza toccare il World**.
  - **invalida** — fine-run (morte 6a **e** vittoria 6b): rimuove il save vivo (§9.4, H-20).
  - **indice_crawler** — scan per intestazione (H-22).

Un load fallito a qualunque strato (formato, coerenza, versione) è un `CaricamentoFallito`:
si resta nel guscio, si segnala, **niente caricamento parziale** (§9.3).
"""

from __future__ import annotations

from pathlib import Path

import esper

from ..fase import Fase
from ..seme import master_seed
from .archivio import Archivio
from .disco import (
    SUFFISSO_STATO,
    StatoCorrotto,
    backup_coppia,
    leggi_archivio,
    leggi_intestazione,
    leggi_stato,
    path_archivio,
    path_stato,
    scrivi_archivio,
    scrivi_stato,
)
from .formato import (
    Corpo,
    Intestazione,
    VersioneIncompatibile,
    migra,
)
from .stato import Stato, applica_stato, serializza_stato
from .tag import tipo_di

# Model id sotto cui la run è generata (forward-compat per replay/dono, §4.1). È solo
# un'etichetta di stato: i dettagli del modello si verificano sui doc API, non qui (F-12).
MODEL_ID_DEFAULT = "claude-opus-4-8"

# Il contesto unico della run (G §6.4): un solo nome, un solo run-World vivo (G-12). Il
# default è il contesto residente del guscio (ACV §7.1).
NOME_RUN = "run"
NOME_DEFAULT = "default"


class CaricamentoFallito(Exception):
    """Load rifiutato (formato/coerenza/versione). Non muta `current_world` (§9.3)."""


# --- Scrittura: a evento/comando, in-run, durabilità ordinata (H-6, H-7, H-14) -

def salva_run(
    directory: Path,
    *,
    archivio: Archivio | None = None,
    model_id: str = MODEL_ID_DEFAULT,
    etichetta: str | None = None,
    timestamp: float = 0.0,
    esplorazione: dict | None = None,
    rng_state: list | None = None,
) -> Path:
    """Salva il World corrente (in-run, NESSUNO `switch_world`). Ritorna il path di stato.

    Il chiamante (guscio) invoca questo **prima** del teardown, a evento/comando — mai
    da un `process()`. La cadenza è del guscio; H è solo il meccanismo di scrittura.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    seme = master_seed()
    if archivio is None:
        # Cintura (audit 2026-08): senza l'Archivio del chiamante si RILEGGE il
        # sidecar esistente — mai sovrascrivere la storia congelata con un vuoto.
        archivio = carica_archivio(directory, _peek_uuid())
    if archivio is None:
        archivio = Archivio(master_seed=seme, model_id=model_id)

    stato = serializza_stato(
        model_id=model_id,
        timestamp=timestamp,
        etichetta=etichetta,
        archivio_ref=path_archivio(directory, _peek_uuid()).name,
        esplorazione=esplorazione,
        rng_state=rng_state,
    )
    uuid = stato.intestazione.uuid

    # Backup della coppia coerente PRIMA di sovrascrivere il save vivo (§10.3).
    backup_coppia(directory, uuid)

    # Ordine di durabilità: il sidecar è reso durevole PRIMA che lo stato lo referenzi.
    scrivi_archivio(path_archivio(directory, uuid), archivio.to_dict())
    scrivi_stato(
        path_stato(directory, uuid),
        stato.intestazione.model_dump(),
        stato.corpo.model_dump(),
    )
    return path_stato(directory, uuid)


def _peek_uuid() -> str:
    """L'uuid del protagonista corrente (per comporre l'archivio_ref senza ri-camminare)."""
    from ..scheda import protagonista

    _ent, marker, _scheda = protagonista()
    return marker.id_dominio


# --- Lettura/validazione: NON tocca il World (contratto di load, §9) -----------

def _verifica_coerenza(intestazione: Intestazione, corpo: Corpo) -> None:
    """Strato 2 del load: i valori sono nel dominio del possibile (§9.1.2).

    - profondità ≥ 1;
    - ogni tag di componente ha un binding nel registry (H-3);
    - `FaseCorrente`, se presente, porta un valore di fase legale;
    - ESATTAMENTE un protagonista: l'invariante mono-PG che il motore impone a
      runtime (death-check, `protagonista()`) va rifiutato QUI, al load — un save
      manomesso con N protagonisti altrimenti passerebbe la validazione e
      esploderebbe al primo tick, tradendo H-12 (valida-e-degrada, mai crash).
    """
    if intestazione.profondita < 1:
        raise CaricamentoFallito(f"profondità impossibile: {intestazione.profondita}")
    protagonisti = 0
    for ent in corpo.entita:
        for comp in ent.componenti:
            try:
                tipo_di(comp.tag)
            except KeyError as e:
                raise CaricamentoFallito(str(e)) from e
            if comp.tag == "protagonista":
                protagonisti += 1
            if comp.tag == "fase_corrente":
                valore = comp.dati.get("fase")
                if valore not in {f.value for f in Fase}:
                    raise CaricamentoFallito(f"fase illegale: {valore!r}")
    if protagonisti != 1:
        raise CaricamentoFallito(
            f"protagonista singleton atteso nel save: trovati {protagonisti}"
        )


def carica_da_disco(directory: Path, uuid: str) -> Stato:
    """Legge, valida e (se serve) migra lo stato. **Non** tocca `current_world`.

    Solleva `CaricamentoFallito` su qualunque strato che non passi (formato, versione,
    coerenza): il chiamante resta nel guscio, niente stato parziale (§9.3).
    """
    path = path_stato(Path(directory), uuid)
    try:
        intest_raw, corpo_raw = leggi_stato(path)
    except StatoCorrotto as e:
        raise CaricamentoFallito(str(e)) from e

    try:
        intest_raw, corpo_raw = migra(intest_raw, corpo_raw)  # versione (§9.2)
        intestazione = Intestazione.model_validate(intest_raw)  # formato/schema (§9.1)
        corpo = Corpo.model_validate(corpo_raw)
    except VersioneIncompatibile as e:
        raise CaricamentoFallito(f"versione incompatibile: {e}") from e
    except Exception as e:  # ValidationError e affini → degrado pulito
        raise CaricamentoFallito(f"formato non valido: {e}") from e

    _verifica_coerenza(intestazione, corpo)  # coerenza interna (§9.1.2)
    return Stato(intestazione=intestazione, corpo=corpo)


def carica_archivio(directory: Path, uuid: str) -> Archivio | None:
    """Carica il sidecar dell'Archivio, o `None` se assente/illeggibile (lasco, H-10)."""
    path = path_archivio(Path(directory), uuid)
    if not path.exists():
        return None
    try:
        return Archivio.from_dict(leggi_archivio(path))
    except Exception:
        return None  # sidecar illeggibile: cache vuota, si rigenera


# --- Operazioni di confine guscio↔run: l'autorità su `current_world` (ESP §0.1) -
# `switch_world`/`delete_world` vivono SOLO qui. Il guscio le CHIAMA (decide il quando);
# H le esegue (possiede il come). Mai dentro un Processor/handler/process() (E-2/E-4).

def parcheggia_default() -> None:
    """Parcheggia nel default World — il contesto residente del guscio (ACV §7.1)."""
    esper.switch_world(NOME_DEFAULT)


def _entra_run_pulito() -> None:
    """Contesto `"run"` **fresco** e unico (G §6.4, G-12): dal default si elimina un
    eventuale `"run"` residuo e si ricrea vuoto. Non si elimina il contesto attivo
    (ESP §0.1): si switcha via prima."""
    esper.switch_world(NOME_DEFAULT)
    if NOME_RUN in esper.list_worlds():
        esper.delete_world(NOME_RUN)
    esper.switch_world(NOME_RUN)


def entra_run_nuova() -> None:
    """Confine guscio→run, **nuova partita** (ACV 3a): entra in un `"run"` fresco. Il
    guscio chiama questa e **poi** fa nascere il protagonista (E-5)."""
    _entra_run_pulito()


def carica_crawler(directory: Path, uuid: str) -> bool:
    """Confine guscio→run, **caricamento** (ACV 3b): valida **prima** di toccare il
    World; su fallimento ritorna `False` e il contesto resta (o torna) al default —
    mai un World parziale come contesto attivo (H-12/E-4). Solo se valido: `"run"`
    fresco → `applica_stato` (deserializzazione al confine, E-5)."""
    try:
        stato = carica_da_disco(directory, uuid)
    except CaricamentoFallito:
        return False  # current_world INTATTO: nessuno switch è avvenuto
    _entra_run_pulito()
    try:
        applica_stato(stato)
    except Exception:
        # La validazione di carico guarda la BUSTA; la ricostruzione dei componenti
        # (`tipo(**dati)`) avviene QUI e può tradirla — un campo rinominato senza
        # migrazione passa i tre strati e poi esplode a metà applicazione. Il World
        # parziale non deve sopravvivere né restare il contesto attivo (audit
        # fondamenta 2026-08): teardown e si torna al menu, save intatto su disco.
        teardown_run()
        return False
    return True


def teardown_run() -> None:
    """Teardown (ACV 7): `switch_world(default)` **poi** `delete_world("run")` (E-6).
    Mai delete del contesto attivo; il default torna il parcheggio del guscio."""
    esper.switch_world(NOME_DEFAULT)
    if NOME_RUN in esper.list_worlds():
        esper.delete_world(NOME_RUN)


# --- Invalidazione a fine-run: morte 6a e vittoria 6b (§9.4, H-20) -------------

def invalida(directory: Path, uuid: str) -> None:
    """Rimuove il save vivo (stato + sidecar). Vale per morte **e** vittoria/piano-
    completato: entrambe concludono la run (suspend-on-load: non c'è "continua dopo la
    fine"). Il backup di recovery resta come protezione da corruzione, non da ripristino."""
    directory = Path(directory)
    for p in (path_stato(directory, uuid), path_archivio(directory, uuid)):
        if p.exists():
            p.unlink()


# --- Indice dei crawler: scan per intestazione, no deep-parse (H-22) -----------

class VoceIndice:
    """Una voce dell'elenco crawler. `corrotta=True` se l'intestazione non parsa."""

    __slots__ = ("uuid", "etichetta", "profondita", "timestamp", "corrotta")

    def __init__(
        self, uuid: str, etichetta: str, profondita: int, timestamp: float, corrotta: bool
    ) -> None:
        self.uuid = uuid
        self.etichetta = etichetta
        self.profondita = profondita
        self.timestamp = timestamp
        self.corrotta = corrotta

    def __repr__(self) -> str:
        return (
            f"VoceIndice(uuid={self.uuid!r}, etichetta={self.etichetta!r}, "
            f"profondita={self.profondita}, corrotta={self.corrotta})"
        )


def indice_crawler(directory: Path) -> list[VoceIndice]:
    """Elenca i crawler leggendo **solo l'intestazione** di ogni save (H-22).

    Un save la cui intestazione non parsa compare come voce **«corrotta»**: non fa
    crashare lo scan né scompare in silenzio (degrado in scan, §5)."""
    directory = Path(directory)
    if not directory.exists():
        return []
    voci: list[VoceIndice] = []
    for path in sorted(directory.glob(f"*{SUFFISSO_STATO}")):
        uuid = path.name[: -len(SUFFISSO_STATO)]
        if uuid.endswith(".bak"):
            continue  # i backup sono SOLO recovery (H §10.3), mai slot dell'elenco
        try:
            intest = leggi_intestazione(path)
            voci.append(
                VoceIndice(
                    uuid=intest["uuid"],
                    etichetta=intest["etichetta"],
                    profondita=intest["profondita"],
                    timestamp=intest["timestamp"],
                    corrotta=False,
                )
            )
        except (StatoCorrotto, KeyError, TypeError):
            voci.append(VoceIndice(uuid, "«corrotta»", -1, 0.0, corrotta=True))
    return voci
