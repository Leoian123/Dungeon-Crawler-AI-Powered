"""L'`Azione` — atomo spezzato (Gruppo 2 §7): GR2-12 (forma), GR2-13 (tre giunture),
GR2-14 (niente corpo skill), GR2-17 (interna al motore, mai DTO). Headless, seeded.
"""

from __future__ import annotations

import ast
import dataclasses
import re
from pathlib import Path

import esper
import pydantic

import contracts
from contracts import CombatResolved, TipoDanno
from motore import (
    ActionPoint,
    Azione,
    Danno,
    Effetto,
    Nemico,
    PuntiVita,
    QuantitaDa,
    SpecNemico,
    protagonista,
    tick,
)
from tests.combat_helpers import avvia_scontro

_MOTORE = Path(__file__).resolve().parents[1] / "src" / "motore"


# --- GR2-12: il loop esegue una `Azione` {sorgente, bersaglio, effetti, costo} --

def test_GR2_12_forma_azione() -> None:
    campi = {f.name for f in dataclasses.fields(Azione)}
    # `mossa` è flavour per la cronaca (chiave diegetica), non una quarta giuntura.
    assert campi == {"sorgente", "bersaglio", "effetti", "costo", "mossa"}

    # L'attacco base è l'UNICA istanza dell'MVP: effetti=[Danno], costo={"AP": 1}.
    az = Azione(sorgente=1, bersaglio=2, effetti=[Danno(quantita_da=QuantitaDa.ATK_EFF)])
    assert az.costo == {"AP": 1}
    assert len(az.effetti) == 1 and isinstance(az.effetti[0], Danno)
    assert az.effetti[0].quantita_da is QuantitaDa.ATK_EFF
    assert az.effetti[0].tipo is TipoDanno.GENERICO     # default untyped (DT-1)

    # Il risolutore esegue un'`Azione` composta dal catalogo mosse (Fase 1: la
    # costruzione vive in mosse.py come DATO; il loop la chiama, non la cabla).
    src = (_MOTORE / "combattimento.py").read_text(encoding="utf-8")
    assert "azione_da_mossa(" in src
    assert "Azione(" in (_MOTORE / "mosse.py").read_text(encoding="utf-8")


# --- GR2-13: scelta da un insieme, costo verificato PRIMA, effetti iterati ------

def test_GR2_13_costo_verificato_prima(mondo_isolato: str) -> None:
    # Giuntura 2: senza AP pagabile, l'azione non si esegue → il nemico non subisce danno.
    avvia_scontro(nemici=[SpecNemico(destrezza=1, punti_vita=1000)],
                  hp_prot=10**9, destrezza_prot=100)  # protagonista agisce per primo
    pent, _m, _s = protagonista()
    nem = [e for e, _ in esper.get_component(Nemico)][0]
    hp0 = esper.component_for_entity(nem, PuntiVita).attuali

    # Azzera l'AP del protagonista PRIMA del tick: il loop refilla a ap_max, quindi per
    # provare il gate del costo azzeriamo anche l'ap_max (costo 1 > 0 → niente azione).
    ap = esper.component_for_entity(pent, ActionPoint)
    ap.ap_max = 0
    tick()
    assert esper.component_for_entity(nem, PuntiVita).attuali == hp0, "AP 0 → nessuna azione"


def test_GR2_13_effetti_iterati_come_lista(mondo_isolato: str) -> None:
    # Giuntura 3: gli effetti sono iterati come lista → il bersaglio subisce danno.
    avvia_scontro(nemici=[SpecNemico(destrezza=1, punti_vita=1000)],
                  hp_prot=10**9, destrezza_prot=100)
    nem = [e for e, _ in esper.get_component(Nemico)][0]
    hp0 = esper.component_for_entity(nem, PuntiVita).attuali
    tick()  # turno del protagonista: itera [Danno] → infligge
    assert esper.component_for_entity(nem, PuntiVita).attuali < hp0


# --- GR2-14 EMENDATO (2026-08): il motore-skill è ACCESO, ma resta senza SISTEMA --
#
# GR2-14 vietava «Mana, cooldown, SistemaSkill» perché erano corpo ANTICIPATO: nel
# Gruppo 2 non c'era ancora una ragione di gioco per averli. La decisione di prodotto
# (Mossa 2, 2026-08) li rende necessari: senza una risorsa, `attacco_pesante` è
# strettamente dominante e la scelta della mossa non è una scelta.
#
# Ciò che il divieto proteggeva DAVVERO resta in piedi, e questo test lo custodisce:
# niente `SistemaSkill` separato. Mana e cooldown sono DATI (un componente posseduto,
# un componente effimero) letti dal risolutore che già c'era — nessun secondo motore
# accanto a `SistemaTurnoCombattimento`.

def test_GR2_14_nessun_sistema_skill_separato() -> None:
    # Statico sui NOMI di classe (non su docstring/commenti: "skill" può comparire nella
    # prosa che spiega *cosa non si fa*).
    classi: set[str] = set()
    for f in _MOTORE.rglob("*.py"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.ClassDef):
                classi.add(n.name)
    vietati = {c for c in classi if "Skill" in c}
    assert vietati == set(), f"nessun motore-skill separato: {vietati}"
    # I due dati dell'economia esistono e sono esattamente due (nessuna proliferazione).
    assert "Mana" in classi and "Ricariche" in classi


def test_GR2_14_il_costo_lo_spende_il_risolutore_che_gia_esisteva() -> None:
    """L'unico punto che scala le risorse resta `_risolvi_azione`: mana e AP si
    pagano nella STESSA giuntura (GR2-13), non in un sistema a parte."""
    sorgente = (_MOTORE / "combattimento.py").read_text(encoding="utf-8")
    corpo = sorgente.split("def _risolvi_azione")[1].split("\n    def ")[0]
    assert 'costo.get("MANA"' in corpo, "il mana non si spende dove si spende l'AP"
    # E nessun altro punto del motore scrive `Mana.attuale` (single-owner).
    scrittori = [
        f.name for f in _MOTORE.rglob("*.py")
        if re.search(r"\.attuale\s*-=", f.read_text(encoding="utf-8"))
    ]
    assert scrittori == ["combattimento.py"], f"la spesa del mana è sparsa: {scrittori}"


# --- GR2-17: `Azione` è interna al motore — non DTO, non attraversa la membrana --

def test_GR2_17_azione_non_attraversa_la_membrana() -> None:
    # Non è un DTO di `contracts` (né esportata, né presente come simbolo).
    assert "Azione" not in contracts.__all__
    assert not hasattr(contracts, "Azione")
    # Statico: l'identificatore `Azione` (parola intera, non il sottostringa di `TipoAzione`)
    # non compare in `contracts/` (GR2-17).
    cdir = Path(__file__).resolve().parents[1] / "src" / "contracts"
    for f in cdir.glob("*.py"):
        assert not re.search(r"\bAzione\b", f.read_text(encoding="utf-8")), f.name


def test_GR2_17_azione_non_e_pydantic() -> None:
    # Atomo interno: dataclass plain, NON un BaseModel Pydantic (non serializzato, non gate).
    for tipo in (Azione, Effetto, Danno):
        assert dataclasses.is_dataclass(tipo)
        assert not issubclass(tipo, pydantic.BaseModel)


def test_GR2_17_ref_vivi_solo_transitori(mondo_isolato: str) -> None:
    # `sorgente`/`bersaglio` sono ref vivi (id esper) ammessi PERCHÉ transitori: dopo il
    # CombatResolved nessuna `Azione` sopravvive in un componente persistente. Verifica che
    # nessuna entità porti un componente `Azione` (non è mai depositata).
    _bus, adapter, _enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=5, punti_vita=1)], hp_prot=10**9, destrezza_prot=100,
    )
    for _ in range(50):
        tick()
        if adapter.events_of(CombatResolved):
            break
    # Nessun componente `Azione` esiste sul World (mai depositata, GR2-17).
    assert esper.get_component(Azione) == []
