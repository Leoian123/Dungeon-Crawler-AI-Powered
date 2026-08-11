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

Uso:
    PYTHONPATH="src;vendor" python -m misura_run --run 10 --seed-base 0
    PYTHONPATH="src;vendor" python -m misura_run --politiche combatti,fuga12 --json out.json
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
    """

    nome: str
    ingaggia: bool = True
    soglia_fuga: int | None = None
    riposa_sotto: float | None = 0.6


# Le quattro politiche della misura storica (§4.1), col riposo che oggi esiste.
POLITICHE: dict[str, Politica] = {
    "combatti": Politica("combatti"),
    "fuga12": Politica("fuga12", soglia_fuga=12),
    "fuga20": Politica("fuga20", soglia_fuga=20),
    "scappa": Politica("scappa", ingaggia=False, soglia_fuga=10**9),
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
    hp_finale: int = 0


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

    pent, _marker, _scheda = protagonista()
    comp = equip_di(pent)
    catalogo = catalogo_oggetti_correnti()
    indossati, snapshot = 0, None

    def _rango(categoria) -> int:
        try:
            return _ORDINE_CATEGORIA.index(categoria.value)
        except ValueError:
            return -1

    for fonte in fonti_zaino(pent):
        oggetto = catalogo.get(fonte)
        if oggetto is None or comp.pezzo_per_fonte(fonte) is not None:
            continue
        if isinstance(oggetto, PezzoArmatura):
            attuale = comp.armatura.get(oggetto.slot)
            if attuale is not None and _rango(attuale.categoria) >= _rango(oggetto.categoria):
                continue
        elif isinstance(oggetto, Arma):
            if comp.arma is not None and comp.arma.danno_base >= oggetto.danno_base:
                continue
        elif not isinstance(oggetto, Accessorio):
            continue
        snapshot = sessione.equipaggia(fonte)
        indossati += 1
        comp = equip_di(pent)  # il manifest è cambiato: rileggi prima del prossimo pezzo
    return indossati, snapshot


# --- Scelte ----------------------------------------------------------------------

def _scelta_combattimento(politica: Politica, opzioni) -> int:
    """L'ultima voce è Fuggi (contratto del menu di scontro); le altre sono mosse."""
    ultima = len(opzioni) - 1
    hp, _massimo = _hp_correnti()
    if politica.soglia_fuga is not None and hp < politica.soglia_fuga:
        return ultima
    for opz in opzioni[:ultima]:
        if opz.abilitata:
            return opz.indice
    return 0  # nessuna mossa pagabile: l'attacco base è sempre la prima voce


def _scelta_scena(
    politica: Politica, opzioni, viste: Counter, rng: random.Random
) -> tuple[int, str]:
    """Priorità: ingaggio (se c'è un mob la scena è solo Combatti/Scappi) →
    riposo sotto soglia → Scendi → Attraversa → stanza meno vista. Ritorna
    (indice, etichetta-scelta) — l'etichetta alimenta il registro delle viste."""
    per_tipo: dict[TipoAzione, list] = {}
    for opz in opzioni:
        per_tipo.setdefault(opz.tipo, []).append(opz)

    if TipoAzione.COMBATTI in per_tipo:
        scelta = (per_tipo[TipoAzione.COMBATTI][0] if politica.ingaggia
                  else per_tipo.get(TipoAzione.SCAPPA, per_tipo[TipoAzione.COMBATTI])[0])
        return scelta.indice, ""
    if politica.riposa_sotto is not None and TipoAzione.RIPOSA in per_tipo:
        hp, massimo = _hp_correnti()
        if massimo > 0 and hp < politica.riposa_sotto * massimo:
            return per_tipo[TipoAzione.RIPOSA][0].indice, ""
    if TipoAzione.SCENDI in per_tipo:
        return per_tipo[TipoAzione.SCENDI][0].indice, ""
    if TipoAzione.ATTRAVERSA in per_tipo:
        # La politica gioca la SPINA e non imbocca mai i vicoli laterali: le
        # deviazioni sono anch'esse ATTRAVERSA e si distinguono solo per
        # etichetta ("Deviazione: …" / "Torna sulla via principale"). Il
        # rientro si prende (non si resta chiusi in un vicolo); la deviazione
        # si ignora — anche perché il custode despawnato al cambio zona rende
        # oggi il rientro un vicolo cieco (bug B, riportato).
        avanti = [o for o in per_tipo[TipoAzione.ATTRAVERSA]
                  if not o.etichetta.startswith("Deviazione")]
        if avanti:
            return avanti[0].indice, "@attraversa"
    if TipoAzione.MUOVI in per_tipo:
        candidate = per_tipo[TipoAzione.MUOVI]
        minimo = min(viste[o.etichetta] for o in candidate)
        meno_viste = [o for o in candidate if viste[o.etichetta] == minimo]
        scelta = rng.choice(meno_viste)
        return scelta.indice, scelta.etichetta
    return opzioni[0].indice, ""


# --- Il loop di una run ----------------------------------------------------------

async def gioca_run(
    politica: Politica,
    seed: int,
    *,
    max_turni: int = 400,
    stagione: str | None = None,
) -> EsitoRun:
    """Una run completa via porte: nuova partita → esplora/combatti/riposa/equipaggia
    → terminale (vittoria/morte) o timeout. Deterministica per (politica, seed)."""
    from main import costruisci_sessione

    kwargs = {"stagione": stagione} if stagione is not None else {}
    sessione = costruisci_sessione(seed=seed, **kwargs)  # offline: mai rete
    esito = EsitoRun(politica=politica.nome, seed=seed)
    cronista = _Cronista(sessione.bus, esito)
    rng = random.Random(f"misura:{politica.nome}:{seed}")
    viste: Counter = Counter()  # etichetta "Vai: stanza N" → visite (azzerato a ogni zona)
    snapshot = sessione.avanza()

    def _passo(indice: int):
        sessione.coda.accoda(PlayerChoseOption(indice))
        return sessione.avanza()

    try:
        while esito.turni < max_turni:
            if snapshot.run_conclusa:
                break
            esito.turni += 1
            esito.profondita = snapshot.profondita
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
            elif etichetta:
                viste[etichetta] += 1
            snapshot = _passo(indice)

        esito.profondita = snapshot.profondita
        hp, _massimo = _hp_correnti() if snapshot.terminale is None else (0, 0)
        if snapshot.terminale is Terminale.PIANO_COMPLETATO:
            esito.esito = "vittoria"
        elif snapshot.terminale is Terminale.SCONFITTA:
            esito.esito = "morte"
        else:
            esito.esito = "timeout"
            esito.hp_finale = hp
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    nomi = [n.strip() for n in args.politiche.split(",") if n.strip()]
    ignote = [n for n in nomi if n not in POLITICHE]
    if ignote:
        print(f"politiche ignote: {', '.join(ignote)} (note: {', '.join(POLITICHE)})")
        return 2

    esiti: list[EsitoRun] = []
    for nome in nomi:
        politica = POLITICHE[nome]
        for i in range(args.run):
            seed = args.seed_base + i
            esito = asyncio.run(gioca_run(
                politica, seed, max_turni=args.max_turni, stagione=args.stagione,
            ))
            esiti.append(esito)
            print(
                f"[{esito.politica}/seed {esito.seed}] {esito.esito} — "
                f"prof. {esito.profondita}, {esito.turni} turni, "
                f"{esito.scontri_vinti}V/{esito.scontri_fuggiti}F/{esito.scontri_persi}P, "
                f"{esito.zone_attraversate} zone, "
                f"{esito.drop_raccolti} drop, {esito.equip_indossati} equip"
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
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
