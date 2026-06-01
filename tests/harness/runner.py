"""HeadlessRun — runner del motore senza Textual e senza rete (criterio C-5).

Mette insieme i tre pezzi dell'arnia:
  - un `NullAdapter` che raccoglie gli eventi di dominio emessi (motore → vista);
  - una **coda degli intenti** in cui iniettare intenti scriptati (vista → motore),
    drenata **una volta per turno** prima dei sistemi — il modello della coda
    drenata-dal-turno di IC §7.1 (non sul tempo di parete);
  - un aggancio per un `FakeProvider` (offline), da usare quando arriverà la
    narrazione AI.

Disciplina dei contesti esper (ESP §0.1): questo runner **non** chiama
`switch_world`. Gira nel mondo già attivo — nei test è il mondo isolato fornito
dalla fixture `mondo_isolato` di `conftest.py`. Il cambio di contesto vive solo al
confine guscio↔run (`src/guscio`), non nell'arnia.

In questa fase non c'è ancora logica di gioco: `process_turn()` chiama
`esper.process()` (che con zero Processor è un no-op) dopo aver drenato gli intenti.
Lo scheletro dimostra il seam: parte e si chiude pulito.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Callable

import esper

from .null_adapter import NullAdapter
from .fake_provider import FakeProvider


class HeadlessRun:
    def __init__(
        self,
        adapter: NullAdapter | None = None,
        provider: FakeProvider | None = None,
    ) -> None:
        self.adapter = adapter if adapter is not None else NullAdapter()
        self.provider = provider if provider is not None else FakeProvider()
        # Coda degli intenti lato motore (IC §7.1). I "widget"/lo script accodano qui.
        self._intents: deque[Any] = deque()
        self.turn = 0
        # Handler di drenaggio degli intenti, opzionale: in questa fase nessuna
        # logica li consuma, quindi li accumuliamo come `drained_intents` per gli
        # assert dei test. Quando il motore avrà il Processor-drenaggio, sostituirà
        # questo callback senza cambiare il seam.
        self.drained_intents: list[Any] = []
        self._intent_sink: Callable[[Any], None] = self.drained_intents.append

    # --- vista → motore: iniezione di intenti scriptati -----------------------
    def inject_intent(self, intent: Any) -> None:
        """Accoda un intento tipizzato (come farebbe un widget)."""
        self._intents.append(intent)

    def set_intent_sink(self, sink: Callable[[Any], None]) -> None:
        """Sostituisce il consumatore degli intenti drenati (futuro: Processor)."""
        self._intent_sink = sink

    # --- motore → vista: emissione di eventi di dominio -----------------------
    def emit(self, event: Any) -> None:
        """Punto da cui il motore pubblica un evento di dominio verso l'adattatore."""
        self.adapter.on_event(event)

    # --- avanzamento guidato dal turno ---------------------------------------
    def _drain_intents(self) -> None:
        """Drena la coda UNA volta, all'inizio del turno (IC §7.1)."""
        while self._intents:
            self._intent_sink(self._intents.popleft())

    def process_turn(self) -> None:
        """Un turno: drena gli intenti, poi fa girare i Processor (esper.process)."""
        self._drain_intents()
        esper.process()  # con zero Processor è un no-op deterministico
        self.turn += 1

    def run(self, turns: int = 1) -> None:
        """Fa girare `turns` turni. L'avanzamento è guidato dal turno, non dall'orologio."""
        for _ in range(turns):
            self.process_turn()
