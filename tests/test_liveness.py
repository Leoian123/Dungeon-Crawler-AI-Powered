"""Le due liveness di release (gate del nodo A): G-L1 (ogni scontro termina) e G-L2
(ogni piano è completabile). Senza entrambe verdi, "giocabile capo-a-fine" non è vero
(G §3, §8.4). Headless, seeded.
"""

from __future__ import annotations

import random

import esper
import pytest

from contracts import CombatResolved, Grado, MortePersonaggio
from motore.calibrazione import R_SOGLIA_CROLLO
from motore import (
    DANNO_BASE,
    OndataRinforzi,
    Piano,
    PianoRinforzi,
    Rigenerazione,
    SpecNemico,
    applica_status,
    piano_completabile,
    protagonista,
    raggiungibili,
    tick,
    valida_piano,
)
from tests.combat_helpers import avvia_scontro


# ============================================================================
# G-L1 — Ogni scontro TERMINA (garanzia di fine, verifica (a) + rete (b))
# ============================================================================
#
# Con gli status EFFETTIVI (la rigenerazione CURA) la garanzia (a) "monotònia degli
# HP" non regge più da sola: la terminazione è garantita PER COSTRUZIONE dalla rete
# (b), l'escalation `SistemaCrollo` (attiva nell'MVP, registrata in produzione): il
# danno inevitabile cresce lineare, bypassa il risolutore e supera qualunque
# sostentamento in un numero limitato di round (aritmetica monotòna). I rinforzi
# restano **finiti** (ogni ondata rilasciata una volta).


def test_GL1_danno_base_positivo_garantisce_progresso() -> None:
    # Il cardine di (a): ogni colpo fa progredire lo stato (HP che scende). Con
    # DANNO_BASE = 0 lo scontro potrebbe stallare; qui è > 0 per costruzione.
    assert DANNO_BASE > 0


@pytest.mark.parametrize("hp_nemico", [1, 5, 20, 100])
def test_GL1_scontro_termina_entro_un_bound(mondo_isolato: str, hp_nemico: int) -> None:
    # Protagonista robusto e veloce → vince; lo scontro chiude entro ~2·HP turni (due
    # combattenti che si alternano). Il bound dimostra che NON cicla all'infinito.
    _bus, adapter, _enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=5, punti_vita=hp_nemico)],
        hp_prot=10**9, destrezza_prot=100,
    )
    bound = 2 * hp_nemico + 20
    for _ in range(bound):
        tick()
        if adapter.events_of(CombatResolved):
            break
    risolti = adapter.events_of(CombatResolved)
    assert risolti, f"scontro non terminato entro {bound} turni (possibile stallo)"
    assert risolti[0].vittoria is True


def test_GL1_scontro_termina_anche_in_morte(mondo_isolato: str) -> None:
    # Anche il ramo opposto termina: nemico inarrestabile → MortePersonaggio entro un
    # bound (gli HP del protagonista scendono di ≥1 per turno del nemico).
    _bus, adapter, _enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=100, punti_vita=10**9)],
        hp_prot=30, destrezza_prot=1,
    )
    for _ in range(30 * 2 + 20):
        tick()
        if adapter.events_of(MortePersonaggio):
            break
    assert adapter.events_of(MortePersonaggio), "morte non raggiunta: scontro non terminante"


def test_GL1_sostentamento_non_stalla_grazie_al_crollo(mondo_isolato: str) -> None:
    # La rigenerazione ora CURA (feel MVP): un build con sostentamento ≥ danno è
    # possibile — la garanzia di terminazione non è più "niente cure" ma la rete
    # PER COSTRUZIONE dell'escalation (SistemaCrollo, G-L1): il danno inevitabile
    # cresce lineare e supera qualunque rigenerazione in round limitati.
    _bus, adapter, _enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=5, punti_vita=10**9)],
        hp_prot=60, destrezza_prot=1,
    )
    pent, _marker, _scheda = protagonista()
    applica_status(pent, Rigenerazione(rango=9, durata=10**9))  # "build sostentamento"

    for _ in range(2 * (R_SOGLIA_CROLLO + 200)):
        tick()
        if adapter.events_of(MortePersonaggio):
            break
    assert adapter.events_of(MortePersonaggio), (
        "lo scontro col build-sostentamento non è terminato: il crollo non morde (G-L1)"
    )


def test_GL1_rinforzi_sono_finiti(mondo_isolato: str) -> None:
    # I rinforzi (binario di mutazione §5) sono BOUNDED: ogni ondata è rilasciata una
    # sola volta → niente ondate infinite (la sorgente di non-terminazione di §5.4).
    # Nemico iniziale tosto abbastanza da raggiungere il round 1 (quando l'ondata esce):
    # col danno deterministico 2b (atk_eff−def_eff/100), deve sopravvivere al primo colpo
    # del protagonista, quindi HP > danno-per-colpo (ex `punti_vita=8`, tarato su DANNO_BASE=1).
    _bus, adapter, enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=5, punti_vita=80)],
        hp_prot=10**9, destrezza_prot=100,
    )
    esper.add_component(
        enc, PianoRinforzi(ondate=[OndataRinforzi(round_trigger=1, nemici=[SpecNemico(destrezza=5, punti_vita=1)])])
    )
    for _ in range(200):
        tick()
        if adapter.events_of(CombatResolved):
            break
    piano = esper.component_for_entity(enc, PianoRinforzi)
    assert piano.rilasciate == {0}, "l'ondata deve uscire UNA volta sola (niente rinforzi infiniti)"
    assert adapter.events_of(CombatResolved), "scontro con rinforzi finiti deve comunque terminare"


# ============================================================================
# G-L2 — Ogni piano è COMPLETABILE (almeno una DiscesaPiano raggiungibile)
# ============================================================================
#
# Il gate di contenuto (`valida_piano`) NON lascia passare un piano senza uscita: lo
# **ripara** (piazza una DiscesaPiano in una stanza raggiungibile) o lo **rifiuta**
# (G-18, §8.4). È la gemella di G-L1: G-L1 chiude lo scontro, G-L2 chiude il piano.


def test_GL2_piano_riparato_e_sempre_completabile() -> None:
    # Un piano senza uscita raggiungibile viene riparato: dopo `valida_piano` è
    # SEMPRE completabile (esiste una DiscesaPiano nelle stanze raggiungibili).
    piano = Piano(partenza=0, adiacenze={0: [1], 1: [0, 2], 2: [1]}, discese=set())
    assert not piano_completabile(piano)
    riparato = valida_piano(piano, ripara=True)
    assert riparato is not None and piano_completabile(riparato)
    assert any(d in raggiungibili(riparato) for d in riparato.discese)


def test_GL2_gate_rifiuta_un_piano_senza_uscita() -> None:
    piano = Piano(partenza=0, adiacenze={0: [1], 1: [0]}, discese={9})  # 9 irraggiungibile
    assert valida_piano(piano, ripara=False) is None  # rifiutato, non lasciato passare


@pytest.mark.parametrize("seed", range(25))
def test_GL2_qualunque_topologia_diventa_completabile(seed: int) -> None:
    # Property test: su topologie casuali, il gate (ripara=True) garantisce SEMPRE la
    # completabilità — nessun piano resta invincibile (liveness dell'esplorazione).
    rng = random.Random(seed)
    n = rng.randint(1, 8)
    adiacenze: dict[int, list[int]] = {i: [] for i in range(n)}
    for a in range(n):
        for b in range(n):
            if a != b and rng.random() < 0.35:
                adiacenze[a].append(b)
    discese = {rng.randrange(n)} if rng.random() < 0.4 else set()
    piano = Piano(partenza=0, adiacenze=adiacenze, discese=discese)

    riparato = valida_piano(piano, ripara=True)
    assert riparato is not None
    assert piano_completabile(riparato), f"topologia seed={seed} non completabile dopo il gate"
    assert any(d in raggiungibili(riparato) for d in riparato.discese)


# --- G-L2 sul CONTENUTO: ogni piano della stagione, non solo topologie sintetiche ---
#
# I test qui sopra dimostrano che il *gate* ripara qualunque topologia. Restava
# scoperto il passo successivo: che ogni piano **realmente pubblicato** produca una
# mappa completabile alla scala che il suo cast impone. Con una stagione a un piano
# solo la distinzione era accademica; con due (o più) non lo è più.

def test_GL2_ogni_piano_della_stagione_e_completabile() -> None:
    """Per OGNI piano della stagione ufficiale, alla sua scala, la topologia generata
    ha una `DiscesaPiano` raggiungibile. Se un piano nuovo entra nella libreria con una
    scala che il generatore non regge, è qui che si scopre — non giocando."""
    from main import risolvi_stagione
    from motore import genera_topologia

    stagione = risolvi_stagione("stagione-1")
    assert len(stagione.piani) >= 2, "il multi-piano dev'essere esercitato, non ipotizzato"
    for livello, piano in enumerate(stagione.piani, start=1):
        topologia = genera_topologia(random.Random(f"seed:{livello}"), piano.n_stanze)
        assert piano_completabile(topologia), (
            f"piano {livello} ({piano.slug}, {piano.n_stanze} stanze): nessuna scala "
            "raggiungibile"
        )
        assert any(d in raggiungibili(topologia) for d in topologia.discese)


def test_GL2_la_mappa_rigenerata_alla_discesa_e_completabile(mondo_isolato: str) -> None:
    """Scendere produce una mappa NUOVA, e anche quella deve avere un'uscita.

    Senza rigenerazione il piano 2 riuserebbe la topologia del piano 1 — comprese le
    stanze già visitate e la scala già usata — e "scendere" sarebbe un contatore che
    sale su una mappa ferma."""
    from motore import crea_mappa, crea_seme, mappa_corrente, rigenera_mappa

    crea_seme(7)
    crea_mappa(random.Random(7), 5)
    _ent, prima = mappa_corrente()

    rigenera_mappa(2, 4)
    trovata = mappa_corrente()
    assert trovata is not None
    _ent2, dopo = trovata
    assert len(esper.get_component(type(dopo))) == 1, "due mappe = due verità spaziali"
    assert piano_completabile(dopo.piano)
    assert dopo.stanza_corrente == dopo.piano.partenza, "si arriva in cima al piano nuovo"
    assert not dopo.visitate, "il piano nuovo non può nascere già esplorato"
    assert len(dopo.piano.adiacenze) == 4 and len(prima.piano.adiacenze) == 5


# --- G-L1 sulla MATRICE COMPLETA: ogni archetipo × ogni grado, anche impari ---------
#
# ⚠️ La distinzione che rende questo test possibile: **G-L1 è «ogni scontro termina»,
# non «il protagonista vince ogni scontro»**. Un mob celestiale che uccide un
# protagonista nudo *è* una terminazione — è permadeath, il terminale di run previsto
# (G-11). Confonderle porterebbe a tarare il gioco perché Carl vinca sempre, che è un
# gioco diverso.
#
# Perciò i due lucchetti sono separati e misurano cose diverse:
#   - **qui** (universale, debole): lo scontro CHIUDE, comunque vada, per ogni
#     combinazione — è il gate di release;
#   - **`test_ttk.py`** (per-profilo, forte): chiude nella banda 2-8 colpi *a parità di
#     corredo atteso*, ed è il lucchetto del feel.

@pytest.mark.parametrize("archetipo", ["slime", "scheletro", "goblin", "felino"])
@pytest.mark.parametrize("grado", list(Grado))
def test_GL1_ogni_archetipo_per_ogni_grado_termina(
    run_pulita, tmp_path, archetipo: str, grado: Grado
) -> None:
    """Protagonista NUDO contro l'intera matrice: nessuno scontro resta aperto.

    Nudo di proposito — è il caso peggiore, quello in cui il giocatore non ha il
    corredo che il grado richiederebbe. Se anche lì si chiude (vincendo, fuggendo o
    morendo), G-L1 vale ovunque."""
    import asyncio

    from contracts import BudgetDesign, CombatResolved, MobAsset, MortePersonaggio
    from contracts import PianoRisolto, PlayerChoseOption, StagioneRisolta
    from main import costruisci_sessione, risolvi_stagione

    ufficiale = risolvi_stagione("stagione-1")
    mob = MobAsset(slug="bersaglio", nome="Bersaglio", archetipo=archetipo, grado=grado,
                   prosa_stanza="Una sagoma ti squadra.")
    piano = PianoRisolto(
        slug="p", versione=1, titolo="GL1", tema="liveness",
        budget=BudgetDesign(gradi=[grado], blocchi=[], archetipi=[archetipo]), cast=[mob],
    )
    stagione = StagioneRisolta(
        slug="s-gl1", versione=1, numero=1, titolo="GL1", mondo="X",
        piani=[piano], archetipi=list(ufficiale.archetipi),
    )
    sessione = costruisci_sessione(nome="Nudo", seed=5, directory=tmp_path, stagione=stagione)

    terminali: list[object] = []
    for tipo in (CombatResolved, MortePersonaggio):
        sessione.bus.registra(tipo, terminali.append)
    try:
        snap = asyncio.run(sessione.prossima_narrazione())
        snap, _ = _clicca(sessione, snap, "Combatti")
        turni = 0
        while snap.fase == "combattimento" and turni < 200:
            snap, agito = _clicca(sessione, snap, "Attacca")
            if not agito:
                # Il menu non offre più di attaccare: il protagonista è morto (o lo
                # scontro si è chiuso). Non è uno stallo — è un terminale, ed è ciò che
                # G-L1 chiede. Continuare a "cliccare" a vuoto conterebbe turni finti.
                break
            turni += 1
        assert turni < 200, (
            f"{archetipo}/{grado.value}: scontro ancora aperto dopo 200 turni — G-L1 "
            "violato (nessun terminale, né vittoria né morte)"
        )
        assert terminali, f"{archetipo}/{grado.value}: chiuso senza pubblicare un terminale"
    finally:
        for tipo in (CombatResolved, MortePersonaggio):
            sessione.bus.deregistra(tipo, terminali.append)


def _clicca(sessione, snap, etichetta: str):
    from contracts import PlayerChoseOption

    voce = next(
        (o.indice for o in snap.opzioni
         if o.etichetta == etichetta or o.etichetta.startswith(etichetta + " —")),
        None,
    )
    if voce is None:                     # il protagonista è morto: il menu è cambiato
        return snap, False
    sessione.coda.accoda(PlayerChoseOption(voce))
    return sessione.avanza(), True
