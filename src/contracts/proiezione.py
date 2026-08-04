"""Proiezione di sola lettura della scheda del protagonista (G §6.6, G-13).

L'AI deve *leggere* lo stato del protagonista per narrarlo ("Carl barcolla, ferito"),
ma non deve mai vedere l'oggetto-scheda **vivo** (i componenti ECS): le farebbe vedere
numeri che potrebbe pretendere di spiegare — e domani negoziare — e legherebbe il
prompt alla shape interna dei componenti (rompendo la membrana `contracts`).

Quindi l'AI riceve un **DTO derivato**: descrittori diegetici (`"ferito"`,
`"avvelenato"`), MAI `hp: 7/30`. È *dato*, non comportamento (IC §2.2): nessun numero,
nessun riferimento al `World` né a entità esper vive. Il motore lo **costruisce** dallo
stato vivo (in `motore`); qui vive solo la **forma**.

È "risolvi prima, narra dopo" applicato allo stato persistente: l'AI narra una *vista*,
non legge il *registro* (G §11).

Dipendenze: solo stdlib + Pydantic (F-2).
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict


class SchedaProiezione(BaseModel):
    """Vista di sola lettura della scheda: descrittori diegetici + stat filtrate per
    visibilità (Gruppo 2 §2.4, GR2-9).

    `frozen=True` la rende immutabile (sola lettura davvero); `extra="forbid"` chiude
    la porta a campi introdotti di soppiatto. *Quali* descrittori e *quanto ricca* è la
    proiezione sono contenuto (Gruppo 2); il **fatto** che esista, e che il filtro di
    visibilità sia già applicato a monte, è forma (G §6.6).

    ⚠️ **Membrana (C-3): è solo forma-dato.** Il filtro per `Visibilita` legge il
    registry del MOTORE (`statistiche.REGISTRY_STAT`): il costruttore vive **lato
    motore** (`narrazione.proietta_scheda`) e passa qui mappe **già filtrate**. Questo
    modulo non importa esper né il registry. La proiezione esprime gli esiti del filtro:
      - `primarie` — solo le `PALESE`: `nome → valore effettivo`;
      - `primarie_occulte` — i nomi delle `VALORE_NASCOSTO` (presenza sì, valore no);
      - le `ESISTENZA_NEGATA` non compaiono in nessuno dei due (GR2-9).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    descrittori: tuple[str, ...] = ()
    primarie: Mapping[str, int] = {}
    primarie_occulte: tuple[str, ...] = ()


class SchedaVista(BaseModel):
    """Scheda del protagonista per la **UI del giocatore** (non per l'AI).

    A differenza di `SchedaProiezione`, qui i numeri PALESI sono ammessi: il
    giocatore vede i propri HP e le proprie stat — è l'AI che non deve vederli
    (G §6.6). Le regole di visibilità restano quelle del registry, applicate a
    monte dal motore: `primarie` = solo PALESI (valori effettivi), le
    VALORE_NASCOSTO compaiono per nome in `primarie_occulte`, le
    ESISTENZA_NEGATA (fortuna) non compaiono MAI (GR2-9).
    Il costruttore vive lato composition root (`SessioneGioco.scheda()`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    uuid: str
    nome: str
    vivo: bool
    hp: int
    hp_max: int
    descrittori: tuple[str, ...] = ()
    primarie: Mapping[str, int] = {}
    primarie_occulte: tuple[str, ...] = ()
    derivate: Mapping[str, int] = {}
    livello: int = 1
    tick_piano: int = 0
