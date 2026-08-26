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

from .calibrazione import AP_MAX_MVP, HP_DEFAULT, PRIMARIE_BASE_CARL
from .mob import Repertorio
from .statistiche import Primarie

# Le mosse di PARTENZA del protagonista (chiavi del catalogo chiuso `mosse.py`).
# È una scelta di CONTENUTO (diventerà dato/asset più avanti); il componente
# `Repertorio` è persistente: il repertorio cresce con la run e viaggia nel save.
MOSSE_INIZIALI_PROTAGONISTA: tuple[str, ...] = ("attacco", "attacco_pesante", "dardo_arcano")

# HP iniziale di default: §11 in `calibrazione.py` (editabile dalla console admin).
_HP_DEFAULT = HP_DEFAULT


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


@dataclass
class Mana:
    """Risorsa-mana **posseduta per-entità**: la spesa delle mosse che costano (§11).

    Come `Scheda.punti_vita`, deposita solo il CORRENTE: il massimo DERIVA da
    Intelligenza (`derivate.max_mana`) — così un modificatore sulla stat si
    propaga da solo, senza un secondo numero da tenere in sincrono."""

    attuale: int


def assicura_mana(entita: int) -> Mana:
    """Il `Mana` dell'entità, montandolo PIENO se assente (save scritti prima che
    il mana esistesse: migrazione lazy, nessun cambio di formato)."""
    comp = esper.try_component(entita, Mana)
    if comp is None:
        from .derivate import max_mana  # locale: derivate importa scheda (ciclo)

        comp = Mana(attuale=max_mana(entita))
        esper.add_component(entita, comp)
    return comp


@dataclass
class ActionPoint:
    """Risorsa-AP **posseduta per-entità** (G §2.1): il sistema-turno la legge e la spende.

    Vive qui (e nella factory mob) come lo **stato-posseduto per-entità** — la stessa casa
    di `HP_corrente` — **non** dentro un'`Azione` usa-e-getta (guida §6.1). Single-owner: il
    loop la rinfresca a `ap_max` a inizio turno e la decrementa per azione risolta. Il
    `costo` di un'`Azione` la referenzia **per chiave** (`{"AP": 1}`), ma la definizione del
    componente sta qui."""

    ap: int
    ap_max: int


def crea_protagonista(
    *,
    destrezza: int | None = None,
    id_dominio: str = "carl",
    punti_vita: int | None = None,
) -> int:
    """Crea l'entità persistente del protagonista. Non è effimera (§6.3).

    `destrezza` e `punti_vita` (HP iniziale) entrano nel vettore `Primarie`: la destrezza
    su `DESTREZZA`, l'HP iniziale su `COSTITUZIONE` (così il massimo derivato `max_hp =
    costituzione_eff`, 1→1 segnaposto §5, coincide con l'HP di partenza → "integro"). Le
    altre primarie vengono dal profilo-base SEGNAPOSTO `PRIMARIE_BASE_CARL`.

    `None` = il valore §11 della calibrazione (`CARL.destrezza`/`HP_DEFAULT`): i knob
    della console valgono sul percorso di gioco reale, non solo negli harness — un
    literal qui era il motivo per cui alzare `CARL.costituzione` non faceva nulla
    (audit 2026-08-07)."""
    valori = dict(PRIMARIE_BASE_CARL)
    if destrezza is None:
        destrezza = PRIMARIE_BASE_CARL[StatId.DESTREZZA]
    if punti_vita is None:
        punti_vita = _HP_DEFAULT
    valori[StatId.DESTREZZA] = destrezza
    valori[StatId.COSTITUZIONE] = punti_vita
    from .equip import Zaino  # locale: il ciclo equip↔scheda resta a senso unico

    ent = esper.create_entity(
        Protagonista(id_dominio=id_dominio),
        Primarie(valori=valori),
        Scheda(vivo=True, punti_vita=punti_vita),
        # L'inventario nasce VUOTO col protagonista: il drop è il suo produttore.
        Zaino(),
        # AP posseduto e persistente: il Combattente effimero del combattimento non lo porta
        # (single-owner, guida §6.1). Sopravvive a CombatResolved; il loop lo rinfresca.
        ActionPoint(ap=AP_MAX_MVP, ap_max=AP_MAX_MVP),
        # Le mosse che il giocatore SCEGLIE in combattimento (menu ← questo dato).
        # Save legacy senza il componente: `_scegli_azione` ripiega su MOSSE_DEFAULT.
        Repertorio(mosse=MOSSE_INIZIALI_PROTAGONISTA),
    )
    # Il mana nasce PIENO, e dopo l'entità: il massimo deriva dalle Primarie appena
    # montate (`max_mana` legge Intelligenza via il fold).
    assicura_mana(ent)
    return ent


def protagonista() -> tuple[int, Protagonista, Scheda]:
    """Ritorna (entità, Protagonista, Scheda) del protagonista (singleton)."""
    trovati = esper.get_components(Protagonista, Scheda)
    if len(trovati) != 1:
        raise RuntimeError(f"protagonista singleton atteso, trovati {len(trovati)}")
    ent, (marker, scheda) = trovati[0]
    return ent, marker, scheda
