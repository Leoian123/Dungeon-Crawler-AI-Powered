"""Il componente-identità del mob — dato puro, modulo FOGLIA (solo contracts + dataclass).

`EntitaMob` vive qui e non in `narrazione.py` perché è anche **persistente**: il registry
dei tag (`persistenza/tag.py`) importa componenti dato-puro, mai i moduli coi sistemi
("la persistenza tocca i dati, mai conosce i sistemi", H §10.5). `narrazione` lo
ri-esporta: i consumatori storici (`from .narrazione import EntitaMob`) non cambiano.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts import Grado, RuoloMob


@dataclass
class EntitaMob:
    """Dato puro dell'entità generata: i campi categoriali scelti dall'AI + flavor +
    la profondità legata dal motore dopo il gate. Le statistiche stanno nel vettore
    `Primarie` (derivate via `stat_eff`, GR2-3) — una sola strada-stat (§16.4), MAI qui.

    `stanza` = la stanza della mappa in cui il mob è registrato (None = non ancora in
    scena). È il DATO da cui si ricostruisce `Mappa.mob_stanza` al load: gli id esper
    non sono mai riferimenti durevoli (H-4), la stanza sì."""

    archetipo: str  # slug del registry archetipi (chiusura per-run, F-6 runtime)
    grado: Grado
    nome: str
    descrizione: str
    livello: int
    stanza: int | None = None
    # Identità cinematografica (Sit.2): flavor puro, default "" → i save storici
    # si deserializzano invariati (campo assente = stringa vuota).
    aspetto: str = ""
    tratto: str = ""
    # Il RUOLO nel mondo (T3): OSTILE = bersaglio (default storico, i save
    # vecchi deserializzano così); PNG = esente dal despawn di zona e mai
    # trattato da nemico della stanza. È identità del mob quanto il grado:
    # campo qui, non componente a parte (un solo dato da tenere in fase).
    ruolo: RuoloMob = RuoloMob.OSTILE
    # ELITÉ: il PNG che tutti idolatrano — IDENTITÀ sopra il comportamento
    # (il ruolo resta PNG). Default False: i save storici deserializzano
    # invariati. Il dialogo lo dice al GM; la mortalità è roba del futuro.
    elite: bool = False
    # Tassonomia + voce (2026-08-16): la categoria decide chi può rompere il
    # divieto del menu (interpellabili), la voce è l'identità PARLATA che i
    # prompt di dialogo/scena vestono. Default retro-compatibili (save storici
    # invariati). `categoria` è il value di `CategoriaPng` (dato jsonable).
    categoria: str = "ordinario"
    voce: str = ""
    # PARLAMENTO (2026-08-16): il tentativo di parlamentare con un OSTILE si fa
    # UNA volta per mob (anti-pesca sociale, gemello dello snodo di scena): il
    # marker persiste col mob — il fallito resta fallito anche dopo un load.
    parlamento_tentato: bool = False
    # La TREGUA del parlamentato (playtest giro 3): True se il gate è stato
    # SUPERATO — chi ti ha ascoltato non ti imbosca (il compositore d'imboscata
    # esclude i suoi omonimi vivi). Default retro-safe come i gemelli.
    parlamento_riuscito: bool = False
    # L'ANCORA DI ZONA (caccia-2, 2026-08-16): la chiave della zona in cui
    # `stanza` vale ("" = piano piatto/legacy). Gli indici di stanza sono
    # per-mappa-di-zona: il PNG — che sopravvive al despawn di zona per
    # esenzione — veniva ritrovato da `png_in_stanza_corrente` in QUALUNQUE
    # zona avesse una stanza di pari indice (menu «Parlamenta» nella zona
    # sbagliata). Default retro-safe: i save storici deserializzano invariati.
    zona: str = ""


@dataclass
class Repertorio:
    """Le mosse che l'entità PORTA (dato nel componente): chiavi del catalogo chiuso
    `mosse.CATALOGO_MOSSE`, mai comportamento. Chi le ESEGUE è il system di
    combattimento (scelta seeded del motore, G-4); chi le POSSIEDE è l'entità.
    Persistente: il repertorio del mob rivelato viaggia nel save."""

    mosse: tuple[str, ...]


def nome_diegetico(entita: int) -> str:
    """Nome per gli eventi di vista: il nome del mob rivelato, `""` per il
    protagonista, «il nemico» per l'effimero senza identità.

    La copia UNICA (registro §4.2-B, chiuso 2026-08-16): viveva identica in
    `combattimento._nome_pubblico` e `status._nome_diegetico` — due copie che
    sarebbero divise al primo ritocco (es. un titolo per l'Elité). Import pigro
    di `Protagonista`: mob resta un modulo foglia."""
    import esper

    em = esper.try_component(entita, EntitaMob)
    if em is not None:
        return em.nome
    from .scheda import Protagonista  # pigro: nessun ciclo mob↔scheda

    return "" if esper.has_component(entita, Protagonista) else "il nemico"
