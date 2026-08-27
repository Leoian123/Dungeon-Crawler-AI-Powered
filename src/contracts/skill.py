"""skill — il contratto del sistema Skill (nodo S).

«Il sistema conta tutto»: una skill è il CONTATORE VIVO di una pratica — il
motore conta i fatti del bus tipizzato (mai l'LLM, mai la prosa) e il
livello è una DERIVATA del conteggio (soglie §11, replay-safe per
costruzione). Niente XP depositata, niente orologio.

Vocabolario delle PRATICHE chiuso: una skill può contare solo fatti che il
motore pubblica davvero — se il fatto non viaggia sul bus, la pratica non
esiste (per costruzione). I testi del catalogo sono ORIGINALI (nota IP nel
piano, docs/sistema-skill.md): il registro si imita, il contenuto no.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .schema import RE_SLUG as _RE_SLUG
from .schema import Fascia


class PraticaSkill(str, Enum):
    """Su QUALE fatto del motore la skill conta. Ogni membro mappa un evento
    di dominio del bus — l'aggiunta di una pratica nuova è una riga qui + il
    binding nell'osservatore, mai un caso speciale nel codice di gioco."""

    MOSSA = "mossa"      # ColpoInferto del protagonista, con la SUA mossa
    FUGA = "fuga"        # CombatResolved con fuga=True
    RIPOSO = "riposo"    # RiposoConcluso NON interrotto
    ZONA = "zona"        # TransizioneZona


class DominioSkill(str, Enum):
    """Il DOMINIO della competenza: la mappa dei sistemi presenti e futuri
    (ratifica 2026-08-27 — la skill è lo strato su cui girano magia,
    crafting, sopravvivenza, combattimento avanzato). I sistemi consumatori
    interrogano il dominio (`livello_dominio`), mai la singola skill."""

    COMBATTIMENTO = "combattimento"
    MAGIA = "magia"
    ARTIGIANATO = "artigianato"
    SOPRAVVIVENZA = "sopravvivenza"
    MOVIMENTO = "movimento"
    MONDANA = "mondana"          # il junk del canone: tono, mai potere


class EffettoCompetenza(str, Enum):
    """COSA il livello muove (vocabolario CHIUSO): ogni membro ha UN
    consumatore nel motore — un effetto nuovo è una riga qui + il suo punto
    unico d'applicazione, mai un numero libero. Il QUANTO per livello lo
    dice la `intensita` (Fascia) via le foglie §11 `COMPETENZA.*`."""

    POTENZA_MOSSA = "potenza_mossa"    # la mossa governata, nel check 2
    MARGINE_FUGA = "margine_fuga"      # il margine delle tre corsie
    RESA_RIPOSO = "resa_riposo"        # HP per tick di riposo
    ESCA_AGGUATI = "esca_agguati"      # il dado-imboscata nel downtime


class SkillAsset(BaseModel):
    """UNA skill come dato autorale (contenuti/skill/*.json, congelata
    per-run come ogni asset) — una COMPETENZA, non un contatore (ratifica
    2026-08-27): il livello ne muove l'`effetto` con la magnitudine della
    `intensita` (Fascia — i numeri sono foglie §11, mai nell'asset).
    `effetto` assente = skill di puro TONO (metà del canone): legittimo, ma
    è una dichiarazione, non un default. `livello_iniziale` è la «valuta»
    della dotazione (il junk di partenza ad alto livello)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str = Field(min_length=1, pattern=_RE_SLUG)
    versione: int = 1
    tags: tuple[str, ...] = ()
    nome: str = Field(min_length=1)
    testo: str = Field(min_length=1)
    tipo: Literal["attiva", "passiva"]
    dominio: DominioSkill
    pratica: PraticaSkill
    mossa: str = ""                  # la chiave del catalogo mosse (solo MOSSA)
    effetto: EffettoCompetenza | None = None
    intensita: Fascia = Fascia.LIEVE
    livello_iniziale: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _coerente(self) -> "SkillAsset":
        if (self.pratica is PraticaSkill.MOSSA) != bool(self.mossa):
            raise ValueError(
                f"skill {self.slug}: la pratica MOSSA vuole la chiave di "
                "mossa, le altre pratiche non la portano"
            )
        if self.tipo == "attiva":
            if self.pratica is not PraticaSkill.MOSSA:
                raise ValueError(
                    f"skill {self.slug}: un'attiva governa una MOSSA — le "
                    "pratiche fuori combattimento sono passive"
                )
            if self.effetto is not EffettoCompetenza.POTENZA_MOSSA:
                raise ValueError(
                    f"skill {self.slug}: l'attiva scala la SUA mossa — "
                    "effetto potenza_mossa, dichiarato"
                )
        elif self.effetto is EffettoCompetenza.POTENZA_MOSSA:
            raise ValueError(
                f"skill {self.slug}: potenza_mossa è delle attive"
            )
        if self.dominio is DominioSkill.MONDANA and self.effetto is not None:
            raise ValueError(
                f"skill {self.slug}: la mondana è tono, mai potere — "
                "un effetto vuole un dominio vero"
            )
        return self


class SkillRigaVista(BaseModel):
    """UNA riga dell'elenco skill per l'host: il registro della pratica come
    lo vede il giocatore. Niente velo (le skill si conoscono: il menu del
    canone elenca tutto — è metà del tono); l'host mostra, mai deduce."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str
    nome: str
    tipo: str          # attiva | passiva
    livello: int
    usi: int
    testo: str
    mossa: str = ""     # per le attive: la chiave che governa
    dominio: str = ""   # la mappa dei sistemi (combattimento, magia, …)
    effetto: str = ""   # cosa muove il livello ("" = tono)
