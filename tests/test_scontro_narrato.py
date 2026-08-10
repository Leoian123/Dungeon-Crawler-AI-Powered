"""Sit.1 + Probl.3 (Fase 5b): le porte narrate dello scontro sulla sessione —
apertura (trailer al tasto Combatti) ed epitaffio (permadeath). Entrambe
non-gating: degradano a None e la cronaca deterministica resta il feedback base.
"""

from __future__ import annotations

import asyncio

from contracts import FattiScontro, PlayerChoseOption
from main import costruisci_sessione
from provider import FakeProvider


def _sessione_in_scontro():
    sessione = costruisci_sessione(seed=1)
    asyncio.run(sessione.prossima_narrazione())
    sessione.coda.accoda(PlayerChoseOption(0))  # Combatti
    snap = sessione.avanza()
    assert snap.fase == "combattimento"
    return sessione


def test_apertura_scontro_veste_il_trailer(run_pulita) -> None:
    sessione = _sessione_in_scontro()
    # Il provider si sostituisce al volo: la porta avvolge il provider CORRENTE.
    fake = FakeProvider([dict(testo="il trailer d'apertura")])
    sessione.provider = fake
    testo = asyncio.run(sessione.prosa_apertura_scontro())
    assert testo == "il trailer d'apertura"
    # Il prompt porta il nemico della scena e nessun esito predeciso.
    prompt = fake.prompt_ricevuti[0]
    assert "[scena]" in prompt and "combattere" in prompt


def test_apertura_scontro_degrada_a_none(run_pulita) -> None:
    sessione = _sessione_in_scontro()
    sessione.provider = FakeProvider([])  # trasporto muto
    assert asyncio.run(sessione.prosa_apertura_scontro()) is None


def test_apertura_fuori_scontro_e_none(run_pulita) -> None:
    sessione = costruisci_sessione(seed=1)
    asyncio.run(sessione.prossima_narrazione())
    assert asyncio.run(sessione.prosa_apertura_scontro()) is None  # nessuna istanza


def test_apertura_porta_la_lore_del_nemico(run_pulita) -> None:
    """T2: l'apertura non riceve più SOLO il nome — descrizione/aspetto/tratto
    dell'avversario ingaggiato entrano come [scena/nemico] nel prompt utente
    (il prefisso cacheato resta intatto)."""
    from contracts import Grado
    from motore import EntitaMob

    sessione = _sessione_in_scontro()
    # L'ingaggio ordinario cattura i dettagli del mob della stanza.
    assert sessione._dettagli_nemico is not None
    sessione._dettagli_nemico = EntitaMob(
        archetipo="slime", grado=Grado.BRONZO, nome="Slime Madre",
        descrizione="Gorgoglia rancore antico.", livello=1,
        aspetto="una corona di melma", tratto="conta i figli a voce alta",
    )
    fake = FakeProvider([dict(testo="!")])
    sessione.provider = fake
    asyncio.run(sessione.prosa_apertura_scontro())
    prompt = fake.prompt_ricevuti[0]
    assert ("[scena/nemico] Gorgoglia rancore antico.; aspetto: una corona di "
            "melma; tratto: conta i figli a voce alta") in prompt
    assert "[fascicolo" not in fake.sistemi[0]  # il prefisso resta il breve


def test_epitaffio_porta_la_lore_del_nemico(run_pulita) -> None:
    from contracts import Grado
    from motore import EntitaMob

    sessione = costruisci_sessione(seed=1)
    sessione._dettagli_nemico = EntitaMob(
        archetipo="slime", grado=Grado.BRONZO, nome="Il Regista",
        descrizione="Dirige la tua morte come un finale di stagione.", livello=1,
    )
    sessione._fatti_epitaffio = FattiScontro(
        vittoria=False, turni=3, hp_persi=30, nemico="Il Regista"
    )
    fake = FakeProvider([dict(testo="Sipario.")])
    sessione.provider = fake
    asyncio.run(sessione.epitaffio())
    assert "[scena/nemico] Dirige la tua morte" in fake.prompt_ricevuti[0]


def test_epitaffio_ignora_lore_di_un_altro_nemico(run_pulita) -> None:
    from contracts import Grado
    from motore import EntitaMob

    sessione = costruisci_sessione(seed=1)
    sessione._dettagli_nemico = EntitaMob(
        archetipo="slime", grado=Grado.BRONZO, nome="Un Altro",
        descrizione="Lore stantia di uno scontro precedente.", livello=1,
    )
    sessione._fatti_epitaffio = FattiScontro(
        vittoria=False, turni=3, hp_persi=30, nemico="Il Regista"
    )
    fake = FakeProvider([dict(testo="Sipario.")])
    sessione.provider = fake
    asyncio.run(sessione.epitaffio())
    assert "[scena/nemico]" not in fake.prompt_ricevuti[0]


def test_apertura_imboscata_cambia_l_innesco(run_pulita) -> None:
    sessione = _sessione_in_scontro()
    fake = FakeProvider([dict(testo="!")])
    sessione.provider = fake
    asyncio.run(sessione.prosa_apertura_scontro(imboscata=True))
    assert "agguato" in fake.prompt_ricevuti[0]


def test_epitaffio_solo_dopo_una_morte(run_pulita) -> None:
    sessione = costruisci_sessione(seed=1)
    assert asyncio.run(sessione.epitaffio()) is None  # nessuna morte registrata
    sessione._fatti_epitaffio = FattiScontro(
        vittoria=False, turni=3, hp_persi=30, nemico="Il Regista"
    )
    fake = FakeProvider([dict(testo="Applausi. Sipario.")])
    sessione.provider = fake
    assert asyncio.run(sessione.epitaffio()) == "Applausi. Sipario."
    prompt = fake.prompt_ricevuti[0]
    assert "Il Regista" in prompt and "EPITAFFIO" in prompt


def test_epitaffio_degrada_a_none(run_pulita) -> None:
    sessione = costruisci_sessione(seed=1)
    sessione._fatti_epitaffio = FattiScontro(vittoria=False, turni=1, hp_persi=30)
    sessione.provider = FakeProvider([])
    assert asyncio.run(sessione.epitaffio()) is None
