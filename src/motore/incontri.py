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


def _nome_mob_di_stanza() -> str:
    """Il nome del mob che presidia (o presidierà) la stanza CORRENTE: vivo in
    scena se già rivelato, altrimenti la derivazione del copione
    (`mob_di_stanza` — l'agguato all'ingresso arriva PRIMA del reveal).
    Lettura tollerante: harness senza mappa/territorio → "" (nessuna
    esclusione), mai un crash."""
    try:
        from .mappa import mappa_corrente, mob_corrente
        from .mob import EntitaMob

        ent = mob_corrente()
        if ent is not None:
            em = esper.try_component(ent, EntitaMob)
            if em is not None and em.nome:
                return em.nome
        from .territorio import mob_di_stanza, zona_corrente

        m = mappa_corrente()
        zona = zona_corrente()
        if m is None or zona is None:
            return ""
        atteso = mob_di_stanza(
            livello_corrente(), zona, m[1].stanza_corrente
        )
        return atteso.nome if atteso is not None else ""
    except Exception:
        return ""


def componi_imboscata_scena(escludi_nome: str = "") -> int:
    """Compone l'incontro dell'imboscata e ritorna l'entità-incontro.

    Con un design attivo pesca dal CAST del piano (il mob arriva con override e
    mosse propri, via `riferimento`); senza design ripiega sull'archetipo di
    default del budget al grado minimo ammesso. Nessuna chiamata, nessun gate:
    è il motore che compone contenuto già suo.

    `escludi_nome` (playtest 2026-08-12, anti déjà-vu): il nemico APPENA ucciso
    non riappare nell'imboscata immediatamente successiva — UNA ri-pescata
    seeded (se anche la seconda lo ripesca, resta lui: tabella piccola, è il
    dungeon a essere monotono, non il dado).

    La TREGUA del parlamentato (playtest giro 3, 2026-08-16): chi ha ASCOLTATO
    il crawler (gate del parlamento superato, mob vivo) non lo imbosca — i suoi
    omonimi ESCONO dalla tabella e dal cast prima della pescata. La tregua è
    un filtro duro, non una ri-pescata di cortesia: mai il déjà-vu del
    personaggio che ti parla e un tick dopo ti salta addosso. L'imboscata in
    sé resta (la zona non fa tregua): a candidati esauriti piomba la sagoma
    di budget."""
    tick = tempo_piano_corrente()
    livello = livello_corrente()
    rng = _rng_imboscata(tick)

    # I nomi in tregua: letti dal World (fatti del motore), zero RNG.
    from .scena import nomi_in_tregua

    tregua = nomi_in_tregua()

    # I nomi da NON ripescare: il nemico appena ucciso (playtest 2026-08-12) e
    # il mob che PRESIDIA la stanza corrente (screenshot 2026-08-26: l'agguato
    # all'ingresso pescava lo stesso Fante della stanza — il GM diceva «non si
    # rialza» e il menu rioffriva Combatti con lo stesso nome, un morto
    # apparentemente risorto). Stessa disciplina: UNA ri-pescata seeded.
    esclusi = {n for n in (escludi_nome, _nome_mob_di_stanza()) if n}

    piano = design_piano_corrente()
    # Col territorio l'agguato pesca dalla TABELLA DI SPAWN della zona corrente
    # (pesata per frequenza, stessa disciplina del copione); mai un boss.
    from .territorio import pesca_spawn

    dalla_tabella = pesca_spawn(rng, escludi=tregua)
    if dalla_tabella is not None and dalla_tabella.nome in esclusi:
        # UNA ri-pescata, stesso stream, con l'esclusione DURA (la disciplina
        # della tregua): a tabella monovoce ritorna None e resta il pescato —
        # è il dungeon a essere monotono, non il dado.
        ripescato = pesca_spawn(rng, escludi=frozenset(tregua) | frozenset(esclusi))
        dalla_tabella = ripescato or dalla_tabella
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
    elif piano is not None and any(m.nome not in tregua for m in piano.cast):
        candidati = [m for m in piano.cast if m.nome not in tregua]
        # Stessa esclusione sul ramo-cast (grazioso: a candidati esauriti
        # resta la lista piena — il dungeon monotono, non un crash).
        filtrati = [m for m in candidati if m.nome not in esclusi]
        mob = rng.choice(filtrati or candidati)
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


def entita_mob_incontro(entita_incontro: int) -> EntitaMob | None:
    """Il componente `EntitaMob` del nemico di un incontro composto (`None` se
    assente) — la generalizzazione di `nome_nemico_incontro`: l'apertura dello
    scontro vuole anche descrizione/aspetto/tratto."""
    pi = esper.try_component(entita_incontro, PianoIncontro)
    if pi is None:
        return None
    for ent in pi.arruolate:
        em = esper.try_component(ent, EntitaMob)
        if em is not None:
            return em
    return None


def nome_nemico_incontro(entita_incontro: int) -> str:
    """Il nome diegetico del nemico di un incontro composto (per l'host che deve
    aprire l'istanza su un `EncounterStarted` non suo — l'imboscata)."""
    em = entita_mob_incontro(entita_incontro)
    return em.nome if em is not None else ""
