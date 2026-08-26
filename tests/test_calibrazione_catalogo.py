"""Il catalogo di calibrazione (§11) e il layer di override: ogni placeholder ha una
spiegazione, i default sono invariati dopo il consolidamento, l'override applica/azzera.
Headless.
"""

from __future__ import annotations

import json

import pytest

from contracts import ClasseProva, Durata, StatId
from motore import calibrazione as cal


# --- Il catalogo è completo e auto-descrittivo --------------------------------

def test_ogni_param_ha_spiegazione_e_metadati() -> None:
    assert cal.elenco(), "il catalogo non può essere vuoto"
    for p in cal.elenco():
        assert p.spiegazione.strip(), p.chiave        # «cosa dovrebbe essere» — obbligatoria
        assert p.categoria.strip(), p.chiave
        assert p.dominio.strip(), p.chiave
        assert p.tipo in {"int", "float", "scelta", "testo"}, (p.chiave, p.tipo)
        if p.tipo == "scelta":
            assert p.scelte and p.default in p.scelte, p.chiave


def test_chiavi_uniche_e_indicizzate() -> None:
    chiavi = [p.chiave for p in cal.elenco()]
    assert len(chiavi) == len(set(chiavi)), "chiavi duplicate nel catalogo"
    assert set(cal.CATALOGO) == set(chiavi)


# --- I default sono invariati dopo il consolidamento (nessun cambio di gameplay) -

def test_default_consolidati_invariati() -> None:
    # Combat knobs.
    assert cal.S_CONTEST == 2 and cal.MIN_COLPO == 0.01 and cal.F_AUTOHIT == 3.0
    assert cal.G_GRAZE == 0.5 and cal.DELTA_BANDA == 0.2
    # `K_EVA` è load-bearing: sotto, la schivata non esiste in partita; sopra ~43, ogni
    # scontro diventa stocastico e il TTK tarato salta. La sua vera definizione sta nei
    # due vincoli per-entità di `test_calibrazione_check1.py`.
    assert cal.K_EVA == 6.0
    # Migrati da catalogo/scheda/combattimento.
    assert cal.PROB_ANOMALIA == 0.05 and cal.PROB_IMBOSCATA == 0.3
    assert cal.DURATA_BLOCCO_DEFAULT == 3 and cal.HP_DEFAULT == 30 and cal.DANNO_BASE == 1
    # Scala ri-derivata per la prova A MARGINE (nessun tiro): il confronto è con lo
    # `stat_eff` grezzo, non più con `stat + d20`, quindi le soglie del d20 non valgono più.
    assert cal.SOGLIE_PROVA[ClasseProva.BRONZO] == 6 and cal.SOGLIE_PROVA[ClasseProva.CELESTIALE] == 32
    assert cal.MARGINE_GRADO == 6 and cal.MARGINE_FUGA_PULITA == 6
    assert cal.CARICO_TICK[Durata.TURNO] == 1 and cal.CARICO_TICK[Durata.UN_BEL_PO] == 8
    assert cal.PRIMARIE_BASE_CARL[StatId.COSTITUZIONE] == 30
    assert cal.REGISTRY_ARCHETIPI["goblin"].destrezza_base == 7


# --- Override: applica, valida, salva (solo i diversi), azzera -----------------

def test_imposta_e_valore(cal_pulita) -> None:
    assert cal.valore("S_CONTEST") == 2
    assert cal.imposta("S_CONTEST", "3") == 3            # coerce stringa→int
    assert cal.valore("S_CONTEST") == 3
    cal.azzera("S_CONTEST")
    assert cal.valore("S_CONTEST") == 2                  # torna al default


def test_imposta_valida_il_tipo(cal_pulita) -> None:
    with pytest.raises(ValueError):
        cal.imposta("MIN_COLPO", "non-un-numero")
    with pytest.raises(ValueError):
        cal.imposta("ARMA_DEFAULT", "spadone")           # fuori dalle scelte ammesse
    assert cal.imposta("ARMA_DEFAULT", "pari") == "pari"  # una scelta valida
    with pytest.raises(KeyError):
        cal.imposta("CHIAVE_INESISTENTE", 1)


def test_salva_override_solo_i_divergenti(cal_pulita, tmp_path) -> None:
    cal.imposta("S_CONTEST", 5)
    cal.imposta("G_GRAZE", 0.5)                          # = default → NON va salvato
    percorso = tmp_path / "ov.json"
    cal.salva_override(percorso)
    dati = json.loads(percorso.read_text(encoding="utf-8"))
    assert dati == {"S_CONTEST": 5}                      # solo ciò che diverge dal default


def test_tabella_ricostruita_dal_catalogo() -> None:
    # Le tabelle pubbliche derivano dalle foglie del catalogo (chiave 'TABELLA.sotto').
    assert cal.M_ARMATURA["veste"] == cal.valore("M_ARMATURA.veste") == 0.10
    assert cal.M_TAGLIA["infima"] == 1.0
    assert cal.COEFF_ACC["naturale"] == 1.3
