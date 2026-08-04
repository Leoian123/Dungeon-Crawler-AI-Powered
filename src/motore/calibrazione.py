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

from contracts import Blocco, ClasseProva, Durata, StatId, TipoAzione, TipoDanno


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
CAT_STATUS = "Status — durate delle afflizioni"
CAT_PROVE = "Prove — soglie delle classi"
CAT_CARL = "Protagonista (Carl) — primarie base e HP"
CAT_MAPPA = "Mappa / esplorazione"
CAT_ARCH_SLIME = "Nemico — Slime"
CAT_ARCH_SCHELETRO = "Nemico — Scheletro"
CAT_ARCH_GOBLIN = "Nemico — Goblin"


# Scelte condivise (categorie di gear), riusate dai Param "scelta" globali e per-archetipo.
_SCELTE_ARMATURA = ("veste", "leggera", "media", "pesante")
_SCELTE_TAGLIA = ("colossale", "enorme", "grossa", "media", "piccola", "infima")
_SCELTE_ARMA = ("pari", "piu_piccola", "mismatch", "naturale")

# Profilo-default per archetipo (§11). `intelligenza_base` di default = ex-proxy
# `destrezza_base // 2` → il comportamento odierno resta invariato finché non si edita.
_ARCH_PROFILI_DEFAULT: tuple[tuple[str, str, str, dict[str, object]], ...] = (
    # `pv_base` TARATI sul TTK 3–6 round dell'analisi §5.4 (prima 6/8/5: col
    # `atk_eff=10` del protagonista ogni mob bronzo moriva in un colpo).
    ("slime", "lo Slime", CAT_ARCH_SLIME, dict(
        destrezza_base=3, pv_base=15, danno_base=1, intelligenza_base=1, difesa_base=0,
        saggezza_base=1, fortuna_base=1, armatura="veste", taglia="media", arma="naturale",
        res_mischia=0.0, res_fuoco=0.0, res_veleno=0.0)),
    ("scheletro", "lo Scheletro", CAT_ARCH_SCHELETRO, dict(
        destrezza_base=5, pv_base=18, danno_base=2, intelligenza_base=2, difesa_base=0,
        saggezza_base=1, fortuna_base=1, armatura="veste", taglia="media", arma="naturale",
        res_mischia=0.0, res_fuoco=0.0, res_veleno=0.0)),
    ("goblin", "il Goblin", CAT_ARCH_GOBLIN, dict(
        destrezza_base=7, pv_base=12, danno_base=2, intelligenza_base=3, difesa_base=0,
        saggezza_base=1, fortuna_base=1, armatura="veste", taglia="media", arma="naturale",
        res_mischia=0.0, res_fuoco=0.0, res_veleno=0.0)),
)


def _archetipi_defs() -> tuple[Param, ...]:
    """Genera le foglie di catalogo per ogni archetipo: stat base + geometria + resistenze
    (13 per archetipo). La `spiegazione` di ogni foglia è il testo d'impatto che console/UI
    mostrano — così *tutta* la parte numerica di un'entità è dato editabile, non codice."""
    out: list[Param] = []
    for nome, disp, cat, d in _ARCH_PROFILI_DEFAULT:
        out += [
            Param(f"ARCH.{nome}.destrezza_base", d["destrezza_base"],
                  f"Destrezza base di {disp}: iniziativa ed evasione (nel vettore: +rango per grado).",
                  cat, "intero ≥1", "int"),
            Param(f"ARCH.{nome}.pv_base", d["pv_base"],
                  f"PV base di {disp} (→ Costituzione, scala con grado·livello).", cat, "intero ≥1", "int"),
            Param(f"ARCH.{nome}.danno_base", d["danno_base"],
                  f"Danno base di {disp} (→ Forza, scala con grado·livello).", cat, "intero ≥1", "int"),
            Param(f"ARCH.{nome}.intelligenza_base", d["intelligenza_base"],
                  f"Intelligenza base di {disp}: accuratezza magica (nel vettore: +rango). "
                  "Prima era un proxy della Destrezza.", cat, "intero ≥1", "int"),
            Param(f"ARCH.{nome}.difesa_base", d["difesa_base"],
                  f"Difesa base di {disp} in centesimi: mitigazione piatta d'armatura (0 = nudo). "
                  "Flat, non scala col grado.", cat, "intero ≥0", "int", "centesimi"),
            Param(f"ARCH.{nome}.saggezza_base", d["saggezza_base"],
                  f"Saggezza base di {disp}: stat nascosta (nel vettore: +rango).", cat, "intero ≥1", "int"),
            Param(f"ARCH.{nome}.fortuna_base", d["fortuna_base"],
                  f"Fortuna base di {disp}: usata nei tiri (nel vettore: +rango).", cat, "intero ≥1", "int"),
            Param(f"ARCH.{nome}.armatura", d["armatura"],
                  f"Categoria d'armatura di {disp}: la mobilità che diventa evasione "
                  "(veste = massima, pesante = minima).", cat, "una chiave di m_armatura",
                  "scelta", scelte=_SCELTE_ARMATURA),
            Param(f"ARCH.{nome}.taglia", d["taglia"],
                  f"Taglia di {disp}: più piccola = schiva di più (fattore m_taglia).",
                  cat, "una chiave di m_taglia", "scelta", scelte=_SCELTE_TAGLIA),
            Param(f"ARCH.{nome}.arma", d["arma"],
                  f"Arma di {disp}: coeff. di accuratezza (arma vs portatore). Precisa ≠ forte: "
                  "muove il colpire, non il danno.", cat, "una chiave di coeff_acc",
                  "scelta", scelte=_SCELTE_ARMA),
            Param(f"ARCH.{nome}.res.mischia", d["res_mischia"],
                  f"Resistenza/vulnerabilità di {disp} al danno da MISCHIA, in punti % "
                  "(valore <0 resiste, >0 vulnerabile, 0 neutro).", cat,
                  "punti %; <0 resiste, >0 vulnerabile"),
            Param(f"ARCH.{nome}.res.fuoco", d["res_fuoco"],
                  f"Resistenza/vulnerabilità di {disp} al danno da FUOCO, in punti % "
                  "(valore <0 resiste, >0 vulnerabile, 0 neutro).", cat,
                  "punti %; <0 resiste, >0 vulnerabile"),
            Param(f"ARCH.{nome}.res.veleno", d["res_veleno"],
                  f"Resistenza/vulnerabilità di {disp} al danno da VELENO, in punti % "
                  "(valore <0 resiste, >0 vulnerabile, 0 neutro).", cat,
                  "punti %; <0 resiste, >0 vulnerabile"),
        ]
    return tuple(out)


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
    Param("MOLT_ATTACCO_PESANTE", 1.5, "Moltiplicatore di danno della mossa 'attacco_pesante' "
          "dei nemici (scelta seeded del motore): entra nel check 2 dentro l'unico round.",
          CAT_TURNO, "1 – 3"),
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
    Param("ARMATURA_DEFAULT", "veste", "Categoria d'armatura di default (entità senza slot gear: "
          "protagonista, nemici-da-scalari). Le entità generate portano il proprio `Corredo`.",
          CAT_GEOM, "una chiave di m_armatura", "scelta", scelte=_SCELTE_ARMATURA),
    Param("TAGLIA_DEFAULT", "media", "Taglia di default (entità senza slot gear).", CAT_GEOM,
          "una chiave di m_taglia", "scelta", scelte=_SCELTE_TAGLIA),
    Param("ARMA_DEFAULT", "naturale", "Arma di default (entità senza slot gear).", CAT_GEOM,
          "una chiave di coeff_acc", "scelta", scelte=_SCELTE_ARMA),
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
    # --- Tempo diegetico (pipeline GM): forbici ed etichette per Durata ---
    Param("FORBICE.turno", "pochi istanti", "Forbice testuale mostrata al giocatore per "
          "Durata=TURNO (finestra di conferma: 'ti prenderà…').", CAT_TEMPO, "testo breve", "testo"),
    Param("FORBICE.un_attimo", "qualche minuto", "Forbice testuale per UN_ATTIMO.", CAT_TEMPO,
          "testo breve", "testo"),
    Param("FORBICE.un_pochino", "20–30 minuti", "Forbice testuale per UN_POCHINO.", CAT_TEMPO,
          "testo breve", "testo"),
    Param("FORBICE.un_bel_po", "circa un'ora", "Forbice testuale per UN_BEL_PO.", CAT_TEMPO,
          "testo breve", "testo"),
    Param("ETICHETTA_TEMPO.turno", "un turno", "Etichetta diegetica di TURNO (prompt/messaggio "
          "GM: i secondi sono finzione, i tick sono gioco — J §3).", CAT_TEMPO, "testo breve", "testo"),
    Param("ETICHETTA_TEMPO.un_attimo", "un attimo", "Etichetta diegetica di UN_ATTIMO.", CAT_TEMPO,
          "testo breve", "testo"),
    Param("ETICHETTA_TEMPO.un_pochino", "un pochino", "Etichetta diegetica di UN_POCHINO.", CAT_TEMPO,
          "testo breve", "testo"),
    Param("ETICHETTA_TEMPO.un_bel_po", "un bel po'", "Etichetta diegetica di UN_BEL_PO.", CAT_TEMPO,
          "testo breve", "testo"),
    Param("DURATA_AZIONE.combatti", "turno", "Durata di default dell'azione COMBATTI (stima "
          "nella finestra di conferma).", CAT_TEMPO, "una Durata", "scelta",
          scelte=("turno", "un_attimo", "un_pochino", "un_bel_po")),
    Param("DURATA_AZIONE.scappa", "turno", "Durata di default di SCAPPA.", CAT_TEMPO,
          "una Durata", "scelta", scelte=("turno", "un_attimo", "un_pochino", "un_bel_po")),
    Param("DURATA_AZIONE.muovi", "turno", "Durata di default di MUOVI (una stanza = cadenza "
          "base, J §4).", CAT_TEMPO, "una Durata", "scelta",
          scelte=("turno", "un_attimo", "un_pochino", "un_bel_po")),
    Param("DURATA_AZIONE.scendi", "un_attimo", "Durata di default di SCENDI.", CAT_TEMPO,
          "una Durata", "scelta", scelte=("turno", "un_attimo", "un_pochino", "un_bel_po")),
    Param("DURATA_AZIONE.altro", "un_pochino", "Durata di default dell'azione libera (ALTRO): "
          "la stima che il giocatore vede prima di confermare.", CAT_TEMPO, "una Durata",
          "scelta", scelte=("turno", "un_attimo", "un_pochino", "un_bel_po")),
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
    # --- Mappa / esplorazione ---
    Param("MAPPA_STANZE", 6, "Numero di stanze del piano generato dalla mappa (catena + un "
          "ramo trasversale seeded; la scala di discesa è garantita raggiungibile, G-18).",
          CAT_MAPPA, "intero ≥2", "int", "stanze"),
)

# Durata di default delle afflizioni per nome-blocco: eccezioni qui, il resto 3.
_DURATE_AFFLIZIONE_DEFAULT = {"stordito": 1}  # corto per costruzione: niente stun-lock


def _status_defs() -> tuple[Param, ...]:
    """Le foglie `STATUS.<nome>.durata_afflizione`, GENERATE dall'enum `Blocco`:
    un blocco nuovo nel vocabolario ha la sua durata §11 senza toccare questo file
    (l'eccezione al default va in `_DURATE_AFFLIZIONE_DEFAULT`)."""
    out: list[Param] = []
    for blocco in Blocco:
        nome = blocco.value
        default = _DURATE_AFFLIZIONE_DEFAULT.get(nome, 3)
        nota = " Corto per costruzione (1 = niente stun-lock)." if default == 1 else ""
        out.append(Param(
            f"STATUS.{nome}.durata_afflizione", default,
            f"Turni di decorso di {nome.upper()} applicato come afflizione "
            f"(rango copiato dall'applicatore, G-6).{nota}",
            CAT_STATUS, "intero ≥1", "int", "turni",
        ))
    return tuple(out)


# Le foglie per-status e per-archetipo sono GENERATE (dall'enum Blocco e dai profili
# base): le tre leve storiche migrano lì, sotto la categoria propria.
_DEFS = _DEFS + _status_defs() + _archetipi_defs()

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
    `scelte` ammesse, testo→str libera, altrimenti float. `ValueError` su input non valido."""
    if param.tipo == "int":
        return int(valore)
    if param.tipo == "scelta":
        s = str(valore)
        if param.scelte and s not in param.scelte:
            raise ValueError(f"'{s}' non in {param.scelte}")
        return s
    if param.tipo == "testo":
        return str(valore)
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
MOLT_ATTACCO_PESANTE = valore("MOLT_ATTACCO_PESANTE")
DANNO_BASE = valore("DANNO_BASE")

PROB_ANOMALIA = valore("PROB_ANOMALIA")
PROB_IMBOSCATA = valore("PROB_IMBOSCATA")
DURATA_BLOCCO_DEFAULT = valore("DURATA_BLOCCO_DEFAULT")
# Durata delle afflizioni per nome-blocco (le classi vivono in status.py: qui solo
# chiavi-stringa, calibrazione non importa i componenti). Derivata dall'ENUM: un
# blocco nuovo ha la sua voce senza toccare questo dict.
DURATA_AFFLIZIONE: dict[str, int] = {
    blocco.value: valore(f"STATUS.{blocco.value}.durata_afflizione") for blocco in Blocco
}
HP_DEFAULT = valore("HP_DEFAULT")
MAPPA_STANZE = valore("MAPPA_STANZE")

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
# Tempo diegetico per la pipeline GM: forbici (finestra di conferma) ed etichette
# (prompt/messaggio). I secondi sono finzione; i tick sono gioco (J §3).
FORBICE_DURATA: dict[Durata, str] = {d: valore(f"FORBICE.{d.value}") for d in Durata}
ETICHETTA_TEMPO: dict[Durata, str] = {d: valore(f"ETICHETTA_TEMPO.{d.value}") for d in Durata}
DURATA_AZIONE: dict[TipoAzione, Durata] = {
    t: Durata(valore(f"DURATA_AZIONE.{t.value}")) for t in TipoAzione
}
PRIMARIE_BASE_CARL: dict[StatId, int] = {
    StatId.FORZA: valore("CARL.forza"), StatId.DESTREZZA: valore("CARL.destrezza"),
    StatId.COSTITUZIONE: valore("CARL.costituzione"), StatId.INTELLIGENZA: valore("CARL.intelligenza"),
    StatId.SAGGEZZA: valore("CARL.saggezza"), StatId.FORTUNA: valore("CARL.fortuna"),
}


# --- Profilo-archetipo + registry (migrati da catalogo): binding F-6 + base §11 -

@dataclass(frozen=True)
class ProfiloArchetipo:
    """Profilo-base di un archetipo (valori §11 dal catalogo). La formula-madre lo scala.

    Oltre alle tre leve storiche (destrezza/pv/danno) porta le stat base mancanti, la
    geometria di combattimento (slot gear per-entità) e le resistenze tipate: tutto DATO
    editabile da catalogo/override (console/UI), mai cablato nel motore."""

    destrezza_base: int
    pv_base: int
    danno_base: int
    intelligenza_base: int
    difesa_base: int
    saggezza_base: int
    fortuna_base: int
    armatura: str
    taglia: str
    arma: str
    resistenze: dict[TipoDanno, float]


# Gli archetipi BASE (storici) del catalogo di calibrazione: gli slug sono l'identità
# (l'enum compilato non esiste più — D1). Gli archetipi NUOVI nascono come asset
# (`contenuti/archetipi/`) e si congelano nella stagione: qui vive solo la taratura
# dei tre storici (foglie `ARCH.*`), che resta l'autorità numerica loro.
ARCHETIPI_BASE: tuple[str, ...] = tuple(nome for nome, _disp, _cat, _d in _ARCH_PROFILI_DEFAULT)

# Tipi di danno tipati (escluso GENERICO, identità DT-6): le foglie `res.<tipo>`.
_TIPI_RESISTIBILI: tuple[TipoDanno, ...] = (TipoDanno.MISCHIA, TipoDanno.FUOCO, TipoDanno.VELENO)


def _resistenze_profilo(nome: str) -> dict[TipoDanno, float]:
    return {t: valore(f"ARCH.{nome}.res.{t.value}") for t in _TIPI_RESISTIBILI}


def _profilo(nome: str) -> ProfiloArchetipo:
    return ProfiloArchetipo(
        destrezza_base=valore(f"ARCH.{nome}.destrezza_base"),
        pv_base=valore(f"ARCH.{nome}.pv_base"),
        danno_base=valore(f"ARCH.{nome}.danno_base"),
        intelligenza_base=valore(f"ARCH.{nome}.intelligenza_base"),
        difesa_base=valore(f"ARCH.{nome}.difesa_base"),
        saggezza_base=valore(f"ARCH.{nome}.saggezza_base"),
        fortuna_base=valore(f"ARCH.{nome}.fortuna_base"),
        armatura=valore(f"ARCH.{nome}.armatura"),
        taglia=valore(f"ARCH.{nome}.taglia"),
        arma=valore(f"ARCH.{nome}.arma"),
        resistenze=_resistenze_profilo(nome),
    )


# `slug → profilo` (import-time; gli override valgono dal prossimo avvio, come le costanti).
REGISTRY_ARCHETIPI: dict[str, ProfiloArchetipo] = {
    nome: _profilo(nome) for nome in ARCHETIPI_BASE
}


def profilo_corrente(archetipo: str) -> ProfiloArchetipo:
    """Profilo **fresco** dagli override in memoria (per le anteprime della UI): a differenza
    di `REGISTRY_ARCHETIPI` (cache-ato all'import) rilegge catalogo+override adesso."""
    if archetipo not in REGISTRY_ARCHETIPI:
        raise KeyError(f"archetipo fuori dal catalogo di calibrazione: {archetipo!r}")
    return _profilo(archetipo)


# (Le vecchie `geometria_da_archetipo`/`resistenze_da_archetipo` sono state ritirate:
# geometria e resistenze si leggono dal PROFILO — `registry_archetipi_correnti()` a
# runtime, `profilo_corrente()` per le anteprime. Audit 2026-08: zero consumatori.)


# --- Formula-madre: (archetipo, grado, livello) → primarie ---------------------

def primarie_da_archetipo(
    archetipo: str, grado, livello: int, *, profilo: ProfiloArchetipo | None = None
) -> dict[StatId, int]:
    """Formula-madre delle `Primarie` di un'entità generata (SEGNAPOSTO §11).

    Profilo-base → vettore delle 7 `Primarie`, scalato da grado e profondità. Moltiplicative
    col fattore (`FORZA←danno_base`, `COSTITUZIONE←pv_base`); additive `+rango`
    (`DESTREZZA/INTELLIGENZA/SAGGEZZA/FORTUNA`); `DIFESA` flat in centesimi. Deriva, non legge
    dall'AI. `profilo` esplicito = anteprima fresca (UI); assente = `REGISTRY_ARCHETIPI`."""
    from .catalogo import rango_grado  # import locale: evita il ciclo calibrazione↔catalogo

    profilo = profilo if profilo is not None else REGISTRY_ARCHETIPI[archetipo]
    rango = rango_grado(grado)
    fattore = rango * max(1, livello)
    return {
        StatId.FORZA: profilo.danno_base * fattore,
        StatId.DESTREZZA: profilo.destrezza_base + rango,
        StatId.COSTITUZIONE: profilo.pv_base * fattore,
        StatId.INTELLIGENZA: profilo.intelligenza_base + rango,
        StatId.DIFESA: profilo.difesa_base,
        StatId.SAGGEZZA: profilo.saggezza_base + rango,
        StatId.FORTUNA: profilo.fortuna_base + rango,
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
