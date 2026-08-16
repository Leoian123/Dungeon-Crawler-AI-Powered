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
    # La FOTOGRAFIA all'uscita (anti zone-hopping, playtest 2026-08-12): per
    # zona lasciata, le stanze che avevano un OSTILE VIVO al momento
    # dell'attraversamento. Al rientro si rimaterializzano SOLO quelle (dal
    # seed del copione: stesso mob) — il morto resta morto, il congedato
    # ritorna. Default retro-safe: i save storici deserializzano invariati.
    stanze_con_vivi: dict[str, list[int]] = field(default_factory=dict)


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
        piano_zona = Piano(
            partenza=base.partenza, adiacenze=adiacenze, discese=set(base.discese)
        )
    else:
        base = genera_topologia(rng, n)
        # Le zone NON-tana non hanno scala: il passaggio (ATTRAVERSA) sta in n-1,
        # custodito dal boss di zona — `discese` vuoto tiene SCENDI fuori dal menu.
        piano_zona = Piano(partenza=base.partenza, adiacenze=base.adiacenze, discese=set())
    _stampa_tipi_zona(livello, zona, piano_zona)
    return piano_zona


def _stampa_tipi_zona(livello: int, zona: Zona, piano_zona: Piano) -> None:
    """La stampa dei tipi con i vincoli DEL TERRITORIO: la stanza del custode è
    BOSS; la SAFE ROOM è garantita per quota di spina (`STANZE.safe_ogni_zone` —
    rara e da trovare, mai regalata) e a pescata nei vicoli laterali (il premio
    della deviazione, `STANZE.prob_safe_laterale`). RNG su stream DEDICATO
    (`…:tipi`): la topologia già pubblicata resta byte-identica."""
    from .calibrazione import STANZE_PROB_SAFE_LATERALE, STANZE_SAFE_OGNI_ZONE
    from .mappa import stampa_tipi

    rng_tipi = random.Random(f"{master_seed()}:piano:{livello}:zona:{zona.chiave}:tipi")
    di_spina = e_di_spina(zona, livello)
    ogni = max(1, int(STANZE_SAFE_OGNI_ZONE))
    stampa_tipi(
        piano_zona,
        rng_tipi,
        boss=stanza_boss_di(zona, piano_zona),
        safe_garantita=di_spina and zona.tier.ordine % ogni == ogni - 1,
        prob_safe=0.0 if di_spina else STANZE_PROB_SAFE_LATERALE,
    )


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
        _rimaterializza_vivi(livello, zona, stato)
    return ent


def _rimaterializza_vivi(livello: int, zona: Zona, stato: StatoTerritorio) -> None:
    """Il RIENTRO ripopola dalla fotografia (anti zone-hopping): per ogni stanza
    che aveva un ostile vivo all'uscita, lo STESSO mob torna — pescato dal seed
    del copione (`master_seed:copione:…`: offline, live e rientro convergono),
    o il custode per la stanza-boss. Ferite non persistite (si è ripreso: il
    prezzo diegetico del tempo passato). Archetipo fuori registry → si salta
    (degrado, mai un crash — stessa guardia di `rimaterializza_custode`)."""
    from contracts import EntitaGenerata

    from .design import registry_archetipi_correnti
    from .narrazione import istanzia_entita

    stanze = stato.stanze_con_vivi.get(zona.chiave)
    if not stanze:
        return
    m = mappa_corrente()
    if m is None:
        return
    mappa = m[1]
    boss_stanza = stanza_boss_di(zona, mappa.piano)
    registry = registry_archetipi_correnti()
    for stanza in stanze:
        if stanza not in mappa.piano.adiacenze:
            continue  # fotografia più larga della zona rigenerata: si salta
        if stanza == boss_stanza:
            mob = boss_della_zona(livello, zona)
        else:
            rng = random.Random(
                f"{master_seed()}:copione:{livello}:{zona.chiave}:{stanza}"
            )
            mob = pesca_spawn(rng)
        if mob is None or mob.archetipo not in registry:
            continue
        ent = istanzia_entita(EntitaGenerata(
            archetipo=mob.archetipo, grado=mob.grado, blocchi=list(mob.blocchi),
            nome=mob.nome, descrizione=mob.descrizione, riferimento=mob.slug,
        ), livello)
        em = esper.component_for_entity(ent, EntitaMob)
        em.stanza = stanza
        mappa.mob_stanza[stanza] = ent


def avvia_territorio(livello: int = 1) -> bool:
    """All'ingresso in run (o alla discesa): se il piano corrente ha un
    territorio, monta la mappa della PRIMA zona della spina e azzera lo stato.
    Ritorna False (nessun effetto) sui piani piatti: il chiamante crea la mappa
    storica."""
    # Il cleanup PRIMA dell'early-return (caccia 2026-08-16): il confine di
    # piano azzera SEMPRE lo stato territoriale del piano lasciato. Con l'ordine
    # inverso, scendere da un piano-mondo a un piano PIATTO lasciava lo
    # `StatoTerritorio` stantio: `zona_corrente()` restava la tana del piano 1 e
    # `finestra_gradi_loot` serviva drop LEGGENDARIO/CELESTIALE su mob di
    # profondità 2 — e il fascicolo GM dichiarava una zona inesistente.
    for ent, _ in list(esper.get_component(StatoTerritorio)):
        esper.delete_entity(ent, immediate=True)
    if territorio_attivo() is None:
        return False
    spina = spina_del_piano(livello)
    rigenera_mappa_zona(livello, spina[0])
    return True


def _slug_sicuro(testo: str) -> str:
    """Un nome libero → slug kebab-case (per i boss istanziati dalle tabelle)."""
    import re as _re

    pulito = _re.sub(r"[^a-z0-9]+", "-", testo.lower()).strip("-")
    return pulito[:60] or "boss-senza-nome"


# Insegne delle deviazioni laterali: vocabolario chiuso, SEGNAPOSTO di canale
# (come i profili-base del protagonista). Il dungeon è uno show con la sua
# cartellonistica: una deviazione ha un'insegna, non un indice. Un piano che
# vorrà le proprie insegne autorate le porterà come tabella d'asset — qui resta
# il default che rende il menu diegetico su qualunque contenuto.
INSEGNE_LATERALI: tuple[str, ...] = (
    "dei Neon Spenti",
    "della Fiera Chiusa",
    "del Parcheggio Interrato",
    "delle Vetrine Murate",
    "del Cinema d'Essai",
    "della Fermata Soppressa",
    "dei Cassonetti Sponsorizzati",
    "del Sottopasso Premium",
)


def insegna_laterale(zona: Zona) -> str:
    """L'insegna DIEGETICA di una zona laterale: «quartiere del Cinema d'Essai».

    Deterministica e stabile (stessa zona → stessa insegna, per sempre) e
    **distinta fra sorelle**: l'offset è seeded sul percorso del genitore, l'indice
    del figlio ruota il vocabolario — due deviazioni affacciate dalla stessa
    partenza non possono ricevere la stessa insegna (finché sono meno delle voci).

    Serve a non stampare al giocatore l'indice interno della zona: l'etichetta
    portava `(0)`/`(2)` — `percorso[-1]` — cioè una struttura dati a video."""
    if not zona.percorso:
        return zona.tier.value
    genitore = "/".join(str(i) for i in zona.percorso[:-1])
    offset = random.Random(
        f"{master_seed()}:insegna:{zona.tier.value}:{genitore}"
    ).randrange(len(INSEGNE_LATERALI))
    insegna = INSEGNE_LATERALI[(offset + zona.percorso[-1]) % len(INSEGNE_LATERALI)]
    return f"{zona.tier.value} {insegna}"


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
        prosa_stanza=_prosa_custode(nome, gimmick, rng),
        durata=Durata.TURNO,
    )


# Cornici della prosa del custode procedurale: vocabolario CHIUSO del canale
# (come le insegne laterali), pescato seeded dallo stesso stream del boss —
# stessa zona, stessa scena, per sempre. Prima c'era UNA cornice per tutti
# («X custodisce il varco. <gimmick> Non sembra dell'umore…»): il momento
# culminante di ogni zona arrivava al giocatore come la riga di una formula,
# identica dal primo quartiere alla provincia. Il {gimmick} resta il cuore
# (è il dato autorato della tabella); la cornice è la regia del Sistema —
# lo show di DCC inquadra ogni custode come un'attrazione diversa.
_CORNICI_CUSTODE: tuple[str, ...] = (
    "{nome} custodisce il varco. {gimmick} Non sembra dell'umore di lasciarti passare.",
    "Le luci calano da sole: il Sistema vuole che tu guardi. {nome} è già in "
    "posa al centro della stanza. {gimmick} Il varco è dietro di lui, e lo sa.",
    "Lo senti prima di vederlo. {gimmick} Poi {nome} si volta verso di te, "
    "e la stanza diventa piccola.",
    "Qualcuno ha ripulito il pavimento davanti al varco: un palcoscenico. "
    "{nome} lo occupa tutto. {gimmick}",
    "{nome} non si alza nemmeno: ti stava aspettando. {gimmick} "
    "Nessuno passa senza un finale.",
    "Un applauso registrato parte da altoparlanti che non esistono. "
    "{gimmick} {nome} ringrazia il pubblico, poi guarda te.",
)


def _prosa_custode(nome: str, gimmick: str, rng: random.Random) -> str:
    """La prosa di stanza del custode: cornice seeded × gimmick autorato.

    Pesca dallo STESSO stream del boss (dopo nome/gimmick/archetipo): stessa
    zona → stessa cornice, e le pescate esistenti non si spostano — il boss di
    un save in corso resta identico, cambia solo la riga che lo presenta."""
    return rng.choice(_CORNICI_CUSTODE).format(nome=nome, gimmick=gimmick)


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


def pavimento_hp_custode(livello: int) -> int:
    """Il PAVIMENTO del pool del custode: gli HP del miglior GREGARIO che la
    tabella di spawn del tier può schierare (round 3: il Nonno-scheletro
    pescava l'archetipo gracile e faceva 12×1.5=18 HP contro il Fante da 24 —
    il momento-boss non deve mai essere più tenero dei riempitivi). Derivato
    con la stessa formula-madre dei mob veri (profilo+override → Costituzione
    → HP), mai numeri propri. 0 senza territorio/tabella: pavimento inerte,
    resta la sola tempra `BOSS.molt_hp`."""
    from contracts import StatId

    from .calibrazione import HP_BASE, K_HP, primarie_da_archetipo
    from .design import profilo_con_override, registry_archetipi_correnti

    territorio = territorio_attivo()
    zona = zona_corrente()
    if territorio is None or zona is None:
        return 0
    registry = registry_archetipi_correnti()
    pavimento = 0
    for voce in _tabella_spawn(territorio, zona.tier):
        mob = voce.mob
        profilo = registry.get(mob.archetipo)
        if profilo is None:
            continue  # archetipo driftato: degrado, mai un crash (stessa guardia del rientro)
        if mob.override:
            profilo = profilo_con_override(profilo, mob.override)
        primarie = primarie_da_archetipo(
            mob.archetipo, mob.grado, livello, profilo=profilo
        )
        hp = round(HP_BASE + K_HP * primarie[StatId.COSTITUZIONE])
        pavimento = max(pavimento, hp)
    return pavimento


def finestra_gradi_loot(livello: int) -> frozenset:
    """La finestra di gradi per il LOOT qui e ora: sul piano-mondo segue il TIER
    della zona corrente (`gradi_del_tier` — il bottino insegue il territorio,
    non la profondità, che resta 1 su tutta la spina); sui piani piatti resta
    `gradi_per_profondita`. Senza questo aggancio il corredo di riferimento dei
    gradi alti era irraggiungibile proprio nelle zone che li schierano (misura
    2026-08-11: nessuna run oltre la città)."""
    from .catalogo import gradi_del_tier, gradi_per_profondita

    # La zona vale solo se il PIANO CORRENTE ha un territorio (stessa guardia di
    # `pesca_spawn`): difesa in profondità per i save scritti quando lo stato
    # territoriale poteva sopravvivere alla discesa su un piano piatto — quei
    # load degradano a `gradi_per_profondita` invece di servire celestiali.
    zona = zona_corrente()
    if zona is not None and territorio_attivo() is not None:
        return gradi_del_tier(zona.tier)
    return gradi_per_profondita(livello)


def rimaterializza_custode() -> int | None:
    """Il custode NON battuto torna in scena nella SUA stanza al rientro in zona.

    Uscire dalla zona lo despawna (`_despawna_mob_di_zona`: la zona nuova nasce
    pulita); al rientro la stanza-boss già narrata RILEGGE l'Archivio, che non
    materializza nulla — senza di lui `attraversamento_consentito` resterebbe
    falso per sempre (soft-lock scovato da `misura_run`). Deterministico, zero
    AI: stesso asset del fascicolo (`boss_della_zona`) e stessa strada
    dell'imboscata (`istanzia_entita` + `registra_mob`) — il motore rimette in
    scena contenuto già suo. `None` = niente da fare (non è la stanza-boss,
    boss battuto, mob già in scena, o boss inesistente)."""
    from contracts import EntitaGenerata

    from .mappa import registra_mob
    from .narrazione import istanzia_entita
    from .piano import livello_corrente

    zona = zona_corrente()
    if (zona is None or not stanza_corrente_e_del_boss()
            or boss_sconfitto(zona) or mob_corrente() is not None):
        return None
    livello = livello_corrente()
    custode = boss_della_zona(livello, zona)
    if custode is None:
        return None
    from .design import registry_archetipi_correnti

    if custode.archetipo not in registry_archetipi_correnti():
        # Questo call-site NON passa dal gate (`istanzia_entita` presume il
        # post-gate): un archetipo driftato (save vecchio, stagione diversa)
        # deve degradare — mai un KeyError dentro una RILETTURA d'Archivio.
        return None
    eg = EntitaGenerata(
        archetipo=custode.archetipo, grado=custode.grado, blocchi=[],
        nome=custode.nome, descrizione=custode.descrizione,
        riferimento=custode.slug,
    )
    ent = istanzia_entita(eg, livello)
    registra_mob(ent)
    return ent


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


def _fotografa_vivi_di_zona() -> None:
    """PRIMA del despawn: le stanze con un OSTILE VIVO finiscono nella
    fotografia persistente (`StatoTerritorio.stanze_con_vivi`) della zona che
    si lascia. È l'informazione che il despawn distruggerebbe — e senza di
    lei il rientro non saprebbe distinguere il congedato (che DEVE tornare)
    dall'ucciso (che non torna): rimaterializzare tutto resusciterebbe i
    morti (farming di drop), non rimaterializzare niente è il zone-hopping."""
    from contracts import RuoloMob

    stato = stato_territorio()
    if stato is None:
        return
    stanze = sorted({
        em.stanza for _ent, em in esper.get_component(EntitaMob)
        if em.ruolo is RuoloMob.OSTILE and em.stanza is not None
    })
    stato.stanze_con_vivi[stato.zona_corrente] = stanze


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
    _fotografa_vivi_di_zona()  # PRIMA del despawn: chi era vivo, e dove
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
        if not stanza_corrente_e_del_boss():
            return
        # La vittoria conta solo se la stanza è rimasta SENZA mob (caccia
        # 2026-08-16): battere un'IMBOSCATA nella stanza-boss col custode vivo
        # marcava il custode come battuto — il varco restava chiuso finché lui
        # occupava la stanza, ma bastava USCIRE e rientrare in zona:
        # `rimaterializza_custode` rimette in scena solo il custode NON battuto,
        # quindi la stanza rinasceva vuota e il boss-gate si apriva senza averlo
        # mai combattuto. Con la vittoria vera il custode morto è già stato
        # smontato (`_smonta` gira prima: registrato prima sul bus) e la stanza
        # è libera; con l'imboscata vinta il custode vivo la occupa ancora.
        from .mappa import mob_corrente

        if mob_corrente() is None:
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
