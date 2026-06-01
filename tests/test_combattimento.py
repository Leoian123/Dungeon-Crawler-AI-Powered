"""Loop di combattimento: AP (G-1), iniziativa (G-3), decisione nemici (G-4),
death-check (G-11), entità effimere (FNC §6.3). Headless, seeded.
"""

from __future__ import annotations

import ast
import random
import re
from pathlib import Path

import esper

from contracts import CombatResolved, EncounterStarted, MortePersonaggio
from motore import (
    Combattente,
    Fase,
    Nemico,
    PuntiVita,
    SpecNemico,
    StatoCombattimento,
    calcola_iniziativa,
    decidi_azione_nemico,
    leggi_fase,
    protagonista,
    tick,
)
from tests.combat_helpers import avvia_scontro

_MOTORE = Path(__file__).resolve().parents[1] / "src" / "motore"


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
    for nome in ("combattimento", "mutazione", "status", "turno", "scheda"):
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
