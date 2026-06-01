"""Loop di combattimento: AP, iniziativa, decisione nemici, death-check, ciclo di vita
delle entità effimere (G §2, §6.2; G-1/3/4/11; FNC §6.3).

Tutto deterministico e **seeded** (FNC §9). **Nessun LLM nel percorso di risoluzione**
(G-4): questo modulo non importa né chiama il provider.

I *numeri* (to-hit, danno, formula-madre) sono Gruppo 2: qui sono segnaposto
(`DANNO_BASE`), la **forma** è completa.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import esper

from contracts import CombatResolved, EncounterStarted, MortePersonaggio, StatId

from .phased import SistemaSempreAttivo, SistemaSoloCombattimento
from .scheda import Protagonista, Scheda, protagonista
from .statistiche import stat_eff
from .turno import azzera_turno_attivo, segna_turno_attivo

# AP max clampato a 1 nell'MVP; i talenti (post-MVP) alzano il max o danno azioni
# bonus. Il loop è scritto AP-driven fin da subito (§2.1).
AP_MAX_MVP = 1

# Segnaposto Gruppo 2.
DANNO_BASE = 1


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
    d'iniziativa — MAI l'id di entità esper (sequenziale e riciclato, G-3/§6.3).
    """

    destrezza: int
    chiave_ordine: int
    ap: int
    ap_max: int


@dataclass
class SpecNemico:
    """Specifica di un nemico da materializzare (composta a monte dall'AI/placeholder)."""

    destrezza: int
    punti_vita: int


@dataclass
class PianoIncontro:
    """Composizione dell'incontro, preparata in narrazione (AI a monte, §5.1).

    Il motore la materializza su `EncounterStarted`. `seed` borda il nondeterminismo
    della risoluzione (FNC §9).
    """

    nemici: list[SpecNemico]
    seed: int


@dataclass
class StatoCombattimento:
    """Stato del giro di combattimento (singleton effimero). Un solo proprietario:
    `SistemaTurnoCombattimento`."""

    ordine: list[int]              # iniziativa: id entità in ordine di attivazione
    indice: int
    round: int
    prossima_chiave: int           # contatore stabile per `chiave_ordine` (spawn order)
    rng: random.Random             # RNG seeded del motore (decisioni nemici)


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
    l'ordine d'iniziativa: lo gestisce il chiamante (materializzazione o rinforzi)."""
    st = stato_combattimento()
    if st is None:
        raise RuntimeError("spawn_nemico richiede uno StatoCombattimento attivo")
    _ent_stato, stato = st
    chiave = stato.prossima_chiave
    stato.prossima_chiave += 1
    return esper.create_entity(
        Nemico(),
        Combattente(destrezza=destrezza, chiave_ordine=chiave, ap=AP_MAX_MVP, ap_max=AP_MAX_MVP),
        PuntiVita(attuali=punti_vita, massimi=punti_vita),
    )


def _nemici_vivi() -> list[int]:
    return [ent for ent, _ in esper.get_component(Nemico) if _e_vivo(ent)]


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

        # Marca l'entità attiva: i sistemi-status (sempre-attivo) ticcano solo lei (G-24).
        segna_turno_attivo(attivo)

        combattente = esper.component_for_entity(attivo, Combattente)
        combattente.ap = combattente.ap_max

        # Loop a Action Point — scritto AP-driven anche con max=1 (G-1).
        while combattente.ap > 0:
            self._risolvi_azione(attivo, stato)
            combattente.ap -= 1

        # Condizione di vittoria: nessun nemico vivo → torna in narrazione.
        if not _nemici_vivi():
            self.bus.pubblica(CombatResolved(entita=attivo, vittoria=True))

    def _risolvi_azione(self, attivo: int, stato: StatoCombattimento) -> None:
        if esper.has_component(attivo, Protagonista):
            bersagli = _nemici_vivi()
            if bersagli:
                infliggi_danno(bersagli[0], DANNO_BASE)
            return
        # Nemico: decisione del MOTORE, seeded (G-4). Mai LLM.
        pent, _marker, pscheda = protagonista()
        bersagli = [pent] if (pscheda.vivo and pscheda.punti_vita > 0) else []
        azione = decidi_azione_nemico(stato.rng, bersagli)
        if azione is not None:
            bersaglio, _mossa = azione
            infliggi_danno(bersaglio, DANNO_BASE)


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
            Combattente(destrezza=stat_eff(pent, StatId.DESTREZZA), chiave_ordine=chiave_prot,
                        ap=AP_MAX_MVP, ap_max=AP_MAX_MVP),
        )

        for spec in piano.nemici:
            spawn_nemico(destrezza=spec.destrezza, punti_vita=spec.punti_vita)

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
