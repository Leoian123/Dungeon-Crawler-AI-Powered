"""Preparazione del contesto: anomalia SEEDED, budget gonfiato, reveal sul bus
(FNC §5.1/§5.5; item 1 della fase). Headless, seeded.

Il motore tira l'anomalia (seeded), calcola budget + set ammissibile e lo inietta nel
prompt; al reveal pubblica `AnomalyTriggered` perché lo showrunner la narri. L'AI non
invoca mai l'anomalia: la narra.
"""

from __future__ import annotations

import asyncio
import random

import esper

from contracts import AnomalyTriggered, BusEventi, Rarita, SchedaProiezione
from motore import (
    EntitaMob,
    PROB_ANOMALIA,
    materializza_turno,
    prepara_contesto,
    procura_turno,
)
from provider import FakeProvider
from tests.harness import NullAdapter
from tests.narr_helpers import budget, turno

_PROIEZIONE = SchedaProiezione(descrittori=("integro",))


def test_anomalia_e_un_tiro_seeded_riproducibile() -> None:
    # Stesso seed → stessa decisione di anomalia (RNG del motore, non dell'LLM).
    for s in (1, 2, 3, 42, 99):
        a = prepara_contesto(1, random.Random(s))
        b = prepara_contesto(1, random.Random(s))
        assert a.anomala == b.anomala
        assert a.rarita_ammesse == b.rarita_ammesse


def test_anomalia_gonfia_il_budget() -> None:
    # Trova un seed che fa scattare l'anomalia e verifica che il budget si allarga.
    seed = next(
        s for s in range(1000) if prepara_contesto(1, random.Random(s)).anomala
    )
    bud = prepara_contesto(1, random.Random(seed))
    assert bud.anomala is True
    # Il budget anomalo ammette anche la rarità più alta (LEGGENDARIO), che il normale no.
    assert Rarita.LEGGENDARIO in bud.rarita_ammesse
    normale = prepara_contesto(1, random.Random(_seed_normale()))
    assert Rarita.LEGGENDARIO not in normale.rarita_ammesse


def _seed_normale() -> int:
    return next(s for s in range(1000) if not prepara_contesto(1, random.Random(s)).anomala)


def test_prob_anomalia_e_bassa() -> None:
    # "L'ingiustizia assurda" è rara (chi sfora è il motore, di tanto in tanto).
    assert 0.0 < PROB_ANOMALIA < 0.5


def test_reveal_anomalyTriggered_alla_materializzazione(mondo_isolato: str) -> None:
    bus = BusEventi()
    adapter = NullAdapter()
    bus.registra(AnomalyTriggered, adapter.on_event)

    # Budget anomalo costruito a mano: alla materializzazione esce il reveal.
    bud = budget(anomala=True, rarita=(Rarita.COMUNE, Rarita.RARO, Rarita.LEGGENDARIO))
    prov = FakeProvider([turno(rarita=Rarita.LEGGENDARIO)])
    res = asyncio.run(procura_turno(prov, bud, _PROIEZIONE))
    assert res.anomala is True

    ent = materializza_turno(res, bus)
    assert esper.has_component(ent, EntitaMob)
    eventi = adapter.events_of(AnomalyTriggered)
    assert len(eventi) == 1 and eventi[0].entita == ent


def test_nessun_reveal_se_budget_normale(mondo_isolato: str) -> None:
    bus = BusEventi()
    adapter = NullAdapter()
    bus.registra(AnomalyTriggered, adapter.on_event)

    prov = FakeProvider([turno()])
    res = asyncio.run(procura_turno(prov, budget(anomala=False), _PROIEZIONE))
    materializza_turno(res, bus)
    assert adapter.events_of(AnomalyTriggered) == []
