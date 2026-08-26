"""I FANTASMI delle run altrui — lore congelata nella run (Fase D sovra-run).

«Qui giace X, aperto in due da Y»: le tracce di altre run (locali o, un
domani, scaricate) entrano nella MIA run come materia narrativa. Due regole
ferree, le stesse linee rosse di sempre:

- il fantasma è LORE, mai stato: non tocca combattimento, drop, numeri — la
  sua unica via d'uscita è una riga di fascicolo che il GM VESTE;
- il set di fantasmi è INPUT della run, congelato nel World alla nascita
  (`monta_fantasmi`, pattern `StagioneAttiva`) e PERSISTENTE col save (tag
  `fantasmi`): il reload mostra le stesse tracce, o il determinismo salta.

L'ASSEGNAZIONE alla stanza è DERIVATA, mai memorizzata: hash stabile di
(fantasma, master seed) modulo le stanze del piano — stessa run, stessa
stanza, per sempre. Solo il `consumato` è stato (una traccia si narra UNA
volta), e viaggia nel save.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Sequence

import esper

from contracts import FantasmaRun

from .mappa import mappa_corrente
from .piano import livello_corrente
from .seme import master_seed


@dataclass
class FantasmaAttivo:
    """Il dato-fantasma dentro la run (traduzione del contratto, come
    `StagioneAttiva` traduce `Stagione`). Mutabile per il solo `consumato`."""

    nome: str
    causa: str = ""
    profondita: int = 1
    stagione: int = 1
    seed: int = 0
    epitaffio: str = ""
    consumato: bool = False


@dataclass
class FantasmiAttivi:
    """Singleton di run: il set congelato all'ingresso (persistente, tag H-3)."""

    lista: list[FantasmaAttivo] = field(default_factory=list)


def monta_fantasmi(fantasmi: Sequence[FantasmaRun]) -> int | None:
    """Congela il set nel World corrente (al confine guscio→run, come la
    stagione). No-op a set vuoto: zero footprint, save come prima."""
    if not fantasmi:
        return None
    return esper.create_entity(FantasmiAttivi(lista=[
        FantasmaAttivo(
            nome=f.nome, causa=f.causa, profondita=f.profondita,
            stagione=f.stagione, seed=f.seed, epitaffio=f.epitaffio,
        )
        for f in fantasmi
    ]))


def fantasmi_correnti() -> FantasmiAttivi | None:
    trovati = esper.get_component(FantasmiAttivi)
    return trovati[0][1] if trovati else None


def _stanza_assegnata(fantasma: FantasmaAttivo, n_stanze: int, master: int) -> int:
    """La stanza della traccia: DERIVAZIONE stabile (sha256, mai `hash()` che è
    salato per processo), così non è un secondo stato da persistere."""
    impronta = f"{fantasma.nome}|{fantasma.seed}|{fantasma.profondita}|{master}"
    digest = hashlib.sha256(impronta.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % max(1, n_stanze)


def _fantasma_in_stanza_corrente() -> FantasmaAttivo | None:
    componente = fantasmi_correnti()
    trovata = mappa_corrente()
    if componente is None or trovata is None:
        return None
    mappa = trovata[1]
    n_stanze = len(mappa.piano.adiacenze)
    try:
        livello = livello_corrente()
        master = master_seed()
    except Exception:
        return None  # harness senza piano/seme: nessuna traccia, mai un crash
    for fantasma in componente.lista:
        if fantasma.consumato or fantasma.profondita != livello:
            continue
        if _stanza_assegnata(fantasma, n_stanze, master) == mappa.stanza_corrente:
            return fantasma  # una traccia per turno: la prima non consumata
    return None


def traccia_fantasma_corrente() -> str:
    """La riga-fatto per il fascicolo GM ("" = nessuna traccia qui). Sola
    lettura: il consumo è un atto separato (`consuma_fantasma_corrente`),
    che la sessione compie solo a turno SCRITTO — la stessa disciplina dei
    gemelli scontro/scena."""
    fantasma = _fantasma_in_stanza_corrente()
    if fantasma is None:
        return ""
    if fantasma.epitaffio:
        return fantasma.epitaffio
    caduta = f", caduto per mano di {fantasma.causa}" if fantasma.causa else ""
    return f"qui giace il crawler {fantasma.nome}{caduta}"


def consuma_fantasma_corrente() -> None:
    """Marca consumata la traccia della stanza corrente (idempotente). Lo stato
    viaggia nel save: al reload la traccia già narrata non torna."""
    fantasma = _fantasma_in_stanza_corrente()
    if fantasma is not None:
        fantasma.consumato = True
