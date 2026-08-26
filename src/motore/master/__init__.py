"""Master-Engine — il canale unico delle chiamate AI del motore.

Ogni percorso verso l'LLM è una **Rotta dichiarata** (schema, corsia, retry,
phase-gate, gating) in un registro; il `MasterEngine` è il dispatcher che le
esegue: guardia di fase → corsia → retry → tally per rotta. Aggiungere un
percorso nuovo = una dichiarazione + un costruttore di prompt (+ gate/fallback
propri se tocca stato), MAI una pipeline nuova.

Il Master-Engine **avvolge** — non riscrive — la disciplina esistente: prompt e
gate restano dominio dei moduli che li possiedono (`narrazione.py`, `gm.py`);
i provider arrivano PER INIEZIONE dal composition root (mai un import di
`provider` nel motore — lint in `test_motore_discipline`).
"""

from .engine import ConsumoRotta, MasterEngine
from .rotte import ROTTE, Corsia, Rotta, registra_rotta

__all__ = [
    "ConsumoRotta",
    "Corsia",
    "MasterEngine",
    "ROTTE",
    "Rotta",
    "registra_rotta",
]
