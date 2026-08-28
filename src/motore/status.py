"""Status: shape, stacking, rango, tick single-owner (G §4; G-5/6/7/8/24).

Gli status sono componenti **dato puro** (ESP §1): `rango: int` + `durata: int`,
**nessun riferimento alla fonte** (G-6: la fonte è effimera, il rango è *copiato*
all'applicazione e lo status diventa autosufficiente).

Stacking = **un'istanza per tipo** sulla stessa entità (default ECS: `add_component`
sovrascrive). Riapplicare lo stesso tipo NON affianca una copia: **compete per rango**
(`applica_status`). Tipi diversi coesistono e ticcano in parallelo (G-8).

Tick = **un solo proprietario per tipo**, nel bucket **sempre-attivo** (G-5): un
`SistemaStatus(tipo=Veleno)` possiede tutti i `Veleno`, ecc. — e si ottiene SEMPRE da
`sistemi_status()`, che li deriva dalla tabella. Cadenza in combattimento =
**per-turno-dell'entità** (G-24): si avanza solo lo status dell'entità attiva
(`TurnoAttivo`), così il burn-rate è invariante al numero di nemici.

I *numeri* (durate, danni, scala dei ranghi) sono Gruppo 2: qui l'effetto-al-tick è
un hook placeholder (default: nessun danno), la forma è completa.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import esper

from contracts import Blocco

from .phased import SistemaSempreAttivo
from .turno import entita_attiva


# --- Componenti-status: dato puro, rango copiato, nessuna fonte (G-6) ----------

@dataclass
class Status:
    """Base dato puro di ogni status. `rango` copiato dall'applicatore (§4.3).

    `innato=True` = CAPACITÀ dell'entità (il blocco del catalogo attaccato al
    reveal: lo slime È velenoso), non un'afflizione subita: non scade mai e non
    danneggia il portatore — agisce sul colpo (trasmissione) o come passiva
    (rigenerazione). `innato=False` (default) = afflizione applicata in scontro:
    ticka, scade, muove gli HP. Campo additivo con default: i save vecchi
    round-trippano invariati."""

    rango: int
    durata: int
    innato: bool = False


@dataclass
class Veleno(Status):
    pass


@dataclass
class Brucia(Status):
    pass


@dataclass
class Rigenerazione(Status):
    pass


@dataclass
class Stordito(Status):
    """Blocco `STORDITO` del catalogo (F §2): ha un binding nel registry (F-6).

    Esiste come componente perché ogni membro di `Blocco` deve essere istanziabile —
    niente nome accettabile dal gate ma non materializzabile.
    """


@dataclass
class Confusione(Status):
    """Status **unsafe** (risoluzione = AI): il suo tick *richiede l'LLM* perché altera
    *come* agisci (J §7). Esiste qui come placeholder dell'**asse safe/unsafe**: i flag
    di tipo (`valenza=DANNOSO`, `risoluzione=AI`) vivono nel catalogo (J-9).

    La sua risoluzione AI-driven è **post-MVP**: nell'MVP nessun meccanismo lo applica
    in gioco e non ha un avanzamento deterministico (è AI-risolto). Serve a far esistere
    la categoria che blocca downtime *e* passa-turno (§5/§6).
    """


# --- L'ASSE safe/unsafe (J §7, J-9): flag di TIPO, qui col resto del dato-status --
# (Vivevano in catalogo.py, che li ri-espone per compatibilità: un solo proprietario.)

class Valenza(str, Enum):
    """Il *segno* dello status — flag ESPLICITO, **non** derivato da `delta < 0` (uno
    `Stordito`/`Confusione` senza delta-HP è comunque `DANNOSO`, J-9)."""

    BENEFICO = "benefico"
    DANNOSO = "dannoso"
    NEUTRO = "neutro"


class Risoluzione(str, Enum):
    """*Come* si risolve il tick. `AI` ⟺ **unsafe** (richiede l'LLM: berserk,
    confusione). `MOTORE` = deterministico, zero LLM (veleno, brucia, rigenerazione)."""

    MOTORE = "motore"
    AI = "ai"  # = unsafe


# --- LA TABELLA: tutto il dato di uno status in UNA riga (audit 2026-08) ----------
#
# ▶ COME SI AGGIUNGE UNO STATUS (tre tocchi, zero rami nel codice):
#   1. il NOME nel vocabolario AI-facing: una riga nell'enum `Blocco` (contracts) —
#      solo se dev'essere emettibile da AI/asset (uno status interno può ometterla);
#   2. la CLASSE-componente qui sotto (dato puro, 2 righe);
#   3. una RIGA in `SPEC_STATUS`.
# Da lì derivano DA SOLI: binding del gate (`REGISTRY_BLOCCHI`), flag safe/unsafe
# (`FLAG_STATUS`), trasmissione col colpo (`TRASMISSIBILI`), sistema di tick
# (`sistemi_status`), persistenza nel save (tag registry) e foglia di calibrazione
# `STATUS.<nome>.durata_afflizione` (generata dall'enum). Il test di completezza
# (`test_status_estensibile.py`) inchioda la catena.

@dataclass(frozen=True)
class SpecStatus:
    """La riga-dato di un tipo di status: identità + comportamento + collocazioni.

    `blocco`: il membro del vocabolario AI-facing (None = status interno, mai
    emettibile da AI/asset — es. Confusione). `trasmissibile`: capacità OFFENSIVA,
    l'innato la applica col colpo; False = PASSIVA (cura il portatore).
    `con_sistema`: False = nessun tick deterministico (Confusione è AI-risolta,
    post-MVP). `persistente`: entra nel registry dei tag del save.

    ⚠️ **Qui non ci sono magnitudini.** `delta_per_rango` e `durata_afflizione` vivono in
    `calibrazione` come foglie §11 generate dall'enum `Blocco`, e `PROFILO_STATUS` le
    monta insieme a questa riga. Erano campi di questa dataclass — gli ultimi numeri di
    bilanciamento fuori dal catalogo: invisibili alla console di calibrazione e non
    tarabili senza toccare il codice. Questa riga dice *come si comporta* uno status;
    *quanto* fa male lo dice §11."""

    componente: type[Status]
    valenza: Valenza
    risoluzione: Risoluzione
    trasmissibile: bool = True
    blocco: Blocco | None = None
    con_sistema: bool = True
    persistente: bool = True
    # `tregua_scadenza=True` = alla scadenza lo status lascia una TREGUA sul
    # bersaglio: lo stesso tipo è RIFIUTATO per `STATUS.tregua_negazione`
    # turni (§11). È il contrappeso strutturale degli status che NEGANO
    # l'azione: col combattimento deterministico (niente proc) un colpo base
    # che storda è un lock perpetuo per costruzione — il playtest live
    # 2026-08-27 è morto 34→0 agendo UNA volta (l'Usciere ristordiva a ogni
    # colpo, sempre prima del turno del giocatore). Vale per entrambi i
    # lati: nemmeno il giocatore concatena stordimenti all'infinito.
    tregua_scadenza: bool = False
    # Il DESCRITTORE diegetico per la scheda/proiezione («avvelenato»,
    # «in fiamme»): B3 del playtest profondo 2026-08-28 — la proiezione
    # derivava i descrittori da un elenco cablato di tre status e il Brucia
    # era invisibile (si moriva di un DoT che la scheda non mostrava). La
    # tabella è l'unico proprietario: un nuovo status è visibile per
    # costruzione. "" = status senza descrittore (non compare in scheda).
    descrittore: str = ""


# La tabella porta il **comportamento** (chi trasmette, chi ha un system, chi persiste);
# le MAGNITUDINI stanno in `calibrazione` (§11) e si leggono al montaggio del profilo.
# Erano letterali qui: gli ultimi numeri di bilanciamento fuori dal catalogo, invisibili
# alla console e non tarabili senza toccare il codice.
SPEC_STATUS: tuple[SpecStatus, ...] = (
    SpecStatus(Veleno, Valenza.DANNOSO, Risoluzione.MOTORE, blocco=Blocco.VELENO,
               descrittore="avvelenato"),
    SpecStatus(Brucia, Valenza.DANNOSO, Risoluzione.MOTORE, blocco=Blocco.BRUCIA,
               descrittore="in fiamme"),
    SpecStatus(Rigenerazione, Valenza.BENEFICO, Risoluzione.MOTORE,
               trasmissibile=False, blocco=Blocco.RIGENERAZIONE,
               descrittore="in rigenerazione"),
    SpecStatus(Stordito, Valenza.DANNOSO, Risoluzione.MOTORE, blocco=Blocco.STORDITO,
               tregua_scadenza=True, descrittore="stordito"),
    SpecStatus(Confusione, Valenza.DANNOSO, Risoluzione.AI,
               trasmissibile=False, con_sistema=False, persistente=False,
               descrittore="confuso"),
)

SPEC_PER_TIPO: dict[type[Status], SpecStatus] = {s.componente: s for s in SPEC_STATUS}


def nome_status(tipo: type[Status]) -> str:
    """Il nome-dato stabile del tipo (chiave delle foglie §11 e dei tag di save)."""
    spec = SPEC_PER_TIPO.get(tipo)
    return spec.blocco.value if spec is not None and spec.blocco else tipo.__name__.lower()


# slug → descrittore diegetico, DERIVATO dalla tabella (B3): la mappa cablata
# che viveva in main.py (`_participio_status`) era il terzo proprietario della
# stessa verità — assorbita qui. I consumatori (proiezione scheda, cronaca)
# leggono questa, mai un elenco proprio.
DESCRITTORI_STATUS: dict[str, str] = {
    nome_status(s.componente): s.descrittore for s in SPEC_STATUS if s.descrittore
}


# --- Derivazioni (mai una seconda dichiarazione) --------------------------------

@dataclass(frozen=True)
class DeltaHp:
    """Il primitivo di tick «muovi HP» (GR2 §7.3): `per_rango × rango` a ogni
    tick — negativo ferisce, positivo cura (clampata al massimo). È il primo
    membro del vocabolario chiuso degli effetti-tick: un primitivo NUOVO
    (es. drenaggio-mana) è CODICE qui (Corsia 3), mai un dato più ricco."""

    per_rango: int


@dataclass(frozen=True)
class ProfiloStatus:
    """Vista comoda per i system: comportamento + durata d'afflizione (§11).

    `effetti_tick` è il comportamento del tick COME DATO (GR2 §7.3): il system
    generico la ITERA — «veleno letale», «rigenerazione celestiale» diventano
    righe di dati, non sistemi dedicati. `delta_per_rango` resta come vista
    comoda dei consumatori storici, derivato dallo stesso numero §11."""

    trasmissibile: bool
    delta_per_rango: int
    durata_afflizione: int
    effetti_tick: tuple = ()


def _profili_status() -> dict[type[Status], ProfiloStatus]:
    """Monta il profilo: comportamento dalla tabella, **numeri dal catalogo §11**.

    Uno status senza foglia (`Confusione`, che non ha un `Blocco` AI-facing) ripiega sui
    default — non è un buco: è uno status a risoluzione AI, senza tick deterministico."""
    from .calibrazione import DELTA_PER_RANGO, DURATA_AFFLIZIONE, DURATA_BLOCCO_DEFAULT

    profili: dict[type[Status], ProfiloStatus] = {}
    for s in SPEC_STATUS:
        delta = DELTA_PER_RANGO.get(nome_status(s.componente), 0)
        profili[s.componente] = ProfiloStatus(
            s.trasmissibile,
            delta,
            DURATA_AFFLIZIONE.get(nome_status(s.componente), DURATA_BLOCCO_DEFAULT),
            # Il dato riproduce lo storico bit-per-bit (oracolo in
            # test_status_tick_oracolo): delta 0 = tupla vuota, nessun effetto
            # (lo Stordito consuma il turno, non gli HP).
            effetti_tick=(DeltaHp(per_rango=delta),) if delta != 0 else (),
        )
    return profili


PROFILO_STATUS: dict[type[Status], ProfiloStatus] = _profili_status()

# I tipi che si trasmettono col colpo (derivato dalla tabella, mai una tupla nel loop).
TRASMISSIBILI: tuple[type[Status], ...] = tuple(
    s.componente for s in SPEC_STATUS if s.trasmissibile
)

# I tipi che round-trippano nel save (il tag registry li importa da qui).
STATUS_PERSISTENTI: tuple[type[Status], ...] = tuple(
    s.componente for s in SPEC_STATUS if s.persistente
)


def afflizione(tipo: type[Status], rango: int) -> Status:
    """Costruisce l'afflizione di `tipo` col rango COPIATO (G-6: autosufficiente) e la
    durata dalla tabella-dato (`DURATA_BLOCCO_DEFAULT` per i tipi fuori tabella)."""
    from .calibrazione import DURATA_BLOCCO_DEFAULT

    profilo = PROFILO_STATUS.get(tipo)
    turni = profilo.durata_afflizione if profilo is not None else DURATA_BLOCCO_DEFAULT
    return tipo(rango=rango, durata=turni, innato=False)


def afflizione_da(capacita: Status) -> Status:
    """L'afflizione trasmessa da una CAPACITÀ innata col colpo."""
    return afflizione(type(capacita), capacita.rango)


# --- La tregua di scadenza: il contrappeso degli status che negano l'azione ------

@dataclass
class TregueStatus:
    """Le tregue attive sull'entità: nome-status → turni residui di rifiuto.

    Componente TRANSIENTE di combattimento (mai nel tag registry del save: il
    save in scontro è vietato e fuori scontro la tregua è moot). Scritta da
    `SistemaStatus` alla scadenza, scalata dal proprietario unico
    `SistemaTregue`, letta da `applica_status` per rifiutare."""

    voci: dict[str, int]


def _in_tregua(entita: int, tipo: type[Status]) -> bool:
    tregue = esper.try_component(entita, TregueStatus)
    return tregue is not None and tregue.voci.get(nome_status(tipo), 0) > 0


def _apri_tregua(entita: int, tipo: type[Status]) -> None:
    from .calibrazione import valore

    turni = int(valore("STATUS.tregua_negazione"))
    if turni <= 0:
        return  # §11: tregua spenta — comportamento storico
    tregue = esper.try_component(entita, TregueStatus)
    if tregue is None:
        esper.add_component(entita, TregueStatus(voci={}))
        tregue = esper.component_for_entity(entita, TregueStatus)
    tregue.voci[nome_status(tipo)] = turni


class SistemaTregue(SistemaSempreAttivo):
    """Proprietario unico dello scorrere delle tregue (stessa cadenza G-24:
    solo l'entità attiva del giro). Registrato DERIVATO da `sistemi_status`."""

    def run(self, dt: int) -> None:
        entita = entita_attiva()
        if entita is None:
            return
        tregue = esper.try_component(entita, TregueStatus)
        if tregue is None:
            return
        for nome in list(tregue.voci):
            tregue.voci[nome] -= 1
            if tregue.voci[nome] <= 0:
                del tregue.voci[nome]
        if not tregue.voci:
            esper.remove_component(entita, TregueStatus)


# --- Applicazione: competizione per rango (G-7) -------------------------------

def applica_status(entita: int, status: Status) -> bool:
    """Applica `status` competendo con l'eventuale residente dello STESSO tipo (§4.2).

    - nessun residente → si applica;
    - `rango` nuovo **>** residente → il nuovo **vince**: subentra con la **propria
      durata fresca** (il residente è cancellato senza residui);
    - `rango` nuovo **≤** residente → il **residente vince**: si **rinfresca** il suo
      timer (non si **diluisce**: il rango resta quello alto), il nuovo è scartato.

    Confronto int-vs-int, fissato all'applicazione: deterministico, non tocca il seed.

    Ritorna **True se lo status è NUOVO** (nessun residente prima): è il fatto
    che decide se annunciarlo — un rinfresco non ristampa «Sei avvelenato!»
    (riscontro playtest 2026-08-12: doppia riga nella stessa cronaca quando
    innato trasmesso ed effetto di mossa applicavano lo stesso blocco).
    """
    tipo = type(status)
    if not status.innato and _in_tregua(entita, tipo):
        # La TREGUA rifiuta: il corpo ha appena scontato questo status e per
        # qualche turno non lo riprende (contrappeso del lock deterministico).
        # Il rifiuto è muto come un rinfresco: nessun «Sei stordito!» falso.
        return False
    residente = esper.try_component(entita, tipo)
    if residente is None:
        esper.add_component(entita, status)
        return True
    if status.rango > residente.rango:
        residente.rango = status.rango
        residente.durata = status.durata
    else:
        residente.durata = max(residente.durata, status.durata)
    return False


# --- Tick: un solo sistema per tipo, sempre-attivo, per-turno-dell'entità ------

def _applica_delta_hp(entita: int, delta: int) -> int | None:
    """Delega al proprietario UNICO della mutazione HP (`salute.muovi_hp`):
    qui viveva una delle quattro copie di «dove vivono gli HP», con la sua
    politica di clamp — ora la politica è in un posto solo."""
    from .salute import muovi_hp  # pigro: nessun ciclo status↔combattimento

    return muovi_hp(entita, delta)


def _nome_diegetico(entita: int) -> str:
    """Nome per gli eventi di vista: delega alla copia UNICA (`mob.nome_diegetico`
    — era duplicata byte-per-byte con `combattimento._nome_pubblico`)."""
    from .mob import nome_diegetico

    return nome_diegetico(entita)


class SistemaStatus(SistemaSempreAttivo):
    """Proprietario unico dell'avanzamento di UN tipo di status (G-5).

    Avanza **solo** lo status dell'entità attiva nel giro (G-24): se non c'è
    un'entità di turno (fuori combattimento, senza cadenza per-stanza ancora
    implementata — J), non avanza nulla.

    Gli status INNATI (capacità del mob) non sono afflizioni: quelli
    trasmissibili (veleno/brucia/stordito) agiscono sul colpo — mai sul
    portatore; le passive (rigenerazione) applicano l'effetto ma non scadono.

    GENERICO: il tipo arriva dal costruttore (la factory `sistemi_status` ne crea
    uno per riga di `SPEC_STATUS`) e il COMPORTAMENTO è DATO della tabella — mai
    una sottoclasse per aggiungere uno status. Le sottoclassi storiche sotto
    restano come alias di compatibilità (test/registrazioni esplicite).
    """

    tipo_status: type[Status] = Status

    def __init__(self, bus=None, *, tipo: type[Status] | None = None) -> None:
        self.bus = bus  # facoltativo: gli effetti si narrano sul Canale B
        if tipo is not None:
            self.tipo_status = tipo

    @property
    def _profilo(self) -> ProfiloStatus:
        return PROFILO_STATUS.get(self.tipo_status) or ProfiloStatus(True, 0, 1)

    def run(self, dt: int) -> None:
        entita = entita_attiva()
        if entita is None:
            return
        comp = esper.try_component(entita, self.tipo_status)
        if comp is None:
            return
        if comp.innato:
            if not self._profilo.trasmissibile:
                self.applica_effetto(entita, comp)  # passiva: effetto sì, scadenza no
            return
        self.applica_effetto(entita, comp)
        comp.durata -= 1
        if comp.durata <= 0:
            esper.remove_component(entita, self.tipo_status)
            spec = SPEC_PER_TIPO.get(self.tipo_status)
            if spec is not None and spec.tregua_scadenza:
                _apri_tregua(entita, self.tipo_status)
            if self.bus is not None:
                # La FINE si narra come l'inizio: prima il giocatore leggeva
                # «Sei avvelenato!» e i tick, mai quando il veleno smetteva.
                from contracts import StatusSvanito

                self.bus.pubblica(StatusSvanito(
                    bersaglio=_nome_diegetico(entita),
                    status=self.tipo_status.__name__.lower(),
                ))

    def applica_effetto(self, entita: int, comp: Status) -> None:
        """Il tick ITERA gli effetti-DATO del profilo (GR2 §7.3): il
        comportamento per-status è una tupla di primitivi chiusi, mai un ramo
        per-status nel system. Tupla vuota = nessun effetto (Stordito)."""
        for effetto in self._profilo.effetti_tick:
            if isinstance(effetto, DeltaHp):
                delta = effetto.per_rango * comp.rango
                _applica_delta_hp(entita, delta)
                if self.bus is not None:
                    from contracts import EffettoStatus

                    self.bus.pubblica(
                        EffettoStatus(
                            bersaglio=_nome_diegetico(entita),
                            status=self.tipo_status.__name__.lower(),
                            delta_hp=delta,
                        )
                    )


def sistemi_status(bus=None) -> list[SistemaSempreAttivo]:
    """UN system per ogni riga di `SPEC_STATUS` con tick deterministico, PIÙ il
    proprietario delle tregue di scadenza: è la registrazione derivata — un
    nuovo status non tocca né il guscio né gli harness (G-5)."""
    sistemi: list[SistemaSempreAttivo] = [
        SistemaStatus(bus, tipo=s.componente) for s in SPEC_STATUS if s.con_sistema
    ]
    # Il proprietario delle tregue corre PRIMA dei tick di status: la tregua
    # aperta da una scadenza in questo stesso turno non si consuma subito —
    # a `STATUS.tregua_negazione = 2` l'afflitto agisce 2 turni su 3 anche
    # sotto pressione continua (l'ordine è parte del contratto: lucchetto).
    sistemi.insert(0, SistemaTregue())
    return sistemi


# ⛔ **Gli alias storici sono stati RITIRATI** (`SistemaVeleno`, `SistemaBrucia`,
# `SistemaRigenerazione`, `SistemaStordito`). Erano sottoclassi nominate che facevano lo
# stesso lavoro di `sistemi_status()`, tenute per compatibilità — e convivevano con la
# derivazione: chi ne registrava una **insieme** al risultato di `sistemi_status()`
# faceva ticcare **due volte** lo stesso status, dimezzandone la durata in silenzio.
# Nessun test lo avrebbe visto, perché entrambe le strade "funzionano" da sole.
#
# Se ti serve il system di un tipo specifico: `SistemaStatus(bus, tipo=Veleno)`, oppure
# — quasi sempre la cosa giusta — `sistemi_status(bus)`, che li deriva tutti dalla
# tabella e non può produrne due per lo stesso status.


# NB: `Confusione` (unsafe, AI-risolto) NON ha un sistema-tick deterministico nell'MVP:
# la sua risoluzione richiede l'LLM (post-MVP, §7). Esiste solo come asse safe/unsafe.
