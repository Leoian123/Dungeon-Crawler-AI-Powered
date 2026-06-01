"""Integrazione end-to-end della fetta verticale (gate del nodo A): un piano intero
giocato capo-a-fine, scriptato e deterministico (provider FAKE, nessuna rete).

boot → nuova partita → esplora (narrazione · prova · incontro) → combatti → vittoria →
discesa (piano-completato = terminale MVP) → menu → carica un altro slot.

Lo stesso identico flusso col **backend Anthropic reale** è in `test_provider_anthropic.py`,
opzionale (saltato senza chiave). Qui tutto è seeded e verificabile, headless.
"""

from __future__ import annotations

import asyncio
import random

import esper
import pytest

from contracts import ClasseProva, MortePersonaggio, PlayerDiscende
from guscio import NOME_DEFAULT, NOME_RUN, Guscio, StatoGuscio, Terminale
from motore import (
    Fase,
    SpecNemico,
    esegui_turno_narrazione,
    in_combattimento,
    ingaggia_combattimento,
    leggi_fase,
    livello_corrente,
    materializza_turno,
    proietta_scheda,
    protagonista,
    risolvi_prova,
    tick,
)
from motore.persistenza.disco import path_stato
from provider import FakeProvider
from tests.narr_helpers import turno


@pytest.fixture
def guscio_pulito():
    esper.switch_world(NOME_DEFAULT)
    if NOME_RUN in esper.list_worlds():
        esper.delete_world(NOME_RUN)
    yield
    esper.switch_world(NOME_DEFAULT)
    if NOME_RUN in esper.list_worlds():
        esper.delete_world(NOME_RUN)


def test_e2e_piano_intero_capo_a_fine(guscio_pulito, tmp_path) -> None:
    g = Guscio(tmp_path)
    assert g.stato is StatoGuscio.MENU  # boot → menu

    # --- prepara un secondo slot su disco (per la fase "carica") ---------------
    asyncio.run(g.gioca_nuova_partita(lambda gg: gg.esci_volontariamente(), uuid="bob"))
    assert path_stato(tmp_path, "bob").exists()
    assert g.stato is StatoGuscio.MENU

    # --- nuova partita "carl" → run -------------------------------------------
    g.nuova_partita(uuid="carl", destrezza=10, hp=30, seed=0)
    assert leggi_fase() is Fase.NARRAZIONE
    rng = random.Random(0)
    provider = FakeProvider([turno().model_dump()])  # un turno scriptato, poi fallback

    # --- esplora: un turno di narrazione (AI propone, gate, materializza) ------
    pent, _marker, scheda = protagonista()
    risultato = asyncio.run(
        esegui_turno_narrazione(
            provider, livello=livello_corrente(), proiezione=proietta_scheda(pent), rng=rng
        )
    )
    assert risultato.turno.prosa  # c'è prosa da narrare
    mob = materializza_turno(risultato, g.bus)
    assert esper.entity_exists(mob)

    # --- esplora: una prova di abilità (motore TIRA seeded) -------------------
    esito = risolvi_prova(scheda.destrezza, ClasseProva.BRONZO, rng)
    assert isinstance(esito, bool)

    # --- incontro + combatti fino alla vittoria -------------------------------
    ingaggia_combattimento(g.bus, nemici=[SpecNemico(destrezza=5, punti_vita=3)], seed=1)
    assert in_combattimento()
    for _ in range(60):
        tick()
        if not in_combattimento():
            break
    assert leggi_fase() is Fase.NARRAZIONE  # vittoria di scontro → torna a NARRAZIONE…
    assert g._terminale is None  # …e NON è un terminale di run (E-8)
    assert protagonista()[2].vivo is True  # Carl è sopravvissuto

    # --- discesa: nell'MVP DiscesaPiano = piano-completato = terminale (G §6.7) -
    g.coda.accoda(PlayerDiscende())  # intento del giocatore → coda (C-8)
    tick()  # DrenaggioIntenti → SistemaDiscesa → attiva_discesa → DiscesaPiano
    assert livello_corrente() == 2
    assert g._terminale is Terminale.PIANO_COMPLETATO

    # --- terminale → cucitura → menu (vittoria invalida lo stato, H-20) --------
    terminale = g.concludi()
    assert terminale is Terminale.PIANO_COMPLETATO
    assert g.stato is StatoGuscio.MENU
    assert esper.current_world == NOME_DEFAULT
    assert not path_stato(tmp_path, "carl").exists()  # fine-run vittoria → invalidato

    # --- carica l'altro slot ---------------------------------------------------
    assert g.carica("bob") is True
    assert g.stato is StatoGuscio.IN_RUN
    assert protagonista()[1].id_dominio == "bob"
    g._terminale = Terminale.USCITA_VOLONTARIA
    g.concludi()


def test_e2e_morte_chiude_la_run(guscio_pulito, tmp_path) -> None:
    # Il ramo opposto del terminale: la morte (permadeath) conclude la run e invalida.
    g = Guscio(tmp_path)
    eventi: list = []
    g.bus.registra(MortePersonaggio, eventi.append)

    def uccidi(gg: Guscio) -> None:
        protagonista()[2].punti_vita = 0  # il death-check seeded emette MortePersonaggio

    terminale = asyncio.run(g.gioca_nuova_partita(uccidi, uuid="carl"))
    assert terminale is Terminale.SCONFITTA
    assert eventi and isinstance(eventi[0], MortePersonaggio)  # MortePersonaggio, non sconfitta
    assert g.stato is StatoGuscio.MENU
    assert not path_stato(tmp_path, "carl").exists()  # morte → save invalidato
