"""T2 dei tipi di stanza: la QUIETE meccanica. Safe room e bagno: nessun mob al
reveal, il dado-imboscata non tira (riposo sicuro per conseguenza); il corridoio
moltiplica il dado (foglia §11). La quiete è design, non un numero.
"""

from __future__ import annotations

import asyncio
import random

from contracts import BusEventi, TipoStanza
from motore import (
    avvia_territorio,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_stagione,
    crea_tempo_piano,
    fattore_imboscata_stanza,
    mappa_corrente,
    mob_corrente,
    riposa,
    stanza_quieta,
    stanza_visitata,
)
from motore.calibrazione import STANZE_MOLT_IMBOSCATA_CORRIDOIO
from motore.tempo import tira_dado_evento
from tests.contenuti_sintetici import piano_territoriale, stagione_sintetica


def _arma_mondo(seed: int = 7) -> BusEventi:
    from main import _stagione_a_attiva

    crea_profondita()
    crea_seme(seed)
    crea_tempo_piano()
    crea_stagione(_stagione_a_attiva(
        stagione_sintetica(piani=[piano_territoriale(1)], slug="s-quiete")
    ))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    avvia_territorio(1)
    return BusEventi()


class _RngFisso(random.Random):
    """Un RNG che pesca sempre 0.0: il dado, se può scattare, scatta."""

    def random(self) -> float:  # type: ignore[override]
        return 0.0


def test_stanza_quieta_per_tipo() -> None:
    assert stanza_quieta(TipoStanza.SAFE_ROOM)
    assert stanza_quieta(TipoStanza.BAGNO)
    assert not stanza_quieta(TipoStanza.NORMALE)
    assert not stanza_quieta(TipoStanza.CORRIDOIO)
    assert not stanza_quieta(TipoStanza.BOSS)


def test_fattore_imboscata_segue_il_tipo(mondo_isolato) -> None:
    _arma_mondo()
    _e, mappa = mappa_corrente()
    stanza = mappa.stanza_corrente
    mappa.piano.tipi[stanza] = TipoStanza.SAFE_ROOM
    assert fattore_imboscata_stanza() == 0.0
    mappa.piano.tipi[stanza] = TipoStanza.BAGNO
    assert fattore_imboscata_stanza() == 0.0
    mappa.piano.tipi[stanza] = TipoStanza.CORRIDOIO
    assert fattore_imboscata_stanza() == float(STANZE_MOLT_IMBOSCATA_CORRIDOIO)
    mappa.piano.tipi.pop(stanza)
    assert fattore_imboscata_stanza() == 1.0


class _RngContatore(random.Random):
    """Pesca sempre 0.0 E conta le pescate: la forma dello stream è un assert."""

    def __init__(self) -> None:
        super().__init__()
        self.pescate = 0

    def random(self) -> float:  # type: ignore[override]
        self.pescate += 1
        return 0.0


def test_il_dado_quieto_non_scatta_mai_ma_pesca_sempre(monkeypatch) -> None:
    """Fattore 0 = niente imboscata anche con probabilità 1 e la pescata più
    sfortunata — e la pescata avviene COMUNQUE, una per tiro: uno short-circuit
    che la saltasse cambierebbe la forma dello stream (replay divergenti)."""
    from motore import tempo as tempo_mod

    monkeypatch.setattr(tempo_mod, "PROB_IMBOSCATA", 1.0)
    caldo, quieto = _RngContatore(), _RngContatore()
    assert tira_dado_evento(caldo, 1.0).imboscata is True
    assert tira_dado_evento(quieto, 0.0).imboscata is False
    assert caldo.pescate == 1 and quieto.pescate == 1, (
        "la pescata deve avvenire in ENTRAMBI i rami: lo stream non cambia forma"
    )


def test_il_moltiplicatore_corridoio_arriva_al_dado(mondo_isolato, monkeypatch) -> None:
    """Fino all'ESITO, non solo alla chiamata: con la pescata al bordo (0.8) e
    probabilità 0.7, l'imboscata scatta SOLO nel corridoio (0.7×1.5 > 0.8 > 0.7).
    Un `_tick_scorrimento` che chiamasse il fattore ma passasse 1.0 al dado
    passerebbe il test-spia: questo no."""
    from motore import componi_imboscata_scena
    from motore import tempo as tempo_mod
    from motore.fase import crea_entita_fase
    from motore.tempo import passa_turno

    class _RngBordo(random.Random):
        def random(self) -> float:  # type: ignore[override]
            return 0.8

    monkeypatch.setattr(tempo_mod, "PROB_IMBOSCATA", 0.7)
    monkeypatch.setattr(tempo_mod, "_rng_dado", lambda _tick: _RngBordo())
    bus = _arma_mondo()
    crea_entita_fase()
    _e, mappa = mappa_corrente()
    stanza = mappa.stanza_corrente

    mappa.piano.tipi.pop(stanza, None)  # NORMALE: 0.8 < 0.7 → niente agguato
    esito = passa_turno(bus, componi_imboscata=componi_imboscata_scena)
    assert esito.imboscata is False

    mappa.piano.tipi[stanza] = TipoStanza.CORRIDOIO  # 0.8 < 1.05 → agguato
    esito = passa_turno(bus, componi_imboscata=componi_imboscata_scena)
    assert esito.imboscata is True


def test_reveal_in_luogo_quieto_non_materializza(run_pulita, tmp_path) -> None:
    """Nella safe room la stanza È la scena: il reveal (copione offline compreso)
    non mette in scena alcun mob, la visita si segna, il menu esiste e non offre
    Combatti."""
    from main import costruisci_sessione

    sessione = costruisci_sessione(
        nome="Quiete", seed=11, directory=tmp_path,
        stagione=stagione_sintetica(piani=[piano_territoriale(1)], slug="s-q2"),
    )
    asyncio.run(sessione.prossima_narrazione())  # reveal della partenza
    _e, mappa = mappa_corrente()
    libere = [s for s in mappa.piano.adiacenze
              if s not in (mappa.piano.partenza,) and s not in mappa.piano.discese]
    stanza = libere[0]
    mappa.piano.tipi[stanza] = TipoStanza.SAFE_ROOM
    mappa.stanza_corrente = stanza

    snapshot = asyncio.run(sessione.prossima_narrazione())
    assert mob_corrente() is None, "il luogo quieto non materializza mai"
    assert stanza_visitata()
    assert "respira" in snapshot.prosa  # la prosa del LUOGO (copione di quiete)
    etichette = {o.etichetta for o in snapshot.opzioni}
    assert "Combatti" not in etichette and etichette, "menu senza ingaggio, mai vuoto"

    # RILETTURA (rientro in zona): il luogo quieto non ha mai avuto mob — la
    # coda onesta «non c'è più» qui MENTIREBBE, e non deve comparire.
    mappa.visitate.discard(stanza)
    snapshot = asyncio.run(sessione.prossima_narrazione())
    assert "non c'è più" not in snapshot.prosa, "la coda onesta mente nel luogo quieto"
    assert stanza_visitata() and mob_corrente() is None
    sessione.esci()


def test_riposo_in_safe_room_mai_interrotto(mondo_isolato, monkeypatch) -> None:
    """Il riposo sicuro è una CONSEGUENZA della quiete: col dado truccato a 1
    l'imboscata scatterebbe a ogni tick, ma nella safe room non tira affatto."""
    from motore import tempo as tempo_mod

    monkeypatch.setattr(tempo_mod, "PROB_IMBOSCATA", 1.0)
    bus = _arma_mondo()
    from motore.fase import crea_entita_fase

    crea_entita_fase()  # il riposo passa dal phase-gate: serve la fase nel World
    _e, mappa = mappa_corrente()
    stanza = mappa.stanza_corrente
    mappa.piano.tipi[stanza] = TipoStanza.SAFE_ROOM
    esito = riposa(bus)
    assert esito is not None and not esito.interrotto

    mappa.piano.tipi.pop(stanza)  # stessa stanza, senza quiete: il dado morde
    esito = riposa(bus)
    assert esito is not None and esito.interrotto


def test_fascicolo_quiete_istruzione_e_niente_mob_atteso(mondo_isolato) -> None:
    from motore import MemoriaTurni, componi_fascicolo
    from motore.gm import sezione_fascicolo

    _arma_mondo()
    _e, mappa = mappa_corrente()
    stanza = mappa.stanza_corrente
    mappa.piano.tipi[stanza] = TipoStanza.SAFE_ROOM
    fascicolo = componi_fascicolo(MemoriaTurni())
    sezione = sezione_fascicolo(fascicolo)
    assert "NESSUN nemico entra in scena" in sezione
    assert fascicolo.mob_atteso_riga == ""  # al GM non si suggerisce un mob qui


def test_turno_quiete_passa_il_gate_del_piano_reale(run_pulita, tmp_path) -> None:
    """Regressione (review 2026-08-11): il segnaposto del copione di quiete deve
    rispettare il BUDGET del piano attivo — il pianoterra pubblicato ammette
    zombie/scheletro/lich, NON lo slime di default: un archetipo fuori budget
    verrebbe respinto dal gate e la safe room narrerebbe il fallback."""
    from main import costruisci_sessione
    from motore import stanza_boss_di, zona_corrente

    sessione = costruisci_sessione(nome="Reale", seed=3, directory=tmp_path)
    asyncio.run(sessione.prossima_narrazione())  # stagione-1 VERA, non sintetica
    _e, mappa = mappa_corrente()
    boss = stanza_boss_di(zona_corrente(), mappa.piano)
    libere = [s for s in mappa.piano.adiacenze
              if s not in (mappa.piano.partenza, boss)
              and s not in mappa.piano.discese]
    stanza = libere[0]
    mappa.piano.tipi[stanza] = TipoStanza.BAGNO
    mappa.stanza_corrente = stanza

    snapshot = asyncio.run(sessione.prossima_narrazione())
    assert mob_corrente() is None
    assert "Sagoma" not in snapshot.prosa, "il gate ha respinto il turno di quiete"
    assert "piastrelle" in snapshot.prosa  # la prosa del LUOGO, non il fallback
    sessione.esci()


def test_il_tick_reale_consulta_il_fattore_della_stanza(mondo_isolato, monkeypatch) -> None:
    """Cablaggio, non formula: `_tick_scorrimento` chiede il fattore alla MAPPA
    a ogni tick — spia sul modulo mappa, tick vero via `passa_turno`. Una
    regressione che scollegasse il dado dal tipo di stanza passerebbe tutti i
    test unitari del fattore: questo la vede."""
    from motore import mappa as mappa_mod
    from motore.calibrazione import STANZE_MOLT_IMBOSCATA_CORRIDOIO as MOLT
    from motore.fase import crea_entita_fase
    from motore.tempo import passa_turno

    fattori_visti: list[float] = []
    vero = mappa_mod.fattore_imboscata_stanza

    def spia() -> float:
        f = vero()
        fattori_visti.append(f)
        return f

    monkeypatch.setattr(mappa_mod, "fattore_imboscata_stanza", spia)
    bus = _arma_mondo()
    crea_entita_fase()
    _e, mappa = mappa_corrente()
    mappa.piano.tipi[mappa.stanza_corrente] = TipoStanza.CORRIDOIO
    passa_turno(bus)
    assert fattori_visti == [float(MOLT)], "il tick non ha consultato la stanza"


def test_quiete_anche_sui_piani_piatti(run_pulita, tmp_path) -> None:
    """Regressione (review 2026-08-11, finding del revisore): il ramo di quiete
    del copione era agganciato SOLO al percorso territoriale — su un piano
    PIATTO un bagno stampato dalla mappa narrava il mob del copione keyed: un
    mostro mai materializzato, congelato in Archivio con la coda onesta
    soppressa. La quiete deve valere su ENTRAMBI i percorsi."""
    from main import costruisci_sessione
    from tests.contenuti_sintetici import piano_sintetico

    sessione = costruisci_sessione(
        nome="Piatto", seed=6, directory=tmp_path,
        stagione=stagione_sintetica(
            piani=[piano_sintetico(1, n_stanze=4)], slug="s-piatto"
        ),
    )
    asyncio.run(sessione.prossima_narrazione())
    _e, mappa = mappa_corrente()
    libere = [s for s in mappa.piano.adiacenze
              if s != mappa.piano.partenza and s not in mappa.piano.discese]
    stanza = libere[0]
    mappa.piano.tipi[stanza] = TipoStanza.BAGNO
    mappa.stanza_corrente = stanza

    snapshot = asyncio.run(sessione.prossima_narrazione())
    assert mob_corrente() is None
    assert "piastrelle" in snapshot.prosa, "sul piatto deve valere il copione di quiete"
    sessione.esci()
