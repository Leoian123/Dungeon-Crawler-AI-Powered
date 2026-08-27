"""Sit.5 (Fase 8): il sistema degli incontri — l'imboscata cucita al dado-evento.

Il dado girava già (seeded, mai orologio): qui si prova il COMPOSITORE
(`componi_imboscata_scena`), le cuciture (spendi_tempo/riposo) e l'host che apre
l'istanza su un `EncounterStarted` non suo.
"""

from __future__ import annotations

import asyncio
import random

import esper

from contracts import EncounterStarted, PlayerChoseOption
from motore import (
    Fase,
    SistemaTempoPiano,
    avvia_run,
    componi_imboscata_scena,
    crea_mappa,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_tempo_piano,
    fast_forward,
    nome_nemico_incontro,
    riposa,
)
from motore import tempo as tempo_mod
from motore.combattimento import PianoIncontro
from motore.mob import EntitaMob
from main import costruisci_sessione


def _arma_run(seed: int = 7) -> None:
    from motore import segna_visitata

    crea_profondita()
    crea_seme(seed)
    crea_tempo_piano()
    crea_mappa(random.Random(seed))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    avvia_run(crea_singleton_fase=True, fase_iniziale=Fase.NARRAZIONE,
              sempre_attivi=[SistemaTempoPiano()])
    # La stanza si RIVELA prima di qualunque downtime (pacing 2026-08-26: il
    # dado-imboscata tace nella stanza non ancora rivelata) e la TREGUA di
    # reveal si consuma subito: qui si testa il dado libero, non il pacing.
    segna_visitata()
    from motore.mappa import consuma_tregua_reveal

    consuma_tregua_reveal()


class _Bus:
    """Bus minimo per i test di composizione (registra/pubblica)."""

    def __init__(self) -> None:
        self.eventi: list[object] = []

    def pubblica(self, evento) -> None:
        self.eventi.append(evento)


def test_compositore_deterministico_e_isolato(mondo_isolato) -> None:
    """Stesso seed + stesso tick → stesso agguato; lo stream RNG di sessione non
    si muove (il compositore non lo riceve nemmeno)."""
    _arma_run()
    a = componi_imboscata_scena()
    b = componi_imboscata_scena()
    pa, pb = esper.component_for_entity(a, PianoIncontro), esper.component_for_entity(b, PianoIncontro)
    assert pa.seed == pb.seed and pa.arruolate and pb.arruolate
    ma = esper.component_for_entity(pa.arruolate[0], EntitaMob)
    mb = esper.component_for_entity(pb.arruolate[0], EntitaMob)
    assert (ma.archetipo, ma.grado, ma.nome) == (mb.archetipo, mb.grado, mb.nome)
    assert nome_nemico_incontro(a) == ma.nome


def test_l_imboscata_non_pesca_il_mob_di_stanza(mondo_isolato) -> None:
    """Screenshot 2026-08-26: l'agguato all'ingresso pescava lo stesso nome del
    mob che PRESIDIA la stanza — il GM diceva «non si rialza» e il menu
    rioffriva Combatti con lo stesso Fante (un morto apparentemente risorto).
    Con l'esclusione: su molti tick campionati, l'imboscata non porta MAI il
    nome del presidiante quando la tabella ha alternative."""
    from motore import avvia_territorio, mob_di_stanza, zona_corrente
    from motore.mappa import mappa_corrente
    from motore.piano import TempoPiano, livello_corrente
    from main import _stagione_a_attiva
    from motore import crea_stagione
    from tests.contenuti_sintetici import piano_territoriale, stagione_sintetica

    crea_profondita()
    crea_seme(7)
    crea_tempo_piano()
    crea_stagione(_stagione_a_attiva(stagione_sintetica(
        piani=[piano_territoriale(1)], slug="s-agguato",
    )))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    avvia_territorio(1)

    m = mappa_corrente()[1]
    presidiante = mob_di_stanza(
        livello_corrente(), zona_corrente(), m.stanza_corrente
    )
    assert presidiante is not None, "l'harness territoriale deve avere il copione"

    tempo = esper.get_component(TempoPiano)[0][1]
    nomi_agguato = set()
    for tick in range(24):
        tempo.tick = tick  # stream d'imboscata diverso per ogni tick
        incontro = componi_imboscata_scena()
        nomi_agguato.add(nome_nemico_incontro(incontro))
    assert len(nomi_agguato) > 1, (
        "campione degenere: la tabella sintetica deve avere alternative"
    )
    assert presidiante.nome not in nomi_agguato, (
        "l'imboscata non deve mai avere il nome del mob che presidia la stanza"
    )


def test_fast_forward_innesca_l_imboscata(mondo_isolato, monkeypatch) -> None:
    _arma_run()
    monkeypatch.setattr(tempo_mod, "PROB_IMBOSCATA", 1.0)
    from motore import mappa as mappa_mod

    monkeypatch.setattr(mappa_mod, "fattore_minacce", lambda: 1.0)  # dado FORZATO
    bus = _Bus()
    from contracts import Durata

    esito = fast_forward(bus, Durata.UN_BEL_PO, componi_imboscata=componi_imboscata_scena)
    assert esito.interrotto_da == "imboscata"
    assert esito.tick_eseguiti == 1  # interrotto al primo tick: i tick restanti non si spendono
    eventi = [e for e in bus.eventi if isinstance(e, EncounterStarted)]
    assert len(eventi) == 1 and eventi[0].imboscata is True
    assert esper.component_for_entity(eventi[0].entita, PianoIncontro).arruolate
    # L'incontro risale al chiamante (round 3): è il dato con cui il turno GM
    # cuce il segnaposto d'agguato sulla prosa.
    assert esito.incontro == eventi[0].entita


def test_riposo_interrotto_recupero_parziale(mondo_isolato, monkeypatch) -> None:
    _arma_run()
    monkeypatch.setattr(tempo_mod, "PROB_IMBOSCATA", 1.0)
    from motore import mappa as mappa_mod

    monkeypatch.setattr(mappa_mod, "fattore_minacce", lambda: 1.0)  # dado FORZATO
    pent, _m, scheda = (None, None, None)
    from motore import protagonista

    pent, _m, scheda = protagonista()
    scheda.punti_vita = 10  # ferito: il riposo avrebbe molto da recuperare
    evento = riposa(_Bus())
    assert evento is not None and evento.interrotto is True
    assert evento.tick_spesi == 1  # solo il tick reale prima dell'agguato


def test_sessione_apre_l_istanza_sull_imboscata(run_pulita, monkeypatch) -> None:
    """E2E: un'azione lunga innesca l'imboscata a metà pipeline — al ritorno la
    fase è combattimento, l'istanza è viva col nome del nemico, la cronaca dice
    «Imboscata!» e l'apertura sa di agguato."""
    monkeypatch.setattr(tempo_mod, "PROB_IMBOSCATA", 1.0)
    sessione = costruisci_sessione(seed=1)
    asyncio.run(sessione.prossima_narrazione())
    riep = sessione.riepiloga_azione("monto la guardia per mezz'ora")
    snap = asyncio.run(sessione.esegui_azione(riep))
    assert snap.fase == "combattimento"
    assert sessione._istanza is not None
    assert sessione._imboscata_in_corso is True
    assert sessione._istanza.nemico  # il nome viene dall'incontro composto
    # Il menu è quello di scontro (mosse + Fuggi in coda).
    assert snap.opzioni and snap.opzioni[-1].etichetta == "Fuggi"
    # E l'apertura racconta l'agguato (flag della sessione, non del chiamante).
    from provider import FakeProvider

    fake = FakeProvider([dict(testo="!")])
    sessione.provider = fake
    asyncio.run(sessione.prosa_apertura_scontro())
    assert "agguato" in fake.prompt_ricevuti[0]


def test_ingaggio_ordinario_non_e_imboscata(run_pulita) -> None:
    sessione = costruisci_sessione(seed=1)
    asyncio.run(sessione.prossima_narrazione())
    sessione.coda.accoda(PlayerChoseOption(0))  # Combatti
    snap = sessione.avanza()
    assert snap.fase == "combattimento"
    assert sessione._imboscata_in_corso is False
