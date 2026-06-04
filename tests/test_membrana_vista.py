"""Membrana motore ⇄ host — verifiche STATICHE del seam **headless** (C-2a, C-5).

Il game engine è indipendente dalla presentazione: nessun layer importa Textual e
Textual non è più una dipendenza del progetto. Sono pure ispezioni del sorgente: girano
senza alcuna libreria di UI installata (è proprio questo il punto del seam headless, C-5).
Una UI futura (web, Electron, TUI…) si innesterà via `contracts` + le porte di
`SessioneGioco`, senza che il motore la conosca.
"""

from __future__ import annotations

import ast
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
        for py in sorted((_SRC / layer).rglob("*.py")):
            if _radici_import(py) & _UI_BANDITE:
                offese.append(str(py.relative_to(_SRC)))
    assert not offese, "UI importata in un layer headless (C-2a):\n" + "\n".join(offese)


# Host/tool OPT-IN che possono importare una UI (fuori dal motore, host-agnostico): non
# fanno parte del game engine headless. Oggi solo la console admin di calibrazione, che
# importa Textual **lazy** (la sua CLI gira senza). Il motore resta coperto da C-2a.
_HOST_OPZIONALI = {"calibratore.py"}


# --- C-5: l'INTERO game engine regge senza alcuna libreria di UI -----------------

def test_C5_intero_src_indipendente_da_ui() -> None:
    # Nessun modulo del game engine importa una libreria di UI: il contratto è l'unico
    # canale verso un host, per costruzione. L'arnia headless gira senza Textual. Gli
    # host/tool opt-in (`_HOST_OPZIONALI`) sono esclusi: sono presentazione/strumenti che
    # vivono *fuori* dal motore (coperto da C-2a), con import di UI lazy.
    offese: list[str] = []
    for py in sorted(_SRC.rglob("*.py")):
        if py.name in _HOST_OPZIONALI:
            continue
        if _radici_import(py) & _UI_BANDITE:
            offese.append(str(py.relative_to(_SRC)))
    assert not offese, "una libreria di UI è importata sotto src/ (C-5):\n" + "\n".join(offese)
