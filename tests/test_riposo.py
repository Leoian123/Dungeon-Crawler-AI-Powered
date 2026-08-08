"""Il riposo di scena: l'anello «sostentati» cucito (giro 2026-08-07).

Tre strati esistevano già — `TipoAzione.RIPOSA`, la foglia `DURATA_AZIONE.riposa`,
`RiposoConcluso` con la riga di cronaca — e nessun percorso li raggiungeva. In più
la mina del fall-through: un'opzione «Riposa» composta SENZA il suo ramo nel port
sarebbe caduta nel fallback di INGAGGIO e avrebbe aperto uno scontro. Questi test
tengono insieme: opzione vera solo quando lecita, recupero clampato ai massimi
derivati, evento in cronaca, tempo speso, e — soprattutto — niente scontro.
"""

from __future__ import annotations

import asyncio
import random

from contracts import BusEventi, PlayerChoseOption, RiposoConcluso, TipoAzione
from main import CronacaBus, costruisci_sessione
from motore import (
    Fase,
    SistemaTempoPiano,
    Veleno,
    applica_status,
    assicura_mana,
    avvia_run,
    crea_mappa,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_tempo_piano,
    max_hp,
    max_mana,
    protagonista,
    riposa,
    tempo_piano_corrente,
)
from motore.calibrazione import RIPOSO_HP_PER_TICK, RIPOSO_MANA_PER_TICK


def _arma(seed: int = 7) -> int:
    crea_profondita()
    crea_seme(seed)
    crea_tempo_piano()
    crea_mappa(random.Random(seed))
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    avvia_run(crea_singleton_fase=True, fase_iniziale=Fase.NARRAZIONE,
              sempre_attivi=[SistemaTempoPiano()])
    return pent


# --- Il centro: recupero clampato, tempo speso, evento pubblicato ---------------

def test_riposa_recupera_spende_tempo_e_pubblica(mondo_isolato: str) -> None:
    pent = _arma()
    _p, _m, scheda = protagonista()
    scheda.punti_vita = 10
    mana = assicura_mana(pent)
    mana.attuale = 1
    bus = BusEventi()
    visti: list[RiposoConcluso] = []
    bus.registra(RiposoConcluso, visti.append)
    t0 = tempo_piano_corrente()
    try:
        evento = riposa(bus)
    finally:
        bus.deregistra(RiposoConcluso, visti.append)

    assert evento is not None and evento.tick_spesi > 0
    assert tempo_piano_corrente() == t0 + evento.tick_spesi  # il riposo COSTA tempo
    atteso_hp = min(max_hp(pent), 10 + evento.tick_spesi * RIPOSO_HP_PER_TICK) - 10
    assert evento.hp_recuperati == atteso_hp and scheda.punti_vita == 10 + atteso_hp
    atteso_mana = min(max_mana(pent), 1 + evento.tick_spesi * RIPOSO_MANA_PER_TICK) - 1
    assert evento.mana_recuperato == atteso_mana and mana.attuale == 1 + atteso_mana
    assert visti == [evento]                       # la cronaca ha il suo produttore


def test_riposa_non_gonfia_oltre_i_massimi_derivati(mondo_isolato: str) -> None:
    pent = _arma()
    _p, _m, scheda = protagonista()
    mana = assicura_mana(pent)                     # nasce pieno
    evento = riposa(None)
    assert evento is not None
    assert scheda.punti_vita == max_hp(pent) and evento.hp_recuperati == 0
    assert mana.attuale == max_mana(pent) and evento.mana_recuperato == 0


def test_riposa_rifiuta_il_downtime_vietato(mondo_isolato: str) -> None:
    """Con uno status DANNOSO addosso il downtime non è lecito (J §5): niente
    tick spesi, niente recupero — il veleno non si dorme via."""
    pent = _arma()
    applica_status(pent, Veleno(rango=1, durata=3))
    t0 = tempo_piano_corrente()
    assert riposa(None) is None
    assert tempo_piano_corrente() == t0


# --- Via porte: l'opzione è vera solo quando lecita, e NON ingaggia -------------

def test_riposa_in_scena_recupera_e_non_apre_uno_scontro(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(nome="Riposo", seed=1, directory=tmp_path)
    cronaca = CronacaBus(sessione.bus)
    try:
        snap = asyncio.run(sessione.prossima_narrazione())
        etichette = {o.etichetta: o.indice for o in snap.opzioni}
        # Col mob vivo la scena è Combatti/Scappi: NIENTE riposo in faccia al nemico.
        assert "Riposa" not in etichette and "Scappi" in etichette

        sessione.coda.accoda(PlayerChoseOption(etichette["Scappi"]))
        snap = sessione.avanza()                   # disimpegno riuscito (DEX 10 vs bronzo)
        etichette = {o.etichetta: o.indice for o in snap.opzioni}
        assert "Riposa" in etichette, f"stanza sicura senza Riposa: {etichette}"

        _p, _m, scheda = protagonista()
        scheda.punti_vita = 15
        cronaca.preleva()
        sessione.coda.accoda(PlayerChoseOption(etichette["Riposa"]))
        snap = sessione.avanza()

        # LA MINA (giro 2026-08-07): senza il ramo esplicito nel port, «Riposa»
        # cadeva nel fallback e APRIVA UNO SCONTRO.
        assert snap.fase == "narrazione", "Riposa ha ingaggiato un combattimento"
        assert scheda.punti_vita > 15, "il riposo non ha recuperato nulla"
        righe = cronaca.preleva()
        assert any(r.startswith("Riposi (") for r in righe), righe
    finally:
        cronaca.chiudi()


def test_lopzione_riposa_ha_il_suo_tipo_chiuso(run_pulita, tmp_path) -> None:
    """Il menu non è testo: l'opzione viaggia col TIPO `RIPOSA` (enum chiuso),
    così ogni host la riconosce senza confrontare stringhe."""
    sessione = costruisci_sessione(nome="Tipo", seed=1, directory=tmp_path)
    snap = asyncio.run(sessione.prossima_narrazione())
    etichette = {o.etichetta: o.indice for o in snap.opzioni}
    sessione.coda.accoda(PlayerChoseOption(etichette["Scappi"]))
    snap = sessione.avanza()
    tipi = {o.tipo for o in snap.opzioni}
    assert TipoAzione.RIPOSA in tipi
