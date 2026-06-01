"""Coda degli intenti: drenata da un Processor SUL TURNO, mai sul tempo di parete
(IC §7.1, C-8); consumo phase-gated nello stesso giro (ESP §4).

Headless: si iniettano intenti scriptati nella coda e si fanno assert sugli eventi
emessi (raccolti dall'adattatore nullo dell'arnia).
"""

from __future__ import annotations

import esper

from contracts import EncounterStarted, PlayerChoseOption, BusEventi
from motore import (
    Fase,
    MessaggioIntento,
    SistemaSoloNarrazione,
    avvia_run,
    collega_transizioni_fase,
    imposta_fase,
    leggi_fase,
    tick,
)
from tests.harness import NullAdapter


def _messaggi() -> list:
    return esper.get_component(MessaggioIntento)


# --- C-8: la coda è drenata da un Processor sul turno, non da un timer ---------

def test_drenaggio_avviene_solo_sul_tick(mondo_isolato: str) -> None:
    coda = avvia_run()  # nessun sistema: solo il drenaggio
    coda.accoda(PlayerChoseOption(1))
    coda.accoda(PlayerChoseOption(2))

    # PRIMA di qualunque tick: nulla è stato drenato. Nessun timer a frame liberi
    # ha potuto svuotare la coda — l'avanzamento è guidato dal turno.
    assert len(coda) == 2
    assert _messaggi() == []

    tick()  # un turno: il Processor di drenaggio gira UNA volta
    assert len(coda) == 0
    assert len(_messaggi()) == 2


def test_drenaggio_una_volta_per_turno(mondo_isolato: str) -> None:
    coda = avvia_run()
    coda.accoda(PlayerChoseOption(0))
    tick()
    assert len(_messaggi()) == 1

    # Un secondo turno senza nuovi intenti non drena nulla di nuovo (edge-triggered).
    tick()
    assert len(_messaggi()) == 1

    # Tre nuovi intenti, un turno: esattamente tre nuovi messaggi (una volta sola).
    coda.accoda(PlayerChoseOption(1))
    coda.accoda(PlayerChoseOption(2))
    coda.accoda(PlayerChoseOption(3))
    tick()
    assert len(_messaggi()) == 4


# --- Consumo phase-gated nello stesso giro (drenaggio → consumatore) -----------

class _ConsumaScelta(SistemaSoloNarrazione):
    """Sistema solo-narrazione: consuma un `MessaggioIntento(PlayerChoseOption)`,
    emette `EncounterStarted` sul bus e RIMUOVE il messaggio (ESP §4, Canale A)."""

    def __init__(self, bus: BusEventi) -> None:
        self.bus = bus

    def run(self, dt: int) -> None:
        for ent, msg in list(esper.get_component(MessaggioIntento)):
            if isinstance(msg.intento, PlayerChoseOption):
                self.bus.pubblica(EncounterStarted(entita=ent))
                esper.remove_component(ent, MessaggioIntento)


def test_intento_drenato_e_consumato_nello_stesso_turno(mondo_isolato: str) -> None:
    bus = BusEventi()
    adapter = NullAdapter()
    bus.registra(EncounterStarted, adapter.on_event)
    collega_transizioni_fase(bus)

    coda = avvia_run(solo_narrazione=[_ConsumaScelta(bus)], fase_iniziale=Fase.NARRAZIONE)

    coda.accoda(PlayerChoseOption(0))
    tick()  # drenaggio (10000) deposita il messaggio; il consumatore (2000) lo gestisce, stesso giro

    # Evento emesso e raccolto dall'adattatore nullo.
    assert adapter.events_of(EncounterStarted)
    # Messaggio consumato (rimosso): nessun residuo.
    assert _messaggi() == []
    # La transizione di fase è scattata via bus.
    assert leggi_fase() == Fase.COMBATTIMENTO


def test_consumo_rispetta_il_phase_gate(mondo_isolato: str) -> None:
    """In COMBATTIMENTO il consumatore di narrazione NON gira: l'intento di
    narrazione non viene servito al volo (IC §7.1)."""
    bus = BusEventi()
    adapter = NullAdapter()
    bus.registra(EncounterStarted, adapter.on_event)

    coda = avvia_run(solo_narrazione=[_ConsumaScelta(bus)], fase_iniziale=Fase.NARRAZIONE)
    imposta_fase(Fase.COMBATTIMENTO)

    coda.accoda(PlayerChoseOption(0))
    tick()  # il messaggio viene drenato, ma il consumatore (solo-narrazione) è gated off

    assert adapter.events_of(EncounterStarted) == []   # nessun evento
    assert len(_messaggi()) == 1                        # messaggio non consumato
