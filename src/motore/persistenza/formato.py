"""Forma su disco dei due artefatti + versione/migrazione (H §4, §8.1, §9.2; H-13).

Modelli **Pydantic** del formato di salvataggio: la stessa disciplina del contratto F,
riusata in **load** per validare ciò che si legge dal disco (H §9.1). Sono DTO di
serializzazione, **interni a H** (non `contracts`): descrivono il *file*, non il dominio.

Due artefatti separati (§2):
  - **stato** (`Intestazione` + `Corpo`): il run-World effimero, in chiaro;
  - **Archivio** (`MetadatiArchivio` + `RecordArchivio`): il sidecar compresso, patrimonio.

`schema_version` è presente **già a v1** (H-13): le migrazioni sono una catena di
funzioni `v→v+1` applicate fino alla corrente. Nessuna migrazione esiste ancora — il
formato non è mai cambiato in modo che un save vecchio non sappia descriversi — ma il
campo e il meccanismo ci sono, e il meccanismo è **provato** (per iniezione, senza
spendere l'identità di una versione: vedi `tests/test_versione_save.py`).
"""

from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, ConfigDict

# Versione corrente dello schema di salvataggio. Migrazioni: v→v+1 (§9.2).
#
# ⚠️ IL NUMERO NON SI ALZA PER ESERCIZIO. Un bump è l'IDENTITÀ di un formato: alzarlo
# senza una trasformazione reale timbra i save esistenti con la versione nuova senza
# cambiarne un byte, e brucia irreversibilmente quello slot — la migrazione v→v+1 VERA,
# quando servirà, non potrà più attraversare i file già timbrati. È esattamente il
# pavimento che si voleva non rompere.
#
# Il meccanismo si esercita INIETTANDO la catena (`migra(..., migrazioni=...,
# versione_corrente=...)`, vedi tests/test_versione_save.py): così è provato che
# funziona senza spendere l'identità di una versione.
#
# Si alza quando — e solo quando — la forma dei dati persistiti cambia in modo che
# un save vecchio non sappia più descriversi: allora si scrive la migrazione, la si
# prova su un save reale della versione precedente, e si bumpa.
SCHEMA_VERSION = 1

_CHIUSO = ConfigDict(extra="forbid")


# --- Stato: intestazione (header di elenco) + corpo (il World) -----------------

class ComponenteSerializzato(BaseModel):
    """Un componente: tag stabile (H-3) + dati tradotti da H (H-2)."""

    model_config = _CHIUSO
    tag: str
    dati: dict


class EntitaSerializzata(BaseModel):
    """Un'entità persistente come la lista dei suoi componenti registrati."""

    model_config = _CHIUSO
    componenti: list[ComponenteSerializzato]


class Intestazione(BaseModel):
    """Header di **elenco** (H §5): letto da solo dallo scan del menu, senza
    deserializzare l'intero corpo (no deep-parse, H-22)."""

    model_config = _CHIUSO
    uuid: str
    etichetta: str
    profondita: int
    timestamp: float
    schema_version: int
    model_id: str


class Corpo(BaseModel):
    """Il corpo dello stato: entità (incl. i singleton), slot d'esplorazione,
    posizione-RNG opzionale (resume mid-run), riferimento al sidecar."""

    model_config = _CHIUSO
    entita: list[EntitaSerializzata]
    archivio_ref: str
    esplorazione: dict | None = None     # slot della Mappa (topologia+posizione+visitate)
    rng_state: list | None = None        # posizione-RNG: solo qui, mai nell'Archivio (§4.1)


# --- Archivio degli Output Validati (sidecar) ---------------------------------

class RecordArchivio(BaseModel):
    """Un record d'Archivio: SOLO selezione + narrazione, MAI statistiche (H-11).

    `tipo` è lo slot F-13 ("output **oppure** marcatore di fallback"): nell'MVP si
    popola solo `"output"` — il ramo-marcatore esiste in forma, non esercitato (§8.3).
    """

    model_config = _CHIUSO
    chiave: str                          # il "prompt seeded" (chiave di lookup, F §8)
    contenuto: dict
    tipo: str = "output"                 # "output" | "fallback" (slot, MVP solo output)


class MetadatiArchivio(BaseModel):
    """Metadati a livello di store: la **copia del master seed** (sopravvive
    all'invalidazione di fine-run, §8.1) e il model id."""

    model_config = _CHIUSO
    master_seed: int
    model_id: str
    schema_version: int


class ArchivioSerializzato(BaseModel):
    model_config = _CHIUSO
    metadati: MetadatiArchivio
    record: list[RecordArchivio] = []


# --- Versione: rifiuto del futuro + catena di migrazioni v→v+1 (§9.2) ----------

class VersioneIncompatibile(Exception):
    """Save di una versione futura (`schema_version` > corrente): rifiuto pulito."""


# Catena di migrazioni: indice = versione di partenza, valore = (intest, corpo)→(intest, corpo).
# Vuota finché `SCHEMA_VERSION` è 1 — e deve restarlo: una voce qui senza un bump non
# scatterebbe mai, un bump senza la voce corrispondente rifiuta i save vecchi (il test
# `test_la_catena_copre_ogni_versione` è la rete). Il *meccanismo* c'è da subito (H-13)
# ed è provato per iniezione (tests/test_versione_save.py): quando servirà la prima
# migrazione vera, si saprà già che la catena funziona.
_MIGRAZIONI: dict[int, Callable[[dict, dict], tuple[dict, dict]]] = {}


def migra(
    intestazione: dict,
    corpo: dict,
    *,
    migrazioni: dict[int, Callable[[dict, dict], tuple[dict, dict]]] | None = None,
    versione_corrente: int = SCHEMA_VERSION,
) -> tuple[dict, dict]:
    """Porta (intestazione, corpo) alla versione corrente applicando la catena
    `v→v+1` (§9.2). Rifiuta una versione futura. `migrazioni` iniettabile per i test.
    """
    catena = _MIGRAZIONI if migrazioni is None else migrazioni
    versione = intestazione.get("schema_version")
    if not isinstance(versione, int):
        raise VersioneIncompatibile("schema_version mancante o non intero")
    if versione > versione_corrente:
        raise VersioneIncompatibile(
            f"save di versione futura {versione} > {versione_corrente}"
        )
    while versione < versione_corrente:
        if versione not in catena:
            raise VersioneIncompatibile(f"nessuna migrazione da v{versione}")
        intestazione, corpo = catena[versione](intestazione, corpo)
        versione += 1
        intestazione["schema_version"] = versione
    return intestazione, corpo
