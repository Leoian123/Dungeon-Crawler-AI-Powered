"""Composition root della v1: cabla il motore (headless) all'adattatore Textual.

È l'**unico** punto che importa entrambi i lati della membrana — `adattatore` (Textual) e
`motore`/`guscio`/`provider`. Non è un layer con membrana: è la *colla*. Il motore resta
ignaro di Textual (C-2a); l'adattatore resta ignaro del `World` (C-2b); qui si incontrano.

`SessioneGioco` è la **porta** verso il motore vista dall'adattatore: produce la
narrazione (coroutine host-agnostica, per il worker), drena gli intenti del giocatore sul
turno e ricostruisce lo `SnapshotVista` da renderizzare. Il giocatore gioca un incontro
completo: narrazione → scelta → combattimento deterministico → ritorno alla narrazione.

Nell'MVP il provider è il **FakeProvider** (offline, scriptato); il backend Anthropic
reale (fase 5) si innesta dietro la stessa interfaccia `genera`.
"""

from __future__ import annotations

import random
import tempfile
from pathlib import Path

from adattatore import GiocoApp
from contracts import (
    Archetipo,
    Blocco,
    ClasseProva,
    Durata,
    EntitaGenerata,
    Opzione,
    OpzioneVista,
    PlayerChoseOption,
    Rarita,
    SnapshotVista,
    TipoAzione,
    TurnoNarrazione,
)
from guscio import Guscio
from motore import (
    MODEL_ID_DEFAULT,
    SpecNemico,
    esegui_turno_narrazione,
    in_combattimento,
    ingaggia_combattimento,
    livello_corrente,
    materializza_turno,
    proietta_scheda,
    protagonista,
    salva_run,
    tenta_disimpegno,
    tick,
)
from provider import FakeProvider

# Menu di narrazione (MVP): il terzetto noto ridotto a Combatti/Scappi (IC §7, niente creep).
_MENU_NARRAZIONE = (
    OpzioneVista(indice=0, etichetta="Combatti", tipo=TipoAzione.COMBATTI),
    OpzioneVista(indice=1, etichetta="Scappi", tipo=TipoAzione.SCAPPA),
)
_MENU_COMBATTIMENTO = (OpzioneVista(indice=0, etichetta="Attacca", tipo=TipoAzione.COMBATTI),)


class SessioneGioco:
    """La porta motore↔vista per la v1: narrazione async, intenti sul turno, snapshot.

    Possiede il run-World (via `Guscio`), il provider e una piccola macchina di modo
    (attesa-narrazione / scelta-narrazione / combattimento). Vive nel composition root:
    può importare il motore — l'adattatore no.
    """

    def __init__(self, provider, *, directory: Path, seed: int = 0) -> None:
        self.provider = provider
        self.rng = random.Random(seed)
        self.guscio = Guscio(directory)
        self.guscio.nuova_partita(uuid="carl", destrezza=10, hp=30, seed=seed)
        self.bus = self.guscio.bus
        self.coda = self.guscio.coda  # CodaIntenti: i widget vi accodano gli intenti
        self._modo = "attesa_narrazione"
        self._opzioni: tuple[OpzioneVista, ...] = ()

    # --- Porte verso l'adattatore --------------------------------------------

    async def prossima_narrazione(self) -> SnapshotVista:
        """Coroutine host-agnostica (il worker la `await`-a, C-6): prepara il contesto,
        chiama l'AI (1 `genera`, gate, fallback) e materializza l'entità. Ritorna lo
        snapshot con prosa + menu di narrazione."""
        pent, _marker, _scheda = protagonista()
        proiezione = proietta_scheda(pent)
        risultato = await esegui_turno_narrazione(
            self.provider, livello=livello_corrente(), proiezione=proiezione, rng=self.rng
        )
        materializza_turno(risultato, self.bus)  # può pubblicare AnomalyTriggered (reveal)
        self._modo = "scelta_narrazione"
        self._opzioni = _MENU_NARRAZIONE
        return SnapshotVista(
            prosa=risultato.turno.prosa,
            opzioni=self._opzioni,
            stato=self._descrittori(),
            fase="narrazione",
        )

    def avanza(self) -> SnapshotVista:
        """Il **turno del motore** per la UI: drena la coda degli intenti (vista→motore,
        IC §7.1) e li serve nella fase corrente, poi ricostruisce lo snapshot. Gli
        intenti stanno nella coda tra l'emissione del widget e questo turno (mai nel bus)."""
        for intento in self.coda.preleva_tutti():
            if isinstance(intento, PlayerChoseOption):
                self._agisci(intento.opzione)
        return self._snapshot_corrente()

    def salva(self) -> str:
        """Salvataggio a mano, in-run (H-6): il World sopravvive, scrittura prima di
        ogni teardown. Ritorna il messaggio da mostrare."""
        salva_run(self.guscio.directory, model_id=MODEL_ID_DEFAULT)
        return "Partita salvata."

    # --- Macchina di modo (interpretazione delle scelte) ----------------------

    def _agisci(self, indice: int) -> None:
        if not (0 <= indice < len(self._opzioni)):
            return
        if self._modo == "scelta_narrazione":
            self._agisci_narrazione(self._opzioni[indice])
        elif self._modo == "combattimento":
            self._agisci_combattimento()

    def _agisci_narrazione(self, opzione: OpzioneVista) -> None:
        if opzione.tipo is TipoAzione.SCAPPA:
            # Disimpegno: prova su stat PRIMA di ingaggiare (FNC §5.3, tirata dal motore).
            _p, _m, scheda = protagonista()
            if tenta_disimpegno(scheda.destrezza, ClasseProva.BRONZO, self.rng):
                self._attendi_narrazione()  # fuga riuscita → nuovo turno
                return
        # Combatti (o disimpegno fallito): si compone l'incontro e si ingaggia a confine.
        ingaggia_combattimento(
            self.bus,
            nemici=[SpecNemico(destrezza=5, punti_vita=3)],
            seed=self.rng.randint(0, 10**9),
        )
        self._modo = "combattimento"
        self._opzioni = _MENU_COMBATTIMENTO

    def _agisci_combattimento(self) -> None:
        tick()  # un turno di combattimento risolto (deterministico, seeded)
        if not in_combattimento():  # CombatResolved ha riportato in NARRAZIONE
            self._attendi_narrazione()

    def _attendi_narrazione(self) -> None:
        self._modo = "attesa_narrazione"
        self._opzioni = ()  # menu vuoto ⇒ l'adattatore lancia il worker per il turno

    # --- Costruzione dello snapshot dal World corrente ------------------------

    def _snapshot_corrente(self) -> SnapshotVista:
        return SnapshotVista(
            prosa="",  # la prosa di transizione arriva via eventi sul bus
            opzioni=self._opzioni,
            stato=self._descrittori(),
            fase="combattimento" if in_combattimento() else "narrazione",
        )

    def _descrittori(self) -> tuple[str, ...]:
        pent, _marker, scheda = protagonista()
        hp = f"HP {scheda.punti_vita}/{scheda.punti_vita_max}"
        return (hp, *proietta_scheda(pent).descrittori)


def _turni_scriptati() -> list[TurnoNarrazione]:
    """Contenuto scriptato per il provider fake (offline). Esauriti, l'orchestrazione
    degrada al fallback deterministico (turno neutro): il gioco non si blocca mai."""
    return [
        TurnoNarrazione(
            prosa="Un corridoio umido gocciola luce verde. Uno Slime Mangiascarti ribolle "
            "tra rifiuti e un Rolex digerito.",
            entita=EntitaGenerata(
                archetipo=Archetipo.SLIME,
                rarita=Rarita.COMUNE,
                blocchi=[Blocco.VELENO],
                nome="Slime Mangiascarti",
                descrizione="Verde, acido, vagamente offeso dalla tua presenza.",
            ),
            opzioni=[
                Opzione(tipo=TipoAzione.COMBATTI, etichetta="Combatti"),
                Opzione(tipo=TipoAzione.SCAPPA, etichetta="Scappi"),
            ],
            durata=Durata.TURNO,
        ),
    ]


def costruisci_app(*, seed: int = 0, directory: Path | None = None) -> GiocoApp:
    """Cabla provider fake → `SessioneGioco` → `GiocoApp` (iniezione delle porte)."""
    directory = directory or Path(tempfile.mkdtemp(prefix="dcc-"))
    provider = FakeProvider([t.model_dump() for t in _turni_scriptati()])
    sessione = SessioneGioco(provider, directory=directory, seed=seed)
    return GiocoApp(
        bus=sessione.bus,
        prossima_narrazione=sessione.prossima_narrazione,
        avanza=sessione.avanza,
        accoda_intento=sessione.coda.accoda,
        salva=sessione.salva,
    )


def main() -> None:  # pragma: no cover (entry point interattivo)
    costruisci_app().run()


if __name__ == "__main__":  # pragma: no cover
    main()
