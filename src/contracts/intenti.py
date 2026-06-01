"""Intenti tipizzati del giocatore — DTO che attraversano la membrana vista → motore
(IC §2.3).

I widget emettono **intenti tipizzati**, mai keystroke grezzi (IC §2.2, vettore 4):
la vista traduce l'input grezzo in intento *prima* di metterlo sul bus. Cambi vista,
gli intenti restano.

L'intento non muta il `World`: entra nella coda lato motore e viene processato sul
turno del motore, nella fase corrente (IC §7.1). Qui vivono solo i *dati* dell'intento.

Dipendenze: solo stdlib (F-2).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Intento:
    """Marcatore comune degli intenti del giocatore. Nessun comportamento."""


@dataclass(frozen=True)
class PlayerChoseOption(Intento):
    """Il giocatore ha scelto la N-esima opzione del menu (IC §2.3, F §2).

    `opzione` è l'**indice** dell'`Opzione` scelta nella `TurnoNarrazione` corrente.
    L'AI propone opzioni tipizzate; il giocatore le trasforma in intento
    scegliendone una. Il motore lega l'indice all'azione nota (`TipoAzione`).
    """

    opzione: int


@dataclass(frozen=True)
class PlayerScappa(Intento):
    """Disimpegno in NARRAZIONE: il giocatore prova a sganciarsi *prima* di ingaggiare
    (FNC §5.3). È una **prova su stat** tirata dal motore (seeded); se riesce, il
    combattimento NON si apre. Da non confondere con la *fuga dal combattimento* a
    scontro iniziato (FNC §4): meccaniche diverse, intenti diversi.
    """


@dataclass(frozen=True)
class PlayerTentaProva(Intento):
    """Il giocatore tenta una prova di abilità proposta dall'AI (G §7.1).

    L'intento NON risolve: il motore TIRA seeded (`stat + soglia → esito`). La
    `classe` è già fissata (immutabile dopo) nel componente-prova; qui l'intento
    porta solo *quale* stat il giocatore impegna (set chiuso, MVP §7.6).
    """

    stat: str


@dataclass(frozen=True)
class PlayerDiscende(Intento):
    """Intento di discesa: il giocatore attiva una `DiscesaPiano` (G §8.1).

    Scendere è un **atto del giocatore**; l'incremento del livello (profondità) è una
    conseguenza posseduta dal MOTORE, scatenata da questo intento. La parola "scala"
    da sola non basta (G §8.3): serve l'atto sul primitivo strutturale.
    """
