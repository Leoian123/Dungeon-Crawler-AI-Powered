"""Proiezione di sola lettura della scheda del protagonista (G §6.6, G-13).

L'AI deve *leggere* lo stato del protagonista per narrarlo ("Carl barcolla, ferito"),
ma non deve mai vedere l'oggetto-scheda **vivo** (i componenti ECS): le farebbe vedere
numeri che potrebbe pretendere di spiegare — e domani negoziare — e legherebbe il
prompt alla shape interna dei componenti (rompendo la membrana `contracts`).

Quindi l'AI riceve un **DTO derivato**: descrittori diegetici (`"ferito"`,
`"avvelenato"`), MAI `hp: 7/30`. È *dato*, non comportamento (IC §2.2): nessun numero,
nessun riferimento al `World` né a entità esper vive. Il motore lo **costruisce** dallo
stato vivo (in `motore`); qui vive solo la **forma**.

È "risolvi prima, narra dopo" applicato allo stato persistente: l'AI narra una *vista*,
non legge il *registro* (G §11).

Dipendenze: solo stdlib + Pydantic (F-2).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

from pydantic import BaseModel, ConfigDict


class SchedaProiezione(BaseModel):
    """Vista di sola lettura della scheda: descrittori diegetici + stat filtrate per
    visibilità (Gruppo 2 §2.4, GR2-9).

    `frozen=True` la rende immutabile (sola lettura davvero); `extra="forbid"` chiude
    la porta a campi introdotti di soppiatto. *Quali* descrittori e *quanto ricca* è la
    proiezione sono contenuto (Gruppo 2); il **fatto** che esista, e che il filtro di
    visibilità sia già applicato a monte, è forma (G §6.6).

    ⚠️ **Membrana (C-3): è solo forma-dato.** Il filtro per `Visibilita` legge il
    registry del MOTORE (`statistiche.REGISTRY_STAT`): il costruttore vive **lato
    motore** (`narrazione.proietta_scheda`) e passa qui mappe **già filtrate**. Questo
    modulo non importa esper né il registry. La proiezione esprime gli esiti del filtro:
      - `primarie` — solo le `PALESE`: `nome → valore effettivo`;
      - `primarie_occulte` — i nomi delle `VALORE_NASCOSTO` (presenza sì, valore no);
      - le `ESISTENZA_NEGATA` non compaiono in nessuno dei due (GR2-9).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    descrittori: tuple[str, ...] = ()
    primarie: Mapping[str, int] = {}
    primarie_occulte: tuple[str, ...] = ()


# --- La scheda del giocatore: skill, equipaggiamento, progressione ---------------
#
# ⚠️ FORMA, non contenuto. Questi DTO dichiarano il CONTRATTO della scheda: cosa un
# host può mostrare e cosa il motore si impegna a dire. Alcuni campi oggi sono
# popolati (le skill vengono dal `Repertorio` + catalogo mosse), altri sono
# DELIBERATAMENTE VUOTI perché il sistema che li riempirà non esiste ancora
# (inventario, oggetti, esperienza). Il contratto esiste lo stesso: quando arriverà
# il contenuto si riempie un campo, non si riscrive un'interfaccia — e la UI che li
# legge oggi (mostrando "nessuno") non cambierà una riga.


class SlotEquip(str, Enum):
    """Gli slot di equipaggiamento: vocabolario CHIUSO (come ogni cosa con
    conseguenza meccanica, F-4). **Un solo enum di slot in tutto il progetto.**

    Aveva due membri (`arma`, `armatura`) perché descriveva le due *leve di geometria*
    che muovono le derivate, non i posti reali dove si indossa qualcosa. Con gli oggetti
    veri servono i nove slot fisici dell'armatura (ADR-1 D5), e la tentazione era
    aggiungere un secondo enum `SlotArmatura` accanto a questo: **due vocabolari di slot
    divergono al primo ritocco** (uno cresce, l'altro no, e la proiezione mostra una
    scheda che non è più il componente). Quindi il vocabolario è uno e i nove slot
    stanno qui dentro; la "famiglia armatura" è il sottoinsieme `SLOT_ARMATURA`.

    `MANO_DX`/`MANO_SX` sono il **layer-armatura** (i guanti), distinto dal **layer
    impugnato** (`ARMA`): guanto e arma convivono sulla stessa mano, non competono.
    Il layer impugnato resta a un mount solo finché la review-armi (ADR-1 D7) non decide
    su off-hand, scudi e due-mani."""

    ARMA = "arma"
    TESTA = "testa"
    BUSTO = "busto"
    BRACCIO_DX = "braccio_dx"
    BRACCIO_SX = "braccio_sx"
    MANO_DX = "mano_dx"
    MANO_SX = "mano_sx"
    GAMBE = "gambe"
    PIEDE_DX = "piede_dx"
    PIEDE_SX = "piede_sx"


# La **famiglia armatura**: i soli slot che entrano nella media pesata di `m_armatura`
# (ADR-1 D5, denominatore fisso). Derivata per esclusione — aggiungere uno slot-armatura
# a `SlotEquip` lo fa entrare qui da solo, mentre un mount impugnato nuovo (off-hand,
# scudo) va escluso ESPLICITAMENTE, che è la parte a cui bisogna pensare.
SLOT_IMPUGNATI: tuple[SlotEquip, ...] = (SlotEquip.ARMA,)
SLOT_ARMATURA: tuple[SlotEquip, ...] = tuple(
    s for s in SlotEquip if s not in SLOT_IMPUGNATI
)


class EquipVista(BaseModel):
    """Uno slot di equipaggiamento come lo vede il giocatore.

    Oggi il motore NON ha oggetti: espone la **categoria di geometria** attiva
    (quella che muove davvero i numeri — `veste`, `naturale`…) e lascia `nome`
    vuoto, che significa "slot vuoto, valgono i default". Quando arriverà
    l'inventario, `nome` porterà l'oggetto e `categoria` resterà la sua
    geometria: nessun campo nuovo, nessuna migrazione della UI."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: SlotEquip
    nome: str = ""        # "" = slot vuoto (nessun oggetto equipaggiato)
    categoria: str = ""   # la chiave di geometria §11 che muove le derivate
    descrizione: str = ""


class SkillVista(BaseModel):
    """Una skill/mossa come la vede il giocatore: cosa costa, se è pronta, perché no.

    `pronta` è la sintesi che la UI usa per abilitare il bottone; `costo_mana`,
    `cd_totale` e `cd_residuo` sono il DETTAGLIO che le fa dire *perché*. Il motore
    resta l'autorità: `pronta` è una fotografia, non un permesso."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chiave: str
    etichetta: str
    descrizione: str = ""
    costo_mana: int = 0
    cd_totale: int = 0
    cd_residuo: int = 0
    pronta: bool = True


class ProgressioneVista(BaseModel):
    """L'avanzamento del personaggio DENTRO la run.

    ⚠️ CONTRATTO VUOTO PER ORA. Non esiste esperienza, non esiste crescita: i campi
    sono a zero e la UI mostrerà una barra ferma. Esiste comunque perché la domanda
    "quanto sono avanzato" è già parte della scheda, e perché il giorno in cui il
    motore comincerà a contare qualcosa non dovrà negoziare un contratto nuovo con
    ogni host già scritto.

    NB: `livello_piano` è la PROFONDITÀ (quanti piani sotto), non un livello di
    personaggio — la distinzione va tenuta ferma qui, dove un host la legge."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    livello_piano: int = 1
    esperienza: int = 0            # sempre 0 finché non esiste una fonte di XP
    esperienza_al_prossimo: int = 0  # 0 = nessuna soglia definita
    punti_da_spendere: int = 0     # 0 = nessuna scelta di crescita pendente


class SchedaVista(BaseModel):
    """Scheda del protagonista per la **UI del giocatore** (non per l'AI).

    A differenza di `SchedaProiezione`, qui i numeri PALESI sono ammessi: il
    giocatore vede i propri HP e le proprie stat — è l'AI che non deve vederli
    (G §6.6). Le regole di visibilità restano quelle del registry, applicate a
    monte dal motore: `primarie` = solo PALESI (valori effettivi), le
    VALORE_NASCOSTO compaiono per nome in `primarie_occulte`, le
    ESISTENZA_NEGATA (fortuna) non compaiono MAI (GR2-9).
    Il costruttore vive lato composition root (`SessioneGioco.scheda()`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    uuid: str
    nome: str
    vivo: bool
    hp: int
    hp_max: int
    descrittori: tuple[str, ...] = ()
    primarie: Mapping[str, int] = {}
    primarie_occulte: tuple[str, ...] = ()
    derivate: Mapping[str, int] = {}
    livello: int = 1
    tick_piano: int = 0

    # --- Risorse, skill, equipaggiamento, progressione (tutti con default: un
    # host che non li legge continua a funzionare, e i costruttori esistenti pure).
    mana: int = 0
    mana_max: int = 0
    skills: tuple[SkillVista, ...] = ()
    equip: tuple[EquipVista, ...] = ()
    # Le FONTI possedute (id di dominio, l'etichetta la risolve l'host dal
    # catalogo): il deposito del canale loot→equip. Default vuoto: un host che
    # non lo legge continua a funzionare.
    zaino: tuple[str, ...] = ()
    progressione: ProgressioneVista = ProgressioneVista()
