"""TTK e feel del combattimento (analisi §5.4: mai one-shot, target 3–6 round).

Due livelli: (1) per-profilo — ogni archetipo×grado regge 2–8 colpi del
protagonista e lo scontro si vince vivi; (2) il giro COMPLETO della Falsa Idra
è giocabile con la tattica ovvia (combatti, fuggi se messo male). Se questi
test diventano rossi si ritoccano i `pv_base`/`danno_base` di calibrazione,
MAI i bound del test. Tutto via porte, offline, seeded.
"""

from __future__ import annotations

import asyncio

import pytest

from contracts import (
    Archetipo,
    BudgetDesign,
    ColpoInferto,
    Grado,
    MobAsset,
    PianoRisolto,
    PlayerChoseOption,
    StagioneRisolta,
)
from main import costruisci_sessione


def _stagione_un_mob(archetipo: Archetipo, grado: Grado) -> StagioneRisolta:
    mob = MobAsset(
        slug="bersaglio", nome="Bersaglio di Prova", archetipo=archetipo,
        grado=grado, prosa_stanza="Una sagoma di prova ti squadra.",
    )
    piano = PianoRisolto(
        slug="p", versione=1, titolo="Prova", tema="ttk",
        budget=BudgetDesign(gradi=[grado], blocchi=[], archetipi=[archetipo]),
        cast=[mob],
    )
    return StagioneRisolta(
        slug="s-ttk", versione=1, numero=1, titolo="TTK", mondo="X", piani=[piano]
    )


def _indice(snap, etichetta: str) -> int:
    return next(o.indice for o in snap.opzioni if o.etichetta == etichetta)


@pytest.mark.parametrize("archetipo", list(Archetipo))
@pytest.mark.parametrize("grado", [Grado.BRONZO, Grado.ARGENTO])
def test_ttk_per_profilo(run_pulita, tmp_path, archetipo: Archetipo, grado: Grado) -> None:
    sessione = costruisci_sessione(
        nome="TTK", seed=1, directory=tmp_path, stagione=_stagione_un_mob(archetipo, grado)
    )
    colpi_giocatore = []
    sessione.bus.registra(ColpoInferto, colpi_giocatore.append)
    try:
        snap = asyncio.run(sessione.prossima_narrazione())
        sessione.coda.accoda(PlayerChoseOption(_indice(snap, "Combatti")))
        snap = sessione.avanza()
        guardia = 0
        while snap.fase == "combattimento" and guardia < 20:
            sessione.coda.accoda(PlayerChoseOption(0))  # Attacca (= un round intero)
            snap = sessione.avanza()
            guardia += 1
        miei = [c for c in colpi_giocatore if c.attaccante == ""]
        assert 2 <= len(miei) <= 8, (
            f"{archetipo.value}/{grado.value}: TTK fuori target ({len(miei)} colpi)"
        )
        hp = sessione.scheda().hp
        assert snap.fase == "narrazione" and hp > 0, (
            f"{archetipo.value}/{grado.value}: non sopravvissuto ({hp} HP)"
        )
    finally:
        sessione.bus.deregistra(ColpoInferto, colpi_giocatore.append)


def test_giro_falsa_idra_giocabile_con_tattica(run_pulita, tmp_path) -> None:
    """Il giro completo: combatti finché stai bene, fuggi se sotto il 40% —
    la tattica minima di un giocatore. Deve arrivare in fondo VIVO."""
    sessione = costruisci_sessione(nome="Giro", seed=1, directory=tmp_path)
    snap = asyncio.run(sessione.prossima_narrazione())
    stanze_viste = 1
    for stanza in range(8):
        # Nella stanza col mob: combatti o fuggi secondo gli HP.
        guardia = 0
        while snap.fase == "combattimento" or any(
            o.etichetta == "Combatti" for o in snap.opzioni
        ):
            assert guardia < 40, f"stanza {stanza}: scontro senza fine"
            guardia += 1
            if snap.fase == "combattimento":
                scelta = 0 if sessione.scheda().hp > 12 else 1  # Attacca | Fuggi
            else:
                scelta = _indice(snap, "Combatti") if sessione.scheda().hp > 12 else _indice(
                    snap, "Scappi"
                )
            sessione.coda.accoda(PlayerChoseOption(scelta))
            snap = sessione.avanza()
            if not snap.opzioni and snap.fase == "narrazione":
                snap = asyncio.run(sessione.prossima_narrazione())
        assert sessione.scheda().vivo, f"morto alla stanza {stanza}"
        if stanza == 7:
            break
        destinazione = f"Vai: stanza {stanza + 1}"
        etichette = {o.etichetta for o in snap.opzioni}
        assert destinazione in etichette, f"stanza {stanza}: {sorted(etichette)}"
        sessione.coda.accoda(PlayerChoseOption(_indice(snap, destinazione)))
        snap = sessione.avanza()
        if not snap.opzioni:
            snap = asyncio.run(sessione.prossima_narrazione())
        stanze_viste += 1
    assert stanze_viste == 8
    assert sessione.scheda().vivo and sessione.scheda().hp > 0
