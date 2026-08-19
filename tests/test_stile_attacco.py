"""Stile marziale vs magico: due accuratezze separate (Des vs Int) lungo tutta la
filiera — catalogo mosse, canale-asset, risolutore. Contesto esper isolato (ESP §0.1).

Il discriminante osservabile è la regola dell'auto-hit del check 1: sotto la banda
(`eva < acc/F`) il colpo connette SENZA pescare. Un attaccante con Intelligenza
enorme e Destrezza minima è in auto-hit SOLO con lo stile magico: contare le
pescate distingue quale accuratezza il risolutore ha davvero usato.
"""

from __future__ import annotations

import random

import esper
import pytest

from contracts import EffettoDati, MossaAsset, StatId, StileAttacco, TipoDanno
from motore import Corredo, Primarie
from motore.azione import Danno, QuantitaDa
from motore.combattimento import risolvi_danno
from motore.mosse import CATALOGO_MOSSE, mossa_da_dati


class _SpiaRng:
    """RNG che delega e conta: distingue l'auto-hit (zero pescate) dalla banda."""

    def __init__(self, seed: int) -> None:
        self._inner = random.Random(seed)
        self.pescate = 0

    def random(self) -> float:
        self.pescate += 1
        return self._inner.random()


def _mago_e_dodger() -> tuple[int, int]:
    """Attaccante Int-enorme/Des-minima contro un bersaglio evasivo (in banda per
    un'accuratezza marziale bassa, sotto-soglia per quella magica enorme)."""
    mago = esper.create_entity(
        Primarie(valori={StatId.FORZA: 10, StatId.DESTREZZA: 1, StatId.INTELLIGENZA: 1000})
    )
    dodger = esper.create_entity(
        Primarie(valori={StatId.DESTREZZA: 20, StatId.COSTITUZIONE: 1}),
        Corredo(armatura="veste", taglia="infima", arma="naturale"),
    )
    return mago, dodger


def test_il_risolutore_mira_con_la_stat_dello_stile(mondo_isolato: str) -> None:
    mago, dodger = _mago_e_dodger()

    # Stile MAGICO: acc_mag (Int 1000) ≫ soglia → auto-hit deterministico, ZERO pescate.
    rng = _SpiaRng(7)
    inflitto = risolvi_danno(
        Danno(quantita_da=QuantitaDa.ATK_EFF, tipo=TipoDanno.FUOCO, stile=StileAttacco.MAGICO),
        mago, dodger, rng,
    )
    assert rng.pescate == 0 and inflitto > 0, "il magico deve mirare con Intelligenza (auto-hit)"

    # Stile FISICO (default): acc_fis (Des 1) è minuscola → il contest PESCA.
    rng = _SpiaRng(7)
    risolvi_danno(Danno(quantita_da=QuantitaDa.ATK_EFF, tipo=TipoDanno.MISCHIA), mago, dodger, rng)
    assert rng.pescate == 1, "il marziale deve mirare con Destrezza (in banda: una pescata)"


def test_il_catalogo_dichiara_gli_stili(mondo_isolato: str) -> None:
    # Gli incantesimi mirano con Int; le mosse marziali restano al default FISICO.
    assert CATALOGO_MOSSE["dardo_arcano"].effetti[0].stile is StileAttacco.MAGICO
    assert CATALOGO_MOSSE["roulette_del_sistema"].effetti[0].stile is StileAttacco.MAGICO
    assert CATALOGO_MOSSE["attacco"].effetti[0].stile is StileAttacco.FISICO
    assert CATALOGO_MOSSE["attacco_pesante"].effetti[0].stile is StileAttacco.FISICO


def test_il_canale_asset_trasporta_lo_stile(mondo_isolato: str) -> None:
    # Una mossa-asset che dichiara lo stile lo ritrova sul primitivo vivo; senza
    # dichiarazione vale il default FISICO (backward-compatible).
    magica = MossaAsset(
        slug="dardo-gelido", etichetta="Dardo gelido",
        effetti=[EffettoDati(primitivo="danno", tipo_danno=TipoDanno.FUOCO,
                             stile=StileAttacco.MAGICO)],
    )
    assert mossa_da_dati(magica).effetti[0].stile is StileAttacco.MAGICO

    muta = MossaAsset(
        slug="zampata", etichetta="Zampata",
        effetti=[EffettoDati(primitivo="danno", tipo_danno=TipoDanno.MISCHIA)],
    )
    assert mossa_da_dati(muta).effetti[0].stile is StileAttacco.FISICO


def test_stile_su_applica_status_e_rifiutato() -> None:
    # `stile` è un campo di danno: su `applica_status` il gate di composizione rifiuta.
    with pytest.raises(ValueError, match="campi di danno"):
        MossaAsset(
            slug="tocco", etichetta="Tocco",
            effetti=[
                EffettoDati(primitivo="danno", tipo_danno=TipoDanno.MISCHIA),
                EffettoDati(primitivo="applica_status", blocco="veleno",
                            stile=StileAttacco.MAGICO),
            ],
        )
