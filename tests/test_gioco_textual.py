"""UI di gioco Textual (host opt-in): smoke test headless via `run_test` (nessun terminale
reale). Boota la narrazione, ingaggia il combattimento e lo porta a chiusura solo attraverso
i widget — la prova che il game engine gira end-to-end dietro una UI, via le sole porte.
"""

from __future__ import annotations

import asyncio

import pytest

import gioco_textual
from main import costruisci_sessione


def test_gioca_un_incontro_dalla_ui() -> None:
    pytest.importorskip("textual")  # host opt-in: senza Textual il test si salta
    from textual.widgets import Button

    async def run() -> None:
        app = gioco_textual._costruisci_app(costruisci_sessione(seed=1))
        async with app.run_test() as pilot:
            await pilot.pause()
            # 1) La narrazione è pronta: prosa + menu Combatti/Scappi/Parlamenta
            #    (2026-08-16: l'ostile mai tentato è parlamentabile).
            assert app.fase_corrente == "narrazione"
            assert app.prosa_corrente.strip()  # la narrazione ha prodotto prosa
            assert len(app.query(Button)) == 3

            # 2) Combatti → combattimento (menu DINAMICO: le mosse del Repertorio
            #    del protagonista + Fuggi ultima — oggi 2 mosse iniziali → 3 voci).
            await pilot.click("#opz-0")
            await pilot.pause()
            assert app.fase_corrente == "combattimento"
            assert len(app.query(Button)) == 4

            # 3) Attacca finché lo scontro non si chiude (ritorno a narrazione) o permadeath.
            for _ in range(40):
                if app.fase_corrente != "combattimento" or app._morto:
                    break
                await pilot.click("#opz-0")
                await pilot.pause()
            assert app._morto or app.fase_corrente == "narrazione"

    asyncio.run(run())


def test_finestra_di_conferma_azione_libera() -> None:
    pytest.importorskip("textual")
    from textual.widgets import Input

    async def run() -> None:
        app = gioco_textual._costruisci_app(costruisci_sessione(seed=1))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")  # apre l'input dell'azione libera
            campo = app.query_one("#azione", Input)
            assert campo.has_class("attiva")
            await pilot.press(*"ispeziono lo slime")
            await pilot.press("enter")   # → finestra di conferma (riepilogo + stima)
            await pilot.pause()
            assert app._in_conferma and campo.value == "ispeziono lo slime"
            await pilot.press("enter")   # immissione: il turno GM risponde
            await pilot.pause()
            assert not campo.has_class("attiva")
            assert app.sessione.ultimo_messaggio is not None
            assert app.sessione.ultimo_messaggio.come == "ispeziono lo slime"

    asyncio.run(run())


def test_il_turno_degradato_avvisa_nel_log() -> None:
    """Regression (audit 2026-08-07): il fallback atomico arrivava al giocatore come
    prosa qualunque — lo si riconosceva solo a occhio dalla «Sagoma indistinta».
    Con un provider che non risponde mai, la UI deve DIRE che il turno è di ripiego."""
    pytest.importorskip("textual")
    from provider import FakeProvider

    async def run() -> None:
        # FIFO vuota: ogni chiamata ritorna None → gating fallita → fallback atomico.
        app = gioco_textual._costruisci_app(
            costruisci_sessione(seed=1, provider=FakeProvider([]))
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.sessione.ultimo_messaggio is not None
            assert app.sessione.ultimo_messaggio.fallback is True
            assert app._avvisi_fallback >= 1, (
                "il turno degradato non ha prodotto l'avviso nel log"
            )

    asyncio.run(run())


def test_zaino_e_scheda_dalla_ui() -> None:
    """La demo del giro nuovo dentro la TUI: vinci → bottino nello zaino → Z apre
    l'inventario → Indossa/Togli via porte → C mostra la scheda. Tutto senza che
    l'host tocchi il motore: solo porte e DTO."""
    pytest.importorskip("textual")
    from textual.widgets import Button

    from motore import calibrazione as cal

    async def run() -> None:
        app = gioco_textual._costruisci_app(costruisci_sessione(seed=1))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("c")             # la scheda non esplode a inizio run
            await pilot.pause()

            await pilot.click("#opz-0")        # Combatti
            await pilot.pause()
            for _ in range(40):                # vinci lo scontro
                if app.fase_corrente != "combattimento" or app._morto:
                    break
                await pilot.click("#opz-0")
                await pilot.pause()
            assert not app._morto and app.fase_corrente == "narrazione"
            zaino = app.sessione.scheda().zaino
            assert zaino, "la vittoria non ha depositato il bottino nello zaino"
            fonte_drop = zaino[0]              # il drop per grado pesca dal pool

            await pilot.press("z")             # inventario nel menu
            await pilot.pause()
            ids = {b.id for b in app.query(Button)}
            assert f"zaino-{fonte_drop}" in ids and "zaino-chiudi" in ids

            await pilot.click(f"#zaino-{fonte_drop}")     # Indossa
            await pilot.pause()
            assert fonte_drop in app.sessione.fonti_indossate()

            await pilot.click(f"#zaino-{fonte_drop}")     # Togli (toggle)
            await pilot.pause()
            assert fonte_drop not in app.sessione.fonti_indossate()

            await pilot.click("#zaino-chiudi")            # torna alla scena
            await pilot.pause()
            assert app.fase_corrente == "narrazione"
            assert not any(
                (b.id or "").startswith("zaino-") for b in app.query(Button)
            ), "chiusa la borsa, il menu deve tornare alla scena"

    vecchio = cal.PROB_DROP
    cal.PROB_DROP = 1.0                        # drop garantito: si dimostra il canale
    try:
        asyncio.run(run())
    finally:
        cal.PROB_DROP = vecchio


def _carisma_alto() -> None:
    """Il gate del parlamento reso deterministico (stesso trucco dei test del
    motore): carisma sopra ogni soglia, mutazione diretta del World attivo."""
    import esper

    from contracts import StatId
    from motore.scheda import protagonista
    from motore.statistiche import Primarie

    pent, _m, _s = protagonista()
    esper.component_for_entity(pent, Primarie).valori[StatId.CARISMA] = 40


def test_mode_scena_batte_e_tronca() -> None:
    """Il parlamentare dalla TUI (il pilot che mancava): Parlamenta apre la
    scena e l'input raccoglie BATTUTE (porta di scena, mai il turno GM); una
    battuta non chiude; l'invio VUOTO tronca e il menu riprende la scena."""
    pytest.importorskip("textual")
    from textual.widgets import Button, Input

    async def run() -> None:
        app = gioco_textual._costruisci_app(costruisci_sessione(seed=1))
        async with app.run_test() as pilot:
            await pilot.pause()
            _carisma_alto()
            parlamenta = next(
                b for b in app.query(Button)
                if str(b.label).startswith("Parlamenta")
            )
            await pilot.click(f"#{parlamenta.id}")
            await pilot.pause()
            assert app._in_scena, "il gate superato entra in mode-scena"
            assert app.sessione.avanza().scena_aperta

            campo = app.query_one("#azione", Input)
            campo.focus()
            await pilot.pause()
            await pilot.press(*"Chi comanda qui?")
            await pilot.press("enter")
            await pilot.pause()
            assert app._in_scena, "una battuta non chiude la scena"
            assert app.sessione.avanza().scena_aperta

            campo.focus()
            await pilot.pause()
            await pilot.press("enter")  # vuoto = il giocatore tronca
            await pilot.pause()
            assert not app._in_scena, "l'invio vuoto tronca la conversazione"
            assert not app.sessione.avanza().scena_aperta

    asyncio.run(run())


def test_permadeath_chiude_il_menu() -> None:
    pytest.importorskip("textual")
    from textual.widgets import Button

    async def run() -> None:
        app = gioco_textual._costruisci_app(costruisci_sessione(seed=1))
        async with app.run_test() as pilot:
            await pilot.pause()
            app._morto = True  # simula il terminale di run (MortePersonaggio)
            await app._mostra(_snap_finto(), [])
            await pilot.pause()
            bottoni = app.query(Button)
            assert len(bottoni) == 1 and bottoni.first().id == "esci"

    asyncio.run(run())


class _SnapFinto:
    prosa = ""
    opzioni: tuple = ()
    stato: tuple = ("HP 0/30",)
    fase = "narrazione"


def _snap_finto() -> _SnapFinto:
    return _SnapFinto()


def test_bandierine_sovra_run(run_pulita, tmp_path) -> None:
    """Le tre bandierine collegate anche in TUI (2026-08-20): --daily deriva
    il seed dalla data (lato host, mai l'orologio del motore), --infestata
    monta i fantasmi dal ledger locale. Stesse porte del web."""
    from datetime import date

    from contracts import EsitoRun, Terminale, seed_del_giorno
    from motore.fantasmi import fantasmi_correnti
    from motore.persistenza.esiti import scrivi_esito
    from motore.seme import master_seed

    esito = EsitoRun(
        uuid_run="deadbeef", nome="Katia", seed=7, terminale=Terminale.SCONFITTA
    )
    scrivi_esito(tmp_path, esito.model_dump(mode="json") | {"id": esito.chiave()})

    sessione = gioco_textual._scegli_sessione(
        ["--daily", "--infestata"], None, directory=tmp_path
    )
    assert master_seed() == seed_del_giorno(date.today().isoformat(), 1)
    montati = fantasmi_correnti()
    assert montati is not None and montati.lista[0].nome == "Katia"
    sessione.esci()


def test_il_tasto_b_apre_la_bacheca() -> None:
    pytest.importorskip("textual")
    from textual.widgets import RichLog

    async def run() -> None:
        app = gioco_textual._costruisci_app(costruisci_sessione(seed=1))
        async with app.run_test() as pilot:
            await pilot.pause()
            rl = app.query_one("#log", RichLog)
            prima = len(rl.lines)
            await pilot.press("b")
            await pilot.pause()
            assert len(rl.lines) > prima, (
                "B scrive la bacheca nel log (o il suo stato vuoto)"
            )

    asyncio.run(run())
