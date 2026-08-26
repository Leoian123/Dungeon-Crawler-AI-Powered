"""Invarianti trasversali del cruscotto (le linee MAI/SEMPRE) — verifiche consolidate.

Molti invarianti hanno già un test dedicato (F-/G-/E-/H-/J-/C-): qui si raccolgono le
linee rosse **grep-abili** del `progetto-indice-decisioni.md` che non avevano ancora un
punto d'asserzione esplicito, così la rassegna è auditabile in un solo posto.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src"


def _moduli(*sottocartelle: str) -> list[Path]:
    if not sottocartelle:
        out = sorted(_SRC.rglob("*.py"))
    else:
        out = []
        for s in sottocartelle:
            out += sorted((_SRC / s).rglob("*.py"))
    # Guardia di non-vuotezza: se un path cambia (è già successo con la rimozione
    # di src/adattatore) il divieto passerebbe per vacuità (audit 2026-08-07).
    assert out, f"nessun modulo trovato per {sottocartelle or ('src',)}"
    return out


# NB: il divieto dell'idioma `World()` di esper (ESP §0) è già coperto — con più
# rigore, su src/ e tests/ — da `test_vendor_esper.py`; qui non si duplica.


# --- "Bus tipizzato di progetto, MAI il dispatcher nativo esper" (ESP §5) ------

def test_dispatcher_nativo_esper_non_usato() -> None:
    # AST: nessuna *chiamata* a dispatch_event/set_handler/remove_handler (la docstring
    # di bus.py li NOMINA per spiegare che non li usa — conta l'uso reale).
    vietati = {"dispatch_event", "set_handler", "remove_handler"}
    for py in _moduli():
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for nodo in ast.walk(tree):
            if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
                assert nodo.func.attr not in vietati, f"{py.relative_to(_SRC)}: usa il dispatcher nativo esper"


# --- "La chiave LLM non finisce MAI in URL, log, codice o documenti" (PLK §4) --

def test_nessuna_chiave_llm_cablata() -> None:
    for py in _moduli():
        src = py.read_text(encoding="utf-8")
        assert "sk-ant" not in src, f"{py.relative_to(_SRC)}: chiave Anthropic cablata!"
        # Nessun assegnamento di una key a stringa letterale.
        for nodo in ast.walk(ast.parse(src)):
            if isinstance(nodo, ast.Assign):
                for t in nodo.targets:
                    nome = getattr(t, "id", "") or getattr(t, "attr", "")
                    if "api_key" in nome.lower() or nome.lower().endswith("key"):
                        assert not isinstance(nodo.value, ast.Constant) or nodo.value.value in (None, ""), (
                            f"{py.relative_to(_SRC)}: key assegnata a un letterale"
                        )


# --- "async sì, thread no" (FNC §7) — niente thread in TUTTO src ---------------

def test_async_si_thread_no() -> None:
    for py in _moduli():
        radici = set()
        for nodo in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Import):
                radici |= {a.name.split(".")[0] for a in nodo.names}
            elif isinstance(nodo, ast.ImportFrom) and not nodo.level and nodo.module:
                radici.add(nodo.module.split(".")[0])
        assert "threading" not in radici, f"{py.relative_to(_SRC)}: importa threading (vietato)"
        assert "_thread" not in radici, f"{py.relative_to(_SRC)}: importa _thread (vietato)"


# --- "switch_world SOLO al confine guscio↔run" (E-2) — uso reale -------------

def test_switch_world_solo_nel_livello_save_load() -> None:
    autorita = _SRC / "motore" / "persistenza" / "salvataggio.py"
    for py in _moduli():
        usate = set()
        for nodo in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Attribute) and nodo.attr in ("switch_world", "delete_world"):
                usate.add(nodo.attr)
        if usate:
            assert py == autorita, f"{py.relative_to(_SRC)}: usa {usate} fuori dal livello save/load"


# --- "Il motore non importa Textual; la membrana è a tenuta" (C-2a) ----------

def test_motore_e_contracts_non_importano_textual() -> None:
    for py in _moduli("motore", "contracts", "guscio", "provider"):
        for nodo in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Import):
                assert all(a.name.split(".")[0] != "textual" for a in nodo.names), py.name
            elif isinstance(nodo, ast.ImportFrom) and not nodo.level and nodo.module:
                assert nodo.module.split(".")[0] != "textual", py.name


# --- "Permadeath: terminale di run = MortePersonaggio, non sconfitta" (G-11) ---

def test_terminale_di_run_e_mortepersonaggio() -> None:
    # Il death-check emette MortePersonaggio; nessun percorso emette
    # "CombatResolved(sconfitta)" come terminale (morte ≠ sconfitta).
    combat = (_SRC / "motore" / "combattimento.py").read_text(encoding="utf-8")
    assert "MortePersonaggio(" in combat
    # La sconfitta non è cablata come evento terminale separato.
    assert "sconfitta=True" not in combat and "Sconfitta(" not in combat


# --- "stdlib + Pydantic soltanto in contracts" già in F-2; qui un sanity ------

def test_contracts_dependency_free_dai_layer() -> None:
    stdlib = set(sys.stdlib_module_names) | {"pydantic", "__future__"}
    for py in _moduli("contracts"):
        for nodo in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.ImportFrom) and not nodo.level and nodo.module:
                radice = nodo.module.split(".")[0]
                assert radice in stdlib, f"{py.name}: import di layer '{radice}' in contracts"
