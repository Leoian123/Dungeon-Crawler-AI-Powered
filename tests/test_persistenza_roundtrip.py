"""Round-trip fedele dello stato (H-L1) + artefatti separati (H-8, H-9, H-21).

salva → ricarica → lo stato (entità, FaseCorrente, status col rango copiato, profondità,
seed) è identico. Headless: si salva nel mondo isolato, si azzera, si riapplica.
"""

from __future__ import annotations

import gzip
import json

import esper

from contracts import StatId
from motore import (
    Fase,
    Veleno,
    carica_archivio,
    carica_da_disco,
    livello_corrente,
    leggi_fase,
    master_seed,
    protagonista,
    salva_run,
    stat_eff,
)
from motore.persistenza.disco import leggi_intestazione, path_archivio, path_stato
from tests.persist_helpers import costruisci_run


def test_HL1_roundtrip_fedele(mondo_isolato: str, tmp_path) -> None:
    pent = costruisci_run(
        fase=Fase.COMBATTIMENTO,
        profondita=4,
        master_seed=987654,
        destrezza=13,
        hp=21,
        id_dominio="carl",
        veleno=(5, 7),  # status col rango copiato
    )

    salva_run(tmp_path, model_id="m1", timestamp=42.0)

    # Azzera il World e ricarica dallo stato su disco.
    esper.clear_database()
    assert list(esper.get_entities()) == []
    stato = carica_da_disco(tmp_path, "carl")
    from motore import applica_stato

    applica_stato(stato)

    # Stato meccanico identico.
    assert leggi_fase() == Fase.COMBATTIMENTO
    assert livello_corrente() == 4
    assert master_seed() == 987654
    pe, marker, scheda = protagonista()
    assert marker.id_dominio == "carl"
    # La destrezza (nel vettore Primarie) sopravvive al round-trip via il fold.
    assert stat_eff(pe, StatId.DESTREZZA) == 13
    assert scheda.punti_vita == 21
    # Lo status sopravvive col rango (copiato) e la durata.
    vel = esper.try_component(pe, Veleno)
    assert vel is not None and vel.rango == 5 and vel.durata == 7


def test_H8_due_artefatti_separati_riferimento_non_contenuto(mondo_isolato: str, tmp_path) -> None:
    costruisci_run(id_dominio="carl")
    salva_run(tmp_path, model_id="m", timestamp=1.0)

    ps = path_stato(tmp_path, "carl")
    pa = path_archivio(tmp_path, "carl")
    assert ps.exists() and pa.exists()
    assert ps != pa  # file separati

    # Lo stato contiene un RIFERIMENTO al sidecar (il nome), non il suo contenuto.
    _intest, corpo = _leggi_due_righe(ps)
    assert corpo["archivio_ref"] == pa.name
    assert "record" not in corpo  # nessun contenuto d'Archivio dentro lo stato


def test_H9_stato_in_chiaro_sidecar_compresso(mondo_isolato: str, tmp_path) -> None:
    costruisci_run(id_dominio="carl")
    salva_run(tmp_path, model_id="m", timestamp=1.0)

    # Stato: testo JSON leggibile (la prima riga parsa come intestazione).
    intest = leggi_intestazione(path_stato(tmp_path, "carl"))
    assert intest["uuid"] == "carl"

    # Sidecar: gzip (magic bytes 0x1f 0x8b), e decomprime a JSON valido.
    raw = path_archivio(tmp_path, "carl").read_bytes()
    assert raw[:2] == b"\x1f\x8b"
    json.loads(gzip.decompress(raw).decode("utf-8"))


def test_H21_master_seed_nello_stato_e_nei_metadati_archivio(mondo_isolato: str, tmp_path) -> None:
    costruisci_run(master_seed=555, id_dominio="carl")
    salva_run(tmp_path, model_id="m", timestamp=1.0)

    # Nello stato: il SemeRun è fra i componenti serializzati.
    _intest, corpo = _leggi_due_righe(path_stato(tmp_path, "carl"))
    semi = [
        c
        for ent in corpo["entita"]
        for c in ent["componenti"]
        if c["tag"] == "seme_run"
    ]
    assert len(semi) == 1 and semi[0]["dati"]["master_seed"] == 555

    # Duplicato nei metadati dell'Archivio (sopravvive all'invalidazione, §8.1).
    archivio = carica_archivio(tmp_path, "carl")
    assert archivio is not None and archivio.master_seed == 555


def _leggi_due_righe(path):
    righe = path.read_text(encoding="utf-8").split("\n")
    return json.loads(righe[0]), json.loads(righe[1])
