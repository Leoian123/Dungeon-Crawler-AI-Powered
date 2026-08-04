"""Contenuti dello show: Stagioni, Piani e Mob come ASSET riusabili.

Il crawl è uno spettacolo: la **Stagione** è l'edizione dello show su un mondo
(aggregato radice), i **Piani** sono i suoi costituenti ordinati per profondità,
i **Mob** sono il cast. Come gli architetti del dungeon nel canone DCC, gli
asset si RIUSANO tra stagioni: la libreria è normalizzata (riferimenti per
slug), ogni asset porta `tags` per l'affinity matching, e il runtime consuma
solo le **forme risolte** (denormalizzate alla creazione della run, poi
congelate nel World — mai la libreria).

Regole di membrana: qui vive la FORMA (F-2: solo stdlib + Pydantic, enum
chiusi del contratto). Niente numeri di gioco, mai: il design è categoriale
(archetipo × grado × blocchi) + testo libero; i numeri li deriva la
calibrazione del motore. La coerenza referenziale (slug pendenti) e il check
F-6 (binding nel registry) vivono a valle (risoluzione in `main`, lint nel
motore); la coerenza cast⊆budget è imposta QUI, sulla forma risolta, per
costruzione.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .schema import RE_SLUG as _RE_SLUG
from .schema import ArchetipoId, Blocco, Durata, Grado

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# Slug e tag: kebab-case minuscolo (pattern condiviso con schema.py), identità
# stabile degli asset e vocabolario dell'affinità. I tag NON sono enum: sono
# folksonomia di authoring.


def _senza_duplicati(valori: list, etichetta: str) -> None:
    if len(set(valori)) != len(valori):
        raise ValueError(f"{etichetta}: voci duplicate")


class BudgetDesign(BaseModel):
    """Il vincolo HARD del gate per un piano: cosa il GM può mettere in scena.

    Il cast è orientativo (entra nei prompt), il budget è la legge: il gate del
    motore respinge qualunque entità fuori da questi set (fuori budget →
    fallback, mai contenuto arbitrario)."""

    model_config = _FROZEN

    gradi: list[Grado] = Field(min_length=1)
    blocchi: list[Blocco] = Field(default_factory=list)  # vuota = nessun blocco ammesso
    archetipi: list[ArchetipoId] = Field(min_length=1)

    @model_validator(mode="after")
    def _unici(self) -> "BudgetDesign":
        _senza_duplicati(self.gradi, "gradi")
        _senza_duplicati(self.blocchi, "blocchi")
        _senza_duplicati(self.archetipi, "archetipi")
        return self


class _Asset(BaseModel):
    """Base comune degli asset di libreria: identità, versione, tag."""

    model_config = _FROZEN

    slug: str = Field(pattern=_RE_SLUG)
    versione: int = Field(default=1, ge=1)
    tags: list[str] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def _tags_validi(self) -> "_Asset":
        import re

        _senza_duplicati(self.tags, "tags")
        for tag in self.tags:
            if not re.fullmatch(_RE_SLUG, tag):
                raise ValueError(f"tag non kebab-case: {tag!r}")
        return self


class ProfiloArchetipoDati(BaseModel):
    """Il profilo numerico di un archetipo COME DATO, authoring-facing.

    Qui i numeri sono LEGALI: li scrive l'autore (umano o agente) dentro l'asset e
    il motore li valida e li scala con la formula-madre. F-3 resta intatto: questi
    numeri non attraversano MAI il contratto AI (`EntitaGenerata` resta senza).
    PARZIALE: un campo `None` si completa dalla calibrazione per gli archetipi
    storici (che restano di sua proprietà numerica); per uno slug NUOVO il profilo
    dev'essere completo — lo impone la risoluzione, come errore di authoring.
    `armatura/taglia/arma` sono chiavi delle tabelle §11 (validate alla risoluzione:
    contracts non conosce il motore). Resistenze in punti % (<0 resiste, >0
    vulnerabile; None = eredita, per i nuovi slug vale 0)."""

    model_config = _FROZEN

    destrezza_base: int | None = Field(default=None, ge=1)
    pv_base: int | None = Field(default=None, ge=1)
    danno_base: int | None = Field(default=None, ge=1)
    intelligenza_base: int | None = Field(default=None, ge=1)
    difesa_base: int | None = Field(default=None, ge=0)
    saggezza_base: int | None = Field(default=None, ge=1)
    fortuna_base: int | None = Field(default=None, ge=1)
    armatura: str | None = None
    taglia: str | None = None
    arma: str | None = None
    res_mischia: float | None = None
    res_fuoco: float | None = None
    res_veleno: float | None = None


class ArchetipoAsset(_Asset):
    """Un ARCHETIPO come asset di libreria: l'identità meccanica di una famiglia di
    mob, creabile da dati (D1: niente enum, niente codice). Alla creazione della run
    gli archetipi riferiti dalla stagione vengono risolti (profilo completato) e
    CONGELATI nella `StagioneAttiva`: il gate valida contro quel registry (F-6
    runtime). `mosse` = repertorio di default dei mob di questo archetipo (chiavi
    del catalogo mosse del motore; lint alla risoluzione/salvataggio)."""

    nome: str = Field(min_length=1)
    descrizione: str = ""
    profilo: ProfiloArchetipoDati | None = None
    mosse: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _mosse_uniche(self) -> "ArchetipoAsset":
        _senza_duplicati(self.mosse, "mosse")
        return self


class MobAsset(_Asset):
    """Un membro del cast: profilo CATEGORIALE + flavor + la sua scena.

    `prosa_stanza` è il copione offline (una scena per stanza); col GM live il
    mob entra nel prompt come suggerimento di cast. Nessuna stat: i numeri li
    deriva la calibrazione da archetipo × grado × livello."""

    nome: str = Field(min_length=1)
    archetipo: ArchetipoId
    grado: Grado
    blocchi: list[Blocco] = Field(default_factory=list)
    descrizione: str = ""
    prosa_stanza: str = Field(min_length=1)
    durata: Durata = Durata.TURNO
    # Espressività per-mob (Fase 5): mosse proprie (vuoto = quelle dell'archetipo,
    # poi il default del motore) e override PARZIALE del profilo d'archetipo —
    # vince campo-per-campo. Authoring-facing: numeri legali qui, mai in
    # `EntitaGenerata` (F-3).
    mosse: list[str] = Field(default_factory=list)
    override: ProfiloArchetipoDati | None = None

    @model_validator(mode="after")
    def _blocchi_unici(self) -> "MobAsset":
        _senza_duplicati(self.blocchi, "blocchi")
        _senza_duplicati(self.mosse, "mosse")
        return self


class PianoAsset(_Asset):
    """Un piano del dungeon: tema, voce, budget hard e cast per RIFERIMENTO.

    `cast` elenca slug di `MobAsset` in ordine di apparizione (offline: una
    stanza per voce; un mob può ripetersi — riuso). `stanze` è la SCALA del
    piano (il piano 1 grande quanto il mondo, il 18 una stanza): `None` = si
    deriva (offline `len(cast)`, live la calibrazione)."""

    titolo: str = Field(min_length=1)
    tema: str = Field(min_length=1)
    stile: list[str] = Field(default_factory=list, max_length=6)
    lore: str = ""
    budget: BudgetDesign
    cast: list[str] = Field(min_length=1)  # slug di MobAsset, ordinati
    stanze: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _cast_slug_validi(self) -> "PianoAsset":
        import re

        for slug in self.cast:
            if not re.fullmatch(_RE_SLUG, slug):
                raise ValueError(f"cast: slug non valido {slug!r}")
        return self


class Stagione(BaseModel):
    """L'edizione dello show su un mondo: l'AGGREGATO radice.

    Possiede la voce editoriale (stile/lore di cornice, ereditati per cascata
    dai piani) e la sequenza dei piani per RIFERIMENTO, ordinata per
    profondità (indice 0 = piano 1). Un piano può ripetersi (riuso di asset).
    """

    model_config = _FROZEN

    slug: str = Field(pattern=_RE_SLUG)
    versione: int = Field(default=1, ge=1)
    tags: list[str] = Field(default_factory=list, max_length=16)
    numero: int = Field(ge=1)
    titolo: str = Field(min_length=1)
    tagline: str = ""
    mondo: str = Field(min_length=1)  # il pianeta reclamato
    stile: list[str] = Field(default_factory=list, max_length=6)
    lore: str = ""
    piani: list[str] = Field(min_length=1)  # slug di PianoAsset, per profondità

    @model_validator(mode="after")
    def _validi(self) -> "Stagione":
        import re

        _senza_duplicati(self.tags, "tags")
        for tag in self.tags:
            if not re.fullmatch(_RE_SLUG, tag):
                raise ValueError(f"tag non kebab-case: {tag!r}")
        for slug in self.piani:
            if not re.fullmatch(_RE_SLUG, slug):
                raise ValueError(f"piani: slug non valido {slug!r}")
        return self


# --- Forme RISOLTE (denormalizzate): prodotte dalla risoluzione, mai autorate ---

class PianoRisolto(BaseModel):
    """Il piano coi riferimenti SCIOLTI: il cast è inline. La coerenza
    cast⊆budget è imposta per costruzione dal validator: un piano risolto
    incoerente non può esistere."""

    model_config = _FROZEN

    slug: str
    versione: int
    tags: list[str] = Field(default_factory=list)
    titolo: str
    tema: str
    stile: list[str] = Field(default_factory=list)
    lore: str = ""
    budget: BudgetDesign
    cast: list[MobAsset] = Field(min_length=1)
    stanze: int | None = None

    @property
    def n_stanze(self) -> int:
        """La scala effettiva per l'offline: esplicita o derivata dal cast."""
        return self.stanze if self.stanze is not None else len(self.cast)

    @model_validator(mode="after")
    def _cast_nel_budget(self) -> "PianoRisolto":
        gradi = set(self.budget.gradi)
        blocchi = set(self.budget.blocchi)
        archetipi = set(self.budget.archetipi)
        for mob in self.cast:
            if mob.grado not in gradi:
                raise ValueError(f"cast fuori budget: {mob.slug} ha grado {mob.grado.value}")
            if mob.archetipo not in archetipi:
                raise ValueError(
                    f"cast fuori budget: {mob.slug} ha archetipo {mob.archetipo}"
                )
            if not set(mob.blocchi) <= blocchi:
                raise ValueError(f"cast fuori budget: {mob.slug} ha blocchi non ammessi")
        return self


class StagioneRisolta(BaseModel):
    """La stagione coi piani SCIOLTI e coerenti: pronta al freeze nel World.

    `archetipi` = gli archetipi riferiti da budget/cast, RISOLTI (profilo completo:
    il merge con la calibrazione è già avvenuto) — il vocabolario chiuso della run."""

    model_config = _FROZEN

    slug: str
    versione: int
    tags: list[str] = Field(default_factory=list)
    numero: int
    titolo: str
    tagline: str = ""
    mondo: str
    stile: list[str] = Field(default_factory=list)
    lore: str = ""
    piani: list[PianoRisolto] = Field(min_length=1)
    archetipi: list[ArchetipoAsset] = Field(default_factory=list)


class AssetVista(BaseModel):
    """Una voce dell'elenco libreria (per l'hub/GM mode e l'affinità)."""

    model_config = _FROZEN

    slug: str
    tipo: Literal["stagione", "piano", "mob", "archetipo"]
    etichetta: str
    tags: list[str] = Field(default_factory=list)
    origine: Literal["ufficiale", "locale"] = "ufficiale"
    valido: bool = True
