"""Host web — DELETE /api/crawlers/{uuid}: pulizia completa dello slot (stato +
sidecar + backup), vietata a run aperta, uuid validato, corrotti eliminabili.
Non è un terminale di run (H-20 intatto; H §10.4: niente DRM contro il giocatore)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from host_web import StatoHost, crea_app


@pytest.fixture
def host(run_pulita, tmp_path):
    stato = StatoHost(directory=tmp_path)
    with TestClient(crea_app(stato)) as client:
        yield client, stato, tmp_path
    stato.chiudi()


def _crea_e_salva(client: TestClient, nome: str = "Da-Eliminare") -> str:
    apertura = client.post("/api/partita", json={"nuovo": {"nome": nome, "seed": 1}})
    assert apertura.status_code == 201
    uuid = apertura.json()["crawler"]["uuid"]
    versione = apertura.json()["versione"]
    assert client.post("/api/partita/salva", json={"versione": versione}).status_code == 200
    assert client.post("/api/partita/esci", json={"versione": versione}).status_code == 200
    return uuid


def test_elimina_slot_completo_inclusi_backup(host) -> None:
    client, _stato, cartella = host
    uuid = _crea_e_salva(client)
    # Due salvataggi → esistono anche i .bak (backup_coppia).
    assert (cartella / f"{uuid}.stato.json").exists()
    r = client.delete(f"/api/crawlers/{uuid}")
    assert r.status_code == 200 and r.json() == {"eliminato": uuid}
    residui = [p.name for p in cartella.glob(f"{uuid}*")]
    assert residui == [], f"file residui dopo l'eliminazione: {residui}"
    assert client.get("/api/crawlers").json()["crawlers"] == []
    # Idempotenza dal punto di vista API: il secondo delete è un 404 pulito.
    assert client.delete(f"/api/crawlers/{uuid}").status_code == 404


def test_elimina_vietato_a_run_aperta(host) -> None:
    client, _stato, _cartella = host
    uuid = _crea_e_salva(client, nome="Sospeso")
    apertura = client.post("/api/partita", json={"nuovo": {"nome": "Attiva", "seed": 2}})
    assert apertura.status_code == 201
    r = client.delete(f"/api/crawlers/{uuid}")
    assert r.status_code == 409 and r.json()["codice"] == "partita_esistente"


def test_elimina_uuid_malformato_422(host) -> None:
    client, _stato, _cartella = host
    r = client.delete("/api/crawlers/..%2Fevil")
    assert r.status_code in (404, 422)  # il path-param strano muore prima o al lint
    r = client.delete("/api/crawlers/UUID_MAIUSCOLO")
    assert r.status_code == 422 and r.json()["codice"] == "uuid_non_valido"


def test_elimina_slot_corrotto(host) -> None:
    client, _stato, cartella = host
    (cartella / "rotto.stato.json").write_text("{non-json", encoding="utf-8")
    [voce] = client.get("/api/crawlers").json()["crawlers"]
    assert voce["corrotta"] is True
    r = client.delete("/api/crawlers/rotto")
    assert r.status_code == 200
    assert client.get("/api/crawlers").json()["crawlers"] == []
