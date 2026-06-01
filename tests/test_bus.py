"""Bus tipizzato di progetto (ESP §5): per-tipo, riferimenti forti, esplicito.

Non è il dispatcher nativo di esper: qui si verifica il comportamento che ESP §5
richiede al bus di progetto.
"""

from __future__ import annotations

import gc

import pytest

from contracts import BusEventi, CombatResolved, EncounterStarted, MortePersonaggio


def test_sottoscrizione_per_tipo() -> None:
    bus = BusEventi()
    visti_encounter: list[EncounterStarted] = []
    visti_morte: list[MortePersonaggio] = []
    bus.registra(EncounterStarted, visti_encounter.append)
    bus.registra(MortePersonaggio, visti_morte.append)

    bus.pubblica(EncounterStarted(entita=7))
    bus.pubblica(MortePersonaggio(causa="veleno"))
    # Un evento di un terzo tipo, senza iscritti: nessun effetto, nessun errore.
    bus.pubblica(CombatResolved(entita=7, vittoria=True))

    assert visti_encounter == [EncounterStarted(entita=7)]
    assert visti_morte == [MortePersonaggio(causa="veleno")]


def test_handler_tenuto_con_riferimento_forte() -> None:
    """Il bus tiene l'handler vivo: niente weak-reference (ESP §5)."""
    bus = BusEventi()
    raccolti: list[int] = []

    # Handler creato in uno scope locale: senza riferimento forte nel bus, dopo la
    # cancellazione del nome locale + gc verrebbe raccolto e l'evento sarebbe muto.
    def handler(evt: EncounterStarted) -> None:
        raccolti.append(evt.entita)

    bus.registra(EncounterStarted, handler)
    del handler
    gc.collect()

    bus.pubblica(EncounterStarted(entita=42))
    assert raccolti == [42], "l'handler è stato raccolto: il bus non lo tiene forte"


def test_deregistrazione_esplicita() -> None:
    bus = BusEventi()
    raccolti: list[int] = []
    handler = lambda evt: raccolti.append(evt.entita)  # noqa: E731

    bus.registra(EncounterStarted, handler)
    bus.pubblica(EncounterStarted(entita=1))
    bus.deregistra(EncounterStarted, handler)
    bus.pubblica(EncounterStarted(entita=2))  # non più consegnato

    assert raccolti == [1]


def test_doppia_registrazione_e_deregistrazione_inesistente_sollevano() -> None:
    bus = BusEventi()
    handler = lambda evt: None  # noqa: E731

    bus.registra(EncounterStarted, handler)
    with pytest.raises(ValueError):
        bus.registra(EncounterStarted, handler)  # già registrato

    bus.deregistra(EncounterStarted, handler)
    with pytest.raises(ValueError):
        bus.deregistra(EncounterStarted, handler)  # non più presente


def test_handler_puo_deregistrarsi_durante_il_dispatch() -> None:
    bus = BusEventi()
    raccolti: list[int] = []

    def una_volta(evt: EncounterStarted) -> None:
        raccolti.append(evt.entita)
        bus.deregistra(EncounterStarted, una_volta)

    bus.registra(EncounterStarted, una_volta)
    bus.pubblica(EncounterStarted(entita=1))
    bus.pubblica(EncounterStarted(entita=2))  # già deregistrato
    assert raccolti == [1]
