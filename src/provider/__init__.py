"""provider — adattatori verso i provider LLM (dietro l'interfaccia di `contracts`).

Il backend reale (Anthropic) e il meccanismo nativo di output strutturato vivono qui,
MAI in `contracts` (PLK §5). Per l'MVP headless c'è il **provider fake** deterministico
(`FakeProvider`): stessa firma del backend reale, ZERO rete, ZERO chiave LLM.
"""

from .fake import FALLISCI, FakeProvider

__all__ = ["FakeProvider", "FALLISCI"]
