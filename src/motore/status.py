"""Status: shape, stacking, rango, tick single-owner (G §4; G-5/6/7/8/24).

Gli status sono componenti **dato puro** (ESP §1): `rango: int` + `durata: int`,
**nessun riferimento alla fonte** (G-6: la fonte è effimera, il rango è *copiato*
all'applicazione e lo status diventa autosufficiente).

Stacking = **un'istanza per tipo** sulla stessa entità (default ECS: `add_component`
sovrascrive). Riapplicare lo stesso tipo NON affianca una copia: **compete per rango**
(`applica_status`). Tipi diversi coesistono e ticcano in parallelo (G-8).

Tick = **un solo proprietario per tipo**, nel bucket **sempre-attivo** (G-5): un
`SistemaVeleno` possiede tutti i `Veleno`, ecc. Cadenza in combattimento =
**per-turno-dell'entità** (G-24): si avanza solo lo status dell'entità attiva
(`TurnoAttivo`), così il burn-rate è invariante al numero di nemici.

I *numeri* (durate, danni, scala dei ranghi) sono Gruppo 2: qui l'effetto-al-tick è
un hook placeholder (default: nessun danno), la forma è completa.
"""

from __future__ import annotations

from dataclasses import dataclass

import esper

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


def afflizione_da(capacita: Status) -> Status:
    """L'afflizione trasmessa da una CAPACITÀ innata col colpo (rango COPIATO,
    G-6: lo status diventa autosufficiente). Lo stordimento si applica corto
    (1 turno): niente stun-lock. La durata è §11 (`DURATA_BLOCCO_DEFAULT`)."""
    from .calibrazione import DURATA_BLOCCO_DEFAULT

    tipo = type(capacita)
    turni = 1 if tipo is Stordito else DURATA_BLOCCO_DEFAULT
    return tipo(rango=capacita.rango, durata=turni, innato=False)


# --- Applicazione: competizione per rango (G-7) -------------------------------

def applica_status(entita: int, status: Status) -> None:
    """Applica `status` competendo con l'eventuale residente dello STESSO tipo (§4.2).

    - nessun residente → si applica;
    - `rango` nuovo **>** residente → il nuovo **vince**: subentra con la **propria
      durata fresca** (il residente è cancellato senza residui);
    - `rango` nuovo **≤** residente → il **residente vince**: si **rinfresca** il suo
      timer (non si **diluisce**: il rango resta quello alto), il nuovo è scartato.

    Confronto int-vs-int, fissato all'applicazione: deterministico, non tocca il seed.
    """
    tipo = type(status)
    residente = esper.try_component(entita, tipo)
    if residente is None:
        esper.add_component(entita, status)
    elif status.rango > residente.rango:
        residente.rango = status.rango
        residente.durata = status.durata
    else:
        residente.durata = max(residente.durata, status.durata)


# --- Tick: un solo sistema per tipo, sempre-attivo, per-turno-dell'entità ------

def _applica_delta_hp(entita: int, delta: int) -> int | None:
    """Muove gli HP dove vivono (`Scheda` per il protagonista, `PuntiVita` per i
    nemici), clampando la CURA al massimo. Ritorna gli HP risultanti (o None).
    Import locali: evitano cicli col modulo di combattimento."""
    from .scheda import Scheda

    scheda = esper.try_component(entita, Scheda)
    if scheda is not None:
        if delta > 0:
            from .derivate import max_hp

            scheda.punti_vita = min(scheda.punti_vita + delta, max_hp(entita))
        else:
            scheda.punti_vita += delta
        return scheda.punti_vita
    from .combattimento import PuntiVita

    pv = esper.try_component(entita, PuntiVita)
    if pv is not None:
        pv.attuali = min(pv.attuali + delta, pv.massimi) if delta > 0 else pv.attuali + delta
        return pv.attuali
    return None


def _nome_diegetico(entita: int) -> str:
    """Nome per gli eventi di vista: il nome del mob, "" per il protagonista."""
    from .narrazione import EntitaMob  # locale: narrazione importa già questo modulo
    from .scheda import Protagonista

    em = esper.try_component(entita, EntitaMob)
    if em is not None:
        return em.nome
    return "" if esper.has_component(entita, Protagonista) else "il nemico"


class _SistemaStatusBase(SistemaSempreAttivo):
    """Proprietario unico dell'avanzamento di UN tipo di status (G-5).

    Avanza **solo** lo status dell'entità attiva nel giro (G-24): se non c'è
    un'entità di turno (fuori combattimento, senza cadenza per-stanza ancora
    implementata — J), non avanza nulla.

    Gli status INNATI (capacità del mob) non sono afflizioni: quelli
    trasmissibili (veleno/brucia/stordito) agiscono sul colpo — mai sul
    portatore; le passive (rigenerazione) applicano l'effetto ma non scadono.
    """

    tipo_status: type[Status] = Status
    trasmissibile: bool = True  # capacità OFFENSIVA: si trasmette col colpo
    delta_per_rango: int = 0    # HP mossi per tick d'afflizione (− danno, + cura)

    def __init__(self, bus=None) -> None:
        self.bus = bus  # facoltativo: gli effetti si narrano sul Canale B

    def run(self, dt: int) -> None:
        entita = entita_attiva()
        if entita is None:
            return
        comp = esper.try_component(entita, self.tipo_status)
        if comp is None:
            return
        if comp.innato:
            if not self.trasmissibile:
                self.applica_effetto(entita, comp)  # passiva: effetto sì, scadenza no
            return
        self.applica_effetto(entita, comp)
        comp.durata -= 1
        if comp.durata <= 0:
            esper.remove_component(entita, self.tipo_status)

    def applica_effetto(self, entita: int, comp: Status) -> None:
        """Effetto al tick: `delta_per_rango × rango` HP (0 = nessun effetto)."""
        if self.delta_per_rango == 0:
            return
        delta = self.delta_per_rango * comp.rango
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


class SistemaVeleno(_SistemaStatusBase):
    tipo_status = Veleno
    delta_per_rango = -1


class SistemaBrucia(_SistemaStatusBase):
    tipo_status = Brucia
    delta_per_rango = -1


class SistemaRigenerazione(_SistemaStatusBase):
    tipo_status = Rigenerazione
    trasmissibile = False  # capacità PASSIVA: rigenera il portatore, non si trasmette
    delta_per_rango = 1


class SistemaStordito(_SistemaStatusBase):
    tipo_status = Stordito
    # Nessun delta HP: l'effetto (saltare il turno) lo consulta il loop di
    # combattimento; qui solo il decorso dell'afflizione (durata).


# NB: `Confusione` (unsafe, AI-risolto) NON ha un sistema-tick deterministico nell'MVP:
# la sua risoluzione richiede l'LLM (post-MVP, §7). Esiste solo come asse safe/unsafe.
