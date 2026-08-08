"""Fase 3 — gli ARCHETIPI sono asset di libreria (D1): si creano come DATI, si
risolvono col merge di calibrazione (storici) o col profilo completo (nuovi), si
CONGELANO nella StagioneAttiva e il gate valida contro quel registry (F-6 runtime).
Zero codice per un archetipo nuovo: un JSON, e il motore lo mette in scena.
"""

from __future__ import annotations

import esper
import pytest

from contracts import (
    ArchetipoAsset,
    BudgetDesign,
    EntitaGenerata,
    Grado,
    MobAsset,
    PianoAsset,
    ProfiloArchetipoDati,
    SchedaProiezione,
    Stagione,
    StatId,
    TipoDanno,
)
from main import _stagione_a_attiva, risolvi_stagione, salva_asset_locale
from motore import (
    Budget,
    Repertorio,
    costruisci_prompt,
    crea_stagione,
    istanzia_entita,
    rango_grado,
    registry_archetipi_correnti,
    valida_turno,
)
from motore.calibrazione import REGISTRY_ARCHETIPI
from motore.corredo import Corredo
from motore.statistiche import Primarie
from tests.narr_helpers import turno

_PROFILO_RATTO = ProfiloArchetipoDati(
    destrezza_base=6, pv_base=9, danno_base=2, intelligenza_base=2, difesa_base=0,
    saggezza_base=1, fortuna_base=2, armatura="leggera", taglia="piccola",
    arma="naturale", res_veleno=-50.0,
)


def _scrivi(cartella, tipo: str, asset) -> None:
    base = cartella / tipo
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{asset.slug}.json").write_text(asset.model_dump_json(), encoding="utf-8")


def _libreria_ratti(tmp_path, *, profilo=_PROFILO_RATTO, mosse=("morso_velenoso",)):
    """Una stagione locale con un archetipo INVENTATO, mai visto dal codice."""
    uff, loc = tmp_path / "uff", tmp_path / "loc"
    _scrivi(loc, "archetipi", ArchetipoAsset(
        slug="ratto-mutante", nome="il Ratto Mutante", profilo=profilo, mosse=list(mosse),
    ))
    _scrivi(loc, "mob", MobAsset(
        slug="ratto-uno", nome="Ratto Alfa", archetipo="ratto-mutante",
        grado=Grado.BRONZO, prosa_stanza="Un fruscio nel condotto.",
    ))
    _scrivi(loc, "piani", PianoAsset(
        slug="tana", titolo="La Tana", tema="condotti",
        budget=BudgetDesign(gradi=[Grado.BRONZO], archetipi=["ratto-mutante"]),
        cast=["ratto-uno"],
    ))
    _scrivi(loc, "stagioni", Stagione(
        slug="s-ratti", numero=1, titolo="Ratti", mondo="Terra", piani=["tana"],
    ))
    return uff, loc


def test_archetipo_nuovo_da_dati_risolto_e_congelato(mondo_isolato, tmp_path) -> None:
    uff, loc = _libreria_ratti(tmp_path)
    risolta = risolvi_stagione("s-ratti", ufficiali=uff, locali=loc)
    assert [a.slug for a in risolta.archetipi] == ["ratto-mutante"]
    assert risolta.archetipi[0].profilo.pv_base == 9  # profilo pieno, com'era nei dati

    crea_stagione(_stagione_a_attiva(risolta))
    registro = registry_archetipi_correnti()
    assert "ratto-mutante" in registro and set(REGISTRY_ARCHETIPI) <= set(registro)

    # Il mob si MATERIALIZZA con la formula-madre applicata al profilo-asset.
    eg = EntitaGenerata(
        archetipo="ratto-mutante", grado=Grado.BRONZO, blocchi=[],
        nome="Ratto Alfa", descrizione="",
    )
    ent = istanzia_entita(eg, livello=1)
    rango = rango_grado(Grado.BRONZO)
    primarie = esper.component_for_entity(ent, Primarie).valori
    assert primarie[StatId.FORZA] == 2 * rango          # danno_base × rango × livello
    assert primarie[StatId.COSTITUZIONE] == 9 * rango   # pv_base × rango × livello
    assert primarie[StatId.DESTREZZA] == 6 + rango
    corredo = esper.component_for_entity(ent, Corredo)
    assert (corredo.armatura, corredo.taglia, corredo.arma) == ("leggera", "piccola", "naturale")
    # Il repertorio dell'archetipo-asset (mosse come dato, eseguite dal system).
    assert tuple(esper.component_for_entity(ent, Repertorio).mosse) == ("morso_velenoso",)


def test_gate_runtime_su_registry_congelato(mondo_isolato, tmp_path) -> None:
    uff, loc = _libreria_ratti(tmp_path)
    crea_stagione(_stagione_a_attiva(risolvi_stagione("s-ratti", ufficiali=uff, locali=loc)))
    bud = Budget(
        livello=1, gradi_ammessi=frozenset({Grado.BRONZO}), blocchi_ammessi=frozenset(),
        archetipo_default="ratto-mutante", archetipi_ammessi=frozenset({"ratto-mutante"}),
    )
    # L'archetipo-asset congelato PASSA il gate (F-6 runtime)...
    assert valida_turno(turno(archetipo="ratto-mutante", blocchi=()), bud) is not None
    # ...un nome ben formato ma fuori registry NO (strato 2), anche se in budget.
    bud_bucato = Budget(
        livello=1, gradi_ammessi=frozenset({Grado.BRONZO}), blocchi_ammessi=frozenset(),
        archetipo_default="slime", archetipi_ammessi=frozenset({"drago-abusivo"}),
    )
    assert valida_turno(turno(archetipo="drago-abusivo", blocchi=()), bud_bucato) is None


def test_slug_nuovo_con_profilo_incompleto_e_errore_di_authoring(tmp_path) -> None:
    parziale = ProfiloArchetipoDati(destrezza_base=6)  # manca quasi tutto
    uff, loc = _libreria_ratti(tmp_path, profilo=parziale)
    with pytest.raises(ValueError, match="profilo incompleto"):
        risolvi_stagione("s-ratti", ufficiali=uff, locali=loc)


def test_mosse_fuori_catalogo_sono_errore(tmp_path) -> None:
    uff, loc = _libreria_ratti(tmp_path, mosse=("raggio-della-morte",))
    with pytest.raises(ValueError, match="mosse fuori catalogo"):
        risolvi_stagione("s-ratti", ufficiali=uff, locali=loc)


def test_storici_risolvono_senza_asset_col_profilo_di_calibrazione(tmp_path) -> None:
    """La stagione ufficiale continua a funzionare: gli storici ereditano i numeri
    dalla calibrazione (che resta la loro autorità) anche senza profilo nell'asset."""
    risolta = risolvi_stagione("stagione-1")  # libreria ufficiale del repo
    slugs = {a.slug for a in risolta.archetipi}
    # Gli storici ci sono tutti; la stagione può averne ALTRI (il `felino` è arrivato
    # col dodger di F7, e porta il proprio profilo nell'asset invece di ereditarlo).
    assert {"slime", "scheletro", "goblin"} <= slugs
    slime = next(a for a in risolta.archetipi if a.slug == "slime")
    atteso = REGISTRY_ARCHETIPI["slime"]
    assert slime.profilo.pv_base == atteso.pv_base
    assert slime.profilo.taglia == atteso.taglia


def test_senza_stagione_il_registry_sono_gli_storici(mondo_isolato) -> None:
    assert registry_archetipi_correnti() == REGISTRY_ARCHETIPI  # harness/save legacy


def test_F10_archetipi_ammessi_nel_prompt() -> None:
    bud = Budget(
        livello=1, gradi_ammessi=frozenset({Grado.BRONZO}), blocchi_ammessi=frozenset(),
        archetipo_default="ratto-mutante",
        archetipi_ammessi=frozenset({"ratto-mutante", "slime"}),
    )
    prompt = costruisci_prompt(bud, SchedaProiezione(descrittori=("integro",)), "voce")
    assert "[budget] archetipi ammessi: ratto-mutante, slime" in prompt


def test_run_completa_con_archetipo_inventato(run_pulita, tmp_path) -> None:
    """La fetta verticale: stagione locale → risoluzione → freeze → reveal → scontro,
    tutto offline e senza una riga di codice per il nuovo archetipo. Il mob combatte
    col SUO profilo (via porte di SessioneGioco, come un host vero)."""
    import asyncio

    from contracts import ColpoInferto, PlayerChoseOption
    from main import costruisci_sessione

    uff, loc = _libreria_ratti(tmp_path)
    risolta = risolvi_stagione("s-ratti", ufficiali=uff, locali=loc)
    sessione = costruisci_sessione(
        nome="Carl", seed=3, directory=tmp_path / "save", stagione=risolta,
    )
    colpi: list[ColpoInferto] = []
    sessione.bus.registra(ColpoInferto, colpi.append)
    try:
        snap = asyncio.run(sessione.prossima_narrazione())
        assert "fruscio" in snap.prosa  # il copione offline del mob-asset
        indice = next(o.indice for o in snap.opzioni if o.etichetta == "Combatti")
        sessione.coda.accoda(PlayerChoseOption(indice))
        snap = sessione.avanza()
        guardia = 0
        while snap.fase == "combattimento" and guardia < 20:
            sessione.coda.accoda(PlayerChoseOption(0))  # Attacca
            snap = sessione.avanza()
            guardia += 1
        assert snap.fase == "narrazione" and sessione.scheda().hp > 0
        # Il nemico ha agito con la mossa del SUO repertorio-asset (dato, non codice).
        del_ratto = [c for c in colpi if c.attaccante == "Ratto Alfa"]
        assert all(c.mossa == "morso_velenoso" for c in del_ratto)
    finally:
        sessione.bus.deregistra(ColpoInferto, colpi.append)


# --- Fase 5: riferimento (reclutamento) + override/mosse per-mob -----------------

def test_riferimento_monta_il_mob_del_cast_con_override(run_pulita, tmp_path) -> None:
    """Il binding esplicito (D5): la scena monta ESATTAMENTE il mob citato, col suo
    override di profilo (pv_base diverso dall'archetipo) e le sue mosse."""
    import asyncio

    from contracts import PlayerChoseOption
    from main import costruisci_sessione
    from motore import Repertorio as Rep
    from motore import mob_corrente
    from motore.statistiche import Primarie as Prim
    import esper as esper_mod

    uff, loc = tmp_path / "uff", tmp_path / "loc"
    _scrivi(loc, "archetipi", ArchetipoAsset(
        slug="ratto-mutante", nome="il Ratto", profilo=_PROFILO_RATTO,
        mosse=["morso_velenoso"],
    ))
    _scrivi(loc, "mob", MobAsset(
        slug="ratto-re", nome="Ratto Re", archetipo="ratto-mutante",
        grado=Grado.BRONZO, prosa_stanza="Il trono di ossicini.",
        mosse=["attacco_pesante"],                       # vince sull'archetipo
        override=ProfiloArchetipoDati(pv_base=30),       # vince campo-per-campo
    ))
    _scrivi(loc, "piani", PianoAsset(
        slug="tana", titolo="La Tana", tema="condotti",
        budget=BudgetDesign(gradi=[Grado.BRONZO], archetipi=["ratto-mutante"]),
        cast=["ratto-re"],
    ))
    _scrivi(loc, "stagioni", Stagione(
        slug="s-re", numero=1, titolo="Re", mondo="Terra", piani=["tana"],
    ))
    sessione = costruisci_sessione(
        nome="Carl", seed=1, directory=tmp_path / "save",
        stagione=risolvi_stagione("s-re", ufficiali=uff, locali=loc),
    )
    try:
        asyncio.run(sessione.prossima_narrazione())  # il reveal della stanza
        ent = mob_corrente()
        assert ent is not None
        prim = esper_mod.component_for_entity(ent, Prim).valori
        assert prim[StatId.COSTITUZIONE] == 30 * rango_grado(Grado.BRONZO)  # override
        assert prim[StatId.DESTREZZA] == 6 + rango_grado(Grado.BRONZO)      # dall'archetipo
        assert tuple(esper_mod.component_for_entity(ent, Rep).mosse) == ("attacco_pesante",)
    finally:
        del sessione


def test_riferimento_fuori_cast_cade_in_fallback(mondo_isolato, tmp_path) -> None:
    from motore import crea_profondita

    uff, loc = _libreria_ratti(tmp_path)
    crea_profondita(1)  # il piano corrente è una derivazione da stagione+profondità
    crea_stagione(_stagione_a_attiva(risolvi_stagione("s-ratti", ufficiali=uff, locali=loc)))
    bud = Budget(
        livello=1, gradi_ammessi=frozenset({Grado.BRONZO}), blocchi_ammessi=frozenset(),
        archetipo_default="ratto-mutante", archetipi_ammessi=frozenset({"ratto-mutante"}),
    )
    dentro = turno(archetipo="ratto-mutante", blocchi=())
    dentro = dentro.model_copy(update={
        "entita": dentro.entita.model_copy(update={"riferimento": "ratto-uno"})
    })
    assert valida_turno(dentro, bud) is not None      # slug del cast → passa
    fuori = dentro.model_copy(update={
        "entita": dentro.entita.model_copy(update={"riferimento": "imbucato"})
    })
    assert valida_turno(fuori, bud) is None           # fuori cast → fallback (F-13)


def test_mosse_per_mob_fuori_catalogo_sono_errore(tmp_path) -> None:
    uff, loc = _libreria_ratti(tmp_path)
    _scrivi(loc, "mob", MobAsset(
        slug="ratto-uno", nome="Ratto Alfa", archetipo="ratto-mutante",
        grado=Grado.BRONZO, prosa_stanza="Squittisce.", mosse=["urlo-cosmico"],
    ))
    with pytest.raises(ValueError, match="mosse fuori catalogo"):
        risolvi_stagione("s-ratti", ufficiali=uff, locali=loc)


def test_salvataggio_locale_lint_archetipo(tmp_path) -> None:
    """`salva_asset_locale` anticipa il lint: profilo incompleto su slug nuovo e
    chiavi gear invalide muoiono al salvataggio, non alla risoluzione."""
    loc = tmp_path / "loc"
    with pytest.raises(ValueError, match="profilo incompleto"):
        salva_asset_locale(
            ArchetipoAsset(slug="mezzo-fatto", nome="X",
                           profilo=ProfiloArchetipoDati(pv_base=5)),
            ufficiali=tmp_path / "uff", locali=loc,
        )
    rotto = ProfiloArchetipoDati(**{
        **_PROFILO_RATTO.model_dump(), "taglia": "gigachad",
    })
    with pytest.raises(ValueError, match="chiave di tabella"):
        salva_asset_locale(
            ArchetipoAsset(slug="rotto", nome="X", profilo=rotto),
            ufficiali=tmp_path / "uff", locali=loc,
        )
    # Un mob che usa un archetipo della libreria locale PASSA il lint.
    salva_asset_locale(
        ArchetipoAsset(slug="ratto-mutante", nome="il Ratto", profilo=_PROFILO_RATTO),
        ufficiali=tmp_path / "uff", locali=loc,
    )
    salva_asset_locale(
        MobAsset(slug="ratto-due", nome="Ratto Beta", archetipo="ratto-mutante",
                 grado=Grado.BRONZO, prosa_stanza="Squittisce."),
        ufficiali=tmp_path / "uff", locali=loc,
    )
