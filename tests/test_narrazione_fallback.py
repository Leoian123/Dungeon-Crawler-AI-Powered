"""Fallback atomico, retry-per-schema, niente secondo giudice, niente save parziale
(F-8, F-9, F-11). Headless, provider fake.
"""

from __future__ import annotations

import asyncio

import esper

from contracts import (
    Archetipo,
    Blocco,
    Flavor,
    Grado,
    SchedaProiezione,
    StatId,
    TipoAzione,
    TurnoNarrazione,
)
from motore import (
    EntitaMob,
    MENU_FISSO,
    PROSA_NEUTRA,
    Primarie,
    RETRY_NARRAZIONE,
    RETRY_PROSA,
    atk_eff,
    fallback_turno,
    genera_prosa,
    materializza_turno,
    max_hp,
    procura_turno,
)
from provider import FakeProvider
from tests.narr_helpers import budget, turno

_PROIEZIONE = SchedaProiezione(descrittori=("integro",))


# --- F-8: fallback atomico; retry/timeout selezionati dallo schema -------------

def test_F8_none_trasporto_collassa_su_fallback() -> None:
    # Tutte le chiamate ritornano None (trasporto): dopo i retry → fallback atomico.
    prov = FakeProvider([None, None])
    res = asyncio.run(procura_turno(prov, budget(), _PROIEZIONE))
    assert res.fallback is True
    _verifica_fallback_atomico(res, budget())


def test_F8_rifiuto_di_gate_collassa_sullo_stesso_fallback() -> None:
    # Candidato che parsa ma è fuori budget (LEGGENDARIO non ammesso): rifiuto-di-gate.
    fuori = turno(grado=Grado.LEGGENDARIO, blocchi=())
    prov = FakeProvider([fuori, fuori])  # anche il retry resta fuori budget
    bud = budget()
    res = asyncio.run(procura_turno(prov, bud, _PROIEZIONE))
    assert res.fallback is True
    _verifica_fallback_atomico(res, bud)


def _verifica_fallback_atomico(res, bud) -> None:
    # Testo neutro + archetipo di default DESIGNATO nel budget + menu fisso, INSIEME.
    t: TurnoNarrazione = res.turno
    assert t.prosa == PROSA_NEUTRA
    assert t.entita.archetipo == bud.archetipo_default
    assert t.entita.grado in bud.gradi_ammessi
    assert [o.tipo for o in t.opzioni] == [o.tipo for o in MENU_FISSO]


def test_F8_archetipo_default_designato_deterministico() -> None:
    # "Designa", non "pesca": due fallback sullo stesso budget danno lo stesso esito
    # (nessun RNG → non consuma il seed stream, F-13).
    bud = budget()
    a = fallback_turno(bud)
    b = fallback_turno(bud)
    assert a.turno.entita.archetipo == b.turno.entita.archetipo
    assert a.turno.entita.grado == b.turno.entita.grado


def test_F8_narrazione_ritenta_prosa_fallisce_in_fretta() -> None:
    # Narrazione: 1 None poi un valido → ritenta e riesce (2 chiamate).
    prov = FakeProvider([None, turno()])
    res = asyncio.run(procura_turno(prov, budget(), _PROIEZIONE))
    assert res.fallback is False
    assert len(prov.chiamate) == RETRY_NARRAZIONE + 1 == 2

    # Modalità-prosa: fallisce in fretta (nessun retry) e PUÒ mancare (None).
    prov2 = FakeProvider([None])
    testo = asyncio.run(genera_prosa(prov2, "prompt flavor"))
    assert testo is None
    assert len(prov2.chiamate) == RETRY_PROSA + 1 == 1


# --- F-9: nessun secondo modello-giudice; l'anomalia è a monte, seeded ---------

def test_F9_nessun_secondo_modello_decide_stato() -> None:
    # Un fuori-budget va in fallback: il provider NON è interpellato una seconda volta
    # con uno schema-giudice. Solo lo schema di narrazione compare.
    fuori = turno(grado=Grado.LEGGENDARIO)
    prov = FakeProvider([fuori, fuori])
    res = asyncio.run(procura_turno(prov, budget(), _PROIEZIONE))
    assert res.fallback is True
    # Tutti gli schemi richiesti sono quelli di narrazione: nessun verbo/giudice extra.
    assert set(prov.schemi_ricevuti) == {TurnoNarrazione}
    # Il rifiuto-di-gate NON innesca un retry di trasporto (il candidato è arrivato):
    # una sola chiamata, poi il fallback. Nessun secondo giro di "giudizio".
    assert len(prov.chiamate) == 1


def test_F9_fuori_budget_resta_violazione_mai_anomalia() -> None:
    # Il motore non ha tirato l'anomalia (budget normale): un candidato fuori budget è
    # SEMPRE una violazione, mai "un'anomalia mancata" ripromossa a valle.
    fuori = turno(grado=Grado.LEGGENDARIO)
    prov = FakeProvider([fuori, fuori])
    bud = budget(anomala=False)
    res = asyncio.run(procura_turno(prov, bud, _PROIEZIONE))
    assert res.anomala is False  # non promossa ad anomalia
    assert res.fallback is True


# --- F-11: nessun turno parziale tocca il save --------------------------------

def test_F11_chiamata_fallita_non_scrive_nulla(mondo_isolato: str) -> None:
    # La coroutine NON muta l'ECS: con una chiamata fallita, nessuna entità nasce.
    assert esper.list_worlds  # sanity: contesto attivo
    entita_prima = list(esper.get_entities())
    prov = FakeProvider([None, None])  # trasporto fallito
    res = asyncio.run(procura_turno(prov, budget(), _PROIEZIONE))
    # Esito prodotto (fallback), ma lo stato del World è invariato finché non si risolve.
    assert res.fallback is True
    assert list(esper.get_entities()) == entita_prima
    assert esper.get_component(EntitaMob) == []


def test_F11_materializzazione_e_passo_separato(mondo_isolato: str) -> None:
    # Lo stato muta SOLO alla risoluzione: è `materializza_turno` a scrivere, non la
    # coroutine. Prima di chiamarlo, nessuna entità; dopo, l'entità esiste.
    prov = FakeProvider([turno()])
    res = asyncio.run(procura_turno(prov, budget(), _PROIEZIONE))
    assert esper.get_component(EntitaMob) == []  # ancora niente
    ent = materializza_turno(res)
    assert esper.has_component(ent, EntitaMob)


def test_mob_porta_primarie_una_sola_strada_stat(mondo_isolato: str) -> None:
    # §16.4: il mob di narrazione usa il vettore `Primarie` come tutto il resto (niente più
    # `Statistiche`, modello morto rimosso). Le stat si derivano via `stat_eff`/derivate.
    prov = FakeProvider([turno()])
    res = asyncio.run(procura_turno(prov, budget(), _PROIEZIONE))
    ent = materializza_turno(res)

    primarie = esper.component_for_entity(ent, Primarie)
    assert isinstance(primarie, Primarie)
    # FORZA/DESTREZZA/COSTITUZIONE/INTELLIGENZA presenti (formula-madre dall'archetipo).
    assert {StatId.FORZA, StatId.DESTREZZA, StatId.COSTITUZIONE, StatId.INTELLIGENZA} <= set(primarie.valori)
    # Le derivate del combattimento leggono `stat_eff` sul mob, come per chiunque altro.
    assert max_hp(ent) >= 1 and atk_eff(ent) >= 1
