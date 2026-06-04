"""La console admin `calibratore`: la CLI headless e uno smoke test della TUI Textual.
Headless (Textual gira via `run_test`, senza terminale reale).
"""

from __future__ import annotations

import asyncio

import pytest

import calibratore
from motore import calibrazione as cal


@pytest.fixture
def cal_pulita():
    prima = dict(cal._OVERRIDE)
    try:
        yield
    finally:
        cal._OVERRIDE.clear()
        cal._OVERRIDE.update(prima)


# --- CLI headless -------------------------------------------------------------

def test_cli_get(capsys) -> None:
    assert calibratore._cli(["get", "S_CONTEST"]) == 0
    assert capsys.readouterr().out.strip() == "2"


def test_cli_list_copre_tutto(capsys) -> None:
    assert calibratore._cli(["list"]) == 0
    out = capsys.readouterr().out
    # Una riga per ogni parametro del catalogo.
    assert out.count("=") >= len(cal.elenco())
    assert "S_CONTEST" in out and "CARL.forza" in out


def test_cli_set_e_reset(cal_pulita, tmp_path, monkeypatch, capsys) -> None:
    # Reindirizza il file di override in tmp (non tocca il repo).
    monkeypatch.setattr(cal, "PERCORSO_OVERRIDE", tmp_path / "ov.json")
    assert calibratore._cli(["set", "F_AUTOHIT", "4"]) == 0
    assert cal.valore("F_AUTOHIT") == 4.0
    assert (tmp_path / "ov.json").exists()
    assert calibratore._cli(["reset", "F_AUTOHIT"]) == 0
    assert cal.valore("F_AUTOHIT") == 3.0


# --- Smoke della TUI Textual --------------------------------------------------

def test_tui_si_monta_e_popola() -> None:
    pytest.importorskip("textual")  # la TUI è opt-in; senza Textual il test si salta

    async def run() -> None:
        app = calibratore._costruisci_app()
        async with app.run_test() as pilot:
            from textual.widgets import DataTable

            tabella = app.query_one("#tabella", DataTable)
            assert tabella.row_count == len(cal.elenco())
            await pilot.pause()
            # La prima riga è evidenziata → il dettaglio è stato richiesto per essa.
            assert app._sel in cal.CATALOGO, "la selezione deve puntare a un parametro noto"

    asyncio.run(run())


def test_tui_modifica_applica_override(cal_pulita) -> None:
    pytest.importorskip("textual")

    async def run() -> None:
        app = calibratore._costruisci_app()
        async with app.run_test() as pilot:
            # Seleziona la prima riga (S_CONTEST), entra in modifica, scrive 3, conferma.
            await pilot.pause()
            await pilot.press("e")                 # apre l'editor precompilato
            await pilot.press("backspace", "3")    # 2 → 3
            await pilot.press("enter")             # applica
            await pilot.pause()
        assert cal.valore("S_CONTEST") == 3        # override applicato in memoria

    asyncio.run(run())
