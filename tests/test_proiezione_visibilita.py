"""Proiezione filtrata per visibilità (Gruppo 2 §2.4, GR2-9): la proiezione omette il
VALORE per `VALORE_NASCOSTO` e omette del tutto la STAT per `ESISTENZA_NEGATA`.

Il filtro vive lato motore (`proietta_scheda`, legge `REGISTRY_STAT`); il DTO in
`contracts` riceve mappe già filtrate (membrana C-3).
"""

from __future__ import annotations

from contracts import StatId
from motore import crea_protagonista, proietta_scheda


def test_GR2_9_visibilita_filtra_la_proiezione(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=12, punti_vita=30)
    proj = proietta_scheda(pent)

    # PALESE: nome + valore effettivo presenti.
    assert proj.primarie[StatId.FORZA.value] >= 1
    assert proj.primarie[StatId.DESTREZZA.value] == 12
    assert proj.primarie[StatId.COSTITUZIONE.value] == 30

    # VALORE_NASCOSTO (Saggezza): il nome compare fra le occulte, il VALORE no.
    assert StatId.SAGGEZZA.value in proj.primarie_occulte
    assert StatId.SAGGEZZA.value not in proj.primarie

    # ESISTENZA_NEGATA (Fortuna): assente da entrambe — la proiezione la nega.
    assert StatId.FORTUNA.value not in proj.primarie
    assert StatId.FORTUNA.value not in proj.primarie_occulte


def test_GR2_9_membrana_proiezione_senza_registry() -> None:
    # Il DTO è solo forma-dato: il modulo `contracts.proiezione` non importa il registry
    # del motore né esper (C-3). Statico sugli IMPORT reali (non sul testo: la docstring
    # può nominare `REGISTRY_STAT` spiegando da dove arriva il filtro).
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "contracts" / "proiezione.py"
    albero = ast.parse(src.read_text(encoding="utf-8"))
    moduli: set[str] = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Import):
            moduli |= {a.name.split(".")[0] for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            moduli.add(nodo.module.split(".")[0])
    assert "esper" not in moduli
    assert "motore" not in moduli
