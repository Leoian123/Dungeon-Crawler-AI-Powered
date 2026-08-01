"""Drenaggio UNIFICATO degli intenti (Canale A): un solo travaso coda→World, consumo
separato per dominio — esplorazione ai sistemi solo-narrazione, combattimento alla sua
fase, menu al port. Il port non preleva più dalla coda e non scarta più nulla.
Contesti esper isolati (ESP §0.1).
"""

from __future__ import annotations

import asyncio

import esper

from contracts import (
    BusEventi,
    DiscesaPiano,
    IntentoEsplorazione,
    PlayerChoseOption,
    PlayerDiscende,
)
from motore import (
    CodaIntenti,
    Fase,
    MessaggioIntento,
    SistemaDiscesa,
    avvia_run,
    consuma_messaggi,
    crea_profondita,
    imposta_fase,
    livello_corrente,
    mappa_corrente,
    messaggi_pendenti,
    tick,
    travasa,
)
from main import costruisci_sessione


def _vai_alla_scala() -> None:
    """Porta la stanza corrente su una scala (il gate di discesa richiede il primitivo)."""
    trovata = mappa_corrente()
    assert trovata is not None
    _ent, mappa = trovata
    mappa.stanza_corrente = next(iter(mappa.piano.discese))


# --- Il travaso unico e il consumo tipizzato -----------------------------------

def test_travasa_fifo_e_consumo_per_tipo(mondo_isolato) -> None:
    coda = CodaIntenti()
    coda.accoda(PlayerChoseOption(0))
    coda.accoda(PlayerDiscende())
    coda.accoda(PlayerChoseOption(1))
    assert travasa(coda) == 3 and len(coda) == 0  # coda svuotata, tutto nel World

    scelte = consuma_messaggi(PlayerChoseOption)
    assert [i.opzione for i in scelte] == [0, 1]  # FIFO, solo il tipo chiesto
    # L'intento di dominio NON è stato scartato: resta pendente per il suo consumatore.
    assert messaggi_pendenti() == 1 and messaggi_pendenti(IntentoEsplorazione) == 1
    assert [type(i) for i in consuma_messaggi(IntentoEsplorazione)] == [PlayerDiscende]
    # Niente gusci vuoti: le entità-messaggio consumate sono eliminate.
    assert not list(esper.get_component(MessaggioIntento))


# --- Separazione per fase: l'esplorazione non si consuma in combattimento ------

def test_intento_esplorazione_attende_la_sua_fase(mondo_isolato) -> None:
    crea_profondita()
    bus = BusEventi()
    coda = avvia_run(solo_narrazione=[SistemaDiscesa(bus)], fase_iniziale=Fase.COMBATTIMENTO)

    coda.accoda(PlayerDiscende())
    tick()  # travaso sì, ma SistemaDiscesa è solo-narrazione: NON consuma
    assert livello_corrente() == 1
    assert messaggi_pendenti(IntentoEsplorazione) == 1  # in attesa, non scartato

    imposta_fase(Fase.NARRAZIONE)
    tick()  # nella sua fase, l'intento viene servito
    assert livello_corrente() == 2
    assert messaggi_pendenti() == 0


# --- Il port: non scarta più gli intenti di dominio ----------------------------

def test_avanza_serve_anche_gli_intenti_di_esplorazione(run_pulita) -> None:
    sessione = costruisci_sessione(seed=3)
    eventi: list[DiscesaPiano] = []
    sessione.bus.registra(DiscesaPiano, eventi.append)
    try:
        asyncio.run(sessione.prossima_narrazione())  # boot: prosa + menu (narrazione)
        _vai_alla_scala()                            # la discesa richiede la scala (mappa)
        sessione.coda.accoda(PlayerDiscende())       # intento di dominio, non di menu
        sessione.avanza()
        assert len(eventi) == 1 and eventi[0].piano == 2  # servito, non scartato
        assert messaggi_pendenti() == 0
    finally:
        sessione.bus.deregistra(DiscesaPiano, eventi.append)


def test_avanza_in_combattimento_fa_attendere_l_esplorazione(run_pulita) -> None:
    sessione = costruisci_sessione(seed=3)
    eventi: list[DiscesaPiano] = []
    sessione.bus.registra(DiscesaPiano, eventi.append)
    try:
        _vai_alla_scala()  # il combattimento avverrà nella stanza della scala
        asyncio.run(sessione.prossima_narrazione())
        sessione.coda.accoda(PlayerChoseOption(0))  # "Combatti" → si entra in combattimento
        sessione.coda.accoda(PlayerDiscende())      # esplorazione: deve ATTENDERE
        snap = sessione.avanza()
        assert snap.fase == "combattimento"
        assert eventi == []                          # non consumato nella fase sbagliata
        assert messaggi_pendenti(IntentoEsplorazione) == 1

        # Si combatte fino a chiudere lo scontro; al ritorno in narrazione il primo
        # `avanza` serve l'intento rimasto in attesa.
        for _ in range(60):
            sessione.coda.accoda(PlayerChoseOption(0))  # "Attacca"
            snap = sessione.avanza()
            if snap.fase != "combattimento":
                break
        assert snap.fase == "narrazione"
        assert len(eventi) == 1                      # la discesa arriva, separata e intatta
    finally:
        sessione.bus.deregistra(DiscesaPiano, eventi.append)


def test_avanza_a_vuoto_non_ticka(run_pulita) -> None:
    # Un poll senza intenti non deve produrre un turno del motore (niente tempo speso).
    sessione = costruisci_sessione(seed=3)
    asyncio.run(sessione.prossima_narrazione())
    from motore import tempo_piano_corrente
    prima = tempo_piano_corrente()
    sessione.avanza()
    assert tempo_piano_corrente() == prima
