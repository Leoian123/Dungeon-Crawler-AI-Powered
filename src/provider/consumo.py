"""Il contatore di CONSUMO del provider — token e chiamate, dato puro.

Prima di questo modulo il backend leggeva `stop_reason` e `parsed_output` e BUTTAVA
`risposta.usage`: in tutto `src/` non esisteva un solo numero su quanto una run
spende. Qualunque decisione sul modello di consegna (web a quota, tetto per run,
contenuto pre-generato) presuppone di poter MISURARE: questo è il minimo che rende
la spesa osservabile.

Il contatore accumula TOKEN, mai valute: i listini cambiano e non appartengono al
motore — il costo lo deriva l'host dal suo listino corrente (stesso principio dei
numeri §11: il dato qui, la politica fuori).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConsumoProvider:
    """Tally cumulativo delle chiamate di un backend.

    Più backend possono CONDIVIDERE la stessa istanza (il composition root la passa
    al modello forte e al veloce): il totale diventa il consumo della run, senza un
    aggregatore a parte."""

    chiamate: int = 0             # risposte ricevute (candidato, refusal o troncatura)
    errori_trasporto: int = 0     # eccezioni rete/timeout/5xx: nessun usage disponibile
    generazioni_fallite: int = 0  # refusal/max_tokens: la risposta c'è, il candidato no
    input_tokens: int = 0
    output_tokens: int = 0
    cache_scritti: int = 0        # cache_creation_input_tokens (scrittura del prefisso)
    cache_letti: int = 0          # cache_read_input_tokens (hit: pagati a tariffa ridotta)

    def registra_risposta(self, usage: object) -> None:
        """Accumula l'`usage` di una risposta API. Campi assenti o `None` valgono 0:
        una forma nuova della risposta non fa mai esplodere il tally (il conteggio è
        osservabilità, non un gate)."""
        self.chiamate += 1
        self.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        self.cache_scritti += int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        self.cache_letti += int(getattr(usage, "cache_read_input_tokens", 0) or 0)
