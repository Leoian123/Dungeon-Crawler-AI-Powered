"""Il permadeath RITIRA lo slot, e non dipende dalla buona volontà dell'host.

Il difetto chiuso qui (trovato giocando, 2026-08-15): il meccanismo di
invalidazione esisteva (`Guscio.concludi` → `invalida`, H-20) ma era appeso a
`SessioneGioco.chiudi_terminale()`, cioè a un atto dell'HOST — e l'unico host di
gioco, la TUI, scriveva «💀 Permadeath, run terminata», montava «Esci» e usciva
**senza mai chiamarlo**. Il file di stato restava su disco: salva → muori →
ricarica, protagonista di nuovo vivo. Il save-scumming batteva la linea rossa del
progetto. Nessun test lo vedeva perché l'unico chiamante di `chiudi_terminale`
era `misura_run`, che lo chiama e quindi «funzionava».

L'oracolo qui non è «esiste una porta che invalida» (esisteva): è **l'exploit**.
Si gioca fino alla morte SENZA che l'host chiuda nulla, e si prova a ricaricare.
"""

from __future__ import annotations

import asyncio

from contracts import PlayerChoseOption, Terminale
from main import carica_sessione, costruisci_sessione, elenca_crawler


async def _gioca_fino_alla_morte(sessione, max_turni: int = 200):
    """Porta la run al terminale di MORTE per la via più corta e deterministica.

    Il protagonista entra nel primo scontro con 1 HP: il death-check chiude al
    primo colpo incassato. Serve una morte CERTA, non una morte emergente — nella
    suite il dado-imboscata è spento (conftest) e una politica suicida in una zona
    ripulita vagherebbe senza morire mai."""
    from motore import protagonista

    _ent, _marker, scheda = protagonista()
    scheda.punti_vita = 1
    turni = 0
    while turni < max_turni:
        snap = sessione.avanza()
        if snap.run_conclusa:
            return snap.terminale
        turni += 1
        if not snap.opzioni:
            await sessione.prossima_narrazione()
            continue
        etichette = [o.etichetta for o in snap.opzioni]
        indice = next(
            (i for i, e in enumerate(etichette) if e.startswith(("Combatti", "Attacca"))),
            None,
        )
        if indice is None:  # mai Riposa/Aspetta: si cerca il terminale
            indice = next(
                (i for i, e in enumerate(etichette) if e.startswith("Vai")), 0
            )
        sessione.coda.accoda(PlayerChoseOption(indice))
    return None


def test_la_morte_ritira_lo_slot_senza_che_l_host_chiuda(run_pulita, tmp_path) -> None:
    """L'EXPLOIT: salva, muori, ricarica. Deve essere impossibile anche se l'host
    non chiama mai `chiudi_terminale()`."""
    sessione = costruisci_sessione(seed=3, directory=tmp_path, nome="Donut")
    asyncio.run(sessione.prossima_narrazione())
    sessione.salva()
    uuid = sessione.uuid
    assert [v.etichetta for v in elenca_crawler(tmp_path)] == ["Donut"]

    terminale = asyncio.run(_gioca_fino_alla_morte(sessione))
    assert terminale is Terminale.SCONFITTA, "la politica suicida deve morire"

    # Nessuna chiamata a `chiudi_terminale`: è esattamente ciò che fa la TUI.
    assert elenca_crawler(tmp_path) == [], "lo slot è ritirato all'istante"
    assert carica_sessione(uuid=uuid, directory=tmp_path) is None, (
        "un crawler morto non si ricarica: sarebbe save-scumming"
    )


def test_l_uscita_volontaria_non_ritira_nulla(run_pulita, tmp_path) -> None:
    """La cintura del test sopra: il ritiro scatta sul TERMINALE, non su ogni
    chiusura. Salva-ed-esci deve continuare a lasciare lo slot riprendibile."""
    sessione = costruisci_sessione(seed=1, directory=tmp_path, nome="Carl")
    asyncio.run(sessione.prossima_narrazione())
    uuid = sessione.uuid
    sessione.esci()
    assert [v.etichetta for v in elenca_crawler(tmp_path)] == ["Carl"]
    assert carica_sessione(uuid=uuid, directory=tmp_path) is not None


def test_il_ritiro_e_idempotente_col_teardown_esplicito(run_pulita, tmp_path) -> None:
    """L'host che FA la cosa giusta non deve rompersi: `chiudi_terminale` gira
    dopo un ritiro già avvenuto senza lamentarsi del file assente."""
    sessione = costruisci_sessione(seed=3, directory=tmp_path, nome="Donut")
    asyncio.run(sessione.prossima_narrazione())
    sessione.salva()
    assert asyncio.run(_gioca_fino_alla_morte(sessione)) is Terminale.SCONFITTA
    assert sessione.chiudi_terminale() == "Run conclusa: lo slot è stato ritirato."
    assert elenca_crawler(tmp_path) == []


# --- Le PORTE DI SCRITTURA dopo il terminale (caccia 2026-08-16) ---------------
# Il ritiro dello slot non basta se salva()/esci() possono RICREARLO: erano le
# due vie di save-scumming confermate dalla verifica avversariale (esci() dopo
# la vittoria risalvava lo slot; salva() dopo la morte lo ricreava).

def test_salva_dopo_la_morte_rifiuta_e_non_ricrea_lo_slot(run_pulita, tmp_path) -> None:
    from main import RunConclusa

    sessione = costruisci_sessione(seed=3, directory=tmp_path, nome="Donut")
    asyncio.run(sessione.prossima_narrazione())
    sessione.salva()
    assert asyncio.run(_gioca_fino_alla_morte(sessione)) is Terminale.SCONFITTA
    assert elenca_crawler(tmp_path) == []
    try:
        sessione.salva()
        raise AssertionError("salva() a run conclusa deve rifiutare")
    except RunConclusa:
        pass
    assert elenca_crawler(tmp_path) == [], "salva() ha ricreato lo slot del morto"


def test_esci_dopo_la_morte_e_il_teardown_non_un_salvataggio(run_pulita, tmp_path) -> None:
    """`esci()` a run conclusa delega a `chiudi_terminale`: niente eccezioni
    spurie («non si salva in combattimento» detto a un morto), niente risalvataggio."""
    sessione = costruisci_sessione(seed=3, directory=tmp_path, nome="Donut")
    asyncio.run(sessione.prossima_narrazione())
    sessione.salva()
    assert asyncio.run(_gioca_fino_alla_morte(sessione)) is Terminale.SCONFITTA
    assert sessione.esci() == "Run conclusa: lo slot è stato ritirato."
    assert elenca_crawler(tmp_path) == []
    assert carica_sessione(uuid=sessione.uuid, directory=tmp_path) is None


def test_il_guscio_non_rinegozia_un_terminale_rilevato(run_pulita, tmp_path) -> None:
    """La cintura nel guscio: `esci_volontariamente` su un terminale già
    rilevato è un no-op — `concludi` deve prendere il ramo `invalida`, mai
    `salva_run` (era la via del save-scumming post-vittoria)."""
    from contracts import Terminale as _T

    sessione = costruisci_sessione(seed=3, directory=tmp_path, nome="Donut")
    asyncio.run(sessione.prossima_narrazione())
    assert asyncio.run(_gioca_fino_alla_morte(sessione)) is Terminale.SCONFITTA
    sessione.guscio.esci_volontariamente()  # l'host confuso: non deve vincere
    assert sessione.guscio.terminale is _T.SCONFITTA


def test_il_bak_di_recovery_non_resuscita_il_morto(run_pulita, tmp_path) -> None:
    """Il `.bak` protegge dalla CORRUZIONE, mai dal permadeath: caricarlo come
    slot (`carica_sessione(uuid=f"{uuid}.bak")`) deve fallire sul mismatch
    d'identità intestazione↔file — era la terza via di resurrezione."""
    sessione = costruisci_sessione(seed=3, directory=tmp_path, nome="Donut")
    asyncio.run(sessione.prossima_narrazione())
    sessione.salva()
    sessione.salva()  # il secondo salvataggio produce la coppia .bak
    uuid = sessione.uuid
    ha_bak = (tmp_path / f"{uuid}.bak.stato.json").exists()
    assert asyncio.run(_gioca_fino_alla_morte(sessione)) is Terminale.SCONFITTA
    assert elenca_crawler(tmp_path) == []
    if ha_bak:
        assert carica_sessione(uuid=f"{uuid}.bak", directory=tmp_path) is None, (
            "il backup di recovery è caricabile come slot: il morto risorge"
        )
