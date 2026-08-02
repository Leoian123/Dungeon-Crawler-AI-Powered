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
    _arma_run()
    prov = FakeProvider([_idea(), _turno(), dict(testo="limata"), dict(testo="riga memoria")])
    esito, _a, _m = _pipeline(prov)
    schemi = [s for _p, s in prov.chiamate]
    assert schemi == [Ideazione, TurnoNarrazione, Flavor, Flavor]
    assert schemi.count(TurnoNarrazione) == 1  # UNA sola chiamata gating (G-22)
    # Struttura I/O per il caching (F §7/H §13): il prefisso statico viaggia nel
    # canale `sistema` (byte-identico su OGNI chiamata), MAI duplicato nel corpo.
    assert prov.sistemi == [PREFISSO_GM] * 4
    assert all(PREFISSO_GM not in p for p, _s in prov.chiamate)
    assert "[ideazione]" in prov.chiamate[1][0]  # l'idea alimenta il prompt gating
    assert esito.messaggio.prosa == "limata" and not esito.da_cache


def test_ideazione_degrada_senza_retry(mondo_isolato) -> None:
    _arma_run()
    prov = FakeProvider([None, _turno(), None, None])
    esito, _a, _m = _pipeline(prov)
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
    prov = FakeProvider([None, fuori, None, None])  # il gate rifiuta ⇒ fallback, SENZA retry
    esito, _a, _m = _pipeline(prov)
    assert esito.messaggio.fallback is True
    assert esito.messaggio.prosa == PROSA_NEUTRA  # limatura degradata ⇒ bozza (neutra)
    assert [s for _p, s in prov.chiamate].count(TurnoNarrazione) == 1  # una sola gating


def test_trasporto_fallito_ritenta_solo_la_gating(mondo_isolato) -> None:
    _arma_run()
    # Ideazione None + gating None due volte (1 + 1 retry) + ancillari degradati.
    prov = FakeProvider([None, None, None, None, None])
    esito, _a, _m = _pipeline(prov)
    assert esito.messaggio.fallback is True
    assert [s for _p, s in prov.chiamate].count(TurnoNarrazione) == 2  # 1 + 1 retry, mai di più


# --- Firma e cache (H §8: congela-una-volta-rileggi-sempre) ----------------------

def test_firma_stabile_e_distinta() -> None:
    assert firma_turno(7, 1, 3, "reveal") == firma_turno(7, 1, 3, "reveal")
    assert firma_turno(7, 1, 3, "reveal") != firma_turno(7, 1, 4, "reveal")
    assert firma_turno(7, 1, 3, "azione", 5) != firma_turno(7, 1, 3, "azione", 6)


def test_cache_rilegge_senza_chiamate(mondo_isolato) -> None:
    _arma_run()
    prov = FakeProvider([_idea(), _turno(), dict(testo="limata"), dict(testo="riga")])
    esito1, arch, mem = _pipeline(prov)
    n = len(prov.chiamate)
    esito2, _a, _m = _pipeline(prov, arch=arch, mem=mem)
    assert esito2.da_cache is True and len(prov.chiamate) == n  # ZERO chiamate
    assert esito2.messaggio.prosa == esito1.messaggio.prosa  # la rivisita ri-emette


# --- Memoria: derivata, ricostruibile dall'Archivio ------------------------------

def test_memoria_ricostruita_dall_archivio(mondo_isolato) -> None:
    _arma_run()
    prov = FakeProvider([None, _turno(), None, dict(testo="C'era uno slime, ora lo sai.")])
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
    prov = FakeProvider([None, turno, None, None])
    prima = tempo_piano_corrente()
    esito, _a, _m = _pipeline(prov)
    speso = esito.messaggio.tempo.tick_spesi
    assert speso == carico_tick(Durata.UN_ATTIMO)
    assert tempo_piano_corrente() == prima + speso  # tick reali, dal calcolatore


def test_ingresso_combattimento_non_spende_tempo(mondo_isolato) -> None:
    _arma_run()
    prov = FakeProvider([None, _turno(), None, None])
    prima = tempo_piano_corrente()
    esito, _a, _m = _pipeline(prov, ingresso_combattimento=True)
    assert esito.messaggio.tempo.tick_spesi == 0
    assert tempo_piano_corrente() == prima  # il tempo lo brucia il loop di combattimento


# --- La prova SOLO se esiste ------------------------------------------------------

def test_prova_solo_se_esiste_e_tira_il_motore(mondo_isolato) -> None:
    _arma_run()
    prov = FakeProvider([
        _idea("prova"), _turno(), dict(classe="bronzo", stat="destrezza"), None, None,
    ])
    esito, _a, _m = _pipeline(prov, azione="scassinare la grata")
    schemi = [s for _p, s in prov.chiamate]
    assert InquadramentoProva in schemi
    assert esito.messaggio.prova is not None
    assert isinstance(esito.messaggio.prova.esito, bool)  # risolta dal MOTORE, seeded


# --- Avanzamento: la pipeline racconta i suoi stadi (per la barra dell'host) -----

def test_avanzamento_monotono_e_completo(mondo_isolato) -> None:
    _arma_run()
    prov = FakeProvider([_idea(), _turno(), dict(testo="l"), dict(testo="m")])
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
    prov = FakeProvider([None, _turno(), None, None])
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
    esito, _a, _m = _pipeline(ProviderPerSchema({TurnoNarrazione: forte}, predefinito=veloce))
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
    dati = leggi_archivio(path_archivio(tmp_path, "carl"))
    assert any(r["tipo"] == TIPO_RECORD_GM for r in dati["record"])  # fix del bug sidecar


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
