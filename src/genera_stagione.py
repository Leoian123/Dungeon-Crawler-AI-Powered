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

Pattern `banco_nemici`: stdlib + composition root; il provider arriva da
`provider.root.scegli_provider` con instradamento authoring→FORTE.
"""

from __future__ import annotations

import asyncio
import json
import math
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
from motore import GRADO_DA_TIER, MasterEngine, mosse_note

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


def prompt_lotto_boss(contesto: str, tier: TierTerritorio, n: int,
                      esclusi: set[str]) -> str:
    vietati = f" Slug già usati (vietati): {', '.join(sorted(esclusi))}." if esclusi else ""
    return "\n".join([
        contesto,
        f"[compito] Genera {n} boss di {tier.value.upper()} per questo piano "
        f"(campo `tier` = \"{tier.value}\" per TUTTI).{vietati} Ognuno con la sua "
        "epoca/citazione, mai due simili nel lotto.",
    ])


def prompt_tabella(contesto: str, tier: TierTerritorio) -> str:
    return "\n".join([
        contesto,
        f"[compito] Genera la TABELLA PROCEDURALE dei boss di {tier.value.upper()}: "
        "8-12 `nomi` (titoli da boss rionale, epoche/cult diversi), 8-12 `gimmick` "
        "(una frase di carattere ciascuno), e gli `archetipi` ammessi (dal "
        "vocabolario). Il motore combinerà nomi × gimmick × archetipi, seeded.",
    ])


def prompt_spawn(contesto: str, tier: TierTerritorio, disponibili: list[str]) -> str:
    return "\n".join([
        contesto,
        f"[mob-disponibili] {', '.join(disponibili)}",
        f"[compito] Componi la TABELLA DI SPAWN del tier {tier.value.upper()}: "
        "scegli SOLO slug dai mob-disponibili e assegna a ciascuno una frequenza "
        "(comune|insolito|raro). I comuni danno il tono, i rari sorprendono.",
    ])


# --- Gate per item (i lint del motore, mai fiducia) -----------------------------

def gate_boss(b: BossGenerato, piano, tier: TierTerritorio,
              slug_visti: set[str], *, ufficiali: Path | None,
              locali: Path | None, sovrascrivi: bool) -> list[str]:
    errori: list[str] = []
    if b.tier is not tier:
        errori.append(f"{b.slug}: tier {b.tier.value}, atteso {tier.value}")
    if b.archetipo not in set(piano.budget.archetipi):
        errori.append(f"{b.slug}: archetipo {b.archetipo} fuori budget")
    fuori_mosse = [m for m in b.mosse if m not in mosse_note()]
    if fuori_mosse:
        errori.append(f"{b.slug}: mosse fuori catalogo: {', '.join(fuori_mosse)}")
    if not set(b.blocchi) <= set(piano.budget.blocchi):
        errori.append(f"{b.slug}: blocchi fuori budget")
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


# --- Il batch (per costruzione: ~2+8+2+2 chiamate FORTE, one-shot) --------------

async def genera_roster(
    engine: MasterEngine, stagione, piano, *,
    n_per_tier: dict[TierTerritorio, int],
    ufficiali: Path | None = None, locali: Path | None = None,
    sovrascrivi: bool = False,
):
    """Il batch di authoring. Ritorna (mob_accettati, tabelle, spawn, respinti)."""
    contesto = contesto_prompt(stagione, piano)
    mob_accettati: list[MobAsset] = []
    per_tier: dict[TierTerritorio, list[str]] = {t: [] for t in _TIER_GENERABILI}
    respinti: list[str] = []
    slug_visti: set[str] = set()

    for tier in _TIER_GENERABILI:
        mancanti = n_per_tier.get(tier, 0)
        for _ in range(math.ceil(mancanti / _LOTTO)):
            quanti = min(_LOTTO, mancanti - len(per_tier[tier]))
            if quanti <= 0:
                break
            lotto = await engine.genera(
                "authoring.boss",
                prompt_lotto_boss(contesto, tier, quanti, slug_visti),
            )
            if lotto is None:
                respinti.append(f"lotto {tier.value}: chiamata degradata (trasporto)")
                continue
            for b in lotto.boss:
                errori = gate_boss(
                    b, piano, tier, slug_visti,
                    ufficiali=ufficiali, locali=locali, sovrascrivi=sovrascrivi,
                )
                if errori:
                    respinti.extend(errori)
                    continue
                slug_visti.add(b.slug)
                mob_accettati.append(boss_a_mob_asset(b))
                per_tier[tier].append(b.slug)

    tabelle: list[TabellaProceduraleGen] = []
    for tier in (TierTerritorio.DISTRETTO, TierTerritorio.QUARTIERE):
        tabella = await engine.genera("authoring.tabella", prompt_tabella(contesto, tier))
        if tabella is None:
            respinti.append(f"tabella {tier.value}: chiamata degradata")
            continue
        if tabella.tier is not tier:
            respinti.append(f"tabella {tier.value}: tier sbagliato ({tabella.tier.value})")
            continue
        fuori = [a for a in tabella.archetipi if a not in set(piano.budget.archetipi)]
        if fuori:
            respinti.append(f"tabella {tier.value}: archetipi fuori budget: {', '.join(fuori)}")
            continue
        tabelle.append(tabella)

    disponibili = sorted(
        {m.slug for m in piano.cast} | {m.slug for m in mob_accettati}
    )
    spawn: list[TabellaSpawnGenerata] = []
    for tier in (TierTerritorio.QUARTIERE, TierTerritorio.CITTA):
        proposta = await engine.genera(
            "authoring.spawn", prompt_spawn(contesto, tier, disponibili)
        )
        if proposta is None:
            respinti.append(f"spawn {tier.value}: chiamata degradata")
            continue
        fuori = [v.mob for v in proposta.voci if v.mob not in set(disponibili)]
        if fuori:
            respinti.append(f"spawn {tier.value}: mob inesistenti: {', '.join(fuori)}")
            continue
        spawn.append(proposta)

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

def main(argv: list[str] | None = None) -> int:  # pragma: no cover (entry point)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    argv = list(sys.argv[1:] if argv is None else argv)

    def _arg(nome: str, default: int) -> int:
        return int(argv[argv.index(nome) + 1]) if nome in argv else default

    slug_stagione = STAGIONE_DEFAULT_SLUG
    stagione = risolvi_stagione(slug_stagione)
    piano = stagione.piani[0]
    if piano.territorio is None:
        print(f"[genera] il piano {piano.slug} non ha territorio: niente da generare")
        return 1

    from contracts import TurnoNarrazione
    from provider import scegli_provider

    instradamento = {TurnoNarrazione: "forte"}
    provider, etichetta = scegli_provider(argv, instradamento=instradamento)
    print(f"[genera] {etichetta}")
    if provider is None:
        from provider import FakeProvider

        provider = FakeProvider([])  # --fake/offline: smoke a zero generazioni
    engine = MasterEngine.avvolgi(provider)

    n_per_tier = {
        TierTerritorio.PROVINCIA: _arg("--provincia", 10),
        TierTerritorio.CITTA: _arg("--citta", 40),
    }
    mob_nuovi, tabelle, spawn, per_tier, respinti = asyncio.run(genera_roster(
        engine, stagione, piano, n_per_tier=n_per_tier,
        sovrascrivi="--sovrascrivi" in argv,
    ))
    print(f"[genera] boss accettati: {len(mob_nuovi)} "
          f"(provincia {len(per_tier[TierTerritorio.PROVINCIA])}, "
          f"citta {len(per_tier[TierTerritorio.CITTA])}); "
          f"tabelle: {len(tabelle)}; spawn: {len(spawn)}")
    for riga in respinti:
        print(f"[genera] ✗ respinto: {riga}")
    consumo = getattr(provider, "consumo", None)
    if consumo is not None:
        print(f"[genera] {consumo.riassunto()}")

    if "--applica" not in argv:
        print("[genera] DRY-RUN: nessuna scrittura (usa --applica per scrivere; "
              "il diff git è la promozione)")
        return 0
    errori = applica(slug_stagione, piano.slug, mob_nuovi, tabelle, spawn, per_tier)
    for riga in errori:
        print(f"[genera] ✗ {riga}")
    if not errori:
        print(f"[genera] applicato: {len(mob_nuovi)} mob + piano {piano.slug} aggiornato")
    return 1 if errori else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
