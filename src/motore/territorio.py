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

from contracts import TierTerritorio

from .design import TerritorioAttivo, design_piano_corrente
from .mappa import Mappa, genera_topologia, mappa_corrente
from .piano import Piano
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

    Da una zona laterale (fuori spina, Fase 6) si rientra alla zona di spina del
    suo stesso tier: il passaggio avanti è uno solo."""
    corrente = zona_corrente()
    if corrente is None:
        return None
    spina = spina_del_piano(livello)
    for i, zona in enumerate(spina):
        if zona.chiave == corrente.chiave:
            return spina[i + 1] if i + 1 < len(spina) else None
    # Zona laterale: si rientra sulla spina al tier SUCCESSIVO al suo.
    indice_tier = ORDINE_SPINA.index(corrente.tier)
    if indice_tier + 1 < len(ORDINE_SPINA):
        return spina[indice_tier + 1]
    return None


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
