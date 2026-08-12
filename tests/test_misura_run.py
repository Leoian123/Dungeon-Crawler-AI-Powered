"""Lucchetti dell'harness di misura della vincibilità (`misura_run`, STATO.md §4.1)
+ la regressione del soft-lock da rientro in zona che l'harness ha scovato.

Le run sono offline (copione, mai rete), seeded, via porte: qui si verifica che la
MISURA sia riproducibile — non un win-rate atteso (quello è il risultato, non il test).
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict

import esper
import pytest

from guscio import NOME_DEFAULT, NOME_RUN
from misura_run import POLITICHE, EsitoRun, gioca_run, riassumi


@pytest.fixture
def mondo_pulito():
    esper.switch_world(NOME_DEFAULT)
    if NOME_RUN in esper.list_worlds():
        esper.delete_world(NOME_RUN)
    yield
    esper.switch_world(NOME_DEFAULT)
    if NOME_RUN in esper.list_worlds():
        esper.delete_world(NOME_RUN)


def test_una_run_produce_un_esito_coerente(mondo_pulito) -> None:
    esito = asyncio.run(gioca_run(POLITICHE["combatti"], seed=0, max_turni=40))
    assert esito.esito in ("vittoria", "morte", "timeout")
    assert esito.turni <= 40
    assert esito.profondita >= 1
    assert esito.narrazioni > 0  # senza turni GM non si è giocato niente


def test_la_misura_e_riproducibile(mondo_pulito) -> None:
    """Stessa (politica, seed) → stesso esito, campo per campo. È la proprietà
    che rende la misura una MISURA (la storica «40 run, zero vittorie» non era
    rilanciabile: l'harness non stava nel repo)."""
    prima = asyncio.run(gioca_run(POLITICHE["fuga12"], seed=3, max_turni=40))
    seconda = asyncio.run(gioca_run(POLITICHE["fuga12"], seed=3, max_turni=40))
    assert asdict(prima) == asdict(seconda)


def test_riassumi_aggrega_per_politica() -> None:
    esiti = [
        EsitoRun(politica="x", seed=0, esito="vittoria", turni=10),
        EsitoRun(politica="x", seed=1, esito="morte", causa_morte="fulmine", turni=20),
        EsitoRun(politica="y", seed=0, esito="timeout", turni=5),
    ]
    righe = {r.politica: r for r in riassumi(esiti)}
    assert righe["x"].run == 2
    assert righe["x"].vittorie == 1 and righe["x"].morti == 1
    assert righe["x"].win_rate == 0.5
    assert righe["x"].turni_medi == 15
    assert righe["x"].cause_morte == {"fulmine": 1}
    assert righe["y"].timeout == 1 and righe["y"].win_rate == 0.0


def test_rilettura_reveal_segna_la_visita(mondo_pulito) -> None:
    """Regressione del SOFT-LOCK da rientro in zona (scoperto dall'harness):
    al rientro la mappa rinasce con `visitate` vuoto; il reveal della stanza fa
    cache-hit sull'Archivio e PRIMA del fix non chiamava mai `segna_visitata()`
    (viveva solo nel ramo live) → scena vuota → l'host chiede un altro turno →
    stesso cache-hit → menu vuoto per sempre. Il contratto verso l'host è:
    dopo un turno GM la scena esiste, da cache o meno."""
    from main import costruisci_sessione
    from motore.mappa import mappa_corrente, stanza_visitata

    sessione = costruisci_sessione(seed=0)
    asyncio.run(sessione.prossima_narrazione())  # primo reveal: congela il turno
    assert stanza_visitata()

    _ent, mappa = mappa_corrente()
    mappa.visitate.clear()  # il rientro in zona: mappa rinata, Archivio già pieno
    snapshot = asyncio.run(sessione.prossima_narrazione())  # rilettura (zero chiamate)
    assert stanza_visitata(), "la rilettura del reveal deve contare come visita"
    assert snapshot.opzioni, "dopo il turno GM riletto la scena deve esistere"
    sessione.esci()


def test_la_politica_gioca_il_nascondino(mondo_isolato) -> None:
    """Il punto della run non è battere il celestiale: è raggiungere la scala
    EVITANDOLO. Nella tana la stanza del Lich non si imbocca mai e, se ci si
    trova davanti a lui, qualunque politica arretra (mai ingaggio)."""
    import random
    from collections import Counter

    from contracts import BusEventi, OpzioneVista, TipoAzione
    from misura_run import _scelta_scena, _stanze_da_evitare
    from motore import (
        avvia_territorio,
        crea_profondita,
        crea_protagonista,
        crea_seme,
        crea_stagione,
        crea_tempo_piano,
        mappa_corrente,
        rigenera_mappa_zona,
        spina_del_piano,
        stanza_boss_di,
    )
    from tests.contenuti_sintetici import piano_territoriale, stagione_sintetica
    from main import _stagione_a_attiva

    crea_profondita()
    crea_seme(7)
    crea_tempo_piano()
    crea_stagione(_stagione_a_attiva(
        stagione_sintetica(piani=[piano_territoriale(1)], slug="s-nascondino")
    ))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    avvia_territorio(1)
    BusEventi()

    spina = spina_del_piano(1)
    assert _stanze_da_evitare() == set()  # nelle zone ordinarie il boss è un gate

    tana = spina[-1]
    rigenera_mappa_zona(1, tana)
    _e, mappa = mappa_corrente()
    boss = stanza_boss_di(tana, mappa.piano)
    assert _stanze_da_evitare() == {boss}

    # Movimento: la stanza del Lich non viene MAI scelta (su molti tiri).
    opzioni = (
        OpzioneVista(indice=0, etichetta=f"Vai: stanza {boss}", tipo=TipoAzione.MUOVI),
        OpzioneVista(indice=1, etichetta="Vai: stanza 0", tipo=TipoAzione.MUOVI),
    )
    for seme in range(20):
        indice, _et = _scelta_scena(
            POLITICHE["combatti"], opzioni, Counter(), random.Random(seme)
        )
        assert indice == 1, "la politica ha imboccato la stanza del Lich"

    # Ingaggio: davanti al custode della tana anche combatti-sempre arretra.
    mappa.stanza_corrente = boss
    scena_lich = (
        OpzioneVista(indice=0, etichetta="Combatti", tipo=TipoAzione.COMBATTI),
        OpzioneVista(indice=1, etichetta="Scappi", tipo=TipoAzione.SCAPPA),
    )
    indice, _et = _scelta_scena(
        POLITICHE["combatti"], scena_lich, Counter(), random.Random(0)
    )
    assert indice == 1, "davanti al celestiale si arretra, mai ingaggio"


def test_stanza_di_legge_solo_etichette_di_movimento() -> None:
    """Il sensore di laboratorio che rilegge l'id-stanza dalle parole del menu:
    le etichette non-movimento non devono produrre un id fantasma."""
    from misura_run import _stanza_di

    assert _stanza_di("Vai: stanza 12") == 12
    assert _stanza_di("Vai: stanza 0") == 0
    assert _stanza_di("Torna sulla via principale") is None
    assert _stanza_di("Attraversa: verso citta") is None
