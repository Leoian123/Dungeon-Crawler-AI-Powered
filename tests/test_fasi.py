"""Fase corrente, phase-gate strutturale, tre bucket con ordine deterministico,
transizioni di fase via bus (FNC §6.1, §6.2, §6.4; IC §7.1).

Tutto headless: niente Textual, niente rete.
"""

from __future__ import annotations

import dataclasses
import json

import esper
import pytest

from contracts import BusEventi, CombatResolved, EncounterStarted
from motore import (
    Fase,
    FaseCorrente,
    PhasedProcessor,
    SistemaSempreAttivo,
    SistemaSoloCombattimento,
    SistemaSoloNarrazione,
    avvia_run,
    collega_transizioni_fase,
    crea_entita_fase,
    imposta_fase,
    leggi_fase,
    tick,
)


# --- Spia: registra il proprio nome quando il suo run() viene eseguito ---------

def _spia(base: type[PhasedProcessor], nome: str, log: list[str]) -> PhasedProcessor:
    class _S(base):  # type: ignore[valid-type, misc]
        def run(self, dt: int) -> None:
            log.append(nome)

    _S.__name__ = f"Spia_{nome}"
    return _S()


# --- 1) FaseCorrente: singleton serializzabile col save -----------------------

def test_fase_corrente_e_dato_puro_serializzabile() -> None:
    fc = FaseCorrente(Fase.COMBATTIMENTO)
    # Dato puro: dataclass, nessun metodo di dominio.
    assert dataclasses.is_dataclass(fc)
    # Serializzabile come stringa (Fase è str-Enum) → round-trip JSON.
    grezzo = json.dumps(dataclasses.asdict(fc))
    ricostruita = FaseCorrente(Fase(json.loads(grezzo)["fase"]))
    assert ricostruita == fc


def test_fase_e_singleton_nel_world(mondo_isolato: str) -> None:
    crea_entita_fase(Fase.NARRAZIONE)
    assert leggi_fase() == Fase.NARRAZIONE
    assert len(esper.get_component(FaseCorrente)) == 1
    imposta_fase(Fase.COMBATTIMENTO)
    assert leggi_fase() == Fase.COMBATTIMENTO


def test_leggi_fase_richiede_esattamente_un_singleton(mondo_isolato: str) -> None:
    with pytest.raises(RuntimeError):
        leggi_fase()  # nessun singleton ancora creato
    crea_entita_fase()
    crea_entita_fase()  # due → non più singleton
    with pytest.raises(RuntimeError):
        leggi_fase()


# --- 2) Phase-gate: i sistemi girano solo nelle loro fasi ---------------------

def test_phase_gate_attiva_solo_la_fase_giusta(mondo_isolato: str) -> None:
    log: list[str] = []
    avvia_run(
        solo_narrazione=[_spia(SistemaSoloNarrazione, "narr", log)],
        solo_combattimento=[_spia(SistemaSoloCombattimento, "comb", log)],
        sempre_attivi=[_spia(SistemaSempreAttivo, "sempre", log)],
        fase_iniziale=Fase.NARRAZIONE,
    )

    tick()
    assert log == ["narr", "sempre"]  # combat gated off in narrazione

    log.clear()
    imposta_fase(Fase.COMBATTIMENTO)
    tick()
    assert log == ["comb", "sempre"]  # narrazione gated off in combattimento


# --- 3) Tre bucket: ordine deterministico dichiarato --------------------------

def test_ordine_dei_sistemi_e_deterministico(mondo_isolato: str) -> None:
    log: list[str] = []
    # Due sempre-attivi per provare anche l'ordine DENTRO un bucket (registrazione).
    avvia_run(
        solo_combattimento=[_spia(SistemaSoloCombattimento, "comb", log)],
        solo_narrazione=[_spia(SistemaSoloNarrazione, "narr", log)],
        sempre_attivi=[
            _spia(SistemaSempreAttivo, "sempreA", log),
            _spia(SistemaSempreAttivo, "sempreB", log),
        ],
        fase_iniziale=Fase.NARRAZIONE,
    )

    tick()
    # Fra bucket: narr(2000) prima di sempre(1000); comb(3000) gated off.
    # Dentro il bucket: ordine di registrazione (sempreA prima di sempreB).
    assert log == ["narr", "sempreA", "sempreB"]

    log.clear()
    imposta_fase(Fase.COMBATTIMENTO)
    tick()
    # comb(3000) prima di sempre(1000); narr gated off.
    assert log == ["comb", "sempreA", "sempreB"]


def test_avvia_run_rifiuta_sistema_nel_bucket_sbagliato(mondo_isolato: str) -> None:
    # Un sistema solo-combattimento messo fra i sempre-attivi: errore esplicito.
    # Difende la partizione "un solo proprietario per componente con stato" (§6.2).
    log: list[str] = []
    with pytest.raises(ValueError):
        avvia_run(sempre_attivi=[_spia(SistemaSoloCombattimento, "x", log)])


# --- 4) Transizioni di fase: solo via evento tipizzato sul bus ----------------

def test_transizioni_di_fase_via_bus(mondo_isolato: str) -> None:
    crea_entita_fase(Fase.NARRAZIONE)
    bus = BusEventi()
    collega_transizioni_fase(bus)

    assert leggi_fase() == Fase.NARRAZIONE
    bus.pubblica(EncounterStarted(entita=1))
    assert leggi_fase() == Fase.COMBATTIMENTO
    bus.pubblica(CombatResolved(entita=1, vittoria=True))
    assert leggi_fase() == Fase.NARRAZIONE
