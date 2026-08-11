"""Composition root della v1 — **headless**: cabla il motore e lo pilota senza UI.

Il game engine è indipendente dalla presentazione: una UI futura (web, Electron, TUI…)
si innesterà su questo stesso strato attraverso le **porte** di `SessioneGioco` e gli
eventi tipizzati del **bus** — tutto espresso sui DTO di `contracts`, mai sul `World`.
Qui non c'è nessuna dipendenza di presentazione: il motore resta ignaro dell'host (C-2a)
e nessun layer importa Textual (C-5). Questo modulo è la *colla* + un driver headless di
riferimento, non un layer con membrana.

`SessioneGioco` è la **porta** verso il motore vista da un qualunque host: produce la
narrazione (coroutine host-agnostica, `await`-abile da un worker UI o da `asyncio.run`),
drena gli intenti del giocatore sul turno e ricostruisce lo `SnapshotVista` da
renderizzare. Il giocatore gioca un incontro completo: narrazione → scelta →
combattimento deterministico → ritorno alla narrazione.

Nell'MVP il provider è il **FakeProvider** (offline, scriptato); il backend Anthropic
reale (fase 5) si innesta dietro la stessa interfaccia `genera`.
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
import tempfile
import time
import weakref
from pathlib import Path
from typing import Callable
from uuid import uuid4

from contracts import (
    AnomalyTriggered,
    AssetVista,
    Blocco,
    BusEventi,
    ClasseProva,
    ColpoInferto,
    CombatResolved,
    EffettoStatus,
    StatusApplicato,
    CrolloDungeon,
    DisimpegnoScena,
    TransizioneZona,
    StatusSvanito,
    TurnoSaltato,
    CrawlerVista,
    MobAsset,
    FabbricaAsset,
    MossaAsset,
    OggettoAsset,
    ArchetipoAsset,
    PianoAsset,
    PianoRisolto,
    ProfiloArchetipoDati,
    EquipVista,
    ProgressioneVista,
    RiposoConcluso,
    SchedaVista,
    Terminale,
    SkillVista,
    SlotEquip,
    Stagione,
    StagioneRisolta,
    TipoDanno,
    DiscesaPiano,
    Durata,
    EncounterStarted,
    EntitaGenerata,
    FattiScontro,
    IntentoEsplorazione,
    MessaggioGM,
    MortePersonaggio,
    OggettoTrovato,
    PlayerDiscende,
    PlayerEquipaggia,
    PlayerAttraversa,
    PlayerSiMuove,
    PlayerToglie,
    OpzioneVista,
    PlayerChoseOption,
    Grado,
    RiepilogoAzione,
    SnapshotVista,
    StatId,
    TipoAzione,
    TurnoNarrazione,
)
from guscio import Guscio
from motore import (
    MODEL_ID_DEFAULT,
    Archivio,
    ArchetipoAttivo,
    AffissoAttivo,
    BaseAttiva,
    EffettoAttivo,
    FabbricaAttiva,
    FamigliaAttiva,
    MossaAttiva,
    OggettoAttivo,
    MasterEngine,
    MemoriaSuArchivio,
    PREFISSO_RIFINITURA,
    entita_mob_incontro,
    nome_nemico_incontro,
    ProfiloArchetipo,
    mosse_note,
    MemoriaTurni,
    OpzioneScena,
    SpecNemico,
    CaricamentoFallito,
    acc_eff,
    atk_eff,
    attacco,
    carica_archivio,
    carica_da_disco,
    componi_opzioni_scena,
    consuma_messaggi,
    def_eff,
    dissolvi_mob,
    esegui_turno_gm,
    eva_eff,
    in_combattimento,
    indice_crawler,
    ingaggia_combattimento,
    iniziativa,
    livello_corrente,
    mappa_corrente,
    mappa_to_dict,
    master_seed,
    max_hp,
    messaggi_da_archivio,
    messaggi_pendenti,
    mob_corrente,
    dettagli_mob_corrente,
    nome_mob_corrente,
    riposa,
    CATALOGO_OGGETTI,
    assicura_zaino,
    fonti_zaino,
    MobAttivo,
    PianoAttivo,
    StagioneAttiva,
    TabellaProceduraleAttiva,
    TerritorioAttivo,
    VoceSpawnAttiva,
    design_piano_corrente,
    stagione_corrente,
    lint_profilo,
    lint_registry,
    nemici_in_scontro,
    prossimo_attivo_e_protagonista,
    mossa_di as mossa_di_catalogo,
    cooldown_residuo,
    assicura_mana,
    etichetta_mossa,
    geometria_di,
    equip_attivo,
    max_mana,
    mossa_pagabile,
    mosse_di,
    richiedi_fuga,
    richiedi_mossa,
    prepara_riepilogo,
    proietta_scheda,
    protagonista,
    salva_run,
    stat_eff,
    spendi_tempo,
    tempo_piano_corrente,
    tenta_disimpegno,
    classe_disimpegno,
    tick,
    travasa,
)
from provider import FakeProvider

# Il menu di combattimento NON è più una costante: lo compone `IstanzaCombattimento`
# dal `Repertorio` del protagonista (una voce per mossa + "Fuggi" ultima). Il menu di
# NARRAZIONE lo compone il MOTORE dalla scena (`componi_opzioni_scena`) — la mappa dispone.

# --- Radici dei percorsi: INSTALLAZIONE (read-only) vs DATI UTENTE (scrivibili) --
#
# Le variabili DCC_* restano l'override esplicito (deploy/container: contenuti
# montati read-only, salvataggi su volume). I DEFAULT sono consapevoli del
# congelamento (PyInstaller): in un eseguibile `__file__` vive nel bundle e "la
# radice del repo" non esiste — e in onefile il bundle (`_MEIPASS`) è una cartella
# TEMPORANEA che sparisce all'uscita, quindi i dati utente non possono mai stare lì.

def _radice_installazione() -> Path:
    """Radice dei dati d'INSTALLAZIONE (la libreria `contenuti/` ufficiale, read-only).
    Processo normale → radice del repo; congelato → il bundle (`_MEIPASS`; onedir:
    la cartella dell'eseguibile)."""
    if getattr(sys, "frozen", False):
        bundle = getattr(sys, "_MEIPASS", "")
        return Path(bundle) if bundle else Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _radice_dati_utente() -> Path:
    """Radice dei dati UTENTE (salvataggi, contenuti locali dell'authoring):
    SCRIVIBILE e durevole, quindi mai dentro il bundle. Congelato → accanto
    all'eseguibile; processo normale → radice del repo."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


# La cartella dei crawler salvati (slot = crawler, H §1). I doc non fissano il
# percorso: default = `salvataggi/` nella radice dei dati utente (gitignored),
# override con DCC_SAVE_DIR. L'elenco è uno scan delle intestazioni (H §5),
# mai un registro.
_RADICE_REPO = _radice_installazione()
DIRECTORY_SALVATAGGI = Path(
    os.environ.get("DCC_SAVE_DIR") or _radice_dati_utente() / "salvataggi"
)

# --- La LIBRERIA dei contenuti dello show (stagioni/piani/mob) -------------------
#
# Asset normalizzati e riusabili (riferimenti per slug, tag per l'affinità):
# gli UFFICIALI sono versionati nel repo (`contenuti/`), i LOCALI — creati dal
# GM mode — vivono in una cartella gitignored (lo "stato di guscio persistente"
# di H §12). In lettura l'ufficiale vince sullo slug; le ufficiali sono
# read-only per l'authoring (si duplicano). Il runtime NON legge mai la
# libreria: consuma la stagione RISOLTA e congelata nel World alla creazione.
DIRECTORY_CONTENUTI = Path(os.environ.get("DCC_CONTENUTI_DIR") or _RADICE_REPO / "contenuti")
DIRECTORY_CONTENUTI_LOCALI = Path(
    os.environ.get("DCC_CONTENUTI_LOCALI_DIR") or _radice_dati_utente() / "contenuti_locali"
)
STAGIONE_DEFAULT = "stagione-1"

TipoAsset = str  # "stagioni" | "piani" | "mob" | "archetipi" (le collezioni della libreria)
MODELLI_ASSET: dict[str, type] = {
    "stagioni": Stagione, "piani": PianoAsset, "mob": MobAsset,
    "archetipi": ArchetipoAsset, "oggetti": OggettoAsset, "mosse": MossaAsset,
    "fabbriche": FabbricaAsset,
}


def mosse_note_authoring(
    ufficiali: Path | None = None, locali: Path | None = None,
) -> frozenset[str]:
    """Le mosse citabili in AUTHORING: il catalogo storico del motore + le
    mosse-asset valide in libreria (il motore non scandisce mai il disco: la
    libreria è del composition root — per questo il set si calcola QUI e si
    passa ai lint)."""
    note = set(mosse_note())
    note |= {
        slug for slug, (asset, _vista)
        in _collezione("mosse", ufficiali, locali).items()
        if asset is not None
    }
    return frozenset(note)


def _etichetta_asset(tipo: str, asset) -> str:
    if tipo == "mosse":
        return asset.etichetta
    if tipo in ("mob", "archetipi", "oggetti", "fabbriche"):
        return asset.nome
    return asset.titolo


def _tipo_vista(tipo: str) -> str:
    return {
        "stagioni": "stagione", "piani": "piano", "mob": "mob",
        "archetipi": "archetipo", "oggetti": "oggetto", "mosse": "mossa",
        "fabbriche": "fabbrica",
    }[tipo]


def _scandisci_collezione(
    tipo: str, cartella: Path, origine: str
) -> dict[str, tuple[object | None, AssetVista]]:
    """Una collezione da disco, LASCA (H-22): file non conforme → voce
    `valido=False`, mostrata ma inutilizzabile — mai un crash di scan."""
    modello = MODELLI_ASSET[tipo]
    voci: dict[str, tuple[object | None, AssetVista]] = {}
    base = cartella / tipo
    if not base.exists():
        return voci
    for percorso in sorted(base.glob("*.json")):
        try:
            asset = modello.model_validate_json(percorso.read_text(encoding="utf-8"))
            vista = AssetVista(
                slug=asset.slug,
                tipo=_tipo_vista(tipo),
                etichetta=_etichetta_asset(tipo, asset),
                tags=asset.tags,
                origine=origine,
                valido=True,
            )
            voci[asset.slug] = (asset, vista)
        except (OSError, ValueError) as _errore:  # ValidationError è un ValueError
            slug = percorso.stem
            voci.setdefault(
                slug,
                (
                    None,
                    AssetVista(
                        slug=slug, tipo=_tipo_vista(tipo), etichetta="«corrotto»",
                        origine=origine, valido=False,
                    ),
                ),
            )
    return voci


def _collezione(
    tipo: str, ufficiali: Path | None = None, locali: Path | None = None
) -> dict[str, tuple[object | None, AssetVista]]:
    """Fusione locali+ufficiali: sull'ombreggiatura di slug l'UFFICIALE vince."""
    fuse = _scandisci_collezione(tipo, locali or DIRECTORY_CONTENUTI_LOCALI, "locale")
    fuse.update(_scandisci_collezione(tipo, ufficiali or DIRECTORY_CONTENUTI, "ufficiale"))
    return fuse


def elenca_asset(
    tipo: str, *, ufficiali: Path | None = None, locali: Path | None = None
) -> list[AssetVista]:
    return [
        vista
        for _slug, (_asset, vista) in sorted(_collezione(tipo, ufficiali, locali).items())
    ]


def carica_asset(
    tipo: str, slug: str, *, ufficiali: Path | None = None, locali: Path | None = None
):
    """L'asset per slug (ufficiale vince), `None` se assente o corrotto."""
    voce = _collezione(tipo, ufficiali, locali).get(slug)
    return voce[0] if voce else None


# I campi CORE del profilo-archetipo (senza le resistenze, che valgono 0 se assenti):
# per uno slug NUOVO devono esserci tutti; per uno storico i mancanti si ereditano.
_CAMPI_PROFILO_CORE = (
    "destrezza_base", "pv_base", "danno_base", "intelligenza_base", "difesa_base",
    "saggezza_base", "fortuna_base", "armatura", "taglia", "arma",
)
_CAMPI_RESISTENZE = {
    "res_mischia": TipoDanno.MISCHIA, "res_fuoco": TipoDanno.FUOCO, "res_veleno": TipoDanno.VELENO,
}


def _lint_mob_espressivo(mob: MobAsset, errori: list[str], note=None) -> None:
    """Lint dell'espressività per-mob (Fase 5): mosse nel catalogo (storico +
    mosse-asset note al chiamante), chiavi gear dell'override valide."""
    from motore.calibrazione import COEFF_ACC, M_ARMATURA, M_TAGLIA

    note = note if note is not None else mosse_note()
    fuori = [m for m in mob.mosse if m not in note]
    if fuori:
        errori.append(f"mob {mob.slug}: mosse fuori catalogo: " + ", ".join(fuori))
    if mob.override is not None:
        for nome, tabella in (("armatura", M_ARMATURA), ("taglia", M_TAGLIA), ("arma", COEFF_ACC)):
            chiave = getattr(mob.override, nome)
            if chiave is not None and chiave not in tabella:
                errori.append(f"mob {mob.slug}: {nome} {chiave!r} non è una chiave di tabella")


def _archetipi_noti(ufficiali: Path | None, locali: Path | None) -> set[str]:
    """Il vocabolario archetipi dell'AUTHORING: storici di calibrazione + asset in
    libreria (validi). È il set contro cui il lint di mob/piani verifica F-6."""
    from motore.calibrazione import REGISTRY_ARCHETIPI

    noti = set(REGISTRY_ARCHETIPI)
    noti |= {
        slug for slug, (asset, vista) in _collezione("archetipi", ufficiali, locali).items()
        if asset is not None
    }
    return noti


def _risolvi_archetipo(
    slug: str, asset: ArchetipoAsset | None, errori: list[str], note=None
) -> ArchetipoAsset | None:
    """Completa il profilo di un archetipo (merge coi valori di calibrazione per gli
    storici; completo obbligatorio per gli slug nuovi) e valida chiavi gear e mosse.
    Accumula in `errori` (errore di authoring, mai degrado a runtime)."""
    from motore.calibrazione import COEFF_ACC, M_ARMATURA, M_TAGLIA, REGISTRY_ARCHETIPI
    from motore.calibrazione import profilo_corrente

    storico = profilo_corrente(slug) if slug in REGISTRY_ARCHETIPI else None
    if asset is None and storico is None:
        errori.append(f"archetipo riferito ma assente: {slug}")
        return None
    dati = (asset.profilo if asset is not None else None) or ProfiloArchetipoDati()

    def campo(nome: str, eredita):
        valore = getattr(dati, nome)
        return valore if valore is not None else eredita

    if storico is None:
        mancanti = [n for n in _CAMPI_PROFILO_CORE if getattr(dati, n) is None]
        if mancanti:
            errori.append(
                f"archetipo {slug}: profilo incompleto (slug nuovo, mancano: "
                + ", ".join(mancanti) + ")"
            )
            return None
    pieno = ProfiloArchetipoDati(
        destrezza_base=campo("destrezza_base", storico.destrezza_base if storico else None),
        pv_base=campo("pv_base", storico.pv_base if storico else None),
        danno_base=campo("danno_base", storico.danno_base if storico else None),
        intelligenza_base=campo("intelligenza_base", storico.intelligenza_base if storico else None),
        difesa_base=campo("difesa_base", storico.difesa_base if storico else None),
        saggezza_base=campo("saggezza_base", storico.saggezza_base if storico else None),
        fortuna_base=campo("fortuna_base", storico.fortuna_base if storico else None),
        armatura=campo("armatura", storico.armatura if storico else None),
        taglia=campo("taglia", storico.taglia if storico else None),
        arma=campo("arma", storico.arma if storico else None),
        res_mischia=campo("res_mischia", storico.resistenze.get(TipoDanno.MISCHIA, 0.0) if storico else 0.0),
        res_fuoco=campo("res_fuoco", storico.resistenze.get(TipoDanno.FUOCO, 0.0) if storico else 0.0),
        res_veleno=campo("res_veleno", storico.resistenze.get(TipoDanno.VELENO, 0.0) if storico else 0.0),
    )
    # Le chiavi gear sono voci delle tabelle §11 (contracts non le conosce: si valida qui).
    for nome, tabella in (("armatura", M_ARMATURA), ("taglia", M_TAGLIA), ("arma", COEFF_ACC)):
        chiave = getattr(pieno, nome)
        if chiave not in tabella:
            errori.append(f"archetipo {slug}: {nome} {chiave!r} non è una chiave di tabella")
    # …e le MAGNITUDINI stanno in una banda derivata dal catalogo: è qui che
    # `pv_base=99999` smette di essere un mob con 99.999 HP e diventa un errore di
    # authoring, sollevato alla risoluzione invece che scoperto giocando.
    errori.extend(lint_profilo(slug, pieno))
    mosse = list(asset.mosse) if asset is not None else []
    note = note if note is not None else mosse_note()
    fuori = [m for m in mosse if m not in note]
    if fuori:
        errori.append(f"archetipo {slug}: mosse fuori catalogo: " + ", ".join(fuori))
    return ArchetipoAsset(
        slug=slug,
        versione=asset.versione if asset is not None else 1,
        tags=list(asset.tags) if asset is not None else [],
        nome=asset.nome if asset is not None else slug,
        descrizione=asset.descrizione if asset is not None else "",
        profilo=pieno,
        mosse=mosse,
    )


def salva_asset_locale(
    asset, *, sovrascrivi: bool = False,
    ufficiali: Path | None = None, locali: Path | None = None,
) -> None:
    """Scrive un asset nella libreria LOCALE (authoring): lint del registry
    (F-6), slug mai in conflitto con un ufficiale, scrittura atomica."""
    tipo = next(t for t, m in MODELLI_ASSET.items() if isinstance(asset, m))
    if tipo == "mob":
        errori = lint_registry(
            [asset.archetipo], asset.blocchi,
            archetipi_noti=_archetipi_noti(ufficiali, locali),
        )
        _lint_mob_espressivo(asset, errori)
    elif tipo == "piani":
        errori = lint_registry(
            asset.budget.archetipi, asset.budget.blocchi,
            archetipi_noti=_archetipi_noti(ufficiali, locali),
        )
    elif tipo == "archetipi":
        # Il lint di authoring anticipa gli errori di risoluzione: profilo completo
        # (per slug nuovi), chiavi gear valide, mosse nel catalogo.
        errori = []
        _risolvi_archetipo(asset.slug, asset, errori)
    else:
        errori = []
    if errori:
        raise ValueError("; ".join(errori))
    if _scandisci_collezione(tipo, ufficiali or DIRECTORY_CONTENUTI, "ufficiale").get(asset.slug):
        raise ValueError(f"slug riservato a un asset ufficiale: {asset.slug}")
    cartella = (locali or DIRECTORY_CONTENUTI_LOCALI) / tipo
    percorso = cartella / f"{asset.slug}.json"
    if percorso.exists() and not sovrascrivi:
        raise ValueError(f"slug già esistente in libreria locale: {asset.slug}")
    cartella.mkdir(parents=True, exist_ok=True)
    temporaneo = percorso.with_suffix(".json.tmp")
    temporaneo.write_text(asset.model_dump_json(indent=2), encoding="utf-8")
    os.replace(temporaneo, percorso)


def elimina_asset_locale(
    tipo: str, slug: str, *, locali: Path | None = None
) -> bool:
    percorso = (locali or DIRECTORY_CONTENUTI_LOCALI) / tipo / f"{slug}.json"
    if not percorso.exists():
        return False
    percorso.unlink()
    return True


def vocabolario(
    *, ufficiali: Path | None = None, locali: Path | None = None
) -> dict:
    """Il VOCABOLARIO per gli host (SPA, agenti): gli enum del contratto + le chiavi
    dei cataloghi del motore (mosse, tabelle gear) + gli archetipi noti (storici ∪
    libreria). È l'unica fonte per i menu degli editor — fine dei duplicati cablati
    nei client. Passa da qui (composition root), mai da un import di `motore` negli
    host (membrana C-2a)."""
    from motore.calibrazione import COEFF_ACC, M_ARMATURA, M_TAGLIA

    return {
        "gradi": [g.value for g in Grado],
        "blocchi": [b.value for b in Blocco],
        "durate": [d.value for d in Durata],
        "tipi_danno": [t.value for t in TipoDanno if t is not TipoDanno.GENERICO],
        "mosse": sorted(mosse_note_authoring(ufficiali, locali)),
        "archetipi": sorted(_archetipi_noti(ufficiali, locali)),
        "armature": list(M_ARMATURA),
        "taglie": list(M_TAGLIA),
        "armi": list(COEFF_ACC),
    }


def _risolvi_territorio(
    territorio, slug_piano: str, errori: list[str],
    *, ufficiali: Path | None, locali: Path | None, note_mosse=None,
):
    """Scioglie i riferimenti del territorio (roster boss e tabelle di spawn):
    slug → MobAsset con lo stesso lint espressivo del cast. `None` = riferimenti
    pendenti (già accumulati in `errori`); la COERENZA la impongono i validator
    di `TerritorioRisolto`/`PianoRisolto` alla costruzione del piano."""
    from contracts import TabellaSpawnRisolta, TerritorioRisolto, VoceSpawnRisolta

    pendenti = False

    def _mob(slug_mob: str, dove: str) -> MobAsset | None:
        nonlocal pendenti
        mob = carica_asset("mob", slug_mob, ufficiali=ufficiali, locali=locali)
        if mob is None:
            errori.append(
                f"mob riferito ma assente: {slug_mob} ({dove}, piano {slug_piano})"
            )
            pendenti = True
            return None
        _lint_mob_espressivo(mob, errori, note_mosse)
        return mob

    boss = {}
    for tier, roster in territorio.boss.items():
        sciolti = [_mob(s, f"boss {tier.value}") for s in roster]
        boss[tier] = [m for m in sciolti if m is not None]
    spawn = []
    for tabella in territorio.spawn:
        voci = []
        for voce in tabella.voci:
            mob = _mob(voce.mob, f"spawn {tabella.tier.value}")
            if mob is not None:
                voci.append(VoceSpawnRisolta(mob=mob, frequenza=voce.frequenza))
        if voci:
            spawn.append(TabellaSpawnRisolta(tier=tabella.tier, voci=voci))
    if pendenti:
        return None
    try:
        return TerritorioRisolto(
            conteggi=territorio.conteggi, boss=boss,
            procedurali=territorio.procedurali, spawn=spawn,
            stanze_per_zona=territorio.stanze_per_zona,
        )
    except ValueError as errore:  # grado==tier, boss[PIANO]==1 (validator)
        errori.append(f"piano {slug_piano}: {errore}")
        return None


def risolvi_stagione(
    stagione: Stagione | str,
    *, ufficiali: Path | None = None, locali: Path | None = None,
) -> StagioneRisolta:
    """Scioglie i riferimenti dell'aggregato (piani → mob) e IMPONE la coerenza:
    slug pendenti, cast fuori budget e categorie senza binding (F-6) sono errori
    di authoring sollevati QUI — mai degradi a runtime. Il risultato è pronto
    per il freeze nel World."""
    if isinstance(stagione, str):
        caricata = carica_asset("stagioni", stagione, ufficiali=ufficiali, locali=locali)
        if caricata is None:
            raise ValueError(f"stagione assente o corrotta: {stagione}")
        stagione = caricata
    errori: list[str] = []
    # Il set delle mosse citabili (storico + mosse-asset in libreria): un mob o
    # un archetipo può citare una mossa nuova appena scritta (T3a).
    note_mosse = mosse_note_authoring(ufficiali, locali)
    piani_risolti: list[PianoRisolto] = []
    slug_archetipi: list[str] = []  # in ordine di prima apparizione (deterministico)
    for slug_piano in stagione.piani:
        piano = carica_asset("piani", slug_piano, ufficiali=ufficiali, locali=locali)
        if piano is None:
            errori.append(f"piano riferito ma assente: {slug_piano}")
            continue
        cast: list[MobAsset] = []
        mancanti = False
        for slug_mob in piano.cast:
            mob = carica_asset("mob", slug_mob, ufficiali=ufficiali, locali=locali)
            if mob is None:
                errori.append(f"mob riferito ma assente: {slug_mob} (piano {slug_piano})")
                mancanti = True
            else:
                _lint_mob_espressivo(mob, errori, note_mosse)
                cast.append(mob)
        if mancanti:
            continue
        # Il TERRITORIO (2026-08-10): roster boss e tabelle di spawn si sciolgono
        # come il cast (slug → MobAsset, con lo stesso lint espressivo); la
        # coerenza (grado==tier, celestiale riservato, tutto ⊆ budget) è imposta
        # dai validator delle forme risolte — qui si accumulano solo gli errori.
        territorio_risolto = None
        if piano.territorio is not None:
            territorio_risolto = _risolvi_territorio(
                piano.territorio, slug_piano, errori,
                ufficiali=ufficiali, locali=locali, note_mosse=note_mosse,
            )
            if territorio_risolto is None and piano.territorio is not None:
                continue  # slug pendenti già a registro: il piano non si monta
        try:
            piani_risolti.append(
                PianoRisolto(
                    slug=piano.slug, versione=piano.versione, tags=piano.tags,
                    titolo=piano.titolo, tema=piano.tema, stile=piano.stile,
                    lore=piano.lore, budget=piano.budget, cast=cast, stanze=piano.stanze,
                    territorio=territorio_risolto,
                )
            )
        except ValueError as errore:  # cast⊆budget + coerenza territorio (validator)
            errori.append(f"piano {slug_piano}: {errore}")
        else:
            mob_extra: list[MobAsset] = []
            if territorio_risolto is not None:
                for roster in territorio_risolto.boss.values():
                    mob_extra.extend(roster)
                for tabella in territorio_risolto.spawn:
                    mob_extra.extend(v.mob for v in tabella.voci)
            for slug_arch in (
                list(piano.budget.archetipi)
                + [m.archetipo for m in cast]
                + [m.archetipo for m in mob_extra]
            ):
                if slug_arch not in slug_archetipi:
                    slug_archetipi.append(slug_arch)
            errori.extend(lint_registry([], piano.budget.blocchi))
    # Gli ARCHETIPI riferiti si risolvono come gli altri asset: profilo completato
    # (merge con la calibrazione per gli storici) e validato — è il vocabolario
    # chiuso che verrà congelato nella run (F-6 runtime, D1).
    archetipi_risolti: list[ArchetipoAsset] = []
    for slug_arch in slug_archetipi:
        asset_arch = carica_asset("archetipi", slug_arch, ufficiali=ufficiali, locali=locali)
        risolto = _risolvi_archetipo(slug_arch, asset_arch, errori, note_mosse)
        if risolto is not None:
            archetipi_risolti.append(risolto)
    # Il POOL DI LOOT (T1b, D-1): gli slug dichiarati dalla stagione, oppure —
    # pool vuoto = lasco — tutta la libreria oggetti valida. Ogni oggetto passa
    # dal lint di banda del motore (numeri in scala, mosse note): errore di
    # authoring qui, mai un degrado a runtime.
    from motore import lint_oggetto

    slug_oggetti = list(stagione.oggetti)
    if not slug_oggetti:
        slug_oggetti = [
            slug for slug, (asset, _vista)
            in sorted(_collezione("oggetti", ufficiali, locali).items())
            if asset is not None
        ]
    oggetti_risolti: list[OggettoAsset] = []
    for slug_ogg in slug_oggetti:
        ogg = carica_asset("oggetti", slug_ogg, ufficiali=ufficiali, locali=locali)
        if ogg is None:
            errori.append(f"oggetto riferito ma assente: {slug_ogg}")
            continue
        errori.extend(lint_oggetto(ogg, mosse_ammesse=note_mosse))
        oggetti_risolti.append(ogg)
    # Le MOSSE-ASSET (T3a, stessa politica lasca): il validator Pydantic è il
    # gate di composizione (PMF-6.4) — qui si risolvono i riferimenti.
    slug_mosse = list(stagione.mosse)
    if not slug_mosse:
        slug_mosse = [
            slug for slug, (asset, _vista)
            in sorted(_collezione("mosse", ufficiali, locali).items())
            if asset is not None
        ]
    mosse_risolte: list[MossaAsset] = []
    for slug_mossa in slug_mosse:
        mossa = carica_asset("mosse", slug_mossa, ufficiali=ufficiali, locali=locali)
        if mossa is None:
            errori.append(f"mossa riferita ma assente: {slug_mossa}")
            continue
        mosse_risolte.append(mossa)
    # La FABBRICA del loot procedurale (lasca: senza slug dichiarato vale la
    # prima valida in libreria; nessuna = niente conio procedurale).
    fabbrica_risolta = None
    slug_fabbrica = stagione.fabbrica
    if slug_fabbrica is None:
        disponibili_fabbriche = sorted(
            slug for slug, (asset, _vista)
            in _collezione("fabbriche", ufficiali, locali).items()
            if asset is not None
        )
        slug_fabbrica = disponibili_fabbriche[0] if disponibili_fabbriche else None
    if slug_fabbrica is not None:
        fabbrica_risolta = carica_asset(
            "fabbriche", slug_fabbrica, ufficiali=ufficiali, locali=locali)
        if fabbrica_risolta is None:
            errori.append(f"fabbrica riferita ma assente: {slug_fabbrica}")
    if errori:
        raise ValueError("stagione non risolvibile:\n- " + "\n- ".join(errori))
    return StagioneRisolta(
        slug=stagione.slug, versione=stagione.versione, tags=stagione.tags,
        numero=stagione.numero, titolo=stagione.titolo, tagline=stagione.tagline,
        mondo=stagione.mondo, stile=stagione.stile, lore=stagione.lore,
        piani=piani_risolti, archetipi=archetipi_risolti, oggetti=oggetti_risolti,
        mosse=mosse_risolte, fabbrica=fabbrica_risolta,
    )


# --- Affinity matching: il riuso degli asset (gli architetti del dungeon) --------
#
# Scoring DETERMINISTICO sui tag: espliciti + impliciti (le categorie contano
# come tag). Zero LLM, zero costo. Questa firma è la PORTA dietro cui, post-MVP,
# si innesta il recupero semantico via embeddings ("prima pesca, poi genera",
# G): richiede un'estensione del contratto Provider (PLK: oggi un solo verbo
# `genera`) — decisione di spec futura, qui solo annotata.

def _tags_asset(tipo: str, asset) -> set[str]:
    tags = set(asset.tags)
    if tipo == "mob":
        tags |= {asset.archetipo, asset.grado.value}
        tags |= {b.value for b in asset.blocchi}
    elif tipo == "piani":
        tags |= set(asset.budget.archetipi)
        tags |= {g.value for g in asset.budget.gradi}
    return tags


def affini(
    tags: list[str], *, tipo: str, k: int = 5, escludi: tuple[str, ...] = (),
    ufficiali: Path | None = None, locali: Path | None = None,
) -> list[AssetVista]:
    """Gli asset della collezione più affini ai tag dati, ordinati per punteggio
    (sovrapposizione, poi Jaccard, poi slug — stabile e riproducibile)."""
    richiesti = {t.strip().lower() for t in tags if t.strip()}
    if not richiesti:
        return []
    classifica: list[tuple[float, float, str, AssetVista]] = []
    for slug, (asset, vista) in _collezione(tipo, ufficiali, locali).items():
        if asset is None or slug in escludi:
            continue
        propri = _tags_asset(tipo, asset)
        sovrapposizione = len(richiesti & propri)
        if sovrapposizione == 0:
            continue
        jaccard = sovrapposizione / len(richiesti | propri)
        classifica.append((-sovrapposizione, -jaccard, slug, vista))
    classifica.sort()
    return [vista for *_resto, vista in classifica[:k]]


def _skills_di(entita: int) -> tuple[SkillVista, ...]:
    """Le skill dell'entità per la scheda: repertorio (dato) × catalogo (numeri).

    Fuori scontro `Ricariche` non esiste → `cd_residuo=0` per costruzione: mai un
    valore stantio. `pronta` riflette comunque il MANA, che è posseduto e persiste:
    in narrazione la scheda può dire "non pronta" — ed è l'informazione che spinge
    a riposare."""
    voci = []
    for chiave in mosse_di(entita):
        mossa = mossa_di_catalogo(chiave)
        if mossa is None:
            continue  # chiave fuori catalogo (dato incompleto): non si inventa nulla
        voci.append(SkillVista(
            chiave=chiave,
            etichetta=etichetta_mossa(chiave),
            costo_mana=mossa.costo_mana,
            cd_totale=mossa.cooldown,
            cd_residuo=cooldown_residuo(entita, chiave),
            pronta=mossa_pagabile(entita, chiave),
        ))
    return tuple(voci)


def _equip_di(entita: int) -> tuple[EquipVista, ...]:
    """Gli slot di equipaggiamento, uno per slot **reale** (ADR-1 F1).

    Due sorgenti, in cascata, che è la stessa cascata delle derivate:
      1. il `ComponenteEquip` — l'oggetto davvero indossato in quello slot;
      2. la **geometria** attiva (`Corredo`, o i default §11) — la categoria che muove i
         numeri quando nessun oggetto occupa lo slot.

    Uno slot vuoto NON è un buco nella scheda: mostra la geometria che vale comunque
    (`veste`, `naturale`), perché è quella a decidere `coeff_eva`/`coeff_acc`. È il
    motivo per cui `categoria` esisteva già prima degli oggetti."""
    armatura, _taglia, arma = geometria_di(entita)
    comp = equip_attivo(entita)

    def _riga(slot: SlotEquip) -> EquipVista:
        indossato = None
        if comp is not None:
            indossato = comp.arma if slot is SlotEquip.ARMA else comp.armatura.get(slot)
        if indossato is None:
            return EquipVista(
                slot=slot, categoria=arma if slot is SlotEquip.ARMA else armatura
            )
        categoria = (
            indossato.taglia.value if slot is SlotEquip.ARMA else indossato.categoria.value
        )
        return EquipVista(slot=slot, nome=indossato.nome, categoria=categoria)

    return tuple(_riga(slot) for slot in SlotEquip)


def _etichetta_mossa_ricca(entita: int, chiave: str) -> str:
    """L'etichetta di menu che DICE il costo: "Dardo arcano — 3 mana", e in ricarica
    "Colpo pesante — ricarica (1)". Composizione di presentazione: vive nel port,
    non nel motore (che possiede i numeri, non le frasi). Il ribattezzo del
    Guardaroba (premi.skill) vince sul nome di catalogo."""
    from motore import guardaroba_attivo

    guardaroba = guardaroba_attivo(entita)
    base = (guardaroba.mosse_vesti.get(chiave) if guardaroba is not None else None) \
        or etichetta_mossa(chiave)
    residuo = cooldown_residuo(entita, chiave)
    if residuo > 0:
        return f"{base} — ricarica ({residuo})"
    _mossa = mossa_di_catalogo(chiave)
    costo = _mossa.costo_mana if _mossa is not None else 0
    return f"{base} — {costo} mana" if costo else base


class IstanzaCombattimento:
    """L'istanza SEPARATA del combattimento: il modello deterministico con le SUE
    interazioni (FNC §5.2 — la pipeline GM qui non gira mai, G-4).

    Nasce all'ingaggio, pilota il loop deterministico (un `tick` per azione), ascolta
    il bus e **raccoglie i fatti** dello scontro; alla chiusura i `FattiScontro`
    rientrano nel fascicolo del primo turno GM successivo (risolvi prima, narra dopo).

    Il MENU è dinamico: una voce per mossa del `Repertorio` del protagonista (il
    binding indice→chiave vive qui, come `_scena` per la narrazione — il contratto
    `OpzioneVista` non porta chiavi di mossa) + "Fuggi" SEMPRE ULTIMA.
    """

    def __init__(self, bus, *, nemico: str = "") -> None:
        self.bus = bus
        self.nemico = nemico
        self._turni = 0
        self._hp_iniziali = protagonista()[2].punti_vita
        self._conclusa = False
        self._vittoria = False
        self._fuga = False
        # I MOMENTI salienti (Fase 5): stringhe deterministiche dal bus — primo
        # sangue, status applicati, colpo di grazia. L'AI del resoconto li VESTE,
        # non li inventa (risolvi prima, narra dopo).
        self._momenti: list[str] = []
        self._ultimo_colpo = ""
        self._coppie = [
            (CombatResolved, self._su_resolved), (MortePersonaggio, self._su_morte),
            (ColpoInferto, self._su_colpo), (StatusApplicato, self._su_status),
        ]
        for tipo, handler in self._coppie:
            bus.registra(tipo, handler)

    @staticmethod
    def _chi(diegetico: str) -> str:
        return diegetico or "il crawler"  # "" = protagonista (contratto eventi)

    def _annota(self, riga: str) -> None:
        if len(self._momenti) < 5 and riga not in self._momenti:
            self._momenti.append(riga)

    def _su_colpo(self, e: ColpoInferto) -> None:
        riga = f"{self._chi(e.attaccante)} colpisce {self._chi(e.bersaglio)}"
        if e.mossa and e.mossa != "attacco":
            riga += f" con {etichetta_mossa(e.mossa)}"
        if not self._momenti:
            self._annota(f"primo sangue: {riga}")
        self._ultimo_colpo = riga

    def _su_status(self, e: StatusApplicato) -> None:
        self._annota(f"{e.fonte or 'il crawler'} infligge {e.status} "
                     f"a {self._chi(e.bersaglio)}")

    def _su_resolved(self, evento: CombatResolved) -> None:
        self._conclusa = True
        self._vittoria = bool(getattr(evento, "vittoria", False))
        self._fuga = bool(getattr(evento, "fuga", False))
        if self._vittoria and self._ultimo_colpo:
            # Fuori dal cap: la chiusura si racconta sempre.
            momento = f"colpo di grazia: {self._ultimo_colpo}"
            if momento not in self._momenti:
                self._momenti.append(momento)

    def _su_morte(self, _evento: MortePersonaggio) -> None:
        self._conclusa = True  # permadeath: lo scontro non si chiude, la run sì

    def _mosse(self) -> tuple[str, ...]:
        """Le chiavi del menu, nell'ordine del Repertorio (la fonte è il motore)."""
        return mosse_di(protagonista()[0])

    @property
    def opzioni(self) -> tuple[OpzioneVista, ...]:
        pent = protagonista()[0]
        voci = []
        for i, chiave in enumerate(self._mosse()):
            pagabile = mossa_pagabile(pent, chiave)
            voci.append(OpzioneVista(
                indice=i,
                etichetta=_etichetta_mossa_ricca(pent, chiave),
                tipo=TipoAzione.COMBATTI,
                abilitata=pagabile,
            ))
        voci.append(OpzioneVista(indice=len(voci), etichetta="Fuggi", tipo=TipoAzione.SCAPPA))
        return tuple(voci)

    def agisci(self, indice: int) -> str | None:
        """Un comando del giocatore = il SUO turno + le risposte dei nemici, in un
        colpo solo (feel: il click non "esegue il turno del mob" in silenzio).
        L'ULTIMA voce (Fuggi) marca il turno come tentativo di disimpegno (FNC §4);
        le altre chiedono la mossa scelta: prova e risoluzione le tira il MOTORE
        dentro il suo sistema-turno.

        Ritorna `None` se il turno è stato speso, altrimenti il MOTIVO del
        rifiuto: un click non resta MAI muto (l'host lo scrive in chat)."""
        mosse = self._mosse()
        if self._conclusa:
            return "Lo scontro è già concluso: la scena sta per riprendere."
        if not (0 <= indice <= len(mosse)):
            return "Scelta non valida."
        if indice == len(mosse):
            richiedi_fuga()
        elif not richiedi_mossa(mosse[indice]):
            # Porta del motore: mossa non pagabile → il turno NON si spende.
            return (f"{etichetta_mossa(mosse[indice])} non è pagabile adesso "
                    "(mana o ricarica): il turno non si spende.")
        tick()  # il turno del protagonista (mossa scelta, o tentativo di fuga)
        self._turni += 1
        # Il giro dei nemici, fino a tornare al protagonista (guardia difensiva).
        guardia = 0
        while (
            not self._conclusa
            and in_combattimento()
            and not prossimo_attivo_e_protagonista()
            and guardia < 16
        ):
            tick()
            guardia += 1

    @property
    def conclusa(self) -> bool:
        return self._conclusa

    def fatti(self) -> FattiScontro:
        """I FATTI dello scontro per il GM (selezione, mai stat vive)."""
        hp_ora = protagonista()[2].punti_vita
        return FattiScontro(
            vittoria=self._vittoria,
            turni=self._turni,
            hp_persi=max(0, self._hp_iniziali - hp_ora),
            nemico=self.nemico,
            fuga=self._fuga,
            momenti=tuple(self._momenti),
        )

    def chiudi(self) -> None:
        for tipo, handler in self._coppie:
            try:
                self.bus.deregistra(tipo, handler)
            except ValueError:
                pass
        self._coppie = []


class SalvataggioInCombattimento(RuntimeError):
    """Salvare/uscire a scontro aperto è vietato per disegno: gli effimeri di
    combattimento non persistono ma `FaseCorrente` sì — quel save si ricarica
    "in combattimento" senza scontro (soft-lock permanente, audit 2026-08)."""


def _serializza_rng(rng: random.Random) -> list:
    """`Random.getstate()` in forma JSON-safe (il seam `rng_state` del save, H)."""
    versione, interno, gauss = rng.getstate()
    return [versione, list(interno), gauss]


def _ripristina_rng(rng: random.Random, dati: list) -> None:
    """Inverso LASCO di `_serializza_rng`: dato malformato → si riparte dal seed
    (degrado, non crash — H-12)."""
    try:
        versione, interno, gauss = dati
        rng.setstate((int(versione), tuple(int(x) for x in interno), gauss))
    except (TypeError, ValueError):
        pass


# --- Una sola run per processo: la collisione diventa RUMOROSA -------------------
#
# Il run-World ha un nome FISSO (`NOME_RUN`): due sessioni aperte nello stesso
# processo condividerebbero IN SILENZIO lo stesso mondo — la seconda smonta e
# ricrea "run" sotto i piedi della prima, che da lì in poi legge la scheda
# dell'altra e ne SALVA il file sotto il proprio percorso (riprodotto, audit
# fondamenta 2026-08). Il registro rende la violazione un errore: aprire una
# sessione INVALIDA la precedente ancora aperta, e ogni porta della sessione
# invalidata solleva invece di operare sul mondo altrui. (Weakref: il registro
# non tiene in vita una sessione abbandonata.)
_SESSIONE_ATTIVA: "weakref.ref[SessioneGioco] | None" = None


def _invalida_sessione_precedente(nuova: "SessioneGioco | None" = None) -> None:
    """Da chiamare PRIMA di toccare il run-World (`nuova_partita`/`carica` lo
    smontano incondizionatamente): anche se l'ingresso poi FALLISCE, il mondo
    della precedente non c'è più — deve saperlo subito, non scoprirlo con un
    errore criptico dei check singleton su un World vuoto."""
    precedente = _SESSIONE_ATTIVA() if _SESSIONE_ATTIVA is not None else None
    if precedente is not None and precedente is not nuova and not precedente._chiusa:
        precedente._invalidata = (
            "un'altra sessione ha preso il run-World di questo processo "
            "(una sola run per processo): chiudi con esci()/chiudi_terminale() "
            "prima di aprirne un'altra"
        )


def _registra_sessione_attiva(sessione: "SessioneGioco") -> None:
    global _SESSIONE_ATTIVA
    _invalida_sessione_precedente(sessione)
    _SESSIONE_ATTIVA = weakref.ref(sessione)


def _rilascia_sessione_attiva(sessione: "SessioneGioco") -> None:
    global _SESSIONE_ATTIVA
    if _SESSIONE_ATTIVA is not None and _SESSIONE_ATTIVA() is sessione:
        _SESSIONE_ATTIVA = None


class SessioneGioco:
    """La porta motore↔host per la v1: narrazione async, intenti sul turno, snapshot.

    Possiede il run-World (via `Guscio`) e il provider. Non tiene una macchina di
    modo propria: il "modo" è la verità del motore (`in_combattimento()` + la scena
    composta dalla mappa). Vive nel composition root: può importare il motore —
    l'host (UI o driver headless) no, vi parla solo via porte.
    """

    def __init__(self, provider, *, directory: Path, seed: int = 0) -> None:
        # Cablaggio comune: il costruttore NON entra in run — lo fanno i factory
        # `nuova` (il protagonista nasce) e `da_salvataggio` (si deserializza),
        # al confine guscio→run (E-5).
        self.provider = provider
        self.rng = random.Random(seed)
        self.guscio = Guscio(directory)
        self.bus = self.guscio.bus
        self.coda = None  # CodaIntenti: nasce all'ingresso in run (dai factory)
        self.archivio: Archivio | None = None
        self.memoria: MemoriaTurni | None = None
        self.memoria_lunga: MemoriaSuArchivio | None = None  # porta narrativa (Fase 6)
        self.uuid = ""
        self.etichetta = ""  # il nome del crawler: etichetta dello slot di save
        self.ultimo_messaggio: MessaggioGM | None = None
        # Il motivo dell'ultimo click RIFIUTATO in combattimento (mossa non
        # pagabile, scontro concluso…): l'host lo scrive in chat — un click non
        # resta mai muto. Si azzera a ogni `avanza()`.
        self.ultimo_rifiuto: str | None = None
        # Callback (etichetta, frazione 0..1) per la barra di attesa dell'host: la
        # pipeline la chiama a ogni stadio; l'host la imposta, il motore non sa di UI.
        self.on_avanzamento = None
        self._chiusa = False  # run conclusa (esci/terminale): le porte si spengono
        self._invalidata: str | None = None  # run-World preso da un'altra sessione
        self._opzioni: tuple[OpzioneVista, ...] = ()
        self._scena: tuple[OpzioneScena, ...] = ()  # binding indice→azione di scena
        self._istanza: IstanzaCombattimento | None = None
        self._fatti_scontro: FattiScontro | None = None  # handoff scontro→GM
        self._fatti_epitaffio: FattiScontro | None = None  # fatti della morte (Fase 5)
        self._nome_mob = ""
        self._imboscata_in_corso = False  # lo scontro aperto è un'imboscata (Sit.5)
        # I dettagli (EntitaMob) dell'avversario dell'ULTIMO scontro aperto: la
        # lore che apertura/epitaffio mettono nel prompt. Sovrascritto a ogni
        # nuova istanza, MAI azzerato a scontro chiuso (l'epitaffio arriva dopo).
        self._dettagli_nemico = None
        # L'ultimo drop deciso dal motore, (fonte, grado): il dato FISSATO che
        # la vestizione AI dei premi potrà vestire, mai cambiare (T2b).
        self._ultimo_drop: tuple[str, str] | None = None
        # Il drop VINTO ma non ancora coniato (solo provider live): il GRADO
        # fissato dal motore — `veste_premio` conia, il flush lo garantisce.
        self._drop_pendente: str | None = None
        # Imboscata (Sit.5): un EncounterStarted che NON ha aperto questa sessione
        # (il dado-evento del tempo) deve comunque avere la sua istanza.
        self.bus.registra(EncounterStarted, self._su_incontro_esterno)

    @classmethod
    def nuova(
        cls,
        provider,
        *,
        directory: Path,
        nome: str = "Carl",
        seed: int = 0,
        n_stanze: int | None = None,
        stagione: StagioneAttiva | None = None,
    ) -> "SessioneGioco":
        """Nuova run: il protagonista NASCE al confine guscio→run. L'uuid identifica
        lo slot di save (slot = crawler, H §1); il nome ne è l'etichetta.
        `stagione` è il design RISOLTO e convertito: congelato nel World."""
        sessione = cls(provider, directory=directory, seed=seed)
        sessione.uuid = uuid4().hex[:8]
        sessione.etichetta = nome
        _invalida_sessione_precedente()  # l'ingresso in run smonta il World corrente
        # Niente literal: destrezza e HP di partenza vengono dalla calibrazione
        # (`CARL.destrezza`/`HP_DEFAULT`), così i knob della console valgono davvero.
        sessione.guscio.nuova_partita(
            uuid=sessione.uuid, seed=seed,
            n_stanze=n_stanze, stagione=stagione,
        )
        _registra_sessione_attiva(sessione)  # il run-World è suo
        sessione.coda = sessione.guscio.coda
        # La pipeline GM: l'Archivio (firma→record) e la memoria di run FRESCHI.
        sessione.archivio = Archivio(master_seed=master_seed(), model_id=MODEL_ID_DEFAULT)
        sessione.memoria = MemoriaTurni()
        sessione.memoria_lunga = MemoriaSuArchivio(sessione.archivio)
        return sessione

    @classmethod
    def da_salvataggio(
        cls, provider, *, directory: Path, uuid: str, seed: int = 0
    ) -> "SessioneGioco | None":
        """Riapre una run sospesa. `None` se il save è illeggibile (MENU intatto,
        H-12). L'Archivio di sessione RIPARTE dal sidecar: la cache firma→turno
        resta intatta (stanze già narrate RILETTE, la storia non si riscrive) e la
        memoria GM si RIDERIVA (la chat non si salva mai — H §11)."""
        # Sonda della BUSTA prima ANCORA di costruire il Guscio: il solo boot
        # parcheggia il contesto nel default, spostandolo sotto i piedi di una
        # sessione eventualmente aperta. Un save illeggibile a questo strato non
        # deve costare NULLA a nessuno (H-12: menu intatto E mondo intatto).
        try:
            carica_da_disco(directory, uuid)
        except CaricamentoFallito:
            return None
        sessione = cls(provider, directory=directory, seed=seed)
        # Da qui l'ingresso smonta il run-World corrente: la precedente va
        # invalidata anche se il PAYLOAD poi tradisce (il suo mondo è perduto).
        _invalida_sessione_precedente()
        if not sessione.guscio.carica(uuid):
            return None  # payload tradito: World smontato e contesto già al default
        _registra_sessione_attiva(sessione)  # il run-World è suo
        # Lo stream RNG di sessione riparte da dov'era (il seam `rng_state` del
        # save, prima scritto-e-mai-riletto): rilettura del corpo già validato.
        try:
            dati_rng = carica_da_disco(directory, uuid).corpo.rng_state
        except Exception:
            dati_rng = None  # lasco: senza stato si riparte dal seed (H-12)
        if dati_rng:
            _ripristina_rng(sessione.rng, dati_rng)
        if sessione.provider is None:
            # Offline: il copione si deriva dalla stagione CONGELATA nel save, mai dalla
            # libreria (che può essere cambiata sotto una run già avviata). Si riparte
            # dal piano CORRENTE e si copre anche la discesa che resta — riprendere una
            # partita al piano 2 non deve consumare il copione del piano 1.
            congelata = stagione_corrente()
            corrente = design_piano_corrente()
            if congelata is not None and corrente is not None:
                # Copione KEYED su (piano, stanza): al reload non serve alcun
                # riallineamento — le stanze già narrate rileggono l'Archivio e
                # ogni stanza nuova pesca la SUA voce, a qualunque profondità.
                sessione.provider = _fake_da_piani(congelata.piani)
            else:  # save legacy senza stagione congelata → la Falsa Idra
                sessione.provider = _fake_da_piano(corrente)
        sessione.uuid = uuid
        sessione.coda = sessione.guscio.coda
        sidecar = carica_archivio(directory, uuid)
        sessione.archivio = sidecar or Archivio(
            master_seed=master_seed(), model_id=MODEL_ID_DEFAULT
        )
        sessione.memoria = MemoriaTurni.ricostruisci(sessione.archivio)
        # La memoria narrativa RIPARTE dallo stesso sidecar: i documenti congelati
        # (record `memoria_doc`) sono già dentro l'Archivio ricaricato.
        sessione.memoria_lunga = MemoriaSuArchivio(sessione.archivio)
        sessione.etichetta = next(
            (v.etichetta for v in indice_crawler(directory) if v.uuid == uuid), uuid
        )
        messaggi = sessione.ricostruisci_thread()
        if messaggi:
            sessione.ultimo_messaggio = messaggi[-1]
        sessione._sincronizza_scena()
        return sessione

    # --- Porte verso l'host ---------------------------------------------------

    async def prossima_narrazione(self) -> SnapshotVista:
        """Coroutine host-agnostica (un worker UI o `asyncio.run` la `await`-a, C-6).

        Il turno passa dalla PIPELINE GM (`esegui_turno_gm`): fascicolo → ideazione →
        composizione (gating+gate) → limatura → scrittura (materializza al reveal,
        spesa tempo, memoria, Archivio). La stanza già visitata RILEGGE il suo turno
        congelato (firma, zero chiamate). I fatti di uno scontro appena chiuso entrano
        nel fascicolo (risolvi prima, narra dopo)."""
        self._guardia_aperta()
        if in_combattimento():  # la pipeline GM non gira nello scontro (istanza a parte)
            return self._snapshot_corrente()
        esito = await esegui_turno_gm(
            self.provider,
            archivio=self.archivio,
            memoria=self.memoria,
            rng=self.rng,
            bus=self.bus,
            esito_scontro=self._fatti_scontro,
            avanzamento=self.on_avanzamento,
            # Barriera: durante gli await del provider un'altra sessione può aver
            # preso il run-World — il ricontrollo scatta PRIMA della scrittura.
            guardia_scrittura=self._guardia_aperta,
            memoria_narrativa=self.memoria_lunga,
        )
        if not esito.da_cache:  # un turno riletto non consuma i fatti: li narrerà il prossimo
            self._fatti_scontro = None
        self.ultimo_messaggio = esito.messaggio
        if esito.risultato is not None:
            self._nome_mob = esito.risultato.turno.entita.nome
        self._sincronizza_scena()
        return self._snapshot_corrente(esito.messaggio.prosa)

    def riepiloga_azione(self, testo: str, tipo: TipoAzione = TipoAzione.ALTRO) -> RiepilogoAzione:
        """La finestra di conferma EDITABILE: 'Stai per…, corretto? Ti prenderà …'.
        Deterministica (calcolatore del tempo + seam skill), zero LLM."""
        self._guardia_aperta()  # legge il World: una sessione invalidata leggerebbe l'altrui
        return prepara_riepilogo(testo, tipo, self.memoria)

    async def esegui_azione(self, riepilogo: RiepilogoAzione) -> SnapshotVista:
        """Immissione: il testo (eventualmente editato) diventa l'azione del fascicolo
        e il turno GM risponde. Il testo libero NON tocca mai lo stato: viaggia solo
        nel prompt; l'unico ritorno meccanico è il turno gated (enum+budget)."""
        self._guardia_aperta()
        if in_combattimento():
            return self._snapshot_corrente()
        esito = await esegui_turno_gm(
            self.provider,
            archivio=self.archivio,
            memoria=self.memoria,
            rng=self.rng,
            bus=self.bus,
            azione=riepilogo.testo_proposto,
            esito_scontro=self._fatti_scontro,
            avanzamento=self.on_avanzamento,
            guardia_scrittura=self._guardia_aperta,  # come in prossima_narrazione
            memoria_narrativa=self.memoria_lunga,
        )
        if not esito.da_cache:
            self._fatti_scontro = None
        self.ultimo_messaggio = esito.messaggio
        self._sincronizza_scena()
        return self._snapshot_corrente(esito.messaggio.prosa)

    def _su_incontro_esterno(self, evento) -> None:
        """Sit.5: l'imboscata del dado-evento apre l'istanza di combattimento al
        volo. Gli ingaggi ordinari non passano di qui (l'istanza la crea
        `_agisci_narrazione` PRIMA di pubblicare l'evento)."""
        if self._istanza is not None or not getattr(evento, "imboscata", False):
            return
        self._imboscata_in_corso = True
        self._istanza = IstanzaCombattimento(
            self.bus, nemico=nome_nemico_incontro(evento.entita)
        )
        self._dettagli_nemico = entita_mob_incontro(evento.entita)

    def _engine(self) -> MasterEngine:
        """Il canale unico delle chiamate AI, sul provider CORRENTE (che può
        cambiare dopo il load: il copione offline si deriva dal save)."""
        prov = self.provider
        return prov if isinstance(prov, MasterEngine) else MasterEngine.avvolgi(prov)

    async def veste_premio(self) -> str | None:
        """Sit.3+4 (contratto premi): la VESTIZIONE del drop GIÀ deciso — il
        motore ha tirato SE e COSA (`_deposita_bottino`), l'AI battezza il
        cimelio (rotta `premi.oggetto`, gating). Gate anti-arbitraggio:
        base/grado/slot immutabili; rifiuto o degrado → resta il nome di
        catalogo (il deposito non dipende MAI da questa chiamata). Se il drop
        concede mosse, `premi.skill` le ribattezza (solo parole, D-3).
        `None` = niente da vestire o fallback silenzioso."""
        self._guardia_aperta()
        if self._drop_pendente is not None:
            return await self._conia_premio()
        if self._ultimo_drop is None:
            return None
        from contracts import Grado as _Grado
        from motore import (
            assicura_guardaroba,
            catalogo_oggetti_correnti,
            gate_premio,
            rango_grado,
        )

        fonte, grado = self._ultimo_drop
        self._ultimo_drop = None
        oggetto = catalogo_oggetti_correnti().get(fonte)
        if oggetto is None:
            return None
        slot = getattr(oggetto, "slot", None)
        prompt = "\n".join([
            f"[premio] Il drop è GIÀ deciso dal motore: base «{fonte}» "
            f"({type(oggetto).__name__.lower()}"
            f"{', slot ' + slot.value if slot is not None else ''}), "
            f"grado {grado}. Nome di catalogo: {getattr(oggetto, 'nome', '') or fonte}.",
            "[istruzione] Battezza il CIMELIO: `nome` memorabile (stile DCC), "
            "`descrizione` tagliente (1-2 frasi), `aspetto` (il dettaglio che si "
            "vede). Ricopia base/grado/slot ESATTI: sono immutabili — la "
            "vestizione è un nome, mai una leva.",
        ])
        candidato = await self._engine().genera(
            "premi.oggetto", prompt, sistema=PREFISSO_RIFINITURA
        )
        if candidato is None or gate_premio(candidato, fonte, grado) is not None:
            return None
        pent, _m, _s = protagonista()
        guardaroba = assicura_guardaroba(pent)
        dettagli = "; ".join(
            x for x in (candidato.descrizione, candidato.aspetto) if x
        )
        guardaroba.vesti[fonte] = (candidato.nome, dettagli)
        if (self.memoria_lunga is not None
                and rango_grado(_Grado(grado)) >= rango_grado(_Grado.ORO)):
            # Il premio memorabile è un EVENTO: il GM ricorda chi ha dato cosa.
            from contracts import DocumentoMemoria, TipoDocumento

            self.memoria_lunga.salva(DocumentoMemoria(
                id=f"premio-{fonte}", tipo=TipoDocumento.EVENTO,
                titolo=candidato.nome,
                testo=f"{grado}: {dettagli}" if dettagli else grado,
                tags=(fonte,),
            ))
        prosa = f"«{candidato.nome}» — {candidato.descrizione}"
        mosse = tuple(getattr(oggetto, "mosse", ()) or ())
        if mosse:
            riga_skill = await self._veste_skill(guardaroba, mosse[0])
            if riga_skill:
                prosa = f"{prosa}\n{riga_skill}"
        return prosa

    async def _conia_premio(self) -> str | None:
        """Il CONIO (la richiesta dell'utente 2026-08-11): a chance di drop
        VINTA, l'AI genera un oggetto NUOVO dentro il frame del motore — il
        GRADO è deciso seeded PRIMA della chiamata e non si negozia; lo schema
        (`OggettoAutorato`) non ha campi numerici; `gate_conio` valida forma,
        banda e mosse della run. Su rifiuto o degrado: deposito deterministico
        dal pool — il drop non dipende MAI dall'esito della chiamata."""
        from contracts import (
            CategoriaArmatura as _Cat,
            Fascia as _Fascia,
            SedeAccessorio as _Sede,
            Taglia as _Taglia,
        )
        from contracts.proiezione import SLOT_ARMATURA
        from motore import (
            assicura_coniati,
            gate_conio,
            mosse_note_correnti,
            rango_grado,
        )
        from contracts import Grado as _Grado

        grado = self._drop_pendente
        self._drop_pendente = None
        prompt = "\n".join([
            "[vocabolario/tipi] armatura, arma, accessorio",
            "[vocabolario/slot-armatura] " + ", ".join(s.value for s in SLOT_ARMATURA),
            "[vocabolario/categorie] " + ", ".join(c.value for c in _Cat),
            "[vocabolario/taglie] " + ", ".join(t.value for t in _Taglia),
            "[vocabolario/sedi] " + ", ".join(s.value for s in _Sede),
            "[vocabolario/fasce] " + ", ".join(f.value for f in _Fascia),
            "[vocabolario/mosse] " + ", ".join(sorted(mosse_note_correnti())),
            f"[premio] La chance di drop è VINTA e il motore ha fissato il "
            f"grado: {grado}.",
            "[istruzione] CONIA il cimelio: slug nuovo kebab-case, nome "
            "memorabile in stile DCC, descrizione tagliente (1-2 frasi); "
            "scegli tipo/slot/categoria/taglia/sede e le FASCE dei "
            f"modificatori dagli enum. `grado` DEVE essere \"{grado}\": è "
            "deciso, non negoziabile. Mosse (solo accessori) SOLO dal "
            "vocabolario. NIENTE numeri: i valori li deriva il motore.",
        ])
        candidato = await self._engine().genera(
            "premi.conio", prompt, sistema=PREFISSO_RIFINITURA
        )
        if candidato is not None:
            attivo, _motivo = gate_conio(
                candidato, grado, mosse_ammesse=mosse_note_correnti(),
            )
            if attivo is not None:
                pent, _m, _s = protagonista()
                assicura_coniati(pent).voci.append(attivo)
                assicura_zaino(pent).fonti.append(attivo.slug)
                self._ultimo_drop = None
                self.bus.pubblica(OggettoTrovato(nome=attivo.nome, fonte=attivo.slug))
                if (self.memoria_lunga is not None
                        and rango_grado(_Grado(grado)) >= rango_grado(_Grado.ORO)):
                    from contracts import DocumentoMemoria, TipoDocumento

                    self.memoria_lunga.salva(DocumentoMemoria(
                        id=f"premio-{attivo.slug}", tipo=TipoDocumento.EVENTO,
                        titolo=attivo.nome,
                        testo=f"{grado}: {attivo.descrizione}"[:300],
                        tags=(attivo.slug,),
                    ))
                return f"«{attivo.nome}» — {attivo.descrizione}"
        # Rifiuto del gate o degrado di trasporto: il drop non si perde.
        self._deposita_da_pool(grado)
        return None

    async def _veste_skill(self, guardaroba, chiave: str) -> str | None:
        """Il ribattezzo della mossa concessa (Sit.4, perimetro D-3): SOLO
        parole — la mossa vera resta la voce di catalogo, costi e numeri
        del §11. Un candidato che cambia la base degrada in silenzio."""
        from motore import mosse_note

        prompt = "\n".join([
            f"[skill] Il premio concede la mossa di catalogo «{chiave}» "
            f"({etichetta_mossa(chiave)}).",
            "[istruzione] Ribattezzala: `nome` memorabile in stile DCC e una "
            "`descrizione` breve. `mossa_base` DEVE restare la chiave esatta: "
            "il ribattezzo è narrativo, la meccanica non si tocca.",
        ])
        candidato = await self._engine().genera(
            "premi.skill", prompt, sistema=PREFISSO_RIFINITURA
        )
        if (candidato is None or candidato.mossa_base != chiave
                or chiave not in mosse_note()):
            return None
        guardaroba.mosse_vesti[chiave] = candidato.nome
        return f"La mossa {etichetta_mossa(chiave)} ora si chiama «{candidato.nome}»."

    def _riga_scena_nemico(self) -> str:
        """La riga `[scena/nemico]` dai dettagli dell'avversario corrente ("" se
        non c'è nulla da dire): descrizione troncata + aspetto/tratto."""
        em = self._dettagli_nemico
        if em is None:
            return ""
        pezzi = [p for p in (
            em.descrizione[:200],
            f"aspetto: {em.aspetto}" if em.aspetto else "",
            f"tratto: {em.tratto}" if em.tratto else "",
        ) if p]
        return f"[scena/nemico] {'; '.join(pezzi)}" if pezzi else ""

    async def prosa_apertura_scontro(self, *, imboscata: bool | None = None) -> str | None:
        """Sit.1 (Fase 5): il trailer d'apertura dello scontro — rotta
        `scontro.apertura`, non-gating, corsia veloce.

        Contratto d'uso NON bloccante: l'host la `await`-a DOPO il flip a
        combattimento — la riga deterministica «Lo scontro ha inizio.» è già in
        cronaca e lo scontro è già giocabile; questa prosa arriva quando arriva.
        `None` = degrado silenzioso (resta la riga fissa)."""
        self._guardia_aperta()
        if self._istanza is None:
            return None
        if imboscata is None:
            imboscata = self._imboscata_in_corso  # il flag lo sa la sessione (Sit.5)
        nemico = self._istanza.nemico or self._nome_mob or "il nemico"
        innesco = ("l'agguato è scattato: nessuno ha scelto questo scontro"
                   if imboscata else "il crawler ha scelto di combattere")
        righe = [
            f"[scena] Lo scontro si apre: davanti al crawler c'è {nemico}; {innesco}.",
        ]
        # La lore del nemico (T2): prima l'apertura riceveva SOLO il nome e il
        # modello re-inventava mob già scritti. Dinamica per scontro → nel
        # prompt utente; PREFISSO_RIFINITURA (cache) resta intatto.
        riga_nemico = self._riga_scena_nemico()
        if riga_nemico:
            righe.append(riga_nemico)
        righe.append(
            "[istruzione] 2-4 frasi cinematiche di APERTURA (un trailer): la "
            "minaccia entra in scena con un gesto che ne mostra il carattere. "
            "Nessun esito anticipato, nessun numero."
        )
        prompt = "\n".join(righe)
        flavor = await self._engine().genera(
            "scontro.apertura", prompt, sistema=PREFISSO_RIFINITURA
        )
        return flavor.testo if flavor is not None else None

    async def epitaffio(self) -> str | None:
        """La voce dello showrunner sulla schermata terminale (permadeath).

        Legge SOLO i fatti già raccolti (`_fatti_epitaffio`): nessuna guardia di
        run (la run è chiusa), nessun Archivio (lo slot è ritirato). `None` =
        nessuna morte registrata o degrado (resta la riga deterministica)."""
        fatti = self._fatti_epitaffio
        if fatti is None:
            return None
        righe = [
            f"[fine] Il crawler {self.etichetta or 'senza nome'} è morto: "
            f"{fatti.nemico or 'il dungeon'} ha chiuso lo scontro in "
            f"{fatti.turni} scambi.",
        ]
        # Il nemico che ti ha ucciso merita la sua descrizione (guardia sul nome:
        # niente lore stantia di uno scontro precedente).
        em = self._dettagli_nemico
        if em is not None and em.nome == (fatti.nemico or "") and em.descrizione:
            righe.append(f"[scena/nemico] {em.descrizione[:200]}")
        righe.append(
            "[istruzione] Un EPITAFFIO da showrunner: 2-4 frasi, ironia nera e un "
            "filo di rispetto — il pubblico saluta. Nessun numero."
        )
        prompt = "\n".join(righe)
        flavor = await self._engine().genera(
            "scontro.epitaffio", prompt, sistema=PREFISSO_RIFINITURA
        )
        return flavor.testo if flavor is not None else None

    def avanza(self) -> SnapshotVista:
        """Il **turno del motore** per l'host (IC §7.1) — drenaggio UNIFICATO:

        1. `travasa` (Canale A, l'unico travaso coda→World): il port NON preleva più
           dalla coda in proprio e NON scarta nulla;
        2. consuma SOLO gli intenti di menu (`PlayerChoseOption`) e li interpreta
           sulla fase corrente del motore e sulla scena mostrata;
        3. gli intenti di DOMINIO restano nel World per i sistemi phase-gated: quelli
           di esplorazione si servono su un turno del motore in NARRAZIONE (qui sotto);
           in COMBATTIMENTO attendono la fine dello scontro — la separazione
           esplorazione/combattimento è il phase-gate, non un filtro del port."""
        self._guardia_aperta()
        self.ultimo_rifiuto = None
        travasa(self.coda)
        for intento in consuma_messaggi(PlayerChoseOption):
            self._agisci(intento.opzione)
        travasa(self.coda)  # le scelte di scena possono aver accodato intenti di dominio
        if not in_combattimento() and messaggi_pendenti(IntentoEsplorazione):
            tick()  # un atto di esplorazione = un turno del motore (movimento, discesa)
        if self._istanza is not None and self._istanza.conclusa:
            # Chiusura dell'istanza di combattimento: i FATTI passano al prossimo
            # turno GM (risolvi prima, narra dopo — FNC §5.2).
            self._fatti_scontro = self._istanza.fatti()
            self._istanza.chiudi()
            self._istanza = None
            self._imboscata_in_corso = False
            if self._fatti_scontro is not None and self._fatti_scontro.vittoria:
                self._deposita_bottino()
            if (self._fatti_scontro is not None
                    and not self._fatti_scontro.vittoria
                    and not self._fatti_scontro.fuga
                    and not protagonista()[2].vivo):
                # Permadeath: i fatti restano leggibili per l'epitaffio anche a
                # run chiusa (la porta non tocca più il World).
                self._fatti_epitaffio = self._fatti_scontro
        self._sincronizza_scena()
        return self._snapshot_corrente()

    def fonti_indossate(self) -> tuple[str, ...]:
        """Le fonti INDOSSO (dal manifest), per l'host dell'inventario: `EquipVista`
        mostra la geometria per slot ma non porta la fonte, e il toggle
        indossa/togli ha bisogno dell'id di dominio durevole."""
        self._guardia_aperta()
        pent, _marker, _scheda = protagonista()
        comp = equip_attivo(pent)
        return comp.fonti() if comp is not None else ()

    def _provider_offline(self) -> bool:
        """Vero se il GM è il copione offline (FakeProvider e derivati): il
        conio non ha un modello da chiamare — il drop resta sincrono dal pool
        (comportamento storico, byte-identico)."""
        prov = self.provider
        if isinstance(prov, MasterEngine):
            from motore import Corsia

            prov = prov.provider_di(Corsia.FORTE)
        return isinstance(prov, FakeProvider)

    def _deposita_bottino(self) -> None:
        """Drop a scontro VINTO: il motore decide SE droppa (`PROB_DROP`) e il
        GRADO — pesato (`LOOT.PESO_GRADO.*`) dentro la finestra della
        profondità — SEEDED e PRIMA di qualunque chiamata AI (risolvi prima,
        narra dopo). Col provider OFFLINE deposita subito dal pool; col
        provider LIVE il drop resta PENDENTE e `veste_premio` prova a
        CONIARE l'oggetto nuovo (rotta gated `premi.conio`), con fallback
        deterministico al pool: il drop non si perde mai (flush in `salva()`
        e a ogni drop successivo)."""
        from motore import calibrazione as _cal
        from motore import gradi_per_profondita, rango_grado

        self._scarica_drop_pendente()   # cintura: mai due pendenti
        if self.rng.random() >= _cal.PROB_DROP:
            return
        finestra = [g.value for g in sorted(
            gradi_per_profondita(livello_corrente()), key=rango_grado)]
        pesi = [_cal.LOOT_PESO_GRADO[g] for g in finestra]
        tiro = self.rng.random() * (sum(pesi) or 1)
        cumulo, grado = 0.0, finestra[-1]
        for g, peso in zip(finestra, pesi):
            cumulo += peso
            if tiro < cumulo:
                grado = g
                break
        from motore import fabbrica_attiva

        if fabbrica_attiva() is not None and self.rng.random() < _cal.PROB_FABBRICA:
            # Il grosso del bottino è PROCEDURALE (stile BL3, in piccolo):
            # parti autorate × stream seeded — deterministico, gratuito,
            # identico offline e live. Il conio AI resta la via del pezzo
            # raro (quando la pesca non sceglie la fabbrica, col GM live).
            self._conia_dalla_fabbrica(grado)
        elif self._provider_offline():
            self._deposita_da_pool(grado)
        else:
            self._drop_pendente = grado

    def _conia_dalla_fabbrica(self, grado: str) -> None:
        """Il conio PROCEDURALE: base × famiglia × affissi per il grado deciso.
        L'oggetto entra nei coniati persistenti e nello zaino; `_ultimo_drop`
        resta armato — la vestizione AI può ancora dare la targhetta al pezzo,
        ma il pezzo esiste comunque (mai un drop appeso a una chiamata)."""
        from motore import assicura_coniati, conia_procedurale

        attivo = conia_procedurale(self.rng, grado)
        if attivo is None:
            self._deposita_da_pool(grado)
            return
        pent, _marker, _scheda = protagonista()
        assicura_coniati(pent).voci.append(attivo)
        assicura_zaino(pent).fonti.append(attivo.slug)
        self._ultimo_drop = (attivo.slug, grado)
        self.bus.pubblica(OggettoTrovato(nome=attivo.nome, fonte=attivo.slug))

    def _deposita_da_pool(self, grado: str) -> None:
        """Il deposito DETERMINISTICO dal pool (storico + congelati + coniati):
        candidati del grado deciso non posseduti; grado scoperto → qualunque
        non posseduto (mai un drop a vuoto per un buco di contenuto). Le
        pescate vengono dallo stream di sessione, in ordine fisso."""
        from motore import catalogo_oggetti_correnti, grado_oggetto

        pent, _marker, _scheda = protagonista()
        zaino = assicura_zaino(pent)
        catalogo = catalogo_oggetti_correnti()
        candidate = [f for f in sorted(catalogo)
                     if f not in zaino.fonti and grado_oggetto(f) == grado]
        if not candidate:
            candidate = [f for f in sorted(catalogo) if f not in zaino.fonti]
        if not candidate:
            return
        fonte = candidate[self.rng.randrange(len(candidate))]
        zaino.fonti.append(fonte)
        oggetto = catalogo[fonte]
        self._ultimo_drop = (fonte, grado_oggetto(fonte))
        self.bus.pubblica(OggettoTrovato(
            nome=getattr(oggetto, "nome", "") or fonte, fonte=fonte,
        ))

    def _scarica_drop_pendente(self) -> None:
        """Flush del drop vinto ma non coniato (host che non ha atteso, save
        imminente): deposito deterministico dal pool — il drop non si perde."""
        if self._drop_pendente is not None:
            grado = self._drop_pendente
            self._drop_pendente = None
            self._deposita_da_pool(grado)

    def equipaggia(self, fonte: str) -> SnapshotVista:
        """Porta dell'inventario (ADR-1 D3): Zaino → manifest, via l'intento
        tipizzato servito da `SistemaEquip` nel bucket di narrazione. In
        combattimento l'intento resta in coda (phase-gate): mai servito dalla
        fase sbagliata, mai più un intento che marcisce nel World."""
        self._guardia_aperta()
        self.coda.accoda(PlayerEquipaggia(fonte=fonte))
        return self.avanza()

    def togli(self, fonte: str) -> SnapshotVista:
        """Porta simmetrica: sfila l'oggetto per `fonte` (rimozione per fonte,
        mai operazione inversa — ADR-1 D1)."""
        self._guardia_aperta()
        self.coda.accoda(PlayerToglie(fonte=fonte))
        return self.avanza()

    def salva(self) -> str:
        """Salvataggio a mano, in-run (H-6): il World sopravvive, scrittura prima di
        ogni teardown. La mappa viaggia nello slot `esplorazione`; l'Archivio (i turni
        GM congelati) viaggia nel sidecar — non viene più azzerato. Etichetta e
        timestamp alimentano l'indice dell'hub (H §5)."""
        self._guardia_aperta()
        self._guardia_fase_salvataggio()
        self._scarica_drop_pendente()   # il drop vinto non si perde in un save
        salva_run(
            self.guscio.directory,
            archivio=self.archivio,
            model_id=MODEL_ID_DEFAULT,
            etichetta=self.etichetta,
            timestamp=time.time(),
            esplorazione=mappa_to_dict(),
            # Lo stream RNG di sessione (anomalie, disimpegni, seed di scontro)
            # riprende da DOVE si era: mai da capo dopo un load.
            rng_state=_serializza_rng(self.rng),
        )
        return "Partita salvata."

    # --- Ciclo di vita della run (hub): scheda, thread, uscita, terminale -------

    def _guardia_aperta(self) -> None:
        if self._invalidata:
            # Prima della guardia questa sessione avrebbe operato IN SILENZIO sul
            # mondo dell'altra (letto la sua scheda, salvato il suo file).
            raise RuntimeError(f"sessione invalidata: {self._invalidata}")
        if self._chiusa:
            raise RuntimeError("sessione chiusa: la run è già stata conclusa")

    def _guardia_fase_salvataggio(self) -> None:
        """Il salvataggio in COMBATTIMENTO è vietato: gli effimeri di scontro
        (`StatoCombattimento`, `Combattente`, `PuntiVita`…) non sono persistenti
        per disegno, ma `FaseCorrente` sì — un save a metà scontro si ricarica
        "in combattimento" senza scontro: soft-lock permanente della run
        (audit 2026-08). Lo scontro è corto (TTK 3–6 round): si risolve o si
        fugge, poi si salva."""
        if in_combattimento():
            raise SalvataggioInCombattimento(
                "Non si salva in combattimento: risolvi lo scontro (o fuggi) e riprova."
            )

    def ricostruisci_thread(self) -> list[MessaggioGM]:
        """Il thread dei turni GM congelati (per l'host, al caricamento): la chat
        non si salva, si RIDERIVA dall'Archivio (H §11)."""
        return messaggi_da_archivio(self.archivio)

    def scheda(self) -> SchedaVista:
        """La scheda del protagonista per la UI del giocatore: numeri PALESI ammessi
        (a differenza della proiezione per l'AI). Visibilità applicata a monte:
        `primarie` = solo PALESI (effettive), occulte per nome, fortuna MAI."""
        self._guardia_aperta()
        pent, marker, scheda = protagonista()
        proiezione = proietta_scheda(pent)
        return SchedaVista(
            uuid=marker.id_dominio,
            nome=self.etichetta,
            vivo=scheda.vivo,
            hp=scheda.punti_vita,
            hp_max=max_hp(pent),
            descrittori=proiezione.descrittori,
            primarie=dict(proiezione.primarie),
            primarie_occulte=proiezione.primarie_occulte,
            derivate={
                "attacco": attacco(pent),
                "iniziativa": iniziativa(pent),
                "colpo": atk_eff(pent),
                "difesa": def_eff(pent),
                # Evasione/accuratezza sono GRANDEZZE (stat × coefficiente di
                # geometria, §5.3-§5.4), non probabilità: si mostrano arrotondate.
                "evasione": int(round(eva_eff(pent))),
                "accuratezza": int(round(acc_eff(pent))),
            },
            livello=livello_corrente(),
            tick_piano=tempo_piano_corrente(),
            mana=assicura_mana(pent).attuale,
            mana_max=max_mana(pent),
            skills=_skills_di(pent),
            equip=_equip_di(pent),
            zaino=fonti_zaino(pent),
            progressione=ProgressioneVista(livello_piano=livello_corrente()),
        )

    def esci(self) -> str:
        """Salva-ed-esci (terminale 6c): l'Archivio di SESSIONE va nel sidecar
        (mai il fallback del guscio), con etichetta e timestamp per l'indice.
        Dopo, la sessione è chiusa: run-World smontato, porte spente."""
        self._guardia_aperta()
        self._guardia_fase_salvataggio()
        self.guscio.esci_volontariamente()
        self.guscio.concludi(
            archivio=self.archivio, etichetta=self.etichetta, timestamp=time.time(),
            rng_state=_serializza_rng(self.rng),
        )
        self._chiusa = True
        _rilascia_sessione_attiva(self)
        return "Partita salvata: puoi riprenderla dall'hub."

    def chiudi_terminale(self) -> str:
        """Chiusura della run TERMINATA (morte 6a / piano completato 6b): il guscio
        ha già rilevato il terminale sul bus; qui l'hand-off — che INVALIDA il save
        (permadeath, H-20) — e il teardown."""
        self._guardia_aperta()
        self.guscio.concludi()
        self._chiusa = True
        _rilascia_sessione_attiva(self)
        return "Run conclusa: lo slot è stato ritirato."

    # --- Interpretazione delle scelte (sulla verità del motore, non su un modo) -

    def _agisci(self, indice: int) -> None:
        if in_combattimento():
            self._agisci_combattimento(indice)
        elif 0 <= indice < len(self._scena):
            self._agisci_narrazione(self._scena[indice])

    def _agisci_narrazione(self, azione: OpzioneScena) -> None:
        if azione.tipo is TipoAzione.SCENDI:
            self.coda.accoda(PlayerDiscende())  # la serve SistemaDiscesa (gate: scala)
            return
        if azione.tipo is TipoAzione.ATTRAVERSA:
            # Il passaggio di zona: lo serve SistemaAttraversamento (gate:
            # stanza-passaggio + boss battuto; per le DEVIAZIONI: partenza,
            # destinazione composta dalla scena), unico proprietario.
            self.coda.accoda(PlayerAttraversa(destinazione=azione.zona or ""))
            return
        if azione.tipo is TipoAzione.MUOVI and azione.stanza is not None:
            self.coda.accoda(PlayerSiMuove(azione.stanza))  # la serve SistemaMovimento
            return
        if azione.tipo is TipoAzione.RIPOSA:
            # ⚠️ Ramo ESPLICITO prima del fallback di ingaggio: senza, «Riposa»
            # sarebbe caduto nel ramo finale e avrebbe APERTO UNO SCONTRO (la
            # mina del fall-through, giro 2026-08-07). Il riposo è del motore:
            # tick spesi via fast-forward, recupero da foglie §11, evento in cronaca.
            riposa(self.bus)
            return
        if azione.tipo is TipoAzione.SCAPPA:
            # Disimpegno: prova su stat PRIMA di ingaggiare (FNC §5.3, tirata dal motore).
            # La destrezza passa dal fold (GR2-3), non da un campo della scheda.
            pent, _m, _scheda = protagonista()
            # La classe la impone il MOB della scena (il suo `Grado`), non una costante:
            # disimpegnarsi da uno slime di bronzo e da un boss non è la stessa impresa.
            if tenta_disimpegno(stat_eff(pent, StatId.DESTREZZA), classe_disimpegno()):
                # ANTI-SOFTLOCK del boss di zona (territorio): il custode del
                # passaggio NON si dissolve col disimpegno — ti RITIRI nella
                # stanza precedente e lui resta al varco (altrimenti la zona si
                # aprirebbe per sparizione del boss, mai per vittoria).
                from motore import stanza_corrente_e_del_boss

                if stanza_corrente_e_del_boss():
                    self.bus.pubblica(DisimpegnoScena(nemico=nome_mob_corrente()))
                    _e, _mappa = mappa_corrente()
                    ritirata = min(_mappa.piano.adiacenze[_mappa.stanza_corrente])
                    _mappa.stanza_corrente = ritirata
                    from motore.calibrazione import DURATA_AZIONE as _DURATE

                    spendi_tempo(self.bus, _DURATE[TipoAzione.SCAPPA])
                    return
                # Il disimpegno si NARRA (prima il mob si dissolveva in silenzio
                # totale): l'evento parte col nome ancora leggibile, poi si smonta.
                self.bus.pubblica(DisimpegnoScena(nemico=nome_mob_corrente()))
                dissolvi_mob()  # fuga riuscita: l'incontro si dissolve, la scena si riapre
                # …e PAGA la sua durata (J): il docstring di `tenta_disimpegno` lo
                # dichiarava, il codice non lo faceva — scappare era gratis anche
                # in tick, e "scappa sempre" un room-clear senza costo.
                from motore.calibrazione import DURATA_AZIONE as _DURATE

                spendi_tempo(self.bus, _DURATE[TipoAzione.SCAPPA])
                return
        # Combatti (o disimpegno fallito): l'incontro è il nemico DELLA STANZA, arruolato
        # col suo profilo calibrato (Primarie/Corredo/Resistenze). Il fallback per scalari
        # resta solo per robustezza (scena senza mob registrato). Lo scontro è pilotato
        # da un'ISTANZA a parte, creata PRIMA dell'ingaggio (snapshot HP pre-scontro).
        mob = mob_corrente()
        # Il nome del nemico viene dall'ENTITÀ (verità del World): l'appunto
        # `_nome_mob` resta solo come ripiego per lo scalare senza mob registrato.
        self._istanza = IstanzaCombattimento(
            self.bus, nemico=nome_mob_corrente() or self._nome_mob
        )
        self._dettagli_nemico = dettagli_mob_corrente()
        ingaggia_combattimento(
            self.bus,
            nemici=None if mob is not None else [SpecNemico(destrezza=5, punti_vita=3)],
            arruolate=[mob] if mob is not None else None,
            seed=self.rng.randint(0, 10**9),
        )

    def _agisci_combattimento(self, indice: int) -> None:
        if self._istanza is not None:
            # L'istanza deterministica possiede lo scontro; un rifiuto (mossa non
            # pagabile, indice fuori scena) diventa feedback per l'host.
            self.ultimo_rifiuto = self._istanza.agisci(indice)
        elif indice >= 0:
            tick()  # difesa: scontro aperto fuori dal port (test/harness)

    def _sincronizza_scena(self) -> None:
        """Riallinea il menu alla verità del motore: in combattimento il menu
        dell'istanza (dinamico, dal Repertorio); altrimenti la SCENA composta dalla
        mappa. Scena vuota = stanza mai narrata ⇒ menu vuoto ⇒ l'host chiede un
        turno di narrazione."""
        if in_combattimento():
            self._scena = ()
            # UNA sola strada per il menu di combattimento: la property dell'istanza
            # (prima qui viveva una costante parallela — riunificate).
            self._opzioni = self._istanza.opzioni if self._istanza is not None else ()
            return
        self._scena = componi_opzioni_scena()
        self._opzioni = tuple(
            OpzioneVista(indice=i, etichetta=az.etichetta, tipo=az.tipo)
            for i, az in enumerate(self._scena)
        )

    # --- Costruzione dello snapshot dal World corrente ------------------------

    def _snapshot_corrente(self, prosa: str = "") -> SnapshotVista:
        """L'UNICO costruttore di `SnapshotVista`. Tutti i produttori passano di
        qui: un campo nuovo del contratto si aggiunge in un punto solo, e non
        esiste una via per cui una porta risponda con dati diversi da un'altra
        (era successo: due porte su tre ignoravano `terminale`/`profondita`)."""
        return SnapshotVista(
            # Vuota di default: la prosa di transizione arriva via eventi sul bus;
            # i turni GM la passano (sono l'unico caso che ne ha una).
            prosa=prosa,
            opzioni=self._opzioni,
            stato=self._descrittori(),
            fase="combattimento" if in_combattimento() else "narrazione",
            terminale=self.terminale,
            profondita=livello_corrente(),
        )

    @property
    def terminale(self) -> Terminale | None:
        """Come è finita la run, `None` se è in corso. È la PORTA che prima non
        c'era: gli host leggevano `guscio._terminale` (privato) o inseguivano gli
        eventi sul bus per capire che la partita era chiusa."""
        return self.guscio.terminale

    def _descrittori(self) -> tuple[str, ...]:
        pent, _marker, scheda = protagonista()
        # Clamp a zero: «HP -4/30» sull'ultima schermata di una run persa
        # comunica un motore rotto, non un overkill (giro 2026-08-07).
        hp = f"HP {max(0, scheda.punti_vita)}/{max_hp(pent)}"  # massimo DERIVATO (§5)
        # Il mana è una risorsa che ora si spende E si recupera: sta nel pannello
        # come gli HP. Lo zaino compare solo quando contiene qualcosa.
        extra: list[str] = [f"mana {assicura_mana(pent).attuale}/{max_mana(pent)}"]
        n_zaino = len(fonti_zaino(pent))
        if n_zaino:
            extra.append(f"zaino: {n_zaino}")
        if in_combattimento() and self.guscio.terminale is None:
            # Il giocatore VEDE chi affronta e quanto gli resta (feel G §5.6);
            # a run CONCLUSA il nemico non si elenca più — lo scontro non esiste.
            for nome, attuali, massimi in nemici_in_scontro():
                extra.append(f"{nome}: {attuali}/{massimi}")
        trovata = mappa_corrente()
        if trovata is not None:
            extra.append(f"stanza {trovata[1].stanza_corrente}")
        if self.ultimo_messaggio is not None:
            extra.append(f"tempo: {self.ultimo_messaggio.tempo.etichetta} "
                         f"(t{self.ultimo_messaggio.tempo.tick_correnti})")
        return (hp, *proietta_scheda(pent).descrittori, *extra)


# --- Cronaca del bus: eventi di dominio → righe di testo (headless, read-only) ----
#
# Lo stesso ruolo "consumatore read-only di eventi" che avrà una UI (IC §2.3), qui
# ridotto a testo: l'host headless si sottoscrive al bus e raccoglie ciò che il motore
# emette. Una UI futura sostituirà questo collettore senza toccare il motore.
def _riga_colpo(e: object) -> str:
    attaccante = getattr(e, "attaccante", "")
    bersaglio = getattr(e, "bersaglio", "")
    danno = getattr(e, "danno", 0)
    unita = "danno" if danno == 1 else "danni"      # «1 danni» era un plurale rotto
    hp = f"({getattr(e, 'hp_rimasti', 0)}/{getattr(e, 'hp_max', 0)})"
    mossa = getattr(e, "mossa", "")
    # La MOSSA si nomina (prima solo l'attacco pesante aveva un inciso): l'etichetta
    # diegetica viene dal catalogo, l'attacco base resta implicito.
    con = f" con {etichetta_mossa(mossa)}" if mossa and mossa != "attacco" else ""
    if attaccante == "":  # il protagonista colpisce
        return f"Colpisci {bersaglio or 'il nemico'}{con}: {danno} {unita} {hp}."
    return f"{attaccante} ti colpisce{con}: {danno} {unita} {hp}."


def _riga_status_applicato(e: object) -> str:
    chi = getattr(e, "bersaglio", "")
    status = getattr(e, "status", "")
    if chi == "":
        return f"Sei {_participio_status(status)}!"
    return f"{chi} è {_participio_status(status)}."


def _participio_status(status: str) -> str:
    return {
        "veleno": "avvelenato", "brucia": "in fiamme",
        "stordito": "stordito", "rigenerazione": "in rigenerazione",
    }.get(status, status)


def _riga_effetto_status(e: object) -> str:
    chi = getattr(e, "bersaglio", "")
    delta = getattr(e, "delta_hp", 0)
    nome_status = getattr(e, "status", "")
    if delta < 0:
        soggetto = "Il veleno" if nome_status == "veleno" else (
            "Le fiamme" if nome_status == "brucia" else nome_status.capitalize()
        )
        verbo = "mordono" if nome_status == "brucia" else "morde"
        if chi == "":  # il clitico va PRIMA del verbo: «morde ti» era sgrammaticato
            return f"{soggetto} ti {verbo}: {delta} HP."
        return f"{soggetto} {verbo} {chi}: {delta} HP."
    chi_bene = "Recuperi" if chi == "" else f"{chi} rigenera"
    return f"{chi_bene} {delta} HP."


def _riga_status_svanito(e: object) -> str:
    chi = getattr(e, "bersaglio", "")
    status = getattr(e, "status", "")
    nome = status.capitalize() if status else "L'effetto"
    if chi == "":
        return f"{nome} esaurito: non fa più effetto su di te."
    return f"{nome} esaurito su {chi}."


def _riga_riposo(e: object) -> str:
    """Il riassunto del riposo: quanto è costato e quanto ha reso. Interrotto =
    il recupero è parziale, e la cronaca lo dice invece di far sembrare che il
    riposo sia semplicemente reso poco."""
    tick = getattr(e, "tick_spesi", 0)
    hp = getattr(e, "hp_recuperati", 0)
    mana = getattr(e, "mana_recuperato", 0)
    resa = ", ".join(
        p for p in (f"+{hp} HP" if hp else "", f"+{mana} mana" if mana else "") if p
    ) or "niente"
    if getattr(e, "interrotto", False):
        return f"Riposo INTERROTTO dopo {tick} tick: {resa}."
    return f"Riposi ({tick} tick): {resa}."


def _riga_turno_saltato(e: object) -> str:
    if getattr(e, "causa", "") == "fuga_negata":
        return "Tenti la fuga: NEGATA, non c'è via d'uscita. Il turno è speso."
    nome = getattr(e, "nome", "")
    return "Sei stordito: salti il turno!" if nome == "" else f"{nome} è stordito: salta il turno."


def _riga_risolto(e: object) -> str:
    if getattr(e, "fuga", False):
        return "Ti disimpegni: fuga riuscita, lo scontro si dissolve."
    if getattr(e, "vittoria", False):
        return "Hai vinto lo scontro."
    return "Lo scontro si chiude."


def _riga_morte(e: object) -> str:
    """La morte è il beat più carico del giro: mai il literal dell'enum
    («Sei morto: sconfitta.») come ultima parola della run."""
    causa = getattr(e, "causa", "")
    dettaglio = f" ({causa})" if causa and causa != "sconfitta" else ""
    return f"Sei morto{dettaglio}. Il dungeon non fa repliche: la run finisce qui."


def _riga_discesa(e: object) -> str:
    """La discesa oltre l'ULTIMO piano è la vittoria: annunciare «Scendi: piano N»
    per un piano che non esiste era l'unico testo che il vincitore leggeva."""
    piano = getattr(e, "piano", "?")
    stagione = stagione_corrente()
    if (stagione is not None and isinstance(piano, int)
            and piano > len(stagione.piani)):
        return "Sali l'ultima scala: aria, luce, silenzio. La discesa è COMPLETA."
    return f"Scendi: piano {piano}."


def _riga_terminale(terminale: Terminale) -> str:
    """La riga di chiusura della run, per QUALUNQUE host (TUI/CLI/web): il dato
    `SnapshotVista.terminale` esisteva e nessuna superficie lo verbalizzava."""
    if terminale is Terminale.PIANO_COMPLETATO:
        return ("🏆 Fuori dall'ultima scala: la discesa è completa. Il dungeon, "
                "a malincuore, applaude — HAI VINTO la run.")
    if terminale is Terminale.SCONFITTA:
        return ("💀 Permadeath: lo slot è ritirato. Il dungeon ringrazia per la "
                "partecipazione.")
    return "La run è in pausa: il crawler ti aspetta dove l'hai lasciato."


_MAPPA_EVENTI: tuple[tuple[type, Callable[[object], str]], ...] = (
    (EncounterStarted, lambda e: (
        "⚠ Imboscata! Qualcosa ti è piombato addosso mentre il tempo scorreva."
        if getattr(e, "imboscata", False) else "Lo scontro ha inizio.")),
    (ColpoInferto, _riga_colpo),
    (StatusApplicato, _riga_status_applicato),
    (EffettoStatus, _riga_effetto_status),
    (StatusSvanito, _riga_status_svanito),
    (CrolloDungeon, lambda e: (
        f"Il dungeon perde la pazienza: tutto trema, tutti sanguinano "
        f"(-{getattr(e, 'danno', 0)} HP a testa).")),
    (DisimpegnoScena, lambda e: (
        f"Ti disimpegni: {getattr(e, 'nemico', '') or 'l’incontro'} non ti segue. "
        f"La scena si riapre.")),
    (TransizioneZona, lambda e: (
        "➤ Varchi il confine: " + {
            "quartiere": "un altro quartiere ti inghiotte.",
            "distretto": "il distretto si apre davanti a te.",
            "citta": "le luci di una città del dungeon.",
            "provincia": "la provincia, sterminata, ti dà il benvenuto.",
            "paese": "sei nel cuore di un paese del piano.",
            "piano": "la TANA. Qualcuno sta contando fino a dieci.",
        }.get(getattr(e, "tier", ""), "una zona nuova del piano."))),
    (OggettoTrovato, lambda e: (
        f"✦ Bottino: {getattr(e, 'nome', '') or getattr(e, 'fonte', '?')} "
        f"(nello zaino).")),
    (TurnoSaltato, _riga_turno_saltato),
    (CombatResolved, _riga_risolto),
    (MortePersonaggio, _riga_morte),
    (AnomalyTriggered, lambda _e: "Il dungeon ride: qualcosa è fuori scala…"),
    (DiscesaPiano, _riga_discesa),
    (RiposoConcluso, _riga_riposo),
)


class CronacaBus:
    """Raccoglie gli eventi di dominio dal bus e li rende come righe (host headless)."""

    def __init__(self, bus: BusEventi) -> None:
        self._bus = bus
        self._righe: list[str] = []
        self._coppie: list[tuple[type, Callable[[object], None]]] = []
        for tipo, formatta in _MAPPA_EVENTI:
            handler = self._fai_handler(formatta)
            bus.registra(tipo, handler)
            self._coppie.append((tipo, handler))

    def _fai_handler(self, formatta: Callable[[object], str]) -> Callable[[object], None]:
        def handler(evento: object) -> None:
            self._righe.append(formatta(evento))
        return handler

    def preleva(self) -> list[str]:
        """Restituisce e svuota le righe accumulate dall'ultima chiamata."""
        righe, self._righe = self._righe, []
        return righe

    def chiudi(self) -> None:
        """Deregistra gli handler: il bus è process-global, sopravvive all'host."""
        for tipo, handler in self._coppie:
            self._bus.deregistra(tipo, handler)
        self._coppie = []


# --- Freeze: dal DTO risolto all'aggregato ATTIVO del motore ---------------------

def _profilo_attivo(dati: ProfiloArchetipoDati) -> ProfiloArchetipo:
    """DTO (profilo PIENO, post-risoluzione) → dataclass del motore."""
    return ProfiloArchetipo(
        destrezza_base=dati.destrezza_base, pv_base=dati.pv_base,
        danno_base=dati.danno_base, intelligenza_base=dati.intelligenza_base,
        difesa_base=dati.difesa_base, saggezza_base=dati.saggezza_base,
        fortuna_base=dati.fortuna_base, armatura=dati.armatura,
        taglia=dati.taglia, arma=dati.arma,
        resistenze={
            tipo: getattr(dati, nome) or 0.0
            for nome, tipo in _CAMPI_RESISTENZE.items()
        },
    )


def _mob_a_attivo(mob: MobAsset) -> MobAttivo:
    """Conversione MobAsset→MobAttivo (usata per cast, roster boss e spawn)."""
    return MobAttivo(
        slug=mob.slug, nome=mob.nome, archetipo=mob.archetipo,
        grado=mob.grado, blocchi=list(mob.blocchi),
        descrizione=mob.descrizione, prosa_stanza=mob.prosa_stanza,
        durata=mob.durata, tags=list(mob.tags),
        mosse=list(mob.mosse),
        override=(
            mob.override.model_dump(exclude_none=True)
            if mob.override is not None else {}
        ),
    )


def _territorio_a_attivo(territorio) -> TerritorioAttivo | None:
    """Conversione TerritorioRisolto→TerritorioAttivo (tier/frequenze come
    `.value`: il componente congelato viaggia nel save col translator generico)."""
    if territorio is None:
        return None
    return TerritorioAttivo(
        conteggi={tier.value: n for tier, n in territorio.conteggi.items()},
        boss={
            tier.value: tuple(_mob_a_attivo(m) for m in roster)
            for tier, roster in territorio.boss.items()
        },
        procedurali=tuple(
            TabellaProceduraleAttiva(
                tier=t.tier.value, nomi=tuple(t.nomi),
                gimmick=tuple(t.gimmick), archetipi=tuple(t.archetipi),
            )
            for t in territorio.procedurali
        ),
        spawn={
            tabella.tier.value: tuple(
                VoceSpawnAttiva(mob=_mob_a_attivo(v.mob), frequenza=v.frequenza.value)
                for v in tabella.voci
            )
            for tabella in territorio.spawn
        },
        stanze_per_zona=territorio.stanze_per_zona,
    )


def _stagione_a_attiva(risolta: StagioneRisolta) -> StagioneAttiva:
    """Conversione DTO→dataclass al confine (la colla vive nel composition root)."""
    return StagioneAttiva(
        slug=risolta.slug,
        versione=risolta.versione,
        numero=risolta.numero,
        titolo=risolta.titolo,
        tagline=risolta.tagline,
        mondo=risolta.mondo,
        stile=list(risolta.stile),
        lore=risolta.lore,
        piani=[
            PianoAttivo(
                slug=piano.slug,
                titolo=piano.titolo,
                tema=piano.tema,
                stile=list(piano.stile),
                lore=piano.lore,
                gradi=list(piano.budget.gradi),
                blocchi=list(piano.budget.blocchi),
                archetipi=list(piano.budget.archetipi),
                cast=[_mob_a_attivo(mob) for mob in piano.cast],
                stanze=piano.stanze,
                tags=list(piano.tags),
                territorio=_territorio_a_attivo(piano.territorio),
            )
            for piano in risolta.piani
        ],
        tags=list(risolta.tags),
        archetipi=[
            ArchetipoAttivo(
                slug=arch.slug, nome=arch.nome, descrizione=arch.descrizione,
                profilo=_profilo_attivo(arch.profilo), mosse=list(arch.mosse),
            )
            for arch in risolta.archetipi
        ],
        oggetti=[
            OggettoAttivo(
                slug=ogg.slug, nome=ogg.nome, tipo=ogg.tipo,
                grado=ogg.grado.value, descrizione=ogg.descrizione,
                slot=ogg.slot.value if ogg.slot is not None else None,
                categoria=ogg.categoria.value if ogg.categoria is not None else None,
                taglia=ogg.taglia.value,
                sede=ogg.sede.value if ogg.sede is not None else None,
                mitigazione_cent=ogg.mitigazione_cent,
                danno_base=ogg.danno_base,
                modificatori=tuple(
                    (m.stat.value, m.fascia.value) for m in ogg.modificatori
                ),
                mosse=tuple(ogg.mosse),
            )
            for ogg in risolta.oggetti
        ],
        mosse=[
            MossaAttiva(
                chiave=mossa.slug,
                etichetta=mossa.etichetta,
                effetti=tuple(
                    EffettoAttivo(
                        primitivo=e.primitivo,
                        tipo_danno=e.tipo_danno.value if e.tipo_danno else None,
                        blocco=e.blocco.value if e.blocco else None,
                        potenza=e.potenza.value if e.potenza else None,
                        rischio=e.rischio.value if e.rischio else None,
                    )
                    for e in mossa.effetti
                ),
                costo=mossa.costo.value,
                ricarica=mossa.ricarica.value,
                azzardo=mossa.azzardo,
            )
            for mossa in risolta.mosse
        ],
        fabbrica=_fabbrica_a_attiva(risolta.fabbrica),
    )


def _fabbrica_a_attiva(fabbrica) -> "FabbricaAttiva | None":
    """FabbricaAsset → FabbricaAttiva (appiattita jsonable, pronta al freeze)."""
    if fabbrica is None:
        return None
    return FabbricaAttiva(
        basi=tuple(
            BaseAttiva(
                nome=b.nome, tipo=b.tipo,
                slot=b.slot.value if b.slot is not None else None,
                categoria=b.categoria.value if b.categoria is not None else None,
                taglia=b.taglia.value,
                sede=b.sede.value if b.sede is not None else None,
            )
            for b in fabbrica.basi
        ),
        famiglie=tuple(
            FamigliaAttiva(
                nome=f.nome, descrizione=f.descrizione,
                modificatori=tuple(
                    (m.stat.value, m.fascia.value) for m in f.modificatori),
            )
            for f in fabbrica.famiglie
        ),
        affissi=tuple(
            AffissoAttivo(
                nome=a.nome,
                res_contro=a.res_contro.value if a.res_contro is not None else None,
                res_fascia=a.res_fascia.value if a.res_fascia is not None else None,
                modificatori=tuple(
                    (m.stat.value, m.fascia.value) for m in a.modificatori),
            )
            for a in fabbrica.affissi
        ),
    )


def turni_da_piano(piano) -> list[TurnoNarrazione]:
    """Il copione offline DERIVATO dal cast del piano (una stanza per voce, in
    ordine). Accetta sia il DTO `PianoRisolto` sia il dataclass `PianoAttivo`
    (stessi campi sul cast: duck-typed). Esauriti i turni, l'orchestrazione
    degrada al fallback deterministico: il gioco non si blocca mai."""
    return [
        TurnoNarrazione(
            prosa=mob.prosa_stanza,
            entita=EntitaGenerata(
                archetipo=mob.archetipo,
                grado=mob.grado,
                blocchi=list(mob.blocchi),
                nome=mob.nome,
                descrizione=mob.descrizione,
                # Binding ESPLICITO mob→scena (D5): la stanza N monta IL mob N del
                # cast (override e mosse suoi), non un sosia posizionale.
                riferimento=mob.slug,
            ),
            durata=mob.durata,
        )
        for mob in piano.cast
    ]


def _turni_scriptati() -> list[TurnoNarrazione]:
    """RETRO-COMPAT: il copione della stagione di default (la Falsa Idra), oggi
    DERIVATO dalla libreria (`contenuti/`) — non più hardcoded."""
    return turni_da_piano(risolvi_stagione(STAGIONE_DEFAULT).piani[0])


class ProviderCopione(FakeProvider):
    """Copione offline **keyed su (piano, stanza)** — mai una coda posizionale.

    La FIFO per-visita aveva tre modi di rompersi, tutti misurati (giro 2026-08-07):
    un'azione libera consumava le voci della stanza successiva (risposta
    non-sequitur ORA e copione shiftato DOPO); scendere prima di aver visitato
    tutte le stanze regalava le voci residue del piano 1 ai reveal del piano 2
    (respinte dal gate → fallback congelato per sempre); il reload doveva
    "saltare" le stanze già narrate. Qui il copione risponde SOLO alla chiamata
    gating, con la voce della stanza in cui il protagonista si trova ORA:
    qualunque ordine di visita, azione libera o ricarica. Gli stadi ancillari
    (ideazione/limatura/distillazione/prova) degradano a `None`, come da
    contratto della pipeline.

    Sottoclasse di `FakeProvider` (stessa firma, stesso tracciamento di prompt
    opachi e `sistemi`; la coda FIFO ereditata resta vuota). Vive nel composition
    root e non in `provider/`: leggere mappa e profondità è lecito QUI, mai nel
    layer di trasporto."""

    def __init__(self, turni_per_livello: dict[int, list[TurnoNarrazione]]) -> None:
        super().__init__()
        self._turni_per_livello = turni_per_livello

    async def genera(self, prompt: str, schema, *, sistema: str = ""):
        if not isinstance(prompt, str):
            raise TypeError(
                f"il prompt verso il provider è una stringa opaca, non {type(prompt)!r} (G-13)"
            )
        self.chiamate.append((prompt, schema))
        self.sistemi.append(sistema)
        if schema is not TurnoNarrazione:
            return None                        # stadi ancillari: degrado dichiarato
        territoriale = self._turno_territoriale()
        if territoriale is not None:
            return territoriale
        turni = self._turni_per_livello.get(livello_corrente())
        trovata = mappa_corrente()
        if not turni or trovata is None:
            return None
        stanza = trovata[1].stanza_corrente
        if stanza >= len(turni):
            return None    # geometria più larga del cast: fallback onesto, mai shift
        return turni[stanza]

    @staticmethod
    def _turno_territoriale() -> TurnoNarrazione | None:
        """Il copione di un piano-mondo si COMPUTA dalla zona, on-demand: stanza
        boss → IL custode (`boss_della_zona`); stanza ordinaria → riempitivo
        pescato SEEDED per-stanza dalla tabella di spawn. Niente liste
        precompilate: la stessa lettura vale dopo un load o in qualunque ordine
        di visita (la rilettura resta compito dell'Archivio). `None` = piano
        piatto: si usa il copione keyed storico."""
        import random as _random

        from motore import (
            boss_della_zona,
            master_seed,
            pesca_spawn,
            stanza_boss_di,
            zona_corrente,
        )

        zona = zona_corrente()
        trovata = mappa_corrente()
        if zona is None or trovata is None:
            return None
        mappa = trovata[1]
        livello = livello_corrente()
        stanza = mappa.stanza_corrente
        if stanza == stanza_boss_di(zona, mappa.piano):
            mob = boss_della_zona(livello, zona)
        else:
            rng = _random.Random(
                f"{master_seed()}:copione:{livello}:{zona.chiave}:{stanza}"
            )
            mob = pesca_spawn(rng)
        if mob is None:
            return None  # tabella vuota: fallback onesto del gate
        return TurnoNarrazione(
            prosa=mob.prosa_stanza,
            entita=EntitaGenerata(
                archetipo=mob.archetipo, grado=mob.grado,
                blocchi=list(mob.blocchi), nome=mob.nome,
                descrizione=mob.descrizione, riferimento=mob.slug,
            ),
            durata=mob.durata,
        )


def _fake_da_piano(piano) -> ProviderCopione:
    """Copione da un piano solo (save legacy senza stagione congelata): la voce
    vive alla profondità CORRENTE del World appena caricato. `None` → la Falsa Idra."""
    if piano is None:
        piano = risolvi_stagione(STAGIONE_DEFAULT).piani[0]
    try:
        livello = livello_corrente()
    except Exception:
        livello = 1
    return ProviderCopione({livello: turni_da_piano(piano)})


def _fake_da_piani(piani) -> ProviderCopione:
    """Il copione di **tutta la discesa**, un piano per profondità (1-based).

    Keyed, non concatenato: ogni reveal, azione o rilettura riceve la voce della
    stanza in cui si trova — il piano 2 si racconta col SUO cast anche scendendo
    alla prima scala, e nessuna chiamata "consuma" il contenuto di qualcun altro."""
    return ProviderCopione({
        i + 1: turni_da_piano(piano) for i, piano in enumerate(piani)
    })


def costruisci_sessione(
    *,
    nome: str = "Carl",
    seed: int = 0,
    directory: Path | None = None,
    provider=None,
    stagione: Stagione | StagioneRisolta | str | None = None,
) -> SessioneGioco:
    """Cabla contenuto+provider → `SessioneGioco.nuova`. Senza `directory` la run
    vive in una tempdir usa-e-getta (demo/test).

    `stagione` (slug, DTO o risolta; default `stagione-1`) viene RISOLTA e
    congelata nella run. Offline (`provider=None`, default SICURO: mai rete
    implicita): il copione del FakeProvider e la scala del piano derivano dal
    piano 1 della stagione. Live: la scala è quella autorata (`stanze`) o la
    calibrazione (`MAPPA_STANZE`); il backend si INIETTA esplicitamente.
    `provider="auto"`: selezione dal composition root (`provider.scegli_provider`,
    live se chiave+SDK ci sono, altrimenti l'offline scriptato) — opt-in
    ESPLICITO, il default resta offline."""
    directory = directory or Path(tempfile.mkdtemp(prefix="dcc-"))
    if provider == "auto":
        from provider import scegli_provider

        provider, _etichetta = scegli_provider([])
    if isinstance(stagione, StagioneRisolta):
        risolta = stagione
    else:
        risolta = risolvi_stagione(stagione if stagione is not None else STAGIONE_DEFAULT)
    piano1 = risolta.piani[0]
    if provider is None:
        n_stanze = piano1.n_stanze  # il copione copre tutte le stanze del PRIMO piano
        # …ma il copione copre l'INTERA discesa: i piani successivi hanno la loro scala
        # (la mappa si rigenera scendendo) e il loro cast.
        provider = _fake_da_piani(risolta.piani)
    else:
        # Stessa scala dell'offline: `stanze` autorata se c'è, altrimenti la
        # taglia del CAST (una stanza per mob). Prima il live ripiegava su
        # MAPPA_STANZE (6): lo stesso contenuto produceva piani da 9 stanze
        # offline e da 6 live — mob senza stanza, misure non trasferibili.
        n_stanze = piano1.stanze if piano1.stanze is not None else piano1.n_stanze
    return SessioneGioco.nuova(
        provider,
        directory=directory,
        nome=nome,
        seed=seed,
        n_stanze=n_stanze,
        stagione=_stagione_a_attiva(risolta),
    )


def carica_sessione(
    *, uuid: str, directory: Path | None = None, provider=None
) -> SessioneGioco | None:
    """Riapre un crawler sospeso (`None` se illeggibile). Il provider offline si
    deriva DOPO il load, dalla stagione congelata nel save (mai dalla libreria:
    le run non vedono le modifiche di authoring)."""
    directory = directory or DIRECTORY_SALVATAGGI
    return SessioneGioco.da_salvataggio(provider, directory=directory, uuid=uuid)


_RE_UUID_CRAWLER = r"^[a-z0-9][a-z0-9-]{0,63}$"


def elimina_crawler(uuid: str, *, directory: Path | None = None) -> bool:
    """Elimina uno slot-crawler dall'hub: stato + sidecar Archivio + i backup
    `.bak` (pulizia completa: è la scelta volontaria del giocatore, non un
    terminale di run — H-20 intatto; H §10.4: nessun DRM contro il giocatore).
    L'uuid è validato (niente separatori di percorso). `False` se non c'era nulla."""
    import re

    if not re.fullmatch(_RE_UUID_CRAWLER, uuid):
        raise ValueError(f"uuid di crawler non valido: {uuid!r}")
    directory = directory or DIRECTORY_SALVATAGGI
    nomi = (
        f"{uuid}.stato.json",
        f"{uuid}.archivio.gz",
        f"{uuid}.bak.stato.json",
        f"{uuid}.bak.archivio.gz",
    )
    trovato = False
    for nome in nomi:
        percorso = directory / nome
        if percorso.exists():
            percorso.unlink()
            trovato = True
    return trovato


def elenca_crawler(directory: Path | None = None) -> list[CrawlerVista]:
    """L'elenco dei crawler salvati come DTO di membrana (per l'host, che non può
    toccare il motore). Scan delle sole intestazioni (H §5); voce corrotta =
    mostrata ma non caricabile (H-22)."""
    directory = directory or DIRECTORY_SALVATAGGI
    if not directory.exists():
        return []
    return [
        CrawlerVista(
            uuid=v.uuid,
            etichetta=v.etichetta,
            profondita=v.profondita,
            timestamp=v.timestamp,
            corrotta=v.corrotta,
        )
        for v in indice_crawler(directory)
    ]


def etichetta_oggetto(fonte: str) -> str:
    """Il nome diegetico di un oggetto del catalogo DELLA RUN ("" o ignoto → la
    fonte): l'host mostra parole, mai id di dominio nudi. La VESTIZIONE del
    Guardaroba (il nome battezzato dall'AI, gated) vince sul catalogo."""
    import esper

    from motore import catalogo_oggetti_correnti, guardaroba_attivo
    from motore.scheda import Protagonista

    for ent, _marker in esper.get_component(Protagonista):
        guardaroba = guardaroba_attivo(ent)
        if guardaroba is not None and fonte in guardaroba.vesti:
            return guardaroba.vesti[fonte][0]
    oggetto = catalogo_oggetti_correnti().get(fonte)
    nome = getattr(oggetto, "nome", "") if oggetto is not None else ""
    return nome or fonte


def _rendi(snapshot: SnapshotVista, stampa: Callable[[str], None]) -> None:
    """Rende uno snapshot come testo (sostituito in blocco, C-4)."""
    if snapshot.prosa:
        stampa(snapshot.prosa)
    stato = ", ".join(snapshot.stato) if snapshot.stato else "—"
    stampa(f"[{snapshot.fase}] {stato}")
    if snapshot.terminale is not None:
        stampa(_riga_terminale(snapshot.terminale))
        return
    for opz in snapshot.opzioni:
        stampa(f"  {opz.indice + 1}. {opz.etichetta}")


def _passo(
    sessione: SessioneGioco, indice: int, cronaca: CronacaBus, stampa: Callable[[str], None]
) -> SnapshotVista:
    """Un passo dell'host: accoda un intento tipizzato (host→motore, C-7), avanza il
    turno, drena la cronaca del bus e rende lo snapshot risultante."""
    sessione.coda.accoda(PlayerChoseOption(indice))
    snapshot = sessione.avanza()
    for riga in cronaca.preleva():
        stampa(riga)
    _rendi(snapshot, stampa)
    return snapshot


async def gioca_un_incontro(
    sessione: SessioneGioco,
    *,
    stampa: Callable[[str], None] = print,
    limite: int = 100,
) -> SnapshotVista:
    """Driver headless di riferimento: gioca un incontro completo via le sole porte.

    Narrazione (await della coroutine) → "Combatti" → "Attacca" finché lo scontro non si
    chiude e si torna alla narrazione. È la prova che il game engine gira end-to-end
    senza alcuna UI: una presentazione reale farebbe gli stessi passi via i suoi widget.
    """
    cronaca = CronacaBus(sessione.bus)
    try:
        snapshot = await sessione.prossima_narrazione()
        _rendi(snapshot, stampa)
        snapshot = _passo(sessione, 0, cronaca, stampa)  # "Combatti" → ingaggia
        guardia = 0
        while snapshot.fase == "combattimento" and guardia < limite:
            snapshot = _passo(sessione, 0, cronaca, stampa)  # "Attacca"
            guardia += 1
        return snapshot
    finally:
        cronaca.chiudi()


def main() -> None:  # pragma: no cover (entry point)
    sessione = costruisci_sessione(seed=1)
    asyncio.run(gioca_un_incontro(sessione))


if __name__ == "__main__":  # pragma: no cover
    main()
