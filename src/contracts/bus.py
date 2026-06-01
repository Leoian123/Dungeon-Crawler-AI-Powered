"""Bus tipizzato di progetto (ESP §5).

Strato sottile SOPRA esper, **non** il dispatcher nativo di esper. Tre proprietà
normative (ESP §5), tutte qui per costruzione:

  - ogni evento è una **classe/dataclass**, non una stringa → sottoscrizione per
    TIPO, niente identificazione per nome (nessun refuso = evento muto);
  - gli handler sono tenuti con **riferimenti FORTI** (una lista normale, mai
    weakref) → non possono essere garbage-collected e sparire silenziosamente;
  - registrazione e deregistrazione **esplicite**.

Il bus resta **stupido** (IC §4): instrada tipi, non decide, non trasforma, non
conserva stato di dominio, non valida. La validazione (gate) sta nel motore.

Dipendenze: solo stdlib. Nessun esper, nessun Textual, nessun provider (F-2).
"""

from __future__ import annotations

from typing import Callable, TypeVar

_E = TypeVar("_E")

# Un handler riceve l'evento del suo tipo e non ritorna nulla (fire-and-forget).
Handler = Callable[[_E], None]


class BusEventi:
    """Bus di dominio: sottoscrizione per tipo, handler a riferimento forte.

    NON è il dispatcher nativo di esper (`dispatch_event`/`set_handler`): quello
    identifica per stringa, non tipizza gli argomenti e tiene gli handler per
    weak-reference (ESP §5). Qui è l'opposto, per scelta.
    """

    def __init__(self) -> None:
        # tipo-di-evento -> lista di handler (riferimenti FORTI, ordine di registrazione).
        self._handlers: dict[type, list[Handler]] = {}

    def registra(self, tipo_evento: type[_E], handler: Handler) -> None:
        """Sottoscrive `handler` agli eventi di tipo ESATTO `tipo_evento`.

        La sottoscrizione è **per tipo**, non per nome. Lo stesso handler non si
        registra due volte sullo stesso tipo.
        """
        lista = self._handlers.setdefault(tipo_evento, [])
        if handler in lista:
            raise ValueError(
                f"handler già registrato per {tipo_evento.__name__}: {handler!r}"
            )
        lista.append(handler)  # riferimento forte: il bus lo tiene vivo

    def deregistra(self, tipo_evento: type[_E], handler: Handler) -> None:
        """Annulla esplicitamente una sottoscrizione. Errore se non c'era."""
        lista = self._handlers.get(tipo_evento)
        if not lista or handler not in lista:
            raise ValueError(
                f"handler non registrato per {tipo_evento.__name__}: {handler!r}"
            )
        lista.remove(handler)
        if not lista:
            del self._handlers[tipo_evento]

    def pubblica(self, evento: object) -> None:
        """Instrada `evento` agli handler registrati sul suo tipo ESATTO.

        Push, fire-and-forget: chi pubblica non sa chi ascolta. Si itera su una
        copia, così un handler può deregistrarsi durante il dispatch senza rompere
        l'iterazione.
        """
        for handler in tuple(self._handlers.get(type(evento), ())):
            handler(evento)

    def pulisci(self) -> None:
        """Rimuove tutte le sottoscrizioni (comodo nel teardown dei test)."""
        self._handlers.clear()
