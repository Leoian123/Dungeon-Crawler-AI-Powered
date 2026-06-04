"""Quantità derivate dal combattimento: funzioni, mai stat depositate (Gruppo 2 §5).

`max_HP`, attacco, iniziativa, e le quattro derivate del risolutore (`atk_eff`, `def_eff`,
`eva_eff`, `acc_eff`) **non** sono stat scritte: sono **derivate** dalle primarie effettive
a runtime, leggendo `stat_eff` (GR2-3 — nessuna lettura diretta di `Primarie[...]`). Un
modificatore su una primaria si propaga **da solo** alla derivata. I *numeri* (tabelle,
pesi, coefficienti) sono SEGNAPOSTO §11 e vivono in `calibrazione.py`, **importati** qui,
mai inline (guida §0).

`HP_corrente` è invece **stato posseduto** (in `Scheda.punti_vita`): l'unico pezzo del
modello-stat mutato direttamente (dal danno), distinto dalle primarie del vettore. Il suo
*massimo* deriva da Costituzione; `clampa_hp` lo tiene ≤ massimo derivato.

**Contratto di scala (§6, da non sbagliare):** `atk_eff` è in **unità**, `def_eff` in
**centesimi** (la conversione `/100` vive nel danno, non qui). `eva_eff`/`acc_eff` sono
scalari (float) del check 1.
"""

from __future__ import annotations

import esper

from contracts import StatId

from . import calibrazione as cal
from .scheda import Scheda
from .statistiche import stat_eff


def max_hp(entita: int) -> int:
    """Massimo HP derivato da Costituzione (risorsa-pool, §5): `HP_BASE + K_HP·Cost`.

    `round(...) → int`: l'HP è un intero anche con `K_HP` frazionario (leva di calibrazione)."""
    return round(cal.HP_BASE + cal.K_HP * stat_eff(entita, StatId.COSTITUZIONE))


def attacco(entita: int) -> int:
    """Attacco/danno base derivato da Forza (mischia MVP, §5). Vedi `atk_eff` (check 2)."""
    return stat_eff(entita, StatId.FORZA)


def iniziativa(entita: int) -> int:
    """Iniziativa derivata da Destrezza (§5/§6) — è una **lettura**, non muta la stat.
    La Destrezza **non** entra nel danno (check 2): alimenta iniziativa ed evasione."""
    return stat_eff(entita, StatId.DESTREZZA)


# --- Le quattro derivate del risolutore a due check (§5/§6, GR2-10) ------------

def atk_eff(att: int) -> int:
    """Offesa del check 2, in **unità** (§5.1): `stat_eff(FORZA)` (+ skill offensive — nessuna
    nell'MVP; l'ex-`mira` confluisce qui, non nel colpire). Niente Destrezza nel danno."""
    return stat_eff(att, StatId.FORZA)


def cost_eff_come_centesimi(ber: int) -> int:
    """Termine muscolare di `def_eff`, in **centesimi** interi (§5.2). `0.01·Cost` (unità)
    vale numericamente `Cost_eff` centesimi — UNA conversione d'unità, esplicita, qui.

    È **fuori** dal fold di `DIFESA` (asimmetria voluta, §5.2): un PCT su `DIFESA` (enchant
    d'armatura) scala solo la somma-armatura, non i muscoli; il termine muscolare si muove
    solo via `Cost_eff`."""
    return stat_eff(ber, StatId.COSTITUZIONE)  # 0.01·Cost (unità) == Cost_eff centesimi


def def_eff(ber: int) -> int:
    """Mitigazione piatta del check 2, in **centesimi** (§5.2). Due addendi separati, ENTRAMBI
    centesimi: il termine muscolare (`cost_eff_come_centesimi`) e l'armatura (`stat_eff(DIFESA)`,
    già in centesimi via `finalizza="centesimi_floor0"`). Il danno converte `/100` (§6)."""
    return cost_eff_come_centesimi(ber) + stat_eff(ber, StatId.DIFESA)  # entrambi CENTESIMI


def _coeff_eva(ber: int, *, pct_evasione: float = 0.0) -> float:
    """Pendenza dell'evasione (§5.3): `m_armatura × m_taglia × (1 + Σ pct_evasione)`.

    `m_armatura`/`m_taglia` sono **selettori di categoria** (un valore ciascuno → prodotto
    *bounded*, non stacking moltiplicativo); le `%` di skill/enchant restano additive dentro
    `(1+Σ)`. SEAM gear: oggi le categorie sono i default MVP (nudo/taglia media); diventeranno
    dato per-entità (slot armatura/taglia)."""
    m_armatura = cal.M_ARMATURA[cal.ARMATURA_DEFAULT]
    m_taglia = cal.M_TAGLIA[cal.TAGLIA_DEFAULT]
    return m_armatura * m_taglia * (1 + pct_evasione)


def eva_eff(ber: int, *, pct_evasione: float = 0.0) -> float:
    """Evasione del check 1 (§5.3): `Des_eff × coeff_eva`. La Destrezza è la *magnitudine*,
    `coeff_eva` la *pendenza* (quanta agilità diventa schivata, dato cosa indossi e quanto sei
    grande). `coeff_eva ≈ 0` → non evadi anche a Des alta (no super-stat). Gli enchant
    `+evasione` entrano in `pct_evasione` (solo schivata), `+Destrezza` in `Des_eff` (schivata
    *e* iniziativa) — due leve distinte."""
    return stat_eff(ber, StatId.DESTREZZA) * _coeff_eva(ber, pct_evasione=pct_evasione)


def acc_eff(att: int, *, w: float = cal.W_FISICO, pct_precisione: float = 0.0) -> float:
    """Accuratezza del check 1 (§5.4), gemello offensivo dell'evasione: `stat_base_acc ×
    coeff_acc × (1 + Σ pct_precisione)`, con `stat_base_acc = w·Des_eff + (1−w)·Int_eff` — UNA
    formula per fisico e magia (Des e Int competono per il peso `w`, dato dell'attacco; mai
    0/1). `coeff_acc` = arma rispetto alla taglia del portatore (default `naturale`). Precisa
    ≠ forte: `coeff_acc` muove il colpire, non il danno."""
    stat_base_acc = w * stat_eff(att, StatId.DESTREZZA) + (1 - w) * stat_eff(att, StatId.INTELLIGENZA)
    coeff_acc = cal.COEFF_ACC[cal.ARMA_DEFAULT]
    return stat_base_acc * coeff_acc * (1 + pct_precisione)


def clampa_hp(entita: int) -> None:
    """Tiene `HP_corrente` ≤ massimo derivato (GR2-10). Da richiamare dopo un danno, dopo
    un modificatore che abbassa la Costituzione, e al load (cablaggio 2b)."""
    scheda = esper.try_component(entita, Scheda)
    if scheda is None:
        return
    tetto = max_hp(entita)
    if scheda.punti_vita > tetto:
        scheda.punti_vita = tetto
