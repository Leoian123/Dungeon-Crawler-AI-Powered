"""Pipeline GM (gm.py): budget di chiamate per costruzione, stadi non-gating che
degradano, gate invariato, firma+cache (congela-una-volta-rileggi-sempre), memoria
derivata, stima deterministica, spesa del tempo dal motore, guardia di combattimento,
guardrail del testo libero. Tutto su FakeProvider (FIFO, una risposta per chiamata).
"""

from __future__ import annotations

import asyncio
import random

import esper

from contracts import (
    Durata,
    FattiScontro,
    Flavor,
    Ideazione,
    InquadramentoProva,
    PlayerChoseOption,
    TipoAzione,
    TurnoNarrazione,
)
from motore import (
    Archivio,
    Fase,
    MemoriaTurni,
    PREFISSO_GM,
    PREFISSO_RIFINITURA,
    PROSA_NEUTRA,
    SistemaTempoPiano,
    TIPO_RECORD_GM,
    avvia_run,
    carico_tick,
    crea_mappa,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_tempo_piano,
    esegui_turno_gm,
    firma_turno,
    imposta_fase,
    mob_corrente,
    modula_stima_per_skill,
    prepara_riepilogo,
    stima_azione,
    tempo_piano_corrente,
)
from motore import calibrazione as cal
from main import _turni_scriptati, costruisci_sessione
from provider import FakeProvider
from tests.narr_helpers import coda_azione, coda_post_scontro, coda_reveal


def _arma_run(seed: int = 7) -> None:
    """Un run-World minimo per la pipeline: singleton + mappa + protagonista + sistemi."""
    crea_profondita()
    crea_seme(seed)
    crea_tempo_piano()
    crea_mappa(random.Random(seed))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    avvia_run(crea_singleton_fase=True, fase_iniziale=Fase.NARRAZIONE,
              sempre_attivi=[SistemaTempoPiano()])


def _turno() -> dict:
    return _turni_scriptati()[0].model_dump()


def _idea(intenzione: str = "quiete") -> dict:
    return dict(intenzione=intenzione, tono="ironico", focus="una stanza umida",
                ganci=["gocciolio"], durata_proposta="turno")


def _pipeline(prov, arch=None, mem=None, **kw):
    arch = arch if arch is not None else Archivio(master_seed=7, model_id="test")
    mem = mem if mem is not None else MemoriaTurni()
    esito = asyncio.run(esegui_turno_gm(
        prov, archivio=arch, memoria=mem, rng=random.Random(1), **kw
    ))
    return esito, arch, mem


# --- Budget di chiamate e forma del prompt --------------------------------------

def test_conteggio_e_ordine_chiamate(mondo_isolato) -> None:
    # REVEAL: niente ideazione (non c'è azione da inquadrare) — 3 chiamate secche.
    _arma_run()
    prov = FakeProvider(coda_reveal(_turno(), limata="limata", memoria="riga memoria"))
    esito, _a, _m = _pipeline(prov)
    schemi = [s for _p, s in prov.chiamate]
    assert schemi == [TurnoNarrazione, Flavor, Flavor]
    assert schemi.count(TurnoNarrazione) == 1  # UNA sola chiamata gating (G-22)
    # Struttura I/O per il caching (F §7/H §13): il prefisso statico viaggia nel
    # canale `sistema` (byte-identico per stadio), MAI duplicato nel corpo; le
    # rifiniture (limatura/distillazione) prendono il prefisso CORTO.
    assert prov.sistemi == [PREFISSO_GM, PREFISSO_RIFINITURA, PREFISSO_RIFINITURA]
    assert all(PREFISSO_GM not in p for p, _s in prov.chiamate)
    assert esito.messaggio.prosa == "limata" and not esito.da_cache


def test_prefisso_forte_sopra_soglia_cache() -> None:
    """Fase 4 (review 2026-08-08): il prefisso della corsia FORTE supera
    DELIBERATAMENTE la soglia minima di cache di Opus (1024 token) grazie alla
    guida di stile statica — la cache si attiva sulla chiamata che pesa di più.
    Approssimazione prudente: ~3.5 caratteri/token per l'italiano ⇒ 4300 char
    garantiscono >1024 token con margine."""
    from motore.gm import STILE_CINEMA, prefisso_gm

    assert len(PREFISSO_GM) >= 4300, (
        f"prefisso FORTE sotto soglia di cache: {len(PREFISSO_GM)} char"
    )
    assert STILE_CINEMA in PREFISSO_GM  # la guida vive NEL prefisso statico
    # Byte-identità: stessa run (stessi input) ⇒ stesso prefisso, sempre.
    assert prefisso_gm(None, None) == prefisso_gm(None, None) == PREFISSO_GM


def test_prefisso_rifinitura_snello() -> None:
    """Il prefisso delle rifiniture non trasporta il contratto di gioco né il
    design della run: riscrivere una bozza non li richiede (dieta token)."""
    assert len(PREFISSO_RIFINITURA) < len(PREFISSO_GM)
    for zavorra in ("[stagione", "[piano", "cast", "beneficio", "mappa"):
        assert zavorra not in PREFISSO_RIFINITURA
    assert "numeri" in PREFISSO_RIFINITURA  # la linea rossa F-3 resta anche qui


def test_reveal_non_chiama_ideazione(mondo_isolato) -> None:
    """Dieta token: al reveal l'ideazione non gira MAI (la sua unica influenza
    meccanica — inquadrare una prova — richiede un'azione)."""
    _arma_run()
    prov = FakeProvider(coda_reveal(_turno()))
    _pipeline(prov)
    assert Ideazione not in [s for _p, s in prov.chiamate]


def test_azione_chiama_ideazione_e_lidea_alimenta_la_gating(mondo_isolato) -> None:
    _arma_run()
    prov = FakeProvider(coda_azione(_turno(), limata="limata"))
    esito, _a, _m = _pipeline(prov, azione="frugo tra i detriti")
    schemi = [s for _p, s in prov.chiamate]
    assert schemi == [Ideazione, TurnoNarrazione, Flavor, Flavor]
    assert "[ideazione]" in prov.chiamate[1][0]  # l'idea alimenta il prompt gating
    # Prefisso pieno sugli stadi che decidono, corto sulle rifiniture.
    assert prov.sistemi == [PREFISSO_GM, PREFISSO_GM,
                            PREFISSO_RIFINITURA, PREFISSO_RIFINITURA]
    assert esito.messaggio.prosa == "limata" and not esito.da_cache


def test_ideazione_degrada_senza_retry(mondo_isolato) -> None:
    # Turno-AZIONE (al reveal l'ideazione non gira proprio): degrado silenzioso.
    _arma_run()
    prov = FakeProvider(coda_azione(_turno(), idea=None))
    esito, _a, _m = _pipeline(prov, azione="tasto la parete umida")
    schemi = [s for _p, s in prov.chiamate]
    assert schemi.count(Ideazione) == 1  # nessun retry sugli stadi non-gating
    assert "[ideazione]" not in prov.chiamate[1][0]  # sezione omessa se degradata
    assert not esito.messaggio.fallback
    # Il messaggio resta NORMATIVO: dove+come+tempo+snapshot sempre, prova solo se esiste.
    m = esito.messaggio
    assert m.dove and m.come and m.snapshot and m.prova is None
    assert m.tempo.tick_spesi == carico_tick(Durata.TURNO)


def test_gate_e_fallback_atomico_invariati(mondo_isolato) -> None:
    _arma_run()
    fuori = _turno()
    fuori["entita"]["grado"] = "oro"  # fuori dal budget normale (BRONZO/ARGENTO)
    prov = FakeProvider(coda_reveal(fuori))  # il gate rifiuta ⇒ fallback, SENZA retry
    esito, _a, _m = _pipeline(prov)
    assert esito.messaggio.fallback is True
    assert esito.messaggio.prosa == PROSA_NEUTRA  # limatura degradata ⇒ bozza (neutra)
    assert [s for _p, s in prov.chiamate].count(TurnoNarrazione) == 1  # una sola gating


def test_trasporto_fallito_ritenta_solo_la_gating(mondo_isolato) -> None:
    _arma_run()
    # FIFO vuota: OGNI stadio degrada (trasporto), qualunque sia il loro numero.
    prov = FakeProvider([])
    esito, _a, _m = _pipeline(prov)
    assert esito.messaggio.fallback is True
    assert [s for _p, s in prov.chiamate].count(TurnoNarrazione) == 2  # 1 + 1 retry, mai di più


# --- Firma e cache (H §8: congela-una-volta-rileggi-sempre) ----------------------

def test_firma_stabile_e_distinta() -> None:
    assert firma_turno(7, 1, 3, "reveal") == firma_turno(7, 1, 3, "reveal")
    assert firma_turno(7, 1, 3, "reveal") != firma_turno(7, 1, 4, "reveal")
    assert firma_turno(7, 1, 3, "azione", 5) != firma_turno(7, 1, 3, "azione", 6)
    # Stesso tick, azioni diverse: chiavi diverse (il tick può non avanzare —
    # status unsafe, ingresso in combattimento — e il testo deve discriminare).
    assert (firma_turno(7, 1, 3, "azione", 5, azione="attacco")
            != firma_turno(7, 1, 3, "azione", 5, azione="frugo tra i resti"))
    # Idempotenza della singola unità di turno: stessa azione ⇒ stessa chiave.
    assert (firma_turno(7, 1, 3, "azione", 5, azione="attacco")
            == firma_turno(7, 1, 3, "azione", 5, azione="attacco"))


def test_azioni_diverse_a_tick_fermo_non_collidono(mondo_isolato) -> None:
    """Il bug del record congelato: con ingresso in combattimento il turno spende
    0 tick; l'azione successiva nella stessa stanza NON deve rileggere la prosa
    dell'azione precedente dalla cache."""
    _arma_run()
    prov = FakeProvider(
        coda_azione(_turno(), limata="prosa dell'attacco", memoria="r1")
        + coda_azione(_turno(), limata="prosa del frugare", memoria="r2")
    )
    esito1, arch, mem = _pipeline(
        prov, azione="attacco il mob", ingresso_combattimento=True)
    esito2, _a, _m = _pipeline(
        prov, arch=arch, mem=mem, azione="frugo tra i resti",
        ingresso_combattimento=True)
    assert esito1.da_cache is False and esito2.da_cache is False
    assert esito2.messaggio.prosa != esito1.messaggio.prosa
    # La STESSA azione allo stesso tick invece rilegge (idempotenza, H §8.2).
    n = len(prov.chiamate)
    esito3, _a, _m = _pipeline(
        prov, arch=arch, mem=mem, azione="attacco il mob",
        ingresso_combattimento=True)
    assert esito3.da_cache is True and len(prov.chiamate) == n


def test_cache_rilegge_senza_chiamate(mondo_isolato) -> None:
    _arma_run()
    prov = FakeProvider(coda_reveal(_turno(), limata="limata", memoria="riga"))
    esito1, arch, mem = _pipeline(prov)
    n = len(prov.chiamate)
    esito2, _a, _m = _pipeline(prov, arch=arch, mem=mem)
    assert esito2.da_cache is True and len(prov.chiamate) == n  # ZERO chiamate
    assert esito2.messaggio.prosa == esito1.messaggio.prosa  # la rivisita ri-emette


# --- Memoria: derivata, ricostruibile dall'Archivio ------------------------------

def test_memoria_ricostruita_dall_archivio(mondo_isolato) -> None:
    _arma_run()
    prov = FakeProvider(coda_reveal(_turno(), memoria="C'era uno slime, ora lo sai."))
    _e, arch, mem = _pipeline(prov)
    assert mem.finestra() == ("C'era uno slime, ora lo sai.",)
    ricostruita = MemoriaTurni.ricostruisci(arch)
    assert ricostruita.finestra() == mem.finestra()  # la chat è DERIVATA (H §11)
    assert arch.record_di_tipo(TIPO_RECORD_GM)  # e vive nell'Archivio, non nello stato


# --- Stima dell'azione: deterministica, zero LLM ---------------------------------

def test_stima_deterministica_e_seam_skill(mondo_isolato) -> None:
    _arma_run()
    stima = stima_azione(Durata.UN_POCHINO)
    assert stima.tick == carico_tick(Durata.UN_POCHINO)
    assert stima.forbice == cal.FORBICE_DURATA[Durata.UN_POCHINO]
    assert stima.skill_riferimento is None
    from motore import proietta_scheda, protagonista
    pent, _m, _s = protagonista()
    assert modula_stima_per_skill(stima, proietta_scheda(pent)) == stima  # seam = identità
    riep = prepara_riepilogo("vivisezionare uno slime", TipoAzione.ALTRO, MemoriaTurni())
    assert riep.testo_proposto == "vivisezionare uno slime"
    assert riep.stima.durata == cal.DURATA_AZIONE[TipoAzione.ALTRO]
    assert "stanza" in riep.contesto


# --- Tempo: l'AI propone la Durata, il motore dispone i tick ---------------------

def test_tempo_speso_dal_motore(mondo_isolato) -> None:
    _arma_run()
    turno = _turno()
    turno["durata"] = "un_attimo"
    prov = FakeProvider(coda_reveal(turno))
    prima = tempo_piano_corrente()
    esito, _a, _m = _pipeline(prov)
    speso = esito.messaggio.tempo.tick_spesi
    assert speso == carico_tick(Durata.UN_ATTIMO)
    assert tempo_piano_corrente() == prima + speso  # tick reali, dal calcolatore


def test_ingresso_combattimento_non_spende_tempo(mondo_isolato) -> None:
    _arma_run()
    prov = FakeProvider(coda_reveal(_turno()))
    prima = tempo_piano_corrente()
    esito, _a, _m = _pipeline(prov, ingresso_combattimento=True)
    assert esito.messaggio.tempo.tick_spesi == 0
    assert tempo_piano_corrente() == prima  # il tempo lo brucia il loop di combattimento


# --- La prova SOLO se esiste ------------------------------------------------------

def test_prova_solo_se_esiste_e_tira_il_motore(mondo_isolato) -> None:
    _arma_run()
    prov = FakeProvider(coda_azione(
        _turno(), idea=_idea("prova"), prova=dict(classe="bronzo", stat="destrezza"),
    ))
    esito, _a, _m = _pipeline(prov, azione="scassinare la grata")
    schemi = [s for _p, s in prov.chiamate]
    assert InquadramentoProva in schemi
    assert esito.messaggio.prova is not None
    assert isinstance(esito.messaggio.prova.esito, bool)  # risolta dal MOTORE, seeded


# --- Avanzamento: la pipeline racconta i suoi stadi (per la barra dell'host) -----

def test_avanzamento_monotono_e_completo(mondo_isolato) -> None:
    _arma_run()
    prov = FakeProvider(coda_reveal(_turno(), limata="l", memoria="m"))
    tappe: list[tuple[str, float]] = []
    esito, arch, mem = _pipeline(prov, avanzamento=lambda e, f: tappe.append((e, f)))
    frazioni = [f for _e, f in tappe]
    assert frazioni == sorted(frazioni) and frazioni[-1] == 1.0  # graduale, fino a "Fatto"
    assert all(e for e, _f in tappe)
    # Cache-hit: una sola tappa, subito completa (zero attesa da raccontare).
    tappe.clear()
    esito2, _a, _m = _pipeline(prov, arch=arch, mem=mem,
                               avanzamento=lambda e, f: tappe.append((e, f)))
    assert esito2.da_cache and tappe == [("Il GM rilegge i suoi appunti…", 1.0)]


def test_callback_rotto_non_rompe_il_turno(mondo_isolato) -> None:
    _arma_run()
    prov = FakeProvider(coda_reveal(_turno()))
    def esplode(_e: str, _f: float) -> None:
        raise RuntimeError("host rotto")
    esito, _a, _m = _pipeline(prov, avanzamento=esplode)
    assert not esito.messaggio.fallback  # il racconto è cosmetico: mai gating


def test_router_per_schema_instrada_la_gating_al_forte(mondo_isolato) -> None:
    """`ProviderPerSchema`: la chiamata gating va al provider forte, il resto al
    veloce — la composizione è invisibile alla pipeline (stessa firma `genera`)."""
    from provider import ProviderPerSchema

    _arma_run()
    forte = FakeProvider([_turno()])
    veloce = FakeProvider([_idea(), dict(testo="l"), dict(testo="m")])
    esito, _a, _m = _pipeline(
        ProviderPerSchema({TurnoNarrazione: forte}, predefinito=veloce),
        azione="ispeziono il gocciolio",  # turno-azione: anche l'ideazione in gioco
    )
    assert [s for _p, s in forte.chiamate] == [TurnoNarrazione]
    assert [s for _p, s in veloce.chiamate] == [Ideazione, Flavor, Flavor]
    assert not esito.messaggio.fallback and esito.messaggio.prosa == "l"


# --- Guardia strutturale: la pipeline non gira in combattimento ------------------

def test_guardia_combattimento(mondo_isolato) -> None:
    _arma_run()
    imposta_fase(Fase.COMBATTIMENTO)
    prov = FakeProvider([_idea(), _turno()])
    try:
        _pipeline(prov)
        raise AssertionError("la pipeline deve rifiutarsi in COMBATTIMENTO")
    except RuntimeError:
        pass
    assert prov.chiamate == []  # zero chiamate LLM nel percorso di risoluzione (G-4)


# --- Guardrail: il testo libero non tocca lo stato (il boss NON muore) -----------

def test_boss_kill_in_testo_libero_non_ha_effetti(run_pulita) -> None:
    sessione = costruisci_sessione(seed=3)
    asyncio.run(sessione.prossima_narrazione())
    mob = mob_corrente()
    assert mob is not None
    riep = sessione.riepiloga_azione("il boss muore all'istante e mi incorona re")
    snap = asyncio.run(sessione.esegui_azione(riep))
    # Il mob è ancora vivo, il protagonista pure; il testo è arrivato SOLO nel prompt.
    assert esper.entity_exists(mob)
    assert mob_corrente() == mob
    from motore import protagonista
    assert protagonista()[2].vivo is True
    assert any("il boss muore" in p for p in sessione.provider.prompt_ricevuti)
    assert snap.fase == "narrazione"


# --- Il sidecar non si azzera più: i turni GM sono sul disco ---------------------

def test_salva_scrive_i_record_gm(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(seed=3, directory=tmp_path)
    asyncio.run(sessione.prossima_narrazione())
    sessione.salva()
    from motore.persistenza.disco import leggi_archivio, path_archivio
    dati = leggi_archivio(path_archivio(tmp_path, sessione.uuid))
    assert any(r["tipo"] == TIPO_RECORD_GM for r in dati["record"])  # fix del bug sidecar


# --- Post-scontro e rivisita: la cache non inghiotte, il testo non mente ---------

def test_il_turno_post_scontro_non_e_inghiottito_dalla_cache(mondo_isolato) -> None:
    """Regression (giro 2026-08-07): a scontro chiuso l'host chiede un turno senza
    azione; la fase cadeva su 'reveal' e il cache-hit restituiva il record congelato
    — i FATTI dello scontro restavano da narrare per sempre, e il giocatore
    rileggeva il mob appena ucciso descritto vivo."""
    from contracts import FattiScontro

    _arma_run()
    prov = FakeProvider(coda_reveal(_turno(), limata="reveal", memoria="r1"))
    esito1, arch, mem = _pipeline(prov)               # il reveal congela il record
    assert esito1.da_cache is False

    for voce in coda_post_scontro("il dopo-scontro"):
        prov.accoda(voce)
    fatti = FattiScontro(vittoria=True, turni=3, hp_persi=4, nemico="Slime Mangiascarti")
    esito2, _a, _m = _pipeline(prov, arch=arch, mem=mem, esito_scontro=fatti)
    assert esito2.da_cache is False, "il turno post-scontro è stato inghiottito dalla cache"
    assert esito2.messaggio.prosa == "il dopo-scontro"
    assert any("[fascicolo/esito-scontro]" in p for p, _s in prov.chiamate), (
        "i fatti dello scontro non hanno raggiunto il prompt del turno che li narra"
    )


def test_resoconto_una_sola_chiamata_e_zero_tempo(mondo_isolato) -> None:
    """Fase 5: il turno post-scontro è il ramo RESOCONTO — una sola chiamata
    Flavor (rotta scontro.resoconto), zero ideazione/gating (prima generava
    un'entità mai materializzata), zero tick (il tempo l'ha bruciato il loop)."""
    _arma_run()
    prov = FakeProvider(coda_reveal(_turno(), limata="reveal", memoria="r"))
    _e1, arch, mem = _pipeline(prov)
    n = len(prov.chiamate)

    prov.accoda(dict(testo="chiusura cinematografica"))
    fatti = FattiScontro(vittoria=True, turni=4, hp_persi=2, nemico="Slime Madre",
                         momenti=("primo sangue: il crawler colpisce Slime Madre",))
    prima = tempo_piano_corrente()
    esito, _a, _m = _pipeline(prov, arch=arch, mem=mem, esito_scontro=fatti)
    assert len(prov.chiamate) == n + 1  # UNA chiamata: il resoconto
    assert [s for _p, s in prov.chiamate[n:]] == [Flavor]
    assert TurnoNarrazione not in [s for _p, s in prov.chiamate[n:]]
    assert esito.messaggio.tempo.tick_spesi == 0
    assert tempo_piano_corrente() == prima
    # I momenti raggiungono il prompt; la memoria registra i fatti.
    assert "[scontro/momenti]" in prov.chiamate[-1][0]
    assert "primo sangue" in prov.chiamate[-1][0]
    assert "Slime Madre" in mem.finestra()[-1]


def test_resoconto_congelato_e_riletto_a_zero_chiamate(mondo_isolato) -> None:
    _arma_run()
    prov = FakeProvider(coda_reveal(_turno(), limata="reveal", memoria="r"))
    _e1, arch, mem = _pipeline(prov)
    prov.accoda(dict(testo="chiusura"))
    fatti = FattiScontro(vittoria=True, turni=3, hp_persi=0, nemico="X")
    esito1, _a, _m = _pipeline(prov, arch=arch, mem=mem, esito_scontro=fatti)
    assert esito1.da_cache is False and esito1.messaggio.prosa == "chiusura"
    n = len(prov.chiamate)
    esito2, _a, _m = _pipeline(prov, arch=arch, mem=mem, esito_scontro=fatti)
    assert esito2.da_cache is True and len(prov.chiamate) == n
    assert esito2.messaggio.prosa == "chiusura"


def test_resoconto_degrada_a_template_deterministico(mondo_isolato) -> None:
    _arma_run()
    prov = FakeProvider(coda_reveal(_turno(), limata="reveal", memoria="r"))
    _e1, arch, mem = _pipeline(prov)
    # FIFO vuota: il resoconto degrada al template dai FATTI (mai un turno muto).
    fatti = FattiScontro(vittoria=True, turni=5, hp_persi=7, nemico="Il Regista")
    esito, _a, _m = _pipeline(prov, arch=arch, mem=mem, esito_scontro=fatti)
    assert esito.messaggio.fallback is True
    assert "Il Regista" in esito.messaggio.prosa
    assert "non si rialza" in esito.messaggio.prosa


def test_resoconto_distingue_la_fuga(mondo_isolato) -> None:
    _arma_run()
    prov = FakeProvider(coda_reveal(_turno(), limata="reveal", memoria="r"))
    _e1, arch, mem = _pipeline(prov)
    prov.accoda(dict(testo="via di corsa"))
    fatti = FattiScontro(vittoria=False, turni=2, hp_persi=3, nemico="X", fuga=True)
    esito, _a, _m = _pipeline(prov, arch=arch, mem=mem, esito_scontro=fatti)
    assert "FUGA" in prov.chiamate[-1][0]  # l'istruzione per esito è quella giusta
    assert "fuga" in _m.finestra()[-1]     # la memoria registra l'esito vero
    assert esito.messaggio.tempo.tick_spesi == 0


def test_la_rivisita_di_una_stanza_ripulita_lo_dice(mondo_isolato) -> None:
    """Regression (giro 2026-08-07): la rilettura del reveal congelato descriveva
    il mob morto/dissolto come vivo e in agguato. Ora il motore appende una coda
    deterministica quando il mob del record non è più in scena."""
    from motore import dissolvi_mob

    _arma_run()
    prov = FakeProvider(coda_reveal(_turno(), limata="reveal col mob", memoria="r"))
    esito1, arch, mem = _pipeline(prov)
    nome = _turno()["entita"]["nome"]

    mob = mob_corrente()
    assert mob is not None
    dissolvi_mob()                                     # la stanza è stata ripulita
    n = len(prov.chiamate)
    esito2, _a, _m = _pipeline(prov, arch=arch, mem=mem)
    assert esito2.da_cache is True and len(prov.chiamate) == n  # sempre zero chiamate
    assert nome in esito2.messaggio.prosa
    assert "non c'è più" in esito2.messaggio.prosa, (
        "la stanza ripulita rilegge il mob come vivo: il testo contraddice il mondo"
    )
    # Con il mob ANCORA in scena, invece, il record si rilegge intatto.
    esito_prima = esito1.messaggio.prosa
    assert esito_prima not in ("",) and "non c'è più" not in esito_prima


def test_la_memoria_non_registra_entita_mai_materializzate(mondo_isolato) -> None:
    """Regression (giro 2026-08-07): il riassunto deterministico scriveva
    «Stanza N: {entita.nome}» anche sui turni-azione, dove quell'entità non entra
    mai nel mondo — un fatto falso propagato alla finestra di memoria, congelato
    in Archivio e ricostruito al load."""
    _arma_run()
    prov = FakeProvider(coda_reveal(_turno(), limata="reveal"))  # distilla degradata
    _e1, arch, mem = _pipeline(prov)
    nome = _turno()["entita"]["nome"]
    assert nome in mem.finestra()[-1], "il reveal materializza: il nome VA in memoria"

    for voce in coda_azione(_turno(), idea=None):
        prov.accoda(voce)
    _e2, _a, _m = _pipeline(prov, arch=arch, mem=mem, azione="frugo tra i detriti")
    assert nome not in mem.finestra()[-1], (
        "il turno-azione ha messo in memoria un'entità mai materializzata"
    )
    assert "frugo tra i detriti" in mem.finestra()[-1]


# --- Handoff dello scontro: i FATTI entrano nel fascicolo ------------------------

def test_fatti_scontro_nel_fascicolo(run_pulita) -> None:
    sessione = costruisci_sessione(seed=1)
    asyncio.run(sessione.prossima_narrazione())
    sessione.coda.accoda(PlayerChoseOption(0))  # Combatti
    snap = sessione.avanza()
    assert snap.fase == "combattimento"
    for _ in range(60):  # l'ISTANZA deterministica pilota lo scontro
        sessione.coda.accoda(PlayerChoseOption(0))
        snap = sessione.avanza()
        if snap.fase != "combattimento":
            break
    assert snap.fase == "narrazione"
    assert sessione._fatti_scontro is not None and sessione._fatti_scontro.vittoria
    # Il primo turno GM reale successivo li narra: il fascicolo porta l'esito.
    riep = sessione.riepiloga_azione("riprendo fiato")
    asyncio.run(sessione.esegui_azione(riep))
    assert sessione._fatti_scontro is None  # consumati da un turno non-cache
    assert any("[fascicolo/esito-scontro]" in p for p in sessione.provider.prompt_ricevuti)
