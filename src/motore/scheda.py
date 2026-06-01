"""Scheda-placeholder del protagonista (G-2, §6.5/§6.6).

Carl predefinito (DCC), nessuna scelta meccanica nell'MVP. La scheda **esiste** come
stato del protagonista persistente (entità del bucket sempre-attivo). G rende
obbligatori adesso tre pezzi; il resto (curva di livello, abilità, stat secondarie) è
contenuto rimandato (Gruppo 2):

  - `destrezza`  — letta dall'iniziativa (§2.2);
  - `vivo`       — lo stato-vita letto dal death-check (§6.2);
  - `punti_vita` / `punti_vita_max` — i campi che alimentano la **proiezione DTO**
    (§6.6): la sorgente da cui il motore deriva `"ferito"`, `"avvelenato"`, ecc.
    (la proiezione vera vive in `contracts`, costruita dal motore — non qui).

L'identità del crawler è un **id di dominio** (§6.3), MAI l'id di entità esper
(sequenziale e riciclato). Vive sul componente e (in H) come metadato del save.

`Scheda`/`Protagonista` sono **dati puri** (ESP §1): nessuna logica.
"""

from __future__ import annotations

from dataclasses import dataclass

import esper

# Valori SEGNAPOSTO (Gruppo 2): non bloccano la forma.
_HP_DEFAULT = 30


@dataclass
class Protagonista:
    """Marker dell'entità persistente + identità di dominio del crawler (§6.3)."""

    id_dominio: str  # uuid/contatore di H; NON l'id di entità esper


@dataclass
class Scheda:
    """Scheda-placeholder: i tre pezzi obbligatori (G-2) + segnaposto Gruppo 2."""

    destrezza: int
    vivo: bool = True
    punti_vita: int = _HP_DEFAULT
    punti_vita_max: int = _HP_DEFAULT


def crea_protagonista(
    *,
    destrezza: int,
    id_dominio: str = "carl",
    punti_vita: int = _HP_DEFAULT,
) -> int:
    """Crea l'entità persistente del protagonista. Non è effimera (§6.3)."""
    return esper.create_entity(
        Protagonista(id_dominio=id_dominio),
        Scheda(destrezza=destrezza, vivo=True, punti_vita=punti_vita, punti_vita_max=punti_vita),
    )


def protagonista() -> tuple[int, Protagonista, Scheda]:
    """Ritorna (entità, Protagonista, Scheda) del protagonista (singleton)."""
    trovati = esper.get_components(Protagonista, Scheda)
    if len(trovati) != 1:
        raise RuntimeError(f"protagonista singleton atteso, trovati {len(trovati)}")
    ent, (marker, scheda) = trovati[0]
    return ent, marker, scheda
