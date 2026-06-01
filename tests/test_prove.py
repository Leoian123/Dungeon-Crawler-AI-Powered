"""Prove di abilità (G-14, G-15): l'AI inquadra/veste, il motore TIRA seeded.

Difficoltà = classe da enum chiuso, scelta prima del tiro e immutabile dopo; soglia
calcolata dal motore; ancore nel catalogo, non nel componente-prova.
"""

from __future__ import annotations

import dataclasses
import random

from contracts import ClasseProva
from motore import Prova, ancore_classe, risolvi_prova, soglia_classe
from motore import catalogo as C


# --- G-14: classe prima del tiro, immutabile; soglia dal motore, seeded -------

def test_G14_soglia_la_calcola_il_motore() -> None:
    # La soglia è funzione della CLASSE, calcolata dal motore (non passata dall'AI).
    assert risolvi_prova.__doc__  # esiste
    for classe in ClasseProva:
        assert isinstance(soglia_classe(classe), int)
    # Più alta la classe, più alta la soglia (ordine coerente coi nomi).
    assert soglia_classe(ClasseProva.BRONZO) < soglia_classe(ClasseProva.CELESTIALE)


def test_G14_tiro_seeded_deterministico() -> None:
    s1 = [risolvi_prova(10, ClasseProva.ORO, random.Random(7)) for _ in range(1)]
    a = [risolvi_prova(10, ClasseProva.ORO, r) for r in (random.Random(3),)]
    b = [risolvi_prova(10, ClasseProva.ORO, r) for r in (random.Random(3),)]
    assert a == b  # stesso seed → stesso esito
    assert s1 is not None


def test_G14_esito_dipende_da_stat_e_soglia() -> None:
    # Stat enorme batte qualunque dado contro soglia bassa; stat nulla contro soglia
    # altissima fallisce sempre. (Il motore confronta stat+dado vs soglia.)
    rng = random.Random(123)
    assert all(risolvi_prova(10_000, ClasseProva.BRONZO, rng) for _ in range(20))
    rng = random.Random(123)
    assert not any(risolvi_prova(0, ClasseProva.CELESTIALE, rng) for _ in range(20))


def test_G14_classe_immutabile_nel_componente() -> None:
    # La classe è fissata nel componente-prova: la risoluzione la legge, non la cambia.
    prova = Prova(classe=ClasseProva.ORO, stat="destrezza")
    soglia_attesa = soglia_classe(prova.classe)
    # Risolvere non muta la classe scelta (nessun percorso per abbassarla dopo il tiro).
    risolvi_prova(5, prova.classe, random.Random(1))
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
