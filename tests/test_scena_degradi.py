"""La composizione del menu: tollerante al World parziale, ma mai MUTA.

`componi_opzioni_scena` decide **cosa il giocatore può fare**. Comporre è una
lettura e non deve esplodere (gli harness montano World senza fase, senza
protagonista, senza territorio), ma i cinque `except Exception` che lo
garantivano erano muti: un guasto vero — una regressione in `puo_downtime`, un
territorio incoerente — si manifestava come «l'opzione non c'era», che è
indistinguibile dal comportamento corretto. Nessun test poteva vederlo.

Ora il degrado si REGISTRA (`degradi_scena`). I due lucchetti sono simmetrici:
su un World completo il registro resta VUOTO (se un giorno una lettura comincia
a degradare in partita, il test lo dice); su un World parziale la composizione
regge E lascia traccia.
"""

from __future__ import annotations

import asyncio
import random

import esper

from contracts import TipoAzione
from motore import (
    azzera_degradi_scena,
    componi_opzioni_scena,
    crea_mappa,
    degradi_scena,
    insegna_laterale,
    segna_visitata,
)
from main import costruisci_sessione


def test_su_un_world_completo_nessun_degrado(run_pulita) -> None:
    """Il lucchetto che conta: in partita vera la scena si compone SENZA
    inghiottire niente. Un rosso qui = un'opzione sta sparendo in silenzio."""
    sessione = costruisci_sessione(seed=1)
    asyncio.run(sessione.prossima_narrazione())
    azzera_degradi_scena()
    opzioni = componi_opzioni_scena()
    assert opzioni, "la scena di una stanza rivelata non è vuota"
    assert degradi_scena() == {}, (
        f"la composizione ha inghiottito un errore in partita: {degradi_scena()}"
    )


def test_il_world_parziale_regge_e_lascia_traccia(mondo_isolato) -> None:
    """Senza fase né protagonista, comporre resta una lettura che non esplode —
    e il registro dice QUALE lettura è degradata e perché."""
    azzera_degradi_scena()
    crea_mappa(random.Random(0), 4)
    segna_visitata()
    opzioni = componi_opzioni_scena()
    assert [o.tipo for o in opzioni] == [TipoAzione.MUOVI] * len(opzioni)
    degradi = degradi_scena()
    assert "downtime" in degradi and "passa_turno" in degradi
    errore, conteggio = degradi["downtime"]
    assert conteggio == 1 and errore, "il registro porta l'errore, non un bool"


def test_il_registro_conta_le_ripetizioni(mondo_isolato) -> None:
    azzera_degradi_scena()
    crea_mappa(random.Random(0), 4)
    segna_visitata()
    componi_opzioni_scena()
    componi_opzioni_scena()
    _errore, conteggio = degradi_scena()["downtime"]
    assert conteggio == 2


# --- Insegne: l'etichetta resta dentro la finzione -----------------------------

def test_l_insegna_non_stampa_indici_interni(run_pulita) -> None:
    """L'etichetta di deviazione portava `percorso[-1]` fra parentesi
    («Deviazione: quartiere vicino (0)»): una struttura dati a video."""
    from contracts import TierTerritorio
    from motore import Zona

    costruisci_sessione(seed=1)  # il seed di run: l'insegna è derivata, non casuale
    insegna = insegna_laterale(Zona(tier=TierTerritorio.QUARTIERE, percorso=(0, 1, 2, 0, 3)))
    assert insegna.startswith("quartiere ")
    assert "(" not in insegna and not insegna.rstrip().endswith(("0", "3"))


def test_le_sorelle_hanno_insegne_DISTINTE(run_pulita) -> None:
    """Due deviazioni affacciate sulla stessa partenza non possono chiamarsi
    uguale: sarebbero due voci di menu indistinguibili."""
    from contracts import TierTerritorio
    from motore import Zona

    costruisci_sessione(seed=1)
    sorelle = [
        insegna_laterale(Zona(tier=TierTerritorio.QUARTIERE, percorso=(0, 0, 0, 0, i)))
        for i in range(3)
    ]
    assert len(set(sorelle)) == 3


def test_l_insegna_e_stabile_per_zona(run_pulita) -> None:
    """Stessa zona → stessa insegna, per sempre: il menu non cambia nome fra
    due visite (e il replay resta replay)."""
    from contracts import TierTerritorio
    from motore import Zona

    costruisci_sessione(seed=1)
    zona = Zona(tier=TierTerritorio.DISTRETTO, percorso=(1, 2, 3, 1))
    assert insegna_laterale(zona) == insegna_laterale(zona)
