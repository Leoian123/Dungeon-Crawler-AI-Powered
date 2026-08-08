"""⛔ **QUESTO NON È IL TIRO DEL COMBATTIMENTO.**

Il combattimento di questo gioco risolve con **due check** e nessuno dei due è qui:
  - **check 1** — il *se* colpisci: gate stocastico-ma-seeded a banda, **una** estrazione
    per colpo, esito a tre vie (pieno / graze / schivata);
  - **check 2** — il *quanto*: **deterministico**, zero estrazioni.

Quanto segue è **casualità opt-in**: esiste *solo* se un oggetto o una magia la dichiara,
ed è roba da build sulla **Fortuna**. Non è il default, non è un fallback, non è "il modo
normale di tirare i danni".

---

### Se stai leggendo questo file per la prima volta

Un sistema di combattimento con `DannoVariabile(min, max)` somiglia moltissimo al
`1d8+STR` dei JRPG e dei GDR da tavolo, e la tentazione naturale è concludere che *questo*
sia il motore del danno e che il resto sia decorazione. **È il contrario.** Il danno base
del gioco è `max(1, round(m·(atk_eff − def_eff/100)·mult))` e non pesca nulla; qui dentro
c'è un primitivo che pochi contenuti dichiarano di volere.

Da dove viene questa scelta (Gr2 §5.2): il dado doveva vivere **solo** dentro «un oggetto
che gioca d'azzardo nel suo component, o una magia che vuole un output incerto». La
tassonomia della casualità in questo motore ha **tre case** e nessuna è "il tiro normale":
  1. il **gate** del check 1 (avoidance, per costruzione stocastica);
  2. l'**anomalia** (il Sistema che impazzisce, fuori dal risolutore);
  3. **questo** — l'opt-in dichiarato.

### Come è reso impossibile confonderle

Non con un commento — con la struttura, perché i commenti si leggono in diagonale:
  - **modulo separato**: un primitivo d'azzardo accanto a `Danno` *sembra* un suo
    fratello. Qui non lo è;
  - **dipendenza a senso unico**: `azzardo` importa `azione`, **mai** il contrario.
    L'atomo base non può raggiungere l'azzardo nemmeno per sbaglio;
  - **consenso esplicito**: il risolutore salta ogni `EffettoAzzardo` che non porti un
    consenso dichiarato. Pescare "per default" non è un bug possibile, è un percorso
    che non esiste;
  - **cinque test** in `tests/test_azzardo_optin.py`, statici, che diventano rossi se
    l'azzardo entra nel repertorio di default o se il risolutore pesca fuori dal check 1.

Tutto ciò che si pesca qui esce dallo **stesso stream seeded** del combattimento: il
replay resta intatto (FNC §9).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from contracts import StatId

from .azione import Effetto
from .calibrazione import FORTUNA_PER_PUNTO, FORTUNA_TETTO_BONUS
from .statistiche import stat_eff


@dataclass
class EffettoAzzardo(Effetto):
    """Marcatore comune dei primitivi che **pescano**. Base astratta, nessun campo.

    È l'**unico** predicato su cui si appoggia tutto il resto (`isinstance(e,
    EffettoAzzardo)`): mai un elenco di nomi, che invecchierebbe al primo primitivo
    nuovo e lascerebbe passare l'azzardo dalla porta di servizio."""


@dataclass
class DannoVariabile(EffettoAzzardo):
    """Danno pescato in `[minimo, massimo]` — *la magia dall'esito incerto*.

    Deliberatamente **non** deriva da `atk_eff`: non è "l'attacco, ma casuale", è un
    effetto che sostituisce la magnitudine con una pescata. Chi lo confondesse col danno
    base avrebbe due sistemi di danno concorrenti — che è precisamente ciò che questo
    modulo esiste per impedire."""

    minimo: int
    massimo: int
    tipo: object = None          # `TipoDanno`; None → GENERICO (nessuna resistenza matcha)


@dataclass
class EsitoAzzardo:
    """Una faccia della tabella d'azzardo: etichetta diegetica + `danno`.

    **Segno = chi lo incassa.** Positivo → il bersaglio; **negativo → chi ha tirato**.
    È questo che rende la tabella un *azzardo* invece di un bonus travestito: il rischio
    è tuo. Zero = la faccia che non fa niente, e serve — una scommessa senza esiti nulli
    è solo un moltiplicatore con più passaggi."""

    etichetta: str
    danno: int


@dataclass
class TiroAzzardo(EffettoAzzardo):
    """Pesca una faccia da una tabella di esiti — *l'oggetto che gioca d'azzardo*.

    Il bias della **Fortuna** entra qui e in nessun altro posto del motore: è la stat che
    il canone DCC dichiara «ufficialmente non una stat reale» e che piega loot, eventi e
    momenti fortunati. Finora era inerte; questo è il suo primo consumatore.

    Il bias sposta la pescata verso le facce migliori, **non** garantisce nulla: una
    Fortuna alta non toglie il rischio, lo inclina."""

    esiti: tuple[EsitoAzzardo, ...]


def bonus_fortuna(entita: int) -> float:
    """Quanto la Fortuna inclina una pescata d'azzardo, in `[0, FORTUNA_TETTO_BONUS]`.

    Cappato di proposito: senza tetto, una build Fortuna trasformerebbe l'azzardo in una
    rendita — e un azzardo che paga sempre non è un azzardo, è un moltiplicatore."""
    fortuna = stat_eff(entita, StatId.FORTUNA)
    return min(FORTUNA_TETTO_BONUS, fortuna * FORTUNA_PER_PUNTO)


def risolvi_danno_variabile(effetto: DannoVariabile, sorgente: int, rng) -> int:
    """Pesca il danno. **Una** estrazione, dallo stream seeded del combattimento."""
    minimo, massimo = min(effetto.minimo, effetto.massimo), max(effetto.minimo, effetto.massimo)
    u = rng.random()
    inclinato = min(1.0, u + bonus_fortuna(sorgente))
    return max(1, minimo + round(inclinato * (massimo - minimo)))


def risolvi_tiro_azzardo(effetto: TiroAzzardo, sorgente: int, rng) -> EsitoAzzardo:
    """Pesca una faccia. **Una** estrazione; la Fortuna inclina verso il fondo della
    tabella, quindi le facce vanno ordinate **dalla peggiore alla migliore**."""
    if not effetto.esiti:
        raise ValueError("TiroAzzardo senza esiti: una tabella vuota non è una scommessa")
    u = rng.random()
    inclinato = min(0.999999, u + bonus_fortuna(sorgente))
    return effetto.esiti[int(inclinato * len(effetto.esiti))]


def risolvi_effetto_azzardo(effetto: EffettoAzzardo, sorgente: int, rng) -> int:
    """Il punto d'ingresso unico per il risolutore: `effetto → danno`.

    **Segno = chi lo incassa**: positivo il bersaglio, negativo chi ha tirato. Una sola
    funzione, così il combattimento ha **una** branch e non un ramo per primitivo — e
    quando arriverà un terzo primitivo d'azzardo il risolutore non si accorgerà di nulla.

    Pesca **esattamente una volta**, dallo stream seeded del combattimento."""
    if isinstance(effetto, DannoVariabile):
        return risolvi_danno_variabile(effetto, sorgente, rng)
    if isinstance(effetto, TiroAzzardo):
        return risolvi_tiro_azzardo(effetto, sorgente, rng).danno
    raise TypeError(f"primitivo d'azzardo senza risoluzione: {type(effetto).__name__}")
