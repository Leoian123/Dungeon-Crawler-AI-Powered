"""Fase 0 — il mob di scena rivelato ROUND-TRIPPA nel save (H-4 via dato, mai id).

Prima del fix `EntitaMob`/`Corredo`/`Resistenze` erano fuori dal registry dei tag:
al load la stanza perdeva il SUO mob (riferimento stale auto-pulito) e l'ingaggio
degradava allo scalare di fallback `SpecNemico(5, 3)`. Ora: i componenti del mob
sono persistenti, la stanza è stampata su `EntitaMob.stanza` alla registrazione, e
`mappa_da_dict` ricollega `mob_stanza` dai dati appena ricreati.
"""

from __future__ import annotations

import random

import esper

from contracts import Blocco, EntitaGenerata, Grado, TipoDanno
from motore import (
    Veleno,
    applica_stato,
    carica_da_disco,
    crea_mappa,
    istanzia_entita,
    mappa_corrente,
    mappa_to_dict,
    max_hp,
    mob_corrente,
    registra_mob,
    salva_run,
    segna_visitata,
)
from motore.corredo import Corredo
from motore.mob import EntitaMob
from motore.modificatori import ResistenzaMod, Resistenze, applica_resistenza
from motore.statistiche import Primarie
from tests.persist_helpers import costruisci_run


def _rivela_mob() -> int:
    """Materializza un mob nella stanza corrente e lo registra (il reveal)."""
    eg = EntitaGenerata(
        archetipo="slime",
        grado=Grado.BRONZO,
        blocchi=[Blocco.VELENO],
        nome="Slime Verde",
        descrizione="Gelatina paziente.",
    )
    ent = istanzia_entita(eg, livello=1)
    registra_mob(ent)
    segna_visitata()
    return ent


def test_mob_di_stanza_roundtrippa(mondo_isolato: str, tmp_path) -> None:
    costruisci_run(id_dominio="carl")
    crea_mappa(random.Random(7), n_stanze=4)
    ent = _rivela_mob()
    # Una resistenza tipata esplicita: il round-trip deve reggere list[dataclass]+enum.
    applica_resistenza(ent, ResistenzaMod(contro=TipoDanno.FUOCO, valore=-50.0, fonte="test"))
    hp_atteso = max_hp(ent)
    primarie_attese = dict(esper.component_for_entity(ent, Primarie).valori)

    salva_run(tmp_path, model_id="m", timestamp=1.0, esplorazione=mappa_to_dict())
    esper.clear_database()
    applica_stato(carica_da_disco(tmp_path, "carl"))

    # La stanza ritrova IL suo mob (niente sosia, niente fallback scalare).
    ent2 = mob_corrente()
    assert ent2 is not None
    em = esper.component_for_entity(ent2, EntitaMob)
    assert em.nome == "Slime Verde" and em.archetipo == "slime"
    assert em.stanza == mappa_corrente()[1].stanza_corrente
    # Il profilo calibrato sopravvive intero: primarie, gear, resistenze, innato.
    assert esper.component_for_entity(ent2, Primarie).valori == primarie_attese
    corredo = esper.component_for_entity(ent2, Corredo)
    assert (corredo.armatura, corredo.taglia, corredo.arma) == ("veste", "media", "naturale")
    res = esper.component_for_entity(ent2, Resistenze)
    assert [(v.contro, v.valore) for v in res.voci] == [(TipoDanno.FUOCO, -50.0)]
    vel = esper.component_for_entity(ent2, Veleno)
    assert vel.innato is True and vel.rango == 1
    # L'ingaggio post-load parte da QUESTO profilo (max_hp identico, non 3 HP scalari).
    assert max_hp(ent2) == hp_atteso


def test_mob_non_registrato_resta_fuori_dalla_mappa(mondo_isolato: str, tmp_path) -> None:
    """Un'entità-mob mai registrata in stanza (stanza=None) round-trippa come entità
    ma non entra in `mob_stanza`: il re-link è guidato SOLO dal dato stampato."""
    costruisci_run(id_dominio="carl")
    crea_mappa(random.Random(7), n_stanze=4)
    eg = EntitaGenerata(
        archetipo="goblin", grado=Grado.BRONZO, blocchi=[],
        nome="Orfano", descrizione="",
    )
    istanzia_entita(eg, livello=1)  # niente registra_mob
    segna_visitata()

    salva_run(tmp_path, model_id="m", timestamp=1.0, esplorazione=mappa_to_dict())
    esper.clear_database()
    applica_stato(carica_da_disco(tmp_path, "carl"))

    assert mob_corrente() is None
    assert len(esper.get_component(EntitaMob)) == 1  # l'entità c'è, la mappa non la lega


def test_save_legacy_senza_mob(mondo_isolato: str, tmp_path) -> None:
    """Un save senza mob di scena (il mondo di ieri) carica pulito: mappa vuota di
    nemici, nessun crash, `mob_corrente()` è None (H-12: degrado, non crash)."""
    costruisci_run(id_dominio="carl")
    crea_mappa(random.Random(7), n_stanze=4)
    segna_visitata()

    salva_run(tmp_path, model_id="m", timestamp=1.0, esplorazione=mappa_to_dict())
    esper.clear_database()
    applica_stato(carica_da_disco(tmp_path, "carl"))

    assert mappa_corrente() is not None
    assert mob_corrente() is None
