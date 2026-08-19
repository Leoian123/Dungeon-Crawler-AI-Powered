"""Wiki del Master — il CONTRATTO (W1, docs/future/wiki-master.md rev. 3).

Gli appunti persistenti del GM: voci versionate con scope di gioco,
segretezza strutturale e regia, scritte da admin/sistema/AI-proposta e
lette dalla run attraverso una SLICE congelata al freeze. Qui vive solo la
forma (DTO + porta): lo store è a livello host (`wiki_master.py`), il
consumo a livello motore (`motore/wiki.py`).

Il contratto della porta, PER-CORSIA (rev. 3 §0):
- corsia di MOTORE e corsia LESSICALE: DETERMINISTICHE — stessa slice +
  stesso contesto + stessa azione → stesse voci nello stesso ordine
  (spareggio totale: punteggio DESC, slug ASC);
- corsia SEMANTICA (W3, non in questo modulo): best-effort-poi-congelata;
  sul congelamento perso DEGRADA alla corsia lessicale — mai un
  ri-embedding retroattivo.

Segretezza (rev. 3 §5): due livelli STRUTTURALI — `in_slice` può entrare
nella slice (e quindi nei prompt), `admin` non esce MAI dal master (né
slice, né save, né bundle di vendita). La REGIA (`citabile`/`velato`/
`solo_contesto`) governa l'istruzione al modello ed è dichiaratamente NON
garantita: è comportamento dell'LLM, non un muro.

Dipendenze: solo stdlib + Pydantic (disciplina di `contracts`).
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .schema import RE_SLUG

_FROZEN = ConfigDict(frozen=True, extra="forbid")

Slug = Annotated[str, StringConstraints(pattern=RE_SLUG)]


class SegretezzaVoce(str, Enum):
    """I due livelli STRUTTURALI (rev. 3 §5): il confine è meccanico."""

    IN_SLICE = "in_slice"   # può entrare nella slice della run
    ADMIN = "admin"         # non esce MAI dal master


class RegiaVoce(str, Enum):
    """La regia dentro l'in-slice: istruzione al GM, dichiaratamente non
    garantita. L'ordine è di RESTRITTIVITÀ crescente (per il taint §4-bis)."""

    CITABILE = "citabile"           # il GM può citarla e mostrarla
    VELATO = "velato"               # la sa, la lascia trasparire, MAI testuale
    SOLO_CONTESTO = "solo_contesto"  # informa la composizione, mai la prosa


# La scala di restrittività per il taint delle proposte (§4-bis): una
# proposta nata con `velato` in contesto non può degradare a `citabile`
# senza un declassamento ESPLICITO dell'admin.
RESTRITTIVITA_REGIA: dict[RegiaVoce, int] = {
    RegiaVoce.CITABILE: 0,
    RegiaVoce.VELATO: 1,
    RegiaVoce.SOLO_CONTESTO: 2,
}


class ProvenienzaVoce(str, Enum):
    """Chi firma una revisione. Il gate strutturale: solo le revisioni
    APPROVATE entrano in indice e slice, quindi `sistema` e `proposta_ai`
    sono fisicamente invisibili al GM finché l'admin non promuove."""

    ADMIN = "admin"
    SISTEMA = "sistema"          # fatti di run promossi dal motore (outbox)
    PROPOSTA_AI = "proposta_ai"  # bootstrap e consolidamento offline


class TipoVoce(str, Enum):
    """La tassonomia delle voci. Vocabolario chiuso, NON AI-facing."""

    AMBIENTAZIONE = "ambientazione"
    PERSONAGGIO = "personaggio"
    LUOGO = "luogo"
    EVENTO = "evento"
    REGOLA = "regola"


class ScopeVoce(BaseModel):
    """Lo scope di gioco È il valid-time (rev. 2/3 §3): «vera dal piano 4
    della stagione 2» sono colonne di gioco, mai timestamp d'orologio.
    `stagione=None` = ogni stagione; `zona=""` = ogni zona (il valore è il
    tier, es. "quartiere"); `piano_a=None` = fino in fondo."""

    model_config = _FROZEN

    stagione: int | None = None
    piano_da: int = 1
    piano_a: int | None = None
    zona: str = ""


class RevisioneVoce(BaseModel):
    """UNA revisione, append-only per disciplina delle API (le proprietà
    del modello sono discipline del cruscotto, non del formato — rev. 3 §2).
    `vincolo` è dato chiuso INERTE in W1 (si consuma al freeze da W3, via
    percorso asset e gate F-6 — mai dalla porta di contesto)."""

    model_config = _FROZEN

    n: int = Field(ge=1)
    testo: str = Field(min_length=1)
    vincolo: dict | None = None
    provenienza: ProvenienzaVoce = ProvenienzaVoce.ADMIN
    ts: str = ""  # ISO-8601, timbrato dallo store host-side


class ApprovazioneVoce(BaseModel):
    model_config = _FROZEN

    revisione_n: int = Field(ge=1)
    autore: str = ""
    ts: str = ""


class LinkVoce(BaseModel):
    """Cross-riferimento superficiale. `tipo="sostituisce"` ha semantica di
    retrieval DEFINITA (rev. 3 §3): la voce bersaglio esce dall'indice e
    dalle slice FUTURE (le slice già congelate non cambiano — F-6)."""

    model_config = _FROZEN

    verso: Slug
    tipo: str = "vedi"


class VoceWiki(BaseModel):
    """UNA voce del master: il record canonico (il formato di storage È il
    formato del bundle — rev. 3 §2). `costante=True` = regime costante: la
    voce entra nel PREFISSO della run (cache), mai nel fascicolo dinamico.
    `inneschi` = chiavi della corsia lessicale (in aggiunta agli inneschi
    di MOTORE, che sono fatti di scena: zona/stanza/entità)."""

    model_config = _FROZEN

    slug: Slug
    tipo: TipoVoce
    scope: ScopeVoce = ScopeVoce()
    segretezza: SegretezzaVoce = SegretezzaVoce.IN_SLICE
    regia: RegiaVoce = RegiaVoce.CITABILE
    costante: bool = False
    inneschi: tuple[str, ...] = ()
    revisioni: tuple[RevisioneVoce, ...] = Field(min_length=1)
    approvazioni: tuple[ApprovazioneVoce, ...] = ()
    link: tuple[LinkVoce, ...] = ()

    @model_validator(mode="after")
    def _coerente(self) -> "VoceWiki":
        numeri = [r.n for r in self.revisioni]
        if numeri != sorted(numeri) or len(set(numeri)) != len(numeri):
            raise ValueError(f"{self.slug}: revisioni non ordinate o duplicate")
        noti = set(numeri)
        for a in self.approvazioni:
            if a.revisione_n not in noti:
                raise ValueError(
                    f"{self.slug}: approvazione di una revisione inesistente "
                    f"({a.revisione_n})"
                )
        return self

    def revisione_corrente(self) -> RevisioneVoce | None:
        """La revisione più alta APPROVATA (`None` = la voce è tutta
        proposta: invisibile a indice e slice — il gate strutturale)."""
        approvate = {a.revisione_n for a in self.approvazioni}
        for rev in reversed(self.revisioni):
            if rev.n in approvate:
                return rev
        return None


class VoceSlice(BaseModel):
    """La PROIEZIONE di una voce dentro la slice: la sola revisione corrente
    approvata, senza storia, senza approvazioni, senza `vincolo` (inerte in
    W1) e — per costruzione — mai `admin`."""

    model_config = _FROZEN

    slug: Slug
    tipo: TipoVoce
    testo: str
    regia: RegiaVoce
    costante: bool = False
    inneschi: tuple[str, ...] = ()
    piano_da: int = 1
    piano_a: int | None = None
    zona: str = ""


class WikiSlice(BaseModel):
    """La fetta di wiki CONGELATA per una run al freeze (rev. 3 §4): scope
    della stagione ∩ segretezza ≠ admin ∩ approvate ∩ non-sostituite.
    Vive in un TERZO artefatto del save a contratto VITALE (§3.1):
    illeggibile o assente ⇒ il load RIFIUTA, mai rigenerazione silenziosa."""

    model_config = _FROZEN

    versione: int = Field(ge=1)
    voci: tuple[VoceSlice, ...] = ()


class PropostaWiki(BaseModel):
    """UNA proposta in uscita dalla run (outbox, rev. 3 §4-bis). `id` è
    DETERMINISTICO (firma del fatto): la raccolta ripetuta e il
    save-scumming deduplicano per costruzione. `taint` = la regia più
    restrittiva vista in run: la promozione può solo DECLASSARE con atto
    esplicito dell'admin."""

    model_config = _FROZEN

    id: str = Field(min_length=1)
    tipo: TipoVoce
    titolo: str
    testo: str
    taint: RegiaVoce = RegiaVoce.CITABILE
    uuid_run: str = ""
    ts: str = ""


class ContestoScena(BaseModel):
    """Gli inneschi di MOTORE della corsia dinamica: fatti, non substring
    di chat (il rimedio strutturale alla fragilità-keyword dei lorebook)."""

    model_config = _FROZEN

    piano: int = 1
    zona: str = ""
    stanza_tipo: str = ""
    entita: tuple[str, ...] = ()


@runtime_checkable
class WikiMaster(Protocol):
    """La porta di LETTURA (master→run). Contratto per-corsia nel docstring
    di modulo. Il verso di ritorno (run→master) NON passa da qui: è la
    seconda porta governata — l'outbox e la coda del cruscotto (§4-bis)."""

    def recupera(
        self, contesto: ContestoScena, azione: str, *, limite: int = 2
    ) -> tuple[VoceSlice, ...]: ...

    def costanti(self, piano: int) -> tuple[VoceSlice, ...]: ...
