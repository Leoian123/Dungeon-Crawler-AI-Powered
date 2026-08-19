"""La FABBRICA del loot procedurale — Borderlands, in piccolo.

Le PARTI (basi × famiglie × affissi) sono asset autorabili (a mano o via
`authoring.fabbrica`); il motore le combina SEEDED a ogni drop: oggetti
deterministici, gratuiti, anche offline. La rarità governa le parti (bronzo =
base+famiglia; argento+ = affisso; oro+ = secondo affisso), i numeri restano
del motore (fasce §11), i nomi si compongono («Lama Fumante dei Becchini»).
"""

from __future__ import annotations

import asyncio
import random

import esper

from contracts import FabbricaAsset, PlayerChoseOption
from main import _fabbrica_a_attiva, costruisci_sessione, risolvi_stagione
from motore import (
    ROTTE,
    calibrazione as cal,
    catalogo_oggetti_correnti,
    conia_procedurale,
    crea_stagione,
    fabbrica_attiva,
    oggetto_da_asset,
    protagonista,
)
from motore.equip import PezzoArmatura, fonti_zaino
from tests.persist_helpers import costruisci_run


def _arma_fabbrica():
    """Congela nella run la fabbrica seed della stagione pubblicata."""
    from main import _stagione_a_attiva

    costruisci_run()
    crea_stagione(_stagione_a_attiva(risolvi_stagione("stagione-1")))
    assert fabbrica_attiva() is not None


def test_stagione_uno_risolve_la_fabbrica() -> None:
    risolta = risolvi_stagione("stagione-1")
    assert risolta.fabbrica is not None
    assert risolta.fabbrica.slug == "catena-dei-morti"


def test_conio_deterministico_e_composto(mondo_isolato) -> None:
    _arma_fabbrica()
    a = conia_procedurale(random.Random(42), "oro")
    b = conia_procedurale(random.Random(42), "oro")
    assert a == b, "stesso stream → stesso oggetto (replay-safe)"
    c = conia_procedurale(random.Random(43), "oro")
    assert c != a, "stream diverso → oggetto diverso"
    # Il nome è composto e lo slug è derivato dal nome + suffisso seeded.
    assert a.nome.split()[0] in {b2.nome for b2 in fabbrica_attiva().basi} \
        or any(a.nome.startswith(b2.nome) for b2 in fabbrica_attiva().basi)
    assert a.grado == "oro"


def test_rarita_governa_le_parti(mondo_isolato) -> None:
    _arma_fabbrica()
    rng = random.Random(7)
    bronzo = conia_procedurale(rng, "bronzo")
    # BRONZO: base × famiglia — niente affissi (né resistenze, mod solo famiglia).
    assert bronzo.resistenze == ()
    # ORO: fino a due affissi — su molti coni almeno uno porta una resistenza.
    con_res = [conia_procedurale(random.Random(i), "oro") for i in range(30)]
    assert any(o.resistenze for o in con_res), "l'elemento non esce mai: affissi rotti"


def test_oggetto_coniato_e_vivo_con_numeri_derivati(mondo_isolato) -> None:
    _arma_fabbrica()
    # Trova un conio d'oro con resistenza (l'"elemento" di BL3).
    attivo = next(
        o for i in range(50)
        if (o := conia_procedurale(random.Random(i), "oro")).resistenze
        and o.tipo == "armatura"
    )
    vivo = oggetto_da_asset(attivo)
    assert isinstance(vivo, PezzoArmatura)
    assert vivo.resistenze and vivo.resistenze[0].valore < 0   # pct §11, riduce
    for mod in vivo.modificatori:
        assert mod.valore >= 3, "fascia × rango(oro)=3: il grado è la scala"


def test_il_drop_conia_dalla_fabbrica(run_pulita, tmp_path, monkeypatch) -> None:
    """A chance vinta, con la fabbrica attiva il drop è PROCEDURALE anche
    OFFLINE: sincrono, seeded, replay-safe — e l'oggetto è equipaggiabile."""
    monkeypatch.setattr(cal, "PROB_DROP", 1.0)
    monkeypatch.setattr(cal, "PROB_FABBRICA", 1.0)
    sessione = costruisci_sessione(nome="Fabbrica", seed=11, directory=tmp_path)
    snap = asyncio.run(sessione.prossima_narrazione())
    etichette = {o.etichetta: o.indice for o in snap.opzioni}
    sessione.coda.accoda(PlayerChoseOption(next(v for k, v in etichette.items() if k.startswith("Combatti"))))
    snap = sessione.avanza()
    for _ in range(60):
        if snap.fase != "combattimento":
            break
        sessione.coda.accoda(PlayerChoseOption(0))
        snap = sessione.avanza()

    pent, _m, _s = protagonista()
    drop = fonti_zaino(pent)
    assert drop, "la vittoria non ha coniato"
    fonte = drop[0]
    assert fonte in catalogo_oggetti_correnti()
    assert fonte not in {"dadi-truccati"} and not fonte.startswith("cappotto-di-scena")
    # Equipaggiabile come un oggetto di libreria (se è indossabile).
    oggetto = catalogo_oggetti_correnti()[fonte]
    if not isinstance(oggetto, type(None)):
        sessione.equipaggia(fonte)

    # Replay: stessa run, stesso seed → stesso conio.
    esper.switch_world("fabbrica-replay")
    try:
        sessione2 = costruisci_sessione(nome="Fabbrica", seed=11,
                                        directory=tmp_path / "replay")
        snap = asyncio.run(sessione2.prossima_narrazione())
        etichette = {o.etichetta: o.indice for o in snap.opzioni}
        sessione2.coda.accoda(PlayerChoseOption(next(v for k, v in etichette.items() if k.startswith("Combatti"))))
        snap = sessione2.avanza()
        for _ in range(60):
            if snap.fase != "combattimento":
                break
            sessione2.coda.accoda(PlayerChoseOption(0))
            snap = sessione2.avanza()
        pent2, _m2, _s2 = protagonista()
        assert fonti_zaino(pent2)[0] == fonte, "il replay deve riconiare identico"
    finally:
        esper.switch_world("default")
        esper.delete_world("fabbrica-replay")


def test_fabbrica_round_trippa_nel_save(mondo_isolato, tmp_path) -> None:
    from motore import applica_stato, carica_da_disco, salva_run, stagione_corrente

    _arma_fabbrica()
    salva_run(tmp_path, model_id="m1", timestamp=1.0)
    esper.clear_database()
    applica_stato(carica_da_disco(tmp_path, "carl"))
    ripresa = stagione_corrente()
    assert ripresa is not None and ripresa.fabbrica is not None
    assert fabbrica_attiva() is not None
    assert conia_procedurale(random.Random(5), "argento") is not None


def test_rotta_authoring_fabbrica_e_conversione() -> None:
    assert "authoring.fabbrica" in ROTTE
    assert ROTTE["authoring.fabbrica"].schema is FabbricaAsset
    # La conversione al congelato appiattisce enum → stringhe.
    risolta = risolvi_stagione("stagione-1")
    attiva = _fabbrica_a_attiva(risolta.fabbrica)
    assert attiva.basi and isinstance(attiva.basi[0].tipo, str)
    assert any(a.res_contro for a in attiva.affissi)


# --- Playtest 2026-08-19: tre «della Maschera» di fila --------------------------

def test_il_conio_non_ripete_la_famiglia(run_pulita) -> None:
    """`escludi_famiglia`: la manifattura dell'ultimo conio non si ripete se
    la fabbrica ne ha altre — SHIFT d'indice, zero draw extra: il resto dello
    stream (affissi, suffisso) resta byte-identico allo storico."""
    import random as _random

    from main import costruisci_sessione
    from motore import conia_procedurale, fabbrica_attiva

    sessione = costruisci_sessione(seed=1)
    fabbrica = fabbrica_attiva()
    assert fabbrica is not None and len(fabbrica.famiglie) > 1

    def famiglia_di(oggetto) -> str:
        return next(
            f.nome for f in fabbrica.famiglie if oggetto.nome.endswith(f.nome)
        )

    a = conia_procedurale(_random.Random(7), "argento")
    fam_a = famiglia_di(a)
    b = conia_procedurale(_random.Random(7), "argento", escludi_famiglia=fam_a)
    assert famiglia_di(b) != fam_a, "la famiglia esclusa non deve ripetersi"
    assert b.slug[-4:] == a.slug[-4:], (
        "lo shift non consuma draw: il suffisso seeded resta identico"
    )
    c = conia_procedurale(
        _random.Random(7), "argento", escludi_famiglia="manifattura inesistente"
    )
    assert (c.slug, c.nome) == (a.slug, a.nome), (
        "senza collisione il conio resta byte-identico allo storico"
    )
    sessione.esci()
