"""Le due liveness di release (gate del nodo A): G-L1 (ogni scontro termina) e G-L2
(ogni piano è completabile). Senza entrambe verdi, "giocabile capo-a-fine" non è vero
(G §3, §8.4). Headless, seeded.
"""

from __future__ import annotations

import random

import esper
import pytest

from contracts import CombatResolved, MortePersonaggio
from motore.calibrazione import R_SOGLIA_CROLLO
from motore import (
    DANNO_BASE,
    OndataRinforzi,
    Piano,
    PianoRinforzi,
    Rigenerazione,
    SpecNemico,
    applica_status,
    piano_completabile,
    protagonista,
    raggiungibili,
    tick,
    valida_piano,
)
from tests.combat_helpers import avvia_scontro


# ============================================================================
# G-L1 — Ogni scontro TERMINA (garanzia di fine, verifica (a) + rete (b))
# ============================================================================
#
# Con gli status EFFETTIVI (la rigenerazione CURA) la garanzia (a) "monotònia degli
# HP" non regge più da sola: la terminazione è garantita PER COSTRUZIONE dalla rete
# (b), l'escalation `SistemaCrollo` (attiva nell'MVP, registrata in produzione): il
# danno inevitabile cresce lineare, bypassa il risolutore e supera qualunque
# sostentamento in un numero limitato di round (aritmetica monotòna). I rinforzi
# restano **finiti** (ogni ondata rilasciata una volta).


def test_GL1_danno_base_positivo_garantisce_progresso() -> None:
    # Il cardine di (a): ogni colpo fa progredire lo stato (HP che scende). Con
    # DANNO_BASE = 0 lo scontro potrebbe stallare; qui è > 0 per costruzione.
    assert DANNO_BASE > 0


@pytest.mark.parametrize("hp_nemico", [1, 5, 20, 100])
def test_GL1_scontro_termina_entro_un_bound(mondo_isolato: str, hp_nemico: int) -> None:
    # Protagonista robusto e veloce → vince; lo scontro chiude entro ~2·HP turni (due
    # combattenti che si alternano). Il bound dimostra che NON cicla all'infinito.
    _bus, adapter, _enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=5, punti_vita=hp_nemico)],
        hp_prot=10**9, destrezza_prot=100,
    )
    bound = 2 * hp_nemico + 20
    for _ in range(bound):
        tick()
        if adapter.events_of(CombatResolved):
            break
    risolti = adapter.events_of(CombatResolved)
    assert risolti, f"scontro non terminato entro {bound} turni (possibile stallo)"
    assert risolti[0].vittoria is True


def test_GL1_scontro_termina_anche_in_morte(mondo_isolato: str) -> None:
    # Anche il ramo opposto termina: nemico inarrestabile → MortePersonaggio entro un
    # bound (gli HP del protagonista scendono di ≥1 per turno del nemico).
    _bus, adapter, _enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=100, punti_vita=10**9)],
        hp_prot=30, destrezza_prot=1,
    )
    for _ in range(30 * 2 + 20):
        tick()
        if adapter.events_of(MortePersonaggio):
            break
    assert adapter.events_of(MortePersonaggio), "morte non raggiunta: scontro non terminante"


def test_GL1_sostentamento_non_stalla_grazie_al_crollo(mondo_isolato: str) -> None:
    # La rigenerazione ora CURA (feel MVP): un build con sostentamento ≥ danno è
    # possibile — la garanzia di terminazione non è più "niente cure" ma la rete
    # PER COSTRUZIONE dell'escalation (SistemaCrollo, G-L1): il danno inevitabile
    # cresce lineare e supera qualunque rigenerazione in round limitati.
    _bus, adapter, _enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=5, punti_vita=10**9)],
        hp_prot=60, destrezza_prot=1,
    )
    pent, _marker, _scheda = protagonista()
    applica_status(pent, Rigenerazione(rango=9, durata=10**9))  # "build sostentamento"

    for _ in range(2 * (R_SOGLIA_CROLLO + 200)):
        tick()
        if adapter.events_of(MortePersonaggio):
            break
    assert adapter.events_of(MortePersonaggio), (
        "lo scontro col build-sostentamento non è terminato: il crollo non morde (G-L1)"
    )


def test_GL1_rinforzi_sono_finiti(mondo_isolato: str) -> None:
    # I rinforzi (binario di mutazione §5) sono BOUNDED: ogni ondata è rilasciata una
    # sola volta → niente ondate infinite (la sorgente di non-terminazione di §5.4).
    # Nemico iniziale tosto abbastanza da raggiungere il round 1 (quando l'ondata esce):
    # col danno deterministico 2b (atk_eff−def_eff/100), deve sopravvivere al primo colpo
    # del protagonista, quindi HP > danno-per-colpo (ex `punti_vita=8`, tarato su DANNO_BASE=1).
    _bus, adapter, enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=5, punti_vita=80)],
        hp_prot=10**9, destrezza_prot=100,
    )
    esper.add_component(
        enc, PianoRinforzi(ondate=[OndataRinforzi(round_trigger=1, nemici=[SpecNemico(destrezza=5, punti_vita=1)])])
    )
    for _ in range(200):
        tick()
        if adapter.events_of(CombatResolved):
            break
    piano = esper.component_for_entity(enc, PianoRinforzi)
    assert piano.rilasciate == {0}, "l'ondata deve uscire UNA volta sola (niente rinforzi infiniti)"
    assert adapter.events_of(CombatResolved), "scontro con rinforzi finiti deve comunque terminare"


# ============================================================================
# G-L2 — Ogni piano è COMPLETABILE (almeno una DiscesaPiano raggiungibile)
# ============================================================================
#
# Il gate di contenuto (`valida_piano`) NON lascia passare un piano senza uscita: lo
# **ripara** (piazza una DiscesaPiano in una stanza raggiungibile) o lo **rifiuta**
# (G-18, §8.4). È la gemella di G-L1: G-L1 chiude lo scontro, G-L2 chiude il piano.


def test_GL2_piano_riparato_e_sempre_completabile() -> None:
    # Un piano senza uscita raggiungibile viene riparato: dopo `valida_piano` è
    # SEMPRE completabile (esiste una DiscesaPiano nelle stanze raggiungibili).
    piano = Piano(partenza=0, adiacenze={0: [1], 1: [0, 2], 2: [1]}, discese=set())
    assert not piano_completabile(piano)
    riparato = valida_piano(piano, ripara=True)
    assert riparato is not None and piano_completabile(riparato)
    assert any(d in raggiungibili(riparato) for d in riparato.discese)


def test_GL2_gate_rifiuta_un_piano_senza_uscita() -> None:
    piano = Piano(partenza=0, adiacenze={0: [1], 1: [0]}, discese={9})  # 9 irraggiungibile
    assert valida_piano(piano, ripara=False) is None  # rifiutato, non lasciato passare


@pytest.mark.parametrize("seed", range(25))
def test_GL2_qualunque_topologia_diventa_completabile(seed: int) -> None:
    # Property test: su topologie casuali, il gate (ripara=True) garantisce SEMPRE la
    # completabilità — nessun piano resta invincibile (liveness dell'esplorazione).
    rng = random.Random(seed)
    n = rng.randint(1, 8)
    adiacenze: dict[int, list[int]] = {i: [] for i in range(n)}
    for a in range(n):
        for b in range(n):
            if a != b and rng.random() < 0.35:
                adiacenze[a].append(b)
    discese = {rng.randrange(n)} if rng.random() < 0.4 else set()
    piano = Piano(partenza=0, adiacenze=adiacenze, discese=discese)

    riparato = valida_piano(piano, ripara=True)
    assert riparato is not None
    assert piano_completabile(riparato), f"topologia seed={seed} non completabile dopo il gate"
    assert any(d in raggiungibili(riparato) for d in riparato.discese)
