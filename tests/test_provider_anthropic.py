"""Backend Anthropic reale: confinamento del meccanismo (F-12), key da env (PLK §4),
e un'integrazione LIVE opzionale (saltata senza SDK + chiave).

Le prove statiche girano sempre (parte della disciplina headless). La prova live è il
"boot → genera col backend reale" — eseguibile a mano con `ANTHROPIC_API_KEY` impostata.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from contracts import Provider
from provider import AnthropicBackend, NOME_VAR_CHIAVE

_SRC = Path(__file__).resolve().parents[1] / "src"


# --- F-12: il meccanismo di output strutturato è confinato nel backend --------

def test_F12_output_strutturato_solo_nel_provider() -> None:
    # I marcatori del meccanismo nativo (parse/output_format/json_schema) NON compaiono
    # in contracts né nel motore: vivono solo nel layer provider (PLK §5, F-12).
    marcatori = ("output_format", "messages.parse", "json_schema", "parsed_output")
    for layer in ("contracts", "motore"):
        for py in sorted((_SRC / layer).rglob("*.py")):
            src = py.read_text(encoding="utf-8")
            for m in marcatori:
                assert m not in src, f"{py.relative_to(_SRC)}: meccanismo structured-output fuori dal provider ({m})"
    # E nel provider c'è davvero.
    backend = (_SRC / "provider" / "anthropic_backend.py").read_text(encoding="utf-8")
    assert "output_format" in backend and "messages.parse" in backend


def test_backend_implementa_la_firma_unica() -> None:
    # Stessa interfaccia del FakeProvider: un solo verbo `genera` (G-19). Istanziabile
    # senza SDK (import pigro) → il Protocol è soddisfatto strutturalmente.
    backend = AnthropicBackend()
    assert isinstance(backend, Provider)
    assert hasattr(backend, "genera")


# --- PLK §4: la chiave da env, MAI cablata ------------------------------------

def test_chiave_da_env_mai_cablata() -> None:
    src = (_SRC / "provider" / "anthropic_backend.py").read_text(encoding="utf-8")
    assert "sk-ant" not in src
    # La key non è passata come stringa: la legge l'SDK dalla var d'ambiente.
    assert NOME_VAR_CHIAVE == "ANTHROPIC_API_KEY"
    tree = ast.parse(src)
    for nodo in ast.walk(tree):
        # Nessuna `api_key="..."` come keyword con valore letterale.
        if isinstance(nodo, ast.keyword) and nodo.arg == "api_key":
            assert not isinstance(nodo.value, ast.Constant), "api_key passata come letterale!"


def test_il_provider_non_costruisce_il_prompt_ne_valida() -> None:
    # Trasporto, non dominio (PLK §3): il backend non importa il gate/catalogo del motore.
    tree = ast.parse((_SRC / "provider" / "anthropic_backend.py").read_text(encoding="utf-8"))
    for nodo in ast.walk(tree):
        if isinstance(nodo, ast.ImportFrom) and not nodo.level and nodo.module:
            assert nodo.module.split(".")[0] != "motore", "il provider non importa il motore (dominio)"


# --- Integrazione LIVE col backend reale (opzionale) --------------------------

_HA_CHIAVE = bool(os.environ.get("ANTHROPIC_API_KEY"))
pytestmark_live = pytest.mark.skipif(
    not _HA_CHIAVE, reason="ANTHROPIC_API_KEY non impostata: integrazione live saltata"
)


@pytestmark_live
def test_live_genera_flavor_conforme() -> None:
    pytest.importorskip("anthropic")
    import asyncio

    from contracts import Flavor

    backend = AnthropicBackend(max_tokens=256)
    prompt = "Scrivi una sola frase sarcastica da showrunner di un dungeon."
    candidato = asyncio.run(backend.genera(prompt, Flavor))
    assert candidato is None or (isinstance(candidato, Flavor) and candidato.testo)


@pytestmark_live
def test_live_turno_di_narrazione_passa_il_gate(mondo_isolato: str) -> None:
    pytest.importorskip("anthropic")
    import asyncio

    from contracts import SchedaProiezione
    from motore import procura_turno
    from tests.narr_helpers import budget

    backend = AnthropicBackend(max_tokens=1024)
    risultato = asyncio.run(
        procura_turno(backend, budget(), SchedaProiezione(descrittori=("integro",)),
                      voce="Sei il dungeon: genera una stanza con un mostro dal catalogo.")
    )
    # Qualunque sia l'esito (reale o fallback), il motore produce un turno GIOCABILE.
    assert risultato.turno.prosa and risultato.turno.opzioni
