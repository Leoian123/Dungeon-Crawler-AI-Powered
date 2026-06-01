"""persistenza — il livello save/load (nodo H), dentro `motore`.

È l'**UNICA autorità su `esper.current_world`** (ESP §0.1): `switch_world`/`delete_world`
vivono **solo qui**, nelle operazioni di confine guscio↔run (`entra_run_nuova`,
`carica_crawler`, `teardown_run`, `parcheggia_default`). Il **guscio orchestra** — decide
*quando* — ma **chiama** queste operazioni; H possiede il *come* (ACV §0). Mai dentro un
Processor, un handler di dominio o la logica di fase (E-2), né in un `process()` (E-4).

*La persistenza tocca i dati, mai conosce i sistemi* (§10.5): qui non si importano
Processor, logica di fase, né il provider — solo componenti dato-puro e l'API World di esper.

Due artefatti separati per file e ciclo vita (§2):
  - **stato** (run-World effimero, JSON in chiaro) — `stato.py`, `formato.py`;
  - **Archivio degli Output Validati** (sidecar compresso, patrimonio) — `archivio.py`.

Traduzione dato↔formato e tag di tipo: `tag.py`. I/O atomico e compressione: `disco.py`.
Orchestrazione (salva/carica/invalida/indice) e contratto di load: `salvataggio.py`.
"""

from .archivio import Archivio
from .disco import (
    StatoCorrotto,
    leggi_archivio,
    leggi_intestazione,
    leggi_stato,
    path_archivio,
    path_stato,
    scrivi_archivio,
    scrivi_stato,
)
from .formato import (
    SCHEMA_VERSION,
    ArchivioSerializzato,
    ComponenteSerializzato,
    Corpo,
    EntitaSerializzata,
    Intestazione,
    MetadatiArchivio,
    RecordArchivio,
    VersioneIncompatibile,
    migra,
)
from .salvataggio import (
    MODEL_ID_DEFAULT,
    NOME_DEFAULT,
    NOME_RUN,
    CaricamentoFallito,
    VoceIndice,
    carica_archivio,
    carica_crawler,
    carica_da_disco,
    entra_run_nuova,
    indice_crawler,
    invalida,
    parcheggia_default,
    salva_run,
    teardown_run,
)
from .stato import Stato, applica_stato, serializza_stato
from .tag import (
    deserializza_componente,
    e_persistente,
    serializza_componente,
    tag_di,
    tipi_registrati,
    tipo_di,
)

__all__ = [
    # artefatti
    "Archivio",
    "Stato",
    # formato su disco
    "SCHEMA_VERSION",
    "Intestazione",
    "Corpo",
    "EntitaSerializzata",
    "ComponenteSerializzato",
    "RecordArchivio",
    "MetadatiArchivio",
    "ArchivioSerializzato",
    "VersioneIncompatibile",
    "migra",
    # traduzione / tag
    "tipi_registrati",
    "e_persistente",
    "tag_di",
    "tipo_di",
    "serializza_componente",
    "deserializza_componente",
    # (de)serializzazione dello stato
    "serializza_stato",
    "applica_stato",
    # I/O su disco
    "StatoCorrotto",
    "path_stato",
    "path_archivio",
    "scrivi_stato",
    "leggi_stato",
    "leggi_intestazione",
    "scrivi_archivio",
    "leggi_archivio",
    # save/load: unica autorità su current_world (ESP §0.1)
    "MODEL_ID_DEFAULT",
    "NOME_RUN",
    "NOME_DEFAULT",
    "CaricamentoFallito",
    "VoceIndice",
    "salva_run",
    "carica_da_disco",
    "carica_archivio",
    "invalida",
    "indice_crawler",
    # operazioni di confine guscio↔run (le chiama il guscio)
    "entra_run_nuova",
    "carica_crawler",
    "teardown_run",
    "parcheggia_default",
]
