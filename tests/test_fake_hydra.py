"""Il giro della Falsa Idra — contenuto scriptato SOLO offline (FakeProvider).

Una stanza per turno del copione, in ordine di visita, e ogni stanza RECLUTA un mob
diverso (archetipo × grado × blocchi → profilo calibrato dal motore, registrato sulla
mappa): è il banco di prova dell'arruolamento per-stanza. Il GM live NON è toccato: il
copione vive nel FakeProvider di `costruisci_sessione`, e la topologia si adatta al
copione solo offline.

⚠️ Le lunghezze qui sono **derivate dal cast**, mai cablate: il cast del piano è
contenuto, e cresce. Un numero scritto a mano trasformerebbe "aggiungere una testa"
in "rompere cinque test", che è il modo migliore per non aggiungerla più.
"""

from __future__ import annotations

import asyncio

import esper

from main import _turni_scriptati, costruisci_sessione
from contracts import Grado, PlayerChoseOption
from motore import Combattente, EntitaMob, dissolvi_mob, mappa_corrente, max_hp, mob_corrente


def test_offline_una_stanza_per_turno_del_copione(run_pulita) -> None:
    sessione = costruisci_sessione(seed=1)
    asyncio.run(sessione.prossima_narrazione())
    trovata = mappa_corrente()
    assert trovata is not None
    _ent, mappa = trovata
    assert len(mappa.piano.adiacenze) == len(_turni_scriptati()) >= 8


def test_il_copione_ha_teste_tutte_diverse() -> None:
    turni = _turni_scriptati()
    assert len(turni) >= 8, "il piano 1 non può impoverirsi sotto il cast storico"
    nomi = [t.entita.nome for t in turni]
    assert len(set(nomi)) == len(turni)  # ogni stanza ha roba diversa
    profili = {(t.entita.archetipo, t.entita.grado, tuple(t.entita.blocchi)) for t in turni}
    assert len(profili) == len(turni)  # anche i profili meccanici sono tutti distinti
    # La truffa è dichiarata: nessuna testa supera l'ARGENTO (il "gold" è vernice).
    assert all(t.entita.grado in {Grado.BRONZO, Grado.ARGENTO} for t in turni)


def test_giro_completo_recluta_un_mob_diverso_per_stanza(run_pulita) -> None:
    """Cammina il piano 0→7 via porte: ogni stanza narrata registra IL SUO mob
    (EntitaMob dal copione, profilo calibrato); nella prima lo scontro ARRUOLA
    l'entità della stanza (mai il fallback). Le altre si attraversano
    dissolvendo il mob (harness): il giro resta un test di reclutamento."""
    attesi = [
        (t.entita.nome, t.entita.archetipo, t.entita.grado) for t in _turni_scriptati()
    ]
    sessione = costruisci_sessione(seed=1)
    visti: list[tuple] = []
    hp_massimi: dict[str, int] = {}
    ultima = len(attesi) - 1

    snap = asyncio.run(sessione.prossima_narrazione())
    for stanza in range(len(attesi)):
        mob = mob_corrente()
        assert mob is not None, f"stanza {stanza}: nessun mob reclutato"
        entita_mob = esper.component_for_entity(mob, EntitaMob)
        visti.append((entita_mob.nome, entita_mob.archetipo, entita_mob.grado))
        hp_massimi[entita_mob.nome] = max_hp(mob)

        if stanza == 0:
            # Lo scontro arruola l'entità DELLA STANZA col suo profilo.
            etichette = {o.etichetta: o.indice for o in snap.opzioni}
            sessione.coda.accoda(PlayerChoseOption(etichette["Combatti"]))
            snap = sessione.avanza()
            assert snap.fase == "combattimento"
            assert esper.has_component(mob, Combattente)  # arruolato, non fallback
            guardia = 0
            while snap.fase == "combattimento" and guardia < 100:
                sessione.coda.accoda(PlayerChoseOption(0))  # Attacca
                snap = sessione.avanza()
                guardia += 1
            assert snap.fase == "narrazione"
        else:
            dissolvi_mob()  # harness: il giro prosegue senza combattere ogni testa
            snap = sessione.avanza()  # a vuoto: niente tick, la scena si ricompone

        if stanza < ultima:
            etichette = {o.etichetta: o.indice for o in snap.opzioni}
            destinazione = f"Vai: stanza {stanza + 1}"
            assert destinazione in etichette, f"stanza {stanza}: {sorted(etichette)}"
            sessione.coda.accoda(PlayerChoseOption(etichette[destinazione]))
            snap = sessione.avanza()
            if not snap.opzioni:  # stanza nuova: serve il turno di narrazione
                snap = asyncio.run(sessione.prossima_narrazione())

    assert visti == attesi  # una stanza per testa, nell'ordine del copione
    # Profilo CALIBRATO, non flavor: a pari archetipo un ARGENTO regge più HP
    # di un BRONZO (la calibrazione deriva i numeri da archetipo × grado).
    assert hp_massimi["Slime Madre"] > hp_massimi["Slime Mangiascarti"]
