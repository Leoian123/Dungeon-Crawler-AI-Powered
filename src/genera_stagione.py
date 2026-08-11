"""«Genera stagione» — l'authoring AI del piano-mondo (strumento, NON gioco).

Il momento in cui l'AI si fa carico del grosso del lavoro (decisione utente
2026-08-10): genera i BOSS dei tier nominati (provincia, città), le TABELLE
procedurali (distretto/quartiere) e le tabelle di SPAWN di un piano-mondo, come
chiamate a parte — authoring-time, mai runtime di gioco. Il motore resta il
gate: ogni item passa dai lint esistenti (slug, archetipo nel budget, mosse
note, blocchi ammessi) e il risultato è validato con `risolvi_stagione` PRIMA
di toccare la libreria. Un item respinto viene SCARTATO E RIPORTATO (umano nel
loop): in authoring non esiste fallback-contenuto.

Zero numeri dall'AI, anche qui: il boss dichiara il TIER, il grado lo deriva il
motore (`GRADO_DA_TIER`, simmetria 6↔6); i profili restano della calibrazione.

Uso (dalla radice del repo, PYTHONPATH="src;vendor"):

    python -m genera_stagione                 # dry-run: genera e RIPORTA, zero scritture
    python -m genera_stagione --applica       # scrive mob + piano nel repo (il diff git
                                              # È la promozione umana)
    python -m genera_stagione --provincia 10 --citta 40
    python -m genera_stagione --fake          # smoke offline (provider muto: 0 generati)

Pattern `banco_nemici`: stdlib + composition root; i backend arrivano da
`provider.root.scegli_corsie` e il Master-Engine li riceve PER CORSIA — così la
`Corsia.FORTE` dichiarata dalle rotte authoring seleziona davvero il modello forte.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from contracts import (
    BossGenerato,
    LottoBossGenerati,
    MobAsset,
    TabellaProceduraleGen,
    TabellaSpawnGenerata,
    TierTerritorio,
)
from main import (
    DIRECTORY_CONTENUTI,
    carica_asset,
    mosse_note_authoring,
    risolvi_stagione,
)
from motore import Corsia, GRADO_DA_TIER, MasterEngine, motivi_fuori_budget

STAGIONE_DEFAULT_SLUG = "stagione-1"

# I tier che il comando genera come ROSTER nominato (il PIANO e il PAESE sono
# canone autorato a mano: il comando non li tocca mai).
_TIER_GENERABILI = (TierTerritorio.PROVINCIA, TierTerritorio.CITTA)
_LOTTO = 5  # boss per chiamata: lotti piccoli degradano bene


# --- Contesto e prompt (la voce della stagione + il canone come few-shot) -------

def contesto_prompt(stagione, piano) -> str:
    """Il contesto condiviso di ogni chiamata di authoring: voce della stagione,
    tema del piano, canone come ESEMPLARI, vocabolari chiusi."""
    righe = [
        f"[stagione] «{stagione.titolo}» — {stagione.tagline}",
        *(f"[stagione/stile] {r}" for r in stagione.stile),
        f"[piano] «{piano.titolo}» — {piano.tema}",
        *(f"[piano/stile] {r}" for r in piano.stile),
    ]
    if piano.lore:
        righe.append(f"[piano/lore] {piano.lore}")
    territorio = piano.territorio
    if territorio is not None:
        for tier, roster in territorio.boss.items():
            for mob in roster:
                righe.append(
                    f"[canone/{tier.value}] {mob.nome} ({mob.archetipo}): "
                    f"{mob.descrizione}"
                )
    righe += [
        "[vocabolario/archetipi] " + ", ".join(piano.budget.archetipi),
        "[vocabolario/blocchi] " + (", ".join(b.value for b in piano.budget.blocchi) or "nessuno"),
        "[vocabolario/mosse] " + ", ".join(sorted(mosse_note_authoring())),
        "[regole] Slug kebab-case minuscolo, unico. NIENTE numeri di gioco: il "
        "grado lo impone il tier, i profili la calibrazione. Ogni boss è "
        "un'epoca storica o un cult su non-morti andato a male: nome memorabile, "
        "descrizione tagliente, prosa_stanza = la sua scena (regia, 3-6 frasi).",
    ]
    return "\n".join(righe)


def prompt_lotto_boss(tier: TierTerritorio, n: int, esclusi: set[str],
                      respinti_prima: tuple[str, ...] = ()) -> str:
    """Il compito di UN lotto. Solo le parti DINAMICHE (vietati, feedback):
    il contesto condiviso viaggia in `sistema=` — byte-identico per tutta la
    sessione, così il prompt caching del backend lavora davvero."""
    vietati = f" Slug già usati (vietati): {', '.join(sorted(esclusi))}." if esclusi else ""
    righe = [
        f"[compito] Genera {n} boss di {tier.value.upper()} per questo piano "
        f"(campo `tier` = \"{tier.value}\" per TUTTI).{vietati} Ognuno con la sua "
        "epoca/citazione, mai due simili nel lotto.",
    ]
    if respinti_prima:
        righe.append(
            "[respinti] Nel giro precedente sono stati SCARTATI: "
            + "; ".join(respinti_prima) + ". Correggi questi errori."
        )
    return "\n".join(righe)


def prompt_tabella(tier: TierTerritorio, respinti_prima: tuple[str, ...] = ()) -> str:
    righe = [
        f"[compito] Genera la TABELLA PROCEDURALE dei boss di {tier.value.upper()}: "
        "8-12 `nomi` (titoli da boss rionale, epoche/cult diversi), 8-12 `gimmick` "
        "(una frase di carattere ciascuno), e gli `archetipi` ammessi (dal "
        "vocabolario). Il motore combinerà nomi × gimmick × archetipi, seeded.",
    ]
    if respinti_prima:
        righe.append(
            "[respinti] La proposta precedente è stata SCARTATA: "
            + "; ".join(respinti_prima) + ". Correggi questi errori."
        )
    return "\n".join(righe)


def prompt_spawn(tier: TierTerritorio, disponibili: list[str],
                 respinti_prima: tuple[str, ...] = ()) -> str:
    righe = [
        f"[mob-disponibili] {', '.join(disponibili)}",
        f"[compito] Componi la TABELLA DI SPAWN del tier {tier.value.upper()}: "
        "scegli SOLO slug dai mob-disponibili e assegna a ciascuno una frequenza "
        "(comune|insolito|raro). I comuni danno il tono, i rari sorprendono.",
    ]
    if respinti_prima:
        righe.append(
            "[respinti] La proposta precedente è stata SCARTATA: "
            + "; ".join(respinti_prima) + ". Correggi questi errori."
        )
    return "\n".join(righe)


# --- Gate per item (i lint del motore, mai fiducia) -----------------------------

def gate_boss(b: BossGenerato, piano, tier: TierTerritorio,
              slug_visti: set[str], *, ufficiali: Path | None,
              locali: Path | None, sovrascrivi: bool) -> list[str]:
    errori: list[str] = []
    if b.tier is not tier:
        errori.append(f"{b.slug}: tier {b.tier.value}, atteso {tier.value}")
    # Regole condivise coi gate runtime (una sola implementazione): grado saltato
    # (lo impone il tier), registry della run saltato (nessuna run attiva in
    # authoring — il binding lo verifica il gate finale `risolvi_stagione`).
    errori += [
        f"{b.slug}: {motivo}"
        for motivo in motivi_fuori_budget(
            b.archetipo, None, b.blocchi,
            archetipi_ammessi=frozenset(piano.budget.archetipi),
            gradi_ammessi=None,
            blocchi_ammessi=frozenset(piano.budget.blocchi),
            mosse=b.mosse,
            con_registry=False,
            mosse_ammesse=mosse_note_authoring(ufficiali, locali),
        )
    ]
    if b.slug in slug_visti:
        errori.append(f"{b.slug}: slug duplicato nel batch")
    elif not sovrascrivi and carica_asset(
        "mob", b.slug, ufficiali=ufficiali, locali=locali
    ) is not None:
        errori.append(f"{b.slug}: slug già in libreria (usa --sovrascrivi)")
    if not b.prosa_stanza.strip():
        errori.append(f"{b.slug}: prosa_stanza vuota")
    return errori


def boss_a_mob_asset(b: BossGenerato) -> MobAsset:
    """BossGenerato → MobAsset: il GRADO lo impone il tier (mai l'AI)."""
    descrizione = b.descrizione
    dettagli = "; ".join(x for x in (b.aspetto, b.tratto) if x)
    if dettagli:
        descrizione = f"{descrizione} {dettagli}".strip()
    return MobAsset(
        slug=b.slug,
        versione=1,
        tags=["nascondino", "non-morti", f"boss-di-{b.tier.value}", "generato"],
        nome=b.nome,
        archetipo=b.archetipo,
        grado=GRADO_DA_TIER[b.tier],
        blocchi=list(b.blocchi),
        descrizione=descrizione,
        prosa_stanza=b.prosa_stanza,
        durata="un_pochino",
        mosse=list(b.mosse),
    )


# --- Il batch (giri paralleli + top-up bounded, ~12-16 chiamate FORTE) -----------

_GIRI_EXTRA = 1  # un solo giro di top-up per i respinti: bounded, mai loop infinito


def _gate_tabella(tabella: TabellaProceduraleGen, tier: TierTerritorio,
                  piano) -> str | None:
    """Motivo di scarto di una tabella procedurale, `None` = passa."""
    if tabella.tier is not tier:
        return f"tabella {tier.value}: tier sbagliato ({tabella.tier.value})"
    fuori = [a for a in tabella.archetipi if a not in set(piano.budget.archetipi)]
    if fuori:
        return f"tabella {tier.value}: archetipi fuori budget: {', '.join(fuori)}"
    return None


def _gate_spawn(proposta: TabellaSpawnGenerata, tier: TierTerritorio,
                disponibili: list[str]) -> str | None:
    """Motivo di scarto di una tabella di spawn, `None` = passa."""
    fuori = [v.mob for v in proposta.voci if v.mob not in set(disponibili)]
    if fuori:
        return f"spawn {tier.value}: mob inesistenti: {', '.join(fuori)}"
    return None


async def genera_roster(
    engine: MasterEngine, stagione, piano, *,
    n_per_tier: dict[TierTerritorio, int],
    ufficiali: Path | None = None, locali: Path | None = None,
    sovrascrivi: bool = False,
):
    """Il batch di authoring. Ritorna (mob_accettati, tabelle, spawn, per_tier, respinti).

    Le chiamate di un giro partono INSIEME (`gather`: l'I/O è il collo); il gate
    resta seriale post-gather, nell'ordine dei task — è lì che gli slug in
    collisione tra lotti paralleli vengono deduplicati. Un giro di TOP-UP
    (bounded, `_GIRI_EXTRA`) rigenera i mancanti col motivo dello scarto nel
    prompt; ogni scarto resta comunque RIPORTATO (mai fallback-contenuto).
    Il contesto condiviso viaggia in `sistema=` (byte-identico per tutta la
    sessione: prompt caching); i dinamici stanno SOLO nel prompt utente.
    """
    contesto = contesto_prompt(stagione, piano)
    mob_accettati: list[MobAsset] = []
    per_tier: dict[TierTerritorio, list[str]] = {t: [] for t in _TIER_GENERABILI}
    respinti: list[str] = []
    slug_visti: set[str] = set()

    # --- Boss nominati: giri di lotti paralleli, top-up per i tier sotto quota ---
    feedback: dict[TierTerritorio, tuple[str, ...]] = {}
    for _ in range(1 + _GIRI_EXTRA):
        tier_dei_lotti: list[TierTerritorio] = []
        prompts: list[str] = []
        for tier in _TIER_GENERABILI:
            mancanti = n_per_tier.get(tier, 0) - len(per_tier[tier])
            for inizio in range(0, mancanti, _LOTTO):
                tier_dei_lotti.append(tier)
                prompts.append(prompt_lotto_boss(
                    tier, min(_LOTTO, mancanti - inizio), slug_visti,
                    feedback.get(tier, ()),
                ))
        if not tier_dei_lotti:
            break
        lotti = await asyncio.gather(*(
            engine.genera("authoring.boss", p, sistema=contesto) for p in prompts
        ))
        motivi_giro: dict[TierTerritorio, list[str]] = {}
        for tier, lotto in zip(tier_dei_lotti, lotti):
            if lotto is None:
                # Trasporto: nessun feedback al modello (non ha sbagliato lui);
                # il tier resta sotto quota e il giro dopo lo riprova da solo.
                respinti.append(f"lotto {tier.value}: chiamata degradata (trasporto)")
                continue
            for b in lotto.boss:
                if len(per_tier[tier]) >= n_per_tier.get(tier, 0):
                    break  # quota piena: gli extra di un lotto largo non entrano
                errori = gate_boss(
                    b, piano, tier, slug_visti,
                    ufficiali=ufficiali, locali=locali, sovrascrivi=sovrascrivi,
                )
                if errori:
                    respinti.extend(errori)
                    motivi_giro.setdefault(tier, []).extend(errori)
                    continue
                slug_visti.add(b.slug)
                mob_accettati.append(boss_a_mob_asset(b))
                per_tier[tier].append(b.slug)
        feedback = {t: tuple(m) for t, m in motivi_giro.items()}

    # --- Tabelle procedurali: in parallelo, un retry col motivo per le respinte ---
    tabelle: list[TabellaProceduraleGen] = []
    da_fare: dict[TierTerritorio, tuple[str, ...]] = {
        t: () for t in (TierTerritorio.DISTRETTO, TierTerritorio.QUARTIERE)
    }
    for _ in range(1 + _GIRI_EXTRA):
        if not da_fare:
            break
        ordine = list(da_fare)
        proposte = await asyncio.gather(*(
            engine.genera("authoring.tabella", prompt_tabella(t, da_fare[t]),
                          sistema=contesto)
            for t in ordine
        ))
        prossimo: dict[TierTerritorio, tuple[str, ...]] = {}
        for tier, tabella in zip(ordine, proposte):
            if tabella is None:
                respinti.append(f"tabella {tier.value}: chiamata degradata")
                prossimo[tier] = ()  # trasporto: si riprova senza feedback
                continue
            motivo = _gate_tabella(tabella, tier, piano)
            if motivo is None:
                tabelle.append(tabella)
            else:
                respinti.append(motivo)
                prossimo[tier] = (motivo,)
        da_fare = prossimo

    # --- Spawn: dipendono dai boss accettati, stessi giri delle tabelle ----------
    disponibili = sorted(
        {m.slug for m in piano.cast} | {m.slug for m in mob_accettati}
    )
    spawn: list[TabellaSpawnGenerata] = []
    da_fare = {t: () for t in (TierTerritorio.QUARTIERE, TierTerritorio.CITTA)}
    for _ in range(1 + _GIRI_EXTRA):
        if not da_fare:
            break
        ordine = list(da_fare)
        proposte = await asyncio.gather(*(
            engine.genera("authoring.spawn", prompt_spawn(t, disponibili, da_fare[t]),
                          sistema=contesto)
            for t in ordine
        ))
        prossimo = {}
        for tier, proposta in zip(ordine, proposte):
            if proposta is None:
                respinti.append(f"spawn {tier.value}: chiamata degradata")
                prossimo[tier] = ()
                continue
            motivo = _gate_spawn(proposta, tier, disponibili)
            if motivo is None:
                spawn.append(proposta)
            else:
                respinti.append(motivo)
                prossimo[tier] = (motivo,)
        da_fare = prossimo

    return mob_accettati, tabelle, spawn, per_tier, respinti


# --- Fabbrica (stile BL3, in piccolo): l'AI scrive le PARTI, il motore conia -----

def prompt_fabbrica(stagione, respinti_prima: tuple[str, ...] = ()) -> str:
    from contracts import CategoriaArmatura, Fascia, SedeAccessorio, Taglia, TipoDanno
    from contracts.proiezione import SLOT_ARMATURA

    righe = [
        "[vocabolario/tipi] armatura, arma, accessorio",
        "[vocabolario/slot-armatura] " + ", ".join(s.value for s in SLOT_ARMATURA),
        "[vocabolario/categorie] " + ", ".join(c.value for c in CategoriaArmatura),
        "[vocabolario/taglie] " + ", ".join(t.value for t in Taglia),
        "[vocabolario/sedi] " + ", ".join(s.value for s in SedeAccessorio),
        "[vocabolario/fasce] " + ", ".join(f.value for f in Fascia),
        "[vocabolario/tipi-danno] " + ", ".join(
            t.value for t in TipoDanno if t.value != "generico"),
        "[compito] Scrivi la FABBRICA del loot di questo piano-mondo: le "
        "TABELLE-PARTI che il motore combinerà seeded a ogni drop (stile "
        "Borderlands, in piccolo). Servono: 5-10 `basi` (i corpi: nomi brevi "
        "tipo «Elmo», «Lama», con slot/categoria/sede coerenti al tipo), 4-8 "
        "`famiglie` (i produttori in-fiction: nome che chiude il nome composto "
        "tipo «del Becchino», una descrizione di carattere, 1-2 modificatori a "
        "fascia), 4-8 `affissi` (aggettivi tipo «Fumante»: o una resistenza "
        "tipata a fascia, o un modificatore). I nomi devono comporsi bene: "
        "«{base} {affisso} {famiglia}». NIENTE numeri: solo fasce ed enum.",
    ]
    if respinti_prima:
        righe.append(
            "[respinti] La proposta precedente è stata SCARTATA: "
            + "; ".join(respinti_prima) + ". Correggi questi errori."
        )
    return "\n".join(righe)


async def genera_fabbrica(
    engine: MasterEngine, stagione, *,
    ufficiali: Path | None = None, locali: Path | None = None,
    sovrascrivi: bool = False,
):
    """UNA fabbrica per la stagione (il validator di `FabbricaAsset` è il gate
    di forma; qui slug e collisioni). Ritorna (fabbrica|None, respinti)."""
    contesto = contesto_prompt(stagione, stagione.piani[0])
    respinti: list[str] = []
    feedback: tuple[str, ...] = ()
    for _ in range(1 + _GIRI_EXTRA):
        fabbrica = await engine.genera(
            "authoring.fabbrica", prompt_fabbrica(stagione, feedback),
            sistema=contesto,
        )
        if fabbrica is None:
            respinti.append("fabbrica: chiamata degradata (trasporto)")
            continue
        if not sovrascrivi and carica_asset(
            "fabbriche", fabbrica.slug, ufficiali=ufficiali, locali=locali
        ) is not None:
            motivo = f"{fabbrica.slug}: slug già in libreria (usa --sovrascrivi)"
            respinti.append(motivo)
            feedback = (motivo,)
            continue
        return fabbrica, respinti
    return None, respinti


# --- Status (T4c, variante PROPOSTA): l'AI propone, l'umano fa i «3 tocchi» ------

def prompt_lotto_status(n: int, esclusi: set[str],
                        respinti_prima: tuple[str, ...] = ()) -> str:
    from contracts import Blocco

    vietati = f" Nomi già usati o esistenti (vietati): {', '.join(sorted(esclusi))}." if esclusi else ""
    righe = [
        "[status-esistenti] " + ", ".join(b.value for b in Blocco),
        f"[compito] PROPONI {n} STATUS nuovi a tema (vocabolario, non contenuto "
        f"di scena).{vietati} Per ciascuno: nome slug, descrizione del carattere, "
        "valenza (benefico|dannoso|neutro), trasmissibile (passa col colpo?), "
        "tick (ferisce|cura|nessuno — coerente con la valenza) e le fasce. "
        "Sono PROPOSTE per la promozione umana: niente doppioni concettuali "
        "degli esistenti.",
    ]
    if respinti_prima:
        righe.append(
            "[respinti] Nel giro precedente sono stati SCARTATI: "
            + "; ".join(respinti_prima) + ". Correggi questi errori."
        )
    return "\n".join(righe)


def gate_status(s, gia_visti: set[str]) -> list[str]:
    """Gate di coerenza delle proposte: nome non collidente col vocabolario
    esistente, valenza↔tick coerente. (La composizione è già forma: schema.)"""
    from contracts import Blocco

    errori: list[str] = []
    if s.nome in {b.value for b in Blocco}:
        errori.append(f"{s.nome}: collide con uno status esistente")
    if s.nome in gia_visti:
        errori.append(f"{s.nome}: duplicato nel batch")
    coerenza = {"benefico": "cura", "dannoso": "ferisce"}
    atteso = coerenza.get(s.valenza)
    if atteso is not None and s.tick not in (atteso, "nessuno"):
        errori.append(f"{s.nome}: tick {s.tick} incoerente con valenza {s.valenza}")
    if s.valenza == "neutro" and s.tick != "nessuno":
        errori.append(f"{s.nome}: uno status neutro non muove HP")
    return errori


async def genera_status(
    engine: MasterEngine, stagione, *, quanti: int, directory_proposte: Path,
):
    """Il batch delle PROPOSTE di status: il file scritto è il brief per i
    «3 tocchi» umani (contenuti_locali/proposte/status/), MAI la libreria —
    per costruzione non esiste un --applica per gli status. Ritorna
    (percorsi_scritti, respinti)."""
    contesto = contesto_prompt(stagione, stagione.piani[0])
    accettati: list = []
    respinti: list[str] = []
    visti: set[str] = set()
    feedback: tuple[str, ...] = ()

    for _ in range(1 + _GIRI_EXTRA):
        mancanti = quanti - len(accettati)
        if mancanti <= 0:
            break
        lotto = await engine.genera(
            "authoring.status", prompt_lotto_status(mancanti, visti, feedback),
            sistema=contesto,
        )
        if lotto is None:
            respinti.append("lotto status: chiamata degradata (trasporto)")
            continue
        motivi_giro: list[str] = []
        for s in lotto.status:
            if len(accettati) >= quanti:
                break
            errori = gate_status(s, visti)
            if errori:
                respinti.extend(errori)
                motivi_giro.extend(errori)
                continue
            visti.add(s.nome)
            accettati.append(s)
        feedback = tuple(motivi_giro)

    percorsi: list[Path] = []
    for s in accettati:
        percorso = directory_proposte / f"{s.nome}.json"
        _scrivi_json(percorso, json.loads(s.model_dump_json()))
        percorsi.append(percorso)
    return percorsi, respinti


# --- Mosse (T3b): il generatore delle meccaniche (composizione di primitivi) -----

_LOTTO_MOSSE = 6


def prompt_lotto_mosse(stagione, n: int, esclusi: set[str],
                       respinti_prima: tuple[str, ...] = ()) -> str:
    """Il compito di UN lotto di mosse: primitivi chiusi, fasce, vocabolari.
    Zero numeri per costruzione (lo schema non ha dove metterli)."""
    from contracts import (
        FasciaCosto,
        FasciaPotenza,
        FasciaRicarica,
        FasciaRischio,
        TipoDanno,
    )

    vietati = f" Slug già usati (vietati): {', '.join(sorted(esclusi))}." if esclusi else ""
    blocchi = sorted({b.value for p in stagione.piani for b in p.budget.blocchi})
    righe = [
        "[vocabolario/primitivi] danno, applica_status, danno_variabile",
        "[vocabolario/tipi-danno] " + ", ".join(
            t.value for t in TipoDanno if t.value != "generico"),
        "[vocabolario/blocchi] " + (", ".join(blocchi) or "nessuno"),
        "[vocabolario/potenza] " + ", ".join(f.value for f in FasciaPotenza),
        "[vocabolario/costo] " + ", ".join(f.value for f in FasciaCosto),
        "[vocabolario/ricarica] " + ", ".join(f.value for f in FasciaRicarica),
        "[vocabolario/rischio] " + ", ".join(f.value for f in FasciaRischio),
        f"[compito] Componi {n} MOSSE di combattimento a tema (etichetta "
        f"diegetica memorabile).{vietati} Regole di composizione: ESATTAMENTE un "
        "primitivo di danno per mossa; `applica_status` (opzionale) DOPO il "
        "danno e con un blocco del vocabolario; `azzardo: true` SOLO se usi "
        "danno_variabile. Una mossa costosa/lunga deve valere il prezzo.",
    ]
    if respinti_prima:
        righe.append(
            "[respinti] Nel giro precedente sono stati SCARTATI: "
            + "; ".join(respinti_prima) + ". Correggi questi errori."
        )
    return "\n".join(righe)


def gate_mossa(m, stagione, slug_visti: set[str], *, ufficiali: Path | None,
               locali: Path | None, sovrascrivi: bool):
    """Gate per item delle mosse autorate: la CONVERSIONE a `MossaAsset` è il
    gate di composizione (PMF-6.4, validator unico); qui i check di contesto.
    Ritorna (asset|None, errori)."""
    from contracts import MossaAsset

    errori: list[str] = []
    if m.slug in slug_visti:
        errori.append(f"{m.slug}: slug duplicato nel batch")
    elif not sovrascrivi and carica_asset(
        "mosse", m.slug, ufficiali=ufficiali, locali=locali
    ) is not None:
        errori.append(f"{m.slug}: slug già in libreria (usa --sovrascrivi)")
    blocchi_stagione = {b for p in stagione.piani for b in p.budget.blocchi}
    for e in m.effetti:
        if e.blocco is not None and e.blocco not in blocchi_stagione:
            errori.append(
                f"{m.slug}: blocco {e.blocco.value} fuori dai budget della stagione")
    try:
        asset = MossaAsset(
            slug=m.slug, versione=1, tags=["generato"],
            etichetta=m.etichetta, effetti=list(m.effetti),
            costo=m.costo, ricarica=m.ricarica, azzardo=m.azzardo,
        )
    except ValueError as errore:
        errori.append(f"{m.slug}: {errore}")
        return None, errori
    return (asset if not errori else None), errori


async def genera_mosse(
    engine: MasterEngine, stagione, *, quanti: int,
    ufficiali: Path | None = None, locali: Path | None = None,
    sovrascrivi: bool = False,
):
    """Il batch mosse: giri paralleli + top-up bounded (pattern boss).
    Ritorna (mosse_accettate, respinti)."""
    contesto = contesto_prompt(stagione, stagione.piani[0])
    accettate: list = []
    respinti: list[str] = []
    slug_visti: set[str] = set()
    feedback: tuple[str, ...] = ()

    for _ in range(1 + _GIRI_EXTRA):
        mancanti = quanti - len(accettate)
        if mancanti <= 0:
            break
        prompts = [
            prompt_lotto_mosse(
                stagione, min(_LOTTO_MOSSE, mancanti - inizio), slug_visti, feedback,
            )
            for inizio in range(0, mancanti, _LOTTO_MOSSE)
        ]
        lotti = await asyncio.gather(*(
            engine.genera("authoring.mossa", p, sistema=contesto) for p in prompts
        ))
        motivi_giro: list[str] = []
        for lotto in lotti:
            if lotto is None:
                respinti.append("lotto mosse: chiamata degradata (trasporto)")
                continue
            for m in lotto.mosse:
                if len(accettate) >= quanti:
                    break
                asset, errori = gate_mossa(
                    m, stagione, slug_visti,
                    ufficiali=ufficiali, locali=locali, sovrascrivi=sovrascrivi,
                )
                if asset is None:
                    respinti.extend(errori)
                    motivi_giro.extend(errori)
                    continue
                slug_visti.add(asset.slug)
                accettate.append(asset)
        feedback = tuple(motivi_giro)

    return accettate, respinti


# --- Oggetti (T2a): il generatore del pool di loot -------------------------------

_LOTTO_OGGETTI = 6  # come i boss: lotti piccoli degradano bene


def prompt_lotto_oggetti(stagione, n: int, esclusi: set[str],
                         respinti_prima: tuple[str, ...] = ()) -> str:
    """Il compito di UN lotto di oggetti: vocabolari chiusi (slot d'armatura,
    categorie, taglie, sedi, fasce, gradi coperti dai piani, mosse note) e
    dinamici (vietati, feedback). Zero numeri: lo schema non ha dove metterli."""
    from contracts import CategoriaArmatura, Fascia, SedeAccessorio, Taglia
    from contracts.proiezione import SLOT_ARMATURA

    vietati = f" Slug già usati (vietati): {', '.join(sorted(esclusi))}." if esclusi else ""
    gradi = sorted(
        {g.value for p in stagione.piani for g in p.budget.gradi},
    )
    righe = [
        "[vocabolario/tipi] armatura, arma, accessorio",
        "[vocabolario/slot-armatura] " + ", ".join(s.value for s in SLOT_ARMATURA),
        "[vocabolario/categorie] " + ", ".join(c.value for c in CategoriaArmatura),
        "[vocabolario/taglie] " + ", ".join(t.value for t in Taglia),
        "[vocabolario/sedi] " + ", ".join(s.value for s in SedeAccessorio),
        "[vocabolario/fasce] " + ", ".join(f.value for f in Fascia),
        "[vocabolario/gradi] " + ", ".join(gradi),
        "[vocabolario/mosse] " + ", ".join(sorted(mosse_note_authoring())),
        f"[compito] Genera {n} OGGETTI di equipaggiamento per questo piano-mondo "
        f"(bottino a tema).{vietati} Mischia i tipi (armature su slot diversi, "
        "un'arma, accessori), copri più gradi; le mosse (opzionali) solo sugli "
        "accessori e SOLO dal vocabolario. NIENTE numeri: scegli fasce ed enum, "
        "i valori li deriva il motore.",
    ]
    if respinti_prima:
        righe.append(
            "[respinti] Nel giro precedente sono stati SCARTATI: "
            + "; ".join(respinti_prima) + ". Correggi questi errori."
        )
    return "\n".join(righe)


def autorato_a_oggetto_asset(o) -> "OggettoAsset":
    """OggettoAutorato → OggettoAsset: nessun numero (li deriverà il motore);
    la coerenza di forma la impone il validator dell'asset (un candidato
    incoerente esplode QUI, e il gate lo riporta come motivo)."""
    from contracts import ModificatoreDati, OggettoAsset

    return OggettoAsset(
        slug=o.slug,
        versione=1,
        tags=["generato", "loot"],
        nome=o.nome,
        descrizione=o.descrizione,
        tipo=o.tipo,
        grado=o.grado,
        slot=o.slot,
        categoria=o.categoria,
        taglia=o.taglia,
        sede=o.sede,
        mosse=list(o.mosse),
        modificatori=[
            ModificatoreDati(stat=m.stat, fascia=m.fascia) for m in o.modificatori
        ],
    )


def gate_oggetto(o, stagione, slug_visti: set[str], *, ufficiali: Path | None,
                 locali: Path | None, sovrascrivi: bool,
                 mosse_extra: frozenset = frozenset()):
    """Gate per item degli oggetti autorati. Ritorna (asset|None, errori)."""
    from motore import lint_oggetto

    errori: list[str] = []
    if o.slug in slug_visti:
        errori.append(f"{o.slug}: slug duplicato nel batch")
    elif not sovrascrivi and carica_asset(
        "oggetti", o.slug, ufficiali=ufficiali, locali=locali
    ) is not None:
        errori.append(f"{o.slug}: slug già in libreria (usa --sovrascrivi)")
    gradi_stagione = {g for p in stagione.piani for g in p.budget.gradi}
    if o.grado not in gradi_stagione:
        errori.append(f"{o.slug}: grado {o.grado.value} fuori dai piani della stagione")
    try:
        asset = autorato_a_oggetto_asset(o)
    except ValueError as errore:
        errori.append(f"{o.slug}: {errore}")
        return None, errori
    errori.extend(lint_oggetto(
        asset,
        mosse_ammesse=mosse_note_authoring(ufficiali, locali) | mosse_extra,
    ))
    return (asset if not errori else None), errori


async def genera_oggetti(
    engine: MasterEngine, stagione, *, quanti: int,
    ufficiali: Path | None = None, locali: Path | None = None,
    sovrascrivi: bool = False, mosse_extra: frozenset = frozenset(),
):
    """Il batch oggetti: stessi giri paralleli + top-up bounded dei boss.
    Ritorna (oggetti_accettati, respinti)."""
    contesto = contesto_prompt(stagione, stagione.piani[0])
    accettati: list = []
    respinti: list[str] = []
    slug_visti: set[str] = set()
    feedback: tuple[str, ...] = ()

    for _ in range(1 + _GIRI_EXTRA):
        mancanti = quanti - len(accettati)
        if mancanti <= 0:
            break
        prompts = [
            prompt_lotto_oggetti(
                stagione, min(_LOTTO_OGGETTI, mancanti - inizio), slug_visti, feedback,
            )
            for inizio in range(0, mancanti, _LOTTO_OGGETTI)
        ]
        lotti = await asyncio.gather(*(
            engine.genera("authoring.oggetto", p, sistema=contesto) for p in prompts
        ))
        motivi_giro: list[str] = []
        for lotto in lotti:
            if lotto is None:
                respinti.append("lotto oggetti: chiamata degradata (trasporto)")
                continue
            for o in lotto.oggetti:
                if len(accettati) >= quanti:
                    break
                asset, errori = gate_oggetto(
                    o, stagione, slug_visti,
                    ufficiali=ufficiali, locali=locali, sovrascrivi=sovrascrivi,
                    mosse_extra=mosse_extra,
                )
                if asset is None:
                    respinti.extend(errori)
                    motivi_giro.extend(errori)
                    continue
                slug_visti.add(asset.slug)
                accettati.append(asset)
        feedback = tuple(motivi_giro)

    return accettati, respinti


# --- Applicazione: scritture atomiche + gate finale (risolvi_stagione) ----------

def _scrivi_json(percorso: Path, dati: dict) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    tmp = percorso.with_suffix(".tmp")
    tmp.write_text(json.dumps(dati, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(percorso)


def applica(
    slug_stagione: str, slug_piano: str, mob_nuovi, tabelle, spawn, per_tier,
    *, oggetti_nuovi=(), mosse_nuove=(), fabbrica_nuova=None,
    radice: Path | None = None, locali: Path | None = None,
) -> list[str]:
    """Scrive i mob e gli oggetti generati e il PianoAsset aggiornato nella
    libreria, con GATE FINALE `risolvi_stagione`: se la stagione aggiornata non
    risolve, ROLLBACK completo (l'authoring non lascia mai la libreria a metà).
    Gli oggetti entrano nel pool lasco della stagione (D-1: `oggetti` vuoto =
    tutta la libreria) senza toccare il file stagione. Ritorna gli errori
    (vuota = applicato)."""
    radice = radice or DIRECTORY_CONTENUTI
    piano_path = radice / "piani" / f"{slug_piano}.json"
    backup_piano = piano_path.read_text(encoding="utf-8")
    piano_dati = json.loads(backup_piano)
    territorio = piano_dati.get("territorio") or {}

    boss = dict(territorio.get("boss") or {})
    for tier, slugs in per_tier.items():
        if slugs:
            boss[tier.value] = list(dict.fromkeys(boss.get(tier.value, []) + slugs))
    if tabelle:
        territorio["procedurali"] = [
            json.loads(t.model_dump_json()) for t in tabelle
        ]
    if spawn:
        territorio["spawn"] = [json.loads(s.model_dump_json()) for s in spawn]
    territorio["boss"] = boss
    piano_dati["territorio"] = territorio

    scritti: list[Path] = []
    try:
        for mob in mob_nuovi:
            percorso = radice / "mob" / f"{mob.slug}.json"
            _scrivi_json(percorso, json.loads(mob.model_dump_json()))
            scritti.append(percorso)
        for mossa in mosse_nuove:
            percorso = radice / "mosse" / f"{mossa.slug}.json"
            _scrivi_json(percorso, json.loads(mossa.model_dump_json()))
            scritti.append(percorso)
        if fabbrica_nuova is not None:
            percorso = radice / "fabbriche" / f"{fabbrica_nuova.slug}.json"
            _scrivi_json(percorso, json.loads(fabbrica_nuova.model_dump_json()))
            scritti.append(percorso)
        for oggetto in oggetti_nuovi:
            percorso = radice / "oggetti" / f"{oggetto.slug}.json"
            _scrivi_json(percorso, json.loads(oggetto.model_dump_json()))
            scritti.append(percorso)
        _scrivi_json(piano_path, piano_dati)
        risolvi_stagione(slug_stagione, ufficiali=radice, locali=locali)  # gate finale
        return []
    except Exception as errore:
        piano_path.write_text(backup_piano, encoding="utf-8")
        for percorso in scritti:
            percorso.unlink(missing_ok=True)
        return [f"gate finale fallito, ROLLBACK completo: {errore}"]


# --- Entry point -----------------------------------------------------------------

def costruisci_parser() -> "argparse.ArgumentParser":
    """La CLI, uniforme al fratello `banco_nemici`. La chiave API resta SOLO
    nell'ambiente: nessun flag la tocca (PLK §4)."""
    import argparse

    p = argparse.ArgumentParser(
        prog="genera_stagione",
        description="Authoring AI del piano-mondo: dry-run di default, --applica scrive.",
    )
    p.add_argument("--provincia", type=int, default=10, help="boss di provincia da generare")
    p.add_argument("--citta", type=int, default=40, help="boss di città da generare")
    p.add_argument("--applica", action="store_true",
                   help="scrive mob + piano nel repo (il diff git è la promozione)")
    p.add_argument("--sovrascrivi", action="store_true",
                   help="accetta anche slug già in libreria")
    p.add_argument("--fake", action="store_true",
                   help="provider offline scriptato (smoke, 0 generati)")
    p.add_argument("--live", action="store_true",
                   help="esige il live (errore chiaro se manca chiave o SDK)")
    p.add_argument("--stagione", default=STAGIONE_DEFAULT_SLUG,
                   help="slug della stagione da risolvere")
    p.add_argument("--piano", default=None,
                   help="slug del piano da popolare (default: il primo della stagione)")
    p.add_argument("--oggetti", type=int, default=0,
                   help="oggetti di equipaggiamento da generare per il pool di loot")
    p.add_argument("--mosse", type=int, default=0,
                   help="mosse di combattimento da generare (composizione di primitivi)")
    p.add_argument("--status", type=int, default=0,
                   help="PROPOSTE di status da generare (brief per i 3 tocchi umani, "
                        "mai libreria: finiscono in contenuti_locali/proposte/status/)")
    p.add_argument("--fabbrica", action="store_true",
                   help="genera le tabelle-parti della fabbrica del loot procedurale")
    return p


def main(argv: list[str] | None = None) -> int:  # pragma: no cover (entry point)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    args = costruisci_parser().parse_args(sys.argv[1:] if argv is None else argv)

    stagione = risolvi_stagione(args.stagione)
    if args.piano is None:
        piano = stagione.piani[0]
    else:
        piano = next((p for p in stagione.piani if p.slug == args.piano), None)
        if piano is None:
            disponibili = ", ".join(p.slug for p in stagione.piani)
            print(f"[genera] piano '{args.piano}' non nella stagione "
                  f"(disponibili: {disponibili})")
            return 1
    if piano.territorio is None:
        print(f"[genera] il piano {piano.slug} non ha territorio: niente da generare")
        return 1

    from provider import CORSIE_DEFAULT, FakeProvider, ProfiloCorsia, scegli_corsie

    # Backend PER CORSIA, non composito per-schema: le rotte authoring dichiarano
    # `Corsia.FORTE` e qui quella dichiarazione arriva davvero al modello forte
    # (con `avvolgi` la corsia della rotta non avrebbe alcun effetto).
    # Profilo AUTHORING: stesso modello forte del gioco, ma timeout paziente —
    # un lotto di 5 boss con prosa è una risposta lunga, e il timeout da gioco
    # (30s, tarato sul turno) la uccideva a metà generazione.
    corsie_authoring = {
        "forte": ProfiloCorsia(modello=CORSIE_DEFAULT["forte"].modello,
                               max_tokens=4096, timeout=240.0),
        "veloce": CORSIE_DEFAULT["veloce"],
    }
    flags_provider = (["--fake"] if args.fake else []) + (["--live"] if args.live else [])
    corsie, etichetta, consumo = scegli_corsie(flags_provider, corsie=corsie_authoring)
    print(f"[genera] {etichetta}")
    if corsie is None:
        engine = MasterEngine.avvolgi(FakeProvider([]))  # --fake/offline: smoke a zero generazioni
    else:
        engine = MasterEngine({
            Corsia.FORTE: corsie["forte"], Corsia.VELOCE: corsie["veloce"],
        })

    n_per_tier = {
        TierTerritorio.PROVINCIA: args.provincia,
        TierTerritorio.CITTA: args.citta,
    }
    mob_nuovi, tabelle, spawn, per_tier, respinti = asyncio.run(genera_roster(
        engine, stagione, piano, n_per_tier=n_per_tier,
        sovrascrivi=args.sovrascrivi,
    ))
    proposte_status: list = []
    if args.status > 0:
        from main import DIRECTORY_CONTENUTI_LOCALI

        proposte_status, respinti_status = asyncio.run(genera_status(
            engine, stagione, quanti=args.status,
            directory_proposte=DIRECTORY_CONTENUTI_LOCALI / "proposte" / "status",
        ))
        respinti.extend(respinti_status)
        for percorso in proposte_status:
            print(f"[genera] proposta di status scritta: {percorso}")
    fabbrica_nuova = None
    if args.fabbrica:
        fabbrica_nuova, respinti_fabbrica = asyncio.run(genera_fabbrica(
            engine, stagione, sovrascrivi=args.sovrascrivi,
        ))
        respinti.extend(respinti_fabbrica)
        if fabbrica_nuova is not None:
            print(f"[genera] fabbrica generata: «{fabbrica_nuova.nome}» "
                  f"({len(fabbrica_nuova.basi)} basi × "
                  f"{len(fabbrica_nuova.famiglie)} famiglie × "
                  f"{len(fabbrica_nuova.affissi)} affissi)")
    mosse_nuove: list = []
    if args.mosse > 0:
        mosse_nuove, respinti_mosse = asyncio.run(genera_mosse(
            engine, stagione, quanti=args.mosse, sovrascrivi=args.sovrascrivi,
        ))
        respinti.extend(respinti_mosse)
    oggetti_nuovi: list = []
    if args.oggetti > 0:
        # Sinergia (--mosse --oggetti): un accessorio può concedere una mossa
        # accettata NELLO STESSO giro (pattern `disponibili` degli spawn).
        oggetti_nuovi, respinti_oggetti = asyncio.run(genera_oggetti(
            engine, stagione, quanti=args.oggetti, sovrascrivi=args.sovrascrivi,
            mosse_extra=frozenset(m.slug for m in mosse_nuove),
        ))
        respinti.extend(respinti_oggetti)
    print(f"[genera] boss accettati: {len(mob_nuovi)} "
          f"(provincia {len(per_tier[TierTerritorio.PROVINCIA])}, "
          f"citta {len(per_tier[TierTerritorio.CITTA])}); "
          f"tabelle: {len(tabelle)}; spawn: {len(spawn)}; "
          f"oggetti: {len(oggetti_nuovi)}; mosse: {len(mosse_nuove)}")
    for riga in respinti:
        print(f"[genera] ✗ respinto: {riga}")
    if consumo is not None:
        print(f"[genera] {consumo.riassunto()}")

    if not args.applica:
        print("[genera] DRY-RUN: nessuna scrittura (usa --applica per scrivere; "
              "il diff git è la promozione)")
        return 0
    errori = applica(
        args.stagione, piano.slug, mob_nuovi, tabelle, spawn, per_tier,
        oggetti_nuovi=oggetti_nuovi, mosse_nuove=mosse_nuove,
        fabbrica_nuova=fabbrica_nuova,
    )
    for riga in errori:
        print(f"[genera] ✗ {riga}")
    if not errori:
        print(f"[genera] applicato: {len(mob_nuovi)} mob + {len(oggetti_nuovi)} "
              f"oggetti + {len(mosse_nuove)} mosse + piano {piano.slug} aggiornato")
    return 1 if errori else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
