"""Il dodger IN PARTITA: la schivata smette di essere teoria (check 1, Gr2 §6).

Fino a qui il check 1 era codice vivo ma **inerte**: ogni entità del gioco aveva la
stessa geometria (`veste/media/naturale`), quindi `eva_eff ≈ 0.1` contro una banda che
si apre a `≈4.33` — auto-hit sempre, per tutti. Schivata e graze esistevano solo nei
property-test su scalari sintetici.

L'archetipo `felino` è la prima entità **di contenuto** che entra in banda: taglia
infima, nessuna armatura, Destrezza alta. Questi test lo verificano dove conta, cioè
in una partita vera giocata via porte.

Le due metà, entrambe necessarie:
  - **positiva** — contro il dodger si manca e si colpisce di striscio;
  - **negativa (guardia gemella)** — contro un mob ordinario le pescate del check 1
    sono ZERO. Senza questa, un `K_EVA` gonfiato renderebbe schivante tutto il
    bestiario e il test positivo continuerebbe a passare, felice.

⚠️ Il dodger NON va aggiunto al parametrize di `test_ttk.py`: richiede legittimamente
più colpi (perché li si manca), e sfonderebbe la banda 2-8 per la ragione sbagliata.
Banda propria, test proprio.
"""

from __future__ import annotations

import asyncio
import random

import esper

from contracts import (
    BudgetDesign,
    ColpoInferto,
    Grado,
    MobAsset,
    PianoRisolto,
    PlayerChoseOption,
    StagioneRisolta,
)
from main import costruisci_sessione
from motore import Primarie, acc_eff, check1, crea_protagonista, eva_eff
from motore import calibrazione as cal
from motore.calibrazione import primarie_da_archetipo
from motore.corredo import Corredo
from motore.design import archetipo_attivo

_DODGER = "felino"
_ORDINARIO = "slime"


def _stagione_con(archetipo: str, grado: Grado) -> StagioneRisolta:
    """Un piano di prova con un solo mob, ma con gli **archetipi risolti veri**.

    Li risolve per la STESSA strada di `risolvi_stagione` (merge con la
    calibrazione per gli storici, profilo dall'asset di libreria per il
    `felino`): è il punto del test — la schivata dev'essere raggiungibile dal
    CONTENUTO del repo, non da un profilo cucito su misura qui dentro."""
    from tests.contenuti_sintetici import archetipi_sintetici

    mob = MobAsset(
        slug="bersaglio", nome="Bersaglio", archetipo=archetipo, grado=grado,
        prosa_stanza="Qualcosa ti squadra dal buio.",
    )
    piano = PianoRisolto(
        slug="p", versione=1, titolo="Prova", tema="dodge",
        budget=BudgetDesign(gradi=[grado], blocchi=[], archetipi=[archetipo]),
        cast=[mob],
    )
    return StagioneRisolta(
        slug="s-dodge", versione=1, numero=1, titolo="Dodge", mondo="X",
        piani=[piano],
        archetipi=archetipi_sintetici(("slime", "scheletro", "goblin", "felino")),
    )


def _indice(snap, etichetta: str) -> int:
    return next(
        o.indice for o in snap.opzioni
        if o.etichetta == etichetta or o.etichetta.startswith(etichetta + " —")
    )


class _SpiaRng:
    """RNG che DELEGA e conta: serve a distinguere "non ha pescato" da "ha pescato e
    ha avuto fortuna" — che è tutta la differenza fra auto-hit e schivata."""

    def __init__(self, seed: int) -> None:
        self._inner = random.Random(seed)
        self.pescate = 0

    def random(self) -> float:
        self.pescate += 1
        return self._inner.random()


def _entita_da_asset(archetipo: str, grado: Grado) -> int:
    """Un'entità con le stat e la geometria che il CONTENUTO le assegna (non scalari
    inventati dal test): è il punto — la schivata dev'essere raggiungibile dagli asset."""
    att = archetipo_attivo(archetipo)
    profilo = att.profilo
    return esper.create_entity(
        Primarie(valori=primarie_da_archetipo(archetipo, grado, 1, profilo=profilo)),
        Corredo(armatura=profilo.armatura, taglia=profilo.taglia, arma=profilo.arma),
    )


# --- 1. La geometria del dodger arriva dagli ASSET ----------------------------

def test_larchetipo_dodger_esiste_ed_e_fatto_per_schivare(run_pulita, tmp_path) -> None:
    costruisci_sessione(nome="D", seed=1, directory=tmp_path,
                        stagione=_stagione_con(_DODGER, Grado.ARGENTO))
    profilo = archetipo_attivo(_DODGER).profilo
    assert profilo.taglia == "infima", "un dodger grosso non schiva: m_taglia lo azzera"
    assert profilo.armatura == "veste", "con l'armatura addosso coeff_eva crolla"
    assert profilo.pv_base < cal.REGISTRY_ARCHETIPI[_ORDINARIO].pv_base, (
        "il dodger paga la schivata in HP: se fosse anche robusto sarebbe solo migliore"
    )


def test_il_dodger_entra_in_banda_lordinario_no(run_pulita, tmp_path) -> None:
    """Le due metà del vincolo, sulle entità che il contenuto produce davvero."""
    costruisci_sessione(nome="D", seed=1, directory=tmp_path,
                        stagione=_stagione_con(_DODGER, Grado.ARGENTO))
    carl = crea_protagonista(destrezza=10, punti_vita=30)
    dodger = _entita_da_asset(_DODGER, Grado.ARGENTO)
    ordinario = _entita_da_asset(_ORDINARIO, Grado.ARGENTO)

    acc = acc_eff(carl)
    soglia = acc / cal.F_AUTOHIT
    assert eva_eff(dodger) >= soglia, (
        f"il dodger di contenuto non arriva alla banda (eva={eva_eff(dodger):.2f} < "
        f"{soglia:.2f}): il check 1 resta codice morto in partita"
    )
    assert eva_eff(ordinario) < soglia, (
        "un mob ordinario è entrato in banda: K_EVA è troppo alto e il TTK tarato salta"
    )


# --- 2. In partita: contro il dodger si manca ---------------------------------

def test_contro_il_dodger_si_manca_e_si_colpisce_di_striscio(run_pulita, tmp_path) -> None:
    """Il test che dice se tutto il lavoro è servito: in una partita vera, i colpi
    andati a segno sono MENO degli attacchi tentati, e fra quelli ce n'è di parziali."""
    sessione = costruisci_sessione(
        nome="D", seed=7, directory=tmp_path,
        stagione=_stagione_con(_DODGER, Grado.ARGENTO),
    )
    colpi: list[ColpoInferto] = []
    sessione.bus.registra(ColpoInferto, colpi.append)
    try:
        snap = asyncio.run(sessione.prossima_narrazione())
        sessione.coda.accoda(PlayerChoseOption(_indice(snap, "Combatti")))
        snap = sessione.avanza()

        attacchi = 0
        while snap.fase == "combattimento" and attacchi < 40:
            sessione.coda.accoda(PlayerChoseOption(_indice(snap, "Attacca")))
            snap = sessione.avanza()
            attacchi += 1

        miei = [c for c in colpi if c.attaccante == ""]
        assert miei, "nessun colpo a segno: il dodger è diventato intoccabile"
        assert len(miei) < attacchi, (
            f"{len(miei)} colpi su {attacchi} attacchi: nessuna schivata. Il check 1 non "
            "sta pescando nemmeno contro un'entità costruita per evitarlo"
        )
        # NB: il **graze** non si verifica qui. Un dodger fragile muore in pochi colpi,
        # quindi una partita offre una manciata di campioni: pretendere di vederci un
        # esito a bassa probabilità sarebbe fragilità travestita da rigore — il test
        # diventerebbe rosso al primo ritocco di `pv_base`, per una ragione che non
        # c'entra nulla con ciò che sta misurando. L'esito a tre vie ha il suo lucchetto
        # in `test_contro_il_dodger_il_check1_pesca`, su 200 estrazioni.
    finally:
        sessione.bus.deregistra(ColpoInferto, colpi.append)


# --- 3. La guardia gemella: contro un ordinario NON si pesca -------------------

def test_contro_un_mob_ordinario_il_check1_non_pesca_mai(run_pulita, tmp_path) -> None:
    """Se questo va rosso, qualcuno ha reso schivante tutto il bestiario.

    È la metà che si dimentica: un `K_EVA` gonfiato farebbe passare il test positivo
    qui sopra e romperebbe in silenzio ogni TTK tarato."""
    costruisci_sessione(nome="D", seed=1, directory=tmp_path,
                        stagione=_stagione_con(_ORDINARIO, Grado.ARGENTO))
    carl = crea_protagonista(destrezza=10, punti_vita=30)
    ordinario = _entita_da_asset(_ORDINARIO, Grado.ARGENTO)

    spia = _SpiaRng(1)
    for _ in range(50):
        assert check1(carl, ordinario, spia) == 1.0     # colpo pieno, deterministico
    assert spia.pescate == 0, (
        f"il check 1 ha pescato {spia.pescate} volte contro un mob ordinario: sotto la "
        "banda deve essere auto-hit DETERMINISTICO, zero estrazioni"
    )


def test_contro_il_dodger_il_check1_pesca(run_pulita, tmp_path) -> None:
    """Il gemello positivo, sullo stesso strumento: qui lo stream si muove."""
    costruisci_sessione(nome="D", seed=1, directory=tmp_path,
                        stagione=_stagione_con(_DODGER, Grado.ARGENTO))
    carl = crea_protagonista(destrezza=10, punti_vita=30)
    dodger = _entita_da_asset(_DODGER, Grado.ARGENTO)

    spia = _SpiaRng(1)
    esiti = {check1(carl, dodger, spia) for _ in range(200)}
    assert spia.pescate == 200, "in banda si pesca UNA volta per colpo, sempre"
    assert 0.0 in esiti, "nessuna schivata piena in 200 colpi"
    assert cal.G_GRAZE in esiti, "nessun graze in 200 colpi: l'esito non è a tre vie"


# --- 4. La fuga premia l'agilità ----------------------------------------------

def test_il_dodger_scappa_meglio(run_pulita, tmp_path) -> None:
    """La Destrezza che serve a schivare serve anche a sganciarsi: la fuga pulita è
    roba da build agile (F2), e il dodger è esattamente quella build."""
    from contracts import ClasseProva
    from motore import margine_prova
    from motore.calibrazione import MARGINE_FUGA_PULITA, PRIMARIE_BASE_CARL
    from contracts import StatId

    costruisci_sessione(nome="D", seed=1, directory=tmp_path,
                        stagione=_stagione_con(_DODGER, Grado.ARGENTO))
    profilo = archetipo_attivo(_DODGER).profilo

    margine_carl = margine_prova(PRIMARIE_BASE_CARL[StatId.DESTREZZA], ClasseProva.BRONZO)
    margine_dodger = margine_prova(profilo.destrezza_base, ClasseProva.BRONZO)
    assert margine_carl < MARGINE_FUGA_PULITA <= margine_dodger, (
        f"Carl {margine_carl}, dodger {margine_dodger}, soglia pulita {MARGINE_FUGA_PULITA}: "
        "la ritirata gratuita deve distinguere chi è agile da chi non lo è"
    )
