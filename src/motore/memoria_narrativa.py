"""`MemoriaSuArchivio` — la memoria narrativa file-based, sul sidecar esistente.

Implementa la porta `MemoriaNarrativa` (contracts) scrivendo i documenti come
record d'Archivio (`tipo="memoria_doc"`, chiave `mem:{tipo}:{id}`): persistenza
GRATIS via il sidecar compresso (H §8), per-run, ricostruzione al load inclusa
— zero formati nuovi, zero dipendenze nuove.

Il recupero è scoring DETERMINISTICO per sovrapposizione di token (niente RNG,
niente rete, niente embedding): sufficiente per ancorare il fascicolo del GM ai
fatti della run. Il DB vettoriale futuro è un'ALTRA implementazione della stessa
porta (a livello guscio, sovra-run) — il seam è il Protocol, non questo modulo.
"""

from __future__ import annotations

import re

from contracts import DocumentoMemoria, TipoDocumento

from .persistenza.archivio import Archivio

TIPO_RECORD_MEMORIA = "memoria_doc"

# Token alfanumerici di almeno 3 caratteri: articoli/preposizioni non pesano.
_RE_TOKEN = re.compile(r"[a-zà-ù0-9]{3,}")


def _tokens(testo: str) -> frozenset[str]:
    return frozenset(_RE_TOKEN.findall(testo.lower()))


class MemoriaSuArchivio:
    """La porta `MemoriaNarrativa` implementata sull'Archivio della run."""

    def __init__(self, archivio: Archivio) -> None:
        self._archivio = archivio

    def salva(self, documento: DocumentoMemoria) -> None:
        """Congela il documento sotto `mem:{tipo}:{id}`: stesso id → aggiornamento
        (memoization idempotente, la semantica dell'Archivio)."""
        chiave = f"mem:{documento.tipo.value}:{documento.id}"
        self._archivio.congela(chiave, documento.model_dump(), tipo=TIPO_RECORD_MEMORIA)

    def recupera(
        self, query: str, *, tipi: tuple[TipoDocumento, ...] = (), limite: int = 3
    ) -> tuple[DocumentoMemoria, ...]:
        """I documenti più rilevanti per la query, per sovrapposizione di token.

        Deterministico: ordina per (punteggio DESC, id ASC) — stessa query e
        stesso store danno sempre la stessa tupla. Punteggio 0 = fuori."""
        chiavi_query = _tokens(query)
        if not chiavi_query:
            return ()
        ammessi = set(tipi) if tipi else None
        candidati: list[tuple[int, str, DocumentoMemoria]] = []
        for record in self._archivio.record_di_tipo(TIPO_RECORD_MEMORIA):
            doc = DocumentoMemoria.model_validate(record.contenuto)
            if ammessi is not None and doc.tipo not in ammessi:
                continue
            pesabili = _tokens(f"{doc.titolo} {doc.testo} {' '.join(doc.tags)}")
            punteggio = len(chiavi_query & pesabili)
            if punteggio > 0:
                candidati.append((punteggio, doc.id, doc))
        candidati.sort(key=lambda t: (-t[0], t[1]))
        return tuple(doc for _p, _i, doc in candidati[:limite])
