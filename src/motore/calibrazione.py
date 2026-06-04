"""Calibrazione del combattimento — i VALORI §11, in **un solo posto** (guida §0).

Tutti i numeri di bilanciamento del Gruppo 2 vivono qui, marcati `# [§11]`: scalari *e*
tabelle. Sono **importati** dove servono (derivate, risolutore, escalation, spawn), MAI
cablati inline nelle formule — cambiare un numero non deve toccare il risolutore.

Distinzione (guida §0):
  - Le tabelle che il cluster **dà** come punto di partenza (`M_ARMATURA`, `M_TAGLIA`,
    `COEFF_ACC`, `MIN_COLPO ≈ 1%`) sono **cablate come default** — sono il punto di
    partenza *dato*, non un'invenzione — ma marcate `[§11]` lo stesso.
  - Gli altri (`S_CONTEST`, `F_AUTOHIT`, `DELTA_BANDA`, `G_GRAZE`, `R_SOGLIA_CROLLO`,
    `MULT_MIN/MAX`, pesi `w`, curva HP, basi-archetipo) sono **placeholder neutri**
    scelti coerenti col vincolo accoppiato del check 1 (guida §11). La calibrazione vera
    è il **property-test accoppiato**; il risolutore non cambia al cambiare dei numeri.

Dipendenze: solo `contracts` a livello di modulo (la formula-madre importa `catalogo`
localmente per evitare il ciclo `calibrazione ↔ catalogo`).
"""

from __future__ import annotations

from contracts import Archetipo, Grado, StatId

# --- Action Point del loop ----------------------------------------------------
# AP max clampato a 1 nell'MVP; i talenti (post-MVP) alzano il max o danno azioni
# bonus. Vive QUI per essere importato sia da `scheda.py` (protagonista) sia da
# `combattimento.py` (nemici) senza ciclo.
AP_MAX_MVP = 1  # [§11] placeholder — da calibrare


# --- Check 1 (colpire): contest seeded a banda + graze (guida §7.1) -----------
S_CONTEST = 2       # [§11] esponente del contest acc^s/(acc^s+eva^s); default s≥2
MIN_COLPO = 0.01    # [§11] floor/cap gemello del colpire (~1% = floor-hit/cap di Mordheim)
F_AUTOHIT = 3       # [§11] banda: si pesca solo se eva_eff ≥ acc_eff/F (sotto = auto-hit)
DELTA_BANDA = 0.20  # [§11] larghezza della banda di graze (bordi clampati nei floor gemelli)
G_GRAZE = 0.5       # [§11] magnitudine del graze (straddle: media invariata, varianza giù)


# --- Tabelle DATE dal cluster (guida §5.3/§5.4): punto di partenza, marcate §11 -
# Coefficiente di mobilità per categoria d'armatura (set uniforme; mix = media pesata).
M_ARMATURA: dict[str, float] = {  # [§11] punto di partenza dato
    "veste": 0.10, "leggera": 0.075, "media": 0.05, "pesante": 0.025,
}
# Coefficiente di taglia (più piccolo = schivi più; colossale = mai).
M_TAGLIA: dict[str, float] = {  # [§11] punto di partenza dato
    "colossale": 0.0, "enorme": 0.01, "grossa": 0.05,
    "media": 0.10, "piccola": 0.50, "infima": 1.00,
}
# Coefficiente d'arma rispetto alla taglia del portatore.
COEFF_ACC: dict[str, float] = {  # [§11] punto di partenza dato
    "pari": 1.0, "piu_piccola": 1.5, "mismatch": 0.0001, "naturale": 1.3,
}


# --- Accuratezza: peso Des↔Int per tipo d'attacco (mai 0/1, guida §5.4) -------
W_FISICO = 0.8  # [§11] attacco fisico → Destrezza domina (l'altra stat in minima parte)
W_MAGIA = 0.2   # [§11] incantesimo → Intelligenza domina


# --- Geometria di default dell'MVP (entità nude, taglia media, armi naturali) --
# SEAM per il gear futuro: queste categorie diventeranno **dato per-entità** (slot
# armatura / taglia / arma). Oggi sono i default da cui le derivate leggono i coeff,
# così il combattimento ordinario è auto-hit deterministico (eva ≪ acc/F) e la forma
# stocastica del check 1 si attiva SOLO contro un dodge-build costruito apposta.
ARMATURA_DEFAULT = "veste"   # [§11] nudo = massima mobilità (per m_armatura)
TAGLIA_DEFAULT = "media"     # [§11]
ARMA_DEFAULT = "naturale"    # [§11] armi naturali (pugni/calci/artigli): base 1.3


# --- Difesa / HP --------------------------------------------------------------
# Il termine muscolare 0.01·Cost è **strutturale**: Cost_eff (unità) vale Cost_eff
# centesimi (vedi `derivate.cost_eff_come_centesimi`) — nessuna costante separata.
HP_BASE = 0  # [§11] curva max_hp = HP_BASE + K_HP·Cost (mantiene l'attuale 1:1 §5)
K_HP = 1     # [§11] (TTK 3–6 round da tarare col property-test)


# --- Escalation a contatore (crollo, guida §9) --------------------------------
R_SOGLIA_CROLLO = 20    # [§11] oltre R turni-scontro l'escalation scatta (rete di sicurezza)
CROLLO_INCREMENTO = 1   # [§11] crescita lineare illimitata del crollo (aritmetica monotòna)


# --- Layer dei tipi: cap di resistenza/vulnerabilità (guida §10.4) ------------
MULT_MIN = 0.25  # [§11] una resistenza non azzera mai del tutto (>0)
MULT_MAX = 3.0   # [§11] cap della vulnerabilità


# --- Basi-archetipo: formula-madre (archetipo, grado, livello) → primarie ------
# UNA sola tabella-archetipo: la base sta in `catalogo.REGISTRY_ARCHETIPI` (il binding F-6,
# `ProfiloArchetipo{destrezza_base, pv_base, danno_base}`, già SEGNAPOSTO §11). Qui la
# **formula** che la mappa a un vettore `Primarie` e la scala per grado/profondità.

def primarie_da_archetipo(archetipo: Archetipo, grado: Grado, livello: int) -> dict[StatId, int]:
    """Formula-madre delle `Primarie` di un'entità generata (SEGNAPOSTO §11).

    Profilo-base (da `REGISTRY_ARCHETIPI`) → vettore `Primarie`, scalato da grado e profondità
    (deriva, non legge dall'AI). Mappa: `FORZA←danno_base`, `DESTREZZA←destrezza_base`,
    `COSTITUZIONE←pv_base`, `INTELLIGENZA←proxy`. I *numeri* sono placeholder; la *struttura*
    è completa.
    """
    from .catalogo import REGISTRY_ARCHETIPI, rango_grado  # import locale: evita il ciclo calibrazione↔catalogo

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

    `SpecNemico` MVP porta solo `(destrezza, punti_vita)`; per far derivare atk/def/eva/acc
    identiche al protagonista, lo spawn ha bisogno di un vettore `Primarie` completo. FORZA e
    INTELLIGENZA non hanno uno scalare nello spec → entrano come **proxy SEGNAPOSTO** legati
    alla destrezza (un mob più agile è anche un po' più offensivo). §11.
    """
    return {
        StatId.FORZA: destrezza,                 # [§11] proxy: nessuno scalare Forza nello spec
        StatId.DESTREZZA: destrezza,
        StatId.COSTITUZIONE: punti_vita,         # è anche la fonte di mitigazione (def_eff)
        StatId.INTELLIGENZA: max(1, destrezza // 2),  # [§11] proxy
    }
