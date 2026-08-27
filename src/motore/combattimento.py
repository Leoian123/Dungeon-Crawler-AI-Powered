"""Loop di combattimento: AP, iniziativa, decisione nemici, risolutore a due check,
escalation, death-check, ciclo di vita delle entità effimere (G §2, §6.2; Gruppo 2
§6/§7/§8; G-1/3/4/11; GR2-10…15; FNC §6.3).

Tutto deterministico e **seeded** (FNC §9). **Nessun LLM nel percorso di risoluzione**
(G-4): questo modulo non importa né chiama il provider. L'unica casualità del percorso
base è il **check 1**, che pesca **una sola volta per colpo** dall'**unico** stream RNG
seeded (`StatoCombattimento.rng`); il check 2 e il layer dei tipi pescano **zero** volte.

I *numeri* (`s`, `F`, `δ`, `g`, `MIN_COLPO`, soglia di crollo, cap-resistenze, formula-madre)
sono `§11` e vivono in `calibrazione.py`, importati qui — la **forma** è completa.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import esper

from contracts import (
    ClasseProva,
    ColpoInferto,
    CombatResolved,
    EncounterStarted,
    MortePersonaggio,
    StatId,
    StatusApplicato,
    StileAttacco,
    TipoDanno,
    CrolloDungeon,
    TurnoSaltato,
)

from .azione import ApplicaStatus, Azione, Danno
from .azzardo import EffettoAzzardo, risolvi_effetto_azzardo_con_faccia
from .catalogo import REGISTRY_BLOCCHI, classe_da_grado, rango_grado
from .calibrazione import (
    AP_MAX_MVP,
    CROLLO_INCREMENTO,
    DANNO_BASE,
    DELTA_BANDA,
    F_AUTOHIT,
    G_GRAZE,
    MARGINE_FUGA_PULITA,
    MIN_COLPO,
    MULT_MAX,
    MULT_MIN,
    R_SOGLIA_CROLLO,
    S_CONTEST,
    primarie_da_scalari,
)
from .derivate import acc_eff_di, atk_eff, def_eff, eva_eff, max_hp
from .mob import EntitaMob, Repertorio, nome_diegetico
from .modificatori import Resistenze
from .mosse import MOSSE_DEFAULT, azione_da_mossa, mossa_di, mosse_concesse
from .phased import SistemaSempreAttivo, SistemaSoloCombattimento
from .prove import margine_prova
from .scheda import ActionPoint, Mana, Protagonista, Scheda, assicura_mana, protagonista
from .statistiche import Primarie, stat_eff
from .status import TRASMISSIBILI, Stordito, afflizione, afflizione_da, applica_status
from .turno import azzera_turno_attivo, segna_turno_attivo

# `DANNO_BASE` (witness storico del floor positivo del danno, G-L1) vive in `calibrazione.py`
# (riesposto via l'import sopra): oggi il floor reale è nel check 2, ma il contratto
# "ogni colpo che connette fa progredire lo stato" resta vero.


# --- Componenti di combattimento (dato puro, ESP §1) --------------------------

@dataclass
class Nemico:
    """Marker di un combattente nemico, con il suo **ciclo di vita** (FNC §6.3).

    `arruolato=False` (default) → nemico SPAWNATO all'ingaggio: entità interamente
    effimera, distrutta su `CombatResolved`. `arruolato=True` → mob di scena **già
    vivo nel World** (rivelato dalla narrazione, legato alla stanza da
    `EntitaMob.stanza`): su `CombatResolved` è effimero solo il *ruolo* di nemico —
    se sopravvive allo scontro (fuga, FNC §4) l'entità RESTA in scena e si limita a
    perdere i componenti di combattimento. Distruggerla anche da viva renderebbe la
    fuga migliore della vittoria (stanza svuotata a costo zero) e consumerebbe il
    cast del piano."""

    arruolato: bool = False


@dataclass
class PuntiVita:
    """HP dei nemici (placeholder Gruppo 2). Il protagonista tiene gli HP in `Scheda`."""

    attuali: int
    massimi: int


@dataclass
class Ricariche:
    """Cooldown per chiave di mossa, **effimero per-scontro** (come `Combattente`).

    Fuori dallo scontro non esiste: i cd si azzerano da soli alla chiusura e non
    entrano MAI nel save (non è nel registry dei tag). Un solo proprietario in
    scrittura: `SistemaTurnoCombattimento` — lo decrementa a inizio turno del
    possessore e lo arma quando la mossa viene risolta."""

    per_mossa: dict[str, int] = field(default_factory=dict)


@dataclass
class Combattente:
    """Stato di combattimento di un partecipante (protagonista o nemico).

    `chiave_ordine` è la **chiave stabile seeded** (ordine di spawn) per il tiebreak
    d'iniziativa — MAI l'id di entità esper (sequenziale e riciclato, G-3/§6.3). L'AP **non**
    vive qui: è `ActionPoint`, componente posseduto per-entità (single-owner, guida §6.1).
    """

    destrezza: int
    chiave_ordine: int


@dataclass
class SpecNemico:
    """Specifica di un nemico da materializzare (composta a monte dall'AI/placeholder)."""

    destrezza: int
    punti_vita: int


@dataclass
class PianoIncontro:
    """Composizione dell'incontro, preparata in narrazione (AI a monte, §5.1).

    Il motore la materializza su `EncounterStarted`. `seed` borda il nondeterminismo
    della risoluzione (FNC §9). Due sorgenti di nemici, componibili:
      - `nemici`: spec per scalari (percorso storico, primarie da proxy);
      - `arruolate`: **entità già vive nel World** (il reveal della stanza, col
        profilo calibrato completo: Primarie/Corredo/Resistenze) — l'arruolamento
        aggiunge SOLO i componenti effimeri di combattimento, il nemico combattuto
        È quello rivelato.
    """

    nemici: list[SpecNemico]
    seed: int
    arruolate: list[int] = field(default_factory=list)


@dataclass
class StatoCombattimento:
    """Stato del giro di combattimento (singleton effimero). Un solo proprietario:
    `SistemaTurnoCombattimento`."""

    ordine: list[int]              # iniziativa: id entità in ordine di attivazione
    indice: int
    round: int
    prossima_chiave: int           # contatore stabile per `chiave_ordine` (spawn order)
    rng: random.Random             # UNICO stream RNG seeded del motore (decisioni nemici + check 1)
    turni_scontro: int = 0         # turni-combattente risolti (contatore cieco dell'escalation, §8)
    crollo: int = 0                # danno inevitabile corrente dell'escalation (cresce oltre la soglia)
    fuga_richiesta: bool = False   # il prossimo turno del protagonista tenta la FUGA (FNC §4)
    mossa_richiesta: str | None = None  # la mossa SCELTA dal giocatore per il suo prossimo turno
    # FOTOGRAFIE all'apertura (nodo O, titoli mid-run): i fatti da impresa si
    # catturano quando i nemici sono ancora leggibili — alla chiusura sono morti.
    hp_iniziali_prot: int = 0      # per `senza_graffi` sull'esito
    grado_massimo: str = ""        # il grado più alto fra i nemici ("" = scalari)
    custode_presente: bool = False  # il custode di zona IN PERSONA è nello scontro


# --- Iniziativa (G-3): destrezza desc, tiebreak su chiave stabile seeded -------

def calcola_iniziativa(combattenti: list[tuple[int, int, int]]) -> list[int]:
    """Ordina per destrezza DECRESCENTE; tiebreak su `chiave_ordine` CRESCENTE.

    `combattenti` = lista di `(entita, destrezza, chiave_ordine)`. La chiave di
    ordinamento NON include `entita` (id esper): solo destrezza e chiave stabile.
    """
    ordinati = sorted(combattenti, key=lambda c: (-c[1], c[2]))
    return [entita for entita, _destrezza, _chiave in ordinati]


# --- Decisione dei nemici (G-4): motore, seeded, deterministica ----------------

def decidi_azione_nemico(
    rng: random.Random,
    bersagli: list[int],
    mosse: tuple[str, ...] = ("attacco", "attacco_pesante"),
) -> tuple[int, str] | None:
    """Sceglie (bersaglio, mossa) in modo deterministico dal RNG seeded del motore.

    Euristiche reali (scelta del bersaglio, quando usare un blocco) = contenuto
    Gruppo 2; qui un placeholder seeded. **Mai** l'LLM (§2.3).
    """
    if not bersagli:
        return None
    bersaglio = rng.choice(bersagli)
    mossa = rng.choice(mosse)
    return bersaglio, mossa


# --- Helper di stato/HP -------------------------------------------------------

def stato_combattimento() -> tuple[int, StatoCombattimento] | None:
    trovati = esper.get_component(StatoCombattimento)
    if not trovati:
        return None
    return trovati[0]


def infliggi_danno(entita: int, danno: int) -> None:
    """Applica danno via il proprietario UNICO della mutazione HP (`salute.muovi_hp`):
    la risoluzione «dove vivono gli HP» e la politica di clamp stanno in un posto solo."""
    from .salute import muovi_hp  # pigro: salute risolve su questo modulo (PuntiVita)

    muovi_hp(entita, -danno)


def _e_vivo(entita: int) -> bool:
    if not esper.entity_exists(entita):
        return False
    scheda = esper.try_component(entita, Scheda)
    if scheda is not None:
        return scheda.vivo and scheda.punti_vita > 0
    pv = esper.try_component(entita, PuntiVita)
    if pv is not None:
        return pv.attuali > 0
    return True


def spawn_nemico(*, destrezza: int, punti_vita: int) -> int:
    """Crea un nemico effimero con la prossima `chiave_ordine` stabile. NON tocca
    l'ordine d'iniziativa: lo gestisce il chiamante (materializzazione o rinforzi).

    Dota il nemico di un vettore `Primarie` (GR2-10, 2b-E) — costruito dalla formula-madre
    `primarie_da_scalari` — così atk/def/eva/acc derivano **identiche** al protagonista
    (`stat_eff`, nessuna seconda strada). `PuntiVita` resta il **pool vivo** del nemico;
    `Primarie[COSTITUZIONE]` è la fonte di **mitigazione** (`def_eff`) — doppio ruolo. Le
    entità di combattimento sono effimere → escluse dal save (come da Gr2 §16.2)."""
    st = stato_combattimento()
    if st is None:
        raise RuntimeError("spawn_nemico richiede uno StatoCombattimento attivo")
    _ent_stato, stato = st
    chiave = stato.prossima_chiave
    stato.prossima_chiave += 1
    ent = esper.create_entity(
        Nemico(arruolato=False),  # nato per lo scontro: muore con lo scontro
        Combattente(destrezza=destrezza, chiave_ordine=chiave),
        ActionPoint(ap=AP_MAX_MVP, ap_max=AP_MAX_MVP),
        Ricariche(),
        Primarie(valori=primarie_da_scalari(destrezza=destrezza, punti_vita=punti_vita)),
        PuntiVita(attuali=punti_vita, massimi=punti_vita),
    )
    assicura_mana(ent)  # dopo le Primarie: il massimo deriva dall'Intelligenza
    return ent


def arruola_entita(entita: int) -> int:
    """Arruola un'entità GIÀ viva del World (il mob rivelato nella stanza) come nemico.

    Aggiunge SOLO i componenti effimeri di combattimento: `Nemico`, `Combattente`
    (destrezza dal fold — GR2-3), `ActionPoint`, `PuntiVita` (pool = `max_hp` derivato
    dalla SUA Costituzione). Le sue `Primarie`/`Corredo`/`Resistenze` restano: le
    derivate del risolutore leggono il profilo calibrato vero. Su `CombatResolved`
    l'entità NON viene distrutta se è ancora viva: `Nemico(arruolato=True)` la marca
    come mob di scena, e lo smontaggio la congeda invece di eliminarla (FNC §4: la
    fuga interrompe lo scontro, non cancella il nemico dalla stanza).

    Le **ferite restano**: un mob già ferito (scontro interrotto da una fuga) viene
    riarruolato col suo `PuntiVita`, non col pool pieno — altrimenti fuggire sarebbe
    il modo gratuito di rigenerare il nemico."""
    st = stato_combattimento()
    if st is None:
        raise RuntimeError("arruola_entita richiede uno StatoCombattimento attivo")
    _ent_stato, stato = st
    chiave = stato.prossima_chiave
    stato.prossima_chiave += 1
    esper.add_component(entita, Nemico(arruolato=True))
    esper.add_component(
        entita, Combattente(destrezza=stat_eff(entita, StatId.DESTREZZA), chiave_ordine=chiave)
    )
    esper.add_component(entita, ActionPoint(ap=AP_MAX_MVP, ap_max=AP_MAX_MVP))
    esper.add_component(entita, Ricariche())
    assicura_mana(entita)  # anche i mob pagano le mosse forti (Int bassa → poche volte)
    if esper.try_component(entita, PuntiVita) is None:
        hp = max_hp(entita)
        # LA TEMPRA DEL CUSTODE (playtest 2026-08-12: il boss di quartiere era
        # più gracile dei suoi gregari): il custode di zona AL PRIMO arruolamento
        # riceve il pool moltiplicato (`BOSS.molt_hp`, §11 — tarabile da
        # console) E MAI sotto il miglior gregario del tier (round 3: il molt
        # sull'archetipo gracile non bastava — 12×1.5=18 restava sotto il Fante
        # da 24). Solo alla CREAZIONE del pool: il custode ferito e riarruolato
        # (ritirata) tiene le sue ferite come tutti.
        from .territorio import (
            boss_sconfitto,
            pavimento_hp_custode,
            stanza_corrente_e_del_boss,
            zona_corrente,
        )

        zona = zona_corrente()
        if (zona is not None and stanza_corrente_e_del_boss()
                and not boss_sconfitto(zona)):
            from .calibrazione import BOSS_MOLT_HP
            from .piano import livello_corrente

            hp = max(hp, round(hp * float(BOSS_MOLT_HP)),
                     pavimento_hp_custode(livello_corrente()))
        esper.add_component(entita, PuntiVita(attuali=hp, massimi=hp))
    return entita


def _congeda(entita: int) -> None:
    """Toglie a un mob ARRUOLATO sopravvissuto i soli componenti di combattimento:
    smette di essere un nemico ingaggiato, resta l'entità di scena.

    `PuntiVita` NON viene tolto di proposito — è la ferita che il mob si porta dietro
    fino al prossimo ingaggio (`arruola_entita` lo riusa). `ActionPoint` e `Mana` sì:
    sono persistenti (registry dei tag), e un mob fuori scontro non deve portarli nel
    save. `Ricariche` è effimero: i cooldown non sopravvivono allo scontro."""
    for componente in (Nemico, Combattente, ActionPoint, Mana, Ricariche):
        if esper.has_component(entita, componente):
            esper.remove_component(entita, componente)


def _nemici_vivi() -> list[int]:
    return [ent for ent, _ in esper.get_component(Nemico) if _e_vivo(ent)]


def _classe_fuga() -> ClasseProva:
    """La classe di prova che lo scontro impone a chi vuole scappare: quella del
    **grado più alto** fra i nemici vivi (il più pericoloso detta il prezzo).

    I nemici **da scalari** (spawn di test/harness, senza `EntitaMob`) non hanno un
    grado: ripiegano su `BRONZO`, cioè il comportamento storico bit-per-bit — così
    l'apertura non regredisce silenziosamente ciò che già funzionava."""
    gradi = [
        em.grado for ent in _nemici_vivi()
        if (em := esper.try_component(ent, EntitaMob)) is not None
    ]
    if not gradi:
        return ClasseProva.BRONZO
    return classe_da_grado(max(gradi, key=rango_grado))


def _tutti_combattenti_vivi() -> list[int]:
    """Tutti i combattenti vivi (nemici + protagonista) — bersagli dell'escalation (§8)."""
    vivi = _nemici_vivi()
    pent, _marker, pscheda = protagonista()
    if pscheda.vivo and pscheda.punti_vita > 0:
        vivi.append(pent)
    return vivi


def _nome_pubblico(entita: int) -> str:
    """Nome diegetico per gli eventi di vista: delega alla copia UNICA
    (`mob.nome_diegetico` — era duplicata con `status._nome_diegetico`)."""
    return nome_diegetico(entita)


def _rango_sorgente(entita: int) -> int:
    """Rango dell'applicatore per gli effetti-status (copiato dal GRADO del mob,
    G §4.3); 1 per chi non è un mob rivelato (protagonista, nemici-da-scalari)."""
    em = esper.try_component(entita, EntitaMob)
    return rango_grado(em.grado) if em is not None else 1


def _hp_di(entita: int) -> tuple[int, int]:
    """(attuali, massimi) via il proprietario unico (`salute.hp_di`); (0, 0) per
    chi non ha HP — era la QUINTA copia di «dove vivono gli HP», scovata dal
    lucchetto di sincronia mentre il registro ne contava quattro."""
    from .salute import hp_di

    return hp_di(entita) or (0, 0)


def nemici_in_scontro() -> list[tuple[str, int, int]]:
    """`(nome, hp, hp_max)` dei nemici VIVI dello scontro — per i descrittori
    dell'host (il giocatore vede chi affronta e quanto gli resta)."""
    voci: list[tuple[str, int, int]] = []
    for ent, _marker in esper.get_component(Nemico):
        if not _e_vivo(ent):
            continue
        attuali, massimi = _hp_di(ent)
        voci.append((_nome_pubblico(ent) or "il nemico", attuali, massimi))
    return voci


def richiedi_fuga() -> None:
    """Segna che il PROSSIMO turno del protagonista tenterà la fuga (FNC §4): la
    rotazione resta del sistema-turno (un solo proprietario), la prova la tira lui."""
    st = stato_combattimento()
    if st is not None:
        st[1].fuga_richiesta = True


def mosse_di(entita: int) -> tuple[str, ...]:
    """Le mosse che l'entità PORTA: le innate dal `Repertorio` (assente/vuoto →
    `MOSSE_DEFAULT`) più quelle CONCESSE dalle fonti registrate nel seam del
    catalogo (`mosse.registra_fonte_mosse` — derivate a ogni lettura, mai
    scritte nel repertorio persistente, che le renderebbe innate dopo un
    save/load). È la fonte unica per il menu dell'host e per la validazione
    della scelta; il risolutore non sa CHI concede."""
    rep = esper.try_component(entita, Repertorio)
    base = tuple(rep.mosse) if rep is not None and rep.mosse else MOSSE_DEFAULT
    concesse = tuple(m for m in mosse_concesse(entita) if m not in base)
    return base + concesse


def cooldown_residuo(entita: int, chiave: str) -> int:
    """Turni che mancano alla ricarica della mossa (0 = pronta). Senza `Ricariche`
    (fuori scontro) è sempre 0: il componente è effimero per costruzione."""
    ric = esper.try_component(entita, Ricariche)
    return ric.per_mossa.get(chiave, 0) if ric is not None else 0


def mossa_pagabile(entita: int, chiave: str) -> bool:
    """La mossa è nel catalogo, non è in ricarica e c'è mana per pagarla.

    È la stessa domanda che si fanno il menu (per disabilitare) e il risolutore
    (per rifiutare): una sola definizione, mai due che divergono."""
    mossa = mossa_di(chiave)     # unico lookup: anche le mosse-asset congelate
    if mossa is None:
        return False
    if cooldown_residuo(entita, chiave) > 0:
        return False
    if mossa.costo_mana > 0:
        mana = esper.try_component(entita, Mana)
        # Chi non ha il pool non lancia: assente ≠ illimitato.
        if mana is None or mana.attuale < mossa.costo_mana:
            return False
    return True


def richiedi_mossa(chiave: str) -> bool:
    """Il PROSSIMO turno del protagonista userà la mossa `chiave` (la scelta del
    giocatore, da menu CHIUSO — il gemello di `richiedi_fuga`). Valida catalogo e
    Repertorio: una chiave estranea è rifiutata (`False`) e non tocca lo stato —
    il motore dispone, l'host propone."""
    st = stato_combattimento()
    if st is None or mossa_di(chiave) is None:
        return False
    pent, _marker, _scheda = protagonista()
    if chiave not in mosse_di(pent) or not mossa_pagabile(pent, chiave):
        return False
    st[1].mossa_richiesta = chiave
    return True


def prossimo_attivo_e_protagonista() -> bool:
    """PEEK (senza mutare la rotazione): il prossimo combattente vivo è il
    protagonista? Replica il salto-morti del sistema-turno; fuori scontro → True.
    Serve all'host per risolvere in un solo comando l'intero giro dei nemici."""
    st = stato_combattimento()
    if st is None:
        return True
    _ent, stato = st
    n = len(stato.ordine)
    if n == 0:
        return True
    indice = stato.indice
    for _ in range(n):
        indice = (indice + 1) % n
        candidato = stato.ordine[indice]
        if _e_vivo(candidato):
            return esper.has_component(candidato, Protagonista)
    return True


# --- Risolutore a due check (Gruppo 2 §6; GR2-11; layer tipi DT-5/6/7) ----------
# Modello Mordheim: check 1 (il *se*, stocastico-ma-seeded a banda+graze) → check 2 (il
# *quanto*, deterministico). Funzioni pure module-level, testabili in isolamento.

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def esito_contest(acc: float, eva: float, rng: random.Random) -> float:
    """Cuore puro del check 1: contest `acc` vs `eva` a banda, esito a tre vie (GR2-11).

    Ritorna `m ∈ {1.0, G_GRAZE, 0.0}` (pieno / graze / schivata). **Sotto la banda** (`eva <
    acc/F`) è **auto-hit deterministico** (`m=1`, **zero pescate**); dentro la banda pesca
    **una sola volta** dall'unico stream seeded. I bordi della banda graze sono **clampati**
    nella finestra dei floor gemelli (preserva `P(danno)` e `P(schivata piena) ≥ MIN_COLPO`).

    Funzione di `(acc, eva)` (scala-invariante al rapporto, Bradley–Terry): separa la *forma
    del contest* dalla *derivazione* delle due magnitudini (`acc_eff_di`/`eva_eff`), così il
    property-test del vincolo accoppiato (§11) la esercita coi due scalari direttamente."""
    if eva < acc / F_AUTOHIT:
        return 1.0                                     # auto-hit: zero pescate
    P = _clamp(acc ** S_CONTEST / (acc ** S_CONTEST + eva ** S_CONTEST), MIN_COLPO, 1 - MIN_COLPO)
    lo = _clamp(P - DELTA_BANDA / 2, MIN_COLPO, 1 - MIN_COLPO)
    hi = _clamp(P + DELTA_BANDA / 2, MIN_COLPO, 1 - MIN_COLPO)
    u = rng.random()                                   # UNA sola estrazione per colpo (FNC §9)
    return 1.0 if u < lo else (G_GRAZE if u < hi else 0.0)


def check1(att: int, ber: int, rng: random.Random,
           stile: StileAttacco = StileAttacco.FISICO) -> float:
    """Check 1 a livello-entità: deriva l'accuratezza DELLO STILE del colpo
    (`acc_eff_di(att, stile)`: FISICO mira con Destrezza, MAGICO con Intelligenza —
    selettore-dato, mai un ramo) e `eva_eff(ber)` (da `stat_eff`, GR2-3), poi delega il
    contest a `esito_contest`. Con la geometria di default dell'MVP (nudo/taglia
    media) `eva ≪ acc/F` → **auto-hit deterministico** per tutti; la forma stocastica si
    attiva solo quando un'entità porta dati d'evasione (seam gear, post-MVP)."""
    return esito_contest(acc_eff_di(att, stile), eva_eff(ber), rng)


def mult_resistenza(ber: int, tipo: TipoDanno) -> float:
    """Moltiplicatore del layer dei tipi (DT-5/6/7): aggrega le resistenze che **matchano**
    il tipo dell'attacco. **Assenza = identità** (`mult=1.0`): nessun `Resistenze`, o nessun
    `ResistenzaMod` con `contro` pari al tipo → danno identico al percorso senza tipi. **Solo
    un filtro-dato** (`r.contro == tipo`), nessun ramo che dirami sul *valore* del tipo. **Zero
    RNG**: funzione pura di dati, il contatore di stream non avanza."""
    cont = esper.try_component(ber, Resistenze)
    if cont is None:
        return 1.0
    somma = sum(r.valore for r in cont.voci if r.contro == tipo)
    return _clamp(1 + somma / 100, MULT_MIN, MULT_MAX)


def check2(m: float, att: int, ber: int, danno: Danno,
           fattore: float = 1.0) -> int:
    """Check 2 — il *quanto*: danno vs difesa, **deterministico** (GR2-11, DT-5).

    `atk_eff` in UNITÀ, `def_eff` in CENTESIMI → `/100`. La **schivata (`m=0`) corto-circuita
    PRIMA del floor** → 0 danni (il colpo non connette). Sui colpi che connettono (`m ∈ {g,
    1}`): `max(1, round(m·(atk−def/100)·mult))` — **un solo `round`, un solo `max(1,·)`**, con
    `m` (graze) e `mult` (resistenza) **dentro lo stesso `round`** (no doppio arrotondamento).
    `fattore` è il moltiplicatore della PRATICA (nodo S: la skill che governa
    la mossa) — 1.0 di default e per i mob: entra nello stesso round."""
    if m == 0:
        return 0                                       # SCHIVATA piena: niente floor (GR2-11/§7.2)
    base = m * (atk_eff(att) - def_eff(ber) / 100)     # PRE-round: non arrotondare qui
    mult = mult_resistenza(ber, danno.tipo)
    # `moltiplicatore` (mossa pesante) e `fattore` (skill) DENTRO lo stesso
    # round: un solo arrotondamento.
    return max(1, round(base * mult * danno.moltiplicatore * fattore))


def risolvi_danno(danno: Danno, att: int, ber: int, rng: random.Random,
                  fattore: float = 1.0) -> int:
    """Risolve un effetto `Danno`: check 1 (una pescata, o zero su auto-hit) poi check 2
    (zero pescate). `danno.quantita_da == ATK_EFF` → magnitudine da `atk_eff(att)`;
    `danno.stile` sceglie l'accuratezza del check 1 (marziale vs magica);
    `fattore` è il moltiplicatore di pratica (nodo S), 1.0 senza skill."""
    m = check1(att, ber, rng, danno.stile)
    return check2(m, att, ber, danno, fattore)


# --- Sistema-turno: AP loop + risoluzione (bucket solo-combattimento) ----------

class SistemaTurnoCombattimento(SistemaSoloCombattimento):
    """Avanza UN turno di combattente per `process()` risolto (FNC §6.4, §2.1)."""

    def __init__(self, bus) -> None:
        self.bus = bus

    def run(self, dt: int) -> None:
        st = stato_combattimento()
        if st is None:
            return
        _ent_stato, stato = st

        # Se il protagonista è morto, lo scontro è finito via MortePersonaggio (G-11):
        # niente CombatResolved(sconfitta).
        _pent, _marker, scheda = protagonista()
        if not scheda.vivo:
            return

        n = len(stato.ordine)
        if n == 0:
            return

        attivo: int | None = None
        for _ in range(n):
            stato.indice = (stato.indice + 1) % n
            if stato.indice == 0:
                stato.round += 1
            candidato = stato.ordine[stato.indice]
            if _e_vivo(candidato):
                attivo = candidato
                break
        if attivo is None:
            return

        # Un turno-combattente risolto in più: alimenta il contatore cieco dell'escalation (§8).
        stato.turni_scontro += 1

        # Marca l'entità attiva: i sistemi-status (sempre-attivo) ticcano solo lei (G-24).
        segna_turno_attivo(attivo)

        # Le RICARICHE scendono a inizio del proprio turno — PRIMA dello stordito:
        # i cooldown recuperano anche mentre si è storditi (si perde il turno, non
        # anche la ricarica). Un solo proprietario in scrittura: questo sistema.
        self._scala_ricariche(attivo)

        # STORDITO (afflizione, non capacità): il turno è consumato senza agire.
        # Il decorso dello status resta di `SistemaStordito` (sempre-attivo, G-5).
        stordito = esper.try_component(attivo, Stordito)
        if stordito is not None and not stordito.innato:
            if esper.has_component(attivo, Protagonista):
                # Il turno è consumato: le scelte legate a QUEL turno muoiono
                # con lui (caccia 2026-08-16). `richiedi_fuga`/`richiedi_mossa`
                # promettono «il PROSSIMO turno», non «un turno futuro»: senza
                # questo azzeramento la fuga chiesta da stordito DIROTTAVA il
                # turno seguente — il giocatore sceglieva Attacca e il motore
                # eseguiva la fuga di due turni prima, colpi d'opportunità
                # (e MortePersonaggio) compresi, per un input mai riconfermato.
                stato.fuga_richiesta = False
                stato.mossa_richiesta = None
            self.bus.pubblica(TurnoSaltato(nome=_nome_pubblico(attivo), causa="stordito"))
            return

        # FUGA richiesta (FNC §4): il turno del protagonista tenta il disimpegno
        # invece dell'azione — risolta dal MOTORE a margine, mai dall'AI.
        if stato.fuga_richiesta and esper.has_component(attivo, Protagonista):
            stato.fuga_richiesta = False
            self._risolvi_fuga(attivo, stato)
            return

        ap_comp = esper.component_for_entity(attivo, ActionPoint)
        ap_comp.ap = ap_comp.ap_max

        # Loop a Action Point — scritto AP-driven anche con max=1 (G-1). Esegue UNA `Azione`.
        while ap_comp.ap > 0:
            if not self._risolvi_azione(attivo, stato, ap_comp):
                break  # nessuna azione disponibile/pagabile: il turno finisce

        # Condizione di vittoria: nessun nemico vivo → torna in narrazione.
        # L'esito porta i FATTI DA IMPRESA (nodo O, titoli mid-run): grado del
        # nemico più alto, custode in persona battuto, vittoria senza graffi —
        # fotografati all'apertura, letti qui e mai dedotti.
        if not _nemici_vivi():
            self.bus.pubblica(CombatResolved(
                entita=attivo, vittoria=True,
                grado_nemico=stato.grado_massimo,
                custode=stato.custode_presente,
                senza_graffi=scheda.punti_vita >= stato.hp_iniziali_prot > 0,
            ))

    def _risolvi_fuga(self, attivo: int, stato: StatoCombattimento) -> None:
        """La fuga in tre corsie: **pulita**, **col colpo d'opportunità**, **negata**.

        Perché tre e non due (il punto di design, da non semplificare per distrazione).
        La prova ora è deterministica: con una soglia sola la fuga sarebbe *sempre*
        riuscita o *mai* riuscita per un dato personaggio, e "fuggi sempre" tornerebbe a
        dominare — il difetto che il fix della fuga aveva già chiuso una volta. La
        risposta non è reintrodurre casualità qui: è **far costare** la ritirata. Il
        margine dice *quanto bene* te la cavi, e il prezzo scala con quello.

        L'incertezza c'è ancora, ma viene da dove è già sanzionata: i colpi
        d'opportunità passano dal **check 1** come qualunque altro colpo. Quindi è
        pre-calcolabile *quale corsia* prenderai, non *se ne esci vivo* — che è
        esattamente la trasparenza tattica che si vuole (sai cosa rischi, non come
        finisce). Nessuna quarta casa di RNG: la tassonomia resta gate/opt-in/anomalia.

        La difficoltà **non è fissa**: la impone il `Grado` più alto fra i nemici vivi,
        via `CLASSE_DA_GRADO`. Scappare da uno slime di bronzo e da un boss celestiale
        non possono chiedere la stessa cosa.
        """
        # La COMPETENZA di fuga (nodo S6) entra nel margine — punti interi,
        # 0 a livello 1: le tre corsie restano le stesse, la pratica le
        # sposta. Import locale: il substrato skill resta a valle.
        from .skill import bonus_margine_fuga

        margine = (margine_prova(stat_eff(attivo, StatId.DESTREZZA), _classe_fuga())
                   + bonus_margine_fuga())
        if margine < 0:
            # Negata: il turno è speso. I nemici agiscono (li serve il giro normale).
            self.bus.pubblica(TurnoSaltato(nome="", causa="fuga_negata"))
            return
        if margine < MARGINE_FUGA_PULITA:
            # Ti disimpegni, ma scoprendo il fianco: ogni nemico vivo tira un colpo.
            # Vivo E in grado di agire: lo stordito perde il turno nel giro normale,
            # non può ritrovare il braccio proprio sul colpo d'opportunità.
            for nemico in _nemici_vivi():
                stordito = esper.try_component(nemico, Stordito)
                if stordito is not None and not stordito.innato:
                    continue
                self._esegui_effetti(
                    azione_da_mossa("attacco", sorgente=nemico, bersaglio=attivo), stato
                )
            # La fuga NON salva per decreto: se il colpo ha ucciso, il death-check
            # (sempre-attivo) pubblica `MortePersonaggio` e la run finisce lì. Emettere
            # comunque `CombatResolved(fuga=True)` significherebbe raccontare una
            # ritirata riuscita a un morto.
            _pent, _marker, pscheda = protagonista()
            if not pscheda.vivo or pscheda.punti_vita <= 0:
                return
        self.bus.pubblica(CombatResolved(
            entita=attivo, vittoria=False, fuga=True,
            grado_nemico=stato.grado_massimo,
        ))

    @staticmethod
    def _scala_ricariche(entita: int) -> None:
        """Un turno di ricarica in meno per ogni mossa in cooldown (le chiavi a zero
        escono dal dict: pronta = assente)."""
        ric = esper.try_component(entita, Ricariche)
        if ric is None:
            return
        ric.per_mossa = {k: v - 1 for k, v in ric.per_mossa.items() if v - 1 > 0}

    def _risolvi_azione(self, attivo: int, stato: StatoCombattimento, ap_comp: ActionPoint) -> bool:
        """Esegue **una `Azione`** percorrendo le tre giunture (GR2-12/13): (1) selezione da
        un insieme (oggi di uno), (2) costo verificato PRIMA, (3) lista di `effetti` iterata.
        Ritorna `True` se ha pagato il costo e agito, `False` se non c'è azione/non è pagabile."""
        azione = self._scegli_azione(attivo, stato)
        if azione is None:                                   # giuntura 1: insieme vuoto (niente bersaglio)
            return False
        costo = azione.costo.get("AP", 1)
        costo_mana = azione.costo.get("MANA", 0)
        mana = esper.try_component(attivo, Mana) if costo_mana else None
        # giuntura 2: TUTTE le risorse verificate PRIMA di spenderne una (GR2-13) —
        # mai un pagamento parziale.
        if ap_comp.ap < costo:
            return False
        if costo_mana and (mana is None or mana.attuale < costo_mana):
            return False
        ap_comp.ap -= costo
        if costo_mana and mana is not None:
            mana.attuale -= costo_mana
        # La mossa va in ricarica appena risolta (il decremento è a inizio turno:
        # `cooldown=2` costa esattamente un proprio turno d'attesa).
        _mossa = mossa_di(azione.mossa)
        ricarica = _mossa.cooldown if _mossa is not None else 0
        if ricarica > 0:
            ric = esper.try_component(attivo, Ricariche)
            if ric is None:
                ric = Ricariche()
                esper.add_component(attivo, ric)
            ric.per_mossa[azione.mossa] = ricarica
        self._esegui_effetti(azione, stato)
        return True

    def _esegui_effetti(self, azione: Azione, stato: StatoCombattimento) -> None:
        """Giuntura 3: itera la lista di `effetti` e li applica (GR2-13).

        Separata da `_risolvi_azione` perché il **colpo d'opportunità** della fuga la
        riusa: è lo stesso colpo di sempre — stesso check 1, stessa pescata, stessi
        eventi — ma **non passa dalle giunture 1-2** (non è un'azione scelta e non
        costa AP: è la conseguenza della ritirata). Duplicarla qui avrebbe significato
        due percorsi di danno che divergono al primo ritocco."""
        # `a_segno` lega i primitivi della STESSA azione: un `ApplicaStatus` dopo un
        # `Danno` vale solo se il colpo ha connesso (il morso che avvelena deve mordere);
        # in una mossa senza Danno si applica e basta (utility pura). Deterministico.
        a_segno: bool | None = None
        # Il moltiplicatore della PRATICA (nodo S): la skill che governa QUESTA
        # mossa, per il protagonista che l'ha praticata — 1.0 per i mob e a
        # livello 1 (byte-identico allo storico). Import locale: il sistema
        # skill resta a valle del combattimento.
        from .skill import fattore_skill

        fattore = fattore_skill(azione.sorgente, azione.mossa)
        for effetto in azione.effetti:                       # giuntura 3: itera la lista
            if isinstance(effetto, Danno):
                # Risolvi PRIMA (motore, seeded), narra DOPO (sul bus): mai LLM qui (G-4).
                inflitto = risolvi_danno(
                    effetto, azione.sorgente, azione.bersaglio, stato.rng,
                    fattore,
                )
                a_segno = inflitto > 0
                if inflitto:
                    infliggi_danno(azione.bersaglio, inflitto)
                    attuali, massimi = _hp_di(azione.bersaglio)
                    # Il colpo È un fatto già arbitrato: si narra sul Canale B (FNC §8).
                    self.bus.pubblica(ColpoInferto(
                        attaccante=_nome_pubblico(azione.sorgente),
                        bersaglio=_nome_pubblico(azione.bersaglio),
                        danno=inflitto,
                        hp_rimasti=max(0, attuali),  # l'overkill non si mostra
                        hp_max=massimi,
                        mossa=azione.mossa,
                    ))
                    # Capacità INNATE trasmissibili: il colpo che connette applica
                    # l'afflizione al bersaglio (lo slime velenoso avvelena, §12).
                    self._trasmetti_status(azione.sorgente, azione.bersaglio)
            elif isinstance(effetto, EffettoAzzardo):
                # AZZARDO OPT-IN (azzardo.py) — NON è il tiro del combattimento: quello
                # sono i due check qui sopra. Senza un consenso dichiarato dalla voce di
                # catalogo, l'effetto è saltato SENZA pescare: lo stream non avanza, e
                # "pescare per default" resta un percorso inesistente.
                if not azione.consenso_azzardo:
                    continue
                inflitto, faccia = risolvi_effetto_azzardo_con_faccia(
                    effetto, azione.sorgente, stato.rng
                )
                if inflitto:
                    # La pescata sostituisce la MAGNITUDINE, non il risolutore
                    # (Gr2 §5.2): verso il bersaglio il *se* colpisci resta del
                    # check 1 (la build evasiva vive anche contro i dadi) e il
                    # layer dei tipi si applica come a ogni colpo; `def_eff` resta
                    # fuori — la pescata rimpiazza (atk−def), non le si somma un
                    # secondo sconto. La faccia NEGATIVA è secca su chi ha tirato:
                    # la propria sfortuna non si schiva.
                    if inflitto > 0:
                        bersaglio = azione.bersaglio
                        if bersaglio is None:
                            continue
                        stile = getattr(effetto, "stile", None) or StileAttacco.FISICO
                        m = check1(azione.sorgente, bersaglio, stato.rng, stile)
                        if m == 0:
                            continue                     # schivata: il colpo non connette
                        tipo = getattr(effetto, "tipo", None) or TipoDanno.GENERICO
                        danno_eff = max(1, round(m * inflitto * mult_resistenza(bersaglio, tipo)))
                    else:
                        bersaglio = azione.sorgente
                        danno_eff = -inflitto
                    infliggi_danno(bersaglio, danno_eff)
                    attuali, massimi = _hp_di(bersaglio)
                    self.bus.pubblica(ColpoInferto(
                        attaccante=_nome_pubblico(azione.sorgente),
                        bersaglio=_nome_pubblico(bersaglio),
                        danno=danno_eff,
                        hp_rimasti=max(0, attuali),
                        hp_max=massimi,
                        mossa=azione.mossa,
                        azzardo=faccia,  # la pescata si RACCONTA (mai muta)
                    ))
            elif isinstance(effetto, ApplicaStatus) and a_segno is not False:
                # Primitivo del catalogo mosse: afflizione dal Blocco, rango copiato
                # dal grado della sorgente (G §4.3); il decorso lo decide status.py.
                cls = REGISTRY_BLOCCHI[effetto.blocco]
                nuovo = applica_status(
                    azione.bersaglio, afflizione(cls, _rango_sorgente(azione.sorgente))
                )
                if nuovo:  # il rinfresco non si annuncia: una sola riga per status
                    self.bus.pubblica(StatusApplicato(
                        bersaglio=_nome_pubblico(azione.bersaglio),
                        status=cls.__name__.lower(),
                        fonte=_nome_pubblico(azione.sorgente) or "il colpo",
                    ))

    def _trasmetti_status(self, sorgente: int, bersaglio: int) -> None:
        # L'insieme dei tipi trasmissibili è DATO (status.PROFILO_STATUS), non una
        # tupla del loop: un nuovo status offensivo entra in tabella, non qui.
        for tipo_status in TRASMISSIBILI:
            innato = esper.try_component(sorgente, tipo_status)
            if innato is None or not innato.innato:
                continue
            # La costruzione dell'afflizione vive in status.py (G-5/G-6): qui
            # solo il momento della trasmissione (il colpo che connette).
            if applica_status(bersaglio, afflizione_da(innato)):
                # Solo lo status NUOVO parla: il colpo che rinfresca un veleno
                # già addosso non ristampa «Sei avvelenato!».
                self.bus.pubblica(StatusApplicato(
                    bersaglio=_nome_pubblico(bersaglio),
                    status=tipo_status.__name__.lower(),
                    fonte=_nome_pubblico(sorgente) or "il colpo",
                ))

    def _scegli_azione(self, attivo: int, stato: StatoCombattimento) -> Azione | None:
        """Sceglie una mossa dal `Repertorio` dell'entità (DATO nel componente; assente
        → `MOSSE_DEFAULT`) e la traduce in `Azione` via il catalogo (`mosse.py`): il
        system esegue, il dato decide cosa esiste. Per il protagonista la mossa è la
        SCELTA del giocatore (`mossa_richiesta`, consumata qui; assente o estranea al
        repertorio → attacco base) e il bersaglio il primo nemico vivo; per il nemico
        la scelta è del **motore**, seeded (`decidi_azione_nemico`), mai l'LLM (G-4)."""
        mosse = mosse_di(attivo)
        mossa = "attacco"
        if esper.has_component(attivo, Protagonista):
            # Consumo one-shot della scelta (il gemello di `fuga_richiesta`): la
            # cintura `in mosse` regge anche se lo stato è mutato dopo il click.
            if stato.mossa_richiesta is not None:
                # Cintura profonda: la scelta può essere invecchiata fra il click e
                # la risoluzione (mana speso, cd armato) → degrada all'attacco base,
                # che è sempre pagabile. Il turno non si perde.
                if stato.mossa_richiesta in mosse and mossa_pagabile(attivo, stato.mossa_richiesta):
                    mossa = stato.mossa_richiesta
                stato.mossa_richiesta = None
            bersagli = _nemici_vivi()
            bersaglio = bersagli[0] if bersagli else None
        else:
            pent, _marker, pscheda = protagonista()
            bersagli = [pent] if (pscheda.vivo and pscheda.punti_vita > 0) else []
            # Anche il motore sceglie solo fra le mosse PAGABILI: un nemico a secco
            # ripiega sull'attacco base invece di sprecare il turno.
            pagabili = tuple(m for m in mosse if mossa_pagabile(attivo, m)) or ("attacco",)
            decisione = decidi_azione_nemico(stato.rng, bersagli, mosse=pagabili)
            if decisione is not None:
                bersaglio, mossa = decisione  # la MOSSA scelta si usa, non si scarta
            else:
                bersaglio = None
        if bersaglio is None:
            return None
        return azione_da_mossa(mossa, sorgente=attivo, bersaglio=bersaglio)


# --- Death-check (G-11): seeded, emette MortePersonaggio, NON CombatResolved ---

class SistemaDeathCheck(SistemaSempreAttivo):
    """Death-check deterministico e seeded. Nell'MVP **sconfitta → morte sempre**;
    l'aggiramento entra dopo come hook additivo (§6.2). Morte ≠ sconfitta: il
    terminale è `MortePersonaggio`, mai `CombatResolved(sconfitta)`."""

    def __init__(self, bus) -> None:
        self.bus = bus

    def run(self, dt: int) -> None:
        trovati = esper.get_components(Protagonista, Scheda)
        if len(trovati) > 1:
            # Invariante mono-protagonista VIOLATO: con N protagonisti questo check
            # non sa chi arbitrare e prima RESTITUIVA in silenzio — la permadeath
            # (linea rossa G-11) si spegneva senza dirlo. Meglio esplodere subito:
            # chi introdurrà il party dovrà passare di qui DI PROPOSITO.
            raise RuntimeError(
                f"death-check: protagonista singleton atteso, trovati {len(trovati)} — "
                "con più protagonisti la permadeath non può arbitrare (G-11)"
            )
        if not trovati:
            return  # mondo in allestimento (harness): nessuno da arbitrare
        _ent, (_marker, scheda) = trovati[0]
        if scheda.vivo and scheda.punti_vita <= 0:
            scheda.vivo = False
            self.bus.pubblica(MortePersonaggio(causa="sconfitta"))


# --- Escalation a contatore (Gruppo 2 §8, G §3/§5; GR2-15): fine per costruzione --

class SistemaCrollo(SistemaSoloCombattimento):
    """Rete di terminazione **per costruzione** (G-L1), **attiva nell'MVP**. A confine di
    turno, **oltre la soglia `R`**, infligge danno **inevitabile e crescente** a **tutti** i
    combattenti — **bypassa** il risolutore a due check, **indipendente dalle stat** (§8).

    È un **contatore cieco** (non il watchdog a delta-danno di G §5.6-b né una curva
    modellata): cresce illimitato e supera qualunque `def` + rigenerazione in un numero
    **limitato** di round (aritmetica monotòna). Bucket solo-combattimento, priorità
    dichiarata (registrato **dopo** il sistema-turno, così legge il `turni_scontro` appena
    avanzato). I numeri (`R`, incremento) sono `§11` in `calibrazione.py`."""

    def __init__(self, bus=None) -> None:
        # Facoltativo per compatibilità con gli harness: SENZA bus l'escalation
        # torna muta — il guscio vero lo passa sempre (HP che calano senza una
        # riga di cronaca erano il buco, giro 2026-08-07).
        self.bus = bus

    def run(self, dt: int) -> None:
        st = stato_combattimento()
        if st is None:
            return
        _ent_stato, stato = st
        if stato.turni_scontro <= R_SOGLIA_CROLLO:
            return
        stato.crollo += CROLLO_INCREMENTO
        for ent in _tutti_combattenti_vivi():
            # Danno inevitabile, indipendente dalle stat: NON passa dal risolutore a due check.
            infliggi_danno(ent, stato.crollo)
        if self.bus is not None:
            self.bus.pubblica(CrolloDungeon(danno=stato.crollo))


def _custode_in_scontro(arruolate) -> bool:
    """Vero se fra gli ARRUOLATI c'è il custode di zona IN PERSONA: stanza-boss,
    boss non ancora battuto, e il mob DELLA stanza è dentro lo scontro. Il
    fatto si fotografa all'apertura (alla chiusura il custode è smontato) e
    identifica il MOB, mai la stanza: un'imboscata vinta nella stanza-boss non
    è il custode — né per il titolo «taglia sul custode» né per la garanzia di
    drop (il bancomat del breaker 2026-08-26). Lettura tollerante: gli harness
    senza territorio non devono esplodere — il degrado è False, mai un crash."""
    try:
        from .mappa import mob_corrente
        from .territorio import (
            boss_sconfitto,
            stanza_corrente_e_del_boss,
            zona_corrente,
        )

        zona = zona_corrente()
        if (zona is None or not stanza_corrente_e_del_boss()
                or boss_sconfitto(zona)):
            return False
        mob = mob_corrente()
        return mob is not None and mob in arruolate
    except Exception:
        return False


# --- Ciclo di vita delle entità di combattimento (effimere) -------------------

def collega_combattimento(bus) -> list[tuple[type, object]]:
    """Materializza su `EncounterStarted`, smonta su `CombatResolved` (FNC §6.3).

    Ritorna le coppie `(tipo, handler)` registrate, così il guscio le **deregistra al
    teardown** della run (E-9): sono handler in-run su un bus process-global."""

    def _materializza(evento: EncounterStarted) -> None:
        piano = esper.try_component(evento.entita, PianoIncontro)
        if piano is None:
            return

        esper.create_entity(
            StatoCombattimento(
                ordine=[], indice=-1, round=0, prossima_chiave=0,
                rng=random.Random(piano.seed),
            )
        )

        # Il protagonista entra in combattimento con un Combattente effimero (chiave 0).
        # La destrezza è snapshot dal fold (GR2-3): l'iniziativa passa da `stat_eff`.
        pent, _marker, _pscheda = protagonista()
        _st_ent, stato = stato_combattimento()  # type: ignore[misc]
        chiave_prot = stato.prossima_chiave
        stato.prossima_chiave += 1
        esper.add_component(
            pent,
            Combattente(destrezza=stat_eff(pent, StatId.DESTREZZA), chiave_ordine=chiave_prot),
        )
        # Ricariche fresche a ogni scontro (effimere: i cd non si portano dietro).
        if not esper.has_component(pent, Ricariche):
            esper.add_component(pent, Ricariche())
        assicura_mana(pent)  # save legacy: il pool nasce pieno alla prima materializzazione
        # L'AP del protagonista è già su `ActionPoint` (persistente, da crea_protagonista):
        # il Combattente effimero non lo porta (single-owner, guida §6.1).

        for spec in piano.nemici:
            spawn_nemico(destrezza=spec.destrezza, punti_vita=spec.punti_vita)
        for ent in piano.arruolate:
            if esper.entity_exists(ent):
                arruola_entita(ent)

        combattenti = [
            (ent, comb.destrezza, comb.chiave_ordine)
            for ent, comb in esper.get_component(Combattente)
        ]
        stato.ordine = calcola_iniziativa(combattenti)
        # Le fotografie da impresa (nodo O): HP d'ingresso del protagonista e
        # grado massimo dei nemici materializzati (per rango; gli scalari
        # senza EntitaMob non contano — "" resta il degrado onesto).
        stato.hp_iniziali_prot = _pscheda.punti_vita
        from .catalogo import RANGO_GRADO

        gradi = [
            em.grado for _ent, (em, _n) in esper.get_components(EntitaMob, Nemico)
        ]
        stato.grado_massimo = (
            max(gradi, key=RANGO_GRADO.__getitem__).value if gradi else ""
        )
        stato.custode_presente = _custode_in_scontro(piano.arruolate)

    def _smonta(_evento: CombatResolved) -> None:
        # Il ciclo di vita dipende da COME il nemico è entrato in scontro (FNC §6.3):
        # lo spawnato è nato per lo scontro e muore con lo scontro; l'arruolato è il
        # mob della stanza — se è ancora vivo (fuga, FNC §4) viene CONGEDATO, non
        # distrutto, e resta in scena col suo legame `EntitaMob.stanza`.
        for ent, nemico in list(esper.get_component(Nemico)):
            # Il FANTASMA (caccia 2026-08-16): il mob d'imboscata è arruolato ma
            # non ha MAI avuto una stanza (`EntitaMob.stanza=None` — non passa da
            # `registra_mob`). Congedarlo lo lasciava nel World come OSTILE
            # irraggiungibile: nessun menu Combatti, ma `minacce_zona` lo contava
            # PER SEMPRE — probabilità d'imboscata gonfiata e riposo più duro in
            # tutta la zona, anche ripulita. Senza stanza a cui tornare, si dissolve con
            # lo scontro (FNC §6.3); niente room-clear gratuito: non presidiava
            # alcuna stanza (l'anti-exploit riguarda i mob DI stanza).
            em = esper.try_component(ent, EntitaMob)
            fantasma = em is not None and em.stanza is None
            if nemico.arruolato and _e_vivo(ent) and not fantasma:
                _congeda(ent)
            else:
                esper.delete_entity(ent, immediate=True)
        azzera_turno_attivo()
        for ent, _ in list(esper.get_component(StatoCombattimento)):
            esper.delete_entity(ent, immediate=True)
        # Il protagonista persiste: perde le sole effimere di scontro (il Combattente
        # e le Ricariche — il Mana invece è posseduto e resta com'è: si recupera
        # riposando, non chiudendo uno scontro).
        for pent, _ in list(esper.get_component(Protagonista)):
            for componente in (Combattente, Ricariche):
                if esper.has_component(pent, componente):
                    esper.remove_component(pent, componente)

    coppie = [(EncounterStarted, _materializza), (CombatResolved, _smonta)]
    for tipo, handler in coppie:
        bus.registra(tipo, handler)
    return coppie
