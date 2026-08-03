"""Host web — la libreria dei contenuti (GM mode): CRUD locale, ufficiali
read-only, affinità, risoluzione, apertura partita con stagione scelta."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from contracts import MobAsset, PianoAsset, Stagione
from host_web import StatoHost, crea_app


def _mob_json(slug: str, **kw) -> dict:
    corpo = {
        "slug": slug, "nome": slug.title(), "archetipo": "slime",
        "grado": "bronzo", "blocchi": ["veleno"],
        "prosa_stanza": f"La scena di {slug}.", "tags": ["prova"],
    }
    corpo.update(kw)
    return corpo


@pytest.fixture
def host(run_pulita, tmp_path):
    uff = tmp_path / "uff"
    (uff / "mob").mkdir(parents=True)
    (uff / "mob" / "canonico.json").write_text(
        json.dumps(_mob_json("canonico", tags=["ufficiale", "teatro"])),
        encoding="utf-8",
    )
    stato = StatoHost(
        directory=tmp_path / "save",
        contenuti_ufficiali=uff,
        contenuti_locali=tmp_path / "loc",
    )
    with TestClient(crea_app(stato)) as client:
        yield client, stato
    stato.chiudi()


def test_crud_locale_e_ufficiale_read_only(host) -> None:
    client, _stato = host
    # Elenco: l'ufficiale c'è.
    asset = client.get("/api/contenuti/mob").json()["asset"]
    assert [(a["slug"], a["origine"]) for a in asset] == [("canonico", "ufficiale")]
    # Crea locale.
    r = client.post("/api/contenuti/mob", json=_mob_json("nuovo"))
    assert r.status_code == 201
    # Slug ufficiale: 409.
    r = client.post("/api/contenuti/mob", json=_mob_json("canonico"))
    assert r.status_code == 409 and r.json()["codice"] == "slug_esistente"
    # PUT su ufficiale: 403.
    r = client.put("/api/contenuti/mob/canonico", json=_mob_json("canonico"))
    assert r.status_code == 403 and r.json()["codice"] == "asset_ufficiale"
    # PUT locale ok; DELETE locale ok; DELETE ufficiale 403.
    r = client.put("/api/contenuti/mob/nuovo", json=_mob_json("nuovo", nome="Rinominato"))
    assert r.status_code == 200 and r.json()["nome"] == "Rinominato"
    assert client.delete("/api/contenuti/mob/nuovo").status_code == 200
    assert client.delete("/api/contenuti/mob/canonico").status_code == 403
    assert client.get("/api/contenuti/mob/nuovo").status_code == 404
    # Corpo non conforme: 422 col lint.
    r = client.post("/api/contenuti/mob", json={"slug": "x"})
    assert r.status_code == 422 and r.json()["codice"] == "contenuto_non_valido"


def test_affini_via_api(host) -> None:
    client, _stato = host
    client.post("/api/contenuti/mob", json=_mob_json("affine", tags=["teatro"]))
    r = client.get("/api/contenuti/affini", params={"tipo": "mob", "tags": "teatro"})
    assert r.status_code == 200
    assert {v["slug"] for v in r.json()["affini"]} == {"canonico", "affine"}


def test_partita_con_stagione_locale(host) -> None:
    client, _stato = host
    # Authoring completo via API: mob → piano → stagione → risoluzione → run.
    client.post("/api/contenuti/mob", json=_mob_json("testa-unica"))
    r = client.post(
        "/api/contenuti/piani",
        json={
            "slug": "piano-prova", "titolo": "Prova", "tema": "una stanza sola",
            "budget": {"gradi": ["bronzo"], "blocchi": ["veleno"], "archetipi": ["slime"]},
            "cast": ["testa-unica"],
        },
    )
    assert r.status_code == 201, r.text
    r = client.post(
        "/api/contenuti/stagioni",
        json={
            "slug": "s-prova", "numero": 9, "titolo": "Prova", "mondo": "Marte",
            "piani": ["piano-prova"],
        },
    )
    assert r.status_code == 201, r.text
    risolta = client.get("/api/contenuti/stagioni/s-prova/risolto")
    assert risolta.status_code == 200
    assert risolta.json()["piani"][0]["cast"][0]["slug"] == "testa-unica"

    apertura = client.post(
        "/api/partita",
        json={"nuovo": {"nome": "Tester", "seed": 1, "stagione": "s-prova"}},
    )
    assert apertura.status_code == 201, apertura.text
    turno = client.post(
        "/api/partita/narrazione", json={"versione": apertura.json()["versione"]}
    )
    assert turno.status_code == 200
    assert "testa-unica" in turno.json()["post"][-1]["messaggio"]["prosa"]


def test_partita_con_stagione_non_risolvibile(host) -> None:
    client, _stato = host
    client.post(
        "/api/contenuti/stagioni",
        json={"slug": "s-rotta", "numero": 1, "titolo": "Rotta", "mondo": "X",
              "piani": ["piano-fantasma"]},
    )
    r = client.post(
        "/api/partita",
        json={"nuovo": {"nome": "Tester", "seed": 1, "stagione": "s-rotta"}},
    )
    assert r.status_code == 422
    assert r.json()["codice"] == "stagione_non_risolvibile"
    assert client.get("/api/partita").status_code == 404  # nessuna run creata


def test_stagione_default_assente_nella_libreria_di_test(host) -> None:
    client, _stato = host
    # La libreria di test NON contiene stagione-1: aprire senza stagione fallisce
    # in modo pulito (l'host non ricade mai sulla libreria del repo).
    r = client.post("/api/partita", json={"nuovo": {"nome": "X", "seed": 1}})
    assert r.status_code == 422
    assert r.json()["codice"] == "stagione_non_risolvibile"
