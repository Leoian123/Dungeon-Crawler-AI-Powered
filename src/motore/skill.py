"""SKILL — lo strato di COMPETENZA (nodo S, ratifica 2026-08-27).

Una skill è una COMPETENZA con un livello che CONTA: «Calpestare 15 fa la
differenza con Calpestare 10». Il livello è una DERIVATA deterministica
(mai XP depositata: soglie triangolari §11 sugli usi contati dal bus
tipizzato — il sistema conta tutto, che è il nostro determinismo), ma la
sua MAGNITUDINE è dichiarata per-skill: `effetto` (vocabolario chiuso
`EffettoCompetenza`) × `intensita` (Fascia) × foglie §11 `COMPETENZA.*`.

Questo modulo è il SUBSTRATO su cui gireranno i sistemi complessi: magia,
artigianato, sopravvivenza, combattimento avanzato leggeranno la SUPERFICIE
(`livello_competenza`, `livello_dominio`, `bonus_competenza`) come gate e
come scala — mai un numero loro, mai un secondo motore.

Disegno (gli stessi confini del nodo O):
- il CATALOGO è congelato nella run alla nascita (`monta_skill`);
- UN componente persistente (`SkillDelCrawler`, tag H-3) possiede catalogo e
  conteggi — un solo proprietario dell'avanzamento;
- ogni effetto ha UN consumatore nel suo punto unico (check 2, margine di
  fuga, resa del riposo, dado-agguati); a livello 1 tutto vale identità:
  lo storico non si muove di un byte;
- la skill di puro TONO resta legittima (dominio mondano, effetto assente):
  metà del canone è «Respirare, livello 3».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import esper

from contracts import (
    CombatResolved,
    ColpoInferto,
    PraticaSkill,
    RiposoConcluso,
    SkillAsset,
    SkillMigliorata,
    TransizioneZona,
)


@dataclass
class SkillRegistrata:
    """La COMPETENZA dentro la run (traduzione PIATTA dell'asset, come
    `ObiettivoAttivo`: il translator di persistenza resta generico).
    `effetto`/`intensita` sono la magnitudine dichiarata: cosa muove il
    livello, e quanto per gradino (le foglie §11 `COMPETENZA.*`)."""

    slug: str
    nome: str
    testo: str
    tipo: str                # attiva | passiva
    pratica: str             # PraticaSkill.value
    mossa: str = ""          # solo pratica MOSSA
    dominio: str = "mondana"  # la mappa dei sistemi (DominioSkill.value)
    effetto: str = ""        # EffettoCompetenza.value ("" = tono)
    intensita: str = "lieve"  # Fascia.value
    livello_iniziale: int = 1


@dataclass
class SkillDelCrawler:
    """Singleton di run: catalogo congelato + conteggi (tag `skill`)."""

    catalogo: list[SkillRegistrata] = field(default_factory=list)
    usi: dict[str, int] = field(default_factory=dict)


def _registrata_da_asset(asset: SkillAsset) -> SkillRegistrata:
    return SkillRegistrata(
        slug=asset.slug,
        nome=asset.nome,
        testo=asset.testo,
        tipo=asset.tipo,
        pratica=asset.pratica.value,
        mossa=asset.mossa,
        dominio=asset.dominio.value,
        effetto=asset.effetto.value if asset.effetto is not None else "",
        intensita=asset.intensita.value,
        livello_iniziale=asset.livello_iniziale,
    )


def monta_skill(assets: Sequence[SkillAsset]) -> int | None:
    """Congela il catalogo skill nel World corrente (confine guscio→run).
    No-op a catalogo vuoto: zero footprint (harness e misure non contano)."""
    if not assets:
        return None
    return esper.create_entity(SkillDelCrawler(
        catalogo=[_registrata_da_asset(a) for a in assets]
    ))


def skill_correnti() -> SkillDelCrawler | None:
    trovati = esper.get_component(SkillDelCrawler)
    return trovati[0][1] if trovati else None


# --- Il livello: derivata del conteggio (mai depositato) ------------------------

def livello_da_usi(usi: int, livello_iniziale: int = 1) -> int:
    """Il livello che QUEL conteggio vale: salire al livello n costa
    `SKILL.usi_livello_base·(n−1)` usi (cumulativa triangolare — la
    «crescita lineare lenta» del canone), col cap §11. La dotazione iniziale
    è un pavimento: il junk di partenza resta alto e cresce solo praticando."""
    from .calibrazione import SKILL_LIVELLO_CAP, SKILL_USI_LIVELLO_BASE

    base = max(1, int(SKILL_USI_LIVELLO_BASE))
    cap = max(1, int(SKILL_LIVELLO_CAP))
    livello = 1
    while livello < cap and usi >= base * livello * (livello + 1) // 2:
        livello += 1
    return min(cap, max(livello, max(1, livello_iniziale)))


def _bonus_indosso(slug: str) -> int:
    """Il canale GearTome (S7): i pezzi INDOSSATI che portano QUESTA skill in
    sé sommano i loro livelli — «la stessa skill a +1 o +5». Derivato alla
    lettura dal manifest (mai depositato): togli il pezzo, il livello torna
    suo — la stessa disciplina dei modificatori. Lettura tollerante: harness
    senza protagonista/equip → 0."""
    try:
        from .equip import equip_attivo
        from .scheda import protagonista

        comp = equip_attivo(protagonista()[0])
        if comp is None:
            return 0
        pezzi = (
            *comp.armatura.values(),
            *((comp.arma,) if comp.arma is not None else ()),
            *comp.accessori,
        )
        return sum(
            int(getattr(p, "skill_livelli", 0))
            for p in pezzi if getattr(p, "skill", "") == slug
        )
    except Exception:
        return 0


def _livello_di(comp: SkillDelCrawler, skill: SkillRegistrata) -> int:
    """Il livello EFFETTIVO: la derivata degli usi (col pavimento della
    dotazione e il cap §11) più il bonus del gear indosso — che può spingere
    OLTRE il cap: è la build («+1 o +5»), dichiarata."""
    base = livello_da_usi(comp.usi.get(skill.slug, 0), skill.livello_iniziale)
    return base + _bonus_indosso(skill.slug)


# --- L'osservatore: conta i fatti, pubblica i gradini ---------------------------

class OsservatoreSkill:
    """L'ascoltatore del bus: a ogni fatto incrementa le pratiche che
    combaciano; se il livello derivato passa un gradino, pubblica
    `SkillMigliorata`. Vive quanto il bus della sessione; `chiudi()` disfa
    (igiene fra run e test — pattern OsservatoreObiettivi)."""

    def __init__(self, bus) -> None:
        self._bus = bus
        self._coppie: list[tuple[type, object]] = []
        for tipo, handler in (
            (ColpoInferto, self._su_colpo),
            (CombatResolved, self._su_risolto),
            (RiposoConcluso, self._su_riposo),
            (TransizioneZona, self._su_zona),
        ):
            bus.registra(tipo, handler)
            self._coppie.append((tipo, handler))

    # I fatti: solo il PROTAGONISTA pratica ("" è la sua firma negli eventi).
    def _su_colpo(self, e: ColpoInferto) -> None:
        if getattr(e, "attaccante", None) != "":
            return
        mossa = getattr(e, "mossa", "") or "attacco"
        self._pratica(PraticaSkill.MOSSA.value, mossa=mossa)

    def _su_risolto(self, e: CombatResolved) -> None:
        if getattr(e, "fuga", False):
            self._pratica(PraticaSkill.FUGA.value)

    def _su_riposo(self, e: RiposoConcluso) -> None:
        if not getattr(e, "interrotto", False):
            self._pratica(PraticaSkill.RIPOSO.value)

    def _su_zona(self, _e: TransizioneZona) -> None:
        self._pratica(PraticaSkill.ZONA.value)

    def _pratica(self, pratica: str, *, mossa: str = "") -> None:
        comp = skill_correnti()
        if comp is None:
            return
        for skill in comp.catalogo:
            if skill.pratica != pratica:
                continue
            if pratica == PraticaSkill.MOSSA.value and skill.mossa != mossa:
                continue
            prima = _livello_di(comp, skill)
            comp.usi[skill.slug] = comp.usi.get(skill.slug, 0) + 1
            dopo = _livello_di(comp, skill)
            if dopo > prima:
                self._bus.pubblica(SkillMigliorata(
                    slug=skill.slug, nome=skill.nome, livello=dopo,
                ))

    def chiudi(self) -> None:
        for tipo, handler in self._coppie:
            self._bus.deregistra(tipo, handler)
        self._coppie = []


def attiva_osservatore_skill(bus) -> OsservatoreSkill:
    return OsservatoreSkill(bus)


# --- LA SUPERFICIE (S5): il substrato che i sistemi interrogano -----------------
#
# Questa è l'API su cui gireranno i sistemi complessi (ratifica 2026-08-27):
# la magia e l'artigianato, quando arriveranno, leggeranno `livello_dominio`
# come gate e `bonus_competenza` come scala — mai un numero loro.

def _rate(skill: SkillRegistrata) -> float:
    from .calibrazione import COMPETENZA_RATE

    return float(COMPETENZA_RATE.get(skill.effetto, {}).get(skill.intensita, 0.0))


def bonus_competenza(effetto: str, *, mossa: str = "") -> float:
    """Il valore VIVO che un effetto di competenza vale adesso: la somma, su
    ogni skill del registro con quell'`effetto` (e quella mossa, per
    `potenza_mossa`), di `(livello − 1) × fascia §11`. A livello 1 vale 0 —
    lo storico non si muove. Lettura tollerante: senza registro → 0."""
    try:
        comp = skill_correnti()
        if comp is None:
            return 0.0
        totale = 0.0
        for skill in comp.catalogo:
            if skill.effetto != effetto:
                continue
            if effetto == "potenza_mossa" and skill.mossa != mossa:
                continue
            livello = _livello_di(comp, skill)
            if livello > 1:
                totale += _rate(skill) * (livello - 1)
        return totale
    except Exception:
        return 0.0


def livello_competenza(slug: str) -> int:
    """Il livello effettivo di UNA competenza (0 = non nel registro)."""
    comp = skill_correnti()
    if comp is None:
        return 0
    for skill in comp.catalogo:
        if skill.slug == slug:
            return _livello_di(comp, skill)
    return 0


def livello_dominio(dominio: str) -> int:
    """La competenza di un DOMINIO: il livello della sua skill migliore
    (0 = dominio mai praticato). È il GATE dei sistemi consumatori futuri:
    «ricetta d'artigianato ≥ 5», «cerchio di magia ≤ livello del dominio»."""
    comp = skill_correnti()
    if comp is None:
        return 0
    livelli = [
        _livello_di(comp, s) for s in comp.catalogo if s.dominio == dominio
    ]
    return max(livelli, default=0)


def competenze_notevoli() -> tuple[tuple[str, int], ...]:
    """Le competenze da FASCICOLO (nodo S8): livello ≥ soglia §11, domini
    non mondani — il master narra un crawler che È le sue competenze."""
    from .calibrazione import SKILL_FASCICOLO_SOGLIA

    comp = skill_correnti()
    if comp is None:
        return ()
    notevoli = []
    for skill in comp.catalogo:
        if skill.dominio == "mondana":
            continue
        livello = _livello_di(comp, skill)
        if livello >= int(SKILL_FASCICOLO_SOGLIA):
            notevoli.append((skill.nome, livello))
    return tuple(sorted(notevoli, key=lambda n: (-n[1], n[0])))


# --- I CONSUMATORI (S6): ogni effetto morde nel suo punto unico -----------------

def fattore_skill(entita: int, chiave_mossa: str) -> float:
    """`potenza_mossa`: il moltiplicatore della mossa GOVERNATA, dentro
    l'unico arrotondamento del check 2. Vale SOLO per il protagonista (il
    registro è suo); mob, mosse non governate e livello 1 → 1.0,
    byte-identico allo storico."""
    try:
        from .scheda import Protagonista

        if esper.try_component(entita, Protagonista) is None:
            return 1.0
        return 1.0 + bonus_competenza("potenza_mossa", mossa=chiave_mossa)
    except Exception:
        return 1.0


def bonus_margine_fuga() -> int:
    """`margine_fuga`: punti INTERI in più sul margine delle tre corsie del
    disimpegno (il pavimento intero tiene la scala della prova)."""
    return int(bonus_competenza("margine_fuga"))


def bonus_resa_riposo() -> int:
    """`resa_riposo`: HP per tick di riposo in più (pavimento intero)."""
    return int(bonus_competenza("resa_riposo"))


def fattore_esca_agguati() -> float:
    """`esca_agguati`: il moltiplicatore (≤1) sul dado-imboscata del
    downtime — chi conosce i passi del piano rischia meno agguati. Pavimento
    0.5: la competenza attenua, non spegne (il dungeon resta il dungeon)."""
    return max(0.5, 1.0 - bonus_competenza("esca_agguati"))


# --- La vista per gli host ------------------------------------------------------

def skill_vista() -> tuple:
    """L'elenco skill per l'host (`SkillRigaVista`): nome, tipo, livello
    derivato, usi. Nessun velo: il menu del canone elenca tutto — vedere
    «Respirare, livello 3» è metà del tono."""
    from contracts import SkillRigaVista

    comp = skill_correnti()
    if comp is None:
        return ()
    return tuple(
        SkillRigaVista(
            slug=s.slug,
            nome=s.nome,
            tipo=s.tipo,
            livello=_livello_di(comp, s),
            usi=comp.usi.get(s.slug, 0),
            testo=s.testo,
            mossa=s.mossa,
            dominio=s.dominio,
            effetto=s.effetto,
        )
        for s in comp.catalogo
    )
