"""Host web — calibrazione (GM mode): la vista del catalogo §11, gli override via
API (imposta/azzera/salva) e l'anteprima coi numeri derivati FRESCHI. L'host non
importa il motore: passa dal backend del calibatore (`calibratore_web`)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from host_web import StatoHost, crea_app
from motore import calibrazione as cal


@pytest.fixture
def host(cal_pulita, tmp_path):
    stato = StatoHost(
        directory=tmp_path / "save",
        contenuti_ufficiali=tmp_path / "uff",
        contenuti_locali=tmp_path / "loc",
    )
    with TestClient(crea_app(stato)) as client:
        yield client
    stato.chiudi()


def test_vista_catalogo(host) -> None:
    r = host.get("/api/calibrazione")
    assert r.status_code == 200
    v = r.json()
    assert len(v["voci"]) == len(cal.elenco())
    assert {a["archetipo"] for a in v["archetipi"]} == {"slime", "scheletro", "goblin"}
    assert v["percorso_override"]
    contest = next(x for x in v["voci"] if x["chiave"] == "S_CONTEST")
    assert contest["sezione"] == "globale" and contest["spiegazione"]


def test_imposta_azzera_e_validazione(host) -> None:
    # Imposta valido → override in memoria, riflesso nella vista.
    r = host.put("/api/calibrazione/voci/ARCH.slime.taglia", json={"valore": "infima"})
    assert r.status_code == 200
    assert r.json() == {"chiave": "ARCH.slime.taglia", "valore": "infima", "override": True}
    assert cal.valore("ARCH.slime.taglia") == "infima"
    # Valore fuori dominio → 422, stato invariato.
    r = host.put("/api/calibrazione/voci/ARCH.slime.taglia", json={"valore": "spadone"})
    assert r.status_code == 422 and r.json()["codice"] == "valore_non_valido"
    assert cal.valore("ARCH.slime.taglia") == "infima"
    # Chiave sconosciuta → 404 (sia imposta che azzera).
    assert host.put("/api/calibrazione/voci/NON.ESISTE", json={"valore": 1}).status_code == 404
    assert host.delete("/api/calibrazione/voci/NON.ESISTE").status_code == 404
    # Azzera → torna al default.
    r = host.delete("/api/calibrazione/voci/ARCH.slime.taglia")
    assert r.status_code == 200
    assert r.json() == {"chiave": "ARCH.slime.taglia", "valore": "media", "override": False}


def test_imposta_numerico_coerced(host) -> None:
    # La UI manda stringhe: il coerce del catalogo le riporta al tipo giusto.
    r = host.put("/api/calibrazione/voci/S_CONTEST", json={"valore": "5"})
    assert r.status_code == 200 and r.json()["valore"] == 5
    r = host.put("/api/calibrazione/voci/G_GRAZE", json={"valore": "0.4"})
    assert r.status_code == 200 and r.json()["valore"] == 0.4


def test_salva_scrive_i_soli_divergenti(host, monkeypatch, tmp_path) -> None:
    percorso = tmp_path / "overrides.json"
    monkeypatch.setattr(cal, "PERCORSO_OVERRIDE", percorso)
    host.put("/api/calibrazione/voci/S_CONTEST", json={"valore": 5})
    host.put("/api/calibrazione/voci/G_GRAZE", json={"valore": 0.5})  # = default
    r = host.post("/api/calibrazione/salva")
    assert r.status_code == 200
    assert r.json() == {"percorso": str(percorso), "n": 1}
    assert json.loads(percorso.read_text(encoding="utf-8")) == {"S_CONTEST": 5}


def test_anteprima_fresca_e_validata(host, mondo_isolato) -> None:
    base = host.post(
        "/api/calibrazione/anteprima",
        json={"archetipo": "slime", "grado": "bronzo", "livello": 1},
    )
    assert base.status_code == 200
    assert set(base.json()) >= {"primarie", "max_hp", "eva_eff", "resistenze_mult"}
    # L'anteprima riflette l'override APPENA impostato (valori freschi, non cache-ati).
    host.put("/api/calibrazione/voci/ARCH.slime.taglia", json={"valore": "infima"})
    dopo = host.post(
        "/api/calibrazione/anteprima",
        json={"archetipo": "slime", "grado": "bronzo", "livello": 1},
    )
    assert dopo.json()["eva_eff"] > base.json()["eva_eff"]
    # Archetipo inesistente → 422 tipizzato.
    r = host.post(
        "/api/calibrazione/anteprima",
        json={"archetipo": "drago", "grado": "bronzo", "livello": 1},
    )
    assert r.status_code == 422 and r.json()["codice"] == "anteprima_non_valida"
