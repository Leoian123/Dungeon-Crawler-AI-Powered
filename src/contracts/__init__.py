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
    ColpoInferto,
    CombatResolved,
    EffettoStatus,
    MortePersonaggio,
    AnomalyTriggered,
    CrolloDungeon,
    DiscesaPiano,
    DisimpegnoScena,
    OggettoTrovato,
    StatusApplicato,
    StatusSvanito,
    RiposoConcluso,
    TurnoSaltato,
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
    PlayerEquipaggia,
    PlayerToglie,
)
from .schema import (
    ArchetipoId,
    Grado,
    StatId,
    Blocco,
    TipoDanno,
    TipoAzione,
    ClasseProva,
    ClasseBeneficio,
    Taglia,
    CategoriaArmatura,
    SedeAccessorio,
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
    ArchetipoAsset,
    AssetVista,
    BudgetDesign,
    MobAsset,
    PianoAsset,
    PianoRisolto,
    ProfiloArchetipoDati,
    Stagione,
    StagioneRisolta,
)
from .hub import CrawlerVista
from .proiezione import (
    EquipVista,
    ProgressioneVista,
    SchedaProiezione,
    SchedaVista,
    SkillVista,
    SlotEquip,
    SLOT_ARMATURA,
    SLOT_IMPUGNATI,
)
from .vista import (
    FattiScontro,
    GradoEsito,
    MessaggioGM,
    OpzioneVista,
    ProvaVista,
    RiepilogoAzione,
    SnapshotVista,
    StimaAzione,
    TempoVista,
    Terminale,
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
    "ColpoInferto",
    "CombatResolved",
    "EffettoStatus",
    "MortePersonaggio",
    "AnomalyTriggered",
    "CrolloDungeon",
    "DiscesaPiano",
    "DisimpegnoScena",
    "OggettoTrovato",
    "StatusApplicato",
    "StatusSvanito",
    "TurnoSaltato",
    "RiposoConcluso",
    # intenti
    "Intento",
    "IntentoCombattimento",
    "IntentoEsplorazione",
    "PlayerSiMuove",
    "PlayerChoseOption",
    "PlayerScappa",
    "PlayerTentaProva",
    "PlayerDiscende",
    "PlayerEquipaggia",
    "PlayerToglie",
    "Taglia",
    "CategoriaArmatura",
    "SedeAccessorio",
    # schema AI↔motore
    "ArchetipoId",
    "Grado",
    "StatId",
    "Blocco",
    "TipoDanno",
    "TipoAzione",
    "ClasseProva",
    "ClasseBeneficio",
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
    "SkillVista",
    "EquipVista",
    "SlotEquip",
    "SLOT_ARMATURA",
    "SLOT_IMPUGNATI",
    "ProgressioneVista",
    "CrawlerVista",
    # contenuti dello show (asset riusabili + forme risolte)
    "AssetVista",
    "BudgetDesign",
    "ArchetipoAsset",
    "MobAsset",
    "PianoAsset",
    "ProfiloArchetipoDati",
    "PianoRisolto",
    "Stagione",
    "StagioneRisolta",
    # snapshot di rendering per la vista
    "OpzioneVista",
    "SnapshotVista",
    "Terminale",
    "MessaggioGM",
    "TempoVista",
    "ProvaVista",
    "GradoEsito",
    "StimaAzione",
    "RiepilogoAzione",
    "FattiScontro",
    # provider
    "Provider",
    "TCandidato",
]
