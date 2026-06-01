"""Test fumo dell'arnia headless: parte e si chiude pulito (criterio C-5).

Verifica il seam — senza Textual, senza rete — su tutte e tre le direzioni:
  - motore → vista: un evento emesso viene raccolto dall'adattatore nullo;
  - vista → motore: un intento scriptato viene drenato UNA volta, sul turno;
  - avanzamento guidato dal turno (non dall'orologio).
Nessun import di Textual, nessun socket, nessuna chiave LLM.
"""

from __future__ import annotations

from dataclasses import dataclass

from tests.harness import HeadlessRun, NullAdapter, FakeProvider


@dataclass
class EventoFinto:
    testo: str


@dataclass
class IntentoFinto:
    opzione: int


def test_arnia_parte_e_si_chiude_pulito(mondo_isolato: str) -> None:
    run = HeadlessRun()
    # Parte pulita.
    assert run.turn == 0
    assert run.adapter.events == []
    # Gira un turno a vuoto: nessun Processor → no-op deterministico.
    run.run(turns=1)
    assert run.turn == 1


def test_arnia_raccoglie_eventi_e_drena_intenti(mondo_isolato: str) -> None:
    adapter = NullAdapter()
    run = HeadlessRun(adapter=adapter, provider=FakeProvider())

    # vista → motore: inietto un intento scriptato prima del turno.
    run.inject_intent(IntentoFinto(opzione=2))
    # motore → vista: il motore (qui simulato) emette un evento di dominio.
    run.emit(EventoFinto("la stanza si rivela"))

    run.run(turns=1)

    # L'intento è stato drenato esattamente una volta, sul turno.
    assert run.drained_intents == [IntentoFinto(opzione=2)]
    # L'evento è stato raccolto dall'adattatore nullo.
    assert adapter.events_of(EventoFinto) == [EventoFinto("la stanza si rivela")]
    # La coda è vuota: nessun ri-drenaggio (semantica edge-triggered).
    run.run(turns=1)
    assert run.drained_intents == [IntentoFinto(opzione=2)]


def test_fake_provider_e_offline(mondo_isolato: str) -> None:
    # Il provider fake non tocca la rete e restituisce risposte in coda.
    import asyncio

    provider = FakeProvider()
    provider.queue_response({"esito": "ok"})
    risposta = asyncio.run(provider.complete({"prompt": "x"}))
    assert risposta == {"esito": "ok"}
    assert provider.calls == [{"prompt": "x"}]
