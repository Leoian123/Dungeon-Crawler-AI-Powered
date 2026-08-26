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
    World (gli id non si serializzano mai, H-4); il LEGAME mob↔stanza però è dato
    (`EntitaMob.stanza`) e al load `mappa_da_dict` lo ricollega;
  - la mappa persiste nello slot `esplorazione` del save (topologia, stanza corrente,
    visitate) via `mappa_to_dict`/`mappa_da_dict`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable

import esper

from contracts import DiscesaPiano, PlayerSiMuove, TipoAzione, TipoStanza

from .calibrazione import (
    MAPPA_STANZE,
    STANZE_FRAZ_CORRIDOI,
    STANZE_PROB_BAGNO,
)
from .intenti_coda import consuma_messaggi
from .mob import EntitaMob
from .phased import SistemaSoloNarrazione
from .piano import Piano, valida_piano
from .seme import master_seed


@dataclass
class Mappa:
    """Singleton di run: topologia + stato spaziale. `mob_stanza` è runtime-only
    (id di entità vive del World corrente — mai serializzati, H-4; al load si
    ricostruisce dal dato `EntitaMob.stanza`)."""

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


def stampa_tipi(
    piano: Piano,
    rng: random.Random,
    *,
    boss: int | None = None,
    safe_garantita: bool = False,
    prob_safe: float = 0.0,
    prob_gilda: float = 0.0,
) -> None:
    """Stampa i `TipoStanza` sulla topologia — il «Borderlands della mappa»:
    vocabolario chiuso × pescate seeded × vincoli. L'AI non c'entra: narra i
    tipi, mai li sceglie (stessa disciplina di SCENDI/ATTRAVERSA).

    Vincoli: partenza e stanze-scala restano NORMALI (il primo reveal e la
    discesa non sono mai "speciali"); `boss` è imposto dal chiamante (il
    territorio sa qual è la stanza del custode); SAFE ROOM al più una —
    garantita (`safe_garantita`, la quota di spina §11) o a pescata
    (`prob_safe`, il premio del vicolo laterale); BAGNO raro, al più uno;
    CORRIDOIO solo su stanze connettive (grado ≥2), a frazione seeded;
    GILDA DEL TUTORIAL a pescata (`prob_gilda`, i primi piani — playtest
    2026-08-17 F4: senza stampa lo slot del maestro non esisteva mai), al
    più una, pescata IN CODA allo stream così le stampe esistenti restano
    byte-identiche (a `prob_gilda=0` zero pescate extra).
    Le stanze non stampate sono NORMALI per assenza (`Piano.tipi`).

    Va chiamata con un RNG **dedicato** (stream `…:tipi`): la topologia già
    pubblicata resta byte-identica, i replay non si muovono.
    """
    tipi: dict[int, TipoStanza] = {}
    speciali = {piano.partenza} | set(piano.discese)
    if boss is not None:
        tipi[boss] = TipoStanza.BOSS
        speciali.add(boss)
    libere = [s for s in sorted(piano.adiacenze) if s not in speciali]
    if (safe_garantita or (prob_safe > 0 and rng.random() < prob_safe)) and libere:
        scelta = rng.choice(libere)
        tipi[scelta] = TipoStanza.SAFE_ROOM
        libere.remove(scelta)
    if libere and rng.random() < STANZE_PROB_BAGNO:
        scelta = rng.choice(libere)
        tipi[scelta] = TipoStanza.BAGNO
        libere.remove(scelta)
    for stanza in libere:
        if len(piano.adiacenze[stanza]) >= 2 and rng.random() < STANZE_FRAZ_CORRIDOI:
            tipi[stanza] = TipoStanza.CORRIDOIO
    # La gilda VINCE sul corridoio (il corridoio è flavor del dado, la gilda è
    # uno slot promesso): candidate = libere non ancora tipizzate O corridoi.
    # Pescata in coda allo stream: a prob 0 zero pescate extra (stampe storiche
    # byte-identiche); safe room e bagno non si sovrascrivono mai.
    candidate = [s for s in libere
                 if s not in tipi or tipi[s] is TipoStanza.CORRIDOIO]
    if candidate and prob_gilda > 0 and rng.random() < prob_gilda:
        tipi[rng.choice(candidate)] = TipoStanza.GILDA_TUTORIAL
    piano.tipi = tipi


def tipo_di(piano: Piano, stanza: int) -> TipoStanza:
    """Il tipo di una stanza (assente dal dict = NORMALE: save storici inclusi)."""
    return piano.tipi.get(stanza, TipoStanza.NORMALE)


def tipo_stanza_corrente() -> TipoStanza:
    """Il tipo della stanza corrente (NORMALE senza mappa: harness/test legacy)."""
    m = mappa_corrente()
    if m is None:
        return TipoStanza.NORMALE
    return tipo_di(m[1].piano, m[1].stanza_corrente)


def stanza_quieta(tipo: TipoStanza | None = None) -> bool:
    """SAFE ROOM e BAGNO sono quieti PER DESIGN (non per numero): nessun mob al
    reveal, il dado-imboscata non tira — il rifugio è un rifugio e la privacy è
    privacy. Senza argomento legge la stanza corrente."""
    t = tipo if tipo is not None else tipo_stanza_corrente()
    return t in (TipoStanza.SAFE_ROOM, TipoStanza.BAGNO)


def fattore_imboscata_stanza() -> float:
    """Il moltiplicatore del dado-imboscata per la stanza corrente: 0 nei luoghi
    quieti (design), la foglia §11 nei corridoi (passaggio esposto), 1 altrove.
    Il tiro resta del motore (`tira_dado_evento`): qui solo il contesto spaziale."""
    from .calibrazione import STANZE_MOLT_IMBOSCATA_CORRIDOIO

    tipo = tipo_stanza_corrente()
    if stanza_quieta(tipo):
        return 0.0
    if tipo is TipoStanza.CORRIDOIO:
        return float(STANZE_MOLT_IMBOSCATA_CORRIDOIO)
    return 1.0


def minacce_zona() -> float:
    """Le MINACCE del chunk corrente (design utente 2026-08-12): i mob ostili
    VIVI materializzati (il despawn di zona garantisce che siano di QUESTA
    zona) + le stanze non ancora rivelate e non-quiete, SCONTATE dalla foglia
    `IMBOSCATA.peso_non_rivelate` (round 3: a peso pieno l'ingresso in zona
    partiva sopra il riferimento e gli agguati arrivavano a catena — il nemico
    potenziale pesa meno del nemico vero). Ripulire la zona = guadagnarsi il
    riposo; rivelare la abbassa comunque."""
    from contracts import RuoloMob

    from .calibrazione import IMBOSCATA_PESO_NON_RIVELATE

    m = mappa_corrente()
    if m is None:
        return 0.0
    vivi = sum(
        1 for _e, em in esper.get_component(EntitaMob)
        if em.ruolo is RuoloMob.OSTILE
    )
    mappa = m[1]
    non_rivelate = sum(
        1 for s in mappa.piano.adiacenze
        if s not in mappa.visitate and not stanza_quieta(tipo_di(mappa.piano, s))
    )
    return vivi + float(IMBOSCATA_PESO_NON_RIVELATE) * non_rivelate


def fattore_minacce() -> float:
    """«Più nemici ci sono, più è alta la probabilità di imboscata; meno nemici
    ci sono, più è semplice riposare» (decisione utente 2026-08-12): il dado
    scala con le minacce del chunk — a zona ripulita tace. La scala è la
    foglia §11 `IMBOSCATA.minacce_riferimento`: a QUEL numero di minacce vale
    la probabilità base, sotto decresce linearmente, sopra cresce."""
    from .calibrazione import IMBOSCATA_MINACCE_RIFERIMENTO

    if mappa_corrente() is None:
        return 1.0  # harness/legacy senza mappa: il dado resta quello di sempre
    riferimento = max(1.0, float(IMBOSCATA_MINACCE_RIFERIMENTO))
    return minacce_zona() / riferimento


def crea_mappa(rng: random.Random, n_stanze: int | None = None) -> int:
    """Crea il singleton `Mappa` nel World corrente (confine di run, come gli altri
    singleton). La partenza è la stanza iniziale, non ancora visitata: il primo turno
    di narrazione la popola. I tipi sono stampati qui (piani piatti: corridoi e
    bagno; boss e safe room sono concetti del territorio)."""
    piano = genera_topologia(rng, n_stanze)
    stampa_tipi(piano, rng)
    return esper.create_entity(Mappa(piano=piano, stanza_corrente=piano.partenza))


def mappa_corrente() -> tuple[int, Mappa] | None:
    trovate = esper.get_component(Mappa)
    return trovate[0] if trovate else None


def rigenera_mappa(livello: int, n_stanze: int | None = None) -> int:
    """Sostituisce la topologia con quella del piano `livello` (G §8.1).

    Scendere non è cambiare stanza: è **un altro piano**, quindi un'altra mappa. Senza
    questo, il secondo piano riuserebbe la topologia del primo — comprese le stanze già
    visitate e la scala già usata — e "scendere" sarebbe solo un contatore che sale.

    Il seed è **derivato** da `master_seed` + livello, mai dall'orologio: due run con lo
    stesso seme producono gli stessi piani nello stesso ordine, che è la condizione del
    replay (FNC §9). La vecchia mappa viene eliminata: un World con due `Mappa` avrebbe
    due verità spaziali e `mappa_corrente` ne sceglierebbe una a caso."""
    for ent, _ in list(esper.get_component(Mappa)):
        esper.delete_entity(ent, immediate=True)
    return crea_mappa(random.Random(f"{master_seed()}:piano:{livello}"), n_stanze)


def collega_discesa_mappa(bus, stanze_per_livello=None) -> Callable[[DiscesaPiano], None]:
    """Registra la rigenerazione della mappa su `DiscesaPiano` (canale bus, in-run).
    Ritorna l'handler registrato: è il valore con cui il guscio deregistra al teardown.

    Vive qui e non nel guscio perché **la mappa possiede la propria topologia**: il
    guscio osserva i terminali, non ricostruisce lo spazio di gioco. `stanze_per_livello`
    è una funzione `livello → n_stanze | None` che l'host fornisce dal contenuto (il
    motore non conosce la libreria); assente → la scala di calibrazione.

    ⚠️ Registrato in-run, va **deregistrato al teardown**: il bus è process-global e
    sopravvive alla run (E/ACV §5.2)."""
    def _su_discesa(evento: DiscesaPiano) -> None:
        # Un piano-mondo scende nella PRIMA zona della sua spina; i piani piatti
        # rigenerano la topologia storica. Import locale: mappa↔territorio non
        # si importano in testa (la mappa resta l'autorità DENTRO la zona).
        from .territorio import avvia_territorio

        if avvia_territorio(livello=evento.piano):
            return
        n = stanze_per_livello(evento.piano) if stanze_per_livello is not None else None
        rigenera_mappa(evento.piano, n)

    bus.registra(DiscesaPiano, _su_discesa)
    return _su_discesa


# --- Lettura di scena (la verità della stanza corrente) ------------------------

def stanza_visitata() -> bool:
    m = mappa_corrente()
    return m is not None and m[1].stanza_corrente in m[1].visitate


def segna_visitata() -> None:
    m = mappa_corrente()
    if m is not None:
        m[1].visitate.add(m[1].stanza_corrente)


def registra_mob(entita: int) -> None:
    """Registra il nemico rivelato nella stanza corrente (il reveal della narrazione).

    Oltre alla voce runtime in `mob_stanza` (id vivo), la stanza è STAMPATA su
    `EntitaMob.stanza`: è il dato persistente da cui il load ricollega mob↔stanza
    (gli id esper non sopravvivono al round-trip, H-4)."""
    m = mappa_corrente()
    if m is not None:
        m[1].mob_stanza[m[1].stanza_corrente] = entita
        em = esper.try_component(entita, EntitaMob)
        if em is not None:
            em.stanza = m[1].stanza_corrente


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


def png_in_stanza_corrente() -> int | None:
    """L'entità-PNG presente nella stanza corrente, o `None`. Scansione ECS su
    `EntitaMob` (T3): i PNG non passano da `mob_stanza` (che è il registro dei
    NEMICI di scena) e `EntitaMob.stanza` è già il dato persistente (H-4) —
    nessun registro nuovo da tenere in fase."""
    from contracts import RuoloMob

    m = mappa_corrente()
    if m is None:
        return None
    stanza = m[1].stanza_corrente
    # L'ancora di ZONA (caccia-2): gli indici di stanza sono per-mappa-di-zona
    # e il PNG sopravvive al despawn per esenzione — senza questo filtro veniva
    # ritrovato in QUALUNQUE zona con una stanza di pari indice. Sul piano
    # piatto (nessun territorio) la chiave è "" e il filtro è identità.
    from .territorio import stato_territorio

    stato = stato_territorio()
    chiave_zona = stato.zona_corrente if stato is not None else ""
    # L'ancora di PIANO (stress-test piazzatore, F2): le chiavi di zona si
    # RIPETONO tra piani («citta/0» esiste sul piano 1 e sul 2) e la discesa
    # non elimina i PNG del piano lasciato (esenzione dal despawn) — senza
    # questo filtro il manager del piano 1 era un fantasma interpellabile
    # nella zona omonima del piano 2.
    from .piano import livello_corrente

    livello = livello_corrente()
    for ent, em in esper.get_component(EntitaMob):
        if (em.ruolo is RuoloMob.PNG and em.stanza == stanza
                and em.zona == chiave_zona and em.livello == livello):
            return ent
    return None


def dettagli_mob_corrente() -> EntitaMob | None:
    """Il componente `EntitaMob` del mob della stanza corrente (`None` se
    assente): il gemello intero di `nome_mob_corrente` — per chi (l'apertura
    dello scontro) vuole descrizione/aspetto/tratto oltre al nome."""
    ent = mob_corrente()
    if ent is None:
        return None
    return esper.try_component(ent, EntitaMob)


def nome_mob_corrente() -> str:
    """Il nome diegetico del mob della stanza corrente ("" se assente): la VERITÀ
    è il componente `EntitaMob`, non un appunto dell'host (che dopo un load o un
    cache-hit sarebbe stantio — audit 2026-08)."""
    em = dettagli_mob_corrente()
    return em.nome if em is not None else ""


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
    `stanza` è il bersaglio per `MUOVI`; `zona` la destinazione (chiave) per le
    DEVIAZIONI di `ATTRAVERSA` (None = avanti sulla spina)."""

    tipo: TipoAzione
    etichetta: str
    stanza: int | None = None
    zona: str | None = None


# --- Degradi di composizione: la scena tollera un World parziale, ma non TACE ---
#
# Comporre il menu è una LETTURA e non deve mai esplodere: gli harness montano
# World parziali (senza fase, senza protagonista, senza territorio) e i singleton
# assenti sollevano. Ma un `except` muto qui è il posto peggiore dove metterlo —
# è la funzione che decide COSA IL GIOCATORE PUÒ FARE, e un guasto vi si
# manifesta come «l'opzione non c'era», indistinguibile dal comportamento
# corretto. Quindi: si tollera, e si REGISTRA. Chiave = il punto di lettura, così
# il registro resta limitato ai punti di composizione e non cresce con la run.
_DEGRADI_SCENA: dict[str, tuple[str, int]] = {}


def degradi_scena() -> dict[str, tuple[str, int]]:
    """I degradi registrati componendo la scena: `punto -> (errore, conteggio)`.

    Superficie di DIAGNOSI (test e host): su un World completo deve restare
    vuota — è il lucchetto che trasforma «l'opzione è sparita» in un fatto
    osservabile invece che in un silenzio."""
    return dict(_DEGRADI_SCENA)


def azzera_degradi_scena() -> None:
    """Svuota il registro (i test lo azzerano nel setup)."""
    _DEGRADI_SCENA.clear()


def _lettura_tollerante(punto: str, fn, default):
    """Esegue una lettura di composizione tollerando il World parziale, e
    registrando il degrado. Mai usata per SCRIVERE: solo per comporre il menu."""
    try:
        return fn()
    except Exception as exc:
        errore = f"{type(exc).__name__}: {exc}"
        _, conteggio = _DEGRADI_SCENA.get(punto, ("", 0))
        _DEGRADI_SCENA[punto] = (errore, conteggio + 1)
        return default


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
        # Il menu DICE chi c'è (playtest round 2: rivisitare la stanza del mob
        # congedato dava un «Combatti» cieco): il nome è verità del World.
        nome = nome_mob_corrente()
        con_mob: list[OpzioneScena] = [
            OpzioneScena(
                tipo=TipoAzione.COMBATTI,
                etichetta=f"Combatti — {nome}" if nome else "Combatti",
            ),
            OpzioneScena(tipo=TipoAzione.SCAPPA, etichetta="Scappi"),
        ]
        # PARLAMENTA con l'OSTILE (2026-08-16): la voce compare solo se il
        # tentativo non è mai stato speso (uno per mob, il marker persiste).
        # Il GATE — margine di carisma vs classe del grado — lo tira il motore
        # alla scelta, mai qui: comporre è una lettura.
        def _parlamentabile() -> bool:
            from .scena import puo_parlamentare

            return puo_parlamentare(mob_corrente())

        if _lettura_tollerante("parlamento", _parlamentabile, False):
            con_mob.append(OpzioneScena(
                tipo=TipoAzione.PARLAMENTA,
                etichetta=f"Parlamenta — {nome}" if nome else "Parlamenta",
            ))
        return tuple(con_mob)
    opzioni: list[OpzioneScena] = []
    # PARLAMENTA col PNG INTERPELLABILE (2026-08-16): solo le categorie che
    # rompono il divieto del menu (maestro di gilda, manager — il verbale
    # 2026-08-10 resta la regola per gli ordinari, GM-pilotati; il narratore
    # parla senza replica e non si interpella). Nessun gate: il PNG ascolta.
    def _png_da_interpellare():
        from .png import png_interpellabile_in_stanza

        ent = png_interpellabile_in_stanza()
        if ent is None:
            return None
        return esper.try_component(ent, EntitaMob)

    em_png = _lettura_tollerante("png_interpellabile", _png_da_interpellare, None)
    if em_png is not None:
        opzioni.append(OpzioneScena(
            tipo=TipoAzione.PARLAMENTA, etichetta=f"Parlamenta — {em_png.nome}",
        ))
    if scala_presente():
        opzioni.append(OpzioneScena(tipo=TipoAzione.SCENDI, etichetta="Scendi la scala"))
    # ATTRAVERSA (territorio): il varco verso la zona successiva — compare SOLO
    # quando è VERO (stanza-passaggio, boss battuto, nessun nemico). Import
    # locale: la mappa resta l'autorità dentro la zona, il territorio sopra.
    from .territorio import (
        attraversamento_consentito,
        e_di_spina,
        zona_corrente,
        zona_di_spina_del_tier,
        zona_successiva,
        zone_laterali,
    )

    varco = _lettura_tollerante("varco", attraversamento_consentito, False)
    if varco:
        from .piano import livello_corrente

        prossima = zona_successiva(livello_corrente())
        dove = prossima.tier.value if prossima is not None else "oltre"
        opzioni.append(OpzioneScena(
            tipo=TipoAzione.ATTRAVERSA, etichetta=f"Attraversa: verso {dove}"
        ))
    # DEVIAZIONI (Fase 6): dalla PARTENZA della zona, le sorelle laterali (zone
    # lazy: nascono dal loro seed alla prima entrata) o il RITORNO sulla spina.
    def _deviazioni() -> list[OpzioneScena]:
        from .piano import livello_corrente
        from .territorio import insegna_laterale

        fuori: list[OpzioneScena] = []
        zona = zona_corrente()
        alla_partenza = (
            zona is not None and m[1].stanza_corrente == m[1].piano.partenza
        )
        if not alla_partenza:
            return fuori
        livello = livello_corrente()
        if e_di_spina(zona, livello):
            for laterale in zone_laterali(livello):
                # L'etichetta è DIEGETICA: prima portava l'indice interno
                # (`percorso[-1]`) fra parentesi — «Deviazione: quartiere vicino
                # (0)» — cioè un numero di struttura dati stampato al giocatore.
                # L'insegna disambigua le sorelle restando dentro la finzione.
                fuori.append(OpzioneScena(
                    tipo=TipoAzione.ATTRAVERSA,
                    etichetta=f"Deviazione: {insegna_laterale(laterale)}",
                    zona=laterale.chiave,
                ))
        else:
            rientro = zona_di_spina_del_tier(zona.tier, livello)
            if rientro is not None:
                fuori.append(OpzioneScena(
                    tipo=TipoAzione.ATTRAVERSA,
                    etichetta="Torna sulla via principale",
                    zona=rientro.chiave,
                ))
        return fuori

    opzioni.extend(_lettura_tollerante("deviazioni", _deviazioni, []))
    # RIPOSA compare solo quando è VERA (stanza sicura + downtime lecito, J §5):
    # come SCENDI/MUOVI, la compone il motore dalla scena, mai l'AI dal testo.
    from .tempo import puo_downtime  # locale: nessun ciclo mappa↔tempo

    downtime = _lettura_tollerante("downtime", puo_downtime, False)
    if downtime:
        # A risorse PIENE «Riposa» era un «niente» selezionabile (round 3): la
        # voce si compone solo se c'è qualcosa da recuperare — HP o mana sotto
        # il massimo derivato. Stessa dottrina di RIPOSA: un'opzione compare
        # quando è VERA.
        def _c_e_da_recuperare() -> bool:
            from .derivate import max_hp, max_mana
            from .scheda import Mana, protagonista as _protagonista

            pent, _marker, scheda = _protagonista()
            mana = esper.try_component(pent, Mana)
            return (
                scheda.punti_vita < max_hp(pent)
                or (mana is not None and mana.attuale < max_mana(pent))
            )

        # Default `True`: se la lettura degrada resta il comportamento storico
        # (la voce c'è) — un degrado non deve TOGLIERE al giocatore un'opzione
        # che il gate precedente ha già dichiarato lecita.
        downtime = _lettura_tollerante("recupero", _c_e_da_recuperare, True)
    if downtime:
        opzioni.append(OpzioneScena(tipo=TipoAzione.RIPOSA, etichetta="Riposa"))
    # APRI BOX (nodo O2): SOLO in SAFE ROOM (ratifica 2026-08-26 — il bagno è
    # privacy, la safe room è il rifugio attrezzato), SOLO se c'è una box in
    # coda e la fabbrica può onorarla — l'opzione compare quando è VERA.
    def _etichetta_box() -> str:
        from .fabbrica import fabbrica_attiva
        from .obiettivi import prossima_box

        if tipo_stanza_corrente() is not TipoStanza.SAFE_ROOM:
            return ""
        box = prossima_box()
        if box is None or fabbrica_attiva() is None:
            return ""
        return (
            f"Apri box — {box.categoria.capitalize()} "
            f"di {box.grado.capitalize()}"
        )

    etichetta_box = _lettura_tollerante("box", _etichetta_box, "")
    if etichetta_box:
        opzioni.append(
            OpzioneScena(tipo=TipoAzione.APRI_BOX, etichetta=etichetta_box)
        )
    # ASPETTA (la valvola di J §6, playtest 2026-08-12): un tick secco per far
    # scorrere gli status. Composta quando è VERA — e coi DANNOSI addosso è
    # l'unica voce di downtime (il veleno blocca Riposa, non Aspetta).
    from .tempo import puo_passare_turno

    aspetta = _lettura_tollerante("passa_turno", puo_passare_turno, False)
    if aspetta:
        opzioni.append(OpzioneScena(tipo=TipoAzione.PASSA, etichetta="Aspetta"))
    for stanza in uscite():
        opzioni.append(
            OpzioneScena(tipo=TipoAzione.MUOVI, etichetta=f"Vai: stanza {stanza}", stanza=stanza)
        )
    return tuple(opzioni)


# --- Persistenza: lo slot `esplorazione` del save (H) --------------------------

def mappa_to_dict() -> dict | None:
    """La mappa come dict JSON-safe per lo slot `esplorazione` (topologia + posizione +
    visitate). Gli ID dei mob (runtime) NON si salvano qui: i mob viaggiano come
    entità persistenti e il legame stanza↔mob è il dato `EntitaMob.stanza`."""
    m = mappa_corrente()
    if m is None:
        return None
    mappa = m[1]
    return {
        "partenza": mappa.piano.partenza,
        "adiacenze": {str(k): list(v) for k, v in mappa.piano.adiacenze.items()},
        "discese": sorted(mappa.piano.discese),
        # Solo i tipi DICHIARATI (assente = NORMALE): il save resta piccolo e i
        # load storici senza chiave migrano gratis.
        "tipi": {str(k): v.value for k, v in sorted(mappa.piano.tipi.items())},
        "stanza_corrente": mappa.stanza_corrente,
        "visitate": sorted(mappa.visitate),
    }


def mappa_da_dict(dati: dict) -> int:
    """Ricostruisce il singleton `Mappa` dal dict dello slot `esplorazione` (load).

    `mob_stanza` (id runtime, mai serializzati — H-4) si RICOLLEGA dai dati: le entità
    con `EntitaMob.stanza` valorizzata sono i mob di scena persistiti (i caduti sono
    stati eliminati dal World a fine scontro, quindi non rinascono)."""
    tipi: dict[int, TipoStanza] = {}
    for k, v in dati.get("tipi", {}).items():
        try:
            tipi[int(k)] = TipoStanza(v)
        except ValueError:
            pass  # vocabolario di una versione futura: assente = NORMALE (H-12,
            #       degrado — mai un crash a World già ricostruito)
    piano = Piano(
        partenza=int(dati["partenza"]),
        adiacenze={int(k): [int(x) for x in v] for k, v in dati["adiacenze"].items()},
        discese={int(x) for x in dati["discese"]},
        tipi=tipi,
    )
    # I PNG restano fuori dal re-link (T3): un PNG in `mob_stanza` verrebbe
    # trattato da nemico della stanza (menu Combatti, varco chiuso) al load.
    from contracts import RuoloMob

    mob_stanza = {
        em.stanza: ent
        for ent, em in esper.get_component(EntitaMob)
        if em.stanza is not None and em.ruolo is not RuoloMob.PNG
    }
    return esper.create_entity(
        Mappa(
            piano=piano,
            stanza_corrente=int(dati["stanza_corrente"]),
            visitate={int(x) for x in dati["visitate"]},
            mob_stanza=mob_stanza,
        )
    )
