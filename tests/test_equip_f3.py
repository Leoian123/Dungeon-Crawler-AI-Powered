"""Equipaggiamento ADR-1 **F3**: `coeff_eva` come media pesata, un solo proprietario.

È l'unica modifica strutturale del blocco equip, e ha tre proprietà da difendere:

1. **Non-regressione esatta.** Con tutti gli slot vuoti la media pesata vale
   `M_ARMATURA["veste"]` **bit-per-bit**: la media è una combinazione convessa
   (Σ pesi = 1), quindi il punto degenere coincide col comportamento di prima. Senza
   questo, aprire il seam avrebbe spostato in silenzio ogni numero del gioco.
2. **Un solo proprietario della geometria.** `m_armatura_di` è l'unica funzione che
   risponde a "quanto ti impaccia l'armatura", con una cascata a tre livelli. Due
   percorsi (uno per il protagonista equipaggiato, uno per i mob) divergerebbero.
3. **La taglia non è equipaggiamento.** Resta per-entità: un gatto in piastra resta un
   gatto: la corazza cambia quanto è agile, non quanto è grande.
"""

from __future__ import annotations

from contracts import SLOT_ARMATURA, CategoriaArmatura, SlotEquip, StatId
from motore import (
    K_EVA,
    M_ARMATURA,
    M_TAGLIA,
    Corredo,
    PezzoArmatura,
    crea_protagonista,
    equipaggia,
    eva_eff,
    m_armatura_di,
    stat_eff,
    togli,
)
from motore.calibrazione import ARMATURA_DEFAULT, PESI_SLOT_ARMATURA, TAGLIA_DEFAULT

import esper


def _pezzo(slot: SlotEquip, categoria: CategoriaArmatura) -> PezzoArmatura:
    return PezzoArmatura(fonte=f"p-{slot.value}", slot=slot, categoria=categoria)


# --- 1. I pesi sono una media, non una somma qualunque ------------------------

def test_i_pesi_sommano_a_uno() -> None:
    """Se non sommassero a 1 non sarebbe una media: riempire slot cambierebbe la
    **scala** dell'evasione invece della sola composizione, e ogni taratura del check 1
    andrebbe rifatta a ogni pezzo indossato."""
    assert abs(sum(PESI_SLOT_ARMATURA.values()) - 1.0) < 1e-9, PESI_SLOT_ARMATURA


def test_i_pesi_coprono_esattamente_gli_slot_armatura() -> None:
    # Invariante #7 fra il vocabolario (`contracts`) e i numeri (`calibrazione`): uno
    # slot senza peso sparirebbe dalla media senza che nulla protesti.
    assert set(PESI_SLOT_ARMATURA) == {s.value for s in SLOT_ARMATURA}
    assert SlotEquip.ARMA.value not in PESI_SLOT_ARMATURA, (
        "il mount impugnato non entra nella media dell'armatura (ADR-1 D5)"
    )


# --- 2. Non-regressione: il punto degenere vale ESATTAMENTE come prima --------

def test_senza_equip_la_media_vale_la_veste_bit_per_bit(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    assert m_armatura_di(pent) == M_ARMATURA[ARMATURA_DEFAULT]


def test_un_manifest_vuoto_non_cambia_nulla(mondo_isolato: str) -> None:
    """Il caso insidioso: il componente ESISTE (magari perché il giocatore si è tolto
    l'ultimo pezzo) ma non ha armatura. Deve valere quanto non averlo affatto."""
    from motore import equip_di
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    prima = eva_eff(pent)
    equip_di(pent)                                  # crea il manifest, vuoto
    assert eva_eff(pent) == prima


def test_mettere_e_togliere_riporta_allo_stesso_valore(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    prima = m_armatura_di(pent)
    equipaggia(pent, _pezzo(SlotEquip.BUSTO, CategoriaArmatura.PESANTE))
    assert m_armatura_di(pent) < prima
    togli(pent, "p-busto")
    assert m_armatura_di(pent) == prima


# --- 3. La media pesata fa quello che dice ------------------------------------

def test_un_solo_pezzo_sposta_la_media_del_suo_peso(mondo_isolato: str) -> None:
    """Il valore atteso è calcolabile a mano, ed è il punto: la formula non è una
    scatola nera, è `Σ peso · mobilità`."""
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    base = M_ARMATURA["veste"]
    equipaggia(pent, _pezzo(SlotEquip.BUSTO, CategoriaArmatura.PESANTE))

    delta_atteso = PESI_SLOT_ARMATURA["busto"] * (M_ARMATURA["pesante"] - base)
    assert abs(m_armatura_di(pent) - (base + delta_atteso)) < 1e-9


def test_tutto_addosso_la_media_collassa_sulla_categoria(mondo_isolato: str) -> None:
    # Nove slot della stessa categoria = quella categoria, esattamente (Σ pesi = 1).
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    for slot in SLOT_ARMATURA:
        equipaggia(pent, _pezzo(slot, CategoriaArmatura.PESANTE))
    assert abs(m_armatura_di(pent) - M_ARMATURA["pesante"]) < 1e-9


def test_piu_piastra_meno_schivata(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    letture = [eva_eff(pent)]
    for slot in SLOT_ARMATURA:
        equipaggia(pent, _pezzo(slot, CategoriaArmatura.PESANTE))
        letture.append(eva_eff(pent))
    assert letture == sorted(letture, reverse=True), (
        f"l'evasione deve scendere a ogni pezzo di piastra: {letture}"
    )


def test_una_veste_addosso_equivale_a_essere_nudi(mondo_isolato: str) -> None:
    """La veste è il fondo della scala: indossarla non deve fare differenza rispetto
    allo slot vuoto, o "spogliarsi" diventerebbe una strategia di evasione."""
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    nudo = m_armatura_di(pent)
    for slot in SLOT_ARMATURA:
        equipaggia(pent, _pezzo(slot, CategoriaArmatura.VESTE))
    assert abs(m_armatura_di(pent) - nudo) < 1e-9


# --- 4. La cascata a tre livelli ----------------------------------------------

def test_il_corredo_resta_la_sorgente_per_chi_non_ha_oggetti(mondo_isolato: str) -> None:
    """Livello 2: i mob generati non hanno un manifest, hanno una categoria. Il loro
    `m_armatura` non deve regredire a un default globale silenzioso (dip. #3)."""
    mob = esper.create_entity(Corredo(armatura="pesante", taglia="grossa", arma="naturale"))
    assert m_armatura_di(mob) == M_ARMATURA["pesante"]


def test_il_manifest_ha_la_precedenza_sul_corredo(mondo_isolato: str) -> None:
    """Livello 1 batte livello 2: se un'entità ha entrambi, comanda ciò che INDOSSA.
    Il `Corredo` è la categoria di default del corpo, non un secondo strato che somma."""
    ent = esper.create_entity(Corredo(armatura="pesante", taglia="media", arma="naturale"))
    equipaggia(ent, _pezzo(SlotEquip.BUSTO, CategoriaArmatura.VESTE))
    atteso = (
        M_ARMATURA["veste"] * PESI_SLOT_ARMATURA["busto"]
        + M_ARMATURA["veste"] * (1 - PESI_SLOT_ARMATURA["busto"])
    )
    assert abs(m_armatura_di(ent) - atteso) < 1e-9, (
        "col manifest attivo gli slot vuoti valgono VESTE, non la categoria del Corredo: "
        "il Corredo è il livello che si usa quando il manifest NON c'è"
    )


def test_un_solo_proprietario_della_mobilita() -> None:
    """**Tutte** le letture di `M_ARMATURA` vivono dentro `m_armatura_di`.

    Sull'AST e non sul testo: un conteggio di stringhe conterebbe anche i commenti, e
    finirebbe per vietare di *spiegare* la formula. Qui si vieta solo di *duplicarla*
    — che è il rischio vero: un secondo lettore della tabella diventa un secondo
    proprietario della geometria, e i due divergono al primo ritocco dei pesi."""
    import ast
    from pathlib import Path

    albero = ast.parse(
        (Path(__file__).resolve().parents[1] / "src" / "motore" / "derivate.py").read_text(
            encoding="utf-8"
        )
    )

    def _letture(nodo) -> int:
        return sum(
            1 for n in ast.walk(nodo)
            if isinstance(n, ast.Subscript)
            and isinstance(n.value, ast.Attribute)
            and n.value.attr == "M_ARMATURA"
        )

    proprietaria = next(
        n for n in ast.walk(albero)
        if isinstance(n, ast.FunctionDef) and n.name == "m_armatura_di"
    )
    assert _letture(proprietaria) >= 1
    assert _letture(albero) == _letture(proprietaria), (
        "qualcuno legge M_ARMATURA fuori da `m_armatura_di`: è un secondo proprietario "
        "della mobilità, e la cascata a tre livelli smette di essere l'unica verità"
    )


# --- 5. La taglia è del corpo, non dell'armatura ------------------------------

def test_la_taglia_non_cambia_indossando_armatura(mondo_isolato: str) -> None:
    gatto = esper.create_entity(
        Corredo(armatura="veste", taglia="infima", arma="naturale"),
    )
    esper.add_component(gatto, _primarie_di(destrezza=20))
    prima = eva_eff(gatto)
    equipaggia(gatto, _pezzo(SlotEquip.BUSTO, CategoriaArmatura.PESANTE))
    dopo = eva_eff(gatto)

    # L'armatura riduce l'evasione (mobilità), ma il fattore-taglia resta quello di un
    # essere infimo: il rapporto fra le due letture non può dipendere dalla taglia.
    assert dopo < prima
    assert M_TAGLIA["infima"] != M_TAGLIA[TAGLIA_DEFAULT], "test cieco: taglie identiche"
    atteso = (
        stat_eff(gatto, StatId.DESTREZZA) * K_EVA * m_armatura_di(gatto) * M_TAGLIA["infima"]
    )
    assert abs(dopo - atteso) < 1e-9


def _primarie_di(*, destrezza: int):
    from motore import Primarie, primarie_da_scalari
    valori = dict(primarie_da_scalari(destrezza=destrezza, punti_vita=10))
    return Primarie(valori=valori)
