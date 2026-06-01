"""Atomicità e durabilità: temp+rename, ordine, backup di recovery (H-14, H-15, H-1).
Headless.
"""

from __future__ import annotations

import gzip
import json

from motore import salva_run
from motore.persistenza.disco import (
    SUFFISSO_BACKUP_ARCHIVIO,
    SUFFISSO_BACKUP_STATO,
    path_archivio,
    path_stato,
    scrivi_stato,
)
from tests.persist_helpers import costruisci_run


# --- H-14: scrittura atomica temp+rename; nessun .tmp residuo ------------------

def test_H14_nessun_file_temporaneo_residuo(mondo_isolato: str, tmp_path) -> None:
    costruisci_run(id_dominio="carl")
    salva_run(tmp_path, model_id="m", timestamp=1.0)
    # Dopo il rename atomico non resta nessun file .tmp.
    assert list(tmp_path.glob("*.tmp")) == []
    # I due file finali esistono e sono completi.
    assert path_stato(tmp_path, "carl").exists()
    assert path_archivio(tmp_path, "carl").exists()


def test_H14_scrittura_atomica_sostituisce_in_blocco(tmp_path) -> None:
    # Scrivere due volte non lascia stato intermedio: il file finale è quello nuovo.
    p = tmp_path / "x.stato.json"
    scrivi_stato(p, {"v": 1}, {"entita": []})
    scrivi_stato(p, {"v": 2}, {"entita": [], "nuovo": True})
    intest, corpo = p.read_text(encoding="utf-8").split("\n")[:2]
    assert json.loads(intest)["v"] == 2
    assert json.loads(corpo)["nuovo"] is True
    assert list(tmp_path.glob("*.tmp")) == []


def test_H14_ordine_di_durabilita_sidecar_prima(mondo_isolato: str, tmp_path) -> None:
    # Quando lo stato referenzia il sidecar, il sidecar è già durevole.
    costruisci_run(id_dominio="carl")
    salva_run(tmp_path, model_id="m", timestamp=1.0)
    _intest, corpo = (
        path_stato(tmp_path, "carl").read_text(encoding="utf-8").split("\n")[:2]
    )
    ref = json.loads(corpo)["archivio_ref"]
    # Il file referenziato esiste davvero (durabilità ordinata, §10.2).
    assert (tmp_path / ref).exists()


# --- H-15: un backup di sola recovery della coppia coerente -------------------

def test_H15_backup_della_coppia_coerente(mondo_isolato: str, tmp_path) -> None:
    costruisci_run(id_dominio="carl", profondita=1)
    salva_run(tmp_path, model_id="m", timestamp=1.0)  # primo save: nessun backup ancora
    assert list(tmp_path.glob(f"*{SUFFISSO_BACKUP_STATO}")) == []

    # Secondo save: la coppia precedente è copiata nel backup (stato + sidecar insieme).
    salva_run(tmp_path, model_id="m", timestamp=2.0)
    assert (tmp_path / f"carl{SUFFISSO_BACKUP_STATO}").exists()
    assert (tmp_path / f"carl{SUFFISSO_BACKUP_ARCHIVIO}").exists()


def test_H15_backup_e_coppia_coerente_stato_e_sidecar(mondo_isolato: str, tmp_path) -> None:
    # Il backup non è solo lo stato: è la COPPIA (ripristinare uno stato vecchio con un
    # sidecar diverso farebbe penzolare il riferimento).
    costruisci_run(id_dominio="carl")
    salva_run(tmp_path, model_id="m", timestamp=1.0)
    salva_run(tmp_path, model_id="m", timestamp=2.0)
    bak_stato = tmp_path / f"carl{SUFFISSO_BACKUP_STATO}"
    bak_arch = tmp_path / f"carl{SUFFISSO_BACKUP_ARCHIVIO}"
    # Il backup-stato è JSON leggibile; il backup-sidecar è gzip valido.
    json.loads(bak_stato.read_text(encoding="utf-8").split("\n")[0])
    gzip.decompress(bak_arch.read_bytes())


# --- H-1: niente pickle/marshal sul percorso di save/load ---------------------

def test_H1_nessun_pickle_nel_save(mondo_isolato: str, tmp_path) -> None:
    costruisci_run(id_dominio="carl")
    salva_run(tmp_path, model_id="m", timestamp=1.0)
    # Il file di stato è testo JSON, non un blob pickle.
    testo = path_stato(tmp_path, "carl").read_text(encoding="utf-8")
    assert testo.lstrip().startswith("{")
