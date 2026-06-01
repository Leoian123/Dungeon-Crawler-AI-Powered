"""Il modello delle statistiche: vettore `Primarie` + registry aperto + **un solo fold**
(Gruppo 2 §2/§3; GR2-1…6, GR2-8).

Principio guida: *la verità è il dato-base; tutto ciò che il gioco legge è derivato,
mai depositato.* Le primarie sono un **vettore posseduto** (`Primarie`, un solo
componente — mai un componente per stat). La stat **effettiva** non esiste come deposito:
`stat_eff` la calcola a ogni lettura combinando base + modificatori — **unico arbitro**,
una strada sola, niente da disallineare (IC §5). Nessuna cache: a turni, con pochissime
entità, il fold costa niente; la cache che va stale è il bug che il design combatte (§3.3).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum

import esper

from contracts import ClasseProva, StatId

from .modificatori import Modificatore, Modificatori, Origine, TipoMod


# --- Il vettore delle primarie: UN solo componente (GR2-1) --------------------

@dataclass
class Primarie:
    """Statistiche primarie di un'entità in **un solo** componente-vettore (§2.1).

    `valori` è *dato* (mappa `StatId → base`), non comportamento: `FORZA` è una **chiave**,
    non un tipo-di-componente. Scritto solo alla nascita o a un evento di progressione;
    letto uniformemente dal fold e dalla derivazione."""

    valori: dict[StatId, int]


# --- Il registry aperto dei tipi-stat (§2.2): primitivi chiusi, composizione aperta -

class Visibilita(str, Enum):
    """I tre assi della segretezza da DCC (§2.4)."""

    PALESE = "palese"                      # la proiezione mostra il valore
    VALORE_NASCOSTO = "valore_nascosto"    # esiste e si usa, ma il valore non si mostra
    ESISTENZA_NEGATA = "esistenza_negata"  # usata nei tiri, la proiezione la nega del tutto


class Modificabilita(str, Enum):
    """Chi può targettare la stat nel fold (§2.4)."""

    TUTTI = "tutti"
    SOLO_PRIVILEGIATI = "solo_privilegiati"


@dataclass(frozen=True)
class RigaStat:
    """Una riga del registry: i flag per stat (valori SEGNAPOSTO Gruppo 2).

    `derivazione: None` è uno stato legittimo (un primitivo in attesa di un sistema, §2.2),
    non un buco."""

    visibilita: Visibilita
    modificabile_da: Modificabilita
    derivazione: Callable[..., int] | None = None
    prova: ClasseProva | None = None
    sblocco: object | None = None


# `StatId → RigaStat`. Aggiungere una stat = una voce all'enum (in `contracts`) + una riga
# qui, senza toccare l'interfaccia AI né il fold (§2.2). Valori SEGNAPOSTO.
REGISTRY_STAT: dict[StatId, RigaStat] = {
    StatId.FORZA: RigaStat(Visibilita.PALESE, Modificabilita.TUTTI),
    StatId.DESTREZZA: RigaStat(Visibilita.PALESE, Modificabilita.TUTTI),
    StatId.COSTITUZIONE: RigaStat(Visibilita.PALESE, Modificabilita.TUTTI),
    # Saggezza: core ma non visualizzabile né modificabile direttamente (canone DCC).
    StatId.SAGGEZZA: RigaStat(Visibilita.VALORE_NASCOSTO, Modificabilita.SOLO_PRIVILEGIATI),
    # Fortuna: "ufficialmente non una stat reale" — usata nei tiri, negata alla proiezione.
    StatId.FORTUNA: RigaStat(Visibilita.ESISTENZA_NEGATA, Modificabilita.TUTTI),
}


# --- Ammissibilità di un modificatore: gate generico, mai un ramo per-stat (§2.4) -

def modificatore_ammesso(stat: StatId, mod: Modificatore) -> bool:
    """`SOLO_PRIVILEGIATI` accetta solo `origine == PRIVILEGIATA` (GR2-8).

    Legge due attributi-dato (`registry[stat].modificabile_da` e `mod.origine`) e non sa
    *quale* stat sia: resta `if` generico, non un ramo per-stat."""
    return (
        REGISTRY_STAT[stat].modificabile_da is Modificabilita.TUTTI
        or mod.origine is Origine.PRIVILEGIATA
    )


def modificatori_su(entita: int) -> Iterable[Modificatore]:
    """Le voci-modificatore attive sull'entità. **Tollera l'assenza** del componente
    `Modificatori` (entità con solo `Primarie`): ritorna vuoto, così `stat_eff` regge al
    primo mount (vedi `collega_combattimento`)."""
    cont = esper.try_component(entita, Modificatori)
    return cont.voci if cont is not None else ()


# --- La stat effettiva: UN solo fold, calcolato non depositato (GR2-3/4/5) ------

def stat_eff(entita: int, stat: StatId) -> int:
    """UNICO punto che combina base + modificatori (§3.2).

    `max(1, round((base + Σflat) × (1 + Σpct)))` — flat prima, pct dopo; pct **additivi**
    (`+10% e +20% → ×1.30`); **floor 1** sulle primarie. Gli unici rami sono *FLAT vs PCT*
    e i filtri bersaglio/ammissibilità: **nessun** `if stat == …` (parametrica su `stat`,
    GR2-4). Calcolata a ogni lettura, mai depositata (GR2-5).

    Order-independent (flat e pct additivi, somma commutativa → replay-safe, GR2-6): il
    `round()` finale assorbe le differenze d'accumulo float a queste magnitudini."""
    base = esper.component_for_entity(entita, Primarie).valori[stat]
    flat = 0.0
    pct = 0.0
    for mod in modificatori_su(entita):
        if mod.stat is not stat:                 # filtro per bersaglio = DATO, non ramo per-stat
            continue
        if not modificatore_ammesso(stat, mod):  # rispetta modificabile_da (§2.4)
            continue
        if mod.tipo is TipoMod.FLAT:
            flat += mod.valore
        else:
            pct += mod.valore
    return max(1, round((base + flat) * (1 + pct)))
