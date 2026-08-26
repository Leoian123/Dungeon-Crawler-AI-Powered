"""obiettivi — il contratto del sistema Obiettivi e Box (nodo O, fase O1).

Il dungeon ti guarda e commenta: un obiettivo è una NOTIFICA DI SISTEMA
deterministica — testo autorale nel registro dello show — che scatta su un
FATTO del motore (un evento del bus tipizzato: mai l'LLM, mai la prosa) e
premia con una BOX (conio ritardato della fabbrica, per categoria e grado)
oppure con una BEFFA dichiarata (anche «nessuna» è una ricompensa, detta).

Vocabolario dei trigger CHIUSO: un obiettivo può ascoltare solo eventi che
il motore pubblica davvero, e le condizioni sono i CAMPI di quegli eventi —
se il fatto non viaggia sul bus, l'obiettivo non può vederlo (per
costruzione, non per disciplina). I testi del catalogo sono ORIGINALI
(nota IP nel piano, docs/obiettivi-e-box.md): il registro si imita, il
testo mai.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .schema import Grado


class EventoTrigger(str, Enum):
    """Su QUALE fatto del motore l'obiettivo ascolta. Ogni membro mappa un
    evento di dominio del bus (contracts/eventi.py) — l'aggiunta di un
    trigger nuovo è una riga qui + il binding nell'osservatore, mai un caso
    speciale nel codice di gioco."""

    COMBAT_RISOLTO = "combat_risolto"        # CombatResolved
    MORTE = "morte"                          # MortePersonaggio (il postumo)
    DISCESA = "discesa"                      # DiscesaPiano
    ZONA_ATTRAVERSATA = "zona_attraversata"  # TransizioneZona
    OGGETTO_TROVATO = "oggetto_trovato"      # OggettoTrovato
    RIPOSO_CONCLUSO = "riposo_concluso"      # RiposoConcluso


class CategoriaBox(str, Enum):
    """La categoria della box: vincola il conio d'apertura a un sottoinsieme
    delle BASI della fabbrica. Una categoria si dichiara SOLO se la fabbrica
    può onorarla: mai una box che non può aprire nulla."""

    ARMI = "armi"                # basi di tipo arma
    INDUMENTI = "indumenti"      # basi di tipo armatura
    ACCESSORI = "accessori"      # basi di tipo accessorio
    AVVENTURIERO = "avventuriero"  # qualunque base: la box generalista


class TriggerObiettivo(BaseModel):
    """Il trigger dichiarativo: l'evento + le condizioni sui SUOI campi.
    `None` = condizione non posta. Una condizione valorizzata su un evento
    che non la trasporta è inerte per costruzione (l'osservatore confronta
    solo i fatti presenti) — il lint del catalogo (O3) la segnalerà."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evento: EventoTrigger
    vittoria: bool | None = None    # combat_risolto
    fuga: bool | None = None        # combat_risolto
    interrotto: bool | None = None  # riposo_concluso
    tier: str | None = None         # zona_attraversata


class BoxRicompensa(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    categoria: CategoriaBox
    grado: Grado


class RicompensaObiettivo(BaseModel):
    """O una box, o una beffa (testo dichiarato) — ALMENO una delle due: la
    ricompensa vuota e muta non esiste, anche il «niente» si annuncia."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    box: BoxRicompensa | None = None
    beffa: str = ""

    @model_validator(mode="after")
    def _almeno_una(self) -> "RicompensaObiettivo":
        if self.box is None and not self.beffa.strip():
            raise ValueError(
                "ricompensa vuota: dichiara una box o una beffa (anche il "
                "«niente» si annuncia)"
            )
        return self


class ObiettivoVista(BaseModel):
    """UNA riga dell'elenco obiettivi per l'host (fase O4): il catalogo della
    run con lo stato di sblocco. Il testo resta VELATO finché non sbloccato
    (lo spoiler dell'obiettivo è metà del gusto): l'host mostra, mai deduce."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str
    titolo: str
    testo: str            # "" finché non sbloccato (velato)
    sbloccato: bool
    ricompensa_testo: str  # "" finché non sbloccato


class AchievementAsset(BaseModel):
    """UN obiettivo come dato autorale (contenuti/obiettivi/*.json, congelato
    per-run come ogni asset). `ripetibile=False` = una volta per run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str = Field(min_length=1)
    versione: int = 1
    tags: tuple[str, ...] = ()
    titolo: str = Field(min_length=1)
    testo: str = Field(min_length=1)
    trigger: TriggerObiettivo
    ricompensa: RicompensaObiettivo
    ripetibile: bool = False
