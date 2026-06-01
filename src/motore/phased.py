"""Phase-gate STRUTTURALE: `PhasedProcessor` (FNC §6.1).

Il check di fase vive **qui, nella base**, e da nessun'altra parte. Un sistema
concreto dichiara `fasi_attive` e implementa `run()`; **non sovrascrive mai**
`process()`. Così un sistema non *può* dimenticare il gate né girare nella fase
sbagliata (il bug silenzioso che FNC §9 vuole escludere).

Tre bucket (FNC §6.2), realizzati come basi che fissano `fasi_attive`:
  - sempre-attivo   → entrambe le fasi (status del protagonista persistente);
  - solo-narrazione → solo `NARRAZIONE`;
  - solo-combattimento → solo `COMBATTIMENTO`.

L'ordine deterministico fra i bucket è dato dalla **priorità** in fase di
registrazione (run.py), non da qui (ESP §2: ordine dichiarato esplicitamente).
"""

from __future__ import annotations

import esper

from .fase import Fase, leggi_fase


class PhasedProcessor(esper.Processor):
    """Base con gate di fase. I concreti implementano `run()`, mai `process()`."""

    # Insieme delle fasi in cui il sistema è attivo. I concreti/le basi lo fissano.
    fasi_attive: frozenset[Fase] = frozenset()

    def process(self, dt: int = 1) -> None:
        """GATE: legge il singleton `FaseCorrente` e delega a `run()` SOLO se attivo.

        Questo è l'unico punto del progetto in cui si controlla la fase per gating.
        I sistemi concreti non lo toccano.
        """
        if leggi_fase() in self.fasi_attive:
            self.run(dt)

    def run(self, dt: int) -> None:
        """La logica del sistema. Da implementare nei concreti."""
        raise NotImplementedError


class SistemaSempreAttivo(PhasedProcessor):
    """Bucket sempre-attivo: gira in entrambe le fasi (tick degli status, FNC §6.2)."""

    fasi_attive = frozenset({Fase.NARRAZIONE, Fase.COMBATTIMENTO})


class SistemaSoloNarrazione(PhasedProcessor):
    """Bucket solo-narrazione: generazione stanze, parsing input narrativo, ecc."""

    fasi_attive = frozenset({Fase.NARRAZIONE})


class SistemaSoloCombattimento(PhasedProcessor):
    """Bucket solo-combattimento: turni, iniziativa, risoluzione, ecc."""

    fasi_attive = frozenset({Fase.COMBATTIMENTO})
