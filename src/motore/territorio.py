"""Il TERRITORIO della run: spina campionata, zone, stato d'attraversamento.

Un piano-mondo (miliardi di abitanti, 150k ingressi: lore) non si materializza
mai per intero: la run ne attraversa una TRAIETTORIA campionata dal seed — la
"spina": quartiere → distretto → città → provincia → paese → la tana del boss
di piano. Ogni zona è una mini-mappa (la `Mappa` di sempre, riusata identica)
col suo boss a custodire il passaggio; la scala del piano esiste SOLO nella
tana. Le zone laterali (Fase 6) sono sorelle della spina, generate on-demand.

Discipline:
  - la spina è una DERIVAZIONE PURA del seed (`master_seed:piano:L:spina`), mai
    persistita: al load si ricomputa identica — si persiste solo lo
    `StatoTerritorio` (dove sei, quali boss hai battuto, cosa hai visitato);
  - un solo proprietario dell'avanzamento zona (qui; la `Mappa` resta l'autorità
    DENTRO la zona);
  - senza territorio nel design (piani piatti storici, save legacy): tutto
    questo modulo è inerte e il comportamento è quello di ieri.

Clausola del NASCONDINO (Fase 4/GL-2): nella tana la stanza del boss è la
penultima e la generazione GARANTISCE un cammino partenza→scala che la evita —
il boss di piano si può aggirare; combatterlo è una scelta, non un pedaggio.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import esper

from contracts import Durata, PlayerAttraversa, TierTerritorio, TransizioneZona

from .design import MobAttivo, TerritorioAttivo, design_piano_corrente
from .intenti_coda import consuma_messaggi
from .mappa import Mappa, genera_topologia, mappa_corrente, mob_corrente
from .mob import EntitaMob
from .phased import SistemaSoloNarrazione
from .piano import Piano
from .scheda import Protagonista
from .seme import master_seed

# L'ordine di ATTRAVERSAMENTO della spina: dal basso alla tana.
ORDINE_SPINA: tuple[TierTerritorio, ...] = (
    TierTerritorio.QUARTIERE,
    TierTerritorio.DISTRETTO,
    TierTerritorio.CITTA,
    TierTerritorio.PROVINCIA,
    TierTerritorio.PAESE,
    TierTerritorio.PIANO,
)

# I livelli d'indirizzo, dall'alto: il percorso di una zona è il prefisso di
# questi indici (paese, provincia, città, distretto, quartiere); la tana è ().
_LIVELLI_INDIRIZZO: tuple[TierTerritorio, ...] = (
    TierTerritorio.PAESE,
    TierTerritorio.PROVINCIA,
    TierTerritorio.CITTA,
    TierTerritorio.DISTRETTO,
    TierTerritorio.QUARTIERE,
)


@dataclass(frozen=True)
class Zona:
    """UNA zona del territorio: il tier + l'indirizzo nella gerarchia.

    `percorso` = indici dall'alto (paese, provincia, città, distretto,
    quartiere) troncati al livello del tier; la tana (tier PIANO) è `()`.
    `chiave` è l'identità STABILE (save, firma d'Archivio, seed di zona)."""

    tier: TierTerritorio
    percorso: tuple[int, ...] = ()

    @property
    def chiave(self) -> str:
        indirizzo = "/".join(str(i) for i in self.percorso)
        return f"{self.tier.value}:{indirizzo}"


def zona_da_chiave(chiave: str) -> Zona:
    """La `Zona` dalla sua chiave (inverso esatto di `.chiave`)."""
    tier_val, _, indirizzo = chiave.partition(":")
    percorso = tuple(int(x) for x in indirizzo.split("/") if x != "")
    return Zona(tier=TierTerritorio(tier_val), percorso=percorso)


@dataclass
class StatoTerritorio:
    """Componente-singleton PERSISTENTE: dove sei nel territorio e cosa è fatto.

    La spina NON è qui (si rideriva dal seed): qui c'è solo ciò che il seed non
    può ricomputare — la posizione e la storia (boss battuti, zone viste).
    I campi sono liste ordinate (jsonable, diff dei save leggibili): le API di
    questo modulo le trattano da insiemi."""

    zona_corrente: str
    boss_sconfitti: list[str] = field(default_factory=list)
    zone_visitate: list[str] = field(default_factory=list)


def stato_territorio() -> StatoTerritorio | None:
    trovati = esper.get_component(StatoTerritorio)
    return trovati[0][1] if trovati else None


def territorio_attivo() -> TerritorioAttivo | None:
    """Il territorio del piano corrente (None = piano piatto/legacy: modulo inerte)."""
    piano = design_piano_corrente()
    return piano.territorio if piano is not None else None


def _conta(territorio: TerritorioAttivo, tier: TierTerritorio) -> int:
    return max(1, int(territorio.conteggi.get(tier.value, 1)))


def spina_del_piano(livello: int) -> tuple[Zona, ...]:
    """Le 6 zone della spina, campionate SEEDED sui conteggi del territorio.

    Derivata pura: stesso seed e stesso livello → stessa spina, a ogni chiamata
    e dopo ogni load (mai persistita). `()` senza territorio."""
    territorio = territorio_attivo()
    if territorio is None:
        return ()
    rng = random.Random(f"{master_seed()}:piano:{livello}:spina")
    indirizzo = tuple(
        rng.randrange(_conta(territorio, tier)) for tier in _LIVELLI_INDIRIZZO
    )
    zone: list[Zona] = []
    for tier in ORDINE_SPINA:
        if tier is TierTerritorio.PIANO:
            zone.append(Zona(tier=tier, percorso=()))
        else:
            profondita = _LIVELLI_INDIRIZZO.index(tier) + 1
            zone.append(Zona(tier=tier, percorso=indirizzo[:profondita]))
    return tuple(zone)


def zona_corrente() -> Zona | None:
    stato = stato_territorio()
    return zona_da_chiave(stato.zona_corrente) if stato is not None else None


def zona_successiva(livello: int) -> Zona | None:
    """La prossima zona della SPINA dopo quella corrente (None = sei alla tana).

    Una zona LATERALE è un vicolo (Fase 6): non ha un "avanti" — da lì si torna
    alla zona di spina da cui si è deviati (`zona_di_spina_del_tier`)."""
    corrente = zona_corrente()
    if corrente is None:
        return None
    spina = spina_del_piano(livello)
    for i, zona in enumerate(spina):
        if zona.chiave == corrente.chiave:
            return spina[i + 1] if i + 1 < len(spina) else None
    return None  # laterale: vicolo, nessun avanti


def e_di_spina(zona: Zona, livello: int) -> bool:
    return any(z.chiave == zona.chiave for z in spina_del_piano(livello))


def zona_di_spina_del_tier(tier: TierTerritorio, livello: int) -> Zona | None:
    """La zona di SPINA di quel tier (il punto di rientro dalle laterali)."""
    for zona in spina_del_piano(livello):
        if zona.tier is tier:
            return zona
    return None


def zone_laterali(livello: int) -> tuple[Zona, ...]:
    """Le 0-2 SORELLE della zona di spina corrente: stessa gerarchia, indice
    finale diverso — campionate SEEDED dalla chiave di zona (derivate pure,
    generate ON-DEMAND alla prima entrata: mappa e boss nascono dal loro seed).
    Vuota fuori dalla spina, alla tana, o se il mondo non ha sorelle."""
    territorio = territorio_attivo()
    corrente = zona_corrente()
    if territorio is None or corrente is None or not corrente.percorso:
        return ()
    if not e_di_spina(corrente, livello):
        return ()
    disponibili = _conta(territorio, corrente.tier)
    mio = corrente.percorso[-1]
    sorelle = [i for i in range(disponibili) if i != mio]
    if not sorelle:
        return ()
    rng = random.Random(f"{master_seed()}:piano:{livello}:laterali:{corrente.chiave}")
    quante = min(rng.randint(0, 2), len(sorelle))
    scelte = rng.sample(sorelle, quante) if quante else []
    return tuple(
        Zona(tier=corrente.tier, percorso=corrente.percorso[:-1] + (i,))
        for i in sorted(scelte)
    )


# --- La mappa DELLA ZONA (riuso di genera_topologia, seed per zona) -------------

def _topologia_zona(livello: int, zona: Zona, territorio: TerritorioAttivo) -> Piano:
    rng = random.Random(f"{master_seed()}:piano:{livello}:zona:{zona.chiave}")
    n = territorio.stanze_per_zona
    if zona.tier is TierTerritorio.PIANO:
        # La tana vuole ALMENO 3 stanze: partenza, la stanza del boss (n-2) e la
        # scala (n-1) — e la garanzia del nascondino: un arco che scavalca il
        # boss, così esiste un cammino partenza→scala che lo EVITA.
        base = genera_topologia(rng, max(3, n or 0) or None)
        stanze = len(base.adiacenze)
        boss = stanze - 2
        adiacenze = {k: list(v) for k, v in base.adiacenze.items()}
        aggira = (stanze - 1) in {x for i in range(boss) for x in adiacenze[i]}
        if not aggira:
            a = rng.randrange(0, boss)  # un arco seeded da PRIMA del boss alla scala
            adiacenze[a].append(stanze - 1)
            adiacenze[stanze - 1].append(a)
        return Piano(partenza=base.partenza, adiacenze=adiacenze, discese=set(base.discese))
    base = genera_topologia(rng, n)
    # Le zone NON-tana non hanno scala: il passaggio (ATTRAVERSA) sta in n-1,
    # custodito dal boss di zona — `discese` vuoto tiene SCENDI fuori dal menu.
    return Piano(partenza=base.partenza, adiacenze=base.adiacenze, discese=set())


def stanza_boss_di(zona: Zona, piano_mappa: Piano) -> int:
    """La stanza del boss: la penultima nella tana (la scala sta dietro, ma si
    può aggirare — nascondino), l'ULTIMA (il passaggio) nelle altre zone."""
    n = len(piano_mappa.adiacenze)
    return n - 2 if zona.tier is TierTerritorio.PIANO else n - 1


def stanza_passaggio_di(zona: Zona, piano_mappa: Piano) -> int:
    """La stanza da cui si ATTRAVERSA verso la zona successiva (ultima stanza).
    Nella tana non c'è passaggio (c'è la scala): ritorna comunque l'ultima."""
    return len(piano_mappa.adiacenze) - 1


def rigenera_mappa_zona(livello: int, zona: Zona) -> int:
    """Sostituisce la mappa con quella DELLA ZONA (seed per-zona, derivato) e
    aggiorna lo `StatoTerritorio` (posizione + visita). Il gemello zonale di
    `rigenera_mappa`."""
    territorio = territorio_attivo()
    assert territorio is not None, "rigenera_mappa_zona senza territorio attivo"
    for ent, _ in list(esper.get_component(Mappa)):
        esper.delete_entity(ent, immediate=True)
    piano_zona = _topologia_zona(livello, zona, territorio)
    ent = esper.create_entity(Mappa(piano=piano_zona, stanza_corrente=piano_zona.partenza))
    stato = stato_territorio()
    if stato is None:
        stato_nuovo = StatoTerritorio(zona_corrente=zona.chiave)
        stato_nuovo.zone_visitate.append(zona.chiave)
        esper.create_entity(stato_nuovo)
    else:
        stato.zona_corrente = zona.chiave
        if zona.chiave not in stato.zone_visitate:
            stato.zone_visitate.append(zona.chiave)
    return ent


def avvia_territorio(livello: int = 1) -> bool:
    """All'ingresso in run (o alla discesa): se il piano corrente ha un
    territorio, monta la mappa della PRIMA zona della spina e azzera lo stato.
    Ritorna False (nessun effetto) sui piani piatti: il chiamante crea la mappa
    storica."""
    if territorio_attivo() is None:
        return False
    for ent, _ in list(esper.get_component(StatoTerritorio)):
        esper.delete_entity(ent, immediate=True)
    spina = spina_del_piano(livello)
    rigenera_mappa_zona(livello, spina[0])
    return True


def _slug_sicuro(testo: str) -> str:
    """Un nome libero → slug kebab-case (per i boss istanziati dalle tabelle)."""
    import re as _re

    pulito = _re.sub(r"[^a-z0-9]+", "-", testo.lower()).strip("-")
    return pulito[:60] or "boss-senza-nome"


def boss_procedurale(livello: int, zona: Zona) -> MobAttivo | None:
    """Il boss ISTANZIATO dalle tabelle procedurali (tier distretto/quartiere):
    nome × gimmick × archetipo pescati seeded dalla chiave di zona; il grado lo
    impone il tier (simmetria 6↔6); i numeri, come sempre, la calibrazione.
    Deterministico, zero chiamate: stessa zona → stesso boss, per sempre."""
    from .catalogo import grado_da_tier

    territorio = territorio_attivo()
    if territorio is None:
        return None
    tabella = next(
        (t for t in territorio.procedurali if t.tier == zona.tier.value), None
    )
    if tabella is None:
        return None
    rng = random.Random(f"{master_seed()}:piano:{livello}:boss:{zona.chiave}")
    nome = rng.choice(list(tabella.nomi))
    gimmick = rng.choice(list(tabella.gimmick))
    archetipo = rng.choice(list(tabella.archetipi))
    return MobAttivo(
        slug=f"boss-{_slug_sicuro(nome)}",
        nome=nome,
        archetipo=archetipo,
        grado=grado_da_tier(zona.tier),
        blocchi=[],
        descrizione=gimmick,
        prosa_stanza=(f"{nome} custodisce il varco. {gimmick} "
                      "Non sembra dell'umore di lasciarti passare."),
        durata=Durata.TURNO,
    )


def boss_della_zona(livello: int, zona: Zona) -> MobAttivo | None:
    """IL boss che custodisce questa zona.

    Tier nominati: pescato SEEDED dal roster del piano (stessa zona → stesso
    boss, per sempre). Tier procedurali: istanziato dalle tabelle."""
    territorio = territorio_attivo()
    if territorio is None:
        return None
    roster = territorio.boss.get(zona.tier.value, ())
    if roster:
        rng = random.Random(f"{master_seed()}:piano:{livello}:boss:{zona.chiave}")
        return rng.choice(list(roster))
    return boss_procedurale(livello, zona)


# --- Tabelle di spawn: la pesca pesata dei riempitivi ---------------------------

def _tabella_spawn(territorio: TerritorioAttivo, tier: TierTerritorio):
    """La tabella del tier, o la più vicina SCENDENDO (un quartiere popola anche
    la città che non dichiara la sua), o la prima disponibile."""
    if tier.value in territorio.spawn:
        return territorio.spawn[tier.value]
    for candidato in reversed(ORDINE_SPINA[: ORDINE_SPINA.index(tier)]):
        if candidato.value in territorio.spawn:
            return territorio.spawn[candidato.value]
    for voci in territorio.spawn.values():
        return voci
    return ()


def pesca_spawn(rng: random.Random) -> MobAttivo | None:
    """UN riempitivo dalla tabella della zona corrente, pescato PESATO
    (`PESO_FREQUENZA`, foglia §11 — la frequenza è categoria del contratto).
    `None` senza territorio: il chiamante usa la via storica (cast)."""
    from .calibrazione import PESO_FREQUENZA

    territorio = territorio_attivo()
    zona = zona_corrente()
    if territorio is None or zona is None:
        return None
    voci = _tabella_spawn(territorio, zona.tier)
    if not voci:
        return None
    pesi = [PESO_FREQUENZA[v.frequenza] for v in voci]
    return rng.choices([v.mob for v in voci], weights=pesi, k=1)[0]


def stanza_corrente_e_del_boss() -> bool:
    """Vero se la stanza corrente è la stanza-boss della zona corrente."""
    zona = zona_corrente()
    m = mappa_corrente()
    if zona is None or m is None:
        return False
    return m[1].stanza_corrente == stanza_boss_di(zona, m[1].piano)


# --- Attraversamento: UN solo proprietario dell'avanzamento zona ----------------

def attraversamento_consentito() -> bool:
    """Il gate del passaggio: stanza-passaggio ∧ boss di zona sconfitto ∧ nessun
    nemico vivo ∧ esiste una zona successiva (nella tana c'è la scala, non il
    passaggio). Falso senza territorio (piani piatti: nessun attraversamento)."""
    from .piano import livello_corrente

    zona = zona_corrente()
    m = mappa_corrente()
    if zona is None or m is None or territorio_attivo() is None:
        return False
    if m[1].stanza_corrente != stanza_passaggio_di(zona, m[1].piano):
        return False
    if mob_corrente() is not None:
        return False
    if not boss_sconfitto(zona):
        return False
    return zona_successiva(livello_corrente()) is not None


def _despawna_mob_di_zona() -> None:
    """Elimina i mob residui della zona che si lascia (entità con `EntitaMob`,
    mai il protagonista): la zona nuova nasce pulita, niente reveal orfani.
    I PNG sopravvivono al cambio zona (T3): non sono arredo della stanza."""
    from contracts import RuoloMob

    for ent, em in list(esper.get_component(EntitaMob)):
        if esper.has_component(ent, Protagonista):
            continue  # cintura: il protagonista non ha EntitaMob, ma mai dire mai
        if em.ruolo is RuoloMob.PNG:
            continue
        esper.delete_entity(ent, immediate=True)


def deviazione_consentita(destinazione: str) -> bool:
    """Il gate delle DEVIAZIONI (laterali e ritorni): si devia dalla PARTENZA
    della zona, senza nemico in stanza, verso una destinazione che la scena ha
    davvero composto — mai un teletrasporto da chiave arbitraria."""
    from .piano import livello_corrente

    corrente = zona_corrente()
    m = mappa_corrente()
    if corrente is None or m is None or territorio_attivo() is None:
        return False
    if m[1].stanza_corrente != m[1].piano.partenza or mob_corrente() is not None:
        return False
    livello = livello_corrente()
    lecite = {z.chiave for z in zone_laterali(livello)}
    if not e_di_spina(corrente, livello):
        rientro = zona_di_spina_del_tier(corrente.tier, livello)
        lecite = {rientro.chiave} if rientro is not None else set()
    return destinazione in lecite


def attraversa(bus, destinazione: str = "") -> bool:
    """Varca un confine di zona. Senza `destinazione`: avanti sulla spina (gate:
    `attraversamento_consentito`); con `destinazione`: deviazione laterale o
    rientro (gate: `deviazione_consentita` — dalla partenza, senza boss: la via
    da cui sei entrato resta libera, il vicolo non ti chiude mai dentro)."""
    from .piano import livello_corrente

    livello = livello_corrente()
    if destinazione:
        if not deviazione_consentita(destinazione):
            return False
        prossima = zona_da_chiave(destinazione)
    else:
        if not attraversamento_consentito():
            return False
        prossima = zona_successiva(livello)
        assert prossima is not None  # garantito dal gate
    _despawna_mob_di_zona()
    rigenera_mappa_zona(livello, prossima)
    if bus is not None:
        bus.pubblica(TransizioneZona(zona=prossima.chiave, tier=prossima.tier.value))
    return True


class SistemaAttraversamento(SistemaSoloNarrazione):
    """Consuma `PlayerAttraversa` (solo in NARRAZIONE) e avanza la zona.

    Gemello di `SistemaDiscesa`: l'avanzamento è una conseguenza POSSEDUTA dal
    motore, scatenata dall'intento; un intento non valido è consumato senza
    effetto. UNICO proprietario dell'avanzamento zona."""

    def __init__(self, bus) -> None:
        self.bus = bus

    def run(self, dt: int) -> None:
        for intento in consuma_messaggi(PlayerAttraversa):
            attraversa(self.bus, getattr(intento, "destinazione", ""))


def collega_boss(bus):
    """Registra il rilevatore di boss sconfitto su `CombatResolved` (in-run).

    La vittoria nella STANZA-BOSS della zona corrente marca il suo custode come
    battuto (`StatoTerritorio.boss_sconfitti`). Il varco resta comunque chiuso
    finché un mob vivo occupa la stanza (`attraversamento_consentito`): una
    vittoria d'imboscata nella stanza sbagliata non apre niente da sola.
    Ritorna l'handler per la deregistrazione al teardown (pattern
    `collega_discesa_mappa`)."""
    from contracts import CombatResolved

    def _su_resolved(evento) -> None:
        if not getattr(evento, "vittoria", False):
            return
        if territorio_attivo() is None:
            return
        if stanza_corrente_e_del_boss():
            registra_boss_sconfitto()

    bus.registra(CombatResolved, _su_resolved)
    return _su_resolved


def boss_sconfitto(zona: Zona | None = None) -> bool:
    """Vero se il boss della zona (default: la corrente) è stato battuto."""
    stato = stato_territorio()
    if stato is None:
        return False
    chiave = (zona or zona_corrente()).chiave if (zona or zona_corrente()) else ""
    return chiave in stato.boss_sconfitti


def registra_boss_sconfitto(zona: Zona | None = None) -> None:
    stato = stato_territorio()
    if stato is None:
        return
    riferimento = zona or zona_corrente()
    if riferimento is not None and riferimento.chiave not in stato.boss_sconfitti:
        stato.boss_sconfitti.append(riferimento.chiave)
