"""Livello = profondità del piano + completabilità (G-16, G-18). Headless, seeded.

Il livello avanza SOLO all'attivazione di una DiscesaPiano per intento del giocatore;
nessun altro evento lo incrementa. Ogni piano generato ha almeno una DiscesaPiano
raggiungibile; il gate rifiuta/ripara un piano senza uscita.
"""

from __future__ import annotations

import esper

from contracts import (
    BusEventi,
    CombatResolved,
    DiscesaPiano,
    EncounterStarted,
    PlayerDiscende,
)
from motore import (
    LIVELLO_INIZIALE,
    MessaggioIntento,
    Piano,
    SistemaDiscesa,
    attiva_discesa,
    avvia_run,
    crea_profondita,
    livello_corrente,
    piano_completabile,
    raggiungibili,
    tick,
    valida_piano,
)
from tests.harness import NullAdapter


# --- G-16: il livello avanza SOLO su DiscesaPiano (intento del giocatore) ------

def test_G16_livello_parte_da_uno(mondo_isolato: str) -> None:
    crea_profondita()
    assert livello_corrente() == LIVELLO_INIZIALE == 1


def test_G16_attiva_discesa_incrementa_ed_emette_evento(mondo_isolato: str) -> None:
    crea_profondita()
    bus = BusEventi()
    adapter = NullAdapter()
    bus.registra(DiscesaPiano, adapter.on_event)

    nuovo = attiva_discesa(bus)
    assert nuovo == 2
    assert livello_corrente() == 2
    eventi = adapter.events_of(DiscesaPiano)
    assert len(eventi) == 1 and eventi[0].piano == 2


def test_G16_nessun_altro_evento_incrementa_il_livello(mondo_isolato: str) -> None:
    crea_profondita()
    bus = BusEventi()
    # Eventi che NON devono toccare il livello.
    bus.pubblica(EncounterStarted(entita=1))
    bus.pubblica(CombatResolved(entita=1, vittoria=True))
    assert livello_corrente() == 1


def test_G16_discesa_solo_per_intento_del_giocatore(mondo_isolato: str) -> None:
    crea_profondita()
    bus = BusEventi()
    adapter = NullAdapter()
    bus.registra(DiscesaPiano, adapter.on_event)
    avvia_run(solo_narrazione=[SistemaDiscesa(bus)])

    # Senza intento, i tick non cambiano il livello.
    tick()
    tick()
    assert livello_corrente() == 1

    # Con l'intento di discesa drenato, il livello avanza (una sola volta).
    esper.create_entity(MessaggioIntento(PlayerDiscende()))
    tick()
    assert livello_corrente() == 2
    assert len(adapter.events_of(DiscesaPiano)) == 1
    # L'intento è consumato: un tick successivo non ri-scende.
    tick()
    assert livello_corrente() == 2


# --- G-18: ogni piano ha almeno una DiscesaPiano raggiungibile ----------------

def _piano_lineare(con_uscita: bool) -> Piano:
    # Stanze 0-1-2-3 in catena; partenza 0. Uscita in 3 se richiesta.
    adiacenze = {0: [1], 1: [0, 2], 2: [1, 3], 3: [2]}
    discese = {3} if con_uscita else set()
    return Piano(partenza=0, adiacenze=adiacenze, discese=discese)


def test_G18_piano_con_uscita_raggiungibile_passa() -> None:
    piano = _piano_lineare(con_uscita=True)
    assert piano_completabile(piano)
    assert valida_piano(piano) is piano  # invariato


def test_G18_piano_senza_uscita_viene_riparato() -> None:
    piano = _piano_lineare(con_uscita=False)
    assert not piano_completabile(piano)
    riparato = valida_piano(piano, ripara=True)
    assert riparato is not None
    assert piano_completabile(riparato)
    # La discesa riparata è in una stanza RAGGIUNGIBILE dalla partenza.
    racc = raggiungibili(riparato)
    assert any(d in racc for d in riparato.discese)


def test_G18_piano_senza_uscita_rifiutato_se_non_si_ripara() -> None:
    piano = _piano_lineare(con_uscita=False)
    assert valida_piano(piano, ripara=False) is None


def test_G18_discesa_irraggiungibile_non_basta() -> None:
    # Stanza 9 isolata contiene una discesa, ma non è raggiungibile dalla partenza.
    piano = Piano(partenza=0, adiacenze={0: [1], 1: [0]}, discese={9})
    assert not piano_completabile(piano)
    riparato = valida_piano(piano)
    assert piano_completabile(riparato)
    racc = raggiungibili(riparato)
    assert any(d in racc for d in riparato.discese)
