"""Adattatore Textual — prove comportamentali via Pilot (C-4, C-6, C-7) + un incontro
completo giocato headless. Si salta se Textual non è installato (l'arnia headless, C-5,
non ne dipende).
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("textual")  # le prove di UI richiedono Textual; l'arnia headless no

import esper

from contracts import BusEventi, MortePersonaggio, PlayerChoseOption, SnapshotVista
from adattatore import GiocoApp


@pytest.fixture
def pulisci_run():
    """Le prove d'integrazione creano un run-World ("run"): lo si ripulisce dopo."""
    yield
    esper.switch_world("default")
    if "run" in esper.list_worlds():
        esper.delete_world("run")


def _app_minimale(*, prossima_narrazione=None, avanza=None, accoda=None, salva=None):
    """GiocoApp con porte iniettate finte: testa l'adattatore in ISOLAMENTO (nessun
    motore, nessun World) — la membrana C-2b in azione."""
    return GiocoApp(
        bus=BusEventi(),
        prossima_narrazione=prossima_narrazione or _narrazione_vuota,
        avanza=avanza or (lambda: SnapshotVista()),
        accoda_intento=accoda or (lambda _i: None),
        salva=salva or (lambda: "Salvato."),
    )


async def _narrazione_vuota() -> SnapshotVista:
    return SnapshotVista(prosa="Una stanza.", opzioni=(), fase="narrazione")


# --- Un incontro completo, giocato headless (la verifica "gioca a mano") -------

def test_incontro_completo_headless(pulisci_run) -> None:
    from main import costruisci_app

    async def gioca() -> None:
        app = costruisci_app(seed=1)
        async with app.run_test() as pilot:
            await pilot.pause()
            for _ in range(20):  # attende il primo turno di narrazione (worker)
                await pilot.pause()
                if app._opzioni_correnti:
                    break
            assert [o.tipo.value for o in app._opzioni_correnti] == ["combatti", "scappa"]
            assert app._snapshot.fase == "narrazione"

            await pilot.press("1")  # Combatti → ingaggia
            await pilot.pause()
            assert app._snapshot.fase == "combattimento"

            for i in range(40):  # Attacca finché lo scontro non si chiude
                await pilot.press("1")
                await pilot.pause()
                if app._snapshot.fase == "narrazione":
                    break
            assert app._snapshot.fase == "narrazione"  # vittoria → ritorno alla narrazione

    asyncio.run(gioca())


# --- C-6: la UI non si blocca durante una chiamata LLM in volo ----------------

def test_C6_ui_non_si_blocca_durante_llm(pulisci_run) -> None:
    blocco = asyncio.Event()
    salvati: list[int] = []

    async def narrazione_appesa() -> SnapshotVista:
        await blocco.wait()  # simula l'LLM "che pensa": non si risolve
        return SnapshotVista(prosa="finalmente", fase="narrazione")

    async def prova() -> None:
        app = _app_minimale(
            prossima_narrazione=narrazione_appesa,
            salva=lambda: (salvati.append(1), "Salvato.")[1],
        )
        async with app.run_test() as pilot:
            await pilot.pause()  # on_mount → worker parte e si blocca su await
            # La UI risponde MENTRE il worker è in volo: il salvataggio va a buon fine.
            await pilot.press("s")
            await pilot.pause()
            assert salvati == [1], "la UI è bloccata durante la chiamata LLM (C-6 violato)"
            blocco.set()  # sblocca per chiudere pulito

    asyncio.run(prova())


def test_C6_worker_exclusive_cancella_la_richiesta_superata(pulisci_run) -> None:
    partite: list[int] = []
    cancellate: list[int] = []
    blocco = asyncio.Event()

    async def narrazione() -> SnapshotVista:
        partite.append(1)
        try:
            await blocco.wait()
        except asyncio.CancelledError:
            cancellate.append(1)
            raise
        return SnapshotVista()

    async def prova() -> None:
        app = _app_minimale(prossima_narrazione=narrazione)
        async with app.run_test() as pilot:
            await pilot.pause()  # worker1 parte, si blocca
            assert partite == [1]
            app._carica_narrazione()  # exclusive=group("narrazione") → cancella worker1
            await pilot.pause()
            assert len(partite) == 2, "il secondo worker non è partito"
            assert cancellate == [1], "la richiesta superata non è stata cancellata (C-6)"
            blocco.set()

    asyncio.run(prova())


def test_C6_worker_e_exclusive_di_gruppo() -> None:
    # Statico: il worker della narrazione è dichiarato exclusive nel suo gruppo.
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "src" / "adattatore" / "app.py").read_text(encoding="utf-8")
    assert 'exclusive=True' in src and 'group="narrazione"' in src


# --- C-7: la scelta del giocatore è un INTENTO tipizzato, non muta il World ----

def test_C7_scelta_emette_intento_tipizzato(pulisci_run) -> None:
    accodati: list = []
    snap_con_opzioni = SnapshotVista(
        prosa="",
        opzioni=(__import__("contracts").OpzioneVista(indice=0, etichetta="Combatti",
                 tipo=__import__("contracts").TipoAzione.COMBATTI),),
        fase="narrazione",
    )

    async def prova() -> None:
        app = _app_minimale(
            prossima_narrazione=lambda: _ritorna(snap_con_opzioni),
            avanza=lambda: SnapshotVista(fase="combattimento"),
            accoda=accodati.append,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            for _ in range(10):
                await pilot.pause()
                if app._opzioni_correnti:
                    break
            await pilot.press("1")  # sceglie l'opzione 0
            await pilot.pause()
            # Il widget ha emesso un intento tipizzato sulla coda, non mutato il World.
            assert len(accodati) == 1
            assert isinstance(accodati[0], PlayerChoseOption) and accodati[0].opzione == 0

    asyncio.run(prova())


async def _ritorna(snap: SnapshotVista) -> SnapshotVista:
    return snap


# --- C-4: lo snapshot è un input di rendering rimpiazzato in blocco ------------

def test_C4_snapshot_rimpiazzato_in_blocco(pulisci_run) -> None:
    from contracts import OpzioneVista, TipoAzione
    from textual.widgets import OptionList

    opt0 = OpzioneVista(indice=0, etichetta="A", tipo=TipoAzione.COMBATTI)
    opt1 = OpzioneVista(indice=1, etichetta="B", tipo=TipoAzione.SCAPPA)
    primo = SnapshotVista(opzioni=(opt0, opt1), stato=("HP 30/30",), fase="narrazione")
    secondo = SnapshotVista(opzioni=(opt0,), stato=("HP 10/30", "ferito"), fase="narrazione")

    async def prova() -> None:
        app = _app_minimale(prossima_narrazione=lambda: _ritorna(primo))
        async with app.run_test() as pilot:
            await pilot.pause()
            for _ in range(10):
                await pilot.pause()
                if app._opzioni_correnti:
                    break
            menu = app.query_one("#menu", OptionList)
            assert menu.option_count == 2 and app._snapshot.stato == ("HP 30/30",)

            # Secondo snapshot: SOSTITUITO in blocco, non accumulato né diffato (C-4).
            app._mostra(secondo)
            await pilot.pause()
            assert menu.option_count == 1, "il menu è stato accumulato, non rimpiazzato"
            assert app._opzioni_correnti == (opt0,)
            assert app._snapshot.stato == ("HP 10/30", "ferito")  # ultimo, non somma

    asyncio.run(prova())
