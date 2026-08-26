"""L'economia delle mosse: mana e cooldown tolgono la dominanza al colpo pesante.

Dopo C1 il giocatore poteva scegliere `attacco_pesante` (molt. 1.5) a costo zero e
allo stesso AP: una scelta che non è una scelta. Qui si prova che la risorsa esiste,
che si spende, che si ricarica, e che il motore rifiuta ciò che non è pagabile —
sia al click (porta) sia alla risoluzione (cintura profonda).
"""

from __future__ import annotations

import esper
import pytest

from contracts import ColpoInferto, Grado, MobAsset, PlayerChoseOption, StatId
from motore import (
    CATALOGO_MOSSE,
    Mana,
    Repertorio,
    Ricariche,
    assicura_mana,
    cooldown_residuo,
    max_mana,
    mossa_pagabile,
    richiedi_mossa,
    stato_combattimento,
    tick,
)
from motore.calibrazione import COOLDOWN_MOSSA, COSTO_MANA_MOSSA
from motore.combattimento import SpecNemico
from motore.persistenza.tag import e_persistente
from motore.scheda import crea_protagonista, protagonista
from motore.statistiche import stat_eff
from main import costruisci_sessione
from tests.combat_helpers import avvia_scontro
from tests.test_combat_feel import _apri_scontro, _indice, _stagione


def _scontro():
    """Nemico inerte e immortale: isola l'economia del protagonista."""
    return avvia_scontro(nemici=[SpecNemico(destrezza=1, punti_vita=10**9)], seed=1)


# --- Il mana è una risorsa posseduta, col massimo DERIVATO -----------------------

def test_il_mana_deriva_dall_intelligenza(mondo_isolato: str) -> None:
    ent = crea_protagonista(destrezza=10)
    mana = esper.component_for_entity(ent, Mana)
    assert mana.attuale == max_mana(ent) == stat_eff(ent, StatId.INTELLIGENZA)


def test_il_mana_e_persistente_e_il_massimo_no(mondo_isolato: str) -> None:
    """Come gli HP: il corrente viaggia nel save, il tetto si ricalcola."""
    assert e_persistente(Mana)
    assert not e_persistente(Ricariche), "i cooldown non devono entrare nei save"
    assert not hasattr(Mana(attuale=1), "massimo")


def test_assicura_mana_ripara_i_save_legacy(mondo_isolato: str) -> None:
    ent = crea_protagonista(destrezza=10)
    esper.remove_component(ent, Mana)  # save scritto prima che il mana esistesse
    assert assicura_mana(ent).attuale == max_mana(ent)


# --- La spesa: una mossa che costa, costa --------------------------------------

def test_il_colpo_pesante_consuma_mana(mondo_isolato: str) -> None:
    _scontro()
    pent = protagonista()[0]
    prima = esper.component_for_entity(pent, Mana).attuale

    assert richiedi_mossa("attacco_pesante") is True
    tick()

    dopo = esper.component_for_entity(pent, Mana).attuale
    assert dopo == prima - COSTO_MANA_MOSSA["attacco_pesante"]


def test_l_attacco_base_non_costa_nulla(mondo_isolato: str) -> None:
    _scontro()
    pent = protagonista()[0]
    prima = esper.component_for_entity(pent, Mana).attuale
    tick()
    assert esper.component_for_entity(pent, Mana).attuale == prima


def test_a_secco_la_mossa_cara_non_e_pagabile(mondo_isolato: str) -> None:
    _scontro()
    pent = protagonista()[0]
    esper.component_for_entity(pent, Mana).attuale = 0
    assert mossa_pagabile(pent, "attacco_pesante") is False
    assert mossa_pagabile(pent, "dardo_arcano") is False
    assert mossa_pagabile(pent, "attacco") is True, "il fallback dev'essere sempre pagabile"


# --- Il cooldown: si arma alla risoluzione, scende a inizio del PROPRIO turno ----

def test_il_pesante_va_in_ricarica_e_torna_pronto(mondo_isolato: str) -> None:
    _scontro()
    pent = protagonista()[0]

    richiedi_mossa("attacco_pesante")
    tick()  # risolve → arma il cd
    assert cooldown_residuo(pent, "attacco_pesante") == COOLDOWN_MOSSA["attacco_pesante"]
    assert mossa_pagabile(pent, "attacco_pesante") is False

    # Il cd scende SOLO nei propri turni (in mezzo c'è il nemico).
    for _ in range(6):
        tick()
        if cooldown_residuo(pent, "attacco_pesante") == 0:
            break
    assert cooldown_residuo(pent, "attacco_pesante") == 0
    assert mossa_pagabile(pent, "attacco_pesante") is True


def test_la_ricarica_scende_anche_da_storditi(mondo_isolato: str) -> None:
    """Si perde il turno, non anche la ricarica: il decremento precede lo stordito."""
    from motore import Stordito, applica_status

    _scontro()
    pent = protagonista()[0]
    richiedi_mossa("attacco_pesante")
    tick()
    residuo = cooldown_residuo(pent, "attacco_pesante")
    applica_status(pent, Stordito(durata=99, rango=1, innato=False))
    for _ in range(6):
        tick()
        if cooldown_residuo(pent, "attacco_pesante") < residuo:
            break
    assert cooldown_residuo(pent, "attacco_pesante") < residuo


def test_le_ricariche_non_sopravvivono_allo_scontro(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(
        nome="Cd", seed=1, directory=tmp_path,
        stagione=_stagione(MobAsset(
            slug="bolla", nome="Bolla", archetipo="slime", grado=Grado.BRONZO,
            blocchi=[], prosa_stanza="Una bolla trema.",
        )),
    )
    snap = _apri_scontro(sessione)
    sessione.coda.accoda(PlayerChoseOption(_indice(snap, "Colpo pesante")))
    snap = sessione.avanza()
    pent = protagonista()[0]

    guardia = 0
    while snap.fase == "combattimento" and guardia < 20:
        sessione.coda.accoda(PlayerChoseOption(_indice(snap, "Attacca")))
        snap = sessione.avanza()
        guardia += 1

    assert snap.fase == "narrazione"
    assert not esper.has_component(pent, Ricariche), "i cd sono effimeri per-scontro"
    assert cooldown_residuo(pent, "attacco_pesante") == 0


def test_il_mana_invece_resta_speso_dopo_lo_scontro(run_pulita, tmp_path) -> None:
    """Il mana si recupera riposando, non chiudendo uno scontro (è la ragione
    per cui il riposo esisterà)."""
    sessione = costruisci_sessione(
        nome="Speso", seed=1, directory=tmp_path,
        stagione=_stagione(MobAsset(
            slug="bolla", nome="Bolla", archetipo="slime", grado=Grado.BRONZO,
            blocchi=[], prosa_stanza="Una bolla trema.",
        )),
    )
    snap = _apri_scontro(sessione)
    pent = protagonista()[0]
    pieno = esper.component_for_entity(pent, Mana).attuale
    sessione.coda.accoda(PlayerChoseOption(_indice(snap, "Dardo arcano")))
    snap = sessione.avanza()

    guardia = 0
    while snap.fase == "combattimento" and guardia < 20:
        sessione.coda.accoda(PlayerChoseOption(_indice(snap, "Attacca")))
        snap = sessione.avanza()
        guardia += 1

    assert esper.component_for_entity(pent, Mana).attuale < pieno


# --- Il rifiuto: due cinture, e nessun turno perso ------------------------------

def test_la_porta_rifiuta_e_non_spende_il_turno(mondo_isolato: str) -> None:
    _scontro()
    pent = protagonista()[0]
    esper.component_for_entity(pent, Mana).attuale = 0
    assert richiedi_mossa("dardo_arcano") is False
    assert stato_combattimento()[1].mossa_richiesta is None


def test_la_cintura_profonda_degrada_all_attacco(mondo_isolato: str) -> None:
    """Se lo stato cambia FRA il click e la risoluzione, il turno non si perde:
    si degrada all'attacco base (sempre pagabile)."""
    bus, _adapter, _enc = _scontro()
    colpi: list[ColpoInferto] = []
    bus.registra(ColpoInferto, colpi.append)
    pent = protagonista()[0]

    assert richiedi_mossa("dardo_arcano") is True
    esper.component_for_entity(pent, Mana).attuale = 0  # il mana sparisce dopo il click
    tick()

    miei = [c for c in colpi if c.attaccante == ""]
    assert miei and miei[-1].mossa == "attacco", "doveva degradare, non saltare il turno"


def test_il_nemico_a_secco_ripiega_sull_attacco(mondo_isolato: str) -> None:
    """Il filtro delle mosse pagabili vale anche per la scelta seeded del motore."""
    bus, _adapter, _enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=100, punti_vita=10**9)], seed=3, hp_prot=10**9
    )
    nemico = [e for e, _ in esper.get_component(Ricariche) if e != protagonista()[0]][0]
    esper.component_for_entity(nemico, Mana).attuale = 0
    colpi: list[ColpoInferto] = []
    bus.registra(ColpoInferto, colpi.append)

    for _ in range(6):
        tick()
    suoi = [c for c in colpi if c.attaccante != ""]
    assert suoi, "il nemico non ha mai colpito"
    assert all(c.mossa == "attacco" for c in suoi), (
        f"un nemico a secco ha usato una mossa cara: {[c.mossa for c in suoi]}"
    )


# --- Il dardo arcano: l'incantesimo esiste e fa danno di FUOCO ------------------

def test_il_menu_mostra_spenta_la_mossa_non_pagabile(run_pulita, tmp_path) -> None:
    """`abilitata=False`: la voce resta (indici stabili) ma l'host la disegna spenta,
    e l'etichetta DICE perché."""
    sessione = costruisci_sessione(
        nome="Spenta", seed=1, directory=tmp_path,
        stagione=_stagione(MobAsset(
            slug="spugna", nome="Spugna", archetipo="slime", grado=Grado.ARGENTO,
            blocchi=[], prosa_stanza="La spugna ribolle.",
        )),
    )
    snap = _apri_scontro(sessione)
    assert all(o.abilitata for o in snap.opzioni), "col pool pieno è tutto giocabile"
    # Il costo è scritto nell'etichetta.
    dardo = next(o for o in snap.opzioni if o.etichetta.startswith("Dardo arcano"))
    assert f"{COSTO_MANA_MOSSA['dardo_arcano']} mana" in dardo.etichetta

    # A secco, il menu si ricompone al turno successivo (via `avanza`, come nel gioco).
    esper.component_for_entity(protagonista()[0], Mana).attuale = 0
    sessione.coda.accoda(PlayerChoseOption(_indice(snap, "Attacca")))
    snap = sessione.avanza()

    spente = {o.etichetta.split(" —")[0] for o in snap.opzioni if not o.abilitata}
    assert spente == {"Colpo pesante", "Dardo arcano"}
    assert next(o for o in snap.opzioni if o.etichetta == "Attacca").abilitata
    assert next(o for o in snap.opzioni if o.etichetta == "Fuggi").abilitata
    # Il numero di voci NON cambia: gli indici restano stabili fra snapshot.
    assert len(snap.opzioni) == 4


def test_il_dardo_arcano_e_fuoco_e_costa_piu_del_pesante(mondo_isolato: str) -> None:
    from contracts import TipoDanno

    dardo = CATALOGO_MOSSE["dardo_arcano"]
    assert dardo.effetti[0].tipo is TipoDanno.FUOCO  # incrocia le resistenze esistenti
    assert dardo.costo_mana > CATALOGO_MOSSE["attacco_pesante"].costo_mana
    assert dardo.cooldown == 0  # il limite è la risorsa, non l'attesa
