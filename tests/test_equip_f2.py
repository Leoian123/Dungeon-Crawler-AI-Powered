"""Equipaggiamento ADR-1 **F2**: `DIFESA` e resistenze da gear, come DATO.

La proprietà che questa fase compra: **un pezzo d'armatura protegge senza che il
risolutore sappia dell'armatura**. `def_eff` sommava già `stat_eff(DIFESA)` in
centesimi e `mult_resistenza` leggeva già `Resistenze`: l'equip ci spinge dentro le
sue voci con la propria `fonte`, e il danno cala. **Zero codice nel motore** — il
lavoro di questa fase è quasi tutto nel dimostrarlo.

L'altra metà, meno ovvia: la mitigazione la **deriva il motore dalla categoria**.
Chi scrive contenuto sceglie il nome "pesante"; il numero sta in `§11`. È lo stesso
principio dell'"AI non emette numeri", esteso alla porta di authoring.

⚠️ Il trade-off da non perdere mai di vista: la stessa categoria che **alza** la
mitigazione **abbassa** `m_armatura` (schivi meno). Vanno in direzioni opposte, e se
un giorno crescessero insieme l'armatura pesante diventerebbe sempre migliore — fine
del tank/dodger. C'è un test apposta.
"""

from __future__ import annotations

import random

from contracts import CategoriaArmatura, SlotEquip, StatId, TipoDanno
import esper

from motore import (
    Danno,
    Primarie,
    MITIGAZIONE_CENT,
    M_ARMATURA,
    PezzoArmatura,
    QuantitaDa,
    ResistenzaMod,
    Resistenze,
    crea_protagonista,
    def_eff,
    equipaggia,
    mitigazione_di,
    mult_resistenza,
    primarie_da_scalari,
    risolvi_danno,
    stat_eff,
    togli,
)

_FONTE = "corazza-di-piastre#1"


def _attaccante(*, forza: int = 60) -> int:
    """Un'entità che picchia forte, senza montare uno scontro: a `risolvi_danno` serve
    solo una sorgente con le sue `Primarie` (le derivate le legge dal fold).

    La Forza è alta di proposito: col colpo già schiacciato sul floor (`max(1, ...)`)
    nessuna armatura potrebbe mostrare di funzionare — si misurerebbe il floor, non la
    mitigazione."""
    valori = dict(primarie_da_scalari(destrezza=1, punti_vita=10))
    valori[StatId.FORZA] = forza
    return esper.create_entity(Primarie(valori=valori))


def _piastra(**kw) -> PezzoArmatura:
    campi = dict(
        fonte=_FONTE, slot=SlotEquip.BUSTO, categoria=CategoriaArmatura.PESANTE,
        nome="Corazza di piastre",
    )
    campi.update(kw)
    return PezzoArmatura(**campi)


# --- 1. La mitigazione la deriva il motore dalla categoria ---------------------

def test_la_mitigazione_deriva_dalla_categoria_non_dallautore() -> None:
    for categoria in CategoriaArmatura:
        pezzo = PezzoArmatura(fonte="x", slot=SlotEquip.BUSTO, categoria=categoria)
        assert mitigazione_di(pezzo) == MITIGAZIONE_CENT[categoria.value]


def test_un_valore_esplicito_ha_la_precedenza() -> None:
    # La via dell'oggetto unico. Resta l'unico punto in cui un autore scrive una
    # magnitudine — il tetto che la limita è lavoro di F8.
    assert mitigazione_di(_piastra(mitigazione_cent=999)) == 999


def test_la_veste_non_protegge() -> None:
    """Uno slot vuoto vale `veste` nella media di `m_armatura` (F5), ma non deve
    regalare difesa: "non indossare niente" non può essere una forma di armatura."""
    assert MITIGAZIONE_CENT["veste"] == 0


def test_protezione_e_mobilita_vanno_in_direzioni_opposte() -> None:
    """Il trade-off tank/dodger è nei DATI, non in una regola: se le due tabelle
    crescessero insieme, la piastra sarebbe sempre la scelta giusta e il dodger non
    esisterebbe come build."""
    per_mitigazione = sorted(M_ARMATURA, key=lambda c: MITIGAZIONE_CENT[c])
    per_mobilita = sorted(M_ARMATURA, key=lambda c: M_ARMATURA[c], reverse=True)
    assert per_mitigazione == per_mobilita, (
        f"ordinate per protezione: {per_mitigazione}; per mobilità: {per_mobilita}. "
        "Devono essere l'una l'inverso dell'altra."
    )


# --- 2. La difesa arriva a `def_eff` da sola ----------------------------------

def test_indossare_larmatura_alza_def_eff_del_valore_esatto(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    prima = def_eff(pent)

    equipaggia(pent, _piastra())
    atteso = MITIGAZIONE_CENT["pesante"]
    assert def_eff(pent) == prima + atteso, "la mitigazione è in CENTESIMI, come DIFESA"
    assert stat_eff(pent, StatId.DIFESA) == atteso

    togli(pent, _FONTE)
    assert def_eff(pent) == prima, "sfilare deve riportare la difesa al valore esatto"


def test_due_pezzi_sommano_e_si_tolgono_indipendentemente(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    base = def_eff(pent)
    equipaggia(pent, _piastra())
    equipaggia(pent, PezzoArmatura(
        fonte="elmo#1", slot=SlotEquip.TESTA, categoria=CategoriaArmatura.MEDIA,
    ))
    assert def_eff(pent) == base + MITIGAZIONE_CENT["pesante"] + MITIGAZIONE_CENT["media"]

    togli(pent, "elmo#1")
    assert def_eff(pent) == base + MITIGAZIONE_CENT["pesante"], (
        "fonti diverse coesistono e si rimuovono INDIPENDENTEMENTE (Gr2 §4.2)"
    )


def test_larmatura_riduce_il_danno_incassato(mondo_isolato: str) -> None:
    """Il punto di arrivo di tutta la fase: il colpo fa meno male, e nessuno ha
    scritto una riga nel risolutore."""
    pent = crea_protagonista(destrezza=10, punti_vita=1000)
    nemico = _attaccante()
    colpo = Danno(quantita_da=QuantitaDa.ATK_EFF, tipo=TipoDanno.MISCHIA)

    nudo = risolvi_danno(colpo, nemico, pent, random.Random(1))
    # Nove slot di piastra: abbastanza da spostare un danno intero anche coi numeri §11
    # di partenza (500 centesimi a slot = 5 punti a slot).
    for slot in (SlotEquip.BUSTO, SlotEquip.TESTA, SlotEquip.GAMBE):
        equipaggia(pent, PezzoArmatura(
            fonte=f"piastra-{slot.value}", slot=slot,
            categoria=CategoriaArmatura.PESANTE,
        ))
    corazzato = risolvi_danno(colpo, nemico, pent, random.Random(1))

    assert corazzato < nudo, f"nudo {nudo}, corazzato {corazzato}: l'armatura non morde"
    assert corazzato >= 1, "il floor del danno resta (GR2-11): l'armatura non azzera"


# --- 3. Le resistenze tipate passano dallo stesso canale ----------------------

def test_una_resistenza_da_gear_cambia_il_moltiplicatore(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    assert mult_resistenza(pent, TipoDanno.FUOCO) == 1.0, "assenza = identità (DT-6)"

    equipaggia(pent, _piastra(resistenze=(
        ResistenzaMod(contro=TipoDanno.FUOCO, valore=-40.0, fonte=_FONTE),
    )))
    assert mult_resistenza(pent, TipoDanno.FUOCO) < 1.0
    assert mult_resistenza(pent, TipoDanno.MISCHIA) == 1.0, (
        "una resistenza al fuoco non deve proteggere dalle mazzate"
    )

    togli(pent, _FONTE)
    assert mult_resistenza(pent, TipoDanno.FUOCO) == 1.0, (
        "la resistenza da gear se ne va con l'oggetto: `rimuovi_resistenza_per_fonte`"
    )


def test_la_resistenza_al_fuoco_cambia_lesito_di_un_incantesimo(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=1000)
    nemico = _attaccante()
    dardo = Danno(quantita_da=QuantitaDa.ATK_EFF, tipo=TipoDanno.FUOCO)

    scoperto = risolvi_danno(dardo, nemico, pent, random.Random(3))
    equipaggia(pent, _piastra(
        mitigazione_cent=0,            # isolo l'effetto: solo resistenza, niente DIFESA
        resistenze=(ResistenzaMod(contro=TipoDanno.FUOCO, valore=-50.0, fonte=_FONTE),),
    ))
    protetto = risolvi_danno(dardo, nemico, pent, random.Random(3))
    assert protetto < scoperto, f"scoperto {scoperto}, protetto {protetto}"


def test_niente_resistenze_niente_componente(mondo_isolato: str) -> None:
    # Un pezzo che non concede resistenze non deve attaccare un contenitore vuoto:
    # l'assenza del componente È il caso normale (identità nel risolutore).
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    equipaggia(pent, _piastra())
    assert esper.try_component(pent, Resistenze) is None


# --- 4. Zero codice nel motore: la prova statica ------------------------------

def test_il_risolutore_e_il_fold_non_conoscono_lequip() -> None:
    """La proprietà che conta: `DIFESA` e `Resistenze` arrivano al **risolutore** e al
    **fold** come dato qualunque, senza che nessuno dei due sappia da dove vengono.

    ⚠️ `derivate.py` è **escluso di proposito**, e la distinzione non è un cavillo:
    `derivate` è il posto in cui la geometria di un'entità *diventa* un numero
    (`m_armatura_di` legge il manifest per la media pesata sui nove slot, ADR-1 F3).
    Quello è il suo mestiere. Un ramo "se ha l'armatura…" in `combattimento.py` o in
    `statistiche.py` sarebbe invece un caso speciale nel cuore delle regole — cioè la
    fine dell'equip-come-dato."""
    from pathlib import Path
    motore = Path(__file__).resolve().parents[1] / "src" / "motore"
    for modulo in ("combattimento.py", "statistiche.py"):
        src = (motore / modulo).read_text(encoding="utf-8")
        for parola in ("ComponenteEquip", "PezzoArmatura", "mitigazione_di", "from .equip"):
            assert parola not in src, f"`{parola}` è comparso in {modulo}"
