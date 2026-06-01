"""Proiezione di sola lettura della scheda (G-13): l'AI legge una vista, non il registro.

L'AI riceve lo stato del protagonista SOLO via DTO di proiezione in `contracts`;
nessun componente ECS vivo è passato al provider/prompt.
"""

from __future__ import annotations

import asyncio

import pytest

from contracts import SchedaProiezione
from motore import (
    applica_status,
    costruisci_prompt,
    crea_protagonista,
    procura_turno,
    proietta_scheda,
    protagonista,
    Veleno,
)
from provider import FakeProvider
from tests.narr_helpers import budget, turno


def test_G13_proiezione_e_un_dto_di_contracts() -> None:
    # Il DTO vive in `contracts` (membrana), non nel motore.
    import contracts

    assert SchedaProiezione.__module__.startswith("contracts")
    assert hasattr(contracts, "SchedaProiezione")


def test_G13_proiezione_senza_numeri(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    _p, _m, scheda = protagonista()
    scheda.punti_vita = 7  # ferito
    applica_status(pent, Veleno(rango=2, durata=3))

    proj = proietta_scheda(pent)
    assert isinstance(proj, SchedaProiezione)
    # Descrittori diegetici, MAI numeri (niente "7", niente "30", niente hp).
    assert "ferito" in proj.descrittori
    assert "avvelenato" in proj.descrittori
    for d in proj.descrittori:
        assert not any(ch.isdigit() for ch in d), f"descrittore con numero: {d!r}"


def test_G13_proiezione_e_immutabile(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    proj = proietta_scheda(pent)
    # frozen=True: sola lettura davvero.
    with pytest.raises(Exception):
        proj.descrittori = ("manomesso",)  # type: ignore[misc]


def test_G13_prompt_riceve_solo_la_proiezione_non_la_scheda_viva(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    proj = proietta_scheda(pent)
    prompt = costruisci_prompt(budget(), proj, voce="V")
    # Il prompt è una stringa opaca; i descrittori vi compaiono, nessun oggetto vivo.
    assert isinstance(prompt, str)
    assert "integro" in prompt


def test_G13_al_provider_arriva_solo_una_stringa(mondo_isolato: str) -> None:
    # Comportamentale: ciò che attraversa il socket è una stringa, mai un componente ECS.
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    proj = proietta_scheda(pent)
    prov = FakeProvider([turno()])
    asyncio.run(procura_turno(prov, budget(), proj))
    assert len(prov.chiamate) == 1
    prompt_inviato, _schema = prov.chiamate[0]
    assert isinstance(prompt_inviato, str)
