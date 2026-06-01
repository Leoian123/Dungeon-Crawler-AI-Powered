"""F-2: `contracts` importa SOLO stdlib + Pydantic; mai esper/Textual/provider/layer.

Verifica statica (AST): si scandiscono tutti i moduli di `src/contracts` e si
controlla la radice di ogni import. Più forte di un grep: vede esattamente i nomi
importati, non sottostringhe.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_CONTRACTS = _REPO / "src" / "contracts"

# Radici esplicitamente VIETATE: layer di progetto e dipendenze "vive"/di provider.
_RADICI_VIETATE = {
    "esper", "textual", "anthropic",
    "motore", "adattatore", "guscio", "provider",  # `provider` = il LAYER, non contracts.provider
}

# Radici permesse oltre alla stdlib: solo Pydantic (e __future__).
_RADICI_PERMESSE_EXTRA = {"pydantic", "__future__"}


def _moduli_contracts() -> list[Path]:
    return sorted(_CONTRACTS.rglob("*.py"))


def _radici_importate(albero: ast.AST) -> list[tuple[str, int]]:
    """Ritorna (radice, linea) per ogni import ASSOLUTO. Gli import relativi
    (intra-`contracts`, level>0) sono leciti e ignorati."""
    radici: list[tuple[str, int]] = []
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                radici.append((alias.name.split(".")[0], nodo.lineno))
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level and nodo.level > 0:
                continue  # `from .x import y` — intra-package, lecito
            if nodo.module:
                radici.append((nodo.module.split(".")[0], nodo.lineno))
    return radici


def test_contracts_ha_moduli() -> None:
    # Guardia: il test non deve passare a vuoto se la cartella sparisce.
    assert _moduli_contracts(), "nessun modulo trovato in src/contracts"


def test_F2_nessun_import_vietato() -> None:
    offese: list[str] = []
    for py in _moduli_contracts():
        albero = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for radice, linea in _radici_importate(albero):
            if radice in _RADICI_VIETATE:
                offese.append(f"{py.relative_to(_REPO)}:{linea}: import vietato '{radice}'")
    assert not offese, "import vietati in contracts:\n" + "\n".join(offese)


def test_F2_solo_stdlib_e_pydantic() -> None:
    stdlib = set(sys.stdlib_module_names)
    inattesi: list[str] = []
    for py in _moduli_contracts():
        albero = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for radice, linea in _radici_importate(albero):
            if radice in _RADICI_PERMESSE_EXTRA or radice in stdlib:
                continue
            inattesi.append(
                f"{py.relative_to(_REPO)}:{linea}: import non-stdlib/non-pydantic '{radice}'"
            )
    assert not inattesi, (
        "contracts deve importare solo stdlib + Pydantic:\n" + "\n".join(inattesi)
    )
