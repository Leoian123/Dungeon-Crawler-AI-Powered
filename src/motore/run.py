"""Assemblaggio della run: bucket di Processor, ordine deterministico, tick, transizioni.

Phase-gate (FNC §6.1): tutti i Processor si registrano **una volta sola all'avvio**,
con ordine fissato dalla **priorità** (parte della spec, ESP §2). Niente remove/re-add
al confine di fase: l'ordine dei sistemi è stabile → determinismo stabile (FNC §9).

Ordine deterministico DICHIARATO (priorità più alta = chiamato per primo):

    PRIORITA_DRENAGGIO_INTENTI  (10000)  drena la coda PRIMA di tutto (IC §7.1)
    BANDA_SOLO_COMBATTIMENTO     (3000)  risoluzione del turno di combattimento
    BANDA_SOLO_NARRAZIONE        (2000)  risoluzione del turno di narrazione
    BANDA_SEMPRE_ATTIVO          (1000)  tick degli status del protagonista (per ultimo)

Entro lo stesso bucket l'ordine è quello di **registrazione** (esper ordina con sort
stabile: a parità di priorità l'ordine d'inserimento è preservato). Così "l'ordine
dei sistemi è parte della spec" è vero a entrambi i livelli: fra bucket (priorità) e
dentro il bucket (ordine di registrazione).
"""

from __future__ import annotations

from typing import Iterable

import esper

from contracts import BusEventi, CombatResolved, EncounterStarted

from .fase import Fase, crea_entita_fase, imposta_fase
from .intenti_coda import CodaIntenti, DrenaggioIntenti
from .phased import PhasedProcessor

# --- Ordine deterministico dei sistemi (parte della spec, FNC §9 / ESP §2) -----
PRIORITA_DRENAGGIO_INTENTI = 10_000
BANDA_SOLO_COMBATTIMENTO = 3_000
BANDA_SOLO_NARRAZIONE = 2_000
BANDA_SEMPRE_ATTIVO = 1_000

# Il `dt` è SIMBOLICO in un turn-based: un "tick di turno", non secondi di parete.
DT_TURNO = 1


def _verifica_bucket(processori: Iterable[PhasedProcessor], atteso: frozenset[Fase], etichetta: str) -> None:
    for p in processori:
        if not isinstance(p, PhasedProcessor):
            raise TypeError(f"bucket {etichetta}: {p!r} non è un PhasedProcessor")
        if p.fasi_attive != atteso:
            raise ValueError(
                f"bucket {etichetta}: {type(p).__name__}.fasi_attive={p.fasi_attive} "
                f"≠ {atteso} (sistema nel bucket sbagliato)"
            )


def avvia_run(
    *,
    sempre_attivi: Iterable[PhasedProcessor] = (),
    solo_narrazione: Iterable[PhasedProcessor] = (),
    solo_combattimento: Iterable[PhasedProcessor] = (),
    fase_iniziale: Fase = Fase.NARRAZIONE,
    crea_singleton_fase: bool = True,
) -> CodaIntenti:
    """Registra il singleton di fase, il drenaggio intenti e i tre bucket, nell'ordine
    deterministico dichiarato. Ritorna la `CodaIntenti` su cui i widget accodano.

    I sistemi vanno passati nel bucket giusto: `avvia_run` verifica che
    `fasi_attive` corrisponda, così un sistema non finisce nel bucket sbagliato.

    `crea_singleton_fase`: nel **caricamento** la `FaseCorrente` torna col save
    (deserializzata, E §6) — il guscio passa `False` per non crearne una seconda;
    nella **nuova partita** resta `True` e il singleton nasce qui.
    """
    sempre_attivi = tuple(sempre_attivi)
    solo_narrazione = tuple(solo_narrazione)
    solo_combattimento = tuple(solo_combattimento)

    _verifica_bucket(solo_combattimento, frozenset({Fase.COMBATTIMENTO}), "solo_combattimento")
    _verifica_bucket(solo_narrazione, frozenset({Fase.NARRAZIONE}), "solo_narrazione")
    _verifica_bucket(sempre_attivi, frozenset({Fase.NARRAZIONE, Fase.COMBATTIMENTO}), "sempre_attivi")

    if crea_singleton_fase:
        crea_entita_fase(fase_iniziale)

    coda = CodaIntenti()
    esper.add_processor(DrenaggioIntenti(coda), priority=PRIORITA_DRENAGGIO_INTENTI)

    for p in solo_combattimento:
        esper.add_processor(p, priority=BANDA_SOLO_COMBATTIMENTO)
    for p in solo_narrazione:
        esper.add_processor(p, priority=BANDA_SOLO_NARRAZIONE)
    for p in sempre_attivi:
        esper.add_processor(p, priority=BANDA_SEMPRE_ATTIVO)

    return coda


def tick(dt: int = DT_TURNO) -> None:
    """UN tick = UNA chiamata al giro dei sistemi, guidata dal turno (FNC §6.4).

    Va invocata **una volta per turno/azione risolta**, mai da un timer a frame. Il
    `dt` è simbolico. L'attesa async dell'LLM tiene viva la UI ma NON chiama `tick`.
    """
    esper.process(dt)


def collega_transizioni_fase(bus: BusEventi) -> list[tuple[type, object]]:
    """Le uniche transizioni di fase (FNC §4), via eventi tipizzati sul bus.

    `EncounterStarted` → `COMBATTIMENTO`; `CombatResolved` → `NARRAZIONE`. Sono
    **scritture** di `FaseCorrente`, non check di fase: la fase la flippano solo
    questi eventi, mai un `process()`.

    Ritorna le coppie `(tipo, handler)` registrate, così il guscio le **deregistra al
    teardown** della run (E-9): il bus è process-global e sopravvive ai run-World.
    """

    def _su_encounter(_evento: EncounterStarted) -> None:
        imposta_fase(Fase.COMBATTIMENTO)

    def _su_resolved(_evento: CombatResolved) -> None:
        imposta_fase(Fase.NARRAZIONE)

    coppie = [(EncounterStarted, _su_encounter), (CombatResolved, _su_resolved)]
    for tipo, handler in coppie:
        bus.registra(tipo, handler)
    return coppie
