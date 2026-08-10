"""Territorio F2b: il passaggio di zona — gate (stanza+boss), sistema con un solo
proprietario, boss-gate su CombatResolved, anti-softlock del disimpegno, menu.
"""

from __future__ import annotations

import asyncio

from contracts import BusEventi, PlayerAttraversa, PlayerChoseOption, TipoAzione, TransizioneZona
from motore import (
    Fase,
    SistemaTempoPiano,
    attraversa,
    attraversamento_consentito,
    avvia_run,
    avvia_territorio,
    boss_della_zona,
    boss_sconfitto,
    collega_boss,
    componi_opzioni_scena,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_stagione,
    crea_tempo_piano,
    mappa_corrente,
    registra_boss_sconfitto,
    segna_visitata,
    spina_del_piano,
    stanza_passaggio_di,
    zona_corrente,
)
from tests.contenuti_sintetici import piano_territoriale, stagione_sintetica


def _arma_mondo(seed: int = 7):
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


def _vai_al_passaggio() -> None:
    _e, mappa = mappa_corrente()
    mappa.stanza_corrente = stanza_passaggio_di(zona_corrente(), mappa.piano)
    segna_visitata()


def test_gate_chiuso_senza_boss_battuto(mondo_isolato) -> None:
    bus = _arma_mondo()
    _vai_al_passaggio()
    assert attraversamento_consentito() is False  # il custode è ancora in piedi
    assert attraversa(bus) is False
    assert zona_corrente() == spina_del_piano(1)[0]  # nessun avanzamento


def test_gate_chiuso_fuori_dalla_stanza_passaggio(mondo_isolato) -> None:
    bus = _arma_mondo()
    registra_boss_sconfitto()
    _e, mappa = mappa_corrente()
    mappa.stanza_corrente = mappa.piano.partenza
    assert attraversamento_consentito() is False
    assert attraversa(bus) is False


def test_attraversa_avanza_di_una_zona_e_pubblica(mondo_isolato) -> None:
    bus = _arma_mondo()
    eventi: list[TransizioneZona] = []
    bus.registra(TransizioneZona, eventi.append)
    registra_boss_sconfitto()
    _vai_al_passaggio()
    assert attraversamento_consentito() is True
    assert attraversa(bus) is True
    spina = spina_del_piano(1)
    assert zona_corrente() == spina[1]  # quartiere → distretto
    assert eventi and eventi[0].zona == spina[1].chiave
    assert eventi[0].tier == spina[1].tier.value
    # La zona nuova nasce non visitata, dalla partenza.
    _e, mappa = mappa_corrente()
    assert mappa.stanza_corrente == mappa.piano.partenza and not mappa.visitate


def test_boss_gate_su_combat_resolved(mondo_isolato) -> None:
    """La vittoria nella STANZA-BOSS marca il custode; altrove (o in fuga) no."""
    from contracts import CombatResolved

    bus = _arma_mondo()
    handler = collega_boss(bus)
    try:
        # Vittoria NON nella stanza-boss: nessun flag.
        bus.pubblica(CombatResolved(entita=0, vittoria=True))
        assert boss_sconfitto() is False
        _vai_al_passaggio()  # nelle zone non-tana il passaggio È la stanza-boss
        # La FUGA nella stanza-boss non apre niente.
        bus.pubblica(CombatResolved(entita=0, vittoria=False, fuga=True))
        assert boss_sconfitto() is False
        # La vittoria sì: il custode cade.
        bus.pubblica(CombatResolved(entita=0, vittoria=True))
        assert boss_sconfitto() is True
    finally:
        bus.deregistra(CombatResolved, handler)


def test_il_menu_offre_attraversa_solo_quando_vero(mondo_isolato) -> None:
    _arma_mondo()
    avvia_run(crea_singleton_fase=True, fase_iniziale=Fase.NARRAZIONE,
              sempre_attivi=[SistemaTempoPiano()])
    _vai_al_passaggio()
    tipi = {o.tipo for o in componi_opzioni_scena()}
    assert TipoAzione.ATTRAVERSA not in tipi  # boss vivo (flag assente)
    registra_boss_sconfitto()
    tipi = {o.tipo for o in componi_opzioni_scena()}
    assert TipoAzione.ATTRAVERSA in tipi
    assert TipoAzione.SCENDI not in tipi  # niente scala nelle zone non-tana


def test_boss_nominato_della_zona_e_deterministico(mondo_isolato) -> None:
    _arma_mondo()
    spina = spina_del_piano(1)
    paese = spina[4]
    assert paese.tier.value == "paese"
    a = boss_della_zona(1, paese)
    b = boss_della_zona(1, paese)
    assert a is not None and a.slug == b.slug  # stessa zona → stesso boss
    assert a.slug == "t-boss-paese"


def test_e2e_il_sistema_serve_l_intento(run_pulita, tmp_path) -> None:
    """Via porte: PlayerAttraversa → SistemaAttraversamento → zona avanzata."""
    from main import costruisci_sessione

    sessione = costruisci_sessione(
        nome="Varco", seed=3, directory=tmp_path,
        stagione=stagione_sintetica(piani=[piano_territoriale(1)], slug="s-e2e"),
    )
    registra_boss_sconfitto()
    _vai_al_passaggio()
    prima = zona_corrente()
    sessione.coda.accoda(PlayerAttraversa())
    sessione.avanza()
    assert zona_corrente() != prima
    assert zona_corrente() == spina_del_piano(1)[1]


def test_disimpegno_dal_boss_ritira_senza_dissolvere(run_pulita, tmp_path) -> None:
    """Anti-softlock: nella stanza del boss il disimpegno riuscito RITIRA il
    crawler nella stanza precedente e il custode resta al varco."""
    import esper
    from main import costruisci_sessione
    from motore import EntitaMob, mob_corrente, registra_mob
    from motore.narrazione import istanzia_entita
    from contracts import EntitaGenerata, Grado

    sessione = costruisci_sessione(
        nome="Ritiro", seed=3, directory=tmp_path,
        stagione=stagione_sintetica(piani=[piano_territoriale(1)], slug="s-ritiro"),
    )
    asyncio.run(sessione.prossima_narrazione())  # reveal della partenza
    # Harness: piazza un "boss" vivo nella stanza-passaggio (la stanza-boss).
    _vai_al_passaggio()
    ent = istanzia_entita(
        EntitaGenerata(archetipo="slime", grado=Grado.BRONZO, blocchi=[],
                       nome="Custode", descrizione="fermo al varco"),
        livello=1,
    )
    registra_mob(ent)
    sessione._sincronizza_scena()
    snap = sessione._snapshot_corrente()
    etichette = {o.etichetta: o.indice for o in snap.opzioni}
    assert "Scappi" in etichette
    _e, mappa = mappa_corrente()
    stanza_boss = mappa.stanza_corrente
    sessione.coda.accoda(PlayerChoseOption(etichette["Scappi"]))
    sessione.avanza()
    _e, mappa = mappa_corrente()
    assert mappa.stanza_corrente != stanza_boss, "il disimpegno deve RITIRARE"
    assert esper.entity_exists(ent), "il custode NON si dissolve"
    em = esper.component_for_entity(ent, EntitaMob)
    assert em.stanza == stanza_boss  # resta registrato al varco
