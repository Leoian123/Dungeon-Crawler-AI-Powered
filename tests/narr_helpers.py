"""Helper condivisi per i test di narrazione (non è un modulo di test).

Costruttori rapidi di candidati `TurnoNarrazione`/budget, per non ripetere la
boilerplate Pydantic in ogni test.
"""

from __future__ import annotations

from contracts import (
    Archetipo,
    Blocco,
    Durata,
    EntitaGenerata,
    Opzione,
    Rarita,
    TipoAzione,
    TurnoNarrazione,
)
from motore import Budget, ARCHETIPO_DEFAULT


def budget(
    *,
    livello: int = 1,
    rarita=(Rarita.COMUNE, Rarita.RARO),
    blocchi=(Blocco.VELENO, Blocco.RIGENERAZIONE),
    archetipo_default: Archetipo = ARCHETIPO_DEFAULT,
    anomala: bool = False,
) -> Budget:
    return Budget(
        livello=livello,
        rarita_ammesse=frozenset(rarita),
        blocchi_ammessi=frozenset(blocchi),
        archetipo_default=archetipo_default,
        anomala=anomala,
    )


def turno(
    *,
    archetipo: Archetipo = Archetipo.SLIME,
    rarita: Rarita = Rarita.COMUNE,
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
            rarita=rarita,
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
