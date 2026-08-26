"""Regression — salva-ed-esci NON deve azzerare il sidecar dell'Archivio (H §11).

`Guscio.concludi()` in uscita volontaria salvava senza `archivio=`: `salva_run`
costruiva un Archivio VUOTO e sovrascriveva il sidecar, cancellando i turni GM
congelati proprio nell'atto di salvare. Il fix: senza `archivio=` il guscio
RILEGGE il sidecar esistente; il chiamante che possiede l'Archivio di sessione
(es. `SessioneGioco`) lo passa esplicitamente, con etichetta e timestamp.
"""

from __future__ import annotations

import esper
import pytest

from guscio import NOME_DEFAULT, NOME_RUN, Guscio
from motore import (
    MODEL_ID_DEFAULT,
    Archivio,
    carica_archivio,
    indice_crawler,
    salva_run,
)


@pytest.fixture
def guscio_pulito():
    """Parcheggia nel default e ripulisce il contesto "run" attorno al test."""
    esper.switch_world(NOME_DEFAULT)
    esper.clear_database()
    if NOME_RUN in esper.list_worlds():
        esper.delete_world(NOME_RUN)
    yield
    esper.switch_world(NOME_DEFAULT)
    if NOME_RUN in esper.list_worlds():
        esper.delete_world(NOME_RUN)
    esper.clear_database()


def _archivio_con_turni(n: int) -> Archivio:
    archivio = Archivio(master_seed=1, model_id=MODEL_ID_DEFAULT)
    for i in range(n):
        archivio.congela(f"firma-{i}", {"seq": i + 1, "prosa": f"turno {i}"}, tipo="turno_gm")
    return archivio


def test_concludi_senza_archivio_non_azzera_il_sidecar(guscio_pulito, tmp_path) -> None:
    g = Guscio(tmp_path)
    g.nuova_partita(uuid="carl", seed=3)
    salva_run(tmp_path, archivio=_archivio_con_turni(2))  # sidecar con 2 turni
    g.esci_volontariamente()
    g.concludi()  # senza archivio=: rilegge il sidecar, non lo azzera
    riletto = carica_archivio(tmp_path, "carl")
    assert riletto is not None
    assert len(riletto.record_di_tipo("turno_gm")) == 2


def test_concludi_con_archivio_etichetta_timestamp(guscio_pulito, tmp_path) -> None:
    g = Guscio(tmp_path)
    g.nuova_partita(uuid="carl", seed=3)
    g.esci_volontariamente()
    g.concludi(archivio=_archivio_con_turni(1), etichetta="Donut", timestamp=123.5)
    [voce] = indice_crawler(tmp_path)
    assert voce.etichetta == "Donut"
    assert voce.timestamp == 123.5
    riletto = carica_archivio(tmp_path, "carl")
    assert riletto is not None
    assert len(riletto.record_di_tipo("turno_gm")) == 1
