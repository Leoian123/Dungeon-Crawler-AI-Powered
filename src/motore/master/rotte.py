"""Il registro delle ROTTE: ogni percorso AI del motore, dichiarato come dato.

Una rotta NON possiede prompt né gate (quelli restano nei moduli di dominio):
dichiara *come* si chiama il trasporto — schema di output, corsia (profilo
astratto forte/veloce: il binding al modello vive nel composition root), numero
di retry, fase in cui la chiamata è lecita, e se l'esito è gating (tocca stato
attraverso un gate) — così l'aggiunta di un percorso è una riga qui, non una
pipeline nuova.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel

from contracts import Flavor, Ideazione, InquadramentoProva, TurnoNarrazione

from ..fase import Fase


class Corsia(str, Enum):
    """Corsia di trasporto ASTRATTA: il motore non nomina mai un modello.

    Il binding corsia→backend (modello, max_tokens, timeout) è del composition
    root (`provider/root.py`), iniettato nel `MasterEngine` alla costruzione."""

    FORTE = "forte"
    VELOCE = "veloce"


@dataclass(frozen=True)
class Rotta:
    """La dichiarazione di UN percorso AI. Dato puro, congelato.

    `fase=None` = lecita in qualunque fase. `gating=True` è documentale e
    osservabilità: l'esito attraversa un gate di validazione prima di toccare
    stato (il gate resta nel modulo di dominio, mai qui)."""

    nome: str
    schema: type[BaseModel]
    corsia: Corsia
    retry: int = 0
    fase: Fase | None = None
    gating: bool = False


ROTTE: dict[str, Rotta] = {}


def registra_rotta(rotta: Rotta) -> None:
    """Registra una rotta. Un doppione di nome è un errore di programmazione
    (due percorsi con lo stesso nome divergerebbero in silenzio), mai un merge."""
    if rotta.nome in ROTTE:
        raise ValueError(f"rotta duplicata: {rotta.nome!r}")
    ROTTE[rotta.nome] = rotta


# --- Le rotte della pipeline GM (G §9.2) — la fotografia dell'esistente --------
# `gm.gating` dichiara retry=1 in SINCRONIA con POLICY_RETRY[TurnoNarrazione]
# (narrazione.py): finché le due vie coesistono, un lucchetto le tiene uguali
# (`test_sincronia_retry_rotta_gating`).

for _rotta in (
    Rotta("gm.ideazione", Ideazione, Corsia.VELOCE, retry=0, fase=Fase.NARRAZIONE),
    Rotta("gm.gating", TurnoNarrazione, Corsia.FORTE, retry=1,
          fase=Fase.NARRAZIONE, gating=True),
    Rotta("gm.prova", InquadramentoProva, Corsia.VELOCE, retry=0, fase=Fase.NARRAZIONE),
    Rotta("gm.limatura", Flavor, Corsia.VELOCE, retry=0, fase=Fase.NARRAZIONE),
    Rotta("gm.distilla", Flavor, Corsia.VELOCE, retry=0, fase=Fase.NARRAZIONE),
    # --- Scontro narrato (Fase 5): tutte non-gating, degrado deterministico ----
    # Apertura: breve trailer al tasto Combatti — vive nella TRANSIZIONE di fase
    # (l'host la attende DOPO il flip), quindi lecita ovunque (fase=None).
    Rotta("scontro.apertura", Flavor, Corsia.VELOCE, retry=0, fase=None),
    # Resoconto: la chiusura cinematografica dai FATTI deterministici — è un
    # turno GM a tutti gli effetti, vive in NARRAZIONE.
    Rotta("scontro.resoconto", Flavor, Corsia.FORTE, retry=0, fase=Fase.NARRAZIONE),
    # Epitaffio: la voce dello showrunner sulla schermata terminale (la run è
    # chiusa: nessuna fase da esigere, nessun Archivio da scrivere).
    Rotta("scontro.epitaffio", Flavor, Corsia.FORTE, retry=0, fase=None),
):
    registra_rotta(_rotta)
