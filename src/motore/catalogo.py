"""Faccia-motore del catalogo: registry, formula, budget, ranghi, classi di prova
(F §3 faccia-motore; FNC §5.5; G §4.3, §7.2/§7.4, §8.1, §10).

`contracts` porta i **nomi** (enum chiusi); QUI vive il **significato** — il binding
`nome → componente ECS` (registry) e la formula `(archetipo, rarità, livello) →
statistiche`. Importano esper e la matematica del gioco → non possono stare in
`contracts` (F §3).

Invariante di sincronia (F-6): **ogni** membro di enum del catalogo-contratto ha una
voce qui. Un nome legale nello schema ma senza binding sarebbe un valore che il gate
accetta e il motore non sa istanziare — un buco silenzioso. È verificabile staticamente.

I **valori** (numeri della formula, voci di budget, probabilità/soffitto delle
anomalie, soglie e ancore delle classi) sono **Gruppo 2**: qui SEGNAPOSTO, in forma
completa (G §13.1). Il punto di G è "la forma ora, i numeri dopo".
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from contracts import Archetipo, Blocco, ClasseProva, Rarita

from .status import Rigenerazione, Status, Stordito, Veleno

# --- Registry: nome → componente / profilo (F §3 faccia-motore, F-6) ----------

# Blocco → classe componente ECS. La chimera "veleno+stordito+rigenerazione" è una
# **somma di componenti** (FNC §5.5): ogni `Blocco` ha qui la sua realizzazione.
REGISTRY_BLOCCHI: dict[Blocco, type[Status]] = {
    Blocco.VELENO: Veleno,
    Blocco.RIGENERAZIONE: Rigenerazione,
    Blocco.STORDITO: Stordito,
}


@dataclass(frozen=True)
class ProfiloArchetipo:
    """Profilo-base di un archetipo (SEGNAPOSTO Gruppo 2). La formula lo scala."""

    destrezza_base: int
    pv_base: int
    danno_base: int


# Archetipo → profilo-base. Ogni archetipo del contratto ha un binding (F-6).
REGISTRY_ARCHETIPI: dict[Archetipo, ProfiloArchetipo] = {
    Archetipo.SLIME: ProfiloArchetipo(destrezza_base=3, pv_base=6, danno_base=1),
    Archetipo.SCHELETRO: ProfiloArchetipo(destrezza_base=5, pv_base=8, danno_base=2),
    Archetipo.GOBLIN: ProfiloArchetipo(destrezza_base=7, pv_base=5, danno_base=2),
}


# --- Ordine totale sulle rarità + mappa rango(rarità) → int (G §4.3) -----------

# Ordine di dichiarazione dell'enum = ordine totale. La mappa è SEGNAPOSTO Gruppo 2;
# l'**esistenza** dell'ordine totale e della mappa è forma (G §4.3).
_RANGHI: dict[Rarita, int] = {r: i for i, r in enumerate(Rarita)}


def rango_rarita(rarita: Rarita) -> int:
    """Rango intero di una rarità (più alto = più rara). Usato come rango di uno
    status applicato da un'entità composta dall'AI (G §4.3)."""
    return _RANGHI[rarita]


# --- Formula-madre: (archetipo, rarità, livello) → statistiche (FNC §5.5) ------

@dataclass(frozen=True)
class Statistiche:
    """Statistiche DERIVATE dal motore (mai emesse dall'AI). SEGNAPOSTO Gruppo 2."""

    destrezza: int
    punti_vita: int
    danno: int


def deriva_statistiche(archetipo: Archetipo, rarita: Rarita, livello: int) -> Statistiche:
    """La formula-madre (SEGNAPOSTO Gruppo 2): quanto picchia un mob è funzione di
    rarità e livello, NON una scelta dell'AI (FNC §5.5).

    Forma: profilo-base scalato da un fattore-rarità e dalla profondità del piano.
    I *numeri* sono placeholder; la *struttura* (deriva, non legge dall'AI) è completa.
    """
    profilo = REGISTRY_ARCHETIPI[archetipo]
    fattore = (rango_rarita(rarita) + 1) * max(1, livello)
    return Statistiche(
        destrezza=profilo.destrezza_base + rango_rarita(rarita),
        punti_vita=profilo.pv_base * fattore,
        danno=profilo.danno_base * fattore,
    )


# Durata di default di uno status-blocco materializzato (SEGNAPOSTO Gruppo 2).
DURATA_BLOCCO_DEFAULT = 3


# --- Budget: set ammissibile per contesto, + anomalia seeded (FNC §5.5) --------

@dataclass(frozen=True)
class Budget:
    """Il set ammissibile per un contesto: ciò entro cui l'AI pesca (soft, nel
    prompt) e ciò che il gate impone (hard, strato 3). Include l'**archetipo di
    default designato** per il fallback (F §6.3) e la profondità (`livello`) come
    contesto (F §4.2).

    `anomala` segnala un budget gonfiato dal motore (tiro seeded): per schema e gate
    è *solo un budget diverso* — nessun campo, nessun ramo speciale (F §4.3).
    """

    livello: int
    rarita_ammesse: frozenset[Rarita]
    blocchi_ammessi: frozenset[Blocco]
    archetipo_default: Archetipo
    anomala: bool = False


# Probabilità dell'anomalia (SEGNAPOSTO Gruppo 2): basso, "l'ingiustizia assurda" rara.
PROB_ANOMALIA = 0.05

# Archetipo di default designato per il fallback (F §6.3): DETERMINISTICO, non pescato.
ARCHETIPO_DEFAULT = Archetipo.SLIME


def _budget_normale(livello: int) -> Budget:
    """Budget ordinario per profondità (SEGNAPOSTO Gruppo 2)."""
    rarita = {Rarita.COMUNE, Rarita.RARO}
    blocchi = {Blocco.VELENO, Blocco.RIGENERAZIONE}
    return Budget(
        livello=livello,
        rarita_ammesse=frozenset(rarita),
        blocchi_ammessi=frozenset(blocchi),
        archetipo_default=ARCHETIPO_DEFAULT,
        anomala=False,
    )


def _budget_anomalo(livello: int) -> Budget:
    """Budget gonfiato dell'anomalia (da tabella, con soffitto — SEGNAPOSTO Gruppo 2).

    Anche il delirio ha un soffitto (FNC §5.5): non valori a caso, un set più largo.
    """
    return Budget(
        livello=livello,
        rarita_ammesse=frozenset(Rarita),       # incl. LEGGENDARIO
        blocchi_ammessi=frozenset(Blocco),      # tutti i blocchi
        archetipo_default=ARCHETIPO_DEFAULT,
        anomala=True,
    )


def prepara_contesto(livello: int, rng: random.Random) -> Budget:
    """Tira l'**anomalia SEEDED** e calcola il budget + set ammissibile (FNC §5.1/§5.5).

    Chi decide di sforare è il **motore**, non l'AI: con bassa probabilità il tiro
    sostituisce il budget normale con uno gonfiato. È RNG del motore (seeded,
    riproducibile in debug — FNC §9), non nondeterminismo dell'LLM.
    """
    if rng.random() < PROB_ANOMALIA:
        return _budget_anomalo(livello)
    return _budget_normale(livello)


# --- Classi di prova: soglia (motore) + ancore (catalogo) (G §7.2/§7.4) --------

# `classe → soglia` (la "formula" della prova): del MOTORE (G §7.2). SEGNAPOSTO Gruppo 2.
_SOGLIE: dict[ClasseProva, int] = {
    ClasseProva.BRONZO: 8,
    ClasseProva.ARGENTO: 12,
    ClasseProva.ORO: 16,
    ClasseProva.CELESTIALE: 22,
}

# Ancore testuali delle classi: **materiale di calibrazione del prompt**, vivono nel
# catalogo, MAI nel componente-prova (G §7.4, G-15). SEGNAPOSTO Gruppo 2.
ANCORE_CLASSE: dict[ClasseProva, tuple[str, ...]] = {
    ClasseProva.BRONZO: ("scappare da una blatta mannara",),
    ClasseProva.ARGENTO: ("disinnescare una trappola rumorosa",),
    ClasseProva.ORO: ("convincere una guardia veterana",),
    ClasseProva.CELESTIALE: ("sedurre un dio",),
}


def soglia_classe(classe: ClasseProva) -> int:
    """La soglia di una classe — calcolata dal MOTORE, mai fissata dall'AI (G-14)."""
    return _SOGLIE[classe]


def ancore_classe(classe: ClasseProva) -> tuple[str, ...]:
    """Le ancore testuali di una classe (per il costruttore del prompt, G §7.4)."""
    return ANCORE_CLASSE[classe]
