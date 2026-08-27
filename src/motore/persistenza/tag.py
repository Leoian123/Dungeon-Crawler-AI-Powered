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

from ..corredo import Corredo
from ..design import StagioneAttiva
from ..equip import ComponenteEquip, Guardaroba, Zaino
from ..oggetti import OggettiConiati
from ..fase import FaseCorrente
from ..mob import EntitaMob, Repertorio
from ..modificatori import Modificatori, Resistenze
from ..fantasmi import FantasmiAttivi
from ..obiettivi import ObiettiviRun
from ..skill import SkillDelCrawler
from ..piano import ProfonditaPiano, TempoPiano
from ..scheda import ActionPoint, Mana, Protagonista, Scheda
from ..territorio import StatoTerritorio
from ..seme import SemeRun
from ..wiki import MarcatoreWiki, PropostePendenti
from ..statistiche import Primarie
from ..status import STATUS_PERSISTENTI, nome_status

# --- Registry: tipo → tag STABILE (H-3). I tag non seguono i nomi di classe. -----

_TAG_PER_TIPO: dict[type, str] = {
    Protagonista: "protagonista",
    Scheda: "scheda",
    Primarie: "primarie",
    Modificatori: "modificatori",
    # AP: risorsa POSSEDUTA del protagonista (G §2.1, guida §6.1) — persistente
    # come la Scheda, non un'effimera di combattimento (quelle restano fuori).
    ActionPoint: "action_point",
    # Mana: risorsa POSSEDUTA come l'AP e gli HP — si spende in scontro e si
    # recupera riposando, quindi deve attraversare il save. Il MASSIMO non è qui:
    # deriva da Intelligenza (`derivate.max_mana`).
    Mana: "mana",
    # Gli STATUS persistenti sono DERIVATI dalla tabella unica (status.SPEC_STATUS):
    # il tag stabile è il nome-dato del tipo (oggi = i nomi storici, H-3 intatto) —
    # un nuovo status entra nel save con la sua riga di tabella, non qui.
    **{cls: nome_status(cls) for cls in STATUS_PERSISTENTI},
    # Il mob di scena rivelato: identità (EntitaMob, con la stanza per il re-link
    # della mappa), profilo gear e resistenze tipate. Round-trippa nel save: al load
    # la stanza NON si ripopola più con un sosia — ritrova IL suo mob (H-4: il
    # legame passa dal dato `stanza`, mai dall'id esper).
    EntitaMob: "entita_mob",
    # I fantasmi delle run altrui (sovra-run, Fase D): set congelato all'ingresso
    # + il flag `consumato` — una traccia narrata non torna al reload.
    FantasmiAttivi: "fantasmi",
    # Obiettivi e Box (nodo O): catalogo congelato + sbloccati + non letti +
    # box chiuse — lo sblocco non si ripete al reload, le box sopravvivono.
    ObiettiviRun: "obiettivi",
    # Skill (nodo S): catalogo congelato + conteggi degli usi — il livello è
    # DERIVATO e non viaggia mai nel save (si ricalcola dagli usi).
    SkillDelCrawler: "skill",
    Corredo: "corredo",
    # Lo Zaino è POSSESSO (fonti di dominio): attraversa il save.
    Zaino: "zaino",
    # Il manifest dell'INDOSSO (ADR-1 F5): round-trippa INSIEME alla coppia
    # filtro-di-provenienza (save) + hook `re_equipaggia` (load) — le voci
    # derivate non viaggiano mai nel save, rinascono dal manifest.
    ComponenteEquip: "equip",
    # La vestizione dei premi (T2b): parole generate e gated — il cimelio
    # battezzato non torna anonimo al load.
    Guardaroba: "guardaroba",
    # Gli oggetti CONIATI in-run (drop generati dall'AI, gated): posseduto
    # persistente — il cimelio nato in run non svanisce al load.
    OggettiConiati: "oggetti_coniati",
    Resistenze: "resistenze",
    Repertorio: "repertorio",
    FaseCorrente: "fase_corrente",
    ProfonditaPiano: "profondita_piano",
    TempoPiano: "tempo_piano",
    SemeRun: "seme_run",
    # La stagione attiva (aggregato di contenuto congelato): il design della run
    # viaggia col save — le run non vedono mai le modifiche di libreria.
    StagioneAttiva: "stagione",
    # Lo stato del TERRITORIO (2026-08-10): posizione nella spina + boss battuti
    # + zone viste. La SPINA non si salva: si rideriva dal seed al load.
    StatoTerritorio: "territorio",
    # Wiki del Master (W1): il MARCATORE dichiara che la run è nata con una
    # slice (il contratto vitale del terzo artefatto passa da qui — rev. 3
    # §3.1); la CODA delle proposte non drenate sopravvive al save. La slice
    # stessa NON è qui: vive in `<uuid>.wiki.gz`, mai nello stato in chiaro.
    MarcatoreWiki: "marcatore_wiki",
    PropostePendenti: "proposte_wiki_pendenti",
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
#
# Un solo translator ricorsivo, **guidato dall'annotazione del campo** (mai da tipi
# hardcoded): chiude scalari, enum, `dict[enum, X]`, `list[dataclass]` e dataclass
# annidate — gli enum sono gestiti *ovunque compaiano* (chiave di mappa **e** campo
# scalare dentro una dataclass annidata). Restare davvero generici è la metà difficile:
# `Primarie.valori: dict[StatId, int]` e `Modificatori.voci: list[Modificatore]` (con tre
# campi-enum dentro `Modificatore`) round-trippano senza una riga dedicata a `StatId`.

@functools.lru_cache(maxsize=None)
def _hints(tipo: type) -> dict[str, object]:
    """Type-hint risolti (le annotazioni stringa di `from __future__ import
    annotations` diventano tipi reali). Serve a ricavare i tipi di chiavi/elementi."""
    return typing.get_type_hints(tipo)


def _e_enum(annot: object) -> bool:
    return isinstance(annot, type) and issubclass(annot, enum.Enum)


def _verso_jsonable(valore: object, annot: object) -> object:
    """Valore vivo → forma JSON-able, guidato dall'annotazione del campo."""
    if isinstance(valore, enum.Enum):
        return valore.value
    origine = typing.get_origin(annot)
    if origine is dict:
        k_t, v_t = typing.get_args(annot)
        return {_verso_jsonable(k, k_t): _verso_jsonable(v, v_t) for k, v in valore.items()}
    if origine in (list, tuple):
        (item_t, *_) = typing.get_args(annot) or (object,)
        return [_verso_jsonable(x, item_t) for x in valore]
    if dataclasses.is_dataclass(valore):
        hints = _hints(type(valore))
        return {
            campo.name: _verso_jsonable(getattr(valore, campo.name), hints.get(campo.name))
            for campo in dataclasses.fields(valore)
        }
    return valore


def _da_jsonable(dato: object, annot: object) -> object:
    """Forma JSON-able → valore vivo, ricostruendo enum/dataclass dai type-hint."""
    if _e_enum(annot):
        return annot(dato)  # type: ignore[operator]
    origine = typing.get_origin(annot)
    # `X | None` (Optional): si scarta il ramo None e si ricorre sul tipo vero —
    # serve ai campi `dataclass | None` (es. `PianoAttivo.territorio`), che prima
    # di questo ramo tornavano dict grezzi in silenzio. PEP 604 incluso.
    import types

    if origine in (typing.Union, types.UnionType):
        if dato is None:
            return None
        interni = [a for a in typing.get_args(annot) if a is not type(None)]
        if len(interni) == 1:
            return _da_jsonable(dato, interni[0])
        return dato  # Union eterogenea: passthrough (nessun campo così, oggi)
    if origine is dict:
        k_t, v_t = typing.get_args(annot)
        return {_da_jsonable(k, k_t): _da_jsonable(v, v_t) for k, v in dato.items()}
    if origine in (list, tuple):
        (item_t, *_) = typing.get_args(annot) or (object,)
        vivi = [_da_jsonable(x, item_t) for x in dato]
        # L'annotazione comanda anche sul CONTENITORE: un campo `tuple[...]`
        # round-trippa come tuple, non come list (invariante di tipo, H-L1).
        return tuple(vivi) if origine is tuple else vivi
    if isinstance(annot, type) and dataclasses.is_dataclass(annot):
        hints = _hints(annot)
        kwargs = {nome: _da_jsonable(v, hints.get(nome)) for nome, v in dato.items()}
        return annot(**kwargs)
    return dato


def serializza_componente(comp: object) -> tuple[str, dict]:
    """Componente → (tag, dati JSON-able). Enum → `.value` ovunque; primitivi invariati."""
    tipo = type(comp)
    hints = _hints(tipo)
    dati: dict[str, object] = {}
    for campo in dataclasses.fields(comp):
        dati[campo.name] = _verso_jsonable(getattr(comp, campo.name), hints.get(campo.name))
    return _TAG_PER_TIPO[tipo], dati


def deserializza_componente(tag: str, dati: dict) -> object:
    """(tag, dati) → istanza del componente, ricostruita dai type-hint risolti del tipo."""
    tipo = tipo_di(tag)
    hints = _hints(tipo)
    kwargs = {nome: _da_jsonable(valore, hints.get(nome)) for nome, valore in dati.items()}
    return tipo(**kwargs)
