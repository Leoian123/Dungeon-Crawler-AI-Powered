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
from main import DIRECTORY_CONTENUTI, carica_asset, risolvi_stagione
from motore import Corsia, GRADO_DA_TIER, MasterEngine, mosse_note, motivi_fuori_budget

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
        "[vocabolario/mosse] " + ", ".join(sorted(mosse_note())),
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


# --- Applicazione: scritture atomiche + gate finale (risolvi_stagione) ----------

def _scrivi_json(percorso: Path, dati: dict) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    tmp = percorso.with_suffix(".tmp")
    tmp.write_text(json.dumps(dati, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(percorso)


def applica(
    slug_stagione: str, slug_piano: str, mob_nuovi, tabelle, spawn, per_tier,
    *, radice: Path | None = None, locali: Path | None = None,
) -> list[str]:
    """Scrive i mob generati e il PianoAsset aggiornato nella libreria, con GATE
    FINALE `risolvi_stagione`: se la stagione aggiornata non risolve, ROLLBACK
    completo (l'authoring non lascia mai la libreria a metà). Ritorna gli errori
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
    print(f"[genera] boss accettati: {len(mob_nuovi)} "
          f"(provincia {len(per_tier[TierTerritorio.PROVINCIA])}, "
          f"citta {len(per_tier[TierTerritorio.CITTA])}); "
          f"tabelle: {len(tabelle)}; spawn: {len(spawn)}")
    for riga in respinti:
        print(f"[genera] ✗ respinto: {riga}")
    if consumo is not None:
        print(f"[genera] {consumo.riassunto()}")

    if not args.applica:
        print("[genera] DRY-RUN: nessuna scrittura (usa --applica per scrivere; "
              "il diff git è la promozione)")
        return 0
    errori = applica(args.stagione, piano.slug, mob_nuovi, tabelle, spawn, per_tier)
    for riga in errori:
        print(f"[genera] ✗ {riga}")
    if not errori:
        print(f"[genera] applicato: {len(mob_nuovi)} mob + piano {piano.slug} aggiornato")
    return 1 if errori else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
