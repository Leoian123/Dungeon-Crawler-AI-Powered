"""Schema del contratto AI↔motore (nodo F) — modelli Pydantic in `contracts`.

Sono **dati**, non comportamento (F §2): nessuna logica di dominio, nessun import di
esper/Textual/provider. Lo stesso modello (a) *emette* lo schema dato al meccanismo
nativo di output strutturato del backend e (b) *valida* il candidato nel gate del
motore — un'unica fonte di verità per la forma (F §1, §3.1).

Tre proprietà strutturali, verificabili staticamente (F §2):
  - **Zero campi numerici in `EntitaGenerata`** — niente hp/danno/difesa/durate, e
    niente `livello` (profondità di piano, del motore). I numeri li deriva il motore
    (F-3, §4.2; G-17).
  - **Tutto ciò che ha conseguenza meccanica è un enum chiuso** (Archetipo, Grado,
    Blocco, TipoAzione, Durata). Solo `prosa/nome/descrizione/etichetta/testo` sono
    testo libero (F-4).
  - **Nessun campo per invocare l'anomalia o alzarsi il budget**: lo schema non lo
    offre, e `extra="forbid"` rifiuta qualunque campo non previsto (F-4, §4.3).

I VALORI degli enum sono **SEGNAPOSTO**: i contenuti veri del catalogo sono di
G/Gruppo 2 (F §9). Qui si fissa la *forma* (enum chiusi), non le *voci*.

Dipendenze: solo stdlib + Pydantic (F-2, §3.1).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

# Config condivisa: vietare campi extra chiude la porta a un campo con cui l'AI
# proverebbe a invocare l'anomalia o ad alzarsi il budget (F-4, §4.3).
_CHIUSO = ConfigDict(extra="forbid")


# --- Enum del catalogo: vocabolario chiuso (contenuti in G) -------------------

class Archetipo(str, Enum):
    """Vocabolario chiuso degli archetipi. Valori SEGNAPOSTO (contenuti in G)."""

    SLIME = "slime"
    SCHELETRO = "scheletro"
    GOBLIN = "goblin"


class Grado(str, Enum):
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


class StatId(str, Enum):
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


class Blocco(str, Enum):
    """Le "interfacce" di FNC §5.5: contratti noti. Valori SEGNAPOSTO (contenuti in G).

    Il binding `Blocco → classe componente ECS` vive nel **registry del motore**
    (importa esper), MAI qui (F §3).
    """

    VELENO = "veleno"
    RIGENERAZIONE = "rigenerazione"
    STORDITO = "stordito"


class TipoDanno(str, Enum):
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


class TipoAzione(str, Enum):
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
    ALTRO = "altro"


class ClasseProva(str, Enum):
    """Difficoltà di una prova di abilità: una **classe nominata**, non un numero
    (G §7.2). L'AI **seleziona** la classe inquadrando la prova, PRIMA del tiro, e
    non può mutarla dopo; il motore mappa `classe → soglia` (seeded) e risolve.

    "celestiale" è un nome come "leggendario": vocabolario chiuso nel contratto. La
    tabella `classe → soglia` (la formula) e le **ancore** testuali vivono nel
    catalogo del MOTORE (G §7.4), MAI qui. Valori SEGNAPOSTO (contenuti in G).
    """

    BRONZO = "bronzo"
    ARGENTO = "argento"
    ORO = "oro"
    CELESTIALE = "celestiale"


class Durata(str, Enum):
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


# --- Modelli dello schema -----------------------------------------------------

class EntitaGenerata(BaseModel):
    """L'entità proposta dall'AI: SOLO nomi categoriali + flavor testuale.

    NESSUN campo numerico: niente hp/danno/difesa/durate, niente `livello` (F-3,
    §4.2). I numeri li deriva/lega il motore da `(archetipo, grado, livello)`.
    """

    model_config = _CHIUSO

    archetipo: Archetipo
    grado: Grado
    blocchi: list[Blocco]
    nome: str          # libero (flavor)
    descrizione: str   # libero (flavor)


class Opzione(BaseModel):
    """Un'opzione del menu: spazio d'azione chiuso (`tipo`) + etichetta libera."""

    model_config = _CHIUSO

    tipo: TipoAzione   # categoriale, chiuso
    etichetta: str     # flavor, libero


class TurnoNarrazione(BaseModel):
    """Il "candidato" della chiamata di narrazione (PLK §2): UNA chiamata `genera`.

    `{ prosa, entità, opzioni, durata }` — senza `livello` (profondità del motore).
    `durata` è una categoria chiusa (F-14): sta QUI, non su `Flavor`.
    """

    model_config = _CHIUSO

    prosa: str
    entita: EntitaGenerata
    opzioni: list[Opzione]
    durata: Durata     # categoria del tempo; il motore la mappa a carico-tick via gate


class Flavor(BaseModel):
    """Schema banale per la chiamata di sola prosa (F §5). NESSUN `durata` (F-1).

    Flavor di combattimento, voce dello showrunner, `Altro`-MVP: output degenere a
    un campo. In combattimento il costo è fisso `TURNO`, cablato nel loop AP (G §2).
    """

    model_config = _CHIUSO

    testo: str
