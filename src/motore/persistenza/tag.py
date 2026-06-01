"""Registry tag→tipo e traduzione dato↔formato (H §4.2, §4.3; H-2, H-3).

Due invarianti di H resi concreti qui:

  - **Tag di tipo stabile** (H-3): ogni componente serializzato porta una stringa
    stabile, disaccoppiata dal nome della classe Python, con un binding nel registry.
    Un rename del componente non rompe i save (si aggiorna la mappa, non il dato). È
    l'equivalente del *type registry / object factory* della serializzazione ECS reale.
  - **La traduzione è di H, non dei componenti** (H-2, §4.3): NIENTE `to_dict`/
    `from_dict` dentro i componenti — sporcherebbero i dati con la conoscenza del
    formato. I componenti restano **dataclass ignare**; qui c'è un serializzatore
    generico per dataclass (campi → dict, enum → `.value`) e il suo inverso (via i
    type-hint risolti). La freccia di dipendenza punta in una sola direzione.

Solo i tipi **registrati** sono persistenti: un'entità con componenti non registrati
(le effimere di combattimento, i messaggi-intento) viene semplicemente saltata in
serializzazione — niente stato effimero finisce nel save.
"""

from __future__ import annotations

import dataclasses
import enum
import functools
import typing

from ..fase import FaseCorrente
from ..piano import ProfonditaPiano, TempoPiano
from ..scheda import Protagonista, Scheda
from ..seme import SemeRun
from ..status import Brucia, Rigenerazione, Stordito, Veleno

# --- Registry: tipo → tag STABILE (H-3). I tag non seguono i nomi di classe. -----

_TAG_PER_TIPO: dict[type, str] = {
    Protagonista: "protagonista",
    Scheda: "scheda",
    Veleno: "veleno",
    Brucia: "brucia",
    Rigenerazione: "rigenerazione",
    Stordito: "stordito",
    FaseCorrente: "fase_corrente",
    ProfonditaPiano: "profondita_piano",
    TempoPiano: "tempo_piano",
    SemeRun: "seme_run",
}
_TIPO_PER_TAG: dict[str, type] = {tag: tipo for tipo, tag in _TAG_PER_TIPO.items()}


def tipi_registrati() -> frozenset[type]:
    """I tipi di componente persistenti (round-trippabili)."""
    return frozenset(_TAG_PER_TIPO)


def e_persistente(tipo: type) -> bool:
    """Vero se il tipo ha un binding nel registry (è persistente)."""
    return tipo in _TAG_PER_TIPO


def tag_di(tipo: type) -> str:
    return _TAG_PER_TIPO[tipo]


def tipo_di(tag: str) -> type:
    if tag not in _TIPO_PER_TAG:
        raise KeyError(f"tag senza binding nel registry: {tag!r}")
    return _TIPO_PER_TAG[tag]


# --- Traduzione generica dataclass↔dict (vive in H, non nei componenti) ---------

@functools.lru_cache(maxsize=None)
def _hints(tipo: type) -> dict[str, object]:
    """Type-hint risolti (le annotazioni stringa di `from __future__ import
    annotations` diventano tipi reali). Serve a riconoscere i campi-enum."""
    return typing.get_type_hints(tipo)


def serializza_componente(comp: object) -> tuple[str, dict]:
    """Componente → (tag, dati JSON-able). Enum → `.value`; primitivi invariati."""
    tipo = type(comp)
    dati: dict[str, object] = {}
    for campo in dataclasses.fields(comp):
        valore = getattr(comp, campo.name)
        dati[campo.name] = valore.value if isinstance(valore, enum.Enum) else valore
    return _TAG_PER_TIPO[tipo], dati


def deserializza_componente(tag: str, dati: dict) -> object:
    """(tag, dati) → istanza del componente. I campi-enum si ricostruiscono dal
    `.value` usando i type-hint risolti del tipo."""
    tipo = tipo_di(tag)
    hints = _hints(tipo)
    kwargs: dict[str, object] = {}
    for nome, valore in dati.items():
        annot = hints.get(nome)
        if isinstance(annot, type) and issubclass(annot, enum.Enum):
            kwargs[nome] = annot(valore)
        else:
            kwargs[nome] = valore
    return tipo(**kwargs)
