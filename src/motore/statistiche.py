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
    non un buco. `finalizza` è la **chiave** (in `FINALIZZA`) della finalizzazione per-stat
    (floor/round/scala): è un **dato della riga**, non un ramo nel fold (GR2-4)."""

    visibilita: Visibilita
    modificabile_da: Modificabilita
    derivazione: Callable[..., int] | None = None
    prova: ClasseProva | None = None
    sblocco: object | None = None
    finalizza: str = "primaria"


# Finalizzazione per-stat = DATO tabellare, non un ramo per-stat nel fold (GR2-4/§3.1).
# L'accumulo (loop) è condiviso e uniforme; la finalizzazione (floor/round/scala) si legge
# dalla riga di registry e si applica in coda. Interi fixed-point (DT-4): `round()` → int.
FINALIZZA: dict[str, Callable[[float], int]] = {
    # primarie: floor 1, in UNITÀ intere (nessuna primaria tocca mai 0, §3.1).
    "primaria": lambda x: max(1, round(x)),
    # DIFESA: floor 0, in CENTESIMI interi (il nudo non ha armatura, def_eff = 0 è
    # legittimo); niente round-a-unità — resta in centesimi, il danno converte /100 (§6).
    "centesimi_floor0": lambda x: max(0, round(x)),
}


# `StatId → RigaStat`. Aggiungere una stat = una voce all'enum (in `contracts`) + una riga
# qui, senza toccare l'interfaccia AI né il fold (§2.2). Valori SEGNAPOSTO.
REGISTRY_STAT: dict[StatId, RigaStat] = {
    StatId.FORZA: RigaStat(Visibilita.PALESE, Modificabilita.TUTTI),
    StatId.DESTREZZA: RigaStat(Visibilita.PALESE, Modificabilita.TUTTI),
    StatId.COSTITUZIONE: RigaStat(Visibilita.PALESE, Modificabilita.TUTTI),
    # Intelligenza: accuratezza magica (Gruppo 2 §5.4), primaria a tutti gli effetti.
    StatId.INTELLIGENZA: RigaStat(Visibilita.PALESE, Modificabilita.TUTTI),
    # Difesa: StatId base 0 (§5.3) — il canale-modificatori dell'armatura. Finalizza in
    # CENTESIMI, floor 0 (non è una primaria): EVASIONE invece NON è una StatId (§4.1).
    StatId.DIFESA: RigaStat(Visibilita.PALESE, Modificabilita.TUTTI, finalizza="centesimi_floor0"),
    # Saggezza: core ma non visualizzabile né modificabile direttamente (canone DCC).
    StatId.SAGGEZZA: RigaStat(Visibilita.VALORE_NASCOSTO, Modificabilita.SOLO_PRIVILEGIATI),
    # Fortuna: "ufficialmente non una stat reale" — usata nei tiri, negata alla proiezione.
    StatId.FORTUNA: RigaStat(Visibilita.ESISTENZA_NEGATA, Modificabilita.TUTTI),
    # Carisma: la stat sociale del parlamentare (2026-08-16). Palese e
    # modificabile da tutti — il corredo potrà portarla come porta le altre.
    StatId.CARISMA: RigaStat(Visibilita.PALESE, Modificabilita.TUTTI),
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
    """UNICO punto che combina base + modificatori (§3.2). Context-free `(entità, stat)`
    (DT-4): il `tipo` di un attacco non entra MAI qui.

    `finalizza[stat]((base + Σflat) × (1 + Σpct))` — flat prima, pct dopo; pct **additivi**
    (`+10% e +20% → ×1.30`). L'**accumulo** (il loop) è uniforme; la **finalizzazione**
    (floor/round/scala) è un **dato della riga di registry** (`finalizza[stat]`: primarie →
    `max(1, round(·))` in unità; `DIFESA` → `max(0, ·)` in centesimi), **non** un ramo
    per-stat (parametrica su `stat`, GR2-4). Calcolata a ogni lettura, mai depositata (GR2-5).

    **Base assente = 0** (`.get(stat, 0)`): per `DIFESA` (base 0, di norma assente dal
    vettore di chi non porta armatura) il fold parte da 0 e la finalizzazione `floor 0`
    rende `def_eff = 0` legittimo — generico, nessun special-case per stat.

    Order-independent (flat e pct additivi, somma commutativa → replay-safe, GR2-6): il
    `round()` finale assorbe le differenze d'accumulo float a queste magnitudini."""
    base = esper.component_for_entity(entita, Primarie).valori.get(stat, 0)
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
    grezzo = (base + flat) * (1 + pct)
    return FINALIZZA[REGISTRY_STAT[stat].finalizza](grezzo)
