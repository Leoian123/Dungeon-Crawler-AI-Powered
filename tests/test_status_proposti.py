"""T4c — `authoring.status` in variante PROPOSTA (D-4): l'AI propone la spec
strutturata, l'umano promuove coi «3 tocchi». Per costruzione non esiste un
`--applica`: l'output è un file-brief in proposte/, mai la libreria.
"""

from __future__ import annotations

import asyncio
import json

from contracts import LottoStatusProposti, StatusProposto
from motore import MasterEngine, ROTTE
from provider import FakeProvider

import genera_stagione as gs
from tests.test_genera_stagione import _libreria_mondo, _stagione_risolta


def _proposta(nome: str, **extra) -> dict:
    base = dict(nome=nome, descrizione="Un carattere nuovo.", valenza="dannoso",
                trasmissibile=True, tick="ferisce")
    base.update(extra)
    return base


def test_rotta_authoring_status_registrata() -> None:
    rotta = ROTTE["authoring.status"]
    assert rotta.gating is True and rotta.corsia.value == "forte"


def test_lo_status_proposto_non_ha_numeri() -> None:
    campi = set(StatusProposto.model_fields)
    assert not campi & {"delta", "durata", "rango", "valore"}
    assert {"tick", "fascia_intensita", "fascia_durata"} <= campi


def test_gate_coerenza_e_collisioni() -> None:
    ok = StatusProposto(**_proposta("gelo"))
    assert gs.gate_status(ok, set()) == []
    collide = StatusProposto(**_proposta("veleno"))
    assert any("collide" in e for e in gs.gate_status(collide, set()))
    incoerente = StatusProposto(**_proposta("benedizione", valenza="benefico",
                                            tick="ferisce"))
    assert any("incoerente" in e for e in gs.gate_status(incoerente, set()))
    neutro = StatusProposto(**_proposta("eco", valenza="neutro", tick="cura"))
    assert any("neutro" in e for e in gs.gate_status(neutro, set()))


def test_genera_status_scrive_solo_proposte(tmp_path) -> None:
    uff = _libreria_mondo(tmp_path)
    stagione = _stagione_risolta(uff)
    lotto = LottoStatusProposti(status=[
        _proposta("gelo"),
        _proposta("veleno"),          # collisione: respinta e riportata
    ]).model_dump()
    prov = FakeProvider([lotto])
    proposte_dir = tmp_path / "proposte" / "status"
    percorsi, respinti = asyncio.run(gs.genera_status(
        MasterEngine.avvolgi(prov), stagione, quanti=2,
        directory_proposte=proposte_dir,
    ))
    assert [p.name for p in percorsi] == ["gelo.json"]
    assert any("collide" in r for r in respinti)
    dati = json.loads((proposte_dir / "gelo.json").read_text(encoding="utf-8"))
    assert dati["valenza"] == "dannoso" and dati["tick"] == "ferisce"
    # SOLO proposte: la libreria (uff) non è stata toccata.
    assert not (uff / "status").exists()
