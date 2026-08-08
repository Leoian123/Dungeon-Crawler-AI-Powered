"""Verifiche statiche dello schema del contratto AI↔motore (F-1, F-3, F-4).

Non serve un contesto esper: sono DTO puri.
"""

from __future__ import annotations

import enum
import typing

import pytest

from contracts import schema as S
from contracts import (
    Blocco,
    Durata,
    EntitaGenerata,
    Flavor,
    Grado,
    Opzione,
    TipoAzione,
    TurnoNarrazione,
)

# Nomi/tipi che NON devono comparire come campi numerici o leve di budget/anomalia.
_NOMI_NUMERICI_VIETATI = {
    "hp", "danno", "difesa", "durata", "durate",
    "livello", "level", "statistiche", "stat",
}
_NOMI_LEVA_VIETATI = {
    "anomalia", "anomaly", "budget", "tetto", "soffitto", "livello", "level",
}
_TIPI_NUMERICI = (int, float, complex)


def _tipi_concreti(annotazione: object) -> set[type]:
    """Raccoglie ricorsivamente i tipi concreti dentro un'annotazione (anche list[...])."""
    origine = typing.get_origin(annotazione)
    args = typing.get_args(annotazione)
    if origine is None and isinstance(annotazione, type):
        return {annotazione}
    trovati: set[type] = set()
    for a in args:
        trovati |= _tipi_concreti(a)
    return trovati


# --- Lo schema esportato è SNELLO: niente docstring in viaggio -----------------

def test_lo_schema_ai_non_trasporta_docstring() -> None:
    """Le docstring (con i riferimenti alle spec interne) sono per chi legge il
    codice: esportate come `description` pesavano ~40% dei token di input di OGNI
    chiamata al provider (audit 2026-08-07). Se un giorno serve una descrizione
    PENSATA per l'AI, si dichiara con `Field(description=...)` e si aggiorna
    questo test elencando le eccezioni volute — mai per docstring di ritorno."""
    import json

    from contracts import Ideazione, InquadramentoProva

    for modello in (TurnoNarrazione, Ideazione, InquadramentoProva, Flavor):
        testo = json.dumps(modello.model_json_schema())
        assert '"description"' not in testo, (
            f"{modello.__name__}: una docstring è tornata nello schema AI-facing"
        )


# --- F-3: EntitaGenerata senza campi numerici (né livello) --------------------

def test_F3_entita_generata_senza_campi_numerici() -> None:
    for nome, info in EntitaGenerata.model_fields.items():
        assert nome.lower() not in _NOMI_NUMERICI_VIETATI, (
            f"campo numerico/vietato in EntitaGenerata: {nome}"
        )
        concreti = _tipi_concreti(info.annotation)
        for tipo in concreti:
            # bool è sottoclasse di int: escluso comunque dai tipi numerici.
            assert not (isinstance(tipo, type) and issubclass(tipo, _TIPI_NUMERICI)), (
                f"campo numerico in EntitaGenerata.{nome}: {tipo}"
            )


def test_F3_entita_generata_non_ha_livello() -> None:
    assert "livello" not in EntitaGenerata.model_fields


def test_F3_campi_attesi_di_entita_generata() -> None:
    # archetipo, grado, blocchi, nome, descrizione (F-1/§2) + `riferimento` (D5):
    # il reclutamento dal cast — un NOME da un set chiuso per-run, opzionale,
    # verificato dal 4° strato del gate. Mai un numero.
    assert set(EntitaGenerata.model_fields) == {
        "archetipo", "grado", "blocchi", "nome", "descrizione", "riferimento",
    }
    assert EntitaGenerata.model_fields["riferimento"].default is None


# --- F-4: campi a conseguenza meccanica = enum chiusi; nessuna leva ------------

def _enum_chiuso(annotazione: object) -> bool:
    return all(
        issubclass(t, enum.Enum)
        for t in _tipi_concreti(annotazione)
    )


def test_F4_campi_meccanici_sono_vocabolari_chiusi() -> None:
    # Grado/Blocco/TipoAzione/Durata restano enum compilati.
    assert _enum_chiuso(EntitaGenerata.model_fields["grado"].annotation)
    assert _enum_chiuso(EntitaGenerata.model_fields["blocchi"].annotation)
    assert _enum_chiuso(Opzione.model_fields["tipo"].annotation)
    assert _enum_chiuso(TurnoNarrazione.model_fields["durata"].annotation)


def test_F4_archetipo_slug_a_chiusura_per_run() -> None:
    # D1: l'archetipo NON è più un enum compilato — è uno slug kebab-case stretto
    # (forma chiusa qui) la cui APPARTENENZA è validata dal gate contro il registry
    # congelato nella run (F-6 runtime, coperto in test_narrazione_gate). Il pattern
    # respinge tutto ciò che non è un nome di catalogo ben formato.
    def _eg(archetipo: str) -> EntitaGenerata:
        return EntitaGenerata(
            archetipo=archetipo, grado=Grado.BRONZO, blocchi=[], nome="x", descrizione="",
        )

    assert _eg("ratto-mutante").archetipo == "ratto-mutante"  # slug nuovo: forma legale
    for illegale in ("Non Kebab", "UPPER", "spazi no", "-inizia-male", "a" * 61, ""):
        with pytest.raises(Exception):
            _eg(illegale)


def test_F4_nessuna_leva_di_budget_o_anomalia() -> None:
    for modello in (EntitaGenerata, Opzione, TurnoNarrazione, Flavor):
        for nome in modello.model_fields:
            assert nome.lower() not in _NOMI_LEVA_VIETATI, (
                f"leva vietata (budget/anomalia/livello) in {modello.__name__}.{nome}"
            )


def test_F4_schema_chiuso_extra_vietati() -> None:
    # extra="forbid": l'AI non può aggiungere un campo per invocare l'anomalia.
    for modello in (EntitaGenerata, Opzione, TurnoNarrazione, Flavor):
        assert modello.model_config.get("extra") == "forbid", modello.__name__
    # Prova comportamentale: un campo extra viene rifiutato dalla validazione.
    with pytest.raises(Exception):
        Flavor.model_validate({"testo": "ok", "anomalia": True})


# --- F-1: forma di TurnoNarrazione e Flavor; durata su Turno, non su Flavor ----

def test_F1_turno_narrazione_ha_i_campi_giusti() -> None:
    # `beneficio` (gate anti-arbitraggio): classificazione su enum chiuso col default
    # NESSUNO — l'AI classifica il vantaggio reclamato, il costo lo applica il motore.
    assert set(TurnoNarrazione.model_fields) == {
        "prosa", "entita", "opzioni", "durata", "beneficio",
    }
    assert "livello" not in TurnoNarrazione.model_fields


def test_F1_durata_su_turno_e_di_tipo_durata() -> None:
    assert "durata" in TurnoNarrazione.model_fields
    assert TurnoNarrazione.model_fields["durata"].annotation is Durata


def test_F1_flavor_non_ha_durata() -> None:
    assert "durata" not in Flavor.model_fields
    assert set(Flavor.model_fields) == {"testo"}


def test_F1_un_solo_schema_di_narrazione() -> None:
    # Lo schema di narrazione è UNO solo (una chiamata `genera` per turno, FNC §5.1).
    from pydantic import BaseModel

    modelli_narrazione = [
        nome for nome, obj in vars(S).items()
        if isinstance(obj, type) and issubclass(obj, BaseModel)
        and "entita" in getattr(obj, "model_fields", {})
    ]
    assert modelli_narrazione == ["TurnoNarrazione"], modelli_narrazione


# --- F-14: Durata è una categoria con ordine totale ---------------------------

def test_F14_durata_ordine_totale() -> None:
    ordinato = [Durata.TURNO, Durata.UN_ATTIMO, Durata.UN_POCHINO, Durata.UN_BEL_PO]
    # Crescente e stretto.
    assert ordinato == sorted(ordinato)
    for piccolo, grande in zip(ordinato, ordinato[1:]):
        assert piccolo < grande
        assert grande > piccolo
        assert piccolo <= grande and grande >= piccolo
        assert piccolo != grande
    # TURNO è il minimo (cadenza base).
    assert min(ordinato) == Durata.TURNO
    # È una categoria, non un numero.
    assert not isinstance(Durata.TURNO.value, (int, float))
