"""Il MECCANISMO di migrazione dei save, esercitato davvero.

Il meccanismo esiste da H-13 ma non è mai scattato: `SCHEMA_VERSION` è rimasta 1 per
tutta la storia del progetto e `_MIGRAZIONI` è vuota. Un meccanismo mai eseguito è un
meccanismo che non si sa se funziona — ed è il pavimento su cui poggiano i save di
chi gioca.

La tentazione era alzare la versione "per esercizio". Sarebbe stato l'errore opposto:
un bump è l'IDENTITÀ di un formato, e alzarlo senza una trasformazione reale timbra i
save esistenti a v2 senza cambiarne un byte — bruciando lo slot v1→v2 per la
migrazione VERA che un giorno servirà. Qui invece la catena si prova per INIEZIONE
(`migra` accetta `migrazioni=` e `versione_corrente=` proprio per questo): il
meccanismo è dimostrato, l'identità di versione resta spendibile.

Il complemento sta in `test_persistenza_*`: che il formato CORRENTE round-trippi.
"""

from __future__ import annotations

import json

import pytest

from motore.persistenza.formato import (
    SCHEMA_VERSION,
    VersioneIncompatibile,
    migra,
)


def _intestazione(versione: int = 1, profondita: int = 1) -> dict:
    return {
        "schema_version": versione,
        "uuid": "u",
        "etichetta": "Carl",
        "profondita": profondita,
        "timestamp": 0.0,
        "model_id": "m",
    }


def _corpo() -> dict:
    return {"entita": [{"componenti": [
        {"tag": "scheda", "dati": {"vivo": True, "punti_vita": 30}},
    ]}], "esplorazione": None, "rng_state": None, "archivio_ref": None}


# --- La catena SCATTA, in ordine, una versione alla volta ------------------------

def test_la_catena_applica_i_passi_in_ordine() -> None:
    """Due migrazioni concatenate: v1→v2→v3. Ogni passo vede l'output del
    precedente, e la versione avanza di uno alla volta (mai un salto)."""
    tracciato: list[int] = []

    def uno_a_due(intest: dict, corpo: dict) -> tuple[dict, dict]:
        tracciato.append(intest["schema_version"])
        corpo["entita"][0]["componenti"][0]["dati"]["aggiunto_in_v2"] = True
        return intest, corpo

    def due_a_tre(intest: dict, corpo: dict) -> tuple[dict, dict]:
        tracciato.append(intest["schema_version"])
        dati = corpo["entita"][0]["componenti"][0]["dati"]
        # v3 vede ciò che v2 ha scritto: i passi sono cumulativi, non paralleli.
        assert dati["aggiunto_in_v2"] is True
        dati["visto_da_v3"] = True
        return intest, corpo

    intest, corpo = migra(
        _intestazione(1), _corpo(),
        migrazioni={1: uno_a_due, 2: due_a_tre}, versione_corrente=3,
    )

    assert tracciato == [1, 2], "i passi devono scattare in ordine, uno alla volta"
    assert intest["schema_version"] == 3
    dati = corpo["entita"][0]["componenti"][0]["dati"]
    assert dati["aggiunto_in_v2"] and dati["visto_da_v3"]


def test_una_migrazione_puo_riparare_un_componente_ritirato() -> None:
    """La forma che servirà davvero: un save vecchio porta campi che il componente
    non ha più (è già successo — `Scheda` aveva `destrezza` e `punti_vita_max`,
    ritirati senza bump). Una migrazione li scarta e il save torna caricabile."""
    corpo = {"entita": [{"componenti": [
        {"tag": "scheda", "dati": {
            "vivo": True, "punti_vita": 30,
            "destrezza": 10, "punti_vita_max": 30,  # campi ritirati
        }},
    ]}], "esplorazione": None, "rng_state": None, "archivio_ref": None}

    def scarta_campi_ritirati(intest: dict, corpo: dict) -> tuple[dict, dict]:
        vivi = {"scheda": {"vivo", "punti_vita"}}
        for entita in corpo["entita"]:
            for comp in entita["componenti"]:
                ammessi = vivi.get(comp["tag"])
                if ammessi is not None:
                    comp["dati"] = {k: v for k, v in comp["dati"].items() if k in ammessi}
        return intest, corpo

    _i, corpo = migra(
        _intestazione(1), corpo,
        migrazioni={1: scarta_campi_ritirati}, versione_corrente=2,
    )
    assert corpo["entita"][0]["componenti"][0]["dati"] == {"vivo": True, "punti_vita": 30}


# --- I rifiuti: cosa la catena NON lascia passare --------------------------------

def test_un_save_dal_futuro_viene_rifiutato() -> None:
    with pytest.raises(VersioneIncompatibile, match="futura"):
        migra(_intestazione(SCHEMA_VERSION + 1), _corpo())


def test_un_buco_nella_catena_e_un_errore_esplicito() -> None:
    """Se un giorno si bumpa DIMENTICANDO la migrazione, il load lo dice invece di
    caricare dati incoerenti. È la rete che rende sicuro alzare la versione."""
    with pytest.raises(VersioneIncompatibile, match="nessuna migrazione"):
        migra(_intestazione(1), _corpo(), migrazioni={}, versione_corrente=2)


def test_una_versione_non_intera_viene_rifiutata() -> None:
    intest = _intestazione()
    intest["schema_version"] = "uno"
    with pytest.raises(VersioneIncompatibile, match="mancante o non intero"):
        migra(intest, _corpo())


def test_un_save_alla_versione_corrente_non_viene_toccato() -> None:
    corpo = _corpo()
    prima = json.dumps(corpo, sort_keys=True)
    _i, dopo = migra(_intestazione(SCHEMA_VERSION), corpo)
    assert json.dumps(dopo, sort_keys=True) == prima


# --- La disciplina: versione e catena non possono divergere ----------------------

def test_la_catena_copre_ogni_versione_fino_alla_corrente() -> None:
    """L'invariante che rende il bump un'operazione sicura: per ogni versione
    passata deve esistere il passo che la porta avanti. Oggi `SCHEMA_VERSION` è 1
    e la catena è vuota — coerente. Il giorno del primo bump questo test diventa
    rosso finché non si scrive la migrazione."""
    from motore.persistenza.formato import _MIGRAZIONI

    mancanti = [v for v in range(1, SCHEMA_VERSION) if v not in _MIGRAZIONI]
    assert not mancanti, f"versioni senza migrazione: {mancanti}"


def test_nessuna_migrazione_inerte_nella_catena() -> None:
    """L'errore che questo file documenta: una voce in catena senza un bump non
    scatterebbe mai (codice morto che sembra protezione), e un bump senza
    trasformazione reale brucia lo slot. Le due cose si muovono INSIEME."""
    from motore.persistenza.formato import _MIGRAZIONI

    inutili = [v for v in _MIGRAZIONI if v >= SCHEMA_VERSION]
    assert not inutili, (
        f"migrazioni che non scatteranno mai (versione ≥ corrente): {inutili}"
    )
