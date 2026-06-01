"""La macchina-guscio: orchestrazione a livello app del ciclo vita cross-World (nodo E).

`boot → menu/slot → run → (sconfitta | piano-completato | uscita volontaria) → menu`
(ACV §1). Il guscio **orchestra** i confini guscio↔run: decide il *quando* e **chiama** le
operazioni di contesto del livello save/load (H), che è l'**unica autorità su
`current_world`** (ESP §0.1) e possiede il *come* (ACV §0). `switch_world`/`delete_world`
**non compaiono qui**: vivono in H. Il guscio non li mette **mai** in un Processor, in un
handler di dominio, né dentro un `process()` in volo (E-2/E-4).

Decisioni strutturali recepite:
  - **Stato del guscio = orchestrazione a livello app** (E-7): questa classe, non un
    World; nessun Processor di guscio. Lo stato del guscio **non** si serializza col save
    della run (E-3): vive qui, non nel blob.
  - **Bus UNO, process-global** (E-9): costruito al boot, fuori da ogni run-World,
    sopravvive ai run-World. Gli handler **in-run** si deregistrano al teardown.
  - **Due primitive, mai scambiate** (E-1): il cambio di World (via H) **solo** al confine
    guscio↔run; le fasi `NARRAZIONE ⇄ COMBATTIMENTO` restano intra-run sul bus (motore).
  - **Lifecycle del protagonista cross-World** (E-5): nasce (nuova partita) o si
    deserializza (caricamento) **esattamente** al confine guscio→run, mai a una fase.
  - **Tre terminali, una cucitura** (E-8): detection in-run sul bus, teardown nella shell
    dopo che il loop cede il controllo. Gli esiti di combattimento **vittoria/fuga**
    tornano a `NARRAZIONE` (bus, in-run) e **non** sono terminali.

Host-agnostica: nessun import di Textual. Il loop di run è una coroutine (IC §6),
guidata dal turno, eseguibile headless.
"""

from __future__ import annotations

import inspect
from enum import Enum
from pathlib import Path

from contracts import BusEventi, DiscesaPiano, MortePersonaggio
from motore import (
    Fase,
    MODEL_ID_DEFAULT,
    NOME_DEFAULT,
    NOME_RUN,
    SistemaBrucia,
    SistemaDeathCheck,
    SistemaDiscesa,
    SistemaRigenerazione,
    SistemaRinforzi,
    SistemaStordito,
    SistemaTurnoCombattimento,
    SistemaVeleno,
    avvia_run,
    carica_crawler,
    collega_combattimento,
    collega_transizioni_fase,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_tempo_piano,
    entra_run_nuova,
    invalida,
    parcheggia_default,
    protagonista,
    salva_run,
    teardown_run,
    tick,
)

# Le primitive di contesto (`switch_world`/`delete_world`) NON vivono qui: l'autorità su
# `current_world` è del livello save/load (ESP §0.1, H). Il guscio **orchestra** — decide
# il *quando* — chiamando le operazioni di confine di H (`entra_run_nuova`,
# `carica_crawler`, `teardown_run`, `parcheggia_default`); H possiede il *come* (ACV §0).
# `NOME_RUN`/`NOME_DEFAULT` sono importati da H (è H che possiede il nome del contesto).


class StatoGuscio(Enum):
    """Lo stato della macchina-guscio. NON si serializza col save (E-3)."""

    BOOT = "boot"
    MENU = "menu"
    IN_RUN = "in_run"


class Terminale(Enum):
    """I tre terminali run→guscio (E-8). Gli esiti vittoria/fuga NON sono qui."""

    SCONFITTA = "sconfitta"               # 6a — death-check seeded → MortePersonaggio
    PIANO_COMPLETATO = "piano_completato"  # 6b — DiscesaPiano (nell'MVP, un piano → vittoria)
    USCITA_VOLONTARIA = "uscita_volontaria"  # 6c — intento del giocatore


class Guscio:
    """La shell orchestration. Possiede il bus process-global e la macchina del ciclo
    vita; **orchestra** i confini guscio↔run delegando il cambio di `current_world` a H
    (l'unica autorità, ESP §0.1)."""

    def __init__(self, directory, *, model_id: str = MODEL_ID_DEFAULT) -> None:
        self.directory = Path(directory)
        self.model_id = model_id
        # BOOT: il bus nasce qui, app-level, fuori da ogni run-World (E-9).
        self.bus = BusEventi()
        self.stato = StatoGuscio.BOOT
        self.coda = None
        self._uuid: str | None = None
        self._terminale: Terminale | None = None
        self._coppie_in_run: list[tuple[type, object]] = []
        self._boot()

    # --- BOOT → MENU ---------------------------------------------------------

    def _boot(self) -> None:
        """Parcheggia nel default World (contesto residente del guscio) ed entra nel menu.
        Il cambio di contesto lo esegue H (`parcheggia_default`): il guscio lo *orchestra*."""
        parcheggia_default()
        self.stato = StatoGuscio.MENU

    # --- Assemblaggio dei sistemi della run (Processor del MOTORE, non del guscio) -

    def _sistemi_run(self):
        return dict(
            sempre_attivi=[
                SistemaVeleno(),
                SistemaBrucia(),
                SistemaRigenerazione(),
                SistemaStordito(),
                SistemaDeathCheck(self.bus),
            ],
            solo_combattimento=[SistemaRinforzi(), SistemaTurnoCombattimento(self.bus)],
            solo_narrazione=[SistemaDiscesa(self.bus)],
        )

    def _registra_handler_run(self) -> None:
        """Registra gli handler **in-run** sul bus process-global e li traccia per il
        teardown (E-9). Engine: transizioni di fase + ciclo vita combattimento. Shell:
        la **detection dei terminali** (morte, piano-completato)."""
        coppie: list[tuple[type, object]] = []
        coppie += collega_transizioni_fase(self.bus)
        coppie += collega_combattimento(self.bus)
        for tipo, handler in ((MortePersonaggio, self._su_morte), (DiscesaPiano, self._su_discesa)):
            self.bus.registra(tipo, handler)
            coppie.append((tipo, handler))
        self._coppie_in_run = coppie

    def _deregistra_handler_run(self) -> None:
        """Deregistra gli handler in-run al teardown: il bus è process-global e
        sopravvive alla run (E-9)."""
        for tipo, handler in self._coppie_in_run:
            self.bus.deregistra(tipo, handler)
        self._coppie_in_run = []

    # --- Detection dei terminali (in-run, sul bus): solo segnale, MAI switch ---

    def _su_morte(self, _evento: MortePersonaggio) -> None:
        """Terminale di perdita (6a). Solo un flag: il teardown è nella shell (E-4)."""
        self._terminale = Terminale.SCONFITTA

    def _su_discesa(self, _evento: DiscesaPiano) -> None:
        """Piano-completato (6b): nell'MVP (un piano) la `DiscesaPiano` è la vittoria
        della run (G §6.7). Solo un flag, nessuno switch in volo (E-4)."""
        self._terminale = Terminale.PIANO_COMPLETATO

    # --- Ingresso run: protagonista NASCE o si DESERIALIZZA, solo qui (E-5) ----

    def nuova_partita(
        self, uuid: str = "carl", *, destrezza: int = 10, hp: int = 30, seed: int = 0
    ) -> None:
        """Confine guscio→run, nuova partita (3a): `"run"` fresco e il protagonista
        **nasce** qui (Carl predefinito, G §6.5). Mai a una transizione di fase (E-5)."""
        assert self.stato == StatoGuscio.MENU, self.stato
        entra_run_nuova()  # H esegue lo switch al `"run"` fresco; il guscio lo orchestra
        # I singleton di stato nascono qui; `FaseCorrente` la crea `avvia_run`.
        crea_profondita()
        crea_seme(seed)
        crea_tempo_piano()
        crea_protagonista(destrezza=destrezza, punti_vita=hp, id_dominio=uuid)
        self.coda = avvia_run(crea_singleton_fase=True, fase_iniziale=Fase.NARRAZIONE, **self._sistemi_run())
        self._registra_handler_run()
        self._uuid = uuid
        self._terminale = None
        self.stato = StatoGuscio.IN_RUN

    def carica(self, uuid: str) -> bool:
        """Confine guscio→run, caricamento (3b): delega a H (`carica_crawler`), che
        valida **prima** (niente switch su fallimento) e poi deserializza nel `"run"`
        fresco — `FaseCorrente` torna col save (E-5). Ritorna `False` se illeggibile
        (si resta nel MENU, `current_world` intatto — E-4/H-12)."""
        assert self.stato == StatoGuscio.MENU, self.stato
        if not carica_crawler(self.directory, uuid):
            return False  # resta nel MENU, current_world INTATTO
        # `FaseCorrente` è tornata col save → non crearne una seconda.
        self.coda = avvia_run(crea_singleton_fase=False, **self._sistemi_run())
        self._registra_handler_run()
        self._uuid = uuid
        self._terminale = None
        self.stato = StatoGuscio.IN_RUN
        return True

    # --- Uscita volontaria (6c): intento del giocatore, solo detection ---------

    def esci_volontariamente(self) -> None:
        """Intento del giocatore (6c): segnala il terminale. NON fa switch_world — è
        solo detection in-run; il teardown è in `concludi` (E-4)."""
        assert self.stato == StatoGuscio.IN_RUN, self.stato
        self._terminale = Terminale.USCITA_VOLONTARIA

    # --- Loop di run host-agnostico (coroutine, guidata dal turno) -------------

    async def esegui_run(self, conducente=None, *, max_turni: int = 10_000) -> Terminale:
        """Gira la run finché un terminale è rilevato sul bus (in-run), poi **cede il
        controllo** (E-4: il teardown lo fa la shell, in `concludi`, non qui).

        `conducente(self)` è il driver host-agnostico di un turno (inietta intenti o,
        nei test, muta lo stato di prova); può essere sync o coroutine.
        """
        assert self.stato == StatoGuscio.IN_RUN, self.stato
        for _ in range(max_turni):
            if conducente is not None:
                esito = conducente(self)
                if inspect.isawaitable(esito):
                    await esito
            if self._terminale is not None:  # es. uscita volontaria
                return self._terminale
            tick()  # un turno del motore (FNC §6.4)
            if self._terminale is not None:  # morte / piano-completato
                return self._terminale
        raise RuntimeError("run non terminata entro max_turni")

    # --- La cucitura unica: hand-off del terminale (E-4, E-8) ------------------

    def concludi(self) -> Terminale:
        """Esegue l'hand-off del terminale rilevato (stessa cucitura per 6a/6b/6c):

        1. **save-wiring PRIMA dello switch** (World ancora vivo): uscita volontaria
           **salva**; morte (6a) e piano-completato (6b) **invalidano** (E-8 / H-20);
        2. deregistra gli handler in-run (il bus sopravvive, E-9);
        3. **teardown** delegato a H (`teardown_run`: `switch_world(default)` →
           `delete_world("run")`, E-6) — chiamato dalla shell, fuori da ogni handler (E-4).

        Da chiamare **dopo** che `esegui_run` ha ceduto il controllo: mai in un handler.
        """
        assert self.stato == StatoGuscio.IN_RUN and self._terminale is not None
        terminale = self._terminale
        uuid = self._uuid

        if terminale is Terminale.USCITA_VOLONTARIA:
            salva_run(self.directory, model_id=self.model_id)
        else:  # SCONFITTA (6a) o PIANO_COMPLETATO (6b): fine-run → invalida
            if uuid is not None:
                invalida(self.directory, uuid)

        self._deregistra_handler_run()
        teardown_run()  # H esegue lo switch+delete; il guscio lo orchestra, fuori da un handler

        self.coda = None
        self._uuid = None
        self._terminale = None
        self.stato = StatoGuscio.MENU
        return terminale

    def _abbandona_run(self) -> None:
        """Pulizia d'emergenza se il loop di run solleva PRIMA di un terminale: deregistra
        gli handler in-run e smonta il run-World **senza save-wiring** (nessun terminale
        valido). Mantiene l'invariante E-9 (handler deregistrati al teardown) anche su
        eccezione; il bus process-global non resta con handler orfani."""
        if self.stato != StatoGuscio.IN_RUN:
            return
        self._deregistra_handler_run()
        teardown_run()
        self.coda = None
        self._uuid = None
        self._terminale = None
        self.stato = StatoGuscio.MENU

    # --- Convenienze: macchina completa nuova-partita / caricamento -----------

    async def gioca_nuova_partita(self, conducente=None, *, uuid: str = "carl", **kw) -> Terminale:
        """Giro completo: nuova partita → loop → hand-off → menu. Ritorna il terminale."""
        self.nuova_partita(uuid, **kw)
        try:
            await self.esegui_run(conducente)
        except BaseException:
            self._abbandona_run()  # niente handler orfani sul bus process-global (E-9)
            raise
        return self.concludi()

    async def gioca_caricamento(self, conducente=None, *, uuid: str) -> Terminale | None:
        """Giro completo da save: carica → loop → hand-off → menu. `None` se il save è
        illeggibile (si resta nel menu)."""
        if not self.carica(uuid):
            return None
        try:
            await self.esegui_run(conducente)
        except BaseException:
            self._abbandona_run()
            raise
        return self.concludi()
