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
    # L'API di Pydantic per l'EMISSIONE della forma (`json_schema_extra`,
    # `__get_pydantic_json_schema__` — usata da contracts per spogliare le docstring
    # dallo schema, audit 2026-08-07) è mascherata prima del check: emettere lo schema
    # è compito dichiarato di contracts (F §1); il divieto copre il TRASPORTO.
    _api_pydantic = ("json_schema_extra", "__get_pydantic_json_schema__")
    marcatori = ("output_format", "messages.parse", "json_schema", "parsed_output")
    file_visti = 0
    for layer in ("contracts", "motore"):
        for py in sorted((_SRC / layer).rglob("*.py")):
            file_visti += 1
            src = py.read_text(encoding="utf-8")
            for api in _api_pydantic:
                src = src.replace(api, "")
            for m in marcatori:
                assert m not in src, f"{py.relative_to(_SRC)}: meccanismo structured-output fuori dal provider ({m})"
    assert file_visti, "contracts/motore vuoti o spostati: il divieto passerebbe per vacuità"
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


# --- Il metodo dell'SDK esiste DAVVERO (regression del live spento) -----------

def test_il_metodo_di_parse_si_risolve_sullo_sdk_installato() -> None:
    """Regression (giro 2026-08-07): il backend chiamava `client.messages.parse`,
    che sull'SDK pinnato NON esiste — AttributeError inghiottito, ogni turno live
    degradato a fallback, e la suite verde perché il lint F-12 controlla la STRINGA
    nel sorgente. Questo test risolve il METODO sull'SDK vero, senza rete."""
    anthropic = pytest.importorskip("anthropic")

    client = anthropic.AsyncAnthropic(api_key="x")  # placeholder: nessuna chiamata
    assert callable(client.beta.messages.parse), (
        "client.beta.messages.parse non esiste più su questo SDK: il trasporto "
        "live è di nuovo spento"
    )


def test_le_cause_di_guasto_sono_distinte() -> None:
    """Un output malformato (troncatura) è GENERAZIONE (pagata); un bug o la rete
    sono TRASPORTO — e la causa resta leggibile nel tally, mai un None indistinto."""
    import asyncio

    import pydantic

    from contracts import Flavor

    try:
        Flavor.model_validate({})
        raise AssertionError("Flavor vuoto doveva essere invalido")
    except pydantic.ValidationError as e:
        errore_forma = e

    class _MessaggiRotti:
        def __init__(self, exc: Exception) -> None:
            self._exc = exc

        async def parse(self, **_kw):
            raise self._exc

    def _client_con(exc: Exception):
        beta = type("Beta", (), {})()
        beta.messages = _MessaggiRotti(exc)
        cli = type("Cli", (), {})()
        cli.beta = beta
        return cli

    b = AnthropicBackend()
    b._client = _client_con(errore_forma)
    assert asyncio.run(b.genera("p", Flavor)) is None
    assert b.consumo.generazioni_fallite == 1 and b.consumo.errori_trasporto == 0
    assert b.consumo.ultima_causa == "forma_output"

    b2 = AnthropicBackend()
    b2._client = _client_con(AttributeError("metodo sparito"))
    assert asyncio.run(b2.genera("p", Flavor)) is None
    assert b2.consumo.errori_trasporto == 1 and b2.consumo.generazioni_fallite == 0
    assert b2.consumo.ultima_causa == "inatteso:AttributeError", (
        "un bug di codice deve dirsi per nome, non travestirsi da guasto di rete"
    )


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
    # ASSERT-IVO di proposito (giro 2026-08-07): con la chiave presente, un None è
    # un trasporto rotto — accettarlo faceva passare il test col backend morto.
    assert isinstance(candidato, Flavor) and candidato.testo, (
        f"generazione live fallita: {backend.consumo.riassunto()}"
    )


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
