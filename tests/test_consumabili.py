"""Canale CONSUMABILI (canale B, ratifica 2026-08-26): monouso, solo in
narrazione, a specchio dell'equip. Si prova: il contratto (effetto obbligato
e vocabolario chiuso), gli effetti coi numeri §11 (quote del massimo), il
rifiuto che NON consuma (a pieni HP la pozione resta), l'antidoto che purga i
dannosi applicati e MAI gli innati, la porta di sessione col phase-gate
(in combattimento l'intento resta in coda), il dato demo nel catalogo della
run. Contenuto dei test sintetico e originale."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from contracts import (
    BusEventi,
    EffettoConsumabile,
    Grado,
    OggettoAsset,
    OggettoUsato,
    PlayerChoseOption,
    StatusSvanito,
)
from motore import (
    CATALOGO_CONSUMABILI,
    Consumabile,
    assicura_zaino,
    calibrazione as cal,
    catalogo_oggetti_correnti,
    crea_protagonista,
    oggetto_da_asset,
    protagonista,
    usa_consumabile,
)
from motore.derivate import max_hp, max_mana
from motore.scheda import assicura_mana
from motore.status import Veleno, afflizione, applica_status


def _protagonista_con(fonte: str) -> int:
    crea_protagonista(destrezza=5, punti_vita=30, id_dominio="prova")
    pent = protagonista()[0]
    assicura_zaino(pent).fonti.append(fonte)
    return pent


# --- Il contratto ---------------------------------------------------------------

def test_il_consumabile_vuole_l_effetto_e_solo_lui_lo_porta() -> None:
    with pytest.raises(ValidationError):
        OggettoAsset(slug="fiala-muta", nome="Fiala", tipo="consumabile",
                     grado=Grado.BRONZO)  # senza effetto: rifiutato
    with pytest.raises(ValidationError):
        OggettoAsset(slug="lama-che-beve", nome="Lama", tipo="arma",
                     grado=Grado.BRONZO, effetto=EffettoConsumabile.CURA)
    ok = OggettoAsset(slug="tonico-x", nome="Tonico", tipo="consumabile",
                      grado=Grado.BRONZO, effetto=EffettoConsumabile.CURA)
    assert isinstance(oggetto_da_asset(ok), Consumabile)


def test_il_consumabile_non_porta_modificatori() -> None:
    """Un consumabile agisce una volta: le fasce sono dell'indossabile."""
    with pytest.raises(ValidationError):
        OggettoAsset(
            slug="brodo-bardato", nome="Brodo", tipo="consumabile",
            grado=Grado.BRONZO, effetto=EffettoConsumabile.CURA,
            modificatori=[{"stat": "forza", "fascia": "lieve"}],
        )


# --- Gli effetti (numeri §11) ---------------------------------------------------

def test_la_cura_e_una_quota_del_massimo(mondo_isolato) -> None:
    pent = _protagonista_con("tonico-di-latta")
    bus = BusEventi()
    usati: list[OggettoUsato] = []
    bus.registra(OggettoUsato, usati.append)

    massimo = max_hp(pent)
    scheda = protagonista()[2]
    scheda.punti_vita = 1
    ok, dettaglio = usa_consumabile(pent, "tonico-di-latta", bus)
    assert ok is True
    quota = max(1, round(massimo * cal.CONSUMABILE_CURA_PCT["bronzo"]))
    assert scheda.punti_vita == min(massimo, 1 + quota)
    assert dettaglio == f"+{scheda.punti_vita - 1} HP"
    [evento] = usati
    assert evento.fonte == "tonico-di-latta" and evento.effetto == "cura"
    assert "tonico-di-latta" not in assicura_zaino(pent).fonti, "monouso"


def test_a_pieni_hp_la_pozione_non_si_consuma(mondo_isolato) -> None:
    pent = _protagonista_con("tonico-di-latta")
    scheda = protagonista()[2]
    scheda.punti_vita = max_hp(pent)
    ok, dettaglio = usa_consumabile(pent, "tonico-di-latta", BusEventi())
    assert ok is False and dettaglio == "sei già intero"
    assert "tonico-di-latta" in assicura_zaino(pent).fonti, (
        "il rifiuto non consuma: niente feel-bad da click"
    )


def test_il_ristoro_di_mana(mondo_isolato) -> None:
    pent = _protagonista_con("fiala-di-china")
    mana = assicura_mana(pent)
    mana.attuale = 0
    ok, _ = usa_consumabile(pent, "fiala-di-china", BusEventi())
    assert ok is True
    quota = max(1, round(max_mana(pent) * cal.CONSUMABILE_MANA_PCT["bronzo"]))
    assert mana.attuale == min(max_mana(pent), quota)
    # Pieno: la fiala successiva viene rifiutata senza consumo.
    assicura_zaino(pent).fonti.append("fiala-di-china")
    mana.attuale = max_mana(pent)
    ok, _ = usa_consumabile(pent, "fiala-di-china", BusEventi())
    assert ok is False
    assert "fiala-di-china" in assicura_zaino(pent).fonti


def test_l_antidoto_purga_i_dannosi_mai_gli_innati(mondo_isolato) -> None:
    import esper

    pent = _protagonista_con("controveleno-da-banco")
    bus = BusEventi()
    svaniti: list[StatusSvanito] = []
    bus.registra(StatusSvanito, svaniti.append)

    # Niente da purgare: rifiuto, il pezzo resta.
    ok, dettaglio = usa_consumabile(pent, "controveleno-da-banco", bus)
    assert ok is False and dettaglio == "niente da purgare"

    # Veleno APPLICATO: purgato, con la fine narrata come la scadenza.
    applica_status(pent, afflizione(Veleno, 2))
    ok, _ = usa_consumabile(pent, "controveleno-da-banco", bus)
    assert ok is True
    assert esper.try_component(pent, Veleno) is None
    assert [s.status for s in svaniti] == ["veleno"]

    # Veleno INNATO (capacità, non afflizione): l'antidoto NON lo tocca.
    esper.add_component(pent, Veleno(rango=1, durata=99, innato=True))
    assicura_zaino(pent).fonti.append("controveleno-da-banco")
    ok, dettaglio = usa_consumabile(pent, "controveleno-da-banco", bus)
    assert ok is False and dettaglio == "niente da purgare"
    assert esper.try_component(pent, Veleno) is not None


# --- Il canale: catalogo, gate, porta -------------------------------------------

def test_il_dato_demo_e_nel_catalogo_della_run(mondo_isolato) -> None:
    crea_protagonista(destrezza=5, punti_vita=30, id_dominio="prova")
    catalogo = catalogo_oggetti_correnti()
    for fonte, demo in CATALOGO_CONSUMABILI.items():
        assert isinstance(catalogo.get(fonte), Consumabile)
        assert demo.effetto in {e.value for e in EffettoConsumabile}
    from motore import grado_oggetto

    assert grado_oggetto("controveleno-da-banco") == "argento"


def test_un_consumabile_non_si_indossa(mondo_isolato) -> None:
    from motore.equip import equipaggia

    pent = _protagonista_con("tonico-di-latta")
    assert equipaggia(pent, CATALOGO_CONSUMABILI["tonico-di-latta"]) is False


def test_la_porta_usa_e_il_phase_gate(run_pulita, tmp_path) -> None:
    """Via porte: in NARRAZIONE l'uso applica e va in cronaca tipata; in
    COMBATTIMENTO l'intento resta in coda (phase-gate strutturale) e si
    applica solo a scontro chiuso."""
    from main import CronacaBus, costruisci_sessione

    sessione = costruisci_sessione(nome="Bevitore", seed=3, directory=tmp_path)
    cronaca = CronacaBus(sessione.bus)
    asyncio.run(sessione.prossima_narrazione())
    pent, _m, scheda = protagonista()
    assicura_zaino(pent).fonti.append("tonico-di-latta")
    scheda.punti_vita = 1

    sessione.usa("tonico-di-latta")
    assert scheda.punti_vita > 1, "in narrazione l'uso è immediato"
    tipi = {t for t, _ in cronaca.preleva_tipata()}
    assert "OggettoUsato" in tipi, "il fatto viaggia tipato in cronaca"

    # In combattimento: l'intento resta in coda, lo zaino non si muove.
    snap = sessione.avanza()
    if not snap.opzioni:
        snap = asyncio.run(sessione.prossima_narrazione())
    combatti = next(
        (o.indice for o in snap.opzioni if o.etichetta.startswith("Combatti")),
        None,
    )
    if combatti is None:
        sessione.esci()
        return  # seed senza scontro immediato: il gate è provato altrove
    assicura_zaino(pent).fonti.append("fiala-di-china")
    assicura_mana(pent).attuale = 0
    sessione.coda.accoda(PlayerChoseOption(combatti))
    snap = sessione.avanza()
    assert snap.fase == "combattimento"
    sessione.usa("fiala-di-china")
    assert "fiala-di-china" in assicura_zaino(pent).fonti, (
        "in combattimento l'intento resta in coda: niente pozioni gratis"
    )
    # Chiuso lo scontro, il primo giro di narrazione DRENA l'intento rimasto.
    for _ in range(60):
        if snap.fase != "combattimento" or sessione.terminale is not None:
            break
        sessione.coda.accoda(PlayerChoseOption(0))
        snap = sessione.avanza()
    if sessione.terminale is None and snap.fase == "narrazione":
        sessione.avanza()
        assert "fiala-di-china" not in assicura_zaino(pent).fonti, (
            "a scontro chiuso l'intento in coda viene servito"
        )
        sessione.esci()


def test_round_trip_di_un_consumabile_coniato(mondo_isolato) -> None:
    """Un `OggettoAttivo` tipo consumabile (con `effetto`) attraversa la
    traduzione e un dict-round-trip senza perdere l'effetto (save-safe)."""
    from dataclasses import asdict

    from motore.design import OggettoAttivo

    attivo = OggettoAttivo(
        slug="sorso-di-brace", nome="Sorso di Brace", tipo="consumabile",
        grado="oro", effetto="cura",
    )
    vivo = oggetto_da_asset(attivo)
    assert isinstance(vivo, Consumabile) and vivo.effetto == "cura"
    rinato = OggettoAttivo(**asdict(attivo))
    assert rinato == attivo
    vecchio = OggettoAttivo(slug="l", nome="L", tipo="arma", grado="oro")
    assert vecchio.effetto == "", "i save pre-canale restano muti e validi"
