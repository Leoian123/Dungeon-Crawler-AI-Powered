"""Il momento «genera stagione» (authoring AI): rotte registrate, gate per item
(scarta e RIPORTA, mai fallback-contenuto), applicazione atomica con gate finale
`risolvi_stagione` e rollback. Tutto offline (FakeProvider scriptato).
"""

from __future__ import annotations

import asyncio
import json

import pytest

from contracts import (
    BossGenerato,
    Grado,
    LottoBossGenerati,
    Stagione,
    TabellaProceduraleGen,
    TabellaSpawnGenerata,
    TierTerritorio,
    VoceSpawnGenerata,
)
from motore import GRADO_DA_TIER, MasterEngine, ROTTE
from provider import FakeProvider

import genera_stagione as gs
from tests.contenuti_sintetici import mob_sintetico


# --- Rotte e schemi --------------------------------------------------------------

def test_rotte_authoring_registrate() -> None:
    for nome in ("authoring.boss", "authoring.tabella", "authoring.spawn"):
        assert nome in ROTTE
        assert ROTTE[nome].gating is True   # il gate è la catena di lint
        assert ROTTE[nome].fase is None     # authoring: fuori-run, nessun World
        assert ROTTE[nome].corsia.value == "forte"


def test_authoring_viaggia_sulla_corsia_forte() -> None:
    """Il CABLAGGIO effettivo, non la dichiarazione: un engine con corsie distinte
    deve portare le rotte authoring SOLO sul provider forte (il vecchio wiring
    per-schema le faceva cadere in silenzio sul predefinito veloce)."""
    from motore import Corsia

    forte, veloce = FakeProvider([]), FakeProvider([])
    engine = MasterEngine({Corsia.FORTE: forte, Corsia.VELOCE: veloce})
    for nome in ("authoring.boss", "authoring.tabella", "authoring.spawn"):
        asyncio.run(engine.genera(nome, "compito di prova"))
    assert forte.chiamate and not veloce.chiamate


def test_boss_generato_senza_numeri_ne_grado() -> None:
    campi = set(BossGenerato.model_fields)
    assert "grado" not in campi, "il grado lo impone il tier, mai l'AI"
    assert not any("hp" in c or "danno" in c or "livello" in c for c in campi)


def test_boss_a_mob_asset_deriva_il_grado_dal_tier() -> None:
    b = BossGenerato(
        slug="il-doge-annegato", archetipo="zombie", tier=TierTerritorio.PROVINCIA,
        nome="Il Doge Annegato", descrizione="Regna su una laguna prosciugata.",
        prosa_stanza="La laguna non c'è più; lui sì.",
    )
    mob = gs.boss_a_mob_asset(b)
    assert mob.grado is GRADO_DA_TIER[TierTerritorio.PROVINCIA] is Grado.PLATINO
    assert mob.slug == "il-doge-annegato"


# --- La libreria di prova (stagione territoriale risolvibile in tmp) -------------

def _libreria_mondo(tmp_path):
    """Una libreria minima con un piano-mondo risolvibile (radice unica)."""
    from tests.test_territorio_modello import _libreria, _piano_asset_territoriale

    lich = mob_sintetico("il-lich", grado=Grado.CELESTIALE)
    riempitivo = mob_sintetico("riempitivo")
    uff, _loc = _libreria(
        tmp_path, mobs=[lich, riempitivo], piani=[_piano_asset_territoriale()],
        stagioni=[Stagione(slug="s", numero=1, titolo="S", mondo="Terra",
                           piani=["mondo"])],
    )
    return uff


def _stagione_risolta(uff):
    from main import risolvi_stagione

    return risolvi_stagione("s", ufficiali=uff, locali=uff / "mai-usata")


# --- Il batch: gate per item, scarto riportato -----------------------------------

def _boss(slug: str, *, tier=TierTerritorio.PROVINCIA, archetipo="slime") -> dict:
    return BossGenerato(
        slug=slug, archetipo=archetipo, tier=tier, nome=slug.title(),
        descrizione="Un boss d'epoca.", prosa_stanza=f"{slug} ti sbarra la strada.",
    ).model_dump()


def _tabella(tier: TierTerritorio) -> dict:
    return TabellaProceduraleGen(
        tier=tier, nomi=["a", "b", "c", "d"], gimmick=["w", "x", "y", "z"],
        archetipi=["slime"],
    ).model_dump()


def test_batch_accetta_valida_e_riporta_i_respinti(tmp_path) -> None:
    uff = _libreria_mondo(tmp_path)
    stagione = _stagione_risolta(uff)
    piano = stagione.piani[0]

    lotto = LottoBossGenerati(boss=[
        BossGenerato(**_boss("la-zarina-guasta")),
        BossGenerato(**{**_boss("l-impostore"), "archetipo": "goblin-spaziale"}),
    ]).model_dump()
    recupero = LottoBossGenerati(boss=[
        BossGenerato(**_boss("il-restauratore")),
    ]).model_dump()
    prov = FakeProvider([
        lotto,      # giro 0: authoring.boss (provincia) — 1 respinto su 2
        recupero,   # giro 1 (top-up col feedback): rimpiazza il respinto
        _tabella(TierTerritorio.DISTRETTO),     # authoring.tabella (in parallelo)
        _tabella(TierTerritorio.QUARTIERE),
        TabellaSpawnGenerata(tier=TierTerritorio.QUARTIERE, voci=[
            VoceSpawnGenerata(mob="riempitivo"),
        ]).model_dump(),
        TabellaSpawnGenerata(tier=TierTerritorio.CITTA, voci=[
            VoceSpawnGenerata(mob="mob-inventato"),  # fuori: mob inesistente
        ]).model_dump(),
        # il retry dello spawn città trova la coda vuota → degrada, riportato
    ])
    mob_nuovi, tabelle, spawn, per_tier, respinti = asyncio.run(gs.genera_roster(
        MasterEngine.avvolgi(prov), stagione, piano,
        n_per_tier={TierTerritorio.PROVINCIA: 2, TierTerritorio.CITTA: 0},
        ufficiali=uff, locali=uff / "mai-usata",
    ))
    assert [m.slug for m in mob_nuovi] == ["la-zarina-guasta", "il-restauratore"]
    assert mob_nuovi[0].grado is Grado.PLATINO  # il grado dal tier, mai dall'AI
    assert per_tier[TierTerritorio.PROVINCIA] == ["la-zarina-guasta", "il-restauratore"]
    assert len(tabelle) == 2 and len(spawn) == 1
    # Gli scarti sono RIPORTATI, mai rimpiazzati in silenzio.
    assert any("goblin-spaziale" in r or "l-impostore" in r for r in respinti)
    assert any("mob-inventato" in r for r in respinti)
    # Il top-up porta il MOTIVO dello scarto nel prompt (dinamico, mai in sistema).
    prompt_topup = prov.prompt_ricevuti[1]
    assert "[respinti]" in prompt_topup and "goblin-spaziale" in prompt_topup
    assert "la-zarina-guasta" in prompt_topup  # i vietati aggiornati con gli accettati


def test_contesto_in_sistema_e_dinamici_nel_prompt(tmp_path) -> None:
    """Prompt caching: il contesto condiviso viaggia in `sistema=` byte-identico
    per TUTTE le chiamate; vietati/feedback/mob-disponibili (dinamici) stanno
    solo nel prompt utente — una riga dinamica nel sistema azzererebbe la cache."""
    uff = _libreria_mondo(tmp_path)
    stagione = _stagione_risolta(uff)
    piano = stagione.piani[0]

    prov = FakeProvider([
        LottoBossGenerati(boss=[BossGenerato(**_boss("la-zarina-guasta"))]).model_dump(),
        _tabella(TierTerritorio.DISTRETTO),
        _tabella(TierTerritorio.QUARTIERE),
        TabellaSpawnGenerata(tier=TierTerritorio.QUARTIERE,
                             voci=[VoceSpawnGenerata(mob="riempitivo")]).model_dump(),
        TabellaSpawnGenerata(tier=TierTerritorio.CITTA,
                             voci=[VoceSpawnGenerata(mob="riempitivo")]).model_dump(),
    ])
    asyncio.run(gs.genera_roster(
        MasterEngine.avvolgi(prov), stagione, piano,
        n_per_tier={TierTerritorio.PROVINCIA: 1, TierTerritorio.CITTA: 0},
        ufficiali=uff, locali=uff / "mai-usata",
    ))
    atteso = gs.contesto_prompt(stagione, piano)
    assert prov.sistemi and all(s == atteso for s in prov.sistemi)
    assert "[vocabolario/mosse]" in atteso
    for prompt in prov.prompt_ricevuti:
        assert "[vocabolario" not in prompt  # il contesto non si ripete nel prompt


def test_dedup_tra_lotti_paralleli(tmp_path) -> None:
    """Due lotti dello stesso giro non si vedono a vicenda: il gate seriale
    post-gather dedupa gli slug in collisione — uno accettato, l'altro respinto
    e RIPORTATO (mai sostituito in silenzio)."""
    uff = _libreria_mondo(tmp_path)
    stagione = _stagione_risolta(uff)
    piano = stagione.piani[0]

    gemello = LottoBossGenerati(boss=[BossGenerato(**_boss("il-gemello"))]).model_dump()
    prov = FakeProvider([gemello, gemello])  # stesso slug da due lotti paralleli
    mob_nuovi, _t, _s, per_tier, respinti = asyncio.run(gs.genera_roster(
        MasterEngine.avvolgi(prov), stagione, piano,
        n_per_tier={TierTerritorio.PROVINCIA: 6, TierTerritorio.CITTA: 0},  # 6 → 2 lotti
        ufficiali=uff, locali=uff / "mai-usata",
    ))
    assert [m.slug for m in mob_nuovi] == ["il-gemello"]
    assert any("duplicato" in r for r in respinti)
    # Il giro 0 ha lanciato DUE lotti (5+1) prima di qualunque gate.
    assert sum("[respinti]" not in p for p in prov.prompt_ricevuti[:2]) == 2


def test_applica_scrive_e_il_gate_finale_tiene(tmp_path) -> None:
    uff = _libreria_mondo(tmp_path)
    stagione = _stagione_risolta(uff)
    piano = stagione.piani[0]
    nuovo = gs.boss_a_mob_asset(BossGenerato(**_boss("la-zarina-guasta")))

    errori = gs.applica(
        "s", piano.slug, [nuovo], [], [],
        {TierTerritorio.PROVINCIA: ["la-zarina-guasta"], TierTerritorio.CITTA: []},
        radice=uff, locali=uff / "mai-usata",
    )
    assert errori == []
    assert (uff / "mob" / "la-zarina-guasta.json").exists()
    aggiornato = json.loads((uff / "piani" / "mondo.json").read_text(encoding="utf-8"))
    assert "la-zarina-guasta" in aggiornato["territorio"]["boss"]["provincia"]
    # E la stagione aggiornata risolve davvero (il gate finale è passato).
    risolta = _stagione_risolta(uff)
    roster = risolta.piani[0].territorio.boss[TierTerritorio.PROVINCIA]
    assert any(m.slug == "la-zarina-guasta" for m in roster)


def test_applica_rollback_se_il_gate_finale_fallisce(tmp_path) -> None:
    """Un mob che i lint di risoluzione respingono (archetipo mai visto) NON deve
    lasciare la libreria a metà: rollback completo, piano intatto."""
    uff = _libreria_mondo(tmp_path)
    piano_prima = (uff / "piani" / "mondo.json").read_text(encoding="utf-8")
    marcio = mob_sintetico("boss-marcio", archetipo="archetipo-fantasma",
                           grado=Grado.PLATINO)

    errori = gs.applica(
        "s", "mondo", [marcio], [], [],
        {TierTerritorio.PROVINCIA: ["boss-marcio"], TierTerritorio.CITTA: []},
        radice=uff, locali=uff / "mai-usata",
    )
    assert errori and "ROLLBACK" in errori[0]
    assert not (uff / "mob" / "boss-marcio.json").exists()
    assert (uff / "piani" / "mondo.json").read_text(encoding="utf-8") == piano_prima
