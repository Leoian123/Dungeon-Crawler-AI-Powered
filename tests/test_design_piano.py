"""Stagioni/Piani/Mob: validatori, risoluzione, freeze nel save, gate, affinità.

La libreria è normalizzata (riferimenti per slug); il runtime consuma SOLO la
stagione risolta e congelata nel World. Tutto offline, disciplina ESP §0.1.
"""

from __future__ import annotations

import asyncio

import pytest

from contracts import (
    Blocco,
    BudgetDesign,
    Grado,
    MobAsset,
    PianoAsset,
    PianoRisolto,
    Stagione,
)
from main import (
    STAGIONE_DEFAULT,
    _stagione_a_attiva,
    _turni_scriptati,
    affini,
    carica_sessione,
    costruisci_sessione,
    elenca_asset,
    risolvi_stagione,
    salva_asset_locale,
    turni_da_piano,
)
from motore import stagione_corrente
from motore.catalogo import prepara_contesto
from motore.narrazione import valida_turno


def _mob(slug: str, *, grado=Grado.BRONZO, archetipo="slime",
         blocchi=(), tags=()) -> MobAsset:
    return MobAsset(
        slug=slug, nome=slug.replace("-", " ").title(), archetipo=archetipo,
        grado=grado, blocchi=list(blocchi), prosa_stanza=f"La scena di {slug}.",
        tags=list(tags),
    )


def _budget(**kw) -> BudgetDesign:
    kw.setdefault("gradi", [Grado.BRONZO, Grado.ARGENTO])
    kw.setdefault("blocchi", [Blocco.VELENO, Blocco.RIGENERAZIONE])
    kw.setdefault("archetipi", ["slime", "scheletro", "goblin"])
    return BudgetDesign(**kw)


# --- Validatori (lint di forma, deterministico) --------------------------------

def test_cast_fuori_budget_respinto_dal_validator() -> None:
    with pytest.raises(ValueError, match="fuori budget"):
        PianoRisolto(
            slug="p", versione=1, titolo="P", tema="t",
            budget=_budget(gradi=[Grado.BRONZO]),
            cast=[_mob("m", grado=Grado.ORO)],
        )


def test_tag_e_slug_malformati_respinti() -> None:
    with pytest.raises(ValueError):
        _mob("m", tags=["Tag Con Spazi"])
    with pytest.raises(ValueError):
        MobAsset(slug="Maiuscolo", nome="X", archetipo="slime",
                 grado=Grado.BRONZO, prosa_stanza="p")
    with pytest.raises(ValueError, match="duplicate"):
        BudgetDesign(gradi=[Grado.BRONZO, Grado.BRONZO], archetipi=["slime"])


# --- Parità: la Falsa Idra derivata dalla libreria = il vecchio copione ---------

def test_parita_falsa_idra() -> None:
    turni = _turni_scriptati()
    assert [t.entita.nome for t in turni] == [
        "Slime Mangiascarti", "Goblin Bigliettaio", "Scheletro Sarto",
        "Gemelli nel Trench", "Goblin Burattinaio", "Coro delle Ossa",
        "Slime Madre", "Il Regista",
    ]
    assert "Rolex" in turni[0].prosa
    assert all(t.entita.grado in {Grado.BRONZO, Grado.ARGENTO} for t in turni)


# --- Risoluzione: riferimenti e coerenza sono errori di AUTHORING ---------------

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


def test_risoluzione_riferimenti_pendenti(tmp_path) -> None:
    uff, loc = _libreria(
        tmp_path,
        stagioni=[Stagione(slug="s", numero=1, titolo="S", mondo="Terra",
                           piani=["fantasma"])],
    )
    with pytest.raises(ValueError, match="fantasma"):
        risolvi_stagione("s", ufficiali=uff, locali=loc)


def test_risoluzione_cast_fuori_budget(tmp_path) -> None:
    uff, loc = _libreria(
        tmp_path,
        mobs=[_mob("oro", grado=Grado.ORO)],
        piani=[PianoAsset(slug="p", titolo="P", tema="t",
                          budget=_budget(gradi=[Grado.BRONZO]), cast=["oro"])],
        stagioni=[Stagione(slug="s", numero=1, titolo="S", mondo="Terra", piani=["p"])],
    )
    with pytest.raises(ValueError, match="fuori budget"):
        risolvi_stagione("s", ufficiali=uff, locali=loc)


# --- Budget dal design + gate archetipi -----------------------------------------

class _RngFisso:
    def __init__(self, valore: float) -> None:
        self._valore = valore

    def random(self) -> float:
        return self._valore


def _piano_attivo_default():
    """Il piano 1 della stagione di default nella forma ATTIVA (quella che il
    motore consuma: `prepara_contesto` è duck-typed su gradi/blocchi/archetipi)."""
    return _stagione_a_attiva(risolvi_stagione(STAGIONE_DEFAULT)).piani[0]


def test_prepara_contesto_dal_piano() -> None:
    piano = _piano_attivo_default()
    budget = prepara_contesto(1, _RngFisso(0.99), piano=piano)
    assert budget.gradi_ammessi == frozenset(piano.gradi)
    assert budget.blocchi_ammessi == frozenset(piano.blocchi)
    assert budget.archetipi_ammessi == frozenset(piano.archetipi)
    assert budget.archetipo_default == piano.archetipi[0]
    assert budget.anomala is False


def test_anomalia_non_cappata_dal_design() -> None:
    budget = prepara_contesto(1, _RngFisso(0.0), piano=_piano_attivo_default())
    assert budget.anomala is True  # tiro anomalo del motore
    assert budget.gradi_ammessi == frozenset(Grado)  # il delirio è del motore


def test_gate_respinge_archetipo_fuori_design() -> None:
    turni = _turni_scriptati()
    goblin = next(t for t in turni if t.entita.archetipo == "goblin")
    piano = _piano_attivo_default()
    from dataclasses import replace

    solo_slime = prepara_contesto(
        1, _RngFisso(0.99), piano=replace(piano, archetipi=["slime"])
    )
    assert valida_turno(goblin, solo_slime) is None
    tutti = prepara_contesto(1, _RngFisso(0.99))  # segnaposto: tutti gli archetipi
    assert valida_turno(goblin, tutti) is not None


# --- Freeze nel save: la stagione viaggia e torna -------------------------------

def test_stagione_congelata_round_trip_nel_save(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(nome="Freeze", seed=1, directory=tmp_path)
    attiva = stagione_corrente()
    assert attiva is not None and attiva.slug == STAGIONE_DEFAULT
    snap = asyncio.run(sessione.prossima_narrazione())
    prosa = snap.prosa
    uuid = sessione.uuid
    sessione.esci()

    ripresa = carica_sessione(uuid=uuid, directory=tmp_path)
    assert ripresa is not None
    tornata = stagione_corrente()
    assert tornata is not None
    assert tornata.slug == STAGIONE_DEFAULT and tornata.numero == 1
    [piano] = tornata.piani
    assert piano.cast[0].nome == "Slime Mangiascarti"
    assert piano.cast[0].archetipo == "slime"  # enum RICOSTRUITO, non str
    # La stanza già narrata è RILETTA (cache): la storia non si riscrive.
    snap2 = asyncio.run(ripresa.prossima_narrazione())
    assert snap2.prosa == prosa


# --- Giro derivato da una stagione ad hoc ---------------------------------------

def test_giro_derivato_da_stagione_ad_hoc(run_pulita, tmp_path) -> None:
    mobs = [_mob(f"testa-{i}", tags=["mini"]) for i in range(3)]
    uff, loc = _libreria(
        tmp_path, mobs=mobs,
        piani=[PianoAsset(slug="mini", titolo="Mini", tema="tre stanze",
                          budget=_budget(), cast=[m.slug for m in mobs])],
        stagioni=[Stagione(slug="s-mini", numero=2, titolo="Mini", mondo="Luna",
                           piani=["mini"])],
    )
    risolta = risolvi_stagione("s-mini", ufficiali=uff, locali=loc)
    sessione = costruisci_sessione(
        nome="Mini", seed=1, directory=tmp_path / "save", stagione=risolta
    )
    from motore import mappa_corrente

    snap = asyncio.run(sessione.prossima_narrazione())
    assert "testa-0" in snap.prosa  # il copione deriva dal cast
    _e, mappa = mappa_corrente()
    assert len(mappa.piano.adiacenze) == 3  # la scala del piano = il cast


# --- Affinità (riuso deterministico) e libreria ---------------------------------

def test_affinita_ordina_per_sovrapposizione(tmp_path) -> None:
    uff, loc = _libreria(
        tmp_path,
        mobs=[
            _mob("a", tags=["teatro", "truffa"]),
            _mob("b", tags=["teatro"]),
            _mob("c", tags=["cucina"]),
        ],
    )
    risultato = affini(["teatro", "truffa"], tipo="mob", ufficiali=uff, locali=loc)
    assert [v.slug for v in risultato] == ["a", "b"]  # c non affine: escluso
    # Le categorie contano come tag impliciti.
    per_archetipo = affini(["slime"], tipo="mob", ufficiali=uff, locali=loc)
    assert {v.slug for v in per_archetipo} == {"a", "b", "c"}


def test_libreria_locale_crud_e_ombreggiatura(tmp_path) -> None:
    uff, loc = _libreria(tmp_path, mobs=[_mob("ufficiale-x")])
    nuovo = _mob("locale-y", tags=["nuovo"])
    salva_asset_locale(nuovo, ufficiali=uff, locali=loc)
    slugs = {v.slug: v.origine for v in elenca_asset("mob", ufficiali=uff, locali=loc)}
    assert slugs == {"ufficiale-x": "ufficiale", "locale-y": "locale"}
    # Slug riservato a un ufficiale: respinto.
    with pytest.raises(ValueError, match="riservato"):
        salva_asset_locale(_mob("ufficiale-x"), ufficiali=uff, locali=loc)
    # Doppione locale senza sovrascrivi: respinto.
    with pytest.raises(ValueError, match="esistente"):
        salva_asset_locale(nuovo, ufficiali=uff, locali=loc)
    # File corrotto: voce mostrata, non usabile, nessun crash.
    (loc / "mob" / "rotto.json").write_text("{non-json", encoding="utf-8")
    viste = {v.slug: v for v in elenca_asset("mob", ufficiali=uff, locali=loc)}
    assert viste["rotto"].valido is False
