"""Quantità derivate: max_HP da Costituzione, HP_corrente posseduto e clampato
(Gruppo 2 §5). Copre GR2-10 (forma).
"""

from __future__ import annotations

import esper

from contracts import StatId
from motore import (
    Modificatore,
    Primarie,
    Scheda,
    TipoMod,
    applica_modificatore,
    clampa_hp,
    crea_protagonista,
    max_hp,
)


def test_GR2_10_max_hp_deriva_da_costituzione(mondo_isolato: str) -> None:
    ent = esper.create_entity(Primarie(valori={StatId.COSTITUZIONE: 30}))
    assert max_hp(ent) == 30  # 1→1 segnaposto §5

    # Un modificatore sulla Costituzione si propaga DA SOLO al massimo derivato.
    applica_modificatore(ent, Modificatore(StatId.COSTITUZIONE, TipoMod.FLAT, -8, "debuff"))
    assert max_hp(ent) == 22


def test_GR2_10_max_hp_non_e_depositato(mondo_isolato: str) -> None:
    ent = esper.create_entity(Primarie(valori={StatId.COSTITUZIONE: 30}))
    prima = {type(c) for c in esper.components_for_entity(ent)}
    max_hp(ent)
    assert {type(c) for c in esper.components_for_entity(ent)} == prima


def test_GR2_10_hp_corrente_posseduto_e_clampato(mondo_isolato: str) -> None:
    # Il protagonista nasce "integro": HP corrente == massimo derivato.
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    scheda = esper.component_for_entity(pent, Scheda)
    assert scheda.punti_vita == max_hp(pent) == 30

    # Se la Costituzione cala (massimo derivato scende), il clamp tiene HP ≤ massimo.
    applica_modificatore(pent, Modificatore(StatId.COSTITUZIONE, TipoMod.FLAT, -10, "debuff"))
    assert max_hp(pent) == 20
    clampa_hp(pent)
    assert scheda.punti_vita == 20

    # HP_corrente è stato posseduto: scende col danno, sotto il massimo, e non risale solo.
    scheda.punti_vita = 5
    clampa_hp(pent)  # 5 ≤ 20: il clamp non lo gonfia
    assert scheda.punti_vita == 5
