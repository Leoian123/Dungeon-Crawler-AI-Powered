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


# --- Tassonomia per dominio (IC §7.1): gli intenti viaggiano su UNA coda con UN solo
# travaso (Canale A), ma il CONSUMO resta separato per dominio: quelli di esplorazione
# vengono serviti dai sistemi solo-narrazione, quelli di combattimento nella fase di
# combattimento. Un intento accodato nella fase "sbagliata" resta in attesa (il
# phase-gate strutturale è la separazione), mai consumato dal dominio sbagliato.

@dataclass(frozen=True)
class IntentoEsplorazione(Intento):
    """Base degli intenti di ESPLORAZIONE (fase NARRAZIONE): discesa, prove, disimpegno.
    Consumati SOLO da sistemi solo-narrazione (o dal turno di narrazione del port)."""


@dataclass(frozen=True)
class IntentoCombattimento(Intento):
    """Base degli intenti di COMBATTIMENTO (fase COMBATTIMENTO): es. la fuga a scontro
    iniziato (FNC §4, post-MVP). Oggi il combattimento è guidato dal menu
    (`PlayerChoseOption`); la base dichiara il canale, separato dall'esplorazione."""


@dataclass(frozen=True)
class PlayerChoseOption(Intento):
    """Il giocatore ha scelto la N-esima opzione del menu (IC §2.3, F §2).

    `opzione` è l'**indice** dell'`Opzione` scelta nella `TurnoNarrazione` corrente.
    L'AI propone opzioni tipizzate; il giocatore le trasforma in intento
    scegliendone una. Il motore lega l'indice all'azione nota (`TipoAzione`).
    È un intento **di menu**: valido in entrambe le fasi, lo interpreta il port
    (`SessioneGioco`) nella fase corrente — per questo non appartiene né alla base
    esplorazione né a quella combattimento.
    """

    opzione: int


@dataclass(frozen=True)
class PlayerScappa(IntentoEsplorazione):
    """Disimpegno in NARRAZIONE: il giocatore prova a sganciarsi *prima* di ingaggiare
    (FNC §5.3). È una **prova su stat** tirata dal motore (seeded); se riesce, il
    combattimento NON si apre. Da non confondere con la *fuga dal combattimento* a
    scontro iniziato (FNC §4): meccaniche diverse, intenti diversi.
    """


@dataclass(frozen=True)
class PlayerTentaProva(IntentoEsplorazione):
    """Il giocatore tenta una prova di abilità proposta dall'AI (G §7.1).

    L'intento NON risolve: il motore TIRA seeded (`stat + soglia → esito`). La
    `classe` è già fissata (immutabile dopo) nel componente-prova; qui l'intento
    porta solo *quale* stat il giocatore impegna (set chiuso, MVP §7.6).
    """

    stat: str


@dataclass(frozen=True)
class PlayerSiMuove(IntentoEsplorazione):
    """Il giocatore si sposta nella stanza `stanza` (adiacente sulla mappa).

    Lo spostamento è un atto del giocatore; la **validità** (adiacenza, nessun nemico
    che ingaggia) la decide il motore sulla mappa — un intento non valido viene
    consumato senza effetto (l'AI/la vista non possono teletrasportare).
    """

    stanza: int


@dataclass(frozen=True)
class PlayerDiscende(IntentoEsplorazione):
    """Intento di discesa: il giocatore attiva una `DiscesaPiano` (G §8.1).

    Scendere è un **atto del giocatore**; l'incremento del livello (profondità) è una
    conseguenza posseduta dal MOTORE, scatenata da questo intento. La parola "scala"
    da sola non basta (G §8.3): serve l'atto sul primitivo strutturale.
    """
