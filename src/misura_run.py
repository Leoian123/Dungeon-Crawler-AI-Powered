"""Misura della vincibilità (STATO.md §4.1): run automatiche via porte, offline, seeded.

È l'harness che rende RIPRODUCIBILE la domanda «il gioco è vincibile giocando?»:
politiche × seed → win-rate, profondità, scontri, drop. La misura storica (40 run,
zero vittorie, pre-loot) era irriproducibile perché questo file non esisteva.

Perimetro:
- **Guida via porte** (`SessioneGioco`): intenti `PlayerChoseOption`, `avanza`,
  `prossima_narrazione`, `equipaggia` — gli stessi passi di un host reale.
- **Sensori di laboratorio**: le soglie delle politiche leggono HP/zaino dal motore
  (`protagonista`, `fonti_zaino`) in SOLA lettura. È strumentazione, non un host:
  vive nel composition root come `banco_nemici.py`, sole stdlib.
- **Offline e seeded**: `provider=None` (copione, mai rete); ogni run è deterministica
  per (politica, seed) — due lanci identici producono lo stesso esito.
- **Raccolto generativo** (`--json-oggetti`): gli oggetti NATI in-run dalla filiera
  (fabbrica/pezzo unico/conio) escono come TEMPLATE completi — oggetto + provenienza
  + uso. Lo script non genera: fotografa. Con `--live` la run esercita la pipeline
  vera (GM, conio AI) e diventa l'e2e del gioco intero — dichiarando che il
  bit-per-bit non vale più.

Uso:
    PYTHONPATH="src;vendor" python -m misura_run --run 10 --seed-base 0
    PYTHONPATH="src;vendor" python -m misura_run --politiche combatti,fuga12 --json out.json
    PYTHONPATH="src;vendor" python -m misura_run --politiche fuga12 --live --json-oggetti raccolto.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from contracts import (
    CombatResolved,
    DiscesaPiano,
    MortePersonaggio,
    OggettoTrovato,
    PlayerChoseOption,
    Terminale,
    TipoAzione,
)

# Ordine di pregio delle categorie-armatura: lo stesso del corredo di riferimento.
_ORDINE_CATEGORIA = ("veste", "leggera", "media", "pesante")


# --- Politiche -------------------------------------------------------------------

@dataclass(frozen=True)
class Politica:
    """Una politica di gioco automatica: decide l'ingaggio, la fuga e il riposo.

    `ingaggia`: a scena con mob sceglie Combatti (True) o Scappi (False).
    `soglia_fuga`: in scontro, HP sotto questa soglia → Fuggi (None = mai).
    `riposa_sotto`: frazione di max HP sotto cui sceglie Riposa quando è di scena.
    `mossa_preferita`: in scontro sceglie QUESTA mossa quando è pagabile (prima
    del fallback «prima pagabile»): è la leva che fa esistere un build nello
    strumento — senza, l'attacco base (sempre primo e gratuito) monopolizza.
    """

    nome: str
    ingaggia: bool = True
    soglia_fuga: int | None = None
    riposa_sotto: float | None = 0.6
    mossa_preferita: str | None = None


# Le quattro politiche della misura storica (§4.1), col riposo che oggi esiste,
# più la politica MAGA (stili separati 2026-08-13): dardo arcano finché c'è mana
# — è l'unica strada da cui `acc_mag_eff` entra nella misura.
POLITICHE: dict[str, Politica] = {
    "combatti": Politica("combatti"),
    "fuga12": Politica("fuga12", soglia_fuga=12),
    "fuga20": Politica("fuga20", soglia_fuga=20),
    "scappa": Politica("scappa", ingaggia=False, soglia_fuga=10**9),
    "mago8": Politica("mago8", soglia_fuga=8, mossa_preferita="dardo_arcano"),
}


# --- Esito di una run ------------------------------------------------------------

@dataclass
class EsitoRun:
    """I fatti misurati di una run automatica (serializzabile: `asdict`)."""

    politica: str
    seed: int
    esito: str = "timeout"          # "vittoria" | "morte" | "timeout"
    causa_morte: str = ""
    profondita: int = 1
    turni: int = 0                  # interazioni dell'harness (passi via porte)
    narrazioni: int = 0             # turni GM richiesti
    scontri_vinti: int = 0
    scontri_fuggiti: int = 0
    scontri_persi: int = 0
    zone_attraversate: int = 0
    discese: int = 0
    drop_raccolti: int = 0
    equip_indossati: int = 0
    riposi: int = 0
    hp_finale: int = 0
    # I battiti di prosa fuori-banda effettivamente RESI (trailer, vestizione,
    # epitaffio). Offline restano 0 per contratto — il copione degrada gli stadi
    # non-gating: il valore è >0 solo con `--live`, dove certifica che la misura
    # ha esercitato anche la narrazione di scontro e non il solo scheletro.
    prose_fuori_banda: int = 0
    # Il RACCOLTO generativo: i template degli oggetti NATI in-run dalla
    # filiera (fabbrica/pezzo unico/conio libero), fotografati a fine run.
    oggetti_coniati: int = 0
    raccolto: list[dict] = field(default_factory=list)


class _Cronista:
    """Registra sul bus i fatti che diventano metriche; si sgancia a fine run."""

    def __init__(self, bus, esito: EsitoRun) -> None:
        self._bus = bus
        self._esito = esito
        self._coppie = [
            (CombatResolved, self._su_scontro),
            (MortePersonaggio, self._su_morte),
            (OggettoTrovato, self._su_drop),
            (DiscesaPiano, self._su_discesa),
        ]
        for tipo, handler in self._coppie:
            bus.registra(tipo, handler)

    def _su_scontro(self, ev) -> None:
        if ev.fuga:
            self._esito.scontri_fuggiti += 1
        elif ev.vittoria:
            self._esito.scontri_vinti += 1
        else:
            self._esito.scontri_persi += 1

    def _su_morte(self, ev) -> None:
        self._esito.causa_morte = ev.causa
        # Lo scontro FATALE non emette CombatResolved (G-11: il terminale è la
        # morte, non una "sconfitta di scontro") — quindi non entrava in NESSUN
        # contatore V/F/P e `scontri_persi` era strutturalmente 0: la metrica
        # mentiva per costruzione. La morte in combattimento È lo scontro perso.
        from motore import in_combattimento

        if in_combattimento():
            self._esito.scontri_persi += 1

    def _su_drop(self, _ev) -> None:
        self._esito.drop_raccolti += 1

    def _su_discesa(self, _ev) -> None:
        self._esito.discese += 1

    def chiudi(self) -> None:
        for tipo, handler in self._coppie:
            try:
                self._bus.deregistra(tipo, handler)
            except ValueError:
                pass
        self._coppie = []


# --- Il rubinetto generativo (sola lettura: fotografa, non genera) ----------------

def _raccolto_oggetti(esito: EsitoRun) -> list[dict]:
    """Gli oggetti NATI in-run diventano TEMPLATE completi (descrizione inclusa).

    Lo script non genera niente: la filiera esistente — fabbrica procedurale,
    pezzo unico, conio libero — converge già tutta in `OggettiConiati`, nella
    forma congelata `OggettoAttivo` (jsonable). Qui la si fotografa a run
    ancora montata, aggiungendo provenienza (chi giocava, com'è finita) ed
    esito d'uso (nello zaino? indossato?): un template che ha giocato — e con
    che risultato — vale più di dieci generati a freddo."""
    from dataclasses import asdict as _asdict

    import esper

    from motore import protagonista
    from motore.equip import equip_attivo, fonti_zaino
    from motore.oggetti import OggettiConiati

    pent, _marker, _scheda = protagonista()
    coniati = esper.try_component(pent, OggettiConiati)
    if coniati is None or not coniati.voci:
        return []
    zaino = set(fonti_zaino(pent))
    comp = equip_attivo(pent)
    indossate = set(comp.fonti()) if comp is not None else set()
    return [{
        "oggetto": _asdict(attivo),
        "provenienza": {
            "politica": esito.politica, "seed": esito.seed,
            "esito_run": esito.esito, "profondita": esito.profondita,
        },
        "uso": {
            "in_zaino": attivo.slug in zaino,
            "indossato": attivo.slug in indossate,
        },
    } for attivo in coniati.voci]


def oggetto_da_template(template: dict):
    """Template JSON → `OggettoAttivo`: il raccolto è una LIBRERIA pronta, non
    un log. json degrada le tuple a liste; qui si risale alla forma congelata
    esatta, quella che `oggetto_da_asset` traduce in oggetto vivo."""
    from motore import OggettoAttivo

    dati = dict(template["oggetto"])
    for campo in ("modificatori", "resistenze"):
        dati[campo] = tuple(tuple(coppia) for coppia in dati.get(campo) or ())
    dati["mosse"] = tuple(dati.get("mosse") or ())
    return OggettoAttivo(**dati)


# --- Sensori (sola lettura dal motore: strumentazione, non host) ------------------

def _hp_correnti() -> tuple[int, int]:
    """(HP correnti, HP massimi) del protagonista."""
    from motore import protagonista
    from motore.derivate import max_hp

    pent, _marker, scheda = protagonista()
    return scheda.punti_vita, max_hp(pent)


def _migliora_equip(sessione) -> tuple[int, object | None]:
    """Vestizione greedy dallo Zaino via la porta `equipaggia` (un pezzo per passo).

    Armatura: per slot vince la categoria più alta (l'ordine del corredo di
    riferimento). Arma: vince il `danno_base` più alto. Accessori: si indossa
    tutto (multiset aperto). Ritorna (n. pezzi indossati, ultimo snapshot o None).
    """
    from motore import protagonista
    from motore.equip import Accessorio, Arma, PezzoArmatura, equip_di, fonti_zaino
    from motore.oggetti import catalogo_oggetti_correnti

    from contracts import Grado
    from motore import grado_oggetto, rango_grado

    pent, _marker, _scheda = protagonista()
    comp = equip_di(pent)
    catalogo = catalogo_oggetti_correnti()
    indossati, snapshot = 0, None

    def _rango(categoria) -> int:
        try:
            return _ORDINE_CATEGORIA.index(categoria.value)
        except ValueError:
            return -1

    def _rango_fonte(fonte: str) -> int:
        try:
            return rango_grado(Grado(grado_oggetto(fonte)))
        except ValueError:
            return 0

    def _costituzione_di(pezzo) -> int:
        from contracts import StatId

        return sum(
            m.valore for m in getattr(pezzo, "modificatori", ())
            if m.stat is StatId.COSTITUZIONE
        )

    for fonte in fonti_zaino(pent):
        oggetto = catalogo.get(fonte)
        if oggetto is None or comp.pezzo_per_fonte(fonte) is not None:
            continue
        if isinstance(oggetto, PezzoArmatura):
            attuale = comp.armatura.get(oggetto.slot)
            if attuale is not None:
                # Prima la categoria (l'asse del corredo di riferimento), poi il
                # GRADO a parità: i modificatori scalano col grado, e senza il
                # tie-break una veste platino perderebbe per sempre contro la
                # prima veste bronzo indossata. Ultimo tie-break: la
                # COSTITUZIONE del pezzo — il giocatore vero, davanti a due
                # elmi uguali, tiene quello che porta HP (diagnosi 2026-08-13:
                # l'elmo del Becchino restava nello zaino).
                chiave_att = (_rango(attuale.categoria), _rango_fonte(attuale.fonte),
                              _costituzione_di(attuale))
                chiave_new = (_rango(oggetto.categoria), _rango_fonte(fonte),
                              _costituzione_di(oggetto))
                if chiave_att >= chiave_new:
                    continue
        elif isinstance(oggetto, Arma):
            if comp.arma is not None and (
                comp.arma.danno_base, _rango_fonte(comp.arma.fonte)
            ) >= (oggetto.danno_base, _rango_fonte(fonte)):
                continue
        elif not isinstance(oggetto, Accessorio):
            continue
        snapshot = sessione.equipaggia(fonte)
        comp = equip_di(pent)  # rileggi il manifest: la verità, non l'intento
        if comp.pezzo_per_fonte(fonte) is not None:
            indossati += 1  # contato SOLO se davvero indosso (l'intento può
            # restare in coda: phase-gate durante un'imboscata scattata qui)
        if snapshot.fase == "combattimento" or snapshot.run_conclusa:
            break  # lo scontro è partito a metà vestizione: si torna al loop
    return indossati, snapshot


# --- Scelte ----------------------------------------------------------------------

def _indice_mossa(chiave: str) -> int | None:
    """L'indice di menu di una mossa del protagonista. Il menu di scontro è
    «una voce per mossa del Repertorio, nello stesso ordine, + Fuggi ultima»
    (contratto dell'istanza combattimento): l'`OpzioneVista` non porta chiavi,
    quindi il laboratorio rilegge l'ordine dal motore. Sensore, sola lettura."""
    from motore import mosse_di, protagonista

    mosse = mosse_di(protagonista()[0])
    return mosse.index(chiave) if chiave in mosse else None


def _scelta_combattimento(politica: Politica, opzioni) -> int:
    """L'ultima voce è Fuggi (contratto del menu di scontro); le altre sono mosse."""
    ultima = len(opzioni) - 1
    hp, _massimo = _hp_correnti()
    if politica.soglia_fuga is not None and hp < politica.soglia_fuga:
        return ultima
    if politica.mossa_preferita is not None:
        indice = _indice_mossa(politica.mossa_preferita)
        if indice is not None and indice < ultima and opzioni[indice].abilitata:
            return indice  # il build gioca la SUA mossa finché è pagabile
    for opz in opzioni[:ultima]:
        if opz.abilitata:
            return opz.indice
    return 0  # nessuna mossa pagabile: l'attacco base è sempre la prima voce


def _stanze_da_evitare() -> set[int]:
    """Il NASCONDINO (la clausola della tana): il punto della run non è battere
    il celestiale, è raggiungere la scala EVITANDOLO — un cammino che scavalca
    la sua stanza esiste per lucchetto (BFS). Nella tana la stanza-boss va
    quindi esclusa dal movimento; nelle altre zone il custode è un gate da
    battere, mai da evitare. Sensore di laboratorio (tipo T1 = dato)."""
    from contracts import TierTerritorio
    from motore import mappa_corrente, stanza_boss_di, zona_corrente

    zona = zona_corrente()
    m = mappa_corrente()
    if zona is None or m is None or zona.tier is not TierTerritorio.PIANO:
        return set()
    return {stanza_boss_di(zona, m[1].piano)}


def _scelta_scena(
    politica: Politica, opzioni, viste: Counter, rng: random.Random
) -> tuple[int, str]:
    """Priorità: ingaggio (se c'è un mob la scena è solo Combatti/Scappi) →
    riposo sotto soglia → porta del boss (pieno prima, poi dentro) → Scendi →
    Attraversa → stanza meno vista. Ritorna (indice, etichetta-scelta) —
    l'etichetta alimenta il registro delle viste."""
    per_tipo: dict[TipoAzione, list] = {}
    for opz in opzioni:
        per_tipo.setdefault(opz.tipo, []).append(opz)

    if TipoAzione.COMBATTI in per_tipo:
        hp, _massimo = _hp_correnti()
        ferito = politica.soglia_fuga is not None and hp < politica.soglia_fuga
        # Il custode della TANA non si ingaggia MAI (qualunque politica): la
        # vittoria è la scala, non il celestiale — davanti a lui si arretra.
        from motore import mappa_corrente as _mc

        m = _mc()
        nella_tana_dal_lich = (
            m is not None and m[1].stanza_corrente in _stanze_da_evitare()
        )
        ingaggia = politica.ingaggia and not ferito and not nella_tana_dal_lich
        # Sotto soglia NON si re-ingaggia: ritirata e riposo, non il livelock.
        scelta = (per_tipo[TipoAzione.COMBATTI][0] if ingaggia
                  else per_tipo.get(TipoAzione.SCAPPA, per_tipo[TipoAzione.COMBATTI])[0])
        return scelta.indice, ""
    if politica.riposa_sotto is not None and TipoAzione.RIPOSA in per_tipo:
        hp, massimo = _hp_correnti()
        if massimo > 0 and hp < politica.riposa_sotto * massimo:
            return per_tipo[TipoAzione.RIPOSA][0].indice, "@riposa"
    # LA PORTA DEL BOSS (misura 2026-08-13): davanti alla stanza-boss NOTA un
    # giocatore fa il PIENO prima di aprire — la politica entrava «quando
    # capita», anche ferita, e il custode diventava una gara di logoramento
    # persa in partenza. A pieno si entra DI PROPOSITO (il boss è il gate del
    # varco, non una stanza qualunque); sotto il pieno si riposa se il riposo è
    # di scena (a risorse piene l'opzione non si compone più), altrimenti si
    # esplora come sempre.
    if TipoAzione.MUOVI in per_tipo:
        porta_boss = _porta_del_boss(per_tipo[TipoAzione.MUOVI])
        if porta_boss is not None:
            hp, massimo = _hp_correnti()
            if hp < massimo and TipoAzione.RIPOSA in per_tipo:
                return per_tipo[TipoAzione.RIPOSA][0].indice, "@riposa"
            if hp >= massimo:
                return porta_boss.indice, porta_boss.etichetta
    if TipoAzione.SCENDI in per_tipo:
        return per_tipo[TipoAzione.SCENDI][0].indice, ""
    if TipoAzione.ATTRAVERSA in per_tipo:
        # La politica gioca la SPINA e non imbocca mai i vicoli laterali: le
        # deviazioni sono anch'esse ATTRAVERSA e si distinguono solo per
        # etichetta ("Deviazione: …" / "Torna sulla via principale"). Il
        # rientro si prende (non si resta chiusi in un vicolo); la deviazione
        # si ignora: la misura di base è il percorso inteso, il loot laterale
        # è una politica a parte se servirà.
        avanti = [o for o in per_tipo[TipoAzione.ATTRAVERSA]
                  if not o.etichetta.startswith("Deviazione")]
        if avanti:
            return avanti[0].indice, "@attraversa"
    if TipoAzione.MUOVI in per_tipo:
        candidate = per_tipo[TipoAzione.MUOVI]
        evita = _stanze_da_evitare()
        if evita:
            # Nascondino: la stanza del Lich non si imbocca. Il cammino che la
            # scavalca esiste per lucchetto; se il menu offrisse SOLO lei si
            # ripiega (mai bloccarsi), ma non deve succedere per costruzione.
            sicure = [o for o in candidate if _stanza_di(o.etichetta) not in evita]
            candidate = sicure or candidate
        minimo = min(viste[o.etichetta] for o in candidate)
        meno_viste = [o for o in candidate if viste[o.etichetta] == minimo]
        scelta = rng.choice(meno_viste)
        return scelta.indice, scelta.etichetta
    return opzioni[0].indice, ""


def _stanza_di(etichetta: str) -> int | None:
    """L'id-stanza da un'etichetta di movimento («Vai: stanza N»): il DTO di
    membrana non porta l'id, il laboratorio lo rilegge dalle parole."""
    coda = etichetta.rsplit(" ", 1)[-1]
    return int(coda) if coda.isdigit() else None


def _porta_del_boss(candidate) -> object | None:
    """Il MUOVI che imbocca la stanza-boss NON battuta della zona corrente
    (tipo T1 = dato di mappa, stesso sensore del nascondino). `None` nella tana
    (lì vige il nascondino: il celestiale si evita, non si prepara), a custode
    battuto, o se nessuna candidata è la sua stanza."""
    from contracts import TierTerritorio
    from motore import (
        boss_sconfitto,
        mappa_corrente,
        stanza_boss_di,
        zona_corrente,
    )

    zona = zona_corrente()
    m = mappa_corrente()
    if zona is None or m is None or zona.tier is TierTerritorio.PIANO:
        return None
    if boss_sconfitto(zona):
        return None
    boss = stanza_boss_di(zona, m[1].piano)
    return next((o for o in candidate if _stanza_di(o.etichetta) == boss), None)


# --- Il loop di una run ----------------------------------------------------------

async def gioca_run(
    politica: Politica,
    seed: int,
    *,
    max_turni: int = 400,
    stagione: str | None = None,
    provider=None,
) -> EsitoRun:
    """Una run completa via porte: nuova partita → esplora/combatti/riposa/equipaggia
    → terminale (vittoria/morte) o timeout. Deterministica per (politica, seed)
    col default offline; `provider` iniettato (run generativa live) rinuncia al
    bit-per-bit ma esercita la pipeline vera (GM, conio) da capo a fondo."""
    from main import costruisci_sessione

    kwargs = {"stagione": stagione} if stagione is not None else {}
    sessione = costruisci_sessione(seed=seed, provider=provider, **kwargs)
    esito = EsitoRun(politica=politica.nome, seed=seed)
    cronista = _Cronista(sessione.bus, esito)
    rng = random.Random(f"misura:{politica.nome}:{seed}")
    viste: Counter = Counter()  # etichetta "Vai: stanza N" → visite (azzerato a ogni zona)
    snapshot = sessione.avanza()

    def _passo(indice: int):
        sessione.coda.accoda(PlayerChoseOption(indice))
        return sessione.avanza()

    async def _drena_prosa() -> None:
        """Consuma i battiti fuori-banda come farebbe un host vero.

        Senza questo, la misura girava su un gioco più povero di quello giocato:
        trailer d'apertura, vestizione del premio ed epitaffio non venivano mai
        chiesti, quindi `--live` non esercitava — né faceva pagare — tre delle
        rotte del Master-Engine. Offline degradano tutti a `None` (il copione non
        risponde agli stadi non-gating): il bit-per-bit della misura resta."""
        while (prosa := await sessione.prossima_prosa()) is not None:
            esito.prose_fuori_banda += 1

    try:
        while esito.turni < max_turni:
            if snapshot.run_conclusa:
                break
            esito.turni += 1
            esito.profondita = snapshot.profondita
            await _drena_prosa()
            if snapshot.fase == "combattimento":
                snapshot = _passo(_scelta_combattimento(politica, snapshot.opzioni))
                continue
            if not snapshot.opzioni:  # stanza mai narrata: serve un turno GM
                snapshot = await sessione.prossima_narrazione()
                esito.narrazioni += 1
                continue
            indossati, dopo_equip = _migliora_equip(sessione)
            esito.equip_indossati += indossati
            if dopo_equip is not None:
                snapshot = dopo_equip
                if snapshot.run_conclusa or snapshot.fase == "combattimento":
                    continue  # un'imboscata può scattare anche qui: si rientra dal loop
            indice, etichetta = _scelta_scena(politica, snapshot.opzioni, viste, rng)
            if etichetta == "@attraversa":
                esito.zone_attraversate += 1
                viste.clear()  # zona nuova: il registro delle stanze riparte
            elif etichetta == "@riposa":
                esito.riposi += 1
            elif etichetta:
                viste[etichetta] += 1
            snapshot = _passo(indice)

        # L'EPITAFFIO è dovuto a run chiusa: il ciclo esce prima di drenarlo.
        await _drena_prosa()
        esito.profondita = snapshot.profondita
        hp, _massimo = _hp_correnti() if snapshot.terminale is None else (0, 0)
        if snapshot.terminale is Terminale.PIANO_COMPLETATO:
            esito.esito = "vittoria"
        elif snapshot.terminale is Terminale.SCONFITTA:
            esito.esito = "morte"
        else:
            esito.esito = "timeout"
            esito.hp_finale = hp
        # Il raccolto si fotografa QUI: run ancora montata (il rubinetto legge il
        # World), esito già noto (entra nella provenienza). Mai far fallire la
        # misura per il raccolto: è un di più, non la misura.
        try:
            esito.raccolto = _raccolto_oggetti(esito)
            esito.oggetti_coniati = len(esito.raccolto)
        except Exception:
            pass
    finally:
        cronista.chiudi()
        if snapshot.terminale is not None:
            sessione.chiudi_terminale()
        else:
            try:
                sessione.esci()  # timeout fuori scontro: chiusura pulita
            except Exception:
                pass  # in scontro il save è vietato: la prossima run invalida il World
    return esito


# --- Aggregazione e report -------------------------------------------------------

@dataclass
class RigaRiassunto:
    """L'aggregato per politica del report finale."""

    politica: str
    run: int = 0
    vittorie: int = 0
    morti: int = 0
    timeout: int = 0
    profondita_max: int = 0
    turni_medi: float = 0.0
    scontri_vinti_medi: float = 0.0
    fughe_medie: float = 0.0
    drop_medi: float = 0.0
    equip_medi: float = 0.0
    cause_morte: dict[str, int] = field(default_factory=dict)

    @property
    def win_rate(self) -> float:
        return self.vittorie / self.run if self.run else 0.0


def riassumi(esiti: list[EsitoRun]) -> list[RigaRiassunto]:
    """Aggrega gli esiti per politica (funzione pura: testabile senza run)."""
    righe: dict[str, RigaRiassunto] = {}
    gruppi: dict[str, list[EsitoRun]] = {}
    for e in esiti:
        gruppi.setdefault(e.politica, []).append(e)
    for politica, gruppo in gruppi.items():
        riga = RigaRiassunto(politica=politica, run=len(gruppo))
        cause: Counter = Counter()
        for e in gruppo:
            if e.esito == "vittoria":
                riga.vittorie += 1
            elif e.esito == "morte":
                riga.morti += 1
                if e.causa_morte:
                    cause[e.causa_morte] += 1
            else:
                riga.timeout += 1
            riga.profondita_max = max(riga.profondita_max, e.profondita)
        n = len(gruppo)
        riga.turni_medi = sum(e.turni for e in gruppo) / n
        riga.scontri_vinti_medi = sum(e.scontri_vinti for e in gruppo) / n
        riga.fughe_medie = sum(e.scontri_fuggiti for e in gruppo) / n
        riga.drop_medi = sum(e.drop_raccolti for e in gruppo) / n
        riga.equip_medi = sum(e.equip_indossati for e in gruppo) / n
        riga.cause_morte = dict(cause.most_common(3))
        righe[politica] = riga
    return [righe[p] for p in sorted(righe)]


def stampa_riassunto(righe: list[RigaRiassunto], stampa=print) -> None:
    intestazione = (
        f"{'politica':<10} {'run':>4} {'vitt':>5} {'morti':>6} {'t.out':>6} "
        f"{'win%':>6} {'prof.max':>9} {'turni~':>7} {'scontri~':>9} {'drop~':>6} {'equip~':>7}"
    )
    stampa(intestazione)
    stampa("-" * len(intestazione))
    for r in righe:
        stampa(
            f"{r.politica:<10} {r.run:>4} {r.vittorie:>5} {r.morti:>6} {r.timeout:>6} "
            f"{r.win_rate * 100:>5.0f}% {r.profondita_max:>9} {r.turni_medi:>7.1f} "
            f"{r.scontri_vinti_medi:>9.1f} {r.drop_medi:>6.1f} {r.equip_medi:>7.1f}"
        )
    for r in righe:
        if r.cause_morte:
            cause = ", ".join(f"{c} ×{n}" for c, n in r.cause_morte.items())
            stampa(f"  {r.politica}: morti per {cause}")


# --- CLI -------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="misura_run",
        description="Run automatiche via porte (offline, seeded): win-rate per politica.",
    )
    parser.add_argument(
        "--politiche", default=",".join(POLITICHE),
        help=f"politiche da misurare, separate da virgola (default: tutte — {', '.join(POLITICHE)})",
    )
    parser.add_argument("--run", type=int, default=10, help="run per politica (default 10)")
    parser.add_argument("--seed-base", type=int, default=0, help="primo seed (default 0)")
    parser.add_argument("--max-turni", type=int, default=400,
                        help="tetto di interazioni per run (default 400)")
    parser.add_argument("--stagione", default=None,
                        help="slug della stagione (default: quella di costruisci_sessione)")
    parser.add_argument("--json", type=Path, default=None,
                        help="scrive gli esiti per-run (JSON) su questo percorso")
    parser.add_argument("--json-oggetti", type=Path, default=None,
                        help="scrive i TEMPLATE degli oggetti coniati in-run "
                             "(oggetto completo + provenienza + uso) su questo percorso")
    parser.add_argument("--live", action="store_true",
                        help="GM live dal composition root (chiave+SDK; senza, degrada "
                             "all'offline scriptato). La run diventa GENERATIVA/e2e: "
                             "esercita la pipeline vera ma perde il bit-per-bit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    nomi = [n.strip() for n in args.politiche.split(",") if n.strip()]
    ignote = [n for n in nomi if n not in POLITICHE]
    if ignote:
        print(f"politiche ignote: {', '.join(ignote)} (note: {', '.join(POLITICHE)})")
        return 2

    provider = None
    if args.live:
        from provider import scegli_provider

        # `["--live"]`: senza chiave o SDK si FALLISCE forte (SystemExit del
        # composition root), mai il degrado silenzioso all'offline — una
        # vendemmia scriptata che si crede live è il bug peggiore da diagnosticare.
        provider, etichetta = scegli_provider(["--live"])
        print(f"provider: {etichetta} — run generativa: la misura perde il bit-per-bit\n")

    esiti: list[EsitoRun] = []
    for nome in nomi:
        politica = POLITICHE[nome]
        for i in range(args.run):
            seed = args.seed_base + i
            esito = asyncio.run(gioca_run(
                politica, seed, max_turni=args.max_turni, stagione=args.stagione,
                provider=provider,
            ))
            esiti.append(esito)
            print(
                f"[{esito.politica}/seed {esito.seed}] {esito.esito} — "
                f"prof. {esito.profondita}, {esito.turni} turni, "
                f"{esito.scontri_vinti}V/{esito.scontri_fuggiti}F/{esito.scontri_persi}P, "
                f"{esito.zone_attraversate} zone, "
                f"{esito.drop_raccolti} drop, {esito.equip_indossati} equip, "
                f"{esito.riposi} riposi, {esito.oggetti_coniati} coniati"
                + (f" ({esito.causa_morte})" if esito.causa_morte else "")
            )

    print()
    stampa_riassunto(riassumi(esiti))
    if args.json is not None:
        args.json.write_text(
            json.dumps([asdict(e) for e in esiti], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nEsiti per-run scritti in {args.json}")
    if args.json_oggetti is not None:
        templates = [t for e in esiti for t in e.raccolto]
        args.json_oggetti.write_text(
            json.dumps({
                "generatore": "misura_run",
                "run": len(esiti),
                "oggetti": templates,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nRaccolti {len(templates)} template-oggetto in {args.json_oggetti}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
