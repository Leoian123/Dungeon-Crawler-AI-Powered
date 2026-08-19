"""Il LEDGER degli esiti di run — il deposito dello strato sovra-run (Fase A).

Un solo file `esiti.jsonl` accanto ai salvataggi, append-only, CROSS-run: è la
storia delle run concluse, non un artefatto della coppia save. `invalida` non
lo tocca — come l'outbox wiki (rev. 3 §4-bis), l'esito nasce ESATTAMENTE
quando il permadeath distrugge tutto il resto: sopravvivere al terminale è il
suo scopo. Dedup per `id` deterministico (la `chiave()` dell'`EsitoRun`): un
doppio onore del terminale riscrive la stessa riga, mai due.

Scrittura BEST-EFFORT dal chiamante (F-W4): un ledger inscrivibile non deve
mai rompere il ritiro dello slot. Lettura tollerante (righe corrotte saltate):
il consumatore futuro è la bacheca (Fase B), che legge e basta — un ledger non
si consuma, quindi NESSUN move-on-read (a differenza dell'outbox).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

NOME_LEDGER = "esiti.jsonl"


def path_esiti(directory: Path) -> Path:
    return Path(directory) / NOME_LEDGER


def _id_presenti(percorso: Path) -> set[str]:
    if not percorso.exists():
        return set()
    presenti = set()
    with percorso.open(encoding="utf-8", errors="replace") as f:
        for riga in f:
            try:
                presenti.add(json.loads(riga).get("id", ""))
            except Exception:
                continue  # riga corrotta: non blocca l'append (lasco)
    return presenti


def scrivi_esito(directory: Path, esito: dict) -> bool:
    """Append con dedup per id. Il timestamp è dell'host (qui, alla
    scrittura): il motore non guarda mai l'orologio. Ritorna True se la
    riga è NUOVA."""
    percorso = path_esiti(directory)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    if esito.get("id") in _id_presenti(percorso):
        return False
    riga = dict(esito)
    if not riga.get("ts"):  # il DTO nasce con ts="" (il motore non ha orologio)
        riga["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with percorso.open("a", encoding="utf-8") as f:
        f.write(json.dumps(riga, ensure_ascii=False) + "\n")
    return True


def leggi_esiti(directory: Path) -> list[dict]:
    """Tutti gli esiti depositati, in ordine di scrittura. Tollerante FINO IN
    FONDO (avversariale 2026-08-19): una riga corrotta si salta, byte non-UTF-8
    diventano riga invalida (errors="replace" → json la scarta), e un ledger
    INAPRIBILE (directory al suo posto, lock, ACL) è una storia vuota — la
    bacheca dell'host non deve MAI andare giù per un file sabotato."""
    percorso = path_esiti(directory)
    esiti = []
    try:
        with percorso.open(encoding="utf-8", errors="replace") as f:
            for riga in f:
                try:
                    dato = json.loads(riga)
                except Exception:
                    continue
                if isinstance(dato, dict):
                    esiti.append(dato)
    except OSError:
        return []
    return esiti
