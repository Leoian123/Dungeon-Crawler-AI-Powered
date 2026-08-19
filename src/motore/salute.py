"""Il proprietario UNICO della mutazione HP (registro §4.2-A, chiuso 2026-08-16).

«Dove vivono gli HP» era replicato in quattro funzioni con clamp diversi:
`status._applica_delta_hp` (clampava la cura), `combattimento.infliggi_danno`
(sottrazione secca), `combattimento._e_vivo` (lettura), `riposo.riposa` (clamp
suo). Quattro copie = quattro posti dove una nuova sede degli HP (o un nuovo
clamp) va ricordata a mano — e il primo dimenticato è un bug di desync.

Qui vive la RISOLUZIONE (protagonista → `Scheda.punti_vita`; nemico →
`PuntiVita.attuali`) e la POLITICA di clamp, una volta sola:
  - la CURA si clampa al massimo derivato (`max_hp` per il protagonista,
    `massimi` per il nemico): mai HP sopra il tetto;
  - il DANNO è sottrazione secca, MAI floor a zero: il death-check legge
    `<= 0` e il margine negativo è informazione (quanto oltre la soglia).
    Il floor per la VISTA è compito di chi confeziona i descrittori.

Modulo foglia con import pigri: status/combattimento/riposo lo importano,
lui non importa nessuno di loro in testa (niente cicli).
"""

from __future__ import annotations

import esper


def hp_di(entita: int) -> tuple[int, int] | None:
    """(attuali, massimi) di chiunque abbia HP; `None` se l'entità non ne ha.

    Il massimo del protagonista è il DERIVATO (`max_hp`: Costituzione + gear),
    non un campo salvato: la stessa verità che usa il clamp della cura."""
    from .scheda import Scheda

    scheda = esper.try_component(entita, Scheda)
    if scheda is not None:
        from .derivate import max_hp

        return scheda.punti_vita, max_hp(entita)
    from .combattimento import PuntiVita

    pv = esper.try_component(entita, PuntiVita)
    if pv is not None:
        return pv.attuali, pv.massimi
    return None


def muovi_hp(entita: int, delta: int) -> int | None:
    """L'UNICA scrittura degli HP: applica `delta` (cura clampata al massimo,
    danno secco) e ritorna gli HP risultanti — `None` se l'entità non ha HP."""
    from .scheda import Scheda

    scheda = esper.try_component(entita, Scheda)
    if scheda is not None:
        if delta > 0:
            from .derivate import max_hp

            scheda.punti_vita = min(scheda.punti_vita + delta, max_hp(entita))
        else:
            scheda.punti_vita += delta
        return scheda.punti_vita
    from .combattimento import PuntiVita

    pv = esper.try_component(entita, PuntiVita)
    if pv is None:
        return None
    pv.attuali = min(pv.attuali + delta, pv.massimi) if delta > 0 else pv.attuali + delta
    return pv.attuali
