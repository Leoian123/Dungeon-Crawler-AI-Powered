"""I/O su disco: scrittura atomica, compressione del solo sidecar, header-only
(H §3, §5, §10; H-9, H-14, H-22).

Tre garanzie fisiche:
  - **Scrittura atomica** (§10.1, H-14): temp + `fsync` + `rename` atomico. Sotto
    permadeath il file di stato non dev'essere **mai** mezzo-scritto.
  - **Stato in chiaro, sidecar compresso** (§3, §8; H-9): lo stato è minuscolo e lo si
    vuole ispezionabile; il testo che cresce vive nell'Archivio, schiacciato con gzip.
  - **Header leggibile da solo** (§5, H-22): il file di stato è due righe — riga 1
    l'intestazione di elenco, riga 2 il corpo. Lo scan del menu legge **solo la riga 1**
    (no deep-parse); un'intestazione illeggibile non fa crashare lo scan.

Formato dello stato (JSON-family, leggibile): due documenti JSON, uno per riga. Niente
pickle/marshal (H-1): solo `json` (stato) e `gzip` di `json` (sidecar).
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
from pathlib import Path

SUFFISSO_STATO = ".stato.json"
SUFFISSO_ARCHIVIO = ".archivio.gz"
SUFFISSO_BACKUP_STATO = ".bak.stato.json"
SUFFISSO_BACKUP_ARCHIVIO = ".bak.archivio.gz"
# Il TERZO artefatto (Wiki del Master, rev. 3 §3.1): la slice congelata.
# Compresso (offuscamento dichiarato, non cifratura), contratto VITALE:
# la laschezza del sidecar NON si applica — vedi salvataggio.carica_wiki_slice.
SUFFISSO_WIKI = ".wiki.gz"
SUFFISSO_BACKUP_WIKI = ".bak.wiki.gz"


class StatoCorrotto(Exception):
    """Il file di stato non è leggibile/parsabile (header o corpo)."""


def _scrivi_atomico(path: Path, dati: bytes) -> None:
    """temp + fsync + rename atomico (H-14). La proprietà tutto-o-niente per file la
    ridà il rename del filesystem; il temp è nella stessa cartella (stesso device)."""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(dati)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)  # atomico su POSIX e Windows


# --- Path helper --------------------------------------------------------------

def path_stato(directory: Path, uuid: str) -> Path:
    return directory / f"{uuid}{SUFFISSO_STATO}"


def path_archivio(directory: Path, uuid: str) -> Path:
    return directory / f"{uuid}{SUFFISSO_ARCHIVIO}"


def path_wiki(directory: Path, uuid: str) -> Path:
    return directory / f"{uuid}{SUFFISSO_WIKI}"


# --- Stato: due righe JSON in chiaro ------------------------------------------

def scrivi_stato(path: Path, intestazione: dict, corpo: dict) -> None:
    """Scrive lo stato in chiaro: riga 1 = intestazione, riga 2 = corpo (atomico)."""
    riga_header = json.dumps(intestazione, ensure_ascii=False)
    riga_corpo = json.dumps(corpo, ensure_ascii=False)
    blob = (riga_header + "\n" + riga_corpo + "\n").encode("utf-8")
    _scrivi_atomico(path, blob)


def leggi_intestazione(path: Path) -> dict:
    """Legge SOLO la prima riga (header di elenco) — niente deep-parse (H-22)."""
    with open(path, encoding="utf-8") as f:
        prima_riga = f.readline()
    if not prima_riga.strip():
        raise StatoCorrotto(f"intestazione vuota: {path.name}")
    try:
        return json.loads(prima_riga)
    except json.JSONDecodeError as e:
        raise StatoCorrotto(f"intestazione illeggibile: {path.name}") from e


def leggi_stato(path: Path) -> tuple[dict, dict]:
    """Legge (intestazione, corpo). Solleva `StatoCorrotto` su file mancante,
    troncato o JSON malformato — il chiamante (contratto di load) degrada con grazia."""
    try:
        with open(path, encoding="utf-8") as f:
            righe = f.read().split("\n")
    except OSError as e:
        raise StatoCorrotto(f"file di stato non leggibile: {path}") from e
    if len(righe) < 2 or not righe[0].strip() or not righe[1].strip():
        raise StatoCorrotto(f"file di stato troncato: {path.name}")
    try:
        return json.loads(righe[0]), json.loads(righe[1])
    except json.JSONDecodeError as e:
        raise StatoCorrotto(f"stato JSON malformato: {path.name}") from e


# --- Archivio: JSON compresso gzip --------------------------------------------

def scrivi_archivio(path: Path, archivio: dict) -> None:
    """Scrive il sidecar COMPRESSO (gzip di JSON), atomico (H-9, H-14)."""
    blob = gzip.compress(json.dumps(archivio, ensure_ascii=False).encode("utf-8"))
    _scrivi_atomico(path, blob)


def leggi_archivio(path: Path) -> dict:
    """Legge e decomprime il sidecar."""
    with open(path, "rb") as f:
        crudo = f.read()
    return json.loads(gzip.decompress(crudo).decode("utf-8"))


# --- Backup di sola recovery: la coppia coerente stato + sidecar (§10.3) -------

def backup_coppia(directory: Path, uuid: str) -> None:
    """Copia l'ultima coppia buona (stato + sidecar) nei nomi di backup, **insieme**
    (§10.2/§10.3). È recovery-da-corruzione, non ripristino a comando: nessuna API la
    riporta in gioco. Si esegue PRIMA di sovrascrivere il save vivo."""
    ps, pa = path_stato(directory, uuid), path_archivio(directory, uuid)
    if ps.exists() and pa.exists():
        shutil.copy2(ps, directory / f"{uuid}{SUFFISSO_BACKUP_STATO}")
        shutil.copy2(pa, directory / f"{uuid}{SUFFISSO_BACKUP_ARCHIVIO}")
        # La TERNA (Wiki del Master, rev. 3 §3.1 — stress-test 2026-08-18):
        # la slice si copia INSIEME (backup coerente = stesso istante).
        # Stessa semantica della coppia: protezione da corruzione, mai
        # auto-ripristino — il contratto vitale resta un rifiuto dichiarato.
        pw = path_wiki(directory, uuid)
        if pw.exists():
            shutil.copy2(pw, directory / f"{uuid}{SUFFISSO_BACKUP_WIKI}")
