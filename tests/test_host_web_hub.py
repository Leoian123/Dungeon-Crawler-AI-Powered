"""Host web — l'hub dei crawler: elenco, apertura (nuovo/carica), uscita,
chiusura del terminale. Slot = crawler (H §1); l'elenco è lo scan delle
intestazioni (H §5). Tutto offline (FakeProvider), disciplina esper ESP §0.1.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from host_web import StatoHost, crea_app
from host_web.sse import flusso_eventi
from motore import protagonista, tick


@pytest.fixture
def host(run_pulita, tmp_path):
    stato = StatoHost(directory=tmp_path)
    with TestClient(crea_app(stato)) as client:
        yield client, stato
    stato.chiudi()


def _apri(client: TestClient, corpo: dict) -> dict:
    r = client.post("/api/partita", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def test_ciclo_hub_completo(host) -> None:
    client, _stato = host
    # Hub vuoto (B7.3: la risposta porta anche lo stato terminale della run attiva).
    vuoto = client.get("/api/crawlers").json()
    assert vuoto["crawlers"] == [] and vuoto["attiva"] is None
    assert vuoto["attiva_morta"] is False and vuoto["attiva_vittoria"] is False

    # Nuovo crawler → un turno GM → salva-ed-esci.
    apertura = _apri(client, {"nuovo": {"nome": "Donut", "seed": 1}})
    assert apertura["crawler"]["nome"] == "Donut"
    uuid = apertura["crawler"]["uuid"]
    turno = client.post(
        "/api/partita/narrazione", json={"versione": apertura["versione"]}
    ).json()
    prosa = turno["post"][-1]["messaggio"]["prosa"]
    uscita = client.post("/api/partita/esci", json={"versione": turno["versione"]})
    assert uscita.status_code == 200

    # Torna all'hub: la partita non c'è più, lo slot sì (con nome vero).
    assert client.get("/api/partita").status_code == 404
    elenco = client.get("/api/crawlers").json()
    assert elenco["attiva"] is None
    [voce] = elenco["crawlers"]
    assert voce["uuid"] == uuid
    assert voce["etichetta"] == "Donut"
    assert voce["timestamp"] > 0

    # Carica: il thread riparte dai turni congelati e si continua a giocare.
    ripresa = _apri(client, {"carica": {"uuid": uuid}})
    # `seed` è il campo TIPATO del CrawlerAttivo (bonifica 2026-08-20): alla
    # RIPRESA è None — il seed effettivo si dichiara solo alle run nuove.
    assert ripresa["crawler"] == {"uuid": uuid, "nome": "Donut", "seed": None}
    thread = client.get("/api/partita/thread").json()
    assert [p["genere"] for p in thread["post"]][:1] == ["gm"]
    assert thread["post"][0]["messaggio"]["prosa"] == prosa
    rilettura = client.post(
        "/api/partita/narrazione", json={"versione": ripresa["versione"]}
    )
    assert rilettura.status_code == 200  # la stanza è RILETTA (cache), si prosegue


def test_apertura_richiede_esattamente_un_ramo(host) -> None:
    client, _stato = host
    # Né nuovo né carica, o entrambi → 422 di validazione Pydantic/FastAPI.
    assert client.post("/api/partita", json={}).status_code == 422
    assert (
        client.post(
            "/api/partita",
            json={"nuovo": {"nome": "A"}, "carica": {"uuid": "x"}},
        ).status_code
        == 422
    )


def test_carica_inesistente_404(host) -> None:
    client, _stato = host
    r = client.post("/api/partita", json={"carica": {"uuid": "fantasma"}})
    assert r.status_code == 404
    assert r.json()["codice"] == "salvataggio_illeggibile"


def test_chiudi_su_run_in_corso_409(host) -> None:
    client, _stato = host
    _apri(client, {"nuovo": {"nome": "Vivo", "seed": 1}})
    r = client.post("/api/partita/chiudi")
    assert r.status_code == 409
    assert r.json()["codice"] == "run_non_terminata"


def test_morte_poi_chiudi_invalida_lo_slot(host) -> None:
    client, stato = host
    apertura = _apri(client, {"nuovo": {"nome": "Sfortunato", "seed": 1}})
    client.post("/api/partita/salva", json={"versione": apertura["versione"]})
    assert len(client.get("/api/crawlers").json()["crawlers"]) == 1
    # Morte harness: il death-check (seeded) emette MortePersonaggio sul bus.
    _pent, _marker, scheda = protagonista()
    scheda.punti_vita = 0
    tick()
    assert stato.morto is True
    assert client.post("/api/partita/esci", json={"versione": 99}).status_code == 410
    r = client.post("/api/partita/chiudi")
    assert r.status_code == 200
    # Permadeath: lo slot è invalidato, si torna all'hub.
    assert client.get("/api/partita").status_code == 404
    assert client.get("/api/crawlers").json()["crawlers"] == []


def test_autosave_alla_creazione_lo_slot_esiste_prima_del_primo_salva(host) -> None:
    """B5 (playtest profondo 2026-08-28): il primo Ade è SPARITO — partita
    creata, mai salvata, processo caduto ⇒ nessuno slot. Ora lo slot esiste
    su disco appena il 201 risponde, senza alcun POST /salva."""
    client, _stato = host
    apertura = _apri(client, {"nuovo": {"nome": "Ade", "seed": 8}})
    elenco = client.get("/api/crawlers").json()
    [voce] = elenco["crawlers"]
    assert voce["uuid"] == apertura["crawler"]["uuid"]
    assert voce["etichetta"] == "Ade", (
        "kill del processo post-creazione: l'hub DEVE elencare lo slot"
    )


def test_hub_post_mortem_dichiara_la_run_terminata(host) -> None:
    """B7.3: con la run attiva morta l'hub non dice più «Run in corso» —
    il dato `attiva_morta` arriva al client."""
    client, stato = host
    _apri(client, {"nuovo": {"nome": "Caduto", "seed": 1}})
    _pent, _marker, scheda = protagonista()
    scheda.punti_vita = 0
    tick()
    assert stato.morto is True
    elenco = client.get("/api/crawlers").json()
    assert elenco["attiva"]["nome"] == "Caduto"
    assert elenco["attiva_morta"] is True
    assert elenco["attiva_vittoria"] is False


def test_scheda_party(host) -> None:
    client, _stato = host
    _apri(client, {"nuovo": {"nome": "Princess", "seed": 2}})
    corpo = client.get("/api/partita/scheda").json()
    [scheda] = corpo["party"]  # il party è il seam: oggi un solo slot pieno
    assert scheda["nome"] == "Princess"
    assert 0 < scheda["hp"] <= scheda["hp_max"]
    assert "destrezza" in scheda["primarie"]
    assert "saggezza" in scheda["primarie_occulte"]
    assert "fortuna" not in scheda["primarie"]
    assert scheda["derivate"]["attacco"] > 0


def test_sse_riceve_run_chiusa_alla_chiusura(run_pulita, tmp_path) -> None:
    stato = StatoHost(directory=tmp_path)

    async def scenario() -> None:
        import httpx

        trasporto = httpx.ASGITransport(app=crea_app(stato))
        async with httpx.AsyncClient(transport=trasporto, base_url="http://test") as client:
            apertura = await client.post(
                "/api/partita", json={"nuovo": {"nome": "Carl", "seed": 1}}
            )
            assert apertura.status_code == 201
            flusso = flusso_eventi(stato)
            assert (await anext(flusso)).startswith(": collegato")
            uscita = await client.post(
                "/api/partita/esci", json={"versione": apertura.json()["versione"]}
            )
            assert uscita.status_code == 200
            blocco = await anext(flusso)
            assert blocco.startswith("event: run_chiusa")
            # Il generatore termina da solo dopo la sentinella.
            try:
                await anext(flusso)
                raise AssertionError("il flusso doveva terminare")
            except StopAsyncIteration:
                pass
            assert not stato._abbonati

    try:
        asyncio.run(asyncio.wait_for(scenario(), timeout=30))
    finally:
        stato.chiudi()
