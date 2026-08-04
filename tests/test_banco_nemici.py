"""Banco di prova della generazione nemici (`src/banco_nemici.py`): la pipeline reale
(gate + formula-madre + materializzazione) e la superficie sperimentale (drop/azioni).
Tutto offline (Fake); nessuna chiamata live.
"""

from __future__ import annotations

import asyncio

import esper
import pytest

import banco_nemici as bn
from contracts import Blocco, Grado
from provider import FakeProvider


def _budget_normale():
    import random
    return bn.prepara_contesto(livello=1, rng=random.Random(0))


# --- Schema sperimentale ------------------------------------------------------

def test_schema_core_piu_drop_azioni() -> None:
    n = bn.nemico_scriptato()
    assert isinstance(n.archetipo, str) and isinstance(n.grado, Grado)
    assert isinstance(n.drop, list) and isinstance(n.azioni, list)
    assert n.azioni and all(isinstance(a, str) for a in n.azioni)   # mosse = stringhe
    # extra="forbid": niente campi non previsti.
    with pytest.raises(Exception):
        bn.NemicoSperimentale(  # type: ignore[call-arg]
            archetipo="slime", grado=Grado.BRONZO, blocchi=[], nome="x",
            descrizione="y", drop=[], azioni=[], extra_non_previsto=1,
        )


# --- Happy-path: gate reale + stat reali dal motore ---------------------------

def test_pipeline_gate_passa_e_stat_reali(mondo_isolato: str) -> None:
    budget = _budget_normale()
    prov = {"(fake)": FakeProvider([bn.nemico_scriptato().model_dump()])}
    esiti = asyncio.run(bn.confronta(prov, "prompt", budget, livello=3))

    assert len(esiti) == 1
    e = esiti[0]
    assert e.trasporto_ok and e.gate_ok and e.motivo_gate is None
    # Stat VALIDATE dal motore (formula-madre): slime pv_base 15 (tarato TTK) ×
    # rango(bronzo=1) × liv 3 = 45.
    assert e.stat is not None
    assert e.stat["primarie"]["costituzione"] == 45
    assert isinstance(e.stat["max_hp"], int) and e.stat["max_hp"] == 45   # int, non float
    assert e.stat["atk_eff"] >= 1
    # Drop/azioni riportati (sperimentali).
    assert e.candidato.drop and e.candidato.azioni


def test_materializzazione_pulisce_dopo_se(mondo_isolato: str) -> None:
    # Il banco materializza, legge le stat, e RIMUOVE l'entità: nessun residuo, niente
    # switch_world (disciplina E-2). Vuoto prima e dopo.
    from motore import EntitaMob

    budget = _budget_normale()
    assert esper.get_component(EntitaMob) == []
    bn.gate_e_stat(bn.nemico_scriptato(), budget, livello=2)
    assert esper.get_component(EntitaMob) == []


# --- Gate-reject: un nemico fuori budget è rifiutato (col motivo) --------------

def test_gate_reject_fuori_budget(mondo_isolato: str) -> None:
    budget = _budget_normale()                               # gradi ammessi: BRONZO, ARGENTO
    fuori = bn.NemicoSperimentale(
        archetipo="slime", grado=Grado.CELESTIALE, blocchi=[],
        nome="Slime Apocalittico", descrizione="Troppo.", drop=[], azioni=["Cancella la realtà"],
    )
    gate_ok, motivo, stat = bn.gate_e_stat(fuori, budget, livello=1)
    assert gate_ok is False and stat is None
    assert "celestiale" in motivo and "budget" in motivo     # motivo leggibile per il confronto


def test_gate_reject_blocco_fuori_budget(mondo_isolato: str) -> None:
    budget = _budget_normale()                               # blocchi ammessi: VELENO, RIGENERAZIONE
    fuori = bn.NemicoSperimentale(
        archetipo="slime", grado=Grado.BRONZO, blocchi=[Blocco.STORDITO],
        nome="Slime Stordente", descrizione="x", drop=[], azioni=[],
    )
    gate_ok, motivo, _ = bn.gate_e_stat(fuori, budget, livello=1)
    assert gate_ok is False and "blocch" in motivo.lower()


def test_trasporto_none_riportato(mondo_isolato: str) -> None:
    budget = _budget_normale()
    esiti = asyncio.run(bn.confronta({"(fake)": FakeProvider([None])}, "p", budget, livello=1))
    assert esiti[0].trasporto_ok is False and esiti[0].candidato is None


# --- CLI smoke ----------------------------------------------------------------

def test_cli_fake_smoke(capsys) -> None:
    assert bn.main(["--fake", "--livello", "2", "--seed", "1"]) == 0
    out = capsys.readouterr().out
    assert "BANCO NEMICI" in out
    assert "Slime Mangiascarti" in out
    # Fase 6: le azioni proposte incrociano il catalogo mosse reale (match-rate).
    assert "azioni (vs catalogo mosse" in out
    assert "SOMMARIO" in out


# --- Disciplina: il banco non importa una UI né tests/ ------------------------

def test_banco_non_importa_ui_ne_tests() -> None:
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "banco_nemici.py"
    radici: set[str] = set()
    for nodo in ast.walk(ast.parse(src.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Import):
            radici |= {a.name.split(".")[0] for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            radici.add(nodo.module.split(".")[0])
    assert "textual" not in radici and "tests" not in radici
