"""L'Archivio degli Output Validati — sidecar compresso, patrimonio (H §8).

Store di record discreti, ciascuno un contenuto **validato dal motore** (uscito dal
gate), **congelato**, **keyed sul prompt seeded** (F §8). Nell'MVP ha un solo inquilino:
la **cache delle stanze**.

Proprietà (H §8):
  - **autosufficiente e promovibile** (§8.1): replayabile senza il blob di stato del
    crawler che l'ha prodotto; i metadati portano una **copia del master seed** (§8.1,
    H-21) e il model id, così sopravvivono all'invalidazione di fine-run (per il dono, §12);
  - **lasco** (§8.3, H-10): un cache-miss → `None` → il chiamante rigenera. Per il
    gameplay è tollerabile; il *formato* resta replay-capace (slot `tipo` dei record),
    ma il ramo-completezza non è esercitato nell'MVP;
  - **solo selezione + narrazione, mai statistiche** (H-11): le stat le ricalcola
    sempre il motore. Lo schema F è già senza numeri, quindi un `TurnoNarrazione`
    validato è un contenuto legittimo da congelare.

La compressione vive QUI (sul sidecar), mai sullo stato (in chiaro, H-9): vedi `disco.py`.
"""

from __future__ import annotations

from .formato import (
    SCHEMA_VERSION,
    ArchivioSerializzato,
    MetadatiArchivio,
    RecordArchivio,
)


class Archivio:
    """Cache frozen-by-key degli output validati. Lasca: miss → `None` (rigenera)."""

    def __init__(self, *, master_seed: int, model_id: str) -> None:
        self.master_seed = master_seed
        self.model_id = model_id
        # chiave (prompt seeded) → record congelato.
        self._record: dict[str, RecordArchivio] = {}

    def congela(self, chiave: str, contenuto: dict, *, tipo: str = "output") -> None:
        """Congela un output validato sotto la sua chiave. Riscrivere la stessa chiave
        sostituisce (memoization idempotente)."""
        self._record[chiave] = RecordArchivio(chiave=chiave, contenuto=contenuto, tipo=tipo)

    def cerca(self, chiave: str) -> dict | None:
        """Rilegge un contenuto congelato, o `None` se assente (cache-miss → rigenera,
        H-10). La rilettura è una **memoization**, non riproducibilità del modello (§8.2)."""
        record = self._record.get(chiave)
        return record.contenuto if record is not None else None

    def __len__(self) -> int:
        return len(self._record)

    # --- (de)serializzazione del formato (la compressione è in disco.py) --------

    def to_dict(self) -> dict:
        modello = ArchivioSerializzato(
            metadati=MetadatiArchivio(
                master_seed=self.master_seed,
                model_id=self.model_id,
                schema_version=SCHEMA_VERSION,
            ),
            record=list(self._record.values()),
        )
        return modello.model_dump()

    @classmethod
    def from_dict(cls, dati: dict) -> "Archivio":
        modello = ArchivioSerializzato.model_validate(dati)
        archivio = cls(
            master_seed=modello.metadati.master_seed,
            model_id=modello.metadati.model_id,
        )
        for record in modello.record:
            archivio._record[record.chiave] = record
        return archivio
