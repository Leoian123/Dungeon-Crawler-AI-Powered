"""Livello = profondità del piano + `DiscesaPiano` + completabilità (G §8; G-16, G-18).

Il **livello è la profondità del piano**: un contatore discreto, dato di stato del
MOTORE (singleton nel World, serializzato col save come `FaseCorrente`), che parte da
`1` e avanza **solo** per un atto fisico — attivare una `DiscesaPiano` per intento del
giocatore. Nessun altro evento lo incrementa (G-16). L'AI non lo tocca (G §8.1).

`DiscesaPiano` (primitivo strutturale) ≠ "scala" (arredo narrativo, G §8.3): la
differenza non sta nella fiction, sta nel **tipo**. Il primitivo è piazzato dal **gate
di contenuto**, non evocato dalla prosa.

Completabilità (liveness dell'esplorazione, G §8.4/G-18): ogni piano generato contiene
**almeno una `DiscesaPiano` raggiungibile** dallo stato iniziale. Il gate rifiuta o
ripara un piano senza uscita — non lo lascia passare.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import esper

from contracts import DiscesaPiano, PlayerDiscende, TipoStanza

from .intenti_coda import consuma_messaggi
from .phased import SistemaSoloNarrazione

# Il livello parte da 1 (il primo piano).
LIVELLO_INIZIALE = 1


@dataclass
class ProfonditaPiano:
    """Singleton di stato: la profondità corrente. Dato puro, serializzabile."""

    livello: int = LIVELLO_INIZIALE


@dataclass
class TempoPiano:
    """Slot del **contatore di tempo-piano** (H §14, H-18): è stato del World,
    serializzato come campo, ma la **semantica** è di J (modello del tempo).

    H lo serializza senza presupporre J — nessuna logica temporale qui: un intero
    forward-compatible che J riempirà di significato (cadenza, fast-forward, crollo
    del piano post-1.0). Dato puro.
    """

    tick: int = 0


def crea_profondita(livello: int = LIVELLO_INIZIALE) -> int:
    """Crea il singleton `ProfonditaPiano`. Una sola per run-World."""
    return esper.create_entity(ProfonditaPiano(livello))


def crea_tempo_piano(tick: int = 0) -> int:
    """Crea il singleton `TempoPiano` (slot di J). Una sola per run-World."""
    return esper.create_entity(TempoPiano(tick))


def tempo_piano_corrente() -> int:
    """Legge il contatore di tempo-piano (J §10). È stato del World serializzato in H;
    J ne possiede la semantica (avanza in entrambe le fasi, nessun cap in 1.0)."""
    trovati = esper.get_component(TempoPiano)
    if len(trovati) != 1:
        raise RuntimeError(f"TempoPiano deve essere un singleton: trovati {len(trovati)}")
    return trovati[0][1].tick


def _singleton() -> ProfonditaPiano:
    trovati = esper.get_component(ProfonditaPiano)
    if len(trovati) != 1:
        raise RuntimeError(
            f"ProfonditaPiano deve essere un singleton: trovati {len(trovati)}"
        )
    return trovati[0][1]


def livello_corrente() -> int:
    """Legge la profondità corrente. È il valore che il budget d'incontro usa come
    contesto (F §4.2)."""
    return _singleton().livello


def attiva_discesa(bus) -> int:
    """Avanza la profondità di 1 e pubblica `DiscesaPiano` (G §8.1).

    È l'**unico** percorso che incrementa il livello: lo scatena l'intento di discesa
    del giocatore (`PlayerDiscende`), il motore ne possiede la conseguenza. Ritorna il
    nuovo livello.
    """
    prof = _singleton()
    prof.livello += 1
    bus.pubblica(DiscesaPiano(piano=prof.livello))
    return prof.livello


class SistemaDiscesa(SistemaSoloNarrazione):
    """Consuma `PlayerDiscende` (solo in NARRAZIONE) e attiva la discesa (G §8.1).

    L'incremento del livello è una **conseguenza posseduta dal motore**, scatenata
    dall'intento del giocatore — non da un altro evento (G-16). Consuma via
    `consuma_messaggi` (Canale A): SOLO il proprio tipo, gli altri intenti restano.

    **Gate spaziale (G §8.1/§8.3):** con una `Mappa` attiva si scende SOLO se la
    stanza corrente contiene una scala (il primitivo strutturale) — la parola "scala"
    nella prosa non concede nulla. Un intento senza scala è consumato senza effetto.
    Senza mappa (harness legacy) la discesa resta libera.
    """

    def __init__(self, bus) -> None:
        self.bus = bus

    def run(self, dt: int) -> None:
        from .mappa import discesa_consentita  # import locale: evita il ciclo piano↔mappa

        for _intento in consuma_messaggi(PlayerDiscende):
            if discesa_consentita():
                attiva_discesa(self.bus)


# --- Topologia del piano + gate di completabilità (G §8.4, G-18) --------------

@dataclass
class Piano:
    """Topologia generata di un piano: stanze (adiacenza non orientata), partenza, e
    l'insieme delle stanze che contengono una `DiscesaPiano` (il primitivo strutturale).

    `discese` è un *insieme di id-stanza*, piazzato dal gate di contenuto — NON dedotto
    dalla parola "scala" (G §8.3).

    `tipi` è il TIPO di ogni stanza (`TipoStanza`, vocabolario chiuso): stampato dal
    generatore (seeded, a vincoli — mai dall'AI), persistito con la mappa. Una stanza
    assente dal dict è NORMALE — così i save scritti prima dei tipi migrano gratis.
    """

    partenza: int
    adiacenze: dict[int, list[int]]
    discese: set[int] = field(default_factory=set)
    tipi: dict[int, "TipoStanza"] = field(default_factory=dict)


def raggiungibili(piano: Piano) -> set[int]:
    """BFS dalla stanza di partenza: le stanze raggiungibili dallo stato iniziale."""
    visti: set[int] = {piano.partenza}
    coda: deque[int] = deque([piano.partenza])
    while coda:
        stanza = coda.popleft()
        for vicina in piano.adiacenze.get(stanza, ()):
            if vicina not in visti:
                visti.add(vicina)
                coda.append(vicina)
    return visti


def piano_completabile(piano: Piano) -> bool:
    """Vero se esiste almeno una `DiscesaPiano` raggiungibile dalla partenza (G-18)."""
    racc = raggiungibili(piano)
    return any(stanza in racc for stanza in piano.discese)


def valida_piano(piano: Piano, *, ripara: bool = True) -> Piano | None:
    """Gate di contenuto sulla topologia (G §8.4, G-18).

    - completabile → passa invariato;
    - non completabile e `ripara=True` → **ripara**: piazza una `DiscesaPiano` in una
      stanza raggiungibile (scelta deterministica: l'id raggiungibile massimo), così la
      run non resta invincibile;
    - non completabile e `ripara=False` → **rifiuta** (`None`).

    Un piano senza uscita non viene mai lasciato passare.
    """
    if piano_completabile(piano):
        return piano
    if not ripara:
        return None
    racc = raggiungibili(piano)
    stanza = max(racc)  # deterministico: nessun RNG, replay-safe
    return Piano(
        partenza=piano.partenza,
        adiacenze=piano.adiacenze,
        discese=set(piano.discese) | {stanza},
        tipi=dict(piano.tipi),
    )
