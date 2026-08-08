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
    acc_eff,
    applica_modificatore,
    atk_eff,
    clampa_hp,
    cost_eff_come_centesimi,
    crea_protagonista,
    def_eff,
    eva_eff,
    max_hp,
)
from motore import calibrazione as cal


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


# --- 2b-B / GR2-10: le quattro derivate del risolutore leggono `stat_eff` -------

def test_atk_eff_da_forza(mondo_isolato: str) -> None:
    # Offesa (check 2) = Forza, in UNITÀ; un modificatore su Forza si propaga da solo.
    ent = esper.create_entity(Primarie(valori={StatId.FORZA: 12}))
    assert atk_eff(ent) == 12
    applica_modificatore(ent, Modificatore(StatId.FORZA, TipoMod.PCT, 0.25, "buff"))
    assert atk_eff(ent) == 15  # 12×1.25


def test_cost_eff_come_centesimi_ritorna_int(mondo_isolato: str) -> None:
    # Termine muscolare in CENTESIMI: Cost_eff (unità) == Cost_eff centesimi (una conversione).
    ent = esper.create_entity(Primarie(valori={StatId.COSTITUZIONE: 30}))
    v = cost_eff_come_centesimi(ent)
    assert isinstance(v, int) and v == 30


def test_def_eff_due_termini_in_centesimi(mondo_isolato: str) -> None:
    # def_eff = muscolare (Cost in centesimi) + armatura (DIFESA, già centesimi), ENTRAMBI
    # centesimi. Nudo: solo il muscolare. Con armatura: i due si sommano in centesimi.
    nudo = esper.create_entity(Primarie(valori={StatId.COSTITUZIONE: 30}))  # niente DIFESA
    assert def_eff(nudo) == 30  # 30 (Cost) + 0 (DIFESA assente)

    armato = esper.create_entity(Primarie(valori={StatId.COSTITUZIONE: 30}))
    applica_modificatore(armato, Modificatore(StatId.DIFESA, TipoMod.FLAT, 310, "corazza"))
    assert def_eff(armato) == 340  # 30 (muscolare) + 310 (armatura), tutto in centesimi


def test_def_eff_pct_armatura_non_gonfia_i_muscoli(mondo_isolato: str) -> None:
    # Asimmetria voluta (§5.2): un +% su DIFESA scala solo l'armatura, non il termine muscolare.
    ent = esper.create_entity(Primarie(valori={StatId.COSTITUZIONE: 30}))
    applica_modificatore(ent, Modificatore(StatId.DIFESA, TipoMod.FLAT, 200, "corazza"))
    applica_modificatore(ent, Modificatore(StatId.DIFESA, TipoMod.PCT, 0.50, "enchant"))
    # muscolare 30 (invariato) + armatura 200×1.50 = 300 → 330. Il +50% NON tocca i 30 muscolari.
    assert def_eff(ent) == 330


def test_eva_eff_destrezza_per_coeff(mondo_isolato: str) -> None:
    # eva_eff = Des_eff × coeff_eva (geometria default MVP: veste×media). Magnitudine da Des.
    ent = esper.create_entity(Primarie(valori={StatId.DESTREZZA: 40}))
    # `K_EVA` è la scala globale: senza di lei il check 1 non si accenderebbe mai (§11).
    coeff = cal.K_EVA * cal.M_ARMATURA[cal.ARMATURA_DEFAULT] * cal.M_TAGLIA[cal.TAGLIA_DEFAULT]
    assert eva_eff(ent) == 40 * coeff
    # Un enchant +evasione entra in pct_evasione (solo schivata), non in Des: alza solo eva.
    assert eva_eff(ent, pct_evasione=1.0) == 40 * coeff * 2


def test_acc_eff_blend_des_int(mondo_isolato: str) -> None:
    # acc_eff = (w·Des + (1−w)·Int) × coeff_acc; default fisico (Des domina) e arma naturale.
    ent = esper.create_entity(Primarie(valori={StatId.DESTREZZA: 10, StatId.INTELLIGENZA: 20}))
    base = cal.W_FISICO * 10 + (1 - cal.W_FISICO) * 20
    assert acc_eff(ent) == base * cal.COEFF_ACC[cal.ARMA_DEFAULT]
    # Ribaltando il peso a magia, Int domina: la formula è UNA sola (mai 0/1).
    assert acc_eff(ent, w=cal.W_MAGIA) == (cal.W_MAGIA * 10 + (1 - cal.W_MAGIA) * 20) * cal.COEFF_ACC[cal.ARMA_DEFAULT]
