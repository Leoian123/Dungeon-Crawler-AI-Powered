"""Property-test del check 1 (Gruppo 2 §11) — parte del compito dichiarato.

Due vincoli sui numeri `§11` (letti da `calibrazione`, MAI cablati qui):
  1. **Vincolo accoppiato** del contest: l'attaccante ordinario colpisce ≥ ~95%, mentre una
     **build d'evasione dedicata** porta il colpire ≤ ~15% (Donut). Esercitato su
     `esito_contest(acc, eva, rng)` — la *forma* del contest, separata dalla derivazione delle
     magnitudini (il wiring per-entità dell'evasione è un seam gear post-MVP).
  2. **Neutralità del graze** a `g = ½` straddle: la media del moltiplicatore `m` coincide col
     binario (E[m] = P) lontano dai clamp — varianza giù, media invariata.

I numeri sono quelli **approvati** nel piano (placeholder §11): se la calibrazione cambia,
questi assert sono la rete che la vincola. La banda statistica è stretta → seed fisso.
"""

from __future__ import annotations

import random

from motore import esito_contest
from motore import calibrazione as cal

_N = 20_000  # campione Monte-Carlo (seed fisso → niente flakiness)


def _connect_rate(acc: float, eva: float, *, seed: int = 12345) -> float:
    """Frazione di colpi che CONNETTONO (m ≠ 0) su `_N` estrazioni seeded.

    ⚠️ Include i **graze**: un colpo di striscio connette. È la metrica giusta per "quante
    volte incassi qualcosa", non per "quante volte le prendi in pieno" (vedi
    `_full_hit_rate`) — e le due divergono di tutta la larghezza della banda `δ`."""
    rng = random.Random(seed)
    connessi = sum(1 for _ in range(_N) if esito_contest(acc, eva, rng) != 0.0)
    return connessi / _N


def _full_hit_rate(acc: float, eva: float, *, seed: int = 12345) -> float:
    """Frazione di colpi PIENI (m = 1). È questo il "colpire" del vincolo Gr2 §11."""
    rng = random.Random(seed)
    pieni = sum(1 for _ in range(_N) if esito_contest(acc, eva, rng) == 1.0)
    return pieni / _N


# --- Vincolo 1: attaccante ordinario ≥ ~95%, dodge-build ≤ ~15% -----------------

def test_vincolo_accoppiato_check1() -> None:
    # Ordinario: con la geometria di default l'evasione ordinaria resta ≪ acc/F → auto-hit.
    # `K_EVA` è la scala globale: senza di lei nemmeno una build dedicata arriverebbe alla
    # banda, quindi entra nel conto anche qui (§11).
    acc_ord = (cal.W_FISICO * 10 + (1 - cal.W_FISICO) * 10) * cal.COEFF_ACC[cal.ARMA_DEFAULT]  # ≈13
    eva_ord = (
        10 * cal.K_EVA * cal.M_ARMATURA[cal.ARMATURA_DEFAULT] * cal.M_TAGLIA[cal.TAGLIA_DEFAULT]
    )
    assert _connect_rate(acc_ord, eva_ord) >= 0.95, "l'attaccante ordinario deve colpire ~sempre"

    # Build d'evasione dedicata (taglia minima + cloth + skill: seam gear): `eva` alza il
    # rapporto eva/acc finché il colpire crolla. Con s=2, eva/acc ≈ 5 → P ≈ 3.8% → connect ≈ 14%.
    acc_att = acc_ord
    eva_dodge = acc_att * 5
    assert _connect_rate(acc_att, eva_dodge) <= 0.15, "una build d'evasione dedicata deve portare il colpire ≤ ~15%"


def test_floor_gemello_nessuno_zero_garantito() -> None:
    # I due floor gemelli reggono al cap: contro un'evasione mostruosa il colpire NON è 0
    # (P ≥ MIN_COLPO), e contro un'accuratezza mostruosa la schivata NON è impossibile.
    assert _connect_rate(1, 10**6) > 0.0
    assert _connect_rate(10**6, 1) >= 0.95


# --- Vincolo 1-bis: gli stessi due punti, ma su ENTITÀ VERE --------------------
#
# Il salto che mancava. I test qui sopra esercitano `esito_contest(acc, eva)` su scalari
# *sintetici*: dimostrano che la FORMA del contest è tarata, non che esista un'entità del
# gioco capace di raggiungere quei numeri. Ed è esattamente lì che il modello era rotto —
# le derivate producevano `eva ≈ 0.1` contro una banda a `≈ 4.33`, quindi il check 1 era
# in auto-hit per OGNI entità e la dodge-build era irraggiungibile *per scala*.
#
# Questi test montano entità reali e leggono `acc_eff`/`eva_eff` dal fold: sono la
# definizione operativa di `K_EVA`.

def _acc_eva(attaccante: int, bersaglio: int) -> tuple[float, float]:
    from motore import acc_eff, eva_eff
    return acc_eff(attaccante), eva_eff(bersaglio)


def _in_banda(acc: float, eva: float) -> bool:
    """Vero se il check 1 PESCA davvero (sotto la banda è auto-hit deterministico)."""
    return eva >= acc / cal.F_AUTOHIT


def test_lentita_ordinaria_resta_in_auto_hit(mondo_isolato: str) -> None:
    """Carl contro un mob ordinario: nessuna pescata, il colpo va a segno.

    È la guardia che impedisce a `K_EVA` di crescere troppo: se un giorno l'entità
    ordinaria entrasse in banda, ogni scontro del gioco diventerebbe stocastico e il
    TTK tarato salterebbe. **Se questo va rosso, si abbassa `K_EVA`** — non si tocca
    l'assert."""
    from motore import Primarie, crea_protagonista, primarie_da_archetipo
    from contracts import Grado
    import esper

    pent = crea_protagonista(destrezza=10, punti_vita=30)
    slime = esper.create_entity(
        Primarie(valori=primarie_da_archetipo("slime", Grado.BRONZO, 1))
    )

    acc, eva = _acc_eva(slime, pent)          # il mob attacca Carl
    assert not _in_banda(acc, eva), (
        f"Carl è entrato in banda (acc={acc:.2f}, eva={eva:.2f}, soglia={acc/cal.F_AUTOHIT:.2f}): "
        "K_EVA è troppo alto e tutto il gioco è diventato stocastico"
    )


def test_una_build_devasione_raggiunge_davvero_la_banda(mondo_isolato: str) -> None:
    """L'altra metà del vincolo: **Donut deve esistere**.

    Un'entità piccola, agile e in veste — alta Destrezza, taglia infima — dev'essere
    colpita di rado da un attaccante ordinario. È il caso canonico che ha motivato
    l'adozione del modello a due check: in un risolutore dove ogni colpo va a segno, un
    gatto ad alta Destrezza e bassa Costituzione muore al piano 1."""
    from motore import Corredo, Primarie, primarie_da_archetipo, primarie_da_scalari
    from contracts import Grado, StatId
    import esper

    slime = esper.create_entity(
        Primarie(valori=primarie_da_archetipo("slime", Grado.BRONZO, 1))
    )
    valori = dict(primarie_da_scalari(destrezza=20, punti_vita=10))
    valori[StatId.DESTREZZA] = 20
    dodger = esper.create_entity(
        Primarie(valori=valori),
        Corredo(armatura="veste", taglia="infima", arma="naturale"),
    )

    acc, eva = _acc_eva(slime, dodger)
    assert _in_banda(acc, eva), (
        f"il dodger NON entra in banda (acc={acc:.2f}, eva={eva:.2f}, "
        f"soglia={acc/cal.F_AUTOHIT:.2f}): con questa scala la schivata non esiste in "
        "partita e il check 1 è codice morto — alza `K_EVA`"
    )
    # Il vincolo di Gr2 §11 è sul colpo PIENO: `(eva/acc)^s = 0.87/0.13`, cioè ≈2.6 a s=2.
    pieni = _full_hit_rate(acc, eva)
    assert pieni <= 0.15, (
        f"il dodger le prende in pieno il {pieni:.0%} delle volte: la build d'evasione "
        "non sta pagando"
    )
    # Il resto sono GRAZE (danno dimezzato), e non è un difetto della taratura: è la rete
    # che la letteratura indica proprio sull'avoidance-build, che altrimenti muore
    # all'unico colpo che passa (Gr2 §3.4). Chi schiva incassa spesso di striscio e di
    # rado in pieno — se un giorno anche questo numero crollasse, il dodger tornerebbe
    # fragile-e-intoccabile invece che schivo.
    connessi = _connect_rate(acc, eva)
    assert pieni < connessi <= 0.30, (
        f"pieni {pieni:.0%}, connessi {connessi:.0%}: fra i due deve starci la banda graze"
    )


def test_la_stessa_destrezza_senza_il_build_non_schiva(mondo_isolato: str) -> None:
    """La Destrezza da sola NON basta: serve il *build* (taglia + ciò che indossi).

    È il paletto contro la super-stat (Gr2 §5): la Destrezza dà la magnitudine, il
    coefficiente la pendenza. Se bastasse alzare Des, l'iniziativa e la schivata
    sarebbero la stessa leva e ogni personaggio agile diventerebbe intoccabile."""
    from motore import Corredo, Primarie, primarie_da_archetipo, primarie_da_scalari
    from contracts import Grado, StatId
    import esper

    slime = esper.create_entity(
        Primarie(valori=primarie_da_archetipo("slime", Grado.BRONZO, 1))
    )
    valori = dict(primarie_da_scalari(destrezza=20, punti_vita=10))
    valori[StatId.DESTREZZA] = 20
    agile_ma_grosso = esper.create_entity(
        Primarie(valori=valori),
        Corredo(armatura="pesante", taglia="media", arma="naturale"),
    )

    acc, eva = _acc_eva(slime, agile_ma_grosso)
    assert not _in_banda(acc, eva), (
        f"acc={acc:.2f}, eva={eva:.2f}: alta Destrezza in piastra non deve schivare — "
        "la Destrezza è la magnitudine, il coefficiente è la pendenza"
    )


# --- Vincolo 2: neutralità del graze a g = ½ (media invariata, varianza giù) -----

def test_graze_neutrale_a_g_mezzo() -> None:
    # acc == eva → P = 0.5; banda [0.4, 0.6] lontana dai clamp. A g=½ straddle: E[m] = P.
    acc = eva = 10.0
    P = acc ** cal.S_CONTEST / (acc ** cal.S_CONTEST + eva ** cal.S_CONTEST)
    lo, hi = P - cal.DELTA_BANDA / 2, P + cal.DELTA_BANDA / 2  # nessun clamp qui

    # Identità strutturale (vale per g=½): E[m] = lo·1 + (hi−lo)·g = (lo+hi)/2 = P.
    e_m_analitico = lo * 1.0 + (hi - lo) * cal.G_GRAZE + (1 - hi) * 0.0
    if cal.G_GRAZE == 0.5:
        assert abs(e_m_analitico - P) < 1e-9, "a g=½ straddle la media-danno è invariata (E[m]=P)"

    # …e il Monte-Carlo lo conferma entro tolleranza.
    rng = random.Random(999)
    media = sum(esito_contest(acc, eva, rng) for _ in range(_N)) / _N
    assert abs(media - e_m_analitico) < 0.02
