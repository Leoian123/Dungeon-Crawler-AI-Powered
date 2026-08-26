"""Backend della console web di calibrazione (host-tool), testato SENZA HTTP: la vista, gli
override (applica/azzera/salva) e l'anteprima che riusa le derivate reali in un World
temporaneo. Nessuna dipendenza di UI nel motore.
"""

from __future__ import annotations

import pytest

import calibratore_web as web
from motore import calibrazione as cal


@pytest.fixture(autouse=True)
def _override_puliti(cal_pulita):
    """Ogni test di questo file tocca gli override: riusa `cal_pulita` (conftest) autouse."""
    yield


def test_vista_ha_sezioni_nemico_e_globale() -> None:
    v = web.costruisci_vista()
    assert v["voci"] and len(v["voci"]) == len(cal.elenco())
    assert {a["archetipo"] for a in v["archetipi"]} == {"slime", "scheletro", "goblin"}
    sez = {x["sezione"] for x in v["voci"]}
    assert sez == {"nemico", "globale"}
    # una foglia per-entità è classificata bene
    fuoco = next(x for x in v["voci"] if x["chiave"] == "ARCH.slime.res.fuoco")
    assert fuoco["gruppo"] == "slime" and fuoco["sotto"] == "Resistenze"


def test_applica_ok_e_marca_override() -> None:
    r = web.applica("ARCH.slime.taglia", "infima")
    assert r == {"ok": True, "valore": "infima", "override": True}
    assert cal.valore("ARCH.slime.taglia") == "infima"


def test_applica_errore_non_muta() -> None:
    r = web.applica("ARCH.slime.taglia", "spadone")
    assert r["ok"] is False and "spadone" in r["errore"]
    assert cal.valore("ARCH.slime.taglia") == "media"  # invariato


def test_azzera_torna_al_default() -> None:
    web.applica("S_CONTEST", 5)
    r = web.azzera("S_CONTEST")
    assert r == {"ok": True, "valore": 2, "override": False}


def test_salva_conta_solo_i_divergenti() -> None:
    web.applica("S_CONTEST", 5)
    web.applica("G_GRAZE", 0.5)  # = default → non conta
    r = web.salva()
    assert r["ok"] is True and r["n"] == 1


def test_anteprima_riflette_override_fresco(mondo_isolato) -> None:
    base = web.anteprima("slime", "bronzo", 1)
    web.applica("ARCH.slime.taglia", "infima")
    web.applica("ARCH.slime.res.fuoco", -50)
    dopo = web.anteprima("slime", "bronzo", 1)
    assert dopo["eva_eff"] > base["eva_eff"]              # taglia più piccola → più evasione
    assert dopo["resistenze_mult"]["fuoco"] == 0.5        # -50% → mult 0.5
    assert set(dopo["primarie"]) == {
        "forza", "destrezza", "costituzione", "intelligenza", "difesa", "saggezza", "fortuna",
        "carisma",  # la stat sociale del parlamentare (2026-08-16)
    }


def test_anteprima_non_lascia_entita(mondo_isolato) -> None:
    import esper

    from motore.statistiche import Primarie
    web.anteprima("goblin", "argento", 2)
    assert list(esper.get_component(Primarie)) == []  # entità usa-e-getta eliminata
