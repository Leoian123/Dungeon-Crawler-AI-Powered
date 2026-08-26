"""Helper condiviso: assembla un run-World in esplorazione (NARRAZIONE) coi sistemi
del tempo registrati. Non è un modulo di test.
"""

from __future__ import annotations

from contracts import BusEventi
from motore import (
    Fase,
    SistemaDeathCheck,
    SistemaDiscesa,
    SistemaRinforzi,
    SistemaTempoPiano,
    SistemaTurnoCombattimento,
    avvia_run,
    collega_combattimento,
    collega_transizioni_fase,
    crea_entita_fase,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_tempo_piano,
    sistemi_status,
)


def avvia_esplorazione(*, seed: int = 42, hp: int = 30, destrezza: int = 10):
    """Crea i singleton + il protagonista + i sistemi (incl. tempo-piano) in NARRAZIONE.
    Ritorna (bus, entità-protagonista)."""
    bus = BusEventi()
    crea_entita_fase(Fase.NARRAZIONE)
    crea_profondita()
    crea_tempo_piano()
    crea_seme(seed)
    pent = crea_protagonista(destrezza=destrezza, punti_vita=hp)
    avvia_run(
        sempre_attivi=[
            # DERIVATI dalla tabella unica (come il guscio vero): un status nuovo
            # entra da sé, e non c'è modo di cablarne due volte lo stesso.
            *sistemi_status(),
            SistemaDeathCheck(bus), SistemaTempoPiano(),
        ],
        solo_combattimento=[SistemaRinforzi(), SistemaTurnoCombattimento(bus)],
        solo_narrazione=[SistemaDiscesa(bus)],
        crea_singleton_fase=False,
    )
    collega_transizioni_fase(bus)
    collega_combattimento(bus)
    return bus, pent
