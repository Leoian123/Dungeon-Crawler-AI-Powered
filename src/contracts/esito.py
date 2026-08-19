"""esito — lo strato SOVRA-RUN in forma di contratto (la «bacheca dei crawler»).

La direzione decisa (2026-08-19): run rigorosamente single-player, con uno
strato sociale ASINCRONO sopra — necrologi dei crawler morti, seed del giorno,
classifiche, «fantasmi» delle run altrui come lore. Il taglio che rende tutto
questo compatibile con le linee rosse del progetto:

- attraverso il confine viaggiano solo ESITI (piccoli dati), mai stato di
  gioco, mai chiamate LLM, mai la chiave;
- il fantasma è LORE, mai stato: non tocca combattimento, drop o numeri;
- né i contracts né il motore guardano l'orologio (J): la data del «giorno» la
  passa l'host, il timestamp lo appone chi scrive su disco.

QUI vive solo il vocabolario. Fase A (questo branch): `EsitoRun`, depositato
dal motore al terminale di run nel ledger `esiti.jsonl`. Fasi B/C/D (branch
futuri: bacheca su react-ecosystem, server-classifica FUORI dal repo motore —
importerà solo `contracts`, la membrana vale anche lì —, fantasmi): i DTO sono
PREPARATI e non ancora consumati da nessuno. Sono il contratto, non lo sviluppo.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, field_validator

from .vista import Terminale


def _terminale_conclusivo(v: Terminale) -> Terminale:
    """Un esito esiste SOLO per una run finita davvero (morte o vittoria).
    L'uscita volontaria non è un esito: la run riprenderà."""
    if v is Terminale.USCITA_VOLONTARIA:
        raise ValueError("l'uscita volontaria non è un esito: la run riprenderà")
    return v


# Il CLAMP dei testi (avversariale 2026-08-19): nome/causa/epitaffio finiscono
# in titoli di bacheca, righe JSONL e — i fantasmi — nel PROMPT del GM. Qui si
# NORMALIZZA (whitespace e control char collassati: un newline nel nome non
# forgia mai righe o titoli) e si TRONCA (una riga forgiata da megabyte non
# gonfia bacheca o prompt). Troncare, MAI rifiutare: il deposito è best-effort
# e un esito legittimo respinto sarebbe storia persa. Il clamp vale anche in
# RILETTURA (la bacheca ri-valida ogni riga): la spazzatura già a ledger
# rientra pulita.
_MAX_TESTO = 200
_MAX_MOMENTO = 300
_MAX_MOMENTI = 8


def _pulito(massimo: int):
    def _clamp(v):
        if isinstance(v, str):
            return " ".join(v.split())[:massimo]
        return v  # non-stringa: la respinge la validazione di tipo, non il clamp

    return _clamp


def _momenti_puliti(v):
    if isinstance(v, (list, tuple)):
        return tuple(_pulito(_MAX_MOMENTO)(m) for m in v[:_MAX_MOMENTI])
    return v


class EsitoRun(BaseModel):
    """Come è finita UNA run: l'atomo dello strato sovra-run (Fase A).

    Solo dati che il motore possiede già al terminale — niente viene calcolato
    apposta, niente stat vive. Una run ha un solo terminale, quindi un solo
    esito: la `chiave()` è deterministica e il deposito è idempotente — un
    doppio onore del permadeath (o il save-scumming) riscrive la stessa riga,
    mai due (stesso principio dell'outbox wiki, rev. 3 §4-bis)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uuid_run: str
    nome: str                      # l'etichetta del crawler (slot = crawler, H §1)
    seed: int                      # il master seed (H §4.1): l'esito resta rigiocabile
    terminale: Terminale           # SOLO SCONFITTA o PIANO_COMPLETATO (validator)
    stagione: int = 1
    profondita: int = 1            # il piano raggiunto
    tick: int = 0                  # l'orologio di piano alla chiusura (J)
    causa: str = ""                # chi/cosa ha ucciso (diegetico) — vuota in vittoria
    momenti: tuple[str, ...] = ()  # i salienti deterministici (materia del necrologio)
    ts: str = ""                   # timestamp dell'HOST alla scrittura, mai del motore

    _conclusivo = field_validator("terminale")(_terminale_conclusivo)
    _nome_pulito = field_validator("nome", "causa", mode="before")(_pulito(_MAX_TESTO))
    _salienti = field_validator("momenti", mode="before")(_momenti_puliti)

    def chiave(self) -> str:
        """L'id deterministico del deposito (dedup del ledger) — per RUN, non
        per (run, terminale): una run legittima ha un solo terminale, e la
        PRIMA chiusura fa storia. Chiudere qui la falla trovata dal giro
        avversariale (2026-08-19): una run resuscitata da copia esterna dei
        file di save che poi VINCE non può affiancare un `piano_completato`
        alla morte già a ledger — il tampering resta inerte (threat model
        no-DRM: non si impedisce la copia, si rende muta)."""
        return f"esito:{self.uuid_run}"


def seed_del_giorno(data_iso: str, stagione: int) -> int:
    """Il seed condiviso del «daily» (Fase C): stessa data + stessa stagione =
    stesso dungeon per chiunque, SENZA server — chiunque può derivarlo. È il
    protocollo condiviso client/server, per questo vive nei contracts.

    `data_iso` (es. "2026-08-19") la fornisce l'HOST: i contracts non guardano
    mai l'orologio (J). Derivazione stabile per costruzione: sha256, primi 4
    byte — cambiarla romperebbe le classifiche di tutti, non si tocca."""
    digest = hashlib.sha256(f"{data_iso}|stagione-{stagione}".encode("utf-8"))
    return int.from_bytes(digest.digest()[:4], "big")


class NecrologioCrawler(BaseModel):
    """Il post della bacheca per un crawler morto (Fase B — PREPARATO, non
    ancora consumato). Il CORPO lo compone il motore dai fatti (esito +
    Archivio); l'AI al più lo veste dentro il canale proposta→gate esistente —
    mai inventare i fatti. Consumatore previsto: il forum sovra-run (branch
    react-ecosystem)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uuid_run: str
    nome: str
    titolo: str
    corpo: str
    stagione: int = 1
    profondita: int = 1
    ts: str = ""


class VoceClassifica(BaseModel):
    """Una riga della classifica del giorno (Fase C — PREPARATA, non ancora
    consumata). Si DERIVA da un `EsitoRun` con `da_esito`: il client proietta
    l'esito, non inventa mai la voce."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    nome: str
    terminale: Terminale
    profondita: int = 1
    tick: int = 0
    uuid_run: str = ""

    _conclusivo = field_validator("terminale")(_terminale_conclusivo)

    @classmethod
    def da_esito(cls, esito: EsitoRun) -> "VoceClassifica":
        return cls(
            nome=esito.nome,
            terminale=esito.terminale,
            profondita=esito.profondita,
            tick=esito.tick,
            uuid_run=esito.uuid_run,
        )


class ClassificaGiorno(BaseModel):
    """La classifica di UN giorno (Fase C — PREPARATA): la forma che il
    server minimale raccoglie e serve. `seed` è ridondante di proposito
    rispetto a `seed_del_giorno(data_iso, stagione)`: il client la verifica,
    non si fida."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    data_iso: str
    stagione: int = 1
    seed: int = 0
    voci: tuple[VoceClassifica, ...] = ()


class FantasmaRun(BaseModel):
    """La traccia di una run ALTRUI dentro la mia (Fase D — PREPARATA, non
    ancora consumata): «qui giace X, aperto in due da Y».

    Due regole ferree, le stesse linee rosse di sempre:
    - il fantasma è LORE, mai stato: non tocca combattimento, drop, numeri —
      entra al più nel fascicolo della scena come fatto da vestire;
    - il set di fantasmi ricevuto è INPUT della run e si CONGELA nel save
      (come `StagioneAttiva`): il reload mostra le stesse tracce, o il
      determinismo/replay salta."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    nome: str
    causa: str = ""
    profondita: int = 1
    stagione: int = 1
    seed: int = 0
    epitaffio: str = ""  # una riga già vestita, pronta per la scena

    # L'epitaffio ENTRA NEL PROMPT del GM: il clamp qui è il primo strato
    # contro un fantasma remoto ostile (testo lungo o multi-riga che tenta di
    # farsi istruzione). Il gate a valle resta l'arbitro — il fantasma non ha
    # comunque alcuna via verso lo stato.
    _nome_pulito = field_validator("nome", "causa", "epitaffio", mode="before")(
        _pulito(_MAX_TESTO)
    )

    @classmethod
    def da_esito(cls, esito: EsitoRun) -> "FantasmaRun":
        return cls(
            nome=esito.nome,
            causa=esito.causa,
            profondita=esito.profondita,
            stagione=esito.stagione,
            seed=esito.seed,
        )
