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
    BudgetDesign,
    ColpoInferto,
    Grado,
    MobAsset,
    PianoRisolto,
    PlayerChoseOption,
    StagioneRisolta,
)
from main import costruisci_sessione


def _stagione_un_mob(archetipo: str, grado: Grado) -> StagioneRisolta:
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
    return next(
        o.indice for o in snap.opzioni
        if o.etichetta == etichetta or o.etichetta.startswith(etichetta + " —")
    )


def _equipaggia_di_riferimento(grado: Grado) -> None:
    """Veste il protagonista con l'equip **atteso** a quel grado (`CORREDO_RIFERIMENTO`).

    Senza questo, il TTK sui gradi alti misurerebbe una cosa che il gioco non chiede
    mai: un celestiale affrontato nudi non è uno scontro sbilanciato, è uno scontro che
    il giocatore non dovrebbe aver modo di iniziare. **È l'equipaggiamento a fare da
    progressione** — non ci sono livelli né punti-esperienza — quindi la banda del TTK
    ha senso solo a parità di corredo atteso."""
    from contracts import CategoriaArmatura, SLOT_ARMATURA, StatId, Taglia
    from motore import (
        CORREDO_RIFERIMENTO, Arma, Modificatore, PezzoArmatura, TipoMod,
        equipaggia, protagonista,
    )

    rif = CORREDO_RIFERIMENTO[grado.value]
    pent, _m, _s = protagonista()
    categoria = CategoriaArmatura(rif["armatura"])
    for slot in SLOT_ARMATURA:
        equipaggia(pent, PezzoArmatura(
            fonte=f"rif-{slot.value}", slot=slot, categoria=categoria,
        ))
    bonus = int(rif["bonus_forza"])
    if bonus:
        equipaggia(pent, Arma(
            fonte="rif-arma", taglia=Taglia.MEDIA, nome="Arma di riferimento",
            modificatori=(Modificatore(stat=StatId.FORZA, tipo=TipoMod.FLAT,
                                       valore=bonus, fonte="rif-arma"),),
        ))


@pytest.mark.parametrize("archetipo", ["slime", "scheletro", "goblin"])
@pytest.mark.parametrize("grado", list(Grado))
def test_ttk_per_profilo(run_pulita, tmp_path, archetipo: str, grado: Grado) -> None:
    """La banda 2-8 colpi vale **per (grado, corredo di riferimento)**, non in assoluto.

    Prima girava su bronzo/argento soltanto, e dal platino in su il protagonista moriva
    per costruzione: HP e danno dei nemici crescevano insieme (un `fattore` unico), e
    nessun equipaggiamento poteva compensare due curve che salivano appaiate. Da F9 le
    curve sono separate e il corredo atteso entra nel conto."""
    sessione = costruisci_sessione(
        nome="TTK", seed=1, directory=tmp_path,
        stagione=_stagione_un_mob(archetipo, grado),
        # La banda TTK è la taratura BASE del check 2: si misura SENZA il
        # registro skill (la pratica che sale mid-scontro sposterebbe la
        # coda dei tier alti — quella è progressione, non banda).
        skill=(),
    )
    _equipaggia_di_riferimento(grado)
    colpi_giocatore = []
    sessione.bus.registra(ColpoInferto, colpi_giocatore.append)
    try:
        snap = asyncio.run(sessione.prossima_narrazione())
        sessione.coda.accoda(PlayerChoseOption(_indice(snap, "Combatti")))
        snap = sessione.avanza()
        guardia = 0
        while snap.fase == "combattimento" and guardia < 20:
            sessione.coda.accoda(PlayerChoseOption(_indice(snap, "Attacca")))  # un round
            snap = sessione.avanza()
            guardia += 1
        miei = [c for c in colpi_giocatore if c.attaccante == ""]
        assert 2 <= len(miei) <= 8, (
            f"{archetipo}/{grado.value}: TTK fuori target ({len(miei)} colpi)"
        )
        hp = sessione.scheda().hp
        assert snap.fase == "narrazione" and hp > 0, (
            f"{archetipo}/{grado.value}: non sopravvissuto ({hp} HP)"
        )
    finally:
        sessione.bus.deregistra(ColpoInferto, colpi_giocatore.append)


def test_giro_completo_giocabile_con_tattica(run_pulita, tmp_path) -> None:
    """Il giro completo: combatti finché stai bene, fuggi se sotto il 40% —
    la tattica minima di un giocatore. Deve arrivare in fondo VIVO. Stagione
    SINTETICA piatta a 8 stanze (il lucchetto è la TATTICA, non il contenuto
    pubblicato — che dal 2026-08-10 è territoriale)."""
    from tests.contenuti_sintetici import stagione_sintetica

    sessione = costruisci_sessione(
        nome="Giro", seed=1, directory=tmp_path,
        stagione=stagione_sintetica(1, n_stanze=8),
        skill=(),  # misura di giocabilità base: senza registro (vedi sopra)
    )
    snap = asyncio.run(sessione.prossima_narrazione())
    stanze_viste = 1
    for stanza in range(8):
        # Nella stanza col mob: combatti o fuggi secondo gli HP.
        guardia = 0
        while snap.fase == "combattimento" or any(
            o.etichetta.startswith("Combatti") for o in snap.opzioni
        ):
            assert guardia < 40, f"stanza {stanza}: scontro senza fine"
            guardia += 1
            if snap.fase == "combattimento":
                # Menu dinamico: mai cablare gli indici (Fuggi non è più il secondo).
                scelta = _indice(snap, "Attacca" if sessione.scheda().hp > 12 else "Fuggi")
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
