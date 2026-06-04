"""Check 2 — danno deterministico: floor 1 sul colpo a segno, schivata (m=0) → 0 PRIMA del
floor, un solo `round`/`floor` (GR2-11; layer tipi DT-5). Headless.
"""

from __future__ import annotations

import esper

from contracts import StatId, TipoDanno
from motore import (
    G_GRAZE,
    Danno,
    Primarie,
    QuantitaDa,
    ResistenzaMod,
    applica_resistenza,
    atk_eff,
    check2,
    def_eff,
)

_D = Danno(quantita_da=QuantitaDa.ATK_EFF)  # GENERICO (untyped): nessuna resistenza applica


def _attaccante(forza: int) -> int:
    return esper.create_entity(Primarie(valori={StatId.FORZA: forza}))


def _bersaglio(*, cost: int = 1, difesa: int = 0) -> int:
    from motore import Modificatore, Modificatori, TipoMod

    voci = [Modificatore(StatId.DIFESA, TipoMod.FLAT, difesa, "armatura")] if difesa else []
    return esper.create_entity(
        Primarie(valori={StatId.COSTITUZIONE: cost}), Modificatori(voci=voci)
    )


# --- GR2-11: il colpo PIENO che connette toglie sempre ≥ 1 HP, qualunque difesa -

def test_colpo_pieno_e_la_forma_max1_round(mondo_isolato: str) -> None:
    att = _attaccante(13)
    ber = _bersaglio(cost=10, difesa=300)               # def_eff = 10 + 300 = 310 centesimi
    # atk in UNITÀ (13), def in CENTESIMI (310) → /100: round(13 − 3,10) = round(9,9) = 10.
    assert check2(1.0, att, ber, _D) == 10
    # È esattamente la forma generale con m=1.
    assert check2(1.0, att, ber, _D) == max(1, round(atk_eff(att) - def_eff(ber) / 100))


def test_floor_1_con_difesa_mostruosa(mondo_isolato: str) -> None:
    # Difesa enorme: la sottrazione va negativa, ma il colpo a segno toglie comunque ≥ 1.
    att = _attaccante(10)
    ber = _bersaglio(cost=10**6)                         # def_eff gigantesco
    assert check2(1.0, att, ber, _D) == 1               # floor 1 (GR2-11), mai 0 su colpo a segno


# --- GR2-11 / §7.2: la SCHIVATA (m=0) fa 0 — corto-circuita PRIMA del floor ------

def test_schivata_zero_prima_del_floor(mondo_isolato: str) -> None:
    att = _attaccante(1000)                             # farebbe tanto danno…
    ber = _bersaglio(cost=1)
    # …ma m=0 (schivata piena) → 0, NON 1: il floor vale solo sui colpi che connettono.
    assert check2(0.0, att, ber, _D) == 0


def test_graze_connette_floor_1(mondo_isolato: str) -> None:
    # Il graze CONNETTE (m=g): danno ≥ 1 (anche lui flooored), magnitudine deterministica.
    att = _attaccante(20)
    ber = _bersaglio(cost=10)
    atteso = max(1, round(G_GRAZE * (atk_eff(att) - def_eff(ber) / 100)))
    assert check2(G_GRAZE, att, ber, _D) == atteso >= 1


# --- DT-5: m (graze) e mult (resistenza) dentro l'UNICO round (no doppio floor) --

def test_unico_round_unico_floor_con_mult(mondo_isolato: str) -> None:
    att = _attaccante(50)
    ber = _bersaglio(cost=10)
    # Resistenza −50% al FUOCO: il mult entra nello STESSO round del graze.
    applica_resistenza(ber, ResistenzaMod(contro=TipoDanno.FUOCO, valore=-50, fonte="fae"))
    fuoco = Danno(quantita_da=QuantitaDa.ATK_EFF, tipo=TipoDanno.FUOCO)

    # UN solo round/floor: m (graze) e mult (resistenza) DENTRO lo stesso round, sulla
    # quantità PRE-round (non arrotondata prima del · mult → niente doppio arrotondamento).
    atteso = max(1, round(G_GRAZE * (atk_eff(att) - def_eff(ber) / 100) * 0.5))  # mult = 1−0.50
    assert check2(G_GRAZE, att, ber, fuoco) == atteso
