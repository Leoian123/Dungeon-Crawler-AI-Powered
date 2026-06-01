"""Archivio degli Output Validati: cache lasca, record senza statistiche (H-10, H-11).
Headless.
"""

from __future__ import annotations

from motore import Archivio, carica_archivio, salva_run
from motore.persistenza.formato import RecordArchivio
from tests.persist_helpers import costruisci_run


# --- H-10: rilettura non rigenerazione; miss → None (lasco) -------------------

def test_H10_congela_e_rileggi() -> None:
    arch = Archivio(master_seed=1, model_id="m")
    contenuto = {"prosa": "I Tubi Singhiozzanti", "entita": {"archetipo": "slime"}}
    arch.congela("prompt-seeded-stanza-7", contenuto)
    # Rilettura dal record congelato: identico (memoization, non ri-generazione).
    assert arch.cerca("prompt-seeded-stanza-7") == contenuto


def test_H10_cache_miss_ritorna_none() -> None:
    arch = Archivio(master_seed=1, model_id="m")
    assert arch.cerca("stanza-mai-vista") is None  # miss → None → il motore rigenera


def test_H10_roundtrip_compresso_preserva_i_record(mondo_isolato: str, tmp_path) -> None:
    costruisci_run(id_dominio="carl")
    arch = Archivio(master_seed=1, model_id="m")
    arch.congela("k1", {"prosa": "stanza uno"})
    arch.congela("k2", {"prosa": "stanza due"})
    salva_run(tmp_path, archivio=arch, model_id="m", timestamp=1.0)

    ricaricato = carica_archivio(tmp_path, "carl")
    assert ricaricato is not None
    assert ricaricato.cerca("k1") == {"prosa": "stanza uno"}
    assert ricaricato.cerca("k2") == {"prosa": "stanza due"}
    assert len(ricaricato) == 2


# --- H-11: record solo selezione + narrazione, nessuna statistica -------------

def test_H11_record_senza_campi_di_statistica() -> None:
    # Il modello del record non porta hp/danno/difesa: solo chiave + contenuto + tipo.
    campi = set(RecordArchivio.model_fields)
    assert campi == {"chiave", "contenuto", "tipo"}
    for vietato in ("hp", "danno", "difesa", "statistiche", "stat"):
        assert vietato not in campi


def test_H11_slot_marcatore_di_fallback_in_forma_non_esercitato() -> None:
    # Il formato regge "output oppure marcatore di fallback" (F-13), ma l'MVP popola
    # solo "output" (§8.3): il default del tipo è "output".
    r = RecordArchivio(chiave="k", contenuto={"prosa": "x"})
    assert r.tipo == "output"


def test_H11_archivio_autosufficiente_porta_il_seed(mondo_isolato: str, tmp_path) -> None:
    # Replayabile senza il blob di stato: i metadati portano master seed + model id.
    costruisci_run(master_seed=4242, id_dominio="carl")
    salva_run(tmp_path, model_id="opus", timestamp=1.0)
    arch = carica_archivio(tmp_path, "carl")
    assert arch is not None
    assert arch.master_seed == 4242
    assert arch.model_id == "opus"
