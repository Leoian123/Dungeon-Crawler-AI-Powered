"""Helper condiviso per l'arnia di combattimento (non è un modulo di test).

Assembla uno scontro headless: protagonista + nemici da `PianoIncontro`, i sistemi
nei bucket giusti, le transizioni e il ciclo di vita, poi pubblica `EncounterStarted`
per materializzare. Ritorna (bus, adapter, entità-incontro).
"""

from __future__ import annotations

import esper

from contracts import BusEventi, CombatResolved, EncounterStarted, MortePersonaggio
from motore import (
    Fase,
    PianoIncontro,
    SistemaCrollo,
    SistemaDeathCheck,
    SistemaRinforzi,
    SistemaTurnoCombattimento,
    avvia_run,
    collega_combattimento,
    collega_transizioni_fase,
    crea_protagonista,
    sistemi_status,
)
from tests.harness import NullAdapter


def avvia_scontro(
    *, nemici, seed: int = 1, hp_prot: int = 10_000, destrezza_prot: int = 10, arruolate=()
):
    bus = BusEventi()
    adapter = NullAdapter()
    for tipo in (EncounterStarted, CombatResolved, MortePersonaggio):
        bus.registra(tipo, adapter.on_event)

    crea_protagonista(destrezza=destrezza_prot, punti_vita=hp_prot)
    enc = esper.create_entity(
        PianoIncontro(nemici=list(nemici), seed=seed, arruolate=list(arruolate))
    )

    avvia_run(
        # Ordine dichiarato dentro il bucket (priorità = registrazione): rinforzi (confine di
        # turno) PRIMA del sistema-turno (G-9); l'escalation `SistemaCrollo` DOPO, così legge
        # il `turni_scontro` appena avanzato dal turno (Gruppo 2 §8, GR2-15).
        solo_combattimento=[SistemaRinforzi(), SistemaTurnoCombattimento(bus), SistemaCrollo()],
        # I tick di status sono derivati dalla tabella unica (SPEC_STATUS), come
        # nel guscio vero: l'arnia di test non elenca più i sistemi a mano.
        sempre_attivi=[*sistemi_status(), SistemaDeathCheck(bus)],
        fase_iniziale=Fase.NARRAZIONE,
    )
    collega_transizioni_fase(bus)
    collega_combattimento(bus)

    bus.pubblica(EncounterStarted(entita=enc))  # flip a COMBATTIMENTO + materializza
    return bus, adapter, enc
