"""Escalation a contatore (`SistemaCrollo`): terminazione per costruzione (GR2-15, Gruppo 2
§8). Danno inevitabile, crescente, a TUTTI, indipendente dalle stat — bypassa il risolutore.
Headless, seeded.
"""

from __future__ import annotations

import random

import esper

from contracts import CombatResolved, MortePersonaggio
from motore import (
    CROLLO_INCREMENTO,
    Fase,
    Nemico,
    PuntiVita,
    R_SOGLIA_CROLLO,
    SistemaCrollo,
    SpecNemico,
    StatoCombattimento,
    crea_protagonista,
    protagonista,
    stato_combattimento,
    tick,
)
from tests.combat_helpers import avvia_scontro


def _stato_oltre_soglia(turni: int) -> None:
    esper.create_entity(
        StatoCombattimento(
            ordine=[], indice=-1, round=0, prossima_chiave=0,
            rng=random.Random(0), turni_scontro=turni, crollo=0,
        )
    )


# --- GR2-15: oltre la soglia, danno inevitabile a TUTTI, indipendente dalle stat -

def test_crollo_inevitabile_a_tutti(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=1000)
    _stato_oltre_soglia(R_SOGLIA_CROLLO + 1)            # già oltre la soglia
    nem = esper.create_entity(Nemico(), PuntiVita(attuali=1000, massimi=1000))
    hp_p0 = protagonista()[2].punti_vita

    SistemaCrollo().run(1)                              # un confine di turno

    _e, stato = stato_combattimento()
    assert stato.crollo == CROLLO_INCREMENTO            # il contatore è cresciuto
    # …e il danno inevitabile ha colpito SIA il protagonista SIA il nemico (a tutti).
    assert protagonista()[2].punti_vita == hp_p0 - CROLLO_INCREMENTO
    assert esper.component_for_entity(nem, PuntiVita).attuali == 1000 - CROLLO_INCREMENTO
    assert pent  # sanity


def test_il_crollo_si_narra_sul_bus(mondo_isolato: str) -> None:
    """Regression (giro 2026-08-07): l'escalation infliggeva danno MUTO — HP che
    calavano senza una riga di cronaca. Col bus, ogni morso del dungeon parla."""
    from contracts import BusEventi, CrolloDungeon

    crea_protagonista(destrezza=10, punti_vita=1000)
    _stato_oltre_soglia(R_SOGLIA_CROLLO + 1)
    esper.create_entity(Nemico(), PuntiVita(attuali=1000, massimi=1000))
    bus = BusEventi()
    visti: list[CrolloDungeon] = []
    bus.registra(CrolloDungeon, visti.append)
    try:
        SistemaCrollo(bus).run(1)
    finally:
        bus.deregistra(CrolloDungeon, visti.append)
    assert visti and visti[-1].danno == CROLLO_INCREMENTO


def test_crollo_non_scatta_sotto_soglia(mondo_isolato: str) -> None:
    crea_protagonista(destrezza=10, punti_vita=1000)
    _stato_oltre_soglia(R_SOGLIA_CROLLO)               # = soglia, NON oltre
    esper.create_entity(Nemico(), PuntiVita(attuali=1000, massimi=1000))
    hp0 = protagonista()[2].punti_vita

    SistemaCrollo().run(1)

    _e, stato = stato_combattimento()
    assert stato.crollo == 0                            # non scattato
    assert protagonista()[2].punti_vita == hp0          # nessun danno


def test_crollo_cresce_illimitato(mondo_isolato: str) -> None:
    crea_protagonista(destrezza=10, punti_vita=10**9)
    _stato_oltre_soglia(R_SOGLIA_CROLLO + 1)
    nem = esper.create_entity(Nemico(), PuntiVita(attuali=10**9, massimi=10**9))

    danni = []
    for _ in range(3):
        prima = esper.component_for_entity(nem, PuntiVita).attuali
        SistemaCrollo().run(1)
        danni.append(prima - esper.component_for_entity(nem, PuntiVita).attuali)
    # Danno inevitabile CRESCENTE (aritmetica monotòna): 1·k, 2·k, 3·k.
    assert danni == [CROLLO_INCREMENTO, 2 * CROLLO_INCREMENTO, 3 * CROLLO_INCREMENTO]


def test_crollo_indipendente_dalle_stat(mondo_isolato: str) -> None:
    # Due nemici con DIFESA opposta subiscono lo STESSO crollo: bypassa `−def` (§8).
    crea_protagonista(destrezza=10, punti_vita=10**9)
    _stato_oltre_soglia(R_SOGLIA_CROLLO + 1)
    from contracts import StatId
    from motore import Modificatore, Modificatori, Primarie, TipoMod

    debole = esper.create_entity(Nemico(), PuntiVita(attuali=1000, massimi=1000),
                                 Primarie(valori={StatId.COSTITUZIONE: 1}))
    corazzato = esper.create_entity(
        Nemico(), PuntiVita(attuali=1000, massimi=1000),
        Primarie(valori={StatId.COSTITUZIONE: 10**6}),
        Modificatori(voci=[Modificatore(StatId.DIFESA, TipoMod.FLAT, 10**6, "piastra")]),
    )
    SistemaCrollo().run(1)
    d1 = 1000 - esper.component_for_entity(debole, PuntiVita).attuali
    d2 = 1000 - esper.component_for_entity(corazzato, PuntiVita).attuali
    assert d1 == d2 == CROLLO_INCREMENTO               # la difesa NON mitiga il crollo


# --- GR2-15 (comportamentale): lo scontro termina in round limitati grazie al crollo

def test_crollo_termina_uno_stallo(mondo_isolato: str) -> None:
    # Stallo "quasi inscalfibile": difese altissime → il danno normale è floored a 1, HP
    # ampi → senza escalation servirebbero ~migliaia di turni. Il crollo (oltre R) lo chiude
    # in un numero LIMITATO di round, indipendentemente dalle stat (G-L1).
    _bus, adapter, _enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=5, punti_vita=1000)],
        hp_prot=1000, destrezza_prot=10,
    )
    terminato = False
    for _ in range(R_SOGLIA_CROLLO + 200):             # bound limitato (≪ 2·HP turni)
        tick()
        if adapter.events_of(CombatResolved) or adapter.events_of(MortePersonaggio):
            terminato = True
            break
    assert terminato, "l'escalation deve chiudere lo stallo in round limitati (GR2-15)"
    st = stato_combattimento()
    # Se lo scontro è ancora montato, il crollo dev'essere scattato (driver della fine).
    if st is not None:
        assert st[1].crollo > 0


def test_crollo_e_solo_combattimento() -> None:
    # Vive nel bucket solo-combattimento (priorità dichiarata, gira a confine di turno).
    assert SistemaCrollo().fasi_attive == frozenset({Fase.COMBATTIMENTO})
