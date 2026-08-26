"""Lucchetti di SINCRONIA sulle copie note (registro §4.2-B).

Le duplicazioni qui sotto «reggono solo finché classe e blocco coincidono» e
«divergeranno al primo ritocco»: questi test le legano, così la divergenza è un
rosso e non un bug diegetico silenzioso (l'evento che nomina uno status che la
tabella dei participi non conosce, la cronaca che chiama «veleno» ciò che il
save tagga «blocco.veleno»).

La copia del nome diegetico è stata UNIFICATA (`mob.nome_diegetico`, 2026-08-16):
qui resta il lucchetto statico che impedisce alle due vecchie sedi di rifarsi
una copia locale.
"""

from __future__ import annotations

from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"


def test_le_tre_convenzioni_di_nome_status_coincidono() -> None:
    """`nome_status()` (chiave §11/save) ≡ `cls.__name__.lower()` (eventi di bus)
    per OGNI riga di `SPEC_STATUS`: gli eventi `StatusApplicato`/`EffettoStatus`
    usano la seconda convenzione, le foglie di calibrazione la prima. Se uno
    status nascesse con classe `VelenoNero` e blocco `veleno_nero`… reggerebbe;
    con blocco `veleno-nero` no — e QUI si vedrebbe."""
    from motore.status import SPEC_STATUS, nome_status

    for spec in SPEC_STATUS:
        assert nome_status(spec.componente) == spec.componente.__name__.lower(), (
            f"{spec.componente.__name__}: il nome-dato ({nome_status(spec.componente)!r}) "
            f"diverge dalla convenzione degli eventi ({spec.componente.__name__.lower()!r})"
        )


def test_ogni_status_del_motore_ha_il_suo_participio() -> None:
    """La tabella dei participi in `main` è l'ultima voce della catena: uno status
    nuovo senza participio arriverebbe a video come «Sei veleno_nero!» — funziona,
    ma rompe la finzione. La tabella deve coprire OGNI status con sistema."""
    from main import _participio_status
    from motore.status import SPEC_STATUS, nome_status

    for spec in SPEC_STATUS:
        if not spec.con_sistema:
            continue
        nome = nome_status(spec.componente)
        participio = _participio_status(nome)
        assert participio != nome or nome == "stordito", (
            f"lo status {nome!r} non ha un participio dedicato in main._participio_status: "
            f"a video uscirebbe «Sei {nome}!»"
        )


def test_il_nome_diegetico_non_si_riduplica() -> None:
    """La copia unica è `mob.nome_diegetico`: se `combattimento` o `status`
    tornano a leggere `EntitaMob.nome` in proprio per gli eventi di vista, le
    due voci divergeranno al primo titolo/prefisso aggiunto. Il segno della
    ricopia è `em.nome` (la risoluzione del NOME): leggere `EntitaMob` per
    grado/lore resta legittimo."""
    for modulo in ("combattimento.py", "status.py"):
        testo = (_SRC / "motore" / modulo).read_text(encoding="utf-8")
        assert "em.nome" not in testo and "return em.nome" not in testo, (
            f"motore/{modulo} risolve di nuovo il nome diegetico in proprio: "
            "delega a mob.nome_diegetico (copia unica)"
        )


def test_gli_hp_hanno_un_solo_proprietario_di_mutazione() -> None:
    """La mutazione HP vive SOLO in `salute.muovi_hp`: una scrittura diretta di
    `punti_vita`/`attuali` fuori da salute (e dai due punti dichiarati: il tetto
    del load in `derivate.clampa_hp`, l'inizializzazione) è una copia che
    divergerà sul clamp. Erano cinque; il registro ne contava quattro."""
    import re

    consentiti = {"salute.py", "derivate.py"}
    for percorso in sorted((_SRC / "motore").glob("*.py")):
        if percorso.name in consentiti:
            continue
        testo = percorso.read_text(encoding="utf-8")
        scritture = [
            r.strip() for r in testo.splitlines()
            if re.search(r"\.(punti_vita|attuali)\s*(=|\+=|-=)[^=]", r)
            and "attuali=" not in r.replace(" ", "")  # costruttori: PuntiVita(attuali=…)
        ]
        assert not scritture, (
            f"motore/{percorso.name} muta gli HP in proprio invece di passare da "
            f"salute.muovi_hp: {scritture}"
        )
