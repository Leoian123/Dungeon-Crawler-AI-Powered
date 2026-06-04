"""Layer dei tipi di danno (additivo, backward-compatible): DT-1…9, DT-L1.

Il tipo è un DATO (Type Object), la resistenza un canale a sé letto solo dal risolutore;
`stat_eff` non cambia; assenza = identità; zero RNG; tipo→status = composizione. Headless.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import esper
import pydantic
import pytest

from contracts import StatId, TipoDanno
from motore import (
    Brucia,
    Danno,
    Primarie,
    QuantitaDa,
    ResistenzaMod,
    Resistenze,
    Stordito,
    Veleno,
    applica_resistenza,
    atk_eff,
    check2,
    def_eff,
    mult_resistenza,
    rimuovi_resistenza_per_fonte,
)

_MOTORE = Path(__file__).resolve().parents[1] / "src" / "motore"


def _att(forza: int) -> int:
    return esper.create_entity(Primarie(valori={StatId.FORZA: forza}))


def _ber(cost: int = 1) -> int:
    return esper.create_entity(Primarie(valori={StatId.COSTITUZIONE: cost}))


# --- DT-1: `Danno.tipo` è un campo dato, default GENERICO; nessun sottotipo ------

def test_DT1_danno_tipo_campo_default_generico() -> None:
    campi = {f.name for f in dataclasses.fields(Danno)}
    assert "tipo" in campi
    assert Danno(quantita_da=QuantitaDa.ATK_EFF).tipo is TipoDanno.GENERICO
    # Nessun sottotipo di Danno (DannoFuoco…): Danno è una foglia del catalogo Effetto.
    classi = {n.name for f in _MOTORE.glob("*.py")
              for n in ast.walk(ast.parse(f.read_text(encoding="utf-8")))
              if isinstance(n, ast.ClassDef)}
    assert not {c for c in classi if c.startswith("Danno") and c != "Danno"}


# --- DT-1/DT-2: il risolutore NON si dirama sul VALORE del tipo (solo il filtro) -

def test_DT2_risolutore_senza_ramo_sul_tipo() -> None:
    src = (_MOTORE / "combattimento.py").read_text(encoding="utf-8")
    # Nessun ramo sul valore del tipo: niente `tipo ==`, niente `== TipoDanno.<membro>`,
    # niente `match` sul tipo. L'UNICO uso è il filtro-dato `r.contro == tipo`.
    assert "== TipoDanno." not in src
    assert "tipo ==" not in src
    assert "r.contro == tipo" in src                   # il filtro per-tipo, qui e solo qui


# --- DT-3: ResistenzaMod chiavettato su TipoDanno, dato puro, rimovibile per fonte

def test_DT3_resistenza_dato_puro_rimovibile_per_fonte(mondo_isolato: str) -> None:
    campi = {f.name for f in dataclasses.fields(ResistenzaMod)}
    assert {"contro", "valore", "fonte"} <= campi
    ber = _ber()
    applica_resistenza(ber, ResistenzaMod(contro=TipoDanno.FUOCO, valore=-30, fonte="mantello"))
    applica_resistenza(ber, ResistenzaMod(contro=TipoDanno.FUOCO, valore=-20, fonte="anello"))
    # Multi-fonte, additiva: −30 −20 = −50 → mult 0.5.
    assert mult_resistenza(ber, TipoDanno.FUOCO) == pytest.approx(0.5)
    # Rimozione per `fonte` (niente operazione inversa): resta solo l'anello (−20 → 0.8).
    rimuovi_resistenza_per_fonte(ber, "mantello")
    assert mult_resistenza(ber, TipoDanno.FUOCO) == pytest.approx(0.8)


# --- DT-4: la firma di stat_eff resta context-free (il tipo non entra nel fold) --

def test_DT4_stat_eff_non_riceve_il_tipo() -> None:
    from motore import stat_eff
    assert list(inspect.signature(stat_eff).parameters) == ["entita", "stat"]
    # E il fold (statistiche.py) non importa né nomina TipoDanno.
    assert "TipoDanno" not in (_MOTORE / "statistiche.py").read_text(encoding="utf-8")


# --- DT-5: m e mult dentro l'UNICO round; GR2-11 (floor 1) resta vero ------------

def test_DT5_forma_chiusa_unico_round(mondo_isolato: str) -> None:
    att, ber = _att(50), _ber(10)
    applica_resistenza(ber, ResistenzaMod(contro=TipoDanno.FUOCO, valore=-40, fonte="fae"))
    fuoco = Danno(quantita_da=QuantitaDa.ATK_EFF, tipo=TipoDanno.FUOCO)
    m = 1.0
    atteso = max(1, round(m * (atk_eff(att) - def_eff(ber) / 100) * 0.6))  # mult = 1−0.40
    assert check2(m, att, ber, fuoco) == atteso
    # Floor 1 regge anche con resistenza estrema (mult al minimo): colpo a segno ≥ 1.
    applica_resistenza(ber, ResistenzaMod(contro=TipoDanno.FUOCO, valore=-10**6, fonte="immune"))
    assert check2(1.0, att, ber, fuoco) >= 1


# --- DT-6: assenza = identità (bit-per-bit col percorso senza tipi) --------------

def test_DT6_assenza_e_identita(mondo_isolato: str) -> None:
    att, ber = _att(30), _ber(50)
    agnostico = Danno(quantita_da=QuantitaDa.ATK_EFF)                  # GENERICO
    for m in (1.0, 0.5, 0.0):
        riferimento = 0 if m == 0 else max(1, round(m * (atk_eff(att) - def_eff(ber) / 100)))
        assert check2(m, att, ber, agnostico) == riferimento          # mult = 1.0, identico
    # Anche con resistenze presenti ma di ALTRO tipo: GENERICO non matcha → identità.
    applica_resistenza(ber, ResistenzaMod(contro=TipoDanno.FUOCO, valore=-90, fonte="x"))
    assert mult_resistenza(ber, TipoDanno.GENERICO) == 1.0


# --- DT-7: zero RNG nel layer (mult è funzione pura di dati) ---------------------

def test_DT7_zero_rng_nel_layer() -> None:
    # Né `mult_resistenza` né `check2` ricevono un RNG: il layer non pesca dallo stream.
    assert "rng" not in inspect.signature(mult_resistenza).parameters
    assert "rng" not in inspect.signature(check2).parameters


# --- DT-8: tipo→status è composizione, non un ramo del risolutore ---------------

def test_DT8_tipo_non_applica_status_implicito(mondo_isolato: str) -> None:
    # Un Danno(FUOCO) risolto NON applica Brucia da solo: lo status sarebbe un Effetto a
    # parte nella lista (composizione), non un ramo automatico del risolutore.
    att, ber = _att(50), _ber(10)
    fuoco = Danno(quantita_da=QuantitaDa.ATK_EFF, tipo=TipoDanno.FUOCO)
    check2(1.0, att, ber, fuoco)
    for tipo_status in (Brucia, Veleno, Stordito):
        assert esper.try_component(ber, tipo_status) is None


# --- DT-9: TipoDanno è enum chiuso; un valore fuori enum è rifiutato dal gate ----

def test_DT9_tipo_fuori_enum_rifiutato() -> None:
    with pytest.raises(ValueError):
        TipoDanno("drago")                              # enum chiuso: nessun conio

    # Al confine schema (gate F): un modello Pydantic con campo TipoDanno rifiuta il fuori-enum.
    class _Schema(pydantic.BaseModel):
        tipo: TipoDanno

    _Schema(tipo=TipoDanno.FUOCO)                        # valido
    with pytest.raises(pydantic.ValidationError):
        _Schema(tipo="drago")                           # rifiutato (fallback, non crash a runtime)


# --- DT-L1: aggiungere un tipo + resistenza è SOLO dati (zero righe nel risolutore)

def test_DTL1_mult_resistenza_generico_su_ogni_tipo(mondo_isolato: str) -> None:
    # Il risolutore tratta OGNI membro di TipoDanno con lo stesso filtro-dato: nessun ramo
    # per-tipo → aggiungere un tipo (una riga di enum) non tocca `mult_resistenza`.
    ber = _ber()
    for tipo in TipoDanno:
        assert mult_resistenza(ber, tipo) == 1.0        # nessuna resistenza → identità, per tutti
    assert esper.try_component(ber, Resistenze) is None  # lettura non deposita nulla
