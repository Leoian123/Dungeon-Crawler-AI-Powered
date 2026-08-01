"""Seam gear per-entità: `derivate` legge il `Corredo` dell'entità con FALLBACK ai default
globali. Entità senza `Corredo` = valori bit-per-bit di oggi; con `Corredo` = i suoi slot.
Contesto esper isolato (ESP §0.1).
"""

from __future__ import annotations

import esper
import pytest

from contracts import StatId
from motore import calibrazione as cal
from motore.corredo import Corredo
from motore.derivate import acc_eff, eva_eff
from motore.statistiche import Primarie


def _primarie() -> Primarie:
    return Primarie(valori={StatId.DESTREZZA: 10, StatId.INTELLIGENZA: 4})


def test_senza_corredo_usa_i_default_globali(mondo_isolato) -> None:
    ent = esper.create_entity(_primarie())
    atteso_eva = 10 * (cal.M_ARMATURA[cal.ARMATURA_DEFAULT] * cal.M_TAGLIA[cal.TAGLIA_DEFAULT])
    assert eva_eff(ent) == pytest.approx(atteso_eva)
    assert acc_eff(ent) == pytest.approx(
        (cal.W_FISICO * 10 + (1 - cal.W_FISICO) * 4) * cal.COEFF_ACC[cal.ARMA_DEFAULT]
    )


def test_con_corredo_usa_i_suoi_slot(mondo_isolato) -> None:
    ent = esper.create_entity(_primarie(), Corredo(armatura="pesante", taglia="piccola", arma="piu_piccola"))
    assert eva_eff(ent) == pytest.approx(10 * (cal.M_ARMATURA["pesante"] * cal.M_TAGLIA["piccola"]))
    assert acc_eff(ent) == pytest.approx(
        (cal.W_FISICO * 10 + (1 - cal.W_FISICO) * 4) * cal.COEFF_ACC["piu_piccola"]
    )


def test_corredo_cambia_l_evasione(mondo_isolato) -> None:
    nudo = esper.create_entity(_primarie())
    agile = esper.create_entity(_primarie(), Corredo(armatura="veste", taglia="infima", arma="naturale"))
    assert eva_eff(agile) > eva_eff(nudo)  # taglia più piccola → schiva di più
