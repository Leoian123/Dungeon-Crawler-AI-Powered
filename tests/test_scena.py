"""Scena narrativa S1 — i lucchetti dei tre gate: chiusura onesta (mai vittorie
a parole), anti-pesca (il check fallito è fallito), tetto di battute (§11).
L'AI compone i blocchi, il MOTORE tira e arbitra: il flusso emerge dal prodotto.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from contracts import (
    BattutaScena,
    BloccoScena,
    ClasseProva,
    EsitoScena,
    StatId,
)
from motore import IstanzaScena, MasterEngine, battuta_scena, fatti_scena
from motore.fase import Fase, crea_entita_fase, imposta_fase
from provider import FakeProvider


def _arma_mondo() -> None:
    from motore import crea_protagonista, crea_seme

    crea_seme(7)
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    crea_entita_fase()


def _engine(*battute: dict) -> MasterEngine:
    return MasterEngine.avvolgi(FakeProvider(list(battute)))


def _negoziazione() -> IstanzaScena:
    return IstanzaScena(
        partecipanti=["Gruppo di crawler ostili"],
        posta="passare il ponte senza combattere",
    )


# --- Il contratto: i campi del blocco sono vincolati -----------------------------

def test_lo_schema_vincola_i_campi_al_blocco() -> None:
    BattutaScena(blocco=BloccoScena.BATTUTA, prosa="Parliamo.")
    BattutaScena(blocco=BloccoScena.SNODO, prosa="Ora o mai più.",
                 classe=ClasseProva.ARGENTO, stat=StatId.SAGGEZZA)
    BattutaScena(blocco=BloccoScena.CHIUDI, prosa="È fatta.",
                 esito=EsitoScena.CONCLUSA)
    with pytest.raises(ValidationError):  # snodo senza inquadramento
        BattutaScena(blocco=BloccoScena.SNODO, prosa="x")
    with pytest.raises(ValidationError):  # l'esito dello snodo non è dell'AI
        BattutaScena(blocco=BloccoScena.SNODO, prosa="x",
                     classe=ClasseProva.BRONZO, stat=StatId.DESTREZZA,
                     esito=EsitoScena.VINTA)
    with pytest.raises(ValidationError):  # chiudi senza esito
        BattutaScena(blocco=BloccoScena.CHIUDI, prosa="x")
    with pytest.raises(ValidationError):  # battuta con campi altrui
        BattutaScena(blocco=BloccoScena.BATTUTA, prosa="x", stat=StatId.FORTUNA)


# --- Gate 1: chiusura onesta — mai vittorie a parole -----------------------------

def test_vinta_senza_snodo_e_illegale_e_la_scena_continua(mondo_isolato) -> None:
    _arma_mondo()
    istanza = _negoziazione()
    prosa = asyncio.run(battuta_scena(
        _engine(dict(blocco="chiudi", prosa="Vi ho convinti!", esito="vinta")),
        istanza, "fidatevi di me",
    ))
    assert istanza.aperta, "la vittoria a parole non chiude la scena"
    assert fatti_scena(istanza) is None
    assert prosa  # la proposta resta prosa: il gate è muto per il modello


def test_vinta_dopo_snodo_superato_e_legale(mondo_isolato) -> None:
    _arma_mondo()
    istanza = _negoziazione()
    # Snodo su una prova che il protagonista PASSA (bronzo su destrezza 10).
    asyncio.run(battuta_scena(
        _engine(dict(blocco="snodo", prosa="Il capo ti squadra.",
                     classe="bronzo", stat="destrezza")),
        istanza, "posso pagare il pedaggio",
    ))
    assert istanza.snodo_superato is True
    asyncio.run(battuta_scena(
        _engine(dict(blocco="chiudi", prosa="Passate.", esito="vinta")),
        istanza, "allora siamo d'accordo",
    ))
    fatti = fatti_scena(istanza)
    assert fatti is not None and fatti.esito is EsitoScena.VINTA
    assert fatti.momenti and "prova bronzo su destrezza" in fatti.momenti[0]


def test_senza_posta_ne_vinta_ne_persa(mondo_isolato) -> None:
    _arma_mondo()
    colloquio = IstanzaScena(partecipanti=["Il Manager"])  # nessuna posta
    asyncio.run(battuta_scena(
        _engine(dict(blocco="chiudi", prosa="Ho vinto io.", esito="vinta")),
        colloquio, "com'è andata l'asta?",
    ))
    assert colloquio.aperta  # vinta senza posta: illegale
    asyncio.run(battuta_scena(
        _engine(dict(blocco="chiudi", prosa="A domani.", esito="conclusa")),
        colloquio, "a domani",
    ))
    assert colloquio.concluso is EsitoScena.CONCLUSA


# --- Gate 2: anti-pesca — il check fallito è fallito ------------------------------

def test_anti_pesca_niente_secondo_tiro(mondo_isolato) -> None:
    _arma_mondo()
    istanza = _negoziazione()
    # Prova IMPOSSIBILE per il protagonista: fallisce (celestiale su destrezza).
    asyncio.run(battuta_scena(
        _engine(dict(blocco="snodo", prosa="Convincili, se ci riesci.",
                     classe="celestiale", stat="destrezza")),
        istanza, "vi conviene lasciarmi passare",
    ))
    assert istanza.snodo_fallito is True and not istanza.snodo_superato
    momenti_prima = list(istanza.momenti)

    # Il modello ripesca: il motore NON tira più (nessun momento nuovo).
    asyncio.run(battuta_scena(
        _engine(dict(blocco="snodo", prosa="E se invece...",
                     classe="bronzo", stat="destrezza")),
        istanza, "riproviamo",
    ))
    assert istanza.momenti == momenti_prima, "retry-fishing: il dado è sacro"
    assert istanza.snodo_superato is False

    # E la vittoria resta illegale per sempre su questa posta.
    asyncio.run(battuta_scena(
        _engine(dict(blocco="chiudi", prosa="Ce l'ho fatta!", esito="vinta")),
        istanza, "quindi passo",
    ))
    assert istanza.aperta


def test_il_fatto_del_tiro_e_visibile_e_nel_prompt_successivo(mondo_isolato) -> None:
    _arma_mondo()
    istanza = _negoziazione()
    prosa = asyncio.run(battuta_scena(
        _engine(dict(blocco="snodo", prosa="Il capo esita.",
                     classe="celestiale", stat="destrezza")),
        istanza, "fatemi passare",
    ))
    assert "prova celestiale su destrezza" in prosa  # la riga del MOTORE, sempre
    fake = FakeProvider([dict(blocco="battuta", prosa="Il capo ride.")])
    asyncio.run(battuta_scena(MasterEngine.avvolgi(fake), istanza, "vi prego"))
    prompt = fake.chiamate[0][0]
    assert "[scena/fatto] prova celestiale" in prompt  # l'AI compone SUI fatti
    assert "non si ripete" in prompt


# --- Gate 3: il tetto §11 chiude d'ufficio ---------------------------------------

def test_al_tetto_la_posta_non_vinta_e_persa(mondo_isolato, monkeypatch) -> None:
    from motore import calibrazione as cal

    monkeypatch.setattr(cal, "SCENA_MAX_BATTUTE", 2)
    _arma_mondo()
    istanza = _negoziazione()
    for _ in range(2):
        asyncio.run(battuta_scena(
            _engine(dict(blocco="battuta", prosa="Si gira intorno al punto.")),
            istanza, "e quindi?",
        ))
    fatti = fatti_scena(istanza)
    assert fatti is not None and fatti.esito is EsitoScena.PERSA
    assert fatti.battute == 2


def test_al_tetto_senza_posta_si_conclude(mondo_isolato, monkeypatch) -> None:
    from motore import calibrazione as cal

    monkeypatch.setattr(cal, "SCENA_MAX_BATTUTE", 1)
    _arma_mondo()
    colloquio = IstanzaScena(partecipanti=["Il Manager"])
    asyncio.run(battuta_scena(
        _engine(dict(blocco="battuta", prosa="Il manager sospira.")),
        colloquio, "parliamo del contratto",
    ))
    assert colloquio.concluso is EsitoScena.CONCLUSA


# --- Fase, degrado, zero mutazioni ----------------------------------------------

def test_in_combattimento_la_scena_e_impossibile(mondo_isolato) -> None:
    """Parlare in combattimento è STRUTTURALMENTE impossibile: la guardia di
    fase del Master-Engine (la stessa di `png.dialogo`), non un check a mano."""
    _arma_mondo()
    imposta_fase(Fase.COMBATTIMENTO)
    istanza = _negoziazione()
    with pytest.raises(RuntimeError, match="NARRAZIONE"):
        asyncio.run(battuta_scena(
            _engine(dict(blocco="battuta", prosa="mai vista")), istanza, "ehi",
        ))
    assert istanza.aperta and istanza.battute_spese == 0  # nulla è successo


def test_degrado_senza_provider_mai_muto(mondo_isolato) -> None:
    _arma_mondo()
    istanza = _negoziazione()
    prosa = asyncio.run(battuta_scena(_engine(), istanza, "c'è nessuno?"))
    assert prosa  # la riga muta deterministica


def test_zero_mutazioni_dello_stato_di_gioco(mondo_isolato) -> None:
    from motore import protagonista

    _arma_mondo()
    _pent, _marker, scheda = protagonista()
    hp_prima = scheda.punti_vita
    istanza = _negoziazione()
    asyncio.run(battuta_scena(
        _engine(dict(blocco="snodo", prosa="Provaci.",
                     classe="oro", stat="costituzione")),
        istanza, "sono più forte di voi",
    ))
    assert protagonista()[2].punti_vita == hp_prima  # la scena non tocca il World
