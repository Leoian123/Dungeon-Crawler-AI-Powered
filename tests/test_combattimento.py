"""Loop di combattimento: AP (G-1), iniziativa (G-3), decisione nemici (G-4),
death-check (G-11), entità effimere (FNC §6.3). Headless, seeded.
"""

from __future__ import annotations

import ast
import random
import re
from pathlib import Path

import esper

from contracts import CombatResolved, EncounterStarted, MortePersonaggio, StatId
from motore import (
    Combattente,
    Fase,
    G_GRAZE,
    Nemico,
    Primarie,
    PuntiVita,
    SpecNemico,
    StatoCombattimento,
    calcola_iniziativa,
    check1,
    decidi_azione_nemico,
    esito_contest,
    leggi_fase,
    protagonista,
    tick,
)
from tests.combat_helpers import avvia_scontro

_MOTORE = Path(__file__).resolve().parents[1] / "src" / "motore"


class _RngScript:
    """RNG-spia deterministico: conta le `.random()` e restituisce valori scriptati."""

    def __init__(self, valori: list[float]) -> None:
        self._valori = list(valori)
        self.chiamate = 0

    def random(self) -> float:
        self.chiamate += 1
        return self._valori.pop(0)


# --- G-1: il loop è scritto AP-driven (`while ap > 0`) ------------------------

def test_G1_loop_e_ap_driven() -> None:
    src = (_MOTORE / "combattimento.py").read_text(encoding="utf-8")
    assert re.search(r"while\s+\w+\.ap\s*>\s*0", src), (
        "il loop di combattimento deve essere scritto AP-driven: `while ...ap > 0`"
    )


# --- G-3: iniziativa, tiebreak su chiave stabile (mai id entità esper) --------

def test_G3_iniziativa_destrezza_poi_chiave() -> None:
    # (entita, destrezza, chiave_ordine). 102 ha destrezza più alta → primo.
    # 100 e 101 pari destrezza → tiebreak su chiave: 101 (chiave 1) prima di 100 (chiave 2).
    combattenti = [(100, 5, 2), (101, 5, 1), (102, 7, 9)]
    assert calcola_iniziativa(combattenti) == [102, 101, 100]


def test_G3_tiebreak_non_usa_id_entita() -> None:
    # id entità 1 (basso) ma chiave 9 (alta); id 999 (alto) ma chiave 1 (bassa).
    # Se il tiebreak usasse l'id, vincerebbe 1; usa la chiave → vince 999.
    combattenti = [(1, 5, 9), (999, 5, 1)]
    assert calcola_iniziativa(combattenti) == [999, 1]


# --- G-4: decisione dei nemici prodotta dal motore, seeded; nessun LLM --------

def test_G4_decisione_nemico_seeded_deterministica() -> None:
    bersagli = [10, 20, 30]
    seq_a = [decidi_azione_nemico(random.Random(42), bersagli) for _ in range(1)]
    # Stessa sequenza di estrazioni da uno stesso RNG seeded → identica.
    r1, r2 = random.Random(7), random.Random(7)
    s1 = [decidi_azione_nemico(r1, bersagli) for _ in range(50)]
    s2 = [decidi_azione_nemico(r2, bersagli) for _ in range(50)]
    assert s1 == s2
    # Seed diverso → sequenza diversa (su 50 estrazioni, collisione trascurabile).
    s3 = [decidi_azione_nemico(random.Random(8), bersagli) for _ in range(50)]
    assert s1 != s3
    assert seq_a  # sanity


def test_G4_nessun_llm_nel_percorso_di_risoluzione() -> None:
    # Statico: i moduli di risoluzione non importano il provider/anthropic né
    # chiamano `genera(`.
    for nome in ("combattimento", "mutazione", "status", "turno", "scheda",
                 "azione", "calibrazione", "derivate"):
        src = (_MOTORE / f"{nome}.py").read_text(encoding="utf-8")
        assert "anthropic" not in src
        assert "genera(" not in src
        albero = ast.parse(src)
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.ImportFrom) and nodo.module:
                assert nodo.module.split(".")[0] != "provider"
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    assert alias.name.split(".")[0] not in {"anthropic", "provider"}


# --- G-11: death-check → MortePersonaggio, NON CombatResolved(sconfitta) ------

def test_G11_death_check_emette_mortepersonaggio(mondo_isolato: str) -> None:
    _bus, adapter, _enc = avvia_scontro(nemici=[SpecNemico(destrezza=5, punti_vita=10**9)],
                                        hp_prot=10, destrezza_prot=10)
    # Forza la sconfitta: HP del protagonista a 0.
    _pent, _marker, scheda = protagonista()
    scheda.punti_vita = 0

    tick()

    assert adapter.events_of(MortePersonaggio), "il death-check deve emettere MortePersonaggio"
    assert adapter.events_of(CombatResolved) == [], "morte ≠ sconfitta: niente CombatResolved"
    # Stato-vita aggiornato (sconfitta → morte nell'MVP).
    _pent, _marker, scheda = protagonista()
    assert scheda.vivo is False


# --- Entità di combattimento effimere: create su EncounterStarted, distrutte su
#     CombatResolved; il protagonista persiste (FNC §6.3) -----------------------

def test_entita_combattimento_effimere(mondo_isolato: str) -> None:
    _bus, adapter, _enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=5, punti_vita=1), SpecNemico(destrezza=6, punti_vita=1)],
        hp_prot=10**9, destrezza_prot=100,  # protagonista veloce e robusto → vince
    )
    pent, _marker, _scheda = protagonista()

    # Materializzate su EncounterStarted.
    assert len(esper.get_component(Nemico)) == 2
    assert esper.has_component(pent, Combattente)
    assert leggi_fase() == Fase.COMBATTIMENTO

    for _ in range(50):
        tick()
        if adapter.events_of(CombatResolved):
            break
    assert adapter.events_of(CombatResolved)

    # Distrutte su CombatResolved; il protagonista persiste senza il Combattente effimero.
    assert esper.get_component(Nemico) == []
    assert esper.get_component(StatoCombattimento) == []
    assert esper.entity_exists(pent)
    assert not esper.has_component(pent, Combattente)
    assert leggi_fase() == Fase.NARRAZIONE


# --- GR2-11: check 1 — contest a banda, esito a tre vie, UNA sola estrazione ----

def test_check1_esito_a_tre_vie_una_pescata() -> None:
    # acc == eva → P = 0.5 (parità). Banda [P−δ/2, P+δ/2] = [0.4, 0.6] (δ=0.20). Una sola
    # estrazione `u` seleziona la categoria; conta DENTRO la banda → esattamente 1 pescata.
    assert esito_contest(10, 10, _RngScript([0.30])) == 1.0       # u < lo → pieno
    g = _RngScript([0.50])
    assert esito_contest(10, 10, g) == G_GRAZE and g.chiamate == 1  # lo ≤ u < hi → graze
    assert esito_contest(10, 10, _RngScript([0.70])) == 0.0       # u ≥ hi → schivata


def test_check1_sotto_banda_autohit_zero_pescate() -> None:
    # eva ben sotto acc/F → auto-hit deterministico (m=1) SENZA pescare (zero estrazioni).
    spia = _RngScript([])  # se pescasse, .pop(0) su lista vuota → IndexError
    assert esito_contest(100, 1, spia) == 1.0
    assert spia.chiamate == 0


def test_check1_floor_gemello_probabilita_colpire() -> None:
    # Anche contro un'evasione mostruosa, P(colpire) ≥ MIN_COLPO (nessun whiff garantito):
    # i bordi sono clampati in [MIN_COLPO, 1−MIN_COLPO] → con u appena sotto hi, connette.
    from motore import MIN_COLPO

    # eva enorme vs acc piccola: hi clampa a MIN_COLPO → u < MIN_COLPO connette (graze/pieno).
    assert esito_contest(1, 10**6, _RngScript([MIN_COLPO / 2])) != 0.0
    # …e u ben sopra MIN_COLPO schiva: P(schivata) < 1 (clamp gemello).
    assert esito_contest(1, 10**6, _RngScript([0.99])) == 0.0


def test_check1_entita_default_autohit(mondo_isolato: str) -> None:
    # Con la geometria di default dell'MVP (nudo/taglia media) eva ≪ acc/F → check1 è auto-hit
    # per tutti, SENZA pescare: il combattimento ordinario è deterministico.
    att = esper.create_entity(Primarie(valori={StatId.FORZA: 10, StatId.DESTREZZA: 10, StatId.INTELLIGENZA: 10}))
    ber = esper.create_entity(Primarie(valori={StatId.DESTREZZA: 40}))  # Dex alta, ma nudo
    spia = _RngScript([])
    assert check1(att, ber, spia) == 1.0 and spia.chiamate == 0


def test_due_check_seeded_deterministico(mondo_isolato: str) -> None:
    # Stesso seed → stessa storia di danno (il check 1 pesca dall'unico stream seeded).
    from contextlib import contextmanager

    @contextmanager
    def _mondo(nome: str):
        esper.switch_world(nome)
        try:
            yield
        finally:
            esper.switch_world("default")
            esper.delete_world(nome)

    def _hp_finale() -> int:
        avvia_scontro(nemici=[SpecNemico(destrezza=5, punti_vita=200)],
                      hp_prot=200, destrezza_prot=10, seed=123)
        for _ in range(60):
            tick()
        return protagonista()[2].punti_vita

    with _mondo("due-check-a"):
        a = _hp_finale()
    with _mondo("due-check-b"):
        b = _hp_finale()
    assert a == b
