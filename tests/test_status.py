"""Status: shape/rango (G-6), single-owner sempre-attivo (G-5), competizione per
rango (G-7), un componente per tipo + coesistenza (G-8), burn-rate invariante al
numero di nemici (G-24).
"""

from __future__ import annotations

import dataclasses
from contextlib import contextmanager
from pathlib import Path

import esper

from motore import (
    Brucia,
    Combattente,
    Rigenerazione,
    SistemaSempreAttivo,
    SistemaSoloCombattimento,
    SpecNemico,
    Status,
    Veleno,
    applica_status,
    entita_attiva,
    protagonista,
    segna_turno_attivo,
    sistemi_status,
    tick,
)
from tests.combat_helpers import avvia_scontro

_MOTORE = Path(__file__).resolve().parents[1] / "src" / "motore"


# --- G-6: rango: int, nessun riferimento alla fonte ---------------------------

def test_G6_status_porta_rango_e_nessuna_fonte() -> None:
    proibiti = {"fonte", "sorgente", "source", "applicatore", "origine", "entita", "owner"}
    for tipo in (Status, Veleno, Brucia, Rigenerazione):
        nomi = {f.name for f in dataclasses.fields(tipo)}
        assert "rango" in nomi, f"{tipo.__name__} deve portare `rango`"
        assert not (nomi & proibiti), f"{tipo.__name__} non deve referenziare la fonte"
    v = Veleno(rango=3, durata=2)
    assert isinstance(v.rango, int)


# --- G-5: nessun handler di status in solo-combattimento; un solo proprietario -

def test_G5_status_solo_nel_bucket_sempre_attivo() -> None:
    """I system di status vivono nel bucket sempre-attivo, e sono UNO per tipo.

    Verificato sui system DERIVATI dalla tabella (`sistemi_status()`), non su classi
    nominate: gli alias storici `SistemaVeleno`/`SistemaBrucia`/… sono stati ritirati
    proprio perché cablarli *insieme* alla derivazione faceva ticcare due volte lo
    stesso status — un bug silenzioso che raddoppiava il decorso."""
    from motore.status import SistemaStatus, SistemaTregue

    sistemi = sistemi_status()
    assert sistemi, "nessun system di status derivato dalla tabella"
    for sistema in sistemi:
        assert isinstance(sistema, SistemaSempreAttivo)
        assert not isinstance(sistema, SistemaSoloCombattimento)
    # Mappa tipo→sistema INIETTIVA: un solo proprietario per tipo (G-5).
    tipi = [s.tipo_status for s in sistemi if isinstance(s, SistemaStatus)]
    assert len(set(tipi)) == len(tipi), f"due system per lo stesso status: {tipi}"
    assert {Veleno, Brucia, Rigenerazione} <= set(tipi)
    # Il proprietario delle tregue è UNO e corre PRIMA dei tick di status:
    # la tregua aperta da una scadenza non si consuma nello stesso turno
    # (l'ordine è parte del contratto della tregua di scadenza).
    tregue = [s for s in sistemi if isinstance(s, SistemaTregue)]
    assert len(tregue) == 1 and isinstance(sistemi[0], SistemaTregue)


def test_G5_avanzamento_status_solo_in_status_py() -> None:
    # L'avanzamento (mutazione di `durata`) vive SOLO in status.py: i sistemi
    # solo-combattimento non toccano la durata degli status.
    for nome in ("combattimento", "mutazione"):
        src = (_MOTORE / f"{nome}.py").read_text(encoding="utf-8")
        assert "durata" not in src, f"{nome}.py non deve avanzare gli status (durata)"


# --- G-7: competizione per rango ----------------------------------------------

def test_G7_competizione_per_rango(mondo_isolato: str) -> None:
    e = esper.create_entity()

    applica_status(e, Veleno(rango=2, durata=3))
    # Rango più alto → il nuovo VINCE, durata fresca; il residente è cancellato.
    applica_status(e, Veleno(rango=5, durata=10))
    v = esper.component_for_entity(e, Veleno)
    assert (v.rango, v.durata) == (5, 10)
    assert len(esper.get_component(Veleno)) == 1  # una sola istanza

    # Rango più basso → il RESIDENTE vince: rinfresca il timer, NON diluisce il rango.
    v.durata = 2
    applica_status(e, Veleno(rango=1, durata=8))
    v = esper.component_for_entity(e, Veleno)
    assert v.rango == 5            # non diluito dal rango basso
    assert v.durata == 8          # rinfrescato

    # Rango uguale → rinfresca comunque il timer del vincitore.
    v.durata = 1
    applica_status(e, Veleno(rango=5, durata=4))
    assert esper.component_for_entity(e, Veleno).durata == 4


# --- La tregua di scadenza: il contrappeso del lock deterministico -------------

def _giro(sistemi) -> None:
    for sistema in sistemi:
        sistema.run(1)


def test_la_tregua_spezza_il_lock_dello_stordimento(mondo_isolato: str) -> None:
    """Playtest live 2026-08-27: l'Usciere stordiva a ogni colpo base e il
    giocatore è morto 34→0 agendo UNA volta — col risolutore deterministico
    (niente proc) lo stun-sul-colpo è un lock perpetuo per costruzione. La
    tregua di scadenza (tabella + §11) garantisce il respiro: dopo la
    scadenza, lo stesso status è rifiutato per `STATUS.tregua_negazione`
    turni — qui il ciclo dell'Usciere diventa stordito/agisci/agisci."""
    from motore.status import Stordito, afflizione
    from motore.status import TregueStatus

    e = esper.create_entity()
    segna_turno_attivo(e)
    sistemi = sistemi_status()

    agiti = 0
    storia = []
    for _round in range(9):
        # Il turno del nemico: il colpo base porta SEMPRE lo stordimento.
        applica_status(e, afflizione(Stordito, 1))
        # Il turno dell'entità: stordita = salta; libera = agisce.
        stordita = esper.try_component(e, Stordito) is not None
        storia.append("salta" if stordita else "agisce")
        if not stordita:
            agiti += 1
        _giro(sistemi)
    # Senza tregua la storia era ["salta"] * 9 (il log del playtest). Con la
    # tregua a 2 (default §11) il ciclo è salta/agisce/agisce.
    assert agiti >= 5, f"il lock non è spezzato: {storia}"
    assert storia[:6] == ["salta", "agisce", "agisce", "salta", "agisce", "agisce"]
    # E il rifiuto è pulito: nei turni in cui agisce, il componente Stordito
    # NON esiste (nessun falso «stordito» nei descrittori della proiezione) —
    # la tregua vive nel suo componente, non in uno status fantasma.
    assert not esper.has_component(e, Stordito)
    # E la tregua si ripulisce da sola: a fine ciclo (finestra consumata al
    # round 9) il componente contabile non resta appeso all'entità.
    assert not esper.has_component(e, TregueStatus)


def test_la_tregua_e_una_foglia_di_calibrazione(mondo_isolato: str, monkeypatch) -> None:
    """`STATUS.tregua_negazione = 0` (§11) = comportamento storico: nessuna
    tregua, lo stordimento riattacca subito — la leva è calibrazione."""
    from motore import calibrazione
    from motore.status import Stordito, afflizione

    monkeypatch.setitem(calibrazione._OVERRIDE, "STATUS.tregua_negazione", 0)
    e = esper.create_entity()
    segna_turno_attivo(e)
    sistemi = sistemi_status()
    applica_status(e, afflizione(Stordito, 1))
    _giro(sistemi)  # scade: durata 1 → 0, nessuna tregua aperta
    assert applica_status(e, afflizione(Stordito, 1)) is True, (
        "a tregua spenta lo stordimento riattacca come da storico"
    )


def test_la_tregua_non_tocca_gli_status_di_danno(mondo_isolato: str) -> None:
    """La tregua vale SOLO per chi la dichiara in tabella (nega-azione): il
    veleno rientra subito — rifiutarlo cambierebbe il bilanciamento dei DoT."""
    from motore.status import afflizione

    e = esper.create_entity()
    segna_turno_attivo(e)
    sistemi = sistemi_status()
    applica_status(e, Veleno(rango=1, durata=1))
    _giro(sistemi)  # scade
    assert not esper.has_component(e, Veleno)
    assert applica_status(e, afflizione(Veleno, 1)) is True


def test_la_capacita_innata_ignora_la_tregua(mondo_isolato: str) -> None:
    """La tregua rifiuta le AFFLIZIONI, mai l'attaccarsi di una CAPACITÀ
    innata (il blocco del catalogo al reveal non è un colpo subito)."""
    from motore.status import Stordito, afflizione

    e = esper.create_entity()
    segna_turno_attivo(e)
    sistemi = sistemi_status()
    applica_status(e, afflizione(Stordito, 1))
    _giro(sistemi)  # scade → tregua aperta
    assert applica_status(e, afflizione(Stordito, 1)) is False  # afflizione: rifiutata
    assert applica_status(e, Stordito(rango=1, durata=1, innato=True)) is True


# --- G-8: un componente per tipo; tipi diversi coesistono e ticcano in parallelo

def test_G8_un_per_tipo_e_coesistenza(mondo_isolato: str) -> None:
    e = esper.create_entity()
    applica_status(e, Veleno(rango=2, durata=3))
    applica_status(e, Veleno(rango=4, durata=3))  # stesso tipo → resta UNA istanza
    assert sum(1 for ent, _ in esper.get_component(Veleno) if ent == e) == 1

    applica_status(e, Brucia(rango=1, durata=2))  # tipo diverso → coesiste
    assert esper.has_component(e, Veleno) and esper.has_component(e, Brucia)

    # Tick in parallelo sui due tipi (l'entità è quella attiva).
    segna_turno_attivo(e)
    for sistema in sistemi_status():          # un giro di tutti i tick, come in run
        sistema.run(1)
    assert esper.component_for_entity(e, Veleno).durata == 2  # 3 → 2
    assert esper.component_for_entity(e, Brucia).durata == 1  # 2 → 1


# --- La FINE di uno status si narra come l'inizio ------------------------------

def test_la_fine_di_uno_status_viene_narrata(mondo_isolato: str) -> None:
    """Regression (giro 2026-08-07): il giocatore leggeva «Sei avvelenato!» e i
    tick «-1 HP», mai QUANDO il veleno finiva — la scadenza rimuoveva il
    componente in silenzio."""
    from contracts import BusEventi, StatusSvanito

    e = esper.create_entity()
    applica_status(e, Veleno(rango=1, durata=1))
    segna_turno_attivo(e)
    bus = BusEventi()
    visti: list[StatusSvanito] = []
    bus.registra(StatusSvanito, visti.append)
    try:
        for sistema in sistemi_status(bus):
            sistema.run(1)
    finally:
        bus.deregistra(StatusSvanito, visti.append)
    assert not esper.has_component(e, Veleno)
    assert visti and visti[-1].status == "veleno", (
        "lo status è scaduto senza che nessun evento lo raccontasse"
    )


# --- G-24: burn-rate invariante al numero di nemici ---------------------------

@contextmanager
def _mondo(nome: str):
    esper.switch_world(nome)
    try:
        yield
    finally:
        esper.switch_world("default")
        esper.delete_world(nome)


def _turni_prot_per_esaurire_veleno(*, nemici_n: int, cariche: int) -> int:
    avvia_scontro(
        nemici=[SpecNemico(destrezza=5, punti_vita=10**9) for _ in range(nemici_n)],
        hp_prot=10**9, destrezza_prot=10, seed=7,
    )
    pent, _marker, _scheda = protagonista()
    applica_status(pent, Veleno(rango=1, durata=cariche))

    turni = 0
    for _ in range(1000):
        if not esper.has_component(pent, Veleno):
            break
        tick()
        if entita_attiva() == pent:  # un turno del protagonista appena risolto
            turni += 1
    return turni


def test_G24_burn_rate_invariante_al_numero_di_nemici() -> None:
    with _mondo("g24-1v1"):
        t_1v1 = _turni_prot_per_esaurire_veleno(nemici_n=1, cariche=3)
    with _mondo("g24-1v3"):
        t_1v3 = _turni_prot_per_esaurire_veleno(nemici_n=3, cariche=3)

    # "3 cariche" dura 3 turni del protagonista, sia in 1-vs-1 sia in 1-vs-3.
    assert t_1v1 == 3
    assert t_1v3 == 3
