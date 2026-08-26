"""Eventi di dominio — DTO che attraversano la membrana motore → vista (IC §2.3).

Sono **dati semplici** (IC §2.2): solo `str`/`int`/`bool` e enum chiusi. Niente
renderable di Rich, niente widget Textual, niente riferimenti al `World` né entità
esper vive. Un `int` qui è un **identificatore opaco** di entità (l'id intero di
esper è un dato, non un oggetto vivo), non un puntatore allo stato.

Viaggiano sul bus tipizzato (`bus.py`) come Canale B di ESP §5: transitori, push,
con molti ascoltatori scorrelati (showrunner, log, adattatore di presentazione).

Dipendenze: solo stdlib (F-2).
"""

from __future__ import annotations

from dataclasses import dataclass

# Id opaco di un'entità di gioco. È un dato (int), NON un'entità esper viva: il
# `World` non attraversa mai la membrana (IC §2.2).
Entita = int


@dataclass(frozen=True)
class EventoDominio:
    """Marcatore comune degli eventi di dominio. Nessun comportamento."""


@dataclass(frozen=True)
class EncounterStarted(EventoDominio):
    """Un incontro è stato composto e innescato (confine narrazione→combattimento).

    La `TurnoNarrazione` che lo emette è clampata a `durata == TURNO` dal gate del
    motore (F §2, C3): F vincola il dato, il gate lo impone — non questo evento.
    `imboscata=True` = l'incontro l'ha innescato il dado-evento del tempo (J §8),
    non una scelta del giocatore: la cronaca e l'apertura lo dicono."""

    entita: Entita
    imboscata: bool = False


@dataclass(frozen=True)
class CombatResolved(EventoDominio):
    """Il combattimento si è risolto. L'esito è già arbitrato dal motore (FNC §5.2).

    *Risolvi prima, narra dopo*: l'evento porta un fatto d'esito già deciso, non una
    richiesta di decisione. `fuga=True` = disimpegno riuscito A SCONTRO APERTO
    (FNC §4): non è né vittoria né sconfitta — lo scontro si chiude senza esito.
    """

    entita: Entita
    vittoria: bool
    fuga: bool = False
    # I FATTI DA IMPRESA (nodo O, titoli mid-run) — fotografati dal motore
    # all'apertura dello scontro, mai dedotti a valle:
    grado_nemico: str = ""     # il grado più alto fra i nemici ("" = scalari)
    custode: bool = False      # lo scontro era nella stanza del custode di zona
    senza_graffi: bool = False # vittoria senza aver perso un solo HP


@dataclass(frozen=True)
class ColpoInferto(EventoDominio):
    """Un colpo è andato a segno (già risolto dal motore: il danno è un fatto).

    `attaccante`/`bersaglio` sono NOMI diegetici; stringa vuota = il protagonista
    (la vista decide come chiamarlo). `mossa` è la chiave della mossa usata.
    """

    attaccante: str
    bersaglio: str
    danno: int
    hp_rimasti: int
    hp_max: int
    mossa: str = "attacco"
    # La FACCIA d'azzardo pescata ("" = colpo ordinario): l'etichetta diegetica
    # dell'esito («Jackpot del Sistema», «La casa vince») — la cronaca la dice,
    # la roulette deve SEMBRARE una roulette (playtest 2026-08-12).
    azzardo: str = ""


@dataclass(frozen=True)
class StatusApplicato(EventoDominio):
    """Uno status è stato applicato in scontro (es. il morso velenoso che avvelena)."""

    bersaglio: str  # "" = protagonista
    status: str     # nome del tipo ("veleno", "stordito", …)
    fonte: str      # nome diegetico di chi l'ha applicato


@dataclass(frozen=True)
class EffettoStatus(EventoDominio):
    """Il tick di uno status ha mosso gli HP (veleno −, rigenerazione +)."""

    bersaglio: str  # "" = protagonista
    status: str
    delta_hp: int   # negativo = danno


@dataclass(frozen=True)
class TurnoSaltato(EventoDominio):
    """Un combattente ha perso il turno (stordito) o l'ha speso senza esito
    (fuga negata: margine impossibile). `nome` "" = protagonista."""

    nome: str
    causa: str  # "stordito" | "fuga_negata"


@dataclass(frozen=True)
class StatusSvanito(EventoDominio):
    """Un'afflizione è SCADUTA: la fine di veleno/brucia/rigenerazione va detta.

    Prima il giocatore leggeva l'inizio («Sei avvelenato!») e i tick («-1 HP»),
    mai la fine — con la rigenerazione valeva l'inverso. `bersaglio` "" =
    protagonista."""

    bersaglio: str
    status: str


@dataclass(frozen=True)
class CrolloDungeon(EventoDominio):
    """L'escalation del dungeon morde TUTTI i combattenti (G §5.6): danno
    inevitabile e crescente con il protrarsi dello scontro. Prima era muto:
    HP che calavano senza una riga di cronaca."""

    danno: int


@dataclass(frozen=True)
class DisimpegnoScena(EventoDominio):
    """Disimpegno riuscito in fase di NARRAZIONE (FNC §4): RITIRATA universale
    (2026-08-12) — tu arretri nella stanza adiacente, il nemico resta alla sua.
    Il disimpegno fallito non ha un evento proprio: sfocia in `EncounterStarted`.

    `ritirata_in` = la stanza in cui arretri (-1 = ignota, retro-compat): la
    cronaca DEVE dire dove sei finito — prima la ritirata era muta e te ne
    accorgevi dal numero di stanza (riscontro playtest)."""

    nemico: str = ""
    ritirata_in: int = -1


@dataclass(frozen=True)
class TransizioneZona(EventoDominio):
    """Il crawler ha varcato il passaggio verso un'altra ZONA del territorio
    (2026-08). L'avanzamento è già disposto dal motore (`SistemaAttraversamento`):
    l'evento è il fatto compiuto, per cronaca e showrunner. `zona` è la chiave
    stabile della zona d'arrivo, `tier` il suo livello nella gerarchia."""

    zona: str
    tier: str


@dataclass(frozen=True)
class OggettoTrovato(EventoDominio):
    """Bottino a fine scontro vinto: il canale del loot parla in cronaca.

    `fonte` è l'id di dominio durevole (quello di Zaino/equip); `nome` è il
    diegetico da mostrare. La TABELLA dei drop è contenuto; questo è il canale."""

    nome: str
    fonte: str


@dataclass(frozen=True)
class RiposoConcluso(EventoDominio):
    """Un riposo è finito: quanto tempo è costato e quanto ha reso.

    `interrotto=True` = il riposo è stato spezzato prima della fine (un'imboscata,
    o la morte): i tick già spesi restano reali e il recupero è PARZIALE — è il
    fatto, non una promessa. È un evento riassuntivo di proposito: il riposo dura
    più tick e una riga per tick sarebbe rumore in cronaca."""

    tick_spesi: int
    hp_recuperati: int
    mana_recuperato: int
    interrotto: bool = False


@dataclass(frozen=True)
class MortePersonaggio(EventoDominio):
    """Terminale di run: permadeath (death-check seeded del motore), non sconfitta.

    È l'evento terminale della run; la `causa` è flavor diegetico, non un numero.
    """

    causa: str


@dataclass(frozen=True)
class BoxAperta(EventoDominio):
    """Una box degli obiettivi si è aperta (nodo O2, solo nei luoghi quieti):
    il conio è del motore (fabbrica, stream isolato per-box — replay-safe),
    l'evento è il fatto compiuto per cronaca e showrunner. `fonte` è l'id di
    dominio dell'oggetto coniato (Zaino/equip), `nome` il diegetico."""

    categoria: str
    grado: str
    nome: str
    fonte: str


@dataclass(frozen=True)
class ObiettivoRaggiunto(EventoDominio):
    """La NOTIFICA DI SISTEMA di un obiettivo sbloccato (nodo O): il dungeon
    ti guarda e commenta. Lo sblocco l'ha deciso l'osservatore del motore su
    un fatto del bus (mai l'LLM); il testo è dato autorale deterministico.
    `ricompensa_testo` è già composto («Una Box … di …» o la beffa): l'host
    lo MOSTRA, mai lo ricostruisce."""

    slug: str
    titolo: str
    testo: str
    ricompensa_testo: str


@dataclass(frozen=True)
class AnomalyTriggered(EventoDominio):
    """Reveal di un'anomalia: il motore l'ha tirata (seeded) e la pubblica perché lo
    showrunner la narri (F §4.3, FNC §5.5, §8).

    L'anomalia è un **tiro del motore**, mai un campo dello schema: l'AI la narra,
    non la invoca. Qui è solo il segnale che è avvenuta.
    """

    entita: Entita


@dataclass(frozen=True)
class DiscesaPiano(EventoDominio):
    """Discesa al piano successivo: l'unico evento che fa avanzare il `livello`
    (profondità del piano, posseduta dal motore — F §4.2, G §8.1).

    `piano` è stato del motore (un `int`), non output dell'AI: non viola F-3, che
    vincola solo `EntitaGenerata`.
    """

    piano: int
