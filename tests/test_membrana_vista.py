"""Membrana motore ⇄ host — verifiche STATICHE del seam **headless** (C-2a, C-5).

Il game engine è indipendente dalla presentazione: nessun layer importa Textual e
Textual non è più una dipendenza del progetto. Sono pure ispezioni del sorgente: girano
senza alcuna libreria di UI installata (è proprio questo il punto del seam headless, C-5).
Una UI futura (web, Electron, TUI…) si innesterà via `contracts` + le porte di
`SessioneGioco`, senza che il motore la conosca.
"""

from __future__ import annotations

import ast

import pytest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src"

# Le librerie di UI bandite da TUTTO `src/` (il motore è host-agnostico).
_UI_BANDITE = {"textual"}


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


# --- L'adattatore Textual è stato rimosso: il game engine torna headless --------

def test_nessun_pacchetto_adattatore() -> None:
    assert not (_SRC / "adattatore").exists(), "src/adattatore deve essere rimosso (headless)"


def test_textual_non_e_una_dipendenza() -> None:
    for nome in ("requirements.txt", "requirements.lock", "pyproject.toml"):
        testo = (_REPO / nome).read_text(encoding="utf-8")
        for riga in testo.splitlines():
            r = riga.strip()
            assert not (r.startswith("textual") and not r.startswith("#")), f"{nome}: {r}"


# --- C-2a: il motore (e contracts/guscio/provider) NON importano una UI ---------

def test_C2a_layer_headless_non_importano_ui() -> None:
    offese: list[str] = []
    for layer in ("motore", "contracts", "guscio", "provider"):
        file = sorted((_SRC / layer).rglob("*.py"))
        assert file, f"{layer}/ vuoto o spostato: il divieto passerebbe per vacuità"
        for py in file:
            if _radici_import(py) & _UI_BANDITE:
                offese.append(str(py.relative_to(_SRC)))
    assert not offese, "UI importata in un layer headless (C-2a):\n" + "\n".join(offese)


# Host/tool OPT-IN che possono importare una UI (fuori dal motore, host-agnostico): non
# fanno parte del game engine headless. La UI di gioco (`gioco_textual.py`) importa
# Textual **lazy** e pilota il motore solo via le porte/`contracts`. Il motore resta
# coperto da C-2a. (La console TUI di calibrazione è stata RITIRATA su questo branch:
# la superficie admin è la pagina Calibrazione del GM mode nella SPA.)
_HOST_OPZIONALI = {"gioco_textual.py"}


# --- Host web (src/host_web): parla al motore SOLO via le porte -------------------
#
# Il layer HTTP è un host opt-in come la TUI: importa `main` (composition root),
# `contracts` e — lazy, come `gioco_textual` — `provider`. MAI `motore`, MAI esper,
# MAI `guscio`: la membrana resta a tenuta anche sul lato web (C-2a/C-2b).
# NB: `_radici_import` cammina l'intero AST, quindi vede anche gli import lazy —
# il divieto qui sotto copre ogni livello, non solo il module-level.

_VIETATE_ALL_HOST_WEB = {"motore", "esper", "guscio"} | _UI_BANDITE


def test_host_web_importa_solo_porte() -> None:
    file = sorted((_SRC / "host_web").rglob("*.py"))
    if not file:
        # Su questo branch host_web NON è travasato (STATO §3): il test esiste per il
        # giorno in cui arriverà. Skip ESPLICITO, mai un verde per vacuità che
        # racconterebbe una copertura inesistente (audit 2026-08-07).
        pytest.skip("src/host_web assente su questo branch: nessun file da vincolare")
    offese: list[str] = []
    for py in file:
        colpite = _radici_import(py) & _VIETATE_ALL_HOST_WEB
        if colpite:
            offese.append(f"{py.relative_to(_SRC)}: {sorted(colpite)}")
    assert not offese, "host_web scavalca la membrana (C-2a):\n" + "\n".join(offese)


# Speculare a C-2a: il framework web non trapela nel game engine (né in `main`,
# che è colla headless — il server appartiene SOLO allo strato host).
_WEB_BANDITE = {"fastapi", "starlette", "uvicorn"}


def test_web_framework_non_trapela_nel_motore() -> None:
    offese: list[str] = []
    bersagli = [
        py
        for layer in ("motore", "contracts", "guscio", "provider")
        for py in sorted((_SRC / layer).rglob("*.py"))
    ] + [_SRC / "main.py", _SRC / "gioco_textual.py"]
    assert len(bersagli) > 2, "layer vuoti o spostati: il divieto passerebbe per vacuità"
    for py in bersagli:
        colpite = _radici_import(py) & _WEB_BANDITE
        if colpite:
            offese.append(f"{py.relative_to(_SRC)}: {sorted(colpite)}")
    assert not offese, "framework web fuori dallo strato host:\n" + "\n".join(offese)


# --- C-5: l'INTERO game engine regge senza alcuna libreria di UI -----------------

def test_C5_intero_src_indipendente_da_ui() -> None:
    # Nessun modulo del game engine importa una libreria di UI: il contratto è l'unico
    # canale verso un host, per costruzione. L'arnia headless gira senza Textual. Gli
    # host/tool opt-in (`_HOST_OPZIONALI`) sono esclusi: sono presentazione/strumenti che
    # vivono *fuori* dal motore (coperto da C-2a), con import di UI lazy.
    file = sorted(_SRC.rglob("*.py"))
    assert file, "src/ vuoto o spostato: il divieto passerebbe per vacuità"
    offese: list[str] = []
    for py in file:
        if py.name in _HOST_OPZIONALI:
            continue
        if _radici_import(py) & _UI_BANDITE:
            offese.append(str(py.relative_to(_SRC)))
    assert not offese, "una libreria di UI è importata sotto src/ (C-5):\n" + "\n".join(offese)
