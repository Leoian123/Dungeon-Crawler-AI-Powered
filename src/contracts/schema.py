"""Schema del contratto AI↔motore (nodo F) — modelli Pydantic in `contracts`.

Sono **dati**, non comportamento (F §2): nessuna logica di dominio, nessun import di
esper/Textual/provider. Lo stesso modello (a) *emette* lo schema dato al meccanismo
nativo di output strutturato del backend e (b) *valida* il candidato nel gate del
motore — un'unica fonte di verità per la forma (F §1, §3.1).

Tre proprietà strutturali, verificabili staticamente (F §2):
  - **Zero campi numerici in `EntitaGenerata`** — niente hp/danno/difesa/durate, e
    niente `livello` (profondità di piano, del motore). I numeri li deriva il motore
    (F-3, §4.2; G-17).
  - **Tutto ciò che ha conseguenza meccanica è un vocabolario chiuso** (F-4): enum
    per Grado/Blocco/TipoAzione/Durata; per gli ARCHETIPI uno slug (`ArchetipoId`)
    la cui chiusura è **per-run** — il registry congelato nella `StagioneAttiva` al
    freeze, contro cui il gate valida (F-6 a runtime). Il nome fuori registry non
    passa MAI il gate: l'autorità resta il motore, la popolazione diventa dato.
    Solo `prosa/nome/descrizione/etichetta/testo` sono testo libero.
  - **Nessun campo per invocare l'anomalia o alzarsi il budget**: lo schema non lo
    offre, e `extra="forbid"` rifiuta qualunque campo non previsto (F-4, §4.3).

I VALORI degli enum sono **SEGNAPOSTO**: i contenuti veri del catalogo sono di
G/Gruppo 2 (F §9). Qui si fissa la *forma* (vocabolari chiusi), non le *voci*.

Dipendenze: solo stdlib + Pydantic (F-2, §3.1).
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .proiezione import SlotEquip

def _senza_docstring(schema: dict) -> None:
    """La docstring resta per chi legge il codice, ma NON viaggia come `description`
    nel JSON schema inviato al provider a ogni chiamata — erano commenti per
    sviluppatori (con riferimenti alle spec interne) che pesavano ~40% dei token di
    input per turno (audit 2026-08-07). Una descrizione PENSATA per l'AI si dichiara
    con `Field(description=...)`: quelle a livello campo non vengono toccate."""
    schema.pop("description", None)


# Config condivisa dei MODELLI: vietare campi extra chiude la porta a un campo con
# cui l'AI proverebbe a invocare l'anomalia o ad alzarsi il budget (F-4, §4.3);
# `json_schema_extra` spoglia la docstring dallo schema esportato.
_CHIUSO = ConfigDict(extra="forbid", json_schema_extra=_senza_docstring)


class SchemaSnello:
    """Mixin degli ENUM del contratto AI: stesso scopo di `_senza_docstring`, per le
    classi che non hanno una `model_config` (la docstring dell'enum finirebbe come
    `description` nella sua voce `$defs`)."""

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        schema = handler(core_schema)
        schema.pop("description", None)
        return schema


# --- Enum del catalogo: vocabolario chiuso (contenuti in G) -------------------

# Slug kebab-case: identità stabile di asset e archetipi (condiviso con contenuti.py).
RE_SLUG = r"^[a-z0-9](?:[a-z0-9-]{0,58}[a-z0-9])?$"

# L'identità di un archetipo NON è più un enum compilato: è uno slug la cui chiusura
# è PER-RUN (il registry archetipi congelato nella stagione al freeze; il gate del
# motore valida l'appartenenza — F-6 a runtime). La forma resta chiusa: pattern
# stretto qui, appartenenza al registry nel gate. Decisione D1 (2026-08): "una riga
# di registry, niente codice" — l'archetipo si CREA come dato, mai come enum.
Slug = Annotated[str, StringConstraints(pattern=RE_SLUG)]
ArchetipoId = Slug


class Grado(SchemaSnello, str, Enum):
    """Vocabolario chiuso del **grado** di un'entità (ex `Rarita`, override Gruppo 2 §1.1).

    Un solo enum AI-facing: l'AI **sceglie un nome**, mai un numero. La mappa
    `Grado → rango:int` (1–6) e gli altri consumatori (moltiplicatore-stat, soglia,
    valore-loot) vivono **lato motore**, a senso unico (catalogo). La parola "rarità"
    sopravvive solo come prosa per "il `Grado` di un'entità". Valori SEGNAPOSTO.
    """

    BRONZO = "bronzo"
    ARGENTO = "argento"
    ORO = "oro"
    PLATINO = "platino"
    LEGGENDARIO = "leggendario"
    CELESTIALE = "celestiale"


class StatId(SchemaSnello, str, Enum):
    """Vocabolario chiuso delle statistiche primarie (Gruppo 2 §2.2): SOLO nomi.

    È vocabolario, non comportamento: i **flag** per stat (visibilità, modificabilità,
    derivazione, prova, sblocco) vivono nel **registry del motore** (`statistiche.py`),
    MAI qui. Set MVP che esercita i tre assi di visibilità (§2.4); valori SEGNAPOSTO.
    """

    FORZA = "forza"
    DESTREZZA = "destrezza"
    COSTITUZIONE = "costituzione"
    INTELLIGENZA = "intelligenza"  # accuratezza magica (Gruppo 2 §5.4); base di acc_eff con Des
    DIFESA = "difesa"          # mitigazione piatta, base 0: canale-modificatori dell'armatura (§5.3)
    SAGGEZZA = "saggezza"      # valore-nascosto, solo-privilegiati (canone DCC)
    FORTUNA = "fortuna"        # esistenza-negata (canone DCC)


class Blocco(SchemaSnello, str, Enum):
    """Le "interfacce" di FNC §5.5: contratti noti. Valori SEGNAPOSTO (contenuti in G).

    Il binding `Blocco → classe componente ECS` vive nel **registry del motore**
    (importa esper), MAI qui (F §3).
    """

    VELENO = "veleno"
    RIGENERAZIONE = "rigenerazione"
    STORDITO = "stordito"
    BRUCIA = "brucia"  # acceso nell'audit 2026-08: il sistema esisteva, il nome no


class TipoDanno(SchemaSnello, str, Enum):
    """Tipo di danno di un attacco — enum chiuso AI-facing (Gruppo 2 tipi §2).

    Stessa famiglia di `Grado`/`Durata`: l'AI lo **dichiara**, il gate-catalogo lo
    **valida**, l'AI non lo **conia** mai. `GENERICO` è il default (untyped): un `Danno`
    senza tipo non incrocia alcuna resistenza → comportamento identico al danno agnostico
    odierno (è ciò che rende il layer dei tipi backward-compatible, DT-6). La gerarchia è
    **dato**, non codice: aggiungere un tipo = **una riga di enum** (+ righe di
    `ResistenzaMod` lato motore), zero righe nel risolutore (DT-2/DT-L1). Roster MVP
    minimale (il resto post); valori SEGNAPOSTO.
    """

    GENERICO = "generico"   # default, untyped: nessuna resistenza vi si applica
    MISCHIA = "mischia"
    FUOCO = "fuoco"
    VELENO = "veleno"


class TipoAzione(SchemaSnello, str, Enum):
    """Spazio d'azione chiuso → mappa su un'azione nota del motore (IC §2.3).

    `SCENDI` e `MUOVI` sono azioni **di scena**: compaiono nel menu SOLO quando la
    mappa (autorità spaziale del motore) le rende vere — una scala nella stanza,
    un'uscita adiacente. L'AI può nominarle nella prosa ma non può concederle (G §8.3):
    le compone il motore dalla scena, mai dal testo.
    """

    COMBATTI = "combatti"
    SCAPPA = "scappa"
    SCENDI = "scendi"
    MUOVI = "muovi"
    # `RIPOSA` è di scena come SCENDI/MUOVI: la compone il motore quando è VERA
    # (stanza senza nemici e nessuno status che lo impedisca), mai l'AI dal testo.
    # Costa tempo — e il tempo, scorrendo, può portare un'imboscata.
    RIPOSA = "riposa"
    # `ATTRAVERSA` (territorio, 2026-08): il passaggio alla zona successiva della
    # spina. Di scena come SCENDI: compare SOLO quando è vero (stanza-passaggio
    # e boss di zona sconfitto) — l'AI può nominarlo, mai concederlo.
    ATTRAVERSA = "attraversa"
    ALTRO = "altro"


class ClasseProva(SchemaSnello, str, Enum):
    """Difficoltà di una prova di abilità: una **classe nominata**, non un numero
    (G §7.2). L'AI **seleziona** la classe inquadrando la prova, PRIMA della
    risoluzione, e non può mutarla dopo; il motore mappa `classe → soglia` e
    **confronta a margine** (G §7.1: nessun tiro).

    "celestiale" è un nome come "leggendario": vocabolario chiuso nel contratto. La
    tabella `classe → soglia` (la formula) e le **ancore** testuali vivono nel
    catalogo del MOTORE (G §7.4), MAI qui. Valori SEGNAPOSTO (contenuti in G).
    """

    # Specchio ESATTO di `Grado`, stesso ordine: la difficoltà di una prova e il grado di
    # un'entità sono la stessa scala nominata (mappa `CLASSE_DA_GRADO`, lato motore). Un
    # membro qui senza la sua foglia §11 è un `KeyError` all'import di `calibrazione`.
    BRONZO = "bronzo"
    ARGENTO = "argento"
    ORO = "oro"
    PLATINO = "platino"
    LEGGENDARIO = "leggendario"
    CELESTIALE = "celestiale"


class Taglia(SchemaSnello, str, Enum):
    """Quanto è grande un'entità (o un'arma): vocabolario CHIUSO, mai un numero.

    Due consumatori lato motore, entrambi §11: `M_TAGLIA` (più piccolo = schivi di più,
    check 1) e la *relazione* fra taglia dell'arma e taglia del portatore (`COEFF_ACC`).
    L'AI sceglie il nome; i coefficienti restano del motore.

    **Invariante di sincronia #7:** ogni `.value` qui deve esistere come chiave in
    `M_TAGLIA` — un membro senza binding è un valore che il gate accetta e il motore non
    sa pesare."""

    COLOSSALE = "colossale"
    ENORME = "enorme"
    GROSSA = "grossa"
    MEDIA = "media"
    PICCOLA = "piccola"
    INFIMA = "infima"


class CategoriaArmatura(SchemaSnello, str, Enum):
    """Quanto è ingombrante un pezzo d'armatura: vocabolario CHIUSO (ADR-1 D5).

    È la leva **spaccata sui due check** che rende leggibile il trade-off tank/dodger:
    la categoria abbassa `coeff_eva` (check 1 — con la piastra addosso schivi meno) e in
    parallelo il pezzo somma a `DIFESA` (check 2 — incassi meno). Una funzione per check,
    nessuna delle due sa dell'altra.

    Sincronia #7: ogni `.value` è una chiave di `M_ARMATURA`."""

    VESTE = "veste"
    LEGGERA = "leggera"
    MEDIA = "media"
    PESANTE = "pesante"


class FasciaCosto(SchemaSnello, str, Enum):
    """Il costo in mana di una mossa, NOMINATO: il numero è la foglia §11
    `MOSSA_FASCIA.costo.<fascia>` — mai nell'asset."""

    GRATUITA = "gratuita"
    ECONOMICA = "economica"
    STANDARD = "standard"
    COSTOSA = "costosa"


class FasciaRicarica(SchemaSnello, str, Enum):
    """I turni di ricarica, NOMINATI (foglia §11 `MOSSA_FASCIA.ricarica.*`)."""

    NESSUNA = "nessuna"
    BREVE = "breve"
    LUNGA = "lunga"


class FasciaPotenza(SchemaSnello, str, Enum):
    """Il moltiplicatore del danno, NOMINATO (foglia §11 `MOSSA_FASCIA.potenza.*`):
    entra UNA volta nel check 2, dentro l'unico arrotondamento (PMF-6.4)."""

    LIEVE = "lieve"
    STANDARD = "standard"
    PESANTE = "pesante"


class FasciaRischio(SchemaSnello, str, Enum):
    """La banda min/max di un danno d'azzardo, NOMINATA (foglia §11
    `MOSSA_FASCIA.rischio.*`)."""

    CONTENUTO = "contenuto"
    SPINTO = "spinto"


class Fascia(SchemaSnello, str, Enum):
    """Il POTERE nominato di un modificatore da oggetto: l'autore (umano o AI)
    sceglie la FASCIA, il motore deriva il numero (§11: fascia × rango del
    grado). Vocabolario chiuso — la linea rossa «l'AI non emette numeri» qui è
    strutturale: nello schema non esiste un campo dove metterli."""

    LIEVE = "lieve"
    MARCATA = "marcata"
    POTENTE = "potente"


class SedeAccessorio(SchemaSnello, str, Enum):
    """Dove si porta un accessorio: **tag di flavour**, non uno slot esclusivo (ADR-1 D6).

    Deliberatamente NON meccanico e NON limitante: gli accessori sono un multiset aperto
    (più anelli, più orecchini), il loro potere sta nei modificatori che portano, non nel
    posto. Estendibile senza conseguenze sul risolutore — è vocabolario, non regola."""

    ORECCHIE = "orecchie"
    NASO = "naso"
    BOCCA = "bocca"
    DITA = "dita"
    COLLO = "collo"
    POLSI = "polsi"
    CAVIGLIE = "caviglie"
    BACINO = "bacino"


class Durata(SchemaSnello, str, Enum):
    """Vocabolario del tempo (J §3.1) — enum chiuso con **ordine totale**.

    NON è un numero (F-14): è una categoria, come `Grado`. L'ordine totale è
    sull'**ordine di dichiarazione** (dal minimo `TURNO` in su), non lessicografico:
    il motore lo mappa a un carico-tick via catalogo (mai nel contratto). Valori e
    carico-tick sono di G/Gruppo 2 (F §9).
    """

    TURNO = "turno"          # minimo = cadenza base (una stanza in esplorazione, J §4)
    UN_ATTIMO = "un_attimo"
    UN_POCHINO = "un_pochino"
    UN_BEL_PO = "un_bel_po"

    @property
    def ordine(self) -> int:
        """Posizione nell'ordine totale (0 = minimo)."""
        return list(type(self).__members__).index(self.name)

    # Ordine totale esplicito sull'ordine di dichiarazione (sovrascrive il confronto
    # lessicografico ereditato da `str`). Solo fra membri di `Durata`.
    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Durata):
            return NotImplemented
        return self.ordine < other.ordine

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Durata):
            return NotImplemented
        return self.ordine <= other.ordine

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Durata):
            return NotImplemented
        return self.ordine > other.ordine

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Durata):
            return NotImplemented
        return self.ordine >= other.ordine


class TierTerritorio(SchemaSnello, str, Enum):
    """La gerarchia TERRITORIALE di un piano-mondo, dal basso: l'ordine di
    dichiarazione È la scala (come `Grado` — e la simmetria è deliberata: 6 tier,
    6 gradi, il grado di un boss è il grado del suo tier, per indice). La mappa
    tier→grado riesposta al motore vive nel catalogo (`GRADO_DA_TIER`), con
    lucchetto di sincronia; qui c'è solo la FORMA (vocabolario chiuso + ordine).
    """

    QUARTIERE = "quartiere"    # ↔ bronzo
    DISTRETTO = "distretto"    # ↔ argento
    CITTA = "citta"            # ↔ oro
    PROVINCIA = "provincia"    # ↔ platino
    PAESE = "paese"            # ↔ leggendario
    PIANO = "piano"            # ↔ celestiale (il boss di piano, e SOLO lui)

    @property
    def ordine(self) -> int:
        """Posizione nell'ordine totale (0 = quartiere)."""
        return list(type(self).__members__).index(self.name)

    @property
    def grado(self) -> "Grado":
        """Il grado del tier, PER INDICE (la simmetria 6↔6 resa forma): è la
        stessa derivazione di `GRADO_DA_TIER` nel catalogo (sincronia F-6)."""
        return list(Grado)[self.ordine]


class Frequenza(SchemaSnello, str, Enum):
    """Quanto spesso una voce di spawn compare — CATEGORIA, mai un peso (F-14).

    L'AI e l'authoring dichiarano la classe; il peso numerico è una foglia §11
    del motore (`PESO_FREQUENZA` in calibrazione), mai nel contratto."""

    COMUNE = "comune"
    INSOLITO = "insolito"
    RARO = "raro"


class ClasseBeneficio(SchemaSnello, str, Enum):
    """Il VANTAGGIO che un'azione libera reclama — enum chiuso, mai testo (F-14).

    È il perno del gate anti-arbitraggio: il giocatore può manipolare la prosa
    quanto vuole, ma un beneficio si ottiene SOLO dichiarandone la classe, e ogni
    classe ha un pavimento di costo di proprietà del motore (§11). L'AI *classifica*
    la richiesta; il conto lo applica il motore. Un'AI ingannata al ribasso non
    regala niente: il pavimento vince in silenzio (mai un retry).

    `NESSUNO` = azione di puro colore (il default: chi non reclama non paga).
    `SVOLTA` = la pretesa di un avanzamento permanente ("maxo la skill"): fuori
    scala per calibrazione — il Sistema presenta la tariffa vera e nega il resto.
    """

    NESSUNO = "nessuno"            # colore: nessun vantaggio reclamato
    RECUPERO = "recupero"          # riposo, medicarsi, riprendere fiato
    LAVORO = "lavoro"              # lavoro manuale: scuoiare, raccogliere, costruire
    ADDESTRAMENTO = "addestramento"  # una sessione di pratica (non la maestria)
    SVOLTA = "svolta"              # pretesa di avanzamento permanente/maestria


# --- Modelli dello schema -----------------------------------------------------

class EntitaGenerata(BaseModel):
    """L'entità proposta dall'AI: SOLO nomi categoriali + flavor testuale.

    NESSUN campo numerico: niente hp/danno/difesa/durate, niente `livello` (F-3,
    §4.2). I numeri li deriva/lega il motore da `(archetipo, grado, livello)`.
    """

    model_config = _CHIUSO

    archetipo: ArchetipoId  # slug: chiusura per-run via registry congelato + gate (F-6)
    grado: Grado
    blocchi: list[Blocco]
    nome: str          # libero (flavor)
    descrizione: str   # libero (flavor)
    # Identità cinematografica (Sit.2, 2026-08): SOLO testo, zero conseguenza
    # meccanica — il dettaglio visivo che resta negli occhi e il tic che rende
    # il mob riconoscibile. Default "" = retro-compatibile (archivi e provider
    # storici non li dichiarano).
    aspetto: str = ""  # libero (flavor): il dettaglio visivo memorabile
    tratto: str = ""   # libero (flavor): l'abitudine/verso che lo distingue
    # RECLUTAMENTO strutturato (D5): lo slug di un mob del CAST del piano corrente.
    # È un NOME da un set chiuso per-run (mai un numero): il gate lo verifica al 4°
    # strato — fuori cast → rifiuto (fallback F-13). None = mob "coniato" dall'AI
    # coi soli campi categoriali (il comportamento storico).
    riferimento: Slug | None = None


class TurnoNarrazione(BaseModel):
    """Il "candidato" della chiamata di narrazione (PLK §2): UNA chiamata `genera`.

    `{ prosa, entità, durata }` — senza `livello` (profondità del motore) e senza
    menu: le azioni possibili le compone la mappa (autorità spaziale), mai l'AI —
    un campo `opzioni` qui era output pagato a ogni chiamata e mai letto.
    `durata` è una categoria chiusa (F-14): sta QUI, non su `Flavor`.
    """

    model_config = _CHIUSO

    prosa: str
    entita: EntitaGenerata
    durata: Durata     # categoria del tempo; il motore la mappa a carico-tick via gate
    # Il vantaggio reclamato dall'azione del giocatore (default = niente): l'AI
    # CLASSIFICA, il motore applica il pavimento di costo (§11) — gate asimmetrico,
    # mai retry. Default per retro-compatibilità (archivi e provider storici).
    beneficio: ClasseBeneficio = ClasseBeneficio.NESSUNO


class Flavor(BaseModel):
    """Schema banale per la chiamata di sola prosa (F §5). NESSUN `durata` (F-1).

    Flavor di combattimento, voce dello showrunner, `Altro`-MVP: output degenere a
    un campo. In combattimento il costo è fisso `TURNO`, cablato nel loop AP (G §2).
    """

    model_config = _CHIUSO

    testo: str


# --- Pipeline GM: schemi degli stadi NON-GATING (G §9.2: fan-out sotto il socket) --

class IntenzioneScena(SchemaSnello, str, Enum):
    """Che tipo di scena l'ideazione propone. Enum chiuso, valori SEGNAPOSTO."""

    SCONTRO = "scontro"
    PROVA = "prova"
    QUIETE = "quiete"
    TRANSIZIONE = "transizione"


class TonoScena(SchemaSnello, str, Enum):
    """Tono narrativo proposto dall'ideazione. Enum chiuso, valori SEGNAPOSTO."""

    IRONICO = "ironico"
    CUPO = "cupo"
    FRENETICO = "frenetico"
    SOSPESO = "sospeso"


class Ideazione(BaseModel):
    """Output dello stadio di IDEAZIONE della pipeline GM — **consultivo** (F-9).

    Alimenta il prompt della chiamata gating, MAI decide stato: nessun campo può
    toccare il World, nessun numero. `durata_proposta` è vocabolario chiuso (J):
    l'AI propone la categoria, il motore dispone i tick. Analogo strutturale di
    `Flavor`: non passa da nessun gate di stato perché non ne ha bisogno.
    """

    model_config = _CHIUSO

    intenzione: IntenzioneScena
    tono: TonoScena
    focus: str                          # una frase consultiva: il cuore della scena
    ganci: list[str] = Field(default_factory=list, max_length=3)
    durata_proposta: Durata


class InquadramentoProva(BaseModel):
    """Inquadramento non-gating di una prova (G §7.1): l'AI SELEZIONA classe e stat
    (enum chiusi), il motore TIRA seeded. Mai un esito, mai una soglia."""

    model_config = _CHIUSO

    classe: ClasseProva
    stat: StatId


# --- Authoring AI della stagione (2026-08-10): schemi del «genera stagione» -----
#
# Chiamate di AUTHORING, non di gioco: l'AI genera il roster dei boss e le
# tabelle di un piano-mondo, il motore li valida coi lint esistenti e li congela
# come asset. ZERO numeri anche qui: il boss dichiara il TIER, mai il grado
# (lo deriva il motore, simmetria 6↔6); i profili restano della calibrazione.

class BossGenerato(BaseModel):
    """UN boss proposto dall'AI di authoring: identità narrativa + selezioni da
    vocabolari chiusi. Il grado NON c'è: lo impone il tier."""

    model_config = _CHIUSO

    slug: Slug
    archetipo: ArchetipoId          # gate: dentro il budget del piano
    tier: TierTerritorio            # il grado lo deriva il motore (GRADO_DA_TIER)
    nome: str
    descrizione: str
    aspetto: str = ""
    tratto: str = ""
    prosa_stanza: str               # la sua scena (il copione offline)
    mosse: list[str] = Field(default_factory=list)   # gate: mosse note
    blocchi: list[Blocco] = Field(default_factory=list)  # gate: dentro il budget


class LottoBossGenerati(BaseModel):
    """Un lotto di boss (≤5 per chiamata: lotti piccoli degradano bene — un item
    respinto non butta la chiamata intera)."""

    model_config = _CHIUSO

    boss: list[BossGenerato] = Field(min_length=1, max_length=5)


class TabellaProceduraleGen(BaseModel):
    """Il materiale per i boss dei tier procedurali (distretto/quartiere):
    nomi × gimmick × archetipi — l'istanza la fa il motore, seeded."""

    model_config = _CHIUSO

    tier: TierTerritorio
    nomi: list[str] = Field(min_length=4, max_length=16)
    gimmick: list[str] = Field(min_length=4, max_length=16)
    archetipi: list[ArchetipoId] = Field(min_length=1)


class VoceSpawnGenerata(BaseModel):
    model_config = _CHIUSO

    mob: Slug                       # gate: un MobAsset esistente
    frequenza: Frequenza = Frequenza.COMUNE  # categoria, mai un peso


class TabellaSpawnGenerata(BaseModel):
    """Una tabella di spawn proposta: voci = mob ESISTENTI + frequenza categoriale."""

    model_config = _CHIUSO

    tier: TierTerritorio
    voci: list[VoceSpawnGenerata] = Field(min_length=1, max_length=12)


class RuoloMob(str, Enum):
    """Il RUOLO di un'entità-mob nel mondo: ostile (bersaglio, il default
    storico) o PNG (personaggio non giocante: esente dal despawn di zona, mai
    trattato da nemico della stanza). NON AI-facing: lo scrive il motore alla
    materializzazione, mai il modello."""

    OSTILE = "ostile"
    PNG = "png"


class EffettoDati(BaseModel):
    """UN effetto di una mossa, come DATO categoriale (GR2 §7, Corsia 2): il
    primitivo è una PAROLA del vocabolario chiuso del motore (`danno`,
    `applica_status`, `danno_variabile` — un primitivo NUOVO è codice, Corsia 3,
    mai un dato più ricco); i parametri sono enum e FASCE, mai numeri.
    Condiviso da `MossaAsset` (libreria) e `MossaAutorata` (AI-facing)."""

    model_config = _CHIUSO

    primitivo: Literal["danno", "applica_status", "danno_variabile"]
    tipo_danno: TipoDanno | None = None       # danno / danno_variabile
    blocco: Blocco | None = None              # applica_status
    potenza: FasciaPotenza | None = None      # danno (default: standard)
    rischio: FasciaRischio | None = None      # danno_variabile (default: contenuto)


class MossaAutorata(BaseModel):
    """UNA mossa proposta dall'AI di authoring: composizione di primitivi chiusi
    + fasce, NESSUN numero per costruzione. Il gate di composizione (PMF-6.4)
    è il validator di `MossaAsset`, applicato alla conversione."""

    model_config = _CHIUSO

    slug: Slug
    etichetta: str
    effetti: list[EffettoDati] = Field(min_length=1, max_length=2)
    costo: FasciaCosto = FasciaCosto.GRATUITA
    ricarica: FasciaRicarica = FasciaRicarica.NESSUNA
    azzardo: bool = False


class LottoMosseAutorate(BaseModel):
    """Un lotto di mosse (≤6 per chiamata)."""

    model_config = _CHIUSO

    mosse: list[MossaAutorata] = Field(min_length=1, max_length=6)


class ModificatoreAutorato(BaseModel):
    """Una voce di potere su un oggetto autorato: stat + FASCIA. Niente numeri."""

    model_config = _CHIUSO

    stat: StatId
    fascia: Fascia


class OggettoAutorato(BaseModel):
    """UN oggetto proposto dall'AI di authoring: identità narrativa + selezioni
    da vocabolari chiusi e FASCE nominate. NESSUN campo numerico PER COSTRUZIONE
    (F-3 strutturale): mitigazione/danno/valori li deriva il motore da
    fascia × grado × categoria alla traduzione in `OggettoAsset`."""

    model_config = _CHIUSO

    slug: Slug
    nome: str
    descrizione: str = ""
    tipo: Literal["armatura", "arma", "accessorio"]
    grado: Grado
    slot: SlotEquip | None = None         # armatura: obbligatorio
    categoria: CategoriaArmatura | None = None
    taglia: Taglia = Taglia.MEDIA
    sede: SedeAccessorio | None = None    # accessorio: obbligatorio
    mosse: list[str] = Field(default_factory=list)   # gate: mosse note (solo accessori)
    modificatori: list[ModificatoreAutorato] = Field(default_factory=list, max_length=3)


class LottoOggettiAutorati(BaseModel):
    """Un lotto di oggetti (≤6 per chiamata: lotti piccoli degradano bene)."""

    model_config = _CHIUSO

    oggetti: list[OggettoAutorato] = Field(min_length=1, max_length=6)


class OggettoGenerato(BaseModel):
    """La VESTIZIONE di un drop GIÀ deciso dal motore (contratto premi, Sit.3):
    l'AI battezza nome/descrizione/aspetto sul `base` fissato. Il gate rifiuta
    un candidato che cambia `base`, altera il `grado` o sposta lo `slot` —
    il verdetto dell'AI è una vestizione, mai una leva (dottrina
    `gate_beneficio`). Fallback: il nome di catalogo."""

    model_config = _CHIUSO

    base: Slug                       # gate: LA fonte del drop, immutabile
    grado: Grado                     # gate: il grado del drop, immutabile
    slot: SlotEquip | None = None    # gate: lo slot della base (ridondanza anti-tamper)
    nome: str
    descrizione: str
    aspetto: str = ""


class SkillGenerata(BaseModel):
    """Il RIBATTEZZO narrativo di una mossa concessa da un premio (Sit.4): la
    mossa VERA resta la voce di catalogo (costi e numeri dal §11, mai da qui).
    `tipo_danno`/`blocco` sono selezioni dichiarative: nell'MVP non mutano la
    meccanica della base — un valore incoerente degrada al solo nome."""

    model_config = _CHIUSO

    mossa_base: str = Field(min_length=1)   # gate: una chiave del catalogo mosse
    nome: str
    descrizione: str = ""
    tipo_danno: TipoDanno | None = None
    blocco: Blocco | None = None


class NemicoSperimentale(BaseModel):
    """Il candidato del BANCO DI PROVA (confronto fra modelli): il **core** di
    `EntitaGenerata` (stessi enum chiusi, da cui il motore deriva le stat REALI)
    + i campi **sperimentali** `drop`/`azioni`, non ancora validati dal motore."""

    model_config = _CHIUSO

    archetipo: ArchetipoId
    grado: Grado
    blocchi: list[Blocco]
    nome: str
    descrizione: str          # stile DCC (ironico/dark-comico)
    drop: list[str]           # SPERIMENTALE: bottino possibile
    azioni: list[str]         # SPERIMENTALE: mosse di combattimento (→ futuro catalogo Effetto)
