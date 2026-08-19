"""I TIPI di stanza (T1): vocabolario chiuso, stampa seeded a vincoli, garanzia
di spina, persistenza, tipo nel fascicolo. «Borderlands della mappa»: le categorie
sono chiuse, la composizione la fa il MOTORE — l'AI le narra, mai le sceglie.
"""

from __future__ import annotations

import random

import esper

from contracts import BusEventi, TipoStanza
from motore import (
    avvia_territorio,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_stagione,
    crea_tempo_piano,
    e_di_spina,
    genera_topologia,
    mappa_corrente,
    rigenera_mappa_zona,
    spina_del_piano,
    stampa_tipi,
    stanza_boss_di,
    tipo_di,
    tipo_stanza_corrente,
    zona_corrente,
)
from motore.calibrazione import STANZE_SAFE_OGNI_ZONE
from tests.contenuti_sintetici import piano_territoriale, stagione_sintetica


def _arma_mondo(seed: int = 7) -> BusEventi:
    from main import _stagione_a_attiva

    crea_profondita()
    crea_seme(seed)
    crea_tempo_piano()
    crea_stagione(_stagione_a_attiva(
        stagione_sintetica(piani=[piano_territoriale(1)], slug="s-tipi")
    ))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    avvia_territorio(1)
    return BusEventi()


# --- La stampa pura: vincoli e determinismo -------------------------------------

def test_stampa_rispetta_i_vincoli() -> None:
    piano = genera_topologia(random.Random(1), 8)
    boss = 6  # non la scala (7): la scala resta NORMALE, il boss è un'altra stanza
    stampa_tipi(piano, random.Random(2), boss=boss, safe_garantita=True)
    assert tipo_di(piano, boss) is TipoStanza.BOSS
    assert tipo_di(piano, piano.partenza) is TipoStanza.NORMALE  # mai speciale
    for scala in piano.discese:
        assert tipo_di(piano, scala) is TipoStanza.NORMALE
    conteggio = list(piano.tipi.values())
    assert conteggio.count(TipoStanza.SAFE_ROOM) == 1  # garantita, e al più una
    assert conteggio.count(TipoStanza.BAGNO) <= 1
    for stanza, tipo in piano.tipi.items():
        if tipo is TipoStanza.CORRIDOIO:
            assert len(piano.adiacenze[stanza]) >= 2  # solo stanze connettive


def test_stampa_deterministica_e_topologia_intatta() -> None:
    a = genera_topologia(random.Random(3), 8)
    b = genera_topologia(random.Random(3), 8)
    com_era = {k: list(v) for k, v in a.adiacenze.items()}  # PRIMA della stampa
    stampa_tipi(a, random.Random(9), boss=7, safe_garantita=True)
    stampa_tipi(b, random.Random(9), boss=7, safe_garantita=True)
    assert a.tipi == b.tipi
    assert a.adiacenze == com_era, "la stampa non deve toccare la topologia"


def test_il_corridoio_esige_una_stanza_connettiva(monkeypatch) -> None:
    """Il vincolo grado ≥2, esercitato davvero (review 2026-08-11: sulle
    topologie generate le stanze libere sono sempre connettive e il vincolo
    non mordeva mai): un Piano a mano con una foglia di grado 1 libera e la
    frazione a 1 — la foglia resta NORMALE, il connettivo diventa corridoio."""
    from motore import mappa as mappa_mod
    from motore.piano import Piano

    monkeypatch.setattr(mappa_mod, "STANZE_FRAZ_CORRIDOI", 1.0)
    piano = Piano(
        partenza=0,
        adiacenze={0: [1], 1: [0, 2, 3], 2: [1], 3: [1]},  # 2 e 3: foglie libere
        discese={2},
    )
    stampa_tipi(piano, random.Random(5))
    assert tipo_di(piano, 3) is TipoStanza.NORMALE, "una foglia non è un corridoio"
    assert tipo_di(piano, 1) is TipoStanza.CORRIDOIO  # il connettivo, a frazione 1


# --- La stampa territoriale: boss ovunque, safe per quota di spina ---------------

def test_ogni_zona_ha_il_boss_stampato(mondo_isolato) -> None:
    _arma_mondo()
    for zona in spina_del_piano(1):
        rigenera_mappa_zona(1, zona)
        _e, mappa = mappa_corrente()
        assert tipo_di(mappa.piano, stanza_boss_di(zona, mappa.piano)) is TipoStanza.BOSS


def test_garanzia_safe_di_spina(mondo_isolato) -> None:
    """La quota §11 (`STANZE.safe_ogni_zone`): le zone di spina con ordine
    ≡ N-1 mod N stampano una SAFE ROOM — se una stanza libera esiste (alla
    scala sintetica la tana da 3 stanze non ne ha: partenza+boss+scala)."""
    _arma_mondo()
    ogni = max(1, int(STANZE_SAFE_OGNI_ZONE))
    verificate = 0
    for zona in spina_del_piano(1):
        rigenera_mappa_zona(1, zona)
        _e, mappa = mappa_corrente()
        tipi = set(mappa.piano.tipi.values())
        speciali = {mappa.piano.partenza, stanza_boss_di(zona, mappa.piano)} | set(
            mappa.piano.discese
        )
        c_e_posto = len(mappa.piano.adiacenze) > len(speciali)
        if zona.tier.ordine % ogni == ogni - 1 and c_e_posto:
            verificate += 1
            assert TipoStanza.SAFE_ROOM in tipi, (
                f"{zona.tier.value}: la safe room di quota manca"
            )
        elif zona.tier.ordine % ogni != ogni - 1:
            # Il complemento «rara, mai regalata»: FUORI quota la spina non
            # stampa safe room — una garanzia allargata a ogni zona passerebbe
            # il ramo sopra ma non questo.
            assert TipoStanza.SAFE_ROOM not in tipi, (
                f"{zona.tier.value}: safe room regalata fuori quota"
            )
    assert verificate > 0, "sentinella: nessuna zona in quota verificata (test vacuo)"


def test_tipi_di_zona_deterministici_e_topologia_invariata(mondo_isolato) -> None:
    """Rigenerare la stessa zona produce identici tipi E identica topologia:
    lo stream `…:tipi` è dedicato, i replay non si muovono."""
    _arma_mondo()
    zona = spina_del_piano(1)[1]
    rigenera_mappa_zona(1, zona)
    _e, mappa = mappa_corrente()
    prima = (dict(mappa.piano.adiacenze), dict(mappa.piano.tipi))
    rigenera_mappa_zona(1, zona)
    _e, mappa = mappa_corrente()
    assert (dict(mappa.piano.adiacenze), dict(mappa.piano.tipi)) == prima


# --- Persistenza: round-trip e migrazione lazy dei save storici ------------------

def test_tipi_roundtrip_nel_save(mondo_isolato) -> None:
    from motore.mappa import Mappa, mappa_da_dict, mappa_to_dict

    _arma_mondo()
    _e, mappa = mappa_corrente()
    assert mappa.piano.tipi  # la zona di partenza ha almeno il boss stampato
    dati = mappa_to_dict()
    attesi = dict(mappa.piano.tipi)
    for ent, _m in list(esper.get_component(Mappa)):
        esper.delete_entity(ent, immediate=True)
    mappa_da_dict(dati)
    _e, mappa = mappa_corrente()
    assert mappa.piano.tipi == attesi


def test_save_storico_senza_tipi_migra_a_normale(mondo_isolato) -> None:
    from motore.mappa import Mappa, mappa_da_dict, mappa_to_dict

    _arma_mondo()
    dati = mappa_to_dict()
    dati.pop("tipi")  # il save scritto prima dei tipi
    for ent, _m in list(esper.get_component(Mappa)):
        esper.delete_entity(ent, immediate=True)
    mappa_da_dict(dati)
    _e, mappa = mappa_corrente()
    assert mappa.piano.tipi == {}
    assert tipo_stanza_corrente() is TipoStanza.NORMALE


# --- Il fascicolo: il GM riceve il tipo (e lo narra, mai lo sceglie) -------------

def test_fascicolo_porta_il_tipo_solo_se_non_normale(mondo_isolato) -> None:
    from motore import MemoriaTurni, componi_fascicolo
    from motore.gm import sezione_fascicolo

    _arma_mondo()
    _e, mappa = mappa_corrente()
    zona = zona_corrente()
    assert zona is not None and e_di_spina(zona, 1)

    boss = stanza_boss_di(zona, mappa.piano)
    mappa.stanza_corrente = boss
    fascicolo = componi_fascicolo(MemoriaTurni())
    assert fascicolo.stanza_tipo == TipoStanza.BOSS.value
    assert "[fascicolo/stanza] tipo: boss" in sezione_fascicolo(fascicolo)

    mappa.stanza_corrente = mappa.piano.partenza  # NORMALE: la riga non c'è
    fascicolo = componi_fascicolo(MemoriaTurni())
    assert fascicolo.stanza_tipo == ""
    assert "[fascicolo/stanza]" not in sezione_fascicolo(fascicolo)


def test_safe_a_pescata_nei_vicoli_laterali(mondo_isolato, monkeypatch) -> None:
    """Il ramo `prob_safe` delle zone LATERALI (il premio del vicolo): con la
    foglia a 1 la sorella stampa una safe room, con la foglia a 0 mai. È
    l'unico ramo di `_stampa_tipi_zona` che le garanzie di spina non toccano."""
    from motore import calibrazione as cal
    from motore import zone_laterali

    _arma_mondo()
    laterali = zone_laterali(1)
    assert laterali, "il territorio sintetico deve offrire almeno una sorella"
    vicolo = laterali[0]

    monkeypatch.setattr(cal, "STANZE_PROB_SAFE_LATERALE", 1.0)
    rigenera_mappa_zona(1, vicolo)
    _e, mappa = mappa_corrente()
    assert TipoStanza.SAFE_ROOM in mappa.piano.tipi.values()

    monkeypatch.setattr(cal, "STANZE_PROB_SAFE_LATERALE", 0.0)
    rigenera_mappa_zona(1, vicolo)
    _e, mappa = mappa_corrente()
    assert TipoStanza.SAFE_ROOM not in mappa.piano.tipi.values()


def test_save_futuro_con_tipo_ignoto_degrada_a_normale(mondo_isolato) -> None:
    """Regressione H-12 (review 2026-08-11): un valore di tipo fuori vocabolario
    (save di versione futura, file editato) non deve MAI far crashare il load a
    World già ricostruito — degrada ad assente (= NORMALE), gli altri tipi
    restano."""
    from motore.mappa import Mappa, mappa_da_dict, mappa_to_dict

    _arma_mondo()
    dati = mappa_to_dict()
    validi = dict(dati["tipi"])
    dati["tipi"]["0"] = "sala_ologrammi"  # vocabolario di domani
    for ent, _m in list(esper.get_component(Mappa)):
        esper.delete_entity(ent, immediate=True)
    mappa_da_dict(dati)  # niente ValueError: degrado, non crash
    _e, mappa = mappa_corrente()
    assert tipo_di(mappa.piano, 0) is TipoStanza.NORMALE
    assert {str(k): v.value for k, v in mappa.piano.tipi.items()} == validi
