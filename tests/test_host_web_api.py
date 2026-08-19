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
    # Il copione offline deriva dalla STAGIONE congelata: il cast può cambiare
    # con il contenuto (era «Slime» nell'era demo) — l'oracolo è che il reveal
    # abbia una prosa vera, non un nome di mob cablato nel test.
    assert len(messaggio["prosa"]) > 40
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


# --- Scena sociale (parlamentare) e prosa fuori banda (collegamenti 2026-08-19) --
# Le due porte che la TUI usava e l'host web NO: `battuta_parlamento` (+
# `abbandona_parlamento`) e `prossima_prosa`. Questi test sono il lucchetto sul
# collegamento: la feature esiste nella UI web, non solo nel motore.

def test_battuta_senza_scena_409(host) -> None:
    client, _stato = host
    apertura = _crea(client)
    corpo = _narra(client, apertura["versione"])
    r = client.post(
        "/api/partita/scena/battuta",
        json={"testo": "C'è nessuno?", "versione": corpo["versione"]},
    )
    assert r.status_code == 409
    assert r.json()["codice"] == "scena_assente"


def _carisma_alto() -> None:
    """Il gate del parlamento reso deterministico (stesso trucco dei test del
    motore): carisma sopra ogni soglia, mutazione diretta del World attivo."""
    import esper
    from contracts import StatId
    from motore.scheda import protagonista
    from motore.statistiche import Primarie

    pent, _m, _s = protagonista()
    esper.component_for_entity(pent, Primarie).valori[StatId.CARISMA] = 40


def test_parlamentare_dal_browser_batte_e_tronca(host) -> None:
    """Il filo intero della scena via API: Parlamenta → scena aperta → battuta
    (post «scena» con lo scambio, scena ancora aperta) → vuoto = tronca."""
    client, _stato = host
    apertura = _crea(client)  # seed=1: il primo mob è parlamentabile
    corpo = _narra(client, apertura["versione"])
    _carisma_alto()
    indice = _indice_opzione(corpo["snapshot"], "Parlamenta")
    corpo = client.post(
        "/api/partita/opzioni",
        json={"indice": indice, "versione": corpo["versione"]},
    ).json()
    assert corpo["snapshot"]["scena_aperta"] is True, "il gate superato apre la scena"

    r = client.post(
        "/api/partita/scena/battuta",
        json={"testo": "Chi comanda qui?", "versione": corpo["versione"]},
    )
    assert r.status_code == 200
    corpo = r.json()
    scena = [p for p in corpo["post"] if p["genere"] == "scena"]
    assert len(scena) == 1
    assert scena[0]["righe"][0] == "«Chi comanda qui?»"
    assert len(scena[0]["righe"]) == 2 and scena[0]["righe"][1], (
        "la risposta del canale scena non è mai vuota (degrado deterministico)"
    )
    assert corpo["snapshot"]["scena_aperta"] is True, "una battuta non chiude la scena"

    r = client.post(
        "/api/partita/scena/battuta",
        json={"testo": "", "versione": corpo["versione"]},
    )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["snapshot"]["scena_aperta"] is False, "battuta vuota = tronca"
    scena = [p for p in corpo["post"] if p["genere"] == "scena"]
    assert scena and "tronca" in scena[0]["righe"][0]


def test_la_prosa_fuori_banda_arriva_al_forum(host, monkeypatch) -> None:
    """Il DRENAGGIO è dell'host, la generazione è del motore: qui si prova il
    trasporto. Offline il battito degrada e DECADE per disegno (la riga di
    cronaca è già uscita), quindi la porta si stubba con un trailer già
    generato: deve diventare un post «prosa» con il suo registro tipografico.
    Prima l'host web non chiamava mai `prossima_prosa` e trailer/premi/
    epitaffi non arrivavano al forum."""
    from contracts import ProsaFuoriBanda, TipoProsa

    client, stato = host
    apertura = _crea(client)
    corpo = _narra(client, apertura["versione"])
    battiti = [ProsaFuoriBanda(tipo=TipoProsa.APERTURA, testo="Luci. Sipario.")]

    async def _finto():
        return battiti.pop(0) if battiti else None

    monkeypatch.setattr(stato.sessione, "prossima_prosa", _finto)
    indice = _indice_opzione(corpo["snapshot"], "Combatti")
    corpo = client.post(
        "/api/partita/opzioni",
        json={"indice": indice, "versione": corpo["versione"]},
    ).json()
    prose = [p for p in corpo["post"] if p["genere"] == "prosa"]
    assert len(prose) == 1
    assert prose[0]["tipo_prosa"] == "apertura"
    assert prose[0]["righe"] == ["Luci. Sipario."]
    # E il thread lo conserva: il reload pagina non perde il battito.
    thread = client.get("/api/partita/thread").json()
    assert any(p["genere"] == "prosa" for p in thread["post"])


# --- Zaino/equip e lotto sovra-run (collegamenti 3-4, 2026-08-19) ---------------

def _metti_nello_zaino(fonte: str) -> None:
    """Il bottino senza combattere (trucco dei test motore): la fonte entra
    nello Zaino del protagonista via World attivo — l'endpoint poi la vede."""
    from motore.equip import assicura_zaino
    from motore.scheda import protagonista

    pent, _m, _s = protagonista()
    assicura_zaino(pent).fonti.append(fonte)


def test_zaino_indossa_e_togli_dal_browser(host) -> None:
    """Il filo dell'inventario via API: zaino vuoto → bottino → Indossa
    (fonte indossata, versione cresciuta) → Togli. Il motore arbitra, l'host
    trasporta."""
    client, _stato = host
    apertura = _crea(client)
    corpo = _narra(client, apertura["versione"])
    assert client.get("/api/partita/zaino").json() == {"fonti": []}

    _metti_nello_zaino("tibia-affilata")
    zaino = client.get("/api/partita/zaino").json()["fonti"]
    assert len(zaino) == 1 and zaino[0]["indossata"] is False
    assert zaino[0]["etichetta"], "l'etichetta diegetica non è mai vuota"

    r = client.post(
        "/api/partita/equipaggia",
        json={"fonte": "tibia-affilata", "versione": corpo["versione"]},
    )
    assert r.status_code == 200
    corpo = r.json()
    zaino = client.get("/api/partita/zaino").json()["fonti"]
    assert zaino[0]["indossata"] is True

    r = client.post(
        "/api/partita/togli",
        json={"fonte": "tibia-affilata", "versione": corpo["versione"]},
    )
    assert r.status_code == 200
    assert client.get("/api/partita/zaino").json()["fonti"][0]["indossata"] is False


def test_equip_rifiuta_fonte_non_posseduta(host) -> None:
    client, _stato = host
    apertura = _crea(client)
    corpo = _narra(client, apertura["versione"])
    r = client.post(
        "/api/partita/equipaggia",
        json={"fonte": "spada-inventata", "versione": corpo["versione"]},
    )
    assert r.status_code == 422
    assert r.json()["codice"] == "fonte_assente"


def _esito_nel_ledger(directory, nome: str = "Katia") -> None:
    from contracts import EsitoRun, Terminale
    from motore.persistenza.esiti import scrivi_esito

    esito = EsitoRun(
        uuid_run="deadbeef", nome=nome, seed=7, terminale=Terminale.SCONFITTA,
        causa="La Regina Scaduta", tick=33,
    )
    scrivi_esito(directory, esito.model_dump(mode="json") | {"id": esito.chiave()})


def test_la_bacheca_serve_i_necrologi(host, tmp_path) -> None:
    """GET /api/bacheca = la proiezione del ledger, senza sessione aperta:
    è storia, si legge anche a hub spento."""
    client, _stato = host
    assert client.get("/api/bacheca").json() == {"necrologi": []}
    _esito_nel_ledger(tmp_path)
    necrologi = client.get("/api/bacheca").json()["necrologi"]
    assert len(necrologi) == 1
    assert necrologi[0]["nome"] == "Katia"
    assert necrologi[0]["titolo"].startswith("†")
    assert "La Regina Scaduta" in necrologi[0]["corpo"]


def test_la_run_del_giorno_deriva_il_seed_dalla_data(host) -> None:
    """`daily: true` → il seed lo detta la data (lato HOST: il motore non
    guarda mai l'orologio). Il seed effettivo torna al client: è il numero
    che la classifica futura verificherà."""
    from datetime import date

    from contracts import seed_del_giorno

    client, _stato = host
    r = client.post(
        "/api/partita",
        json={"nuovo": {"nome": "Daily", "seed": 999, "daily": True}},
    )
    assert r.status_code == 201
    atteso = seed_del_giorno(date.today().isoformat(), 1)  # stagione-1 → numero 1
    assert r.json()["crawler"]["seed"] == atteso, (
        "il daily ignora il seed scelto a mano e usa quello del giorno"
    )


def test_il_dungeon_infestato_monta_i_fantasmi(host, tmp_path) -> None:
    """`infestata: true` → le sconfitte del ledger locale entrano come
    fantasmi-lore congelati nel World; senza flag, zero footprint (il
    comportamento storico non cambia di un bit)."""
    from motore.fantasmi import fantasmi_correnti

    client, _stato = host
    _esito_nel_ledger(tmp_path)
    r = client.post(
        "/api/partita",
        json={"nuovo": {"nome": "Cacciatore", "seed": 3, "infestata": True}},
    )
    assert r.status_code == 201
    montati = fantasmi_correnti()
    assert montati is not None and len(montati.lista) == 1
    assert montati.lista[0].nome == "Katia"

    client.post("/api/partita/esci", json={"versione": r.json()["versione"]})
    r = client.post(
        "/api/partita", json={"nuovo": {"nome": "Prudente", "seed": 3}}
    )
    assert r.status_code == 201
    assert fantasmi_correnti() is None, "senza flag: run storica identica"


# --- Playtest 2026-08-19: la vittoria non veniva mai narrata a menu pieno -------

def test_la_chiusura_dello_scontro_produce_subito_il_resoconto(host) -> None:
    """Il ramo resoconto di `esegui_turno_gm` esisteva (dai FATTI, fallback
    deterministico offline) ma l'host web non lo chiedeva mai se il menu di
    scena non era vuoto: vinci e la vittoria resta non narrata. Ora la
    transizione combattimento→narrazione chiede SUBITO il turno GM."""
    client, _stato = host
    apertura = _crea(client)
    corpo = _narra(client, apertura["versione"])
    indice = _indice_opzione(corpo["snapshot"], "Combatti")
    corpo = client.post(
        "/api/partita/opzioni", json={"indice": indice, "versione": corpo["versione"]}
    ).json()
    guardia = 0
    ultimo = corpo
    while corpo["fase"] == "combattimento" and not corpo["morto"] and guardia < 60:
        indice = _indice_opzione(corpo["snapshot"], "Attacca")
        ultimo = client.post(
            "/api/partita/opzioni", json={"indice": indice, "versione": corpo["versione"]}
        ).json()
        corpo = ultimo
        guardia += 1
    assert corpo["fase"] == "narrazione" and not corpo["morto"]
    assert corpo["snapshot"]["opzioni"], "il menu di scena è PIENO: era il caso rotto"
    gm = [p for p in ultimo["post"] if p["genere"] == "gm"]
    assert gm, "la chiusura dello scontro deve produrre il turno GM del resoconto"
    assert gm[-1]["messaggio"]["prosa"].strip(), (
        "il resoconto ha prosa anche offline (fallback deterministico dai fatti)"
    )


# --- Lo script di lancio «doppio click e giochi» (2026-08-20) -------------------

def test_la_spa_compilata_viene_servita_dall_host(tmp_path) -> None:
    """`monta_spa`: con la build in web/dist l'host serve la SPA alla radice
    (una origine sola, niente proxy) e le rotte /api/* — registrate prima —
    vincono sempre sul mount statico."""
    from host_web import StatoHost, crea_app
    from host_web.__main__ import monta_spa

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        "<title>DCC</title><div id=root></div>", encoding="utf-8"
    )
    stato = StatoHost(directory=tmp_path)
    app = crea_app(stato)
    assert monta_spa(app, dist) is True
    with TestClient(app) as client:
        assert "DCC" in client.get("/").text, "la radice serve index.html"
        r = client.get("/api/crawlers")
        assert r.status_code == 200 and "crawlers" in r.json(), (
            "le API vincono sul mount statico"
        )
    stato.chiudi()


def test_senza_build_l_host_resta_api_only(tmp_path) -> None:
    from host_web import StatoHost, crea_app
    from host_web.__main__ import monta_spa

    stato = StatoHost(directory=tmp_path)
    app = crea_app(stato)
    assert monta_spa(app, tmp_path / "dist-inesistente") is False
    stato.chiudi()
