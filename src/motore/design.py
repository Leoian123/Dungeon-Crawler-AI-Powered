"""La Stagione ATTIVA della run: l'aggregato di contenuto congelato nel World.

Alla creazione della run, la stagione scelta viene RISOLTA (riferimenti
sciolti, lint superato — vive in `main`, il composition root) e congelata qui
come singleton ECS: da quel momento il runtime non tocca mai la libreria, e
le modifiche di authoring non raggiungono le run in corso. Il componente è
registrato nel tag registry (H): viaggia nel save come `SemeRun`/`TempoPiano`.

Il "piano corrente" NON è un secondo singleton: è una DERIVAZIONE —
`design_piano_corrente()` = `stagione.piani[livello_corrente() - 1]` — una
sola fonte di verità; la discesa cambia solo l'indice (MVP: un piano, la
discesa è vittoria; il modello regge già gli N piani del canone).

Giro delle dipendenze (a senso unico): Stagione→Piano→Mob (dato) → Budget
(vincolo runtime, `catalogo.prepara_contesto`) → gate/prompt; il cast →
copione offline; il registry archetipi (F-6) ← lint.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import esper

from contracts import Archetipo, Blocco, Durata, Grado


@dataclass(frozen=True)
class MobAttivo:
    """Un membro del cast, congelato (specchio dataclass del MobAsset)."""

    slug: str
    nome: str
    archetipo: Archetipo
    grado: Grado
    blocchi: list[Blocco]
    descrizione: str
    prosa_stanza: str
    durata: Durata
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PianoAttivo:
    """Un piano della stagione, congelato: tema/voce + budget hard + cast."""

    slug: str
    titolo: str
    tema: str
    stile: list[str]
    lore: str
    gradi: list[Grado]
    blocchi: list[Blocco]
    archetipi: list[Archetipo]
    cast: list[MobAttivo]
    stanze: int | None = None  # scala esplicita; None = derivata (offline: len(cast))
    tags: list[str] = field(default_factory=list)

    @property
    def n_stanze(self) -> int:
        return self.stanze if self.stanze is not None else len(self.cast)


@dataclass(frozen=True)
class StagioneAttiva:
    """L'edizione dello show congelata nella run (singleton, persistente)."""

    slug: str
    versione: int
    numero: int
    titolo: str
    tagline: str
    mondo: str
    stile: list[str]
    lore: str
    piani: list[PianoAttivo]
    tags: list[str] = field(default_factory=list)


def crea_stagione(stagione: StagioneAttiva) -> int:
    """Congela la stagione nel World corrente (al confine guscio→run, E-5)."""
    return esper.create_entity(stagione)


def stagione_corrente() -> StagioneAttiva | None:
    """Il singleton, LASCO: `None` = save legacy o harness senza stagione —
    il motore degrada ai segnaposto (budget hardcoded, prefisso base)."""
    trovate = esper.get_component(StagioneAttiva)
    return trovate[0][1] if trovate else None


def design_piano_corrente() -> PianoAttivo | None:
    """Il piano della profondità corrente — DERIVAZIONE, mai un secondo stato.

    Livello oltre l'ultimo piano descritto → ultimo piano (lasco: la stagione
    può descrivere meno piani di quanti il motore ne farà scendere)."""
    stagione = stagione_corrente()
    if stagione is None or not stagione.piani:
        return None
    from .piano import livello_corrente

    indice = min(livello_corrente(), len(stagione.piani)) - 1
    return stagione.piani[indice]


def lint_registry(archetipi, blocchi) -> list[str]:
    """Check F-6: ogni categoria usata dal contenuto ha un binding nei registry
    del motore. Oggi enum e registry coincidono (test F-6): è la cintura di
    sicurezza che rende l'invariante un errore di authoring, mai un crash."""
    from .calibrazione import REGISTRY_ARCHETIPI
    from .catalogo import REGISTRY_BLOCCHI

    errori: list[str] = []
    for archetipo in archetipi:
        if archetipo not in REGISTRY_ARCHETIPI:
            errori.append(f"archetipo senza profilo di calibrazione: {archetipo.value}")
    for blocco in blocchi:
        if blocco not in REGISTRY_BLOCCHI:
            errori.append(f"blocco senza binding nel registry: {blocco.value}")
    return errori
