"""Modello del tempo: strato di scorrimento + primitive di tempo (nodo J).

Il **tick core condiviso** (status → death-check) è già costruito (fasi 3–4): gira a
ogni `process()` risolto, in entrambe le fasi, posseduto da G in combattimento. Qui J
**aggiunge** ciò che vive **solo fuori combattimento** (§2.2):

  - il **contatore di tempo-piano** che avanza al tick condiviso (`SistemaTempoPiano`,
    sempre-attivo, un solo proprietario — J-14);
  - i due **meccanismi di scorrimento** — **passa-turno** (un tick manuale token-zero,
    §6) e **fast-forward** (downtime, comprime N tick, §5) — ciascuno un **tick di
    scorrimento** che estende il core con **dado-evento** (tiro seeded, §8) ed **effetto
    a confine** (es. imboscata → `EncounterStarted`, §9).

Invarianti rispettati:
  - *Il tempo avanza SOLO per tick risolti, mai per orologio* (J-4): qui non c'è
    `sleep`/timer; un avanzamento è un `process()`. Il tempo narrato è lettura, non
    avanzamento (§1).
  - *J non avanza gli status per conto suo* (J-5): il tick di scorrimento chiama
    `process()` e lascia che l'unico proprietario (bucket sempre-attivo) li muova.
  - *Ordine del tick* (J-11): status → death-check → (**morte ⇒ fine tick, niente
    dado**) → dado-evento → effetto a confine. La **morte tronca** prima dell'evento.
  - *In combattimento i passi 3–4 NON girano* (J-17): passa-turno/fast-forward sono
    disabilitati dai predicati-safe appena `FaseCorrente == COMBATTIMENTO` (J-13). La
    mutazione dello scontro è il binario di G §5, non un dado generico.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

import esper

from contracts import EncounterStarted

from .catalogo import PROB_IMBOSCATA, e_dannoso, e_unsafe, gate_durata, tipi_status_noti
from .fase import in_narrazione
from .phased import SistemaSempreAttivo
from .piano import TempoPiano, tempo_piano_corrente
from .scheda import protagonista
from .seme import master_seed
from .turno import entita_attiva, segna_turno_attivo


class TempoNonAvanzabile(Exception):
    """Scorrimento richiesto in una condizione non-safe (combattimento o status che
    blocca). Il predicato è del MOTORE, non un giudizio dell'AI (§7)."""


# --- Contatore di tempo-piano: unico proprietario, avanza al tick condiviso ----

class SistemaTempoPiano(SistemaSempreAttivo):
    """Avanza il contatore di tempo-piano (J §10, J-14). Sempre-attivo, **un solo
    proprietario**; gated sull'entità attiva come gli status (cadenza coerente):

    - in **esplorazione** il tick di scorrimento attiva il protagonista → +1 per stanza;
    - in **combattimento** avanza al confine di turno dell'entità → uno scontro lungo
      brucia tempo-piano (§10). Unità non omogenee, **irrilevante in 1.0** (nessun cap,
      J-15); da disambiguare solo per il crollo post-1.0 (§11).
    """

    def run(self, dt: int) -> None:
        if entita_attiva() is None:
            return  # nessun turno d'entità in corso → niente da contare
        trovati = esper.get_component(TempoPiano)
        if trovati:
            trovati[0][1].tick += 1


# --- Predicati safe (del motore): downtime e passa-turno (§5/§6/§7) ------------

def _status_attivi(entita: int) -> list[type]:
    return [t for t in tipi_status_noti() if esper.has_component(entita, t)]


def ha_status_dannoso(entita: int) -> bool:
    """Vero se sull'entità è attivo almeno uno status `DANNOSO` (flag di tipo, §7)."""
    return any(e_dannoso(t) for t in _status_attivi(entita))


def ha_status_unsafe(entita: int) -> bool:
    """Vero se è attivo almeno uno status `unsafe` (risoluzione = AI, §7)."""
    return any(e_unsafe(t) for t in _status_attivi(entita))


def puo_downtime() -> bool:
    """Fast-forward abilitato ⟺ `NARRAZIONE ∧ nessuno DANNOSO ∧ nessuno unsafe` (§5).
    I tick negativi non permettono il riposo: la valvola è il passa-turno (§6)."""
    if not in_narrazione():  # auto-disabilitato in combattimento (J-13)
        return False
    pent, _marker, _scheda = protagonista()
    return not ha_status_dannoso(pent) and not ha_status_unsafe(pent)


def puo_passare_turno() -> bool:
    """Passa-turno abilitato ⟺ `NARRAZIONE ∧ nessuno unsafe` (§6). Gli status DANNOSI a
    risoluzione-motore **non** lo bloccano: è lì che serve (far scorrere il veleno)."""
    if not in_narrazione():  # auto-disabilitato in combattimento (J-13)
        return False
    pent, _marker, _scheda = protagonista()
    return not ha_status_unsafe(pent)


# --- Dado-evento: tiro seeded del motore (famiglia anomalia, §8) ---------------

@dataclass(frozen=True)
class EsitoDado:
    """L'esito di un tiro di dado-evento. SEGNAPOSTO MVP: solo "imboscata"; la tabella
    per contesto (voci, probabilità) è Gruppo 2 (§8)."""

    imboscata: bool


def tira_dado_evento(rng: random.Random) -> EsitoDado:
    """Tira il dado-evento. È un **tiro del motore**: decide il *fatto*; l'AI semmai ne
    veste il verdetto dopo (§8). Mai una chiamata LLM, mai non-seeded (J-10)."""
    return EsitoDado(imboscata=rng.random() < PROB_IMBOSCATA)


def _rng_dado(tick: int) -> random.Random:
    """RNG del dado seeded da `master_seed` + `tick` (§8): **stesso seed, stesso tick →
    stesso esito** (replay-safe, J-10). Il seme è una stringa deterministica `seed:tick`,
    così ogni tick ha il suo RNG e non si consuma uno stream condiviso → niente
    desincronizzazione (famiglia F-13)."""
    return random.Random(f"{master_seed()}:{tick}")


# --- Il tick di scorrimento (l'ordine normativo §9, J-11) ----------------------

@dataclass(frozen=True)
class RisultatoTick:
    """Esito di un tick di scorrimento. `morte`: la morte ha troncato il tick (niente
    dado). `imboscata`: il dado ha innescato un cambio di fase a confine."""

    morte: bool
    imboscata: bool


def _tick_scorrimento(bus, componi_imboscata: Callable[[], int] | None) -> RisultatoTick:
    """UN tick di scorrimento, nell'ordine normativo (§9, J-11):

    status → death-check (nel `process()`) → **morte? fine, niente dado** →
    dado-evento → effetto a confine (imboscata → `EncounterStarted`, solo su vivo).

    Atomico (F-11): i tick già eseguiti restano reali; lo stato muta alla risoluzione.
    """
    pent, _marker, _scheda = protagonista()

    # 1–2. Core condiviso: attiva il protagonista (cadenza per-stanza, §4) e processa
    #      (status → death-check → avanza tempo-piano). J non muove gli status: li muove
    #      il loro unico proprietario dentro `process()` (J-5).
    segna_turno_attivo(pent)
    esper.process()

    # 3. La morte TRONCA il tick: niente dado, niente imboscata su un cadavere (§9, J-11).
    _pent, _marker, scheda = protagonista()
    if not scheda.vivo:
        return RisultatoTick(morte=True, imboscata=False)

    # 4. Dado-evento (seeded a questo tick): token-zero salvo evento (§8).
    esito = tira_dado_evento(_rng_dado(tempo_piano_corrente()))

    # 5. Effetto a confine di tick — solo su protagonista vivo (J-12). L'imboscata emette
    #    `EncounterStarted` (l'unica via di transizione, FNC §4); la *composizione* dello
    #    scontro è a monte (callback del chiamante, G §5.1), J ne emette solo il confine.
    if esito.imboscata and componi_imboscata is not None:
        enc = componi_imboscata()
        bus.pubblica(EncounterStarted(entita=enc, imboscata=True))
        return RisultatoTick(morte=False, imboscata=True)
    return RisultatoTick(morte=False, imboscata=False)


# --- Passa-turno: tick manuale token-zero (§6) --------------------------------

def passa_turno(bus, *, componi_imboscata: Callable[[], int] | None = None) -> RisultatoTick:
    """Avanza **esattamente un** tick senza spendere una chiamata LLM (§6, J-7/J-8).

    **Non** è una `genera` con schema banale: è la procedura del tick invocata una volta
    (token-zero salvo evento). Abilitato solo se `puo_passare_turno()` (NARRAZIONE ∧
    nessuno unsafe); i DANNOSI a risoluzione-motore **non** lo bloccano (J-7).
    """
    if not puo_passare_turno():
        raise TempoNonAvanzabile(
            "passa-turno non disponibile: in combattimento o status unsafe attivo"
        )
    return _tick_scorrimento(bus, componi_imboscata)


# --- Fast-forward: downtime narrato, comprime N tick (§5) ----------------------

@dataclass(frozen=True)
class RisultatoFastForward:
    """Esito di un downtime: quanti tick eseguiti e da cosa è stato interrotto."""

    tick_eseguiti: int
    interrotto_da: str | None  # "morte" | "imboscata" | None (completato)


def fast_forward(
    bus, durata, *, componi_imboscata: Callable[[], int] | None = None
) -> RisultatoFastForward:
    """Comprime `gate_durata(durata)` tick, **uno per uno**, fermandosi al primo che
    scatena morte o evento (§5, J-6). I tick già eseguiti restano **reali** (atomico).

    Abilitato solo se `puo_downtime()` (NARRAZIONE ∧ nessuno DANNOSO ∧ nessuno unsafe):
    non si riposa mentre il veleno morde — lì la valvola è il passa-turno (§6).
    """
    if not puo_downtime():
        raise TempoNonAvanzabile(
            "downtime non disponibile: in combattimento o status dannoso/unsafe attivo"
        )
    n = gate_durata(durata)  # durata → gate → carico-tick (mai diretto, J-3)
    eseguiti = 0
    for _ in range(n):
        ris = _tick_scorrimento(bus, componi_imboscata)
        eseguiti += 1
        if ris.morte:
            return RisultatoFastForward(tick_eseguiti=eseguiti, interrotto_da="morte")
        if ris.imboscata:
            return RisultatoFastForward(tick_eseguiti=eseguiti, interrotto_da="imboscata")
    return RisultatoFastForward(tick_eseguiti=eseguiti, interrotto_da=None)
