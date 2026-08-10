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

from contracts import Blocco, ClasseBeneficio, ClasseProva, Durata, Frequenza, Grado, StatId, TipoAzione, TipoDanno


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
CAT_MOSSE = "Mosse — mana, cooldown, moltiplicatori"
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
    Param("MOLT_ATTACCO_PESANTE", 1.5, "Moltiplicatore di danno della mossa 'attacco_pesante': "
          "entra nel check 2 dentro l'unico round.", CAT_MOSSE, "1 – 3"),
    # --- Economia delle mosse: mana e cooldown (il freno alla mossa dominante) ---
    Param("MANA_BASE", 0, "Termine costante della curva max_mana = MANA_BASE + K_MANA·Int. "
          "Il massimo NON è depositato: deriva (come max_hp da Costituzione).",
          CAT_MOSSE, "intero ≥0", "int", "mana"),
    Param("K_MANA", 1, "Mana per punto di Intelligenza. Con Int 10 → pool 10: regge ~3 dardi "
          "o 5 colpi pesanti prima del riposo.", CAT_MOSSE, "0 – 3"),
    Param("MOSSA.attacco_pesante.costo_mana", 2, "Mana speso dal colpo pesante: con il cooldown "
          "è il freno che gli toglie la dominanza (prima: molt. 1.5 a costo zero).",
          CAT_MOSSE, "intero ≥0", "int", "mana"),
    Param("MOSSA.attacco_pesante.cooldown", 2, "Turni di ricarica del colpo pesante. Convenzione: "
          "N=2 blocca esattamente un proprio turno (N=1 è di fatto nullo).",
          CAT_MOSSE, "intero ≥0", "int", "turni"),
    Param("MOSSA.morso_velenoso.cooldown", 3, "Ricarica del morso velenoso: il mob non "
          "ri-avvelena a ogni turno.", CAT_MOSSE, "intero ≥0", "int", "turni"),
    Param("MOSSA.sputo_infuocato.cooldown", 3, "Ricarica dello sputo infuocato.",
          CAT_MOSSE, "intero ≥0", "int", "turni"),
    Param("MOSSA.roulette_del_sistema.costo_mana", 4, "Mana della Roulette del Sistema "
          "(azzardo opt-in): cara di proposito — un colpo che può fare 1 come 20 non "
          "dev'essere anche economico.", CAT_MOSSE, "intero ≥0", "int"),
    Param("MOSSA.dardo_arcano.costo_mana", 3, "Mana del dardo arcano: l'incantesimo del "
          "protagonista. Costa più del pesante e non ha ricarica — la risorsa È il limite.",
          CAT_MOSSE, "intero ≥0", "int", "mana"),
    Param("MOLT_DARDO_ARCANO", 1.2, "Moltiplicatore del dardo arcano. Danno di tipo FUOCO: "
          "incrocia le resistenze già calibrate (nessun tipo nuovo nel vocabolario chiuso).",
          CAT_MOSSE, "1 – 3"),
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
    # --- mitigazione per categoria: l'ALTRA metà dello stesso pezzo d'armatura ---
    # `M_ARMATURA` dice quanto la categoria ti fa schivare (check 1); questa quanto ti fa
    # incassare (check 2). Vanno in DIREZIONI OPPOSTE ed è il punto: la piastra protegge
    # e impaccia, la veste lascia agili e scoperti. Se un giorno crescessero insieme, il
    # trade-off tank/dodger sparirebbe e l'armatura pesante diventerebbe sempre migliore.
    # In CENTESIMI, come tutta la `DIFESA` (contratto di scala §6): 100 = 1 punto di danno.
    Param("MITIGAZIONE_CENT.veste", 0, "Mitigazione della veste/nudo: nessuna (uno slot "
          "vuoto non protegge).", CAT_ARMATURA, "0", "int", unita="centesimi"),
    Param("MITIGAZIONE_CENT.leggera", 100, "Mitigazione dell'armatura leggera, per slot.",
          CAT_ARMATURA, "0 – 300", "int", unita="centesimi"),
    Param("MITIGAZIONE_CENT.media", 250, "Mitigazione dell'armatura media, per slot.",
          CAT_ARMATURA, "> leggera", "int", unita="centesimi"),
    Param("MITIGAZIONE_CENT.pesante", 500, "Mitigazione della piastra, per slot. Nove slot "
          "pieni di piastra valgono 45 punti di difesa: tarare guardando il TTK, non il "
          "singolo pezzo.", CAT_ARMATURA, "> media", "int", unita="centesimi"),
    Param("GRADI_PER_PROFONDITA", 2, "Quanti gradi diversi può schierare un piano, "
          "partendo dal bronzo e salendo di uno ogni `PROFONDITA_PER_GRADO` piani. "
          "Lega la difficoltà alla discesa: senza, il budget senza-piano offre "
          "`{bronzo, argento}` a qualunque profondità, e un piano 10 sarebbe facile "
          "quanto il primo.", CAT_CHECK2, "intero ≥1", "int"),
    Param("PROFONDITA_PER_GRADO", 1, "Ogni quanti piani la finestra dei gradi sale di "
          "uno. 1 = un grado nuovo a ogni piano.", CAT_CHECK2, "intero ≥1", "int"),
    Param("K_RANGO_HP", 0.7, "Quanto crescono gli HP per ogni GRADO sopra il bronzo "
          "(0.7 = +70% a passo). Deve stare SOPRA `K_RANGO_DANNO`: se le due curve "
          "salgono insieme, i nemici di grado alto diventano più duri E più letali "
          "contemporaneamente, il TTK esce dalla banda e nessun equipaggiamento può "
          "compensare. È così che il protagonista moriva per costruzione dal platino "
          "in su.", CAT_CHECK2, "> K_RANGO_DANNO"),
    Param("K_RANGO_DANNO", 0.4, "Quanto cresce il danno per ogni GRADO sopra il bronzo. "
          "Tenuto BASSO di proposito: un nemico di grado alto dev'essere una prova di "
          "resistenza, non un one-shot. Alzarlo è il modo più veloce di rendere il gioco "
          "ingiocabile ai piani profondi.", CAT_CHECK2, "< K_RANGO_HP"),
    Param("K_LIVELLO_HP", 0.5, "Quanto crescono gli HP per ogni PIANO sotto il primo. "
          "Gemello di K_RANGO_HP sull'asse profondità.", CAT_CHECK2, "≥0"),
    Param("K_LIVELLO_DANNO", 0.3, "Quanto cresce il danno per ogni PIANO sotto il primo. "
          "Gemello di K_RANGO_DANNO: sotto K_LIVELLO_HP, per la stessa ragione.",
          CAT_CHECK2, "< K_LIVELLO_HP"),
    # --- Corredo di riferimento: l'equip ATTESO al grado (la progressione, come dato) ---
    # Non è "cosa il giocatore possiede": è **cosa il gioco si aspetta che porti** quando
    # incontra quel grado. Serve a due cose insieme: dare al TTK una banda misurabile per
    # ogni grado (un celestiale affrontato nudi non è uno scontro, è un suicidio), e
    # dichiarare la curva del loot prima che il loot esista. È l'equipaggiamento a fare da
    # progressione, in assenza di livelli e punti-esperienza.
    Param("CORREDO_RIF.bronzo.armatura", "veste", "Armatura attesa contro un BRONZO: "
          "nessuna — è il grado con cui si comincia.", CAT_CHECK2, "chiave di m_armatura",
          "scelta", scelte=_SCELTE_ARMATURA),
    Param("CORREDO_RIF.bronzo.bonus_forza", 0, "Bonus d'attacco atteso contro un BRONZO.",
          CAT_CHECK2, "intero ≥0", "int"),
    Param("CORREDO_RIF.argento.armatura", "veste", "Armatura attesa contro un ARGENTO.",
          CAT_CHECK2, "chiave di m_armatura", "scelta", scelte=_SCELTE_ARMATURA),
    Param("CORREDO_RIF.argento.bonus_forza", 0, "Bonus d'attacco atteso contro un ARGENTO.",
          CAT_CHECK2, "intero ≥0", "int"),
    Param("CORREDO_RIF.oro.armatura", "leggera", "Armatura attesa contro un ORO: qui la "
          "mitigazione comincia a contare.", CAT_CHECK2, "chiave di m_armatura", "scelta",
          scelte=_SCELTE_ARMATURA),
    Param("CORREDO_RIF.oro.bonus_forza", 0, "Bonus d'attacco atteso contro un ORO.",
          CAT_CHECK2, "intero ≥0", "int"),
    Param("CORREDO_RIF.platino.armatura", "media", "Armatura attesa contro un PLATINO.",
          CAT_CHECK2, "chiave di m_armatura", "scelta", scelte=_SCELTE_ARMATURA),
    Param("CORREDO_RIF.platino.bonus_forza", 2, "Bonus d'attacco atteso contro un PLATINO: "
          "senza, lo scontro esce dalla banda per LUNGHEZZA (il nemico non muore).",
          CAT_CHECK2, "intero ≥0", "int"),
    Param("CORREDO_RIF.leggendario.armatura", "pesante", "Armatura attesa contro un "
          "LEGGENDARIO.", CAT_CHECK2, "chiave di m_armatura", "scelta", scelte=_SCELTE_ARMATURA),
    Param("CORREDO_RIF.leggendario.bonus_forza", 2, "Bonus d'attacco atteso contro un "
          "LEGGENDARIO.", CAT_CHECK2, "intero ≥0", "int"),
    Param("CORREDO_RIF.celestiale.armatura", "pesante", "Armatura attesa contro un "
          "CELESTIALE: piastra piena.", CAT_CHECK2, "chiave di m_armatura", "scelta",
          scelte=_SCELTE_ARMATURA),
    Param("CORREDO_RIF.celestiale.bonus_forza", 4, "Bonus d'attacco atteso contro un "
          "CELESTIALE.", CAT_CHECK2, "intero ≥0", "int"),
    Param("FORTUNA_PER_PUNTO", 0.02, "Quanto un punto di Fortuna inclina una pescata "
          "d'AZZARDO OPT-IN (mai il colpire, mai il danno base: quelli non pescano). È il "
          "primo consumatore reale della Fortuna, che il canone DCC dichiara «non una "
          "stat vera» e che piega loot ed eventi.", CAT_CHECK1, "0 – 0.1"),
    Param("FORTUNA_TETTO_BONUS", 0.35, "Tetto del bias di Fortuna. Cappato di proposito: "
          "senza, una build Fortuna trasformerebbe l'azzardo in una rendita — e un "
          "azzardo che paga sempre non è un azzardo, è un moltiplicatore.",
          CAT_CHECK1, "0 – 0.5"),
    Param("TETTO_AUTHORING", 4.0, "Quante volte il massimo storico può valere un numero "
          "scritto a mano in un asset, prima che la risoluzione lo rifiuti come errore "
          "di authoring. È la porta che mancava all'invariante «i numeri li deriva il "
          "motore»: era difeso sulla porta in-run (l'AI sceglie nomi, mai magnitudini) "
          "ma non su quella di authoring, dove `pv_base=99999` passava. Largo apposta — "
          "deve fermare il refuso e l'abuso, non il contenuto ambizioso.",
          CAT_CHECK2, "≥1; 1 = nessun asset può superare gli storici"),
    Param("K_EVA", 6.0, "SCALA GLOBALE dell'evasione: `coeff_eva = K_EVA · m_armatura · "
          "m_taglia · (1+Σpct)`. Esiste perché senza di lui il check 1 è IRRAGGIUNGIBILE: "
          "con le sole tabelle, un'entità qualunque ha eva≈0.1 contro acc≈13 e la banda si "
          "apre a ~4.33 — 43 volte sopra. Non è un problema di bilanciamento ma di SCALA, e "
          "va risolto con un knob dedicato invece di riscrivere M_ARMATURA/M_TAGLIA, che "
          "sono dato del cluster e portano la semantica RELATIVA (corretta). Si tara "
          "INSIEME a S_CONTEST contro due vincoli simultanei — vedi "
          "tests/test_calibrazione_check1.py, che è la vera definizione di questo numero.",
          CAT_CHECK1, "0 – ~40 (sopra ~43 anche l'attaccante ordinario entra in banda)"),
    # --- pesi degli slot nella media di m_armatura (ADR-1 II.3) ---
    # `m_armatura` di un'entità è la **media pesata** dei suoi nove slot: quanto un pezzo
    # ti impaccia dipende da DOVE lo porti. Gambe e busto pesano più dei piedi perché è lì
    # che una corazza toglie mobilità davvero. I pesi DEVONO sommare a 1 (è una media, e
    # un test lo impone): il denominatore è fisso, altrimenti riempire slot cambierebbe la
    # scala invece della sola composizione.
    Param("PESI_SLOT.busto", 0.22, "Peso del busto nella media di m_armatura: la corazza "
          "che conta di più.", CAT_ARMATURA, "0 – 1, somma dei nove = 1"),
    Param("PESI_SLOT.gambe", 0.20, "Peso delle gambe: correre è mezza schivata.",
          CAT_ARMATURA, "0 – 1"),
    Param("PESI_SLOT.testa", 0.14, "Peso della testa (elmo: vedere è schivare).",
          CAT_ARMATURA, "0 – 1"),
    Param("PESI_SLOT.braccio_dx", 0.09, "Peso del braccio destro.", CAT_ARMATURA, "0 – 1"),
    Param("PESI_SLOT.braccio_sx", 0.09, "Peso del braccio sinistro.", CAT_ARMATURA, "0 – 1"),
    Param("PESI_SLOT.mano_dx", 0.05, "Peso della mano destra (guanto).", CAT_ARMATURA, "0 – 1"),
    Param("PESI_SLOT.mano_sx", 0.05, "Peso della mano sinistra (guanto).", CAT_ARMATURA, "0 – 1"),
    Param("PESI_SLOT.piede_dx", 0.08, "Peso del piede destro (stivale).", CAT_ARMATURA, "0 – 1"),
    Param("PESI_SLOT.piede_sx", 0.08, "Peso del piede sinistro (stivale).", CAT_ARMATURA, "0 – 1"),
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
    # Pesi delle classi di frequenza delle tabelle di spawn (territorio, 2026-08):
    # la FORMA (comune/insolito/raro) è vocabolario chiuso del contratto; i pesi
    # sono foglie §11 — l'AI e l'authoring non emettono mai un numero.
    Param("PESO_FREQUENZA.comune", 6, "Peso di pesca di una voce di spawn COMUNE.",
          CAT_PROB, "intero ≥1", "int"),
    Param("PESO_FREQUENZA.insolito", 3, "Peso di pesca di una voce di spawn INSOLITA.",
          CAT_PROB, "intero ≥1", "int"),
    Param("PESO_FREQUENZA.raro", 1, "Peso di pesca di una voce di spawn RARA.",
          CAT_PROB, "intero ≥1", "int"),
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
    Param("DURATA_AZIONE.riposa", "un_pochino", "Durata del RIPOSO: quanti tick di piano "
          "costa fermarsi a recuperare. È la leva del rischio — il dado-evento gira a "
          "ogni tick, quindi più lungo il riposo, più probabile l'imboscata.",
          CAT_TEMPO, "una Durata", "scelta",
          scelte=("turno", "un_attimo", "un_pochino", "un_bel_po")),
    Param("DURATA_AZIONE.altro", "un_pochino", "Durata di default dell'azione libera (ALTRO): "
          "la stima che il giocatore vede prima di confermare.", CAT_TEMPO, "una Durata",
          "scelta", scelte=("turno", "un_attimo", "un_pochino", "un_bel_po")),
    # --- Pavimenti dei benefici (gate anti-arbitraggio, asimmetrico) ---
    # Il costo MINIMO che una classe di beneficio reclama: l'AI classifica, il motore
    # addebita. `fuori_scala` = irraggiungibile in-run: beneficio negato, tariffa in
    # faccia. Il gate clampa SOLO verso l'alto (più tempo del pavimento passa sempre):
    # la manipolazione spinge in una direzione sola, la difesa pure.
    Param("PAVIMENTO_BENEFICIO.nessuno", "turno", "Azione di puro colore: nessun pavimento "
          "(il minimo di cadenza).", CAT_TEMPO, "una Durata o fuori_scala", "scelta",
          scelte=("turno", "un_attimo", "un_pochino", "un_bel_po", "fuori_scala")),
    Param("PAVIMENTO_BENEFICIO.recupero", "un_pochino", "Riposare/medicarsi costa almeno "
          "questo: sotto, il recupero non esiste.", CAT_TEMPO, "una Durata o fuori_scala",
          "scelta", scelte=("turno", "un_attimo", "un_pochino", "un_bel_po", "fuori_scala")),
    Param("PAVIMENTO_BENEFICIO.lavoro", "un_pochino", "Lavoro manuale (scuoiare, raccogliere, "
          "costruire): il minimo per un esito che valga qualcosa.", CAT_TEMPO,
          "una Durata o fuori_scala", "scelta",
          scelte=("turno", "un_attimo", "un_pochino", "un_bel_po", "fuori_scala")),
    Param("PAVIMENTO_BENEFICIO.addestramento", "un_bel_po", "Una sessione di pratica: meno "
          "di così è ginnastica, non allenamento.", CAT_TEMPO, "una Durata o fuori_scala",
          "scelta", scelte=("turno", "un_attimo", "un_pochino", "un_bel_po", "fuori_scala")),
    Param("PAVIMENTO_BENEFICIO.svolta", "fuori_scala", "La pretesa di maestria/avanzamento "
          "permanente: fuori scala per costruzione — il Sistema mostra la tariffa vera e "
          "nega il resto. Nessun gaslighting la abbassa: non è nel prompt, è qui.",
          CAT_TEMPO, "una Durata o fuori_scala", "scelta",
          scelte=("turno", "un_attimo", "un_pochino", "un_bel_po", "fuori_scala")),
    Param("TARIFFA_FUORI_SCALA.recupero", "una giornata intera", "Etichetta diegetica della "
          "tariffa se RECUPERO fosse ricalibrato fuori scala.", CAT_TEMPO, "testo breve", "testo"),
    Param("TARIFFA_FUORI_SCALA.lavoro", "qualche giorno", "Etichetta diegetica della tariffa "
          "se LAVORO fosse ricalibrato fuori scala.", CAT_TEMPO, "testo breve", "testo"),
    Param("TARIFFA_FUORI_SCALA.addestramento", "qualche mese", "Etichetta diegetica della "
          "tariffa se ADDESTRAMENTO fosse ricalibrato fuori scala.", CAT_TEMPO,
          "testo breve", "testo"),
    Param("TARIFFA_FUORI_SCALA.svolta", "circa due anni", "La tariffa che il Sistema sbatte "
          "in faccia a chi pretende la maestria: prendere o lasciare.", CAT_TEMPO,
          "testo breve", "testo"),
    # --- Prove ---
    # Scala RI-DERIVATA per la prova a margine (nessun tiro): ci si confronta con lo
    # `stat_eff` GREZZO, non più con `stat + d20`. Riferimento: Carl nasce a 10 in ogni
    # primaria → bronzo passa di misura, argento è in bilico, oro chiede equipaggiamento
    # (≈ +10 da gear), celestiale resta fuori portata anche equipaggiati. È la scala che
    # rende la classe una *promessa* leggibile, non un numero arbitrario.
    Param("SOGLIA_PROVA.bronzo", 6, "Soglia (margine deterministico) della classe BRONZO: più "
          "alta = più difficile. Riferimento: stat base 10 la supera di 4.", CAT_PROVE,
          "interi crescenti", "int"),
    Param("SOGLIA_PROVA.argento", 10, "Soglia della classe ARGENTO: la pari-stat di un "
          "personaggio non specializzato (margine 0 = riesce, ma di misura).", CAT_PROVE,
          "> bronzo", "int"),
    Param("SOGLIA_PROVA.oro", 14, "Soglia della classe ORO: fuori portata a stat base, "
          "raggiungibile equipaggiati o con la stat giusta.", CAT_PROVE, "> argento", "int"),
    Param("SOGLIA_PROVA.platino", 18, "Soglia della classe PLATINO.", CAT_PROVE, "> oro", "int"),
    Param("SOGLIA_PROVA.leggendario", 24, "Soglia della classe LEGGENDARIO.", CAT_PROVE,
          "> platino", "int"),
    Param("SOGLIA_PROVA.celestiale", 32, "Soglia della classe CELESTIALE ('sedurre un dio'): "
          "deve restare irraggiungibile con l'equip dell'MVP.", CAT_PROVE, "> leggendario", "int"),
    Param("MARGINE_GRADO", 6, "Ampiezza della fascia dei gradi di esito: margine ≥ +MARGINE_GRADO "
          "= successo pieno, ≤ −MARGINE_GRADO = fallimento grave, in mezzo successo/fallimento "
          "normale. È la texture che sostituisce la varianza del dado.", CAT_PROVE,
          "intero ≥1 (fasce simmetriche attorno a 0)", "int"),
    Param("MARGINE_FUGA_PULITA", 6, "Margine dal quale la fuga dal combattimento è PULITA "
          "(costo zero). Sotto, ma ≥0, si fugge incassando il colpo d'opportunità di ogni "
          "nemico vivo; sotto zero la fuga è negata e il turno è speso. Tarato SOPRA il "
          "margine di Carl contro un bronzo (10−6=4) di proposito: la ritirata gratuita "
          "dev'essere una cosa da BUILD agile, non l'uscita di sicurezza sempre aperta di "
          "chiunque — altrimenti 'fuggi sempre' torna a dominare. Abbassalo per rendere il "
          "gioco più clemente.", CAT_PROVE, "intero ≥0", "int"),
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
    # --- Riposo (l'anello «sostentati»: recupero per tick di downtime) ---
    Param("RIPOSO.hp_per_tick", 2, "HP recuperati per tick di riposo. Il riposo spende "
          "DURATA_AZIONE.riposa via fast-forward; il recupero è tick × questa foglia, "
          "clampato al massimo derivato — alzala per un dungeon clemente.",
          CAT_TEMPO, "intero ≥0", "int", "HP/tick"),
    Param("RIPOSO.mana_per_tick", 1, "Mana recuperato per tick di riposo (clampato al "
          "massimo derivato da Intelligenza).", CAT_TEMPO, "intero ≥0", "int", "mana/tick"),
    Param("PROB_DROP", 0.5, "Probabilità che uno scontro VINTO lasci un oggetto (pescata "
          "seeded dallo stream di sessione, fra le fonti del catalogo non ancora "
          "possedute). 0 = niente loot; 1 = drop garantito.", CAT_MAPPA, "0 – 1", "float"),
    # --- Mappa / esplorazione ---
    Param("MAPPA_STANZE", 6, "Numero di stanze del piano generato dalla mappa (catena + un "
          "ramo trasversale seeded; la scala di discesa è garantita raggiungibile, G-18).",
          CAT_MAPPA, "intero ≥2", "int", "stanze"),
)

# Durata di default delle afflizioni per nome-blocco: eccezioni qui, il resto 3.
_DURATE_AFFLIZIONE_DEFAULT = {"stordito": 1}  # corto per costruzione: niente stun-lock

# HP mossi per tick d'afflizione, per rango. Segno = direzione: negativo ferisce,
# positivo cura, **zero = l'effetto sta altrove** (lo Stordito non toglie HP: consuma il
# turno). Erano letterali in `SPEC_STATUS`, cioè gli ultimi numeri di bilanciamento
# rimasti fuori dal catalogo §11 — invisibili alla console di calibrazione e non
# tarabili senza toccare il codice.
_DELTA_PER_RANGO_DEFAULT = {"veleno": -1, "brucia": -1, "rigenerazione": +1, "stordito": 0}


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
        delta = _DELTA_PER_RANGO_DEFAULT.get(nome, -1)
        out.append(Param(
            f"STATUS.{nome}.delta_per_rango", delta,
            f"HP mossi a ogni tick di {nome.upper()}, MOLTIPLICATI per il rango. "
            "Negativo ferisce, positivo cura, 0 = l'effetto non passa dagli HP "
            "(lo Stordito consuma il turno).",
            CAT_STATUS, "intero (segno = direzione)", "int", "HP per rango",
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
K_EVA = valore("K_EVA")
TETTO_AUTHORING = valore("TETTO_AUTHORING")
FORTUNA_PER_PUNTO = valore("FORTUNA_PER_PUNTO")
FORTUNA_TETTO_BONUS = valore("FORTUNA_TETTO_BONUS")
GRADI_PER_PROFONDITA = valore("GRADI_PER_PROFONDITA")
PROFONDITA_PER_GRADO = valore("PROFONDITA_PER_GRADO")
K_RANGO_HP = valore("K_RANGO_HP")
K_RANGO_DANNO = valore("K_RANGO_DANNO")
K_LIVELLO_HP = valore("K_LIVELLO_HP")
K_LIVELLO_DANNO = valore("K_LIVELLO_DANNO")
# Generato dall'enum `Grado` (sincronia #7): un grado nuovo senza corredo di riferimento
# è un `KeyError` all'import, non uno scontro tarato per caso.
CORREDO_RIFERIMENTO: dict[str, dict[str, object]] = {
    grado.value: {
        "armatura": valore(f"CORREDO_RIF.{grado.value}.armatura"),
        "bonus_forza": valore(f"CORREDO_RIF.{grado.value}.bonus_forza"),
    }
    for grado in Grado
}

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
MOLT_DARDO_ARCANO = valore("MOLT_DARDO_ARCANO")
MANA_BASE = valore("MANA_BASE")
K_MANA = valore("K_MANA")
# Costi e ricariche per chiave di mossa: il catalogo (`mosse.py`) li LEGGE, non li
# possiede — così la console §11 li tara senza toccare il codice.
COSTO_MANA_MOSSA: dict[str, int] = {
    "attacco_pesante": valore("MOSSA.attacco_pesante.costo_mana"),
    "dardo_arcano": valore("MOSSA.dardo_arcano.costo_mana"),
    "roulette_del_sistema": valore("MOSSA.roulette_del_sistema.costo_mana"),
}
COOLDOWN_MOSSA: dict[str, int] = {
    "attacco_pesante": valore("MOSSA.attacco_pesante.cooldown"),
    "morso_velenoso": valore("MOSSA.morso_velenoso.cooldown"),
    "sputo_infuocato": valore("MOSSA.sputo_infuocato.cooldown"),
}
DANNO_BASE = valore("DANNO_BASE")

PROB_ANOMALIA = valore("PROB_ANOMALIA")
PROB_IMBOSCATA = valore("PROB_IMBOSCATA")
# Pesi per classe di frequenza (chiavi-stringa: derivate dall'enum del contratto —
# un membro nuovo di `Frequenza` senza foglia è un KeyError all'import, pattern
# SPEC_STATUS). Consumate da `territorio.pesca_spawn` via il catalogo.
PESO_FREQUENZA: dict[str, int] = {
    f.value: valore(f"PESO_FREQUENZA.{f.value}") for f in Frequenza
}
DURATA_BLOCCO_DEFAULT = valore("DURATA_BLOCCO_DEFAULT")
# Durata delle afflizioni per nome-blocco (le classi vivono in status.py: qui solo
# chiavi-stringa, calibrazione non importa i componenti). Derivata dall'ENUM: un
# blocco nuovo ha la sua voce senza toccare questo dict.
DURATA_AFFLIZIONE: dict[str, int] = {
    blocco.value: valore(f"STATUS.{blocco.value}.durata_afflizione") for blocco in Blocco
}
DELTA_PER_RANGO: dict[str, int] = {
    blocco.value: valore(f"STATUS.{blocco.value}.delta_per_rango") for blocco in Blocco
}
HP_DEFAULT = valore("HP_DEFAULT")
MAPPA_STANZE = valore("MAPPA_STANZE")
RIPOSO_HP_PER_TICK = valore("RIPOSO.hp_per_tick")
RIPOSO_MANA_PER_TICK = valore("RIPOSO.mana_per_tick")
PROB_DROP = valore("PROB_DROP")

M_ARMATURA: dict[str, float] = {
    "veste": valore("M_ARMATURA.veste"), "leggera": valore("M_ARMATURA.leggera"),
    "media": valore("M_ARMATURA.media"), "pesante": valore("M_ARMATURA.pesante"),
}
# Generata dalle stesse chiavi di `M_ARMATURA`: le due facce della categoria non possono
# desincronizzarsi (una categoria che schiva ma non protegge sarebbe un buco silenzioso).
MITIGAZIONE_CENT: dict[str, int] = {
    categoria: valore(f"MITIGAZIONE_CENT.{categoria}") for categoria in M_ARMATURA
}
# Chiavi = i `.value` degli slot-armatura di `contracts` (invariante #7, verificato da
# `test_equip_f3.py`). Non le elenco importando `SLOT_ARMATURA` per non far dipendere la
# calibrazione dalla proiezione: qui vivono i numeri, il vocabolario sta in `contracts`.
PESI_SLOT_ARMATURA: dict[str, float] = {
    slot: valore(f"PESI_SLOT.{slot}")
    for slot in (
        "testa", "busto", "braccio_dx", "braccio_sx",
        "mano_dx", "mano_sx", "gambe", "piede_dx", "piede_sx",
    )
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
# **Generata dall'enum**, non elencata a mano: era una lista letterale a 4 voci mentre
# `ClasseProva` ne aveva 4 e `Grado` 6 — la desincronizzazione stava nell'enum, e una tabella
# scritta a mano non poteva accorgersene. Così una classe nuova senza la sua foglia §11 è un
# `KeyError` all'import (rumoroso), mai una voce mancante scoperta a runtime (F-6).
SOGLIE_PROVA: dict[ClasseProva, int] = {
    classe: valore(f"SOGLIA_PROVA.{classe.value}") for classe in ClasseProva
}
MARGINE_GRADO = valore("MARGINE_GRADO")
MARGINE_FUGA_PULITA = valore("MARGINE_FUGA_PULITA")
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
# Gate anti-arbitraggio (gm.py): pavimento di costo per classe di beneficio. Il
# sentinella `fuori_scala` NON è una `Durata`: resta stringa, e la tabella delle
# tariffe fornisce l'etichetta diegetica per il rifiuto. Comprensione per-enum:
# una classe nuova senza voce = KeyError all'import (F-6), mai un buco a runtime.
FUORI_SCALA = "fuori_scala"
PAVIMENTO_BENEFICIO: dict[ClasseBeneficio, str] = {
    c: valore(f"PAVIMENTO_BENEFICIO.{c.value}") for c in ClasseBeneficio
}
TARIFFA_FUORI_SCALA: dict[ClasseBeneficio, str] = {
    c: valore(f"TARIFFA_FUORI_SCALA.{c.value}")
    for c in ClasseBeneficio if c is not ClasseBeneficio.NESSUNO
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
    (`FORZA←danno_base`, `COSTITUZIONE←pv_base`); additive `+rango`
    (`DESTREZZA/INTELLIGENZA/SAGGEZZA/FORTUNA`); `DIFESA` flat in centesimi. Deriva, non legge
    dall'AI. `profilo` esplicito = anteprima fresca (UI); assente = `REGISTRY_ARCHETIPI`.

    **HP e danno scalano SEPARATAMENTE, ed è il punto della fase F9.** Prima c'era un
    `fattore = rango × livello` unico applicato a entrambi: al crescere del grado lo
    scontro diventava insieme **più lungo** (HP↑) e **più letale** (danno↑) — il modo più
    rapido di uscire dalla banda del TTK. Misurato: contro uno scheletro celestiale il
    protagonista serviva 11 colpi e ne incassava 3, cioè moriva *per costruzione*, e
    nessuna quantità di equipaggiamento poteva compensare due curve che salivano insieme.

    Ora gli HP salgono più del danno (`K_RANGO_HP > K_RANGO_DANNO`): i nemici di grado
    alto sono **più duri**, non **più letali**, e la mitigazione da gear può reggere il
    passo. Chi ritocca queste due costanti sposta il gioco intero — il lucchetto è
    `tests/test_ttk.py`."""
    from .catalogo import rango_grado  # import locale: evita il ciclo calibrazione↔catalogo

    profilo = profilo if profilo is not None else REGISTRY_ARCHETIPI[archetipo]
    rango = rango_grado(grado)
    passi_rango = rango - 1                      # bronzo = 0: il profilo-base è il bronzo
    passi_livello = max(1, livello) - 1
    scala_hp = (1 + K_RANGO_HP * passi_rango) * (1 + K_LIVELLO_HP * passi_livello)
    scala_danno = (1 + K_RANGO_DANNO * passi_rango) * (1 + K_LIVELLO_DANNO * passi_livello)
    return {
        StatId.FORZA: max(1, round(profilo.danno_base * scala_danno)),
        StatId.DESTREZZA: profilo.destrezza_base + rango,
        StatId.COSTITUZIONE: max(1, round(profilo.pv_base * scala_hp)),
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
