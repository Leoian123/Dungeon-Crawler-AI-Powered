"""Adattatore nullo: consumatore read-only di eventi di dominio, senza Textual.

È lo stesso ruolo dell'adattatore di presentazione (IC §2.3) ma senza UI: si
sottoscrive agli eventi di dominio emessi dal motore e li *raccoglie* invece di
tradurli in chiamate Textual. Permette al test di fare `assert` su cosa il motore
ha emesso (criterio C-5).

Non importa Textual, non importa esper, non apre socket. Traffica solo in eventi
(DTO di dominio). In questa fase l'"evento" è un oggetto qualunque: quando arriva
il bus tipizzato di `contracts`, la firma resta identica — cambia solo il tipo.
"""

from __future__ import annotations

from typing import Any


class NullAdapter:
    """Raccoglie gli eventi di dominio emessi dal motore (read-only).

    Uso: `motore` (o l'arnia) chiama `on_event(evento)` per ogni evento di dominio;
    il test ispeziona `events`.
    """

    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        """Riceve un evento di dominio. Read-only: accumula, non muta lo stato."""
        self.events.append(event)

    def events_of(self, event_type: type) -> list[Any]:
        """Filtra gli eventi raccolti per tipo (comodità per gli assert)."""
        return [e for e in self.events if isinstance(e, event_type)]

    def clear(self) -> None:
        self.events.clear()
