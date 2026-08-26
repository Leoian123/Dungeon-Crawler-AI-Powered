"""Territorio F3: tabelle di spawn (pesca pesata), boss procedurali, copione
zona-aware, imboscate dalla tabella, anomalia senza celestiale, fascicolo.
"""

from __future__ import annotations

import asyncio
import random

from contracts import Grado, TierTerritorio
from motore import (
    avvia_territorio,
    boss_della_zona,
    boss_procedurale,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_stagione,
    crea_tempo_piano,
    mappa_corrente,
    pesca_spawn,
    rigenera_mappa_zona,
    spina_del_piano,
    stanza_boss_di,
    zona_corrente,
)
from tests.contenuti_sintetici import piano_territoriale, stagione_sintetica


def _arma_mondo(seed: int = 7) -> None:
    from main import _stagione_a_attiva

    crea_profondita()
    crea_seme(seed)
    crea_tempo_piano()
    crea_stagione(_stagione_a_attiva(
        stagione_sintetica(piani=[piano_territoriale(1)], slug="s-mondo")
    ))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    avvia_territorio(1)


def test_pesca_spawn_deterministica_e_dalla_tabella(mondo_isolato) -> None:
    _arma_mondo()
    a = pesca_spawn(random.Random("x"))
    b = pesca_spawn(random.Random("x"))
    assert a is not None and a.slug == b.slug  # stesso rng → stessa pescata
    assert a.slug.startswith("t-riempitivo-")  # dalle voci della tabella


def test_pesca_rispetta_i_pesi(mondo_isolato) -> None:
    """Su molte pescate, il COMUNE domina il RARO (peso 6 vs 1)."""
    _arma_mondo()
    rng = random.Random(42)
    conteggi: dict[str, int] = {}
    for _ in range(300):
        mob = pesca_spawn(rng)
        conteggi[mob.slug] = conteggi.get(mob.slug, 0) + 1
    raro = conteggi.get("t-riempitivo-0", 0)      # frequenza RARO nel sintetico
    comuni = sum(v for k, v in conteggi.items() if k != "t-riempitivo-0")
    assert comuni > raro * 2, conteggi


def test_tabella_fallback_sui_tier_senza_voce(mondo_isolato) -> None:
    """La città non dichiara una tabella: pesca da quella del quartiere (la più
    vicina scendendo) invece di restare a mani vuote."""
    _arma_mondo()
    spina = spina_del_piano(1)
    rigenera_mappa_zona(1, spina[2])  # città
    assert zona_corrente().tier is TierTerritorio.CITTA
    mob = pesca_spawn(random.Random(1))
    assert mob is not None and mob.slug.startswith("t-riempitivo-")


def test_boss_procedurale_deterministico_e_del_suo_tier(mondo_isolato) -> None:
    _arma_mondo()
    spina = spina_del_piano(1)
    quartiere, distretto = spina[0], spina[1]
    a = boss_procedurale(1, quartiere)
    b = boss_procedurale(1, quartiere)
    assert a is not None and a.slug == b.slug and a.nome == b.nome
    assert a.grado is Grado.BRONZO          # il grado lo impone il tier
    c = boss_della_zona(1, distretto)       # tier procedurale → dalle tabelle
    assert c is not None and c.grado is Grado.ARGENTO
    assert c.prosa_stanza                   # ha la sua scena per il copione


def test_boss_procedurale_riferibile_dal_gate(mondo_isolato) -> None:
    """Il 4° strato del gate riconosce il boss ISTANZIATO della zona corrente."""
    from motore.design import mob_del_cast

    _arma_mondo()
    boss = boss_della_zona(1, zona_corrente())
    assert boss is not None
    assert mob_del_cast(boss.slug) is not None
    assert mob_del_cast("boss-inesistente") is None


def test_imboscata_pesca_dalla_tabella_mai_un_boss(mondo_isolato, monkeypatch) -> None:
    import esper

    from motore import tempo as tempo_mod
    from motore.combattimento import PianoIncontro
    from motore import EntitaMob, componi_imboscata_scena

    _arma_mondo()
    monkeypatch.setattr(tempo_mod, "PROB_IMBOSCATA", 1.0)
    enc = componi_imboscata_scena()
    pi = esper.component_for_entity(enc, PianoIncontro)
    em = esper.component_for_entity(pi.arruolate[0], EntitaMob)
    assert em.archetipo in {"slime", "scheletro", "goblin"}
    assert not em.nome.lower().startswith("il boss")  # riempitivo, mai il custode
    assert em.grado is Grado.BRONZO  # dalle voci della tabella (sintetico)


def test_anomalia_senza_celestiale_sui_piani_mondo(mondo_isolato) -> None:
    from motore.catalogo import prepara_contesto
    from motore.design import design_piano_corrente

    class _RngFisso:
        def __init__(self, v: float) -> None:
            self._v = v

        def random(self) -> float:
            return self._v

    _arma_mondo()
    piano = design_piano_corrente()
    anomalo = prepara_contesto(1, _RngFisso(0.0), piano=piano)
    assert anomalo.anomala is True
    assert Grado.CELESTIALE not in anomalo.gradi_ammessi  # riservato al boss di piano
    assert Grado.LEGGENDARIO in anomalo.gradi_ammessi     # il delirio resta delirio
    # Sui piani PIATTI il comportamento storico non cambia.
    anomalo_piatto = prepara_contesto(1, _RngFisso(0.0), piano=None)
    assert Grado.CELESTIALE in anomalo_piatto.gradi_ammessi


def test_fascicolo_porta_zona_e_custode(mondo_isolato) -> None:
    from motore import MemoriaTurni
    from motore.gm import componi_fascicolo, sezione_fascicolo

    _arma_mondo()
    fascicolo = componi_fascicolo(MemoriaTurni())
    assert fascicolo.territorio_riga
    sezione = sezione_fascicolo(fascicolo)
    assert "[fascicolo/territorio]" in sezione
    assert "quartiere" in sezione and "custode del varco" in sezione


def test_copione_territoriale_boss_e_riempitivi(run_pulita, tmp_path) -> None:
    """E2E offline: il reveal della partenza è un riempitivo della tabella; nella
    stanza-boss il reveal è IL custode (riferimento incluso). Zero liste
    precompilate: il copione si computa dalla zona."""
    import esper

    from main import costruisci_sessione
    from motore import EntitaMob, mob_corrente
    from motore.narrazione import PROSA_NEUTRA

    sessione = costruisci_sessione(
        nome="Copione", seed=3, directory=tmp_path,
        stagione=stagione_sintetica(piani=[piano_territoriale(1)], slug="s-copione"),
    )
    snap = asyncio.run(sessione.prossima_narrazione())
    assert snap.prosa and snap.prosa != PROSA_NEUTRA
    mob = mob_corrente()
    assert mob is not None
    em = esper.component_for_entity(mob, EntitaMob)
    assert em.archetipo in {"slime", "scheletro", "goblin"}

    # Harness: salta alla stanza-boss della zona e chiedi il reveal.
    from motore import dissolvi_mob

    dissolvi_mob()
    _e, mappa = mappa_corrente()
    mappa.stanza_corrente = stanza_boss_di(zona_corrente(), mappa.piano)
    snap = asyncio.run(sessione.prossima_narrazione())
    boss_atteso = boss_della_zona(1, zona_corrente())
    em = esper.component_for_entity(mob_corrente(), EntitaMob)
    assert em.nome == boss_atteso.nome, "la stanza-boss deve rivelare IL custode"
    assert em.grado is boss_atteso.grado
