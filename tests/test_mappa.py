"""La Mappa come autorità spaziale: topologia seeded completabile (G-18), movimento a
intenti (il motore dispone), scena→opzioni composta dalla mappa (Scendi SOLO con la
scala), arruolamento del mob della stanza in combattimento (il nemico combattuto È il
reveal), persistenza nello slot `esplorazione`. Contesti esper isolati (ESP §0.1).
"""

from __future__ import annotations

import asyncio
import random

import esper

from contracts import (
    DiscesaPiano,
    PlayerChoseOption,
    TipoAzione,
)
from motore import (
    Combattente,
    PuntiVita,
    componi_opzioni_scena,
    crea_mappa,
    genera_topologia,
    livello_corrente,
    mappa_corrente,
    mappa_da_dict,
    mappa_to_dict,
    mob_corrente,
    muovi,
    piano_completabile,
    registra_mob,
    scala_presente,
    segna_visitata,
    stanza_visitata,
)
from motore.corredo import Corredo
from motore.statistiche import Primarie
from main import costruisci_sessione


# --- Generazione: seeded, completabile ----------------------------------------

def test_topologia_seeded_e_completabile() -> None:
    p1 = genera_topologia(random.Random(7))
    p2 = genera_topologia(random.Random(7))
    assert p1.adiacenze == p2.adiacenze and p1.discese == p2.discese  # deterministica
    assert piano_completabile(p1)  # G-18: scala raggiungibile
    assert genera_topologia(random.Random(9), 2).discese == {1}  # minimo: 2 stanze


# --- Movimento: adiacenza sì, teletrasporto no, ingaggio blocca ----------------

def test_muovi_solo_su_adiacenza(mondo_isolato) -> None:
    crea_mappa(random.Random(0), 5)
    _e, m = mappa_corrente()
    assert m.stanza_corrente == 0
    assert muovi(1) is True and m.stanza_corrente == 1
    lontane = [s for s in range(5) if s not in m.piano.adiacenze[1] and s != 1]
    if lontane:
        assert muovi(lontane[0]) is False  # niente teletrasporto
    assert m.stanza_corrente == 1


def test_mob_vivo_blocca_il_movimento(mondo_isolato) -> None:
    crea_mappa(random.Random(0), 4)
    segna_visitata()
    mob = esper.create_entity(Primarie(valori={}))
    registra_mob(mob)
    assert muovi(1) is False  # l'ingaggio blocca: serve SCAPPA/COMBATTI
    esper.delete_entity(mob, immediate=True)
    assert mob_corrente() is None  # auto-pulizia del riferimento stale
    assert muovi(1) is True


# --- Scena → opzioni: la mappa dispone -----------------------------------------

def test_scena_con_mob_solo_combatti_scappi(mondo_isolato) -> None:
    crea_mappa(random.Random(0), 4)
    segna_visitata()
    registra_mob(esper.create_entity(Primarie(valori={})))
    tipi = [o.tipo for o in componi_opzioni_scena()]
    assert tipi == [TipoAzione.COMBATTI, TipoAzione.SCAPPA]


def test_scendi_solo_con_la_scala(mondo_isolato) -> None:
    crea_mappa(random.Random(0), 4)
    _e, m = mappa_corrente()
    segna_visitata()
    assert not scala_presente()
    assert TipoAzione.SCENDI not in [o.tipo for o in componi_opzioni_scena()]
    m.stanza_corrente = next(iter(m.piano.discese))  # sulla scala
    m.visitate.add(m.stanza_corrente)
    opzioni = componi_opzioni_scena()
    assert opzioni[0].tipo is TipoAzione.SCENDI  # la scala rende visibile Scendi
    assert all(o.stanza is not None for o in opzioni if o.tipo is TipoAzione.MUOVI)


def test_stanza_non_visitata_scena_vuota(mondo_isolato) -> None:
    crea_mappa(random.Random(0), 4)
    assert not stanza_visitata()
    assert componi_opzioni_scena() == ()  # l'host deve chiedere un turno di narrazione


# --- Persistenza: slot esplorazione --------------------------------------------

def test_mappa_roundtrip_dict(mondo_isolato) -> None:
    crea_mappa(random.Random(3), 5)
    _e, m = mappa_corrente()
    m.stanza_corrente = 2
    m.visitate |= {0, 1, 2}
    registra_mob(esper.create_entity(Primarie(valori={})))  # runtime: NON deve salvarsi
    dati = mappa_to_dict()
    esper.delete_entity(_e, immediate=True)
    mappa_da_dict(dati)
    _e2, ripresa = mappa_corrente()
    assert ripresa.stanza_corrente == 2 and ripresa.visitate == {0, 1, 2}
    assert ripresa.piano.adiacenze == m.piano.adiacenze
    assert ripresa.mob_stanza == {}  # i mob effimeri non tornano: la stanza si ripopola


# --- Il giro completo dalla porta: mappa + arruolamento + vittoria --------------

def test_sessione_arruola_il_mob_della_stanza(run_pulita) -> None:
    sessione = costruisci_sessione(seed=1)
    asyncio.run(sessione.prossima_narrazione())
    mob = mob_corrente()
    assert mob is not None and esper.has_component(mob, Corredo)  # profilo calibrato
    sessione.coda.accoda(PlayerChoseOption(0))  # "Combatti"
    snap = sessione.avanza()
    assert snap.fase == "combattimento"
    # Il nemico arruolato È l'entità della stanza: componenti effimeri sopra il reveal.
    assert esper.has_component(mob, PuntiVita)
    assert esper.has_component(mob, Combattente)


def _stagione_leggera():
    """Due piani di sole comparse bronzo: il test verifica il CABLAGGIO del ciclo
    (esplora → combatti → scala → Scendi), non la taratura del contenuto ufficiale.
    Col copione keyed il mob appartiene alla STANZA (D5), quindi la rotta del bot
    incontra il cast reale del piano: legare questo test alla Falsa Idra lo
    trasformerebbe in un test di bilanciamento."""
    from contracts import BudgetDesign, Grado, MobAsset, PianoRisolto, StagioneRisolta
    from main import risolvi_stagione

    def _piano(n: int) -> PianoRisolto:
        cast = [
            MobAsset(slug=f"comparsa-{n}-{i}", nome=f"Comparsa {n}.{i}",
                     archetipo="slime", grado=Grado.BRONZO,
                     prosa_stanza=f"La stanza {i} del piano {n} borbotta di slime.")
            for i in range(3)
        ]
        return PianoRisolto(
            slug=f"leggero-{n}", versione=1, titolo=f"Leggero {n}", tema="cablaggio",
            budget=BudgetDesign(gradi=[Grado.BRONZO], blocchi=[], archetipi=["slime"]),
            cast=cast,
        )

    ufficiale = risolvi_stagione("stagione-1")
    return StagioneRisolta(
        slug="s-cablaggio", versione=1, numero=1, titolo="Cablaggio", mondo="X",
        piani=[_piano(1), _piano(2)], archetipi=list(ufficiale.archetipi),
    )


def test_sessione_vince_esplorando_fino_alla_scala(run_pulita) -> None:
    """Il ciclo che prima era irraggiungibile: esplora → combatti → muovi → scala →
    Scendi → DiscesaPiano (vittoria MVP), tutto dalle porte, via la scena."""
    sessione = costruisci_sessione(seed=1, stagione=_stagione_leggera())
    eventi: list[DiscesaPiano] = []
    sessione.bus.registra(DiscesaPiano, eventi.append)
    try:
        snap = asyncio.run(sessione.prossima_narrazione())
        for _ in range(80):  # guardia globale
            if eventi:
                break
            etichette = [o.etichetta for o in snap.opzioni]
            if not snap.opzioni:  # stanza nuova: serve un turno di narrazione
                snap = asyncio.run(sessione.prossima_narrazione())
                continue
            if snap.fase == "combattimento":
                sessione.coda.accoda(PlayerChoseOption(0))  # Attacca
            elif "Scendi la scala" in etichette:
                sessione.coda.accoda(PlayerChoseOption(etichette.index("Scendi la scala")))
            elif "Combatti" in etichette:
                sessione.coda.accoda(PlayerChoseOption(etichette.index("Combatti")))
            else:  # solo movimento: vai verso la stanza col numero più alto (la scala è in fondo)
                idx = max(
                    range(len(snap.opzioni)),
                    key=lambda i: sessione._scena[i].stanza or -1,
                )
                sessione.coda.accoda(PlayerChoseOption(idx))
            snap = sessione.avanza()
        assert eventi and eventi[0].piano == 2  # la discesa è avvenuta
        # ⚠️ Scendere NON è più vincere: con una stagione a più piani il terminale
        # scatta solo uscendo dall'ULTIMO. Qui si è arrivati al piano 2 di 2, quindi
        # la run CONTINUA — ed è il punto: prima questo ramo era irraggiungibile.
        assert sessione.guscio.terminale is None, (
            "la run si è chiusa alla prima discesa: il secondo piano è tornato "
            "irraggiungibile"
        )
        assert livello_corrente() == 2
    finally:
        sessione.bus.deregistra(DiscesaPiano, eventi.append)
