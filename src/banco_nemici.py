"""Banco di prova: generazione nemici a confronto fra modelli LLM.

Dato un piccolo contesto (turno precedente, livello, seed), genera un nemico **completo** e
**confronta più modelli** sullo stesso input. Riusa il **vero motore headless** per la parte
*genuina* — gate (catalogo+budget), formula-madre delle stat, materializzazione nel World —
così le stat e lo storage non sono falsi positivi.

`drop` e `azioni` sono la **superficie sperimentale**, ancora *fuori* dal motore:
  - `drop`  = bottino possibile (lista di stringhe);
  - `azioni` = le **mosse di combattimento** che il nemico potrebbe usare (lista di stringhe).
    Sono la materia prima per progettare come mapparle un domani sul catalogo chiuso di
    `Effetto`/`Azione` (`motore/azione.py`) — il "lego" da sbloccare guardando i modelli. Per
    ora NON sono validate dal motore: l'output le marca esplicitamente come SPERIMENTALI.

Questo modulo è un **host/tool** (come `main.py`/`calibratore_web.py`): importa motore+contracts+
provider, vive a livello root, non importa una UI né `tests/`.

Uso:
  python -m banco_nemici --fake --livello 2 --seed 1            # offline, niente API
  python -m banco_nemici --livello 3 --seed 7 --contesto "…" \
                         --modelli claude-opus-4-8 <altro-id>   # live (ANTHROPIC_API_KEY)
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import esper

from contracts import (
    Blocco,
    Durata,
    EntitaGenerata,
    Grado,
    NemicoSperimentale,
    SchedaProiezione,
    TurnoNarrazione,
)
from motore import (
    MasterEngine,
    mosse_note,
    motivi_fuori_budget,
    Primarie,
    acc_fis_eff,
    acc_mag_eff,
    atk_eff,
    costruisci_prompt,
    def_eff,
    eva_eff,
    istanzia_entita,
    max_hp,
    prepara_contesto,
    stat_eff,
    valida_turno,
)
from provider import AnthropicBackend, FakeProvider, MODELLO_DEFAULT


# Lo schema sperimentale `NemicoSperimentale` vive in `contracts.schema` (come i
# fratelli di authoring) ed è registrato nella rotta `banco.nemico`: anche il
# banco passa dal Master-Engine — nessuna chiamata AI bypassa il canale unico.

# Contesto giocatore minimo per il prompt (come `main.py`): qui non serve un protagonista vivo.
_PROIEZIONE = SchedaProiezione(descrittori=("integro",))


def costruisci_prompt_nemico(budget, contesto: str) -> str:
    """Prompt = base reale del motore (`costruisci_prompt`, con budget/anomalia iniettati) +
    poche righe sperimentali per `drop` e `azioni` (mosse di combattimento), in stile DCC."""
    base = costruisci_prompt(budget, _PROIEZIONE, contesto)
    extra = [
        "",
        "[extra sperimentale] Oltre ai campi del catalogo, proponi anche:",
        "- drop: lista di bottini possibili che il nemico può lasciare (oggetti brevi, stile DCC).",
        "- azioni: lista delle MOSSE che il nemico può compiere in COMBATTIMENTO (stringhe brevi),",
        "  coerenti con archetipo/blocchi, in stile Dungeon Crawler Carl (ironico, dark-comico).",
        "Tieni archetipo/grado/blocchi DENTRO il budget indicato sopra.",
    ]
    return base + "\n" + "\n".join(extra)


# --- Gate reale + diagnosi del motivo (per il confronto fra modelli) -----------

def _diagnosi_gate(eg: EntitaGenerata, budget) -> str | None:
    """Il MOTIVO leggibile di un rifiuto, dalle stesse regole condivise dei gate
    (`motivi_fuori_budget` — niente mirror manuale che possa divergere). `None` =
    passerebbe. L'autorità resta `valida_turno`."""
    motivi = motivi_fuori_budget(
        eg.archetipo, eg.grado, eg.blocchi,
        archetipi_ammessi=budget.archetipi_ammessi,
        gradi_ammessi=budget.gradi_ammessi,
        blocchi_ammessi=budget.blocchi_ammessi,
    )
    return "; ".join(motivi) if motivi else None


def _stat_materializzando(eg: EntitaGenerata, livello: int) -> dict:
    """Materializza l'entità nel World corrente con la **vera** `istanzia_entita` (formula-madre
    + componenti), legge le stat **reali**, poi **rimuove l'entità** (non accumula, non usa
    `switch_world` — disciplina E-2: lo `switch_world` vive solo al confine guscio↔run)."""
    ent = istanzia_entita(eg, livello)
    try:
        primarie = esper.component_for_entity(ent, Primarie).valori
        return {
            "primarie": {s.value: stat_eff(ent, s) for s in primarie},  # valori EFFETTIVI
            "max_hp": max_hp(ent),
            "atk_eff": atk_eff(ent),
            "def_eff_centesimi": def_eff(ent),
            "eva_eff": round(eva_eff(ent), 4),
            "acc_fis_eff": round(acc_fis_eff(ent), 4),
            "acc_mag_eff": round(acc_mag_eff(ent), 4),
        }
    finally:
        esper.delete_entity(ent, immediate=True)  # ripulisci: la materializzazione non lascia residui


# --- Esito per modello --------------------------------------------------------

@dataclass
class Esito:
    modello: str
    trasporto_ok: bool                       # il provider ha prodotto un candidato conforme?
    candidato: NemicoSperimentale | None
    gate_ok: bool                            # il core passa il gate reale (catalogo+budget)?
    motivo_gate: str | None
    stat: dict | None                        # stat reali (solo se gate_ok)


def gate_e_stat(cand: NemicoSperimentale, budget, livello: int) -> tuple[bool, str | None, dict | None]:
    """Passa il **core** del candidato per il gate reale del motore; se passa, materializza e
    legge le stat reali. Ritorna (gate_ok, motivo, stat)."""
    eg = EntitaGenerata(
        archetipo=cand.archetipo, grado=cand.grado, blocchi=cand.blocchi,
        nome=cand.nome, descrizione=cand.descrizione,
    )
    turno = TurnoNarrazione(prosa="(banco di prova)", entita=eg, durata=Durata.TURNO)
    validato = valida_turno(turno, budget)        # autorità del gate (schema·catalogo·budget)
    motivo = _diagnosi_gate(eg, budget)
    if validato is None:
        return False, motivo or "rifiutato dal gate", None
    return True, None, _stat_materializzando(eg, livello)


async def confronta(engines: dict, prompt: str, budget, livello: int) -> list[Esito]:
    """Genera in **parallelo** su tutti i modelli (I/O di rete), poi gate+materializzazione
    **seriali** (esper è stato globale). Ogni modello è un `MasterEngine` sulla
    rotta `banco.nemico`: stesso canale (e stesso tally) del resto del progetto."""
    nomi = list(engines)
    candidati = await asyncio.gather(*(engines[n].genera("banco.nemico", prompt) for n in nomi))
    esiti: list[Esito] = []
    for nome, cand in zip(nomi, candidati):
        if cand is None:
            esiti.append(Esito(nome, False, None, False, "trasporto fallito (None)", None))
            continue
        gate_ok, motivo, stat = gate_e_stat(cand, budget, livello)
        esiti.append(Esito(nome, True, cand, gate_ok, motivo, stat))
    return esiti


# --- Stampa -------------------------------------------------------------------

def _riga(s: str, stampa) -> None:
    stampa(s)


def stampa_confronto(esiti: list[Esito], budget, livello: int, contesto: str, stampa=print) -> None:
    gradi = ", ".join(sorted(g.value for g in budget.gradi_ammessi))
    blocchi = ", ".join(sorted(b.value for b in budget.blocchi_ammessi))
    _riga(f"╔═ BANCO NEMICI · livello {livello} · budget gradi[{gradi}] blocchi[{blocchi}]"
          f"{' · ANOMALIA' if budget.anomala else ''}", stampa)
    _riga(f"║ contesto: {contesto!r}", stampa)
    _riga("╚" + "═" * 60, stampa)

    for e in esiti:
        _riga("", stampa)
        _riga(f"══ MODELLO: {e.modello} ", stampa)
        if not e.trasporto_ok:
            _riga(f"  trasporto: FALLITO — {e.motivo_gate}", stampa)
            continue
        c = e.candidato
        assert c is not None
        if e.gate_ok:
            _riga(f"  gate: ✓ PASSATO   nemico: «{c.nome}»  [{c.archetipo} / {c.grado.value}]", stampa)
        else:
            _riga(f"  gate: ✗ RIFIUTATO — {e.motivo_gate}   (proposto: «{c.nome}» "
                  f"[{c.archetipo} / {c.grado.value}])", stampa)
        _riga(f"  descrizione (DCC): {c.descrizione}", stampa)
        if e.gate_ok and e.stat:
            prim = "  ".join(f"{k}={v}" for k, v in e.stat["primarie"].items())
            _riga("  stat (VALIDATE dal motore):", stampa)
            _riga(f"    primarie: {prim}", stampa)
            _riga(f"    max_hp={e.stat['max_hp']}  atk_eff={e.stat['atk_eff']}  "
                  f"def_eff={e.stat['def_eff_centesimi']}cent  eva_eff={e.stat['eva_eff']}  "
                  f"acc_fis={e.stat['acc_fis_eff']}  acc_mag={e.stat['acc_mag_eff']}", stampa)
            _riga(f"    blocchi: {', '.join(b.value for b in c.blocchi) or '—'}", stampa)
        _riga("  [SPERIMENTALE — non ancora validato dal motore]", stampa)
        _riga(f"    drop:   {c.drop}", stampa)
        # Le `azioni` incrociano il catalogo mosse REALE (Fase 6): ✓ = eseguibile
        # oggi dal motore, ✗ = materia prima per nuove voci di catalogo.
        marcate = [f"{'✓' if a in mosse_note() else '✗'}{a}" for a in c.azioni]
        note = sum(1 for a in c.azioni if a in mosse_note())
        _riga(f"    azioni (vs catalogo mosse, {note}/{len(c.azioni)} note): {marcate}", stampa)

    # Riga-sommario per il colpo d'occhio del confronto.
    _riga("", stampa)
    _riga("── SOMMARIO ──────────────────────────────────────────────", stampa)
    _riga(f"  {'modello':<24} {'gate':<10} {'nome':<22} {'grado':<10} drop azioni", stampa)
    for e in esiti:
        if not e.trasporto_ok:
            _riga(f"  {e.modello:<24} {'—(None)':<10}", stampa)
            continue
        c = e.candidato
        esito = "PASS" if e.gate_ok else "REJECT"
        _riga(f"  {e.modello:<24} {esito:<10} {c.nome[:22]:<22} {c.grado.value:<10} "
              f"{len(c.drop):>4} {len(c.azioni):>6}", stampa)


# --- Fake offline -------------------------------------------------------------

def nemico_scriptato() -> NemicoSperimentale:
    """Nemico in-budget (BRONZO + VELENO) per il percorso `--fake` (e i test): la pipeline
    gira end-to-end senza rete."""
    return NemicoSperimentale(
        archetipo="slime", grado=Grado.BRONZO, blocchi=[Blocco.VELENO],
        nome="Slime Mangiascarti",
        descrizione="Verde, acido, vagamente offeso dalla tua presenza. Ha digerito un Rolex.",
        drop=["Melma tossica", "Rolex digerito (rotto)", "1 Credito di Sistema"],
        azioni=["Sputo acido", "Avvolgi e soffoca", "Si divide in due se ferito"],
    )


# --- CLI ----------------------------------------------------------------------

def _costruisci_engines(args) -> tuple[dict, dict]:
    """UN `MasterEngine` per modello (`avvolgi` è l'uso legittimo: il confronto È
    un modello su tutte le corsie). Ritorna `(engines, consumi)` — il consumo per
    modello si stampa a fine run (prima si perdeva)."""
    if args.fake:
        fake = FakeProvider([nemico_scriptato().model_dump()])
        return {"(fake)": MasterEngine.avvolgi(fake)}, {}
    modelli = args.modelli or [MODELLO_DEFAULT]
    engines, consumi = {}, {}
    for m in modelli:
        backend = AnthropicBackend(modello=m, max_tokens=args.max_tokens, timeout=args.timeout)
        engines[m] = MasterEngine.avvolgi(backend)
        consumi[m] = backend.consumo
    return engines, consumi


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

    p = argparse.ArgumentParser(prog="banco_nemici", description="Genera un nemico e confronta più modelli.")
    p.add_argument("--livello", type=int, default=1, help="profondità del piano (scala stat + budget)")
    p.add_argument("--seed", type=int, default=0, help="seed del tiro anomalia (riproducibilità)")
    p.add_argument("--contesto", default="Il dungeon osserva, in attesa.", help="il turno precedente")
    p.add_argument("--contesto-file", help="file con il contesto (alternativa a --contesto)")
    p.add_argument("--modelli", nargs="*", default=[], help="uno o più model id Anthropic da confrontare")
    p.add_argument("--fake", action="store_true", help="provider offline scriptato (niente API)")
    p.add_argument("--max-tokens", type=int, default=2048)
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args(argv)

    contesto = (
        Path(args.contesto_file).read_text(encoding="utf-8").strip()
        if args.contesto_file else args.contesto
    )
    budget = prepara_contesto(args.livello, random.Random(args.seed))
    prompt = costruisci_prompt_nemico(budget, contesto)
    engines, consumi = _costruisci_engines(args)

    esiti = asyncio.run(confronta(engines, prompt, budget, args.livello))
    stampa_confronto(esiti, budget, args.livello, contesto)
    for nome, consumo in consumi.items():
        print(f"[consumo] {nome}: {consumo.riassunto()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
