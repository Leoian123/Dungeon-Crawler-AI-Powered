"""La prova a margine: **nessun tiro**, e l'assenza è verificata staticamente (G §7.1).

Due famiglie di test:
  1. **il lucchetto strutturale** — `prove.py` non importa `random` e `esito_prova` non
     accetta un RNG. Non è una convenzione da ricordare: è una proprietà del sorgente,
     quindi non si aggira per distrazione né "per fortuna del seed";
  2. **il property-test della scala** — le soglie §11 non sono numeri arbitrari:
     promettono che a stat base il bronzo passi, l'oro no, e che il celestiale resti
     fuori portata anche equipaggiati. Se qualcuno le ritocca rompendo quella promessa,
     è qui che se ne accorge.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from contracts import ClasseProva, GradoEsito
from motore import esito_prova, grado_da_margine, margine_prova, prova_riuscita
from motore import prove as modulo_prove
from motore.calibrazione import MARGINE_GRADO

_SORGENTE_PROVE = Path(modulo_prove.__file__)

# Stat di riferimento della scala (`SOGLIA_PROVA.*` in calibrazione): Carl nasce a 10 in
# ogni primaria; il gear dell'MVP vale all'incirca +10.
_STAT_BASE = 10
_STAT_EQUIPAGGIATA = 20


# --- 1. Il lucchetto: qui non si tira ------------------------------------------

def test_il_modulo_prove_non_importa_random() -> None:
    albero = ast.parse(_SORGENTE_PROVE.read_text(encoding="utf-8"))
    importati = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Import):
            importati.update(alias.name.split(".")[0] for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            importati.add(nodo.module.split(".")[0])
    assert "random" not in importati, (
        "prove.py ha ripreso a importare `random`: G §7.1 vuole un confronto a margine, "
        "non un tiro. Se serve un upset, è materia da primitivo opt-in (Fortuna), non "
        "dal percorso base."
    )


def test_la_firma_non_accetta_un_rng() -> None:
    # L'assenza del parametro È il contratto: senza RNG in firma, non c'è modo di
    # pescare, e nessun chiamante può "passare un seed" per sbaglio.
    for funzione in (esito_prova, margine_prova, prova_riuscita):
        parametri = set(inspect.signature(funzione).parameters)
        assert not parametri & {"rng", "random", "seed"}, funzione.__name__


def test_stessa_domanda_stessa_risposta_senza_seed() -> None:
    # Determinismo senza stream: due chiamate identiche danno lo stesso oggetto-valore.
    assert esito_prova(12, ClasseProva.ARGENTO) == esito_prova(12, ClasseProva.ARGENTO)


# --- 2. Il margine e i suoi gradi ----------------------------------------------

def test_il_margine_e_lo_scarto_dalla_soglia() -> None:
    from motore import soglia_classe
    for classe in ClasseProva:
        assert margine_prova(17, classe) == 17 - soglia_classe(classe)


def test_riuscita_e_esattamente_margine_non_negativo() -> None:
    # Il confine è a zero: margine 0 RIESCE (di misura). Un off-by-one qui sposta
    # silenziosamente la difficoltà di ogni prova del gioco.
    for classe in ClasseProva:
        from motore import soglia_classe
        soglia = soglia_classe(classe)
        assert prova_riuscita(soglia, classe) is True
        assert prova_riuscita(soglia - 1, classe) is False


def test_le_quattro_fasce_del_grado() -> None:
    assert grado_da_margine(MARGINE_GRADO) is GradoEsito.SUCCESSO_PIENO
    assert grado_da_margine(MARGINE_GRADO - 1) is GradoEsito.SUCCESSO
    assert grado_da_margine(0) is GradoEsito.SUCCESSO
    assert grado_da_margine(-1) is GradoEsito.FALLIMENTO
    assert grado_da_margine(-MARGINE_GRADO + 1) is GradoEsito.FALLIMENTO
    assert grado_da_margine(-MARGINE_GRADO) is GradoEsito.FALLIMENTO_GRAVE


def test_il_grado_e_monotono_nel_margine() -> None:
    ordine = [
        GradoEsito.FALLIMENTO_GRAVE, GradoEsito.FALLIMENTO,
        GradoEsito.SUCCESSO, GradoEsito.SUCCESSO_PIENO,
    ]
    posizioni = [ordine.index(grado_da_margine(m)) for m in range(-20, 21)]
    assert posizioni == sorted(posizioni), "il grado peggiora al crescere del margine"


# --- 3. La scala §11 promette qualcosa: questo è il lucchetto della promessa ----

def test_a_stat_base_il_bronzo_passa_e_loro_no() -> None:
    assert prova_riuscita(_STAT_BASE, ClasseProva.BRONZO)
    assert prova_riuscita(_STAT_BASE, ClasseProva.ARGENTO)   # di misura (margine 0)
    assert not prova_riuscita(_STAT_BASE, ClasseProva.ORO)


def test_equipaggiati_loro_si_apre_ma_il_celestiale_no() -> None:
    assert prova_riuscita(_STAT_EQUIPAGGIATA, ClasseProva.ORO)
    assert not prova_riuscita(_STAT_EQUIPAGGIATA, ClasseProva.CELESTIALE), (
        "il celestiale ('sedurre un dio') deve restare fuori portata con l'equip "
        "dell'MVP: se diventa raggiungibile, la classe più alta smette di significare "
        "qualcosa e l'AI può inquadrarci qualunque cosa."
    )


def test_le_classi_sono_ordinate_per_difficolta_reale() -> None:
    # Non basta che le soglie crescano: deve crescere anche la difficoltà *percepita*,
    # cioè a stat fissa il numero di classi superate non può aumentare salendo.
    superate = [prova_riuscita(_STAT_EQUIPAGGIATA, c) for c in ClasseProva]
    assert superate == sorted(superate, reverse=True), superate
