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
    TurnoSaltato,
    CrawlerVista,
    MobAsset,
    ArchetipoAsset,
    PianoAsset,
    PianoRisolto,
    ProfiloArchetipoDati,
    EquipVista,
    ProgressioneVista,
    SchedaVista,
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
    PlayerDiscende,
    PlayerSiMuove,
    Opzione,
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
    nome_mob_corrente,
    MobAttivo,
    PianoAttivo,
    StagioneAttiva,
    design_piano_corrente,
    lint_registry,
    nemici_in_scontro,
    prossimo_attivo_e_protagonista,
    CATALOGO_MOSSE,
    cooldown_residuo,
    assicura_mana,
    etichetta_mossa,
    geometria_di,
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
    tempo_piano_corrente,
    tenta_disimpegno,
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
    "stagioni": Stagione, "piani": PianoAsset, "mob": MobAsset, "archetipi": ArchetipoAsset,
}


def _etichetta_asset(tipo: str, asset) -> str:
    return asset.nome if tipo in ("mob", "archetipi") else asset.titolo


def _tipo_vista(tipo: str) -> str:
    return {
        "stagioni": "stagione", "piani": "piano", "mob": "mob", "archetipi": "archetipo",
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


def _lint_mob_espressivo(mob: MobAsset, errori: list[str]) -> None:
    """Lint dell'espressività per-mob (Fase 5): mosse nel catalogo del motore,
    chiavi gear dell'override valide. Accumula errori di authoring."""
    from motore.calibrazione import COEFF_ACC, M_ARMATURA, M_TAGLIA

    fuori = [m for m in mob.mosse if m not in mosse_note()]
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
    slug: str, asset: ArchetipoAsset | None, errori: list[str]
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
    mosse = list(asset.mosse) if asset is not None else []
    fuori = [m for m in mosse if m not in mosse_note()]
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
        "mosse": sorted(mosse_note()),
        "archetipi": sorted(_archetipi_noti(ufficiali, locali)),
        "armature": list(M_ARMATURA),
        "taglie": list(M_TAGLIA),
        "armi": list(COEFF_ACC),
    }


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
                _lint_mob_espressivo(mob, errori)
                cast.append(mob)
        if mancanti:
            continue
        try:
            piani_risolti.append(
                PianoRisolto(
                    slug=piano.slug, versione=piano.versione, tags=piano.tags,
                    titolo=piano.titolo, tema=piano.tema, stile=piano.stile,
                    lore=piano.lore, budget=piano.budget, cast=cast, stanze=piano.stanze,
                )
            )
        except ValueError as errore:  # cast⊆budget imposto dal validator
            errori.append(f"piano {slug_piano}: {errore}")
        else:
            for slug_arch in list(piano.budget.archetipi) + [m.archetipo for m in cast]:
                if slug_arch not in slug_archetipi:
                    slug_archetipi.append(slug_arch)
            errori.extend(lint_registry([], piano.budget.blocchi))
    # Gli ARCHETIPI riferiti si risolvono come gli altri asset: profilo completato
    # (merge con la calibrazione per gli storici) e validato — è il vocabolario
    # chiuso che verrà congelato nella run (F-6 runtime, D1).
    archetipi_risolti: list[ArchetipoAsset] = []
    for slug_arch in slug_archetipi:
        asset_arch = carica_asset("archetipi", slug_arch, ufficiali=ufficiali, locali=locali)
        risolto = _risolvi_archetipo(slug_arch, asset_arch, errori)
        if risolto is not None:
            archetipi_risolti.append(risolto)
    if errori:
        raise ValueError("stagione non risolvibile:\n- " + "\n- ".join(errori))
    return StagioneRisolta(
        slug=stagione.slug, versione=stagione.versione, tags=stagione.tags,
        numero=stagione.numero, titolo=stagione.titolo, tagline=stagione.tagline,
        mondo=stagione.mondo, stile=stagione.stile, lore=stagione.lore,
        piani=piani_risolti, archetipi=archetipi_risolti,
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
        mossa = CATALOGO_MOSSE.get(chiave)
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
    """Gli slot di equipaggiamento. OGGI SEMPRE VUOTI di oggetti: il motore non ne
    ha: si espone la GEOMETRIA attiva (`Corredo`, o i default §11), che è ciò che
    muove davvero le derivate. Il giorno in cui esisteranno gli oggetti, `nome` si
    riempie e questa funzione resta della stessa forma."""
    armatura, _taglia, arma = geometria_di(entita)
    return (
        EquipVista(slot=SlotEquip.ARMA, categoria=arma),
        EquipVista(slot=SlotEquip.ARMATURA, categoria=armatura),
    )


def _etichetta_mossa_ricca(entita: int, chiave: str) -> str:
    """L'etichetta di menu che DICE il costo: "Dardo arcano — 3 mana", e in ricarica
    "Colpo pesante — ricarica (1)". Composizione di presentazione: vive nel port,
    non nel motore (che possiede i numeri, non le frasi)."""
    base = etichetta_mossa(chiave)
    residuo = cooldown_residuo(entita, chiave)
    if residuo > 0:
        return f"{base} — ricarica ({residuo})"
    costo = CATALOGO_MOSSE[chiave].costo_mana if chiave in CATALOGO_MOSSE else 0
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
        self._coppie = [(CombatResolved, self._su_resolved), (MortePersonaggio, self._su_morte)]
        for tipo, handler in self._coppie:
            bus.registra(tipo, handler)

    def _su_resolved(self, evento: CombatResolved) -> None:
        self._conclusa = True
        self._vittoria = bool(getattr(evento, "vittoria", False))
        self._fuga = bool(getattr(evento, "fuga", False))

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

    def agisci(self, indice: int) -> None:
        """Un comando del giocatore = il SUO turno + le risposte dei nemici, in un
        colpo solo (feel: il click non "esegue il turno del mob" in silenzio).
        L'ULTIMA voce (Fuggi) marca il turno come tentativo di disimpegno (FNC §4);
        le altre chiedono la mossa scelta: prova e risoluzione le tira il MOTORE
        dentro il suo sistema-turno."""
        mosse = self._mosse()
        if self._conclusa or not (0 <= indice <= len(mosse)):
            return
        if indice == len(mosse):
            richiedi_fuga()
        elif not richiedi_mossa(mosse[indice]):
            return  # scelta rifiutata dal motore: nessun turno speso
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
        self.uuid = ""
        self.etichetta = ""  # il nome del crawler: etichetta dello slot di save
        self.ultimo_messaggio: MessaggioGM | None = None
        # Callback (etichetta, frazione 0..1) per la barra di attesa dell'host: la
        # pipeline la chiama a ogni stadio; l'host la imposta, il motore non sa di UI.
        self.on_avanzamento = None
        self._chiusa = False  # run conclusa (esci/terminale): le porte si spengono
        self._invalidata: str | None = None  # run-World preso da un'altra sessione
        self._opzioni: tuple[OpzioneVista, ...] = ()
        self._scena: tuple[OpzioneScena, ...] = ()  # binding indice→azione di scena
        self._istanza: IstanzaCombattimento | None = None
        self._fatti_scontro: FattiScontro | None = None  # handoff scontro→GM
        self._nome_mob = ""

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
        sessione.guscio.nuova_partita(
            uuid=sessione.uuid, destrezza=10, hp=30, seed=seed,
            n_stanze=n_stanze, stagione=stagione,
        )
        _registra_sessione_attiva(sessione)  # il run-World è suo
        sessione.coda = sessione.guscio.coda
        # La pipeline GM: l'Archivio (firma→record) e la memoria di run FRESCHI.
        sessione.archivio = Archivio(master_seed=master_seed(), model_id=MODEL_ID_DEFAULT)
        sessione.memoria = MemoriaTurni()
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
            # Offline: il copione si deriva dalla stagione CONGELATA nel save
            # (design_piano_corrente; save legacy → Falsa Idra), mai dalla libreria.
            sessione.provider = _fake_da_piano(design_piano_corrente())
        sessione.uuid = uuid
        sessione.coda = sessione.guscio.coda
        sidecar = carica_archivio(directory, uuid)
        sessione.archivio = sidecar or Archivio(
            master_seed=master_seed(), model_id=MODEL_ID_DEFAULT
        )
        sessione.memoria = MemoriaTurni.ricostruisci(sessione.archivio)
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
        )
        if not esito.da_cache:  # un turno riletto non consuma i fatti: li narrerà il prossimo
            self._fatti_scontro = None
        self.ultimo_messaggio = esito.messaggio
        if esito.risultato is not None:
            self._nome_mob = esito.risultato.turno.entita.nome
        self._sincronizza_scena()
        return SnapshotVista(
            prosa=esito.messaggio.prosa,
            opzioni=self._opzioni,
            stato=self._descrittori(),
            fase="narrazione",
        )

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
        )
        if not esito.da_cache:
            self._fatti_scontro = None
        self.ultimo_messaggio = esito.messaggio
        self._sincronizza_scena()
        return SnapshotVista(
            prosa=esito.messaggio.prosa,
            opzioni=self._opzioni,
            stato=self._descrittori(),
            fase="narrazione",
        )

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
        self._sincronizza_scena()
        return self._snapshot_corrente()

    def salva(self) -> str:
        """Salvataggio a mano, in-run (H-6): il World sopravvive, scrittura prima di
        ogni teardown. La mappa viaggia nello slot `esplorazione`; l'Archivio (i turni
        GM congelati) viaggia nel sidecar — non viene più azzerato. Etichetta e
        timestamp alimentano l'indice dell'hub (H §5)."""
        self._guardia_aperta()
        self._guardia_fase_salvataggio()
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
        if azione.tipo is TipoAzione.MUOVI and azione.stanza is not None:
            self.coda.accoda(PlayerSiMuove(azione.stanza))  # la serve SistemaMovimento
            return
        if azione.tipo is TipoAzione.SCAPPA:
            # Disimpegno: prova su stat PRIMA di ingaggiare (FNC §5.3, tirata dal motore).
            # La destrezza passa dal fold (GR2-3), non da un campo della scheda.
            pent, _m, _scheda = protagonista()
            if tenta_disimpegno(stat_eff(pent, StatId.DESTREZZA), ClasseProva.BRONZO, self.rng):
                dissolvi_mob()  # fuga riuscita: l'incontro si dissolve, la scena si riapre
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
        ingaggia_combattimento(
            self.bus,
            nemici=None if mob is not None else [SpecNemico(destrezza=5, punti_vita=3)],
            arruolate=[mob] if mob is not None else None,
            seed=self.rng.randint(0, 10**9),
        )

    def _agisci_combattimento(self, indice: int) -> None:
        if self._istanza is not None:
            self._istanza.agisci(indice)  # l'istanza deterministica possiede lo scontro
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

    def _snapshot_corrente(self) -> SnapshotVista:
        return SnapshotVista(
            prosa="",  # la prosa di transizione arriva via eventi sul bus
            opzioni=self._opzioni,
            stato=self._descrittori(),
            fase="combattimento" if in_combattimento() else "narrazione",
        )

    def _descrittori(self) -> tuple[str, ...]:
        pent, _marker, scheda = protagonista()
        hp = f"HP {scheda.punti_vita}/{max_hp(pent)}"  # massimo DERIVATO (§5)
        extra: list[str] = []
        if in_combattimento():
            # Il giocatore VEDE chi affronta e quanto gli resta (feel G §5.6).
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
    hp = f"({getattr(e, 'hp_rimasti', 0)}/{getattr(e, 'hp_max', 0)})"
    pesante = " — COLPO PESANTE" if getattr(e, "mossa", "") == "attacco_pesante" else ""
    if attaccante == "":  # il protagonista colpisce
        return f"Colpisci {bersaglio or 'il nemico'}: {danno} danni {hp}{pesante}."
    return f"{attaccante} ti colpisce: {danno} danni {hp}{pesante}."


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
        vittima = "ti" if chi == "" else chi
        return f"{soggetto} {'morde' if nome_status == 'veleno' else 'mordono'} {vittima}: {delta} HP."
    chi_bene = "Recuperi" if chi == "" else f"{chi} rigenera"
    return f"{chi_bene} {delta} HP."


def _riga_turno_saltato(e: object) -> str:
    if getattr(e, "causa", "") == "fuga_fallita":
        return "Tenti la fuga: FALLITA. Il nemico ne approfitta."
    nome = getattr(e, "nome", "")
    return "Sei stordito: salti il turno!" if nome == "" else f"{nome} è stordito: salta il turno."


def _riga_risolto(e: object) -> str:
    if getattr(e, "fuga", False):
        return "Ti disimpegni: fuga riuscita, lo scontro si dissolve."
    if getattr(e, "vittoria", False):
        return "Hai vinto lo scontro."
    return "Lo scontro si chiude."


_MAPPA_EVENTI: tuple[tuple[type, Callable[[object], str]], ...] = (
    (EncounterStarted, lambda _e: "Lo scontro ha inizio."),
    (ColpoInferto, _riga_colpo),
    (StatusApplicato, _riga_status_applicato),
    (EffettoStatus, _riga_effetto_status),
    (TurnoSaltato, _riga_turno_saltato),
    (CombatResolved, _riga_risolto),
    (MortePersonaggio, lambda e: f"Sei morto: {getattr(e, 'causa', '')}."),
    (AnomalyTriggered, lambda _e: "Il dungeon ride: qualcosa è fuori scala…"),
    (DiscesaPiano, lambda e: f"Scendi: piano {getattr(e, 'piano', '?')}."),
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
                cast=[
                    MobAttivo(
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
                    for mob in piano.cast
                ],
                stanze=piano.stanze,
                tags=list(piano.tags),
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
    )


def turni_da_piano(piano) -> list[TurnoNarrazione]:
    """Il copione offline DERIVATO dal cast del piano (una stanza per voce, in
    ordine). Accetta sia il DTO `PianoRisolto` sia il dataclass `PianoAttivo`
    (stessi campi sul cast: duck-typed). Esauriti i turni, l'orchestrazione
    degrada al fallback deterministico: il gioco non si blocca mai."""
    combatti_o_scappa = [
        Opzione(tipo=TipoAzione.COMBATTI, etichetta="Combatti"),
        Opzione(tipo=TipoAzione.SCAPPA, etichetta="Scappi"),
    ]
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
            opzioni=combatti_o_scappa,
            durata=mob.durata,
        )
        for mob in piano.cast
    ]


def _turni_scriptati() -> list[TurnoNarrazione]:
    """RETRO-COMPAT: il copione della stagione di default (la Falsa Idra), oggi
    DERIVATO dalla libreria (`contenuti/`) — non più hardcoded."""
    return turni_da_piano(risolvi_stagione(STAGIONE_DEFAULT).piani[0])


def _fake_da_piano(piano) -> FakeProvider:
    """Il **FakeProvider scriptato** (offline): FIFO per chiamata — la pipeline GM
    fa (fino a) 4 chiamate per turno, quindi il copione scripta gli stadi in
    ordine: ideazione degradata (`None`), IL turno gating, limatura e
    distillazione degradate. `piano=None` (save legacy) → la Falsa Idra."""
    if piano is None:
        piano = risolvi_stagione(STAGIONE_DEFAULT).piani[0]
    risposte: list[object] = []
    for turno in turni_da_piano(piano):
        risposte += [None, turno.model_dump(), None, None]
    return FakeProvider(risposte)


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
    calibrazione (`MAPPA_STANZE`); il backend si INIETTA esplicitamente."""
    directory = directory or Path(tempfile.mkdtemp(prefix="dcc-"))
    if isinstance(stagione, StagioneRisolta):
        risolta = stagione
    else:
        risolta = risolvi_stagione(stagione if stagione is not None else STAGIONE_DEFAULT)
    piano1 = risolta.piani[0]
    if provider is None:
        n_stanze = piano1.n_stanze  # il copione copre tutte le stanze
        provider = _fake_da_piano(piano1)
    else:
        n_stanze = piano1.stanze  # scala autorata; None → MAPPA_STANZE
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


def _rendi(snapshot: SnapshotVista, stampa: Callable[[str], None]) -> None:
    """Rende uno snapshot come testo (sostituito in blocco, C-4)."""
    if snapshot.prosa:
        stampa(snapshot.prosa)
    stato = ", ".join(snapshot.stato) if snapshot.stato else "—"
    stampa(f"[{snapshot.fase}] {stato}")
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
