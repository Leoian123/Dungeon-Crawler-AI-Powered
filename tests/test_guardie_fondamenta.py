"""Le guardie della "Mossa 1" (audit fondamenta 2026-08): ciò che prima corrompeva
in SILENZIO ora fallisce RUMOROSAMENTE — o viene ripristinato.

  - death-check con protagonista duplicato → RuntimeError (la permadeath, linea
    rossa G-11, non si spegne più zitta);
  - seconda sessione nello stesso processo → la prima è INVALIDATA e ogni sua
    porta solleva (prima leggeva la scheda dell'altra e ne salvava il file);
  - save il cui payload tradisce la busta → load rifiutato E contesto restituito
    al default (prima: TypeError grezzo con un run-World a metà come contesto);
  - radici dei percorsi: installazione (read-only) vs dati utente (scrivibili),
    consapevoli del congelamento PyInstaller.
"""

from __future__ import annotations

import asyncio
import json
import sys

import pytest

import esper

from contracts import BusEventi, MortePersonaggio
from guscio import NOME_DEFAULT, NOME_RUN
from main import carica_sessione, costruisci_sessione
from motore import SistemaDeathCheck, crea_protagonista
from motore.persistenza import carica_crawler


# --- Death-check: il mono-protagonista è un invariante RUMOROSO ------------------

def test_death_check_esplode_con_protagonista_duplicato(mondo_isolato) -> None:
    """Con N>1 protagonisti il check prima RESTITUIVA in silenzio: un PG a 0 HP
    non moriva mai e nessuno se ne accorgeva. Chi introdurrà il party deve
    passare di qui di proposito."""
    crea_protagonista(destrezza=10, id_dominio="a")
    crea_protagonista(destrezza=10, id_dominio="b")
    with pytest.raises(RuntimeError, match="protagonista singleton"):
        SistemaDeathCheck(BusEventi()).run(0)


def test_death_check_tollera_il_mondo_in_allestimento(mondo_isolato) -> None:
    """Zero protagonisti = harness/allestimento: nessuno da arbitrare, nessun errore."""
    SistemaDeathCheck(BusEventi()).run(0)  # non solleva


def test_death_check_funziona_ancora_con_un_protagonista(mondo_isolato) -> None:
    """La guardia non deve rompere il caso normale (regressione)."""
    bus = BusEventi()
    morti: list[MortePersonaggio] = []
    bus.registra(MortePersonaggio, morti.append)
    ent = crea_protagonista(destrezza=10)
    from motore import Scheda

    scheda = esper.component_for_entity(ent, Scheda)
    scheda.punti_vita = 0
    SistemaDeathCheck(bus).run(0)
    assert len(morti) == 1 and not scheda.vivo


# --- Una sola run per processo: la collisione è un errore, non una fusione -------

def test_seconda_sessione_invalida_la_prima_rumorosamente(run_pulita, tmp_path) -> None:
    """Riprodotto nell'audit: la sessione A, dopo la nascita di B, leggeva la
    scheda di B e ne SALVAVA il file. Ora ogni porta di A solleva."""
    a = costruisci_sessione(nome="Alfa", seed=1, directory=tmp_path)
    b = costruisci_sessione(nome="Beta", seed=2, directory=tmp_path)

    with pytest.raises(RuntimeError, match="invalidata"):
        a.avanza()
    with pytest.raises(RuntimeError, match="invalidata"):
        a.salva()
    with pytest.raises(RuntimeError, match="invalidata"):
        a.scheda()
    with pytest.raises(RuntimeError, match="invalidata"):
        a.riepiloga_azione("provo comunque")  # legge il World: guardata anche lei

    # La sessione NUOVA è pienamente operativa: il posto è suo.
    snap = asyncio.run(b.prossima_narrazione())
    assert snap.fase == "narrazione"
    assert b.scheda().nome == "Beta"


class _ProviderChePassaLaMano:
    """Wrapper che cede il loop prima di ogni `genera`: nel test, un'altra sessione
    può nascere ESATTAMENTE mentre il turno è sospeso (come su una rete vera)."""

    def __init__(self, interno) -> None:
        self._interno = interno

    async def genera(self, prompt, schema, *, sistema=""):
        await asyncio.sleep(0)
        return await self._interno.genera(prompt, schema, sistema=sistema)


def test_il_turno_in_volo_di_una_sessione_invalidata_non_scrive(run_pulita, tmp_path) -> None:
    """Il buco trovato in review: la guardia d'ingresso non copriva la coroutine
    GIÀ SOSPESA sugli await del provider — riprendeva e scriveva (mob, tempo,
    visitata) nel World della sessione nuova. La barriera `guardia_scrittura`
    scatta dopo l'ultimo await e prima di toccare il World."""
    a = costruisci_sessione(nome="Alfa", seed=1, directory=tmp_path)
    a.provider = _ProviderChePassaLaMano(a.provider)

    async def scenario():
        turno_di_a = asyncio.ensure_future(a.prossima_narrazione())
        await asyncio.sleep(0)  # il turno di A parte e si sospende sul provider
        b = costruisci_sessione(nome="Beta", seed=2, directory=tmp_path)
        with pytest.raises(RuntimeError, match="invalidata"):
            await turno_di_a  # il turno in volo cade ALLA BARRIERA, senza scrivere
        return b

    b = asyncio.run(scenario())
    # Il mondo di B è intatto: il SUO primo turno è davvero il primo (il reveal
    # della stanza 0 avviene ora, non è stato consumato dal turno fantasma di A).
    snap = asyncio.run(b.prossima_narrazione())
    assert snap.fase == "narrazione" and snap.prosa
    assert b.scheda().nome == "Beta"


def test_load_fallito_sul_payload_invalida_la_sessione_aperta(run_pulita, tmp_path) -> None:
    """Secondo buco di review: il rollback del load smontava il World della
    sessione aperta ma NON la invalidava — le sue porte morivano con errori
    criptici dei check singleton ('trovati 0') invece del messaggio di guardia."""
    donatore = costruisci_sessione(nome="Donatore", seed=1, directory=tmp_path)
    uuid = donatore.uuid
    donatore.esci()
    _sabota_componente(
        tmp_path / f"{uuid}.stato.json", "scheda", "punti_vita", "punti_ferita"
    )

    aperta = costruisci_sessione(nome="Aperta", seed=2, directory=tmp_path)
    assert carica_sessione(uuid=uuid, directory=tmp_path) is None
    # Il World di `aperta` è stato smontato dal tentativo: lo deve DIRE.
    with pytest.raises(RuntimeError, match="invalidata"):
        aperta.avanza()


def test_busta_corrotta_non_costa_il_world_alla_sessione_aperta(run_pulita, tmp_path) -> None:
    """Il caso simmetrico: se il save muore allo strato di BUSTA (file illeggibile),
    il World non viene mai toccato — la sessione aperta resta viva e giocabile."""
    aperta = costruisci_sessione(nome="Superstite", seed=1, directory=tmp_path)
    (tmp_path / "zzzz.stato.json").write_text("non-json{", encoding="utf-8")

    assert carica_sessione(uuid="zzzz", directory=tmp_path) is None
    snap = asyncio.run(aperta.prossima_narrazione())  # nessuna invalidazione
    assert snap.fase == "narrazione"
    assert aperta.scheda().nome == "Superstite"


def test_save_con_due_protagonisti_rifiutato_al_load(run_pulita, tmp_path) -> None:
    """Un save manomesso con N protagonisti passava i tre strati di validazione e
    faceva esplodere il death-check al primo tick: ora muore in `_verifica_coerenza`
    (H-12: valida-e-degrada, menu intatto, World mai toccato)."""
    sessione = costruisci_sessione(nome="Doppio", seed=1, directory=tmp_path)
    uuid = sessione.uuid
    sessione.esci()

    path = tmp_path / f"{uuid}.stato.json"
    righe = path.read_text(encoding="utf-8").split("\n")
    corpo = json.loads(righe[1])
    protagonista_serializzato = next(
        e for e in corpo["entita"]
        if any(c["tag"] == "protagonista" for c in e["componenti"])
    )
    corpo["entita"].append(json.loads(json.dumps(protagonista_serializzato)))
    righe[1] = json.dumps(corpo, ensure_ascii=False)
    path.write_text("\n".join(righe), encoding="utf-8")

    assert carica_crawler(tmp_path, uuid) is False
    assert esper.current_world == NOME_DEFAULT
    assert NOME_RUN not in esper.list_worlds()


def test_sessione_abbandonata_e_raccolta_non_blocca_la_successiva(run_pulita, tmp_path) -> None:
    """Il registro è un weakref: una sessione abbandonata e garbage-collected non
    tiene occupato il posto e la successiva nasce pulita."""
    import gc

    a = costruisci_sessione(nome="Abbandonata", seed=1, directory=tmp_path)
    del a
    gc.collect()
    b = costruisci_sessione(nome="Erede", seed=2, directory=tmp_path)
    assert asyncio.run(b.prossima_narrazione()).fase == "narrazione"


def test_chiudere_la_sessione_rilascia_il_posto(run_pulita, tmp_path) -> None:
    """esci() rilascia il registro: la sessione successiva NON nasce da una
    collisione e la precedente resta 'chiusa' (non 'invalidata')."""
    a = costruisci_sessione(nome="Alfa", seed=1, directory=tmp_path)
    a.esci()
    b = costruisci_sessione(nome="Beta", seed=2, directory=tmp_path)
    with pytest.raises(RuntimeError, match="chiusa"):
        a.avanza()  # chiusa regolarmente, mai invalidata
    assert asyncio.run(b.prossima_narrazione()).fase == "narrazione"


# --- Load con payload tradito: rifiuto E contesto ripristinato -------------------

def _sabota_componente(path, tag: str, campo: str, nuovo: str) -> None:
    """Rinomina un campo DENTRO i dati di un componente: la busta resta valida
    (`ComponenteSerializzato.dati` è un dict opaco), la ricostruzione esplode.
    Formato su disco: riga 1 = intestazione, riga 2 = corpo (disco.py)."""
    righe = path.read_text(encoding="utf-8").split("\n")
    corpo = json.loads(righe[1])
    for entita in corpo["entita"]:
        for comp in entita["componenti"]:
            if comp["tag"] == tag and campo in comp["dati"]:
                comp["dati"][nuovo] = comp["dati"].pop(campo)
                righe[1] = json.dumps(corpo, ensure_ascii=False)
                path.write_text("\n".join(righe), encoding="utf-8")
                return
    raise AssertionError(f"componente {tag!r} con campo {campo!r} non trovato nel save")


def test_load_con_payload_tradito_ripristina_il_contesto(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(nome="Rotto", seed=1, directory=tmp_path)
    uuid = sessione.uuid
    sessione.esci()  # scrive il save valido

    _sabota_componente(
        tmp_path / f"{uuid}.stato.json", "scheda", "punti_vita", "punti_ferita"
    )

    assert carica_crawler(tmp_path, uuid) is False
    # Il contesto è il default e il run-World parziale NON è sopravvissuto.
    assert esper.current_world == NOME_DEFAULT
    assert NOME_RUN not in esper.list_worlds()
    # E la porta di sessione degrada come da contratto (None, menu intatto).
    assert carica_sessione(uuid=uuid, directory=tmp_path) is None


# --- Radici dei percorsi: installazione vs dati utente, frozen-aware -------------

def test_radici_congelate_distinguono_installazione_da_dati_utente(
    monkeypatch, tmp_path
) -> None:
    """PyInstaller: contenuti dal bundle (read-only), dati utente ACCANTO
    all'eseguibile — mai dentro `_MEIPASS`, che in onefile è una cartella
    temporanea che sparisce all'uscita."""
    import main

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "app" / "gioco.exe"))

    assert main._radice_installazione() == tmp_path / "bundle"
    assert main._radice_dati_utente() == (tmp_path / "app").resolve()


def test_radici_normali_sono_la_radice_del_repo() -> None:
    import main

    radice = main._radice_installazione()
    assert (radice / "contenuti").is_dir()  # la libreria ufficiale è lì
    assert main._radice_dati_utente() == radice
