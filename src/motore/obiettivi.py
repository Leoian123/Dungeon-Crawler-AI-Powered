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
    # I fatti da IMPRESA (titoli mid-run):
    custode: bool | None = None
    senza_graffi: bool | None = None
    grado_nemico_minimo: str = ""   # "" = nessun vincolo di rango
    soglia: int = 0                 # 0 = immediata; N = alla N-esima occorrenza
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
    # I CONTATORI delle serie (titoli a soglia): occorrenze delle condizioni
    # per slug — persistenti, si azzerano allo sblocco (il ripetibile riparte).
    conteggi: dict[str, int] = field(default_factory=dict)


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
        custode=asset.trigger.custode,
        senza_graffi=asset.trigger.senza_graffi,
        grado_nemico_minimo=(
            asset.trigger.grado_nemico_minimo.value
            if asset.trigger.grado_nemico_minimo is not None else ""
        ),
        soglia=asset.trigger.soglia or 0,
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

_CONDIZIONI = ("vittoria", "fuga", "interrotto", "tier", "custode", "senza_graffi")


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
            # La SERIE (titoli a soglia): l'impresa vale alla N-esima
            # occorrenza; il contatore persiste col save e si azzera allo
            # sblocco (il ripetibile riparte da zero: ogni multiplo suona).
            if obiettivo.soglia > 1:
                conte = comp.conteggi.get(obiettivo.slug, 0) + 1
                comp.conteggi[obiettivo.slug] = conte
                if conte < obiettivo.soglia:
                    continue
                comp.conteggi[obiettivo.slug] = 0
            self._sblocca(comp, obiettivo)

    @staticmethod
    def _condizioni_vere(obiettivo: ObiettivoAttivo, evento: object) -> bool:
        sentinella = object()
        for nome in _CONDIZIONI:
            atteso = getattr(obiettivo, nome)
            if atteso is None:
                continue
            # Il fatto deve ESISTERE sull'evento ed essere uguale: una
            # condizione su un campo che l'evento non trasporta è falsa.
            reale = getattr(evento, nome, sentinella)
            if reale is sentinella or reale != atteso:
                return False
        if obiettivo.grado_nemico_minimo:
            # Rango ≥ soglia (la mappa Grado→rango è del motore, mai dell'AI):
            # un evento senza grado ("" = scalari) non è mai un'impresa di rango.
            from contracts import Grado

            from .catalogo import RANGO_GRADO

            reale = getattr(evento, "grado_nemico", sentinella)
            if reale is sentinella or not reale:
                return False
            try:
                rango = RANGO_GRADO[Grado(reale)]
            except (KeyError, ValueError):
                return False
            if rango < RANGO_GRADO[Grado(obiettivo.grado_nemico_minimo)]:
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


# --- Le viste per gli host (fase O4) --------------------------------------------

def elenco_vista() -> tuple:
    """L'elenco obiettivi per l'host (`ObiettivoVista`): il catalogo della
    run con lo stato di sblocco. VELATO finché chiuso — titolo visibile,
    testo e ricompensa arrivano solo a sblocco avvenuto: lo spoiler è metà
    del premio."""
    from contracts import ObiettivoVista

    comp = obiettivi_correnti()
    if comp is None:
        return ()
    return tuple(
        ObiettivoVista(
            slug=o.slug,
            titolo=o.titolo,
            testo=o.testo if o.slug in comp.sbloccati else "",
            sbloccato=o.slug in comp.sbloccati,
            ricompensa_testo=(
                _ricompensa_testo(o) if o.slug in comp.sbloccati else ""
            ),
        )
        for o in comp.catalogo
    )


def drena_non_letti() -> tuple:
    """Le notifiche ARRETRATE (decisione §O-5): gli sblocchi non ancora
    mostrati, come `ObiettivoRaggiunto` già composti — l'host li scrive come
    se fossero appena accaduti, poi la coda è vuota. Il live passa dalla
    cronaca: l'host drena in silenzio dopo ogni turno, e a un load trova qui
    solo ciò che nessuna superficie ha mai mostrato."""
    comp = obiettivi_correnti()
    if comp is None or not comp.non_letti:
        return ()
    per_slug = {o.slug: o for o in comp.catalogo}
    notifiche = []
    for slug in comp.non_letti:
        obiettivo = per_slug.get(slug)
        if obiettivo is None:
            continue  # catalogo driftato: la notifica orfana decade
        notifiche.append(ObiettivoRaggiunto(
            slug=obiettivo.slug,
            titolo=obiettivo.titolo,
            testo=obiettivo.testo,
            ricompensa_testo=_ricompensa_testo(obiettivo),
        ))
    comp.non_letti.clear()
    return tuple(notifiche)


# --- L'apertura delle box (fase O2): solo nei luoghi quieti ---------------------

# Categoria della box → tipi di BASE della fabbrica che può estrarre.
# `None` = qualunque base (la box generalista). Una categoria si dichiara solo
# se la fabbrica può onorarla: il vincolo che azzera i candidati è un errore
# di catalogo e l'apertura degrada a no-op, mai a crash.
_TIPI_PER_CATEGORIA: dict[str, tuple[str, ...] | None] = {
    "armi": ("arma",),
    "indumenti": ("armatura",),
    "accessori": ("accessorio",),
    "avventuriero": None,
}


def prossima_box() -> BoxChiusa | None:
    """La prossima box in coda (FIFO: la prima guadagnata è la prima aperta).
    Sola lettura: comporre il menu non consuma niente."""
    comp = obiettivi_correnti()
    if comp is None or not comp.box:
        return None
    return comp.box[0]


def apri_prossima_box(bus) -> object | None:
    """Apre la prossima box: conio della fabbrica VINCOLATO alla categoria,
    su stream RNG ISOLATO `master_seed:box:{id}` — replay-safe, lo stream di
    sessione non si muove; stessa box = stesso oggetto, sempre.

    GATE STRUTTURALE: SOLO in SAFE ROOM (ratifica 2026-08-26: il bagno è
    privacy, non servizi — la safe room è il rifugio attrezzato). La
    composizione del menu è la prima guardia, questa è la cintura — un host
    che chiama fuori posto riceve `None`, mai un oggetto. La box esce dalla
    coda SOLO a conio riuscito. Deposito: coniati persistenti + zaino; il
    fatto va in cronaca (`BoxAperta`)."""
    import random

    from contracts import BoxAperta, TipoStanza

    from .equip import assicura_zaino
    from .fabbrica import conia_procedurale
    from .mappa import tipo_stanza_corrente
    from .oggetti import assicura_coniati
    from .scheda import protagonista
    from .seme import master_seed

    comp = obiettivi_correnti()
    if comp is None or not comp.box:
        return None
    if tipo_stanza_corrente() is not TipoStanza.SAFE_ROOM:
        return None
    box = comp.box[0]
    rng = random.Random(f"{master_seed()}:box:{box.id}")
    attivo = conia_procedurale(
        rng, box.grado, tipi_base=_TIPI_PER_CATEGORIA.get(box.categoria),
    )
    if attivo is None:
        return None  # fabbrica assente o categoria non onorabile: la box resta
    comp.box.pop(0)
    pent, _marker, _scheda = protagonista()
    assicura_coniati(pent).voci.append(attivo)
    assicura_zaino(pent).fonti.append(attivo.slug)
    bus.pubblica(BoxAperta(
        categoria=box.categoria, grado=box.grado,
        nome=attivo.nome, fonte=attivo.slug,
    ))
    return attivo
