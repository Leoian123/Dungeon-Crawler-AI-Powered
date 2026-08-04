"""Criteri con copertura implicita altrove, resi ESPLICITI per la rassegna del gate
del nodo A (F-7, G-2, G-17, G-23, C-3, H-L2, J-L1, J-L2). Headless.
"""

from __future__ import annotations

import asyncio
import dataclasses
import random

import esper

from contracts import Durata, EntitaGenerata, Flavor, MortePersonaggio
from motore import (
    REGISTRY_BLOCCHI,
    Primarie,
    Scheda,
    Status,
    fast_forward,
    genera_prosa,
    passa_turno,
    protagonista,
    tempo_piano_corrente,
)
from provider import FakeProvider
from tests.tempo_helpers import avvia_esplorazione


# --- F-7: chiamate di sola prosa = stesso verbo `genera`, schema Flavor --------

def test_F7_prosa_stesso_verbo_schema_flavor() -> None:
    prov = FakeProvider([Flavor(testo="ciao")])
    testo = asyncio.run(genera_prosa(prov, "prompt opaco"))
    assert testo == "ciao"
    assert prov.schemi_ricevuti == [Flavor]  # stesso verbo, schema banale (non un 2° metodo)


def test_F7_prosa_puo_mancare_senza_mutare_stato() -> None:
    prov = FakeProvider([None])  # l'`Altro`-MVP/flavor può mancare
    assert asyncio.run(genera_prosa(prov, "p")) is None  # nessuna eccezione, nessuno stato toccato


# --- G-2 / Gruppo 2 §5: la scheda è la risorsa-vita; le primarie nel vettore --

def test_G2_scheda_porta_i_pezzi_obbligatori() -> None:
    campi = {f.name for f in dataclasses.fields(Scheda)}
    assert "vivo" in campi               # stato-vita del death-check (§6.2)
    assert "punti_vita" in campi         # HP corrente: risorsa posseduta (§5)
    # Il massimo HP NON è depositato: deriva da Costituzione (GR2-10).
    assert "punti_vita_max" not in campi
    # La destrezza vive nel vettore Primarie, non in Scheda (una strada sola, §3.3).
    assert "destrezza" not in campi
    assert "valori" in {f.name for f in dataclasses.fields(Primarie)}


# --- G-17: `livello` NON è un input dell'AI -----------------------------------

def test_G17_livello_assente_da_entita_generata() -> None:
    assert "livello" not in EntitaGenerata.model_fields


# --- G-23: i blocchi del catalogo sono primitivi componibili (componenti ECS) --

def test_G23_blocchi_sono_primitivi_componibili() -> None:
    # Ogni blocco mappa a un COMPONENTE dato-puro (status), non a un effetto monolitico:
    # un'entità è una *somma* di questi componenti (composizione aperta).
    for blocco, tipo in REGISTRY_BLOCCHI.items():
        assert isinstance(tipo, type) and issubclass(tipo, Status), blocco
        # `innato` = stato d'istanza (capacità vs afflizione), resta dato puro.
        assert {f.name for f in dataclasses.fields(tipo)} == {"rango", "durata", "innato"}


# --- C-3: il motore non importa una vista/adattatore (host-agnostico) -----------

def test_C3_motore_non_importa_una_vista() -> None:
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src"
    # Il motore resta host-agnostico: niente import di un adattatore di presentazione
    # (rimosso nel ritorno a headless) né di una libreria di UI.
    for py in (src / "motore").rglob("*.py"):
        for nodo in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.ImportFrom) and not nodo.level and nodo.module:
                assert nodo.module.split(".")[0] not in {"adattatore", "textual"}, py.name


# --- H-L2: un crash a metà scrittura non lascia un save inservibile ------------

def test_HL2_scrittura_atomica_e_backup(mondo_isolato: str, tmp_path) -> None:
    from motore import salva_run
    from motore.persistenza.disco import (
        SUFFISSO_BACKUP_STATO,
        leggi_intestazione,
        path_stato,
    )
    from tests.persist_helpers import costruisci_run

    costruisci_run(id_dominio="carl")
    salva_run(tmp_path, model_id="m", timestamp=1.0)
    salva_run(tmp_path, model_id="m", timestamp=2.0)  # secondo save → backup della coppia
    # Niente file temporaneo residuo (rename atomico) e l'ultimo save è integro.
    assert list(tmp_path.glob("*.tmp")) == []
    assert leggi_intestazione(path_stato(tmp_path, "carl"))["uuid"] == "carl"
    # Esiste il backup di sola recovery della coppia coerente.
    assert (tmp_path / f"carl{SUFFISSO_BACKUP_STATO}").exists()


# --- J-L1 / J-L2: il tempo avanza solo per tick; lo scorrimento si arresta sulla morte

def test_JL1_il_tempo_avanza_solo_per_tick(mondo_isolato: str) -> None:
    _bus, _pent = avvia_esplorazione(seed=_seed_no_imboscata())
    t0 = tempo_piano_corrente()
    # Senza un tick risolto (nessun passa-turno/fast-forward), il tempo NON avanza.
    assert tempo_piano_corrente() == t0
    passa_turno(_bus)
    assert tempo_piano_corrente() == t0 + 1  # avanzato solo grazie al tick


def test_JL2_lo_scorrimento_si_arresta_sulla_morte(mondo_isolato: str) -> None:
    bus, pent = avvia_esplorazione(seed=_seed_no_imboscata())
    eventi: list = []
    bus.registra(MortePersonaggio, eventi.append)
    protagonista()[2].punti_vita = 0  # il prossimo tick: death-check → morte
    ris = fast_forward(bus, Durata.UN_BEL_PO)
    assert ris.interrotto_da == "morte" and ris.tick_eseguiti == 1
    assert eventi, "la morte deve emergere e troncare lo scorrimento (J-L2)"


def _seed_no_imboscata() -> int:
    from motore import PROB_IMBOSCATA

    return next(s for s in range(10_000) if random.Random(f"{s}:1").random() >= PROB_IMBOSCATA)
