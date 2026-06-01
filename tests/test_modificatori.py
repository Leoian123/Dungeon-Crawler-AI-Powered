"""Modificatori: rimozione per `fonte`, coesistenza, gate privilegiato, tag stabile
(Gruppo 2 §4/§2.4). Copre GR2-7, GR2-8, GR2-16.
"""

from __future__ import annotations

import typing

import esper

from contracts import StatId
from motore import (
    Modificatore,
    Origine,
    Primarie,
    TipoMod,
    applica_modificatore,
    rimuovi_per_fonte,
    stat_eff,
)


# --- GR2-7: rimozione per `fonte` senza operazione inversa; fonti che sommano ---

def test_GR2_7_rimozione_per_fonte_ripristina(mondo_isolato: str) -> None:
    ent = esper.create_entity(Primarie(valori={StatId.FORZA: 10}))
    base = stat_eff(ent, StatId.FORZA)

    applica_modificatore(ent, Modificatore(StatId.FORZA, TipoMod.FLAT, 5, "equip"))
    applica_modificatore(ent, Modificatore(StatId.FORZA, TipoMod.PCT, 0.20, "buff"))
    # Due fonti diverse sulla stessa stat coesistono e sommano: (10+5)×1.20 = 18.
    assert stat_eff(ent, StatId.FORZA) == 18

    # Togliere una fonte ripristina, senza inversione di operazioni: (10)×1.20 = 12.
    rimuovi_per_fonte(ent, "equip")
    assert stat_eff(ent, StatId.FORZA) == 12

    # Togliere l'ultima fonte riporta esattamente al valore pre-applicazione.
    rimuovi_per_fonte(ent, "buff")
    assert stat_eff(ent, StatId.FORZA) == base


def test_GR2_7_rimozione_fonte_inesistente_e_innocua(mondo_isolato: str) -> None:
    ent = esper.create_entity(Primarie(valori={StatId.FORZA: 10}))
    rimuovi_per_fonte(ent, "mai_applicata")  # nessun componente Modificatori: no-op
    assert stat_eff(ent, StatId.FORZA) == 10


# --- GR2-8: una stat SOLO_PRIVILEGIATI accetta solo origine=PRIVILEGIATA --------

def test_GR2_8_gate_privilegiato(mondo_isolato: str) -> None:
    # SAGGEZZA è SOLO_PRIVILEGIATI nel registry (canone DCC).
    ent = esper.create_entity(Primarie(valori={StatId.SAGGEZZA: 8}))

    # Un modificatore NORMALE viene ignorato dal fold.
    applica_modificatore(ent, Modificatore(StatId.SAGGEZZA, TipoMod.FLAT, 10, "equip", Origine.NORMALE))
    assert stat_eff(ent, StatId.SAGGEZZA) == 8

    # Un modificatore PRIVILEGIATA (zona speciale) invece passa.
    applica_modificatore(
        ent, Modificatore(StatId.SAGGEZZA, TipoMod.FLAT, 10, "zona", Origine.PRIVILEGIATA)
    )
    assert stat_eff(ent, StatId.SAGGEZZA) == 18

    # Su una stat TUTTI (FORZA), anche il NORMALE passa (il gate è per-stat-dato, non globale).
    ent2 = esper.create_entity(Primarie(valori={StatId.FORZA: 10}))
    applica_modificatore(ent2, Modificatore(StatId.FORZA, TipoMod.FLAT, 5, "equip", Origine.NORMALE))
    assert stat_eff(ent2, StatId.FORZA) == 15


# --- GR2-16: `fonte` è un tag di dominio stabile (str), mai un id esper ---------

def test_GR2_16_fonte_e_tag_stabile_str() -> None:
    # La forma-dato impone un tag, non un riferimento vivo: l'annotazione di `fonte` è str.
    hints = typing.get_type_hints(Modificatore)
    assert hints["fonte"] is str
    # Morde: se `fonte` fosse `int` (un id esper), questo controllo fallirebbe.
    assert hints["fonte"] is not int
