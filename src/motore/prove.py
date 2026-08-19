"""Prove di abilità in esplorazione (G §7; G-14, G-15).

Spaccatura di autorità: **l'AI inquadra e veste, il motore RISOLVE**. L'AI negozia
l'*inquadramento* (quale prova, come la si tenta), mai il *risultato*.

Flusso (G §7.1):
  1. l'AI propone la prova (narrazione, via la chiamata di sola prosa);
  2. l'intento del giocatore → evento tipizzato (`PlayerTentaProva`), non prosa risolta;
  3. il MOTORE **confronta a margine**: `margine = stat_eff − soglia_classe`;
  4. l'AI veste il risultato (risolvi prima, narra dopo).

**NESSUN TIRO — e l'assenza è il contratto.** Questo modulo non importa `random` e
`esito_prova` non accetta un RNG: non è una convenzione, è ciò che rende la regola
verificabile staticamente (`test_prove_margine.py`). Prima qui viveva un `d20`
segnaposto, che contraddiceva G §7.1 e per giunta teneva un numero di risoluzione
(`_FACCE_DADO`) fuori dal catalogo §11.

Perché deterministica: una prova che non si tira **non si ri-tira ricaricando** — è
il rinforzo meccanico della permadeath e del no-save-scum (G §6.1). Il brivido viene
da altrove: l'AI *inquadra* la classe senza mostrare la soglia, e i **gradi di
successo** danno la texture che il dado dava gratis.

Dove vive ancora la casualità (tassonomia a tre case, e questa non è una di quelle):
il **check 1** del combattimento (gate stocastico-ma-seeded), l'**anomalia**, e i
primitivi **opt-in** d'azzardo. Un "upset" su una prova, se lo si vorrà, è materia da
oggetto Fortuna-flavored — mai il percorso base.

Difficoltà = **classe nominata da enum chiuso** (`ClasseProva`), scelta PRIMA della
risoluzione e **immutabile dopo** (G-14). La soglia la calcola il motore
(`catalogo.soglia_classe`), mai l'AI. Le **ancore** testuali vivono nel catalogo, non
qui (G-15): il componente-prova porta SOLO l'etichetta di classe.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts import ClasseProva, GradoEsito

from .calibrazione import MARGINE_GRADO
from .catalogo import soglia_classe


@dataclass
class Prova:
    """Componente-prova: dato puro, serializzabile. Porta SOLO la classe scelta
    (etichetta dall'enum) e quale stat si impegna — **mai** le ancore (G-15).

    La `classe` è fissata all'inquadramento e non muta dopo (G-14): la risoluzione la
    legge, non la riscrive.
    """

    classe: ClasseProva
    stat: str = "destrezza"


@dataclass(frozen=True)
class EsitoProva:
    """L'esito calcolato: lo **scarto** e il grado che ne deriva.

    `riuscita` non è un campo ma una lettura di `margine`: due fonti di verità per la
    stessa cosa divergerebbero al primo refuso."""

    margine: int
    grado: GradoEsito

    @property
    def riuscita(self) -> bool:
        return self.margine >= 0


def grado_da_margine(margine: int) -> GradoEsito:
    """Fasce simmetriche attorno allo zero, ampiezza `MARGINE_GRADO` (§11).

    Nessuna tabella per-classe e nessun ramo per-classe: la difficoltà è già dentro il
    margine (l'ha sottratta la soglia), quindi il grado è funzione del solo scarto."""
    if margine >= MARGINE_GRADO:
        return GradoEsito.SUCCESSO_PIENO
    if margine >= 0:
        return GradoEsito.SUCCESSO
    if margine > -MARGINE_GRADO:
        return GradoEsito.FALLIMENTO
    return GradoEsito.FALLIMENTO_GRAVE


def margine_prova(valore_stat: int, classe: ClasseProva) -> int:
    """Lo scarto fra la stat effettiva impegnata e la soglia della classe (G §7.1).

    La **soglia la calcola il motore** da `classe` (`catalogo.soglia_classe`), mai
    l'AI (G-14). La classe entra già fissata: la funzione non la rinomina né
    l'abbassa — non c'è un percorso per mutarla dopo."""
    return valore_stat - soglia_classe(classe)


def esito_prova(valore_stat: int, classe: ClasseProva) -> EsitoProva:
    """Risolve la prova: `margine = stat − soglia(classe)`, più il grado di esito.

    **Deterministica**: nessun `rng` fra i parametri, per costruzione (G §7.1)."""
    margine = margine_prova(valore_stat, classe)
    return EsitoProva(margine=margine, grado=grado_da_margine(margine))


def prova_riuscita(valore_stat: int, classe: ClasseProva) -> bool:
    """Scorciatoia booleana per i chiamanti che non hanno bisogno del grado."""
    return esito_prova(valore_stat, classe).riuscita
