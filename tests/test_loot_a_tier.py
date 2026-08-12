"""Il loot insegue il territorio (STATO.md §4.1, passo 1): sui piani-mondo la
finestra dei gradi del bottino segue il TIER della zona corrente (`gradi_del_tier`
+ `finestra_gradi_loot`), non la profondità — che resta 1 per tutta la spina.
Sui piani piatti resta l'autorità storica (`gradi_per_profondita`).
"""

from __future__ import annotations

from contracts import BusEventi, Grado, TierTerritorio
from motore import (
    GRADO_DA_TIER,
    avvia_territorio,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_stagione,
    crea_tempo_piano,
    finestra_gradi_loot,
    gradi_del_tier,
    gradi_per_profondita,
    rango_grado,
    rigenera_mappa_zona,
    spina_del_piano,
    zona_corrente,
)
from tests.contenuti_sintetici import piano_territoriale, stagione_sintetica


def _arma_mondo(seed: int = 7) -> BusEventi:
    from main import _stagione_a_attiva

    crea_profondita()
    crea_seme(seed)
    crea_tempo_piano()
    crea_stagione(_stagione_a_attiva(
        stagione_sintetica(piani=[piano_territoriale(1)], slug="s-loot")
    ))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    avvia_territorio(1)
    return BusEventi()


def test_la_finestra_contiene_il_grado_del_tier() -> None:
    for tier in TierTerritorio:
        finestra = gradi_del_tier(tier)
        assert finestra, f"finestra vuota per {tier}"
        assert GRADO_DA_TIER[tier] in finestra, (
            f"{tier}: la finestra deve CONTENERE il grado del tier"
        )


def test_il_primo_tier_coincide_con_la_profondita_1() -> None:
    """Il quartiere non è più generoso del piano-1 storico: stessa finestra —
    lucchetto di sincronia fra le due formule gemelle."""
    assert gradi_del_tier(TierTerritorio.QUARTIERE) == gradi_per_profondita(1)


def test_l_ultimo_tier_clampa_senza_stringersi() -> None:
    """La tana loota {leggendario, celestiale}: i suoi riempitivi sono
    leggendari (il celestiale è il Lich, mai lo spawn) — la finestra clampa
    in cima invece di ridursi al solo grado irraggiungibile."""
    finestra = gradi_del_tier(TierTerritorio.PIANO)
    assert Grado.CELESTIALE in finestra
    assert Grado.LEGGENDARIO in finestra


def test_senza_territorio_vale_la_profondita(mondo_isolato) -> None:
    """Piani piatti / harness: `finestra_gradi_loot` degrada sull'autorità storica."""
    for livello in (1, 3, 7):
        assert finestra_gradi_loot(livello) == gradi_per_profondita(livello)


def test_sul_piano_mondo_vale_il_tier_della_zona(mondo_isolato) -> None:
    """La finestra del drop segue la zona: a metà spina i gradi sono quelli del
    tier (era il buco della misura 2026-08-11: nemici a oro, loot a bronzo)."""
    _arma_mondo()
    spina = spina_del_piano(1)
    assert finestra_gradi_loot(1) == gradi_del_tier(spina[0].tier)  # quartiere
    for zona in (spina[2], spina[4]):  # città, paese
        rigenera_mappa_zona(1, zona)
        assert zona_corrente() == zona
        assert finestra_gradi_loot(1) == gradi_del_tier(zona.tier)
        assert finestra_gradi_loot(1) != gradi_per_profondita(1), (
            "a metà spina la finestra NON può essere quella della profondità 1"
        )


def test_il_deposito_del_drop_usa_la_finestra_del_tier(mondo_isolato, run_pulita, tmp_path) -> None:
    """Il CABLAGGIO, non il sensore (review 2026-08-11): `_deposita_bottino`
    deve consultare `finestra_gradi_loot` — ripristinare lì la finestra di
    profondità (il bug esatto della misura 0/40) passerebbe ogni altro test,
    perché sui piani piatti le due formule coincidono."""
    import asyncio
    import random

    import motore
    from main import costruisci_sessione
    from tests.contenuti_sintetici import piano_territoriale, stagione_sintetica

    sessione = costruisci_sessione(
        nome="Drop", seed=4, directory=tmp_path,
        stagione=stagione_sintetica(piani=[piano_territoriale(1)], slug="s-drop"),
    )
    asyncio.run(sessione.prossima_narrazione())

    finestre_chieste: list[frozenset] = []
    vera = motore.finestra_gradi_loot

    def spia(livello: int):
        finestra = vera(livello)
        finestre_chieste.append(finestra)
        return finestra

    class _RngVince(random.Random):
        """La chance di drop è sempre vinta: il deposito DEVE consultare la finestra."""

        def random(self) -> float:  # type: ignore[override]
            return 0.0

        def randrange(self, *args, **kwargs) -> int:  # type: ignore[override]
            return 0

    sessione.rng = _RngVince()
    try:
        motore.finestra_gradi_loot = spia
        sessione._deposita_bottino()
    finally:
        motore.finestra_gradi_loot = vera
    assert finestre_chieste, "il deposito non ha consultato la finestra del tier"
    assert finestre_chieste[0] == gradi_del_tier(zona_corrente().tier)
    sessione.esci()
