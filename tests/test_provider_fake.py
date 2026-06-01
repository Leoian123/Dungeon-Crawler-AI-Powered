"""Provider fake deterministico: stessa firma del backend reale, offline (nodo F).

Verifica che `genera(prompt, schema)` restituisca candidati scriptati e `None` su
richiesta, validi contro lo schema, registri i prompt opachi, e non importi rete/chiave.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from contracts import Flavor, Provider, TurnoNarrazione
from provider import FakeProvider
from tests.narr_helpers import turno

_PROVIDER = Path(__file__).resolve().parents[1] / "src" / "provider"


def test_fake_implementa_il_protocollo_provider() -> None:
    # Stessa interfaccia che userà il backend reale (Provider Protocol di contracts).
    assert isinstance(FakeProvider(), Provider)


def test_genera_ritorna_candidato_scriptato() -> None:
    cand = turno()
    prov = FakeProvider([cand])
    risultato = asyncio.run(prov.genera("prompt opaco", TurnoNarrazione))
    assert risultato == cand
    assert prov.prompt_ricevuti == ["prompt opaco"]
    assert prov.schemi_ricevuti == [TurnoNarrazione]


def test_genera_valida_dict_contro_schema() -> None:
    prov = FakeProvider([turno().model_dump()])
    risultato = asyncio.run(prov.genera("p", TurnoNarrazione))
    assert isinstance(risultato, TurnoNarrazione)


def test_none_scriptato_e_coda_vuota_danno_none() -> None:
    prov = FakeProvider([None])
    assert asyncio.run(prov.genera("p", TurnoNarrazione)) is None  # None scriptato
    assert asyncio.run(prov.genera("p", TurnoNarrazione)) is None  # coda vuota


def test_schema_diverso_stesso_verbo() -> None:
    # Un solo verbo `genera`; cambia lo schema, non il metodo (F §5).
    prov = FakeProvider([Flavor(testo="ciao")])
    risultato = asyncio.run(prov.genera("p", Flavor))
    assert isinstance(risultato, Flavor)


def test_prompt_non_stringa_rifiutato() -> None:
    # Nessun componente ECS vivo attraversa il socket (G-13): il prompt è una stringa.
    prov = FakeProvider([turno()])
    with pytest.raises(TypeError):
        asyncio.run(prov.genera({"scheda": "viva"}, TurnoNarrazione))


def test_nessuna_rete_nessuna_chiave_nel_modulo() -> None:
    # Statico: il provider fake non importa client di rete né nomina chiavi/anthropic.
    src = (_PROVIDER / "fake.py").read_text(encoding="utf-8")
    for vietato in ("anthropic", "requests", "httpx", "urllib", "api_key", "ANTHROPIC_API_KEY"):
        assert vietato not in src, f"il provider fake non deve toccare la rete/chiave: {vietato}"
