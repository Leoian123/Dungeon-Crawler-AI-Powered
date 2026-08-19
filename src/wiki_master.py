"""Wiki del Master — lo STORE host-side (W1, versione da sviluppo).

La verità nei FILE (rev. 3 §2, ratifica §11.0 pendente): le voci vivono
come record JSON per-slug nella directory della wiki, scritti SOLO da
queste API (validazione Pydantic, scrittura atomica tmp+replace, revisioni
append-only per disciplina). L'indice SQLite derivato arriva in W2: a 10³
voci lo scan diretto basta e avanza per il cruscotto di sviluppo.

Questo modulo importa SOLO contracts + stdlib (membrana C-2a: un domani la
SPA lo monta dietro FastAPI senza toccare il motore). Il motore non importa
MAI questo modulo: consuma la WikiSlice che il composition root gli
congela nel save (rev. 3 §4).

Qui vivono anche: l'ESTRAZIONE della slice (il choke-point di segretezza —
`admin` non esce mai da qui) e il REGISTRO delle estrazioni (rev. 3 §2.1.3:
il prerequisito dello scrub è sapere quali run hanno estratto cosa).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from contracts import (
    ApprovazioneVoce,
    ProvenienzaVoce,
    RevisioneVoce,
    SegretezzaVoce,
    VoceSlice,
    VoceWiki,
    WikiSlice,
)

DIRECTORY_WIKI = Path(os.environ.get("DCC_WIKI_DIR", "wiki"))
_REGISTRO_ESTRAZIONI = ".estrazioni.jsonl"


def _percorso(slug: str, directory: Path | None) -> Path:
    return (directory or DIRECTORY_WIKI) / f"{slug}.json"


def _scrivi_atomico(percorso: Path, dati: dict) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    tmp = percorso.with_suffix(".tmp")
    tmp.write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(percorso)


def carica_voce(slug: str, *, directory: Path | None = None) -> VoceWiki | None:
    """La voce dal master (`None` se assente o corrotta — scan lasco H-22:
    il cruscotto la mostrerà come invalida, mai un crash)."""
    percorso = _percorso(slug, directory)
    if not percorso.exists():
        return None
    try:
        voce = VoceWiki.model_validate(
            json.loads(percorso.read_text(encoding="utf-8"))
        )
    except Exception:
        return None
    if voce.slug != percorso.stem:
        # Avversariale 2026-08-18 (F-W5): un file copiato sotto un altro nome
        # dichiarava lo slug dell'originale — DOPPIONI di slug nella slice.
        # Il nome del file È l'identità: mismatch = voce invalida (lasco).
        return None
    return voce


# La cache dello scan, per FIRMA della cartella (mtime_ns+size — il pattern
# `_collezione` di main.py): a 10³ voci lo scan freddo costa secondi di
# Pydantic+I/O (playtest 2026-08-18, F-W3) e la creazione di una run non può
# pagarlo ogni volta. La firma invalida da sé a ogni scrittura (le API
# scrivono file: mtime cambia).
_CACHE_VOCI: dict[Path, tuple[tuple, list[VoceWiki]]] = {}


def _firma_cartella(base: Path) -> tuple:
    return tuple(sorted(
        (p.name, p.stat().st_mtime_ns, p.stat().st_size)
        for p in base.glob("*.json")
    ))


def elenca_voci(*, directory: Path | None = None) -> list[VoceWiki]:
    """Tutte le voci valide del master, ordinate per slug (deterministico).
    Scan con cache per firma: il primo passaggio paga, i successivi no."""
    base = (directory or DIRECTORY_WIKI).resolve()
    if not base.exists():
        return []
    firma = _firma_cartella(base)
    in_cache = _CACHE_VOCI.get(base)
    if in_cache is not None and in_cache[0] == firma:
        return list(in_cache[1])
    voci = []
    for percorso in sorted(base.glob("*.json")):
        voce = carica_voce(percorso.stem, directory=base)
        if voce is not None:
            voci.append(voce)
    _CACHE_VOCI[base] = (firma, voci)
    return list(voci)


def salva_voce(voce: VoceWiki, *, directory: Path | None = None) -> Path:
    """Scrive la voce (validata, atomica). Le API sono le SOLE scrittrici
    dichiarate: un edit a mano resta possibile sui file (rev. 3 §2 — è una
    libertà di chi se ne assume la responsabilità), ma append-only e gate
    valgono solo passando da qui."""
    percorso = _percorso(voce.slug, directory)
    _scrivi_atomico(percorso, voce.model_dump(mode="json"))
    return percorso


def aggiungi_revisione(
    slug: str,
    testo: str,
    *,
    provenienza: ProvenienzaVoce = ProvenienzaVoce.ADMIN,
    vincolo: dict | None = None,
    directory: Path | None = None,
) -> VoceWiki:
    """«La revisione corregge» (rev. 3 §3): append della revisione n+1,
    NON approvata (il gate strutturale: invisibile a indice e slice finché
    l'admin non promuove). Mai un UPDATE delle righe esistenti."""
    voce = carica_voce(slug, directory=directory)
    if voce is None:
        raise ValueError(f"voce inesistente: {slug}")
    n = voce.revisioni[-1].n + 1
    nuova = voce.model_copy(update={"revisioni": voce.revisioni + (
        RevisioneVoce(n=n, testo=testo, vincolo=vincolo, provenienza=provenienza,
                      ts=_ora()),
    )})
    salva_voce(nuova, directory=directory)
    return nuova


def approva(
    slug: str, revisione_n: int, *, autore: str = "admin",
    directory: Path | None = None,
) -> VoceWiki:
    """La promozione: append dell'approvazione. L'AI propone, l'admin dispone."""
    voce = carica_voce(slug, directory=directory)
    if voce is None:
        raise ValueError(f"voce inesistente: {slug}")
    nuova = voce.model_copy(update={"approvazioni": voce.approvazioni + (
        ApprovazioneVoce(revisione_n=revisione_n, autore=autore, ts=_ora()),
    )})
    salva_voce(nuova, directory=directory)
    return nuova


def _ora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# --- L'estrazione: il choke-point di segretezza (rev. 3 §4) --------------------

def estrai_slice(
    stagione: int, *, directory: Path | None = None
) -> WikiSlice | None:
    """La fetta di wiki per una run al freeze: {scope della stagione ∩
    segretezza ≠ admin ∩ revisione corrente APPROVATA ∩ non-sostituite}.

    È l'UNICO punto in cui il contenuto lascia il master verso una run
    (l'export del bundle è l'altra estrazione, W2 — mai una copia). `None`
    se non c'è nulla da congelare: la run nasce senza wiki, zero footprint
    (i save legacy e i mondi senza wiki restano identici a prima)."""
    voci = elenca_voci(directory=directory)
    if not voci:
        return None
    # La supersessione per scope (§3): la voce bersaglio di un link
    # `sostituisce` di una voce APPROVATA esce dalle slice future.
    sostituite = {
        l.verso
        for v in voci if v.revisione_corrente() is not None
        for l in v.link if l.tipo == "sostituisce"
    }
    proiettate = []
    for voce in voci:
        if voce.segretezza is SegretezzaVoce.ADMIN:
            continue  # il muro: admin non esce MAI dal master
        if voce.slug in sostituite:
            continue
        if voce.scope.stagione is not None and voce.scope.stagione != stagione:
            continue
        rev = voce.revisione_corrente()
        if rev is None:
            continue  # tutta proposta: fisicamente invisibile
        proiettate.append(VoceSlice(
            slug=voce.slug, tipo=voce.tipo, testo=rev.testo, regia=voce.regia,
            costante=voce.costante, inneschi=voce.inneschi,
            piano_da=voce.scope.piano_da, piano_a=voce.scope.piano_a,
            zona=voce.scope.zona,
        ))
    if not proiettate:
        return None
    proiettate.sort(key=lambda v: v.slug)  # ordine totale: slice deterministica
    return WikiSlice(versione=_prossima_versione(directory), voci=tuple(proiettate))


def registra_estrazione(
    uuid_run: str, versione: int, *, directory: Path | None = None
) -> None:
    """Il registro master-side (rev. 3 §2.1.3): quali run hanno estratto
    quale versione — il prerequisito di «salvataggi colpiti» dello scrub."""
    base = directory or DIRECTORY_WIKI
    base.mkdir(parents=True, exist_ok=True)
    riga = json.dumps({"uuid": uuid_run, "versione": versione, "ts": _ora()})
    with (base / _REGISTRO_ESTRAZIONI).open("a", encoding="utf-8") as f:
        f.write(riga + "\n")


def _prossima_versione(directory: Path | None) -> int:
    base = directory or DIRECTORY_WIKI
    registro = base / _REGISTRO_ESTRAZIONI
    if not registro.exists():
        return 1
    with registro.open(encoding="utf-8") as f:
        return sum(1 for _ in f) + 1


# --- La validazione dei vincoli all'authoring (rev. 3 §6) ----------------------

def lint_vincolo(vincolo: dict | None, *, archetipi_noti: set[str]) -> list[str]:
    """Il check che il cruscotto esegue a OGNI scrittura (lo stesso
    dell'import del bundle, W2): un vincolo che cita slug ignoti è un
    errore di authoring QUI — il freeze resta la cintura (degrado
    dichiarato, mai crash). W1 valida la sola chiave `archetipi` (il
    vocabolario completo dei vincoli è la decisione §11.2)."""
    if not vincolo:
        return []
    errori = []
    for slug in vincolo.get("archetipi", []):
        if slug not in archetipi_noti:
            errori.append(f"vincolo: archetipo ignoto {slug!r}")
    return errori
