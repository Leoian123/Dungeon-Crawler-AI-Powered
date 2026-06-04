"""Modello-stat: vettore `Primarie`, registry, **un solo fold** (Gruppo 2 §2/§3).

Copre GR2-1 (un solo componente, niente componente-per-stat), GR2-2 (registry+campi),
GR2-3/4 (statici: `stat_eff` unico combinatore, nessun ramo per-stat), GR2-5 (forma del
fold), GR2-6 (order-independence). I test statici sono scritti per **mordere**: ognuno
verifica anche, su un campione sintetico che VIOLA il criterio, che il rilevatore scatti.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

import esper

from contracts import StatId
from motore import (
    FINALIZZA,
    Modificatore,
    Modificatori,
    Origine,
    Primarie,
    REGISTRY_STAT,
    RigaStat,
    TipoMod,
    applica_modificatore,
    stat_eff,
)
from motore import statistiche as S

_MOTORE = Path(__file__).resolve().parents[1] / "src" / "motore"

# Nomi che, se comparissero come classe-componente, significherebbero "un componente per
# stat" (l'anti-pattern di GR2-1).
_NOMI_STAT_COMPONENTE = {s.name.capitalize() for s in StatId}  # Forza, Destrezza, ...


def _classi_in(sorgente: str) -> set[str]:
    return {n.name for n in ast.walk(ast.parse(sorgente)) if isinstance(n, ast.ClassDef)}


# --- GR2-1: un solo componente `Primarie`, nessun componente-per-stat ----------

def test_GR2_1_un_solo_vettore_primarie() -> None:
    campi = {f for f in Primarie.__dataclass_fields__}
    assert campi == {"valori"}, "Primarie è il vettore (mappa StatId→base), un solo campo"

    classi: set[str] = set()
    for f in _MOTORE.glob("*.py"):
        classi |= _classi_in(f.read_text(encoding="utf-8"))
    intruse = classi & _NOMI_STAT_COMPONENTE
    assert not intruse, f"componente-per-stat vietato (GR2-1): {intruse}"

    # Morde: una classe omonima di una stat verrebbe rilevata.
    finto = _classi_in("class Forza:\n    pass\n")
    assert finto & _NOMI_STAT_COMPONENTE == {"Forza"}


# --- GR2-2: i tipi-stat vivono in un registry con i cinque campi ---------------

def test_GR2_2_registry_aperto_con_i_campi() -> None:
    assert set(REGISTRY_STAT) <= set(StatId)
    attesi = {"visibilita", "modificabile_da", "derivazione", "prova", "sblocco"}
    assert attesi <= set(RigaStat.__dataclass_fields__)
    for stat, riga in REGISTRY_STAT.items():
        assert isinstance(riga, RigaStat), stat
    # StatId è enum chiuso e vive in contracts (vocabolario), non nel motore.
    assert StatId.__module__.startswith("contracts")


# --- GR2-3: `stat_eff` è l'unico punto che combina base + modificatori ---------

def test_GR2_3_stat_eff_unico_combinatore() -> None:
    # Il token di accumulo dei modificatori (`mod.valore`) compare in UN solo file.
    files = {
        f.name
        for f in _MOTORE.glob("*.py")
        if "mod.valore" in f.read_text(encoding="utf-8")
    }
    assert files == {"statistiche.py"}, files
    # Le derivate non leggono `Primarie` a mano: passano da `stat_eff`.
    der = (_MOTORE / "derivate.py").read_text(encoding="utf-8")
    assert "stat_eff(" in der and ".valori[" not in der


# --- GR2-4: nessun ramo per-stat nel fold (`if stat == …`) ---------------------

def _ramo_per_stat(funzione_sorgente: str) -> bool:
    """Vero se l'AST confronta `stat` con un membro di `StatId` (ramo per-stat)."""
    albero = ast.parse(textwrap.dedent(funzione_sorgente))
    for nodo in ast.walk(albero):
        if not isinstance(nodo, ast.Compare):
            continue
        nomi = {n.id for n in ast.walk(nodo) if isinstance(n, ast.Name)}
        attrs = {a.attr for a in ast.walk(nodo) if isinstance(a, ast.Attribute)}
        membri = {s.name for s in StatId}
        if "stat" in nomi and (attrs & membri or "StatId" in nomi):
            return True
    return False


def test_GR2_4_nessun_ramo_per_stat() -> None:
    assert _ramo_per_stat(inspect.getsource(stat_eff)) is False
    # Morde: una funzione con `if stat == StatId.FORZA` viene rilevata.
    violante = "def f(stat):\n    if stat == StatId.FORZA:\n        return 1\n    return 0\n"
    assert _ramo_per_stat(violante) is True


# --- GR2-5: forma del fold (base+Σflat)×(1+Σpct), pct additivi, floor 1 --------

def test_GR2_5_fold_pct_additivi_e_floor(mondo_isolato: str) -> None:
    ent = esper.create_entity(Primarie(valori={StatId.FORZA: 100}))
    # pct additivi: +10% e +20% → ×1.30 (non ×1.32 del moltiplicativo).
    esper.add_component(ent, Modificatori(voci=[
        Modificatore(StatId.FORZA, TipoMod.PCT, 0.10, "a"),
        Modificatore(StatId.FORZA, TipoMod.PCT, 0.20, "b"),
    ]))
    assert stat_eff(ent, StatId.FORZA) == 130  # 100×1.30, additivo

    # flat prima, pct dopo: (100+10)×1.30 = 143.
    esper.component_for_entity(ent, Modificatori).voci.append(
        Modificatore(StatId.FORZA, TipoMod.FLAT, 10, "c")
    )
    assert stat_eff(ent, StatId.FORZA) == 143

    # floor 1: niente primaria sotto 1.
    giu = esper.create_entity(
        Primarie(valori={StatId.FORZA: 10}),
        Modificatori(voci=[Modificatore(StatId.FORZA, TipoMod.FLAT, -100, "x")]),
    )
    assert stat_eff(giu, StatId.FORZA) == 1


def test_GR2_5_effettiva_non_depositata(mondo_isolato: str) -> None:
    ent = esper.create_entity(Primarie(valori={StatId.FORZA: 7}))
    prima = {type(c) for c in esper.components_for_entity(ent)}
    stat_eff(ent, StatId.FORZA)
    dopo = {type(c) for c in esper.components_for_entity(ent)}
    assert prima == dopo, "stat_eff non deposita un componente-cache (IC §5)"


# --- GR2-6: l'ordine di iterazione dei modificatori non cambia l'effettiva -----

def test_GR2_6_order_independence(mondo_isolato: str) -> None:
    voci = [
        Modificatore(StatId.FORZA, TipoMod.FLAT, 5, "a"),
        Modificatore(StatId.FORZA, TipoMod.PCT, 0.10, "b"),
        Modificatore(StatId.FORZA, TipoMod.FLAT, 3, "c"),
        Modificatore(StatId.FORZA, TipoMod.PCT, 0.20, "d"),
    ]
    e1 = esper.create_entity(Primarie(valori={StatId.FORZA: 50}), Modificatori(voci=list(voci)))
    e2 = esper.create_entity(
        Primarie(valori={StatId.FORZA: 50}), Modificatori(voci=list(reversed(voci)))
    )
    assert stat_eff(e1, StatId.FORZA) == stat_eff(e2, StatId.FORZA)


# --- 2b-A / GR2-4: la finalizzazione è un DATO di registry, non un ramo per-stat -

def test_GR2_4_finalizza_e_dato_di_registry() -> None:
    # Ogni riga ha il campo `finalizza`, ed è una chiave di `FINALIZZA` (le due finalizzazioni
    # decise: primarie e DIFESA). Niente `if stat == …` nel fold (già verificato in GR2-4).
    assert "finalizza" in RigaStat.__dataclass_fields__
    assert set(FINALIZZA) >= {"primaria", "centesimi_floor0"}
    for stat, riga in REGISTRY_STAT.items():
        assert riga.finalizza in FINALIZZA, stat
    # Il fold delega alla tabella, non a un ramo: il sorgente nomina `FINALIZZA[`.
    assert "FINALIZZA[" in inspect.getsource(stat_eff)


def test_GR2_5_intelligenza_finalizza_come_primaria(mondo_isolato: str) -> None:
    # INTELLIGENZA è una primaria: floor 1 in unità, fold `(base+Σflat)×(1+Σpct)`.
    ent = esper.create_entity(Primarie(valori={StatId.INTELLIGENZA: 10}))
    assert stat_eff(ent, StatId.INTELLIGENZA) == 10
    applica_modificatore(ent, Modificatore(StatId.INTELLIGENZA, TipoMod.PCT, 0.20, "buff"))
    assert stat_eff(ent, StatId.INTELLIGENZA) == 12      # 10×1.20
    # Floor 1: due debuff additivi che farebbero ×0 si fermano a 1 (mai 0 su una primaria).
    giu = esper.create_entity(
        Primarie(valori={StatId.INTELLIGENZA: 10}),
        Modificatori(voci=[Modificatore(StatId.INTELLIGENZA, TipoMod.FLAT, -100, "x")]),
    )
    assert stat_eff(giu, StatId.INTELLIGENZA) == 1


# --- 2b-A / GR2-5: DIFESA è base 0, floor 0, in CENTESIMI (non una primaria) ----

def test_GR2_5_difesa_base_zero_floor0(mondo_isolato: str) -> None:
    # Il nudo non porta DIFESA nel vettore: base assente → fold parte da 0, finalizza floor 0.
    nudo = esper.create_entity(Primarie(valori={StatId.FORZA: 10}))  # niente DIFESA
    assert stat_eff(nudo, StatId.DIFESA) == 0            # def_eff = 0 è legittimo (§5.3)

    # L'armatura somma in CENTESIMI via un Modificatore{DIFESA}: 310 centesimi = 3,10 unità.
    armato = esper.create_entity(
        Primarie(valori={StatId.FORZA: 10}),
        Modificatori(voci=[Modificatore(StatId.DIFESA, TipoMod.FLAT, 310, "corazza")]),
    )
    assert stat_eff(armato, StatId.DIFESA) == 310        # CENTESIMI, niente round-a-unità
    # Floor 0 (non 1): un debuff che porterebbe sotto zero si ferma a 0, non a 1.
    giu = esper.create_entity(
        Primarie(valori={StatId.DIFESA: 50}),
        Modificatori(voci=[Modificatore(StatId.DIFESA, TipoMod.FLAT, -999, "frantuma")]),
    )
    assert stat_eff(giu, StatId.DIFESA) == 0


def test_GR2_5_difesa_pct_scala_solo_armatura(mondo_isolato: str) -> None:
    # Un PCT su DIFESA scala SOLO la somma-armatura (centesimi), non altro: +20% su 300 = 360.
    ent = esper.create_entity(
        Primarie(valori={StatId.DIFESA: 300}),
        Modificatori(voci=[Modificatore(StatId.DIFESA, TipoMod.PCT, 0.20, "enchant")]),
    )
    assert stat_eff(ent, StatId.DIFESA) == 360


# --- DT-4: la firma di stat_eff resta context-free `(entità, stat)` -------------

def test_DT4_stat_eff_firma_context_free() -> None:
    params = list(inspect.signature(stat_eff).parameters)
    assert params == ["entita", "stat"], "stat_eff non deve ricevere un 3° parametro-contesto"
