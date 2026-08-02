"""Socket generativo: un verbo per schema, niente save da chiamata in volo, chiamate
non-gating che non bloccano (G-19, G-20, G-22). Headless, provider fake.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import esper

from contracts import Flavor, Provider, TurnoNarrazione
from motore import (
    EntitaMob,
    RETRY_NARRAZIONE,
    genera_prosa,
    procura_turno,
)
from provider import FakeProvider
from tests.narr_helpers import budget, turno

_SRC = Path(__file__).resolve().parents[1] / "src"
_PROIEZIONE_VUOTA = __import__("contracts").SchedaProiezione(descrittori=("integro",))


# --- G-19: una sola firma verso il provider; prompt e gate nel motore ---------

def test_G19_provider_ha_un_solo_verbo() -> None:
    # Il Protocol `Provider` espone un solo metodo applicativo: `genera`.
    src = (_SRC / "contracts" / "provider.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    metodi = [
        n.name
        for cls in ast.walk(tree)
        if isinstance(cls, ast.ClassDef) and cls.name == "Provider"
        for n in cls.body
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
        and not n.name.startswith("_")
    ]
    assert metodi == ["genera"], metodi


def test_G19_un_verbo_due_schemi() -> None:
    # Lo stesso verbo serve narrazione e flavor: cambia lo schema, non il metodo.
    prov = FakeProvider([turno(), Flavor(testo="flavor")])
    a = asyncio.run(prov.genera("p", TurnoNarrazione))
    b = asyncio.run(prov.genera("p", Flavor))
    assert isinstance(a, TurnoNarrazione)
    assert isinstance(b, Flavor)
    assert isinstance(prov, Provider)


def test_G19_nessun_secondo_metodo_sul_provider() -> None:
    # Il FakeProvider non espone un secondo verbo generativo per tipo di chiamata.
    metodi_async = [
        m for m in dir(FakeProvider)
        if not m.startswith("_") and asyncio.iscoroutinefunction(getattr(FakeProvider, m))
    ]
    assert metodi_async == ["genera"], metodi_async


def test_G19_prompt_e_gate_vivono_nel_motore() -> None:
    narr = (_SRC / "motore" / "narrazione.py").read_text(encoding="utf-8")
    assert "def costruisci_prompt" in narr  # prompt costruito nel motore
    assert "def valida_turno" in narr       # gate nel motore
    # L'orchestrazione è host-agnostica: nessun import di textual.
    tree = ast.parse(narr)
    for nodo in ast.walk(tree):
        if isinstance(nodo, ast.ImportFrom) and nodo.module:
            assert nodo.module.split(".")[0] != "textual"
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                assert alias.name.split(".")[0] != "textual"


# --- G-20: una genera in volo (fallita/cancellata/in retry) non scrive sul save -

def test_G20_chiamata_in_retry_non_scrive(mondo_isolato: str) -> None:
    # Durante i retry (prima risposta None), nessuna entità è materializzata.
    prima = list(esper.get_entities())
    prov = FakeProvider([None, turno()])
    res = asyncio.run(procura_turno(prov, budget(), _PROIEZIONE_VUOTA))
    assert len(prov.chiamate) == RETRY_NARRAZIONE + 1  # ha ritentato
    assert res.fallback is False
    # La coroutine non ha scritto: lo stato è quello di prima (nessun EntitaMob).
    assert esper.get_component(EntitaMob) == []
    assert list(esper.get_entities()) == prima


def test_G20_chiamata_cancellata_non_scrive(mondo_isolato: str) -> None:
    class ProviderAppeso:
        async def genera(self, prompt, schema, *, sistema=""):
            await asyncio.Event().wait()  # non si risolve mai

    async def scenario() -> None:
        task = asyncio.create_task(
            procura_turno(ProviderAppeso(), budget(), _PROIEZIONE_VUOTA)
        )
        await asyncio.sleep(0)  # lascia partire la coroutine
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    prima = list(esper.get_entities())
    asyncio.run(scenario())
    # Cancellata in volo: lo stato resta al turno precedente (niente scritto).
    assert esper.get_component(EntitaMob) == []
    assert list(esper.get_entities()) == prima


# --- G-22: chiamate non-gating non bloccano; una sola gating per turno ---------

def test_G22_una_sola_chiamata_gating_per_turno(mondo_isolato: str) -> None:
    # La chiamata di narrazione (gating) usa SOLO lo schema TurnoNarrazione.
    prov = FakeProvider([turno()])
    asyncio.run(procura_turno(prov, budget(), _PROIEZIONE_VUOTA))
    assert set(prov.schemi_ricevuti) == {TurnoNarrazione}


def test_G22_flavor_non_gating_puo_mancare_senza_bloccare(mondo_isolato: str) -> None:
    # Il flavor (non-gating) fallisce, ma NON blocca la risoluzione del turno gating.
    prov_flavor = FakeProvider([None])  # flavor assente
    testo = asyncio.run(genera_prosa(prov_flavor, "prompt flavor"))
    assert testo is None  # mancato, ma nessuna eccezione, nessun blocco

    prov_turno = FakeProvider([turno()])
    res = asyncio.run(procura_turno(prov_turno, budget(), _PROIEZIONE_VUOTA))
    assert res.fallback is False  # la risoluzione gating procede comunque
