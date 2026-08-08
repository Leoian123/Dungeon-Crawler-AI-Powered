"""provider — adattatori verso i provider LLM (dietro l'interfaccia di `contracts`).

Due implementazioni della stessa firma `genera(prompt, schema)`:
  - **`FakeProvider`** — deterministico, offline, ZERO rete/chiave: l'MVP headless e i
    test girano su questo (C-5).
  - **`AnthropicBackend`** — il backend reale: possiede SOLO il trasporto (chiamata API,
    output strutturato nativo, pin del modello, key da env), MAI il dominio. L'SDK
    `anthropic` è importato pigramente, così questo modulo si importa anche senza SDK.

La selezione di *quale* implementazione è config/ambiente (PLK §4): il motore vede la
stessa interfaccia. Il meccanismo nativo di output strutturato vive qui, MAI in
`contracts` (PLK §5, F-12).
"""

from .composito import ProviderPerSchema
from .consumo import ConsumoProvider
from .anthropic_backend import (
    MODELLO_DEFAULT,
    MODELLO_VELOCE,
    NOME_VAR_CHIAVE,
    AnthropicBackend,
    chiave_presente,
    sdk_disponibile,
)
from .fake import FALLISCI, FakeProvider
from .root import CORSIE_DEFAULT, ProfiloCorsia, costruisci_backend_live, scegli_provider

__all__ = [
    "FakeProvider",
    "FALLISCI",
    "AnthropicBackend",
    "ConsumoProvider",
    "CORSIE_DEFAULT",
    "MODELLO_DEFAULT",
    "MODELLO_VELOCE",
    "NOME_VAR_CHIAVE",
    "ProfiloCorsia",
    "ProviderPerSchema",
    "chiave_presente",
    "costruisci_backend_live",
    "scegli_provider",
    "sdk_disponibile",
]
