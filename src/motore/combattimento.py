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
    TipoDanno,
    TurnoSaltato,
)

from .azione import Azione, Danno, QuantitaDa
from .calibrazione import (
    AP_MAX_MVP,
    CROLLO_INCREMENTO,
    DANNO_BASE,
    DELTA_BANDA,
    F_AUTOHIT,
    G_GRAZE,
    MIN_COLPO,
    MOLT_ATTACCO_PESANTE,
    MULT_MAX,
    MULT_MIN,
    R_SOGLIA_CROLLO,
    S_CONTEST,
    primarie_da_scalari,
)
from .derivate import acc_eff, atk_eff, def_eff, eva_eff, max_hp
from .modificatori import Resistenze
from .phased import SistemaSempreAttivo, SistemaSoloCombattimento
from .prove import risolvi_prova
from .scheda import ActionPoint, Protagonista, Scheda, protagonista
from .statistiche import Primarie, stat_eff
from .status import Brucia, Stordito, Veleno, afflizione_da, applica_status
from .turno import azzera_turno_attivo, segna_turno_attivo

# `DANNO_BASE` (witness storico del floor positivo del danno, G-L1) vive in `calibrazione.py`
# (riesposto via l'import sopra): oggi il floor reale è nel check 2, ma il contratto
# "ogni colpo che connette fa progredire lo stato" resta vero.


# --- Componenti di combattimento (dato puro, ESP §1) --------------------------

@dataclass
class Nemico:
    """Marker di un combattente nemico (entità EFFIMERA: distrutta su CombatResolved)."""


@dataclass
class PuntiVita:
    """HP dei nemici (placeholder Gruppo 2). Il protagonista tiene gli HP in `Scheda`."""

    attuali: int
    massimi: int


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
    """Applica danno dove vivono gli HP: `Scheda` per il protagonista, `PuntiVita`
    per i nemici."""
    scheda = esper.try_component(entita, Scheda)
    if scheda is not None:
        scheda.punti_vita -= danno
        return
    pv = esper.try_component(entita, PuntiVita)
    if pv is not None:
        pv.attuali -= danno


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
    return esper.create_entity(
        Nemico(),
        Combattente(destrezza=destrezza, chiave_ordine=chiave),
        ActionPoint(ap=AP_MAX_MVP, ap_max=AP_MAX_MVP),
        Primarie(valori=primarie_da_scalari(destrezza=destrezza, punti_vita=punti_vita)),
        PuntiVita(attuali=punti_vita, massimi=punti_vita),
    )


def arruola_entita(entita: int) -> int:
    """Arruola un'entità GIÀ viva del World (il mob rivelato nella stanza) come nemico.

    Aggiunge SOLO i componenti effimeri di combattimento: `Nemico`, `Combattente`
    (destrezza dal fold — GR2-3), `ActionPoint`, `PuntiVita` (pool = `max_hp` derivato
    dalla SUA Costituzione). Le sue `Primarie`/`Corredo`/`Resistenze` restano: le
    derivate del risolutore leggono il profilo calibrato vero. Su `CombatResolved`
    l'entità segue il ciclo di vita effimero (eliminata come ogni `Nemico`)."""
    st = stato_combattimento()
    if st is None:
        raise RuntimeError("arruola_entita richiede uno StatoCombattimento attivo")
    _ent_stato, stato = st
    chiave = stato.prossima_chiave
    stato.prossima_chiave += 1
    hp = max_hp(entita)
    esper.add_component(entita, Nemico())
    esper.add_component(
        entita, Combattente(destrezza=stat_eff(entita, StatId.DESTREZZA), chiave_ordine=chiave)
    )
    esper.add_component(entita, ActionPoint(ap=AP_MAX_MVP, ap_max=AP_MAX_MVP))
    esper.add_component(entita, PuntiVita(attuali=hp, massimi=hp))
    return entita


def _nemici_vivi() -> list[int]:
    return [ent for ent, _ in esper.get_component(Nemico) if _e_vivo(ent)]


def _tutti_combattenti_vivi() -> list[int]:
    """Tutti i combattenti vivi (nemici + protagonista) — bersagli dell'escalation (§8)."""
    vivi = _nemici_vivi()
    pent, _marker, pscheda = protagonista()
    if pscheda.vivo and pscheda.punti_vita > 0:
        vivi.append(pent)
    return vivi


def _nome_pubblico(entita: int) -> str:
    """Nome diegetico per gli eventi di vista: il nome del mob rivelato, "" per il
    protagonista. Import locale: `narrazione` importa già questo modulo."""
    from .narrazione import EntitaMob

    em = esper.try_component(entita, EntitaMob)
    if em is not None:
        return em.nome
    return "" if esper.has_component(entita, Protagonista) else "il nemico"


def _hp_di(entita: int) -> tuple[int, int]:
    """(attuali, massimi) dove vivono gli HP (`Scheda`/`PuntiVita`)."""
    scheda = esper.try_component(entita, Scheda)
    if scheda is not None:
        return scheda.punti_vita, max_hp(entita)
    pv = esper.try_component(entita, PuntiVita)
    if pv is not None:
        return pv.attuali, pv.massimi
    return 0, 0


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
    del contest* dalla *derivazione* delle due magnitudini (`acc_eff`/`eva_eff`), così il
    property-test del vincolo accoppiato (§11) la esercita coi due scalari direttamente."""
    if eva < acc / F_AUTOHIT:
        return 1.0                                     # auto-hit: zero pescate
    P = _clamp(acc ** S_CONTEST / (acc ** S_CONTEST + eva ** S_CONTEST), MIN_COLPO, 1 - MIN_COLPO)
    lo = _clamp(P - DELTA_BANDA / 2, MIN_COLPO, 1 - MIN_COLPO)
    hi = _clamp(P + DELTA_BANDA / 2, MIN_COLPO, 1 - MIN_COLPO)
    u = rng.random()                                   # UNA sola estrazione per colpo (FNC §9)
    return 1.0 if u < lo else (G_GRAZE if u < hi else 0.0)


def check1(att: int, ber: int, rng: random.Random) -> float:
    """Check 1 a livello-entità: deriva `acc_eff(att)`/`eva_eff(ber)` (da `stat_eff`, GR2-3) e
    delega il contest a `esito_contest`. Con la geometria di default dell'MVP (nudo/taglia
    media) `eva ≪ acc/F` → **auto-hit deterministico** per tutti; la forma stocastica si
    attiva solo quando un'entità porta dati d'evasione (seam gear, post-MVP)."""
    return esito_contest(acc_eff(att), eva_eff(ber), rng)


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


def check2(m: float, att: int, ber: int, danno: Danno) -> int:
    """Check 2 — il *quanto*: danno vs difesa, **deterministico** (GR2-11, DT-5).

    `atk_eff` in UNITÀ, `def_eff` in CENTESIMI → `/100`. La **schivata (`m=0`) corto-circuita
    PRIMA del floor** → 0 danni (il colpo non connette). Sui colpi che connettono (`m ∈ {g,
    1}`): `max(1, round(m·(atk−def/100)·mult))` — **un solo `round`, un solo `max(1,·)`**, con
    `m` (graze) e `mult` (resistenza) **dentro lo stesso `round`** (no doppio arrotondamento)."""
    if m == 0:
        return 0                                       # SCHIVATA piena: niente floor (GR2-11/§7.2)
    base = m * (atk_eff(att) - def_eff(ber) / 100)     # PRE-round: non arrotondare qui
    mult = mult_resistenza(ber, danno.tipo)
    # `moltiplicatore` (mossa pesante) DENTRO lo stesso round: un solo arrotondamento.
    return max(1, round(base * mult * danno.moltiplicatore))


def risolvi_danno(danno: Danno, att: int, ber: int, rng: random.Random) -> int:
    """Risolve un effetto `Danno`: check 1 (una pescata, o zero su auto-hit) poi check 2
    (zero pescate). `danno.quantita_da == ATK_EFF` → magnitudine da `atk_eff(att)`."""
    m = check1(att, ber, rng)
    return check2(m, att, ber, danno)


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

        # STORDITO (afflizione, non capacità): il turno è consumato senza agire.
        # Il decorso dello status resta di `SistemaStordito` (sempre-attivo, G-5).
        stordito = esper.try_component(attivo, Stordito)
        if stordito is not None and not stordito.innato:
            self.bus.pubblica(TurnoSaltato(nome=_nome_pubblico(attivo), causa="stordito"))
            return

        # FUGA richiesta (FNC §4): il turno del protagonista tenta il disimpegno
        # invece dell'azione — prova seeded del MOTORE, mai dell'AI.
        if stato.fuga_richiesta and esper.has_component(attivo, Protagonista):
            stato.fuga_richiesta = False
            if risolvi_prova(
                stat_eff(attivo, StatId.DESTREZZA), ClasseProva.BRONZO, stato.rng
            ):
                # Chiusura senza esito: né vittoria né sconfitta (FNC §4).
                self.bus.pubblica(CombatResolved(entita=attivo, vittoria=False, fuga=True))
            else:
                self.bus.pubblica(TurnoSaltato(nome="", causa="fuga_fallita"))
            return

        ap_comp = esper.component_for_entity(attivo, ActionPoint)
        ap_comp.ap = ap_comp.ap_max

        # Loop a Action Point — scritto AP-driven anche con max=1 (G-1). Esegue UNA `Azione`.
        while ap_comp.ap > 0:
            if not self._risolvi_azione(attivo, stato, ap_comp):
                break  # nessuna azione disponibile/pagabile: il turno finisce

        # Condizione di vittoria: nessun nemico vivo → torna in narrazione.
        if not _nemici_vivi():
            self.bus.pubblica(CombatResolved(entita=attivo, vittoria=True))

    def _risolvi_azione(self, attivo: int, stato: StatoCombattimento, ap_comp: ActionPoint) -> bool:
        """Esegue **una `Azione`** percorrendo le tre giunture (GR2-12/13): (1) selezione da
        un insieme (oggi di uno), (2) costo verificato PRIMA, (3) lista di `effetti` iterata.
        Ritorna `True` se ha pagato il costo e agito, `False` se non c'è azione/non è pagabile."""
        azione = self._scegli_azione(attivo, stato)
        if azione is None:                                   # giuntura 1: insieme vuoto (niente bersaglio)
            return False
        costo = azione.costo.get("AP", 1)
        if ap_comp.ap < costo:                               # giuntura 2: costo pagabile? (GR2-13)
            return False
        ap_comp.ap -= costo
        for effetto in azione.effetti:                       # giuntura 3: itera la lista (oggi di uno)
            if isinstance(effetto, Danno):
                # Risolvi PRIMA (motore, seeded), narra DOPO (sul bus): mai LLM qui (G-4).
                inflitto = risolvi_danno(effetto, azione.sorgente, azione.bersaglio, stato.rng)
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
        return True

    def _trasmetti_status(self, sorgente: int, bersaglio: int) -> None:
        for tipo_status in (Veleno, Brucia, Stordito):
            innato = esper.try_component(sorgente, tipo_status)
            if innato is None or not innato.innato:
                continue
            # La costruzione dell'afflizione vive in status.py (G-5/G-6): qui
            # solo il momento della trasmissione (il colpo che connette).
            applica_status(bersaglio, afflizione_da(innato))
            self.bus.pubblica(StatusApplicato(
                bersaglio=_nome_pubblico(bersaglio),
                status=tipo_status.__name__.lower(),
                fonte=_nome_pubblico(sorgente) or "il colpo",
            ))

    def _scegli_azione(self, attivo: int, stato: StatoCombattimento) -> Azione | None:
        """Sceglie un'`Azione` dall'insieme disponibile sull'entità (oggi `[attacco_base]`).
        Per il protagonista il bersaglio è il primo nemico vivo; per il nemico la scelta è del
        **motore**, seeded (`decidi_azione_nemico`), mai l'LLM (G-4)."""
        mossa = "attacco"
        if esper.has_component(attivo, Protagonista):
            bersagli = _nemici_vivi()
            bersaglio = bersagli[0] if bersagli else None
        else:
            pent, _marker, pscheda = protagonista()
            bersagli = [pent] if (pscheda.vivo and pscheda.punti_vita > 0) else []
            decisione = decidi_azione_nemico(stato.rng, bersagli)
            if decisione is not None:
                bersaglio, mossa = decisione  # la MOSSA scelta si usa, non si scarta
            else:
                bersaglio = None
        if bersaglio is None:
            return None
        # Attacco base = l'istanza di sempre; la mossa pesante scala il danno (§11).
        moltiplicatore = MOLT_ATTACCO_PESANTE if mossa == "attacco_pesante" else 1.0
        return Azione(
            sorgente=attivo,
            bersaglio=bersaglio,
            effetti=[Danno(quantita_da=QuantitaDa.ATK_EFF, moltiplicatore=moltiplicatore)],
            mossa=mossa,
        )


# --- Death-check (G-11): seeded, emette MortePersonaggio, NON CombatResolved ---

class SistemaDeathCheck(SistemaSempreAttivo):
    """Death-check deterministico e seeded. Nell'MVP **sconfitta → morte sempre**;
    l'aggiramento entra dopo come hook additivo (§6.2). Morte ≠ sconfitta: il
    terminale è `MortePersonaggio`, mai `CombatResolved(sconfitta)`."""

    def __init__(self, bus) -> None:
        self.bus = bus

    def run(self, dt: int) -> None:
        trovati = esper.get_components(Protagonista, Scheda)
        if len(trovati) != 1:
            return
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

    def _smonta(_evento: CombatResolved) -> None:
        for ent, _ in list(esper.get_component(Nemico)):
            esper.delete_entity(ent, immediate=True)
        azzera_turno_attivo()
        for ent, _ in list(esper.get_component(StatoCombattimento)):
            esper.delete_entity(ent, immediate=True)
        # Il protagonista persiste: perde solo il Combattente effimero.
        for pent, _ in list(esper.get_component(Protagonista)):
            if esper.has_component(pent, Combattente):
                esper.remove_component(pent, Combattente)

    coppie = [(EncounterStarted, _materializza), (CombatResolved, _smonta)]
    for tipo, handler in coppie:
        bus.registra(tipo, handler)
    return coppie
