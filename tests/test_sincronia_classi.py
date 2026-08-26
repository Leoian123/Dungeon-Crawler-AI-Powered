"""Sincronia strutturale `Grado` ↔ `ClasseProva` ↔ foglie §11 (F-6).

Il bug che questi test impediscono di ripetere: `ClasseProva` aveva **4** membri mentre
`Grado` ne aveva **6**, e le tabelle `SOGLIE_PROVA`/`ANCORE_CLASSE` erano liste scritte a
mano — quindi *coerenti con l'enum sbagliato*. Nessun test poteva accorgersene, perché
tutti iteravano `ClasseProva`, cioè la fonte del difetto.

La difesa è strutturale, non di disciplina:
  - `SOGLIE_PROVA` è **generata** dall'enum → una classe senza foglia §11 è `KeyError`
    all'import di `calibrazione`, non un buco scoperto a runtime;
  - `CLASSE_DA_GRADO` è una `zip(..., strict=True)` → se i due enum divergono di un
    membro, l'import esplode invece di accoppiare in silenzio le prime N voci.
Questi test lucchettano le due proprietà **dall'esterno**, sui due enum insieme.
"""

from __future__ import annotations

from contracts import ClasseProva, Grado
from motore import ancore_classe, soglia_classe
from motore.calibrazione import SOGLIE_PROVA
from motore.catalogo import CLASSE_DA_GRADO, classe_da_grado

# NB: nessuna fixture di World qui — questi test ispezionano enum e tabelle di catalogo,
# non toccano mai `esper`. Il contesto isolato (ESP §0.1) serve a chi crea entità.


# --- Le due scale sono la stessa scala, vista da due lati ---------------------

def test_classe_prova_e_grado_hanno_la_stessa_cardinalita() -> None:
    assert len(ClasseProva) == len(Grado) == 6


def test_i_due_enum_hanno_gli_stessi_nomi_nello_stesso_ordine() -> None:
    # Non basta la cardinalità: l'accoppiamento è POSIZIONALE (zip), quindi un ordine
    # diverso accoppierebbe silenziosamente "oro" con "platino".
    assert [c.value for c in ClasseProva] == [g.value for g in Grado]


def test_classe_da_grado_e_totale_e_biiettiva() -> None:
    assert set(CLASSE_DA_GRADO) == set(Grado)
    assert set(CLASSE_DA_GRADO.values()) == set(ClasseProva)
    for grado in Grado:
        # Accoppiamento per NOME, non solo per posizione: è la proprietà che rende la
        # mappa leggibile ("un nemico d'oro impone una prova d'oro").
        assert classe_da_grado(grado).value == grado.value


# --- Ogni classe ha la sua foglia §11 e la sua ancora (F-6) -------------------

def test_ogni_classe_ha_una_soglia() -> None:
    assert set(SOGLIE_PROVA) == set(ClasseProva)
    for classe in ClasseProva:
        assert isinstance(soglia_classe(classe), int)


def test_le_soglie_sono_strettamente_crescenti() -> None:
    soglie = [soglia_classe(c) for c in ClasseProva]
    assert soglie == sorted(soglie), soglie
    assert len(set(soglie)) == len(soglie), f"due classi con la stessa soglia: {soglie}"


def test_ogni_classe_ha_almeno_unancora() -> None:
    for classe in ClasseProva:
        ancore = ancore_classe(classe)
        assert isinstance(ancore, tuple) and len(ancore) >= 1
        assert all(a.strip() for a in ancore)


def test_le_ancore_sono_distinte_per_classe() -> None:
    # Due classi con la stessa ancora sarebbero un copia-incolla che svuota il freno
    # all'inflazione di classe (G §7.4): l'ancora serve a far *sentire* la differenza.
    tutte = [a for c in ClasseProva for a in ancore_classe(c)]
    assert len(set(tutte)) == len(tutte)
