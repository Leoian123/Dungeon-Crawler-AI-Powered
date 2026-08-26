"""T4a — l'ORACOLO bit-per-bit del tick degli status, scritto PRIMA del
refactor a `effetti_tick` (GR2 §7.3): quando il comportamento per-status
diventa DATO (una tupla di primitivi iterata dal system generico), queste
sequenze devono riprodursi identiche. Se un valore qui cambia, il refactor
ha cambiato il gioco — non è più un refactor.
"""

from __future__ import annotations

import esper

from motore import (
    Brucia,
    Rigenerazione,
    Stordito,
    Veleno,
    applica_status,
    sistemi_status,
)
from motore.scheda import Scheda
from motore.turno import segna_turno_attivo
from tests.persist_helpers import costruisci_run


def _hp(ent: int) -> int:
    return esper.component_for_entity(ent, Scheda).punti_vita


def _giro(ent: int, n: int) -> list[int]:
    sequenza = []
    for _ in range(n):
        for sistema in sistemi_status():
            sistema.run(1)
        sequenza.append(_hp(ent))
    return sequenza


def test_oracolo_veleno_afflizione(mondo_isolato) -> None:
    pent = costruisci_run(hp=30)
    applica_status(pent, Veleno(rango=2, durata=3))
    segna_turno_attivo(pent)
    # delta_per_rango(veleno) = −1 × rango 2 = −2/tick per 3 tick, poi svanito.
    assert _giro(pent, 4) == [28, 26, 24, 24]
    assert not esper.has_component(pent, Veleno)


def test_oracolo_brucia_afflizione(mondo_isolato) -> None:
    pent = costruisci_run(hp=30)
    applica_status(pent, Brucia(rango=1, durata=2))
    segna_turno_attivo(pent)
    assert _giro(pent, 3) == [29, 28, 28]
    assert not esper.has_component(pent, Brucia)


def test_oracolo_rigenerazione_cura_clampata(mondo_isolato) -> None:
    pent = costruisci_run(hp=30)
    esper.component_for_entity(pent, Scheda).punti_vita = 28
    applica_status(pent, Rigenerazione(rango=1, durata=4))
    segna_turno_attivo(pent)
    # +1/tick, clampata al massimo derivato (30): 29, 30, 30, 30.
    assert _giro(pent, 4) == [29, 30, 30, 30]


def test_oracolo_stordito_zero_hp(mondo_isolato) -> None:
    pent = costruisci_run(hp=30)
    applica_status(pent, Stordito(rango=3, durata=1))
    segna_turno_attivo(pent)
    # Lo Stordito non muove HP (l'effetto è consumare il turno) e dura 1.
    assert _giro(pent, 2) == [30, 30]
    assert not esper.has_component(pent, Stordito)


def test_oracolo_innato_passivo_non_scade(mondo_isolato) -> None:
    pent = costruisci_run(hp=30)
    esper.component_for_entity(pent, Scheda).punti_vita = 25
    applica_status(pent, Rigenerazione(rango=1, durata=99, innato=True))
    segna_turno_attivo(pent)
    # Passiva innata: l'effetto tikka, la scadenza no.
    assert _giro(pent, 3) == [26, 27, 28]
    assert esper.has_component(pent, Rigenerazione)


def test_oracolo_innato_trasmissibile_non_tocca_il_portatore(mondo_isolato) -> None:
    pent = costruisci_run(hp=30)
    applica_status(pent, Veleno(rango=5, durata=99, innato=True))
    segna_turno_attivo(pent)
    # Capacità innata trasmissibile: agisce sul COLPO, mai sul portatore.
    assert _giro(pent, 3) == [30, 30, 30]
    assert esper.has_component(pent, Veleno)
