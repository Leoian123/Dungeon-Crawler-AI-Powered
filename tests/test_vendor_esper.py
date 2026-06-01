"""Verifica sul codice VENDORIZZATO che l'API a livello di modulo sia quella usata,
e che l'idioma vietato di istanziazione del World non compaia mai nel sorgente di
progetto (ESP §0).

Non si va a memoria: si controlla l'esper effettivamente importato dal repo.

Nota: il pattern vietato viene costruito per concatenazione (vedi `_NEEDLE`) così
da non comparire MAI come letterale in questo file — altrimenti la guardia
inciamperebbe su sé stessa e potrebbe restare scansionando tutto src/ e tests/,
inclusa sé stessa.
"""

from __future__ import annotations

from pathlib import Path

import esper

_REPO = Path(__file__).resolve().parents[1]
# Sorgente di PROGETTO (non il vendor di terze parti).
_DIRS_DI_PROGETTO = [_REPO / "src", _REPO / "tests"]

# Idioma vietato in esper 3.x: istanziazione del World. Costruito per concatenazione
# per non comparire come letterale qui dentro.
_NEEDLE = "esper." + "World("


def test_esper_e_la_versione_vendorizzata_pinnata() -> None:
    # È davvero la 3.x vendorizzata nel repo, non un esper installato altrove.
    assert esper.__version__ == "3.7"
    assert (_REPO / "vendor" / "esper").resolve() in Path(esper.__file__).resolve().parents


def test_api_a_livello_di_modulo_presente() -> None:
    # Le funzioni a livello di modulo richieste dalla fase esistono e sono callable.
    for nome in (
        "create_entity",
        "add_component",
        "get_component",
        "get_components",
        "switch_world",
        "delete_world",
        "process",
    ):
        assert callable(getattr(esper, nome)), f"esper.{nome} mancante o non callable"


def test_world_class_non_esiste() -> None:
    # In esper 3.x l'oggetto World è stato rimosso: non deve esistere come attributo.
    assert not hasattr(esper, "World"), "esper.World non deve esistere nella serie 3.x"


def test_nessun_world_instanziato_nel_sorgente_di_progetto() -> None:
    """Grep: l'istanziazione del World è VIETATA nel sorgente di progetto (src/, tests/)."""
    offesi: list[str] = []
    for base in _DIRS_DI_PROGETTO:
        for py in base.rglob("*.py"):
            testo = py.read_text(encoding="utf-8")
            for num, riga in enumerate(testo.splitlines(), start=1):
                if _NEEDLE in riga:
                    offesi.append(f"{py.relative_to(_REPO)}:{num}: {riga.strip()}")
    assert not offesi, f"Uso vietato di {_NEEDLE}\n" + "\n".join(offesi)
