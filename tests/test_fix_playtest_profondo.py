"""I fix del playtest profondo 2026-08-28 (run di Ade, seed 8, morte contro
Evil Ash): B1 «Vai» in tregua muto (compositore↔esecutore divergiti), B2 il
tritacarne del boss ingaggiato (fuga che non arretra), B3 status dannosi
invisibili in scheda, B4 difesa in centesimi, B6 etichetta box che mente sul
grado, B7.4 gate del parlamento silente.

Il lucchetto-chiave di B1 testa la COPPIA, non i due lati separati: ogni
opzione `MUOVI` composta, se scelta, muta `stanza_corrente` — è il test che
avrebbe preso la regressione (il fix P0-2 aveva aggiornato il compositore,
`muovi()` rifiutava ancora).
"""

from __future__ import annotations

import asyncio
import random

import esper

from contracts import (
    BusEventi,
    CombatResolved,
    DisimpegnoFallito,
    DisimpegnoScena,
    EncounterStarted,
    EntitaGenerata,
    Grado,
    ParlamentoRisolto,
    TipoAzione,
)
from motore import (
    EntitaMob,
    SpecNemico,
    avvia_territorio,
    componi_opzioni_scena,
    crea_entita_fase,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_stagione,
    crea_tempo_piano,
    discesa_consentita,
    mappa_corrente,
    mob_corrente,
    muovi,
    passaggio_concesso,
    protagonista,
    registra_mob,
    richiedi_fuga,
    segna_visitata,
    stanza_di_ritirata,
    tick,
)
from tests.contenuti_sintetici import piano_territoriale, stagione_sintetica


def _arma_mondo(seed: int = 7) -> BusEventi:
    from main import _stagione_a_attiva

    crea_profondita()
    crea_seme(seed)
    crea_tempo_piano()
    crea_stagione(_stagione_a_attiva(
        stagione_sintetica(piani=[piano_territoriale(1)], slug="s-profondo")
    ))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    crea_entita_fase()
    avvia_territorio(1)
    return BusEventi()


def _mob_in_stanza(*, parlamentato: bool) -> int:
    """Un ostile registrato nella stanza corrente, col marker di tregua a
    scelta (l'harness manipola il dato persistente, come il gioco dopo un
    parlamento riuscito)."""
    from motore.narrazione import istanzia_entita

    ent = istanzia_entita(EntitaGenerata(
        archetipo="slime", grado=Grado.BRONZO, blocchi=[],
        nome="Fante", descrizione="di prova",
    ), 1)
    registra_mob(ent)
    segna_visitata()
    em = esper.component_for_entity(ent, EntitaMob)
    em.parlamento_tentato = True
    em.parlamento_riuscito = parlamentato
    return ent


# --- B1 · il «Vai» in tregua MUOVE (coppia compositore↔esecutore) ---------------

def test_b1_ogni_vai_composto_in_tregua_muove(mondo_isolato) -> None:
    """Property di coerenza: OGNI `MUOVI` composto, se scelto, muta
    `stanza_corrente` — mai un'opzione lecita a effetto nullo. È il lucchetto
    che avrebbe preso la regressione P0 del 27/08."""
    _arma_mondo()
    _mob_in_stanza(parlamentato=True)
    assert passaggio_concesso() is True

    opzioni = componi_opzioni_scena()
    vai = [o for o in opzioni if o.tipo is TipoAzione.MUOVI]
    assert vai, "in tregua col gregario il passaggio si compone"
    _e, mappa = mappa_corrente()
    partenza = mappa.stanza_corrente
    for opzione in vai:
        assert muovi(opzione.stanza) is True, (
            f"l'opzione composta «{opzione.etichetta}» deve muovere"
        )
        assert mappa.stanza_corrente == opzione.stanza
        mappa.stanza_corrente = partenza  # LAB: si riprova ogni uscita


def test_b1_mob_non_parlamentato_ne_opzione_ne_movimento(mondo_isolato) -> None:
    """Caso negativo della coppia: mob vivo NON parlamentato ⇒ `muovi()`
    rifiuta E l'opzione non è composta (i due lati dicono la stessa cosa)."""
    _arma_mondo()
    _mob_in_stanza(parlamentato=False)
    assert passaggio_concesso() is False

    opzioni = componi_opzioni_scena()
    assert not [o for o in opzioni if o.tipo in (TipoAzione.MUOVI, TipoAzione.SCENDI)]
    _e, mappa = mappa_corrente()
    partenza = mappa.stanza_corrente
    for uscita in mappa.piano.adiacenze.get(partenza, ()):
        assert muovi(uscita) is False
    assert mappa.stanza_corrente == partenza


def test_b1_custode_in_tregua_resta_boss_gate(mondo_isolato) -> None:
    """Tregua col CUSTODE imbattuto ⇒ né opzione né movimento: il boss-gate
    non si parla (l'Attraversa vive dietro la vittoria)."""
    from motore import stanza_boss_di, zona_corrente

    _arma_mondo()
    _e, mappa = mappa_corrente()
    zona = zona_corrente()
    mappa.stanza_corrente = stanza_boss_di(zona, mappa.piano)
    _mob_in_stanza(parlamentato=True)

    assert passaggio_concesso() is False
    opzioni = componi_opzioni_scena()
    assert not [o for o in opzioni if o.tipo in (TipoAzione.MUOVI, TipoAzione.SCENDI)]
    for uscita in mappa.piano.adiacenze.get(mappa.stanza_corrente, ()):
        assert muovi(uscita) is False


def test_b1_la_discesa_ha_lo_stesso_proprietario(mondo_isolato) -> None:
    """Il gemello SCENDI: la scala col mob non parlamentato è chiusa (non era
    mai stata guardata: una fuga gratis), in tregua è aperta come il resto."""
    _arma_mondo()
    _e, mappa = mappa_corrente()
    mappa.piano.discese.add(mappa.stanza_corrente)  # LAB: scala qui

    ent = _mob_in_stanza(parlamentato=False)
    assert discesa_consentita() is False, "la scala non è una fuga gratis"
    em = esper.component_for_entity(ent, EntitaMob)
    em.parlamento_riuscito = True
    assert discesa_consentita() is True, "in tregua la scala si scende"
    opzioni = componi_opzioni_scena()
    assert [o for o in opzioni if o.tipo is TipoAzione.SCENDI], (
        "il compositore dice la stessa cosa dell'esecutore"
    )


# --- B2 · la fuga in combattimento riuscita ARRETRA -----------------------------

def _scontro_con_mappa(*, destrezza: int):
    """Scontro headless + mappa: la ritirata della fuga ha una destinazione."""
    from motore import crea_mappa
    from tests.combat_helpers import avvia_scontro

    bus, adapter, enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=1, punti_vita=5)], seed=1,
        hp_prot=10_000, destrezza_prot=destrezza,
    )
    crea_mappa(random.Random(1), 4)
    ritirate: list[DisimpegnoScena] = []
    bus.registra(DisimpegnoScena, ritirate.append)
    return bus, adapter, ritirate


def test_b2_fuga_pulita_arretra_e_la_cronaca_lo_dice(mondo_isolato) -> None:
    from contracts import ClasseProva
    from motore.calibrazione import MARGINE_FUGA_PULITA, SOGLIE_PROVA

    dex = SOGLIE_PROVA[ClasseProva.BRONZO] + MARGINE_FUGA_PULITA
    _bus, adapter, ritirate = _scontro_con_mappa(destrezza=dex)
    _e, mappa = mappa_corrente()
    partenza = mappa.stanza_corrente
    attesa = stanza_di_ritirata()
    richiedi_fuga()
    tick()
    assert [e for e in adapter.events_of(CombatResolved) if e.fuga]
    assert mappa.stanza_corrente == attesa != partenza, (
        "la fuga riuscita È il disimpegno: si esce dalla stanza"
    )
    [evento] = ritirate
    assert evento.ritirata_in == attesa, "la ritirata parla in cronaca"


def test_b2_fuga_con_colpo_dopportunita_arretra_comunque(mondo_isolato) -> None:
    from contracts import ClasseProva
    from motore.calibrazione import SOGLIE_PROVA

    dex = SOGLIE_PROVA[ClasseProva.BRONZO]  # margine 0: corsia 2
    _bus, adapter, ritirate = _scontro_con_mappa(destrezza=dex)
    _e, mappa = mappa_corrente()
    attesa = stanza_di_ritirata()
    richiedi_fuga()
    tick()
    _pent, _m, scheda = protagonista()
    assert scheda.punti_vita < 10_000, "la corsia 2 morde"
    assert mappa.stanza_corrente == attesa, "ma porta comunque FUORI dalla stanza"
    assert ritirate


def test_b2_fuga_negata_resta_nella_stanza(mondo_isolato) -> None:
    from contracts import ClasseProva
    from motore.calibrazione import SOGLIE_PROVA

    dex = SOGLIE_PROVA[ClasseProva.BRONZO] - 1  # margine -1: corsia 3
    _bus, adapter, ritirate = _scontro_con_mappa(destrezza=dex)
    _e, mappa = mappa_corrente()
    partenza = mappa.stanza_corrente
    richiedi_fuga()
    tick()
    assert not adapter.events_of(CombatResolved), "negata: lo scontro resta aperto"
    assert mappa.stanza_corrente == partenza, "la corsia che punisce non arretra"
    assert not ritirate


def test_b2_sequenza_trappola_fuga_dal_mob_di_stanza(run_pulita, tmp_path) -> None:
    """L'oracolo della trappola di Evil Ash: ingaggio del mob di stanza →
    fuga riuscita → sei nella stanza ADIACENTE (mai più il menu del mob al
    primo giro) e lui resta registrato alla sua stanza, ferite comprese."""
    from contracts import PlayerChoseOption, StatId
    from main import costruisci_sessione
    from motore import stat_eff
    from motore.statistiche import Primarie

    sessione = costruisci_sessione(
        nome="Ade", seed=8, directory=tmp_path,
        stagione=stagione_sintetica(piani=[piano_territoriale(1)], slug="s-evilash"),
    )
    asyncio.run(sessione.prossima_narrazione())
    ent = mob_corrente()
    assert ent is not None, "il copione del seed 8 rivela un mob in partenza"
    _e, mappa = mappa_corrente()
    stanza_del_mob = mappa.stanza_corrente
    attesa = stanza_di_ritirata()

    # Destrezza da fuga pulita: qui si prova la RITIRATA, non la corsia.
    from motore.calibrazione import MARGINE_FUGA_PULITA, SOGLIE_PROVA
    from motore.catalogo import classe_da_grado

    pent = protagonista()[0]
    primarie = esper.component_for_entity(pent, Primarie)
    em = esper.component_for_entity(ent, EntitaMob)
    soglia = SOGLIE_PROVA[classe_da_grado(em.grado)]
    primarie.valori[StatId.DESTREZZA] = soglia + MARGINE_FUGA_PULITA + 5
    assert stat_eff(pent, StatId.DESTREZZA) >= soglia

    sessione._sincronizza_scena()
    snap = sessione._snapshot_corrente()
    indici = {o.etichetta: o.indice for o in snap.opzioni}
    combatti = next(k for k in indici if k.startswith("Combatti"))
    sessione.coda.accoda(PlayerChoseOption(indici[combatti]))
    snap = sessione.avanza()
    assert snap.fase == "combattimento"

    fuggi = next(
        o.indice for o in snap.opzioni if o.etichetta.lower().startswith("fuggi")
    )
    sessione.coda.accoda(PlayerChoseOption(fuggi))
    snap = sessione.avanza()

    assert snap.fase == "narrazione", "la fuga chiude lo scontro"
    assert mappa.stanza_corrente == attesa != stanza_del_mob, (
        "il tritacarne: la fuga deve portare FUORI dalla stanza del mob"
    )
    assert esper.entity_exists(ent), "il mob non si dissolve"
    assert esper.component_for_entity(ent, EntitaMob).stanza == stanza_del_mob
    etichette = [o.etichetta for o in sessione._snapshot_corrente().opzioni]
    assert not any(e.startswith("Combatti") for e in etichette), (
        "nella stanza adiacente non c'è il menu del mob appena lasciato"
    )
    sessione.esci()


def test_b2_disimpegno_di_scena_fallito_ha_la_riga_fatto(
    run_pulita, tmp_path, monkeypatch
) -> None:
    """Lo «Scappi» pre-ingaggio fallito pubblica `DisimpegnoFallito` PRIMA
    dell'`EncounterStarted`: il rifiuto non è più muto (linea rossa)."""
    import main as main_mod
    from contracts import PlayerChoseOption
    from main import costruisci_sessione

    sessione = costruisci_sessione(
        nome="Rincorso", seed=8, directory=tmp_path,
        stagione=stagione_sintetica(piani=[piano_territoriale(1)], slug="s-riagg"),
    )
    asyncio.run(sessione.prossima_narrazione())
    assert mob_corrente() is not None
    monkeypatch.setattr(main_mod, "tenta_disimpegno", lambda *_a, **_k: False)

    accaduti: list[object] = []
    sessione.bus.registra(DisimpegnoFallito, accaduti.append)
    sessione.bus.registra(EncounterStarted, accaduti.append)
    sessione._sincronizza_scena()
    snap = sessione._snapshot_corrente()
    scappi = next(
        o.indice for o in snap.opzioni if o.tipo is TipoAzione.SCAPPA
    )
    sessione.coda.accoda(PlayerChoseOption(scappi))
    sessione.avanza()

    tipi = [type(e) for e in accaduti]
    assert DisimpegnoFallito in tipi, "il disimpegno fallito lascia la riga-fatto"
    assert tipi.index(DisimpegnoFallito) < tipi.index(EncounterStarted), (
        "prima la causa (prova persa), poi l'effetto (lo scontro si riapre)"
    )
    fallito = next(e for e in accaduti if isinstance(e, DisimpegnoFallito))
    assert fallito.classe, "la riga dice CONTRO COSA hai perso"
    # Lo scontro riaperto vieta il salva-ed-esci: il teardown di `run_pulita`
    # smonta il run-World — qui non si esce di cortesia.


# --- B3 · gli status si vedono in scheda per costruzione ------------------------

def test_b3_ogni_status_della_tabella_ha_il_descrittore_in_scheda(
    mondo_isolato,
) -> None:
    """Property sulla TABELLA UNICA: per OGNI riga di `SPEC_STATUS` con
    descrittore, applicare lo status ⇒ il descrittore compare nella
    proiezione. Copre anche gli status futuri (il Brucia invisibile era
    esattamente la riga fuori dall'elenco cablato)."""
    from motore import proietta_scheda
    from motore.status import SPEC_STATUS, afflizione

    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    pent = protagonista()[0]
    for spec in SPEC_STATUS:
        assert spec.descrittore, (
            f"{spec.componente.__name__}: ogni status della tabella deve avere "
            "un descrittore — uno status invisibile in scheda è il bug B3"
        )
        esper.add_component(pent, afflizione(spec.componente, 1))
        assert spec.descrittore in proietta_scheda(pent).descrittori, (
            f"{spec.componente.__name__} applicato ma invisibile in scheda"
        )
        esper.remove_component(pent, spec.componente)
        assert spec.descrittore not in proietta_scheda(pent).descrittori


def test_b3_il_brucia_si_vede_e_la_cronaca_usa_la_stessa_tabella(
    mondo_isolato,
) -> None:
    """L'oracolo del playtest: protagonista col Brucia ⇒ la scheda dice
    «in fiamme». E il participio della cronaca legge la STESSA colonna
    (main teneva la terza copia della mappa slug→descrittore)."""
    from main import _participio_status
    from motore import proietta_scheda
    from motore.status import Brucia, DESCRITTORI_STATUS, afflizione

    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    pent = protagonista()[0]
    esper.add_component(pent, afflizione(Brucia, 2))
    assert "in fiamme" in proietta_scheda(pent).descrittori
    assert _participio_status("brucia") == DESCRITTORI_STATUS["brucia"] == "in fiamme"


# --- B4 · la difesa si proietta in unità di mitigazione -------------------------

def test_b4_difesa_proiettata_nell_ordine_delle_altre_derivate(
    run_pulita, tmp_path,
) -> None:
    """`def_eff` resta centesimi nel motore (contratto §5.2); la SCHEDA la
    mostra /100 a una cifra — mai più DEF 238 accanto ad ATK 12."""
    from main import costruisci_sessione
    from motore.derivate import def_eff

    sessione = costruisci_sessione(nome="Mit", seed=3, directory=tmp_path)
    pent = protagonista()[0]
    scheda = sessione.scheda()
    assert scheda.derivate["difesa"] == round(def_eff(pent) / 100, 1)
    assert scheda.derivate["difesa"] < 100, (
        "la mitigazione proiettata è nell'ordine di grandezza delle derivate"
    )
    sessione.esci()


# --- B6 · l'etichetta della box dice il grado di APERTURA -----------------------

def test_b6_etichetta_e_apertura_leggono_la_stessa_scalata(
    run_pulita, tmp_path, monkeypatch,
) -> None:
    """Territorio più profondo del conio: l'etichetta annuncia la scalata
    («bronzo → argento qui») e `BoxAperta.grado` coincide col grado promesso
    — stessa funzione (`grado_apertura`), coincidenza per costruzione."""
    from contracts import BoxAperta, TipoStanza
    from main import costruisci_sessione
    from motore import territorio as territorio_mod
    from motore.obiettivi import BoxChiusa, grado_apertura, obiettivi_correnti

    sessione = costruisci_sessione(nome="Box", seed=3, directory=tmp_path)
    asyncio.run(sessione.prossima_narrazione())
    from motore import dissolvi_mob

    if mob_corrente() is not None:
        dissolvi_mob()  # LAB: la safe room di prova nasce sgombra
    _e, mappa = mappa_corrente()
    mappa.piano.tipi[mappa.stanza_corrente] = TipoStanza.SAFE_ROOM
    comp = obiettivi_correnti()
    comp.box.append(BoxChiusa(id="prova:1", categoria="armi", grado="bronzo"))
    # Il territorio qui è un quartiere (finestra dal bronzo): si FORZA la
    # finestra-loot più profonda per esercitare la scalata vera.
    monkeypatch.setattr(
        territorio_mod, "finestra_gradi_loot", lambda _liv: {Grado.ARGENTO}
    )

    box = comp.box[0]
    promesso = grado_apertura(box)
    assert promesso == "argento", "premessa: la finestra forza la scalata"
    opzioni = componi_opzioni_scena()
    etichetta = next(o.etichetta for o in opzioni if o.tipo is TipoAzione.APRI_BOX)
    assert "Argento" in etichetta and "Bronzo" in etichetta, (
        f"l'etichetta deve dire la scalata, non mentire sul conio: {etichetta!r}"
    )

    aperture: list[BoxAperta] = []
    sessione.bus.registra(BoxAperta, aperture.append)
    from motore.obiettivi import apri_prossima_box

    assert apri_prossima_box(sessione.bus) is not None
    [evento] = aperture
    assert evento.grado == promesso, "etichetta e apertura: la stessa promessa"
    sessione.esci()


# --- B7.4 · il gate del parlamento lascia la riga-fatto -------------------------

def test_b74_il_gate_del_parlamento_pubblica_l_esito(run_pulita, tmp_path) -> None:
    """La prova di carisma all'apertura scena produce `ParlamentoRisolto`
    (ascoltato/rifiutato, con la classe); il convinto che riascolta non
    ri-tira e non ristampa."""
    from contracts import StatId
    from main import costruisci_sessione
    from motore.statistiche import Primarie

    sessione = costruisci_sessione(
        nome="Voce", seed=8, directory=tmp_path,
        stagione=stagione_sintetica(piani=[piano_territoriale(1)], slug="s-gate"),
    )
    asyncio.run(sessione.prossima_narrazione())
    ent = mob_corrente()
    assert ent is not None
    pent = protagonista()[0]
    esper.component_for_entity(pent, Primarie).valori[StatId.CARISMA] = 99

    esiti: list[ParlamentoRisolto] = []
    sessione.bus.registra(ParlamentoRisolto, esiti.append)
    sessione._apri_parlamento()
    [esito] = esiti
    assert esito.ascoltato is True
    assert esito.classe, "la riga dice contro quale classe hai parlato"
    assert esito.nemico

    # Il convinto riascolta: nessuna seconda prova, nessuna seconda riga.
    sessione.abbandona_parlamento()
    sessione._apri_parlamento()
    assert len(esiti) == 1, "il riascolto non ri-tira il gate"
    sessione.abbandona_parlamento()
    sessione.esci()


def test_b74_il_rifiuto_del_gate_pubblica_l_esito(run_pulita, tmp_path) -> None:
    from contracts import StatId
    from main import costruisci_sessione
    from motore.statistiche import Primarie

    sessione = costruisci_sessione(
        nome="Muto", seed=8, directory=tmp_path,
        stagione=stagione_sintetica(piani=[piano_territoriale(1)], slug="s-gate2"),
    )
    asyncio.run(sessione.prossima_narrazione())
    assert mob_corrente() is not None
    pent = protagonista()[0]
    esper.component_for_entity(pent, Primarie).valori[StatId.CARISMA] = 0

    esiti: list[ParlamentoRisolto] = []
    sessione.bus.registra(ParlamentoRisolto, esiti.append)
    sessione._apri_parlamento()
    [esito] = esiti
    assert esito.ascoltato is False
    assert sessione._scena_sociale is None, "il rifiutato non apre la scena"
    sessione.esci()


# --- B7.2 · l'ordine del menu è un contratto: slot fissi ------------------------

def test_b72_il_menu_ha_slot_stabili_movimento_in_fondo(mondo_isolato) -> None:
    """Le voci non saltano di corsia: tempo prima del movimento, riposo dopo
    l'attesa, il movimento sempre in fondo — l'indice sotto il cursore non
    cambia significato fra una ricomposizione e l'altra."""
    from motore.mappa import _SLOT_MENU

    _arma_mondo()
    segna_visitata()
    opzioni = componi_opzioni_scena()
    slot = [_SLOT_MENU.get(o.tipo, 99) for o in opzioni]
    assert slot == sorted(slot), (
        f"menu fuori corsia: {[o.etichetta for o in opzioni]}"
    )
    assert _SLOT_MENU[TipoAzione.PASSA] < _SLOT_MENU[TipoAzione.RIPOSA], (
        "il riposo sta dopo l'attesa"
    )
    assert max(
        _SLOT_MENU[t] for t in (TipoAzione.PASSA, TipoAzione.SMALTISCI,
                                TipoAzione.RIPOSA, TipoAzione.PARLAMENTA,
                                TipoAzione.APRI_BOX)
    ) < min(
        _SLOT_MENU[t] for t in (TipoAzione.MUOVI, TipoAzione.SCENDI,
                                TipoAzione.ATTRAVERSA)
    ), "il movimento vive in fondo, sempre"


# ════════════════════════════════════════════════════════════════════════════
# Appendice — i difetti del rigiro di collaudo (run «Kora», 2026-08-28): B8-B11
# ════════════════════════════════════════════════════════════════════════════

# --- B8 · le opzioni di ZONA si compongono (e funzionano) anche in tregua -------

def test_b8_il_vicolo_parlato_non_e_una_sacca(run_pulita, tmp_path) -> None:
    """L'oracolo di Kora: nel vicolo, mob della porta in TREGUA — «Torna
    sulla via principale» è composta E funzionante: mai più costretti a
    uccidere chi ti ha appena concesso il passo."""
    from main import costruisci_sessione
    from motore import dissolvi_mob
    from motore.territorio import (
        Zona,
        attraversa,
        deviazione_consentita,
        e_di_spina,
        rigenera_mappa_zona,
        stato_territorio,
        zona_corrente,
    )

    sessione = costruisci_sessione(
        nome="Kora", seed=8, directory=tmp_path,
        stagione=stagione_sintetica(piani=[piano_territoriale(1)], slug="s-vicolo"),
    )
    asyncio.run(sessione.prossima_narrazione())
    if mob_corrente() is not None:
        dissolvi_mob()

    # LAB: ci si porta in un VICOLO (sorella della zona di spina corrente) —
    # il teletrasporto dell'harness, non la via di gioco: qui si prova il
    # menu del rientro, non il campionamento delle laterali.
    quartiere = zona_corrente()
    laterale = Zona(
        tier=quartiere.tier,
        percorso=quartiere.percorso[:-1] + (quartiere.percorso[-1] + 1,),
    )
    assert not e_di_spina(laterale, 1), "premessa: la sorella non è di spina"
    stato_territorio().zona_corrente = laterale.chiave
    rigenera_mappa_zona(1, laterale)
    segna_visitata()

    ent = _mob_in_stanza(parlamentato=False)
    etichette = [o.etichetta for o in componi_opzioni_scena()]
    assert "Torna sulla via principale" not in etichette, (
        "col mob NON parlamentato il rientro resta chiuso"
    )

    esper.component_for_entity(ent, EntitaMob).parlamento_riuscito = True
    opzioni = componi_opzioni_scena()
    rientro = next(
        (o for o in opzioni if o.etichetta == "Torna sulla via principale"), None
    )
    assert rientro is not None, "in tregua il rientro dal vicolo SI COMPONE"
    # La coppia compositore-esecutore (stessa lezione di B1): l'opzione
    # composta, se scelta, CAMBIA zona.
    assert deviazione_consentita(rientro.zona) is True
    assert attraversa(sessione.bus, rientro.zona) is True
    assert zona_corrente().chiave == rientro.zona, "il rientro MUOVE davvero"
    sessione.esci()


def test_b8_il_varco_di_spina_in_tregua_resta_dietro_il_boss_gate(
    run_pulita, tmp_path
) -> None:
    """Il gregario in tregua sulla stanza-passaggio non apre il varco che
    solo il boss battuto apre; a boss battuto, la tregua non lo chiude."""
    from main import costruisci_sessione
    from motore import dissolvi_mob, registra_boss_sconfitto
    from motore.territorio import (
        attraversa,
        attraversamento_consentito,
        stanza_passaggio_di,
        zona_corrente,
    )

    sessione = costruisci_sessione(
        nome="Varco", seed=8, directory=tmp_path,
        stagione=stagione_sintetica(piani=[piano_territoriale(1)], slug="s-varco"),
    )
    asyncio.run(sessione.prossima_narrazione())
    if mob_corrente() is not None:
        dissolvi_mob()
    _e, mappa = mappa_corrente()
    zona = zona_corrente()
    # Il custode presidia PROPRIO il varco (per disegno): la stanza-passaggio
    # è la stanza-boss — il caso più duro per la tregua.
    mappa.stanza_corrente = stanza_passaggio_di(zona, mappa.piano)
    segna_visitata()
    _mob_in_stanza(parlamentato=True)

    # Boss VIVO: né composto né consentito — la tregua non scavalca il gate
    # (il mob parlato nella stanza del custode imbattuto È il boss-gate).
    assert attraversamento_consentito() is False
    assert not [
        o for o in componi_opzioni_scena()
        if o.tipo is TipoAzione.ATTRAVERSA and o.zona is None
    ]

    # Boss BATTUTO: il gregario in tregua non chiude il varco.
    registra_boss_sconfitto()
    avanti = [
        o for o in componi_opzioni_scena()
        if o.tipo is TipoAzione.ATTRAVERSA and o.zona is None
    ]
    assert avanti, "a boss battuto e tregua attiva l'Attraversa si compone"
    assert attraversamento_consentito() is True
    prima = zona.chiave
    assert attraversa(sessione.bus) is True
    assert zona_corrente().chiave != prima, "l'Attraversa composto MUOVE davvero"
    sessione.esci()


# --- B9.1 · la durata residua dei dannosi si vede (solo dal giocatore) ----------

def test_b91_la_scheda_conta_i_tick_e_l_ai_no(run_pulita, tmp_path) -> None:
    from main import costruisci_sessione
    from motore import proietta_scheda
    from motore.status import Brucia, afflizione

    sessione = costruisci_sessione(nome="Conto", seed=3, directory=tmp_path)
    pent = protagonista()[0]
    brucia = afflizione(Brucia, 1)
    brucia.durata = 3
    esper.add_component(pent, brucia)

    assert "in fiamme (3)" in sessione.scheda().descrittori, (
        "il giocatore fa la matematica PRIMA di decidere (B9.1)"
    )
    brucia.durata = 1
    assert "in fiamme (1)" in sessione.scheda().descrittori, "il conteggio scala"
    # G-13 intatto: la proiezione per l'AI resta senza numeri.
    for d in proietta_scheda(pent).descrittori:
        assert not any(ch.isdigit() for ch in d), f"numero nella proiezione AI: {d!r}"
    sessione.esci()


# --- B9.2 · la fabbrica conia i consumabili (il canale ha una fonte viva) -------

def test_b92_la_fabbrica_conia_il_tonico_e_si_beve(run_pulita, tmp_path) -> None:
    """Con le basi «consumabile» nella fabbrica della stagione, il conio
    produce un Consumabile VIVO: entra in catalogo, `/usa` lo beve (cura
    applicata, oggetto consumato). Era il canale completo senza fonti:
    40+ oggetti in tre run profonde, zero cure."""
    import random as _random

    from main import costruisci_sessione
    from motore import assicura_zaino, fabbrica_attiva, usa_consumabile
    from motore.consumabili import Consumabile
    from motore.fabbrica import conia_procedurale
    from motore.oggetti import assicura_coniati, catalogo_oggetti_correnti

    sessione = costruisci_sessione(nome="Cure", seed=3, directory=tmp_path)
    assert any(
        b.tipo == "consumabile" for b in fabbrica_attiva().basi
    ), "la stagione-1 ha le basi consumabili (B9.2)"

    attivo = conia_procedurale(
        _random.Random(7), "bronzo", tipi_base=("consumabile",)
    )
    assert attivo is not None and attivo.tipo == "consumabile"
    assert attivo.effetto in {"cura", "ristoro_mana", "antidoto"}

    pent = protagonista()[0]
    assicura_coniati(pent).voci.append(attivo)
    assicura_zaino(pent).fonti.append(attivo.slug)
    vivo = catalogo_oggetti_correnti()[attivo.slug]
    assert isinstance(vivo, Consumabile), "il coniato traduce in Consumabile"

    if attivo.effetto == "cura":
        _p, _m, scheda = protagonista()
        scheda.punti_vita = max(1, scheda.punti_vita - 10)
        prima = scheda.punti_vita
        ok, dettaglio = usa_consumabile(pent, attivo.slug, sessione.bus)
        assert ok, dettaglio
        assert scheda.punti_vita > prima, "la cura muove gli HP"
        assert attivo.slug not in assicura_zaino(pent).fonti, "monouso"
    sessione.esci()


def test_b92_oracolo_di_kora_col_tonico_si_sopravvive(run_pulita, tmp_path) -> None:
    """Il test che racconta la tenaglia: HP = 3 tick di Brucia, smaltimento
    in un click. SENZA cura è morte matematica; CON un tonico in zaino la
    stessa sequenza sopravvive."""
    import esper as _esper

    from contracts import PlayerChoseOption
    from main import costruisci_sessione
    from motore import (
        CATALOGO_CONSUMABILI, applica_status, assicura_zaino, usa_consumabile,
    )
    from motore.calibrazione import DELTA_PER_RANGO
    from motore.status import Brucia, afflizione

    danno_tick = abs(int(DELTA_PER_RANGO.get("brucia", 0)))
    assert danno_tick > 0, "premessa: il Brucia morde (§11)"

    def _sequenza(con_tonico: bool) -> bool:
        """True se il crawler è vivo alla fine. Stesso seed, stessa sequenza."""
        directory = tmp_path / ("con" if con_tonico else "senza")
        sessione = costruisci_sessione(nome="Kora", seed=5, directory=directory)
        asyncio.run(sessione.prossima_narrazione())
        if mob_corrente() is not None:
            _esper.delete_entity(mob_corrente(), immediate=True)
        pent, _m, scheda = protagonista()
        brucia = afflizione(Brucia, 1)
        brucia.durata = 3
        applica_status(pent, brucia)
        scheda.punti_vita = 3 * danno_tick  # esattamente i tick della tenaglia
        if con_tonico:
            assert "tonico-di-latta" in CATALOGO_CONSUMABILI
            assicura_zaino(pent).fonti.append("tonico-di-latta")
            ok, dettaglio = usa_consumabile(pent, "tonico-di-latta", sessione.bus)
            assert ok, dettaglio
        sessione._sincronizza_scena()
        snap = sessione._snapshot_corrente()
        indice = next(
            o.indice for o in snap.opzioni if o.etichetta == "Aspetta che passi"
        )
        sessione.coda.accoda(PlayerChoseOption(indice))
        sessione.avanza()
        vivo = protagonista()[2].vivo
        if vivo:
            sessione.esci()
        return vivo

    assert _sequenza(con_tonico=False) is False, (
        "senza cure la tenaglia è morte matematica (la fine di Kora)"
    )
    assert _sequenza(con_tonico=True) is True, (
        "con un tonico in zaino la stessa sequenza sopravvive"
    )


# --- B10 · il riferimento-boss vale solo nella stanza del custode ---------------

def test_b10_il_boss_autorato_non_fa_il_riempitivo(mondo_isolato) -> None:
    """Turno con `riferimento` a uno slug SOLO-boss: su una stanza qualunque
    il gate rifiuta (fallback deterministico); sulla stanza del custode
    resta accettato. Mai più due DJ Rigor Mortis nella stessa città."""
    from contracts import Grado as _G
    from motore import Budget, valida_turno
    from motore.design import riferimento_solo_boss
    from motore.territorio import boss_della_zona, stanza_boss_di, zona_corrente
    from tests.narr_helpers import turno as turno_h

    _arma_mondo()
    segna_visitata()
    zona = zona_corrente()
    boss = boss_della_zona(1, zona)
    assert boss is not None
    assert riferimento_solo_boss(boss.slug) is True, (
        "premessa: il custode non è in cast/spawn — è SOLO roster boss"
    )

    bud = Budget(
        livello=1, gradi_ammessi=frozenset(_G),
        blocchi_ammessi=frozenset(), archetipo_default="slime",
        archetipi_ammessi=frozenset({"slime"}),
    )
    candidato = turno_h(blocchi=())
    candidato = candidato.model_copy(update={
        "entita": candidato.entita.model_copy(update={"riferimento": boss.slug})
    })

    _e, mappa = mappa_corrente()
    assert mappa.stanza_corrente != stanza_boss_di(zona, mappa.piano)
    assert valida_turno(candidato, bud) is None, (
        "il boss reclutato come riempitivo è FUORI budget: fallback"
    )

    mappa.stanza_corrente = stanza_boss_di(zona, mappa.piano)
    assert valida_turno(candidato, bud) is not None, (
        "nella stanza del custode il riferimento resta legittimo"
    )


# --- B11 · il necrologio fuori-combattimento conserva i momenti -----------------

def test_b11_la_morte_fuori_scontro_eredita_i_momenti(run_pulita, tmp_path) -> None:
    from contracts import EffettoStatus, FattiScontro, Terminale
    from main import costruisci_sessione
    from motore import tick as _tick

    sessione = costruisci_sessione(
        nome="Kora", seed=8, directory=tmp_path,
        stagione=stagione_sintetica(piani=[piano_territoriale(1)], slug="s-necro"),
    )
    asyncio.run(sessione.prossima_narrazione())
    # L'ultimo scontro (chiuso in FUGA) ha avuto i suoi momenti: l'harness
    # li fissa come farebbe l'istanza alla chiusura.
    sessione._fatti_ultimo_scontro = FattiScontro(
        vittoria=False, turni=4, hp_persi=39, nemico="Evil Ash", fuga=True,
        momenti=("primo sangue: il crawler colpisce Evil Ash",),
    )
    # Il DoT morde fuori dallo scontro (l'evento vero del bus)...
    sessione.bus.pubblica(EffettoStatus(bersaglio="", status="brucia", delta_hp=-5))
    # ...e uccide: il death-check del motore pubblica MortePersonaggio.
    protagonista()[2].punti_vita = 0
    _tick()
    assert sessione.guscio.terminale is Terminale.SCONFITTA

    fatti = sessione._fatti_epitaffio
    assert fatti is not None, "la morte fuori-scontro compone i fatti (B11)"
    assert fatti.nemico == "Evil Ash", "l'attribuzione al carnefice regge"
    assert "primo sangue: il crawler colpisce Evil Ash" in fatti.momenti, (
        "i momenti della lotta vera sopravvivono alla fuga"
    )
    assert any("spento dal Brucia" in m for m in fatti.momenti), (
        "la chiusa sintetica dice di cosa sei morto"
    )
    esito = sessione._componi_esito()
    assert esito is not None and esito["causa"] == "Evil Ash"
    assert any("primo sangue" in m for m in esito["momenti"]), (
        "il necrologio in bacheca riceve i momenti"
    )
