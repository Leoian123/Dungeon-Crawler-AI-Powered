"""Fase 1 — le mosse sono DATI: catalogo `CATALOGO_MOSSE`, componente `Repertorio`,
primitivo `ApplicaStatus`, danno TIPATO che attiva il layer resistenze.

Il system (`_scegli_azione`) esegue; cosa esiste lo decide il dato: la scelta resta
del motore, seeded (G-4), e il comportamento storico è il repertorio di default.
"""

from __future__ import annotations

import random

import esper

from contracts import (
    Blocco,
    ColpoInferto,
    EntitaGenerata,
    Grado,
    StatusApplicato,
    TipoDanno,
)
from motore import (
    CATALOGO_MOSSE,
    MOSSE_DEFAULT,
    Repertorio,
    Veleno,
    azione_da_mossa,
    istanzia_entita,
    mosse_note,
    rango_grado,
    tick,
)
from motore.azione import ApplicaStatus, Danno
from motore.calibrazione import DURATA_AFFLIZIONE, MOLT_ATTACCO_PESANTE
from motore.combattimento import mult_resistenza, risolvi_danno
from motore.modificatori import ResistenzaMod, applica_resistenza
from motore.persistenza.tag import e_persistente
from motore.scheda import protagonista
from tests.combat_helpers import avvia_scontro


def _mob(archetipo: str, grado: Grado, *, mosse: tuple[str, ...] | None = None) -> int:
    eg = EntitaGenerata(
        archetipo=archetipo, grado=grado, blocchi=[], nome="Cavia", descrizione="",
    )
    ent = istanzia_entita(eg, livello=1)
    if mosse is not None:
        esper.add_component(ent, Repertorio(mosse=mosse))  # sovrascrive il default
    return ent


# --- Il catalogo: chiave → Azione (composizione, non codice nel loop) -----------

def test_catalogo_traduce_chiave_in_azione() -> None:
    az = azione_da_mossa("attacco_pesante", sorgente=1, bersaglio=2)
    assert az.mossa == "attacco_pesante" and az.costo == {"AP": 1}
    (danno,) = az.effetti
    assert isinstance(danno, Danno)
    assert danno.tipo is TipoDanno.MISCHIA          # il danno base è TIPATO (DT-1 attivo)
    assert danno.moltiplicatore == MOLT_ATTACCO_PESANTE

    assert MOSSE_DEFAULT == ("attacco", "attacco_pesante")  # lo storico, ora come dato
    assert mosse_note() >= {"attacco", "attacco_pesante", "morso_velenoso"}
    # La composizione di primitivi (G-23): morso = Danno + ApplicaStatus, in DATI.
    effetti = CATALOGO_MOSSE["morso_velenoso"].effetti
    assert [type(e) for e in effetti] == [Danno, ApplicaStatus]
    assert effetti[1].blocco is Blocco.VELENO


def test_repertorio_e_persistente() -> None:
    assert e_persistente(Repertorio)


# --- Il repertorio guida la scelta seeded del motore ----------------------------

def test_repertorio_custom_vincola_le_mosse(mondo_isolato: str) -> None:
    ent = _mob("slime", Grado.BRONZO, mosse=("attacco_pesante",))
    bus, _adapter, _enc = avvia_scontro(nemici=[], arruolate=[ent], destrezza_prot=1)
    colpi: list[ColpoInferto] = []
    bus.registra(ColpoInferto, colpi.append)

    for _ in range(20):
        tick()
        if colpi:
            break
    nemiche = [c for c in colpi if c.attaccante == "Cavia"]
    assert nemiche, "il mob deve aver colpito"
    assert all(c.mossa == "attacco_pesante" for c in nemiche)  # solo la mossa dichiarata


def test_istanzia_attacca_il_repertorio_default(mondo_isolato: str) -> None:
    ent = _mob("goblin", Grado.BRONZO)  # nessun override
    rep = esper.component_for_entity(ent, Repertorio)
    assert tuple(rep.mosse) == MOSSE_DEFAULT


# --- ApplicaStatus: afflizione dal catalogo, rango dal grado della sorgente -----

def test_applica_status_col_rango_del_grado(mondo_isolato: str) -> None:
    ent = _mob("goblin", Grado.ARGENTO, mosse=("morso_velenoso",))
    bus, _adapter, _enc = avvia_scontro(nemici=[], arruolate=[ent], destrezza_prot=1)
    applicati: list[StatusApplicato] = []
    bus.registra(StatusApplicato, applicati.append)

    for _ in range(20):
        tick()
        if applicati:
            break
    assert applicati and applicati[0].status == "veleno"
    pent, _marker, _scheda = protagonista()
    vel = esper.component_for_entity(pent, Veleno)
    assert vel.innato is False
    assert vel.rango == rango_grado(Grado.ARGENTO)          # copiato dal GRADO (G §4.3)
    assert vel.durata == DURATA_AFFLIZIONE["veleno"]        # dalla tabella-dato §11


# --- Danno tipato: il layer resistenze non è più inerte -------------------------

def test_danno_tipato_incrocia_le_resistenze(mondo_isolato: str) -> None:
    sorgente = _mob("goblin", Grado.BRONZO)
    bersaglio = _mob("slime", Grado.BRONZO)
    attacco = CATALOGO_MOSSE["attacco"].effetti[0]

    d_neutro = risolvi_danno(attacco, sorgente, bersaglio, random.Random(9))
    # +100% di vulnerabilità alla MISCHIA → moltiplicatore 2.0 sul colpo tipato.
    applica_resistenza(bersaglio, ResistenzaMod(contro=TipoDanno.MISCHIA, valore=100.0, fonte="test"))
    assert mult_resistenza(bersaglio, TipoDanno.MISCHIA) == 2.0
    d_vulnerabile = risolvi_danno(attacco, sorgente, bersaglio, random.Random(9))
    assert d_vulnerabile > d_neutro

    # Un danno GENERICO (untyped) NON incrocia quella resistenza: identità DT-6.
    generico = Danno(quantita_da=attacco.quantita_da)
    assert risolvi_danno(generico, sorgente, bersaglio, random.Random(9)) == d_neutro
