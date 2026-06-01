"""Aggancio per un provider LLM fake — SENZA rete.

Scheletro: nel nodo F questo implementerà l'interfaccia provider di `contracts`
restituendo output validati pre-confezionati (utile anche per il replay
riproducibile: seed + cache degli output, criterio C-5 doppio uso).

Per ora è un segnaposto deterministico: nessuna chiamata di rete, nessuna chiave.
Restituisce risposte in coda nell'ordine in cui sono state caricate.
"""

from __future__ import annotations

from collections import deque
from typing import Any


class FakeProvider:
    """Provider deterministico, offline. Nessun I/O, nessuna chiave LLM.

    Caricare risposte con `queue_response(...)`; il motore (in futuro) le consuma
    via `complete(...)`. Se la coda è vuota, solleva — così un test che si aspetta
    una chiamata LLM non mascherata fallisce in modo rumoroso invece che muto.
    """

    def __init__(self) -> None:
        self._responses: deque[Any] = deque()
        self.calls: list[Any] = []

    def queue_response(self, response: Any) -> None:
        self._responses.append(response)

    async def complete(self, request: Any) -> Any:
        """Punto d'aggancio async (FNC §7: async sì, thread no). Offline."""
        self.calls.append(request)
        if not self._responses:
            raise AssertionError(
                "FakeProvider: nessuna risposta in coda per la richiesta ricevuta."
            )
        return self._responses.popleft()
