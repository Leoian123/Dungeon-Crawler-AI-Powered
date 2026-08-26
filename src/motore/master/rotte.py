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

from contracts import (
    BattutaScena,
    FabbricaAsset,
    Flavor,
    Ideazione,
    InquadramentoProva,
    LottoBossGenerati,
    LottoMosseAutorate,
    LottoOggettiAutorati,
    LottoStatusProposti,
    NemicoSperimentale,
    OggettoAutorato,
    OggettoGenerato,
    PezzoUnico,
    SkillGenerata,
    TabellaProceduraleGen,
    TabellaSpawnGenerata,
    TurnoNarrazione,
)

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
    # --- Authoring della stagione (2026-08-10): chiamate FUORI-RUN (fase=None,
    # non esiste un World), gating=True — il gate è la catena di lint esistente
    # (registry F-6, mosse note, budget, risoluzione finale). Corsia FORTE: il
    # contenuto si genera una volta e resta.
    Rotta("authoring.boss", LottoBossGenerati, Corsia.FORTE, retry=1,
          fase=None, gating=True),
    Rotta("authoring.tabella", TabellaProceduraleGen, Corsia.FORTE, retry=1,
          fase=None, gating=True),
    Rotta("authoring.spawn", TabellaSpawnGenerata, Corsia.FORTE, retry=1,
          fase=None, gating=True),
    Rotta("authoring.oggetto", LottoOggettiAutorati, Corsia.FORTE, retry=1,
          fase=None, gating=True),
    Rotta("authoring.mossa", LottoMosseAutorate, Corsia.FORTE, retry=1,
          fase=None, gating=True),
    # authoring.status (D-4, variante PROPOSTA): l'esito è un file-brief per
    # i «3 tocchi» umani, MAI la libreria — gating=True per il gate di
    # coerenza, ma niente --applica per costruzione.
    Rotta("authoring.status", LottoStatusProposti, Corsia.FORTE, retry=1,
          fase=None, gating=True),
    # La FABBRICA del loot procedurale: l'AI scrive le tabelle-parti UNA volta
    # (il vocabolario), il motore le combina seeded a ogni drop (le istanze).
    Rotta("authoring.fabbrica", FabbricaAsset, Corsia.FORTE, retry=1,
          fase=None, gating=True),
    # --- Premi (contratto premi, Sit.3+4): la VESTIZIONE del drop già deciso.
    # gating=True (l'esito tocca il Guardaroba), FORTE (il premio è un momento
    # chiave), fase NARRAZIONE (il resoconto post-scontro è il suo posto).
    Rotta("premi.oggetto", OggettoGenerato, Corsia.FORTE, retry=1,
          fase=Fase.NARRAZIONE, gating=True),
    # Il CONIO libero: senza fabbrica attiva, l'AI genera l'oggetto NUOVO
    # dentro il frame del motore (grado deciso seeded prima della chiamata).
    Rotta("premi.conio", OggettoAutorato, Corsia.FORTE, retry=1,
          fase=Fase.NARRAZIONE, gating=True),
    # Il PEZZO UNICO: con la fabbrica attiva il conio è OTTIMIZZATO — l'AI
    # sceglie i COMPONENTI per nome dalle tabelle-parti e firma la targhetta;
    # l'assemblaggio è lo stesso del procedurale (un solo assemblatore).
    Rotta("premi.unico", PezzoUnico, Corsia.FORTE, retry=1,
          fase=Fase.NARRAZIONE, gating=True),
    Rotta("premi.skill", SkillGenerata, Corsia.FORTE, retry=1,
          fase=Fase.NARRAZIONE, gating=True),
    # --- Dialogo PNG (T3): SOLA PROSA (mai esiti — la voce va solo a video),
    # phase-gated a NARRAZIONE: parlare in combattimento è strutturalmente
    # impossibile (la guardia di fase, non un check a mano). Corsia VELOCE:
    # è flavor conversazionale; se la voce risulta piatta, il cambio a FORTE
    # è un dato in questa riga.
    Rotta("png.dialogo", Flavor, Corsia.VELOCE, retry=0,
          fase=Fase.NARRAZIONE, gating=False),
    # --- Scena narrativa (S1): il battito a BLOCCHI — l'AI compone (battuta/
    # snodo/chiudi), il motore arbitra (tiro dello snodo, legalità della
    # chiusura, anti-pesca). Corsia VELOCE (è conversazione), phase-gated a
    # NARRAZIONE come il dialogo PNG; retry=1: lo schema è strict sui campi
    # per-blocco e un tentativo di correzione vale la chiamata.
    Rotta("scena.blocco", BattutaScena, Corsia.VELOCE, retry=1,
          fase=Fase.NARRAZIONE, gating=False),
    # --- Banco di prova nemici: strumento fuori-run (fase=None), gating=True
    # (il core passa da `valida_turno`). Corsia FORTE: è il confronto fra
    # modelli sul percorso di qualità. retry=0: un None VA riportato com'è.
    Rotta("banco.nemico", NemicoSperimentale, Corsia.FORTE, retry=0,
          fase=None, gating=True),
):
    registra_rotta(_rotta)
