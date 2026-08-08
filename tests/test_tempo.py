"""Modello del tempo (nodo J): scorrimento, dado-evento, fast-forward, passa-turno.
Criteri J-1…J-17. Headless, seeded.
"""

from __future__ import annotations

import ast
import random
from pathlib import Path

import esper
import pytest

from contracts import (
    BusEventi,
    CombatResolved,
    Durata,
    EncounterStarted,
    MortePersonaggio,
)
from motore import (
    Confusione,
    Fase,
    PROB_IMBOSCATA,
    PianoIncontro,
    Risoluzione,
    SistemaDeathCheck,
    sistemi_status,
    SistemaDiscesa,
    SistemaRinforzi,
    SistemaTempoPiano,
    SistemaTurnoCombattimento,
    SpecNemico,
    TempoNonAvanzabile,
    Valenza,
    Veleno,
    applica_status,
    avvia_run,
    carico_tick,
    collega_combattimento,
    collega_transizioni_fase,
    crea_entita_fase,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_tempo_piano,
    e_dannoso,
    e_unsafe,
    fast_forward,
    fallback_turno,
    gate_durata,
    leggi_fase,
    passa_turno,
    protagonista,
    puo_downtime,
    puo_passare_turno,
    tempo_piano_corrente,
    tira_dado_evento,
    valenza_di,
)
from motore import catalogo as C
from tests.narr_helpers import budget

_SRC = Path(__file__).resolve().parents[1] / "src"
_MOTORE = _SRC / "motore"


# --- Arnia di esplorazione: singleton + protagonista + sistemi registrati ------

def _avvia_esplorazione(*, seed: int = 42, hp: int = 30, destrezza: int = 10):
    bus = BusEventi()
    crea_entita_fase(Fase.NARRAZIONE)
    crea_profondita()
    crea_tempo_piano()
    crea_seme(seed)
    pent = crea_protagonista(destrezza=destrezza, punti_vita=hp)
    avvia_run(
        sempre_attivi=[
            # DERIVATI dalla tabella unica (come il guscio vero): un status nuovo
            # entra da sé, e non c'è modo di cablarne due volte lo stesso.
            *sistemi_status(),
            SistemaDeathCheck(bus), SistemaTempoPiano(),
        ],
        solo_combattimento=[SistemaRinforzi(), SistemaTurnoCombattimento(bus)],
        solo_narrazione=[SistemaDiscesa(bus)],
        crea_singleton_fase=False,
    )
    collega_transizioni_fase(bus)
    collega_combattimento(bus)
    return bus, pent


def _seed_dado(*, imboscata: bool, tick: int = 1) -> int:
    """Trova un master_seed per cui il dado a `tick` dà (o non dà) imboscata."""
    for s in range(10_000):
        scatta = random.Random(f"{s}:{tick}").random() < PROB_IMBOSCATA
        if scatta == imboscata:
            return s
    raise AssertionError("nessun seed trovato")


# --- J-1: Durata vocabolario in contracts; mappa nel catalogo del motore -------

def test_J1_durata_vocabolario_in_contracts_mappa_nel_motore() -> None:
    # I valori dell'enum sono stringhe (vocabolario), non numeri.
    for d in Durata:
        assert isinstance(d.value, str) and not isinstance(d.value, (int, float))
    # La mappa Durata→tick vive nel MOTORE (catalogo la riespone da `calibrazione`, §11),
    # non in contracts né sul componente.
    assert hasattr(C, "CARICO_TICK")
    from contracts import schema as S

    assert not hasattr(S, "CARICO_TICK") and not hasattr(S, "carico_tick")


def test_J1_carico_tick_monotono_non_decrescente() -> None:
    # TURNO = minimo (cadenza base); non-decrescente sull'ordine totale di Durata (§3.1).
    ordinate = sorted(Durata, key=lambda d: d.ordine)
    carichi = [carico_tick(d) for d in ordinate]
    assert carichi[0] == carico_tick(Durata.TURNO)
    assert carichi == sorted(carichi)  # non-decrescente
    assert min(carichi) == carico_tick(Durata.TURNO)


# --- J-2: durata solo su TurnoNarrazione, mai su Flavor ------------------------

def test_J2_durata_solo_su_turno_narrazione() -> None:
    from contracts import Flavor, TurnoNarrazione

    assert TurnoNarrazione.model_fields["durata"].annotation is Durata
    assert "durata" not in Flavor.model_fields


# --- J-3: la durata passa per un gate (mai diretto); identità nell'MVP ---------

def test_J3_gate_durata_e_identita_nell_mvp() -> None:
    for d in Durata:
        assert gate_durata(d) == carico_tick(d)  # identità (MVP)
    # Il gate è il punto d'innesto: i meccanismi di scorrimento lo usano (verificato sotto).
    src = (_MOTORE / "tempo.py").read_text(encoding="utf-8")
    assert "gate_durata" in src  # fast_forward passa per il gate


# --- J-4: nessun avanzamento a orologio (no sleep/timer) -----------------------

def test_J4_nessun_avanzamento_a_orologio() -> None:
    for py in _MOTORE.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for nodo in ast.walk(tree):
            if isinstance(nodo, ast.Attribute) and nodo.attr in ("sleep",):
                # né time.sleep né asyncio.sleep nel motore (avanzamento solo per tick).
                raise AssertionError(f"{py.name}: uso di .sleep (avanzamento a orologio?)")
            if isinstance(nodo, ast.Import):
                for a in nodo.names:
                    assert a.name.split(".")[0] != "threading", py.name


# --- J-5: J non avanza gli status per conto suo --------------------------------

def test_J5_tempo_non_muta_gli_status() -> None:
    # Il modulo tempo non scrive sui campi degli status: chiama process(), e l'unico
    # proprietario (bucket sempre-attivo) li avanza.
    src = (_MOTORE / "tempo.py").read_text(encoding="utf-8")
    assert ".durata -=" not in src and ".durata =" not in src
    assert "esper.process()" in src  # delega l'avanzamento al giro dei sistemi


def test_J5_burn_rate_per_stanza_in_esplorazione(mondo_isolato: str) -> None:
    # Cadenza per-stanza: un Veleno "3 cariche" dura 3 tick di scorrimento (3 stanze).
    bus, pent = _avvia_esplorazione(seed=_seed_dado(imboscata=False))
    applica_status(pent, Veleno(rango=2, durata=3))
    for atteso in (2, 1, 0):
        passa_turno(bus)  # nessun callback → l'eventuale dado non flippa
        v = esper.try_component(pent, Veleno)
        rimasta = v.durata if v is not None else 0
        assert rimasta == atteso
    assert esper.try_component(pent, Veleno) is None  # scaduto dopo 3 stanze


# --- J-6: fast-forward (downtime) — precondizioni, compressione, interruzione ---

def test_J6_fast_forward_pulito_comprime_n_tick(mondo_isolato: str) -> None:
    bus, _pent = _avvia_esplorazione(seed=_seed_dado(imboscata=False))
    t0 = tempo_piano_corrente()
    ris = fast_forward(bus, Durata.UN_BEL_PO)  # 8 tick
    assert ris.tick_eseguiti == carico_tick(Durata.UN_BEL_PO) == 8
    assert ris.interrotto_da is None
    assert tempo_piano_corrente() == t0 + 8  # tick eseguiti reali (atomico)


def test_J6_fast_forward_bloccato_da_status_dannoso(mondo_isolato: str) -> None:
    bus, pent = _avvia_esplorazione()
    applica_status(pent, Veleno(rango=1, durata=5))  # DANNOSO
    assert puo_downtime() is False
    with pytest.raises(TempoNonAvanzabile):
        fast_forward(bus, Durata.TURNO)


def test_J6_fast_forward_bloccato_da_status_unsafe(mondo_isolato: str) -> None:
    bus, pent = _avvia_esplorazione()
    applica_status(pent, Confusione(rango=1, durata=5))  # unsafe (AI)
    assert puo_downtime() is False
    with pytest.raises(TempoNonAvanzabile):
        fast_forward(bus, Durata.UN_BEL_PO)


def test_J6_fast_forward_interrotto_da_morte(mondo_isolato: str) -> None:
    bus, pent = _avvia_esplorazione(seed=_seed_dado(imboscata=False), hp=30)
    _p, _m, scheda = protagonista()
    scheda.punti_vita = 0  # il primo tick: death-check → morte → tronca
    ris = fast_forward(bus, Durata.UN_BEL_PO)
    assert ris.interrotto_da == "morte"
    assert ris.tick_eseguiti == 1  # si ferma al tick della morte
    assert protagonista()[2].vivo is False


# --- J-7: passa-turno — un tick; unsafe blocca, dannoso-motore no --------------

def test_J7_passa_turno_avanza_un_tick(mondo_isolato: str) -> None:
    bus, _pent = _avvia_esplorazione(seed=_seed_dado(imboscata=False))
    t0 = tempo_piano_corrente()
    passa_turno(bus)
    assert tempo_piano_corrente() == t0 + 1


def test_J7_dannoso_motore_non_blocca_passa_turno(mondo_isolato: str) -> None:
    bus, pent = _avvia_esplorazione(seed=_seed_dado(imboscata=False))
    applica_status(pent, Veleno(rango=1, durata=5))  # DANNOSO ma risoluzione MOTORE
    assert puo_passare_turno() is True  # NON bloccato: è lì che serve (far scorrere)
    t0 = tempo_piano_corrente()
    passa_turno(bus)
    assert tempo_piano_corrente() == t0 + 1


def test_J7_unsafe_blocca_passa_turno(mondo_isolato: str) -> None:
    bus, pent = _avvia_esplorazione()
    applica_status(pent, Confusione(rango=1, durata=5))  # unsafe
    assert puo_passare_turno() is False
    with pytest.raises(TempoNonAvanzabile):
        passa_turno(bus)


# --- J-8: passa-turno non è una `genera` --------------------------------------

def test_J8_passa_turno_non_e_una_genera() -> None:
    src = (_MOTORE / "tempo.py").read_text(encoding="utf-8")
    assert "genera(" not in src  # nessuna chiamata al provider
    tree = ast.parse(src)
    for nodo in ast.walk(tree):
        if isinstance(nodo, ast.ImportFrom) and nodo.module:
            assert nodo.module.split(".")[0] != "provider", "tempo non importa il provider"


# --- J-9: valenza/risoluzione = flag di TIPO nel catalogo, non sul componente --

def test_J9_flag_status_nel_catalogo_non_sul_componente() -> None:
    import dataclasses

    # I componenti-status portano {rango, durata, innato}: nessun campo
    # valenza/risoluzione (quelli sono flag di TIPO, nel catalogo). `innato` è
    # stato d'ISTANZA (capacità del mob vs afflizione subita), non un flag di tipo.
    for tipo in (Veleno, Confusione):
        campi = {f.name for f in dataclasses.fields(tipo)}
        assert campi == {"rango", "durata", "innato"}
    # I flag vivono nel catalogo (mappa di tipo).
    assert hasattr(C, "FLAG_STATUS")


def test_J9_valenza_esplicita_non_da_delta() -> None:
    # Stordito non ha delta-HP ma è DANNOSO: la valenza è un flag esplicito, non da delta<0.
    from motore import Stordito

    assert valenza_di(Stordito) is Valenza.DANNOSO
    assert e_dannoso(Stordito) is True
    # Confusione è unsafe (risoluzione AI); Veleno è MOTORE.
    assert e_unsafe(Confusione) is True
    from motore import risoluzione_di

    assert risoluzione_di(Veleno) is Risoluzione.MOTORE


def test_J9_flag_non_alterano_lo_stacking(mondo_isolato: str) -> None:
    # La presenza dei flag (nel catalogo) non cambia la competizione per rango (G-7).
    _bus, pent = _avvia_esplorazione()
    applica_status(pent, Veleno(rango=1, durata=2))
    applica_status(pent, Veleno(rango=3, durata=5))  # rango più alto vince
    v = esper.component_for_entity(pent, Veleno)
    assert v.rango == 3 and v.durata == 5
    assert len([1 for _e, _c in esper.get_component(Veleno)]) == 1  # un'istanza per tipo


# --- J-10: dado-evento seeded, replay-safe ------------------------------------

def test_J10_dado_seeded_deterministico() -> None:
    a = tira_dado_evento(random.Random("42:1"))
    b = tira_dado_evento(random.Random("42:1"))
    assert a == b  # stesso seed → stesso esito
    diversi = tira_dado_evento(random.Random("43:1"))
    assert isinstance(diversi.imboscata, bool)


# --- J-11 / J-12: morte tronca prima del dado; imboscata solo a confine, su vivo

def test_J11_morte_tronca_prima_del_dado(mondo_isolato: str) -> None:
    # Anche con un callback d'imboscata pronto, se il tick uccide NON si tira il dado:
    # il callback non viene chiamato (niente imboscata su un cadavere).
    bus, pent = _avvia_esplorazione(seed=_seed_dado(imboscata=True))
    _p, _m, scheda = protagonista()
    scheda.punti_vita = 0
    chiamato = []
    ris = passa_turno(bus, componi_imboscata=lambda: chiamato.append(1) or 999)
    assert ris.morte is True and ris.imboscata is False
    assert chiamato == []  # dado NON tirato: la morte ha troncato


def test_J12_imboscata_emette_encounter_a_confine(mondo_isolato: str) -> None:
    seed = _seed_dado(imboscata=True)  # il dado scatta al tick 1
    bus, _pent = _avvia_esplorazione(seed=seed)
    eventi: list = []
    bus.registra(EncounterStarted, eventi.append)

    def _componi() -> int:
        return esper.create_entity(PianoIncontro(nemici=[SpecNemico(destrezza=5, punti_vita=3)], seed=1))

    assert leggi_fase() is Fase.NARRAZIONE
    ris = passa_turno(bus, componi_imboscata=_componi)
    assert ris.imboscata is True
    assert len(eventi) == 1  # EncounterStarted emesso a confine di tick
    # Flip a COMBATTIMENTO + materializzazione (FNC §4/§6.3).
    from motore import Nemico

    assert leggi_fase() is Fase.COMBATTIMENTO
    assert len(esper.get_component(Nemico)) == 1


# --- J-13: in combattimento passa-turno/fast-forward disabilitati -------------

def test_J13_scorrimento_disabilitato_in_combattimento(mondo_isolato: str) -> None:
    bus, _pent = _avvia_esplorazione(seed=_seed_dado(imboscata=True))

    def _componi() -> int:
        return esper.create_entity(PianoIncontro(nemici=[SpecNemico(destrezza=5, punti_vita=3)], seed=1))

    passa_turno(bus, componi_imboscata=_componi)  # innesca l'imboscata → COMBATTIMENTO
    assert leggi_fase() is Fase.COMBATTIMENTO
    # Predicati-safe falsi automaticamente, senza logica dedicata.
    assert puo_passare_turno() is False and puo_downtime() is False
    with pytest.raises(TempoNonAvanzabile):
        passa_turno(bus)
    with pytest.raises(TempoNonAvanzabile):
        fast_forward(bus, Durata.TURNO)


# --- J-14: tempo-piano = un solo proprietario, sempre-attivo ------------------

def test_J14_tempo_piano_un_solo_proprietario() -> None:
    # SistemaTempoPiano è sempre-attivo (entrambe le fasi).
    assert SistemaTempoPiano().fasi_attive == frozenset({Fase.NARRAZIONE, Fase.COMBATTIMENTO})
    # Nessun altro modulo del motore muta TempoPiano.tick.
    offese = []
    for py in _MOTORE.rglob("*.py"):
        if py.name in ("tempo.py", "piano.py"):
            continue  # tempo.py: il proprietario; piano.py: definizione/reader del dato
        src = py.read_text(encoding="utf-8")
        if "TempoPiano" in src and ".tick" in src:
            offese.append(py.name)
    assert offese == [], f"altri muta-tempo-piano: {offese}"


def test_J14_tempo_piano_avanza_in_combattimento(mondo_isolato: str) -> None:
    # Vivendo nel bucket sempre-attivo, il contatore avanza al tick condiviso anche in
    # combattimento (uno scontro lungo brucia tempo-piano, §10).
    bus, _pent = _avvia_esplorazione(seed=_seed_dado(imboscata=False))
    enc = esper.create_entity(PianoIncontro(nemici=[SpecNemico(destrezza=5, punti_vita=10**9)], seed=1))
    bus.pubblica(EncounterStarted(entita=enc))
    assert leggi_fase() is Fase.COMBATTIMENTO
    from motore import tick

    t0 = tempo_piano_corrente()
    tick()  # un turno di combattimento risolto
    assert tempo_piano_corrente() > t0  # avanzato anche in combattimento


# --- J-15: nessun cap di tempo nella 1.0 --------------------------------------

def test_J15_nessun_cap_il_contatore_non_gatekeepa(mondo_isolato: str) -> None:
    bus, _pent = _avvia_esplorazione(seed=_seed_dado(imboscata=False))
    for _ in range(20):
        passa_turno(bus)  # il contatore cresce…
    assert tempo_piano_corrente() >= 20
    # …e non blocca nulla: il passa-turno resta disponibile a qualunque valore.
    assert puo_passare_turno() is True
    passa_turno(bus)


# --- J-16: durata del fallback designata e deterministica ---------------------

def test_J16_fallback_durata_designata_deterministica() -> None:
    a = fallback_turno(budget())
    b = fallback_turno(budget())
    assert a.turno.durata is Durata.TURNO  # designata, non pescata
    assert a.turno.durata == b.turno.durata  # deterministica (nessun RNG)


# --- J-17: core condiviso in entrambe le fasi; dado/effetto NON in combat ------

def test_J17_dado_non_cablato_nel_loop_di_combattimento() -> None:
    # combattimento.py NON tira il dado-evento né importa lo strato di scorrimento.
    src = (_MOTORE / "combattimento.py").read_text(encoding="utf-8")
    assert "tira_dado_evento" not in src and "dado" not in src.lower()
    tree = ast.parse(src)
    for nodo in ast.walk(tree):
        if isinstance(nodo, ast.ImportFrom) and nodo.module:
            assert nodo.module.split(".")[-1] != "tempo", "combattimento non importa lo scorrimento"
