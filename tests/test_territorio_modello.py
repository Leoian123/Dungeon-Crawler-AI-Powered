"""Il modello territoriale (Fase 1): forma nei contratti, simmetria tier↔grado,
coerenza per costruzione (grado==tier, celestiale riservato, roster/tabelle),
risoluzione degli slug e freeze nel World (round-trip del componente).
"""

from __future__ import annotations

import pytest

from contracts import (
    Frequenza,
    Grado,
    PianoAsset,
    Stagione,
    TabellaBossProcedurali,
    TabellaSpawn,
    TerritorioDesign,
    TierTerritorio,
    VoceSpawn,
)
from motore import GRADO_DA_TIER, grado_da_tier
from tests.contenuti_sintetici import (
    mob_sintetico,
    piano_sintetico,
    piano_territoriale,
    stagione_sintetica,
    territorio_sintetico,
)


# --- Simmetria 6↔6: tier e grado sono la stessa scala nominata ------------------

def test_sincronia_tier_grado_per_indice() -> None:
    """F-6: la mappa è derivata per indice (zip strict) — un membro aggiunto a uno
    solo dei due enum esplode qui, non a runtime."""
    assert len(TierTerritorio) == len(Grado) == 6
    assert GRADO_DA_TIER[TierTerritorio.QUARTIERE] is Grado.BRONZO
    assert GRADO_DA_TIER[TierTerritorio.PIANO] is Grado.CELESTIALE
    for tier in TierTerritorio:
        # La derivazione di contracts (`tier.grado`) e quella del catalogo
        # (`grado_da_tier`) sono LA STESSA mappa: mai due verità.
        assert tier.grado is grado_da_tier(tier) is GRADO_DA_TIER[tier]


def test_peso_frequenza_completo_per_enum() -> None:
    """Pattern SPEC_STATUS: ogni membro di Frequenza ha la sua foglia §11."""
    from motore.calibrazione import PESO_FREQUENZA

    assert set(PESO_FREQUENZA) == {f.value for f in Frequenza}
    assert all(peso >= 1 for peso in PESO_FREQUENZA.values())


# --- Coerenza per costruzione (validator delle forme) ---------------------------

def test_boss_fuori_tier_respinto() -> None:
    territorio = territorio_sintetico()
    boss_sbagliato = dict(territorio.boss)
    boss_sbagliato[TierTerritorio.PAESE] = [
        mob_sintetico("impostore", grado=Grado.BRONZO)  # il paese esige leggendario
    ]
    with pytest.raises(ValueError, match="fuori tier"):
        territorio.model_copy(update={"boss": boss_sbagliato}).model_validate(
            territorio.model_copy(update={"boss": boss_sbagliato}).model_dump()
        )


def test_boss_di_piano_esattamente_uno() -> None:
    territorio = territorio_sintetico()
    senza_piano = {
        tier: roster for tier, roster in territorio.boss.items()
        if tier is not TierTerritorio.PIANO
    }
    with pytest.raises(ValueError, match="ESATTAMENTE un boss"):
        territorio.model_copy(update={"boss": senza_piano}).model_validate(
            territorio.model_copy(update={"boss": senza_piano}).model_dump()
        )


def test_celestiale_riservato_al_boss_di_piano() -> None:
    # Nel CAST di un piano territoriale il celestiale è vietato...
    with pytest.raises(ValueError, match="celestiale riservato"):
        piano_sintetico(
            1, gradi=tuple(Grado),
            cast=[mob_sintetico("abusivo", grado=Grado.CELESTIALE)],
            territorio=territorio_sintetico(),
        )
    # ...e nelle tabelle di spawn pure.
    from contracts import TabellaSpawnRisolta, VoceSpawnRisolta

    territorio = territorio_sintetico()
    spawn_abusivo = [TabellaSpawnRisolta(
        tier=TierTerritorio.QUARTIERE,
        voci=[VoceSpawnRisolta(
            mob=mob_sintetico("lich-abusivo", grado=Grado.CELESTIALE),
            frequenza=Frequenza.RARO,
        )],
    )]
    with pytest.raises(ValueError, match="celestiale riservato"):
        piano_sintetico(
            1, gradi=tuple(Grado),
            territorio=territorio.model_copy(update={"spawn": spawn_abusivo}),
        )


def test_design_rifiuta_roster_su_tier_procedurale_e_tabelle_mancanti() -> None:
    procedurali = [TabellaBossProcedurali(
        tier=TierTerritorio.DISTRETTO,
        nomi=["a", "b", "c", "d"], gimmick=["w", "x", "y", "z"],
        archetipi=["slime"],
    )]
    spawn = [TabellaSpawn(tier=TierTerritorio.QUARTIERE,
                          voci=[VoceSpawn(mob="riempitivo")])]
    with pytest.raises(ValueError, match="procedurale"):
        TerritorioDesign(
            boss={TierTerritorio.PIANO: ["il-boss"],
                  TierTerritorio.QUARTIERE: ["abusivo"]},
            procedurali=procedurali * 2, spawn=spawn,
        )
    doppio_distretto = procedurali + [procedurali[0].model_copy(
        update={"nomi": ["e", "f", "g", "h"]}
    )]
    with pytest.raises(ValueError, match="manca la tabella"):
        TerritorioDesign(
            boss={TierTerritorio.PIANO: ["il-boss"]},
            procedurali=doppio_distretto,  # due tabelle, ma il quartiere manca
            spawn=spawn,
        )


def test_design_conteggi_coerenti() -> None:
    procedurali = [
        TabellaBossProcedurali(
            tier=tier, nomi=["a", "b", "c", "d"], gimmick=["w", "x", "y", "z"],
            archetipi=["slime"],
        )
        for tier in (TierTerritorio.DISTRETTO, TierTerritorio.QUARTIERE)
    ]
    spawn = [TabellaSpawn(tier=TierTerritorio.QUARTIERE,
                          voci=[VoceSpawn(mob="riempitivo")])]
    with pytest.raises(ValueError, match="sempre 1"):
        TerritorioDesign(
            conteggi={TierTerritorio.PIANO: 2},
            boss={TierTerritorio.PIANO: ["il-boss"]},
            procedurali=procedurali, spawn=spawn,
        )
    with pytest.raises(ValueError, match="oltre il conteggio"):
        TerritorioDesign(
            conteggi={TierTerritorio.PAESE: 1},
            boss={TierTerritorio.PIANO: ["il-boss"],
                  TierTerritorio.PAESE: ["leon", "ash"]},
            procedurali=procedurali, spawn=spawn,
        )


def test_archetipi_procedurali_fuori_budget_respinti() -> None:
    territorio = territorio_sintetico()
    procedurali_fuori = [
        t.model_copy(update={"archetipi": ["goblin-spaziale"]})
        for t in territorio.procedurali
    ]
    with pytest.raises(ValueError, match="archetipi fuori budget"):
        piano_sintetico(
            1, gradi=tuple(Grado),
            territorio=territorio.model_copy(update={"procedurali": procedurali_fuori}),
        )


# --- Risoluzione: slug del territorio sciolti come il cast ----------------------

def _libreria(tmp_path, *, mobs=(), piani=(), stagioni=()):
    uff = tmp_path / "uff"
    loc = tmp_path / "loc"
    for asset, tipo in [*((m, "mob") for m in mobs),
                        *((p, "piani") for p in piani),
                        *((s, "stagioni") for s in stagioni)]:
        cartella = uff / tipo
        cartella.mkdir(parents=True, exist_ok=True)
        (cartella / f"{asset.slug}.json").write_text(
            asset.model_dump_json(), encoding="utf-8"
        )
    return uff, loc


def _design_minimo() -> TerritorioDesign:
    return TerritorioDesign(
        boss={TierTerritorio.PIANO: ["il-lich"]},
        procedurali=[
            TabellaBossProcedurali(
                tier=tier, nomi=["a", "b", "c", "d"], gimmick=["w", "x", "y", "z"],
                archetipi=["slime"],
            )
            for tier in (TierTerritorio.DISTRETTO, TierTerritorio.QUARTIERE)
        ],
        spawn=[TabellaSpawn(tier=TierTerritorio.QUARTIERE,
                            voci=[VoceSpawn(mob="riempitivo")])],
    )


def _piano_asset_territoriale() -> PianoAsset:
    from contracts import BudgetDesign

    return PianoAsset(
        slug="mondo", titolo="Mondo", tema="t",
        budget=BudgetDesign(gradi=list(Grado), archetipi=["slime"]),
        cast=["riempitivo"],
        territorio=_design_minimo(),
    )


def test_risoluzione_scioglie_i_boss_del_territorio(tmp_path) -> None:
    from main import risolvi_stagione

    lich = mob_sintetico("il-lich", grado=Grado.CELESTIALE)
    riempitivo = mob_sintetico("riempitivo")
    uff, loc = _libreria(
        tmp_path, mobs=[lich, riempitivo], piani=[_piano_asset_territoriale()],
        stagioni=[Stagione(slug="s", numero=1, titolo="S", mondo="Terra",
                           piani=["mondo"])],
    )
    risolta = risolvi_stagione("s", ufficiali=uff, locali=loc)
    territorio = risolta.piani[0].territorio
    assert territorio is not None
    assert territorio.boss[TierTerritorio.PIANO][0].slug == "il-lich"
    assert territorio.spawn[0].voci[0].mob.slug == "riempitivo"


def test_risoluzione_boss_pendente_e_errore_di_authoring(tmp_path) -> None:
    from main import risolvi_stagione

    uff, loc = _libreria(
        tmp_path, mobs=[mob_sintetico("riempitivo")],
        piani=[_piano_asset_territoriale()],  # "il-lich" NON esiste in libreria
        stagioni=[Stagione(slug="s", numero=1, titolo="S", mondo="Terra",
                           piani=["mondo"])],
    )
    with pytest.raises(ValueError, match="il-lich"):
        risolvi_stagione("s", ufficiali=uff, locali=loc)


# --- Freeze: il territorio viaggia nel componente StagioneAttiva ----------------

def test_freeze_e_round_trip_del_territorio(mondo_isolato) -> None:
    from main import _stagione_a_attiva
    from motore.persistenza.tag import deserializza_componente, serializza_componente

    attiva = _stagione_a_attiva(
        stagione_sintetica(piani=[piano_territoriale(1)], slug="s-mondo")
    )
    territorio = attiva.piani[0].territorio
    assert territorio is not None
    assert territorio.boss["piano"][0].grado is Grado.CELESTIALE
    assert territorio.spawn["quartiere"][0].frequenza in {f.value for f in Frequenza}

    tag, dati = serializza_componente(attiva)
    rinata = deserializza_componente(tag, dati)
    assert rinata == attiva  # Optional[dataclass] round-trippa (fix del translator)


def test_mob_del_cast_riconosce_boss_e_spawn(mondo_isolato) -> None:
    """Il 4° strato del gate accetta i riferimenti a boss e riempitivi del
    territorio: sono contenuto del piano quanto il cast."""
    from main import _stagione_a_attiva
    from motore import crea_profondita, crea_stagione
    from motore.design import mob_del_cast

    crea_profondita()
    crea_stagione(_stagione_a_attiva(
        stagione_sintetica(piani=[piano_territoriale(1)], slug="s-mondo")
    ))
    assert mob_del_cast("t-boss-piano") is not None
    assert mob_del_cast("t-boss-paese") is not None
    assert mob_del_cast("t-riempitivo-0") is not None
    assert mob_del_cast("fantasma") is None
