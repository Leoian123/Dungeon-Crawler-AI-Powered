"""Snapshot di stato per la vista — **input di rendering**, non verità (IC §2.2).

L'adattatore di presentazione rende ciò che il motore gli consegna già confezionato:
prosa, opzioni del menu, descrittori di stato (HP/status/budget), fase corrente. È un
**DTO** che attraversa la membrana, **rimpiazzato in blocco** a ogni emissione e **mai
accumulato né diffato** lato vista (C-4): la fonte di verità resta il `World`.

Niente renderable di Rich, niente widget Textual, niente riferimenti al `World`: solo
dati semplici (IC §2.2). Dipendenze: solo stdlib + Pydantic (come tutto `contracts`).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from .schema import Durata, TipoAzione


class Terminale(str, Enum):
    """Come una run FINISCE (E-8). Vocabolario chiuso, e vive QUI perché è la
    domanda che ogni host deve poter fare senza guardare dentro il motore.

    Prima stava in `guscio.macchina` e l'unico modo di leggerlo era un attributo
    privato: un host non poteva distinguere «sono sceso di un piano» da «ho vinto
    la run» — distinzione che col multi-piano diventa la differenza fra continuare
    e chiudere la partita. Gli esiti di un singolo SCONTRO (vittoria, fuga) non
    sono qui: quelli sono `CombatResolved`."""

    SCONFITTA = "sconfitta"                   # permadeath: death-check seeded (G-11)
    PIANO_COMPLETATO = "piano_completato"     # l'ultima discesa: la run è vinta
    USCITA_VOLONTARIA = "uscita_volontaria"   # salva-ed-esci: la run riprenderà


class OpzioneVista(BaseModel):
    """Una voce del menu a opzioni discrete (IC §1.2): indice + etichetta + tipo chiuso.

    Il giocatore la sceglie per **indice** (→ `PlayerChoseOption(indice)`, IC §2.3); il
    `tipo` è categoriale (mai testo grezzo). L'`etichetta` è flavour, da rendere a video.

    `abilitata=False` = voce MOSTRATA ma non giocabile ora (una mossa senza mana o in
    ricarica): l'host la disegna spenta invece di farla sparire — gli indici restano
    stabili fra snapshot e il giocatore vede *perché* non può. È COSMESI: l'autorità
    resta il motore, che rifiuta comunque la scelta non pagabile.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    indice: int
    etichetta: str
    tipo: TipoAzione
    abilitata: bool = True


class SnapshotVista(BaseModel):
    """Lo stato corrente confezionato per il render (sostituito in blocco, C-4).

    - `prosa`: testo della narrazione/flavour da appendere allo scroll;
    - `opzioni`: il menu discreto corrente (vuoto ⇒ "in attesa di un turno");
    - `stato`: descrittori diegetici per il pannello (es. `("ferito", "avvelenato")`);
    - `fase`: `"narrazione" | "combattimento"` (per il titolo/contesto del pannello);
    - `terminale`: **come è finita la run**, `None` finché è in corso;
    - `profondita`: a che piano si è ORA (sale con ogni discesa).

    ⚠️ `terminale` è il campo che permette a un host di distinguere «sono sceso di
    un piano» da «ho vinto». Prima non esisteva: dopo la morte lo snapshot serviva
    ancora un menu giocabile, e l'unico modo di sapere che la run era finita era
    leggere un attributo privato del guscio. Col multi-piano quella distinzione
    diventa la differenza fra proseguire e chiudere la partita — per questo il
    campo nasce PRIMA della feature che lo richiede."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prosa: str = ""
    opzioni: tuple[OpzioneVista, ...] = ()
    stato: tuple[str, ...] = ()
    fase: str = "narrazione"
    terminale: Terminale | None = None
    profondita: int = 1

    @property
    def run_conclusa(self) -> bool:
        """La run è finita (in qualunque modo): l'host deve chiudere, non proseguire."""
        return self.terminale is not None


# --- Pipeline GM: il MESSAGGIO per turno verso l'host (input di rendering, C-4) ---

class TempoVista(BaseModel):
    """L'idea temporale del turno: contatore interno + tick. I tick vengono SEMPRE
    dal calcolatore del motore (`carico_tick`), MAI dall'AI (J §13)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tick_correnti: int   # tempo di piano a fine turno
    tick_spesi: int      # carico-tick della durata disposta dal motore
    etichetta: str       # forma diegetica ("un pochino", "20–30 minuti")


class GradoEsito(str, Enum):
    """Quanto bene (o male) è andata una prova — **derivato dal margine**, non scelto.

    Vive qui e non in `schema.py` perché **non è AI-facing**: l'AI inquadra la prova
    (sceglie la `ClasseProva`), il motore la risolve e *deriva* questo grado dallo
    scarto fra stat effettiva e soglia. L'AI lo riceve per vestirlo di prosa, mai per
    negoziarlo — è l'altra metà di "risolvi prima, narra dopo".

    I gradi esistono perché una prova deterministica senza sfumature sarebbe un
    interruttore: il margine dice *di quanto* ce l'hai fatta, ed è lì che sta la
    texture che il dado dava gratis (G §7.1, "gradi di successo dal margine")."""

    FALLIMENTO_GRAVE = "fallimento_grave"
    FALLIMENTO = "fallimento"
    SUCCESSO = "successo"
    SUCCESSO_PIENO = "successo_pieno"


class ProvaVista(BaseModel):
    """La prova del turno, SOLO se esiste. `esito=None` = inquadrata, non risolta;
    l'esito, quando c'è, l'ha **calcolato** il MOTORE (a margine, senza tiro), mai l'AI.

    `margine` e `grado` sono il dettaglio che rende raccontabile l'esito ("di un soffio"
    vs "senza nemmeno provarci"); `esito` resta il booleano di sempre, come lettura di
    compatibilità per gli host già scritti."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    classe: str
    stat: str
    esito: bool | None = None
    margine: int | None = None
    grado: GradoEsito | None = None


class MessaggioGM(BaseModel):
    """Il messaggio del GM per un turno di narrazione (sostituito in blocco, C-4).

    Obblighi strutturali (pipeline GM): SEMPRE `dove`+`come` (contestualizzazione),
    SEMPRE `tempo` (contatore + tick dal motore), SEMPRE `snapshot`; `prova` SOLO se
    esiste. `prosa` è la versione limata (o la bozza uscita dal gate se la limatura
    è degradata). Non è verità: la fonte resta il World.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    prosa: str
    dove: str
    come: str
    tempo: TempoVista
    snapshot: tuple[str, ...] = ()
    prova: ProvaVista | None = None
    opzioni: tuple[OpzioneVista, ...] = ()
    fallback: bool = False


class StimaAzione(BaseModel):
    """Stima DETERMINISTICA del costo di un'azione per la finestra di conferma.

    `tick` viene dal calcolatore del tempo (`carico_tick(durata)`) — l'LLM non stima
    MAI la spesa di tempo. `skill_riferimento` è il SEAM del modulatore per-skill:
    dichiarato, non ancora implementato (None nell'MVP)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    durata: Durata
    tick: int
    forbice: str                        # es. "20–30 minuti" (tabella di calibrazione)
    skill_riferimento: str | None = None


class RiepilogoAzione(BaseModel):
    """La finestra di conferma EDITABILE: 'Stai per…, corretto?' + stima precisa.

    `testo_proposto` è ciò che il giocatore può correggere prima dell'immissione;
    `contesto` è il dove+come della scena corrente."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    testo_proposto: str
    contesto: str
    stima: StimaAzione


class FattiScontro(BaseModel):
    """I FATTI di uno scontro risolto dall'istanza di combattimento (deterministica):
    entrano nel fascicolo del primo turno GM successivo perché l'AI li VESTA
    (risolvi prima, narra dopo — FNC §5.2). Selezione di fatti, mai stat vive."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vittoria: bool
    turni: int
    hp_persi: int
    nemico: str = ""
    fuga: bool = False  # disimpegno riuscito a scontro aperto (FNC §4)
