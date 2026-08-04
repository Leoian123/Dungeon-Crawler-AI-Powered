"""I valori per-entità che PRIMA mancavano — Intelligenza/Difesa/Saggezza/Fortuna base
(non popolate per i nemici), la geometria (default globali inerti) e le resistenze (nessuna
tabella) — ora sono DATO: passandoli, il componente/entità li riflette e le derivate cambiano.

Si costruisce l'entità dal profilo **fresco** (`profilo_corrente`, override in memoria), non da
`REGISTRY_ARCHETIPI` (cache-ato all'import). Contesto esper isolato (ESP §0.1).
"""

from __future__ import annotations

import esper

from contracts import Grado, StatId, TipoDanno
from motore import calibrazione as cal
from motore.catalogo import rango_grado
from motore.combattimento import mult_resistenza
from motore.corredo import Corredo
from motore.derivate import def_eff, eva_eff
from motore.modificatori import ResistenzaMod, Resistenze
from motore.statistiche import Primarie


def _entita_slime(profilo, *, grado=Grado.BRONZO, livello=1) -> int:
    """Materializza uno Slime dal profilo dato, con Corredo (come `istanzia_entita`)."""
    primarie = cal.primarie_da_archetipo("slime", grado, livello, profilo=profilo)
    return esper.create_entity(
        Primarie(valori=dict(primarie)),
        Corredo(armatura=profilo.armatura, taglia=profilo.taglia, arma=profilo.arma),
    )


def test_stat_base_mancanti_entrano_nel_vettore(cal_pulita) -> None:
    cal.imposta("ARCH.slime.intelligenza_base", 9)
    cal.imposta("ARCH.slime.difesa_base", 40)
    cal.imposta("ARCH.slime.saggezza_base", 7)
    cal.imposta("ARCH.slime.fortuna_base", 3)
    profilo = cal.profilo_corrente("slime")
    rango = rango_grado(Grado.BRONZO)  # 1
    pr = cal.primarie_da_archetipo("slime", Grado.BRONZO, 1, profilo=profilo)
    assert pr[StatId.INTELLIGENZA] == 9 + rango  # prima era un proxy destrezza//2
    assert pr[StatId.DIFESA] == 40               # flat, non scala col grado
    assert pr[StatId.SAGGEZZA] == 7 + rango
    assert pr[StatId.FORTUNA] == 3 + rango


def test_difesa_base_mancante_ora_muove_def_eff(cal_pulita, mondo_isolato) -> None:
    d0 = def_eff(_entita_slime(cal.profilo_corrente("slime")))  # difesa_base default 0
    cal.imposta("ARCH.slime.difesa_base", 40)
    d1 = def_eff(_entita_slime(cal.profilo_corrente("slime")))
    assert d1 == d0 + 40  # la Difesa (centesimi) si somma alla mitigazione, prima inerte


def test_geometria_mancante_passata_muove_l_evasione(cal_pulita, mondo_isolato) -> None:
    e0 = eva_eff(_entita_slime(cal.profilo_corrente("slime")))  # taglia media (default)
    cal.imposta("ARCH.slime.taglia", "infima")
    e1 = eva_eff(_entita_slime(cal.profilo_corrente("slime")))
    assert e1 > e0  # taglia più piccola → schiva di più (seam gear per-entità)


def test_resistenza_mancante_passata_muta_il_mult(cal_pulita, mondo_isolato) -> None:
    cal.imposta("ARCH.slime.res.fuoco", -50)
    # `resistenze_da_archetipo` legge REGISTRY (import-time): per l'anteprima/override in
    # memoria si passa il profilo fresco (`profilo_corrente`), come fa la UI.
    res = {t: v for t, v in cal.profilo_corrente("slime").resistenze.items() if v != 0}
    assert res == {TipoDanno.FUOCO: -50.0}
    ent = esper.create_entity(
        Primarie(valori={StatId.COSTITUZIONE: 6}),
        Resistenze(voci=[ResistenzaMod(contro=t, valore=v, fonte="test") for t, v in res.items()]),
    )
    assert mult_resistenza(ent, TipoDanno.FUOCO) == 0.5   # -50% → mult 0.5
    assert mult_resistenza(ent, TipoDanno.VELENO) == 1.0  # non passato = identità
