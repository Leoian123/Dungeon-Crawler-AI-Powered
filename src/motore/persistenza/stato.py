"""(De)serializzazione del run-World: entità via `components_for_entity` (H §4.1).

`serializza_stato` cammina le entità del World corrente e, per ciascuna, prende i suoi
componenti via `components_for_entity` (FNC §6.1), serializzando **solo** quelli
registrati (tag.py): protagonista, status, e i singleton `FaseCorrente` /
`ProfonditaPiano` / `TempoPiano` / `SemeRun`. Le entità effimere (combattimento,
messaggi-intento) non hanno componenti registrati → vengono saltate: niente stato
effimero nel save.

`applica_stato` ricrea le entità nel World corrente (il chiamante garantisce che sia
pulito). Le nuove entità ricevono **nuovi id esper** — e va bene: nessun id esper è mai
un riferimento durevole (H-4); le referenze (l'uuid) sono valori copiati.
"""

from __future__ import annotations

from dataclasses import dataclass

import esper

from ..piano import ProfonditaPiano
from ..scheda import Protagonista, Scheda
from .formato import (
    SCHEMA_VERSION,
    ComponenteSerializzato,
    Corpo,
    EntitaSerializzata,
    Intestazione,
)
from .tag import deserializza_componente, e_persistente, serializza_componente


@dataclass
class Stato:
    """Lo stato di una run pronto per il disco / appena letto dal disco."""

    intestazione: Intestazione
    corpo: Corpo


def _trova_protagonista() -> tuple[Protagonista, int]:
    trovati = esper.get_components(Protagonista, Scheda)
    if len(trovati) != 1:
        raise RuntimeError(f"protagonista singleton atteso, trovati {len(trovati)}")
    _ent, (marker, _scheda) = trovati[0]
    prof = esper.get_component(ProfonditaPiano)
    livello = prof[0][1].livello if prof else 1
    return marker, livello


def serializza_stato(
    *,
    model_id: str,
    timestamp: float,
    etichetta: str | None = None,
    archivio_ref: str,
    esplorazione: dict | None = None,
    rng_state: list | None = None,
) -> Stato:
    """Fotografa il World corrente in uno `Stato` (header + corpo). Nessuna scrittura
    su disco qui: pura traduzione dati→formato (H §4.3)."""
    marker, livello = _trova_protagonista()

    entita: list[EntitaSerializzata] = []
    for ent in sorted(esper.get_entities()):
        componenti: list[ComponenteSerializzato] = []
        for comp in esper.components_for_entity(ent):
            if e_persistente(type(comp)):
                tag, dati = serializza_componente(comp)
                componenti.append(ComponenteSerializzato(tag=tag, dati=dati))
        if componenti:
            entita.append(EntitaSerializzata(componenti=componenti))

    intestazione = Intestazione(
        uuid=marker.id_dominio,
        etichetta=etichetta if etichetta is not None else marker.id_dominio,
        profondita=livello,
        timestamp=timestamp,
        schema_version=SCHEMA_VERSION,
        model_id=model_id,
    )
    corpo = Corpo(
        entita=entita,
        archivio_ref=archivio_ref,
        esplorazione=esplorazione,
        rng_state=rng_state,
    )
    return Stato(intestazione=intestazione, corpo=corpo)


def applica_stato(stato: Stato) -> None:
    """Ricrea le entità dello `Stato` nel World corrente (assunto pulito).

    Ogni entità rinasce con i suoi componenti tradotti; i singleton tornano come
    entità a sé (`leggi_fase`/`livello_corrente`/`master_seed` ritrovano il loro
    singleton). Nessun riferimento esper durevole da risolvere (load diretto, §4.4).
    Lo slot `esplorazione`, se popolato, ricostruisce il singleton `Mappa` (topologia,
    stanza corrente, visitate — i mob effimeri non erano salvati: si ripopola).
    """
    for ent_ser in stato.corpo.entita:
        componenti = [
            deserializza_componente(c.tag, c.dati) for c in ent_ser.componenti
        ]
        esper.create_entity(*componenti)
    if stato.corpo.esplorazione:
        from ..mappa import mappa_da_dict  # import locale: H resta leggero all'import

        mappa_da_dict(stato.corpo.esplorazione)
