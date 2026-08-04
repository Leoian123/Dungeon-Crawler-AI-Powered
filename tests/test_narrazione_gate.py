"""Gate a tre strati nel MOTORE: schema · catalogo · budget (F-5, F-6, F-10).

Headless, nessuna rete. Il gate è una funzione pura del motore (`valida_turno`): non
serve un contesto esper per provarne i tre strati.
"""

from __future__ import annotations

import ast
from pathlib import Path

from contracts import Blocco, Durata, Grado
from contracts import schema as S
from motore import (
    REGISTRY_ARCHETIPI,
    REGISTRY_BLOCCHI,
    rango_grado,
    valida_turno,
)
from tests.narr_helpers import budget, turno

_SRC = Path(__file__).resolve().parents[1] / "src"
_MOTORE = _SRC / "motore"
_CONTRACTS = _SRC / "contracts"


# --- F-5: il gate vive nel motore e applica i TRE strati ----------------------

def test_F5_strato_schema_rifiuta_non_conforme() -> None:
    # Un candidato che non parsa nello schema → rifiutato (strato 1). Simuliamo con un
    # oggetto che espone model_dump() ma con payload non conforme.
    class Finto:
        def model_dump(self):
            return {"prosa": "x"}  # mancano entita/opzioni/durata

    assert valida_turno(Finto(), budget()) is None


def test_F5_strato_catalogo_e_budget_insieme() -> None:
    # Candidato pienamente legale → passa.
    assert valida_turno(turno(grado=Grado.BRONZO, blocchi=(Blocco.VELENO,)), budget()) is not None


def test_F5_gate_nel_motore_non_nella_membrana_ne_nel_bus() -> None:
    # Statico: la validazione di budget/catalogo NON vive in contracts (membrana) né
    # nel bus; vive nel motore (narrazione.py). Cerchiamo i marcatori del gate.
    bus = (_CONTRACTS / "bus.py").read_text(encoding="utf-8")
    assert "budget" not in bus.lower()
    assert "gradi_ammessi" not in bus
    narr = (_MOTORE / "narrazione.py").read_text(encoding="utf-8")
    assert "def valida_turno" in narr
    assert "gradi_ammessi" in narr and "blocchi_ammessi" in narr


def test_F5_budget_obbligatorio_anche_sotto_grammatica() -> None:
    # Sotto grammatica schema+catalogo sono garantiti per costruzione; il BUDGET no.
    # Un candidato grammaticalmente perfetto ma fuori budget deve cadere sullo strato 3.
    bud = budget(gradi=(Grado.BRONZO,), blocchi=(Blocco.VELENO,))
    fuori = turno(grado=Grado.ARGENTO, blocchi=(Blocco.VELENO,))  # ARGENTO non ammesso
    assert fuori.entita.grado in Grado  # grammaticalmente valido
    assert valida_turno(fuori, bud) is None  # ma il budget lo respinge


# --- F-6: ogni membro di enum del catalogo ha un binding nel registry ---------

def test_F6_ogni_blocco_ha_un_binding() -> None:
    assert set(REGISTRY_BLOCCHI) == set(Blocco), "ogni Blocco deve avere un componente ECS"


def test_F6_ogni_archetipo_ha_un_binding() -> None:
    # D1: l'archetipo è uno slug a chiusura per-run. L'invariante F-6 diventa: ogni
    # nome che il GATE può accettare (il registry stesso, e con lui il default di
    # fallback e il budget segnaposto) ha un profilo istanziabile — mai un nome
    # accettabile ma non materializzabile.
    from motore import ARCHETIPO_DEFAULT, Budget

    assert set(REGISTRY_ARCHETIPI) == {"slime", "scheletro", "goblin"}  # gli storici
    assert ARCHETIPO_DEFAULT in REGISTRY_ARCHETIPI
    bud = budget()
    assert bud.archetipi_ammessi <= set(REGISTRY_ARCHETIPI)
    assert isinstance(bud, Budget)
    # Un archetipo ben formato ma FUORI registry non passa il gate (strato 2).
    fuori = turno(archetipo="drago-inventato")
    assert valida_turno(fuori, budget()) is None


def test_F6_ogni_grado_ha_un_rango() -> None:
    # Ordine totale sui gradi: ogni membro mappa a un int, tutti distinti.
    ranghi = [rango_grado(g) for g in Grado]
    assert len(set(ranghi)) == len(list(Grado))


def test_F6_nessun_nome_accettabile_ma_non_istanziabile() -> None:
    # Per ogni blocco legale, il gate lo accetta E il registry lo sa istanziare.
    for blocco in Blocco:
        cand = turno(grado=Grado.BRONZO, blocchi=(blocco,))
        bud = budget(blocchi=tuple(Blocco))  # budget largo: isola lo strato catalogo
        assert valida_turno(cand, bud) is not None
        cls = REGISTRY_BLOCCHI[blocco]
        istanza = cls(rango=1, durata=3)  # istanziabile davvero
        assert istanza is not None


# --- F-10: il budget raggiunge l'AI DUE volte (prompt soft + gate hard) -------

def test_F10_budget_nel_prompt_soft() -> None:
    from contracts import SchedaProiezione
    from motore import costruisci_prompt

    bud = budget(gradi=(Grado.BRONZO,), blocchi=(Blocco.VELENO,))
    prompt = costruisci_prompt(bud, SchedaProiezione(descrittori=("integro",)), voce="V")
    # Il set ammissibile è iniettato come testo (soft): l'AI lo rispetta se glielo dici.
    assert "bronzo" in prompt
    assert "veleno" in prompt


def test_F10_gate_hard_non_sostituito_dal_prompt() -> None:
    # Anche se il prompt "diceva" il budget, un candidato fuori budget passa comunque
    # dal provider: solo il gate (hard) lo respinge. È l'unica garanzia vera.
    bud = budget(gradi=(Grado.BRONZO,), blocchi=(Blocco.VELENO,))
    fuori_grado = turno(grado=Grado.ARGENTO, blocchi=(Blocco.VELENO,))
    fuori_blocco = turno(grado=Grado.BRONZO, blocchi=(Blocco.RIGENERAZIONE,))
    assert valida_turno(fuori_grado, bud) is None
    assert valida_turno(fuori_blocco, bud) is None


def test_F10_il_gate_non_e_nel_provider() -> None:
    # Statico: il provider (trasporto) non valida catalogo/budget — è dominio del motore.
    # I marcatori del gate (set ammissibile, funzione di gate) NON vivono nel provider.
    fake = (_SRC / "provider" / "fake.py").read_text(encoding="utf-8")
    assert "gradi_ammessi" not in fake
    assert "blocchi_ammessi" not in fake
    assert "valida_turno" not in fake
    tree = ast.parse(fake)
    # Il provider non importa il motore (niente gate dietro al socket).
    for nodo in ast.walk(tree):
        if isinstance(nodo, ast.ImportFrom) and nodo.module:
            assert nodo.module.split(".")[0] != "motore"
