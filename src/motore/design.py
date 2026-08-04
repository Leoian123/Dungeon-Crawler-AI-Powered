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

from contracts import Blocco, Durata, Grado

from .calibrazione import ProfiloArchetipo


@dataclass(frozen=True)
class ArchetipoAttivo:
    """Un archetipo della run, congelato: identità + profilo PIENO (il merge con la
    calibrazione è avvenuto alla risoluzione) + repertorio di mosse di default.
    È la voce del vocabolario chiuso per-run contro cui il gate valida (F-6)."""

    slug: str
    nome: str
    descrizione: str
    profilo: ProfiloArchetipo
    mosse: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MobAttivo:
    """Un membro del cast, congelato (specchio dataclass del MobAsset).

    `mosse` = repertorio proprio (vuoto → quello dell'archetipo → default motore);
    `override` = campi del profilo che VINCONO su quello d'archetipo (dict piatto
    jsonable, i soli campi presenti: viaggia nel save col resto della stagione)."""

    slug: str
    nome: str
    archetipo: str  # slug del registry archetipi (chiusura per-run, D1)
    grado: Grado
    blocchi: list[Blocco]
    descrizione: str
    prosa_stanza: str
    durata: Durata
    tags: list[str] = field(default_factory=list)
    mosse: list[str] = field(default_factory=list)
    override: dict = field(default_factory=dict)


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
    archetipi: list[str]
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
    # Il vocabolario archetipi della run (D1): vuoto = save legacy → fallback ai
    # soli storici di calibrazione (`registry_archetipi_correnti`).
    archetipi: list[ArchetipoAttivo] = field(default_factory=list)


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


def registry_archetipi_correnti() -> dict[str, ProfiloArchetipo]:
    """Il vocabolario archetipi DELLA RUN (F-6 runtime): gli storici di calibrazione
    più gli archetipi-asset congelati nella stagione (che, se ridefiniscono uno
    storico, VINCONO — freeze batte libreria). Senza stagione (harness, save
    legacy): i soli storici — il comportamento di ieri."""
    from .calibrazione import REGISTRY_ARCHETIPI

    registro = dict(REGISTRY_ARCHETIPI)
    stagione = stagione_corrente()
    if stagione is not None:
        for arch in stagione.archetipi:
            registro[arch.slug] = arch.profilo
    return registro


def mob_del_cast(slug: str) -> MobAttivo | None:
    """Il membro del cast del PIANO CORRENTE con questo slug (None = fuori cast).
    È la risoluzione del `riferimento` (D5): il gate la usa come 4° strato."""
    piano = design_piano_corrente()
    if piano is None:
        return None
    for mob in piano.cast:
        if mob.slug == slug:
            return mob
    return None


# I campi override che toccano le resistenze: nel profilo diventano voci del dict.
_OVERRIDE_RESISTENZE = {"res_mischia": "mischia", "res_fuoco": "fuoco", "res_veleno": "veleno"}


def profilo_con_override(profilo: ProfiloArchetipo, override: dict) -> ProfiloArchetipo:
    """Applica al profilo l'override PARZIALE per-mob (dict piatto: i campi presenti
    vincono, gli assenti restano dell'archetipo). Puro dato → dato."""
    if not override:
        return profilo
    from contracts import TipoDanno
    from dataclasses import replace

    campi = {
        k: v for k, v in override.items()
        if k not in _OVERRIDE_RESISTENZE and v is not None
    }
    resistenze = dict(profilo.resistenze)
    for chiave, nome_tipo in _OVERRIDE_RESISTENZE.items():
        if override.get(chiave) is not None:
            resistenze[TipoDanno(nome_tipo)] = float(override[chiave])
    return replace(profilo, resistenze=resistenze, **campi)


def archetipo_attivo(slug: str) -> ArchetipoAttivo | None:
    """La voce congelata per `slug` (None = non è un archetipo-asset della run)."""
    stagione = stagione_corrente()
    if stagione is None:
        return None
    for arch in stagione.archetipi:
        if arch.slug == slug:
            return arch
    return None


def lint_registry(archetipi, blocchi, *, archetipi_noti=None) -> list[str]:
    """Check F-6: ogni categoria usata dal contenuto ha un binding nei registry.

    Gli archetipi sono slug con chiusura PER-RUN (D1): il set dei nomi istanziabili
    è `archetipi_noti` (storici di calibrazione ∪ archetipi-asset risolti — lo passa
    il composition root); default = i soli storici. È la cintura che rende
    l'invariante un errore di authoring, mai un crash."""
    from .calibrazione import REGISTRY_ARCHETIPI
    from .catalogo import REGISTRY_BLOCCHI

    noti = set(REGISTRY_ARCHETIPI) if archetipi_noti is None else set(archetipi_noti)
    errori: list[str] = []
    for archetipo in archetipi:
        if archetipo not in noti:
            errori.append(f"archetipo senza profilo nel registry: {archetipo}")
    for blocco in blocchi:
        if blocco not in REGISTRY_BLOCCHI:
            errori.append(f"blocco senza binding nel registry: {blocco.value}")
    return errori
