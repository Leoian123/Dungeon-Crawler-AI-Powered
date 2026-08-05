"""Host web (FastAPI) — l'API di gioco sopra le porte di `SessioneGioco`.

Tutto offline: `provider=None` ⇒ FakeProvider (mai una chiamata di rete, mai la
chiave). Disciplina esper: fixture `run_pulita` (ESP §0.1) — la sessione switcha
al run-World, il teardown lo elimina. Il bus è process-global: ogni test chiude
lo `StatoHost` (deregistrazione handler) nel teardown della fixture.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from host_web import StatoHost, crea_app


@pytest.fixture
def host(run_pulita, tmp_path):
    stato = StatoHost(directory=tmp_path)
    with TestClient(crea_app(stato)) as client:
        yield client, stato
    stato.chiudi()


def _crea(client: TestClient, seed: int = 1, nome: str = "Carl") -> dict:
    risposta = client.post(
        "/api/partita", json={"nuovo": {"nome": nome, "seed": seed}}
    )
    assert risposta.status_code == 201
    return risposta.json()


def _narra(client: TestClient, versione: int) -> dict:
    risposta = client.post("/api/partita/narrazione", json={"versione": versione})
    assert risposta.status_code == 200
    return risposta.json()


def _indice_opzione(snapshot: dict, etichetta: str) -> int:
    for opzione in snapshot["opzioni"]:
        if opzione["etichetta"].split(" —")[0] == etichetta:
            return opzione["indice"]
    raise AssertionError(f"opzione {etichetta!r} assente: {snapshot['opzioni']}")


# --- Ciclo di vita -----------------------------------------------------------

def test_senza_partita_404(host) -> None:
    client, _stato = host
    assert client.get("/api/partita").status_code == 404
    assert client.get("/api/partita/thread").status_code == 404
    r = client.post("/api/partita/narrazione", json={"versione": 0})
    assert r.status_code == 404
    assert r.json()["codice"] == "partita_assente"


def test_creazione_e_partita_unica(host) -> None:
    client, _stato = host
    corpo = _crea(client)
    assert corpo["versione"] == 1  # l'apertura riallinea la scena (avanza sync)
    assert corpo["morto"] is False
    assert corpo["crawler"]["nome"] == "Carl"
    assert corpo["snapshot"]["opzioni"] == []  # stanza mai narrata: menu vuoto
    doppia = client.post("/api/partita", json={"nuovo": {"nome": "X", "seed": 2}})
    assert doppia.status_code == 409
    assert doppia.json()["codice"] == "partita_esistente"


def test_live_negato_senza_chiave_o_con_fake_forzato(host, monkeypatch) -> None:
    client, stato = host
    corpo = {"gm": "live", "nuovo": {"nome": "Live", "seed": 1}}
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post("/api/partita", json=corpo)
    assert r.status_code == 503
    assert r.json()["codice"] == "live_non_disponibile"
    stato.live_vietato = True  # come il lancio con --fake
    monkeypatch.setenv("ANTHROPIC_API_KEY", "presente-ma-vietata")
    r = client.post("/api/partita", json=corpo)
    assert r.status_code == 503  # nessun degrado muto: il rifiuto è esplicito


# --- Il turno ----------------------------------------------------------------

def test_prima_narrazione_produce_il_post_del_forum(host) -> None:
    client, _stato = host
    apertura = _crea(client)
    corpo = _narra(client, apertura["versione"])
    assert corpo["versione"] == apertura["versione"] + 1
    [post] = corpo["post"]
    assert post["genere"] == "gm"
    messaggio = post["messaggio"]
    assert "Slime" in messaggio["prosa"]  # il copione del FakeProvider
    assert messaggio["dove"] and messaggio["come"]  # contestualizzazione obbligata
    assert isinstance(messaggio["tempo"]["tick_correnti"], int)
    etichette = [o["etichetta"].split(" —")[0] for o in corpo["snapshot"]["opzioni"]]
    assert "Combatti" in etichette
    # Il thread ricostruisce il forum al reload pagina.
    thread = client.get("/api/partita/thread").json()
    assert [p["genere"] for p in thread["post"]] == ["gm"]


def test_versione_stantia_409(host) -> None:
    client, _stato = host
    apertura = _crea(client)
    corpo = _narra(client, apertura["versione"])
    stantia = client.post(
        "/api/partita/narrazione", json={"versione": apertura["versione"]}
    )
    assert stantia.status_code == 409
    dettaglio = stantia.json()
    assert dettaglio["codice"] == "turno_stantio"
    assert dettaglio["versione_corrente"] == corpo["versione"]


def test_opzione_fuori_menu_422(host) -> None:
    client, _stato = host
    apertura = _crea(client)
    corpo = _narra(client, apertura["versione"])
    r = client.post(
        "/api/partita/opzioni", json={"indice": 99, "versione": corpo["versione"]}
    )
    assert r.status_code == 422
    assert r.json()["codice"] == "opzione_invalida"


def test_azione_libera_doppio_giro(host) -> None:
    client, _stato = host
    apertura = _crea(client)
    corpo = _narra(client, apertura["versione"])
    # 1) anteprima: deterministica, zero LLM, la versione NON cambia.
    anteprima = client.post(
        "/api/partita/azione/anteprima", json={"testo": "frugo tra i rifiuti"}
    )
    assert anteprima.status_code == 200
    riepilogo = anteprima.json()["riepilogo"]
    assert riepilogo["testo_proposto"] == "frugo tra i rifiuti"
    assert isinstance(riepilogo["stima"]["tick"], int)
    assert riepilogo["stima"]["forbice"]
    assert anteprima.json()["versione"] == corpo["versione"]
    # 2) immissione (testo eventualmente editato): un nuovo post GM.
    azione = client.post(
        "/api/partita/azione",
        json={"testo": "frugo tra i rifiuti con cautela", "versione": corpo["versione"]},
    )
    assert azione.status_code == 200
    assert azione.json()["versione"] == corpo["versione"] + 1
    assert any(p["genere"] == "gm" for p in azione.json()["post"])


def test_combattimento_end_to_end(host) -> None:
    client, _stato = host
    apertura = _crea(client)
    corpo = _narra(client, apertura["versione"])
    indice = _indice_opzione(corpo["snapshot"], "Combatti")
    corpo = client.post(
        "/api/partita/opzioni", json={"indice": indice, "versione": corpo["versione"]}
    ).json()
    assert corpo["fase"] == "combattimento"
    # Menu dinamico dal Repertorio: mosse + Fuggi SEMPRE ULTIMA.
    etichette = [o["etichetta"].split(" —")[0] for o in corpo["snapshot"]["opzioni"]]
    assert etichette == ["Attacca", "Colpo pesante", "Dardo arcano", "Fuggi"]
    assert etichette[-1] == "Fuggi"
    guardia = 0
    while corpo["fase"] == "combattimento" and not corpo["morto"] and guardia < 100:
        indice = _indice_opzione(corpo["snapshot"], "Attacca")
        risposta = client.post(
            "/api/partita/opzioni", json={"indice": indice, "versione": corpo["versione"]}
        )
        assert risposta.status_code == 200
        corpo = risposta.json()
        guardia += 1
    assert corpo["fase"] == "narrazione" or corpo["morto"]
    # La chiusura dello scontro è passata dal bus alla cronaca → post "evento".
    thread = client.get("/api/partita/thread").json()
    assert any(p["genere"] == "evento" for p in thread["post"])


def test_permadeath_chiude_le_post_410(host) -> None:
    client, stato = host
    apertura = _crea(client)
    corpo = _narra(client, apertura["versione"])
    versione = corpo["versione"]
    stato.morto = True  # il flag che l'handler di MortePersonaggio imposta
    for percorso, body in (
        ("/api/partita/narrazione", {"versione": versione}),
        ("/api/partita/opzioni", {"indice": 0, "versione": versione}),
        ("/api/partita/azione/anteprima", {"testo": "mi rialzo"}),
        ("/api/partita/azione", {"testo": "mi rialzo", "versione": versione}),
        ("/api/partita/salva", {"versione": versione}),
        ("/api/partita/esci", {"versione": versione}),
    ):
        r = client.post(percorso, json=body)
        assert r.status_code == 410, percorso
        assert r.json()["codice"] == "run_terminata"
    # In sola lettura il thread resta consultabile.
    assert client.get("/api/partita/thread").status_code == 200


def test_salva(host) -> None:
    client, _stato = host
    apertura = _crea(client)
    corpo = _narra(client, apertura["versione"])
    r = client.post("/api/partita/salva", json={"versione": corpo["versione"]})
    assert r.status_code == 200
    assert "salvata" in r.json()["messaggio"].lower()
