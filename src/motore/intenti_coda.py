"""Coda degli intenti lato motore + travaso unico (Canale A) (IC §7.1, C-8).

Gli host **accodano** intenti tipizzati in `CodaIntenti`. L'UNICO travaso coda→World
è la funzione **`travasa`**: la invocano il Processor `DrenaggioIntenti` (a ogni
turno, priorità massima) e il port al proprio turno (`SessioneGioco.avanza`) — un
solo proprietario della trasformazione, due punti di innesco. Nessun altro preleva
dalla coda; nessuno la filtra o scarta.

Il consumo è **guidato dal turno, non dal tempo di parete** (FNC §6.4): i sistemi
girano solo dentro `esper.process()`, mai da un timer a frame liberi. Questo è ciò
che rende C-8 codice e non proposito.

Forma del consumo (ESP §4, Canale A). Il travaso non *risolve* gli intenti né legge
la fase: deposita ogni intento come **componente-messaggio** (`MessaggioIntento`) nel
World. I consumatori (i `PhasedProcessor` gated alla loro fase, o il port per gli
intenti di menu) usano **`consuma_messaggi(tipo)`**: ognuno ritira SOLO il proprio
dominio, gli altri messaggi restano in attesa della loro fase. Così "il drenaggio
rispetta il phase-gate" (IC §7.1) è strutturale: in `COMBATTIMENTO` il consumatore
di intenti di esplorazione semplicemente non gira, e l'intento attende.
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
        (l'unico chiamante è `travasa`, il travaso del Canale A)."""
        intenti = list(self._coda)
        self._coda.clear()
        return intenti


@dataclass
class MessaggioIntento:
    """Componente-messaggio (Canale A): un intento travasato, in attesa del SUO
    consumatore (fase giusta o port). Il consumatore lo ritira via `consuma_messaggi`,
    che elimina l'entità-messaggio (ESP §4)."""

    intento: Intento


def travasa(coda: CodaIntenti) -> int:
    """L'UNICO travaso coda→World (Canale A): svuota la coda e deposita un
    `MessaggioIntento` per intento, in ordine FIFO. Ritorna quanti ne ha travasati.

    Chi lo invoca (il `DrenaggioIntenti` al tick, o il port al proprio turno) non
    cambia la semantica: il travaso è posseduto QUI — nessun altro preleva dalla coda.
    """
    intenti = coda.preleva_tutti()
    for intento in intenti:
        esper.create_entity(MessaggioIntento(intento))
    return len(intenti)


def consuma_messaggi(tipo: type) -> list[Intento]:
    """Rimuove e ritorna (FIFO) gli intenti pendenti che sono istanze di `tipo`.

    È il verbo dei CONSUMATORI (sistemi phase-gated o il port): ognuno consuma SOLO
    il proprio dominio (`isinstance`, quindi anche una base come `IntentoEsplorazione`),
    gli altri messaggi restano nel World in attesa della loro fase. L'entità-messaggio
    viene eliminata (niente gusci vuoti)."""
    consumati: list[Intento] = []
    for ent, msg in list(esper.get_component(MessaggioIntento)):
        if isinstance(msg.intento, tipo):
            consumati.append(msg.intento)
            esper.delete_entity(ent, immediate=True)
    return consumati


def messaggi_pendenti(tipo: type = Intento) -> int:
    """Quanti intenti pendenti (istanze di `tipo`) attendono un consumatore. Read-only."""
    return sum(1 for _e, m in esper.get_component(MessaggioIntento) if isinstance(m.intento, tipo))


class DrenaggioIntenti(esper.Processor):
    """Drena `CodaIntenti` una volta per turno e deposita i `MessaggioIntento`.

    NON è un `PhasedProcessor` e **non legge la fase**: gira ogni turno (priorità
    massima) col solo compito di travasare la coda esterna nel World (delega a
    `travasa`, il travaso unico). Il gating del *consumo* è dei `PhasedProcessor`
    consumatori, non suo (nessun check di fase a mano qui).
    """

    def __init__(self, coda: CodaIntenti) -> None:
        self.coda = coda

    def process(self, dt: int = 1) -> None:
        travasa(self.coda)
