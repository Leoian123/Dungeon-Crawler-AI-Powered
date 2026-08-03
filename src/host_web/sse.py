"""Canale SSE dell'host web: eventi del processo → `text/event-stream`.

Trasporta SOLO segnali di presentazione (IC §3 — contratto sì, trasporto no):
`progresso` (i 5 stadi della pipeline GM), `evento_bus` (eventi di dominio),
`post` (nuovo post del thread: il client ri-fetcha), `morte`. Nessun turno guidato
dall'orologio: il ping periodico è keep-alive del TRASPORTO, mai un tick di gioco
(IC §7.1).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from .stato import SENTINELLA_CHIUSURA, StatoHost

INTERVALLO_PING = 15.0  # keep-alive contro i proxy che chiudono gli stream quieti


def formatta(evento: str, dati: dict[str, Any]) -> str:
    return f"event: {evento}\ndata: {json.dumps(dati, ensure_ascii=False)}\n\n"


async def flusso_eventi(stato: StatoHost) -> AsyncIterator[str]:
    """Generatore per `StreamingResponse`: una coda per abbonato, ping periodico."""
    coda = stato.sottoscrivi()
    try:
        yield ": collegato\n\n"
        while True:
            try:
                evento, dati = await asyncio.wait_for(coda.get(), timeout=INTERVALLO_PING)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            if (evento, dati) == SENTINELLA_CHIUSURA:
                # La run si è chiusa (hub): lo stream termina, il client riapre
                # l'EventSource alla run successiva.
                yield formatta("run_chiusa", {})
                return
            yield formatta(evento, dati)
    finally:
        stato.disdici(coda)
