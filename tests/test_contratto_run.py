"""Il CONTRATTO dello stato di run: come fa un host a sapere che la partita è finita.

Prima non poteva saperlo dal contratto: dopo la morte lo `SnapshotVista` serviva
ancora un menu giocabile, e l'unico accesso alla verità era `guscio._terminale` —
un attributo privato che perfino i test leggevano. Col multi-piano quella
distinzione diventa la differenza fra «sono sceso di un piano» e «ho vinto la run»:
per questo il campo nasce PRIMA della feature che lo userà.

Qui c'è anche la forma di ciò che il riposo dichiarerà (`TipoAzione.RIPOSA`,
`RiposoConcluso`): il vocabolario chiuso si estende una volta sola, e va esteso
prima che qualcuno ci costruisca sopra.
"""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

import contracts
from contracts import (
    RiposoConcluso,
    SnapshotVista,
    Terminale,
    TipoAzione,
)
from main import costruisci_sessione


# --- Il terminale è un contratto, non un attributo privato ----------------------

def test_il_terminale_attraversa_la_membrana() -> None:
    assert "Terminale" in contracts.__all__
    assert {t.value for t in Terminale} == {
        "sconfitta", "piano_completato", "uscita_volontaria",
    }


def test_lo_snapshot_dichiara_lo_stato_di_run() -> None:
    """Default = run in corso. `run_conclusa` è la domanda che l'host fa davvero."""
    vivo = SnapshotVista()
    assert vivo.terminale is None and vivo.run_conclusa is False
    assert vivo.profondita == 1

    finito = SnapshotVista(terminale=Terminale.PIANO_COMPLETATO, profondita=3)
    assert finito.run_conclusa is True
    assert finito.profondita == 3


def test_il_guscio_espone_il_terminale_pubblicamente(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(nome="Vivo", seed=1, directory=tmp_path)
    assert sessione.guscio.terminale is None
    assert sessione.terminale is None


def test_lo_snapshot_di_una_run_viva_dice_che_e_viva(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(nome="Vivo", seed=1, directory=tmp_path)
    snap = asyncio.run(sessione.prossima_narrazione())
    assert snap.run_conclusa is False
    assert snap.terminale is None
    assert snap.profondita == 1


def test_la_run_conclusa_attraversa_la_membrana(run_pulita, tmp_path) -> None:
    """IL test che conta, e ora conta davvero: lo snapshot distingue **«sceso di un
    piano»** da **«vinto»**.

    Il contratto era stato scritto anticipando questo momento (`terminale`/`profondita`
    esistevano già); finché la stagione aveva un piano solo, però, la prima discesa era
    indistinguibile dalla vittoria e il ramo "continua" non era esercitato da nessuno.
    Con due piani lo è: si scende, la run VIVE, si scende ancora e finisce."""
    from contracts import PlayerDiscende
    from motore import mappa_corrente

    def _scendi(sessione):
        _ent, mappa = mappa_corrente()
        mappa.stanza_corrente = next(iter(mappa.piano.discese))  # la discesa vuole la scala
        sessione.coda.accoda(PlayerDiscende())
        return sessione.avanza()

    from tests.contenuti_sintetici import stagione_sintetica

    sessione = costruisci_sessione(
        nome="Sceso", seed=1, directory=tmp_path, stagione=stagione_sintetica(2)
    )
    snap = asyncio.run(sessione.prossima_narrazione())
    assert snap.run_conclusa is False

    snap = _scendi(sessione)                      # piano 1 → 2: si continua
    assert snap.terminale is None, "scendere dal PRIMO piano non è vincere"
    assert snap.run_conclusa is False
    assert snap.profondita == 2

    snap = _scendi(sessione)                      # piano 2 → fuori: vittoria
    assert snap.terminale is Terminale.PIANO_COMPLETATO
    assert snap.run_conclusa is True, "l'host deve poterlo sapere DAL CONTRATTO"
    assert snap.profondita == 3


def test_ogni_porta_risponde_con_lo_STESSO_stato_di_run(run_pulita, tmp_path) -> None:
    """Il difetto trovato in review: `terminale`/`profondita` erano stati aggiunti a
    UNO solo dei tre costruttori di snapshot, quindi `avanza()` diceva
    «PIANO_COMPLETATO, piano 2» e la `prossima_narrazione()` successiva rispondeva
    «run viva, piano 1» — sulla stessa sessione. Ora il costruttore è uno solo."""
    from contracts import PlayerDiscende
    from motore import livello_corrente, mappa_corrente

    from tests.contenuti_sintetici import stagione_sintetica

    sessione = costruisci_sessione(
        nome="Coerente", seed=1, directory=tmp_path, stagione=stagione_sintetica(2)
    )
    snap = asyncio.run(sessione.prossima_narrazione())
    assert (snap.terminale, snap.profondita) == (sessione.terminale, livello_corrente())

    _ent, mappa = mappa_corrente()
    mappa.stanza_corrente = next(iter(mappa.piano.discese))
    sessione.coda.accoda(PlayerDiscende())
    dopo_avanza = sessione.avanza()

    # La porta ASYNC deve concordare con quella sincrona, sulla stessa verità.
    dopo_narrazione = asyncio.run(sessione.prossima_narrazione())
    for snap in (dopo_avanza, dopo_narrazione):
        assert snap.terminale is sessione.terminale
        assert snap.profondita == livello_corrente()
    # Qui la run è VIVA (sceso al piano 2 di 2): ciò che il test difende è la
    # COERENZA fra le porte, non un esito particolare — le due devono raccontare la
    # stessa run, conclusa o no.
    assert dopo_narrazione.run_conclusa is dopo_avanza.run_conclusa


def test_l_hand_off_restituisce_il_terminale_e_torna_al_menu(run_pulita, tmp_path) -> None:
    """Uscire NON è perdere: `concludi` distingue i tre modi di finire e li
    RESTITUISCE. Dopo l'hand-off il guscio è di nuovo al menu (terminale azzerato):
    la domanda «com'è finita» si fa PRIMA di chiudere, o sul valore di ritorno."""
    sessione = costruisci_sessione(nome="Uscito", seed=1, directory=tmp_path)
    asyncio.run(sessione.prossima_narrazione())
    sessione.guscio.esci_volontariamente()
    assert sessione.guscio.terminale is Terminale.USCITA_VOLONTARIA
    assert sessione._snapshot_corrente().run_conclusa is True

    assert sessione.guscio.concludi() is Terminale.USCITA_VOLONTARIA
    assert sessione.guscio.terminale is None  # tornato al menu, pronto per un'altra run


# --- La forma del riposo: dichiarata prima di essere implementata ---------------

def test_riposa_e_nel_vocabolario_chiuso_delle_azioni() -> None:
    """`TipoAzione` è chiuso: estenderlo è una decisione di contratto, e si fa una
    volta sola — prima che l'implementazione ci si appoggi."""
    assert TipoAzione.RIPOSA.value == "riposa"
    assert TipoAzione("riposa") is TipoAzione.RIPOSA


def test_ogni_azione_ha_la_sua_durata_di_calibrazione() -> None:
    """⚠️ Trappola nota: `DURATA_AZIONE` itera TUTTO `TipoAzione` all'import — un
    membro nuovo senza la sua foglia §11 fa esplodere il motore al caricamento.
    Questo test la rende impossibile da dimenticare."""
    from motore.calibrazione import DURATA_AZIONE

    mancanti = [t.value for t in TipoAzione if t not in DURATA_AZIONE]
    assert not mancanti, f"TipoAzione senza foglia DURATA_AZIONE: {mancanti}"


def test_ogni_evento_di_dominio_ha_una_riga_di_cronaca() -> None:
    """La disciplina che mancava agli EVENTI, e che le azioni avevano già: un
    evento dichiarato ma assente dalla cronaca nasce MUTO — pubblicato, e invisibile
    al giocatore. La tabella è scritta a mano, quindi serve una rete che la tenga
    allineata al vocabolario."""
    from contracts.eventi import EventoDominio
    from main import _MAPPA_EVENTI

    def discendenti(base: type) -> set[type]:
        figli = set(base.__subclasses__())
        return figli | {n for f in figli for n in discendenti(f)}

    dichiarati = discendenti(EventoDominio)
    raccontati = {tipo for tipo, _formatta in _MAPPA_EVENTI}
    muti = {t.__name__ for t in dichiarati - raccontati}
    assert not muti, f"eventi senza riga di cronaca (nascerebbero muti): {sorted(muti)}"


def test_la_cronaca_della_fuga_negata_non_racconta_uno_stordimento() -> None:
    """Regression (audit 2026-08-07): il produttore emette `causa="fuga_negata"`,
    ma il consumer gestiva solo "fuga_fallita" (mai emessa da nessuno) e ripiegava
    sul ramo stordito: chi si vedeva negare la fuga leggeva «Sei stordito»."""
    from contracts import TurnoSaltato
    from main import _riga_turno_saltato

    negata = _riga_turno_saltato(TurnoSaltato(nome="", causa="fuga_negata"))
    assert "fuga" in negata.lower() and "stordito" not in negata.lower()
    stordito = _riga_turno_saltato(TurnoSaltato(nome="", causa="stordito"))
    assert "stordito" in stordito.lower()


def test_ogni_terminale_ha_una_riga_di_chiusura() -> None:
    """Regression (giro 2026-08-07): la VITTORIA della run era completamente muta
    — `PIANO_COMPLETATO` arrivava nello snapshot e nessuna superficie lo
    verbalizzava; l'ultima riga letta vincendo era una discesa verso un piano
    inesistente."""
    from contracts import Terminale
    from main import _riga_terminale

    righe = {t: _riga_terminale(t) for t in Terminale}
    assert all(righe.values()), "un terminale senza testo chiude la run in silenzio"
    assert len(set(righe.values())) == len(righe), "due terminali con la stessa riga"
    assert "VINTO" in righe[Terminale.PIANO_COMPLETATO]


def test_la_morte_non_recita_il_literal_dellenum() -> None:
    from main import _riga_morte

    riga = _riga_morte(type("E", (), {"causa": "sconfitta"})())
    assert "sconfitta" not in riga and "morto" in riga.lower()


def test_la_discesa_oltre_lultimo_piano_e_vittoria_non_un_piano_nuovo(
    run_pulita, tmp_path
) -> None:
    from contracts import DiscesaPiano
    from main import _riga_discesa, costruisci_sessione
    from tests.contenuti_sintetici import stagione_sintetica

    # Stagione SINTETICA a 2 piani: la riga di discesa dipende dal numero di
    # piani della stagione congelata, non dal contenuto pubblicato (2026-08-10).
    costruisci_sessione(
        nome="Fine", seed=1, directory=tmp_path, stagione=stagione_sintetica(2)
    )
    dentro = _riga_discesa(DiscesaPiano(piano=2))
    fuori = _riga_discesa(DiscesaPiano(piano=3))
    assert "piano 2" in dentro
    assert "piano 3" not in fuori and "COMPLETA" in fuori


def test_i_descrittori_non_mostrano_hp_negativi(run_pulita, tmp_path) -> None:
    """L'ultima schermata di una run persa mostrava «HP -4/30» col nemico ancora
    in lista: numeri sporchi nel momento più carico del giro."""
    import asyncio as _asyncio

    from main import costruisci_sessione
    from motore import protagonista

    sessione = costruisci_sessione(nome="Fine", seed=1, directory=tmp_path)
    _asyncio.run(sessione.prossima_narrazione())
    _p, _m, scheda = protagonista()
    scheda.punti_vita = -4
    stato = sessione._descrittori()
    assert any(s.startswith("HP 0/") for s in stato), stato


def test_le_righe_di_colpo_flettono_e_nominano_la_mossa() -> None:
    """«1 danni» era un plurale rotto, e la mossa usata non compariva mai."""
    from main import _riga_colpo

    def _e(**kw):
        base = dict(attaccante="", bersaglio="Slime", danno=1,
                    hp_rimasti=4, hp_max=5, mossa="attacco")
        base.update(kw)
        return type("E", (), base)()

    uno = _riga_colpo(_e(danno=1))
    assert "1 danno " in uno and "1 danni" not in uno
    dardo = _riga_colpo(_e(danno=3, mossa="dardo_arcano"))
    assert "3 danni" in dardo and "con Dardo arcano" in dardo


def test_il_veleno_ti_morde_col_clitico_al_posto_giusto() -> None:
    from main import _riga_effetto_status

    e = type("E", (), {"bersaglio": "", "delta_hp": -1, "status": "veleno"})()
    assert _riga_effetto_status(e) == "Il veleno ti morde: -1 HP."


def test_il_disimpegno_di_scena_ha_una_riga(run_pulita, tmp_path) -> None:
    """Regression (giro 2026-08-07): il disimpegno riuscito dissolveva il mob in
    silenzio totale — nessun evento, nessuna riga."""
    import asyncio as _asyncio

    from contracts import PlayerChoseOption
    from main import CronacaBus, costruisci_sessione

    from motore import tempo_piano_corrente

    sessione = costruisci_sessione(nome="Scappa", seed=1, directory=tmp_path)
    cronaca = CronacaBus(sessione.bus)
    try:
        snap = _asyncio.run(sessione.prossima_narrazione())
        etichette = {o.etichetta: o.indice for o in snap.opzioni}
        assert "Scappi" in etichette, f"scena inattesa: {etichette}"
        cronaca.preleva()
        t0 = tempo_piano_corrente()
        sessione.coda.accoda(PlayerChoseOption(etichette["Scappi"]))
        sessione.avanza()
        righe = cronaca.preleva()
        assert any("disimpegni" in r for r in righe), (
            f"nessuna riga per il disimpegno riuscito: {righe}"
        )
        # …e il disimpegno PAGA la sua durata (il docstring lo dichiarava, il
        # codice no: scappare era gratis anche in tick — giro 2026-08-07).
        assert tempo_piano_corrente() > t0, "il disimpegno non ha speso tempo"
    finally:
        cronaca.chiudi()


def test_la_cronaca_del_riposo_distingue_l_interruzione() -> None:
    """Un riposo spezzato NON deve sembrare un riposo che ha reso poco."""
    from main import _riga_riposo

    intero = _riga_riposo(RiposoConcluso(tick_spesi=4, hp_recuperati=8, mana_recuperato=8))
    spezzato = _riga_riposo(
        RiposoConcluso(tick_spesi=1, hp_recuperati=2, mana_recuperato=2, interrotto=True)
    )
    assert "INTERROTTO" in spezzato and "INTERROTTO" not in intero
    assert "+8 HP" in intero and "+2 HP" in spezzato


def test_riposo_concluso_e_un_evento_di_dominio() -> None:
    """Riassuntivo di proposito: il riposo dura più tick e una riga per tick
    sarebbe rumore. `interrotto` è un FATTO (l'imboscata è già avvenuta), non
    una promessa."""
    assert "RiposoConcluso" in contracts.__all__
    assert dataclasses.is_dataclass(RiposoConcluso)

    evento = RiposoConcluso(tick_spesi=2, hp_recuperati=4, mana_recuperato=4, interrotto=True)
    assert evento.interrotto is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        evento.tick_spesi = 99  # type: ignore[misc]

    # Un riposo completo è il default: `interrotto` non va dichiarato ogni volta.
    assert RiposoConcluso(tick_spesi=4, hp_recuperati=8, mana_recuperato=8).interrotto is False
