"""Il riposo di scena — l'anello «sostentati» del giro (J §5, FNC §4).

Tre strati esistevano già e nessun percorso li cuciva (giro 2026-08-07):
`TipoAzione.RIPOSA` nel contratto, la foglia `DURATA_AZIONE.riposa` in
calibrazione, `RiposoConcluso` con la sua riga di cronaca già scritta. Qui vive
il centro: la durata si spende via `fast_forward` (downtime lecito, J §5), i
tick ESEGUITI si convertono in HP/mana dalle foglie §11, l'evento si pubblica.

La scrittura degli HP passa dal clamp al massimo DERIVATO — stesso contratto
di cura di `status._applica_delta_hp` (il punto del registro debito
«proprietario unico degli HP» copre anche questa sede).

L'imboscata che interromperebbe il riposo resta un seam dichiarato
(`componi_imboscata` non ancora collegato, vedi `tempo.fast_forward`): quando
verrà cucita, `RiposoConcluso.interrotto=True` e il recupero parziale sui tick
reali sono GIÀ il comportamento di questa funzione — i tick eseguiti sono
quelli che `fast_forward` ha davvero speso.
"""

from __future__ import annotations

import esper

from contracts import RiposoConcluso, TipoAzione

from .calibrazione import DURATA_AZIONE, RIPOSO_HP_PER_TICK, RIPOSO_MANA_PER_TICK
from .derivate import max_mana
from .scheda import Mana, protagonista
from .tempo import fast_forward, puo_downtime


def riposa(bus) -> RiposoConcluso | None:
    """UN riposo completo. `None` = downtime non lecito (combattimento, status
    dannoso o unsafe): niente tick spesi, niente recupero, il chiamante decide
    come dirlo.

    Il recupero è `tick × foglia §11`, clampato ai massimi derivati: il riposo
    non gonfia mai oltre il tetto, e un riposo fermato a metà avrà recuperato
    solo i tick reali (atomicità di `fast_forward`)."""
    if not puo_downtime():
        return None
    from .incontri import componi_imboscata_scena  # pigro: riposo è un modulo foglia

    # Il seam è cucito SOLO con un bus vero: senza bus (harness) un incontro
    # composto non avrebbe l'evento di transizione — meglio nessun agguato che
    # un World incoerente.
    esito = fast_forward(
        bus, DURATA_AZIONE[TipoAzione.RIPOSA],
        componi_imboscata=componi_imboscata_scena if bus is not None else None,
    )
    tick = esito.tick_eseguiti

    pent, _marker, scheda = protagonista()
    prima_hp = scheda.punti_vita
    # La cura passa dal proprietario UNICO della mutazione HP (`salute.muovi_hp`):
    # il clamp al massimo derivato è la POLITICA di quel modulo, non una copia qui.
    # La COMPETENZA di riposo (nodo S6) alza la resa per tick — 0 a livello 1.
    from .salute import muovi_hp
    from .skill import bonus_resa_riposo

    muovi_hp(pent, tick * (RIPOSO_HP_PER_TICK + bonus_resa_riposo()))
    hp_recuperati = scheda.punti_vita - prima_hp

    mana = esper.try_component(pent, Mana)
    mana_recuperato = 0
    if mana is not None:
        prima_mana = mana.attuale
        mana.attuale = min(max_mana(pent), prima_mana + tick * RIPOSO_MANA_PER_TICK)
        mana_recuperato = mana.attuale - prima_mana

    evento = RiposoConcluso(
        tick_spesi=tick, hp_recuperati=hp_recuperati, mana_recuperato=mana_recuperato,
        interrotto=esito.interrotto_da is not None,
    )
    if bus is not None:
        bus.pubblica(evento)
    return evento
