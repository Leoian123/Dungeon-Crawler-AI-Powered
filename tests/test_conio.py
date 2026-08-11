"""Il CONIO del drop (premi.conio): a chance di drop VINTA, col provider live
il sistema GENERA l'oggetto — grado fissato seeded dal motore PRIMA della
chiamata, schema senza campi numerici, gate su forma/banda/mosse/slug; su
rifiuto o degrado il deposito ricade sul pool (il drop non si perde MAI:
flush anche in salva() e al drop successivo). Offline: percorso storico
sincrono, byte-identico (coperto dalla suite esistente).
"""

from __future__ import annotations

import asyncio

from contracts import Fascia, Grado, ModificatoreAutorato, OggettoAutorato, StatId
from main import costruisci_sessione, etichetta_oggetto
from motore import calibrazione as cal
from motore import (
    catalogo_oggetti_correnti,
    gate_conio,
    grado_oggetto,
    protagonista,
)
from motore.equip import fonti_zaino
from provider import FakeProvider

from tests.test_premi import _vinci_uno_scontro


class _ProviderLive:
    """Un doppio 'live-like' (NON FakeProvider: la sessione lo tratta da vivo)
    con la stessa firma del backend: coda scriptata, prompt osservabili."""

    def __init__(self, candidati=()):
        self._coda = list(candidati)
        self.prompt_ricevuti: list[str] = []

    async def genera(self, prompt, schema, *, sistema=""):
        self.prompt_ricevuti.append(prompt)
        if not self._coda:
            return None
        prossimo = self._coda.pop(0)
        if prossimo is None:
            return None
        return schema.model_validate(prossimo)


def _conio(slug: str = "corona-del-sesto", grado: str = "bronzo", **extra) -> dict:
    base = dict(
        slug=slug, nome="Corona del Sesto",
        descrizione="Un cerchietto di lamiera che sa di regalità scaduta.",
        tipo="accessorio", grado=grado, sede="dita",
        modificatori=[dict(stat="fortuna", fascia="lieve")],
    )
    base.update(extra)
    return base


def _sessione_con_pendente(tmp_path, monkeypatch):
    """Vince uno scontro OFFLINE (deposito sincrono storico), poi arma un drop
    pendente col grado della finestra: il frame che il conio deve rispettare."""
    monkeypatch.setattr(cal, "PROB_DROP", 1.0)
    sessione = costruisci_sessione(nome="Conio", seed=7, directory=tmp_path)
    _vinci_uno_scontro(sessione)
    sessione._ultimo_drop = None
    sessione._drop_pendente = "bronzo"
    return sessione


def test_live_il_drop_resta_pendente_e_il_conio_deposita(run_pulita, tmp_path, monkeypatch) -> None:
    sessione = _sessione_con_pendente(tmp_path, monkeypatch)
    live = _ProviderLive([_conio()])
    sessione.provider = live
    # Live-like: _deposita_bottino ora lascerebbe il drop PENDENTE.
    assert sessione._provider_offline() is False

    prosa = asyncio.run(sessione.veste_premio())
    assert prosa is not None and "Corona del Sesto" in prosa
    # Il prompt porta il frame del motore: grado deciso, non negoziabile.
    assert 'grado: bronzo' in live.prompt_ricevuti[0]
    pent, _m, _s = protagonista()
    assert "corona-del-sesto" in fonti_zaino(pent)
    assert "corona-del-sesto" in catalogo_oggetti_correnti()
    assert grado_oggetto("corona-del-sesto") == "bronzo"
    assert etichetta_oggetto("corona-del-sesto") == "Corona del Sesto"
    assert sessione._drop_pendente is None


def test_conio_equipaggiabile_e_round_trippa(run_pulita, tmp_path, monkeypatch) -> None:
    sessione = _sessione_con_pendente(tmp_path, monkeypatch)
    sessione.provider = _ProviderLive([_conio()])
    assert asyncio.run(sessione.veste_premio()) is not None
    # L'oggetto coniato passa dal canale equip come uno di libreria.
    sessione.equipaggia("corona-del-sesto")
    assert "corona-del-sesto" in sessione.fonti_indossate()

    sessione.salva()
    uuid = sessione.uuid
    sessione.esci()
    from main import carica_sessione

    ripresa = carica_sessione(uuid=uuid, directory=tmp_path)
    assert ripresa is not None
    pent, _m, _s = protagonista()
    assert "corona-del-sesto" in fonti_zaino(pent)
    assert "corona-del-sesto" in catalogo_oggetti_correnti()   # coniati persistenti
    assert "corona-del-sesto" in ripresa.fonti_indossate()     # e re-equipaggiati (F5)


def test_gate_rifiuta_grado_negoziato_e_ricade_sul_pool(run_pulita, tmp_path, monkeypatch) -> None:
    sessione = _sessione_con_pendente(tmp_path, monkeypatch)
    barare = _conio(grado="celestiale")            # alza il grado: respinto
    sessione.provider = _ProviderLive([barare])
    pent, _m, _s = protagonista()
    prima = set(fonti_zaino(pent))

    assert asyncio.run(sessione.veste_premio()) is None
    dopo = set(fonti_zaino(pent))
    # Il drop NON si è perso: un oggetto del pool è stato depositato.
    assert len(dopo) == len(prima) + 1
    assert "corona-del-sesto" not in catalogo_oggetti_correnti()


def test_degrado_trasporto_ricade_sul_pool(run_pulita, tmp_path, monkeypatch) -> None:
    sessione = _sessione_con_pendente(tmp_path, monkeypatch)
    sessione.provider = _ProviderLive([None, None])   # trasporto muto (+ retry rotta)
    pent, _m, _s = protagonista()
    prima = set(fonti_zaino(pent))
    assert asyncio.run(sessione.veste_premio()) is None
    assert len(set(fonti_zaino(pent))) == len(prima) + 1


def test_salva_scarica_il_pendente(run_pulita, tmp_path, monkeypatch) -> None:
    """Un save con drop pendente lo deposita PRIMA di scrivere: il drop vinto
    non si perde nemmeno se l'host non ha mai atteso la vestizione."""
    sessione = _sessione_con_pendente(tmp_path, monkeypatch)
    pent, _m, _s = protagonista()
    prima = set(fonti_zaino(pent))
    sessione.salva()
    assert sessione._drop_pendente is None
    assert len(set(fonti_zaino(pent))) == len(prima) + 1


def test_gate_conio_slug_esistente_e_forma() -> None:
    ok = OggettoAutorato(**_conio())
    collide = OggettoAutorato(**_conio(slug="dadi-truccati"))
    attivo, motivo = gate_conio(collide, "bronzo")
    assert attivo is None and "già esistente" in motivo
    attivo, motivo = gate_conio(ok, "bronzo")
    assert attivo is not None and attivo.slug == "corona-del-sesto"
    assert attivo.modificatori == (("fortuna", "lieve"),)
