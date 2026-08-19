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
