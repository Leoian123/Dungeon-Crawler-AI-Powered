"""Scheda-placeholder del protagonista (G-2, §6.5/§6.6; Gruppo 2 §2/§5).

Carl predefinito (DCC), nessuna scelta meccanica nell'MVP. Le statistiche primarie del
protagonista vivono nel **vettore `Primarie`** (Gruppo 2 §2.1), aggiunto alla nascita;
`Scheda` resta la **risorsa-vita posseduta**:

  - `vivo`        — lo stato-vita letto dal death-check (§6.2);
  - `punti_vita`  — HP **corrente** (stato posseduto, mutato dal danno). Il suo *massimo*
    NON è depositato: deriva da Costituzione (`derivate.max_hp`, GR2-10). La destrezza,
    letta dall'iniziativa/prove, è `Primarie[DESTREZZA]` via `stat_eff` — non un campo qui
    (una strada sola, §3.3).

L'identità del crawler è un **id di dominio** (§6.3), MAI l'id di entità esper. Vive sul
componente e (in H) come metadato del save. `Scheda`/`Protagonista` sono **dati puri**
(ESP §1): nessuna logica.
"""

from __future__ import annotations

from dataclasses import dataclass

import esper

from contracts import StatId

from .catalogo import PRIMARIE_BASE_CARL
from .statistiche import Primarie

# Valori SEGNAPOSTO (Gruppo 2): non bloccano la forma.
_HP_DEFAULT = 30


@dataclass
class Protagonista:
    """Marker dell'entità persistente + identità di dominio del crawler (§6.3)."""

    id_dominio: str  # uuid/contatore di H; NON l'id di entità esper


@dataclass
class Scheda:
    """Risorsa-vita posseduta del protagonista: `vivo` + HP **corrente** (§5).

    Il massimo HP non è qui: deriva da Costituzione (`derivate.max_hp`, GR2-10)."""

    vivo: bool = True
    punti_vita: int = _HP_DEFAULT


def crea_protagonista(
    *,
    destrezza: int,
    id_dominio: str = "carl",
    punti_vita: int = _HP_DEFAULT,
) -> int:
    """Crea l'entità persistente del protagonista. Non è effimera (§6.3).

    `destrezza` e `punti_vita` (HP iniziale) entrano nel vettore `Primarie`: la destrezza
    su `DESTREZZA`, l'HP iniziale su `COSTITUZIONE` (così il massimo derivato `max_hp =
    costituzione_eff`, 1→1 segnaposto §5, coincide con l'HP di partenza → "integro"). Le
    altre primarie vengono dal profilo-base SEGNAPOSTO `PRIMARIE_BASE_CARL`."""
    valori = dict(PRIMARIE_BASE_CARL)
    valori[StatId.DESTREZZA] = destrezza
    valori[StatId.COSTITUZIONE] = punti_vita
    return esper.create_entity(
        Protagonista(id_dominio=id_dominio),
        Primarie(valori=valori),
        Scheda(vivo=True, punti_vita=punti_vita),
    )


def protagonista() -> tuple[int, Protagonista, Scheda]:
    """Ritorna (entità, Protagonista, Scheda) del protagonista (singleton)."""
    trovati = esper.get_components(Protagonista, Scheda)
    if len(trovati) != 1:
        raise RuntimeError(f"protagonista singleton atteso, trovati {len(trovati)}")
    ent, (marker, scheda) = trovati[0]
    return ent, marker, scheda
