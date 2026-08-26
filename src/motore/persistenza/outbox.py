"""L'OUTBOX delle proposte wiki — artefatto PROPRIO, fuori dalla coppia save.

Rev. 3 §4-bis: il sidecar muore col permadeath (`invalida` fa unlink), e le
proposte devono sopravvivere alla morte del crawler — è il loro scopo.
Quindi vivono in `<uuid>.proposte.jsonl` accanto ai salvataggi, con ciclo
di vita INDIPENDENTE: `invalida` non lo tocca; lo rimuove solo la pulizia
esplicita dell'hub (`elimina_crawler` — scelta del giocatore, non un
terminale).

Scrittura: append-only, dedup per id (gli id sono deterministici: il
save-scumming ri-propone lo stesso fatto con lo stesso id, e la riga non
si duplica). Lettura/consumo: del cruscotto (W2) — `consuma` fa
move-on-read per non rileggere mai due volte.
"""

from __future__ import annotations

import json
import time
from pathlib import Path


def path_outbox(directory: Path, uuid: str) -> Path:
    return Path(directory) / f"{uuid}.proposte.jsonl"


def _id_presenti(percorso: Path) -> set[str]:
    if not percorso.exists():
        return set()
    presenti = set()
    with percorso.open(encoding="utf-8") as f:
        for riga in f:
            try:
                presenti.add(json.loads(riga).get("id", ""))
            except Exception:
                continue  # riga corrotta: non blocca l'append (lasco)
    return presenti


def scrivi_proposte(
    directory: Path, uuid: str, proposte: list[dict]
) -> int:
    """Append con dedup per id. Ritorna quante righe NUOVE ha scritto.
    Il timestamp è dell'host (qui, alla scrittura): il motore non guarda
    mai l'orologio."""
    if not proposte:
        return 0
    percorso = path_outbox(directory, uuid)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    presenti = _id_presenti(percorso)
    nuove = 0
    with percorso.open("a", encoding="utf-8") as f:
        for proposta in proposte:
            if proposta.get("id") in presenti:
                continue
            riga = dict(proposta)
            riga.setdefault("uuid_run", uuid)
            riga.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
            f.write(json.dumps(riga, ensure_ascii=False) + "\n")
            presenti.add(proposta.get("id"))
            nuove += 1
    return nuove


def leggi_proposte(directory: Path, uuid: str) -> list[dict]:
    """Lettura pura (per il cruscotto e i test)."""
    percorso = path_outbox(directory, uuid)
    if not percorso.exists():
        return []
    proposte = []
    with percorso.open(encoding="utf-8") as f:
        for riga in f:
            try:
                proposte.append(json.loads(riga))
            except Exception:
                continue
    return proposte


def consuma_proposta(directory: Path, uuid: str, id_proposta: str) -> dict | None:
    """Consumo PUNTUALE (cruscotto W2): estrae UNA proposta per id riscrivendo
    il file senza quella riga. L'outbox è una CODA, non un registro: il
    consumo parziale è la stessa semantica del move-on-read, a grana fine —
    l'admin decide proposta per proposta, le altre restano in coda. `None`
    se assente; righe corrotte preservate com'erano (lasco)."""
    percorso = path_outbox(directory, uuid)
    if not percorso.exists():
        return None
    restanti: list[str] = []
    trovata: dict | None = None
    with percorso.open(encoding="utf-8") as f:
        for riga in f:
            try:
                dato = json.loads(riga)
            except Exception:
                restanti.append(riga.rstrip("\n"))
                continue
            if trovata is None and dato.get("id") == id_proposta:
                trovata = dato
            else:
                restanti.append(json.dumps(dato, ensure_ascii=False))
    if trovata is None:
        return None
    if restanti:
        percorso.write_text("\n".join(restanti) + "\n", encoding="utf-8")
    else:
        percorso.unlink()
    return trovata


def consuma_proposte(directory: Path, uuid: str) -> list[dict]:
    """Move-on-read: rinomina il file e ritorna il contenuto — il cruscotto
    non rilegge mai due volte, e la run (se ancora viva) riparte da vuoto."""
    percorso = path_outbox(directory, uuid)
    if not percorso.exists():
        return []
    consumato = percorso.with_suffix(".consumate.jsonl")
    percorso.replace(consumato)
    proposte = []
    with consumato.open(encoding="utf-8") as f:
        for riga in f:
            try:
                proposte.append(json.loads(riga))
            except Exception:
                continue
    return proposte
