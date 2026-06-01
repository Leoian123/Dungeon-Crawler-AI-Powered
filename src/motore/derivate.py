"""Quantità derivate dal combattimento: funzioni, mai stat depositate (Gruppo 2 §5).

`max_HP`, attacco, iniziativa, mira, evasione **non** sono stat scritte: sono **derivate**
dalle primarie effettive a runtime, leggendo `stat_eff`. Un modificatore su una primaria
si propaga **da solo** alla derivata. Derivazione **1→1 nell'MVP** (una primaria → una
derivata; le combo N→1 sono sapore post-MVP). I *numeri* (fattori, `EVASIONE_BASE`) sono
SEGNAPOSTO §11; qui le formule sono identità sulla stat-sorgente (forma completa, GR2-10).

`HP_corrente` è invece **stato posseduto** (in `Scheda.punti_vita`): l'unico pezzo del
modello-stat mutato direttamente (dal danno), distinto dalle primarie del vettore. Il suo
*massimo* deriva da Costituzione; `clampa_hp` lo tiene ≤ massimo derivato.
"""

from __future__ import annotations

import esper

from contracts import StatId

from .scheda import Scheda
from .statistiche import stat_eff


def max_hp(entita: int) -> int:
    """Massimo HP derivato da Costituzione (risorsa-pool, §5). 1→1 segnaposto."""
    return stat_eff(entita, StatId.COSTITUZIONE)


def attacco(entita: int) -> int:
    """Attacco/danno base derivato da Forza (mischia MVP, §5)."""
    return stat_eff(entita, StatId.FORZA)


def iniziativa(entita: int) -> int:
    """Iniziativa derivata da Destrezza (§5/§6) — è una **lettura**, non muta la stat."""
    return stat_eff(entita, StatId.DESTREZZA)


def mira(entita: int) -> int:
    """Mira (to-hit) derivata da Destrezza (§6)."""
    return stat_eff(entita, StatId.DESTREZZA)


def evasione(entita: int) -> int:
    """Contributo di Destrezza all'evasione (§6). `EVASIONE_BASE` si somma nel
    combattimento (2b, SEGNAPOSTO §11), non qui."""
    return stat_eff(entita, StatId.DESTREZZA)


def clampa_hp(entita: int) -> None:
    """Tiene `HP_corrente` ≤ massimo derivato (GR2-10). Da richiamare dopo un danno, dopo
    un modificatore che abbassa la Costituzione, e al load (cablaggio 2b)."""
    scheda = esper.try_component(entita, Scheda)
    if scheda is None:
        return
    tetto = max_hp(entita)
    if scheda.punti_vita > tetto:
        scheda.punti_vita = tetto
