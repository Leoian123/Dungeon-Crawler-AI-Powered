"""Composition root della v1 — **headless**: cabla il motore e lo pilota senza UI.

Il game engine è indipendente dalla presentazione: una UI futura (web, Electron, TUI…)
si innesterà su questo stesso strato attraverso le **porte** di `SessioneGioco` e gli
eventi tipizzati del **bus** — tutto espresso sui DTO di `contracts`, mai sul `World`.
Qui non c'è nessuna dipendenza di presentazione: il motore resta ignaro dell'host (C-2a)
e nessun layer importa Textual (C-5). Questo modulo è la *colla* + un driver headless di
riferimento, non un layer con membrana.

`SessioneGioco` è la **porta** verso il motore vista da un qualunque host: produce la
narrazione (coroutine host-agnostica, `await`-abile da un worker UI o da `asyncio.run`),
drena gli intenti del giocatore sul turno e ricostruisce lo `SnapshotVista` da
renderizzare. Il giocatore gioca un incontro completo: narrazione → scelta →
combattimento deterministico → ritorno alla narrazione.

Nell'MVP il provider è il **FakeProvider** (offline, scriptato); il backend Anthropic
reale (fase 5) si innesta dietro la stessa interfaccia `genera`.
"""

from __future__ import annotations

import asyncio
import random
import tempfile
from pathlib import Path
from typing import Callable

from contracts import (
    AnomalyTriggered,
    Archetipo,
    Blocco,
    BusEventi,
    ClasseProva,
    CombatResolved,
    DiscesaPiano,
    Durata,
    EncounterStarted,
    EntitaGenerata,
    IntentoEsplorazione,
    MortePersonaggio,
    PlayerDiscende,
    PlayerSiMuove,
    Opzione,
    OpzioneVista,
    PlayerChoseOption,
    Grado,
    SnapshotVista,
    StatId,
    TipoAzione,
    TurnoNarrazione,
)
from guscio import Guscio
from motore import (
    MODEL_ID_DEFAULT,
    OpzioneScena,
    SpecNemico,
    componi_opzioni_scena,
    consuma_messaggi,
    dissolvi_mob,
    esegui_turno_narrazione,
    in_combattimento,
    ingaggia_combattimento,
    livello_corrente,
    mappa_to_dict,
    materializza_turno,
    max_hp,
    messaggi_pendenti,
    mob_corrente,
    proietta_scheda,
    protagonista,
    registra_mob,
    salva_run,
    segna_visitata,
    stanza_visitata,
    stat_eff,
    tenta_disimpegno,
    tick,
    travasa,
)
from provider import FakeProvider

# Menu di combattimento (MVP). Il menu di NARRAZIONE non è più cablato qui: lo compone
# il MOTORE dalla scena (`componi_opzioni_scena` sulla mappa) — la mappa dispone.
_MENU_COMBATTIMENTO = (OpzioneVista(indice=0, etichetta="Attacca", tipo=TipoAzione.COMBATTI),)


class SessioneGioco:
    """La porta motore↔host per la v1: narrazione async, intenti sul turno, snapshot.

    Possiede il run-World (via `Guscio`) e il provider. Non tiene una macchina di
    modo propria: il "modo" è la verità del motore (`in_combattimento()` + la scena
    composta dalla mappa). Vive nel composition root: può importare il motore —
    l'host (UI o driver headless) no, vi parla solo via porte.
    """

    def __init__(self, provider, *, directory: Path, seed: int = 0) -> None:
        self.provider = provider
        self.rng = random.Random(seed)
        self.guscio = Guscio(directory)
        self.guscio.nuova_partita(uuid="carl", destrezza=10, hp=30, seed=seed)
        self.bus = self.guscio.bus
        self.coda = self.guscio.coda  # CodaIntenti: l'host vi accoda gli intenti
        self._opzioni: tuple[OpzioneVista, ...] = ()
        self._scena: tuple[OpzioneScena, ...] = ()  # binding indice→azione di scena

    # --- Porte verso l'host ---------------------------------------------------

    async def prossima_narrazione(self) -> SnapshotVista:
        """Coroutine host-agnostica (un worker UI o `asyncio.run` la `await`-a, C-6).

        Il turno di narrazione è legato alla MAPPA: se la stanza corrente non è mai
        stata visitata, prepara il contesto, chiama l'AI (1 `genera`, gate, fallback),
        materializza l'entità e la **registra nella stanza** (il reveal è un contenuto
        della mappa). Una stanza già visitata non richiama l'AI. Il menu è la scena."""
        prosa = ""
        if not stanza_visitata():
            pent, _marker, _scheda = protagonista()
            proiezione = proietta_scheda(pent)
            risultato = await esegui_turno_narrazione(
                self.provider, livello=livello_corrente(), proiezione=proiezione, rng=self.rng
            )
            ent = materializza_turno(risultato, self.bus)  # può pubblicare AnomalyTriggered
            registra_mob(ent)  # il nemico rivelato appartiene alla stanza (la mappa dispone)
            segna_visitata()
            prosa = risultato.turno.prosa
        self._sincronizza_scena()
        return SnapshotVista(
            prosa=prosa,
            opzioni=self._opzioni,
            stato=self._descrittori(),
            fase="narrazione",
        )

    def avanza(self) -> SnapshotVista:
        """Il **turno del motore** per l'host (IC §7.1) — drenaggio UNIFICATO:

        1. `travasa` (Canale A, l'unico travaso coda→World): il port NON preleva più
           dalla coda in proprio e NON scarta nulla;
        2. consuma SOLO gli intenti di menu (`PlayerChoseOption`) e li interpreta
           sulla fase corrente del motore e sulla scena mostrata;
        3. gli intenti di DOMINIO restano nel World per i sistemi phase-gated: quelli
           di esplorazione si servono su un turno del motore in NARRAZIONE (qui sotto);
           in COMBATTIMENTO attendono la fine dello scontro — la separazione
           esplorazione/combattimento è il phase-gate, non un filtro del port."""
        travasa(self.coda)
        for intento in consuma_messaggi(PlayerChoseOption):
            self._agisci(intento.opzione)
        travasa(self.coda)  # le scelte di scena possono aver accodato intenti di dominio
        if not in_combattimento() and messaggi_pendenti(IntentoEsplorazione):
            tick()  # un atto di esplorazione = un turno del motore (movimento, discesa)
        self._sincronizza_scena()
        return self._snapshot_corrente()

    def salva(self) -> str:
        """Salvataggio a mano, in-run (H-6): il World sopravvive, scrittura prima di
        ogni teardown. La mappa viaggia nello slot `esplorazione`."""
        salva_run(self.guscio.directory, model_id=MODEL_ID_DEFAULT, esplorazione=mappa_to_dict())
        return "Partita salvata."

    # --- Interpretazione delle scelte (sulla verità del motore, non su un modo) -

    def _agisci(self, indice: int) -> None:
        if in_combattimento():
            if 0 <= indice < len(_MENU_COMBATTIMENTO):
                self._agisci_combattimento()
        elif 0 <= indice < len(self._scena):
            self._agisci_narrazione(self._scena[indice])

    def _agisci_narrazione(self, azione: OpzioneScena) -> None:
        if azione.tipo is TipoAzione.SCENDI:
            self.coda.accoda(PlayerDiscende())  # la serve SistemaDiscesa (gate: scala)
            return
        if azione.tipo is TipoAzione.MUOVI and azione.stanza is not None:
            self.coda.accoda(PlayerSiMuove(azione.stanza))  # la serve SistemaMovimento
            return
        if azione.tipo is TipoAzione.SCAPPA:
            # Disimpegno: prova su stat PRIMA di ingaggiare (FNC §5.3, tirata dal motore).
            # La destrezza passa dal fold (GR2-3), non da un campo della scheda.
            pent, _m, _scheda = protagonista()
            if tenta_disimpegno(stat_eff(pent, StatId.DESTREZZA), ClasseProva.BRONZO, self.rng):
                dissolvi_mob()  # fuga riuscita: l'incontro si dissolve, la scena si riapre
                return
        # Combatti (o disimpegno fallito): l'incontro è il nemico DELLA STANZA, arruolato
        # col suo profilo calibrato (Primarie/Corredo/Resistenze). Il fallback per scalari
        # resta solo per robustezza (scena senza mob registrato).
        mob = mob_corrente()
        ingaggia_combattimento(
            self.bus,
            nemici=None if mob is not None else [SpecNemico(destrezza=5, punti_vita=3)],
            arruolate=[mob] if mob is not None else None,
            seed=self.rng.randint(0, 10**9),
        )

    def _agisci_combattimento(self) -> None:
        tick()  # un turno di combattimento risolto (deterministico, seeded)

    def _sincronizza_scena(self) -> None:
        """Riallinea il menu alla verità del motore: in combattimento il menu di
        combattimento; altrimenti la SCENA composta dalla mappa. Scena vuota = stanza
        mai narrata ⇒ menu vuoto ⇒ l'host chiede un turno di narrazione."""
        if in_combattimento():
            self._scena = ()
            self._opzioni = _MENU_COMBATTIMENTO
            return
        self._scena = componi_opzioni_scena()
        self._opzioni = tuple(
            OpzioneVista(indice=i, etichetta=az.etichetta, tipo=az.tipo)
            for i, az in enumerate(self._scena)
        )

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
        hp = f"HP {scheda.punti_vita}/{max_hp(pent)}"  # massimo DERIVATO (§5)
        return (hp, *proietta_scheda(pent).descrittori)


# --- Cronaca del bus: eventi di dominio → righe di testo (headless, read-only) ----
#
# Lo stesso ruolo "consumatore read-only di eventi" che avrà una UI (IC §2.3), qui
# ridotto a testo: l'host headless si sottoscrive al bus e raccoglie ciò che il motore
# emette. Una UI futura sostituirà questo collettore senza toccare il motore.
_MAPPA_EVENTI: tuple[tuple[type, Callable[[object], str]], ...] = (
    (EncounterStarted, lambda _e: "Lo scontro ha inizio."),
    (CombatResolved, lambda e: (
        "Hai vinto lo scontro." if getattr(e, "vittoria", False) else "Lo scontro si chiude."
    )),
    (MortePersonaggio, lambda e: f"Sei morto: {getattr(e, 'causa', '')}."),
    (AnomalyTriggered, lambda _e: "Il dungeon ride: qualcosa è fuori scala…"),
    (DiscesaPiano, lambda e: f"Scendi: piano {getattr(e, 'piano', '?')}."),
)


class CronacaBus:
    """Raccoglie gli eventi di dominio dal bus e li rende come righe (host headless)."""

    def __init__(self, bus: BusEventi) -> None:
        self._bus = bus
        self._righe: list[str] = []
        self._coppie: list[tuple[type, Callable[[object], None]]] = []
        for tipo, formatta in _MAPPA_EVENTI:
            handler = self._fai_handler(formatta)
            bus.registra(tipo, handler)
            self._coppie.append((tipo, handler))

    def _fai_handler(self, formatta: Callable[[object], str]) -> Callable[[object], None]:
        def handler(evento: object) -> None:
            self._righe.append(formatta(evento))
        return handler

    def preleva(self) -> list[str]:
        """Restituisce e svuota le righe accumulate dall'ultima chiamata."""
        righe, self._righe = self._righe, []
        return righe

    def chiudi(self) -> None:
        """Deregistra gli handler: il bus è process-global, sopravvive all'host."""
        for tipo, handler in self._coppie:
            self._bus.deregistra(tipo, handler)
        self._coppie = []


def _turni_scriptati() -> list[TurnoNarrazione]:
    """Contenuto scriptato per il provider fake (offline). Esauriti, l'orchestrazione
    degrada al fallback deterministico (turno neutro): il gioco non si blocca mai."""
    return [
        TurnoNarrazione(
            prosa="Un corridoio umido gocciola luce verde. Uno Slime Mangiascarti ribolle "
            "tra rifiuti e un Rolex digerito.",
            entita=EntitaGenerata(
                archetipo=Archetipo.SLIME,
                grado=Grado.BRONZO,
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


def costruisci_sessione(*, seed: int = 0, directory: Path | None = None) -> SessioneGioco:
    """Cabla provider fake → `SessioneGioco` (la porta del motore vista dall'host)."""
    directory = directory or Path(tempfile.mkdtemp(prefix="dcc-"))
    provider = FakeProvider([t.model_dump() for t in _turni_scriptati()])
    return SessioneGioco(provider, directory=directory, seed=seed)


def _rendi(snapshot: SnapshotVista, stampa: Callable[[str], None]) -> None:
    """Rende uno snapshot come testo (sostituito in blocco, C-4)."""
    if snapshot.prosa:
        stampa(snapshot.prosa)
    stato = ", ".join(snapshot.stato) if snapshot.stato else "—"
    stampa(f"[{snapshot.fase}] {stato}")
    for opz in snapshot.opzioni:
        stampa(f"  {opz.indice + 1}. {opz.etichetta}")


def _passo(
    sessione: SessioneGioco, indice: int, cronaca: CronacaBus, stampa: Callable[[str], None]
) -> SnapshotVista:
    """Un passo dell'host: accoda un intento tipizzato (host→motore, C-7), avanza il
    turno, drena la cronaca del bus e rende lo snapshot risultante."""
    sessione.coda.accoda(PlayerChoseOption(indice))
    snapshot = sessione.avanza()
    for riga in cronaca.preleva():
        stampa(riga)
    _rendi(snapshot, stampa)
    return snapshot


async def gioca_un_incontro(
    sessione: SessioneGioco,
    *,
    stampa: Callable[[str], None] = print,
    limite: int = 100,
) -> SnapshotVista:
    """Driver headless di riferimento: gioca un incontro completo via le sole porte.

    Narrazione (await della coroutine) → "Combatti" → "Attacca" finché lo scontro non si
    chiude e si torna alla narrazione. È la prova che il game engine gira end-to-end
    senza alcuna UI: una presentazione reale farebbe gli stessi passi via i suoi widget.
    """
    cronaca = CronacaBus(sessione.bus)
    try:
        snapshot = await sessione.prossima_narrazione()
        _rendi(snapshot, stampa)
        snapshot = _passo(sessione, 0, cronaca, stampa)  # "Combatti" → ingaggia
        guardia = 0
        while snapshot.fase == "combattimento" and guardia < limite:
            snapshot = _passo(sessione, 0, cronaca, stampa)  # "Attacca"
            guardia += 1
        return snapshot
    finally:
        cronaca.chiudi()


def main() -> None:  # pragma: no cover (entry point)
    sessione = costruisci_sessione(seed=1)
    asyncio.run(gioca_un_incontro(sessione))


if __name__ == "__main__":  # pragma: no cover
    main()
