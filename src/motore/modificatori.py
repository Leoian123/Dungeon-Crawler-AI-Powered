"""Modificatori di statistica: una forma, lifecycle diversi (Gruppo 2 §4).

Un **modificatore** è un dato puro `{stat, tipo, valore, fonte, origine}`: positivo o
negativo è solo il **segno** di `valore` (zero casi speciali buff/debuff). La `fonte` è
**obbligatoria** ed è un **tag di dominio stabile** — l'id di dominio di un oggetto, il
tag del tipo-status, l'uuid del crawler — **mai** l'`id` di entità esper (sequenziale,
riciclato al teardown) né un riferimento vivo (GR2-16, onora G-3/G-6/G-12). La rimozione
è "togli i modificatori dove `fonte == X`", non un'operazione inversa (§4.1).

`origine` alimenta il gate del fold per le stat `SOLO_PRIVILEGIATI` (§2.4): è
un'**etichetta di provenienza** impostata dal sistema che conia il modificatore (codice
fidato), non un controllo di sicurezza.

Tutti i modificatori di un'entità vivono in **un** componente `Modificatori` (lista di
`voci`): fonti diverse coesistono e sommano (§4.2). Il fold (`statistiche.stat_eff`) le
legge genericamente; questo modulo non importa `statistiche` (dipendenza a senso unico).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import esper

from contracts import StatId, TipoDanno


class TipoMod(str, Enum):
    """Le due categorie generiche del fold (§3.1): additivo piatto vs percentuale."""

    FLAT = "flat"
    PCT = "pct"


class Origine(str, Enum):
    """Provenienza del modificatore — alimenta il gate `SOLO_PRIVILEGIATI` (§2.4).

    Etichetta di *da dove viene*, non una guardia di permesso: equip/status →
    `NORMALE`; un sistema designato ("zona speciale") → `PRIVILEGIATA`.
    """

    NORMALE = "normale"
    PRIVILEGIATA = "privilegiata"


@dataclass
class Modificatore:
    """Dato puro: targetta una `stat`, additivo per `tipo`, etichettato da `fonte`.

    `fonte` = tag di dominio stabile, confrontato **per valore** alla rimozione (GR2-16).
    `valore` è float (i pct sono frazioni: `0.1` = +10%); i flat interi restano interi.
    """

    stat: StatId
    tipo: TipoMod
    valore: float
    fonte: str
    origine: Origine = Origine.NORMALE


@dataclass
class Modificatori:
    """Componente-contenitore: tutte le voci attive su un'entità (§4.2)."""

    voci: list[Modificatore] = field(default_factory=list)


# --- Helper di applicazione / rimozione (la rimozione NON si gestisce, §4.1) ----

def applica_modificatore(entita: int, mod: Modificatore) -> None:
    """Aggiunge una voce, creando il componente `Modificatori` se assente.

    Fonti diverse sulla stessa stat **coesistono e sommano**: nessuna competizione qui
    (quella è regola interna agli status dello stesso tipo, non ai modificatori)."""
    cont = esper.try_component(entita, Modificatori)
    if cont is None:
        esper.add_component(entita, Modificatori(voci=[mod]))
    else:
        cont.voci.append(mod)


def rimuovi_per_fonte(entita: int, fonte: str) -> None:
    """Toglie **tutte** le voci con quella `fonte` — niente operazione inversa (§4.1).

    La prossima `stat_eff` ricalcola da capo: mettere e togliere sono entrambi banali e
    identici per FLAT/PCT e per segno (GR2-7)."""
    cont = esper.try_component(entita, Modificatori)
    if cont is None:
        return
    cont.voci = [m for m in cont.voci if m.fonte != fonte]


# --- Resistenza tipata: un canale a sé, fuori dal fold (layer tipi, DT-3) -------
# **Riusa** la disciplina dato-puro di §4, ma è chiavettata su un `TipoDanno` (non uno
# `StatId`) e vive in un componente-resistenza letto **solo dal risolutore del check 2**,
# **mai** dal fold `stat_eff` (che resta context-free, DT-4). Multi-fonte e **additiva**
# (PCT additivi, somma commutativa → replay-safe); rimozione **per `fonte`**.

@dataclass
class ResistenzaMod:
    """Mitigazione/vulnerabilità condizionata a un `TipoDanno` (DT-3). Dato puro, stessa
    disciplina del `Modificatore` (§4): `valore < 0` = resistenza (riduce), `valore > 0` =
    vulnerabilità (aumenta); `fonte` = tag di dominio stabile (mai id esper né ref vivo). È
    **PCT** per costruzione (moltiplicativa, §5), distinta dal FLAT di `DIFESA` (il tank)."""

    contro: TipoDanno
    valore: float
    fonte: str
    tipo_mod: TipoMod = TipoMod.PCT
    origine: Origine = Origine.NORMALE


@dataclass
class Resistenze:
    """Componente-contenitore delle resistenze tipate di un'entità. Letto **solo** dal
    risolutore del danno (mai da `stat_eff`): un fascio di `ResistenzaMod`, filtrato per
    `contro == tipo` al momento del colpo."""

    voci: list[ResistenzaMod] = field(default_factory=list)


def applica_resistenza(entita: int, res: ResistenzaMod) -> None:
    """Aggiunge una resistenza, creando il componente `Resistenze` se assente. Più fonti
    sulla stessa coppia (entità, tipo) **coesistono e sommano** (come i modificatori, §4.2)."""
    cont = esper.try_component(entita, Resistenze)
    if cont is None:
        esper.add_component(entita, Resistenze(voci=[res]))
    else:
        cont.voci.append(res)


def rimuovi_resistenza_per_fonte(entita: int, fonte: str) -> None:
    """Toglie le resistenze con quella `fonte` — niente `÷` inverso (come §4.1)."""
    cont = esper.try_component(entita, Resistenze)
    if cont is None:
        return
    cont.voci = [r for r in cont.voci if r.fonte != fonte]
