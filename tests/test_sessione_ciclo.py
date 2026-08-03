"""Ciclo di vita della sessione via porte: nuova → gioca → salva-ed-esci →
elenco → carica (thread ricostruito, storia NON riscritta) → terminale.

Tutto offline (FakeProvider). Disciplina esper: `run_pulita` (ESP §0.1).
"""

from __future__ import annotations

import asyncio

from main import (
    carica_sessione,
    costruisci_sessione,
    elenca_crawler,
    gioca_un_incontro,
)
from motore import protagonista, tick


def test_ciclo_completo_nuova_esci_elenca_carica(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(nome="Donut", seed=1, directory=tmp_path)
    snap = asyncio.run(sessione.prossima_narrazione())
    prosa_originale = snap.prosa
    assert "Slime" in prosa_originale
    uuid = sessione.uuid
    assert sessione.salva() == "Partita salvata."
    messaggio = sessione.esci()
    assert "riprenderla" in messaggio

    # La sessione chiusa spegne le porte.
    try:
        sessione.avanza()
        raise AssertionError("le porte devono spegnersi dopo l'uscita")
    except RuntimeError:
        pass

    # L'elenco mostra lo slot con nome e timestamp reali.
    [voce] = elenca_crawler(tmp_path)
    assert voce.uuid == uuid
    assert voce.etichetta == "Donut"
    assert voce.timestamp > 0
    assert voce.corrotta is False

    # Caricamento: thread ricostruito, stessa prosa, si continua a giocare.
    ripresa = carica_sessione(uuid=uuid, directory=tmp_path)
    assert ripresa is not None
    assert ripresa.etichetta == "Donut"
    thread = ripresa.ricostruisci_thread()
    assert len(thread) == 1
    assert thread[0].prosa == prosa_originale
    assert ripresa.ultimo_messaggio is not None

    # La stanza già narrata viene RILETTA (cache firma→turno): il FakeProvider
    # della ripresa è vergine, ma la prosa resta quella congelata — la storia
    # non si riscrive (H §11).
    snap2 = asyncio.run(ripresa.prossima_narrazione())
    assert snap2.prosa == prosa_originale
    assert [o.etichetta for o in snap2.opzioni]  # la scena è ricomposta


def test_scheda_vista_visibilita(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(nome="Princess", seed=2, directory=tmp_path)
    scheda = sessione.scheda()
    assert scheda.nome == "Princess"
    assert scheda.vivo is True
    assert 0 < scheda.hp <= scheda.hp_max
    assert "destrezza" in scheda.primarie  # PALESE, valore effettivo
    assert "saggezza" in scheda.primarie_occulte  # nome sì, valore mai
    assert "fortuna" not in scheda.primarie  # ESISTENZA_NEGATA: mai (GR2-9)
    assert "fortuna" not in scheda.primarie_occulte
    assert scheda.derivate["attacco"] > 0
    assert scheda.livello >= 1


def test_terminale_morte_invalida_lo_slot(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(nome="Sfortunato", seed=1, directory=tmp_path)
    sessione.salva()
    assert len(elenca_crawler(tmp_path)) == 1
    asyncio.run(sessione.prossima_narrazione())
    # Morte forzata: il death-check (seeded) emette MortePersonaggio sul bus e il
    # guscio rileva il terminale 6a.
    _pent, _marker, scheda = protagonista()
    scheda.punti_vita = 0
    tick()  # un turno del motore (harness): il death-check emette MortePersonaggio
    assert sessione.chiudi_terminale() == "Run conclusa: lo slot è stato ritirato."
    assert elenca_crawler(tmp_path) == []  # permadeath: save invalidato (H-20)


def test_due_run_sequenziali_nello_stesso_processo(run_pulita, tmp_path) -> None:
    prima = costruisci_sessione(nome="Uno", seed=1, directory=tmp_path)
    asyncio.run(prima.prossima_narrazione())
    prima.esci()
    seconda = costruisci_sessione(nome="Due", seed=2, directory=tmp_path)
    snap = asyncio.run(gioca_un_incontro(seconda, stampa=lambda _r: None))
    assert snap.fase in {"narrazione", "combattimento"}
    seconda.esci()
    etichette = sorted(v.etichetta for v in elenca_crawler(tmp_path))
    assert etichette == ["Due", "Uno"]
