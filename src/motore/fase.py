"""Fase corrente della run come **componente-singleton nel World** (FNC §6.1).

La fase è **stato di gioco nel World**, non una variabile globale nascosta: vive in
un componente-singleton su un'entità dedicata, così si serializza naturalmente col
salvataggio (H). Solo gli eventi `EncounterStarted`/`CombatResolved` ne cambiano il
valore (FNC §4) — qui sta solo lo stato + i suoi accessori.

`FaseCorrente` è un **dato puro** (ESP §1): nessuna logica. La logica del gate vive
in `PhasedProcessor` (phased.py), che legge questo singleton via `leggi_fase()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import esper


class Fase(str, Enum):
    """Le due fasi-stato, mutuamente esclusive nel tempo (FNC §3)."""

    NARRAZIONE = "narrazione"
    COMBATTIMENTO = "combattimento"


@dataclass
class FaseCorrente:
    """Componente-singleton: la fase corrente. Dato puro, serializzabile col save.

    `Fase` è una `str`-Enum → si serializza come stringa (JSON-friendly) senza
    codifiche custom.
    """

    fase: Fase


def crea_entita_fase(fase: Fase = Fase.NARRAZIONE) -> int:
    """Crea l'entità che porta il singleton `FaseCorrente`. Una sola per World."""
    return esper.create_entity(FaseCorrente(fase))


def leggi_fase() -> Fase:
    """Legge la fase corrente dal singleton. È l'UNICA lettura-per-gate del progetto:
    la usa solo `PhasedProcessor` (phased.py). Nessun sistema la chiama a mano.
    """
    trovati = esper.get_component(FaseCorrente)
    if len(trovati) != 1:
        raise RuntimeError(
            f"FaseCorrente deve essere un singleton nel World: trovati {len(trovati)}"
        )
    return trovati[0][1].fase


def imposta_fase(fase: Fase) -> None:
    """Cambia la fase corrente (proprietà delle sole transizioni FNC §4).

    È una **scrittura**, non un check-di-fase: la chiamano i gestori di transizione
    sul bus (`EncounterStarted`/`CombatResolved`), mai i `process()` per decidere se
    girare.
    """
    trovati = esper.get_component(FaseCorrente)
    if len(trovati) != 1:
        raise RuntimeError(
            f"FaseCorrente deve essere un singleton nel World: trovati {len(trovati)}"
        )
    trovati[0][1].fase = fase
