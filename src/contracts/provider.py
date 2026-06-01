"""Interfaccia provider — il confine di astrazione verso l'LLM (PLK §2).

SOLO la firma (Protocol). Nessuna implementazione: il backend reale (Anthropic) e il
meccanismo nativo di output strutturato vivono nel layer `provider/` del progetto,
MAI in `contracts` (PLK §5, D-5). Qui sta il *contratto* che il motore e il provider
onorano.

  genera(prompt, schema) -> candidato_conforme_allo_schema | None

- `prompt` arriva già assemblato dal motore ed è **opaco** al provider: voce/tono +
  contesto + budget iniettato nel testo li costruisce il motore (dominio), non il
  provider (PLK §2, §3). Per questo `budget`/`contesto` NON sono nella firma.
- `schema` (un modello Pydantic di `schema.py`) pilota l'output strutturato e rende
  il verbo **generico**, non cablato sulla generazione-stanza: lo stesso `genera`
  serve narrazione e flavor — cambia lo schema, non il verbo (F §5).
- Il ritorno è un **candidato conforme allo schema oppure `None`** (qualunque causa
  di fallimento collassa su `None`, PLK §2). Conformità sintattica allo schema sì;
  appartenenza al catalogo e rispetto del budget NO: quelli sono giudizi del gate
  nel motore (PLK §2, §4).

È **async**: la chiamata all'LLM è l'unico request/response del sistema (IC §6) e
vive sotto il modello async di FNC §7 (async sì, thread no). La coroutine
host-agnostica del motore fa `await provider.genera(...)`.

Dipendenze: solo stdlib (`typing`) + Pydantic (F-2).
"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

# Il candidato è un'istanza del modello passato come `schema`.
TCandidato = TypeVar("TCandidato", bound=BaseModel)


@runtime_checkable
class Provider(Protocol):
    """Astrazione provider: un solo verbo, `genera`. Nessuna autorità di dominio.

    Possiede il **trasporto** (chiamata API, output strutturato, timeout/retry, pin
    del modello, lettura della key). NON costruisce il prompt, NON valida
    catalogo/budget, NON sceglie il fallback (PLK §3).
    """

    async def genera(
        self, prompt: str, schema: type[TCandidato]
    ) -> TCandidato | None:
        """Genera un candidato conforme a `schema`, oppure `None` se fallisce."""
        ...
