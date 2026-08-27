"""I fix del playtest 2026-08-12 (riscontri utente): dedupe dello status
annunciato, drop garantito sul custode, la valvola «Aspetta», e il dado-minacce
(imboscata ∝ nemici nel chunk: il riposo in campo si GUADAGNA ripulendo).
"""

from __future__ import annotations

import asyncio

from contracts import BusEventi, StatusApplicato, TipoAzione, TipoStanza
from motore import (
    applica_status,
    avvia_territorio,
    componi_opzioni_scena,
    crea_entita_fase,
    crea_profondita,
    crea_protagonista,
    crea_seme,
    crea_stagione,
    crea_tempo_piano,
    fattore_minacce,
    mappa_corrente,
    minacce_zona,
    protagonista,
    riposa,
    segna_visitata,
)
from motore.status import Veleno, afflizione
from tests.contenuti_sintetici import piano_territoriale, stagione_sintetica


def _arma_mondo(seed: int = 7) -> BusEventi:
    from main import _stagione_a_attiva

    crea_profondita()
    crea_seme(seed)
    crea_tempo_piano()
    crea_stagione(_stagione_a_attiva(
        stagione_sintetica(piani=[piano_territoriale(1)], slug="s-playfix")
    ))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    crea_entita_fase()
    avvia_territorio(1)
    return BusEventi()


# --- Fix: «Sei avvelenato!» una volta sola ---------------------------------------

def test_applica_status_dice_se_nuovo(mondo_isolato) -> None:
    """Il fatto che decide l'annuncio: la prima applicazione è NUOVA, il
    rinfresco no — la cronaca non ristampa lo status già addosso."""
    import esper

    ent = esper.create_entity()
    assert applica_status(ent, afflizione(Veleno, 1)) is True
    assert applica_status(ent, afflizione(Veleno, 1)) is False  # rinfresco
    assert applica_status(ent, afflizione(Veleno, 3)) is False  # upgrade di rango


# --- Fix: il custode battuto non lascia mai a mani vuote --------------------------

def test_drop_garantito_sul_custode(run_pulita, tmp_path) -> None:
    """La garanzia è del CUSTODE IN PERSONA (`FattiScontro.custode`), mai
    della stanza: il breaker 2026-08-26 aveva promosso l'edge per-stanza a
    bancomat (imboscate vinte in stanza-boss = drop garantiti a ripetizione)."""
    import random

    from contracts import FattiScontro
    from main import costruisci_sessione
    from motore import assicura_zaino, registra_boss_sconfitto, stanza_boss_di, zona_corrente

    sessione = costruisci_sessione(
        nome="Boss", seed=9, directory=tmp_path,
        stagione=stagione_sintetica(piani=[piano_territoriale(1)], slug="s-bossdrop"),
    )
    asyncio.run(sessione.prossima_narrazione())
    _e, mappa = mappa_corrente()
    zona = zona_corrente()

    class _RngPerde(random.Random):
        """La chance di drop è sempre PERSA: solo la garanzia può depositare."""

        def random(self) -> float:  # type: ignore[override]
            return 0.999

        def randrange(self, *a, **k) -> int:  # type: ignore[override]
            return 0

    sessione.rng = _RngPerde()
    pent = protagonista()[0]
    prima = len(assicura_zaino(pent).fonti)

    # Vittoria ordinaria (non è il custode), chance persa → niente.
    sessione._fatti_scontro = FattiScontro(vittoria=True, turni=1, hp_persi=0)
    sessione._deposita_bottino()
    assert len(assicura_zaino(pent).fonti) == prima

    # ANTI-BANCOMAT: stanza-boss, custode GIÀ battuto, vittoria d'imboscata
    # (`custode=False`) → la stanza non regala niente, la chance si tira come
    # ovunque (e qui è persa).
    mappa.stanza_corrente = stanza_boss_di(zona, mappa.piano)
    segna_visitata()
    registra_boss_sconfitto()
    sessione._fatti_scontro = FattiScontro(vittoria=True, turni=1, hp_persi=0)
    sessione._deposita_bottino()
    assert len(assicura_zaino(pent).fonti) == prima, (
        "la stanza-boss non è un bancomat: senza il custode nello scontro, "
        "nessuna garanzia"
    )

    # La vittoria SUL custode: garantito.
    sessione._fatti_scontro = FattiScontro(
        vittoria=True, turni=1, hp_persi=0, custode=True,
    )
    sessione._deposita_bottino()
    assert len(assicura_zaino(pent).fonti) == prima + 1, (
        "il momento-boss non finisce a mani vuote"
    )
    sessione.esci()


def test_custode_in_scontro_fotografa_il_mob_non_la_stanza(mondo_isolato) -> None:
    """La fotografia all'apertura (`StatoCombattimento.custode_presente`):
    True SOLO se il mob DELLA stanza-boss, a boss non ancora battuto, è fra
    gli arruolati — l'imboscata nella stessa stanza non è mai il custode."""
    from contracts import EntitaGenerata, Grado
    from motore import (
        registra_boss_sconfitto,
        registra_mob,
        stanza_boss_di,
        zona_corrente,
    )
    from motore.combattimento import _custode_in_scontro
    from motore.narrazione import istanzia_entita

    # Senza territorio (harness nudo): degrado a False, mai un crash.
    assert _custode_in_scontro([1, 2]) is False

    _arma_mondo()
    segna_visitata()
    assert _custode_in_scontro([1]) is False  # partenza: non è la stanza-boss

    _e, mappa = mappa_corrente()
    mappa.stanza_corrente = stanza_boss_di(zona_corrente(), mappa.piano)
    segna_visitata()
    ent = istanzia_entita(
        EntitaGenerata(archetipo="slime", grado=Grado.BRONZO, blocchi=[],
                       nome="Custode", descrizione="fermo al varco"),
        livello=1,
    )
    registra_mob(ent)
    assert _custode_in_scontro([ent]) is True, "il custode in persona"
    assert _custode_in_scontro([ent + 999]) is False, (
        "l'imboscata in stanza-boss non è il custode"
    )
    registra_boss_sconfitto()
    assert _custode_in_scontro([ent]) is False, (
        "a custode battuto la stanza non promuove più nessuno"
    )


# --- Fix: la valvola «Aspetta» (la tenaglia del veleno si apre) -------------------

def test_aspetta_e_di_scena_anche_avvelenato(mondo_isolato) -> None:
    """Col veleno addosso Riposa sparisce (dannoso) ma Aspetta RESTA: è la
    valvola di J §6 — i dannosi non bloccano il passa-turno."""
    _arma_mondo()
    segna_visitata()  # la scena si compone solo su stanza narrata
    protagonista()[2].punti_vita -= 5  # ferito: il riposo ha qualcosa da fare
    tipi = {o.tipo for o in componi_opzioni_scena()}
    assert TipoAzione.PASSA in tipi and TipoAzione.RIPOSA in tipi

    pent = protagonista()[0]
    applica_status(pent, afflizione(Veleno, 1))
    tipi = {o.tipo for o in componi_opzioni_scena()}
    assert TipoAzione.RIPOSA not in tipi, "il veleno blocca il riposo"
    assert TipoAzione.PASSA in tipi, "ma NON la valvola: si può aspettare"


# --- Round 3: a risorse piene «Riposa» non si compone -----------------------------

def test_riposa_sparisce_a_risorse_piene(mondo_isolato) -> None:
    """Il «Riposi: niente» del round 3: a HP e mana PIENI l'opzione non è vera
    e non si compone; basta una ferita (o mana speso) perché torni."""
    from motore import assicura_mana

    _arma_mondo()
    segna_visitata()
    tipi = {o.tipo for o in componi_opzioni_scena()}
    assert TipoAzione.RIPOSA not in tipi, "a risorse piene il riposo fa «niente»"
    assert TipoAzione.PASSA in tipi  # la valvola del tempo resta

    scheda = protagonista()[2]
    scheda.punti_vita -= 1
    tipi = {o.tipo for o in componi_opzioni_scena()}
    assert TipoAzione.RIPOSA in tipi, "ferito, il riposo torna di scena"

    scheda.punti_vita += 1  # integro di nuovo... ma col mana speso
    pent = protagonista()[0]
    assicura_mana(pent).attuale = 0
    tipi = {o.tipo for o in componi_opzioni_scena()}
    assert TipoAzione.RIPOSA in tipi, "anche il solo mana giustifica il riposo"


# --- Fix: imboscata ∝ minacce — il riposo si guadagna -----------------------------

def test_minacce_contano_vivi_e_stanze_non_rivelate(mondo_isolato) -> None:
    """Round 3: la stanza non rivelata è un nemico POTENZIALE, non un nemico —
    pesa `IMBOSCATA.peso_non_rivelate` (<1), il vivo pesa 1 pieno."""
    from contracts import EntitaGenerata, Grado
    from motore.calibrazione import IMBOSCATA_PESO_NON_RIVELATE as PESO
    from motore.narrazione import istanzia_entita

    assert 0 < float(PESO) < 1, "lo sconto dell'incognita è il punto del fix"
    _arma_mondo()
    _e, mappa = mappa_corrente()
    non_quiete = [s for s in mappa.piano.adiacenze
                  if mappa.piano.tipi.get(s) not in (TipoStanza.SAFE_ROOM,
                                                     TipoStanza.BAGNO)]
    assert minacce_zona() == PESO * len(non_quiete)  # tutte da rivelare, zero vivi

    mappa.visitate.add(mappa.stanza_corrente)  # una rivelata in meno...
    atteso = PESO * (len(non_quiete)
                     - (1 if mappa.stanza_corrente in non_quiete else 0))
    assert minacce_zona() == atteso

    ent = istanzia_entita(EntitaGenerata(
        archetipo="slime", grado=Grado.BRONZO, blocchi=[],
        nome="Slime", descrizione="molliccio",
    ), 1)
    assert minacce_zona() == atteso + 1  # ...e un vivo in più: peso PIENO
    import esper

    esper.delete_entity(ent, immediate=True)
    assert minacce_zona() == atteso  # ucciso = minaccia in meno


def test_a_zona_ripulita_il_riposo_in_campo_e_sicuro(mondo_isolato, monkeypatch) -> None:
    """La meccanica del playtest: PROB_IMBOSCATA=1 ma zona RIPULITA (tutto
    rivelato, zero vivi) → fattore minacce 0 → il riposo arriva in fondo.
    Prima del fix un riposo da 4 tick moriva ~76%% delle volte OVUNQUE."""
    from motore import tempo as tempo_mod

    monkeypatch.setattr(tempo_mod, "PROB_IMBOSCATA", 1.0)
    bus = _arma_mondo()
    _e, mappa = mappa_corrente()
    mappa.visitate.update(mappa.piano.adiacenze)  # zona interamente rivelata
    assert minacce_zona() == 0 and fattore_minacce() == 0.0

    esito = riposa(bus)
    assert esito is not None and not esito.interrotto, (
        "a zona ripulita il riposo in campo è GUADAGNATO"
    )


# --- Fix: la ritirata universale — «Scappi» non ripulisce mai la stanza -----------

def test_scappi_ritira_e_il_mob_resta(run_pulita, tmp_path) -> None:
    """L'exploit del playtest: prima il disimpegno di scena DISSOLVEVA il mob
    ordinario (room-clear gratuito, la fuga migliore della vittoria). Ora vale
    per tutti il ramo del custode: tu arretri, lui resta alla sua stanza —
    rivisitarla significa ritrovarlo."""
    import esper

    from main import costruisci_sessione
    from motore import EntitaMob, mob_corrente

    sessione = costruisci_sessione(
        nome="Fuga", seed=5, directory=tmp_path,
        stagione=stagione_sintetica(piani=[piano_territoriale(1)], slug="s-ritira"),
    )
    asyncio.run(sessione.prossima_narrazione())  # reveal: il mob è in scena
    ent = mob_corrente()
    assert ent is not None
    _e, mappa = mappa_corrente()
    stanza_del_mob = mappa.stanza_corrente

    snapshot = sessione._snapshot_corrente()
    etichette = {o.etichetta: o.indice for o in snapshot.opzioni}
    assert "Scappi" in etichette
    from contracts import PlayerChoseOption

    sessione.coda.accoda(PlayerChoseOption(etichette["Scappi"]))
    sessione.avanza()

    _e, mappa = mappa_corrente()
    assert mappa.stanza_corrente != stanza_del_mob, "il disimpegno RITIRA"
    assert esper.entity_exists(ent), "il mob NON si dissolve mai"
    em = esper.component_for_entity(ent, EntitaMob)
    assert em.stanza == stanza_del_mob  # resta registrato alla SUA stanza

    mappa.stanza_corrente = stanza_del_mob  # rivisita: lo ritrovi
    assert mob_corrente() == ent
    sessione.esci()


# --- Fix: il backtracking paga il suo tick ----------------------------------------

def test_muoversi_su_stanza_visitata_costa_un_tick(run_pulita, tmp_path) -> None:
    """Il buco della tenaglia: i movimenti su stanze visitate costavano 0 tick
    (il veleno non si smaltiva camminando). Ora il backtracking spende un tick
    pieno; la stanza NUOVA continua a pagare col solo turno di reveal."""
    import esper

    from contracts import PlayerChoseOption
    from main import costruisci_sessione
    from motore import (
        applica_status,
        dissolvi_mob,
        mob_corrente,
        protagonista,
        tempo_piano_corrente,
    )
    from motore.status import Veleno, afflizione

    sessione = costruisci_sessione(
        nome="Passi", seed=11, directory=tmp_path,
        stagione=stagione_sintetica(piani=[piano_territoriale(1)], slug="s-passi"),
    )
    asyncio.run(sessione.prossima_narrazione())  # reveal della partenza
    if mob_corrente() is not None:
        dissolvi_mob()  # LAB: si libera la scena (nel gioco vero: scontro/ritirata)

    def _muovi(stanza: int) -> None:
        sessione._sincronizza_scena()
        snapshot = sessione._snapshot_corrente()
        indici = {o.etichetta: o.indice for o in snapshot.opzioni}
        sessione.coda.accoda(PlayerChoseOption(indici[f"Vai: stanza {stanza}"]))
        sessione.avanza()

    _e, mappa = mappa_corrente()
    partenza = mappa.stanza_corrente
    vicina = mappa.piano.adiacenze[partenza][0]

    # ANDATA (stanza nuova): il movimento in se' non spende — pagherebbe il reveal.
    prima = tempo_piano_corrente()
    _muovi(vicina)
    assert mappa.stanza_corrente == vicina
    assert tempo_piano_corrente() == prima, "la stanza nuova paga col reveal, non due volte"

    # RITORNO su stanza visitata: UN tick pieno — e il veleno ticka camminando.
    mappa.visitate.add(vicina)  # LAB: la vicina risulta narrata (menu componibile)
    pent = protagonista()[0]
    applica_status(pent, afflizione(Veleno, 1))
    durata_prima = esper.component_for_entity(pent, Veleno).durata
    prima = tempo_piano_corrente()
    _muovi(partenza)
    assert mappa.stanza_corrente == partenza
    assert tempo_piano_corrente() == prima + 1, "il backtracking paga il suo tick"
    durata_dopo = esper.component_for_entity(pent, Veleno).durata
    assert durata_dopo == durata_prima - 1, "il veleno si smaltisce camminando"
    sessione.esci()


# --- Playtest a 3 persone (2026-08-27): la verità del World arriva alla prosa ----

def test_il_contratto_vieta_gli_esiti_meccanici_in_prosa() -> None:
    """P0 del playtest a 3 persone: il motore teneva lo stato ma l'AI narrava
    i successi rifiutati (la soglia varcata a parole, la box aperta sul
    bancone, i passaggi promessi). Il gemello narrativo del gate è una
    clausola di CONTRATTO — statica, in cache, uniforme su OGNI intento
    rifiutato — non un prompt mirato per caso."""
    from motore import PREFISSO_GM
    from motore.scena import _ISTRUZIONE_BLOCCHI

    assert "esiti MECCANICI non avvengono mai nella prosa" in PREFISSO_GM
    assert "MAI il compimento non concesso" in PREFISSO_GM
    # E la scena (dove il Postino «consegnava» la chiave) porta lo stesso
    # divieto in forma sua: promettere sì, consegnare mai.
    assert "mai consegnarli" in _ISTRUZIONE_BLOCCHI


# --- Round 3: l'agguato è cucito alla prosa del turno -----------------------------

def test_l_agguato_e_cucito_alla_prosa_del_reveal(run_pulita, tmp_path, monkeypatch) -> None:
    """Il difetto più visibile del round 3: reveal + imboscata nello stesso
    respiro mostravano la prosa del mob DI STANZA (il Legionario) sopra la barra
    dell'ambusher (Ballerino 41/41) — leggevi di uno e combattevi l'altro. Ora
    il MOTORE appende il segnaposto («Prima che tu possa guardarti intorno…»)
    che nomina chi ti piomba addosso; l'Archivio congela la prosa PULITA: la
    rilettura della stanza non ripete l'agguato di un tick passato."""
    from main import costruisci_sessione
    from motore import mappa as mappa_mod
    from motore import tempo as tempo_mod
    from motore.gm import TIPO_RECORD_GM

    monkeypatch.setattr(tempo_mod, "PROB_IMBOSCATA", 1.0)
    monkeypatch.setattr(mappa_mod, "fattore_minacce", lambda: 1.0)
    sessione = costruisci_sessione(
        nome="Varco", seed=3, directory=tmp_path,
        stagione=stagione_sintetica(piani=[piano_territoriale(1)], slug="s-varco"),
    )
    # Il REVEAL non imbosca più (tregua di reveal, playtest live 2026-08-27):
    # anche col dado forzato, il primo turno presenta la stanza e basta.
    snap = asyncio.run(sessione.prossima_narrazione())
    assert snap.fase == "narrazione", "il turno che rivela non imbosca"
    # La cucitura vive dove l'agguato resta LEGITTIMO: un turno con prosa
    # che SPENDE tempo dopo la tregua — l'azione libera, col dado forzato.
    riep = sessione.riepiloga_azione("perlustro il perimetro della stanza")
    snap = asyncio.run(sessione.esegui_azione(riep))
    assert snap.fase == "combattimento"
    assert sessione._imboscata_in_corso is True
    nemico = sessione._istanza.nemico
    assert "ti piomba addosso" in snap.prosa
    assert nemico and nemico in snap.prosa.split("\n\n")[-1], (
        "il segnaposto nomina CHI ti piomba addosso, non un generico rumore"
    )
    for record in sessione.archivio.record_di_tipo(TIPO_RECORD_GM):
        assert "piomba addosso" not in record.contenuto.get("prosa", ""), (
            "l'Archivio deve restare pulito: l'agguato non è della stanza"
        )
    # Niente `esci()`: in combattimento non si salva (guardia audit 2026-08);
    # il teardown di `run_pulita` smonta il World come nell'e2e gemello.


# --- Round 2 (playtest 2026-08-12): il zone-hopping non ripulisce -----------------

def test_zone_hopping_non_ripulisce_ne_resuscita(run_pulita, tmp_path) -> None:
    """Il buco che aggirava la ritirata universale: uscire e rientrare dalla
    zona despawnava anche il mob CONGEDATO (room-clear gratuito via deviazione).
    Ora la fotografia all'uscita distingue: il congedato TORNA (stesso mob, dal
    seed del copione), il morto RESTA morto (niente farming di resurrezione)."""
    import esper

    from main import costruisci_sessione
    from motore import EntitaMob, mob_corrente, zona_corrente
    from motore.territorio import (
        _despawna_mob_di_zona,
        _fotografa_vivi_di_zona,
        rigenera_mappa_zona,
    )

    sessione = costruisci_sessione(
        nome="Hop", seed=5, directory=tmp_path,
        stagione=stagione_sintetica(piani=[piano_territoriale(1)], slug="s-hop"),
    )
    asyncio.run(sessione.prossima_narrazione())  # reveal: mob in partenza
    ent = mob_corrente()
    assert ent is not None
    nome_prima = esper.component_for_entity(ent, EntitaMob).nome
    _e, mappa = mappa_corrente()
    stanza_del_mob = mappa.stanza_corrente
    zona = zona_corrente()

    # USCITA e RIENTRO (i passi di `attraversa`, sulla stessa zona):
    _fotografa_vivi_di_zona()
    _despawna_mob_di_zona()
    rigenera_mappa_zona(1, zona)
    _e, mappa = mappa_corrente()
    tornato = mappa.mob_stanza.get(stanza_del_mob)
    assert tornato is not None, "il congedato DEVE tornare: niente room-clear via zone-hop"
    em = esper.component_for_entity(tornato, EntitaMob)
    assert em.nome == nome_prima, "stesso mob (seed del copione), non un altro"

    # Il MORTO invece resta morto: si uccide e si rifà il giro.
    esper.delete_entity(tornato, immediate=True)
    _fotografa_vivi_di_zona()
    _despawna_mob_di_zona()
    rigenera_mappa_zona(1, zona)
    _e, mappa = mappa_corrente()
    assert mappa.mob_stanza.get(stanza_del_mob) is None, (
        "il morto non si rimaterializza: niente farming di resurrezione"
    )
    sessione.esci()


# --- Round 2: azzardo che si racconta, anomalia onesta, tempra, déjà-vu -----------

def test_l_azzardo_espone_la_faccia(mondo_isolato) -> None:
    """Il contratto dormiente `EsitoAzzardo.etichetta` acceso: il risolutore
    ritorna (danno, FACCIA) e la riga di cronaca la premette («⚄ …!»)."""
    import random

    from main import _riga_colpo
    from contracts import ColpoInferto
    from motore.azzardo import (
        EsitoAzzardo,
        TiroAzzardo,
        risolvi_effetto_azzardo_con_faccia,
    )

    from motore import protagonista as _prot

    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    ent = _prot()[0]  # sorgente col vettore Primarie (la Fortuna esiste)
    tiro = TiroAzzardo(esiti=(
        EsitoAzzardo(etichetta="La casa vince", danno=-3),
        EsitoAzzardo(etichetta="Jackpot del Sistema", danno=13),
    ))
    danno, faccia = risolvi_effetto_azzardo_con_faccia(tiro, ent, random.Random(1))
    assert faccia in ("La casa vince", "Jackpot del Sistema")
    assert danno in (-3, 13)

    riga = _riga_colpo(ColpoInferto(
        attaccante="", bersaglio="Fante", danno=13, hp_rimasti=1, hp_max=24,
        mossa="roulette", azzardo="Jackpot del Sistema",
    ))
    assert riga.startswith("⚄ Jackpot del Sistema!"), riga
    liscia = _riga_colpo(ColpoInferto(
        attaccante="", bersaglio="Fante", danno=3, hp_rimasti=9, hp_max=24,
    ))
    assert "⚄" not in liscia  # il colpo ordinario resta ordinario


def test_l_anomalia_si_annuncia_solo_se_manifesta(mondo_isolato) -> None:
    """«Il dungeon ride…» prometteva un evento che offline non arrivava mai:
    ora l'annuncio esige il FATTO — un grado fuori dalla finestra del contesto."""
    from contracts import AnomalyTriggered, Grado
    from motore import materializza_turno
    from motore.narrazione import RisultatoTurno
    from tests.narr_helpers import turno as turno_h

    _arma_mondo()
    bus = BusEventi()
    eventi: list = []
    bus.registra(AnomalyTriggered, eventi.append)
    from motore import prepara_contesto
    import random

    budget = prepara_contesto(1, random.Random(0))
    dentro = turno_h(grado=Grado.BRONZO)   # dentro la finestra del quartiere
    materializza_turno(RisultatoTurno(
        turno=dentro, budget=budget, fallback=False, anomala=True), bus)
    assert eventi == [], "anomalia dichiarata ma non manifesta: l'annuncio tace"

    fuori = turno_h(grado=Grado.ORO)       # fuori scala per il quartiere
    materializza_turno(RisultatoTurno(
        turno=fuori, budget=budget, fallback=False, anomala=True), bus)
    assert len(eventi) == 1, "l'anomalia MANIFESTA si annuncia"


def test_tempra_del_custode(mondo_isolato) -> None:
    """Il momento-boss si sente: al primo arruolamento del custode il pool HP è
    moltiplicato (`BOSS.molt_hp`); il gregario resta ai suoi max_hp."""
    import esper

    from contracts import EntitaGenerata, Grado
    from motore import (
        PuntiVita,
        max_hp,
        stanza_boss_di,
        zona_corrente,
    )
    from motore.calibrazione import BOSS_MOLT_HP
    from motore.narrazione import istanzia_entita

    import random

    from motore import arruola_entita
    from motore.combattimento import StatoCombattimento

    _arma_mondo()
    _e, mappa = mappa_corrente()
    zona = zona_corrente()
    esper.create_entity(StatoCombattimento(
        ordine=[], indice=0, round=1, prossima_chiave=0, rng=random.Random(1),
    ))

    def _mob() -> int:
        return istanzia_entita(EntitaGenerata(
            archetipo="slime", grado=Grado.BRONZO, blocchi=[],
            nome="Cavia", descrizione="di prova",
        ), 1)

    # Gregario in stanza ordinaria: pool = max_hp liscio.
    gregario = _mob()
    arruola_entita(gregario)
    pv = esper.component_for_entity(gregario, PuntiVita)
    assert pv.massimi == max_hp(gregario)

    # Il CUSTODE (stanza-boss, boss in piedi): pool moltiplicato.
    mappa.stanza_corrente = stanza_boss_di(zona, mappa.piano)
    custode = _mob()
    arruola_entita(custode)
    pv = esper.component_for_entity(custode, PuntiVita)
    assert pv.massimi == round(max_hp(custode) * float(BOSS_MOLT_HP)), (
        "la tempra del custode non è stata applicata"
    )


def test_pavimento_del_custode_sul_miglior_gregario(mondo_isolato, monkeypatch) -> None:
    """Round 3: la tempra moltiplicativa non basta quando il custode pesca
    l'archetipo gracile (Nonno-scheletro 12×1.5=18 HP sotto il Fante da 24).
    Il pavimento è il miglior GREGARIO che la tabella del tier può schierare:
    il momento-boss non è mai più tenero dei riempitivi."""
    import random

    import esper

    from contracts import EntitaGenerata, Frequenza, Grado, VoceSpawnRisolta
    from main import _stagione_a_attiva
    from motore import (
        PuntiVita,
        arruola_entita,
        max_hp,
        stanza_boss_di,
        zona_corrente,
    )
    from motore import calibrazione as cal_mod
    from motore.combattimento import StatoCombattimento
    from motore.narrazione import istanzia_entita
    from motore.territorio import pavimento_hp_custode
    from tests.contenuti_sintetici import (
        mob_sintetico,
        piano_sintetico,
        territorio_sintetico,
    )

    crea_profondita()
    crea_seme(7)
    crea_tempo_piano()
    terr = territorio_sintetico("pav")
    # Il «Fante»: un riempitivo di grado sopra il custode gracile.
    terr.spawn[0].voci.append(VoceSpawnRisolta(
        mob=mob_sintetico("pav-fante", grado=Grado.ORO),
        frequenza=Frequenza.COMUNE,
    ))
    crea_stagione(_stagione_a_attiva(stagione_sintetica(
        piani=[piano_sintetico(1, gradi=tuple(Grado), slug="mondo-1", territorio=terr)],
        slug="s-pavimento",
    )))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    crea_entita_fase()
    avvia_territorio(1)

    # Il pavimento È il miglior gregario vero: stessa formula-madre del mob materializzato.
    fante = istanzia_entita(EntitaGenerata(
        archetipo="slime", grado=Grado.ORO, blocchi=[],
        nome="Fante", descrizione="di linea",
    ), 1)
    assert pavimento_hp_custode(1) == max_hp(fante)
    esper.delete_entity(fante, immediate=True)

    _e, mappa = mappa_corrente()
    zona = zona_corrente()
    esper.create_entity(StatoCombattimento(
        ordine=[], indice=0, round=1, prossima_chiave=0, rng=random.Random(1),
    ))
    mappa.stanza_corrente = stanza_boss_di(zona, mappa.piano)
    monkeypatch.setattr(cal_mod, "BOSS_MOLT_HP", 1.0)  # tempra spenta: parla solo il pavimento
    custode = istanzia_entita(EntitaGenerata(
        archetipo="slime", grado=Grado.BRONZO, blocchi=[],
        nome="Nonno", descrizione="gracile",
    ), 1)
    assert max_hp(custode) < pavimento_hp_custode(1), "premessa: il pescaggio è il gracile"
    arruola_entita(custode)
    pv = esper.component_for_entity(custode, PuntiVita)
    assert pv.massimi == pavimento_hp_custode(1), (
        "il custode non scende mai sotto il miglior gregario del tier"
    )


def test_imboscata_senza_deja_vu(mondo_isolato, monkeypatch) -> None:
    """Il nemico appena ucciso non riappare nell'imboscata immediata: una
    ri-pescata seeded. Se anche la seconda lo ripesca (tabella monotona),
    resta lui — il dado non mente per cortesia."""
    from motore import componi_imboscata_scena, entita_mob_incontro
    from motore import territorio as territorio_mod
    from tests.contenuti_sintetici import mob_sintetico
    from main import _mob_a_attivo

    _arma_mondo()
    a = _mob_a_attivo(mob_sintetico("gia-morto", prosa="p"))
    b = _mob_a_attivo(mob_sintetico("un-altro", prosa="p"))
    sequenza = iter([a, b])
    monkeypatch.setattr(territorio_mod, "pesca_spawn",
                        lambda _rng, escludi=frozenset(): next(sequenza, b))
    enc = componi_imboscata_scena(escludi_nome=a.nome)
    em = entita_mob_incontro(enc)
    assert em is not None and em.nome == b.nome, (
        "il déjà-vu: doveva ripescare, non riproporre il morto"
    )


# --- Playtest 2026-08-19 (web): il déjà-vu delle stanze adiacenti ---------------

def test_stanze_adiacenti_non_ripetono_il_mob(run_pulita, tmp_path) -> None:
    """Due Fanti identici (stesso mob, stessa prosa) in stanze adiacenti:
    `mob_di_stanza` ri-pesca con esclusione quando la pescata coincide con
    quella GREZZA della stanza precedente. Una ripetizione consecutiva resta
    lecita SOLO se la tabella non offre alternative (voce unica)."""
    import random as _random

    from main import costruisci_sessione
    from motore import master_seed, mob_di_stanza, pesca_spawn, zona_corrente

    for seed in (1, 3, 2156223982):  # l'ultimo è il daily del playtest
        sessione = costruisci_sessione(seed=seed, directory=tmp_path / str(seed))
        zona = zona_corrente()
        assert zona is not None, "la stagione-1 ha il territorio"
        stanze = sorted(mappa_corrente()[1].piano.adiacenze)
        for precedente, stanza in zip(stanze, stanze[1:]):
            a = mob_di_stanza(1, zona, precedente)
            b = mob_di_stanza(1, zona, stanza)
            if a is None or b is None or a.slug != b.slug:
                continue
            rng = _random.Random(
                f"{master_seed()}:copione:1:{zona.chiave}:{stanza}"
            )
            pesca_spawn(rng)  # consuma la pescata grezza, come fa la funzione
            assert pesca_spawn(rng, escludi=frozenset({b.nome})) is None, (
                f"seed {seed}: {b.slug} ripetuto in {precedente}->{stanza} "
                "con alternative disponibili in tabella"
            )
        sessione.esci()


def test_mob_di_stanza_e_path_independent(run_pulita) -> None:
    """La derivazione dipende SOLO da (seed, zona, numero di stanza): due
    letture della stessa stanza danno lo stesso mob — replay, rientro e
    riletture non divergono mai dall'ordine di visita."""
    from main import costruisci_sessione
    from motore import mob_di_stanza, zona_corrente

    sessione = costruisci_sessione(seed=3)
    zona = zona_corrente()
    prima = [getattr(mob_di_stanza(1, zona, s), "slug", None) for s in range(6)]
    seconda = [getattr(mob_di_stanza(1, zona, s), "slug", None) for s in reversed(range(6))]
    assert prima == list(reversed(seconda))
    sessione.esci()
