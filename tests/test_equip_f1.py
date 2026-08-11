"""Equipaggiamento ADR-1 **F1**: manifest durevole, effetti derivati, gate di fase.

Le quattro proprietà che questa fase deve garantire, in ordine di importanza:

1. **L'equip non ha una meccanica propria.** I modificatori di un pezzo arrivano al
   fold `stat_eff` da soli: il risolutore non li conosce e non è stato toccato. Se un
   giorno qualcuno aggiunge un ramo "se ha l'armatura…" nel loop, `test_zero_righe_*`
   diventa rosso.
2. **Togliere è rimuovere per fonte**, mai un'operazione inversa: mettere e togliere
   sono simmetrici e la base non si corrompe.
3. **Phase-gate strutturale**: si equipaggia solo in NARRAZIONE, e non per un `if fase`
   ma perché il sistema vive nel bucket solo-narrazione.
4. **Il buco di persistenza è dichiarato**, non dimenticato (vedi l'ultimo test).
"""

from __future__ import annotations

import ast
from pathlib import Path

from contracts import (
    CategoriaArmatura,
    PlayerEquipaggia,
    PlayerToglie,
    SedeAccessorio,
    SlotEquip,
    StatId,
    Taglia,
)
from motore import (
    Accessorio,
    Arma,
    CodaIntenti,
    ComponenteEquip,
    Fase,
    M_ARMATURA,
    M_TAGLIA,
    Modificatore,
    PezzoArmatura,
    SistemaEquip,
    TipoMod,
    avvia_run,
    crea_protagonista,
    equip_attivo,
    equipaggia,
    imposta_fase,
    max_hp,
    protagonista,
    stat_eff,
    tick,
    togli,
    travasa,
)
from motore.calibrazione import COEFF_ACC

_MOTORE = Path(__file__).resolve().parents[1] / "src" / "motore"

_FONTE = "pettorale-di-latta#1"


def _pettorale(*, mod_costituzione: int = 0) -> PezzoArmatura:
    mods = ()
    if mod_costituzione:
        mods = (
            Modificatore(
                stat=StatId.COSTITUZIONE, tipo=TipoMod.FLAT,
                valore=mod_costituzione, fonte=_FONTE,
            ),
        )
    return PezzoArmatura(
        fonte=_FONTE, slot=SlotEquip.BUSTO, categoria=CategoriaArmatura.PESANTE,
        nome="Pettorale di latta", mitigazione_cent=250, modificatori=mods,
    )


# --- 1. I modificatori arrivano al fold da soli --------------------------------

def test_un_pezzo_indossato_muove_stat_eff_senza_codice_nel_risolutore(
    mondo_isolato: str,
) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    base = stat_eff(pent, StatId.COSTITUZIONE)

    equipaggia(pent, _pettorale(mod_costituzione=4))
    assert stat_eff(pent, StatId.COSTITUZIONE) == base + 4

    togli(pent, _FONTE)
    assert stat_eff(pent, StatId.COSTITUZIONE) == base, (
        "togliere deve riportare la stat al valore di partenza ESATTO: se qui c'è "
        "deriva, qualcuno ha 'disfatto' il bonus invece di rimuoverlo per fonte"
    )


def test_zero_righe_di_equip_nel_risolutore_di_combattimento() -> None:
    """La prova che l'equip è additivo: il combattimento non lo nomina nemmeno.

    Statico apposta — un test comportamentale passerebbe anche con un ramo speciale
    nascosto nel loop, questo no."""
    src = (_MOTORE / "combattimento.py").read_text(encoding="utf-8")
    for parola in ("ComponenteEquip", "PezzoArmatura", "equip_di", "equipaggia"):
        assert parola not in src, (
            f"`{parola}` è comparso in combattimento.py: l'equip deve passare dai canali "
            "che esistono già (Modificatori/Resistenze), non da un ramo nel risolutore"
        )


def test_il_manifest_porta_le_sorgenti_non_gli_effetti(mondo_isolato: str) -> None:
    # D1: una sola sorgente di verità. Il componente elenca gli OGGETTI; le voci-mod
    # stanno in `Modificatori` e sono derivate — mai duplicate qui dentro.
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    equipaggia(pent, _pettorale(mod_costituzione=4))
    comp = equip_attivo(pent)
    assert comp is not None
    assert comp.armatura[SlotEquip.BUSTO].fonte == _FONTE
    campi = set(ComponenteEquip.__dataclass_fields__)
    # D1 PURO di nuovo: anche le mosse concesse sono DERIVATE alla lettura
    # (`mosse_da_equip`), mai annotate qui né scritte nel Repertorio persistente
    # (che le rendeva innate dopo un save/load — giro 2026-08-07).
    assert campi == {"armatura", "arma", "accessori"}, (
        "il manifest non deve accumulare una copia delle voci-modificatore: due copie "
        "divergono e non c'è un punto di riconciliazione (ADR-1 D1)"
    )


# --- 2. Simmetria e slot esclusivi ---------------------------------------------

def test_lo_slot_armatura_e_esclusivo_e_sostituire_non_lascia_orfani(
    mondo_isolato: str,
) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    base = stat_eff(pent, StatId.COSTITUZIONE)
    equipaggia(pent, _pettorale(mod_costituzione=4))

    altro = PezzoArmatura(
        fonte="corazza#2", slot=SlotEquip.BUSTO, categoria=CategoriaArmatura.MEDIA,
        modificatori=(
            Modificatore(stat=StatId.COSTITUZIONE, tipo=TipoMod.FLAT,
                         valore=1, fonte="corazza#2"),
        ),
    )
    equipaggia(pent, altro)

    comp = equip_attivo(pent)
    assert comp is not None and comp.armatura[SlotEquip.BUSTO].fonte == "corazza#2"
    assert stat_eff(pent, StatId.COSTITUZIONE) == base + 1, (
        "il pezzo sostituito ha lasciato i suoi modificatori attaccati: un bonus "
        "fantasma di un oggetto che il giocatore non porta più"
    )


def test_lo_stesso_oggetto_non_si_equipaggia_due_volte(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    assert equipaggia(pent, _pettorale(mod_costituzione=4)) is True
    assert equipaggia(pent, _pettorale(mod_costituzione=4)) is False, (
        "doppio equip = bonus contato due volte"
    )


def test_gli_accessori_fungibili_si_tolgono_uno_alla_volta(mondo_isolato: str) -> None:
    """D6: la `fonte` degli accessori è per-ISTANZA. Con una fonte di tipo, togliersi
    un anello ne toglierebbe cinque."""
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    for i in range(3):
        equipaggia(pent, Accessorio(
            fonte=f"anello-di-ferro#{i}", sede=SedeAccessorio.DITA,
            modificatori=(
                Modificatore(stat=StatId.FORZA, tipo=TipoMod.FLAT, valore=1,
                             fonte=f"anello-di-ferro#{i}"),
            ),
        ))
    base_forza = stat_eff(pent, StatId.FORZA)
    togli(pent, "anello-di-ferro#1")
    assert stat_eff(pent, StatId.FORZA) == base_forza - 1
    comp = equip_attivo(pent)
    assert comp is not None and len(comp.accessori) == 2


def test_larma_va_nel_mount_impugnato_non_in_uno_slot_armatura(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    equipaggia(pent, Arma(fonte="spilla#1", taglia=Taglia.PICCOLA, nome="Spilla"))
    comp = equip_attivo(pent)
    assert comp is not None and comp.arma is not None and comp.arma.fonte == "spilla#1"
    assert not comp.armatura, "l'arma non occupa uno slot-armatura (guanto e arma convivono)"


def test_un_pezzo_darmatura_con_slot_arma_e_rifiutato(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    intruso = PezzoArmatura(
        fonte="x#1", slot=SlotEquip.ARMA, categoria=CategoriaArmatura.VESTE
    )
    assert equipaggia(pent, intruso) is False, (
        "un pezzo d'armatura nel mount impugnato falserebbe il denominatore della "
        "media pesata di m_armatura (ADR-1 D5)"
    )


# --- 3. `clampa_hp` sui pezzi che toccano la Costituzione (D2) ------------------

def test_indossare_piu_costituzione_alza_il_massimo_e_non_cura(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    _e, _m, scheda = protagonista()
    scheda.punti_vita = 20                       # ferito
    tetto_prima = max_hp(pent)

    equipaggia(pent, _pettorale(mod_costituzione=6))
    assert max_hp(pent) == tetto_prima + 6
    assert scheda.punti_vita == 20, "equipaggiare non è una cura (ADR-1 D2)"


def test_togliere_costituzione_abbassa_il_tetto_e_clampa_il_corrente(
    mondo_isolato: str,
) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    _e, _m, scheda = protagonista()
    equipaggia(pent, _pettorale(mod_costituzione=6))
    scheda.punti_vita = max_hp(pent)             # curato al nuovo massimo

    togli(pent, _FONTE)
    assert scheda.punti_vita == max_hp(pent), (
        "sfilare l'armatura che dava Costituzione deve clampare il corrente: senza "
        "questo si resta sopra il proprio massimo, e la perdita di HP che rende il "
        "cambio d'armatura una SCELTA non avviene mai (ADR-1 D2)"
    )


# --- 4. Il phase-gate è strutturale, non un `if` -------------------------------

def test_il_sistema_equip_vive_nel_bucket_solo_narrazione() -> None:
    from motore import SistemaSoloNarrazione
    assert issubclass(SistemaEquip, SistemaSoloNarrazione)
    assert SistemaEquip.fasi_attive == frozenset({Fase.NARRAZIONE})


def test_nessun_controllo_di_fase_scritto_a_mano_in_equip() -> None:
    """Il phase-gate è la registrazione nel bucket, mai un ramo (invariante di progetto).
    Statico: un `if leggi_fase() ==` qui dentro sarebbe una seconda regola di fase, che
    prima o poi diverge da quella strutturale."""
    albero = ast.parse((_MOTORE / "equip.py").read_text(encoding="utf-8"))
    chiamate = {
        n.func.id for n in ast.walk(albero)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "leggi_fase" not in chiamate and "in_combattimento" not in chiamate


def test_lintento_equipaggia_agisce_in_narrazione_e_non_in_combattimento(
    mondo_isolato: str,
) -> None:
    pettorale = _pettorale(mod_costituzione=4)
    sistema = SistemaEquip({_FONTE: pettorale})
    avvia_run(solo_narrazione=[sistema], fase_iniziale=Fase.COMBATTIMENTO)
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    base = stat_eff(pent, StatId.COSTITUZIONE)

    # In COMBATTIMENTO il sistema non gira: l'intento resta in coda, intatto.
    coda = CodaIntenti()
    coda.accoda(PlayerEquipaggia(fonte=_FONTE))
    travasa(coda)
    tick()
    assert stat_eff(pent, StatId.COSTITUZIONE) == base
    assert equip_attivo(pent) is None

    # In NARRAZIONE lo stesso intento — mai riaccodato — viene servito.
    imposta_fase(Fase.NARRAZIONE)
    tick()
    assert stat_eff(pent, StatId.COSTITUZIONE) == base + 4, (
        "l'intento accodato nella fase sbagliata deve ATTENDERE la sua fase, non essere "
        "scartato: il phase-gate separa i domini, non cestina gli intenti"
    )


def test_una_fonte_ignota_e_consumata_senza_effetto(mondo_isolato: str) -> None:
    sistema = SistemaEquip({})
    avvia_run(solo_narrazione=[sistema], fase_iniziale=Fase.NARRAZIONE)
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    coda = CodaIntenti()
    coda.accoda(PlayerEquipaggia(fonte="oggetto-che-non-esiste"))
    travasa(coda)
    tick()
    assert equip_attivo(pent) is None       # nessun manifest creato per nulla


def test_lintento_toglie_sfila_davvero(mondo_isolato: str) -> None:
    pettorale = _pettorale(mod_costituzione=4)
    sistema = SistemaEquip({_FONTE: pettorale})
    avvia_run(solo_narrazione=[sistema], fase_iniziale=Fase.NARRAZIONE)
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    base = stat_eff(pent, StatId.COSTITUZIONE)

    coda = CodaIntenti()
    coda.accoda(PlayerEquipaggia(fonte=_FONTE))
    travasa(coda)
    tick()
    assert stat_eff(pent, StatId.COSTITUZIONE) == base + 4
    coda.accoda(PlayerToglie(fonte=_FONTE))
    travasa(coda)
    tick()
    assert stat_eff(pent, StatId.COSTITUZIONE) == base


# --- 5. Sincronia enum ↔ chiavi di calibrazione (invariante #7) ----------------

def test_ogni_categoria_armatura_ha_il_suo_coefficiente() -> None:
    for categoria in CategoriaArmatura:
        assert categoria.value in M_ARMATURA, (
            f"{categoria} non ha una riga in M_ARMATURA: un valore che il gate accetta "
            "e il motore non sa pesare"
        )


def test_ogni_taglia_ha_il_suo_coefficiente() -> None:
    for taglia in Taglia:
        assert taglia.value in M_TAGLIA


def test_le_relazioni_darma_hanno_il_loro_coefficiente() -> None:
    # `coeff_acc` è size-based: le chiavi sono RELAZIONI, non categorie d'arma (D7).
    assert set(COEFF_ACC) >= {"pari", "piu_piccola", "mismatch", "naturale"}


# --- 6. La persistenza F5 è ATTIVA: tag e hook viaggiano insieme ---------------

def test_equip_persistente_con_hook_F5(mondo_isolato: str) -> None:
    """`ComponenteEquip` È nel registry dei tag del save (ADR-1 F5) — l'opposto
    del vecchio lucchetto, capovolto INSIEME alla coppia che lo rendeva sicuro:
    filtro di provenienza nel save (`filtrato_per_save`) + hook di re-equip al
    load (`re_equipaggia`). Senza uno dei due, il salvataggio mentirebbe (equip
    morto al load, o voci doppie): il round-trip byte-identico è in
    `test_equip_f5.py`."""
    from motore.equip import filtrato_per_save, re_equipaggia  # la coppia esiste
    from motore.persistenza.tag import _TAG_PER_TIPO

    assert ComponenteEquip in _TAG_PER_TIPO
    assert callable(filtrato_per_save) and callable(re_equipaggia)
