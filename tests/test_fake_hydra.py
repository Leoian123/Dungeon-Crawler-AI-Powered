"""Il giro del copione keyed — contenuto scriptato SOLO offline (FakeProvider).

Una stanza per turno del copione, in ordine di visita, e ogni stanza RECLUTA un
mob diverso (archetipo × grado × blocchi → profilo calibrato dal motore,
registrato sulla mappa): è il banco di prova dell'arruolamento per-stanza. Il GM
live NON è toccato: il copione vive nel FakeProvider di `costruisci_sessione`, e
la topologia si adatta al copione solo offline.

Il cast è SINTETICO e variegato (perimetro: forma, non contenuto — 2026-08-10):
il test prova il MECCANISMO del reclutamento, non il cast di una stagione vera.
Le lunghezze sono derivate dal cast, mai cablate.
"""

from __future__ import annotations

import asyncio

import esper

from contracts import Blocco, Grado, PlayerChoseOption
from main import costruisci_sessione, turni_da_piano
from motore import Combattente, EntitaMob, dissolvi_mob, mappa_corrente, max_hp, mob_corrente
from tests.contenuti_sintetici import mob_sintetico, piano_sintetico, stagione_sintetica


def _stagione_variegata():
    """Un piano di cast tutto diverso: archetipi, gradi e blocchi mai ripetuti in
    coppia — le assert di distinzione provano che ogni stanza monta IL SUO mob."""
    cast = [
        mob_sintetico("testa-slime-b", archetipo="slime", grado=Grado.BRONZO),
        mob_sintetico("testa-goblin-b", archetipo="goblin", grado=Grado.BRONZO),
        mob_sintetico("testa-ossa-b", archetipo="scheletro", grado=Grado.BRONZO),
        mob_sintetico("testa-velenosa", archetipo="slime", grado=Grado.BRONZO,
                      blocchi=(Blocco.VELENO,)),
        mob_sintetico("testa-goblin-a", archetipo="goblin", grado=Grado.ARGENTO),
        mob_sintetico("testa-slime-a", archetipo="slime", grado=Grado.ARGENTO),
    ]
    return stagione_sintetica(piani=[piano_sintetico(1, cast=cast)], slug="s-teste")


def test_offline_una_stanza_per_turno_del_copione(run_pulita) -> None:
    stagione = _stagione_variegata()
    sessione = costruisci_sessione(seed=1, stagione=stagione)
    asyncio.run(sessione.prossima_narrazione())
    trovata = mappa_corrente()
    assert trovata is not None
    _ent, mappa = trovata
    assert len(mappa.piano.adiacenze) == len(turni_da_piano(stagione.piani[0]))
    assert sessione is not None


def test_il_copione_ha_teste_tutte_diverse() -> None:
    stagione = _stagione_variegata()
    turni = turni_da_piano(stagione.piani[0])
    nomi = [t.entita.nome for t in turni]
    assert len(set(nomi)) == len(turni)  # ogni stanza ha roba diversa
    profili = {(t.entita.archetipo, t.entita.grado, tuple(t.entita.blocchi)) for t in turni}
    assert len(profili) == len(turni)  # anche i profili meccanici sono tutti distinti
    assert all(t.entita.grado in {Grado.BRONZO, Grado.ARGENTO} for t in turni)


def test_giro_completo_recluta_un_mob_diverso_per_stanza(run_pulita) -> None:
    """Cammina il piano via porte: ogni stanza narrata registra IL SUO mob
    (EntitaMob dal copione, profilo calibrato); nella prima lo scontro ARRUOLA
    l'entità della stanza (mai il fallback). Le altre si attraversano
    dissolvendo il mob (harness): il giro resta un test di reclutamento."""
    stagione = _stagione_variegata()
    attesi = [
        (t.entita.nome, t.entita.archetipo, t.entita.grado)
        for t in turni_da_piano(stagione.piani[0])
    ]
    sessione = costruisci_sessione(seed=1, stagione=stagione)
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
            sessione.coda.accoda(PlayerChoseOption(next(v for k, v in etichette.items() if k.startswith("Combatti"))))
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
    assert hp_massimi["Testa Slime A"] > hp_massimi["Testa Slime B"]
