"""Disciplina statica della persistenza (H-1/2/3/4/5/16/17/18/19).

Verifiche AST/grep sui moduli di `motore/persistenza`: la persistenza tocca i dati,
mai conosce i sistemi (§10.5).
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

from motore.persistenza import tag as TAG
from motore.persistenza.formato import Corpo, Intestazione, RecordArchivio
from motore.scheda import Protagonista, Scheda
from motore.status import Veleno

_SRC = Path(__file__).resolve().parents[1] / "src"
_PERS = _SRC / "motore" / "persistenza"


def _moduli() -> list[Path]:
    out = sorted(_PERS.glob("*.py"))
    assert out, "motore/persistenza vuoto o spostato: i divieti passerebbero per vacuità"
    return out


# --- H-1 / H-19: niente pickle, niente prompt caching -------------------------

def test_H1_nessun_pickle_o_marshal() -> None:
    # Niente uso (import o chiamata) di pickle/marshal sul percorso di save/load.
    for py in _moduli():
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for nodo in ast.walk(tree):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    assert alias.name.split(".")[0] not in {"pickle", "marshal"}, py.name
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                assert nodo.module.split(".")[0] not in {"pickle", "marshal"}, py.name


def test_H19_nessun_prompt_caching_in_H() -> None:
    for py in _moduli():
        src = py.read_text(encoding="utf-8").lower()
        assert "prompt_cach" not in src and "prompt caching" not in src, py.name


# --- H-2: i componenti non portano to_dict/from_dict (traduzione in H) ---------

def test_H2_componenti_senza_to_dict_from_dict() -> None:
    for componente in (Protagonista, Scheda, Veleno):
        assert not hasattr(componente, "to_dict"), componente.__name__
        assert not hasattr(componente, "from_dict"), componente.__name__


# --- H-3: ogni tag ha un binding; round-trip dei tipi registrati --------------

def test_H3_registry_tag_biunivoco() -> None:
    tipi = TAG.tipi_registrati()
    tag = {TAG.tag_di(t) for t in tipi}
    assert len(tag) == len(tipi)  # tag distinti
    for t in tipi:
        assert TAG.tipo_di(TAG.tag_di(t)) is t  # round-trip tag→tipo→tag


def test_H3_tag_senza_binding_solleva() -> None:
    import pytest

    with pytest.raises(KeyError):
        TAG.tipo_di("tag_inesistente")


# --- H-4: nessun id di entità esper serializzato come riferimento durevole -----

def test_H4_nessun_id_esper_nei_componenti_serializzati() -> None:
    # I dati serializzati di un componente non contengono campi-id di entità esper:
    # l'identità è l'uuid (su Protagonista.id_dominio), un valore copiato.
    tag, dati = TAG.serializza_componente(Protagonista(id_dominio="carl"))
    assert tag == "protagonista"
    assert dati == {"id_dominio": "carl"}
    assert "entita" not in dati and "entity" not in dati and "ent_id" not in dati


def test_H4_corpo_non_referenzia_id_esper() -> None:
    # Il modello Corpo non ha campi che reggano referenze inter-entità via id esper.
    campi = set(Corpo.model_fields)
    assert "entita" in campi  # lista di entità, ciascuna coi suoi componenti
    # Nessun campo di "riferimenti"/"mappa id" (load diretto, niente 3-fasi nell'MVP).
    assert not any("id" in c and c != "uuid" for c in campi)


# --- H-5: identità = uuid in un componente E nel metadato; niente contatore ----

def test_H5_uuid_in_componente_e_in_intestazione() -> None:
    assert "id_dominio" in {f.name for f in dataclasses.fields(Protagonista)}
    assert "uuid" in Intestazione.model_fields


def test_H5_nessun_contatore_app_level_di_id() -> None:
    for py in _moduli():
        src = py.read_text(encoding="utf-8").lower()
        # Nessun "prossimo id crawler"/contatore globale (si usa uuid, §5).
        assert "prossimo_id" not in src and "next_id" not in src


# --- H-16: la persistenza non importa sistemi/Processor/provider/Textual -------

def test_H16_nessun_import_di_sistemi_o_provider_o_textual() -> None:
    radici_vietate = {"textual", "provider", "anthropic"}
    offese: list[str] = []
    for py in _moduli():
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for nodo in ast.walk(tree):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    if alias.name.split(".")[0] in radici_vietate:
                        offese.append(f"{py.name}: import {alias.name}")
            elif isinstance(nodo, ast.ImportFrom):
                if nodo.level == 0 and nodo.module and nodo.module.split(".")[0] in radici_vietate:
                    offese.append(f"{py.name}: from {nodo.module}")
    assert not offese, "import vietati nella persistenza:\n" + "\n".join(offese)


def test_H16_nessun_processor_nella_persistenza() -> None:
    # La persistenza non definisce Processor: non può ticcare (save a evento, non a tick).
    for py in _moduli():
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for nodo in ast.walk(tree):
            if isinstance(nodo, ast.ClassDef):
                basi = {b.id for b in nodo.bases if isinstance(b, ast.Name)}
                basi |= {
                    b.attr for b in nodo.bases if isinstance(b, ast.Attribute)
                }
                assert "Processor" not in basi and "PhasedProcessor" not in basi, nodo.name


# --- H-17: nessun log di chat serializzato ------------------------------------

def test_H17_nessuna_persistenza_della_chat() -> None:
    # I modelli del formato non hanno campi di conversazione/chat (è derivata).
    for modello in (Intestazione, Corpo, RecordArchivio):
        for campo in modello.model_fields:
            assert "chat" not in campo.lower() and "conversaz" not in campo.lower(), (
                f"{modello.__name__}.{campo}"
            )


# --- H-18: il contatore di tempo-piano è un campo serializzato, senza logica ---

def test_H18_tempo_piano_e_un_componente_registrato_senza_logica() -> None:
    from motore.piano import TempoPiano

    # È un dato puro (campo serializzato), con un tag nel registry.
    assert TAG.e_persistente(TempoPiano)
    assert {f.name for f in dataclasses.fields(TempoPiano)} == {"tick"}
    # Nessun METODO di logica temporale sul componente (slot per J): i soli attributi
    # di classe non-dunder sono i default dei campi (dato), non funzioni.
    metodi = [
        m for m, v in vars(TempoPiano).items() if not m.startswith("__") and callable(v)
    ]
    assert metodi == [], f"TempoPiano non deve avere logica: {metodi}"
