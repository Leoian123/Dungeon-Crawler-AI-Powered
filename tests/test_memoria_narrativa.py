"""Porta della memoria narrativa (Fase 6): contratto in contracts, implementazione
file-based sull'Archivio, recupero deterministico, aggancio al fascicolo del GM.
"""

from __future__ import annotations

import asyncio
import random

import pytest

from contracts import DocumentoMemoria, FattiScontro, MemoriaNarrativa, TipoDocumento
from motore import (
    Archivio,
    Fase,
    MemoriaSuArchivio,
    MemoriaTurni,
    SistemaTempoPiano,
    TIPO_RECORD_MEMORIA,
    avvia_run,
    crea_mappa,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_tempo_piano,
    esegui_turno_gm,
)
from provider import FakeProvider
from tests.narr_helpers import coda_azione, coda_reveal

from main import _turni_scriptati


def _doc(id: str, titolo: str, testo: str, tipo=TipoDocumento.EVENTO, tags=()) -> DocumentoMemoria:
    return DocumentoMemoria(id=id, tipo=tipo, titolo=titolo, testo=testo, tags=tuple(tags))


def _memoria() -> MemoriaSuArchivio:
    return MemoriaSuArchivio(Archivio(master_seed=7, model_id="test"))


# --- Contratto e roundtrip ------------------------------------------------------

def test_implementa_la_porta() -> None:
    assert isinstance(_memoria(), MemoriaNarrativa)


def test_roundtrip_e_aggiornamento_idempotente() -> None:
    mem = _memoria()
    mem.salva(_doc("slime-madre", "Slime Madre", "Divorata nella stanza 3."))
    trovati = mem.recupera("slime madre")
    assert len(trovati) == 1 and trovati[0].testo.startswith("Divorata")
    # Stesso id → aggiornamento, mai un doppione.
    mem.salva(_doc("slime-madre", "Slime Madre", "Tornata: nessuno sa come."))
    trovati = mem.recupera("slime madre")
    assert len(trovati) == 1 and "Tornata" in trovati[0].testo


def test_ricostruzione_dal_sidecar() -> None:
    arch = Archivio(master_seed=7, model_id="test")
    MemoriaSuArchivio(arch).salva(_doc("il-regista", "Il Regista", "Dirige da dietro il sipario."))
    # Il roundtrip di serializzazione dell'Archivio è la persistenza della memoria.
    rinato = Archivio.from_dict(arch.to_dict())
    doc = MemoriaSuArchivio(rinato).recupera("regista sipario")
    assert doc and doc[0].id == "il-regista"
    assert rinato.record_di_tipo(TIPO_RECORD_MEMORIA)


# --- Recupero: deterministico, filtrato, limitato -------------------------------

def test_recupero_deterministico_e_ordinato() -> None:
    mem = _memoria()
    mem.salva(_doc("a-goblin", "Goblin bigliettaio", "Strappa biglietti e dita."))
    mem.salva(_doc("b-goblin", "Goblin burattinaio", "Muove fili nel teatro dei goblin."))
    mem.salva(_doc("c-slime", "Slime", "Verde e paziente."))
    prima = mem.recupera("i goblin del teatro")
    seconda = mem.recupera("i goblin del teatro")
    assert prima == seconda  # stesso input → stessa tupla, stesso ordine
    assert [d.id for d in prima][:2] == ["b-goblin", "a-goblin"]  # punteggio, poi id
    assert all("slime" != d.id for d in prima)  # punteggio 0 = fuori


def test_filtro_per_tipo_e_limite() -> None:
    mem = _memoria()
    mem.salva(_doc("evento-x", "La caduta", "Il ponte è crollato.", TipoDocumento.EVENTO))
    mem.salva(_doc("png-x", "Il custode", "Sa del ponte crollato.", TipoDocumento.PERSONAGGIO))
    solo_png = mem.recupera("ponte crollato", tipi=(TipoDocumento.PERSONAGGIO,))
    assert [d.id for d in solo_png] == ["png-x"]
    assert len(mem.recupera("ponte crollato", limite=1)) == 1


def test_query_vuota_non_recupera_nulla() -> None:
    mem = _memoria()
    mem.salva(_doc("x", "X", "Qualcosa."))
    assert mem.recupera("") == () and mem.recupera("a e") == ()


def test_id_non_slug_rifiutato() -> None:
    with pytest.raises(Exception):
        _doc("Non Uno Slug", "T", "t")


# --- Aggancio al fascicolo del GM -----------------------------------------------

def _arma_run(seed: int = 7) -> None:
    crea_profondita()
    crea_seme(seed)
    crea_tempo_piano()
    crea_mappa(random.Random(seed))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    avvia_run(crea_singleton_fase=True, fase_iniziale=Fase.NARRAZIONE,
              sempre_attivi=[SistemaTempoPiano()])


def _pipeline(prov, arch, mem, memoria_narrativa, **kw):
    return asyncio.run(esegui_turno_gm(
        prov, archivio=arch, memoria=mem, rng=random.Random(1),
        memoria_narrativa=memoria_narrativa, **kw
    ))


def test_la_memoria_lunga_entra_nel_prompt_solo_se_rilevante(mondo_isolato) -> None:
    _arma_run()
    arch = Archivio(master_seed=7, model_id="test")
    lunga = MemoriaSuArchivio(arch)
    lunga.salva(_doc("patto-slime", "Il patto con lo slime",
                     "Il crawler ha risparmiato lo slime della stanza 1."))
    turno = _turni_scriptati()[0].model_dump()

    prov = FakeProvider(coda_reveal(turno) + coda_azione(turno))
    mem = MemoriaTurni()
    # Reveal: nessuna azione → nessuna query → sezione assente.
    _pipeline(prov, arch, mem, lunga)
    assert all("[fascicolo/memoria-lunga]" not in p for p, _s in prov.chiamate)
    # Azione che tocca il documento: la sezione compare nel prompt gating.
    _pipeline(prov, arch, mem, lunga, azione="cerco lo slime del patto")
    assert any("[fascicolo/memoria-lunga]" in p and "patto" in p
               for p, _s in prov.chiamate)


def test_mob_memorabile_scrive_un_personaggio(mondo_isolato, monkeypatch) -> None:
    """Sit.2: la materializzazione di un mob di grado alto (o anomalia) salva un
    PERSONAGGIO nella memoria narrativa — deterministico, zero chiamate."""
    from contracts import Grado
    from motore import gm as gm_mod
    from tests.narr_helpers import budget as costruisci_budget

    _arma_run()
    bud = costruisci_budget(gradi=(Grado.BRONZO, Grado.ORO))
    monkeypatch.setattr(gm_mod, "prepara_contesto", lambda livello, rng, piano=None: bud)

    turno = _turni_scriptati()[0].model_dump()
    turno["entita"]["grado"] = "oro"
    turno["entita"]["aspetto"] = "una corona di denti da latte"
    turno["entita"]["tratto"] = "canticchia jingle pubblicitari"

    arch = Archivio(master_seed=7, model_id="test")
    lunga = MemoriaSuArchivio(arch)
    _pipeline(FakeProvider(coda_reveal(turno)), arch, MemoriaTurni(), lunga)

    nome = turno["entita"]["nome"]
    doc = lunga.recupera(nome, tipi=(TipoDocumento.PERSONAGGIO,))
    assert doc and doc[0].titolo == nome
    assert "corona di denti" in doc[0].testo and "oro" in doc[0].testo


def test_mob_ordinario_non_intasa_la_memoria(mondo_isolato) -> None:
    _arma_run()
    arch = Archivio(master_seed=7, model_id="test")
    lunga = MemoriaSuArchivio(arch)
    turno = _turni_scriptati()[0].model_dump()  # grado bronzo, nessuna anomalia
    _pipeline(FakeProvider(coda_reveal(turno)), arch, MemoriaTurni(), lunga)
    assert not arch.record_di_tipo(TIPO_RECORD_MEMORIA)


def test_il_resoconto_scrive_un_evento(mondo_isolato) -> None:
    _arma_run()
    arch = Archivio(master_seed=7, model_id="test")
    lunga = MemoriaSuArchivio(arch)
    turno = _turni_scriptati()[0].model_dump()
    prov = FakeProvider(coda_reveal(turno))
    mem = MemoriaTurni()
    _pipeline(prov, arch, mem, lunga)  # reveal: la stanza esiste

    prov.accoda(dict(testo="chiusura"))
    fatti = FattiScontro(vittoria=True, turni=3, hp_persi=1, nemico="Slime Mangiascarti",
                         momenti=("colpo di grazia: il crawler colpisce",))
    _pipeline(prov, arch, mem, lunga, esito_scontro=fatti)
    doc = lunga.recupera("scontro slime mangiascarti", tipi=(TipoDocumento.EVENTO,))
    assert doc and "vinto in 3 turni" in doc[0].testo
    assert "colpo di grazia" in doc[0].testo
