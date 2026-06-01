"""Master seed della run come **singleton nel World** (H §4.1, §8.1; H-21).

Il **master seed** è il seme RNG da cui derivano deterministicamente tiri, spawn,
death-check, iniziativa (FNC §9). È **dato di prima classe** della persistenza:
- vive nel blob di stato (è un componente serializzato, §4.1);
- viene **duplicato nei metadati dell'Archivio** (§8.1), perché alla fine-run lo stato
  è invalidato (§7) e, senza la copia, il dono (§12) lo perderebbe.

È **distinto dal "prompt seeded"** (chiave di lookup dell'Archivio, F §8): cose diverse,
in posti diversi (§4.1). Qui c'è il master seed, non la chiave di cache.

`SemeRun` è un **dato puro** (ESP §1): nessuna logica, nessun RNG vivo. Lo *stato/posizione*
dell'RNG (resume mid-run) è dettaglio d'implementazione che, se servirà, vivrà nel solo
blob di stato (§4.1) — **mai** duplicato nell'Archivio (il dono rigioca da turno 0).
"""

from __future__ import annotations

from dataclasses import dataclass

import esper


@dataclass
class SemeRun:
    """Singleton: il master seed della run. Dato puro, serializzabile col save."""

    master_seed: int


def crea_seme(master_seed: int) -> int:
    """Crea il singleton `SemeRun`. Una sola per run-World."""
    return esper.create_entity(SemeRun(master_seed))


def master_seed() -> int:
    """Legge il master seed della run dal singleton."""
    trovati = esper.get_component(SemeRun)
    if len(trovati) != 1:
        raise RuntimeError(f"SemeRun deve essere un singleton: trovati {len(trovati)}")
    return trovati[0][1].master_seed
