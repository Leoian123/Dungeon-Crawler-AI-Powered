"""Stato del processo host web: la sessione UNICA, il thread del forum, i canali SSE.

Un processo = una partita: l'API di esper è a livello di modulo (World process-global)
e il bus del `Guscio` è unico — l'host web NON può servire più run concorrenti (ACV
§5.2). `StatoHost` è il possesso dell'host: la `SessioneGioco` adottata, il lock che
serializza gli ingressi nel motore (non rientrante), il thread del forum (accumulo di
TESTO in memoria di processo, non stato: la verità resta il World — C-4; la
ricostruzione dall'Archivio persistito è un secondo taglio) e le code degli abbonati
SSE. Importa SOLO `main` (composition root) e `contracts`: mai `motore`, mai esper
(membrana C-2a, verificata in tests/test_membrana_vista.py).
"""

from __future__ import annotations

import asyncio
from dataclasses import is_dataclass
from dataclasses import asdict as dataclass_asdict
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict

from contracts import (
    AnomalyTriggered,
    CombatResolved,
    DiscesaPiano,
    EncounterStarted,
    MessaggioGM,
    MortePersonaggio,
    SnapshotVista,
)
from main import CronacaBus, SessioneGioco

# Gli eventi di dominio inoltrati sul canale SSE (consumatore read-only, IC §2.3).
_EVENTI_DOMINIO: tuple[type, ...] = (
    EncounterStarted,
    CombatResolved,
    MortePersonaggio,
    AnomalyTriggered,
    DiscesaPiano,
)


class PostThread(BaseModel):
    """Un post del forum play-by-post.

    `genere="gm"`: un turno del GM (`MessaggioGM`: prosa + dove/come + tempo + prova).
    `genere="evento"`: righe di cronaca del bus (scontro iniziato, esito, discesa…).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int
    genere: str  # "gm" | "evento"
    messaggio: MessaggioGM | None = None
    righe: tuple[str, ...] = ()


class StatoHost:
    """La sessione unica del processo + versione-turno + thread + abbonati SSE.

    `versione` cresce di 1 a ogni ingresso nel motore che produce un nuovo snapshot:
    le POST di gioco la portano nel body e un valore stantio viene rifiutato (409) —
    gli indici delle opzioni valgono SOLO per lo snapshot corrente.
    """

    def __init__(self) -> None:
        self.sessione: SessioneGioco | None = None
        self.cronaca: CronacaBus | None = None
        self.lock = asyncio.Lock()  # il motore NON è rientrante: un ingresso alla volta
        self.versione = 0
        self.thread: list[PostThread] = []
        self.morto = False
        self.gm_etichetta = ""
        self.snapshot: SnapshotVista | None = None  # sostituito in blocco (C-4)
        self.live_vietato = False  # lancio con --fake: l'API non può chiedere il live
        self._abbonati: list[asyncio.Queue] = []
        self._coppie_bus: list[tuple[type, Callable[[object], None]]] = []

    # --- Ciclo di vita ------------------------------------------------------

    def adotta(self, sessione: SessioneGioco, etichetta: str) -> None:
        """Adotta la sessione appena costruita: cronaca, handler SSE, avanzamento."""
        self.sessione = sessione
        self.gm_etichetta = etichetta
        self.cronaca = CronacaBus(sessione.bus)
        sessione.on_avanzamento = self._su_avanzamento
        for tipo in _EVENTI_DOMINIO:
            handler = self._fai_handler(tipo)
            sessione.bus.registra(tipo, handler)
            self._coppie_bus.append((tipo, handler))

    def chiudi(self) -> None:
        """Deregistra tutto dal bus (process-global: gli handler non devono
        sopravvivere all'host — stessa disciplina di `CronacaBus.chiudi`)."""
        if self.cronaca is not None:
            self.cronaca.chiudi()
            self.cronaca = None
        if self.sessione is not None:
            for tipo, handler in self._coppie_bus:
                try:
                    self.sessione.bus.deregistra(tipo, handler)
                except ValueError:
                    pass
        self._coppie_bus = []

    # --- Il thread del forum ------------------------------------------------

    def registra_turno(
        self,
        snap: SnapshotVista,
        *,
        righe: list[str],
        messaggio: MessaggioGM | None,
    ) -> list[PostThread]:
        """Chiude un ingresso nel motore: nuovi post, snapshot rimpiazzato in blocco,
        versione incrementata, segnale `post` agli abbonati SSE."""
        nuovi: list[PostThread] = []
        if righe:
            nuovi.append(
                PostThread(id=len(self.thread), genere="evento", righe=tuple(righe))
            )
        if messaggio is not None:
            nuovi.append(
                PostThread(
                    id=len(self.thread) + len(nuovi), genere="gm", messaggio=messaggio
                )
            )
        self.thread.extend(nuovi)
        self.snapshot = snap
        self.versione += 1
        self.pubblica("post", {"versione": self.versione})
        return nuovi

    # --- Canale SSE (code per abbonato; un solo event loop ⇒ put_nowait) ------

    def sottoscrivi(self) -> asyncio.Queue:
        coda: asyncio.Queue = asyncio.Queue()
        self._abbonati.append(coda)
        return coda

    def disdici(self, coda: asyncio.Queue) -> None:
        try:
            self._abbonati.remove(coda)
        except ValueError:
            pass

    def pubblica(self, evento: str, dati: dict[str, Any]) -> None:
        for coda in self._abbonati:
            coda.put_nowait((evento, dati))

    # --- Callback dal motore (sincroni, sullo stesso event loop) --------------

    def _su_avanzamento(self, etichetta: str, frazione: float) -> None:
        # I 5 stadi della pipeline GM: l'unico segnale di latenza (niente streaming
        # token: il Provider ha un solo verbo `genera` — PLK §2).
        self.pubblica("progresso", {"etichetta": etichetta, "frazione": frazione})

    def _fai_handler(self, tipo: type) -> Callable[[object], None]:
        def handler(evento: object) -> None:
            dati = dataclass_asdict(evento) if is_dataclass(evento) else {}
            self.pubblica("evento_bus", {"tipo": tipo.__name__, "dati": dati})
            if tipo is MortePersonaggio:
                self.morto = True  # permadeath: terminale di run
                self.pubblica("morte", {"causa": getattr(evento, "causa", "")})

        return handler
