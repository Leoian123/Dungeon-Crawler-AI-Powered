"""Helper condivisi per i test di narrazione (non è un modulo di test).

Costruttori rapidi di candidati `TurnoNarrazione`/budget, per non ripetere la
boilerplate Pydantic in ogni test.
"""

from __future__ import annotations

from contracts import (
    Blocco,
    Durata,
    EntitaGenerata,
    Grado,
    Opzione,
    TipoAzione,
    TurnoNarrazione,
)
from motore import Budget, ARCHETIPO_DEFAULT


def budget(
    *,
    livello: int = 1,
    gradi=(Grado.BRONZO, Grado.ARGENTO),
    blocchi=(Blocco.VELENO, Blocco.RIGENERAZIONE),
    archetipo_default: str = ARCHETIPO_DEFAULT,
    anomala: bool = False,
) -> Budget:
    return Budget(
        livello=livello,
        gradi_ammessi=frozenset(gradi),
        blocchi_ammessi=frozenset(blocchi),
        archetipo_default=archetipo_default,
        anomala=anomala,
    )


def turno(
    *,
    archetipo: str = "slime",
    grado: Grado = Grado.BRONZO,
    blocchi=(Blocco.VELENO,),
    durata: Durata = Durata.TURNO,
    prosa: str = "Una stanza.",
    nome: str = "Slime Mangiascarti",
    descrizione: str = "Verde, viscido.",
) -> TurnoNarrazione:
    return TurnoNarrazione(
        prosa=prosa,
        entita=EntitaGenerata(
            archetipo=archetipo,
            grado=grado,
            blocchi=list(blocchi),
            nome=nome,
            descrizione=descrizione,
        ),
        opzioni=[
            Opzione(tipo=TipoAzione.COMBATTI, etichetta="Combatti"),
            Opzione(tipo=TipoAzione.SCAPPA, etichetta="Scappi"),
        ],
        durata=durata,
    )
