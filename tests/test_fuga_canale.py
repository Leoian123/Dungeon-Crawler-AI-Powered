"""La fuga dal combattimento: tre corsie, e un prezzo che scala col margine (FNC §4).

Perché il canale esiste. La prova è diventata deterministica (G §7.1): con una sola
soglia la fuga sarebbe *sempre* riuscita o *mai* riuscita per un dato personaggio, e
"fuggi sempre" tornerebbe a dominare — il difetto che il fix della fuga aveva già
chiuso una volta. La risposta non è reintrodurre casualità qui, ma **far costare** la
ritirata:

    margine ≥ MARGINE_FUGA_PULITA     → pulita, costo zero
    0 ≤ margine < MARGINE_FUGA_PULITA → i nemici vivi tirano un colpo d'opportunità
    margine < 0                       → negata, turno speso

I colpi d'opportunità passano dal **check 1** come qualunque altro colpo: nessuna
quarta casa di RNG (la tassonomia resta gate / opt-in / anomalia). Il test più
importante del file è l'ultimo: la fuga **non salva per decreto**.
"""

from __future__ import annotations

import esper

from contracts import ClasseProva, CombatResolved, MortePersonaggio, TurnoSaltato
from motore import SpecNemico, Stordito, protagonista, richiedi_fuga, tick
from motore.calibrazione import MARGINE_FUGA_PULITA, SOGLIE_PROVA
from tests.combat_helpers import avvia_scontro

# I nemici da scalari non hanno `EntitaMob` → la classe ripiega su BRONZO (comportamento
# storico). Le stat qui sotto sono calcolate su quella soglia.
_SOGLIA_BRONZO = SOGLIE_PROVA[ClasseProva.BRONZO]

_DEX_PULITA = _SOGLIA_BRONZO + MARGINE_FUGA_PULITA      # margine esatto della corsia 1
_DEX_OPPORTUNITA = _SOGLIA_BRONZO                        # margine 0 → corsia 2
_DEX_NEGATA = _SOGLIA_BRONZO - 1                         # margine -1 → corsia 3


def _fuggi_un_turno(*, destrezza: int, nemici, hp_prot: int = 10_000):
    """Monta uno scontro, chiede la fuga e fa girare UN turno del protagonista.

    Ritorna `(adapter, saltati)`: l'arnia registra gli esiti di scontro, i `TurnoSaltato`
    li raccogliamo qui perché servono solo a questo file."""
    bus, adapter, _enc = avvia_scontro(
        nemici=nemici, seed=1, hp_prot=hp_prot, destrezza_prot=destrezza
    )
    saltati: list[TurnoSaltato] = []
    bus.registra(TurnoSaltato, saltati.append)
    richiedi_fuga()
    # Il protagonista ha la destrezza più alta dei nemici sotto test → agisce per primo.
    tick()
    return adapter, saltati


def _eventi(adapter, tipo) -> list:
    return adapter.events_of(tipo)


# --- Corsia 1: fuga pulita ----------------------------------------------------

def test_margine_alto_fuga_pulita_senza_danno(mondo_isolato: str) -> None:
    adapter, saltati = _fuggi_un_turno(
        destrezza=_DEX_PULITA, nemici=[SpecNemico(destrezza=1, punti_vita=5)]
    )
    risolti = _eventi(adapter, CombatResolved)
    assert risolti and risolti[-1].fuga is True and risolti[-1].vittoria is False
    # Costo zero: il protagonista esce con gli HP intatti.
    _pent, _m, scheda = protagonista()
    assert scheda.punti_vita == 10_000


# --- Corsia 2: fuga col colpo d'opportunità -----------------------------------

def test_margine_basso_si_fugge_ma_si_incassa(mondo_isolato: str) -> None:
    adapter, saltati = _fuggi_un_turno(
        destrezza=_DEX_OPPORTUNITA, nemici=[SpecNemico(destrezza=1, punti_vita=5)]
    )
    risolti = _eventi(adapter, CombatResolved)
    assert risolti and risolti[-1].fuga is True, "con margine ≥ 0 la fuga riesce comunque"
    _pent, _m, scheda = protagonista()
    assert scheda.punti_vita < 10_000, "il colpo d'opportunità deve aver morso"


def test_un_colpo_dopportunita_per_ogni_nemico_vivo(mondo_isolato: str) -> None:
    # Il prezzo scala col numero di nemici: scappare da tre costa più che da uno.
    adapter_uno, _saltati = _fuggi_un_turno(
        destrezza=_DEX_OPPORTUNITA, nemici=[SpecNemico(destrezza=1, punti_vita=5)]
    )
    _p1, _m1, scheda_uno = protagonista()
    danno_da_uno = 10_000 - scheda_uno.punti_vita

    esper.switch_world("test-fuga-tre-nemici")
    try:
        adapter_tre, _saltati3 = _fuggi_un_turno(
            destrezza=_DEX_OPPORTUNITA,
            nemici=[SpecNemico(destrezza=1, punti_vita=5) for _ in range(3)],
        )
        _p3, _m3, scheda_tre = protagonista()
        danno_da_tre = 10_000 - scheda_tre.punti_vita
    finally:
        esper.switch_world("default")
        esper.delete_world("test-fuga-tre-nemici")

    assert danno_da_uno > 0
    assert danno_da_tre == 3 * danno_da_uno, (
        f"un colpo per nemico vivo: atteso {3 * danno_da_uno}, ottenuto {danno_da_tre}"
    )


def test_il_nemico_stordito_non_tira_il_colpo_dopportunita(mondo_isolato: str) -> None:
    """Regression (audit 2026-08-07): nel giro normale lo stordito perde il turno,
    ma sulla fuga tirava comunque il colpo d'opportunità — «stordito» deve valere
    anche per il braccio teso sulla schiena di chi scappa."""
    from motore.combattimento import _nemici_vivi

    bus, adapter, _enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=1, punti_vita=5)], seed=1,
        hp_prot=10_000, destrezza_prot=_DEX_OPPORTUNITA,
    )
    [nemico] = _nemici_vivi()
    esper.add_component(nemico, Stordito(rango=1, durata=2))
    richiedi_fuga()
    tick()
    risolti = adapter.events_of(CombatResolved)
    assert risolti and risolti[-1].fuga is True
    _pent, _m, scheda = protagonista()
    assert scheda.punti_vita == 10_000, (
        "il nemico stordito ha colpito comunque sul disimpegno"
    )


# --- Corsia 3: fuga negata ----------------------------------------------------

def test_margine_negativo_fuga_negata_e_turno_speso(mondo_isolato: str) -> None:
    adapter, saltati = _fuggi_un_turno(
        destrezza=_DEX_NEGATA, nemici=[SpecNemico(destrezza=1, punti_vita=5)]
    )
    assert not _eventi(adapter, CombatResolved), "la fuga negata NON chiude lo scontro"
    assert saltati and saltati[-1].causa == "fuga_negata"


def test_carl_a_stat_base_non_fugge_gratis_da_un_bronzo(mondo_isolato: str) -> None:
    """Il lucchetto anti-regressione del bilanciamento, non un dettaglio di taratura.

    Se la ritirata gratuita fosse alla portata del personaggio di partenza contro il
    nemico più debole, "fuggi sempre" tornerebbe a essere la scelta ottimale — è
    letteralmente il difetto che il gioco aveva (90% di vittorie fuggendo sempre) e che
    era già stato chiuso una volta. `MARGINE_FUGA_PULITA` è tarato **sopra** il margine
    di Carl contro un bronzo apposta: la fuga pulita è roba da build agile.
    """
    from contracts import StatId
    from motore.calibrazione import PRIMARIE_BASE_CARL

    dex_carl = PRIMARIE_BASE_CARL[StatId.DESTREZZA]
    margine_contro_bronzo = dex_carl - _SOGLIA_BRONZO
    assert 0 <= margine_contro_bronzo < MARGINE_FUGA_PULITA, (
        f"Carl (DEX {dex_carl}) contro un bronzo ha margine {margine_contro_bronzo}: "
        f"deve poter fuggire, ma PAGANDO (soglia pulita: {MARGINE_FUGA_PULITA}). "
        "Se questo assert è rosso, la fuga è tornata gratis o impossibile — entrambe "
        "regressioni, non ritocchi."
    )


def test_la_classe_dipende_dal_nemico_non_e_una_costante(mondo_isolato: str) -> None:
    # Stessa destrezza, avversario diverso: contro un mob senza grado (scalare) si
    # ripiega su BRONZO. È il ramo di compatibilità, e deve restare quello storico.
    from motore.combattimento import _classe_fuga
    assert _classe_fuga() is ClasseProva.BRONZO


# --- Il test che conta: la fuga non salva per decreto -------------------------

def test_se_il_colpo_dopportunita_uccide_e_morte_non_fuga(mondo_isolato: str) -> None:
    """Un protagonista a 1 HP che si ritira sotto i colpi **muore**.

    Emettere `CombatResolved(fuga=True)` qui significherebbe raccontare una ritirata
    riuscita a un cadavere — e, peggio, far sopravvivere alla permadeath (G-11) chi
    ha cliccato "Fuggi" al momento giusto."""
    adapter, saltati = _fuggi_un_turno(
        destrezza=_DEX_OPPORTUNITA,
        nemici=[SpecNemico(destrezza=1, punti_vita=5)],
        hp_prot=1,
    )
    morti = _eventi(adapter, MortePersonaggio)
    fughe = [e for e in _eventi(adapter, CombatResolved) if e.fuga]
    assert morti, "il colpo d'opportunità che uccide deve produrre MortePersonaggio"
    assert not fughe, "nessuna fuga riuscita può essere annunciata dopo la morte"
