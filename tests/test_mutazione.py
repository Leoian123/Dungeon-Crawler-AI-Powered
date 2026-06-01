"""Binario di mutazione intra-fase: rinforzi a confine di turno, effimeri (G-9);
nessun `EncounterStarted` ri-emesso per aggiungere nemici (G-10).
"""

from __future__ import annotations

from pathlib import Path

import esper

from contracts import CombatResolved, EncounterStarted
from motore import (
    Nemico,
    OndataRinforzi,
    PianoRinforzi,
    PuntiVita,
    SpecNemico,
    stato_combattimento,
    tick,
)
from tests.combat_helpers import avvia_scontro

_MOTORE = Path(__file__).resolve().parents[1] / "src" / "motore"


def test_G9_rinforzi_a_confine_di_turno_ed_effimeri(mondo_isolato: str) -> None:
    _bus, adapter, _enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=5, punti_vita=10**9)],
        hp_prot=10**9, destrezza_prot=1, seed=1,
    )
    # Ondata programmata al round 2 (composta a monte; il motore la rilascia).
    ent_stato, _stato = stato_combattimento()
    esper.add_component(
        ent_stato,
        PianoRinforzi(ondate=[OndataRinforzi(round_trigger=2, nemici=[SpecNemico(7, 10**9)])]),
    )

    assert len(esper.get_component(Nemico)) == 1
    adapter.clear()  # dimentica l'EncounterStarted iniziale

    for _ in range(40):
        tick()
        if len(esper.get_component(Nemico)) == 2:
            break

    # Il rinforzo è materializzato (a confine di turno, dal sistema dedicato)...
    assert len(esper.get_component(Nemico)) == 2
    # ...e NESSUN EncounterStarted è stato ri-emesso per aggiungerlo (G-10).
    assert adapter.events_of(EncounterStarted) == []

    # I rinforzi sono effimeri: su CombatResolved vengono distrutti come gli altri.
    for _ent, pv in esper.get_component(PuntiVita):
        pv.attuali = 0  # uccidi tutti i nemici → vittoria
    for _ in range(20):
        tick()
        if adapter.events_of(CombatResolved):
            break
    assert adapter.events_of(CombatResolved)
    assert esper.get_component(Nemico) == []


def test_G10_rinforzi_non_riemettono_encounterstarted_statico() -> None:
    # Statico: il modulo dei rinforzi non EMETTE EncounterStarted (mutazione intra-fase
    # ≠ transizione di fase). Si controlla l'uso come codice — costruzione dell'evento
    # o pubblicazione sul bus — non la menzione nei commenti/docstring.
    src = (_MOTORE / "mutazione.py").read_text(encoding="utf-8")
    assert "EncounterStarted(" not in src, "i rinforzi non costruiscono EncounterStarted"
    assert "pubblica(" not in src, "i rinforzi non pubblicano sul bus (stato via Canale A)"
