"""contracts — la membrana motore ⇄ vista (IC §2) e il contratto AI↔motore (nodo F).

ZERO dipendenze di progetto: **solo stdlib + Pydantic** (F-2). NON importa esper,
Textual, provider (il layer), motore, adattatore. È il vocabolario condiviso:
  - il **bus tipizzato** di progetto (ESP §5) — `bus.py`;
  - gli **eventi di dominio** (motore → vista) — `eventi.py`;
  - gli **intenti** del giocatore (vista → motore) — `intenti.py`;
  - lo **schema Pydantic** del contratto AI↔motore (nodo F) — `schema.py`;
  - l'**interfaccia provider** (solo firma/Protocol, PLK §2) — `provider.py`.

Motore e vista importano *questo*, e non si importano mai a vicenda (C-3).
"""

from .bus import BusEventi, Handler
from .eventi import (
    Entita,
    EventoDominio,
    EncounterStarted,
    CombatResolved,
    MortePersonaggio,
    AnomalyTriggered,
    DiscesaPiano,
)
from .intenti import (
    Intento,
    IntentoCombattimento,
    IntentoEsplorazione,
    PlayerChoseOption,
    PlayerScappa,
    PlayerSiMuove,
    PlayerTentaProva,
    PlayerDiscende,
)
from .schema import (
    Archetipo,
    Grado,
    StatId,
    Blocco,
    TipoDanno,
    TipoAzione,
    ClasseProva,
    Durata,
    EntitaGenerata,
    Opzione,
    TurnoNarrazione,
    Flavor,
    IntenzioneScena,
    TonoScena,
    Ideazione,
    InquadramentoProva,
)
from .contenuti import (
    AssetVista,
    BudgetDesign,
    MobAsset,
    PianoAsset,
    PianoRisolto,
    Stagione,
    StagioneRisolta,
)
from .hub import CrawlerVista
from .proiezione import SchedaProiezione, SchedaVista
from .vista import (
    FattiScontro,
    MessaggioGM,
    OpzioneVista,
    ProvaVista,
    RiepilogoAzione,
    SnapshotVista,
    StimaAzione,
    TempoVista,
)
from .provider import Provider, TCandidato

__all__ = [
    # bus
    "BusEventi",
    "Handler",
    # eventi di dominio
    "Entita",
    "EventoDominio",
    "EncounterStarted",
    "CombatResolved",
    "MortePersonaggio",
    "AnomalyTriggered",
    "DiscesaPiano",
    # intenti
    "Intento",
    "IntentoCombattimento",
    "IntentoEsplorazione",
    "PlayerSiMuove",
    "PlayerChoseOption",
    "PlayerScappa",
    "PlayerTentaProva",
    "PlayerDiscende",
    # schema AI↔motore
    "Archetipo",
    "Grado",
    "StatId",
    "Blocco",
    "TipoDanno",
    "TipoAzione",
    "ClasseProva",
    "Durata",
    "EntitaGenerata",
    "Opzione",
    "TurnoNarrazione",
    "Flavor",
    "IntenzioneScena",
    "TonoScena",
    "Ideazione",
    "InquadramentoProva",
    # proiezione scheda (sola lettura) + scheda per la UI + hub
    "SchedaProiezione",
    "SchedaVista",
    "CrawlerVista",
    # contenuti dello show (asset riusabili + forme risolte)
    "AssetVista",
    "BudgetDesign",
    "MobAsset",
    "PianoAsset",
    "PianoRisolto",
    "Stagione",
    "StagioneRisolta",
    # snapshot di rendering per la vista
    "OpzioneVista",
    "SnapshotVista",
    "MessaggioGM",
    "TempoVista",
    "ProvaVista",
    "StimaAzione",
    "RiepilogoAzione",
    "FattiScontro",
    # provider
    "Provider",
    "TCandidato",
]
