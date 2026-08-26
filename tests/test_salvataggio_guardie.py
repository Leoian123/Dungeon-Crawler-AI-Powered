"""Fix audit 2026-08 — le guardie del salvataggio e il seam `rng_state`.

1. Salvare/uscire in COMBATTIMENTO è vietato (`SalvataggioInCombattimento`): un
   save a metà scontro si ricaricherebbe "in combattimento" senza scontro
   (soft-lock permanente — riprodotto nell'audit). A scontro risolto si salva.
2. `rng_state` ora è scritto E ripristinato: dopo un load lo stream RNG di
   sessione (anomalie, disimpegni, seed di scontro) riprende ESATTAMENTE da
   dov'era — prima il parametro era un fantasma (mai passato, mai riletto).
3. Il translator dei componenti rispetta il CONTENITORE: `tuple[...]` → tuple.
"""

from __future__ import annotations

import asyncio

import pytest

from contracts import PlayerChoseOption
from main import SalvataggioInCombattimento, carica_sessione, costruisci_sessione


def test_salva_ed_esci_vietati_in_combattimento(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(nome="X", seed=1, directory=tmp_path)
    snap = asyncio.run(sessione.prossima_narrazione())
    indice = next(o.indice for o in snap.opzioni if o.etichetta.startswith("Combatti"))
    sessione.coda.accoda(PlayerChoseOption(indice))
    snap = sessione.avanza()
    assert snap.fase == "combattimento"

    with pytest.raises(SalvataggioInCombattimento):
        sessione.salva()
    with pytest.raises(SalvataggioInCombattimento):
        sessione.esci()
    # La sessione resta VIVA e giocabile: si risolve lo scontro e si salva.
    guardia = 0
    while snap.fase == "combattimento" and guardia < 20:
        sessione.coda.accoda(PlayerChoseOption(0))  # Attacca
        snap = sessione.avanza()
        guardia += 1
    assert snap.fase == "narrazione"
    assert sessione.salva() == "Partita salvata."
    sessione.esci()


def test_rng_state_riprende_esattamente_dopo_il_load(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(nome="X", seed=3, directory=tmp_path)
    asyncio.run(sessione.prossima_narrazione())
    for _ in range(5):
        sessione.rng.random()  # lo stream diverge dal seed puro
    stato_atteso = sessione.rng.getstate()
    uuid = sessione.uuid
    sessione.esci()  # salva-ed-esci: scrive anche rng_state

    ricaricata = carica_sessione(uuid=uuid, directory=tmp_path)
    assert ricaricata is not None
    # Non "da capo col seed": ESATTAMENTE lo stato del momento dell'uscita.
    assert ricaricata.rng.getstate() == stato_atteso
    ricaricata.esci()


def test_tuple_roundtrip_nel_translator() -> None:
    from motore import Repertorio
    from motore.persistenza.tag import deserializza_componente, serializza_componente

    tag, dati = serializza_componente(Repertorio(mosse=("attacco", "morso_velenoso")))
    vivo = deserializza_componente(tag, dati)
    assert vivo.mosse == ("attacco", "morso_velenoso")
    assert isinstance(vivo.mosse, tuple)  # l'annotazione comanda sul contenitore
