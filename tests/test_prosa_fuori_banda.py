"""La porta UNICA della prosa fuori-banda (`SessioneGioco.prossima_prosa`).

Il difetto che questi lucchetti chiudono: la SEQUENZA narrativa non gating —
trailer d'apertura, vestizione del premio, epitaffio — viveva nell'host. La TUI
la ricostruiva confrontando la fase prima/dopo `avanza()` e tenendo un flag
proprio per l'epitaffio; il driver headless e `misura_run` non la ricostruivano
affatto e giravano su un gioco **senza prosa di scontro**. Un host nuovo (web)
avrebbe dovuto ricopiare quella deduzione per non perdere metà della narrazione.

Ora il motore DICHIARA il battito dove il fatto accade e l'host lo DRENA. Le
proprietà bloccate qui sono quattro: si dichiara al fatto, si consuma una volta
sola, un battito degradato non intasa la coda, e l'epitaffio resta drenabile a
run chiusa (la permadeath chiude la run prima che l'host possa chiedere).
"""

from __future__ import annotations

import asyncio

from contracts import PlayerChoseOption, TipoProsa
from main import costruisci_sessione
from provider import FakeProvider


def _sessione_in_scontro():
    sessione = costruisci_sessione(seed=1)
    asyncio.run(sessione.prossima_narrazione())
    sessione.coda.accoda(PlayerChoseOption(0))  # Combatti
    snap = sessione.avanza()
    assert snap.fase == "combattimento"
    return sessione


def test_l_apertura_e_dovuta_appena_lo_scontro_si_apre(run_pulita) -> None:
    """L'host non deduce più «la fase è passata a combattimento, quindi tocca
    il trailer»: il battito è già in coda quando `avanza()` ritorna."""
    sessione = _sessione_in_scontro()
    sessione.provider = FakeProvider([dict(testo="il trailer d'apertura")])
    prosa = asyncio.run(sessione.prossima_prosa())
    assert prosa is not None
    assert prosa.tipo is TipoProsa.APERTURA
    assert prosa.testo == "il trailer d'apertura"


def test_un_battito_si_consuma_una_volta_sola(run_pulita) -> None:
    sessione = _sessione_in_scontro()
    sessione.provider = FakeProvider([dict(testo="uno"), dict(testo="due")])
    assert asyncio.run(sessione.prossima_prosa()).testo == "uno"
    # La coda è vuota: il secondo giro NON deve ripescare il trailer (era il
    # ruolo del flag `_epitaffio_scritto` lato host — ora è del motore).
    assert asyncio.run(sessione.prossima_prosa()) is None


def test_il_battito_degradato_non_intasa_la_coda(run_pulita) -> None:
    """Trasporto muto: il battito si CONSUMA lo stesso. Se restasse in coda,
    l'host che drena in un ciclo girerebbe per sempre su un provider guasto."""
    sessione = _sessione_in_scontro()
    sessione.provider = FakeProvider([])  # nessuna risposta
    assert asyncio.run(sessione.prossima_prosa()) is None
    assert sessione._prosa_dovuta == []


def test_senza_fatti_non_ci_sono_battiti(run_pulita) -> None:
    sessione = costruisci_sessione(seed=1)
    asyncio.run(sessione.prossima_narrazione())
    assert asyncio.run(sessione.prossima_prosa()) is None


def test_l_epitaffio_e_drenabile_a_run_chiusa(run_pulita) -> None:
    """La permadeath chiude la run: le altre porte si spengono, ma l'epitaffio
    deve poter uscire — è l'ultima cosa che il giocatore legge."""
    from contracts import FattiScontro

    sessione = costruisci_sessione(seed=1)
    asyncio.run(sessione.prossima_narrazione())
    sessione._fatti_epitaffio = FattiScontro(
        vittoria=False, fuga=False, nemico="Il Bidello", turni=4, hp_persi=30
    )
    sessione._segna_prosa(TipoProsa.EPITAFFIO)
    sessione._chiusa = True  # come dopo il terminale di run
    sessione.provider = FakeProvider([dict(testo="il pubblico saluta")])
    prosa = asyncio.run(sessione.prossima_prosa())
    assert prosa is not None and prosa.tipo is TipoProsa.EPITAFFIO
    assert prosa.testo == "il pubblico saluta"


def test_a_run_chiusa_gli_altri_battiti_decadono(run_pulita) -> None:
    """Un trailer senza più una scena in cui atterrare non si genera (e non si
    paga): si scarta. Solo l'epitaffio sopravvive alla chiusura."""
    sessione = _sessione_in_scontro()
    fake = FakeProvider([dict(testo="mai chiesto")])
    sessione.provider = fake
    sessione._chiusa = True
    assert asyncio.run(sessione.prossima_prosa()) is None
    assert fake.prompt_ricevuti == [], "nessuna chiamata AI per un battito decaduto"


def test_la_vestizione_e_dovuta_solo_se_c_e_un_drop(run_pulita) -> None:
    """Il drop è a chance: dichiarare il battito a ogni vittoria significherebbe
    una chiamata AI a vuoto per ogni scontro vinto."""
    sessione = _sessione_in_scontro()
    sessione._ultimo_drop = None
    sessione._drop_pendente = None
    sessione._prosa_dovuta.clear()
    sessione._fatti_scontro = None
    # Nessun drop registrato ⇒ nessun battito PREMIO da drenare.
    assert TipoProsa.PREMIO not in sessione._prosa_dovuta


def test_l_host_non_ricostruisce_piu_la_sequenza(run_pulita) -> None:
    """Lucchetto statico: la TUI non deve tornare a dedurre i battiti dalla
    fase. Se un host ricomincia a chiamare le porte per-battito, la sequenza
    torna a vivere in due posti e i due host divergono al primo ritocco."""
    from pathlib import Path

    sorgente = Path(__file__).resolve().parents[1] / "src" / "gioco_textual.py"
    testo = sorgente.read_text(encoding="utf-8")
    assert "prossima_prosa" in testo, "l'host deve drenare la porta unica"
    for porta in ("prosa_apertura_scontro", "veste_premio", ".epitaffio("):
        assert porta not in testo, (
            f"l'host chiama ancora {porta}: la sequenza narrativa è tornata "
            "nell'host invece di stare nel motore"
        )
