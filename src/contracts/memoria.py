"""Porta della MEMORIA NARRATIVA — il contratto, non l'implementazione (Fase 6).

La memoria DINAMICA della run (personaggi incontrati, luoghi segnati, eventi,
interazioni) vive dietro questo Protocol: il motore vi scrive documenti e ne
recupera i più rilevanti per il fascicolo del GM. Il lore STATICO di stagione
non passa di qui (vive nel prefisso di sistema, congelato per la run).

Implementazioni: oggi `MemoriaSuArchivio` (motore, file-based deterministica sul
sidecar esistente); domani un DB vettoriale/RAG a livello guscio — STESSA porta,
zero modifiche al motore (decisione utente 2026-08-08: porta ora, vettoriale
dopo). Il recupero è un servizio di CONTESTO: alimenta prompt, mai stato — un
documento non attraversa alcun gate perché non ne ha bisogno.

Dipendenze: solo stdlib + Pydantic (disciplina di `contracts`).
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, StringConstraints

from .schema import RE_SLUG


class TipoDocumento(str, Enum):
    """Le categorie della memoria dinamica. Vocabolario chiuso del MOTORE (non
    AI-facing: l'AI non conia documenti, il motore li scrive dai fatti)."""

    PERSONAGGIO = "personaggio"
    LUOGO = "luogo"
    EVENTO = "evento"
    INTERAZIONE = "interazione"
    LORE = "lore"


class DocumentoMemoria(BaseModel):
    """UN fatto narrativo durevole. Dato puro, congelato.

    `id` è uno slug stabile (stessa forma degli asset): riscrivere lo stesso id
    AGGIORNA il documento (memoization idempotente, come l'Archivio). `piano` e
    `tick` ancorano il documento al momento in cui è stato scritto."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Annotated[str, StringConstraints(pattern=RE_SLUG)]
    tipo: TipoDocumento
    titolo: str
    testo: str
    tags: tuple[str, ...] = ()
    piano: int = 0
    tick: int = 0


@runtime_checkable
class MemoriaNarrativa(Protocol):
    """La porta: salva/recupera. Nessuna autorità di dominio, nessun gate.

    `recupera` è DETERMINISTICO per contratto (stessa query + stesso store →
    stessi documenti nello stesso ordine): la riproducibilità della run non
    dipende dall'implementazione dello scoring."""

    def salva(self, documento: DocumentoMemoria) -> None: ...

    def recupera(
        self, query: str, *, tipi: tuple[TipoDocumento, ...] = (), limite: int = 3
    ) -> tuple[DocumentoMemoria, ...]: ...
