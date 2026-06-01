"""Coda degli intenti lato motore + Processor di drenaggio (IC §7.1, C-8).

I widget (futuri) **accodano** intenti tipizzati in `CodaIntenti`. Il motore la
**drena UNA volta per turno** tramite `DrenaggioIntenti`, un Processor ad **alta
priorità** che gira all'inizio del giro (run.py gli assegna la priorità massima).

Il drenaggio è **guidato dal turno, non dal tempo di parete** (FNC §6.4): avviene
solo dentro `esper.process()`, mai da un timer a frame liberi. Questo è ciò che
rende C-8 codice e non proposito.

Forma del consumo (ESP §4, Canale A). Il drenaggio non *risolve* gli intenti né
legge la fase: deposita ogni intento drenato come **componente-messaggio**
(`MessaggioIntento`) nel World. I sistemi che lo consumano sono `PhasedProcessor`
gated alla loro fase e, nello **stesso giro** (priorità più bassa del drenaggio, ma
stessa `process()`), lo leggono e lo **rimuovono** (Canale A: il consumatore toglie
il tag). Così "il drenaggio rispetta il phase-gate" (IC §7.1) è strutturale: in
`COMBATTIMENTO` il consumatore di intenti di narrazione semplicemente non gira.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import esper

from contracts import Intento


class CodaIntenti:
    """Coda lato motore: i widget vi **accodano** intenti tipizzati; il motore la
    drena dal turno. NON è il bus (che è stateless, IC §4): lo stato vive qui,
    nell'endpoint, drenato dal turno."""

    def __init__(self) -> None:
        self._coda: deque[Intento] = deque()

    def accoda(self, intento: Intento) -> None:
        """Punto d'ingresso dei widget: accoda un intento tipizzato."""
        self._coda.append(intento)

    def __len__(self) -> int:
        return len(self._coda)

    def preleva_tutti(self) -> list[Intento]:
        """Svuota la coda e ritorna gli intenti in ordine FIFO. Uso interno al motore
        (lo chiama `DrenaggioIntenti`, una volta per turno)."""
        intenti = list(self._coda)
        self._coda.clear()
        return intenti


@dataclass
class MessaggioIntento:
    """Componente-messaggio (Canale A): un intento drenato in attesa di consumo nella
    fase corrente. Il consumatore lo **rimuove** nello stesso `run()` (ESP §4)."""

    intento: Intento


class DrenaggioIntenti(esper.Processor):
    """Drena `CodaIntenti` una volta per turno e deposita i `MessaggioIntento`.

    NON è un `PhasedProcessor` e **non legge la fase**: gira ogni turno (priorità
    massima) col solo compito di travasare la coda esterna nel World. Il gating del
    *consumo* è dei `PhasedProcessor` consumatori, non suo (nessun check di fase a
    mano qui).
    """

    def __init__(self, coda: CodaIntenti) -> None:
        self.coda = coda

    def process(self, dt: int = 1) -> None:
        for intento in self.coda.preleva_tutti():
            esper.create_entity(MessaggioIntento(intento))
