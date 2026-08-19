"""Equipaggiamento ADR-1 **F5**: persistenza normalizzata del manifest.

La coppia che rende sicuro il tag `"equip"` nel save:
  - **filtro di provenienza** nel save (`filtrato_per_save`): le voci di
    `Modificatori`/`Resistenze` derivate dall'equip NON viaggiano — la sorgente
    durevole è il manifest;
  - **hook di re-equip** al load (`re_equipaggia` in `applica_stato`): le voci
    rinascono dal manifest, poi `clampa_hp` (D2).

L'oracolo della coppia è il round-trip save→load→save **byte-identico**: se il
filtro manca, il secondo save porta voci doppie; se l'hook manca, il secondo
save perde le voci — in entrambi i casi i byte divergono.
"""

from __future__ import annotations

import json

import esper

from contracts import CategoriaArmatura, SedeAccessorio, SlotEquip, StatId, Taglia, TipoDanno
from motore import (
    Accessorio,
    Modificatore,
    PezzoArmatura,
    TipoMod,
    applica_stato,
    carica_da_disco,
    equip_attivo,
    equipaggia,
    max_hp,
    salva_run,
    stat_eff,
)
from motore.equip import assicura_zaino, mosse_da_equip
from motore.modificatori import Modificatori, ResistenzaMod, Resistenze
from motore.persistenza.disco import path_stato
from motore.scheda import Scheda
from tests.persist_helpers import costruisci_run

_PETTO = PezzoArmatura(
    fonte="pettorale-di-latta#1",
    slot=SlotEquip.BUSTO,
    categoria=CategoriaArmatura.MEDIA,
    nome="Pettorale di latta",
    taglia=Taglia.MEDIA,
    modificatori=(
        Modificatore(stat=StatId.COSTITUZIONE, tipo=TipoMod.FLAT, valore=4,
                     fonte="pettorale-di-latta#1"),
    ),
    resistenze=(
        ResistenzaMod(contro=TipoDanno.FUOCO, valore=-0.2, fonte="pettorale-di-latta#1"),
    ),
)

_ANELLO = Accessorio(
    fonte="anello-del-croupier#1",
    sede=SedeAccessorio.DITA,
    nome="Anello del croupier",
    mosse=("roulette_del_sistema",),
)


def _dump_canali(ent: int) -> str:
    """La fotografia confrontabile dei canali derivabili (l'oracolo)."""
    mods = esper.try_component(ent, Modificatori)
    res = esper.try_component(ent, Resistenze)
    return json.dumps({
        "mods": sorted((v.stat.value, v.tipo.value, v.valore, v.fonte)
                       for v in (mods.voci if mods else [])),
        "res": sorted((v.contro.value, v.valore, v.fonte)
                      for v in (res.voci if res else [])),
    })


def _arma_ed_equipaggia() -> int:
    pent = costruisci_run(hp=30)
    zaino = assicura_zaino(pent)
    zaino.fonti += [_PETTO.fonte, _ANELLO.fonte]
    assert equipaggia(pent, _PETTO) and equipaggia(pent, _ANELLO)
    return pent


def test_roundtrip_senza_desync(mondo_isolato: str, tmp_path) -> None:
    pent = _arma_ed_equipaggia()
    stat_prima = stat_eff(pent, StatId.COSTITUZIONE)
    max_prima = max_hp(pent)
    canali_prima = _dump_canali(pent)

    salva_run(tmp_path, model_id="m1", timestamp=1.0)
    primo_save = path_stato(tmp_path, "carl").read_text(encoding="utf-8")

    esper.clear_database()
    applica_stato(carica_da_disco(tmp_path, "carl"))
    from motore import protagonista

    pent2, _m, _s = protagonista()

    # Gli effetti dell'equip sono VIVI dopo il load (hook di re-equip).
    assert stat_eff(pent2, StatId.COSTITUZIONE) == stat_prima
    assert max_hp(pent2) == max_prima
    assert _dump_canali(pent2) == canali_prima
    manifest = equip_attivo(pent2)
    assert manifest is not None and set(manifest.fonti()) == {_PETTO.fonte, _ANELLO.fonte}
    # La mossa concessa resta derivata (mai nel Repertorio persistente).
    assert "roulette_del_sistema" in mosse_da_equip(pent2)

    # save→load→save: byte-identico sul file di stato = niente voci doppie
    # (filtro) e niente voci perse (hook). È l'oracolo della coppia.
    salva_run(tmp_path, model_id="m1", timestamp=1.0)
    secondo_save = path_stato(tmp_path, "carl").read_text(encoding="utf-8")
    assert secondo_save == primo_save


def test_il_save_non_porta_voci_derivate(mondo_isolato: str, tmp_path) -> None:
    pent = _arma_ed_equipaggia()
    salva_run(tmp_path, model_id="m1", timestamp=1.0)
    testo = path_stato(tmp_path, "carl").read_text(encoding="utf-8")
    corpo = json.loads(testo.splitlines()[1])  # riga 1 = header, riga 2 = corpo
    # Nel payload il manifest c'è; nessuna voce di Modificatori/Resistenze con
    # la fonte dell'equip (viaggiano SOLO nel manifest).
    assert '"equip"' in testo
    voci_mod = [
        v
        for ent in corpo["entita"]
        for comp in ent["componenti"] if comp["tag"] in ("modificatori", "resistenze")
        for v in comp["dati"]["voci"]
    ]
    assert all(v["fonte"] not in (_PETTO.fonte, _ANELLO.fonte) for v in voci_mod)
    # ...e i canali VIVI nel World non sono stati toccati dal save (il filtro
    # lavora su una copia).
    assert any(v.fonte == _PETTO.fonte
               for v in esper.component_for_entity(pent, Modificatori).voci)


def test_clampa_hp_al_load_su_malus_costituzione(mondo_isolato: str, tmp_path) -> None:
    """D2 dopo un load: un pezzo con −COSTITUZIONE abbassa il tetto e il
    corrente deve seguirlo anche nel mondo ricaricato."""
    pent = costruisci_run(hp=30)
    maledetto = PezzoArmatura(
        fonte="cilicio#1", slot=SlotEquip.BUSTO, categoria=CategoriaArmatura.VESTE,
        modificatori=(Modificatore(stat=StatId.COSTITUZIONE, tipo=TipoMod.FLAT,
                                   valore=-8, fonte="cilicio#1"),),
    )
    assicura_zaino(pent).fonti.append(maledetto.fonte)
    assert equipaggia(pent, maledetto)
    tetto_ridotto = max_hp(pent)
    assert esper.component_for_entity(pent, Scheda).punti_vita <= tetto_ridotto

    salva_run(tmp_path, model_id="m1", timestamp=1.0)
    esper.clear_database()
    applica_stato(carica_da_disco(tmp_path, "carl"))
    from motore import protagonista

    pent2, _m, _s = protagonista()
    assert max_hp(pent2) == tetto_ridotto
    assert esper.component_for_entity(pent2, Scheda).punti_vita <= tetto_ridotto


def test_save_legacy_senza_manifest_resta_da_riequipaggiare(mondo_isolato: str, tmp_path) -> None:
    """Un save scritto senza il tag equip (o un crawler mai equipaggiato) carica
    come oggi: zaino pieno, nessun manifest, nulla di rotto."""
    pent = costruisci_run(hp=30)
    assicura_zaino(pent).fonti.append("dadi-truccati")
    salva_run(tmp_path, model_id="m1", timestamp=1.0)
    esper.clear_database()
    applica_stato(carica_da_disco(tmp_path, "carl"))
    from motore import protagonista

    pent2, _m, _s = protagonista()
    assert equip_attivo(pent2) is None
    from motore.equip import fonti_zaino

    assert fonti_zaino(pent2) == ("dadi-truccati",)
