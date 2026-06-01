"""Eventi di dominio — DTO che attraversano la membrana motore → vista (IC §2.3).

Sono **dati semplici** (IC §2.2): solo `str`/`int`/`bool` e enum chiusi. Niente
renderable di Rich, niente widget Textual, niente riferimenti al `World` né entità
esper vive. Un `int` qui è un **identificatore opaco** di entità (l'id intero di
esper è un dato, non un oggetto vivo), non un puntatore allo stato.

Viaggiano sul bus tipizzato (`bus.py`) come Canale B di ESP §5: transitori, push,
con molti ascoltatori scorrelati (showrunner, log, adattatore di presentazione).

Dipendenze: solo stdlib (F-2).
"""

from __future__ import annotations

from dataclasses import dataclass

# Id opaco di un'entità di gioco. È un dato (int), NON un'entità esper viva: il
# `World` non attraversa mai la membrana (IC §2.2).
Entita = int


@dataclass(frozen=True)
class EventoDominio:
    """Marcatore comune degli eventi di dominio. Nessun comportamento."""


@dataclass(frozen=True)
class EncounterStarted(EventoDominio):
    """Un incontro è stato composto e innescato (confine narrazione→combattimento).

    La `TurnoNarrazione` che lo emette è clampata a `durata == TURNO` dal gate del
    motore (F §2, C3): F vincola il dato, il gate lo impone — non questo evento.
    """

    entita: Entita


@dataclass(frozen=True)
class CombatResolved(EventoDominio):
    """Il combattimento si è risolto. L'esito è già arbitrato dal motore (FNC §5.2).

    *Risolvi prima, narra dopo*: l'evento porta un fatto d'esito già deciso, non una
    richiesta di decisione.
    """

    entita: Entita
    vittoria: bool


@dataclass(frozen=True)
class MortePersonaggio(EventoDominio):
    """Terminale di run: permadeath (death-check seeded del motore), non sconfitta.

    È l'evento terminale della run; la `causa` è flavor diegetico, non un numero.
    """

    causa: str


@dataclass(frozen=True)
class AnomalyTriggered(EventoDominio):
    """Reveal di un'anomalia: il motore l'ha tirata (seeded) e la pubblica perché lo
    showrunner la narri (F §4.3, FNC §5.5, §8).

    L'anomalia è un **tiro del motore**, mai un campo dello schema: l'AI la narra,
    non la invoca. Qui è solo il segnale che è avvenuta.
    """

    entita: Entita


@dataclass(frozen=True)
class DiscesaPiano(EventoDominio):
    """Discesa al piano successivo: l'unico evento che fa avanzare il `livello`
    (profondità del piano, posseduta dal motore — F §4.2, G §8.1).

    `piano` è stato del motore (un `int`), non output dell'AI: non viola F-3, che
    vincola solo `EntitaGenerata`.
    """

    piano: int
