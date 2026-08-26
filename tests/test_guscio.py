"""Macchina-guscio e ciclo vita cross-World (E-1…E-9). Headless, nell'arnia.

Questi test gestiscono i contesti World **tramite il guscio** (default ⇄ "run"), quindi
NON usano la fixture `mondo_isolato` (che isola un singolo World): usano `guscio_pulito`,
che parcheggia nel default e ripulisce "run" attorno a ogni test.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import esper
import pytest

from contracts import (
    BusEventi,
    CombatResolved,
    EncounterStarted,
    MortePersonaggio,
    PlayerDiscende,
    StatId,
)
from guscio import NOME_DEFAULT, NOME_RUN, Guscio, StatoGuscio, Terminale
from motore import MessaggioIntento, leggi_fase, Fase, mappa_corrente, protagonista, stat_eff
from motore.persistenza.disco import path_stato

_SRC = Path(__file__).resolve().parents[1] / "src"


@pytest.fixture
def guscio_pulito():
    """Parcheggia nel default e ripulisce il contesto "run" attorno al test."""
    esper.switch_world(NOME_DEFAULT)
    esper.clear_database()
    if NOME_RUN in esper.list_worlds():
        esper.delete_world(NOME_RUN)
    yield
    esper.switch_world(NOME_DEFAULT)
    if NOME_RUN in esper.list_worlds():
        esper.delete_world(NOME_RUN)
    esper.clear_database()


# --- Driver di prova (conducenti host-agnostici di un turno) ------------------

def _uccidi(g: Guscio) -> None:
    _pe, _m, scheda = protagonista()
    scheda.punti_vita = 0  # il death-check (seeded) emette MortePersonaggio


def _scendi(g: Guscio) -> None:
    # Il gate di discesa richiede la SCALA nella stanza corrente (mappa): il conducente
    # di prova si porta sulla scala, poi emette l'intento.
    trovata = mappa_corrente()
    if trovata is not None:
        _ent, mappa = trovata
        mappa.stanza_corrente = next(iter(mappa.piano.discese))
    esper.create_entity(MessaggioIntento(PlayerDiscende()))  # SistemaDiscesa → DiscesaPiano


def _esci(g: Guscio) -> None:
    g.esci_volontariamente()


# --- E-9: bus uno, process-global, costruito al boot, sopravvive ai run-World --

def test_E9_bus_process_global_sopravvive_ai_run_world(guscio_pulito, tmp_path) -> None:
    g = Guscio(tmp_path)
    bus_al_boot = g.bus
    assert isinstance(bus_al_boot, BusEventi)
    # Dopo un giro di run completo, è lo STESSO bus (non muore/ricrea col run-World).
    asyncio.run(g.gioca_nuova_partita(_esci, uuid="x"))
    assert g.bus is bus_al_boot


def test_E9_handler_in_run_deregistrati_al_teardown(guscio_pulito, tmp_path) -> None:
    g = Guscio(tmp_path)
    g.nuova_partita(uuid="carl")
    assert g._coppie_in_run, "gli handler in-run devono essere registrati durante la run"
    g._terminale = Terminale.USCITA_VOLONTARIA
    g.concludi()
    # Al teardown gli handler in-run sono deregistrati; il bus sopravvive vuoto di run.
    assert g._coppie_in_run == []


# --- E-5: il protagonista nasce/deserializza SOLO al confine guscio→run --------

def test_E5_protagonista_nasce_al_confine_non_a_una_fase(guscio_pulito, tmp_path) -> None:
    g = Guscio(tmp_path)
    assert g.stato == StatoGuscio.MENU
    g.nuova_partita(uuid="carl", destrezza=11)
    # Nato esattamente all'ingresso run, nel contesto "run".
    assert esper.current_world == NOME_RUN
    pe, marker, _scheda = protagonista()
    assert marker.id_dominio == "carl" and stat_eff(pe, StatId.DESTREZZA) == 11
    g._terminale = Terminale.USCITA_VOLONTARIA
    g.concludi()


def test_E5_carica_fallito_resta_nel_menu_senza_toccare_il_world(guscio_pulito, tmp_path) -> None:
    # Caricamento di un save inesistente: valida PRIMA di switchare → resta nel MENU,
    # `current_world` intatto, nessun "run" creato (E-4/H-12 al confine guscio→run).
    g = Guscio(tmp_path)
    prima = esper.current_world
    assert g.carica("inesistente") is False
    assert g.stato == StatoGuscio.MENU
    assert esper.current_world == prima == NOME_DEFAULT
    assert NOME_RUN not in esper.list_worlds()


def test_E5_caricamento_deserializza_al_confine(guscio_pulito, tmp_path) -> None:
    g = Guscio(tmp_path)
    # Crea e salva uno slot via uscita volontaria.
    asyncio.run(g.gioca_nuova_partita(_esci, uuid="bob", destrezza=9))
    assert path_stato(tmp_path, "bob").exists()
    # Caricamento: il protagonista è deserializzato al confine guscio→run.
    assert g.carica("bob") is True
    assert esper.current_world == NOME_RUN
    pe, marker, _scheda = protagonista()
    assert marker.id_dominio == "bob" and stat_eff(pe, StatId.DESTREZZA) == 9
    g._terminale = Terminale.USCITA_VOLONTARIA
    g.concludi()


# --- E-6: teardown = switch_world(default) POI delete_world("run") -------------

def test_E6_teardown_torna_al_default_ed_elimina_run(guscio_pulito, tmp_path) -> None:
    g = Guscio(tmp_path)
    g.nuova_partita(uuid="carl")
    assert NOME_RUN in esper.list_worlds()
    g._terminale = Terminale.USCITA_VOLONTARIA
    g.concludi()
    # Dopo il teardown: parcheggiati nel default, "run" eliminato (mai delete del attivo).
    assert esper.current_world == NOME_DEFAULT
    assert NOME_RUN not in esper.list_worlds()


def test_E6_un_solo_run_world_vivo(guscio_pulito, tmp_path) -> None:
    g = Guscio(tmp_path)
    asyncio.run(g.gioca_nuova_partita(_esci, uuid="a"))
    asyncio.run(g.gioca_nuova_partita(_esci, uuid="b"))
    # "run" viene ricreato fresco ogni volta: mai due run-World residenti.
    assert esper.list_worlds().count(NOME_RUN) <= 1


# --- E-3: lo stato del guscio NON si serializza col save -----------------------

def test_E3_stato_guscio_non_nel_save(guscio_pulito, tmp_path) -> None:
    import json

    g = Guscio(tmp_path)
    asyncio.run(g.gioca_nuova_partita(_esci, uuid="carl"))
    intest, corpo = path_stato(tmp_path, "carl").read_text(encoding="utf-8").split("\n")[:2]
    blob = (intest + corpo).lower()
    # Nessuna traccia dello stato della macchina-guscio nel blob salvato.
    for parola in ("statoguscio", "in_run", "guscio", "terminale", "menu"):
        assert parola not in blob, f"stato di guscio trapelato nel save: {parola}"
    # Il blob contiene il run-World (FaseCorrente fra i componenti).
    tag = [c["tag"] for ent in json.loads(corpo)["entita"] for c in ent["componenti"]]
    assert "fase_corrente" in tag


# --- E-7: stato del guscio = orchestrazione app, non un World/Processor ---------

def test_E7_guscio_non_e_un_world_ne_un_processor(guscio_pulito, tmp_path) -> None:
    g = Guscio(tmp_path)
    assert not isinstance(g, esper.Processor)
    # Lo stato del guscio vive su attributi dell'oggetto (orchestrazione app), non in
    # un World dedicato: nessun "World-menu" creato dal guscio.
    assert g.stato == StatoGuscio.MENU
    assert NOME_RUN not in esper.list_worlds()  # nessun World fuori dalla run


def test_E7_nessun_processor_di_guscio_definito() -> None:
    src = (_SRC / "guscio" / "macchina.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for nodo in ast.walk(tree):
        if isinstance(nodo, ast.ClassDef):
            basi = {b.id for b in nodo.bases if isinstance(b, ast.Name)}
            basi |= {b.attr for b in nodo.bases if isinstance(b, ast.Attribute)}
            assert "Processor" not in basi and "PhasedProcessor" not in basi, nodo.name


def test_E7_guscio_e_host_agnostico_niente_textual() -> None:
    # L'orchestrazione del guscio è host-agnostica (IC §6): nessun import di Textual.
    file = sorted((_SRC / "guscio").glob("*.py"))
    assert file, "src/guscio vuoto o spostato: il divieto passerebbe per vacuità"
    for py in file:
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for nodo in ast.walk(tree):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    assert alias.name.split(".")[0] != "textual", py.name
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                assert nodo.module.split(".")[0] != "textual", py.name


# --- E-8: ogni fine-run passa per la stessa cucitura; vittoria/fuga NON terminali -

def test_E8_tre_terminali_stessa_cucitura(guscio_pulito, tmp_path) -> None:
    # Sconfitta → invalida; piano-completato → invalida; uscita volontaria → salva.
    for uuid, driver, atteso in (
        ("morto", _uccidi, Terminale.SCONFITTA),
        ("vinto", _scendi, Terminale.PIANO_COMPLETATO),
        ("uscito", _esci, Terminale.USCITA_VOLONTARIA),
    ):
        g = Guscio(tmp_path)
        term = asyncio.run(g.gioca_nuova_partita(driver, uuid=uuid))
        assert term is atteso
        assert g.stato == StatoGuscio.MENU  # ogni terminale torna al menu, stessa cucitura
        # Save-wiring: i due fine-run invalidano; l'uscita volontaria salva.
        if atteso is Terminale.USCITA_VOLONTARIA:
            assert path_stato(tmp_path, uuid).exists()
        else:
            assert not path_stato(tmp_path, uuid).exists()


def test_E8_vittoria_di_scontro_torna_a_narrazione_non_e_terminale(guscio_pulito, tmp_path) -> None:
    g = Guscio(tmp_path)
    g.nuova_partita(uuid="carl")
    # CombatResolved(vittoria) è un esito di combattimento: torna a NARRAZIONE (bus),
    # NON è un terminale di run. Il guscio resta IN_RUN, nessun terminale rilevato.
    g.bus.pubblica(EncounterStarted(entita=1))
    assert leggi_fase() == Fase.COMBATTIMENTO
    g.bus.pubblica(CombatResolved(entita=1, vittoria=True))
    assert leggi_fase() == Fase.NARRAZIONE
    assert g._terminale is None
    assert g.stato == StatoGuscio.IN_RUN
    g._terminale = Terminale.USCITA_VOLONTARIA
    g.concludi()


# --- E-4: detection in-run, teardown nella shell; mai switch in un handler ------

def test_E4_handler_di_terminale_non_fa_switch_world(guscio_pulito, tmp_path) -> None:
    from motore import tick

    g = Guscio(tmp_path)
    g.nuova_partita(uuid="carl")

    # Osservatore aggiuntivo: registra in che World si gira mentre l'handler scatta.
    # Il death-check pubblica MortePersonaggio DENTRO un process(): nessuno switch deve
    # avvenire in volo (E-4) — l'handler del guscio segna solo il terminale.
    visto: list[str] = []
    osserva = lambda _ev: visto.append(esper.current_world)
    g.bus.registra(MortePersonaggio, osserva)

    _uccidi(g)
    tick()  # death-check → MortePersonaggio → (handler del guscio + osservatore)

    assert visto == [NOME_RUN]  # durante l'handler eravamo ancora nel run-World
    assert g._terminale == Terminale.SCONFITTA
    assert esper.current_world == NOME_RUN  # nessun teardown nell'handler

    g.bus.deregistra(MortePersonaggio, osserva)
    g.concludi()
    assert esper.current_world == NOME_DEFAULT  # il teardown è nella shell, DOPO


def test_E4_il_giro_completo_gira_nellarnia(guscio_pulito, tmp_path) -> None:
    # boot → nuova partita → morte → menu → carica-altro-slot.
    g = Guscio(tmp_path)
    assert g.stato == StatoGuscio.MENU  # boot → menu

    # Prepara un secondo slot su disco (uscita volontaria → salva).
    asyncio.run(g.gioca_nuova_partita(_esci, uuid="bob"))
    assert path_stato(tmp_path, "bob").exists()

    # Nuova partita "carl" che muore.
    term = asyncio.run(g.gioca_nuova_partita(_uccidi, uuid="carl"))
    assert term is Terminale.SCONFITTA
    assert g.stato == StatoGuscio.MENU
    assert not path_stato(tmp_path, "carl").exists()  # morte → invalidato

    # Carica l'altro slot.
    assert g.carica("bob") is True
    assert g.stato == StatoGuscio.IN_RUN
    _pe, marker, _scheda = protagonista()
    assert marker.id_dominio == "bob"
    g._terminale = Terminale.USCITA_VOLONTARIA
    g.concludi()


# --- E-1 / E-2: le due primitive non si scambiano; switch_world solo in H -------
#
# NB: per ESP §0.1 + ACV 3b + il piano di build (Fase 6: "livello save/load = UNICA
# autorità su current_world"), `switch_world`/`delete_world` vivono nel **livello
# save/load** (motore/persistenza), NON nel guscio. Il guscio le ORCHESTRA (decide il
# quando) chiamando le operazioni di confine di H (ACV §0: "H possiede il come"). Il
# divieto di E-2 è strutturale: mai in un Processor/handler/logica di fase.

_MODULI_SRC = sorted((_SRC).rglob("*.py"))
assert _MODULI_SRC, "src/ vuoto o spostato: i divieti passerebbero per vacuità"
_FILE_AUTORITA = _SRC / "motore" / "persistenza" / "salvataggio.py"


def _usa_primitiva_world(src: str) -> set[str]:
    """Le primitive di World effettivamente USATE (chiamate/attributi), via AST: ignora
    docstring e commenti (dove un modulo può legittimamente *nominarle*)."""
    trovate: set[str] = set()
    for nodo in ast.walk(ast.parse(src)):
        if isinstance(nodo, ast.Attribute) and nodo.attr in ("switch_world", "delete_world"):
            trovate.add(nodo.attr)
        elif isinstance(nodo, ast.Name) and nodo.id in ("switch_world", "delete_world"):
            trovate.add(nodo.id)
    return trovate


def test_E2_switch_world_solo_nel_livello_save_load() -> None:
    # `switch_world`/`delete_world` USATI in UN SOLO file: il livello save/load (H),
    # unica autorità su current_world (ESP §0.1). Da nessun'altra parte — né guscio, né
    # sistemi del motore, né membrana.
    offese: list[str] = []
    for py in _MODULI_SRC:
        usate = _usa_primitiva_world(py.read_text(encoding="utf-8"))
        if usate and py != _FILE_AUTORITA:
            offese.append(f"{py.relative_to(_SRC)}: {sorted(usate)}")
    assert not offese, "switch_world/delete_world fuori dal livello save/load:\n" + "\n".join(offese)
    # E l'autorità le usa davvero (non è un file vuoto).
    assert _usa_primitiva_world(_FILE_AUTORITA.read_text(encoding="utf-8")) == {"switch_world", "delete_world"}


def test_E2_switch_world_non_in_un_processor_o_handler() -> None:
    # Nel guscio, nessun metodo (in particolare gli handler di terminale) usa le
    # primitive di World: il guscio DELEGA a H, non switcha mai di persona.
    src = (_SRC / "guscio" / "macchina.py").read_text(encoding="utf-8")
    assert _usa_primitiva_world(src) == set()


def test_E1_le_due_primitive_non_si_scambiano() -> None:
    # (a) Le fasi NARRAZIONE⇄COMBATTIMENTO NON usano switch_world: la transizione di
    #     fase è una scrittura di FaseCorrente sul bus (intra-run).
    fase_src = (_SRC / "motore" / "fase.py").read_text(encoding="utf-8")
    run_src = (_SRC / "motore" / "run.py").read_text(encoding="utf-8")
    assert not _usa_primitiva_world(fase_src) and not _usa_primitiva_world(run_src)

    # (b) L'ingresso/uscita dalla run usa switch_world (in H, l'autorità), NON un evento
    #     di bus; il guscio lo orchestra chiamando le operazioni di confine di H.
    guscio_src = (_SRC / "guscio" / "macchina.py").read_text(encoding="utf-8")
    for op in ("entra_run_nuova", "carica_crawler", "teardown_run"):
        assert op in guscio_src, f"il guscio deve delegare a H l'operazione di confine {op}"
