"""Prove di abilità (G-14, G-15): l'AI inquadra/veste, il motore RISOLVE a margine.

Difficoltà = classe da enum chiuso, scelta prima della risoluzione e immutabile dopo;
soglia calcolata dal motore; ancore nel catalogo, non nel componente-prova.

⚠️ Questo file testava un `d20` (`stat + tiro ≥ soglia`) che era un **segnaposto** e
contraddiceva G §7.1 («il motore confronta a margine… nessun tiro»). I criteri G-14 e
G-15 sono gli stessi: è cambiato il meccanismo sotto, non ciò che va garantito. Il
"nessun tiro" ha il suo lucchetto in `test_prove_margine.py`.
"""

from __future__ import annotations

import dataclasses

from contracts import ClasseProva
from motore import Prova, ancore_classe, esito_prova, prova_riuscita, soglia_classe
from motore import catalogo as C


# --- G-14: classe prima della risoluzione, immutabile; soglia dal motore -------

def test_G14_soglia_la_calcola_il_motore() -> None:
    # La soglia è funzione della CLASSE, calcolata dal motore (non passata dall'AI).
    for classe in ClasseProva:
        assert isinstance(soglia_classe(classe), int)
    # Più alta la classe, più alta la soglia (ordine coerente coi nomi).
    assert soglia_classe(ClasseProva.BRONZO) < soglia_classe(ClasseProva.CELESTIALE)


def test_G14_risoluzione_deterministica() -> None:
    # Nessun seed da passare, e due chiamate identiche danno lo stesso esito: la
    # riproducibilità qui non dipende da uno stream, è una proprietà della funzione.
    a = esito_prova(10, ClasseProva.ORO)
    b = esito_prova(10, ClasseProva.ORO)
    assert a == b


def test_G14_esito_dipende_da_stat_e_soglia() -> None:
    # Stat enorme batte una soglia bassa; stat nulla contro la soglia più alta fallisce.
    assert prova_riuscita(10_000, ClasseProva.BRONZO)
    assert not prova_riuscita(0, ClasseProva.CELESTIALE)


def test_G14_classe_immutabile_nel_componente() -> None:
    # La classe è fissata nel componente-prova: la risoluzione la legge, non la cambia.
    prova = Prova(classe=ClasseProva.ORO, stat="destrezza")
    soglia_attesa = soglia_classe(prova.classe)
    esito_prova(5, prova.classe)
    assert prova.classe == ClasseProva.ORO
    assert soglia_classe(prova.classe) == soglia_attesa


# --- G-15: ancore nel catalogo, non nel componente-prova ----------------------

def test_G15_componente_prova_porta_solo_la_classe() -> None:
    campi = {f.name for f in dataclasses.fields(Prova)}
    assert campi == {"classe", "stat"}
    # Nessun campo "ancore"/"esempi" nel componente.
    assert "ancore" not in campi and "esempi" not in campi


def test_G15_ancore_vivono_nel_catalogo() -> None:
    # Le ancore sono nel catalogo (registry di dominio), non nell'entità-prova.
    for classe in ClasseProva:
        ancore = ancore_classe(classe)
        assert isinstance(ancore, tuple) and len(ancore) >= 1
    assert hasattr(C, "ANCORE_CLASSE")
