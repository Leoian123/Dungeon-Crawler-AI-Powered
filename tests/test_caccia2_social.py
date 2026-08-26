"""Lucchetti della caccia-2 (2026-08-16, sera): i reperti confermati sulla
superficie social appena costruita e sui suoi incroci. Come sempre: il test è
l'exploit o il sintomo, mai l'esistenza del meccanismo.
"""

from __future__ import annotations

import asyncio

import esper

from contracts import Grado, PlayerChoseOption, RuoloMob, StatId, TipoAzione
from main import costruisci_sessione


def _carisma(valore: int) -> None:
    from motore.scheda import protagonista
    from motore.statistiche import Primarie

    pent, _m, _s = protagonista()
    esper.component_for_entity(pent, Primarie).valori[StatId.CARISMA] = valore


# --- Save legacy: il crawler non nasce muto --------------------------------------

def test_il_save_legacy_ripara_il_carisma_al_load(run_pulita, tmp_path) -> None:
    """Un save scritto prima della primaria CARISMA la reintegra al load dal
    profilo-base §11 — senza, il vecchio crawler pescava il floor 1 e falliva
    OGNI parlamento (soglia bronzo 6), bruciando il tentativo unico per mob."""
    from main import carica_sessione
    from motore.scheda import protagonista
    from motore.statistiche import Primarie, stat_eff

    sessione = costruisci_sessione(seed=1, directory=tmp_path, nome="Vecchio")
    asyncio.run(sessione.prossima_narrazione())
    # Il save di IERI: il vettore non conosce carisma.
    pent, _m, _s = protagonista()
    del esper.component_for_entity(pent, Primarie).valori[StatId.CARISMA]
    sessione.salva()
    uuid = sessione.uuid
    sessione.esci()
    ripresa = carica_sessione(uuid=uuid, directory=tmp_path)
    assert ripresa is not None
    pent, _m, _s = protagonista()
    from motore.calibrazione import PRIMARIE_BASE_CARL

    assert stat_eff(pent, StatId.CARISMA) == PRIMARIE_BASE_CARL[StatId.CARISMA], (
        "il crawler legacy è muto: carisma al floor invece che al profilo-base"
    )


def test_la_riparazione_non_sovrascrive_le_stat_personalizzate(run_pulita, tmp_path) -> None:
    from main import carica_sessione
    from motore.scheda import protagonista
    from motore.statistiche import Primarie

    sessione = costruisci_sessione(seed=1, directory=tmp_path, nome="Tarato")
    asyncio.run(sessione.prossima_narrazione())
    pent, _m, _s = protagonista()
    prim = esper.component_for_entity(pent, Primarie)
    prim.valori[StatId.DESTREZZA] = 17    # la build del giocatore
    del prim.valori[StatId.CARISMA]
    sessione.salva()
    uuid = sessione.uuid
    sessione.esci()
    carica_sessione(uuid=uuid, directory=tmp_path)
    pent, _m, _s = protagonista()
    prim = esper.component_for_entity(pent, Primarie)
    assert prim.valori[StatId.DESTREZZA] == 17, (
        "la riparazione ha sovrascritto una stat personalizzata del save"
    )


# --- Zone-hop: l'anti-pesca sociale sopravvive alla rimaterializzazione ---------

def test_il_parlamento_speso_sopravvive_al_giro_di_zona(run_pulita) -> None:
    """L'exploit confermato: tentativo speso → esci dalla zona → rientra — il
    mob rimaterializzato dal seed NON torna parlamentabile (il marker viaggia
    nella fotografia dello StatoTerritorio, come i vivi)."""
    from contracts import TierTerritorio
    from motore import EntitaMob, StatoTerritorio, Zona, tenta_parlamento
    from motore.scena import puo_parlamentare
    from motore.territorio import _fotografa_vivi_di_zona, _rimaterializza_vivi

    sessione = costruisci_sessione(seed=1)
    asyncio.run(sessione.prossima_narrazione())
    _carisma(1)
    from motore import mob_corrente, stato_territorio

    mob = mob_corrente()
    em = esper.component_for_entity(mob, EntitaMob)
    stanza_del_mob = em.stanza
    esito = tenta_parlamento(mob)
    assert esito is not None and not esito.riuscito
    stato = stato_territorio()
    assert stato is not None
    zona = stato.zona_corrente
    # Il giro di zona: fotografa → despawn → rimaterializza (le stesse tre
    # mosse dell'attraversamento, senza il viaggio).
    _fotografa_vivi_di_zona()
    assert stanza_del_mob in stato.parlamenti_spesi.get(zona, []), (
        "la fotografia non registra il tentativo speso"
    )
    esper.delete_entity(mob, immediate=True)
    from motore.territorio import zona_da_chiave
    from motore.piano import livello_corrente

    _rimaterializza_vivi(livello_corrente(), zona_da_chiave(zona), stato)
    rinato = mob_corrente()
    assert rinato is not None, "il vivo fotografato deve tornare"
    assert not puo_parlamentare(rinato), (
        "il mob rimaterializzato ha dimenticato il rifiuto: anti-pesca aggirata"
    )


# --- La scena conclusa si consuma e lascia memoria ------------------------------

def test_i_fatti_scena_si_consumano_al_primo_turno_fresco(run_pulita) -> None:
    """La conversazione chiusa si narra UNA volta: il reveal fresco successivo
    non deve ri-iniettare [fascicolo/esito-scena] all'infinito."""
    from contracts import FattiScena, EsitoScena

    sessione = costruisci_sessione(seed=1)
    asyncio.run(sessione.prossima_narrazione())
    sessione._fatti_scena = FattiScena(
        partecipanti=("Il Fante",), esito=EsitoScena.CONCLUSA,
        posta="", battute=3, momenti=(),
    )
    # Un turno GM fresco (azione libera: sempre non-cache) consuma ENTRAMBI i gemelli.
    riepilogo = sessione.riepiloga_azione("mi guardo intorno")
    asyncio.run(sessione.esegui_azione(riepilogo))
    assert sessione._fatti_scena is None and sessione._fatti_scontro is None


def test_la_chiusura_offline_scrive_la_memoria(run_pulita) -> None:
    """La scena chiusa d'ufficio al 2° muto lascia il documento INTERAZIONE
    (con le ancore piano/tick): offline ogni scena spariva dal ricordo."""
    from contracts import TipoDocumento

    sessione = costruisci_sessione(seed=1)
    snap = asyncio.run(sessione.prossima_narrazione())
    _carisma(40)
    indice = next(o.indice for o in snap.opzioni if o.tipo is TipoAzione.PARLAMENTA)
    sessione.coda.accoda(PlayerChoseOption(indice))
    assert sessione.avanza().scena_aperta
    asyncio.run(sessione.battuta_parlamento("Ehi."))
    asyncio.run(sessione.battuta_parlamento("Mi senti?"))  # 2° muto: chiude
    assert not sessione.avanza().scena_aperta
    documenti = [d for d in sessione.memoria_lunga.recupera("Fante", limite=5)
                 if d.tipo is TipoDocumento.INTERAZIONE and d.id.startswith("scena-")]
    assert documenti, "la chiusura d'ufficio non ha scritto il documento INTERAZIONE"
    assert documenti[0].piano >= 1 and documenti[0].tick >= 1, (
        "il documento-scena è senza ancore piano/tick (il gemello dialogo-* le ha)"
    )
    assert "carisma" in documenti[0].testo, (
        "la riga-fatto del parlamento riuscito non è nel ricordo"
    )


# --- Il PNG resta nella SUA zona ------------------------------------------------

def test_il_png_non_appare_nella_zona_sbagliata(run_pulita) -> None:
    """Gli indici di stanza sono per-zona: il PNG materializzato nella spina
    non deve farsi trovare nella laterale alla stanza di pari indice."""
    from motore import EntitaMob, png_in_stanza_corrente, stato_territorio
    from motore.mappa import mappa_corrente

    sessione = costruisci_sessione(seed=1)
    asyncio.run(sessione.prossima_narrazione())
    stato = stato_territorio()
    m = mappa_corrente()
    stanza = m[1].stanza_corrente
    png = esper.create_entity(EntitaMob(
        archetipo="zombie", grado=Grado.BRONZO, nome="Maestro Kettle",
        descrizione="insegna a sopravvivere", livello=1, stanza=stanza,
        ruolo=RuoloMob.PNG, categoria="maestro_gilda", voce="brusco, frasi corte",
        zona=stato.zona_corrente,
    ))
    assert png_in_stanza_corrente() == png, "nella SUA zona si trova"
    # Il cambio zona senza spostare il PNG: la chiave corrente cambia.
    stato.zona_corrente = "quartiere:0/0/0/0/1"
    assert png_in_stanza_corrente() is None, (
        "il PNG è stato trovato in un'altra zona alla stanza di pari indice"
    )


# --- La TUI esce dal modo-scena con la scena ------------------------------------

def test_la_tui_esce_dal_modo_scena_su_azione_di_menu() -> None:
    """L'exploit confermato: Parlamenta → Combatti → la TUI restava in
    modo-scena e l'Invio successivo crashava l'app (RuntimeError → panic)."""
    import pytest

    pytest.importorskip("textual")
    import gioco_textual
    from textual.widgets import Input

    async def run() -> None:
        sessione = costruisci_sessione(seed=1)
        app = gioco_textual._costruisci_app(sessione)
        async with app.run_test() as pilot:
            await pilot.pause()
            _carisma(40)
            snap = sessione.avanza()
            indice = next(o.indice for o in snap.opzioni
                          if o.tipo is TipoAzione.PARLAMENTA)
            await pilot.click(f"#opz-{indice}")
            await pilot.pause()
            assert app._in_scena, "Parlamenta riuscito: modo-scena attivo"
            snap = sessione.avanza()
            indice = next(o.indice for o in snap.opzioni
                          if o.tipo is TipoAzione.COMBATTI)
            await pilot.click(f"#opz-{indice}")
            await pilot.pause()
            assert not app._in_scena, (
                "la TUI è rimasta in modo-scena a scena abbandonata: il "
                "prossimo Invio crasha l'app"
            )
            assert not app.query_one("#azione", Input).has_class("attiva")

    import asyncio as _asyncio

    _asyncio.run(run())
