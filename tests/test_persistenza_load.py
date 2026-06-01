"""Contratto di load: valida-e-degrada, versione/migrazione, scan dell'elenco
(H-12, H-13, H-22). Headless.
"""

from __future__ import annotations

import json

import esper
import pytest

from motore import (
    CaricamentoFallito,
    carica_da_disco,
    indice_crawler,
    salva_run,
)
from motore.persistenza.disco import path_stato
from motore.persistenza.formato import SCHEMA_VERSION, VersioneIncompatibile, migra
from tests.persist_helpers import costruisci_run


# --- H-12: load di un file corrotto/troncato/di versione incompatibile --------

def test_H12_file_mancante_degrada_senza_crash(mondo_isolato: str, tmp_path) -> None:
    with pytest.raises(CaricamentoFallito):
        carica_da_disco(tmp_path, "inesistente")


def test_H12_json_malformato_degrada(mondo_isolato: str, tmp_path) -> None:
    p = path_stato(tmp_path, "carl")
    p.write_text("{non json\n{nemmeno}\n", encoding="utf-8")
    with pytest.raises(CaricamentoFallito):
        carica_da_disco(tmp_path, "carl")


def test_H12_file_troncato_degrada(mondo_isolato: str, tmp_path) -> None:
    # Solo l'intestazione, niente corpo: troncato.
    p = path_stato(tmp_path, "carl")
    p.write_text(json.dumps({"uuid": "carl"}) + "\n", encoding="utf-8")
    with pytest.raises(CaricamentoFallito):
        carica_da_disco(tmp_path, "carl")


def test_H12_coerenza_profondita_impossibile(mondo_isolato: str, tmp_path) -> None:
    costruisci_run(id_dominio="carl")
    salva_run(tmp_path, model_id="m", timestamp=1.0)
    # Manomette la profondità a 0 (impossibile: ≥ 1).
    p = path_stato(tmp_path, "carl")
    intest, corpo = p.read_text(encoding="utf-8").split("\n")[:2]
    intest_d = json.loads(intest)
    intest_d["profondita"] = 0
    p.write_text(json.dumps(intest_d) + "\n" + corpo + "\n", encoding="utf-8")
    with pytest.raises(CaricamentoFallito):
        carica_da_disco(tmp_path, "carl")


def test_H12_load_fallito_non_muta_current_world(mondo_isolato: str, tmp_path) -> None:
    prima = esper.current_world
    # carica_da_disco valida e legge SENZA toccare il World: su fallimento solleva e
    # `current_world` resta intatto (il guscio resterà nel menu, niente switch).
    with pytest.raises(CaricamentoFallito):
        carica_da_disco(tmp_path, "inesistente")
    assert esper.current_world == prima  # current_world INTATTO
    assert list(esper.get_entities()) == []  # nessuno stato parziale


def test_H12_versione_futura_rifiutata(mondo_isolato: str, tmp_path) -> None:
    costruisci_run(id_dominio="carl")
    salva_run(tmp_path, model_id="m", timestamp=1.0)
    p = path_stato(tmp_path, "carl")
    intest, corpo = p.read_text(encoding="utf-8").split("\n")[:2]
    intest_d = json.loads(intest)
    intest_d["schema_version"] = SCHEMA_VERSION + 99  # dal futuro
    p.write_text(json.dumps(intest_d) + "\n" + corpo + "\n", encoding="utf-8")
    with pytest.raises(CaricamentoFallito):
        carica_da_disco(tmp_path, "carl")


# --- H-13: schema_version a v1, migrazione = catena v→v+1 ---------------------

def test_H13_schema_version_e_model_id_presenti(mondo_isolato: str, tmp_path) -> None:
    costruisci_run(id_dominio="carl")
    salva_run(tmp_path, model_id="opus-x", timestamp=1.0)
    intest = json.loads(path_stato(tmp_path, "carl").read_text(encoding="utf-8").split("\n")[0])
    assert intest["schema_version"] == SCHEMA_VERSION
    assert intest["model_id"] == "opus-x"


def test_H13_migrazione_e_una_catena_incrementale() -> None:
    # Catena iniettata: v1→v2→v3 applicata in ordine, ciascuna +1.
    def da1(intest, corpo):
        corpo = {**corpo, "passo1": True}
        return intest, corpo

    def da2(intest, corpo):
        corpo = {**corpo, "passo2": True}
        return intest, corpo

    intest = {"schema_version": 1}
    corpo = {"entita": []}
    intest_out, corpo_out = migra(
        intest, corpo, migrazioni={1: da1, 2: da2}, versione_corrente=3
    )
    assert intest_out["schema_version"] == 3
    assert corpo_out["passo1"] and corpo_out["passo2"]


def test_H13_migrazione_futura_solleva() -> None:
    with pytest.raises(VersioneIncompatibile):
        migra({"schema_version": 5}, {"entita": []}, versione_corrente=1)


# --- H-22: scan dell'elenco legge solo l'intestazione; corrotto = «corrotta» --

def test_H22_indice_legge_solo_intestazione(mondo_isolato: str, tmp_path) -> None:
    costruisci_run(profondita=2, id_dominio="alfa")
    salva_run(tmp_path, model_id="m", timestamp=7.0, etichetta="Alfa")

    voci = indice_crawler(tmp_path)
    assert len(voci) == 1
    v = voci[0]
    assert v.uuid == "alfa" and v.etichetta == "Alfa" and v.profondita == 2
    assert v.corrotta is False


def test_H22_intestazione_illeggibile_compare_come_corrotta(mondo_isolato: str, tmp_path) -> None:
    # Save valido + save con intestazione rotta: lo scan non crasha, segna «corrotta».
    costruisci_run(id_dominio="buono")
    salva_run(tmp_path, model_id="m", timestamp=1.0)
    (path_stato(tmp_path, "rotto")).write_text("{header non valido\n{}\n", encoding="utf-8")

    voci = {v.uuid: v for v in indice_crawler(tmp_path)}
    assert voci["buono"].corrotta is False
    assert voci["rotto"].corrotta is True
    assert voci["rotto"].etichetta == "«corrotta»"
