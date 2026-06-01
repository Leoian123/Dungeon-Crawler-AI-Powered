"""Backend Anthropic reale dietro l'unica firma `genera(prompt, schema)` (nodo D/PLK).

Possiede **solo il trasporto** (PLK §3): chiamata API, meccanismo nativo di output
strutturato, pin del modello, lettura della key. **NON** costruisce il prompt, **non**
valida catalogo/budget, **non** sceglie il fallback — quelli restano nel motore. Stessa
interfaccia del `FakeProvider`: il motore non sa quale dei due ha davanti.

Meccanismo di output strutturato (verificato sulla doc API attuale, **non** a memoria —
F-12): `client.messages.parse(..., output_format=<modello Pydantic>) → .parsed_output`
(istanza validata). `stop_reason` `"refusal"`/`"max_tokens"` = generazione fallita.
Confinato **qui**, mai in `contracts`/`motore`/membrana (F-12).

La **chiave** la legge l'SDK da `ANTHROPIC_API_KEY` (config/env): non è MAI cablata, in
URL, log o codice (PLK §4). L'SDK `anthropic` è importato **pigramente** dentro il
metodo: l'arnia headless (C-5) e i 200+ test non richiedono l'SDK installato.

Politica di fallimento: il backend mappa ogni causa su **`None`** (rete/timeout/
rate-limit, refusal, troncatura `max_tokens`); *quanto* ritentare e su cosa ripiegare lo
decide il **motore** dallo schema (F §5.1), non il provider.
"""

from __future__ import annotations

from contracts import TCandidato

# Pin del modello (PLK: il provider possiede il pin). Aggiornarlo è deliberato.
MODELLO_DEFAULT = "claude-opus-4-8"
# Nome della variabile d'ambiente che l'SDK legge da solo. La key NON passa di qui.
NOME_VAR_CHIAVE = "ANTHROPIC_API_KEY"

# Cause di fallimento di generazione (PLK §6): trattate come "candidato assente" → None.
_STOP_FALLITI = frozenset({"refusal", "max_tokens"})


class AnthropicBackend:
    """Provider reale. Una chiamata strutturata per invocazione (provider sottile, G §9.2)."""

    def __init__(
        self, *, modello: str = MODELLO_DEFAULT, max_tokens: int = 2048, timeout: float = 30.0
    ) -> None:
        self.modello = modello
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._client = None  # creato pigramente (lazy): nessun SDK finché non si chiama

    def _client_async(self):
        if self._client is None:
            import anthropic  # lazy: l'arnia headless non richiede l'SDK installato

            # La key la legge l'SDK da ANTHROPIC_API_KEY: mai cablata, mai loggata (PLK §4).
            self._client = anthropic.AsyncAnthropic(timeout=self.timeout)
        return self._client

    async def genera(
        self, prompt: str, schema: type[TCandidato]
    ) -> TCandidato | None:
        """Chiama l'API con output strutturato nativo; ritorna un candidato conforme a
        `schema` oppure `None`. Il `prompt` è **opaco** (lo assembla il motore, PLK §2)."""
        client = self._client_async()
        try:
            risposta = await client.messages.parse(
                model=self.modello,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
            )
        except Exception:
            # Trasporto: rete / timeout / rate-limit / 5xx → None. Il motore ripiega
            # (retry per schema, poi fallback atomico) — non è compito del provider.
            return None

        # Refusal o troncatura (max_tokens): generazione fallita → None (PLK §6).
        if getattr(risposta, "stop_reason", None) in _STOP_FALLITI:
            return None

        candidato = getattr(risposta, "parsed_output", None)
        # Cintura e bretelle: solo un'istanza conforme allo schema passa (il gate del
        # motore farà comunque catalogo+budget; qui è la garanzia di forma del trasporto).
        return candidato if isinstance(candidato, schema) else None
