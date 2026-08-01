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
            # 1) La narrazione è pronta: prosa + menu Combatti/Scappi.
            assert app.fase_corrente == "narrazione"
            assert app.prosa_corrente.strip()  # la narrazione ha prodotto prosa
            assert len(app.query(Button)) == 2

            # 2) Combatti → si passa al combattimento (un solo bottone: Attacca).
            await pilot.click("#opz-0")
            await pilot.pause()
            assert app.fase_corrente == "combattimento"
            assert len(app.query(Button)) == 1

            # 3) Attacca finché lo scontro non si chiude (ritorno a narrazione) o permadeath.
            for _ in range(40):
                if app.fase_corrente != "combattimento" or app._morto:
                    break
                await pilot.click("#opz-0")
                await pilot.pause()
            assert app._morto or app.fase_corrente == "narrazione"

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
