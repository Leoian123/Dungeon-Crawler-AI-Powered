"""Il dispatcher del Master-Engine: guardia di fase → corsia → retry → tally.

Sta SOTTO il socket (G §9.2): ogni `genera` è una chiamata strutturata al
provider della corsia dichiarata dalla rotta. Non costruisce prompt, non valida
candidati, non sceglie fallback — quelli restano nei moduli di dominio. È il
punto UNICO dove si contano le chiamate per percorso (`tally`): la domanda
"dove vanno i token di un turno?" ha una risposta per rotta, non un totale muto.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from pydantic import BaseModel

from ..bonifica import misura_slop, retry_bonifica, righe_regia
from ..fase import Fase, in_combattimento
from ..tipografia import rifinisci_caporali
from .rotte import ROTTE, Corsia, Rotta

# I campi di PROSA A VIDEO degli schemi delle rotte (`prosa` nei turni e nei
# blocchi di scena, `testo` nei Flavor): gli unici che rifinitura tipografica
# e bonifica toccano — mai slug, enum o campi d'authoring.
_CAMPI_PROSA = ("prosa", "testo")


def _campo_prosa(candidato) -> tuple[str, str] | None:
    for campo in _CAMPI_PROSA:
        valore = getattr(candidato, campo, None)
        if isinstance(valore, str):
            return campo, valore
    return None


def _rifinisci_prosa(candidato) -> None:
    """Rifinitura di FORMA (mai di contenuto): i caporali mischiati agli apici
    dritti nella prosa a video (playtest 2026-08-27). Non è validazione né
    fallback: il candidato è già conforme."""
    trovato = _campo_prosa(candidato)
    if trovato is not None:
        campo, valore = trovato
        setattr(candidato, campo, rifinisci_caporali(valore))


@dataclass
class ConsumoRotta:
    """Il conteggio di UNA rotta: chiamate fatte, degradi (tutti i tentativi
    None), regie (giri extra del gate di forma) e slop (violazioni
    sopravvissute nel testo accettato — la telemetria della bonifica)."""

    chiamate: int = 0
    degradi: int = 0
    regie: int = 0
    slop: int = 0


class MasterEngine:
    """Il canale unico: `genera(nome_rotta, prompt)` al posto di N pipeline.

    Riceve i provider per corsia PER INIEZIONE (composition root); `avvolgi` è
    l'adattatore di transizione — un solo provider su entrambe le corsie — che
    tiene vivi i FakeProvider/ProviderCopione esistenti senza toccarli."""

    def __init__(self, corsie: Mapping[Corsia, object]) -> None:
        mancanti = {c for c in Corsia} - set(corsie)
        if mancanti:
            raise ValueError(f"corsie senza provider: {sorted(c.value for c in mancanti)}")
        self._corsie = dict(corsie)
        self.tally: dict[str, ConsumoRotta] = {}

    @classmethod
    def avvolgi(cls, provider) -> "MasterEngine":
        """Un solo provider su TUTTE le corsie (fake, copione, o composto che
        instrada già per schema): il ponte di compatibilità."""
        return cls({corsia: provider for corsia in Corsia})

    def provider_di(self, corsia: Corsia):
        """Il provider di una corsia — per i moduli che possiedono la propria
        pipeline di chiamata (es. `procura_turno`, che tiene prompt+gate+retry)."""
        return self._corsie[corsia]

    async def genera(self, nome: str, prompt: str, *, sistema: str = "") -> BaseModel | None:
        """Esegue la rotta: guardia di fase, corsia, retry dichiarati, tally.

        `None` = degrado (trasporto o schema, dopo i retry della rotta): il
        chiamante applica il SUO fallback — l'engine non ne inventa uno."""
        rotta = ROTTE[nome]
        self._guardia_fase(rotta)
        provider = self._corsie[rotta.corsia]
        conto = self.tally.setdefault(rotta.nome, ConsumoRotta())
        for _ in range(rotta.retry + 1):
            conto.chiamate += 1
            candidato = await provider.genera(prompt, rotta.schema, sistema=sistema)
            if candidato is not None:
                _rifinisci_prosa(candidato)
                if rotta.bonifica:
                    candidato = await self._bonifica(
                        rotta, provider, prompt, sistema, candidato, conto
                    )
                return candidato
        conto.degradi += 1
        return None

    async def _bonifica(
        self, rotta: Rotta, provider, prompt: str, sistema: str, candidato, conto
    ):
        """Il gate di FORMA (tabella REGOLE_SLOP): a violazione, UN giro di
        regia — stessa chiamata, con le violazioni come note. Si tiene il
        testo con MENO violazioni; la forma non blocca mai il gioco: al
        limite si accetta e si conta (`conto.slop`)."""
        trovato = _campo_prosa(candidato)
        if trovato is None:
            return candidato
        violazioni = misura_slop(trovato[1])
        for _ in range(retry_bonifica()):
            if not violazioni:
                break
            conto.regie += 1
            conto.chiamate += 1
            secondo = await provider.genera(
                f"{prompt}\n{righe_regia(violazioni)}", rotta.schema, sistema=sistema
            )
            if secondo is None:
                break  # trasporto giù: resta il primo — la regia non degrada mai
            _rifinisci_prosa(secondo)
            trovato2 = _campo_prosa(secondo)
            v2 = misura_slop(trovato2[1]) if trovato2 is not None else violazioni
            if len(v2) < len(violazioni):
                candidato, violazioni = secondo, v2
        conto.slop += len(violazioni)
        return candidato

    @staticmethod
    def _guardia_fase(rotta: Rotta) -> None:
        """Phase-gate PER CHIAMATA: una rotta dichiarata per una fase non parte
        mai nell'altra — strutturale, mai un check a mano nei chiamanti. (La
        query è `in_combattimento()`: la lettura-per-gate `leggi_fase` resta
        esclusiva di PhasedProcessor.)"""
        if rotta.fase is None:
            return
        combatte = in_combattimento()
        if rotta.fase is Fase.NARRAZIONE and combatte:
            raise RuntimeError(
                f"rotta {rotta.nome!r}: vive in NARRAZIONE, la fase corrente è COMBATTIMENTO"
            )
        if rotta.fase is Fase.COMBATTIMENTO and not combatte:
            raise RuntimeError(
                f"rotta {rotta.nome!r}: vive in COMBATTIMENTO, la fase corrente è NARRAZIONE"
            )
