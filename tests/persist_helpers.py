"""Helper condivisi per i test di persistenza (non è un modulo di test).

Assembla un run-World minimale nel contesto esper corrente: i singleton
(`FaseCorrente`, `ProfonditaPiano`, `TempoPiano`, `SemeRun`) + il protagonista, con
eventuali status applicati. Riflette ciò che il guscio costruirebbe a inizio run.
"""

from __future__ import annotations

import esper

from motore import (
    Fase,
    Veleno,
    applica_status,
    crea_entita_fase,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_tempo_piano,
    imposta_fase,
)


def costruisci_run(
    *,
    fase: Fase = Fase.NARRAZIONE,
    profondita: int = 1,
    master_seed: int = 12345,
    tempo: int = 0,
    destrezza: int = 10,
    hp: int = 30,
    id_dominio: str = "carl",
    veleno: tuple[int, int] | None = None,  # (rango, durata) opzionale
) -> int:
    """Crea i singleton + il protagonista nel World corrente. Ritorna l'entità protag."""
    crea_entita_fase()
    imposta_fase(fase)
    crea_profondita(profondita)
    crea_tempo_piano(tempo)
    crea_seme(master_seed)
    pent = crea_protagonista(destrezza=destrezza, punti_vita=hp, id_dominio=id_dominio)
    if veleno is not None:
        rango, durata = veleno
        applica_status(pent, Veleno(rango=rango, durata=durata))
    return pent
