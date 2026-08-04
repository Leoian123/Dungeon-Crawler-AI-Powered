"""Corredo di combattimento per-entità: gli slot gear che erano default globali (Gruppo 2 §5).

`Corredo` è **dato puro** (ESP §1): tre chiavi di categoria — `armatura` (→ `M_ARMATURA`),
`taglia` (→ `M_TAGLIA`), `arma` (→ `COEFF_ACC`). I *numeri* dietro le categorie vivono in
`calibrazione.py`; qui c'è solo la **selezione** per-entità.

È il "seam gear" che `derivate.py` legge: un'entità **con** `Corredo` usa i suoi slot, una
**senza** (protagonista, nemici-da-scalari) ripiega sui default globali `*_DEFAULT` — così
l'apertura del seam è retro-compatibile bit-per-bit. Componente **persistente** (registry
in `persistenza/tag.py`, come `Resistenze`): il profilo del mob rivelato round-trippa.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Corredo:
    """Slot gear per-entità: chiavi delle tabelle di calibrazione (mai numeri inline)."""

    armatura: str
    taglia: str
    arma: str
