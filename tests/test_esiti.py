"""Lo strato sovra-run, Fase A: l'`EsitoRun` e il suo ledger.

La direzione (2026-08-19): run single-player, strato sociale ASINCRONO sopra —
attraverso il confine viaggiano solo ESITI, mai stato di gioco. Qui si prova:
il contratto (un esito esiste solo per morte/vittoria), il protocollo del
seed-del-giorno (stabile per costruzione), il ledger (append-only, dedup,
tollerante), e il deposito VERO: la morte scrive l'esito nel ledger prima che
il permadeath invalidi tutto — e l'uscita volontaria non scrive niente.

I DTO delle fasi B/C/D (necrologio, classifica, fantasma) sono contratti
PREPARATI: qui si prova solo che derivano fedelmente dall'esito, non un
consumo che ancora non esiste.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import ValidationError

from contracts import (
    EsitoRun,
    FantasmaRun,
    PlayerChoseOption,
    Terminale,
    VoceClassifica,
    seed_del_giorno,
)
from main import costruisci_sessione
from motore.persistenza.esiti import leggi_esiti, path_esiti, scrivi_esito


async def _gioca_fino_alla_morte(sessione, max_turni: int = 200):
    """La morte CERTA per la via più corta (gemello di `test_permadeath_slot`,
    non importabile fra moduli di test): 1 HP e politica suicida."""
    from motore import protagonista

    _ent, _marker, scheda = protagonista()
    scheda.punti_vita = 1
    turni = 0
    while turni < max_turni:
        snap = sessione.avanza()
        if snap.run_conclusa:
            return snap.terminale
        turni += 1
        if not snap.opzioni:
            await sessione.prossima_narrazione()
            continue
        etichette = [o.etichetta for o in snap.opzioni]
        indice = next(
            (i for i, e in enumerate(etichette) if e.startswith(("Combatti", "Attacca"))),
            None,
        )
        if indice is None:
            indice = next(
                (i for i, e in enumerate(etichette) if e.startswith("Vai")), 0
            )
        sessione.coda.accoda(PlayerChoseOption(indice))
    return None


def _esito(**extra) -> EsitoRun:
    base = dict(
        uuid_run="abc12345",
        nome="Donut",
        seed=3,
        terminale=Terminale.SCONFITTA,
        causa="Scheletro del Saloon",
    )
    return EsitoRun(**(base | extra))


# --- Il contratto -------------------------------------------------------------

def test_l_uscita_volontaria_non_e_un_esito() -> None:
    """Salva-ed-esci non finisce nella storia: la run riprenderà."""
    with pytest.raises(ValidationError):
        _esito(terminale=Terminale.USCITA_VOLONTARIA)


def test_la_vittoria_e_un_esito() -> None:
    esito = _esito(terminale=Terminale.PIANO_COMPLETATO, causa="")
    assert esito.terminale is Terminale.PIANO_COMPLETATO


def test_la_chiave_e_deterministica_e_per_run() -> None:
    """Stesso esito = stessa chiave (il dedup del ledger si appoggia qui).
    E la chiave è per RUN, non per terminale: una run ha UNA chiusura — la
    «vittoria» di una run resuscitata non affianca la morte già a ledger."""
    assert _esito().chiave() == _esito().chiave()
    assert _esito().chiave() == _esito(
        terminale=Terminale.PIANO_COMPLETATO, causa=""
    ).chiave()
    assert _esito().chiave() != _esito(uuid_run="ffff0000").chiave()


def test_seed_del_giorno_stabile_e_sensibile() -> None:
    """Il protocollo del daily: chiunque lo deriva uguale, e giorno o stagione
    diversi danno dungeon diversi. Il valore atteso è CABLATO di proposito:
    cambiare la derivazione romperebbe le classifiche di tutti."""
    a = seed_del_giorno("2026-08-19", 1)
    assert a == seed_del_giorno("2026-08-19", 1)
    assert a != seed_del_giorno("2026-08-20", 1)
    assert a != seed_del_giorno("2026-08-19", 2)
    assert a == 2156223982


def test_i_derivati_proiettano_l_esito() -> None:
    """Fasi C/D preparate: voce di classifica e fantasma DERIVANO dall'esito
    (il client proietta, non inventa)."""
    esito = _esito(profondita=2, tick=40)
    voce = VoceClassifica.da_esito(esito)
    assert (voce.nome, voce.profondita, voce.tick) == ("Donut", 2, 40)
    fantasma = FantasmaRun.da_esito(esito)
    assert fantasma.causa == "Scheletro del Saloon"
    assert fantasma.seed == 3


# --- Il ledger ----------------------------------------------------------------

def test_il_ledger_deduplica_per_id(tmp_path) -> None:
    riga = _esito().model_dump(mode="json") | {"id": _esito().chiave()}
    assert scrivi_esito(tmp_path, riga) is True
    assert scrivi_esito(tmp_path, riga) is False
    esiti = leggi_esiti(tmp_path)
    assert len(esiti) == 1
    assert esiti[0]["ts"], "il timestamp lo appone l'host alla scrittura"


def test_una_riga_corrotta_non_ferma_la_storia(tmp_path) -> None:
    scrivi_esito(tmp_path, {"id": "e1", "nome": "Carl"})
    with path_esiti(tmp_path).open("a", encoding="utf-8") as f:
        f.write("{corrotta\n")
    assert scrivi_esito(tmp_path, {"id": "e2", "nome": "Donut"}) is True
    assert [e["id"] for e in leggi_esiti(tmp_path)] == ["e1", "e2"]


# --- Il deposito vero (l'innesto nel permadeath) ------------------------------

def test_la_morte_deposita_l_esito_nel_ledger(run_pulita, tmp_path) -> None:
    """Il funnel: muori → l'esito è nel ledger, ANCHE se l'host non chiude mai
    nulla (stesso principio del ritiro dello slot). E il teardown esplicito
    dopo non lo duplica: la chiave è deterministica."""
    sessione = costruisci_sessione(seed=3, directory=tmp_path, nome="Donut")
    asyncio.run(sessione.prossima_narrazione())
    sessione.salva()
    assert asyncio.run(_gioca_fino_alla_morte(sessione)) is Terminale.SCONFITTA

    esiti = leggi_esiti(tmp_path)
    assert len(esiti) == 1
    esito = esiti[0]
    assert esito["terminale"] == "sconfitta"
    assert esito["nome"] == "Donut"
    assert esito["uuid_run"] == sessione.uuid
    assert esito["seed"] == 3, "il master seed rende l'esito rigiocabile"
    assert esito["id"] == f"esito:{sessione.uuid}"

    sessione.chiudi_terminale()  # l'host diligente non produce un doppione
    assert len(leggi_esiti(tmp_path)) == 1


def test_l_esito_sopravvive_al_ritiro_dello_slot(run_pulita, tmp_path) -> None:
    """Il ledger è FUORI dalla coppia save: `invalida` ritira lo slot ma la
    storia resta — sopravvivere al permadeath è lo scopo dell'esito."""
    from main import elenca_crawler

    sessione = costruisci_sessione(seed=3, directory=tmp_path, nome="Donut")
    asyncio.run(sessione.prossima_narrazione())
    sessione.salva()
    assert asyncio.run(_gioca_fino_alla_morte(sessione)) is Terminale.SCONFITTA
    assert elenca_crawler(tmp_path) == [], "lo slot è ritirato"
    assert path_esiti(tmp_path).exists(), "la storia no"


def test_l_uscita_volontaria_non_deposita_niente(run_pulita, tmp_path) -> None:
    """La cintura: il deposito scatta sul TERMINALE, non su ogni chiusura."""
    sessione = costruisci_sessione(seed=1, directory=tmp_path, nome="Carl")
    asyncio.run(sessione.prossima_narrazione())
    sessione.esci()
    assert not path_esiti(tmp_path).exists()
    assert leggi_esiti(tmp_path) == []
