"""T2 — i nemici autorati si sentono in gioco: il MOB ATTESO della stanza entra
nel fascicolo del reveal (lore autorata nel prompt, seed del copione condiviso
con l'offline) e la memoria narrativa viene recuperata anche al reveal.
"""

from __future__ import annotations

import asyncio
import random

from contracts import DocumentoMemoria, TipoDocumento
from motore import (
    Archivio,
    MemoriaSuArchivio,
    MemoriaTurni,
    SistemaTempoPiano,
    avvia_run,
    avvia_territorio,
    componi_fascicolo,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_stagione,
    crea_tempo_piano,
    esegui_turno_gm,
)
from motore.fase import Fase
from provider import FakeProvider
from tests.contenuti_sintetici import piano_territoriale, stagione_sintetica
from tests.narr_helpers import coda_reveal
from tests.narr_helpers import turno as turno_sintetico


def _arma_run_territoriale(seed: int = 7) -> None:
    from main import _stagione_a_attiva

    crea_profondita()
    crea_seme(seed)
    crea_tempo_piano()
    crea_stagione(_stagione_a_attiva(
        stagione_sintetica(piani=[piano_territoriale(1)], slug="s-mondo")
    ))
    assert avvia_territorio(1) is True  # monta la mappa della prima zona
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    avvia_run(crea_singleton_fase=True, fase_iniziale=Fase.NARRAZIONE,
              sempre_attivi=[SistemaTempoPiano()])


def test_mob_atteso_nel_fascicolo_al_reveal(mondo_isolato) -> None:
    _arma_run_territoriale()
    f = componi_fascicolo(MemoriaTurni())
    assert f.mob_atteso_riga and f.mob_atteso_query
    assert 'riferimento="' in f.mob_atteso_riga  # il gate strato 4 lo riconosce
    # Deterministico per costruzione: RNG derivato dal seed del copione, mai lo
    # stream di sessione — stessa stanza, stesso atteso, a ogni lettura.
    assert componi_fascicolo(MemoriaTurni()).mob_atteso_riga == f.mob_atteso_riga
    # Su un turno-AZIONE la riga non c'è: il mob atteso è cosa da reveal.
    assert componi_fascicolo(MemoriaTurni(), azione="guardo").mob_atteso_riga == ""


def test_senza_territorio_nessun_mob_atteso(mondo_isolato) -> None:
    from motore import crea_mappa

    crea_profondita()
    crea_seme(7)
    crea_tempo_piano()
    crea_mappa(random.Random(7))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    avvia_run(crea_singleton_fase=True, fase_iniziale=Fase.NARRAZIONE,
              sempre_attivi=[SistemaTempoPiano()])
    f = componi_fascicolo(MemoriaTurni())
    assert f.mob_atteso_riga == "" and f.mob_atteso_query == ""


def test_reveal_prompt_porta_mob_atteso_e_memoria(mondo_isolato) -> None:
    """Il prompt gating del reveal porta [fascicolo/mob-atteso]; e con un
    documento in memoria sul mob atteso, il recupero scatta ANCHE al reveal
    (prima la query era sempre vuota: il momento dell'ingresso in scena era
    l'unico senza memoria)."""
    _arma_run_territoriale()
    f = componi_fascicolo(MemoriaTurni())
    slug = f.mob_atteso_query.split()[-1]

    arch = Archivio(master_seed=7, model_id="test")
    lunga = MemoriaSuArchivio(arch)
    lunga.salva(DocumentoMemoria(
        id=f"mob-{slug}", tipo=TipoDocumento.PERSONAGGIO,
        titolo=f.mob_atteso_query, testo=f"Già incontrato: {f.mob_atteso_query}.",
        tags=(slug,),
    ))
    prov = FakeProvider(coda_reveal(turno_sintetico().model_dump()))
    asyncio.run(esegui_turno_gm(
        prov, archivio=arch, memoria=MemoriaTurni(), rng=random.Random(1),
        memoria_narrativa=lunga,
    ))
    assert any("[fascicolo/mob-atteso]" in p for p, _s in prov.chiamate)
    assert any("[fascicolo/memoria-lunga]" in p for p, _s in prov.chiamate)
    # Il prefisso di sistema (cache) NON porta il mob atteso: è dinamico.
    assert all("[fascicolo/mob-atteso]" not in s for s in prov.sistemi)
