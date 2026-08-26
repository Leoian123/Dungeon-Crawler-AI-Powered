"""⛔ **L'azzardo NON è il tiro del combattimento** — e questi test lo rendono difficile
da dimenticare.

Il rischio che questo file esiste per coprire non è un bug: è un **fraintendimento**. Un
sistema con `DannoVariabile(min, max)` somiglia moltissimo al `1d8+STR` dei JRPG, e chi
arriva su questo codice più tardi — persona o agente — tenderà a concludere che *quello*
sia il motore del danno. Non lo è: il danno del gioco è deterministico (check 2), il solo
tiro del percorso base è il gate del check 1, e questo modulo è casualità **opt-in** che
esiste solo dove un oggetto o una magia la dichiara (Gr2 §5.2).

I cinque test sotto sono la difesa, e sono **statici o quasi** di proposito: non si
aggirano per fortuna del seed, e falliscono al momento della modifica invece che durante
una partita.

  T1 — l'azzardo non è nel percorso base (nessun repertorio di default, nessun asset);
  T2 — il risolutore pesca SOLO per il check 1: contate le estrazioni;
  T3 — senza consenso dichiarato non si pesca affatto;
  T4 — `azione.py` non importa `azzardo` (la dipendenza è a senso unico);
  T5 — l'atomo base ha esattamente due primitivi.
"""

from __future__ import annotations

import ast
import random
from pathlib import Path

import esper
import pytest

from contracts import SedeAccessorio, StatId
from motore import (
    Accessorio,
    Azione,
    CATALOGO_MOSSE,
    MOSSE_DEFAULT,
    Primarie,
    SistemaTurnoCombattimento,
    azione_da_mossa,
    crea_protagonista,
    equipaggia,
    mosse_di,
    primarie_da_scalari,
    togli,
)
from motore.azzardo import (
    DannoVariabile,
    EffettoAzzardo,
    EsitoAzzardo,
    TiroAzzardo,
    risolvi_effetto_azzardo,
)
from motore.scheda import MOSSE_INIZIALI_PROTAGONISTA
from tests.combat_helpers import avvia_scontro

_MOTORE = Path(__file__).resolve().parents[1] / "src" / "motore"
_CONTENUTI = Path(__file__).resolve().parents[1] / "contenuti"


class _SpiaRng:
    """RNG che delega e CONTA: distingue "non ha pescato" da "ha pescato bene"."""

    def __init__(self, seed: int = 1) -> None:
        self._inner = random.Random(seed)
        self.pescate = 0

    def random(self) -> float:
        self.pescate += 1
        return self._inner.random()

    def choice(self, seq):
        self.pescate += 1
        return self._inner.choice(seq)

    def randrange(self, *a, **k):
        self.pescate += 1
        return self._inner.randrange(*a, **k)


def _effetti_azzardo(effetti) -> list:
    return [e for e in effetti if isinstance(e, EffettoAzzardo)]


# --- T1: il PERCORSO BASE non contiene azzardo --------------------------------

def test_T1_nessun_azzardo_nel_repertorio_di_default() -> None:
    """Il repertorio di chi non dichiara nulla, e quello iniziale del protagonista.

    Se una mossa d'azzardo finisse qui, *ogni* entità del gioco comincerebbe a pescare e
    la casualità opt-in diventerebbe il default — cioè esattamente la cosa che il
    modello a due check esiste per evitare."""
    for chiave in set(MOSSE_DEFAULT) | set(MOSSE_INIZIALI_PROTAGONISTA) | {"attacco"}:
        mossa = CATALOGO_MOSSE[chiave]
        assert not _effetti_azzardo(mossa.effetti), (
            f"la mossa di default '{chiave}' contiene un primitivo d'azzardo"
        )
        assert not mossa.azzardo, f"la mossa di default '{chiave}' si dichiara d'azzardo"


def test_T1_nessun_asset_pubblicato_porta_una_mossa_dazzardo() -> None:
    """Nemmeno dal contenuto: un archetipo o un mob che concedesse una mossa d'azzardo
    la metterebbe in mano a *ogni* sua istanza, in silenzio."""
    import json

    dazzardo = {k for k, m in CATALOGO_MOSSE.items() if m.azzardo}
    assert dazzardo, "nessuna mossa d'azzardo nel catalogo: il test non sta provando nulla"
    for percorso in (*_CONTENUTI.glob("archetipi/*.json"), *_CONTENUTI.glob("mob/*.json")):
        dati = json.loads(percorso.read_text(encoding="utf-8"))
        mosse = set(dati.get("mosse") or ())
        assert not (mosse & dazzardo), (
            f"{percorso.name} concede una mossa d'azzardo: l'opt-in deve restare una "
            "scelta del giocatore, non una dotazione del bestiario"
        )


def test_T1_la_mossa_dazzardo_esiste_ma_va_procurata(mondo_isolato: str) -> None:
    # Il contrappunto: l'azzardo ESISTE (altrimenti T1 sarebbe vero per vuoto), e ci si
    # arriva solo equipaggiando l'oggetto che lo concede.
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    assert "roulette_del_sistema" not in mosse_di(pent)

    dadi = Accessorio(
        fonte="dadi-truccati#1", sede=SedeAccessorio.DITA, nome="Dadi Truccati",
        mosse=("roulette_del_sistema",),
    )
    equipaggia(pent, dadi)
    assert "roulette_del_sistema" in mosse_di(pent), (
        "l'oggetto che gioca d'azzardo deve concedere la sua mossa (Gr2 §5.2)"
    )
    togli(pent, "dadi-truccati#1")
    assert "roulette_del_sistema" not in mosse_di(pent), (
        "sfilato l'oggetto, la mossa resta: è il bonus fantasma, versione skill"
    )


def test_T1_sfilare_loggetto_non_cancella_la_mossa_innata(mondo_isolato: str) -> None:
    """Regression (audit 2026-08-07): la revoca toglieva incondizionatamente — un
    accessorio che concede una mossa GIÀ innata se la portava via nello sfilarsi."""
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    innate = mosse_di(pent)
    assert innate, "protagonista senza mosse: il test non sta provando nulla"
    mossa = innate[0]
    anello = Accessorio(fonte="anello-eco", sede=SedeAccessorio.DITA, mosse=(mossa,))
    equipaggia(pent, anello)
    togli(pent, "anello-eco")
    assert mossa in mosse_di(pent), (
        "sfilare l'anello ha cancellato la mossa con cui il protagonista è NATO"
    )


def test_T1_due_oggetti_stessa_mossa_ne_basta_uno_indosso(mondo_isolato: str) -> None:
    """Il gemello del bonus fantasma: due oggetti concedono la stessa mossa, sfilarne
    UNO non deve revocarla finché l'altro resta al dito."""
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    for fonte in ("dadi-a", "dadi-b"):
        equipaggia(pent, Accessorio(
            fonte=fonte, sede=SedeAccessorio.DITA, mosse=("roulette_del_sistema",),
        ))
    togli(pent, "dadi-a")
    assert "roulette_del_sistema" in mosse_di(pent), (
        "il gemello è ancora indosso: la mossa non va revocata"
    )
    togli(pent, "dadi-b")
    assert "roulette_del_sistema" not in mosse_di(pent)


# --- T2: il risolutore pesca SOLO per il check 1 -------------------------------

def test_T2_uno_scontro_base_pesca_solo_per_il_check1(mondo_isolato: str) -> None:
    """Con la geometria di default tutti sono in auto-hit, quindi il check 1 non pesca:
    un colpo base deve costare **zero** estrazioni. Se questo numero cresce, qualcosa nel
    percorso base ha cominciato a tirare."""
    from motore import SpecNemico, stato_combattimento

    _bus, _adapter, _enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=1, punti_vita=50)],
        hp_prot=10_000, destrezza_prot=10,
    )

    _ent, stato = stato_combattimento()
    spia = _SpiaRng(1)
    stato.rng = spia

    sistema = SistemaTurnoCombattimento(_bus)
    prima = spia.pescate
    sistema.run(1)                                  # un turno completo
    dopo = spia.pescate

    # Le uniche pescate ammesse sono quelle della DECISIONE del nemico (bersaglio+mossa,
    # G-4) — mai del danno. Il check 1 in auto-hit non pesca.
    assert dopo - prima <= 2, (
        f"{dopo - prima} estrazioni in un turno base: il percorso base ha cominciato a "
        "pescare oltre il check 1"
    )


# --- T3: senza consenso non si pesca ------------------------------------------

def test_T3_senza_consenso_lazzardo_non_pesca(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    azione = Azione(
        sorgente=pent, bersaglio=pent,
        effetti=[DannoVariabile(minimo=5, massimo=5)],
    )
    assert azione.consenso_azzardo is False, "il consenso deve essere OFF di default"

    spia = _SpiaRng(1)
    sistema = SistemaTurnoCombattimento(bus=None)
    sistema._esegui_effetti(azione, type("S", (), {"rng": spia})())
    assert spia.pescate == 0, (
        "il risolutore ha pescato per un effetto d'azzardo senza consenso: 'pescare per "
        "default' dev'essere un percorso inesistente, non un caso gestito"
    )

    # Il gemello POSITIVO, senza il quale l'assert qui sopra passerebbe anche con un
    # dispatch rotto (zero pescate perché l'azzardo non è implementato affatto).
    class _BusMuto:
        def pubblica(self, _evento) -> None: ...

    consenziente = Azione(
        sorgente=pent, bersaglio=pent,
        effetti=[DannoVariabile(minimo=5, massimo=5)],
        consenso_azzardo=True,
    )
    spia2 = _SpiaRng(1)
    SistemaTurnoCombattimento(_BusMuto())._esegui_effetti(
        consenziente, type("S", (), {"rng": spia2})()
    )
    assert spia2.pescate == 1, (
        f"{spia2.pescate} estrazioni col consenso acceso: l'azzardo deve pescare "
        "ESATTAMENTE una volta per effetto"
    )


def test_T3_con_consenso_pesca_ed_e_riproducibile(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    effetto = DannoVariabile(minimo=1, massimo=20)

    a = risolvi_effetto_azzardo(effetto, pent, random.Random(7))
    b = risolvi_effetto_azzardo(effetto, pent, random.Random(7))
    assert a == b, "stesso seed, stesso esito: l'azzardo resta seeded (FNC §9)"
    assert 1 <= a <= 20


def test_T3_il_consenso_lo_accende_la_voce_di_catalogo(mondo_isolato: str) -> None:
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    base = azione_da_mossa("attacco", sorgente=pent, bersaglio=pent)
    azzardo = azione_da_mossa("roulette_del_sistema", sorgente=pent, bersaglio=pent)
    assert base.consenso_azzardo is False
    assert azzardo.consenso_azzardo is True


# --- T6: l'azzardo sostituisce la MAGNITUDINE, non il risolutore ---------------

def test_T6_lazzardo_paga_il_layer_dei_tipi(mondo_isolato: str) -> None:
    """Regression (audit 2026-08-07): il ramo `EffettoAzzardo` applicava il danno
    grezzo — il «dado di fuoco» bruciava anche l'ignifugo, e l'azzardo diventava
    strettamente dominante sul percorso base mitigato."""
    from contracts import TipoDanno
    from motore import PuntiVita, ResistenzaMod, applica_resistenza

    class _BusMuto:
        def pubblica(self, _evento) -> None: ...

    pent = crea_protagonista(destrezza=10, punti_vita=30)
    nudo = esper.create_entity(
        Primarie(valori={StatId.DESTREZZA: 1}), PuntiVita(attuali=100, massimi=100)
    )
    ignifugo = esper.create_entity(
        Primarie(valori={StatId.DESTREZZA: 1}), PuntiVita(attuali=100, massimi=100)
    )
    applica_resistenza(
        ignifugo, ResistenzaMod(contro=TipoDanno.FUOCO, valore=-50, fonte="pelle")
    )

    def _colpisci(bersaglio: int) -> int:
        azione = Azione(
            sorgente=pent, bersaglio=bersaglio,
            effetti=[DannoVariabile(minimo=10, massimo=10, tipo=TipoDanno.FUOCO)],
            consenso_azzardo=True,
        )
        prima = esper.component_for_entity(bersaglio, PuntiVita).attuali
        SistemaTurnoCombattimento(_BusMuto())._esegui_effetti(
            azione, type("S", (), {"rng": random.Random(3)})()
        )
        return prima - esper.component_for_entity(bersaglio, PuntiVita).attuali

    danno_nudo = _colpisci(nudo)
    danno_ignifugo = _colpisci(ignifugo)
    assert danno_nudo == 10, "senza resistenze la pescata passa intera"
    assert danno_ignifugo == 5, (
        f"−50 contro FUOCO deve dimezzare anche il dado: {danno_ignifugo} (atteso 5)"
    )


def test_T6_il_dodger_schiva_anche_i_dadi(mondo_isolato: str) -> None:
    """Il gemello del check 1: verso un bersaglio IN BANDA l'azzardo pesca due volte
    (il dado + il gate del colpo). Senza il gate, la mossa d'azzardo colpirebbe
    sempre — strettamente dominante proprio contro la build che il check 1 esiste
    per far vivere."""
    from motore import PuntiVita, check1
    from motore.corredo import Corredo

    class _BusMuto:
        def pubblica(self, _evento) -> None: ...

    pent = crea_protagonista(destrezza=10, punti_vita=30)
    dodger = esper.create_entity(
        Primarie(valori=dict(primarie_da_scalari(destrezza=100, punti_vita=100))),
        Corredo(armatura="veste", taglia="infima", arma="naturale"),
        PuntiVita(attuali=100, massimi=100),
    )
    spia = _SpiaRng(1)
    check1(pent, dodger, spia)
    assert spia.pescate == 1, "precondizione fallita: il bersaglio non è in banda"

    azione = Azione(
        sorgente=pent, bersaglio=dodger,
        effetti=[DannoVariabile(minimo=10, massimo=10)],
        consenso_azzardo=True,
    )
    spia2 = _SpiaRng(1)
    SistemaTurnoCombattimento(_BusMuto())._esegui_effetti(
        azione, type("S", (), {"rng": spia2})()
    )
    assert spia2.pescate == 2, (
        f"{spia2.pescate} pescate (attese 2: il dado + il check 1): l'azzardo verso "
        "un bersaglio in banda deve passare dal gate del colpo"
    )


# --- T4: la dipendenza è a senso unico ----------------------------------------

def test_T4_lazione_base_non_importa_lazzardo() -> None:
    """`azzardo` importa `azione`, mai il contrario: l'atomo base non può raggiungere
    l'azzardo nemmeno per un import distratto."""
    albero = ast.parse((_MOTORE / "azione.py").read_text(encoding="utf-8"))
    moduli = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.ImportFrom) and nodo.module:
            moduli.add(nodo.module)
        elif isinstance(nodo, ast.Import):
            moduli.update(a.name for a in nodo.names)
    assert not any("azzardo" in m for m in moduli), (
        "azione.py ha importato azzardo: la dipendenza dev'essere a senso unico"
    )
    assert "random" not in moduli, "l'atomo base non pesca e non deve conoscere `random`"


# --- T5: l'atomo base ha esattamente due primitivi ----------------------------

def test_T5_lo_stesso_atomo_base_resta_a_due_primitivi() -> None:
    """Le sottoclassi dirette di `Effetto` definite in `azione.py` sono `{Danno,
    ApplicaStatus}`. Un terzo primitivo lì dentro è una decisione di design (corsia 3),
    non un ritocco — e va presa di proposito, non scoperta."""
    albero = ast.parse((_MOTORE / "azione.py").read_text(encoding="utf-8"))
    figli = {
        n.name for n in ast.walk(albero)
        if isinstance(n, ast.ClassDef)
        and any(isinstance(b, ast.Name) and b.id == "Effetto" for b in n.bases)
    }
    assert figli == {"Danno", "ApplicaStatus"}, figli


def test_T5_i_primitivi_dazzardo_vivono_altrove() -> None:
    # …e il loro modulo NON definisce sottoclassi di `Danno`: sono un ramo
    # separato dell'albero degli effetti, non "il danno con una variante".
    albero = ast.parse((_MOTORE / "azzardo.py").read_text(encoding="utf-8"))
    basi = {
        b.id
        for n in ast.walk(albero) if isinstance(n, ast.ClassDef)
        for b in n.bases if isinstance(b, ast.Name)
    }
    assert "Danno" not in basi
    assert "EffettoAzzardo" in basi


# --- La Fortuna: il primo consumatore reale -----------------------------------

def test_la_fortuna_inclina_ma_non_garantisce(mondo_isolato: str) -> None:
    """Il bias esiste (la Fortuna era una stat inerte), ma è **cappato**: un azzardo che
    paga sempre non è un azzardo, è un moltiplicatore."""
    from motore.azzardo import bonus_fortuna
    from motore.calibrazione import FORTUNA_TETTO_BONUS

    sfortunato = esper.create_entity(
        Primarie(valori={**primarie_da_scalari(destrezza=1, punti_vita=1), StatId.FORTUNA: 1})
    )
    baciato = esper.create_entity(
        Primarie(valori={**primarie_da_scalari(destrezza=1, punti_vita=1), StatId.FORTUNA: 999})
    )
    assert bonus_fortuna(sfortunato) < bonus_fortuna(baciato)
    assert bonus_fortuna(baciato) <= FORTUNA_TETTO_BONUS


def test_la_tabella_dazzardo_puo_ritorcersi(mondo_isolato: str) -> None:
    """Il segno dice CHI incassa: negativo = chi ha tirato. Una tabella che non può mai
    ferire chi la usa non è una scommessa."""
    esiti = (EsitoAzzardo("il banco vince", -5), EsitoAzzardo("colpo pieno", 20))
    tiro = TiroAzzardo(esiti=esiti)
    pent = crea_protagonista(destrezza=10, punti_vita=30)
    visti = {risolvi_effetto_azzardo(tiro, pent, random.Random(s)) for s in range(30)}
    assert any(v < 0 for v in visti), "nessuna faccia sfavorevole in 30 pescate"
    assert any(v > 0 for v in visti)


def test_una_tabella_vuota_e_un_errore_non_un_silenzio() -> None:
    with pytest.raises(ValueError):
        risolvi_effetto_azzardo(TiroAzzardo(esiti=()), 1, random.Random(1))
