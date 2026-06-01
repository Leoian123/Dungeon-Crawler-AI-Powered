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
