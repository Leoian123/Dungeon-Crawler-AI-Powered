"""Binario di mutazione intra-fase dello scontro: rinforzi (G §5; G-9/G-10).

"Aggiungere nemici a uno scontro in corso" è **mutazione intra-fase**, distinta dagli
eventi di transizione (`EncounterStarted`/`CombatResolved` cambiano *fase*; questa
**resta dentro `COMBATTIMENTO`**). Disciplina:

  - **Autorità (chi):** il **motore** (questo sistema seeded) rilascia ondate che
    l'AI ha **composto a monte** su `EncounterStarted` (§5.1). Mai iniezione live.
  - **Canale (come):** Canale A — un **componente-programma** (`PianoRinforzi`) letto
    da un sistema. Lo stato passa per A; l'eventuale reveal narrativo per il bus
    (Canale B) è additivo, non qui.
  - **Timing (quando):** a **confine di turno**, da un sistema a **priorità
    dichiarata** (registrato PRIMA del sistema-turno nel bucket solo-combattimento),
    **mai** durante l'iterazione di un'azione (§5.3).
  - **Cosa:** i nuovi combattenti ereditano gli invarianti §5.4 (effimeri, status
    single-owner, chiave d'iniziativa stabile).

**Mai (ri)emettere `EncounterStarted`** per aggiungere nemici (G-10): non è una
transizione di fase.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import esper

from .combattimento import SpecNemico, spawn_nemico, stato_combattimento
from .phased import SistemaSoloCombattimento


@dataclass
class OndataRinforzi:
    """Un'ondata programmata: i nemici entrano quando lo scontro raggiunge il round."""

    round_trigger: int
    nemici: list[SpecNemico]


@dataclass
class PianoRinforzi:
    """Componente-programma sullo scontro (Canale A). `rilasciate` = indici già usciti."""

    ondate: list[OndataRinforzi]
    rilasciate: set[int] = field(default_factory=set)


class SistemaRinforzi(SistemaSoloCombattimento):
    """Rilascia le ondate dovute, a confine di turno. Nessun `EncounterStarted`."""

    def run(self, dt: int) -> None:
        st = stato_combattimento()
        if st is None:
            return
        _ent_stato, stato = st

        trovati = esper.get_component(PianoRinforzi)
        if not trovati:
            return
        _ent_piano, piano = trovati[0]

        for indice, ondata in enumerate(piano.ondate):
            if indice in piano.rilasciate:
                continue
            if stato.round >= ondata.round_trigger:
                for spec in ondata.nemici:
                    nuovo = spawn_nemico(destrezza=spec.destrezza, punti_vita=spec.punti_vita)
                    stato.ordine.append(nuovo)  # i rinforzi entrano in coda all'iniziativa
                piano.rilasciate.add(indice)
