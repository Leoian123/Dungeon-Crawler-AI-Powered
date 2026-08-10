"""T3 — fondamenta PNG: materializzazione (un mob senza ostilità), esenzioni
(despawn di zona, registro nemici della mappa), rotta di dialogo phase-gated di
SOLA prosa (zero esiti, zero mutazioni), memoria INTERAZIONE dai fatti.
"""

from __future__ import annotations

import asyncio
import random

import esper
import pytest

from contracts import Durata, Grado, RuoloMob, TipoDocumento
from motore import (
    Archivio,
    EntitaMob,
    MasterEngine,
    MemoriaSuArchivio,
    Primarie,
    ROTTE,
    SistemaTempoPiano,
    avvia_run,
    crea_mappa,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_tempo_piano,
    dialoga,
    mappa_corrente,
    materializza_png,
    mob_corrente,
    png_in_stanza_corrente,
    tempo_piano_corrente,
)
from motore.fase import Fase
from provider import FakeProvider


def _png_attivo(nome: str = "L'Archivista"):
    from motore.design import MobAttivo

    return MobAttivo(
        slug="archivista-demo", nome=nome, archetipo="slime",
        grado=Grado.BRONZO, blocchi=[], descrizione="Cataloga i caduti del piano.",
        prosa_stanza="Una scena.", durata=Durata.TURNO,
    )


def _arma_narrazione(fase: Fase = Fase.NARRAZIONE) -> int:
    """Harness minimo: mappa + tempo + fase. Ritorna la stanza corrente."""
    crea_profondita()
    crea_seme(7)
    crea_tempo_piano()
    crea_mappa(random.Random(7))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    avvia_run(crea_singleton_fase=True, fase_iniziale=fase,
              sempre_attivi=[SistemaTempoPiano()])
    return mappa_corrente()[1].stanza_corrente


# --- Materializzazione: un mob a tutti gli effetti, senza ostilità -------------

def test_materializza_png_col_profilo_calibrato(mondo_isolato) -> None:
    stanza = _arma_narrazione()
    ent = materializza_png(_png_attivo(), livello=1, stanza=stanza)
    em = esper.component_for_entity(ent, EntitaMob)
    assert em.ruolo is RuoloMob.PNG and em.stanza == stanza
    # Stessa strada del mob: le primarie escono dalla formula-madre.
    assert esper.component_for_entity(ent, Primarie).valori
    # MAI il nemico della stanza: mob_corrente non lo vede, la query PNG sì.
    assert mob_corrente() is None
    assert png_in_stanza_corrente() == ent


def test_png_sopravvive_al_despawn_di_zona(mondo_isolato) -> None:
    from motore.territorio import _despawna_mob_di_zona

    stanza = _arma_narrazione()
    png = materializza_png(_png_attivo(), livello=1, stanza=stanza)
    ostile = esper.create_entity(EntitaMob(
        archetipo="slime", grado=Grado.BRONZO, nome="Ostile",
        descrizione="x", livello=1, stanza=stanza,
    ))
    _despawna_mob_di_zona()
    assert esper.entity_exists(png), "il PNG non è arredo della zona"
    assert not esper.entity_exists(ostile)


def test_png_fuori_dal_relink_della_mappa(mondo_isolato) -> None:
    """Al load il PNG non entra in `mob_stanza`: non diventa il nemico della
    stanza (menu Combatti, varco chiuso)."""
    from motore.mappa import mappa_da_dict, mappa_to_dict

    stanza = _arma_narrazione()
    png = materializza_png(_png_attivo(), livello=1, stanza=stanza)
    m = mappa_corrente()
    dati = mappa_to_dict()
    esper.delete_entity(m[0], immediate=True)
    mappa_da_dict(dati)
    assert mob_corrente() is None
    assert png_in_stanza_corrente() == png


def test_ruolo_round_trippa_e_i_save_legacy_sono_ostili(mondo_isolato) -> None:
    from motore.persistenza.tag import deserializza_componente, serializza_componente

    em = EntitaMob(archetipo="slime", grado=Grado.BRONZO, nome="A",
                   descrizione="d", livello=1, ruolo=RuoloMob.PNG)
    tag, dati = serializza_componente(em)
    assert dati["ruolo"] == "png"
    vivo = deserializza_componente(tag, dati)
    assert vivo.ruolo is RuoloMob.PNG
    # Save legacy: campo assente → OSTILE (default storico).
    dati_legacy = {k: v for k, v in dati.items() if k != "ruolo"}
    assert deserializza_componente(tag, dati_legacy).ruolo is RuoloMob.OSTILE


# --- Dialogo: sola prosa, phase-gated, zero mutazioni --------------------------

def test_rotta_dialogo_registrata_di_sola_prosa() -> None:
    from contracts import Flavor

    rotta = ROTTE["png.dialogo"]
    assert rotta.schema is Flavor and rotta.gating is False
    assert rotta.fase is Fase.NARRAZIONE  # parlare in combattimento: impossibile


def test_dialogo_felice_senza_mutazioni(mondo_isolato) -> None:
    stanza = _arma_narrazione()
    ent = materializza_png(_png_attivo(), livello=1, stanza=stanza)
    arch = Archivio(master_seed=7, model_id="test")
    lunga = MemoriaSuArchivio(arch)
    fake = FakeProvider([dict(testo="«Nome? Piano d'ingresso?»")])
    tick_prima = tempo_piano_corrente()
    componenti_prima = len(esper.components_for_entity(ent))

    risposta = asyncio.run(dialoga(
        MasterEngine.avvolgi(fake), ent, "chi è passato di qui?",
        memoria_narrativa=lunga,
    ))
    assert risposta == "«Nome? Piano d'ingresso?»"
    prompt = fake.prompt_ricevuti[0]
    assert "[png]" in prompt and "[battuta]" in prompt and "arbitro" in prompt
    # ZERO mutazioni: niente tempo speso, niente componenti nuovi, fase intatta.
    assert tempo_piano_corrente() == tick_prima
    assert len(esper.components_for_entity(ent)) == componenti_prima
    # L'INTERAZIONE è scritta DAI FATTI (la battuta), con id per-slug.
    doc = lunga.recupera("archivista", tipi=(TipoDocumento.INTERAZIONE,))
    assert doc and doc[0].id.startswith("dialogo-l-archivista")
    assert "chi è passato di qui?" in doc[0].testo


def test_dialogo_degrada_deterministico(mondo_isolato) -> None:
    stanza = _arma_narrazione()
    ent = materializza_png(_png_attivo(), livello=1, stanza=stanza)
    risposta = asyncio.run(dialoga(MasterEngine.avvolgi(FakeProvider([])), ent, "ehi"))
    assert risposta == "L'Archivista ti squadra a lungo. Non risponde."


def test_dialogo_in_combattimento_impossibile(mondo_isolato) -> None:
    stanza = _arma_narrazione(fase=Fase.COMBATTIMENTO)
    ent = materializza_png(_png_attivo(), livello=1, stanza=stanza)
    with pytest.raises(RuntimeError, match="NARRAZIONE"):
        asyncio.run(dialoga(MasterEngine.avvolgi(FakeProvider([])), ent, "ciao"))


def test_dialogo_recupera_la_memoria_del_png(mondo_isolato) -> None:
    stanza = _arma_narrazione()
    ent = materializza_png(_png_attivo(), livello=1, stanza=stanza)
    arch = Archivio(master_seed=7, model_id="test")
    lunga = MemoriaSuArchivio(arch)
    asyncio.run(dialoga(MasterEngine.avvolgi(FakeProvider([dict(testo="a")])),
                        ent, "prima battuta", memoria_narrativa=lunga))
    fake = FakeProvider([dict(testo="b")])
    asyncio.run(dialoga(MasterEngine.avvolgi(fake), ent, "seconda battuta",
                        memoria_narrativa=lunga))
    # Il secondo giro vede l'interazione precedente nel prompt...
    assert any("[memoria]" in p for p in fake.prompt_ricevuti)
    # ...e il documento resta UNO, aggiornato (stesso id = idempotente).
    doc = lunga.recupera("archivista", tipi=(TipoDocumento.INTERAZIONE,))
    assert len(doc) == 1 and "seconda battuta" in doc[0].testo


# --- L'asset demo del canale ----------------------------------------------------

def test_asset_demo_png_carica_e_materializza(mondo_isolato) -> None:
    """Il dato-demo del canale: `contenuti/mob/archivista-del-sesto.json` (tag
    `png`, NON referenziato dal cast: inerte per il gioco finché l'utente non
    lo arruola). Carica, converte a MobAttivo e materializza."""
    from main import DIRECTORY_CONTENUTI, carica_asset
    from motore.design import MobAttivo

    asset = carica_asset("mob", "archivista-del-sesto",
                         ufficiali=DIRECTORY_CONTENUTI, locali=None)
    assert asset is not None and "png" in asset.tags
    stanza = _arma_narrazione()
    # zombie non è negli storici: per il test si materializza sull'archetipo
    # di calibrazione (il canale, non il contenuto).
    attivo = MobAttivo(
        slug=asset.slug, nome=asset.nome, archetipo="slime", grado=asset.grado,
        blocchi=list(asset.blocchi), descrizione=asset.descrizione,
        prosa_stanza=asset.prosa_stanza, durata=asset.durata,
    )
    ent = materializza_png(attivo, livello=1, stanza=stanza)
    em = esper.component_for_entity(ent, EntitaMob)
    assert em.ruolo is RuoloMob.PNG and em.nome == asset.nome
