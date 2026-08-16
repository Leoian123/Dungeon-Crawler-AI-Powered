"""Lucchetti della caccia avversariale 2026-08-16 (workflow a 6 cacciatori +
verifica): i reperti CONFERMATI e corretti, oltre a quelli già in
`test_permadeath_slot`. Ogni test è l'exploit/il sintomo, non l'esistenza
del meccanismo che lo chiude.
"""

from __future__ import annotations

import asyncio
import random

import esper

from contracts import CombatResolved, PlayerChoseOption, RuoloMob, Grado
from main import costruisci_sessione
from provider import FakeProvider


# --- Fuga armata sotto stordimento: l'input non dirotta il turno dopo ----------

def test_la_fuga_chiesta_da_stordito_muore_col_turno(run_pulita) -> None:
    """Il giocatore stordito clicca Fuggi: il turno è consumato dallo stordito.
    La richiesta NON deve sopravvivere — al turno dopo sceglie Attacca e il
    motore eseguiva la fuga di due turni prima (colpi d'opportunità e morte
    compresi) per un input mai riconfermato."""
    from motore import stato_combattimento
    from motore.scheda import protagonista
    from motore.status import Stordito

    sessione = costruisci_sessione(seed=1)
    asyncio.run(sessione.prossima_narrazione())
    sessione.coda.accoda(PlayerChoseOption(0))  # Combatti
    snap = sessione.avanza()
    assert snap.fase == "combattimento"
    pent, _m, _s = protagonista()
    st = stato_combattimento()
    assert st is not None
    # Stordimento come afflizione (non innato): il prossimo turno salta.
    esper.add_component(pent, Stordito(rango=1, durata=3, innato=False))
    etichette = [o.etichetta for o in snap.opzioni]
    indice_fuggi = next(i for i, e in enumerate(etichette) if e.startswith("Fuggi"))
    sessione.coda.accoda(PlayerChoseOption(indice_fuggi))
    snap = sessione.avanza()  # il turno del protagonista è consumato dallo stun
    st = stato_combattimento()
    if st is None:
        return  # lo scontro si è chiuso comunque (nemico morto dal crollo): niente da dirottare
    assert st[1].fuga_richiesta is False, (
        "la fuga chiesta dal turno stordito è sopravvissuta: dirotterà il turno dopo"
    )
    assert st[1].mossa_richiesta is None


# --- Territorio stantio: il confine di piano azzera SEMPRE lo stato ------------

def test_la_discesa_su_piano_piatto_azzera_lo_stato_territoriale(mondo_isolato) -> None:
    """Piano-mondo → piano piatto: senza cleanup lo `StatoTerritorio` della tana
    sopravviveva e `finestra_gradi_loot` serviva drop celestiali a profondità 2."""
    from contracts import TierTerritorio
    from motore import StatoTerritorio, Zona, avvia_territorio

    esper.create_entity(StatoTerritorio(
        zona_corrente=Zona(tier=TierTerritorio.PIANO).chiave,
    ))
    # Nessuna stagione montata ⇒ nessun territorio attivo: il piano è piatto.
    assert avvia_territorio(livello=2) is False
    assert not esper.get_component(StatoTerritorio), (
        "lo stato territoriale del piano lasciato è sopravvissuto alla discesa"
    )


def test_finestra_loot_ignora_la_zona_senza_territorio_attivo(mondo_isolato) -> None:
    """Difesa in profondità per i save già scritti con lo stato stantio: la
    zona vale solo se il piano CORRENTE ha un territorio."""
    from contracts import TierTerritorio
    from motore import StatoTerritorio, Zona, finestra_gradi_loot
    from motore.catalogo import gradi_per_profondita

    esper.create_entity(StatoTerritorio(
        zona_corrente=Zona(tier=TierTerritorio.PIANO).chiave,
    ))
    assert finestra_gradi_loot(2) == gradi_per_profondita(2), (
        "la finestra del loot segue una zona di un territorio che non esiste più"
    )


# --- Famiglia premi: nessuna scrittura oltre la barriera di sessione -----------

class _ProviderCheInvalida(FakeProvider):
    """Simula il caso reale: durante l'await del conio un'altra sessione prende
    il run-World e questa viene invalidata."""

    def __init__(self, sessione, risposte) -> None:
        super().__init__(risposte)
        self._sessione = sessione

    async def genera(self, prompt, schema, *, sistema=""):
        self._sessione._invalidata = "un'altra sessione ha preso il run-World (test)"
        return await super().genera(prompt, schema, sistema=sistema)


def test_la_vestizione_non_scrive_su_sessione_invalidata(run_pulita) -> None:
    """La barriera post-await (stessa disciplina di `guardia_scrittura` del GM):
    se la sessione cade durante l'attesa, la coroutine cade SENZA scrivere —
    prima il cimelio veniva battezzato nel guardaroba del protagonista ALTRUI."""
    from motore import assicura_guardaroba, catalogo_oggetti_correnti
    from motore.scheda import protagonista

    sessione = costruisci_sessione(seed=1)
    asyncio.run(sessione.prossima_narrazione())
    fonte = sorted(catalogo_oggetti_correnti())[0]
    sessione._ultimo_drop = (fonte, Grado.BRONZO.value)
    from motore import grado_oggetto

    sessione.provider = _ProviderCheInvalida(sessione, [dict(
        base=fonte, grado=grado_oggetto(fonte),
        nome="Cimelio Rubato", descrizione="battezzato altrove",
    )])
    pent, _m, _s = protagonista()
    guardaroba = assicura_guardaroba(pent)
    prima = dict(guardaroba.vesti)
    try:
        asyncio.run(sessione.veste_premio())
        raise AssertionError("la barriera post-await non è scattata")
    except RuntimeError as e:
        assert "invalidata" in str(e)
    assert dict(guardaroba.vesti) == prima, (
        "la vestizione ha scritto nel World di una sessione invalidata"
    )


# --- Mob fantasma d'imboscata: si dissolve con lo scontro ----------------------

def test_il_mob_di_imboscata_congedato_non_resta_fantasma(mondo_isolato) -> None:
    """Fuga da un'imboscata: il mob arruolato SENZA stanza (mai registrato
    sulla mappa) non si congeda — si dissolve. Congedarlo lo lasciava nel World
    come OSTILE irraggiungibile che gonfiava `minacce_zona` per sempre."""
    from contracts import Durata
    from motore import EntitaMob
    from motore.combattimento import Nemico, PuntiVita, collega_combattimento
    from contracts.bus import BusEventi

    bus = BusEventi()
    coppie = collega_combattimento(bus)
    try:
        fantasma = esper.create_entity(
            EntitaMob(archetipo="slime", grado=Grado.BRONZO, nome="Agguato",
                      descrizione="sbuca dal nulla", livello=1, stanza=None,
                      ruolo=RuoloMob.OSTILE),
            Nemico(arruolato=True),
            PuntiVita(attuali=5, massimi=5),
        )
        di_stanza = esper.create_entity(
            EntitaMob(archetipo="slime", grado=Grado.BRONZO, nome="Di Stanza",
                      descrizione="presidia la stanza", livello=1, stanza=3,
                      ruolo=RuoloMob.OSTILE),
            Nemico(arruolato=True),
            PuntiVita(attuali=5, massimi=5),
        )
        bus.pubblica(CombatResolved(entita=fantasma, vittoria=False, fuga=True))
        assert not esper.entity_exists(fantasma), (
            "il mob d'imboscata è rimasto nel World senza stanza: minaccia eterna"
        )
        assert esper.entity_exists(di_stanza), (
            "il mob DI stanza deve restare congedato (anti room-clear gratuito)"
        )
        assert not esper.has_component(di_stanza, Nemico)
    finally:
        for tipo, handler in coppie:
            bus.deregistra(tipo, handler)
