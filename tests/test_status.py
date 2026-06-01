"""Status: shape/rango (G-6), single-owner sempre-attivo (G-5), competizione per
rango (G-7), un componente per tipo + coesistenza (G-8), burn-rate invariante al
numero di nemici (G-24).
"""

from __future__ import annotations

import dataclasses
from contextlib import contextmanager
from pathlib import Path

import esper

from motore import (
    Brucia,
    Combattente,
    Rigenerazione,
    SistemaBrucia,
    SistemaRigenerazione,
    SistemaSempreAttivo,
    SistemaSoloCombattimento,
    SistemaVeleno,
    SpecNemico,
    Status,
    Veleno,
    applica_status,
    entita_attiva,
    protagonista,
    segna_turno_attivo,
    tick,
)
from tests.combat_helpers import avvia_scontro

_MOTORE = Path(__file__).resolve().parents[1] / "src" / "motore"


# --- G-6: rango: int, nessun riferimento alla fonte ---------------------------

def test_G6_status_porta_rango_e_nessuna_fonte() -> None:
    proibiti = {"fonte", "sorgente", "source", "applicatore", "origine", "entita", "owner"}
    for tipo in (Status, Veleno, Brucia, Rigenerazione):
        nomi = {f.name for f in dataclasses.fields(tipo)}
        assert "rango" in nomi, f"{tipo.__name__} deve portare `rango`"
        assert not (nomi & proibiti), f"{tipo.__name__} non deve referenziare la fonte"
    v = Veleno(rango=3, durata=2)
    assert isinstance(v.rango, int)


# --- G-5: nessun handler di status in solo-combattimento; un solo proprietario -

def test_G5_status_solo_nel_bucket_sempre_attivo() -> None:
    for sistema in (SistemaVeleno, SistemaBrucia, SistemaRigenerazione):
        assert issubclass(sistema, SistemaSempreAttivo)
        assert not issubclass(sistema, SistemaSoloCombattimento)
    # Mappa tipo→sistema iniettiva: un solo proprietario per tipo.
    tipi = [SistemaVeleno.tipo_status, SistemaBrucia.tipo_status, SistemaRigenerazione.tipo_status]
    assert tipi == [Veleno, Brucia, Rigenerazione]
    assert len(set(tipi)) == 3


def test_G5_avanzamento_status_solo_in_status_py() -> None:
    # L'avanzamento (mutazione di `durata`) vive SOLO in status.py: i sistemi
    # solo-combattimento non toccano la durata degli status.
    for nome in ("combattimento", "mutazione"):
        src = (_MOTORE / f"{nome}.py").read_text(encoding="utf-8")
        assert "durata" not in src, f"{nome}.py non deve avanzare gli status (durata)"


# --- G-7: competizione per rango ----------------------------------------------

def test_G7_competizione_per_rango(mondo_isolato: str) -> None:
    e = esper.create_entity()

    applica_status(e, Veleno(rango=2, durata=3))
    # Rango più alto → il nuovo VINCE, durata fresca; il residente è cancellato.
    applica_status(e, Veleno(rango=5, durata=10))
    v = esper.component_for_entity(e, Veleno)
    assert (v.rango, v.durata) == (5, 10)
    assert len(esper.get_component(Veleno)) == 1  # una sola istanza

    # Rango più basso → il RESIDENTE vince: rinfresca il timer, NON diluisce il rango.
    v.durata = 2
    applica_status(e, Veleno(rango=1, durata=8))
    v = esper.component_for_entity(e, Veleno)
    assert v.rango == 5            # non diluito dal rango basso
    assert v.durata == 8          # rinfrescato

    # Rango uguale → rinfresca comunque il timer del vincitore.
    v.durata = 1
    applica_status(e, Veleno(rango=5, durata=4))
    assert esper.component_for_entity(e, Veleno).durata == 4


# --- G-8: un componente per tipo; tipi diversi coesistono e ticcano in parallelo

def test_G8_un_per_tipo_e_coesistenza(mondo_isolato: str) -> None:
    e = esper.create_entity()
    applica_status(e, Veleno(rango=2, durata=3))
    applica_status(e, Veleno(rango=4, durata=3))  # stesso tipo → resta UNA istanza
    assert sum(1 for ent, _ in esper.get_component(Veleno) if ent == e) == 1

    applica_status(e, Brucia(rango=1, durata=2))  # tipo diverso → coesiste
    assert esper.has_component(e, Veleno) and esper.has_component(e, Brucia)

    # Tick in parallelo sui due tipi (l'entità è quella attiva).
    segna_turno_attivo(e)
    SistemaVeleno().run(1)
    SistemaBrucia().run(1)
    assert esper.component_for_entity(e, Veleno).durata == 2  # 3 → 2
    assert esper.component_for_entity(e, Brucia).durata == 1  # 2 → 1


# --- G-24: burn-rate invariante al numero di nemici ---------------------------

@contextmanager
def _mondo(nome: str):
    esper.switch_world(nome)
    try:
        yield
    finally:
        esper.switch_world("default")
        esper.delete_world(nome)


def _turni_prot_per_esaurire_veleno(*, nemici_n: int, cariche: int) -> int:
    avvia_scontro(
        nemici=[SpecNemico(destrezza=5, punti_vita=10**9) for _ in range(nemici_n)],
        hp_prot=10**9, destrezza_prot=10, seed=7,
    )
    pent, _marker, _scheda = protagonista()
    applica_status(pent, Veleno(rango=1, durata=cariche))

    turni = 0
    for _ in range(1000):
        if not esper.has_component(pent, Veleno):
            break
        tick()
        if entita_attiva() == pent:  # un turno del protagonista appena risolto
            turni += 1
    return turni


def test_G24_burn_rate_invariante_al_numero_di_nemici() -> None:
    with _mondo("g24-1v1"):
        t_1v1 = _turni_prot_per_esaurire_veleno(nemici_n=1, cariche=3)
    with _mondo("g24-1v3"):
        t_1v3 = _turni_prot_per_esaurire_veleno(nemici_n=3, cariche=3)

    # "3 cariche" dura 3 turni del protagonista, sia in 1-vs-1 sia in 1-vs-3.
    assert t_1v1 == 3
    assert t_1v3 == 3
