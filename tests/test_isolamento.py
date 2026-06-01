"""Dimostra che lo stato esper NON trapela tra un test e l'altro (ESP §0.1).

I due test usano lo STESSO contesto (`mondo_condiviso`, nome fisso): è il caso
peggiore, dove un mancato isolamento si manifesterebbe. Ognuno verifica che il
mondo parta VUOTO, poi ci scrive dentro. Eseguiti in sequenza, passano entrambi
solo perché il teardown elimina il mondo e lo switch del test successivo lo ricrea
azzerato. Se l'isolamento si rompesse, il secondo a girare vedrebbe le entità del
primo e fallirebbe l'assert di mondo vuoto.

L'ordine di esecuzione non è garantito da pytest, ma la simmetria dei due test
rende la dimostrazione valida in qualsiasi ordine.
"""

from __future__ import annotations

from dataclasses import dataclass

import esper


@dataclass
class Segnalino:
    valore: int


def _conta_segnalini() -> int:
    return len(esper.get_component(Segnalino))


def test_isolamento_primo(mondo_condiviso: str) -> None:
    # Il mondo deve partire vuoto: nessuna entità ereditata.
    assert _conta_segnalini() == 0
    esper.create_entity(Segnalino(1))
    esper.create_entity(Segnalino(2))
    assert _conta_segnalini() == 2


def test_isolamento_secondo(mondo_condiviso: str) -> None:
    # Se lo stato del test precedente fosse trapelato, qui vedremmo 2 segnalini.
    assert _conta_segnalini() == 0
    esper.create_entity(Segnalino(99))
    assert _conta_segnalini() == 1
