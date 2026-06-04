"""Property-test del check 1 (Gruppo 2 §11) — parte del compito dichiarato.

Due vincoli sui numeri `§11` (letti da `calibrazione`, MAI cablati qui):
  1. **Vincolo accoppiato** del contest: l'attaccante ordinario colpisce ≥ ~95%, mentre una
     **build d'evasione dedicata** porta il colpire ≤ ~15% (Donut). Esercitato su
     `esito_contest(acc, eva, rng)` — la *forma* del contest, separata dalla derivazione delle
     magnitudini (il wiring per-entità dell'evasione è un seam gear post-MVP).
  2. **Neutralità del graze** a `g = ½` straddle: la media del moltiplicatore `m` coincide col
     binario (E[m] = P) lontano dai clamp — varianza giù, media invariata.

I numeri sono quelli **approvati** nel piano (placeholder §11): se la calibrazione cambia,
questi assert sono la rete che la vincola. La banda statistica è stretta → seed fisso.
"""

from __future__ import annotations

import random

from motore import esito_contest
from motore import calibrazione as cal

_N = 20_000  # campione Monte-Carlo (seed fisso → niente flakiness)


def _connect_rate(acc: float, eva: float, *, seed: int = 12345) -> float:
    """Frazione di colpi che CONNETTONO (m ≠ 0) su `_N` estrazioni seeded."""
    rng = random.Random(seed)
    connessi = sum(1 for _ in range(_N) if esito_contest(acc, eva, rng) != 0.0)
    return connessi / _N


# --- Vincolo 1: attaccante ordinario ≥ ~95%, dodge-build ≤ ~15% -----------------

def test_vincolo_accoppiato_check1() -> None:
    # Ordinario: con la geometria di default (coeff_eva ~0.01, coeff_acc ~1.3) l'evasione
    # ordinaria è ≪ acc/F → auto-hit. Rappresentato da scalari Carl-like.
    acc_ord = (cal.W_FISICO * 10 + (1 - cal.W_FISICO) * 10) * cal.COEFF_ACC[cal.ARMA_DEFAULT]  # ≈13
    eva_ord = 10 * cal.M_ARMATURA[cal.ARMATURA_DEFAULT] * cal.M_TAGLIA[cal.TAGLIA_DEFAULT]      # ≈0.1
    assert _connect_rate(acc_ord, eva_ord) >= 0.95, "l'attaccante ordinario deve colpire ~sempre"

    # Build d'evasione dedicata (taglia minima + cloth + skill: seam gear): `eva` alza il
    # rapporto eva/acc finché il colpire crolla. Con s=2, eva/acc ≈ 5 → P ≈ 3.8% → connect ≈ 14%.
    acc_att = acc_ord
    eva_dodge = acc_att * 5
    assert _connect_rate(acc_att, eva_dodge) <= 0.15, "una build d'evasione dedicata deve portare il colpire ≤ ~15%"


def test_floor_gemello_nessuno_zero_garantito() -> None:
    # I due floor gemelli reggono al cap: contro un'evasione mostruosa il colpire NON è 0
    # (P ≥ MIN_COLPO), e contro un'accuratezza mostruosa la schivata NON è impossibile.
    assert _connect_rate(1, 10**6) > 0.0
    assert _connect_rate(10**6, 1) >= 0.95


# --- Vincolo 2: neutralità del graze a g = ½ (media invariata, varianza giù) -----

def test_graze_neutrale_a_g_mezzo() -> None:
    # acc == eva → P = 0.5; banda [0.4, 0.6] lontana dai clamp. A g=½ straddle: E[m] = P.
    acc = eva = 10.0
    P = acc ** cal.S_CONTEST / (acc ** cal.S_CONTEST + eva ** cal.S_CONTEST)
    lo, hi = P - cal.DELTA_BANDA / 2, P + cal.DELTA_BANDA / 2  # nessun clamp qui

    # Identità strutturale (vale per g=½): E[m] = lo·1 + (hi−lo)·g = (lo+hi)/2 = P.
    e_m_analitico = lo * 1.0 + (hi - lo) * cal.G_GRAZE + (1 - hi) * 0.0
    if cal.G_GRAZE == 0.5:
        assert abs(e_m_analitico - P) < 1e-9, "a g=½ straddle la media-danno è invariata (E[m]=P)"

    # …e il Monte-Carlo lo conferma entro tolleranza.
    rng = random.Random(999)
    media = sum(esito_contest(acc, eva, rng) for _ in range(_N)) / _N
    assert abs(media - e_m_analitico) < 0.02
