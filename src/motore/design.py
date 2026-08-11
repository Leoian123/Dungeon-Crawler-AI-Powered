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
class TabellaProceduraleAttiva:
    """Il materiale congelato per istanziare i boss dei tier procedurali
    (distretto/quartiere): nome × gimmick × archetipo, pescati seeded a runtime.
    `tier` è il `.value` dell'enum (jsonable, come `Grado` nei componenti)."""

    tier: str
    nomi: tuple[str, ...]
    gimmick: tuple[str, ...]
    archetipi: tuple[str, ...]


@dataclass(frozen=True)
class VoceSpawnAttiva:
    """Una voce di tabella di spawn congelata: il mob + la classe di frequenza
    (`.value`: il peso numerico è la foglia §11 `PESO_FREQUENZA`)."""

    mob: MobAttivo
    frequenza: str


@dataclass(frozen=True)
class TerritorioAttivo:
    """La gerarchia territoriale del piano, congelata (2026-08-10).

    `conteggi`/`boss`/`spawn` sono keyed sul `.value` del tier (jsonable: il
    componente viaggia nel save col translator generico). I roster boss vivono
    QUI e non nel cast: il boss è un RUOLO del piano, il mob resta un asset."""

    conteggi: dict[str, int] = field(default_factory=dict)
    boss: dict[str, tuple[MobAttivo, ...]] = field(default_factory=dict)
    procedurali: tuple[TabellaProceduraleAttiva, ...] = ()
    spawn: dict[str, tuple[VoceSpawnAttiva, ...]] = field(default_factory=dict)
    stanze_per_zona: int | None = None


@dataclass(frozen=True)
class EffettoAttivo:
    """Un effetto di mossa-asset congelato (jsonable: stringhe dei vocabolari)."""

    primitivo: str
    tipo_danno: str | None = None
    blocco: str | None = None
    potenza: str | None = None
    rischio: str | None = None


@dataclass(frozen=True)
class MossaAttiva:
    """Una mossa-asset congelata nella run: la traduzione a `Mossa` viva (coi
    numeri dalle fasce §11) è di `mosse.mossa_da_dati` — unico traduttore."""

    chiave: str
    etichetta: str = ""
    effetti: tuple[EffettoAttivo, ...] = ()
    costo: str = "gratuita"
    ricarica: str = "nessuna"
    azzardo: bool = False


@dataclass(frozen=True)
class OggettoAttivo:
    """Un oggetto del pool di loot, congelato nella run (appiattito jsonable:
    enum come `.value`, coppie stat×fascia come tuple — il translator generico
    lo porta nel save senza righe dedicate). La traduzione a oggetto vivo è di
    `oggetti.oggetto_da_asset` (unico traduttore, numeri dal §11)."""

    slug: str
    nome: str
    tipo: str                       # armatura | arma | accessorio
    grado: str
    descrizione: str = ""
    slot: str | None = None
    categoria: str | None = None
    taglia: str = "media"
    sede: str | None = None
    mitigazione_cent: int | None = None
    danno_base: int | None = None
    modificatori: tuple[tuple[str, str], ...] = ()   # (stat, fascia)
    mosse: tuple[str, ...] = ()


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
    # La gerarchia territoriale (None = piano piatto storico, save legacy inclusi).
    territorio: TerritorioAttivo | None = None

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
    # Il pool di loot della run (T1b): vuoto = save legacy → il solo catalogo
    # storico dimostrativo (`oggetti.catalogo_oggetti_correnti`).
    oggetti: list[OggettoAttivo] = field(default_factory=list)
    # Le mosse-asset della run (T3a): vuoto = save legacy → il solo
    # `CATALOGO_MOSSE` storico (`mosse.mossa_di`).
    mosse: list[MossaAttiva] = field(default_factory=list)


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
    È la risoluzione del `riferimento` (D5): il gate la usa come 4° strato.

    Col territorio attivo il "cast" della run include anche i ROSTER BOSS e le
    voci delle tabelle di spawn: sono contenuto del piano a tutti gli effetti —
    il gate li riconosce come riferimenti legittimi (2026-08-10)."""
    piano = design_piano_corrente()
    if piano is None:
        return None
    for mob in piano.cast:
        if mob.slug == slug:
            return mob
    if piano.territorio is not None:
        for roster in piano.territorio.boss.values():
            for mob in roster:
                if mob.slug == slug:
                    return mob
        for voci in piano.territorio.spawn.values():
            for voce in voci:
                if voce.mob.slug == slug:
                    return voce.mob
        # Il boss PROCEDURALE della zona corrente (istanziato dalle tabelle,
        # deterministico): riferibile quanto un membro del roster. Import
        # locale: design è a monte di territorio.
        from .piano import livello_corrente
        from .territorio import boss_della_zona, zona_corrente

        zona = zona_corrente()
        if zona is not None:
            candidato = boss_della_zona(livello_corrente(), zona)
            if candidato is not None and candidato.slug == slug:
                return candidato
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


def lint_profilo(slug: str, profilo) -> list[str]:
    """Check di **magnitudine** su un profilo autorato: i numeri stanno in banda?

    Chiude l'ultima porta scoperta dell'invariante "i numeri li deriva il motore".
    L'invariante era difeso sulla porta **in-run** (l'AI sceglie da enum chiusi, mai
    magnitudini) ma non su quella di **authoring**: `ProfiloArchetipoDati` valida la
    *presenza* dei campi (`ge=1`), mai il *valore*, quindi un asset con `pv_base=99999`
    passava e produceva un mob con 99.999 HP — G-L1 fuori dalla finestra, TTK
    insensato, e nessun errore da nessuna parte.

    La banda è **derivata dal catalogo**, non scritta a mano: `TETTO_AUTHORING ×` il
    massimo fra i profili storici. Così alzare deliberatamente la scala del gioco
    (calibrazione) allarga la banda da sé, mentre un refuso di battitura resta fuori.

    Vive nel MOTORE e non in `contracts` per una ragione di confine: la banda dipende
    da §11, e `contracts` non conosce la calibrazione (F-2).

    Ritorna la lista degli errori — di **authoring**, sollevati alla risoluzione, mai
    un crash a runtime."""
    from .calibrazione import REGISTRY_ARCHETIPI, TETTO_AUTHORING

    campi = ("pv_base", "danno_base", "destrezza_base", "intelligenza_base",
             "saggezza_base", "fortuna_base", "difesa_base")
    errori: list[str] = []
    for campo in campi:
        valore = getattr(profilo, campo, None)
        if valore is None:
            continue
        storici = [getattr(p, campo, 0) or 0 for p in REGISTRY_ARCHETIPI.values()]
        tetto = max([*storici, 1]) * TETTO_AUTHORING
        if valore > tetto:
            errori.append(
                f"archetipo {slug}: {campo}={valore} fuori banda (tetto {tetto:g}, "
                f"derivato dal catalogo §11). I numeri li deriva il motore: se serve "
                f"davvero una scala più grande, si alza la calibrazione, non l'asset."
            )
    return errori


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
