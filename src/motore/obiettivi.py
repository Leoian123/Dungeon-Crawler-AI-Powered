"""OBIETTIVI E BOX — l'osservatore del motore (nodo O, fase O1).

Il dungeon ti guarda e commenta: gli obiettivi ascoltano il BUS TIPIZZATO
(fatti già arbitrati — mai l'LLM, mai la prosa) e sbloccano notifiche di
sistema deterministiche, con la ricompensa nel dato: una BOX (conio
ritardato della fabbrica, si aprirà nei luoghi quieti — fase O2) o una
BEFFA dichiarata.

Disegno:
- il CATALOGO è congelato nella run alla nascita (`monta_obiettivi`, stesso
  confine della stagione e dei fantasmi): l'authoring successivo non tocca
  le run in corso;
- UN componente persistente (`ObiettiviRun`, tag H-3) possiede tutto:
  catalogo, sbloccati, notifiche non lette, box chiuse — un solo
  proprietario dell'avanzamento;
- lo sblocco è IDEMPOTENTE per i non-ripetibili (il registro `sbloccati` è
  la guardia) e la valutazione legge SOLO i campi che l'evento trasporta;
- le box NON entrano nello Zaino (quello è il canale dell'equipaggiabile):
  sono possesso proprio del componente, con id deterministico — sarà lo
  stream del conio d'apertura (O2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import esper

from contracts import (
    AchievementAsset,
    CombatResolved,
    DiscesaPiano,
    EventoTrigger,
    MortePersonaggio,
    ObiettivoRaggiunto,
    OggettoTrovato,
    RiposoConcluso,
    TransizioneZona,
)


@dataclass
class ObiettivoAttivo:
    """Il dato-obiettivo dentro la run (traduzione PIATTA dell'asset: il
    translator di persistenza resta generico, niente annidamenti profondi)."""

    slug: str
    titolo: str
    testo: str
    evento: str                     # EventoTrigger.value
    vittoria: bool | None = None
    fuga: bool | None = None
    interrotto: bool | None = None
    tier: str | None = None
    box_categoria: str = ""         # "" = niente box
    box_grado: str = ""
    beffa: str = ""
    ripetibile: bool = False


@dataclass
class BoxChiusa:
    """Una box non ancora aperta: possesso persistente. `id` è deterministico
    (obiettivo + progressivo): sarà la chiave dello stream di conio (O2)."""

    id: str
    categoria: str
    grado: str


@dataclass
class ObiettiviRun:
    """Singleton di run: catalogo congelato + stato (tag `obiettivi`)."""

    catalogo: list[ObiettivoAttivo] = field(default_factory=list)
    sbloccati: list[str] = field(default_factory=list)
    non_letti: list[str] = field(default_factory=list)
    box: list[BoxChiusa] = field(default_factory=list)


def _attivo_da_asset(asset: AchievementAsset) -> ObiettivoAttivo:
    box = asset.ricompensa.box
    return ObiettivoAttivo(
        slug=asset.slug,
        titolo=asset.titolo,
        testo=asset.testo,
        evento=asset.trigger.evento.value,
        vittoria=asset.trigger.vittoria,
        fuga=asset.trigger.fuga,
        interrotto=asset.trigger.interrotto,
        tier=asset.trigger.tier,
        box_categoria=box.categoria.value if box is not None else "",
        box_grado=box.grado.value if box is not None else "",
        beffa=asset.ricompensa.beffa,
        ripetibile=asset.ripetibile,
    )


def monta_obiettivi(assets: Sequence[AchievementAsset]) -> int | None:
    """Congela il catalogo nel World corrente (confine guscio→run, come la
    stagione e i fantasmi). No-op a catalogo vuoto: zero footprint."""
    if not assets:
        return None
    return esper.create_entity(ObiettiviRun(
        catalogo=[_attivo_da_asset(a) for a in assets]
    ))


def obiettivi_correnti() -> ObiettiviRun | None:
    trovati = esper.get_component(ObiettiviRun)
    return trovati[0][1] if trovati else None


def _ricompensa_testo(obiettivo: ObiettivoAttivo) -> str:
    """La riga-ricompensa, composta QUI (deterministica): l'host la mostra,
    mai la ricostruisce."""
    if obiettivo.box_categoria:
        return (
            f"Hai ricevuto una Box {obiettivo.box_categoria.capitalize()} "
            f"di {obiettivo.box_grado.capitalize()}."
        )
    return obiettivo.beffa


# Il binding trigger→evento di bus: l'aggiunta di un trigger è una riga qui.
# Per ogni evento, i FATTI che trasporta (solo quelli: una condizione su un
# campo assente non può mai essere vera — per costruzione).
_BINDING: dict[str, type] = {
    EventoTrigger.COMBAT_RISOLTO.value: CombatResolved,
    EventoTrigger.MORTE.value: MortePersonaggio,
    EventoTrigger.DISCESA.value: DiscesaPiano,
    EventoTrigger.ZONA_ATTRAVERSATA.value: TransizioneZona,
    EventoTrigger.OGGETTO_TROVATO.value: OggettoTrovato,
    EventoTrigger.RIPOSO_CONCLUSO.value: RiposoConcluso,
}

_CONDIZIONI = ("vittoria", "fuga", "interrotto", "tier")


class OsservatoreObiettivi:
    """L'ascoltatore del bus: valuta il catalogo della run CORRENTE a ogni
    fatto. Vive quanto il bus della sessione (per-guscio): la registrazione
    è nel costruttore, `chiudi()` la disfa (igiene fra scontri e test)."""

    def __init__(self, bus) -> None:
        self._bus = bus
        self._coppie: list[tuple[type, object]] = []
        for nome_trigger, tipo_evento in _BINDING.items():
            handler = self._fai_handler(nome_trigger)
            bus.registra(tipo_evento, handler)
            self._coppie.append((tipo_evento, handler))

    def _fai_handler(self, nome_trigger: str):
        def handler(evento: object) -> None:
            self._valuta(nome_trigger, evento)
        return handler

    def _valuta(self, nome_trigger: str, evento: object) -> None:
        comp = obiettivi_correnti()
        if comp is None:
            return
        for obiettivo in comp.catalogo:
            if obiettivo.evento != nome_trigger:
                continue
            if obiettivo.slug in comp.sbloccati and not obiettivo.ripetibile:
                continue
            if not self._condizioni_vere(obiettivo, evento):
                continue
            self._sblocca(comp, obiettivo)

    @staticmethod
    def _condizioni_vere(obiettivo: ObiettivoAttivo, evento: object) -> bool:
        for nome in _CONDIZIONI:
            atteso = getattr(obiettivo, nome)
            if atteso is None:
                continue
            # Il fatto deve ESISTERE sull'evento ed essere uguale: una
            # condizione su un campo che l'evento non trasporta è falsa.
            sentinella = object()
            reale = getattr(evento, nome, sentinella)
            if reale is sentinella or reale != atteso:
                return False
        return True

    def _sblocca(self, comp: ObiettiviRun, obiettivo: ObiettivoAttivo) -> None:
        if obiettivo.slug not in comp.sbloccati:
            comp.sbloccati.append(obiettivo.slug)
        comp.non_letti.append(obiettivo.slug)
        if obiettivo.box_categoria:
            comp.box.append(BoxChiusa(
                id=f"{obiettivo.slug}#{len(comp.box)}",
                categoria=obiettivo.box_categoria,
                grado=obiettivo.box_grado,
            ))
        self._bus.pubblica(ObiettivoRaggiunto(
            slug=obiettivo.slug,
            titolo=obiettivo.titolo,
            testo=obiettivo.testo,
            ricompensa_testo=_ricompensa_testo(obiettivo),
        ))

    def chiudi(self) -> None:
        for tipo, handler in self._coppie:
            self._bus.deregistra(tipo, handler)
        self._coppie = []


def attiva_osservatore(bus) -> OsservatoreObiettivi:
    return OsservatoreObiettivi(bus)
