"""Configurazione pytest: isolamento del contesto globale di esper (ESP §0.1).

L'API a livello di modulo di esper opera su un contesto World di default implicito,
attivo all'import. Senza isolamento, ogni test eredita lo stato del precedente:
test che passano da soli e falliscono in sequenza (la flakiness peggiore).

Disciplina (ESP §0.1):
  setup    -> esper.switch_world("<nome-di-test>")   (crea il mondo al primo switch)
  teardown -> esper.switch_world("default")           (mai eliminare il contesto attivo)
              esper.delete_world("<nome-di-test>")     (lo switch successivo lo ricrea vuoto)

`mondo_isolato`  -> un mondo unico per test (uso generale).
`mondo_condiviso`-> un mondo a nome FISSO, condiviso fra i test della demo: serve a
                    *dimostrare* che, pur riusando lo stesso nome, lo stato non
                    trapela perché il teardown elimina il mondo.
"""

from __future__ import annotations

import os

# I test asseriscono la calibrazione di **default** (§11): un eventuale file di override
# locale (creato dalla console admin) NON deve cambiarne l'esito. Puntando il percorso a
# `os.devnull` (illeggibile come JSON → nessun override) il motore carica sempre i default.
# Va impostato PRIMA che `motore.calibrazione` venga importato dal primo test.
os.environ["DCC_CALIBRAZIONE_OVERRIDE"] = os.devnull

from contextlib import contextmanager
from typing import Iterator

import pytest

import esper

_DEFAULT_WORLD = "default"


def _sanitize(node_id: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in node_id)


@contextmanager
def _isola(world_name: str) -> Iterator[str]:
    """Esegue un blocco in un contesto esper isolato e lo elimina all'uscita."""
    esper.switch_world(world_name)
    try:
        yield world_name
    finally:
        # Non si può eliminare il contesto attivo: si switcha via *prima*.
        esper.switch_world(_DEFAULT_WORLD)
        esper.delete_world(world_name)


@pytest.fixture
def mondo_isolato(request: pytest.FixtureRequest) -> Iterator[str]:
    """Contesto esper dedicato e azzerato, unico per ogni test."""
    with _isola(f"test-{_sanitize(request.node.nodeid)}") as name:
        yield name


@pytest.fixture
def mondo_condiviso() -> Iterator[str]:
    """Contesto esper a nome FISSO, riusato dalla demo di non-trapelamento."""
    with _isola("mondo-condiviso-di-prova") as name:
        yield name


@pytest.fixture
def cal_pulita() -> Iterator[None]:
    """Snapshot/restore degli override di calibrazione in memoria: i test che
    impostano override (`cal.imposta`) non si sporcano a vicenda."""
    from motore import calibrazione as cal

    prima = dict(cal._OVERRIDE)
    try:
        yield
    finally:
        cal._OVERRIDE.clear()
        cal._OVERRIDE.update(prima)


@pytest.fixture
def run_pulita() -> Iterator[None]:
    """Isolamento per i test che passano dal `Guscio`/`SessioneGioco` (che switcha al
    run-World): run-World fresco prima e dopo, parcheggio nel default."""
    from guscio import NOME_DEFAULT, NOME_RUN

    def _pulisci() -> None:
        esper.switch_world(NOME_DEFAULT)
        if NOME_RUN in esper.list_worlds():
            esper.delete_world(NOME_RUN)

    _pulisci()
    yield
    _pulisci()
