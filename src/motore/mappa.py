"""Mappa del piano: l'**autorità spaziale** del motore (G §8; G-18).

La `Mappa` è lo strumento con cui il SISTEMA dispone tutto ciò che è geograficamente
rilevante: la topologia delle stanze (il `Piano` di piano.py, finora dormiente), la
stanza corrente, le stanze visitate, i nemici presenti e le interazioni strutturali
(la scala = `DiscesaPiano`). Lo **stato-scena del turno** è la lettura della mappa
sulla stanza corrente: da lì il motore **compone le opzioni** del menu
(`componi_opzioni_scena`) — l'AI narra e popola, la mappa dispone (G §8.3: la parola
"scala" nella prosa non concede nulla; conta il primitivo sulla mappa).

Proprietà:
  - topologia **generata dal motore, seeded** e validata completabile (`valida_piano`,
    G-18): almeno una scala raggiungibile, sempre;
  - il movimento è un intento (`PlayerSiMuove`) consumato da `SistemaMovimento`
    (solo-narrazione, Canale A): adiacenza e assenza di ingaggio le verifica il
    motore — un intento non valido è consumato senza effetto;
  - i **nemici** registrati per stanza sono riferimenti runtime a entità vive del
    World (mai persistiti: al save restano fuori, la stanza si ripopola);
  - la mappa persiste nello slot `esplorazione` del save (topologia, stanza corrente,
    visitate) via `mappa_to_dict`/`mappa_da_dict`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import esper

from contracts import PlayerSiMuove, TipoAzione

from .calibrazione import MAPPA_STANZE
from .intenti_coda import consuma_messaggi
from .phased import SistemaSoloNarrazione
from .piano import Piano, valida_piano


@dataclass
class Mappa:
    """Singleton di run: topologia + stato spaziale. `mob_stanza` è runtime-only
    (id di entità vive del World corrente — mai serializzati, H-4)."""

    piano: Piano
    stanza_corrente: int
    visitate: set[int] = field(default_factory=set)
    mob_stanza: dict[int, int] = field(default_factory=dict)


# --- Generazione (seeded, motore-owned) ----------------------------------------

def genera_topologia(rng: random.Random, n_stanze: int | None = None) -> Piano:
    """Topologia seeded: catena 0..n-1 + un ramo trasversale, scala nell'ultima stanza.

    Passa SEMPRE dal gate di completabilità (`valida_piano`, G-18): per costruzione la
    catena rende la scala raggiungibile; il gate resta come cintura di sicurezza."""
    n = int(n_stanze if n_stanze is not None else MAPPA_STANZE)
    n = max(2, n)
    adiacenze: dict[int, list[int]] = {i: [] for i in range(n)}
    for i in range(n - 1):
        adiacenze[i].append(i + 1)
        adiacenze[i + 1].append(i)
    if n >= 4:  # un ramo trasversale seeded (scorciatoia), per non essere un corridoio
        a = rng.randrange(0, n - 2)
        b = rng.randrange(a + 2, n)
        if b not in adiacenze[a]:
            adiacenze[a].append(b)
            adiacenze[b].append(a)
    piano = Piano(partenza=0, adiacenze=adiacenze, discese={n - 1})
    validato = valida_piano(piano)
    assert validato is not None  # ripara=True: mai None
    return validato


def crea_mappa(rng: random.Random, n_stanze: int | None = None) -> int:
    """Crea il singleton `Mappa` nel World corrente (confine di run, come gli altri
    singleton). La partenza è la stanza iniziale, non ancora visitata: il primo turno
    di narrazione la popola."""
    piano = genera_topologia(rng, n_stanze)
    return esper.create_entity(Mappa(piano=piano, stanza_corrente=piano.partenza))


def mappa_corrente() -> tuple[int, Mappa] | None:
    trovate = esper.get_component(Mappa)
    return trovate[0] if trovate else None


# --- Lettura di scena (la verità della stanza corrente) ------------------------

def stanza_visitata() -> bool:
    m = mappa_corrente()
    return m is not None and m[1].stanza_corrente in m[1].visitate


def segna_visitata() -> None:
    m = mappa_corrente()
    if m is not None:
        m[1].visitate.add(m[1].stanza_corrente)


def registra_mob(entita: int) -> None:
    """Registra il nemico rivelato nella stanza corrente (il reveal della narrazione)."""
    m = mappa_corrente()
    if m is not None:
        m[1].mob_stanza[m[1].stanza_corrente] = entita


def rimuovi_mob() -> None:
    """Deregistra il nemico dalla stanza corrente (solo la mappa, non l'entità)."""
    m = mappa_corrente()
    if m is not None:
        m[1].mob_stanza.pop(m[1].stanza_corrente, None)


def dissolvi_mob() -> None:
    """Disimpegno riuscito (FNC §5.3): l'incontro non si apre e il nemico della stanza
    si dissolve — entità eliminata E deregistrata (nessun reveal orfano nel World)."""
    ent = mob_corrente()
    if ent is not None:
        esper.delete_entity(ent, immediate=True)
    rimuovi_mob()


def mob_corrente() -> int | None:
    """L'entità-nemico viva nella stanza corrente, o None. Auto-pulisce i riferimenti
    stale (nemico eliminato dal ciclo di vita del combattimento)."""
    m = mappa_corrente()
    if m is None:
        return None
    mappa = m[1]
    ent = mappa.mob_stanza.get(mappa.stanza_corrente)
    if ent is None:
        return None
    if not esper.entity_exists(ent):
        mappa.mob_stanza.pop(mappa.stanza_corrente, None)
        return None
    return ent


def scala_presente() -> bool:
    m = mappa_corrente()
    return m is not None and m[1].stanza_corrente in m[1].piano.discese


def uscite() -> tuple[int, ...]:
    m = mappa_corrente()
    if m is None:
        return ()
    return tuple(m[1].piano.adiacenze.get(m[1].stanza_corrente, ()))


def discesa_consentita() -> bool:
    """Gate della discesa: senza mappa (harness/test legacy) la discesa resta libera;
    con la mappa serve la **scala nella stanza corrente** (G §8.1/§8.3)."""
    m = mappa_corrente()
    if m is None:
        return True
    return scala_presente()


# --- Movimento: intento → sistema (Canale A, solo-narrazione) ------------------

def muovi(stanza: int) -> bool:
    """Sposta nella stanza `stanza` se adiacente e senza nemico che ingaggia.
    Ritorna True se il movimento è avvenuto. Il motore dispone: niente teletrasporto,
    niente fuga gratis (con un nemico vivo serve SCAPPA, FNC §5.3)."""
    m = mappa_corrente()
    if m is None:
        return False
    mappa = m[1]
    if mob_corrente() is not None:
        return False
    if stanza not in mappa.piano.adiacenze.get(mappa.stanza_corrente, ()):
        return False
    mappa.stanza_corrente = stanza
    return True


class SistemaMovimento(SistemaSoloNarrazione):
    """Consuma `PlayerSiMuove` (solo in NARRAZIONE) e applica il movimento sulla mappa.
    Un intento non valido (non adiacente, nemico presente) è consumato senza effetto."""

    def run(self, dt: int) -> None:
        for intento in consuma_messaggi(PlayerSiMuove):
            muovi(intento.stanza)


# --- Composizione della scena: le opzioni le dispone la mappa ------------------

@dataclass(frozen=True)
class OpzioneScena:
    """Un'azione legale nella scena corrente, composta dal MOTORE dalla mappa.
    `stanza` è il bersaglio per `MUOVI` (None altrimenti)."""

    tipo: TipoAzione
    etichetta: str
    stanza: int | None = None


def componi_opzioni_scena() -> tuple[OpzioneScena, ...]:
    """Il menu di narrazione come **verità della scena** (mai cablato nel port):

    - stanza non ancora visitata → `()` (l'host deve chiedere un turno di narrazione);
    - nemico vivo → COMBATTI / SCAPPA (l'ingaggio blocca il movimento);
    - altrimenti → SCENDI se c'è la scala + MUOVI per ogni uscita.
    Senza mappa ritorna `()` (nessuna scena da comporre)."""
    m = mappa_corrente()
    if m is None or not stanza_visitata():
        return ()
    if mob_corrente() is not None:
        return (
            OpzioneScena(tipo=TipoAzione.COMBATTI, etichetta="Combatti"),
            OpzioneScena(tipo=TipoAzione.SCAPPA, etichetta="Scappi"),
        )
    opzioni: list[OpzioneScena] = []
    if scala_presente():
        opzioni.append(OpzioneScena(tipo=TipoAzione.SCENDI, etichetta="Scendi la scala"))
    for stanza in uscite():
        opzioni.append(
            OpzioneScena(tipo=TipoAzione.MUOVI, etichetta=f"Vai: stanza {stanza}", stanza=stanza)
        )
    return tuple(opzioni)


# --- Persistenza: lo slot `esplorazione` del save (H) --------------------------

def mappa_to_dict() -> dict | None:
    """La mappa come dict JSON-safe per lo slot `esplorazione` (topologia + posizione +
    visitate). I mob (runtime, effimeri) NON si salvano: la stanza si ripopola."""
    m = mappa_corrente()
    if m is None:
        return None
    mappa = m[1]
    return {
        "partenza": mappa.piano.partenza,
        "adiacenze": {str(k): list(v) for k, v in mappa.piano.adiacenze.items()},
        "discese": sorted(mappa.piano.discese),
        "stanza_corrente": mappa.stanza_corrente,
        "visitate": sorted(mappa.visitate),
    }


def mappa_da_dict(dati: dict) -> int:
    """Ricostruisce il singleton `Mappa` dal dict dello slot `esplorazione` (load)."""
    piano = Piano(
        partenza=int(dati["partenza"]),
        adiacenze={int(k): [int(x) for x in v] for k, v in dati["adiacenze"].items()},
        discese={int(x) for x in dati["discese"]},
    )
    return esper.create_entity(
        Mappa(
            piano=piano,
            stanza_corrente=int(dati["stanza_corrente"]),
            visitate={int(x) for x in dati["visitate"]},
        )
    )
