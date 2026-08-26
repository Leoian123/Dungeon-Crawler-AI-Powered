"""T3 — le mosse come asset (GR2 §7, Corsia 2) e il generatore `authoring.mossa`.

- Il VALIDATORE di `MossaAsset` è il gate di composizione (PMF-6.3/6.4) e vale
  identico per umano, AI e file a mano.
- `mossa_da_dati` è l'unico traduttore (fasce §11 → numeri); `mossa_di` l'unico
  lookup runtime: una mossa-asset congelata è pagabile ed eseguibile come una
  storica, e round-trippa nel save.
"""

from __future__ import annotations

import asyncio

import pytest

from contracts import (
    Blocco,
    EffettoDati,
    FasciaCosto,
    FasciaPotenza,
    FasciaRicarica,
    LottoMosseAutorate,
    MossaAsset,
    TipoDanno,
)
from motore import (
    MasterEngine,
    ROTTE,
    catalogo_mosse_correnti,
    etichetta_mossa,
    mossa_da_dati,
    mossa_di,
    mosse_note_correnti,
)
from motore.azione import ApplicaStatus, Danno
from motore.calibrazione import FASCIA_COSTO_MOSSA, FASCIA_POTENZA_MOSSA
from provider import FakeProvider


def _mossa(slug: str = "colpo-di-prova", **extra) -> MossaAsset:
    base = dict(
        slug=slug, etichetta="Colpo di prova",
        effetti=[EffettoDati(primitivo="danno", tipo_danno=TipoDanno.MISCHIA,
                             potenza=FasciaPotenza.PESANTE)],
        costo=FasciaCosto.STANDARD, ricarica=FasciaRicarica.BREVE,
    )
    base.update(extra)
    return MossaAsset(**base)


# --- Il validatore di composizione (PMF-6.4): un solo gate ----------------------

def test_composizione_esattamente_un_danno() -> None:
    with pytest.raises(ValueError, match="ESATTAMENTE un primitivo di danno"):
        _mossa(effetti=[
            EffettoDati(primitivo="danno", tipo_danno=TipoDanno.MISCHIA),
            EffettoDati(primitivo="danno", tipo_danno=TipoDanno.FUOCO),
        ])
    with pytest.raises(ValueError, match="ESATTAMENTE un primitivo di danno"):
        _mossa(effetti=[EffettoDati(primitivo="applica_status", blocco=Blocco.VELENO)])


def test_status_mai_prima_del_danno() -> None:
    with pytest.raises(ValueError, match="a_segno"):
        _mossa(effetti=[
            EffettoDati(primitivo="applica_status", blocco=Blocco.VELENO),
            EffettoDati(primitivo="danno", tipo_danno=TipoDanno.VELENO),
        ])


def test_azzardo_e_consenso_coerente() -> None:
    with pytest.raises(ValueError, match="azzardo"):
        _mossa(azzardo=True)                       # dichiarato ma senza danno_variabile
    with pytest.raises(ValueError, match="azzardo"):
        _mossa(effetti=[EffettoDati(primitivo="danno_variabile",
                                    tipo_danno=TipoDanno.GENERICO)])  # pesca non dichiarata
    ok = _mossa(effetti=[EffettoDati(primitivo="danno_variabile",
                                     tipo_danno=TipoDanno.GENERICO)], azzardo=True)
    assert ok.azzardo is True


def test_nessun_campo_numerico_nella_mossa_asset() -> None:
    campi = set(MossaAsset.model_fields) | set(EffettoDati.model_fields)
    assert not campi & {"moltiplicatore", "costo_mana", "cooldown", "minimo", "massimo"}, \
        "un numero nella mossa-asset romperebbe la linea rossa: solo fasce"


# --- Traduzione e lookup --------------------------------------------------------

def test_mossa_da_dati_deriva_i_numeri_dalle_fasce() -> None:
    viva = mossa_da_dati(_mossa())
    assert viva.chiave == "colpo-di-prova"
    assert viva.costo_mana == FASCIA_COSTO_MOSSA["standard"]
    assert viva.cooldown > 0
    danno = viva.effetti[0]
    assert isinstance(danno, Danno) and danno.tipo is TipoDanno.MISCHIA
    assert danno.moltiplicatore == FASCIA_POTENZA_MOSSA["pesante"]

    con_status = mossa_da_dati(_mossa(effetti=[
        EffettoDati(primitivo="danno", tipo_danno=TipoDanno.VELENO),
        EffettoDati(primitivo="applica_status", blocco=Blocco.VELENO),
    ]))
    assert isinstance(con_status.effetti[1], ApplicaStatus)
    assert con_status.effetti[1].blocco is Blocco.VELENO


def test_mossa_congelata_pagabile_ed_eseguibile(mondo_isolato) -> None:
    """Una mossa-asset congelata nella run si seleziona, si paga e si risolve
    nelle tre giunture identicamente a una storica."""
    from motore import mossa_pagabile
    from motore.design import EffettoAttivo, MossaAttiva, StagioneAttiva, crea_stagione
    from main import _stagione_a_attiva
    from tests.contenuti_sintetici import stagione_sintetica
    from tests.persist_helpers import costruisci_run
    import esper

    from motore.mob import Repertorio

    pent = costruisci_run()
    base = _stagione_a_attiva(stagione_sintetica(1))
    con_mosse = StagioneAttiva(**{
        **{c: getattr(base, c) for c in base.__dataclass_fields__},
        "mosse": [MossaAttiva(
            chiave="colpo-di-prova", etichetta="Colpo di prova",
            effetti=(EffettoAttivo(primitivo="danno", tipo_danno="mischia",
                                   potenza="pesante"),),
            costo="gratuita", ricarica="nessuna",
        )],
    })
    crea_stagione(con_mosse)

    assert mossa_di("colpo-di-prova") is not None
    assert "colpo-di-prova" in mosse_note_correnti()
    assert "colpo-di-prova" in catalogo_mosse_correnti()
    assert etichetta_mossa("colpo-di-prova") == "Colpo di prova"
    # Nel Repertorio del protagonista la mossa è pagabile e richiedibile.
    rep = esper.try_component(pent, Repertorio)
    esper.add_component(pent, Repertorio(mosse=(*(rep.mosse if rep else ()), "colpo-di-prova")))
    assert mossa_pagabile(pent, "colpo-di-prova")


def test_freeze_round_trippa_nel_save(mondo_isolato, tmp_path) -> None:
    import esper

    from motore import applica_stato, carica_da_disco, salva_run, stagione_corrente
    from motore.design import EffettoAttivo, MossaAttiva, StagioneAttiva, crea_stagione
    from main import _stagione_a_attiva
    from tests.contenuti_sintetici import stagione_sintetica
    from tests.persist_helpers import costruisci_run

    costruisci_run()
    base = _stagione_a_attiva(stagione_sintetica(1))
    crea_stagione(StagioneAttiva(**{
        **{c: getattr(base, c) for c in base.__dataclass_fields__},
        "mosse": [MossaAttiva(
            chiave="urlo-di-prova", etichetta="Urlo",
            effetti=(EffettoAttivo(primitivo="danno", tipo_danno="fuoco"),),
        )],
    }))
    salva_run(tmp_path, model_id="m1", timestamp=1.0)
    esper.clear_database()
    applica_stato(carica_da_disco(tmp_path, "carl"))
    ripresa = stagione_corrente()
    assert ripresa is not None and ripresa.mosse[0].chiave == "urlo-di-prova"
    assert mossa_di("urlo-di-prova") is not None


def test_stagione_uno_risolve_le_mosse_seed() -> None:
    from main import risolvi_stagione

    risolta = risolvi_stagione("stagione-1")
    assert {"colpo-di-sipario", "alito-di-cimitero"} <= {m.slug for m in risolta.mosse}


def test_un_mob_puo_citare_una_mossa_asset() -> None:
    """Il lint di risoluzione vede anche le mosse-asset della libreria: un mob
    che cita `colpo-di-sipario` non è più «fuori catalogo»."""
    from main import mosse_note_authoring

    assert "colpo-di-sipario" in mosse_note_authoring()


# --- authoring.mossa (T3b) ------------------------------------------------------

def test_rotta_authoring_mossa_registrata() -> None:
    rotta = ROTTE["authoring.mossa"]
    assert rotta.gating is True and rotta.corsia.value == "forte"


def test_genera_mosse_gate_e_report(tmp_path) -> None:
    import genera_stagione as gs
    from tests.test_genera_stagione import _libreria_mondo, _stagione_risolta

    uff = _libreria_mondo(tmp_path)
    stagione = _stagione_risolta(uff)
    lotto = LottoMosseAutorate(mosse=[
        dict(slug="artiglio-di-prova", etichetta="Artiglio",
             effetti=[dict(primitivo="danno", tipo_danno="mischia")]),
        # azzardo incoerente: respinto dal validator alla conversione
        dict(slug="bara-truccata", etichetta="Bara", azzardo=True,
             effetti=[dict(primitivo="danno", tipo_danno="mischia")]),
    ]).model_dump()
    prov = FakeProvider([lotto])
    accettate, respinti = asyncio.run(gs.genera_mosse(
        MasterEngine.avvolgi(prov), stagione, quanti=2,
        ufficiali=uff, locali=uff / "mai-usata",
    ))
    assert [m.slug for m in accettate] == ["artiglio-di-prova"]
    assert any("azzardo" in r for r in respinti)
    assert "[vocabolario/primitivi]" in prov.prompt_ricevuti[0]
