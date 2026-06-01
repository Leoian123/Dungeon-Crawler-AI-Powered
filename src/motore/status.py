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
    """Base dato puro di ogni status. `rango` copiato dall'applicatore (§4.3)."""

    rango: int
    durata: int


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

class _SistemaStatusBase(SistemaSempreAttivo):
    """Proprietario unico dell'avanzamento di UN tipo di status (G-5).

    Avanza **solo** lo status dell'entità attiva nel giro (G-24): se non c'è
    un'entità di turno (fuori combattimento, senza cadenza per-stanza ancora
    implementata — J), non avanza nulla.
    """

    tipo_status: type[Status] = Status

    def run(self, dt: int) -> None:
        entita = entita_attiva()
        if entita is None:
            return
        comp = esper.try_component(entita, self.tipo_status)
        if comp is None:
            return
        self.applica_effetto(entita, comp)  # effetto placeholder (Gruppo 2)
        comp.durata -= 1
        if comp.durata <= 0:
            esper.remove_component(entita, self.tipo_status)

    def applica_effetto(self, entita: int, comp: Status) -> None:
        """Effetto al tick. Default: nessuno (i numeri sono Gruppo 2)."""


class SistemaVeleno(_SistemaStatusBase):
    tipo_status = Veleno


class SistemaBrucia(_SistemaStatusBase):
    tipo_status = Brucia


class SistemaRigenerazione(_SistemaStatusBase):
    tipo_status = Rigenerazione


class SistemaStordito(_SistemaStatusBase):
    tipo_status = Stordito
