"""Il canale loot → zaino → equip, ACCESO end-to-end (giro 2026-08-07).

Prima: `SistemaEquip` era l'unico Processor del motore mai registrato da un host,
gli intenti `PlayerEquipaggia`/`PlayerToglie` non avevano produttori (un intento
accodato marciva nel World, causando pure tick spurii), e non esisteva alcuna
generazione di bottino: l'oggetto dimostrativo era raggiungibile solo dai test.

Ora il CANALE esiste per intero: vittoria → drop seeded (`PROB_DROP` §11, stream
di sessione) → `Zaino` (posseduto, persistente) → porta `equipaggia`/`togli` →
manifest+effetti. La TABELLA dei drop è contenuto e oggi ha un solo oggetto:
questi test verificano il canale, non il bestiario.
"""

from __future__ import annotations

import asyncio

from contracts import PlayerChoseOption
from main import CronacaBus, carica_sessione, costruisci_sessione
from motore import calibrazione as cal
from motore import equip_attivo, fonti_zaino, mosse_di, protagonista


def _vinci_uno_scontro(sessione):
    snap = asyncio.run(sessione.prossima_narrazione())
    etichette = {o.etichetta: o.indice for o in snap.opzioni}
    sessione.coda.accoda(PlayerChoseOption(etichette["Combatti"]))
    snap = sessione.avanza()
    for _ in range(60):
        if snap.fase != "combattimento":
            return snap
        sessione.coda.accoda(PlayerChoseOption(0))     # Attacca
        snap = sessione.avanza()
    raise AssertionError("lo scontro non si è chiuso in 60 turni")


def test_il_canale_equip_e_acceso_end_to_end(run_pulita, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cal, "PROB_DROP", 1.0)         # drop garantito: si testa il canale
    sessione = costruisci_sessione(nome="Loot", seed=1, directory=tmp_path)
    cronaca = CronacaBus(sessione.bus)
    try:
        _vinci_uno_scontro(sessione)

        # 1. VITTORIA → DROP: la fonte è nello zaino, la cronaca lo annuncia,
        #    la scheda-vista lo espone all'host.
        pent, _m, _s = protagonista()
        assert "dadi-truccati" in fonti_zaino(pent)
        assert any(r.startswith("✦ Bottino:") for r in cronaca.preleva())
        assert "dadi-truccati" in sessione.scheda().zaino

        # 2. PORTA equipaggia → il manifest si popola e la mossa concessa arriva.
        assert "roulette_del_sistema" not in mosse_di(pent)
        sessione.equipaggia("dadi-truccati")
        assert "roulette_del_sistema" in mosse_di(pent)
        comp = equip_attivo(pent)
        assert comp is not None and comp.pezzo_per_fonte("dadi-truccati") is not None
        assert "dadi-truccati" in fonti_zaino(pent)    # possesso ≠ indosso

        # 3. PORTA togli → la mossa se ne va, il possesso resta.
        sessione.togli("dadi-truccati")
        assert "roulette_del_sistema" not in mosse_di(pent)
        assert "dadi-truccati" in fonti_zaino(pent)

        # 4. ROUND-TRIP (ADR-1 F5): zaino E manifest attraversano il save; al
        #    load l'hook di re-equip ri-deriva gli effetti — l'oggetto indossato
        #    resta indosso e la mossa concessa è viva senza rifare nulla.
        sessione.equipaggia("dadi-truccati")
        sessione.salva()
        uuid = sessione.uuid
        sessione.esci()
        ripresa = carica_sessione(uuid=uuid, directory=tmp_path)
        assert ripresa is not None
        pent2, _m2, _s2 = protagonista()
        assert "dadi-truccati" in fonti_zaino(pent2), "lo zaino non ha round-trippato"
        comp2 = equip_attivo(pent2)
        assert comp2 is not None and comp2.pezzo_per_fonte("dadi-truccati") is not None
        assert "roulette_del_sistema" in mosse_di(pent2)
        ripresa.togli("dadi-truccati")                 # e si può togliere subito
        assert "roulette_del_sistema" not in mosse_di(pent2)
    finally:
        cronaca.chiudi()


def test_senza_possesso_lequip_e_un_no_op(run_pulita, tmp_path) -> None:
    """Il gate del possesso: col catalogo globale si indossa solo ciò che il drop
    ha depositato. (Un catalogo esplicito passato a `SistemaEquip` resta la
    dichiarazione di possesso del chiamante: harness invariati.)"""
    sessione = costruisci_sessione(nome="NoLoot", seed=1, directory=tmp_path)
    asyncio.run(sessione.prossima_narrazione())
    pent, _m, _s = protagonista()
    assert fonti_zaino(pent) == ()
    sessione.equipaggia("dadi-truccati")
    assert "roulette_del_sistema" not in mosse_di(pent)
    assert equip_attivo(pent) is None


def test_il_drop_e_seeded_e_rispetta_la_probabilita(run_pulita, tmp_path, monkeypatch) -> None:
    """PROB_DROP=0 → mai bottino: il knob §11 governa il canale (e la pescata
    passa dallo stream di sessione, non da un RNG globale)."""
    monkeypatch.setattr(cal, "PROB_DROP", 0.0)
    sessione = costruisci_sessione(nome="Secco", seed=1, directory=tmp_path)
    _vinci_uno_scontro(sessione)
    pent, _m, _s = protagonista()
    assert fonti_zaino(pent) == ()
