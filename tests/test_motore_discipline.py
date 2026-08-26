"""Discipline statiche del motore (verifiche del prompt di fase):

  - nessun check di fase a mano FUORI da `PhasedProcessor` (la lettura-per-gate
    `leggi_fase()` appare solo in fase.py [def] e phased.py [uso]);
  - la coda è drenata da un Processor sul turno, NON da un timer: nessun
    `threading`/`asyncio`/`sleep`/`Timer` nel motore (C-8, FNC §6.4 / §7);
  - il motore non importa Textual (C-2a).
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_MOTORE = _REPO / "src" / "motore"


def _moduli() -> list[Path]:
    return sorted(_MOTORE.rglob("*.py"))


def test_ci_sono_moduli_motore() -> None:
    assert _moduli(), "nessun modulo in src/motore"


def test_leggi_fase_solo_nella_base_phased() -> None:
    """`leggi_fase(` (lettura-per-gate) solo dove è lecito: definizione in fase.py,
    uso nel gate di phased.py. Altrove = check di fase a mano → vietato (FNC §6.1)."""
    consentiti = {"fase.py", "phased.py"}
    offese: list[str] = []
    for py in _moduli():
        for num, riga in enumerate(py.read_text(encoding="utf-8").splitlines(), start=1):
            if "leggi_fase(" in riga and py.name not in consentiti:
                offese.append(f"{py.relative_to(_REPO)}:{num}: {riga.strip()}")
    assert not offese, (
        "check di fase a mano fuori da PhasedProcessor:\n" + "\n".join(offese)
    )


def _radici_importate(albero: ast.AST) -> set[str]:
    radici: set[str] = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                radici.add(alias.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom):
            if not nodo.level and nodo.module:
                radici.add(nodo.module.split(".")[0])
    return radici


def test_motore_non_importa_textual_ne_thread_ne_timer() -> None:
    vietati = {"textual", "threading", "asyncio"}
    # ECCEZIONE DOCUMENTATA: `gm.py` è la coroutine di ORCHESTRAZIONE del fan-out
    # (G §9.2-9.3: "una sola unità async cancellabile", le N chiamate dentro un solo
    # await) — `asyncio.gather` è composizione di chiamate, non un orologio. Il
    # divieto vero (niente avanzamento a tempo di parete) resta coperto per TUTTI i
    # moduli, gm.py incluso, da `test_nessun_timer_a_tempo_di_parete`.
    esenzioni_asyncio = {"gm.py"}
    offese: list[str] = []
    for py in _moduli():
        radici = _radici_importate(ast.parse(py.read_text(encoding="utf-8")))
        for v in vietati & radici:
            if v == "asyncio" and py.name in esenzioni_asyncio:
                continue
            offese.append(f"{py.relative_to(_REPO)}: import vietato '{v}'")
    assert not offese, (
        "il motore non usa Textual/thread/async-clock (C-2a, C-8, FNC §6.4/§7):\n"
        + "\n".join(offese)
    )


def test_motore_non_importa_provider() -> None:
    """Il motore riceve i provider PER INIEZIONE (membrana C-2): nessun modulo
    sotto `motore/` — sottopacchetti inclusi — importa la radice `provider`.
    Controllo sugli import REALI (AST), non sulle stringhe (review 2026-08-08):
    posato insieme a `provider/root.py`, perché il composition root che ora vive
    nel pacchetto provider non venga mai risucchiato nel motore."""
    moduli = _moduli()
    assert moduli, "glob vuoto: il lint passerebbe per vacuità"
    offese: list[str] = []
    for py in moduli:
        radici = _radici_importate(ast.parse(py.read_text(encoding="utf-8")))
        if "provider" in radici:
            offese.append(f"{py.relative_to(_REPO)}: import della radice 'provider'")
    assert not offese, (
        "il motore non importa provider (iniezione, mai import):\n" + "\n".join(offese)
    )


def test_nessun_timer_a_tempo_di_parete() -> None:
    """Nessun avanzamento sul tempo di parete: niente `sleep(`/`Timer`/`time.time(`
    nel motore (l'avanzamento è guidato dal turno, FNC §6.4)."""
    spie = ("sleep(", "Timer", "time.time(", "perf_counter(", "monotonic(")
    offese: list[str] = []
    for py in _moduli():
        for num, riga in enumerate(py.read_text(encoding="utf-8").splitlines(), start=1):
            for spia in spie:
                if spia in riga:
                    offese.append(f"{py.relative_to(_REPO)}:{num}: {riga.strip()}")
    assert not offese, "tracce di avanzamento sul tempo di parete:\n" + "\n".join(offese)
