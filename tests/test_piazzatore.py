"""Il PIAZZATORE PNG (P1, docs/future/piazzatore-png.md).

Le regole bloccate qui:
- Lo SLOT decide la categoria (canone DCC): manager nel bagno, maestro nelle
  gilde; la stanza senza slot non riceve interpellabili — il vincolo del
  playtest giro 3 (mai un PNG a funzione dietro un custode) è strutturale.
- La pescata è SEEDED e affine (tag del piano), il piazzamento IDEMPOTENTE
  (il rientro non duplica) e un personaggio esiste UNA volta.
- Il fascicolo GM VEDE il PNG (B1) e al reveal riceve la sua scena autorata
  (B6); l'archetipo fuori registry è un rifiuto dichiarato, mai un KeyError
  (B3); il roster si riempie dalla libreria per affinità (B2).
"""

from __future__ import annotations

import asyncio
import dataclasses
import random

import esper

from contracts import Durata, Grado, RuoloMob, TipoStanza
from main import costruisci_sessione


def _attivo(slug, nome, categoria, tags=(), archetipo="zombie", elite=False):
    from motore import MobAttivo

    return MobAttivo(
        slug=slug, nome=nome, archetipo=archetipo, grado=Grado.BRONZO,
        blocchi=[], descrizione="Cataloga ogni cosa.",
        prosa_stanza="Timbra una scheda senza guardarti.", durata=Durata.TURNO,
        tags=list(tags), categoria=categoria,
        voce="burocratese: frasi da modulo", elite=elite,
    )


def _sessione_con_roster(mobs, seed: int = 1, directory=None):
    """Sessione avviata + roster PNG del piano 1 SOSTITUITO (il congelato si
    rimpiazza col gemello: componente frozen → replace + add_component) + slot
    seeded della zona NEUTRALIZZATI (i test governano i propri slot)."""
    from motore import StagioneAttiva, mappa_corrente
    from motore.piazzatore import SLOT_CATEGORIA

    kwargs = dict(seed=seed)
    if directory is not None:
        kwargs.update(directory=directory, nome="Carl")
    sessione = costruisci_sessione(**kwargs)
    asyncio.run(sessione.prossima_narrazione())
    ent, stagione = esper.get_component(StagioneAttiva)[0]
    piani = list(stagione.piani)
    piani[0] = dataclasses.replace(piani[0], png=list(mobs))
    esper.add_component(ent, dataclasses.replace(stagione, piani=piani))
    mappa = mappa_corrente()[1]
    for stanza, tipo in list(mappa.piano.tipi.items()):
        if tipo in SLOT_CATEGORIA:
            mappa.piano.tipi[stanza] = TipoStanza.NORMALE
    return sessione


def _stanza_con_slot(tipo: TipoStanza) -> int:
    """Assegna `tipo` a una stanza libera (né partenza, né tipizzata, né con
    ostili) della zona corrente e la ritorna."""
    from motore import mappa_corrente

    mappa = mappa_corrente()[1]
    for stanza in sorted(mappa.piano.adiacenze):
        if (stanza != mappa.piano.partenza and stanza not in mappa.piano.tipi
                and stanza not in mappa.mob_stanza):
            mappa.piano.tipi[stanza] = tipo
            return stanza
    raise AssertionError("nessuna stanza libera nella zona di prova")


def _piazza():
    from motore import piazza_png_di_zona
    from motore.piano import livello_corrente
    from motore.territorio import zona_corrente

    return piazza_png_di_zona(livello_corrente(), zona_corrente())


# --- Lo slot, l'idempotenza, l'unicità ------------------------------------------

def test_il_manager_si_piazza_nel_bagno_una_volta_sola(run_pulita) -> None:
    from motore import EntitaMob
    from motore.territorio import zona_corrente

    _sessione_con_roster([_attivo("m-vero", "Il Manager Vero", "manager")])
    bagno = _stanza_con_slot(TipoStanza.BAGNO)
    piazzati = _piazza()
    assert len(piazzati) == 1, "un candidato, uno slot: un piazzamento"
    em = esper.component_for_entity(piazzati[0], EntitaMob)
    assert em.stanza == bagno and em.categoria == "manager"
    assert em.ruolo is RuoloMob.PNG, "il piazzato non è mai un nemico"
    assert em.zona == zona_corrente().chiave, "l'ancora di zona viaggia col piazzato"
    assert _piazza() == [], "il rientro è un no-op: il personaggio esiste già"


def test_lo_slot_rifiuta_la_categoria_sbagliata(run_pulita) -> None:
    """Il maestro non sta nel bagno, il manager non insegna in gilda — e la
    stanza NORMALE non riceve interpellabili: il vincolo giro-3 è strutturale."""
    _sessione_con_roster([_attivo("g-uno", "Il Maestro", "maestro_gilda")])
    _stanza_con_slot(TipoStanza.BAGNO)
    assert _piazza() == [], "bagno = slot manager: il maestro resta in libreria"


def test_il_maestro_si_piazza_in_gilda(run_pulita) -> None:
    from motore import EntitaMob

    _sessione_con_roster([_attivo("g-uno", "Il Maestro", "maestro_gilda")])
    gilda = _stanza_con_slot(TipoStanza.GILDA_TUTORIAL)
    piazzati = _piazza()
    assert len(piazzati) == 1
    assert esper.component_for_entity(piazzati[0], EntitaMob).stanza == gilda


# --- La pescata: affine e seeded -------------------------------------------------

def test_la_pescata_e_affine_e_a_parita_seeded(run_pulita) -> None:
    from motore.piazzatore import _pesca_affine

    affine = _attivo("a-alfa", "Alfa", "manager", tags=["nascondino"])
    neutro = _attivo("b-beta", "Beta", "manager")
    assert _pesca_affine([neutro, affine], ["nascondino"], random.Random(1)) is affine, (
        "il tag del piano decide: l'affine vince sul neutro"
    )
    terzo = _attivo("c-gamma", "Gamma", "manager")
    prima = _pesca_affine([neutro, terzo], ["nascondino"], random.Random(5))
    seconda = _pesca_affine([neutro, terzo], ["nascondino"], random.Random(5))
    assert prima is seconda, "a parità di punteggio decide il seed, non il caso"


# --- Il fascicolo vede il PNG (B1) e la sua scena (B6) ---------------------------

def test_il_fascicolo_vede_il_png_e_al_reveal_la_sua_scena(run_pulita) -> None:
    from motore import mappa_corrente
    from motore.gm import componi_fascicolo, sezione_fascicolo

    sessione = _sessione_con_roster([_attivo("m-vero", "Il Manager Vero", "manager")])
    bagno = _stanza_con_slot(TipoStanza.BAGNO)
    assert len(_piazza()) == 1
    mappa_corrente()[1].stanza_corrente = bagno  # teletrasporto di laboratorio
    testo = sezione_fascicolo(componi_fascicolo(sessione.memoria))
    assert "[fascicolo/png]" in testo and "Il Manager Vero" in testo, (
        "il fascicolo era CIECO sui PNG: il GM deve ricevere chi c'è in stanza"
    )
    assert "Parlamenta" in testo, "la regia distingue l'interpellabile"
    assert "[fascicolo/png/scena]" in testo and "Timbra una scheda" in testo, (
        "al reveal la prosa autorata del PNG è il materiale di scena"
    )


# --- Le falle dello stress-test (F1/F2/F3) ---------------------------------------

def test_la_stanza_del_maestro_non_spawna_ostili_al_reveal(run_pulita) -> None:
    """F1: le gilde NON sono quiete — il reveal materializzava un ostile
    DAVANTI al maestro appena piazzato (vincolo giro-3 violato dal motore
    stesso). Ora la stanza dell'interpellabile è riservata: nessun ostile al
    reveal, la voce Parlamenta si compone."""
    from contracts import TipoAzione
    from motore import mappa_corrente, mob_corrente

    sessione = _sessione_con_roster([_attivo("g-uno", "Il Maestro", "maestro_gilda")])
    gilda = _stanza_con_slot(TipoStanza.GILDA_TUTORIAL)
    assert len(_piazza()) == 1
    mappa_corrente()[1].stanza_corrente = gilda
    snap = asyncio.run(sessione.prossima_narrazione())  # il reveal offline
    assert mob_corrente() is None, (
        "il reveal ha materializzato un ostile nella stanza del maestro"
    )
    assert any(o.tipo is TipoAzione.PARLAMENTA for o in snap.opzioni), (
        "il maestro deve essere interpellabile nella SUA stanza"
    )


def test_il_png_di_un_altro_piano_non_e_un_fantasma(run_pulita) -> None:
    """F2: le chiavi di zona si RIPETONO tra piani e la discesa non elimina i
    PNG del piano lasciato — il manager del piano 1 era un interpellabile
    fantasma nella zona omonima del piano 2. Il sensore filtra per livello."""
    from motore import mappa_corrente
    from motore.mappa import png_in_stanza_corrente
    from motore.piano import ProfonditaPiano

    _sessione_con_roster([_attivo("m-vero", "Il Manager Vero", "manager")])
    bagno = _stanza_con_slot(TipoStanza.BAGNO)
    assert len(_piazza()) == 1
    mappa_corrente()[1].stanza_corrente = bagno
    assert png_in_stanza_corrente() is not None, "sul SUO piano il PNG si vede"
    esper.get_component(ProfonditaPiano)[0][1].livello = 2  # discesa di laboratorio
    assert png_in_stanza_corrente() is None, (
        "il PNG del piano 1 è visibile sul piano 2: collisione di chiavi zona"
    )


def test_il_personaggio_non_sta_nel_vivaio_ostile(run_pulita) -> None:
    """F3: un interpellabile nel cast/spawn/boss esisterebbe DUE volte (ostile
    del reveal E piazzabile dal roster): errore di authoring al risolutore."""
    import pytest
    from contracts import Grado as G
    from contracts.contenuti import BudgetDesign, MobAsset, PianoRisolto

    manager = MobAsset.model_validate(dict(
        slug="manager-in-cast", nome="Il Manager", archetipo="zombie",
        grado="bronzo", prosa_stanza="Sorride da un contratto.",
        categoria="manager", voce="contrattuale: clausole recitate a voce",
    ))
    budget = BudgetDesign(gradi=[G.BRONZO], archetipi=["zombie"])
    with pytest.raises(ValueError, match="personaggio"):
        PianoRisolto(slug="p-prova", versione=1, titolo="T", tema="t",
                     budget=budget, cast=[manager])


def test_il_giro_di_zona_non_duplica_il_piazzato(run_pulita) -> None:
    """Il percorso VERO del rientro (fotografa → despawn → rimonta, che
    ri-lancia il piazzatore dentro `rigenera_mappa_zona`): il manager resta
    UNO — l'idempotenza regge il ciclo completo, non solo la doppia chiamata."""
    from motore import EntitaMob
    from motore.piano import livello_corrente
    from motore.territorio import (
        _despawna_mob_di_zona,
        _fotografa_vivi_di_zona,
        rigenera_mappa_zona,
        zona_corrente,
        zona_da_chiave,
    )

    _sessione_con_roster([_attivo("m-vero", "Il Manager Vero", "manager")])
    _stanza_con_slot(TipoStanza.BAGNO)
    assert len(_piazza()) == 1
    chiave = zona_corrente().chiave
    _fotografa_vivi_di_zona()
    _despawna_mob_di_zona()
    rigenera_mappa_zona(livello_corrente(), zona_da_chiave(chiave))
    superstiti = [em for _e, em in esper.get_component(EntitaMob)
                  if em.nome == "Il Manager Vero"]
    assert len(superstiti) == 1, (
        f"il giro di zona doveva lasciare UN manager, trovati {len(superstiti)}"
    )


# --- F4: la gilda si stampa (senza stampa, lo slot del maestro non esiste mai) ---

def test_la_gilda_si_stampa_sui_primi_piani(run_pulita) -> None:
    """F4 (playtest 2026-08-17): `stampa_tipi` non stampava MAI le gilde — il
    piazzatore era verde nei lucchetti (slot a mano) e MORTO in partita, con
    la lore di stagione che promette gilde «disseminate nei piani da 1 a 3».
    Ora: pescata `prob_gilda` in CODA allo stream (a 0 = stampe storiche
    byte-identiche), al più una, mai su partenza/scala/boss."""
    from motore.mappa import genera_topologia, stampa_tipi

    piano = genera_topologia(random.Random(1), 6)
    stampa_tipi(piano, random.Random(1), boss=3, prob_gilda=1.0)
    gilde = [s for s, t in piano.tipi.items() if t is TipoStanza.GILDA_TUTORIAL]
    assert len(gilde) == 1, "prob 1.0: esattamente una gilda"
    assert gilde[0] not in {piano.partenza, 3} | set(piano.discese), (
        "la gilda non sta su partenza, boss o scala"
    )
    spento = genera_topologia(random.Random(1), 6)
    stampa_tipi(spento, random.Random(1), boss=3, prob_gilda=0.0)
    assert all(t is not TipoStanza.GILDA_TUTORIAL for t in spento.tipi.values()), (
        "a prob 0 (piani oltre STANZE.gilda_fino_al_piano) la gilda non si stampa"
    )


def test_l_archivista_entra_in_partita_dal_solo_seed(run_pulita) -> None:
    """L'oracolo del playtest: seed 9, zona d'ingresso del pianoterra — la
    gilda si stampa e l'archivista ci viene piazzato DAVVERO (niente slot di
    laboratorio, niente roster finto: stagione-1 com'è). Se questo lucchetto
    si rompe cambiando le tarature §11, il canale in partita è da riprovare."""
    from motore import EntitaMob

    sessione = costruisci_sessione(seed=9)
    asyncio.run(sessione.prossima_narrazione())
    png = [em for _e, em in esper.get_component(EntitaMob)
           if em.ruolo is RuoloMob.PNG]
    assert any(em.nome == "L'Archivista del Sesto" for em in png), (
        "seed 9 doveva piazzare l'archivista nella gilda della zona d'ingresso"
    )


# --- Le guardie e il roster ------------------------------------------------------

def test_l_archetipo_ignoto_e_un_rifiuto_dichiarato(run_pulita) -> None:
    """La mina #7 del rilievo: KeyError a valle — ora `None`, come il gate
    Elité (si salta, mai un crash)."""
    from motore import materializza_png

    _sessione_con_roster([])
    fantasma = _attivo("x-ignoto", "X", "manager", archetipo="archetipo-inesistente")
    assert materializza_png(fantasma, 1, 0) is None


def test_il_roster_si_riempie_dalla_libreria_per_affinita(run_pulita) -> None:
    """B2: il risolutore pesca dalla libreria i personaggi (categoria ≠
    ordinario, o Elité) affini ai tag del piano — l'archivista (nascondino,
    non-morti) entra nel roster del pianoterra senza una riga di authoring."""
    from main import risolvi_stagione

    risolta = risolvi_stagione("stagione-1")
    assert any(m.slug == "archivista-del-sesto" for m in risolta.piani[0].png), (
        "l'affinità di tag doveva portare l'archivista nel roster del piano 1"
    )
    assert all(not m.elite or m.slug for m in risolta.piani[0].png)  # roster ben formato


def test_il_piazzato_round_trippa_nel_save(run_pulita, tmp_path) -> None:
    from main import carica_sessione
    from motore import EntitaMob

    sessione = _sessione_con_roster(
        [_attivo("m-vero", "Il Manager Vero", "manager")], directory=tmp_path,
    )
    _stanza_con_slot(TipoStanza.BAGNO)
    assert len(_piazza()) == 1
    sessione.salva()
    uuid = sessione.uuid
    sessione.esci()
    carica_sessione(uuid=uuid, directory=tmp_path)
    nomi = {em.nome for _e, em in esper.get_component(EntitaMob)
            if em.ruolo is RuoloMob.PNG}
    assert "Il Manager Vero" in nomi, "il piazzato deve sopravvivere al load"
