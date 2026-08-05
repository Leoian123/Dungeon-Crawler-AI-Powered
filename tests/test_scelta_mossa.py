"""Il canale della SCELTA: la mossa del giocatore arriva davvero al risolutore.

Prima esisteva solo `richiedi_fuga`: l'indice 0 del menu non trasportava nulla e la
mossa del protagonista era cablata ad "attacco" (il `Repertorio` veniva risolto e
scartato alla riga dopo). Qui si prova che il menu è DATO, che la scelta viaggia, e
che il motore resta l'autorità su cosa è lecito.
"""

from __future__ import annotations

import asyncio

import esper
import pytest

from contracts import Blocco, ColpoInferto, Grado, MobAsset, PlayerChoseOption
from motore import (
    MOSSE_DEFAULT,
    Repertorio,
    etichetta_mossa,
    mosse_di,
    richiedi_mossa,
    tick,
)
from motore.combattimento import SpecNemico, stato_combattimento
from motore.scheda import MOSSE_INIZIALI_PROTAGONISTA, crea_protagonista, protagonista
from tests.combat_helpers import avvia_scontro
from main import costruisci_sessione
from tests.test_combat_feel import _apri_scontro, _indice, _stagione


# --- Il protagonista PORTA le sue mosse (dato persistente) ----------------------

def test_il_protagonista_nasce_con_un_repertorio(mondo_isolato: str) -> None:
    ent = crea_protagonista(destrezza=10)
    rep = esper.component_for_entity(ent, Repertorio)
    assert rep.mosse == MOSSE_INIZIALI_PROTAGONISTA
    assert mosse_di(ent) == MOSSE_INIZIALI_PROTAGONISTA


def test_senza_repertorio_si_ripiega_sul_default(mondo_isolato: str) -> None:
    """Save legacy: il componente non c'è → il comportamento storico regge."""
    ent = crea_protagonista(destrezza=10)
    esper.remove_component(ent, Repertorio)
    assert mosse_di(ent) == MOSSE_DEFAULT


# --- La scelta viaggia fino al risolutore ---------------------------------------

def _scontro_con_prot():
    """Uno scontro headless con un nemico che non muore al primo colpo."""
    return avvia_scontro(nemici=[SpecNemico(destrezza=1, punti_vita=10_000)], seed=1)


def test_la_mossa_scelta_arriva_al_colpo(mondo_isolato: str) -> None:
    bus, _adapter, _enc = _scontro_con_prot()
    colpi: list[ColpoInferto] = []
    bus.registra(ColpoInferto, colpi.append)

    assert richiedi_mossa("attacco_pesante") is True
    tick()  # il turno del protagonista

    miei = [c for c in colpi if c.attaccante == ""]
    assert miei and miei[-1].mossa == "attacco_pesante", (
        "la mossa scelta non è arrivata al risolutore"
    )


def test_senza_scelta_resta_l_attacco_base(mondo_isolato: str) -> None:
    bus, _adapter, _enc = _scontro_con_prot()
    colpi: list[ColpoInferto] = []
    bus.registra(ColpoInferto, colpi.append)

    tick()  # nessuna richiesta: il default non cambia

    miei = [c for c in colpi if c.attaccante == ""]
    assert miei and miei[-1].mossa == "attacco"


def test_la_scelta_si_consuma_in_un_solo_turno(mondo_isolato: str) -> None:
    """One-shot come `fuga_richiesta`: il turno dopo si torna all'attacco base."""
    bus, _adapter, _enc = _scontro_con_prot()
    colpi: list[ColpoInferto] = []
    bus.registra(ColpoInferto, colpi.append)

    richiedi_mossa("attacco_pesante")
    tick()
    assert stato_combattimento()[1].mossa_richiesta is None
    colpi.clear()
    for _ in range(4):  # il giro passa dal nemico: si ticca fino al mio turno
        tick()
        if [c for c in colpi if c.attaccante == ""]:
            break
    miei = [c for c in colpi if c.attaccante == ""]
    assert miei and miei[-1].mossa == "attacco"


# --- Il motore è l'autorità: cosa NON si può chiedere ----------------------------

def test_mossa_fuori_dal_repertorio_rifiutata(mondo_isolato: str) -> None:
    """`morso_velenoso` esiste nel catalogo ma NON è del protagonista."""
    _scontro_con_prot()
    assert richiedi_mossa("morso_velenoso") is False
    assert stato_combattimento()[1].mossa_richiesta is None


def test_mossa_inventata_rifiutata(mondo_isolato: str) -> None:
    _scontro_con_prot()
    assert richiedi_mossa("pugno_di_fuoco_cosmico") is False
    assert stato_combattimento()[1].mossa_richiesta is None


def test_richiedi_mossa_fuori_scontro_non_esplode(mondo_isolato: str) -> None:
    crea_protagonista(destrezza=10)
    assert richiedi_mossa("attacco") is False  # nessuno StatoCombattimento


# --- Il menu è dinamico e "Fuggi" resta l'ultima --------------------------------

def _mob_resistente() -> MobAsset:
    return MobAsset(
        slug="spugna", nome="Spugna Argentata", archetipo="slime",
        grado=Grado.ARGENTO, blocchi=[], prosa_stanza="La spugna ribolle.",
    )


def test_il_menu_riflette_il_repertorio(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(
        nome="Menu", seed=1, directory=tmp_path, stagione=_stagione(_mob_resistente())
    )
    snap = _apri_scontro(sessione)
    attese = [etichetta_mossa(m) for m in MOSSE_INIZIALI_PROTAGONISTA] + ["Fuggi"]
    assert [o.etichetta for o in snap.opzioni] == attese
    # Indici contigui e coerenti con la posizione: il binding è posizionale.
    assert [o.indice for o in snap.opzioni] == list(range(len(attese)))


def test_una_mossa_in_piu_allunga_il_menu_senza_spostare_fuggi(
    run_pulita, tmp_path
) -> None:
    """Il menu è DATO: aggiungere una mossa al Repertorio basta, zero codice."""
    sessione = costruisci_sessione(
        nome="Piu", seed=1, directory=tmp_path, stagione=_stagione(_mob_resistente())
    )
    pent = protagonista()[0]
    rep = esper.component_for_entity(pent, Repertorio)
    esper.remove_component(pent, Repertorio)
    esper.add_component(pent, Repertorio(mosse=rep.mosse + ("morso_velenoso",)))

    snap = _apri_scontro(sessione)
    etichette = [o.etichetta for o in snap.opzioni]
    assert "Morso velenoso" in etichette
    assert etichette[-1] == "Fuggi", "Fuggi deve restare l'ultima voce"

    # E ora quella mossa È lecita: il gate guarda il Repertorio, non una lista fissa.
    sessione.coda.accoda(PlayerChoseOption(_indice(snap, "Morso velenoso")))
    snap = sessione.avanza()
    assert snap.fase in ("combattimento", "narrazione")


def test_click_su_indice_fuori_menu_non_spende_il_turno(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(
        nome="Fuori", seed=1, directory=tmp_path, stagione=_stagione(_mob_resistente())
    )
    snap = _apri_scontro(sessione)
    hp_prima = sessione.scheda().hp
    sessione.coda.accoda(PlayerChoseOption(99))
    snap = sessione.avanza()
    assert snap.fase == "combattimento"
    assert sessione.scheda().hp == hp_prima, "un indice illegale non deve costare un turno"
