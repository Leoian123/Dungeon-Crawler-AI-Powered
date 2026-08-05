"""Il contatore di consumo del backend: l'`usage` delle risposte non si butta più via.

Offline per costruzione: il client Anthropic è FINTO (iniettato in `_client`, così
l'import pigro dell'SDK non scatta mai) — si verifica il TALLY, non il trasporto.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel

from provider import AnthropicBackend, ConsumoProvider


class _Candidato(BaseModel):
    testo: str = ""


class _Usage:
    def __init__(self, **campi: int) -> None:
        self.__dict__.update(campi)


class _Risposta:
    def __init__(self, *, usage=None, stop_reason="end_turn", parsed_output=None) -> None:
        self.usage = usage
        self.stop_reason = stop_reason
        self.parsed_output = parsed_output


class _MessaggiFinti:
    """`client.messages.parse` scriptato: un esito per chiamata, in ordine."""

    def __init__(self, esiti: list) -> None:
        self._esiti = list(esiti)

    async def parse(self, **_kwargs):
        esito = self._esiti.pop(0)
        if isinstance(esito, Exception):
            raise esito
        return esito


class _ClientFinto:
    def __init__(self, esiti: list) -> None:
        self.messages = _MessaggiFinti(esiti)


def _backend(esiti: list, consumo: ConsumoProvider | None = None) -> AnthropicBackend:
    b = AnthropicBackend(consumo=consumo)
    b._client = _ClientFinto(esiti)  # bypassa l'import pigro dell'SDK
    return b


def test_una_risposta_buona_accumula_l_usage() -> None:
    b = _backend([
        _Risposta(
            usage=_Usage(
                input_tokens=100, output_tokens=20,
                cache_creation_input_tokens=5, cache_read_input_tokens=7,
            ),
            parsed_output=_Candidato(testo="ok"),
        )
    ])
    esito = asyncio.run(b.genera("p", _Candidato))
    assert esito is not None and esito.testo == "ok"
    assert b.consumo.chiamate == 1
    assert (b.consumo.input_tokens, b.consumo.output_tokens) == (100, 20)
    assert (b.consumo.cache_scritti, b.consumo.cache_letti) == (5, 7)
    assert b.consumo.errori_trasporto == 0 and b.consumo.generazioni_fallite == 0


def test_anche_un_refusal_si_paga() -> None:
    b = _backend([
        _Risposta(usage=_Usage(input_tokens=50, output_tokens=3), stop_reason="refusal")
    ])
    assert asyncio.run(b.genera("p", _Candidato)) is None
    assert b.consumo.chiamate == 1 and b.consumo.generazioni_fallite == 1
    assert b.consumo.input_tokens == 50  # il rifiuto costa comunque: va contato


def test_errore_di_trasporto_conta_a_parte() -> None:
    b = _backend([TimeoutError("rete giù")])
    assert asyncio.run(b.genera("p", _Candidato)) is None
    assert b.consumo.errori_trasporto == 1
    assert b.consumo.chiamate == 0 and b.consumo.input_tokens == 0


def test_usage_assente_non_esplode() -> None:
    """Cintura: una forma nuova della risposta (usage mancante) non rompe il tally."""
    b = _backend([_Risposta(usage=None, parsed_output=_Candidato())])
    assert asyncio.run(b.genera("p", _Candidato)) is not None
    assert b.consumo.chiamate == 1 and b.consumo.input_tokens == 0


def test_due_backend_condividono_il_tally_della_run() -> None:
    """Il composition root passa UN ConsumoProvider a forte e veloce: il totale
    è il consumo della run, senza aggregatori."""
    condiviso = ConsumoProvider()
    forte = _backend(
        [_Risposta(usage=_Usage(input_tokens=10), parsed_output=_Candidato())], condiviso
    )
    veloce = _backend(
        [_Risposta(usage=_Usage(input_tokens=7), parsed_output=_Candidato())], condiviso
    )
    asyncio.run(forte.genera("p", _Candidato))
    asyncio.run(veloce.genera("p", _Candidato))
    assert condiviso.chiamate == 2 and condiviso.input_tokens == 17


def test_scegli_provider_live_condivide_davvero_il_tally(monkeypatch) -> None:
    """Lucchetto sul CABLAGGIO (non solo sull'unità): il ramo live di
    `_scegli_provider` deve passare lo STESSO ConsumoProvider a forte e veloce —
    se qualcuno toglie `consumo=consumo` da uno dei due, il totale per-run torna
    a essere spezzato in silenzio."""
    import gioco_textual
    import provider as pacchetto
    from contracts import TurnoNarrazione

    # Presenza di chiave e SDK simulate: il ramo live COSTRUISCE i backend ma non
    # chiama mai la rete (l'SDK è importato pigramente, solo alla prima genera).
    monkeypatch.setattr(pacchetto, "chiave_presente", lambda: True)
    monkeypatch.setattr(pacchetto, "sdk_disponibile", lambda: True)

    composto, _etichetta = gioco_textual._scegli_provider([])
    forte = composto._per_schema[TurnoNarrazione]
    veloce = composto._predefinito
    assert forte.consumo is veloce.consumo
