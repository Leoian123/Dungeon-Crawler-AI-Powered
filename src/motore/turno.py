"""Segnale "di chi è il turno" — il seam della cadenza per-entità (G §4.4, G-24).

In combattimento uno status avanza **al confine del turno dell'entità che lo porta**
(una volta per round per entità), non a ogni `process()` globale. Per ottenerlo senza
accoppiare il tick degli status al combattimento, il sistema-turno marca **quale
entità si sta attivando** in questo giro; i sistemi-status (bucket sempre-attivo)
ticcano **solo** gli status di quell'entità.

`TurnoAttivo` è un componente-singleton transitorio (non serializzato: vive solo
durante lo scontro). Lo imposta il sistema-turno (un solo proprietario); lo leggono
i sistemi-status. Fuori da un turno d'entità non c'è segnale → nessun tick (la
cadenza in esplorazione, per-stanza, è di J: hook futuro).
"""

from __future__ import annotations

from dataclasses import dataclass

import esper


@dataclass
class TurnoAttivo:
    """Singleton: l'entità che si sta attivando in questo giro (id di runtime).

    L'id di entità esper qui è un **puntatore transitorio** entro un singolo giro,
    non un'identità persistita né una chiave di tiebreak (quelle non usano mai l'id
    esper — G-3/§6.3).
    """

    entita: int


def segna_turno_attivo(entita: int) -> None:
    trovati = esper.get_component(TurnoAttivo)
    if trovati:
        trovati[0][1].entita = entita
    else:
        esper.create_entity(TurnoAttivo(entita))


def entita_attiva() -> int | None:
    trovati = esper.get_component(TurnoAttivo)
    return trovati[0][1].entita if trovati else None


def azzera_turno_attivo() -> None:
    for ent, _ in list(esper.get_component(TurnoAttivo)):
        esper.delete_entity(ent, immediate=True)
