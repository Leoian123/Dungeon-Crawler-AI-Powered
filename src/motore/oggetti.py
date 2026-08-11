"""Oggetti — il canale-asset del loot (ADR-2 ridotto): traduzione e lint.

Il precedente è quello degli archetipi: l'asset (`OggettoAsset`, contracts) è
authoring-facing — fasce ed enum, coi soli numeri LEGALI dell'authoring umano
(`mitigazione_cent`, `danno_base`) tenuti in banda dal lint; il congelamento
per-run è un `OggettoAttivo` dentro la `StagioneAttiva`; e QUI vive l'unica
traduzione dati→oggetto vivo (`PezzoArmatura`/`Arma`/`Accessorio`), coi numeri
derivati da §11 (fascia × rango del grado, categoria → mitigazione, grado →
danno arma). La membrana regge: contracts possiede la FORMA, il motore i numeri.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import esper

from contracts import CategoriaArmatura, Grado, SedeAccessorio, StatId, Taglia
from contracts.proiezione import SlotEquip

from .calibrazione import (
    DANNO_ARMA_PER_GRADO,
    MITIGAZIONE_CENT,
    OGGETTO_MOD_FASCIA,
    TETTO_AUTHORING,
)
from .catalogo import RANGO_GRADO
from .design import OggettoAttivo
from .equip import CATALOGO_OGGETTI, Accessorio, Arma, PezzoArmatura
from .modificatori import Modificatore, TipoMod


def _modificatori_vivi(o) -> tuple[Modificatore, ...]:
    """Le voci a FASCIA dell'asset → `Modificatore` vivi: valore = fascia ×
    rango del grado (mai un numero nell'asset AI-facing)."""
    rango = RANGO_GRADO[Grado(o.grado)]
    return tuple(
        Modificatore(
            stat=StatId(stat), tipo=TipoMod.FLAT,
            valore=OGGETTO_MOD_FASCIA[fascia] * rango, fonte=o.slug,
        )
        for stat, fascia in _coppie_modificatori(o)
    )


def _coppie_modificatori(o) -> tuple[tuple[str, str], ...]:
    """Le coppie (stat, fascia) da un OggettoAsset (Pydantic) o un OggettoAttivo
    (dataclass appiattito): un solo lettore per le due forme."""
    prime = getattr(o, "modificatori", ())
    coppie = []
    for voce in prime:
        if isinstance(voce, tuple):
            coppie.append((voce[0], voce[1]))
        else:  # ModificatoreDati
            coppie.append((voce.stat.value, voce.fascia.value))
    return tuple(coppie)


def _valore_enum(campo, enum_cls):
    """str | Enum | None → Enum | None (le due forme di sorgente)."""
    if campo is None:
        return None
    return campo if isinstance(campo, enum_cls) else enum_cls(campo)


def oggetto_da_asset(o) -> PezzoArmatura | Arma | Accessorio:
    """Asset/attivo → oggetto vivo del canale equip. Duck-typed sulle due forme
    (`OggettoAsset` con enum, `OggettoAttivo` con stringhe): i numeri mancanti
    li mette il motore — mitigazione dalla categoria (via `mitigazione_di`),
    danno arma dal grado."""
    tipo = o.tipo
    nome = o.nome
    mods = _modificatori_vivi(o)
    if tipo == "armatura":
        return PezzoArmatura(
            fonte=o.slug,
            slot=_valore_enum(o.slot, SlotEquip),
            categoria=_valore_enum(o.categoria, CategoriaArmatura),
            nome=nome,
            taglia=_valore_enum(o.taglia, Taglia),
            mitigazione_cent=o.mitigazione_cent,
            modificatori=mods,
        )
    if tipo == "arma":
        danno = o.danno_base
        if danno is None:
            danno = DANNO_ARMA_PER_GRADO[Grado(o.grado).value]
        return Arma(
            fonte=o.slug,
            taglia=_valore_enum(o.taglia, Taglia),
            nome=nome,
            danno_base=danno,
            modificatori=mods,
        )
    return Accessorio(
        fonte=o.slug,
        sede=_valore_enum(o.sede, SedeAccessorio),
        nome=nome,
        modificatori=mods,
        mosse=tuple(o.mosse),
    )


def lint_oggetto(asset, *, mosse_ammesse=None) -> list[str]:
    """Il gate numerico dell'authoring oggetti (trasposizione di `lint_profilo`):
    la banda è DERIVATA dal catalogo §11 (`max(storici) × TETTO_AUTHORING`) —
    alzare la scala del gioco allarga la banda da sé, il refuso resta fuori.
    Le mosse concesse devono esistere (F-6): `mosse_ammesse=None` = il catalogo
    storico; il chiamante che conosce la libreria (mosse-asset) passa il suo set."""
    from .mosse import mosse_note

    errori: list[str] = []
    if asset.mitigazione_cent is not None:
        tetto = max(MITIGAZIONE_CENT.values()) * TETTO_AUTHORING
        if asset.mitigazione_cent > tetto:
            errori.append(
                f"oggetto {asset.slug}: mitigazione_cent={asset.mitigazione_cent} "
                f"fuori banda (tetto {tetto:g}, derivato da §11). I numeri li "
                "deriva il motore: se serve una scala più grande, si alza la "
                "calibrazione, non l'asset."
            )
    if asset.danno_base is not None:
        tetto = max(DANNO_ARMA_PER_GRADO.values()) * TETTO_AUTHORING
        if asset.danno_base > tetto:
            errori.append(
                f"oggetto {asset.slug}: danno_base={asset.danno_base} fuori "
                f"banda (tetto {tetto:g}, derivato da §11)."
            )
    note = mosse_note() if mosse_ammesse is None else mosse_ammesse
    fuori = [m for m in asset.mosse if m not in note]
    if fuori:
        errori.append(f"oggetto {asset.slug}: mosse fuori catalogo: {', '.join(fuori)}")
    return errori


@dataclass
class OggettiConiati:
    """Gli oggetti CONIATI in-run (drop generati dall'AI e GATED): dato del
    posseduto, PERSISTENTE — un cimelio nato in questa run non svanisce al
    load. Il catalogo corrente li somma (il gate del conio rifiuta gli slug
    esistenti: un conio non ombreggia mai la libreria)."""

    # L'annotazione PIENA è il contratto del translator di persistenza: senza,
    # al load le voci resterebbero dict grezzi.
    voci: list[OggettoAttivo] = field(default_factory=list)


def assicura_coniati(entita: int) -> OggettiConiati:
    comp = esper.try_component(entita, OggettiConiati)
    if comp is None:
        comp = OggettiConiati()
        esper.add_component(entita, comp)
    return comp


def _coniati_correnti():
    for _ent, coniati in esper.get_component(OggettiConiati):
        yield from coniati.voci


def attivo_da_asset(ogg) -> OggettoAttivo:
    """OggettoAsset (Pydantic, enum) → `OggettoAttivo` (congelato, jsonable)."""
    return OggettoAttivo(
        slug=ogg.slug, nome=ogg.nome, tipo=ogg.tipo,
        grado=ogg.grado.value, descrizione=ogg.descrizione,
        slot=ogg.slot.value if ogg.slot is not None else None,
        categoria=ogg.categoria.value if ogg.categoria is not None else None,
        taglia=ogg.taglia.value,
        sede=ogg.sede.value if ogg.sede is not None else None,
        mitigazione_cent=ogg.mitigazione_cent,
        danno_base=ogg.danno_base,
        modificatori=tuple((m.stat.value, m.fascia.value) for m in ogg.modificatori),
        mosse=tuple(ogg.mosse),
    )


def catalogo_oggetti_correnti() -> dict[str, object]:
    """Il catalogo oggetti DELLA RUN: lo storico (`CATALOGO_OGGETTI`, il
    fallback dimostrativo) più gli oggetti-asset congelati nella stagione —
    freeze batte catalogo, come per gli archetipi — più gli oggetti CONIATI
    in-run. Senza stagione (harness, save legacy): storici + coniati."""
    from .design import stagione_corrente

    catalogo = dict(CATALOGO_OGGETTI)
    stagione = stagione_corrente()
    if stagione is not None:
        for attivo in getattr(stagione, "oggetti", ()):
            catalogo[attivo.slug] = oggetto_da_asset(attivo)
    for attivo in _coniati_correnti():
        catalogo[attivo.slug] = oggetto_da_asset(attivo)
    return catalogo


def gate_conio(candidato, grado: str, *, mosse_ammesse=frozenset()):
    """Il gate del CONIO runtime: il motore ha fissato il GRADO (seeded, PRIMA
    della chiamata — risolvi prima, narra dopo) e il candidato non lo negozia;
    la conversione all'asset è il validator di forma; il lint tiene banda e
    mosse concesse dentro il catalogo DELLA RUN; lo slug dev'essere nuovo.
    Ritorna (OggettoAttivo | None, motivo)."""
    from contracts import ModificatoreDati, OggettoAsset

    if candidato.grado.value != grado:
        return None, f"grado alterato ({candidato.grado.value} ≠ {grado})"
    if candidato.slug in catalogo_oggetti_correnti():
        return None, f"slug già esistente: {candidato.slug}"
    try:
        asset = OggettoAsset(
            slug=candidato.slug, versione=1, tags=["coniato"],
            nome=candidato.nome, descrizione=candidato.descrizione,
            tipo=candidato.tipo, grado=candidato.grado, slot=candidato.slot,
            categoria=candidato.categoria, taglia=candidato.taglia,
            sede=candidato.sede, mosse=list(candidato.mosse),
            modificatori=[
                ModificatoreDati(stat=m.stat, fascia=m.fascia)
                for m in candidato.modificatori
            ],
        )
    except ValueError as errore:
        return None, str(errore)
    errori = lint_oggetto(asset, mosse_ammesse=mosse_ammesse)
    if errori:
        return None, "; ".join(errori)
    return attivo_da_asset(asset), None


def gate_premio(candidato, fonte: str, grado: str) -> str | None:
    """Anti-arbitraggio della vestizione (contratto premi): il candidato non
    cambia la base, non altera il grado, non sposta lo slot. `None` = passa;
    altrimenti il MOTIVO — e il chiamante degrada al nome di catalogo (il
    deposito è già avvenuto e non dipende MAI da questa chiamata)."""
    if candidato.base != fonte:
        return f"base cambiata ({candidato.base!r} ≠ {fonte!r})"
    if candidato.grado.value != grado:
        return f"grado alterato ({candidato.grado.value} ≠ {grado})"
    oggetto = catalogo_oggetti_correnti().get(fonte)
    if oggetto is None:
        return "base non nel catalogo della run"
    slot_base = getattr(oggetto, "slot", None)
    if candidato.slot is not None and candidato.slot is not slot_base:
        return "slot spostato (l'AI non sposta un elmo ai piedi)"
    return None


def grado_oggetto(fonte: str) -> str:
    """Il grado (valore stringa) dell'oggetto congelato o coniato con quella
    fonte; gli storici senza grado valgono BRONZO."""
    from .design import stagione_corrente

    stagione = stagione_corrente()
    if stagione is not None:
        for attivo in getattr(stagione, "oggetti", ()):
            if attivo.slug == fonte:
                return attivo.grado
    for attivo in _coniati_correnti():
        if attivo.slug == fonte:
            return attivo.grado
    return Grado.BRONZO.value
