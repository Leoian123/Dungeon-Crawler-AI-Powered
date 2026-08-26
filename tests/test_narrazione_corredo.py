"""`istanzia_entita` lega la geometria (Corredo) e le resistenze dell'archetipo DOPO il gate
(il motore conia i numeri, l'AI dichiara solo nomi). `fonte` = tag di dominio stabile, mai
un id esper. Le resistenze nulle non attaccano nulla (identità DT-6). Contesto isolato.
"""

from __future__ import annotations

import esper

import dataclasses

from contracts import EntitaGenerata, Grado, TipoDanno
from motore import narrazione
from motore.calibrazione import profilo_corrente
from motore.combattimento import mult_resistenza
from motore.corredo import Corredo
from motore.modificatori import Resistenze


def _slime() -> EntitaGenerata:
    return EntitaGenerata(
        archetipo="slime", grado=Grado.BRONZO, blocchi=[],
        nome="Slime di prova", descrizione="verde",
    )


def test_istanzia_attacca_il_corredo(mondo_isolato) -> None:
    ent = narrazione.istanzia_entita(_slime(), livello=1)
    corredo = esper.component_for_entity(ent, Corredo)
    p = profilo_corrente("slime")
    assert (corredo.armatura, corredo.taglia, corredo.arma) == (p.armatura, p.taglia, p.arma)


def test_profilo_neutro_non_attacca_resistenze(mondo_isolato) -> None:
    ent = narrazione.istanzia_entita(_slime(), livello=1)  # default: tutte le res a 0
    assert esper.try_component(ent, Resistenze) is None


def test_resistenze_dal_profilo_con_fonte_stabile(monkeypatch, mondo_isolato) -> None:
    # Il profilo arriva dal registry della run (D1): si inietta un registry con lo
    # slime resistente al fuoco — la strada dei dati, non un hook per-archetipo.
    resistente = dataclasses.replace(
        profilo_corrente("slime"), resistenze={TipoDanno.FUOCO: -50.0},
    )
    monkeypatch.setattr(
        narrazione, "registry_archetipi_correnti", lambda: {"slime": resistente},
    )
    ent = narrazione.istanzia_entita(_slime(), livello=1)
    res = esper.component_for_entity(ent, Resistenze)
    assert [(v.contro, v.valore, v.fonte) for v in res.voci] == [(TipoDanno.FUOCO, -50.0, "archetipo:slime")]
    assert mult_resistenza(ent, TipoDanno.FUOCO) == 0.5   # -50% → mult 0.5
    assert mult_resistenza(ent, TipoDanno.VELENO) == 1.0  # non toccato = identità


def test_corredo_e_resistenze_sono_persistenti() -> None:
    """Rovesciato in Fase 0 (mob componibili): il profilo del mob rivelato round-trippa
    nel save — prima si perdeva e l'ingaggio post-load degradava allo scalare di
    fallback (cfr. test_persistenza_mob.py). Gli EFFIMERI di combattimento restano fuori."""
    from motore.combattimento import Combattente, Nemico, PuntiVita
    from motore.persistenza.tag import e_persistente

    assert e_persistente(Corredo)
    assert e_persistente(Resistenze)
    for effimero in (Nemico, Combattente, PuntiVita):
        assert not e_persistente(effimero)
