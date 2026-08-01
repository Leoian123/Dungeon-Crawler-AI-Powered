"""`istanzia_entita` lega la geometria (Corredo) e le resistenze dell'archetipo DOPO il gate
(il motore conia i numeri, l'AI dichiara solo nomi). `fonte` = tag di dominio stabile, mai
un id esper. Le resistenze nulle non attaccano nulla (identità DT-6). Contesto isolato.
"""

from __future__ import annotations

import esper

from contracts import Archetipo, EntitaGenerata, Grado, TipoDanno
from motore import narrazione
from motore.combattimento import mult_resistenza
from motore.corredo import Corredo
from motore.modificatori import Resistenze


def _slime() -> EntitaGenerata:
    return EntitaGenerata(
        archetipo=Archetipo.SLIME, grado=Grado.BRONZO, blocchi=[],
        nome="Slime di prova", descrizione="verde",
    )


def test_istanzia_attacca_il_corredo(mondo_isolato) -> None:
    ent = narrazione.istanzia_entita(_slime(), livello=1)
    corredo = esper.component_for_entity(ent, Corredo)
    assert (corredo.armatura, corredo.taglia, corredo.arma) == narrazione.geometria_da_archetipo(Archetipo.SLIME)


def test_profilo_neutro_non_attacca_resistenze(mondo_isolato) -> None:
    ent = narrazione.istanzia_entita(_slime(), livello=1)  # default: tutte le res a 0
    assert esper.try_component(ent, Resistenze) is None


def test_resistenze_dal_profilo_con_fonte_stabile(monkeypatch, mondo_isolato) -> None:
    monkeypatch.setattr(
        narrazione, "resistenze_da_archetipo",
        lambda a: {TipoDanno.FUOCO: -50.0},
    )
    ent = narrazione.istanzia_entita(_slime(), livello=1)
    res = esper.component_for_entity(ent, Resistenze)
    assert [(v.contro, v.valore, v.fonte) for v in res.voci] == [(TipoDanno.FUOCO, -50.0, "archetipo:slime")]
    assert mult_resistenza(ent, TipoDanno.FUOCO) == 0.5   # -50% → mult 0.5
    assert mult_resistenza(ent, TipoDanno.VELENO) == 1.0  # non toccato = identità


def test_corredo_e_resistenze_non_sono_persistenti() -> None:
    from motore.persistenza.tag import e_persistente
    assert not e_persistente(Corredo)
    assert not e_persistente(Resistenze)
