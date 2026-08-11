"""T1b/T1c — il canale-asset degli oggetti e il drop per grado.

- `OggettoAsset`: forma coerente per tipo (validator), FASCE mai numeri nei
  modificatori; i numeri legali dell'authoring umano passano dal lint di banda.
- `oggetto_da_asset`: i numeri li deriva il motore (fascia × rango, categoria →
  mitigazione, grado → danno arma).
- Congelamento: `StagioneAttiva.oggetti` round-trippa nel save; il catalogo
  corrente = storico ∪ congelati (freeze batte catalogo).
- Drop per grado: dentro la finestra della profondità, ordine di pescate fisso,
  e il criterio di §4.1-3 — il corredo di riferimento è RAGGIUNGIBILE.
"""

from __future__ import annotations

import asyncio

import pytest

from contracts import (
    CategoriaArmatura,
    Fascia,
    Grado,
    ModificatoreDati,
    OggettoAsset,
    StatId,
)
from motore import (
    OggettoAttivo,
    catalogo_oggetti_correnti,
    lint_oggetto,
    oggetto_da_asset,
)
from motore.calibrazione import MITIGAZIONE_CENT, OGGETTO_MOD_FASCIA
from motore.equip import Accessorio, Arma, PezzoArmatura


def _armatura(**extra) -> OggettoAsset:
    base = dict(
        slug="pettorale-test", nome="Pettorale", tipo="armatura",
        grado=Grado.ARGENTO, slot="busto", categoria="media",
    )
    base.update(extra)
    return OggettoAsset(**base)


# --- Forma: il validator tiene i tre tipi coerenti -----------------------------

def test_forma_coerente_per_tipo() -> None:
    assert _armatura().slot is not None
    with pytest.raises(ValueError):
        _armatura(slot=None)                       # armatura senza slot
    with pytest.raises(ValueError):
        _armatura(slot="arma")                     # slot fuori famiglia armatura
    with pytest.raises(ValueError):
        OggettoAsset(slug="a", nome="A", tipo="accessorio", grado=Grado.BRONZO)  # senza sede
    with pytest.raises(ValueError):
        OggettoAsset(slug="a", nome="A", tipo="arma", grado=Grado.BRONZO,
                     sede="dita")                  # sede su un'arma
    with pytest.raises(ValueError):
        _armatura(danno_base=3)                    # danno su un'armatura
    with pytest.raises(ValueError):
        _armatura(modificatori=[
            ModificatoreDati(stat=StatId.FORZA, fascia=Fascia.LIEVE),
            ModificatoreDati(stat=StatId.FORZA, fascia=Fascia.POTENTE),
        ])                                         # stat duplicata


def test_i_modificatori_sono_fasce_mai_numeri() -> None:
    campi = set(ModificatoreDati.model_fields)
    assert campi == {"stat", "fascia"}, "un numero nel modificatore AI-facing romperebbe F-3"


# --- Lint di banda (pattern lint_profilo): il refuso resta fuori ---------------

def test_lint_banda_mitigazione() -> None:
    assert lint_oggetto(_armatura(mitigazione_cent=300)) == []
    errori = lint_oggetto(_armatura(mitigazione_cent=99999))
    assert errori and "fuori banda" in errori[0]


def test_lint_mosse_note() -> None:
    ogg = OggettoAsset(slug="a", nome="A", tipo="accessorio", grado=Grado.BRONZO,
                       sede="dita", mosse=["mossa-inventata"])
    errori = lint_oggetto(ogg)
    assert errori and "fuori catalogo" in errori[0]


# --- Traduzione: i numeri li deriva il motore ----------------------------------

def test_oggetto_da_asset_deriva_i_numeri() -> None:
    ogg = _armatura(modificatori=[
        ModificatoreDati(stat=StatId.COSTITUZIONE, fascia=Fascia.MARCATA),
    ])
    pezzo = oggetto_da_asset(ogg)
    assert isinstance(pezzo, PezzoArmatura)
    assert pezzo.fonte == "pettorale-test"
    assert pezzo.categoria is CategoriaArmatura.MEDIA
    assert pezzo.mitigazione_cent is None          # derivata dalla categoria (§11)
    # fascia × rango: MARCATA (2) × ARGENTO (rango 2) = 4.
    assert pezzo.modificatori[0].valore == OGGETTO_MOD_FASCIA["marcata"] * 2

    arma = oggetto_da_asset(OggettoAsset(
        slug="lama-test", nome="Lama", tipo="arma", grado=Grado.ORO,
    ))
    assert isinstance(arma, Arma) and arma.danno_base == 3   # DANNO_ARMA[oro]=rango

    accessorio = oggetto_da_asset(OggettoAsset(
        slug="anello-test", nome="Anello", tipo="accessorio", grado=Grado.BRONZO,
        sede="dita", mosse=["attacco"],
    ))
    assert isinstance(accessorio, Accessorio) and accessorio.mosse == ("attacco",)


def test_traduzione_identica_dalla_forma_congelata() -> None:
    """Asset e OggettoAttivo (appiattito) producono lo STESSO oggetto vivo:
    un solo traduttore, due sorgenti."""
    ogg = _armatura(modificatori=[
        ModificatoreDati(stat=StatId.FORZA, fascia=Fascia.LIEVE),
    ])
    attivo = OggettoAttivo(
        slug=ogg.slug, nome=ogg.nome, tipo=ogg.tipo, grado=ogg.grado.value,
        slot=ogg.slot.value, categoria=ogg.categoria.value, taglia=ogg.taglia.value,
        modificatori=(("forza", "lieve"),),
    )
    assert oggetto_da_asset(ogg) == oggetto_da_asset(attivo)


# --- Congelamento per-run e catalogo corrente ----------------------------------

def test_catalogo_corrente_senza_stagione_e_lo_storico(mondo_isolato) -> None:
    catalogo = catalogo_oggetti_correnti()
    assert "dadi-truccati" in catalogo             # il fallback dimostrativo
    assert "cappotto-di-scena" not in catalogo     # i seed vivono nella stagione


def test_congelamento_e_save_roundtrip(mondo_isolato, tmp_path) -> None:
    import esper

    from motore import applica_stato, carica_da_disco, salva_run, stagione_corrente
    from motore.design import StagioneAttiva, crea_stagione
    from tests.contenuti_sintetici import stagione_sintetica
    from main import _stagione_a_attiva
    from tests.persist_helpers import costruisci_run

    costruisci_run()
    base = _stagione_a_attiva(stagione_sintetica(1))
    con_oggetti = StagioneAttiva(**{
        **{c: getattr(base, c) for c in base.__dataclass_fields__},
        "oggetti": [OggettoAttivo(
            slug="anello-x", nome="Anello X", tipo="accessorio", grado="oro",
            sede="dita", modificatori=(("fortuna", "potente"),),
        )],
    })
    crea_stagione(con_oggetti)
    assert "anello-x" in catalogo_oggetti_correnti()

    salva_run(tmp_path, model_id="m1", timestamp=1.0)
    esper.clear_database()
    applica_stato(carica_da_disco(tmp_path, "carl"))
    ripresa = stagione_corrente()
    assert ripresa is not None and ripresa.oggetti[0].slug == "anello-x"
    assert ripresa.oggetti[0].modificatori == (("fortuna", "potente"),)
    assert "anello-x" in catalogo_oggetti_correnti()


def test_stagione_uno_risolve_i_seed() -> None:
    """La stagione pubblicata risolve col pool lasco (D-1: `oggetti` vuoto =
    tutta la libreria valida) e i seed passano il lint."""
    from main import risolvi_stagione

    risolta = risolvi_stagione("stagione-1")
    slugs = {o.slug for o in risolta.oggetti}
    assert {"cappotto-di-scena", "tibia-affilata", "anello-di-pellicola"} <= slugs


# --- Il drop per grado (T1c) ----------------------------------------------------

def _sessione_con_drop(tmp_path, monkeypatch):
    from main import costruisci_sessione
    from motore import calibrazione as cal

    monkeypatch.setattr(cal, "PROB_DROP", 1.0)
    sessione = costruisci_sessione(nome="Loot", seed=7, directory=tmp_path)
    asyncio.run(sessione.prossima_narrazione())
    return sessione


def test_drop_deterministico_e_nella_finestra(run_pulita, tmp_path, monkeypatch) -> None:
    from motore import gradi_per_profondita, livello_corrente, protagonista
    from motore.equip import fonti_zaino

    sessione = _sessione_con_drop(tmp_path, monkeypatch)
    for _ in range(6):
        sessione._deposita_bottino()
    pent, _m, _s = protagonista()
    drop = fonti_zaino(pent)
    assert drop, "con PROB_DROP=1 il drop non può mancare"
    # Ogni fonte pescata (finché ci sono candidati in finestra) è di un grado
    # ammesso alla profondità corrente.
    from motore import grado_oggetto

    finestra = {g.value for g in gradi_per_profondita(livello_corrente())}
    assert all(grado_oggetto(f) in finestra for f in drop[:2])
    # Determinismo: stessa sequenza con lo stesso seed.
    sessione2 = _sessione_con_drop(tmp_path, monkeypatch)
    for _ in range(6):
        sessione2._deposita_bottino()
    pent2, _m2, _s2 = protagonista()
    assert fonti_zaino(pent2) == drop


def test_corredo_di_riferimento_raggiungibile(run_pulita, tmp_path, monkeypatch) -> None:
    """Il criterio di §4.1-3, falsificabile: con PROB_DROP=1, scendendo si
    raccoglie un'armatura della categoria attesa dal corredo di riferimento
    per il grado massimo della finestra corrente."""
    from motore import gradi_per_profondita, livello_corrente, protagonista, rango_grado
    from motore.calibrazione import CORREDO_RIFERIMENTO
    from motore.equip import fonti_zaino

    ordine = ["veste", "leggera", "media", "pesante"]
    sessione = _sessione_con_drop(tmp_path, monkeypatch)
    for _ in range(12):                            # svuota i candidati in finestra
        sessione._deposita_bottino()
    pent, _m, _s = protagonista()

    grado_max = max(gradi_per_profondita(livello_corrente()), key=rango_grado)
    attesa = str(CORREDO_RIFERIMENTO[grado_max.value]["armatura"])
    catalogo = catalogo_oggetti_correnti()
    migliore = max(
        (
            ordine.index(oggetto.categoria.value)
            for fonte in fonti_zaino(pent)
            if isinstance((oggetto := catalogo.get(fonte)), PezzoArmatura)
        ),
        default=-1,
    )
    assert migliore >= ordine.index(attesa), (
        f"scendendo non si raggiunge il corredo atteso ({attesa}): il loot non sostenta"
    )
