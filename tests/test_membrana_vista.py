"""Membrana motore ⇄ vista — verifiche STATICHE (C-1, C-2a, C-2b, C-5, C-7-statico).

Sono pure ispezioni del sorgente: girano **anche senza Textual installato** (sono parte
della prova del seam headless, C-5). Le prove comportamentali dell'adattatore (Pilot)
vivono in `test_adattatore.py` e si saltano se Textual manca.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src"


def _radici_import(py: Path) -> set[str]:
    radici: set[str] = set()
    for nodo in ast.walk(ast.parse(py.read_text(encoding="utf-8"), filename=str(py))):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                radici.add(alias.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom):
            if not nodo.level and nodo.module:  # assoluti (i relativi sono intra-package)
                radici.add(nodo.module.split(".")[0])
    return radici


# --- C-1: textual pinnato esatto + chiusura transitiva congelata --------------

def test_C1_textual_pinnato_esatto() -> None:
    req = (_REPO / "requirements.txt").read_text(encoding="utf-8")
    # Pin esatto, niente range aperti (mai >=, ~=, *).
    assert "textual==8.2.7" in req
    for riga in req.splitlines():
        r = riga.strip()
        if r.startswith("textual") and not r.startswith("#"):
            assert "==" in r and ">=" not in r and "~=" not in r, r


def test_C1_lockfile_congela_la_chiusura_transitiva() -> None:
    lock = (_REPO / "requirements.lock").read_text(encoding="utf-8")
    # Non più un placeholder: la chiusura di Textual è pinnata esatta.
    assert "DA CONGELARE" not in lock and "PLACEHOLDER" not in lock
    for pkg in ("textual==8.2.7", "rich==", "markdown-it-py==", "mdurl==",
                "linkify-it-py==", "mdit-py-plugins==", "uc-micro-py==", "platformdirs=="):
        assert pkg in lock, f"manca dal lockfile: {pkg}"


# --- C-2a: il motore (e contracts/guscio) NON importano Textual ---------------

def test_C2a_layer_headless_non_importano_textual() -> None:
    offese: list[str] = []
    for layer in ("motore", "contracts", "guscio", "provider"):
        for py in sorted((_SRC / layer).rglob("*.py")):
            if "textual" in _radici_import(py):
                offese.append(str(py.relative_to(_SRC)))
    assert not offese, "Textual importato in un layer headless (C-2a):\n" + "\n".join(offese)


# --- C-2b: l'adattatore importa SOLO contracts + Textual ----------------------

def test_C2b_adattatore_importa_solo_contracts_e_textual() -> None:
    import sys

    vietate = {"esper", "motore", "guscio", "provider"}
    consentite_extra = {"contracts", "textual", "rich"}  # rich è transitivo di textual
    stdlib = set(sys.stdlib_module_names)
    offese: list[str] = []
    for py in sorted((_SRC / "adattatore").glob("*.py")):
        for radice in _radici_import(py):
            if radice in vietate:
                offese.append(f"{py.name}: import vietato '{radice}'")
            elif radice not in consentite_extra and radice not in stdlib and radice != "__future__":
                offese.append(f"{py.name}: import inatteso '{radice}'")
    assert not offese, "l'adattatore deve importare solo contracts + Textual (C-2b):\n" + "\n".join(offese)


def test_C2b_adattatore_non_usa_world_ne_processor() -> None:
    # AST, non stringhe: il docstring NOMINA legittimamente esper/World/Processor per
    # documentare il divieto. Conta l'USO reale (nomi/attributi), non la prosa.
    for py in sorted((_SRC / "adattatore").glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for nodo in ast.walk(tree):
            if isinstance(nodo, ast.Name):
                assert nodo.id not in {"esper", "World", "Processor"}, f"{py.name}: usa {nodo.id}"
            if isinstance(nodo, ast.Attribute) and isinstance(nodo.value, ast.Name):
                assert nodo.value.id != "esper", f"{py.name}: accede a esper.{nodo.attr}"


# --- C-5: il seam headless regge senza Textual (i layer non lo importano) ------

def test_C5_arnia_headless_indipendente_da_textual() -> None:
    # Se i layer headless non importano Textual (C-2a), l'intera arnia (213 test) gira
    # senza di esso: il contratto È l'unico canale, per costruzione.
    for layer in ("motore", "contracts", "guscio", "provider"):
        for py in sorted((_SRC / layer).rglob("*.py")):
            assert "textual" not in _radici_import(py), f"{py.relative_to(_SRC)} importa textual"


# --- C-7 (statico): l'adattatore non chiama l'LLM né muta il World -------------

def test_C7_adattatore_non_chiama_llm() -> None:
    for py in sorted((_SRC / "adattatore").glob("*.py")):
        src = py.read_text(encoding="utf-8")
        assert "genera(" not in src, f"{py.name}: chiama il provider LLM"
        assert "provider" not in _radici_import(py), f"{py.name}: importa il provider"
