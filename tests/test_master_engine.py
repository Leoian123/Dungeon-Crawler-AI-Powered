"""Master-Engine (`motore/master/`): registro delle rotte, dispatcher con guardia
di fase, corsie, retry per rotta e tally — il canale unico delle chiamate AI.

I provider restano INIETTATI (FakeProvider): l'engine non costruisce prompt, non
valida, non sceglie fallback — trasporta secondo la dichiarazione della rotta.
"""

from __future__ import annotations

import asyncio

import pytest

from contracts import Flavor, Ideazione, TurnoNarrazione
from motore import (
    Fase,
    MasterEngine,
    ROTTE,
    Rotta,
    avvia_run,
    crea_seme,
    imposta_fase,
    registra_rotta,
)
from motore.master import Corsia
from motore.narrazione import POLICY_RETRY
from provider import FakeProvider
from tests.narr_helpers import IDEA_QUIETE


def _arma_fase(fase: Fase = Fase.NARRAZIONE) -> None:
    crea_seme(7)
    avvia_run(crea_singleton_fase=True, fase_iniziale=fase)


# --- Registro -------------------------------------------------------------------

def test_rotte_gm_registrate() -> None:
    attese = {"gm.ideazione", "gm.gating", "gm.prova", "gm.limatura", "gm.distilla"}
    assert attese <= set(ROTTE)
    assert ROTTE["gm.gating"].gating is True
    assert ROTTE["gm.gating"].corsia is Corsia.FORTE
    assert all(ROTTE[n].corsia is Corsia.VELOCE for n in attese - {"gm.gating"})
    assert all(ROTTE[n].fase is Fase.NARRAZIONE for n in attese)


def test_doppione_di_nome_e_un_errore() -> None:
    with pytest.raises(ValueError):
        registra_rotta(Rotta("gm.gating", Flavor, Corsia.VELOCE))


def test_sincronia_retry_rotta_gating() -> None:
    """Finché POLICY_RETRY (narrazione) e la rotta `gm.gating` coesistono, devono
    dichiarare LO STESSO retry: una divergenza silenziosa cambierebbe il budget
    di chiamate a seconda della via d'ingresso (review 2026-08-08)."""
    assert ROTTE["gm.gating"].retry == POLICY_RETRY[TurnoNarrazione]


# --- Dispatcher: corsie, retry, tally, guardia di fase --------------------------

def test_corsie_instradate(mondo_isolato) -> None:
    _arma_fase()
    forte, veloce = FakeProvider([]), FakeProvider([IDEA_QUIETE])
    engine = MasterEngine({Corsia.FORTE: forte, Corsia.VELOCE: veloce})
    idea = asyncio.run(engine.genera("gm.ideazione", "prompt"))
    assert isinstance(idea, Ideazione)
    assert veloce.schemi_ricevuti == [Ideazione] and forte.chiamate == []
    assert engine.provider_di(Corsia.FORTE) is forte


def test_retry_per_rotta_e_tally(mondo_isolato) -> None:
    _arma_fase()
    # gm.gating dichiara 1 retry: [None, valido] → 2 chiamate, 1 candidato.
    prov = FakeProvider([None, {"prosa": "x", "entita": {
        "archetipo": "slime", "grado": "bronzo", "blocchi": [],
        "nome": "n", "descrizione": "d"}, "durata": "turno"}])
    engine = MasterEngine.avvolgi(prov)
    cand = asyncio.run(engine.genera("gm.gating", "p"))
    assert isinstance(cand, TurnoNarrazione)
    assert len(prov.chiamate) == 2
    assert engine.tally["gm.gating"].chiamate == 2
    assert engine.tally["gm.gating"].degradi == 0

    # gm.limatura dichiara 0 retry: un None è un degrado secco.
    assert asyncio.run(engine.genera("gm.limatura", "p")) is None
    assert engine.tally["gm.limatura"].chiamate == 1
    assert engine.tally["gm.limatura"].degradi == 1


def test_guardia_di_fase_zero_chiamate(mondo_isolato) -> None:
    """Una rotta di NARRAZIONE invocata in COMBATTIMENTO è un errore STRUTTURALE:
    RuntimeError prima di qualunque chiamata al provider (G-4)."""
    _arma_fase(Fase.COMBATTIMENTO)
    prov = FakeProvider([IDEA_QUIETE])
    engine = MasterEngine.avvolgi(prov)
    with pytest.raises(RuntimeError):
        asyncio.run(engine.genera("gm.ideazione", "p"))
    assert prov.chiamate == []


def test_corsie_incomplete_rifiutate() -> None:
    with pytest.raises(ValueError):
        MasterEngine({Corsia.FORTE: FakeProvider([])})


def test_avvolgi_copre_tutte_le_corsie() -> None:
    prov = FakeProvider([])
    engine = MasterEngine.avvolgi(prov)
    assert all(engine.provider_di(c) is prov for c in Corsia)


# --- Rifinitura tipografica della prosa (playtest live 2026-08-27) --------------

def test_rifinisci_caporali_a_bilancio() -> None:
    """Il finding cinico: il modello apre col caporale e chiude con l'apice
    dritto. La regola a bilancio ripara chiusure e aperture mischiate; uno
    stile UNIFORME (solo apici, o nessun dialogo) resta intatto."""
    from motore.tipografia import rifinisci_caporali

    assert rifinisci_caporali('«Anche i morti hanno sete, ogni tanto."') == (
        "«Anche i morti hanno sete, ogni tanto.»"
    )
    assert rifinisci_caporali('Dice "così» e se ne va.') == "Dice «così» e se ne va."
    assert rifinisci_caporali("«Già a posto.» Poi tace.") == "«Già a posto.» Poi tace."
    # Stile uniforme senza caporali: non è un errore, nessun ritocco.
    assert rifinisci_caporali('Dice "ciao" e basta.') == 'Dice "ciao" e basta.'
    assert rifinisci_caporali("Nessun dialogo qui.") == "Nessun dialogo qui."
    assert rifinisci_caporali("") == ""
    # Anche gli apici curvi rientrano nel bilancio.
    assert rifinisci_caporali("«Vieni qui” disse.") == "«Vieni qui» disse."


def test_engine_rifinisce_la_prosa_del_candidato(mondo_isolato) -> None:
    """La rifinitura vive nel canale unico: OGNI rotta consegna prosa già
    rifinita — il chiamante non deve ricordarsene."""
    _arma_fase()
    prov = FakeProvider([{"prosa": '«Mezzogiorno."', "entita": {
        "archetipo": "slime", "grado": "bronzo", "blocchi": [],
        "nome": "n", "descrizione": "d"}, "durata": "turno"}])
    engine = MasterEngine.avvolgi(prov)
    cand = asyncio.run(engine.genera("gm.gating", "p"))
    assert cand is not None and cand.prosa == "«Mezzogiorno.»"
