"""T2b — la vestizione AI dei premi (contratto premi, Sit.3+4).

Il dado è GIÀ girato: `_deposita_bottino` decide SE e COSA (seeded, T1c) e
fissa `_ultimo_drop`; la rotta `premi.oggetto` VESTE il drop dopo — il gate
anti-arbitraggio respinge chi cambia base, altera il grado o sposta lo slot,
e il fallback è il nome di catalogo (il deposito non dipende mai dall'AI).
Il ribattezzo delle mosse (`premi.skill`) è SOLO parole (D-3).
"""

from __future__ import annotations

import asyncio

from contracts import Grado, OggettoGenerato, PlayerChoseOption, TipoDocumento
from main import costruisci_sessione, etichetta_oggetto
from motore import (
    MasterEngine,
    ROTTE,
    gate_premio,
    guardaroba_attivo,
    protagonista,
)
from motore import calibrazione as cal
from motore.equip import fonti_zaino
from provider import FakeProvider


def _vinci_uno_scontro(sessione):
    snap = asyncio.run(sessione.prossima_narrazione())
    etichette = {o.etichetta: o.indice for o in snap.opzioni}
    sessione.coda.accoda(PlayerChoseOption(next(v for k, v in etichette.items() if k.startswith("Combatti"))))
    snap = sessione.avanza()
    for _ in range(60):
        if snap.fase != "combattimento":
            return snap
        sessione.coda.accoda(PlayerChoseOption(0))
        snap = sessione.avanza()
    raise AssertionError("lo scontro non si è chiuso in 60 turni")


def _sessione_con_drop(tmp_path, monkeypatch):
    monkeypatch.setattr(cal, "PROB_DROP", 1.0)
    sessione = costruisci_sessione(nome="Premi", seed=7, directory=tmp_path)
    _vinci_uno_scontro(sessione)
    assert sessione._ultimo_drop is not None, "la vittoria non ha fissato il drop"
    return sessione


def test_rotte_premi_registrate() -> None:
    for nome in ("premi.oggetto", "premi.skill"):
        assert nome in ROTTE
        assert ROTTE[nome].gating is True
        assert ROTTE[nome].corsia.value == "forte"


def test_vestizione_accettata_veste_senza_toccare_il_drop(run_pulita, tmp_path, monkeypatch) -> None:
    sessione = _sessione_con_drop(tmp_path, monkeypatch)
    fonte, grado = sessione._ultimo_drop
    pent, _m, _s = protagonista()
    zaino_prima = fonti_zaino(pent)

    fake = FakeProvider([OggettoGenerato(
        base=fonte, grado=Grado(grado), nome="Il Cimelio del Sesto",
        descrizione="Un pezzo che ha visto cose.", aspetto="odora di popcorn",
    ).model_dump()])
    sessione.provider = fake
    prosa = asyncio.run(sessione.veste_premio())

    assert prosa is not None and "Il Cimelio del Sesto" in prosa
    # Il drop NON cambia: stessa fonte in zaino, solo il nome è vestito.
    assert fonti_zaino(pent) == zaino_prima
    assert etichetta_oggetto(fonte) == "Il Cimelio del Sesto"
    guardaroba = guardaroba_attivo(pent)
    assert guardaroba is not None and fonte in guardaroba.vesti
    assert sessione._ultimo_drop is None  # consumato: mai due vestizioni


def test_anti_arbitraggio_rifiuta_e_degrada_al_catalogo(run_pulita, tmp_path, monkeypatch) -> None:
    sessione = _sessione_con_drop(tmp_path, monkeypatch)
    fonte, grado = sessione._ultimo_drop
    barare = OggettoGenerato(
        base=fonte, grado=Grado.CELESTIALE,      # alza il grado: respinto
        nome="Reliquia Divina", descrizione="Troppo bella per essere vera.",
    )
    assert gate_premio(barare, fonte, grado) is not None
    sessione.provider = FakeProvider([barare.model_dump()])
    assert asyncio.run(sessione.veste_premio()) is None
    pent, _m, _s = protagonista()
    assert guardaroba_attivo(pent) is None or fonte not in guardaroba_attivo(pent).vesti
    assert etichetta_oggetto(fonte) != "Reliquia Divina"   # resta il catalogo


def test_gate_premio_base_cambiata() -> None:
    candidato = OggettoGenerato(base="altro-oggetto", grado=Grado.BRONZO,
                                nome="X", descrizione="y")
    assert "base cambiata" in gate_premio(candidato, "cappotto-di-scena", "bronzo")


def test_degrado_trasporto_lascia_il_catalogo(run_pulita, tmp_path, monkeypatch) -> None:
    sessione = _sessione_con_drop(tmp_path, monkeypatch)
    fonte, _grado = sessione._ultimo_drop
    sessione.provider = FakeProvider([])       # trasporto muto (+ retry rotta)
    assert asyncio.run(sessione.veste_premio()) is None
    assert etichetta_oggetto(fonte)            # il nome di catalogo resta


def test_guardaroba_round_trippa_nel_save(run_pulita, tmp_path, monkeypatch) -> None:
    sessione = _sessione_con_drop(tmp_path, monkeypatch)
    fonte, grado = sessione._ultimo_drop
    sessione.provider = FakeProvider([OggettoGenerato(
        base=fonte, grado=Grado(grado), nome="Cimelio Persistente",
        descrizione="Non si dimentica.",
    ).model_dump()])
    assert asyncio.run(sessione.veste_premio()) is not None
    sessione.salva()
    uuid = sessione.uuid
    sessione.esci()

    from main import carica_sessione

    ripresa = carica_sessione(uuid=uuid, directory=tmp_path)
    assert ripresa is not None
    assert etichetta_oggetto(fonte) == "Cimelio Persistente"


def test_premio_oro_scrive_un_evento_in_memoria(run_pulita, tmp_path, monkeypatch) -> None:
    sessione = _sessione_con_drop(tmp_path, monkeypatch)
    fonte, _grado = sessione._ultimo_drop
    # Forza un drop d'oro fissato dal motore (il gate confronta contro QUESTO).
    sessione._ultimo_drop = (fonte, "oro")
    sessione.provider = FakeProvider([OggettoGenerato(
        base=fonte, grado=Grado.ORO, nome="Cimelio Dorato", descrizione="Brilla.",
    ).model_dump()])
    assert asyncio.run(sessione.veste_premio()) is not None
    doc = sessione.memoria_lunga.recupera(fonte, tipi=(TipoDocumento.EVENTO,))
    assert doc and doc[0].id == f"premio-{fonte}"
