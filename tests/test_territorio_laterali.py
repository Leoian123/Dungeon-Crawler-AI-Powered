"""Territorio F6: le zone LATERALI lazy — deviazioni seeded dalla partenza,
vicolo senza avanzamento di spina, ritorno libero, telecronaca nel fascicolo.
"""

from __future__ import annotations

from contracts import BusEventi, TransizioneZona
from motore import (
    attraversa,
    avvia_territorio,
    boss_della_zona,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_stagione,
    crea_tempo_piano,
    deviazione_consentita,
    e_di_spina,
    mappa_corrente,
    spina_del_piano,
    zona_corrente,
    zona_di_spina_del_tier,
    zona_successiva,
    zone_laterali,
)
from tests.contenuti_sintetici import piano_territoriale, stagione_sintetica


def _arma_mondo(seed: int = 7) -> BusEventi:
    from main import _stagione_a_attiva

    crea_profondita()
    crea_seme(seed)
    crea_tempo_piano()
    crea_stagione(_stagione_a_attiva(
        stagione_sintetica(piani=[piano_territoriale(1)], slug="s-mondo")
    ))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    avvia_territorio(1)
    return BusEventi()


def _seme_con_laterali(massimo: int = 60) -> int:
    """Un seed la cui zona di partenza HA deviazioni (0-2 sono seeded: si cerca).
    Esplora in mondi usa-e-getta e RIENTRA nel mondo del test (mai 'default')."""
    import esper

    mondo_del_test = esper.current_world
    for seed in range(massimo):
        nome = f"cerca-laterali-{seed}"
        esper.switch_world(nome)
        try:
            _arma_mondo(seed)
            trovate = bool(zone_laterali(1))
        finally:
            esper.switch_world(mondo_del_test)
            esper.delete_world(nome)
        if trovate:
            return seed
    raise AssertionError("nessun seed con laterali entro il limite (improbabile)")


def test_laterali_deterministiche_e_sorelle(mondo_isolato) -> None:
    seed = _seme_con_laterali()
    _arma_mondo(seed)
    laterali = zone_laterali(1)
    assert laterali == zone_laterali(1)  # derivate pure: stessa chiamata, stesse zone
    corrente = zona_corrente()
    for laterale in laterali:
        assert laterale.tier is corrente.tier                      # sorelle: stesso tier
        assert laterale.percorso[:-1] == corrente.percorso[:-1]    # stesso genitore
        assert laterale.percorso[-1] != corrente.percorso[-1]      # indice diverso
        assert not e_di_spina(laterale, 1)


def test_deviazione_dalla_partenza_e_ritorno_libero(mondo_isolato) -> None:
    """Andata: dalla partenza della zona di spina verso la sorella (senza boss:
    la via da cui entri resta libera). La laterale è un VICOLO (nessun avanti);
    il ritorno sulla spina è dalla sua partenza, libero."""
    seed = _seme_con_laterali()
    bus = _arma_mondo(seed)
    eventi: list[TransizioneZona] = []
    bus.registra(TransizioneZona, eventi.append)
    spina0 = zona_corrente()
    laterale = zone_laterali(1)[0]

    assert deviazione_consentita(laterale.chiave) is True  # partenza, nessun mob
    assert attraversa(bus, laterale.chiave) is True
    assert zona_corrente() == laterale
    assert eventi and eventi[-1].zona == laterale.chiave
    # Il vicolo: nessun avanzamento di spina da qui, e il boss ESISTE (lazy).
    assert zona_successiva(1) is None
    assert boss_della_zona(1, laterale) is not None
    # Ritorno: dalla partenza della laterale, verso la zona di spina del tier.
    rientro = zona_di_spina_del_tier(laterale.tier, 1)
    assert rientro == spina0
    assert deviazione_consentita(rientro.chiave) is True
    assert attraversa(bus, rientro.chiave) is True
    assert zona_corrente() == spina0


def test_deviazione_negata_fuori_dalla_partenza_o_arbitraria(mondo_isolato) -> None:
    seed = _seme_con_laterali()
    bus = _arma_mondo(seed)
    laterale = zone_laterali(1)[0]
    # Fuori dalla partenza: negata.
    _e, mappa = mappa_corrente()
    mappa.stanza_corrente = len(mappa.piano.adiacenze) - 1
    assert deviazione_consentita(laterale.chiave) is False
    assert attraversa(bus, laterale.chiave) is False
    # Destinazione ARBITRARIA (mai composta dalla scena): negata — niente
    # teletrasporto da chiave inventata.
    mappa.stanza_corrente = mappa.piano.partenza
    assert deviazione_consentita("citta:9/9/9") is False
    assert attraversa(bus, "citta:9/9/9") is False


def test_scena_offre_la_deviazione_e_il_ritorno(mondo_isolato) -> None:
    from contracts import TipoAzione
    from motore import Fase, SistemaTempoPiano, avvia_run, componi_opzioni_scena, segna_visitata

    seed = _seme_con_laterali()
    bus = _arma_mondo(seed)
    avvia_run(crea_singleton_fase=True, fase_iniziale=Fase.NARRAZIONE,
              sempre_attivi=[SistemaTempoPiano()])
    segna_visitata()
    laterali = zone_laterali(1)
    deviazioni = [o for o in componi_opzioni_scena()
                  if o.tipo is TipoAzione.ATTRAVERSA and o.zona]
    assert {o.zona for o in deviazioni} == {z.chiave for z in laterali}
    # Dentro la laterale, la scena offre il RITORNO.
    attraversa(bus, laterali[0].chiave)
    segna_visitata()
    ritorni = [o for o in componi_opzioni_scena()
               if o.tipo is TipoAzione.ATTRAVERSA and o.zona]
    assert len(ritorni) == 1
    assert ritorni[0].zona == zona_di_spina_del_tier(laterali[0].tier, 1).chiave


def test_fascicolo_porta_la_telecronaca_del_miliardo(mondo_isolato) -> None:
    from motore import MemoriaTurni
    from motore.gm import componi_fascicolo, sezione_fascicolo

    _arma_mondo()
    sezione = sezione_fascicolo(componi_fascicolo(MemoriaTurni()))
    assert "VASTO" in sezione and "150.000 ingressi" in sezione
    assert "altri crawler" in sezione
