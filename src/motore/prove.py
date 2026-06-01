"""Prove di abilità in esplorazione (G §7; G-14, G-15).

Spaccatura di autorità: **l'AI inquadra e veste, il motore TIRA** (seeded). L'AI
negozia l'*inquadramento* (quale prova, come la si tenta), mai il *risultato*.

Flusso (G §7.1):
  1. l'AI propone la prova (narrazione, via la chiamata di sola prosa);
  2. l'intento del giocatore → evento tipizzato (`PlayerTentaProva`), non prosa risolta;
  3. il MOTORE tira, seeded e deterministico: `stat + soglia → successo/fallimento`;
  4. l'AI veste il risultato (risolvi prima, narra dopo).

Difficoltà = **classe nominata da enum chiuso** (`ClasseProva`), scelta PRIMA del tiro
e **immutabile dopo** (G-14). La soglia la calcola il motore (`catalogo.soglia_classe`),
mai l'AI. Le **ancore** testuali delle classi vivono nel catalogo, non qui (G-15): il
componente-prova porta SOLO l'etichetta di classe.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from contracts import ClasseProva

from .catalogo import soglia_classe

# Dado della prova (SEGNAPOSTO Gruppo 2): la struttura `stat + tiro ≥ soglia` è forma.
_FACCE_DADO = 20


@dataclass
class Prova:
    """Componente-prova: dato puro, serializzabile. Porta SOLO la classe scelta
    (etichetta dall'enum) e quale stat si impegna — **mai** le ancore (G-15).

    La `classe` è fissata all'inquadramento e non muta dopo (G-14): la risoluzione la
    legge, non la riscrive.
    """

    classe: ClasseProva
    stat: str = "destrezza"


def risolvi_prova(valore_stat: int, classe: ClasseProva, rng: random.Random) -> bool:
    """Tira la prova: `stat + dado ≥ soglia(classe)`. Deterministico e SEEDED (G §7.3).

    La **soglia la calcola il motore** da `classe` (`catalogo.soglia_classe`), mai
    l'AI (G-14). La classe entra come argomento già fissato: la funzione non la
    rinomina né l'abbassa — non c'è un percorso per mutarla dopo il tiro.
    """
    soglia = soglia_classe(classe)
    tiro = rng.randint(1, _FACCE_DADO)
    return valore_stat + tiro >= soglia
