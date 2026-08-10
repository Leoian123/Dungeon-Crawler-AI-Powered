"""Territorio F2a: la spina campionata, le mappe di zona, la tana col nascondino
e lo stato persistente. Tutto su stagioni sintetiche col territorio.
"""

from __future__ import annotations

import esper

from contracts import TierTerritorio
from motore import (
    ORDINE_SPINA,
    avvia_territorio,
    crea_profondita,
    crea_seme,
    crea_stagione,
    crea_tempo_piano,
    mappa_corrente,
    spina_del_piano,
    stanza_boss_di,
    stato_territorio,
    territorio_attivo,
    zona_corrente,
    zona_da_chiave,
    zona_successiva,
)
from motore.persistenza.tag import deserializza_componente, serializza_componente
from motore.territorio import StatoTerritorio, Zona, rigenera_mappa_zona
from tests.contenuti_sintetici import piano_territoriale, stagione_sintetica


def _arma_mondo(seed: int = 7) -> None:
    from main import _stagione_a_attiva

    crea_profondita()
    crea_seme(seed)
    crea_tempo_piano()
    crea_stagione(_stagione_a_attiva(
        stagione_sintetica(piani=[piano_territoriale(1)], slug="s-mondo")
    ))


def test_spina_deterministica_e_completa(mondo_isolato) -> None:
    _arma_mondo(seed=7)
    spina = spina_del_piano(1)
    assert [z.tier for z in spina] == list(ORDINE_SPINA)  # quartiere → … → tana
    assert spina == spina_del_piano(1), "stessa run, stessa spina (derivata pura)"
    # L'indirizzo è coerente: ogni zona è il PREFISSO della più profonda.
    quartiere = spina[0]
    assert len(quartiere.percorso) == 5
    for zona in spina[1:-1]:
        assert quartiere.percorso[: len(zona.percorso)] == zona.percorso
    assert spina[-1].tier is TierTerritorio.PIANO and spina[-1].percorso == ()
    # Chiave stabile e invertibile.
    for zona in spina:
        assert zona_da_chiave(zona.chiave) == zona


def test_spina_cambia_col_seed(mondo_isolato) -> None:
    _arma_mondo(seed=7)
    prima = spina_del_piano(1)
    esper.switch_world("altro-seme-spina")
    try:
        _arma_mondo(seed=8)
        seconda = spina_del_piano(1)
    finally:
        esper.switch_world("default")
        esper.delete_world("altro-seme-spina")
    assert prima != seconda  # i conteggi (2×10×40×4×4) rendono la collisione irrisoria


def test_senza_territorio_il_modulo_e_inerte(mondo_isolato) -> None:
    from main import _stagione_a_attiva

    crea_profondita()
    crea_seme(7)
    crea_stagione(_stagione_a_attiva(stagione_sintetica(1)))  # piano PIATTO
    assert territorio_attivo() is None
    assert spina_del_piano(1) == ()
    assert avvia_territorio(1) is False
    assert stato_territorio() is None


def test_avvio_monta_la_prima_zona_della_spina(mondo_isolato) -> None:
    _arma_mondo()
    assert avvia_territorio(1) is True
    spina = spina_del_piano(1)
    assert zona_corrente() == spina[0]  # si parte dal quartiere
    stato = stato_territorio()
    assert stato is not None and stato.zone_visitate == [spina[0].chiave]
    _ent, mappa = mappa_corrente()
    assert len(mappa.piano.adiacenze) == 3  # stanze_per_zona del sintetico
    assert not mappa.piano.discese, "nelle zone non-tana NON c'è scala"


def test_mappa_di_zona_seeded_per_zona(mondo_isolato) -> None:
    _arma_mondo()
    avvia_territorio(1)
    spina = spina_del_piano(1)
    rigenera_mappa_zona(1, spina[1])
    _e1, mappa_distretto = mappa_corrente()
    rigenera_mappa_zona(1, spina[0])
    rigenera_mappa_zona(1, spina[1])
    _e2, di_nuovo = mappa_corrente()
    assert mappa_distretto.piano.adiacenze == di_nuovo.piano.adiacenze  # seed per zona
    assert zona_corrente() == spina[1]


def test_tana_scala_dietro_il_boss_ma_aggirabile(mondo_isolato) -> None:
    """La clausola del NASCONDINO: nella tana la scala esiste (unica del piano),
    il boss sta nella penultima stanza, ed esiste un cammino partenza→scala che
    NON passa dalla sua stanza."""
    _arma_mondo()
    avvia_territorio(1)
    tana = spina_del_piano(1)[-1]
    rigenera_mappa_zona(1, tana)
    _ent, mappa = mappa_corrente()
    n = len(mappa.piano.adiacenze)
    assert mappa.piano.discese == {n - 1}, "la scala del piano vive SOLO nella tana"
    boss = stanza_boss_di(tana, mappa.piano)
    assert boss == n - 2

    # BFS dalla partenza alla scala EVITANDO la stanza del boss.
    da_visitare, visti = [mappa.piano.partenza], {mappa.piano.partenza}
    while da_visitare:
        stanza = da_visitare.pop()
        for uscita in mappa.piano.adiacenze[stanza]:
            if uscita == boss or uscita in visti:
                continue
            visti.add(uscita)
            da_visitare.append(uscita)
    assert (n - 1) in visti, "la scala DEVE essere raggiungibile senza passare dal boss"


def test_zona_successiva_percorre_la_spina(mondo_isolato) -> None:
    _arma_mondo()
    avvia_territorio(1)
    spina = spina_del_piano(1)
    for atteso in spina[1:]:
        prossima = zona_successiva(1)
        assert prossima == atteso
        rigenera_mappa_zona(1, prossima)
    assert zona_successiva(1) is None  # alla tana la spina finisce (c'è la scala)


def test_stato_territorio_round_trippa(mondo_isolato) -> None:
    stato = StatoTerritorio(
        zona_corrente="citta:0/3/12",
        boss_sconfitti=["quartiere:0/3/12/2/1", "distretto:0/3/12/2"],
        zone_visitate=["quartiere:0/3/12/2/1", "distretto:0/3/12/2", "citta:0/3/12"],
    )
    tag, dati = serializza_componente(stato)
    assert tag == "territorio"
    assert deserializza_componente(tag, dati) == stato


def test_discesa_da_piano_territoriale_monta_il_quartiere(mondo_isolato) -> None:
    """La discesa su un piano-mondo entra dalla prima zona della spina del piano
    NUOVO (via l'handler di mappa già cablato)."""
    from contracts import BusEventi, DiscesaPiano
    from motore import collega_discesa_mappa
    from main import _stagione_a_attiva

    crea_profondita()
    crea_seme(7)
    crea_tempo_piano()
    crea_stagione(_stagione_a_attiva(stagione_sintetica(
        piani=[piano_territoriale(1, prefisso="t"), piano_territoriale(2, prefisso="u")],
        slug="s-due-mondi",
    )))
    avvia_territorio(1)
    bus = BusEventi()
    handler = collega_discesa_mappa(bus)
    try:
        from motore.piano import attiva_discesa

        attiva_discesa(bus)
        assert zona_corrente() == spina_del_piano(2)[0]
        stato = stato_territorio()
        assert stato.boss_sconfitti == []  # il piano nuovo riparte pulito
    finally:
        bus.deregistra(DiscesaPiano, handler)
