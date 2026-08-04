"""Fase NARRAZIONE: socket generativo, gate a tre strati, materializzazione, fallback
(FNC §5; F §4/§5/§6; G §9; criteri F-5/6/8/9/10/11, G-13/19/20/22/25).

Ordinamento del flusso dati (FNC §5.1) — **AI a monte, gate di validazione a valle**:

    il MOTORE prepara il contesto (anomalia seeded, budget + set ammissibile)
      → 1 chiamata `genera` strutturata, col budget NEL prompt (soft)
        → GATE (schema · catalogo · budget) — ciò che non passa non tocca lo stato
          → il motore istanzia l'entità (stat DERIVATE) e applica al World

Disciplina del socket (G §9):
  - **un solo verbo** verso il provider, `genera(prompt, schema)` — niente secondo
    metodo per tipo (G-19); prompt e gate vivono **qui, nel motore**;
  - l'orchestrazione è una **coroutine host-agnostica** (stdlib, nessun import
    Textual): si testa headless;
  - una `genera` in volo (fallita/cancellata/in retry) **non scrive sul save**: la
    coroutine NON muta l'ECS; la materializzazione è un passo sincrono separato, alla
    risoluzione del turno (G-20, F §6.1).

Politica di fallimento **selezionata dallo schema, lato motore** (F §5.1): la
narrazione (atomica) ritenta; la modalità-prosa (cosmetica) fallisce in fretta.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import esper
from pydantic import ValidationError

from contracts import (
    AnomalyTriggered,
    Durata,
    EncounterStarted,
    EntitaGenerata,
    Flavor,
    Opzione,
    SchedaProiezione,
    TipoAzione,
    TurnoNarrazione,
)

from .calibrazione import primarie_da_archetipo
from .corredo import Corredo
from .design import (
    archetipo_attivo,
    mob_del_cast,
    profilo_con_override,
    registry_archetipi_correnti,
)
from .modificatori import ResistenzaMod, Resistenze
from .catalogo import (
    DURATA_BLOCCO_DEFAULT,
    REGISTRY_BLOCCHI,
    Budget,
    prepara_contesto,
    rango_grado,
)
from .combattimento import PianoIncontro, SpecNemico
from .derivate import max_hp
from .mob import EntitaMob, Repertorio
from .mosse import MOSSE_DEFAULT
from .prove import risolvi_prova
from .scheda import Scheda
from .statistiche import REGISTRY_STAT, Primarie, Visibilita, stat_eff
from .status import Rigenerazione, Stordito, Veleno

# --- Politica di retry, selezionata dallo SCHEMA (F §5.1, F-8) -----------------

# Narrazione: atomica e vale la pena ritentare → 1 retry (2 tentativi totali).
RETRY_NARRAZIONE = 1
# Modalità-prosa: cosmetica, fallisce in fretta → nessun retry.
RETRY_PROSA = 0


# --- Testi neutri di fallback (SEGNAPOSTO Gruppo 2) ---------------------------

PROSA_NEUTRA = "La stanza è silenziosa. Qualcosa si muove nell'ombra."
NOME_NEUTRO = "Sagoma indistinta"
DESCRIZIONE_NEUTRA = "Una presenza generica, abbozzata dal dungeon."

# Il menu fisso di default (F §6.3): Combatti / Scappi / Altro.
MENU_FISSO: tuple[Opzione, ...] = (
    Opzione(tipo=TipoAzione.COMBATTI, etichetta="Combatti"),
    Opzione(tipo=TipoAzione.SCAPPA, etichetta="Scappi"),
    Opzione(tipo=TipoAzione.ALTRO, etichetta="Altro"),
)


# --- Componente dell'entità generata (materializzata nel World) ---------------
# `EntitaMob` vive in `mob.py` (modulo foglia: è persistente e il registry dei tag
# non importa moduli coi sistemi); l'import sopra lo ri-esporta per i consumatori
# storici (`from .narrazione import EntitaMob`).


# --- Proiezione di sola lettura della scheda (G §6.6, G-13) -------------------

def proietta_scheda(entita_protagonista: int) -> SchedaProiezione:
    """Costruisce il DTO di sola lettura dallo stato VIVO (G-13; Gruppo 2 §2.4/GR2-9).

    L'AI riceve `("ferito", "avvelenato")` + le primarie **filtrate per visibilità**, MAI
    un componente ECS vivo. È il motore — non l'AI — a derivare i descrittori e ad
    applicare il filtro: il registry `REGISTRY_STAT` vive QUI (motore), il DTO in
    `contracts` riceve mappe già filtrate (membrana C-3).
    """
    scheda = esper.component_for_entity(entita_protagonista, Scheda)
    descrittori: list[str] = []
    if not scheda.vivo:
        descrittori.append("morente")
    elif scheda.punti_vita < max_hp(entita_protagonista):  # massimo DERIVATO (§5)
        descrittori.append("ferito")
    else:
        descrittori.append("integro")
    if esper.try_component(entita_protagonista, Veleno) is not None:
        descrittori.append("avvelenato")
    if esper.try_component(entita_protagonista, Stordito) is not None:
        descrittori.append("stordito")
    if esper.try_component(entita_protagonista, Rigenerazione) is not None:
        descrittori.append("in rigenerazione")

    # Primarie filtrate per visibilità (GR2-9): PALESE → valore effettivo; VALORE_NASCOSTO
    # → solo il nome; ESISTENZA_NEGATA → omessa del tutto. Ordine stabile dal registry.
    valori = esper.component_for_entity(entita_protagonista, Primarie).valori
    primarie: dict[str, int] = {}
    occulte: list[str] = []
    for stat, riga in REGISTRY_STAT.items():
        if stat not in valori:
            continue
        if riga.visibilita is Visibilita.PALESE:
            primarie[stat.value] = stat_eff(entita_protagonista, stat)
        elif riga.visibilita is Visibilita.VALORE_NASCOSTO:
            occulte.append(stat.value)
        # ESISTENZA_NEGATA: la proiezione la tratta come se non esistesse.
    return SchedaProiezione(
        descrittori=tuple(descrittori),
        primarie=primarie,
        primarie_occulte=tuple(occulte),
    )


# --- Costruzione del prompt: budget iniettato NEL testo (soft, F §4.1, F-10) ---

def costruisci_prompt(budget: Budget, proiezione: SchedaProiezione, voce: str) -> str:
    """Assembla il prompt OPACO (voce + contesto + budget + proiezione). È testo (str):
    nessun componente ECS vivo lo attraversa (G-13).

    Il **budget è iniettato come testo** (soft): l'AI lo rispetta solo se glielo dici
    (F §4.1). È necessario ma mai sufficiente — il gate resta l'unica garanzia (F-10).
    Se il budget è anomalo, il prompt **lo sa già** (così la stanza è all'altezza,
    FNC §5.5): l'anomalia entra solo come budget gonfiato, mai come campo.
    """
    gradi = ", ".join(sorted(g.value for g in budget.gradi_ammessi))
    blocchi = ", ".join(sorted(b.value for b in budget.blocchi_ammessi))
    # Fix F-10: anche gli ARCHETIPI raggiungono l'AI due volte (prompt soft + gate
    # hard) — prima erano vincolati solo hard, con più fallback del necessario.
    archetipi = ", ".join(sorted(budget.archetipi_ammessi))
    stato = ", ".join(proiezione.descrittori) if proiezione.descrittori else "ignoto"
    righe = [
        voce,
        f"[contesto] profondità del piano: {budget.livello}",
        f"[contesto] stato del protagonista (vista): {stato}",
        f"[budget] archetipi ammessi: {archetipi}",
        f"[budget] gradi ammessi: {gradi}",
        f"[budget] blocchi ammessi: {blocchi}",
        "[budget] scegli archetipo/grado/blocchi DENTRO il budget; "
        "non emettere numeri né livello.",
    ]
    if budget.anomala:
        righe.append("[anomalia] il dungeon ha tirato fuori scala: questo scontro è un evento.")
    return "\n".join(righe)


# --- Il gate: tre strati nel MOTORE (F §4, F-5/F-6/F-10; clamp G-25/F-14) ------

def valida_turno(
    candidato: TurnoNarrazione,
    budget: Budget,
    *,
    ingresso_combattimento: bool = False,
) -> TurnoNarrazione | None:
    """Gate a tre strati. Ciò che non passa ritorna `None` (rifiuto-di-dominio).

    1. **Schema** — il candidato ri-parsa nel modello Pydantic (garanzia
       backend-agnostica: un backend senza grammatica produrrebbe testo da parsare).
    2. **Catalogo** — ogni archetipo/`Blocco` scelto ha un binding nel registry
       (F-6): per gli archetipi il registry è quello DELLA RUN (storici + asset
       congelati nella stagione, D1) — nessun nome accettabile ma non istanziabile.
    3. **Budget** — rarità e insieme di blocchi cadono nel set ammissibile (F-10). È
       **obbligatorio e insostituibile**: la grammatica vincola il vocabolario, non i
       valori; il budget è un vincolo di valore → solo il gate lo garantisce.

    Clamp d'ingresso (G-25/F-14): una `TurnoNarrazione` che innesca un incontro ha
    `durata == TURNO` dopo il gate — l'imboscata è una singola battuta, non comprime
    tempo. È l'unico punto in cui il gate non è identità già nell'MVP.
    """
    # Strato 1: conformità di schema.
    try:
        cand = TurnoNarrazione.model_validate(candidato.model_dump())
    except ValidationError:
        return None

    eg = cand.entita

    # Strato 2: appartenenza al catalogo + binding nel registry (per gli archetipi:
    # il registry congelato della run — F-6 diventa runtime, D1).
    if eg.archetipo not in registry_archetipi_correnti():
        return None
    for blocco in eg.blocchi:
        if blocco not in REGISTRY_BLOCCHI:
            return None

    # Strato 3: rispetto del budget (HARD, oltre al soft del prompt).
    if eg.grado not in budget.gradi_ammessi:
        return None
    if not set(eg.blocchi) <= budget.blocchi_ammessi:
        return None
    if eg.archetipo not in budget.archetipi_ammessi:
        return None  # il design del piano vincola anche gli archetipi

    # Strato 4 (D5): il `riferimento` è un RECLUTAMENTO dal cast del piano corrente
    # — un nome fuori cast è un rifiuto (fallback F-13), mai contenuto arbitrario.
    # Senza un piano attivo (harness, save legacy) il vincolo non esiste: il
    # riferimento resta un'annotazione inerte (la materializzazione lo ignora).
    if eg.riferimento is not None:
        from .design import design_piano_corrente

        if design_piano_corrente() is not None and mob_del_cast(eg.riferimento) is None:
            return None

    # Clamp d'ingresso al combattimento (C3): la durata è ricondotta a TURNO.
    if ingresso_combattimento and cand.durata != Durata.TURNO:
        cand = cand.model_copy(update={"durata": Durata.TURNO})

    return cand


# --- Esito di un turno: validato OPPURE fallback (seam di replay, F-13) --------

@dataclass
class RisultatoTurno:
    """L'esito di un turno di narrazione, PRIMA della materializzazione nel World.

    `fallback=True` marca un turno andato in ripiego: va registrato come tale per il
    replay (F-13) — il replay lo riproduce, non richiama l'LLM. `anomala` propaga il
    flag del budget per il reveal `AnomalyTriggered` alla materializzazione (F §4.3).
    """

    turno: TurnoNarrazione
    budget: Budget
    fallback: bool
    anomala: bool


# --- Fallback atomico, locale, deterministico (F §6.3, F-8) -------------------

def fallback_turno(budget: Budget, *, ingresso_combattimento: bool = False) -> RisultatoTurno:
    """Il fallback unico: testo neutro + archetipo di default DESIGNATO nel budget +
    menu fisso, applicati **insieme** (atomico).

    - **Locale** — catalogo e testo neutro sono in casa: nessuna rete.
    - **Deterministico** — l'archetipo di default è *designato* (non pescato) e la
      rarità è la **minima ammessa** (scelta deterministica): il fallback **non
      consuma il seed stream del gioco** (F-13, §8). Niente RNG qui.
    """
    archetipo = budget.archetipo_default
    grado = min(budget.gradi_ammessi, key=rango_grado)  # deterministico
    entita = EntitaGenerata(
        archetipo=archetipo,
        grado=grado,
        blocchi=[],
        nome=NOME_NEUTRO,
        descrizione=DESCRIZIONE_NEUTRA,
    )
    turno = TurnoNarrazione(
        prosa=PROSA_NEUTRA,
        entita=entita,
        opzioni=list(MENU_FISSO),
        durata=Durata.TURNO,
    )
    # In-budget per costruzione; ripassa per il gate per coerenza (e clamp d'ingresso).
    validato = valida_turno(turno, budget, ingresso_combattimento=ingresso_combattimento)
    assert validato is not None, "il fallback deve essere in-budget per costruzione"
    return RisultatoTurno(turno=validato, budget=budget, fallback=True, anomala=budget.anomala)


# --- Socket: un verbo, politica selezionata dallo schema (G-19, F §5.1) -------

# Politica di retry PER SCHEMA (F §5.1): la narrazione (gating, atomica) ritenta;
# tutto il resto — prosa, ideazione, inquadramenti: non-gating — fallisce in fretta.
# Default sicuro: uno schema non registrato prende 0 retry.
POLICY_RETRY: dict[type, int] = {TurnoNarrazione: RETRY_NARRAZIONE}


async def _chiama_con_policy(provider, prompt: str, schema, sistema: str = ""):
    """Chiama `genera` col numero di tentativi selezionato dallo SCHEMA (F §5.1).

    Narrazione → ritenta; modalità-prosa/stadi non-gating → falliscono in fretta. È
    **il motore** a decidere, perché è lui che sa *che tipo* di chiamata è (ha scelto
    prompt e schema). `sistema` = prefisso statico separato (F §7: il trasporto può
    marcarlo per il prompt caching)."""
    tentativi = POLICY_RETRY.get(schema, RETRY_PROSA)
    for _ in range(tentativi + 1):
        candidato = await provider.genera(prompt, schema, sistema=sistema)
        if candidato is not None:
            return candidato
    return None


async def genera_prosa(provider, prompt: str, *, sistema: str = "") -> str | None:
    """Chiamata di sola prosa (flavor, showrunner, `Altro`-MVP): STESSO verbo `genera`
    con schema banale `Flavor` (F §5, G-19). Cosmetica: **può mancare** (F §5.1).

    Non tocca mai lo stato meccanico (è prosa, non `TurnoNarrazione`): è il confine
    duro di FNC §5.6 reso strutturale. Se fallisce, ritorna `None` e il chiamante
    degrada a una continuazione neutra — senza bloccare la risoluzione (non-gating,
    G-22).
    """
    candidato = await _chiama_con_policy(provider, prompt, Flavor, sistema)
    return candidato.testo if candidato is not None else None


async def procura_turno(
    provider,
    budget: Budget,
    proiezione: SchedaProiezione,
    *,
    voce: str = "Il dungeon osserva.",
    ingresso_combattimento: bool = False,
    sistema: str = "",
) -> RisultatoTurno:
    """Coroutine host-agnostica: prompt → `genera` (con policy) → gate → esito.

    NON muta l'ECS: ritorna un `RisultatoTurno` (validato o fallback). La
    materializzazione è un passo sincrono separato (`materializza_turno`), così una
    chiamata in volo non scrive nulla sul save (G-20, F §6.1).

    `None` (trasporto) e rifiuto-di-gate (dominio) **collassano sullo stesso fallback
    atomico** (F-8): non c'è esito "prosa valida ma entità no". Nessun secondo
    modello-giudice reinterpreta un fuori-budget (F-9): il fallback è il terminale.
    """
    prompt = costruisci_prompt(budget, proiezione, voce)
    candidato = await _chiama_con_policy(provider, prompt, TurnoNarrazione, sistema)

    validato = None
    if candidato is not None:
        validato = valida_turno(
            candidato, budget, ingresso_combattimento=ingresso_combattimento
        )

    if validato is None:
        return fallback_turno(budget, ingresso_combattimento=ingresso_combattimento)
    return RisultatoTurno(
        turno=validato, budget=budget, fallback=False, anomala=budget.anomala
    )


async def esegui_turno_narrazione(
    provider,
    *,
    livello: int,
    proiezione: SchedaProiezione,
    rng: random.Random,
    voce: str = "Il dungeon osserva.",
    ingresso_combattimento: bool = False,
) -> RisultatoTurno:
    """Turno completo: prepara il contesto (anomalia SEEDED) e procura l'esito.

    Comodità che lega `prepara_contesto` (tiro dell'anomalia, monte FNC §5.1) e
    `procura_turno`. Resta host-agnostica e non muta l'ECS.
    """
    budget = prepara_contesto(livello, rng)
    return await procura_turno(
        provider, budget, proiezione, voce=voce, ingresso_combattimento=ingresso_combattimento
    )


# --- Materializzazione: passo SINCRONO, alla risoluzione (stat DERIVATE) -------

def istanzia_entita(entita: EntitaGenerata, livello: int) -> int:
    """Istanzia l'entità validata nel World con le stat **derivate dal motore** (F-6).

    Le primarie escono dalla formula-madre `(profilo, grado, livello) → Primarie`:
    **stesso vettore** del protagonista e dei nemici, letto via `stat_eff` — una sola
    strada-stat (§16.4). Il PROFILO viene dal registry archetipi DELLA RUN (storici di
    calibrazione + asset congelati nella stagione — D1): l'entità è composta da dati,
    mai da rami per-archetipo. I blocchi scelti diventano componenti-status (la chimera
    è una somma di componenti, FNC §5.5), col **rango copiato dalla rarità** (G §4.3).
    Il `livello` (profondità) è legato qui, dopo il gate — l'AI non lo ha emesso (G-17).
    """
    profilo = registry_archetipi_correnti()[entita.archetipo]  # post-gate: sempre presente
    # RECLUTAMENTO (D5): col `riferimento` si materializza QUEL mob del cast — il suo
    # override di profilo vince campo-per-campo, le sue mosse vincono sul repertorio
    # d'archetipo. Tutto dato → dato, mai un ramo per-mob nel codice.
    reclutato = mob_del_cast(entita.riferimento) if entita.riferimento else None
    if reclutato is not None:
        profilo = profilo_con_override(profilo, reclutato.override)
    primarie = Primarie(
        valori=primarie_da_archetipo(entita.archetipo, entita.grado, livello, profilo=profilo)
    )
    rango = rango_grado(entita.grado)

    # Repertorio: mosse del mob reclutato → dell'archetipo-asset → default del motore.
    attivo = archetipo_attivo(entita.archetipo)
    if reclutato is not None and reclutato.mosse:
        mosse = tuple(reclutato.mosse)
    elif attivo is not None and attivo.mosse:
        mosse = tuple(attivo.mosse)
    else:
        mosse = MOSSE_DEFAULT

    componenti: list[object] = [
        EntitaMob(
            archetipo=entita.archetipo,
            grado=entita.grado,
            nome=entita.nome,
            descrizione=entita.descrizione,
            livello=livello,
        ),
        primarie,
        # Seam gear per-entità: le chiavi vengono dal profilo (dato), mai da lookup
        # per-archetipo nel codice.
        Corredo(armatura=profilo.armatura, taglia=profilo.taglia, arma=profilo.arma),
        # Le mosse che il mob porta (dato nel componente; il system le esegue).
        Repertorio(mosse=mosse),
    ]
    resistenze = {t: v for t, v in profilo.resistenze.items() if v != 0}
    if resistenze:  # assenza = identità DT-6: nessun Resistenze se il profilo è neutro
        fonte = f"archetipo:{entita.archetipo}"  # tag di dominio stabile (mai id esper)
        componenti.append(Resistenze(voci=[
            ResistenzaMod(contro=tipo, valore=valore, fonte=fonte)
            for tipo, valore in resistenze.items()
        ]))
    for blocco in entita.blocchi:
        cls = REGISTRY_BLOCCHI[blocco]
        # INNATO: capacità del mob (lo slime È velenoso), non afflizione — non
        # scade, non danneggia il portatore; agisce sul colpo o come passiva.
        componenti.append(cls(rango=rango, durata=DURATA_BLOCCO_DEFAULT, innato=True))

    return esper.create_entity(*componenti)


def materializza_turno(risultato: RisultatoTurno, bus=None) -> int:
    """Applica l'esito al World (passo sincrono, alla risoluzione del turno).

    Istanzia l'entità validata con le stat derivate; se il budget era anomalo,
    pubblica `AnomalyTriggered` sul bus al reveal, perché lo showrunner la narri
    (F §4.3, FNC §5.5/§8) — fire-and-forget, read-only. Ritorna l'id dell'entità.
    """
    ent = istanzia_entita(risultato.turno.entita, risultato.budget.livello)
    if bus is not None and risultato.anomala:
        bus.pubblica(AnomalyTriggered(entita=ent))
    return ent


# --- Disimpegno: prova su stat PRIMA di ingaggiare (FNC §5.3) ------------------

def tenta_disimpegno(destrezza: int, classe, rng: random.Random) -> bool:
    """Disimpegno in NARRAZIONE: una prova su stat *prima* di ingaggiare. Il **motore
    tira** (seeded); se riesce, il combattimento NON si apre (FNC §5.3).

    Distinto dalla *fuga dal combattimento* a scontro iniziato (FNC §4): qui non c'è
    ancora nessuno scontro da cui fuggire. Riusa la meccanica delle prove (G §7).
    """
    return risolvi_prova(destrezza, classe, rng)


# --- Confine narrazione→combattimento: EncounterStarted al tick (G-25) ---------

def ingaggia_combattimento(
    bus,
    *,
    nemici: list[SpecNemico] | None = None,
    seed: int,
    arruolate: list[int] | None = None,
) -> int:
    """Emette `EncounterStarted` al **confine di tick**, dopo che l'incontro è stato
    composto in NARRAZIONE (G §5.1, G-25).

    La composizione (il `PianoIncontro`) è dati a monte: **nessuna entità di
    combattimento è materializzata qui** — lo spawn avviene nell'handler di
    `EncounterStarted` (combattimento.py), *dopo* il flip a COMBATTIMENTO. Ordine
    fissato: composizione in narrazione → gate (clamp `durata=TURNO`) →
    `EncounterStarted` → flip. `arruolate` = entità già vive (il reveal della scena)
    da arruolare col loro profilo calibrato. Ritorna l'entità-incontro.
    """
    enc = esper.create_entity(
        PianoIncontro(nemici=list(nemici or []), seed=seed, arruolate=list(arruolate or []))
    )
    bus.pubblica(EncounterStarted(entita=enc))
    return enc
