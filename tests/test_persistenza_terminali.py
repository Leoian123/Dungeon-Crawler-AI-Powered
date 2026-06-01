"""Cadenza ed esiti terminali della persistenza (H-6, H-7, H-20, G-12 lato persistenza).
Headless.
"""

from __future__ import annotations

import esper

from motore import (
    NOME_DEFAULT,
    NOME_RUN,
    carica_crawler,
    indice_crawler,
    invalida,
    livello_corrente,
    protagonista,
    salva_run,
)
from motore.persistenza.disco import path_archivio, path_stato
from tests.persist_helpers import costruisci_run


# --- H-6 / H-7: save in-run, prima dello switch (non cambia current_world) -----

def test_H7_salva_non_cambia_current_world(mondo_isolato: str, tmp_path) -> None:
    costruisci_run(id_dominio="carl")
    prima = esper.current_world
    salva_run(tmp_path, model_id="m", timestamp=1.0)
    # Il salvataggio è in-run: il World sopravvive, nessuno switch (la scrittura
    # precede il teardown del guscio, non lo accompagna — H-7).
    assert esper.current_world == prima


def test_H6_salva_e_esplicito_non_un_processor() -> None:
    # Il save è a evento/comando: `salva_run` è una funzione chiamata esplicitamente,
    # non un Processor che ticca. (La disciplina statica è in test_persistenza_disciplina.)
    assert callable(salva_run)
    assert not isinstance(salva_run, esper.Processor)


# --- H-20: ogni terminale run→guscio ha un'azione; invalidazione a fine-run ----

def test_H20_invalida_rimuove_il_save(mondo_isolato: str, tmp_path) -> None:
    costruisci_run(id_dominio="carl")
    salva_run(tmp_path, model_id="m", timestamp=1.0)
    assert path_stato(tmp_path, "carl").exists()
    assert path_archivio(tmp_path, "carl").exists()

    # Fine-run (morte 6a o vittoria 6b): si invalida (non si salva).
    invalida(tmp_path, "carl")
    assert not path_stato(tmp_path, "carl").exists()
    assert not path_archivio(tmp_path, "carl").exists()


def test_H20_save_invalidato_sparisce_dallindice(mondo_isolato: str, tmp_path) -> None:
    costruisci_run(id_dominio="carl")
    salva_run(tmp_path, model_id="m", timestamp=1.0)
    assert any(v.uuid == "carl" for v in indice_crawler(tmp_path))
    invalida(tmp_path, "carl")
    assert not any(v.uuid == "carl" for v in indice_crawler(tmp_path))


# --- G-12 lato persistenza: H è l'autorità su current_world (carica_crawler) ---
# `switch_world` vive QUI (livello save/load, ESP §0.1): `carica_crawler` valida e poi
# entra nel contesto unico "run". Il guscio orchestra (test_guscio); H esegue.

def test_G12_carica_crawler_entra_nel_contesto_run(mondo_isolato: str, tmp_path) -> None:
    costruisci_run(profondita=3, master_seed=77, id_dominio="carl")
    salva_run(tmp_path, model_id="m", timestamp=1.0)
    try:
        ok = carica_crawler(tmp_path, "carl")
        assert ok is True
        assert esper.current_world == NOME_RUN  # contesto unico "run"
        assert livello_corrente() == 3
        _pe, marker, _scheda = protagonista()
        assert marker.id_dominio == "carl"
    finally:
        # Pulizia: H possiede lo switch; qui torno al mondo isolato del test perché il
        # teardown della fixture elimini correttamente il suo contesto.
        esper.switch_world(NOME_DEFAULT)
        if NOME_RUN in esper.list_worlds():
            esper.delete_world(NOME_RUN)
        esper.switch_world(mondo_isolato)


def test_G12_carica_crawler_fallito_non_muta_current_world(mondo_isolato: str, tmp_path) -> None:
    prima = esper.current_world
    # Valida PRIMA di switchare: su save inesistente ritorna False, niente switch.
    assert carica_crawler(tmp_path, "inesistente") is False
    assert esper.current_world == prima
    assert NOME_RUN not in esper.list_worlds()
