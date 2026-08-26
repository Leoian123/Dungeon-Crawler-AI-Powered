"""Quantità derivate dal combattimento: funzioni, mai stat depositate (Gruppo 2 §5).

`max_HP`, attacco, iniziativa, e le derivate del risolutore (`atk_eff`, `def_eff`,
`eva_eff`, `acc_fis_eff`/`acc_mag_eff`) **non** sono stat scritte: sono **derivate** dalle primarie effettive
a runtime, leggendo `stat_eff` (GR2-3 — nessuna lettura diretta di `Primarie[...]`). Un
modificatore su una primaria si propaga **da solo** alla derivata. I *numeri* (tabelle,
pesi, coefficienti) sono SEGNAPOSTO §11 e vivono in `calibrazione.py`, **importati** qui,
mai inline (guida §0).

`HP_corrente` è invece **stato posseduto** (in `Scheda.punti_vita`): l'unico pezzo del
modello-stat mutato direttamente (dal danno), distinto dalle primarie del vettore. Il suo
*massimo* deriva da Costituzione; `clampa_hp` lo tiene ≤ massimo derivato.

**Contratto di scala (§6, da non sbagliare):** `atk_eff` è in **unità**, `def_eff` in
**centesimi** (la conversione `/100` vive nel danno, non qui). `eva_eff` e le due
accuratezze sono scalari (float) del check 1.
"""

from __future__ import annotations

import esper

from contracts import CategoriaArmatura, SlotEquip, StatId, StileAttacco

from . import calibrazione as cal
from .corredo import Corredo
from .equip import ComponenteEquip
from .scheda import Scheda
from .statistiche import stat_eff


def geometria_di(entita: int) -> tuple[str, str, str]:
    """Slot gear (armatura, taglia, arma) dell'entità: il suo `Corredo` se presente,
    altrimenti i **default globali** (`*_DEFAULT`). È l'apertura del seam gear: entità senza
    `Corredo` (protagonista, nemici-da-scalari) restano ai valori odierni, bit-per-bit.

    Pubblica perché è anche la fonte di `EquipVista`: la scheda mostra la geometria
    ATTIVA (ciò che muove le derivate) senza che l'host debba leggere il World."""
    c = esper.try_component(entita, Corredo)
    if c is None:
        return cal.ARMATURA_DEFAULT, cal.TAGLIA_DEFAULT, cal.ARMA_DEFAULT
    return c.armatura, c.taglia, c.arma


_geometria = geometria_di  # alias storico (call-site interni di questo modulo)


def max_hp(entita: int) -> int:
    """Massimo HP derivato da Costituzione (risorsa-pool, §5): `HP_BASE + K_HP·Cost`.

    `round(...) → int`: l'HP è un intero anche con `K_HP` frazionario (leva di calibrazione)."""
    return round(cal.HP_BASE + cal.K_HP * stat_eff(entita, StatId.COSTITUZIONE))


def max_mana(entita: int) -> int:
    """Massimo mana derivato da Intelligenza: `MANA_BASE + K_MANA·Int` (§11).
    Stessa dottrina di `max_hp`: il massimo non è depositato, deriva."""
    return round(cal.MANA_BASE + cal.K_MANA * stat_eff(entita, StatId.INTELLIGENZA))


def attacco(entita: int) -> int:
    """Attacco/danno base derivato da Forza (mischia MVP, §5). Vedi `atk_eff` (check 2)."""
    return stat_eff(entita, StatId.FORZA)


def iniziativa(entita: int) -> int:
    """Iniziativa derivata da Destrezza (§5/§6) — è una **lettura**, non muta la stat.
    La Destrezza **non** entra nel danno (check 2): alimenta iniziativa ed evasione."""
    return stat_eff(entita, StatId.DESTREZZA)


# --- Le quattro derivate del risolutore a due check (§5/§6, GR2-10) ------------

def atk_eff(att: int) -> int:
    """Offesa del check 2, in **unità** (§5.1): `stat_eff(FORZA)` + il danno
    dell'arma IMPUGNATA (review-armi 2026-08-26, nodo B1: il layer impugnato è
    SVEGLIO — in un gioco senza livelli la progressione offensiva viaggia
    sull'equip, come quella difensiva già faceva via fascia×rango). Le entità
    senza manifest equip non si muovono di un punto: lo scaling dei mob resta
    `K_RANGO_DANNO`. Niente Destrezza nel danno."""
    return stat_eff(att, StatId.FORZA) + danno_arma_impugnata(att)


def danno_arma_impugnata(entita: int) -> int:
    """Il contributo dell'arma indossata: `danno_base` del pezzo nel mount
    ARMA (0 a mani nude o senza manifest — il degrado è il comportamento
    storico, mai un crash). Import locale: derivate resta a monte di equip."""
    from .equip import equip_attivo

    comp = equip_attivo(entita)
    if comp is None or comp.arma is None:
        return 0
    return max(0, int(comp.arma.danno_base))


def cost_eff_come_centesimi(ber: int) -> int:
    """Termine muscolare di `def_eff`, in **centesimi** interi (§5.2). `0.01·Cost` (unità)
    vale numericamente `Cost_eff` centesimi — UNA conversione d'unità, esplicita, qui.

    È **fuori** dal fold di `DIFESA` (asimmetria voluta, §5.2): un PCT su `DIFESA` (enchant
    d'armatura) scala solo la somma-armatura, non i muscoli; il termine muscolare si muove
    solo via `Cost_eff`."""
    return stat_eff(ber, StatId.COSTITUZIONE)  # 0.01·Cost (unità) == Cost_eff centesimi


def def_eff(ber: int) -> int:
    """Mitigazione piatta del check 2, in **centesimi** (§5.2). Due addendi separati, ENTRAMBI
    centesimi: il termine muscolare (`cost_eff_come_centesimi`) e l'armatura (`stat_eff(DIFESA)`,
    già in centesimi via `finalizza="centesimi_floor0"`). Il danno converte `/100` (§6)."""
    return cost_eff_come_centesimi(ber) + stat_eff(ber, StatId.DIFESA)  # entrambi CENTESIMI


def m_armatura_di(ber: int) -> float:
    """La mobilità concessa da ciò che l'entità **indossa**, in cascata a tre livelli.

    **Un solo proprietario.** Questa è l'unica funzione che risponde alla domanda "quanto
    ti impaccia l'armatura": tre sorgenti, una funzione. Se un giorno il calcolo si
    sdoppiasse (uno per il protagonista equipaggiato, uno per i mob), `coeff_eva`
    avrebbe due padroni e i due divergerebbero al primo ritocco.

    1. **`ComponenteEquip`** → **media pesata sui nove slot** (ADR-1 II.3). Uno slot vuoto
       vale `VESTE`: non indossare niente è la massima mobilità, non un buco nella media.
    2. **`Corredo`** → il selettore singolo di sempre (i mob generati, che non hanno
       oggetti ma hanno una categoria).
    3. **niente** → i default globali `*_DEFAULT`.

    Il livello 1 **degenera esattamente** nel livello 2 quando tutti gli slot sono vuoti:
    la media pesata è una combinazione convessa (Σ pesi = 1), quindi vale `M_ARMATURA["veste"]`
    bit-per-bit. È ciò che rende l'apertura non-regressiva.
    """
    comp = esper.try_component(ber, ComponenteEquip)
    if comp is None or not comp.armatura:
        armatura, _taglia, _arma = _geometria(ber)      # livelli 2 e 3
        return cal.M_ARMATURA[armatura]

    totale = 0.0
    for slot, peso in cal.PESI_SLOT_ARMATURA.items():
        pezzo = comp.armatura.get(SlotEquip(slot))
        categoria = pezzo.categoria.value if pezzo is not None else CategoriaArmatura.VESTE.value
        totale += peso * cal.M_ARMATURA[categoria]
    return totale


def _coeff_eva(ber: int, *, pct_evasione: float = 0.0) -> float:
    """Pendenza dell'evasione (§5.3): `m_armatura × m_taglia × (1 + Σ pct_evasione)`.

    `m_armatura`/`m_taglia` sono **selettori di categoria** (un valore ciascuno → prodotto
    *bounded*, non stacking moltiplicativo); le `%` di skill/enchant restano additive dentro
    `(1+Σ)`. La mobilità passa da `m_armatura_di` (cascata equip → corredo → default); la
    **taglia** resta per-entità dal `Corredo`, perché è una proprietà del corpo, non di ciò
    che indossa: un gatto in armatura pesante resta un gatto.

    `K_EVA` è la **scala globale** (§11), e senza di lei il check 1 non si accenderebbe
    mai: il prodotto delle due tabelle sta attorno a `0.01`, contro un'accuratezza
    dell'ordine delle decine. Le tabelle portano il rapporto *fra* le categorie (giusto),
    il knob porta la magnitudine — due cose separate, tarate separatamente."""
    _armatura, taglia, _arma = _geometria(ber)
    m_taglia = cal.M_TAGLIA[taglia]
    return cal.K_EVA * m_armatura_di(ber) * m_taglia * (1 + pct_evasione)


def eva_eff(ber: int, *, pct_evasione: float = 0.0) -> float:
    """Evasione del check 1 (§5.3): `Des_eff × coeff_eva`. La Destrezza è la *magnitudine*,
    `coeff_eva` la *pendenza* (quanta agilità diventa schivata, dato cosa indossi e quanto sei
    grande). `coeff_eva ≈ 0` → non evadi anche a Des alta (no super-stat). Gli enchant
    `+evasione` entrano in `pct_evasione` (solo schivata), `+Destrezza` in `Des_eff` (schivata
    *e* iniziativa) — due leve distinte."""
    return stat_eff(ber, StatId.DESTREZZA) * _coeff_eva(ber, pct_evasione=pct_evasione)


# Lo STILE marziale e quello magico sono due accuratezze SEPARATE (niente blend `w`):
# quale stat mira è un **selettore-dato** sullo `StileAttacco` del colpo, mai un ramo.
STAT_ACC_DI_STILE: dict[StileAttacco, StatId] = {
    StileAttacco.FISICO: StatId.DESTREZZA,
    StileAttacco.MAGICO: StatId.INTELLIGENZA,
}


def acc_eff_di(att: int, stile: StileAttacco, *, pct_precisione: float = 0.0) -> float:
    """Accuratezza del check 1 (§5.4), gemello offensivo dell'evasione: `stat_eff(stat_di_stile)
    × coeff_acc × (1 + Σ pct_precisione)`. UNA forma, due stili: la stat che mira viene da
    `STAT_ACC_DI_STILE` (FISICO → Destrezza, MAGICO → Intelligenza), la geometria è la stessa —
    `coeff_acc` = arma rispetto alla taglia del portatore (dal `Corredo`, fallback
    `ARMA_DEFAULT`; per il magico l'arma è il catalizzatore). Precisa ≠ forte: `coeff_acc`
    muove il colpire, non il danno."""
    stat_base_acc = stat_eff(att, STAT_ACC_DI_STILE[stile])
    _armatura, _taglia, arma = _geometria(att)
    coeff_acc = cal.COEFF_ACC[arma]
    return stat_base_acc * coeff_acc * (1 + pct_precisione)


def acc_fis_eff(att: int, *, pct_precisione: float = 0.0) -> float:
    """Accuratezza MARZIALE (stile fisico): Destrezza guida il colpire."""
    return acc_eff_di(att, StileAttacco.FISICO, pct_precisione=pct_precisione)


def acc_mag_eff(att: int, *, pct_precisione: float = 0.0) -> float:
    """Accuratezza MAGICA: Intelligenza guida il colpire (la stessa stat del mana:
    chi lancia bene lancia anche a lungo — leva unica, tarabile con `COEFF_ACC`)."""
    return acc_eff_di(att, StileAttacco.MAGICO, pct_precisione=pct_precisione)


def clampa_hp(entita: int) -> None:
    """Tiene `HP_corrente` ≤ massimo derivato (GR2-10). Da richiamare dopo un danno, dopo
    un modificatore che abbassa la Costituzione, e al load (cablaggio 2b)."""
    scheda = esper.try_component(entita, Scheda)
    if scheda is None:
        return
    tetto = max_hp(entita)
    if scheda.punti_vita > tetto:
        scheda.punti_vita = tetto


def clampa_mana(entita: int) -> None:
    """Il GEMELLO di `clampa_hp` sul mana (caccia 2026-08-16): togliere un pezzo
    `+INTELLIGENZA` abbassa `max_mana` derivato, e il corrente deve seguirlo —
    senza questo clamp restava sopra il massimo (mana fantasma da spendere)."""
    from .scheda import Mana  # locale: derivate resta importabile da scheda

    mana = esper.try_component(entita, Mana)
    if mana is None:
        return
    tetto = max_mana(entita)
    if mana.attuale > tetto:
        mana.attuale = tetto
