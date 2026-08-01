"""Estensione per-entità del catalogo §11: profili completi per archetipo (stat base +
geometria + resistenze) editabili come DATO, formula-madre a 7 primarie, getter e profilo
fresco per l'anteprima. Headless.
"""

from __future__ import annotations

import pytest

from contracts import Archetipo, Grado, StatId, TipoDanno
from motore import calibrazione as cal


_NOMI = ("slime", "scheletro", "goblin")
_SUFFISSI = (
    "destrezza_base", "pv_base", "danno_base", "intelligenza_base", "difesa_base",
    "saggezza_base", "fortuna_base", "armatura", "taglia", "arma",
    "res.mischia", "res.fuoco", "res.veleno",
)


def test_ogni_archetipo_ha_il_profilo_completo() -> None:
    for nome in _NOMI:
        for suf in _SUFFISSI:
            assert f"ARCH.{nome}.{suf}" in cal.CATALOGO, (nome, suf)


def test_default_storici_invariati() -> None:
    # Le tre leve storiche non cambiano valore di default (nessun cambio di gameplay).
    p = cal.REGISTRY_ARCHETIPI[Archetipo.GOBLIN]
    assert (p.destrezza_base, p.pv_base, p.danno_base) == (7, 5, 2)
    assert p.armatura == "veste" and p.taglia == "media" and p.arma == "naturale"


def test_getter_ritornano_i_default() -> None:
    assert cal.geometria_da_archetipo(Archetipo.SLIME) == ("veste", "media", "naturale")
    assert cal.resistenze_da_archetipo(Archetipo.SLIME) == {}  # tutte 0 = identità DT-6


def test_formula_popola_le_sette_primarie() -> None:
    pr = cal.primarie_da_archetipo(Archetipo.SLIME, Grado.BRONZO, 1)
    assert set(pr) == set(StatId)  # tutte e 7, non più solo 4
    from motore.catalogo import rango_grado
    rango = rango_grado(Grado.BRONZO)
    prof = cal.REGISTRY_ARCHETIPI[Archetipo.SLIME]
    assert pr[StatId.INTELLIGENZA] == prof.intelligenza_base + rango  # non più proxy //2
    assert pr[StatId.DIFESA] == prof.difesa_base                      # flat, default 0
    assert pr[StatId.FORZA] == prof.danno_base * rango                # moltiplicativa, invariata
    assert pr[StatId.COSTITUZIONE] == prof.pv_base * rango


def test_imposta_e_valida_le_nuove_foglie(cal_pulita) -> None:
    with pytest.raises(ValueError):
        cal.imposta("ARCH.slime.taglia", "spadone")        # fuori dalle scelte
    with pytest.raises(ValueError):
        cal.imposta("ARCH.slime.res.fuoco", "non-numero")  # float non valido
    assert cal.imposta("ARCH.slime.res.fuoco", -50) == -50.0


def test_profilo_corrente_e_fresco(cal_pulita) -> None:
    # REGISTRY_ARCHETIPI è cache-ato all'import; profilo_corrente rilegge gli override ora.
    assert cal.profilo_corrente(Archetipo.SLIME).taglia == "media"
    cal.imposta("ARCH.slime.taglia", "infima")
    assert cal.profilo_corrente(Archetipo.SLIME).taglia == "infima"
    assert cal.REGISTRY_ARCHETIPI[Archetipo.SLIME].taglia == "media"  # cache invariata


def test_resistenze_da_archetipo_filtra_le_nulle(monkeypatch) -> None:
    prof = cal.REGISTRY_ARCHETIPI[Archetipo.SLIME]
    modif = cal.ProfiloArchetipo(**{**vars(prof), "resistenze": {TipoDanno.FUOCO: -50.0, TipoDanno.MISCHIA: 0.0}})
    monkeypatch.setitem(cal.REGISTRY_ARCHETIPI, Archetipo.SLIME, modif)
    assert cal.resistenze_da_archetipo(Archetipo.SLIME) == {TipoDanno.FUOCO: -50.0}
