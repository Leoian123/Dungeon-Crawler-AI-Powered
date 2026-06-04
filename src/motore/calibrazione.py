"""Calibrazione del gioco — **tutti** i numeri §11 in un solo posto (guida §0), con un
**catalogo** auto-descrittivo e un **layer di override** editabile dalla console admin.

Tre cose vivono qui:
  1. **Il catalogo** (`CATALOGO`): per ogni placeholder, valore di default, **spiegazione**
     («cosa dovrebbe essere»), dominio/range suggerito, categoria, unità. È il contenuto che
     la console admin (`src/calibratore.py`) mostra e gestisce.
  2. **Gli override**: un file JSON *gitignored* (`calibrazione.overrides.json`, o il path in
     `DCC_CALIBRAZIONE_OVERRIDE`) caricato **all'import**. I valori editati valgono dal
     **prossimo avvio** del motore; il sorgente resta coi default (reversibile).
  3. **Le costanti/tabelle pubbliche** derivate dal catalogo+override, coi nomi di sempre — i
     consumatori (`from .calibrazione import S_CONTEST`) non cambiano, ma ora riflettono gli
     override.

Distinzione (guida §0): le tabelle che il cluster **dà** (`M_ARMATURA`, `M_TAGLIA`,
`COEFF_ACC`, `MIN_COLPO ≈ 1%`) sono cablate come default *dato*; il resto è placeholder
neutro coerente col vincolo accoppiato del check 1. La calibrazione vera è il property-test.

Dipendenze: stdlib + `contracts` (i vocabolari enum). La formula-madre importa `catalogo`
**localmente** (evita il ciclo `calibrazione ↔ catalogo`).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from contracts import Archetipo, ClasseProva, Durata, StatId


# --- Il catalogo: ogni placeholder con la sua spiegazione (cosa dovrebbe essere) -

@dataclass(frozen=True)
class Param:
    """Una voce del catalogo di calibrazione.

    `chiave` è l'identità stabile (anche per le foglie di tabella, in forma `TABELLA.sotto`);
    `default` il valore cablato; `spiegazione` *cosa* il numero dovrebbe essere e perché;
    `dominio` il range/forma suggerito; `categoria` raggruppa nella console; `tipo` guida
    l'editing (`int`/`float`/`scelta`); `scelte` popola le scelte se `tipo == "scelta"`."""

    chiave: str
    default: object
    spiegazione: str
    categoria: str
    dominio: str
    tipo: str = "float"
    unita: str = ""
    scelte: tuple[str, ...] = ()


# Categorie (ordine di presentazione nella console).
CAT_CHECK1 = "Check 1 — colpire (contest/banda/graze)"
CAT_CHECK2 = "Check 2 — danno/difesa & HP"
CAT_ACC = "Accuratezza — pesi Des↔Int"
CAT_ARMATURA = "Tabella m_armatura (mobilità per categoria)"
CAT_TAGLIA = "Tabella m_taglia (più piccolo = schivi più)"
CAT_ARMA = "Tabella coeff_acc (arma vs portatore)"
CAT_GEOM = "Geometria di default dell'MVP (seam gear)"
CAT_TIPI = "Layer tipi — cap resistenze/vulnerabilità"
CAT_CROLLO = "Escalation (crollo) — terminazione"
CAT_TURNO = "Turno / Action Point"
CAT_PROB = "Probabilità (anomalia, imboscata)"
CAT_TEMPO = "Tempo (durate, durata-blocco)"
CAT_PROVE = "Prove — soglie delle classi"
CAT_CARL = "Protagonista (Carl) — primarie base e HP"
CAT_ARCH = "Archetipi nemici — profili base"


_DEFS: tuple[Param, ...] = (
    # --- Check 1 ---
    Param("S_CONTEST", 2, "Nitidezza del contest acc^s/(acc^s+eva^s): un piccolo vantaggio di "
          "accuratezza pesa di più al crescere di s. s=1 morbido, s≥2 netto (favorevole su "
          "gradino-banda e raggiungibilità del dodge-build). Va tarato INSIEME a F (gradino = "
          "1/(F^s+1)) e alla scala di coeff_eva.", CAT_CHECK1, "intero ≥1; default ≥2", "int"),
    Param("MIN_COLPO", 0.01, "Floor/cap gemello del colpire (~1% = floor-hit/cap di Mordheim): "
          "garantisce P(qualche danno) ≥ MIN_COLPO e P(schivata piena) ≥ MIN_COLPO. Nessuna "
          "schivata al 100%, nessun whiff garantito.", CAT_CHECK1, "0 < x < 0.5; tipico ~0.01"),
    Param("F_AUTOHIT", 3, "Larghezza della banda del gate: si tira solo se eva ≥ acc/F; sotto è "
          "auto-hit deterministico. F grande → banda larga ma riapre il whiff 1% universale; "
          "piccolo → cliff netto. Accoppiato a s. Sweet-spot moderato.", CAT_CHECK1,
          ">1, moderato (~2–4)", "float"),
    Param("DELTA_BANDA", 0.20, "Ampiezza della banda di graze attorno a P. Piccolo → modello "
          "quasi binario; grande → molti glancing blow. I bordi sono clampati nei floor "
          "gemelli.", CAT_CHECK1, "0 – ~0.4"),
    Param("G_GRAZE", 0.5, "Frazione di danno del graze ('mezza schivata'). 0.5 straddle = media "
          "invariata, varianza giù (protegge il fragile per riduzione di spike); <0.5 = dial "
          "'salva-fragile' (abbassa anche la media).", CAT_CHECK1, "0 – 1; default 0.5"),
    # --- Check 2 / HP ---
    Param("HP_BASE", 0, "Termine costante della curva max_HP = HP_BASE + K_HP·Cost.", CAT_CHECK2,
          "intero ≥0", "int", "HP"),
    Param("K_HP", 1, "Pendenza HP per punto di Costituzione (curva HP; obiettivo TTK 3–6 round).",
          CAT_CHECK2, ">0", "float", "HP/Cost"),
    Param("MULT_MIN", 0.25, "Cap minimo del moltiplicatore di resistenza (>0: una resistenza non "
          "azzera mai del tutto il danno; il floor 1 fa comunque ≥1 sul colpo a segno).",
          CAT_TIPI, "0 < x ≤ 1"),
    Param("MULT_MAX", 3.0, "Cap massimo del moltiplicatore di vulnerabilità (quanto una "
          "vulnerabilità può amplificare il danno).", CAT_TIPI, "≥ 1"),
    # --- Accuratezza ---
    Param("W_FISICO", 0.8, "Peso di Destrezza nell'accuratezza di un attacco FISICO (l'altra "
          "quota va a Intelligenza). MAI 0/1: l'altra stat entra 'in minima parte'.", CAT_ACC,
          "0.5 – 1 (mai 1)"),
    Param("W_MAGIA", 0.2, "Peso di Destrezza in un attacco MAGICO (Intelligenza domina). MAI 0/1.",
          CAT_ACC, "0 – 0.5 (mai 0)"),
    # --- Crollo ---
    Param("R_SOGLIA_CROLLO", 20, "Turni-scontro oltre cui scatta l'escalation: dev'essere una "
          "rete di sicurezza che quasi mai scatta in uno scontro normale.", CAT_CROLLO,
          "intero >0, ampio", "int", "turni"),
    Param("CROLLO_INCREMENTO", 1, "Incremento del danno inevitabile a ogni turno oltre soglia "
          "(crescita lineare illimitata, aritmetica monotòna → fine in round limitati).",
          CAT_CROLLO, "intero ≥1", "int", "HP/turno"),
    # --- Turno / AP ---
    Param("AP_MAX_MVP", 1, "Action Point per turno nell'MVP (i talenti post-MVP alzano il max o "
          "danno azioni bonus). Il loop è scritto AP-driven fin da subito.", CAT_TURNO,
          "intero ≥1", "int", "AP"),
    Param("DANNO_BASE", 1, "Witness storico del floor positivo del danno (G-L1): ogni colpo a "
          "segno toglie ≥1 HP. Oggi il floor reale è nel check 2; conservato per quel contratto.",
          CAT_TURNO, "intero ≥1", "int", "HP"),
    # --- m_armatura ---
    Param("M_ARMATURA.veste", 0.10, "Mobilità della veste/nudo (massima): slot vuoto = veste.",
          CAT_ARMATURA, "0 – ~0.15"),
    Param("M_ARMATURA.leggera", 0.075, "Mobilità dell'armatura leggera.", CAT_ARMATURA, "0 – 0.10"),
    Param("M_ARMATURA.media", 0.05, "Mobilità dell'armatura media.", CAT_ARMATURA, "0 – 0.075"),
    Param("M_ARMATURA.pesante", 0.025, "Mobilità della piastra (minima: tanca, non schiva).",
          CAT_ARMATURA, "0 – 0.05"),
    # --- m_taglia ---
    Param("M_TAGLIA.colossale", 0.0, "Taglia colossale: non schiva mai.", CAT_TAGLIA, "0"),
    Param("M_TAGLIA.enorme", 0.01, "Taglia enorme.", CAT_TAGLIA, "0 – 0.05"),
    Param("M_TAGLIA.grossa", 0.05, "Taglia grossa.", CAT_TAGLIA, "0 – 0.10"),
    Param("M_TAGLIA.media", 0.10, "Taglia media (umano).", CAT_TAGLIA, "~0.10"),
    Param("M_TAGLIA.piccola", 0.50, "Taglia piccola: schiva molto.", CAT_TAGLIA, "0.2 – 0.7"),
    Param("M_TAGLIA.infima", 1.00, "Taglia infima (Donut): schivata massima.", CAT_TAGLIA, "~1.0"),
    # --- coeff_acc ---
    Param("COEFF_ACC.pari", 1.0, "Arma di taglia pari al portatore: accuratezza neutra.", CAT_ARMA,
          "~1.0"),
    Param("COEFF_ACC.piu_piccola", 1.5, "Arma più piccola: più maneggevole/precisa (NON più "
          "forte: alza il colpire, non il danno).", CAT_ARMA, ">1"),
    Param("COEFF_ACC.mismatch", 0.0001, "Arma troppo grande (≥+3 categorie, colossale in mano a "
          "un uomo): ingovernabile. NON è auto-miss (il floor MIN_COLPO regge).", CAT_ARMA,
          "→0 (>0)"),
    Param("COEFF_ACC.naturale", 1.3, "Armi naturali (pugni/calci/artigli): 'roba loro', istinto.",
          CAT_ARMA, ">1"),
    # --- Geometria default (scelte) ---
    Param("ARMATURA_DEFAULT", "veste", "Categoria d'armatura di default dell'MVP (entità nude). "
          "Seam gear: diventerà dato per-entità.", CAT_GEOM, "una chiave di m_armatura", "scelta",
          scelte=("veste", "leggera", "media", "pesante")),
    Param("TAGLIA_DEFAULT", "media", "Taglia di default dell'MVP.", CAT_GEOM,
          "una chiave di m_taglia", "scelta",
          scelte=("colossale", "enorme", "grossa", "media", "piccola", "infima")),
    Param("ARMA_DEFAULT", "naturale", "Arma di default dell'MVP (armi naturali).", CAT_GEOM,
          "una chiave di coeff_acc", "scelta",
          scelte=("pari", "piu_piccola", "mismatch", "naturale")),
    # --- Probabilità ---
    Param("PROB_ANOMALIA", 0.05, "Probabilità che il dungeon 'tiri fuori scala' (budget gonfiato "
          "dal motore, seeded). Bassa: 'l'ingiustizia assurda' è rara.", CAT_PROB, "0 – 1"),
    Param("PROB_IMBOSCATA", 0.3, "Probabilità del dado-evento d'imboscata per tick di scorrimento "
          "(fuori combattimento).", CAT_PROB, "0 – 1"),
    # --- Tempo ---
    Param("DURATA_BLOCCO_DEFAULT", 3, "Durata (cariche) di default di uno status-blocco "
          "materializzato.", CAT_TEMPO, "intero ≥1", "int", "tick"),
    Param("CARICO_TICK.turno", 1, "Tick di cadenza per Durata=TURNO (cadenza base = 1).",
          CAT_TEMPO, "intero ≥1 (= base)", "int", "tick"),
    Param("CARICO_TICK.un_attimo", 2, "Tick per Durata=UN_ATTIMO.", CAT_TEMPO, "intero, monotòno",
          "int", "tick"),
    Param("CARICO_TICK.un_pochino", 4, "Tick per Durata=UN_POCHINO.", CAT_TEMPO, "intero, monotòno",
          "int", "tick"),
    Param("CARICO_TICK.un_bel_po", 8, "Tick per Durata=UN_BEL_PO.", CAT_TEMPO, "intero, monotòno",
          "int", "tick"),
    # --- Prove ---
    Param("SOGLIA_PROVA.bronzo", 8, "Soglia (margine deterministico) della classe BRONZO: più "
          "alta = più difficile.", CAT_PROVE, "interi crescenti", "int"),
    Param("SOGLIA_PROVA.argento", 12, "Soglia della classe ARGENTO.", CAT_PROVE, "> bronzo", "int"),
    Param("SOGLIA_PROVA.oro", 16, "Soglia della classe ORO.", CAT_PROVE, "> argento", "int"),
    Param("SOGLIA_PROVA.celestiale", 22, "Soglia della classe CELESTIALE ('sedurre un dio').",
          CAT_PROVE, "> oro", "int"),
    # --- Carl ---
    Param("CARL.forza", 10, "Forza base di Carl (alimenta atk_eff/danno).", CAT_CARL, "intero ≥1",
          "int"),
    Param("CARL.destrezza", 10, "Destrezza base di Carl (sovrascritta alla creazione: iniziativa "
          "ed evasione).", CAT_CARL, "intero ≥1", "int"),
    Param("CARL.costituzione", 30, "Costituzione base di Carl (sovrascritta = HP iniziale; "
          "mitigazione muscolare).", CAT_CARL, "intero ≥1", "int"),
    Param("CARL.intelligenza", 10, "Intelligenza base di Carl (accuratezza magica).", CAT_CARL,
          "intero ≥1", "int"),
    Param("CARL.saggezza", 8, "Saggezza base di Carl (valore-nascosto, solo-privilegiati).",
          CAT_CARL, "intero ≥1", "int"),
    Param("CARL.fortuna", 5, "Fortuna base di Carl (esistenza-negata, usata nei tiri).", CAT_CARL,
          "intero ≥1", "int"),
    Param("HP_DEFAULT", 30, "HP iniziale del protagonista (= Costituzione iniziale → nasce "
          "'integro').", CAT_CARL, "intero ≥1", "int", "HP"),
    # --- Archetipi nemici ---
    Param("ARCH.slime.destrezza_base", 3, "Destrezza base dello Slime.", CAT_ARCH, "intero ≥1",
          "int"),
    Param("ARCH.slime.pv_base", 6, "PV base dello Slime (→ Costituzione).", CAT_ARCH, "intero ≥1",
          "int"),
    Param("ARCH.slime.danno_base", 1, "Danno base dello Slime (→ Forza).", CAT_ARCH, "intero ≥1",
          "int"),
    Param("ARCH.scheletro.destrezza_base", 5, "Destrezza base dello Scheletro.", CAT_ARCH,
          "intero ≥1", "int"),
    Param("ARCH.scheletro.pv_base", 8, "PV base dello Scheletro.", CAT_ARCH, "intero ≥1", "int"),
    Param("ARCH.scheletro.danno_base", 2, "Danno base dello Scheletro.", CAT_ARCH, "intero ≥1",
          "int"),
    Param("ARCH.goblin.destrezza_base", 7, "Destrezza base del Goblin (agile).", CAT_ARCH,
          "intero ≥1", "int"),
    Param("ARCH.goblin.pv_base", 5, "PV base del Goblin (fragile).", CAT_ARCH, "intero ≥1", "int"),
    Param("ARCH.goblin.danno_base", 2, "Danno base del Goblin.", CAT_ARCH, "intero ≥1", "int"),
)

CATALOGO: dict[str, Param] = {p.chiave: p for p in _DEFS}


# --- Layer di override: file JSON gitignored, caricato all'import -------------

PERCORSO_OVERRIDE: Path = Path(
    os.environ.get("DCC_CALIBRAZIONE_OVERRIDE", str(Path(__file__).with_name("calibrazione.overrides.json")))
)


def _carica_override() -> dict[str, object]:
    """Legge il file di override (se esiste). Tollerante: file assente/illeggibile → vuoto."""
    try:
        dati = json.loads(PERCORSO_OVERRIDE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {}
    return {k: v for k, v in dati.items() if k in CATALOGO}  # ignora chiavi sconosciute


_OVERRIDE: dict[str, object] = _carica_override()


def _coerce(param: Param, valore: object) -> object:
    """Riporta `valore` al tipo del param e lo **valida**: int→int, scelta→una delle
    `scelte` ammesse, altrimenti float. Solleva `ValueError` su input non valido."""
    if param.tipo == "int":
        return int(valore)
    if param.tipo == "scelta":
        s = str(valore)
        if param.scelte and s not in param.scelte:
            raise ValueError(f"'{s}' non in {param.scelte}")
        return s
    return float(valore)


def valore(chiave: str) -> object:
    """Valore effettivo: override se presente, altrimenti default (col tipo giusto)."""
    param = CATALOGO[chiave]
    grezzo = _OVERRIDE.get(chiave, param.default)
    return _coerce(param, grezzo)


# --- API per la console admin -------------------------------------------------

def elenco() -> tuple[Param, ...]:
    """Il catalogo, nell'ordine di dichiarazione (per la console)."""
    return _DEFS


def categorie() -> tuple[str, ...]:
    """Le categorie, nell'ordine di prima apparizione."""
    viste: list[str] = []
    for p in _DEFS:
        if p.categoria not in viste:
            viste.append(p.categoria)
    return tuple(viste)


def override_correnti() -> dict[str, object]:
    """Copia degli override attualmente in memoria (chiave → valore)."""
    return dict(_OVERRIDE)


def imposta(chiave: str, grezzo: object) -> object:
    """Imposta un override in memoria (validato e coerced). Ritorna il valore applicato.
    Non scrive su disco: chiamare `salva_override` per persistere."""
    if chiave not in CATALOGO:
        raise KeyError(chiave)
    val = _coerce(CATALOGO[chiave], grezzo)
    _OVERRIDE[chiave] = val
    return val


def azzera(chiave: str) -> None:
    """Rimuove l'override di `chiave` (torna al default)."""
    _OVERRIDE.pop(chiave, None)


def salva_override(percorso: Path | None = None) -> Path:
    """Persiste gli override su disco (solo le chiavi che divergono dal default)."""
    p = percorso or PERCORSO_OVERRIDE
    da_salvare = {k: v for k, v in _OVERRIDE.items() if v != CATALOGO[k].default}
    p.write_text(json.dumps(da_salvare, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


# --- Costanti pubbliche: derivate dal catalogo+override (nomi di sempre) -------
# I consumatori importano questi; ora riflettono gli override caricati all'import.

S_CONTEST = valore("S_CONTEST")
MIN_COLPO = valore("MIN_COLPO")
F_AUTOHIT = valore("F_AUTOHIT")
DELTA_BANDA = valore("DELTA_BANDA")
G_GRAZE = valore("G_GRAZE")

HP_BASE = valore("HP_BASE")
K_HP = valore("K_HP")
MULT_MIN = valore("MULT_MIN")
MULT_MAX = valore("MULT_MAX")

W_FISICO = valore("W_FISICO")
W_MAGIA = valore("W_MAGIA")

R_SOGLIA_CROLLO = valore("R_SOGLIA_CROLLO")
CROLLO_INCREMENTO = valore("CROLLO_INCREMENTO")

AP_MAX_MVP = valore("AP_MAX_MVP")
DANNO_BASE = valore("DANNO_BASE")

PROB_ANOMALIA = valore("PROB_ANOMALIA")
PROB_IMBOSCATA = valore("PROB_IMBOSCATA")
DURATA_BLOCCO_DEFAULT = valore("DURATA_BLOCCO_DEFAULT")
HP_DEFAULT = valore("HP_DEFAULT")

M_ARMATURA: dict[str, float] = {
    "veste": valore("M_ARMATURA.veste"), "leggera": valore("M_ARMATURA.leggera"),
    "media": valore("M_ARMATURA.media"), "pesante": valore("M_ARMATURA.pesante"),
}
M_TAGLIA: dict[str, float] = {
    "colossale": valore("M_TAGLIA.colossale"), "enorme": valore("M_TAGLIA.enorme"),
    "grossa": valore("M_TAGLIA.grossa"), "media": valore("M_TAGLIA.media"),
    "piccola": valore("M_TAGLIA.piccola"), "infima": valore("M_TAGLIA.infima"),
}
COEFF_ACC: dict[str, float] = {
    "pari": valore("COEFF_ACC.pari"), "piu_piccola": valore("COEFF_ACC.piu_piccola"),
    "mismatch": valore("COEFF_ACC.mismatch"), "naturale": valore("COEFF_ACC.naturale"),
}

ARMATURA_DEFAULT = valore("ARMATURA_DEFAULT")
TAGLIA_DEFAULT = valore("TAGLIA_DEFAULT")
ARMA_DEFAULT = valore("ARMA_DEFAULT")

# Tabelle migrate da `catalogo.py` (ora derivate dal catalogo+override).
SOGLIE_PROVA: dict[ClasseProva, int] = {
    ClasseProva.BRONZO: valore("SOGLIA_PROVA.bronzo"),
    ClasseProva.ARGENTO: valore("SOGLIA_PROVA.argento"),
    ClasseProva.ORO: valore("SOGLIA_PROVA.oro"),
    ClasseProva.CELESTIALE: valore("SOGLIA_PROVA.celestiale"),
}
CARICO_TICK: dict[Durata, int] = {
    Durata.TURNO: valore("CARICO_TICK.turno"),
    Durata.UN_ATTIMO: valore("CARICO_TICK.un_attimo"),
    Durata.UN_POCHINO: valore("CARICO_TICK.un_pochino"),
    Durata.UN_BEL_PO: valore("CARICO_TICK.un_bel_po"),
}
PRIMARIE_BASE_CARL: dict[StatId, int] = {
    StatId.FORZA: valore("CARL.forza"), StatId.DESTREZZA: valore("CARL.destrezza"),
    StatId.COSTITUZIONE: valore("CARL.costituzione"), StatId.INTELLIGENZA: valore("CARL.intelligenza"),
    StatId.SAGGEZZA: valore("CARL.saggezza"), StatId.FORTUNA: valore("CARL.fortuna"),
}


# --- Profilo-archetipo + registry (migrati da catalogo): binding F-6 + base §11 -

@dataclass(frozen=True)
class ProfiloArchetipo:
    """Profilo-base di un archetipo (valori §11 dal catalogo). La formula-madre lo scala."""

    destrezza_base: int
    pv_base: int
    danno_base: int


def _profilo(nome: str) -> ProfiloArchetipo:
    return ProfiloArchetipo(
        destrezza_base=valore(f"ARCH.{nome}.destrezza_base"),
        pv_base=valore(f"ARCH.{nome}.pv_base"),
        danno_base=valore(f"ARCH.{nome}.danno_base"),
    )


# `Archetipo → profilo`. Binding F-6 (ogni archetipo ha una voce) + base della formula-madre.
REGISTRY_ARCHETIPI: dict[Archetipo, ProfiloArchetipo] = {
    Archetipo.SLIME: _profilo("slime"),
    Archetipo.SCHELETRO: _profilo("scheletro"),
    Archetipo.GOBLIN: _profilo("goblin"),
}


# --- Formula-madre: (archetipo, grado, livello) → primarie ---------------------

def primarie_da_archetipo(archetipo: Archetipo, grado, livello: int) -> dict[StatId, int]:
    """Formula-madre delle `Primarie` di un'entità generata (SEGNAPOSTO §11).

    Profilo-base (da `REGISTRY_ARCHETIPI`) → vettore `Primarie`, scalato da grado e profondità.
    Mappa: `FORZA←danno_base`, `DESTREZZA←destrezza_base`, `COSTITUZIONE←pv_base`,
    `INTELLIGENZA←proxy`. Deriva, non legge dall'AI."""
    from .catalogo import rango_grado  # import locale: evita il ciclo calibrazione↔catalogo

    profilo = REGISTRY_ARCHETIPI[archetipo]
    rango = rango_grado(grado)
    fattore = rango * max(1, livello)
    return {
        StatId.FORZA: profilo.danno_base * fattore,
        StatId.DESTREZZA: profilo.destrezza_base + rango,
        StatId.COSTITUZIONE: profilo.pv_base * fattore,
        StatId.INTELLIGENZA: max(1, profilo.destrezza_base // 2),  # [§11] proxy
    }


def primarie_da_scalari(*, destrezza: int, punti_vita: int) -> dict[StatId, int]:
    """Fallback dello spawn quando il nemico è specificato per **scalari** (non archetipo).

    FORZA e INTELLIGENZA non hanno uno scalare nello spec → proxy legati alla destrezza."""
    return {
        StatId.FORZA: destrezza,
        StatId.DESTREZZA: destrezza,
        StatId.COSTITUZIONE: punti_vita,
        StatId.INTELLIGENZA: max(1, destrezza // 2),
    }
