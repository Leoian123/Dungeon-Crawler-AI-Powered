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

from dataclasses import dataclass, field

# Cause che contano come GENERAZIONE fallita (la richiesta è arrivata al modello e
# si è pagata): tutto il resto è trasporto/configurazione.
_CAUSE_GENERAZIONE = frozenset({"refusal", "max_tokens", "forma_output"})


@dataclass
class ConsumoProvider:
    """Tally cumulativo delle chiamate di un backend.

    Più backend possono CONDIVIDERE la stessa istanza (il composition root la passa
    al modello forte e al veloce): il totale diventa il consumo della run, senza un
    aggregatore a parte."""

    chiamate: int = 0             # risposte ricevute (candidato, refusal o troncatura)
    errori_trasporto: int = 0     # eccezioni rete/timeout/5xx/bug: nessun candidato
    generazioni_fallite: int = 0  # refusal/troncatura/output malformato: pagata, vuota
    input_tokens: int = 0
    output_tokens: int = 0
    cache_scritti: int = 0        # cache_creation_input_tokens (scrittura del prefisso)
    cache_letti: int = 0          # cache_read_input_tokens (hit: pagati a tariffa ridotta)
    # La tassonomia dei guasti: quale causa, quante volte, e l'ultima vista. Prima
    # tutto collassava su un None indistinto e "trasporto" copriva anche i bug di
    # codice (giro 2026-08-07: un AttributeError inghiottito ha mascherato per
    # sempre il fatto che il metodo dell'SDK non esisteva).
    cause: dict[str, int] = field(default_factory=dict)
    ultima_causa: str = ""

    def riassunto(self) -> str:
        """Una riga leggibile per l'host: spesa e guasti della sessione. Esiste
        perché il tally veniva accumulato e MAI mostrato (audit 2026-08-07): quando
        il GM live degradava al turno neutro, nessuno poteva dire perché."""
        dettaglio = ""
        if self.cause:
            voci = ", ".join(f"{k}×{v}" for k, v in sorted(self.cause.items()))
            dettaglio = f" [{voci}]"
        return (
            f"consumo LLM: {self.chiamate} chiamate, "
            f"{self.input_tokens} tok in / {self.output_tokens} tok out "
            f"(cache: {self.cache_letti} letti, {self.cache_scritti} scritti); "
            f"guasti: {self.errori_trasporto} trasporto, "
            f"{self.generazioni_fallite} generazione{dettaglio}"
        )

    def registra_guasto(self, causa: str) -> None:
        """Un fallimento con la sua causa: incrementa il contatore giusto e tiene
        la tassonomia. `causa` è una parola chiave stabile (es. "rete", "timeout",
        "http_401", "refusal", "max_tokens", "forma_output", "inatteso:TypeError")."""
        self.ultima_causa = causa
        self.cause[causa] = self.cause.get(causa, 0) + 1
        if causa in _CAUSE_GENERAZIONE:
            self.generazioni_fallite += 1
        else:
            self.errori_trasporto += 1

    def registra_risposta(self, usage: object) -> None:
        """Accumula l'`usage` di una risposta API. Campi assenti o `None` valgono 0:
        una forma nuova della risposta non fa mai esplodere il tally (il conteggio è
        osservabilità, non un gate)."""
        self.chiamate += 1
        self.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        self.cache_scritti += int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        self.cache_letti += int(getattr(usage, "cache_read_input_tokens", 0) or 0)
