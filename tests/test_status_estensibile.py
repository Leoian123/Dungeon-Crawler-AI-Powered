"""Audit 2026-08 — gli status si INTRODUCONO con tre tocchi, il resto deriva.

La ricetta (documentata in status.py): 1 riga nell'enum `Blocco` (contracts) +
la classe-componente + 1 riga in `SPEC_STATUS`. Da lì derivano DA SOLI: binding
del gate (`REGISTRY_BLOCCHI`), flag safe/unsafe (`FLAG_STATUS`), trasmissione col
colpo (`TRASMISSIBILI`), sistema di tick (`sistemi_status`), persistenza nel save
(tag registry) e foglia §11 `STATUS.<nome>.durata_afflizione` (generata dall'enum).

Il test di completezza qui sotto è il LUCCHETTO della catena: se si aggiunge un
nome all'enum senza la riga di tabella (o viceversa) la suite lo dice subito, con
un messaggio chiaro — mai un "nome accettabile ma non istanziabile" (F-6).

`Brucia` è la dimostrazione: prima dell'audit il sistema/tag/foglia esistevano ma
il nome non era nel vocabolario → tutto irraggiungibile. Ora è un Blocco vero:
innato su un mob, trasmesso col colpo, applicato dalla mossa `sputo_infuocato`.
"""

from __future__ import annotations

import esper

from contracts import Blocco, EntitaGenerata, Grado, StatusApplicato
from motore import (
    Brucia,
    CATALOGO_MOSSE,
    FLAG_STATUS,
    REGISTRY_BLOCCHI,
    Repertorio,
    SPEC_STATUS,
    SistemaStatus,
    istanzia_entita,
    sistemi_status,
    tick,
)
from motore.calibrazione import CATALOGO, DURATA_AFFLIZIONE
from motore.persistenza.tag import e_persistente
from motore.scheda import protagonista
from motore.status import PROFILO_STATUS, TRASMISSIBILI, nome_status
from tests.combat_helpers import avvia_scontro


# --- Il lucchetto: ogni derivazione copre ogni voce, senza buchi -----------------

def test_completezza_della_catena_status() -> None:
    per_blocco = {s.blocco: s for s in SPEC_STATUS if s.blocco is not None}
    # 1) Ogni Blocco dell'enum ha la sua riga di tabella (e quindi il binding F-6).
    for blocco in Blocco:
        assert blocco in per_blocco, (
            f"Blocco.{blocco.name} è nell'enum ma non in SPEC_STATUS: aggiungi la "
            "riga di tabella in status.py (è il 3° tocco della ricetta)"
        )
        assert REGISTRY_BLOCCHI[blocco] is per_blocco[blocco].componente
        # 2) La foglia §11 è generata dall'enum: durata editabile da console/SPA.
        assert f"STATUS.{blocco.value}.durata_afflizione" in CATALOGO
        assert blocco.value in DURATA_AFFLIZIONE
    # 3) Ogni riga di tabella ha flag, profilo, e (se persistente) il tag di save.
    for spec in SPEC_STATUS:
        assert spec.componente in FLAG_STATUS
        assert spec.componente in PROFILO_STATUS
        assert e_persistente(spec.componente) is spec.persistente
    # 4) Un sistema di tick per ogni riga con_sistema, col tipo giusto (G-5).
    tipi_sistemi = [s.tipo_status for s in sistemi_status()]
    attesi = [s.componente for s in SPEC_STATUS if s.con_sistema]
    assert tipi_sistemi == attesi
    assert all(isinstance(s, SistemaStatus) for s in sistemi_status())
    # 5) La trasmissione col colpo è derivata, mai una tupla nel loop.
    assert set(TRASMISSIBILI) == {s.componente for s in SPEC_STATUS if s.trasmissibile}


def test_nome_status_stabile_per_i_tag() -> None:
    # Il tag di save = nome-dato del tipo (H-3): per i blocchi è il valore d'enum.
    assert nome_status(Brucia) == "brucia"
    from motore import Confusione
    assert nome_status(Confusione) == "confusione"  # fuori vocabolario: nome classe


# --- Brucia, end-to-end: da vicolo cieco a status completo -----------------------

def test_brucia_innato_si_trasmette_col_colpo(mondo_isolato: str) -> None:
    eg = EntitaGenerata(
        archetipo="slime", grado=Grado.BRONZO, blocchi=[Blocco.BRUCIA],
        nome="Slime Lavico", descrizione="",
    )
    ent = istanzia_entita(eg, livello=1)
    assert esper.component_for_entity(ent, Brucia).innato is True

    bus, _adapter, _enc = avvia_scontro(nemici=[], arruolate=[ent], destrezza_prot=1)
    applicati: list[StatusApplicato] = []
    bus.registra(StatusApplicato, applicati.append)
    for _ in range(20):
        tick()
        if applicati:
            break
    assert applicati and applicati[0].status == "brucia"
    pent, _marker, _scheda = protagonista()
    afflizione = esper.component_for_entity(pent, Brucia)
    assert afflizione.innato is False
    assert afflizione.durata == DURATA_AFFLIZIONE["brucia"]


def test_sputo_infuocato_applica_brucia(mondo_isolato: str) -> None:
    eg = EntitaGenerata(
        archetipo="goblin", grado=Grado.BRONZO, blocchi=[],
        nome="Piromane", descrizione="",
    )
    ent = istanzia_entita(eg, livello=1)
    esper.add_component(ent, Repertorio(mosse=("sputo_infuocato",)))
    assert "sputo_infuocato" in CATALOGO_MOSSE  # la mossa è una voce di catalogo

    bus, _adapter, _enc = avvia_scontro(nemici=[], arruolate=[ent], destrezza_prot=1)
    applicati: list[StatusApplicato] = []
    bus.registra(StatusApplicato, applicati.append)
    for _ in range(20):
        tick()
        if applicati:
            break
    assert applicati and applicati[0].status == "brucia"
    pent, _marker, _scheda = protagonista()
    assert esper.component_for_entity(pent, Brucia).innato is False


def test_brucia_ammesso_negli_asset() -> None:
    """Un mob-asset può dichiarare BRUCIA nei blocchi: il lint F-6 lo accetta
    (prima dell'audit il nome non esisteva nel vocabolario)."""
    from contracts import MobAsset
    from motore import lint_registry

    mob = MobAsset(
        slug="salamandra", nome="Salamandra", archetipo="slime",
        grado=Grado.BRONZO, blocchi=[Blocco.BRUCIA], prosa_stanza="Sfrigola.",
    )
    assert lint_registry([mob.archetipo], mob.blocchi) == []
