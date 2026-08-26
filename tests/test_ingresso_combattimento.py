"""Confine narrazione→combattimento (G-25) + disimpegno (FNC §5.3). Headless, seeded.

Una TurnoNarrazione che emette EncounterStarted è prodotta in NARRAZIONE e ha
durata == TURNO dopo il gate; nessuna entità di combattimento prima del confine.
Il disimpegno è una prova su stat PRIMA di ingaggiare (distinta dalla fuga in combat).
"""

from __future__ import annotations

import asyncio

import esper

from contracts import (
    BusEventi,
    ClasseProva,
    CombatResolved,
    Durata,
    EncounterStarted,
    MortePersonaggio,
    SchedaProiezione,
)
from motore import (
    Fase,
    Nemico,
    SpecNemico,
    SistemaDeathCheck,
    SistemaTurnoCombattimento,
    avvia_run,
    collega_combattimento,
    collega_transizioni_fase,
    crea_protagonista,
    ingaggia_combattimento,
    leggi_fase,
    procura_turno,
    tenta_disimpegno,
    valida_turno,
)
from provider import FakeProvider
from tests.narr_helpers import budget, turno

_PROIEZIONE = SchedaProiezione(descrittori=("integro",))


# --- G-25: clamp d'ingresso a TURNO; nessuna entità di combat prima del confine -

def test_G25_clamp_durata_a_turno() -> None:
    # Una battuta d'ingresso con durata "lunga" è ricondotta a TURNO dal gate.
    candidato = turno(durata=Durata.UN_BEL_PO)
    clamped = valida_turno(candidato, budget(), ingresso_combattimento=True)
    assert clamped is not None
    assert clamped.durata == Durata.TURNO


def test_G25_battuta_prodotta_in_narrazione_durata_turno() -> None:
    # La TurnoNarrazione d'ingresso è prodotta col flag d'ingresso → durata == TURNO.
    prov = FakeProvider([turno(durata=Durata.UN_ATTIMO)])
    res = asyncio.run(
        procura_turno(prov, budget(), _PROIEZIONE, ingresso_combattimento=True)
    )
    assert res.turno.durata == Durata.TURNO


def test_G25_nessuna_entita_combat_prima_del_confine(mondo_isolato: str) -> None:
    bus = BusEventi()
    crea_protagonista(destrezza=10, punti_vita=1000)
    avvia_run(
        solo_combattimento=[SistemaTurnoCombattimento(bus)],
        sempre_attivi=[SistemaDeathCheck(bus)],
        fase_iniziale=Fase.NARRAZIONE,
    )
    collega_transizioni_fase(bus)
    collega_combattimento(bus)

    # Battuta d'ingresso composta in NARRAZIONE: ancora nessuna entità di combattimento.
    prov = FakeProvider([turno(durata=Durata.UN_BEL_PO)])
    res = asyncio.run(
        procura_turno(prov, budget(), _PROIEZIONE, ingresso_combattimento=True)
    )
    assert res.turno.durata == Durata.TURNO
    assert leggi_fase() == Fase.NARRAZIONE
    assert esper.get_component(Nemico) == []  # nessun nemico materializzato

    # Solo al confine di tick — EncounterStarted — nascono i nemici e si flippa.
    ingaggia_combattimento(bus, nemici=[SpecNemico(destrezza=5, punti_vita=3)], seed=1)
    assert leggi_fase() == Fase.COMBATTIMENTO
    assert len(esper.get_component(Nemico)) == 1


# --- FNC §5.3: disimpegno = prova su stat PRIMA di ingaggiare ------------------

def test_disimpegno_riuscito_non_apre_il_combattimento() -> None:
    # Stat altissima vs classe facile → disimpegno riuscito (il motore confronta a
    # margine: nessun RNG da passare, G §7.1).
    assert tenta_disimpegno(10_000, ClasseProva.BRONZO) is True


def test_disimpegno_fallito_e_deterministico() -> None:
    a = tenta_disimpegno(0, ClasseProva.CELESTIALE)
    b = tenta_disimpegno(0, ClasseProva.CELESTIALE)
    assert a == b is False


def test_disimpegno_la_classe_la_impone_il_grado_del_mob() -> None:
    # La difficoltà non è una costante: la stessa stat basta contro un bronzo e non
    # contro un celestiale. È ciò che impedisce a "Scappa" di essere sempre uguale.
    stat = 10
    assert tenta_disimpegno(stat, ClasseProva.BRONZO) is True
    assert tenta_disimpegno(stat, ClasseProva.CELESTIALE) is False


def test_disimpegno_distinto_dalla_fuga_in_combattimento(mondo_isolato: str) -> None:
    # Il disimpegno NON apre lo scontro: se riesce, restiamo in narrazione, nessun
    # EncounterStarted, nessun Nemico. (La fuga DENTRO il combattimento è altro: emette
    # CombatResolved, e non è questo percorso.)
    bus = BusEventi()
    eventi: list = []
    for tipo in (EncounterStarted, CombatResolved, MortePersonaggio):
        bus.registra(tipo, eventi.append)

    riuscito = tenta_disimpegno(10_000, ClasseProva.BRONZO)
    if riuscito:
        pass  # nessun ingaggio
    assert eventi == []
    assert esper.get_component(Nemico) == []
