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
from dataclasses import dataclass

from contracts import Blocco, ClasseProva, Durata, Grado

# I VALORI §11 vivono in `calibrazione.py` (un solo posto, guida §0); qui se ne **rieaspongono**
# i migrati per non rompere i consumatori storici (`from .catalogo import REGISTRY_ARCHETIPI`…).
from .calibrazione import (  # noqa: F401  (re-export)
    CARICO_TICK,
    DURATA_BLOCCO_DEFAULT,
    PRIMARIE_BASE_CARL,
    PROB_ANOMALIA,
    PROB_IMBOSCATA,
    REGISTRY_ARCHETIPI,
    SOGLIE_PROVA,
    ProfiloArchetipo,
)
from .status import (  # noqa: F401  (Valenza/Risoluzione: re-export di compatibilità)
    SPEC_STATUS,
    Risoluzione,
    Status,
    Valenza,
)

# --- Registry: nome → componente / profilo (F §3 faccia-motore, F-6) ----------

# Blocco → classe componente ECS, DERIVATO dalla tabella unica `SPEC_STATUS`
# (status.py): la chimera "veleno+stordito+rigenerazione" è una **somma di
# componenti** (FNC §5.5), e un Blocco nuovo si accende con una riga di tabella.
REGISTRY_BLOCCHI: dict[Blocco, type[Status]] = {
    s.blocco: s.componente for s in SPEC_STATUS if s.blocco is not None
}


# `ProfiloArchetipo`, `REGISTRY_ARCHETIPI` (binding F-6 + base §11) e `PRIMARIE_BASE_CARL`
# vivono ora in `calibrazione.py` (rieasposti sopra): editabili dalla console admin.


# --- Mappa `Grado → rango:int` (G §4.3; override Gruppo 2 §1.1) ----------------

# A senso unico: `Grado` (nome, AI-facing) → `rango:int` (1–6) che i sistemi confrontano.
# L'**anomalia** assegna `rango > 6` lato motore, mai un membro dell'enum. SEGNAPOSTO §11.
RANGO_GRADO: dict[Grado, int] = {grado: i for i, grado in enumerate(Grado, start=1)}


def rango_grado(grado: Grado) -> int:
    """Il `rango:int` (1–6) del `Grado`. Usato come rango di uno status applicato da
    un'entità composta dall'AI (G §4.3) e per la scelta deterministica del fallback."""
    return RANGO_GRADO[grado]


# --- Formula-madre: (archetipo, grado, livello) → primarie (FNC §5.5) ----------
# La formula vive in `calibrazione.primarie_da_archetipo` (mappa `REGISTRY_ARCHETIPI` → vettore
# `Primarie`, scalato per grado/profondità): UNA sola strada-stat, derivata via `stat_eff`
# (§16.4). `REGISTRY_ARCHETIPI` qui resta il **binding F-6** (ogni `Archetipo` ha un profilo) e
# la **base** che quella formula consuma.


# `DURATA_BLOCCO_DEFAULT` vive in `calibrazione.py` (riesposto sopra).


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
    gradi_ammessi: frozenset[Grado]
    blocchi_ammessi: frozenset[Blocco]
    archetipo_default: str
    anomala: bool = False
    # Vincolo del design di piano (stagione attiva): default = gli archetipi del
    # catalogo di calibrazione — i budget segnaposto e i chiamanti storici restano
    # invariati. (Slug, non enum: la chiusura è per-run, D1.)
    archetipi_ammessi: frozenset[str] = frozenset(REGISTRY_ARCHETIPI)


# `PROB_ANOMALIA` vive in `calibrazione.py` (riesposto sopra).

# Archetipo di default designato per il fallback (F §6.3): DETERMINISTICO, non pescato.
# (Scelta categoriale, non un numero §11 → resta qui.)
ARCHETIPO_DEFAULT = "slime"


def _budget_normale(livello: int) -> Budget:
    """Budget ordinario per profondità (SEGNAPOSTO Gruppo 2)."""
    gradi = {Grado.BRONZO, Grado.ARGENTO}
    blocchi = {Blocco.VELENO, Blocco.RIGENERAZIONE}
    return Budget(
        livello=livello,
        gradi_ammessi=frozenset(gradi),
        blocchi_ammessi=frozenset(blocchi),
        archetipo_default=ARCHETIPO_DEFAULT,
        anomala=False,
    )


def _budget_anomalo(livello: int) -> Budget:
    """Budget gonfiato dell'anomalia (da tabella, con soffitto — SEGNAPOSTO Gruppo 2).

    Anche il delirio ha un soffitto (FNC §5.5): non valori a caso, un set più largo.
    """
    from .design import registry_archetipi_correnti  # locale: evita il ciclo design↔catalogo

    return Budget(
        livello=livello,
        gradi_ammessi=frozenset(Grado),         # incl. LEGGENDARIO/CELESTIALE
        blocchi_ammessi=frozenset(Blocco),      # tutti i blocchi
        # L'anomalia apre TUTTO il vocabolario della run (storici + asset congelati).
        archetipi_ammessi=frozenset(registry_archetipi_correnti()),
        archetipo_default=ARCHETIPO_DEFAULT,
        anomala=True,
    )


def prepara_contesto(livello: int, rng: random.Random, *, piano=None) -> Budget:
    """Tira l'**anomalia SEEDED** e calcola il budget + set ammissibile (FNC §5.1/§5.5).

    Chi decide di sforare è il **motore**, non l'AI: con bassa probabilità il tiro
    sostituisce il budget normale con uno gonfiato. È RNG del motore (seeded,
    riproducibile in debug — FNC §9), non nondeterminismo dell'LLM.

    `piano` è il design del piano corrente (`design.PianoAttivo`, duck-typed per
    non accoppiare il catalogo al modulo design): se presente, il budget ORDINARIO
    viene dai suoi set (gradi/blocchi/archetipi ammessi) — è il vincolo hard del
    contenuto autorato. L'ANOMALIA non è cappata dal design: resta il tiro del
    dungeon coi set interi (anche il delirio è del motore, non dell'autore).
    Senza piano (save legacy, harness, banco): il segnaposto storico, invariato.
    """
    if rng.random() < PROB_ANOMALIA:
        return _budget_anomalo(livello)
    if piano is None:
        return _budget_normale(livello)
    return Budget(
        livello=livello,
        gradi_ammessi=frozenset(piano.gradi),
        blocchi_ammessi=frozenset(piano.blocchi),
        archetipi_ammessi=frozenset(piano.archetipi),
        # Deterministico e in-budget per costruzione (il lint impone archetipi ≥1).
        archetipo_default=piano.archetipi[0],
        anomala=False,
    )


# --- Classi di prova: soglia (motore) + ancore (catalogo) (G §7.2/§7.4) --------

# `classe → soglia` (la "formula" della prova) vive in `calibrazione.SOGLIE_PROVA` (§11).

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
    return SOGLIE_PROVA[classe]


def ancore_classe(classe: ClasseProva) -> tuple[str, ...]:
    """Le ancore testuali di una classe (per il costruttore del prompt, G §7.4)."""
    return ANCORE_CLASSE[classe]


# --- Mappa `Durata → carico-tick` + gate (J §3.2/§3.3, §3.5; F-14, J-1/J-3) ----
# La `Durata` è solo vocabolario in `contracts`; QUI vive la sua traduzione in tick
# (`calibrazione.CARICO_TICK`, §11): monotòna non-decrescente rispetto a `Durata.ordine`
# (`TURNO` = minimo = cadenza base, §3.1).


def carico_tick(durata: Durata) -> int:
    """Quanti tick di cadenza comprime una `Durata` (formula del motore, J §3.2)."""
    return CARICO_TICK[durata]


def gate_durata(durata: Durata) -> int:
    """Gate `durata → carico-tick`, MAI `durata → tick diretto` (J §3.5, J-3).

    Nell'MVP è **identità** (ci si fida dell'enum chiuso, nessun tetto): più tick = più
    esposizione, non meno → niente exploit senza cap (§3.5). Il punto d'innesto esiste
    per il clamp della fase di crollo (§11), post-1.0. È QUI che passa ogni durata: i
    meccanismi di scorrimento chiamano `gate_durata`, non `carico_tick` diretto.
    """
    return carico_tick(durata)


# --- Asse safe/unsafe degli status: flag di TIPO (J §7, J-9) -------------------
# `Valenza`/`Risoluzione` vivono in status.py con la tabella unica `SPEC_STATUS`
# (un solo proprietario del dato-status); qui il catalogo li ri-espone e DERIVA la
# mappa storica dei flag — di sola lettura, non tocca lo stacking.
FLAG_STATUS: dict[type[Status], tuple[Valenza, Risoluzione]] = {
    s.componente: (s.valenza, s.risoluzione) for s in SPEC_STATUS
}


def tipi_status_noti() -> frozenset[type[Status]]:
    """I tipi-status con flag noti nel catalogo."""
    return frozenset(FLAG_STATUS)


def valenza_di(tipo_status: type[Status]) -> Valenza:
    return FLAG_STATUS[tipo_status][0]


def risoluzione_di(tipo_status: type[Status]) -> Risoluzione:
    return FLAG_STATUS[tipo_status][1]


def e_unsafe(tipo_status: type[Status]) -> bool:
    """Vero se lo status è `AI`-risolto (unsafe): blocca anche il passa-turno (§6/§7)."""
    return risoluzione_di(tipo_status) is Risoluzione.AI


def e_dannoso(tipo_status: type[Status]) -> bool:
    """Vero se lo status è `DANNOSO`: blocca il downtime (§5/§7)."""
    return valenza_di(tipo_status) is Valenza.DANNOSO


# --- Dado-evento: probabilità d'imboscata per tick di scorrimento (J §8) -------
# `PROB_IMBOSCATA` vive in `calibrazione.py` (riesposto sopra): la *forma* (un tiro seeded
# a ogni tick) è del motore; il *valore* è §11.
