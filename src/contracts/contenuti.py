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

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .schema import RE_SLUG as _RE_SLUG
from .schema import (
    ArchetipoId,
    Blocco,
    CategoriaArmatura,
    CategoriaPng,
    Durata,
    Fascia,
    FasciaCosto,
    FasciaRicarica,
    Frequenza,
    Grado,
    SedeAccessorio,
    StatId,
    Taglia,
    TierTerritorio,
    TipoDanno,
)
from .proiezione import SLOT_ARMATURA, SlotEquip
from .schema import EffettoDati

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
    # Identità cinematografica (la lore che il dialogo e il reveal vestono):
    # facoltativa per il mob ordinario — la sua lore MINIMA resta comunque
    # `prosa_stanza`, obbligatoria — RIGOROSA per l'Elité (validator sotto).
    aspetto: str = ""
    tratto: str = ""
    # ELITÉ (decisione utente 2026-08-11): il PNG che tutti nel dungeon
    # IDOLATRANO — il nome dell'ambientazione (i Garrosh/Arthas di questo
    # mondo). È IDENTITÀ, non ruolo: il comportamento resta quello del PNG
    # (mai ostile, mai despawn, dialogo GM-pilotato). Contratti attivi ORA:
    # lore piena obbligatoria; mai nei roster boss/spawn/cast (un idolo non
    # custodisce varchi e non è un incontro: si INCONTRA, dal piano minimo
    # §11 `ELITE.piano_minimo` in su). Farlo morire è roba del futuro.
    elite: bool = False
    # CATEGORIA (decisione utente 2026-08-16): chi può rompere il divieto del
    # menu. Default ORDINARIO = GM-pilotato (i save e gli asset storici
    # deserializzano invariati); le categorie interpellabili portano l'obbligo
    # di forma della VOCE (validator sotto).
    categoria: CategoriaPng = CategoriaPng.ORDINARIO
    # La VOCE (decisione utente 2026-08-16): come il personaggio PARLA —
    # cadenza, registro, scelta di frasi, tic verbali. Non è la lore (aspetto/
    # tratto dicono chi è; la voce dice come suona). Entra nel prompt di
    # dialogo e scena: è il dato che impedisce «dialoghi diversi fra loro solo
    # a parole e non per cadenza». Compatta per il budget token: 1-2 frasi.
    voce: str = ""
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

    @model_validator(mode="after")
    def _elite_esige_la_lore(self) -> "MobAsset":
        """«Tutti devono avere una lore» — e l'idolo più di tutti: un Elité
        senza biografia completa non può ESISTERE come asset."""
        if self.elite:
            for campo in ("descrizione", "aspetto", "tratto"):
                if not getattr(self, campo).strip():
                    raise ValueError(
                        f"elite {self.slug}: `{campo}` obbligatorio — l'idolo "
                        "del dungeon esige la lore piena (descrizione, "
                        "aspetto, tratto)"
                    )
        return self

    @model_validator(mode="after")
    def _interpellabile_esige_la_voce(self) -> "MobAsset":
        """OBBLIGO DI FORMA della voce (decisione utente 2026-08-16): un PNG che
        il giocatore può interpellare direttamente — o che parla da narratore —
        senza una voce autorata sarebbe «un archetipo ripetitivo: dialoghi
        diversi solo a parole». Come la lore per l'Elité: senza voce, l'asset
        interpellabile non può esistere. Vale anche per l'Elité (l'idolo ha una
        voce per definizione)."""
        esige = self.elite or self.categoria in (
            CategoriaPng.MAESTRO_GILDA, CategoriaPng.MANAGER, CategoriaPng.NARRATORE,
        )
        if esige and not self.voce.strip():
            raise ValueError(
                f"{self.slug}: `voce` obbligatoria per categoria "
                f"{self.categoria.value}{' / elite' if self.elite else ''} — "
                "cadenza, registro e frasario sono l'identità parlata, non un extra"
            )
        return self


class ModificatoreDati(BaseModel):
    """UNA voce categoriale di potere su un oggetto: stat + FASCIA nominata.
    Il numero lo deriva il motore (§11: fascia × rango del grado) — qui non
    esiste un campo dove scriverlo."""

    model_config = _FROZEN

    stat: StatId
    fascia: Fascia


class EffettoConsumabile(str, Enum):
    """Vocabolario CHIUSO degli effetti di un consumabile (canale B, ratifica
    2026-08-26): l'asset NOMINA l'effetto, i numeri li deriva il motore
    (§11 per grado — `CONSUMABILE.CURA_PCT.*`, `CONSUMABILE.MANA_PCT.*`).
    Un effetto nuovo è un membro qui + una riga nell'esecutore del motore
    (pattern SPEC_STATUS: il buco è un KeyError all'import, mai un numero
    inventato altrove)."""

    CURA = "cura"                  # HP: quota del massimo, per grado
    RISTORO_MANA = "ristoro_mana"  # mana: quota del massimo, per grado
    ANTIDOTO = "antidoto"          # purga gli status DANNOSI (mai gli innati)
    TOMO = "tomo"                  # INSEGNA una mossa (canale GearTome, nodo S)


class OggettoAsset(_Asset):
    """Un OGGETTO come asset di libreria: il canale del loot (ADR-2 ridotto).

    Quattro forme in un solo tipo (`tipo` discrimina): armatura (slot esclusivo
    + categoria), arma (mount unico), accessorio (multiset aperto, può concedere
    mosse), CONSUMABILE (monouso: nomina un `effetto` dal vocabolario chiuso,
    mai numeri — canale B, 2026-08-26). I `modificatori` sono FASCE (mai
    numeri); `mitigazione_cent` e `danno_base` sono i numeri LEGALI
    dell'authoring umano (pattern `ProfiloArchetipoDati`) — `None` = derivati
    dal motore (categoria→mitigazione, grado→danno) — e il lint di banda del
    motore li tiene in scala."""

    nome: str = Field(min_length=1)
    descrizione: str = ""
    tipo: Literal["armatura", "arma", "accessorio", "consumabile"]
    grado: Grado                          # il tier di loot: qualità e budget del drop
    slot: SlotEquip | None = None         # armatura: obbligatorio (∈ SLOT_ARMATURA)
    categoria: CategoriaArmatura | None = None
    taglia: Taglia = Taglia.MEDIA
    sede: SedeAccessorio | None = None    # accessorio: obbligatorio
    mosse: list[str] = Field(default_factory=list)       # solo accessori
    modificatori: list[ModificatoreDati] = Field(default_factory=list, max_length=4)
    mitigazione_cent: int | None = Field(default=None, ge=0)
    danno_base: int | None = Field(default=None, ge=0)
    effetto: EffettoConsumabile | None = None            # solo consumabili
    insegna_mossa: str = ""                              # solo effetto TOMO
    # Il canale GearTome del nodo S7: ALCUNI oggetti portano una skill in sé
    # — il pezzo indossato ALZA il livello effettivo della competenza («la
    # stessa skill a +1 o +5» del riferimento). SOLO gli indossabili: il
    # consumabile insegna col tomo, non indossa competenza. `skill` è lo
    # slug del catalogo skill (lint a valle), `skill_livelli` il bonus.
    skill: str = ""
    skill_livelli: int = Field(default=0, ge=0, le=5)

    @model_validator(mode="after")
    def _coerente_per_tipo(self) -> "OggettoAsset":
        if self.tipo == "armatura":
            if self.slot is None or self.categoria is None:
                raise ValueError(f"oggetto {self.slug}: un'armatura vuole slot e categoria")
            if self.slot not in SLOT_ARMATURA:
                raise ValueError(f"oggetto {self.slug}: {self.slot.value!r} non è uno slot d'armatura")
        else:
            if self.slot is not None or self.categoria is not None or self.mitigazione_cent is not None:
                raise ValueError(f"oggetto {self.slug}: slot/categoria/mitigazione sono solo dell'armatura")
        if self.tipo == "accessorio":
            if self.sede is None:
                raise ValueError(f"oggetto {self.slug}: un accessorio vuole la sede")
        else:
            if self.sede is not None or self.mosse:
                raise ValueError(f"oggetto {self.slug}: sede/mosse sono solo dell'accessorio")
        if self.tipo != "arma" and self.danno_base is not None:
            raise ValueError(f"oggetto {self.slug}: danno_base è solo dell'arma")
        if self.tipo == "consumabile":
            if self.effetto is None:
                raise ValueError(f"oggetto {self.slug}: un consumabile vuole l'effetto")
            if self.modificatori:
                raise ValueError(
                    f"oggetto {self.slug}: i modificatori sono dell'indossabile — "
                    "un consumabile agisce una volta, non si porta addosso"
                )
            if (self.effetto is EffettoConsumabile.TOMO) != bool(self.insegna_mossa):
                raise ValueError(
                    f"oggetto {self.slug}: il TOMO vuole la mossa che insegna, "
                    "gli altri effetti non la portano"
                )
        elif self.effetto is not None:
            raise ValueError(f"oggetto {self.slug}: l'effetto è solo del consumabile")
        elif self.insegna_mossa:
            raise ValueError(f"oggetto {self.slug}: insegna_mossa è solo del tomo")
        if bool(self.skill) != (self.skill_livelli >= 1):
            raise ValueError(
                f"oggetto {self.slug}: la skill portata vuole i suoi livelli "
                "(e viceversa) — il canale GearTome è una coppia"
            )
        if self.skill and self.tipo == "consumabile":
            raise ValueError(
                f"oggetto {self.slug}: il consumabile non indossa competenza "
                "— la skill in sé è degli indossabili, il tomo insegna"
            )
        _senza_duplicati([m.stat for m in self.modificatori], "modificatori (stat)")
        _senza_duplicati(self.mosse, "mosse")
        return self


class ParteBase(BaseModel):
    """Il CORPO di un oggetto della fabbrica (stile BL3, in piccolo): la forma
    fisica — tipo, e i campi che quel tipo esige. Il nome è la testa del nome
    composto («Lama …», «Elmo …»).

    `tipo="consumabile"` (B9.2, rigiro Kora 2026-08-28: il canale consumabili
    era completo ma NESSUNA fonte lo alimentava — 40+ oggetti in tre run
    profonde, zero cure): la base nomina l'`effetto` dal vocabolario chiuso e
    la fabbrica conia tonici/antidoti come ogni altro pezzo — drop e box
    inclusi. Il TOMO resta fuori: insegna una mossa specifica, è contenuto
    autorato (asset `OggettoAsset`), mai un conio."""

    model_config = _FROZEN

    nome: str = Field(min_length=1)
    tipo: Literal["armatura", "arma", "accessorio", "consumabile"]
    slot: SlotEquip | None = None         # armatura
    categoria: CategoriaArmatura | None = None
    taglia: Taglia = Taglia.MEDIA
    sede: SedeAccessorio | None = None    # accessorio
    effetto: EffettoConsumabile | None = None  # consumabile

    @model_validator(mode="after")
    def _coerente(self) -> "ParteBase":
        if self.tipo == "armatura" and (self.slot is None or self.categoria is None
                                        or self.slot not in SLOT_ARMATURA):
            raise ValueError(f"parte base {self.nome!r}: armatura senza slot/categoria validi")
        if self.tipo == "accessorio" and self.sede is None:
            raise ValueError(f"parte base {self.nome!r}: accessorio senza sede")
        if self.tipo == "consumabile":
            if self.effetto is None:
                raise ValueError(
                    f"parte base {self.nome!r}: consumabile senza effetto"
                )
            if self.effetto is EffettoConsumabile.TOMO:
                raise ValueError(
                    f"parte base {self.nome!r}: il TOMO non si conia — insegna "
                    "una mossa specifica, è un asset autorato"
                )
        elif self.effetto is not None:
            raise ValueError(
                f"parte base {self.nome!r}: `effetto` vale solo per i consumabili"
            )
        return self


class ParteFamiglia(BaseModel):
    """La FAMIGLIA (il "produttore" di BL3): flavor + il tratto caratteristico
    come modificatori a FASCIA. Il nome è la coda del nome composto
    («… dei Becchini»)."""

    model_config = _FROZEN

    nome: str = Field(min_length=1)
    descrizione: str = ""
    modificatori: list[ModificatoreDati] = Field(default_factory=list, max_length=2)


class ParteAffisso(BaseModel):
    """L'AFFISSO (l'"elemento"/tratto di BL3): un aggettivo nel nome
    («Fumante …») + resistenza tipata a fascia e/o un modificatore.
    `descrizione` è la NOTA autorale dell'elemento — la riga che il
    compositore delle descrizioni tesse nel pezzo coniato (§B-4): il testo
    è dato d'asset, mai generato dal motore."""

    model_config = _FROZEN

    nome: str = Field(min_length=1)
    descrizione: str = ""
    res_contro: TipoDanno | None = None       # resistenza elementale...
    res_fascia: Fascia | None = None          # ...con l'intensità a fascia
    modificatori: list[ModificatoreDati] = Field(default_factory=list, max_length=1)
    # L'affisso che porta una SKILL in sé (S7, il conio che pesca competenza):
    # il pezzo coniato con questo affisso alza il livello della skill finché
    # indosso — stessa coppia degli oggetti autorati, stesso lint a valle.
    skill: str = ""
    skill_livelli: int = Field(default=0, ge=0, le=5)

    @model_validator(mode="after")
    def _res_coerente(self) -> "ParteAffisso":
        if (self.res_contro is None) != (self.res_fascia is None):
            raise ValueError(f"affisso {self.nome!r}: res_contro e res_fascia vanno insieme")
        if bool(self.skill) != (self.skill_livelli >= 1):
            raise ValueError(
                f"affisso {self.nome!r}: la skill portata vuole i suoi livelli"
            )
        if self.res_contro is None and not self.modificatori and not self.skill:
            raise ValueError(f"affisso {self.nome!r}: un affisso deve portare qualcosa")
        return self


class FabbricaAsset(_Asset):
    """La FABBRICA del loot procedurale (stile Borderlands, in piccolo): le
    tabelle-parti che il motore combina SEEDED a ogni drop — basi × famiglie ×
    affissi × grado. Le parti sono FASCE ed enum (mai numeri): i valori li
    deriva il motore (fascia × rango del grado). Il precedente è la tabella
    dei boss procedurali: si autora il vocabolario, il motore conia le
    istanze — deterministiche, gratuite, anche offline."""

    nome: str = Field(min_length=1)
    basi: list[ParteBase] = Field(min_length=2, max_length=16)
    famiglie: list[ParteFamiglia] = Field(min_length=2, max_length=16)
    affissi: list[ParteAffisso] = Field(min_length=2, max_length=16)

    @model_validator(mode="after")
    def _nomi_unici(self) -> "FabbricaAsset":
        _senza_duplicati([b.nome for b in self.basi], "basi")
        _senza_duplicati([f.nome for f in self.famiglie], "famiglie")
        _senza_duplicati([a.nome for a in self.affissi], "affissi")
        return self


class MossaAsset(_Asset):
    """Una MOSSA come asset di libreria: composizione di primitivi chiusi
    (GR2 §7.3 — «voce di catalogo + righe di Effetto, zero righe nel loop»).

    Il VALIDATORE è il gate di composizione (PMF-6.3/6.4) e vale identico per
    umano, AI e file scritto a mano: esattamente UN primitivo di danno per
    mossa (il moltiplicatore entra una volta nel check 2, dentro l'unico
    arrotondamento — stacking additivo preservato); `applica_status` mai prima
    del danno (la legatura a_segno del risolutore è semantica, non stile);
    `azzardo` ⟺ c'è un `danno_variabile` (il consenso resta dichiarativo).
    Costi e ricariche sono FASCE (foglie §11), mai numeri."""

    etichetta: str = Field(min_length=1)      # il nome diegetico nel menu
    effetti: list[EffettoDati] = Field(min_length=1, max_length=2)
    costo: FasciaCosto = FasciaCosto.GRATUITA
    ricarica: FasciaRicarica = FasciaRicarica.NESSUNA
    azzardo: bool = False

    @model_validator(mode="after")
    def _composizione_valida(self) -> "MossaAsset":
        danni = [e for e in self.effetti if e.primitivo in ("danno", "danno_variabile")]
        if len(danni) != 1:
            raise ValueError(
                f"mossa {self.slug}: serve ESATTAMENTE un primitivo di danno "
                f"(trovati {len(danni)}) — un solo round, stacking additivo (PMF-6.4)"
            )
        indice_danno = self.effetti.index(danni[0])
        for indice, e in enumerate(self.effetti):
            if e.primitivo == "applica_status":
                if indice < indice_danno:
                    raise ValueError(
                        f"mossa {self.slug}: applica_status prima del danno — "
                        "lo status passa SOLO col colpo che connette (a_segno)"
                    )
                if e.blocco is None:
                    raise ValueError(f"mossa {self.slug}: applica_status senza blocco")
                if (e.tipo_danno is not None or e.potenza is not None
                        or e.rischio is not None or e.stile is not None):
                    raise ValueError(f"mossa {self.slug}: campi di danno su applica_status")
            if e.primitivo == "danno" and (e.blocco is not None or e.rischio is not None):
                raise ValueError(f"mossa {self.slug}: campi impropri sul primitivo danno")
            if e.primitivo == "danno_variabile" and (e.blocco is not None or e.potenza is not None):
                raise ValueError(f"mossa {self.slug}: campi impropri su danno_variabile")
        con_azzardo = any(e.primitivo == "danno_variabile" for e in self.effetti)
        if self.azzardo != con_azzardo:
            raise ValueError(
                f"mossa {self.slug}: azzardo={self.azzardo} ma "
                f"danno_variabile={'presente' if con_azzardo else 'assente'} — "
                "il consenso è della mossa e deve dire il vero (F10)"
            )
        return self


# --- Territorio: la gerarchia di un piano-mondo (2026-08-10) --------------------
#
# Un piano che ospita miliardi non si autora stanza per stanza: si autorano le
# ANCORE (roster boss canonici, tabelle) e il motore campiona il resto, seeded.
# I tier con roster NOMINATO sono PIANO/PAESE/PROVINCIA/CITTA; DISTRETTO e
# QUARTIERE sono procedurali (tabelle nome×gimmick×archetipo, istanziati a
# runtime dal seed di zona). La simmetria tier↔grado è forma (schema.py).

# I tier col roster nominato vs i tier procedurali (chiusi, per costruzione).
_TIER_NOMINATI = frozenset({
    TierTerritorio.PIANO, TierTerritorio.PAESE,
    TierTerritorio.PROVINCIA, TierTerritorio.CITTA,
})
_TIER_PROCEDURALI = frozenset({TierTerritorio.DISTRETTO, TierTerritorio.QUARTIERE})


class VoceSpawn(BaseModel):
    """Una voce di tabella di spawn: UN mob (per slug) con la sua frequenza.

    La frequenza è una categoria (F-14): il peso numerico è una foglia §11."""

    model_config = _FROZEN

    mob: str = Field(pattern=_RE_SLUG)
    frequenza: Frequenza = Frequenza.COMUNE


class TabellaSpawn(BaseModel):
    """La tabella di spawn di un TIER: chi popola le stanze ordinarie delle zone
    di quel livello (riempitivi del copione offline, pescate d'imboscata,
    suggerimenti soft nel prompt live)."""

    model_config = _FROZEN

    tier: TierTerritorio
    voci: list[VoceSpawn] = Field(min_length=1)

    @model_validator(mode="after")
    def _voci_uniche(self) -> "TabellaSpawn":
        _senza_duplicati([v.mob for v in self.voci], "voci")
        return self


class TabellaBossProcedurali(BaseModel):
    """Il materiale per ISTANZIARE (seeded, a runtime) i boss dei tier
    procedurali: nome × gimmick × archetipo. Il grado non c'è: lo impone il
    tier (simmetria 6↔6); i numeri li deriva la calibrazione come sempre."""

    model_config = _FROZEN

    tier: TierTerritorio
    nomi: list[str] = Field(min_length=4)
    gimmick: list[str] = Field(min_length=4)
    archetipi: list[ArchetipoId] = Field(min_length=1)

    @model_validator(mode="after")
    def _tier_procedurale(self) -> "TabellaBossProcedurali":
        if self.tier not in _TIER_PROCEDURALI:
            raise ValueError(
                f"tabella procedurale sul tier {self.tier.value}: i tier nominati "
                "hanno un roster, non una tabella"
            )
        _senza_duplicati(self.nomi, "nomi")
        _senza_duplicati(self.gimmick, "gimmick")
        _senza_duplicati(self.archetipi, "archetipi")
        return self


class TerritorioDesign(BaseModel):
    """La gerarchia territoriale di un piano-mondo. Assente sul `PianoAsset` =
    piano piatto storico (retro-compatibile).

    `conteggi` è la SCALA del mondo per tier (lore + campionamento della spina:
    quante province, quante città…); PIANO non vi compare (è sempre 1).
    `boss` è il roster NOMINATO per tier (slug di `MobAsset`): canonici autorati
    + generati dall'authoring AI. `procedurali` copre distretti e quartieri."""

    model_config = _FROZEN

    conteggi: dict[TierTerritorio, int] = Field(default_factory=dict)
    boss: dict[TierTerritorio, list[str]] = Field(default_factory=dict)
    procedurali: list[TabellaBossProcedurali] = Field(min_length=2)
    spawn: list[TabellaSpawn] = Field(min_length=1)
    stanze_per_zona: int | None = Field(default=None, ge=2)

    def conta(self, tier: TierTerritorio) -> int:
        """Quante unità di quel tier esistono nel mondo (default 1)."""
        return self.conteggi.get(tier, 1)

    @model_validator(mode="after")
    def _coerente(self) -> "TerritorioDesign":
        if TierTerritorio.PIANO in self.conteggi:
            raise ValueError("conteggi: il tier 'piano' è sempre 1, non si dichiara")
        for tier, n in self.conteggi.items():
            if n < 1:
                raise ValueError(f"conteggi: {tier.value} deve essere >= 1")
        import re

        for tier, roster in self.boss.items():
            if tier not in _TIER_NOMINATI:
                raise ValueError(
                    f"boss: il tier {tier.value} è procedurale (tabelle, non roster)"
                )
            _senza_duplicati(roster, f"boss[{tier.value}]")
            for slug in roster:
                if not re.fullmatch(_RE_SLUG, slug):
                    raise ValueError(f"boss[{tier.value}]: slug non valido {slug!r}")
        if len(self.boss.get(TierTerritorio.PIANO, [])) != 1:
            raise ValueError("boss: il tier 'piano' vuole ESATTAMENTE un boss")
        for tier, roster in self.boss.items():
            if tier in self.conteggi and len(roster) > self.conteggi[tier]:
                raise ValueError(
                    f"boss[{tier.value}]: roster ({len(roster)}) oltre il "
                    f"conteggio del mondo ({self.conteggi[tier]})"
                )
        coperti = {t.tier for t in self.procedurali}
        if not _TIER_PROCEDURALI <= coperti:
            mancanti = ", ".join(t.value for t in _TIER_PROCEDURALI - coperti)
            raise ValueError(f"procedurali: manca la tabella per: {mancanti}")
        _senza_duplicati([t.tier for t in self.procedurali], "procedurali")
        _senza_duplicati([t.tier for t in self.spawn], "spawn")
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
    # La gerarchia territoriale (2026-08-10): assente = piano piatto storico.
    territorio: TerritorioDesign | None = None

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
    # Il POOL DI LOOT della stagione, per riferimento (slug di OggettoAsset).
    # VUOTO = lasco: tutta la libreria oggetti valida (D-1) — la stagione può
    # stringere il pool quando il loot diventa curatela editoriale.
    oggetti: list[str] = Field(default_factory=list)
    # Le MOSSE-ASSET della stagione (stessa politica lasca: vuoto = tutta la
    # libreria mosse valida). Congelate nella run, si sommano al catalogo.
    mosse: list[str] = Field(default_factory=list)
    # La FABBRICA del loot procedurale (slug di FabbricaAsset). None = lasca:
    # la prima fabbrica valida in libreria (ordine di slug); assente = niente
    # conio procedurale, restano pool e conio AI.
    fabbrica: str | None = None

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
        _senza_duplicati(self.oggetti, "oggetti")
        for slug in self.oggetti:
            if not re.fullmatch(_RE_SLUG, slug):
                raise ValueError(f"oggetti: slug non valido {slug!r}")
        _senza_duplicati(self.mosse, "mosse")
        for slug in self.mosse:
            if not re.fullmatch(_RE_SLUG, slug):
                raise ValueError(f"mosse: slug non valido {slug!r}")
        if self.fabbrica is not None and not re.fullmatch(_RE_SLUG, self.fabbrica):
            raise ValueError(f"fabbrica: slug non valido {self.fabbrica!r}")
        return self


# --- Forme RISOLTE (denormalizzate): prodotte dalla risoluzione, mai autorate ---

class VoceSpawnRisolta(BaseModel):
    """Una voce di spawn col mob SCIOLTO (inline)."""

    model_config = _FROZEN

    mob: MobAsset
    frequenza: Frequenza = Frequenza.COMUNE


class TabellaSpawnRisolta(BaseModel):
    model_config = _FROZEN

    tier: TierTerritorio
    voci: list[VoceSpawnRisolta] = Field(min_length=1)


class TerritorioRisolto(BaseModel):
    """Il territorio coi roster SCIOLTI e coerenti per costruzione:

    - il grado di ogni boss È il grado del suo tier (simmetria 6↔6, per indice);
    - il CELESTIALE è riservato al boss di PIANO (per costruzione: nessun altro
      tier lo può avere, e cast/spawn lo escludono nel validator del piano);
    - gli archetipi delle tabelle procedurali sono slug (⊆ budget: validator del
      piano risolto, che il budget lo possiede)."""

    model_config = _FROZEN

    conteggi: dict[TierTerritorio, int] = Field(default_factory=dict)
    boss: dict[TierTerritorio, list[MobAsset]] = Field(default_factory=dict)
    procedurali: list[TabellaBossProcedurali] = Field(min_length=2)
    spawn: list[TabellaSpawnRisolta] = Field(min_length=1)
    stanze_per_zona: int | None = None

    def conta(self, tier: TierTerritorio) -> int:
        return self.conteggi.get(tier, 1)

    @model_validator(mode="after")
    def _boss_del_loro_tier(self) -> "TerritorioRisolto":
        if len(self.boss.get(TierTerritorio.PIANO, [])) != 1:
            raise ValueError("territorio: il tier 'piano' vuole ESATTAMENTE un boss")
        for tier, roster in self.boss.items():
            if tier not in _TIER_NOMINATI:
                raise ValueError(f"territorio: roster sul tier procedurale {tier.value}")
            for mob in roster:
                if mob.grado is not tier.grado:
                    raise ValueError(
                        f"boss fuori tier: {mob.slug} è {mob.grado.value}, il tier "
                        f"{tier.value} esige {tier.grado.value}"
                    )
        return self

    @model_validator(mode="after")
    def _un_elite_non_custodisce_varchi(self) -> "TerritorioRisolto":
        """L'Elité è il PNG idolatrato: MAI un custode (di nessun tier — men che
        meno il boss di piano) e MAI una voce di spawn. Per costruzione."""
        for tier, roster in self.boss.items():
            for mob in roster:
                if mob.elite:
                    raise ValueError(
                        f"elite {mob.slug} nel roster boss di {tier.value}: un "
                        "idolo non custodisce varchi (è un PNG, non un boss)"
                    )
        for tabella in self.spawn:
            for voce in tabella.voci:
                if voce.mob.elite:
                    raise ValueError(
                        f"elite {voce.mob.slug} nella tabella di spawn di "
                        f"{tabella.tier.value}: l'idolo si incontra, non spawna"
                    )
        return self


class PianoRisolto(BaseModel):
    """Il piano coi riferimenti SCIOLTI: il cast è inline. La coerenza
    cast⊆budget è imposta per costruzione dal validator: un piano risolto
    incoerente non può esistere. L'Elité non sta MAI nel cast (il cast è il
    vivaio dei mob OSTILI del GM e delle imboscate: l'idolo non ne fa parte —
    vive in libreria e si materializza solo dal canale PNG)."""

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
    territorio: TerritorioRisolto | None = None
    # Il ROSTER PNG del piano (piazzatore P1, 2026-08-17): i personaggi NON
    # ostili che il piazzatore può mettere in scena — riempito dal risolutore
    # per affinità di tag con la libreria (categoria ≠ ordinario, o Elité).
    # NON è cast: niente vincolo di budget (il PNG non è il vivaio ostile) e
    # l'Elité qui PUÒ stare — è esattamente il suo posto. Default vuoto:
    # stagioni risolte storiche invariate.
    png: list[MobAsset] = Field(default_factory=list)

    @property
    def n_stanze(self) -> int:
        """La scala effettiva per l'offline: esplicita o derivata dal cast."""
        return self.stanze if self.stanze is not None else len(self.cast)

    def _controlla_nel_budget(self, mob: MobAsset, dove: str) -> None:
        if mob.grado not in set(self.budget.gradi):
            raise ValueError(f"{dove} fuori budget: {mob.slug} ha grado {mob.grado.value}")
        if mob.archetipo not in set(self.budget.archetipi):
            raise ValueError(f"{dove} fuori budget: {mob.slug} ha archetipo {mob.archetipo}")
        if not set(mob.blocchi) <= set(self.budget.blocchi):
            raise ValueError(f"{dove} fuori budget: {mob.slug} ha blocchi non ammessi")
        if mob.categoria is not CategoriaPng.ORDINARIO:
            # Il PERSONAGGIO non è un incontro (stress-test piazzatore, F3):
            # cast, spawn e boss sono il vivaio OSTILE — un interpellabile o
            # un narratore lì dentro esisterebbe due volte (ostile del reveal
            # E piazzabile dal roster PNG), stesso nome, due corpi.
            raise ValueError(
                f"{dove}: {mob.slug} è un personaggio ({mob.categoria.value}), "
                "non un incontro — vive nel roster PNG, mai nel vivaio ostile"
            )

    @model_validator(mode="after")
    def _cast_nel_budget(self) -> "PianoRisolto":
        for mob in self.cast:
            self._controlla_nel_budget(mob, "cast")
            if mob.elite:
                # Il cast è il vivaio OSTILE (reveal e imboscate): l'idolo non
                # ne fa parte — vive in libreria, canale PNG e basta.
                raise ValueError(
                    f"elite {mob.slug} nel cast: l'idolo non è un incontro "
                    "di combattimento"
                )
        return self

    @model_validator(mode="after")
    def _territorio_coerente(self) -> "PianoRisolto":
        t = self.territorio
        if t is None:
            return self
        # Il CELESTIALE è l'identità del boss di piano: mai nel cast, mai nelle
        # tabelle di spawn (i roster inferiori lo escludono già per costruzione).
        for mob in self.cast:
            if mob.grado is Grado.CELESTIALE:
                raise ValueError(
                    f"celestiale riservato al boss di piano: {mob.slug} nel cast"
                )
        for tabella in t.spawn:
            for voce in tabella.voci:
                self._controlla_nel_budget(voce.mob, f"spawn[{tabella.tier.value}]")
                if voce.mob.grado is Grado.CELESTIALE:
                    raise ValueError(
                        f"celestiale riservato al boss di piano: {voce.mob.slug} "
                        f"nella tabella di spawn {tabella.tier.value}"
                    )
        for tier, roster in t.boss.items():
            for mob in roster:
                self._controlla_nel_budget(mob, f"boss[{tier.value}]")
        archetipi = set(self.budget.archetipi)
        for tabella in t.procedurali:
            fuori = [a for a in tabella.archetipi if a not in archetipi]
            if fuori:
                raise ValueError(
                    f"procedurali[{tabella.tier.value}]: archetipi fuori budget: "
                    + ", ".join(fuori)
                )
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
    # Il pool di loot risolto (D-1: `Stagione.oggetti` se dichiarato, altrimenti
    # tutta la libreria valida) — pronto al freeze come gli archetipi.
    oggetti: list[OggettoAsset] = Field(default_factory=list)
    fabbrica: FabbricaAsset | None = None
    # Le mosse-asset risolte (stessa politica lasca), pronte al freeze.
    mosse: list[MossaAsset] = Field(default_factory=list)


class AssetVista(BaseModel):
    """Una voce dell'elenco libreria (per l'hub/GM mode e l'affinità)."""

    model_config = _FROZEN

    slug: str
    tipo: Literal["stagione", "piano", "mob", "archetipo", "oggetto", "mossa", "fabbrica"]
    etichetta: str
    tags: list[str] = Field(default_factory=list)
    origine: Literal["ufficiale", "locale"] = "ufficiale"
    valido: bool = True
