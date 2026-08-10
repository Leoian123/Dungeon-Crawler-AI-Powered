"""Il compositore degli INCONTRI a sorpresa (Sit.5) — l'imboscata, cucita.

Il dado-evento del tempo (J §8) girava già a ogni tick di scorrimento, ma il
seam `componi_imboscata` non era collegato: l'imboscata usciva sempre a vuoto.
Qui vive il compositore che il motore passa a `passa_turno`/`fast_forward`:

  - il nemico è scelto DETERMINISTICAMENTE dal cast del piano corrente (o
    dall'archetipo di default del budget, senza design) con un RNG **isolato**
    `master_seed:imboscata:tick` — stesso seed e stesso tick → stesso agguato,
    e lo stream RNG di sessione NON si muove (replay-safe, famiglia F-13);
  - l'entità si materializza col profilo calibrato completo (stessa strada del
    reveal: `istanzia_entita`) e viene ARRUOLATA nel `PianoIncontro`;
  - `tempo._tick_scorrimento` pubblica lui `EncounterStarted` (l'unica via di
    transizione): qui si COMPONE soltanto, mai si cambia fase.

L'AI non c'entra: l'imboscata è un fatto del motore; semmai la veste dopo
(`prosa_apertura_scontro(imboscata=True)` e il resoconto, Fase 5).
"""

from __future__ import annotations

import random

import esper

from contracts import EntitaGenerata

from .catalogo import prepara_contesto, rango_grado
from .combattimento import PianoIncontro
from .design import design_piano_corrente
from .mob import EntitaMob
from .narrazione import istanzia_entita
from .piano import livello_corrente, tempo_piano_corrente
from .seme import master_seed


def _rng_imboscata(tick: int) -> random.Random:
    """Stream RNG DEDICATO all'imboscata di questo tick: non consuma né il seed
    stream di sessione né quello del dado-evento (`seed:tick`)."""
    return random.Random(f"{master_seed()}:imboscata:{tick}")


def componi_imboscata_scena() -> int:
    """Compone l'incontro dell'imboscata e ritorna l'entità-incontro.

    Con un design attivo pesca dal CAST del piano (il mob arriva con override e
    mosse propri, via `riferimento`); senza design ripiega sull'archetipo di
    default del budget al grado minimo ammesso. Nessuna chiamata, nessun gate:
    è il motore che compone contenuto già suo."""
    tick = tempo_piano_corrente()
    livello = livello_corrente()
    rng = _rng_imboscata(tick)

    piano = design_piano_corrente()
    # Col territorio l'agguato pesca dalla TABELLA DI SPAWN della zona corrente
    # (pesata per frequenza, stessa disciplina del copione); mai un boss.
    from .territorio import pesca_spawn

    dalla_tabella = pesca_spawn(rng)
    if dalla_tabella is not None:
        mob = dalla_tabella
        eg = EntitaGenerata(
            archetipo=mob.archetipo,
            grado=mob.grado,
            blocchi=[],
            nome=mob.nome,
            descrizione=mob.descrizione,
            riferimento=mob.slug,
        )
    elif piano is not None and piano.cast:
        mob = rng.choice(list(piano.cast))
        eg = EntitaGenerata(
            archetipo=mob.archetipo,
            grado=mob.grado,
            blocchi=[],
            nome=mob.nome,
            descrizione=mob.descrizione,
            riferimento=mob.slug,  # il mob del cast, con le sue mosse e override
        )
    else:
        budget = prepara_contesto(livello, rng)
        eg = EntitaGenerata(
            archetipo=budget.archetipo_default,
            grado=min(budget.gradi_ammessi, key=rango_grado),
            blocchi=[],
            nome="Sagoma nell'ombra",
            descrizione="Ti ha teso l'agguato mentre il tempo scorreva.",
        )
    ent = istanzia_entita(eg, livello)
    return esper.create_entity(
        PianoIncontro(nemici=[], seed=rng.randint(0, 2**31 - 1), arruolate=[ent])
    )


def nome_nemico_incontro(entita_incontro: int) -> str:
    """Il nome diegetico del nemico di un incontro composto (per l'host che deve
    aprire l'istanza su un `EncounterStarted` non suo — l'imboscata)."""
    pi = esper.try_component(entita_incontro, PianoIncontro)
    if pi is None:
        return ""
    for ent in pi.arruolate:
        em = esper.try_component(ent, EntitaMob)
        if em is not None:
            return em.nome
    return ""
