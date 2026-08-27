"""Il PARLAMENTO (asse social S2, decisioni utente 2026-08-16).

Le regole bloccate qui:
- I mob OSTILI parlamentano solo superando un margine di CARISMA contro la
  classe del loro grado (`classe_da_grado`); il tentativo è UNO per mob e il
  marker PERSISTE (anti-pesca sociale, anche oltre il load).
- Solo le categorie INTERPELLABILI (maestro_gilda, manager) rompono il divieto
  del menu (verbale 2026-08-10); l'ORDINARIO resta GM-pilotato, il NARRATORE
  parla senza replica.
- La VOCE è obbligo di forma per gli interpellabili e VESTE i prompt: dialoghi
  diversi «per cadenza, scelta di frasi e formazione», non solo a parole.
- Le mine del rilievo restano disinnescate: PARLAMENTA ha la sua foglia
  `DURATA_AZIONE` (niente KeyError), il ramo esplicito (niente scontro dal
  fall-through), il segnale `scena_aperta` (niente turno GM in mezzo al
  dialogo), la chiusura anticipata offline (niente 12 righe mute).
"""

from __future__ import annotations

import asyncio

import esper

from contracts import CategoriaPng, Grado, PlayerChoseOption, StatId, TipoAzione
from main import costruisci_sessione
from provider import FakeProvider


def _sessione_con_mob(seed: int = 1):
    sessione = costruisci_sessione(seed=seed)
    snap = asyncio.run(sessione.prossima_narrazione())
    assert any(o.tipo is TipoAzione.PARLAMENTA for o in snap.opzioni), (
        "l'ostile mai tentato deve essere parlamentabile"
    )
    return sessione, snap


def _indice(snap, tipo):
    return next(o.indice for o in snap.opzioni if o.tipo is tipo)


def _carisma(sessione, valore: int) -> None:
    from motore.scheda import protagonista
    from motore.statistiche import Primarie

    pent, _m, _s = protagonista()
    esper.component_for_entity(pent, Primarie).valori[StatId.CARISMA] = valore


# --- Il gate: margine di carisma vs classe del grado ---------------------------

def test_il_carisma_alto_apre_la_scena(run_pulita) -> None:
    sessione, snap = _sessione_con_mob()
    _carisma(sessione, 40)  # sopra ogni soglia: il mob ascolta
    sessione.coda.accoda(PlayerChoseOption(_indice(snap, TipoAzione.PARLAMENTA)))
    snap = sessione.avanza()
    assert snap.scena_aperta, "il gate superato apre la scena"
    assert snap.fase == "narrazione", "parlamentare non è mai un ingaggio"


def test_il_carisma_basso_viene_rifiutato_e_il_tentativo_e_speso(run_pulita) -> None:
    """Il fallito è fallito (anti-pesca sociale): niente scena, riga-fatto del
    motore, e la voce NON si ricompone mai più per quel mob."""
    sessione, snap = _sessione_con_mob()
    _carisma(sessione, 1)  # sotto la soglia bronzo (6)
    sessione.coda.accoda(PlayerChoseOption(_indice(snap, TipoAzione.PARLAMENTA)))
    snap = sessione.avanza()
    assert not snap.scena_aperta
    assert sessione.ultimo_rifiuto and "carisma" in sessione.ultimo_rifiuto, (
        "il tiro non è mai muto: la riga-fatto arriva all'host"
    )
    assert all(o.tipo is not TipoAzione.PARLAMENTA for o in snap.opzioni), (
        "il tentativo è UNO per mob: la voce è sparita"
    )


def test_il_marker_del_tentativo_persiste_nel_save(run_pulita, tmp_path) -> None:
    """Anti-pesca oltre il load: salva dopo il rifiuto, ricarica — il mob non
    è tornato parlamentabile."""
    sessione = costruisci_sessione(seed=1, directory=tmp_path, nome="Carl")
    snap = asyncio.run(sessione.prossima_narrazione())
    _carisma(sessione, 1)
    sessione.coda.accoda(PlayerChoseOption(_indice(snap, TipoAzione.PARLAMENTA)))
    sessione.avanza()
    uuid = sessione.uuid
    sessione.esci()
    from main import carica_sessione

    ripresa = carica_sessione(uuid=uuid, directory=tmp_path)
    snap = ripresa.avanza()
    assert all(o.tipo is not TipoAzione.PARLAMENTA for o in snap.opzioni), (
        "il marker parlamento_tentato non è round-trippato nel save"
    )


def test_la_difficolta_segue_il_grado_del_mob(run_pulita) -> None:
    """Parlare con un mob d'ORO è una prova d'ORO: stesso carisma, esiti
    diversi al variare del grado — la scala sociale è la scala del gioco."""
    from motore import EntitaMob, tenta_parlamento
    from motore.scena import puo_parlamentare

    sessione, _snap = _sessione_con_mob()
    _carisma(sessione, 7)  # sopra bronzo (6), sotto oro (14)
    from motore import mob_corrente

    mob = mob_corrente()
    em = esper.component_for_entity(mob, EntitaMob)
    em.grado = Grado.ORO
    esito = tenta_parlamento(mob)
    assert esito is not None and not esito.riuscito, "7 < soglia oro: rifiutato"
    em.parlamento_tentato = False  # reset di laboratorio
    em.grado = Grado.BRONZO
    esito = tenta_parlamento(mob)
    assert esito is not None and esito.riuscito, "7 > soglia bronzo: ascolta"


# --- Il convinto riascolta (P1 playtest a 3 persone, 2026-08-27) ----------------

def test_il_convinto_riascolta_senza_ritirare(run_pulita) -> None:
    """Il successo bruciava il Parlamenta come il rifiuto: la chiacchierona
    non poteva più parlare coi suoi «amici». Ora il CONVINTO riascolta — la
    voce resta nel menu e riaprire la scena non ri-tira il gate (il margine
    non si ri-pesca: anti-pesca vale anche al contrario). Il RIFIUTATO resta
    rifiutato: quel lucchetto non si tocca."""
    from motore import EntitaMob, mob_corrente, tenta_parlamento
    from motore.scena import puo_parlamentare

    sessione, _snap = _sessione_con_mob()
    _carisma(sessione, 40)
    mob = mob_corrente()
    em = esper.component_for_entity(mob, EntitaMob)
    esito = tenta_parlamento(mob)
    assert esito is not None and esito.riuscito
    assert puo_parlamentare(mob), "il convinto deve restare interpellabile"
    # La riapertura NON è una seconda prova: nessun nuovo tiro, esito già suo.
    _carisma(sessione, 1)  # se il gate ritirasse, ora fallirebbe
    secondo = tenta_parlamento(mob)
    assert secondo is not None and secondo.riuscito
    assert "ascolta ancora" in secondo.riga_fatto
    assert em.parlamento_riuscito, "la tregua resta"


def test_il_rifiutato_resta_rifiutato(run_pulita) -> None:
    from motore import mob_corrente, tenta_parlamento
    from motore.scena import puo_parlamentare

    sessione, _snap = _sessione_con_mob()
    _carisma(sessione, 1)
    mob = mob_corrente()
    esito = tenta_parlamento(mob)
    assert esito is not None and not esito.riuscito
    assert not puo_parlamentare(mob)
    assert tenta_parlamento(mob) is None  # il tentativo è speso: nessun bis


# --- La tregua del parlamentato (playtest giro 3, 2026-08-16) ------------------

def test_il_gate_superato_marca_la_tregua(run_pulita) -> None:
    """Il gate scrive ANCHE l'esito, non solo il tentativo: superato = tregua
    (`parlamento_riuscito`), fallito = nessuna tregua (il rifiutato resta un
    nemico e può imboscarti)."""
    from motore import EntitaMob, mob_corrente, nomi_in_tregua, tenta_parlamento

    sessione, _snap = _sessione_con_mob()
    _carisma(sessione, 40)
    mob = mob_corrente()
    em = esper.component_for_entity(mob, EntitaMob)
    esito = tenta_parlamento(mob)
    assert esito is not None and esito.riuscito
    assert em.parlamento_riuscito and em.nome in nomi_in_tregua()
    # Reset di laboratorio COMPLETO: il convinto ora riascolta senza ritirare
    # (P1 playtest a 3 persone) — per rigiocare il gate serve un mob vergine.
    em.parlamento_tentato = False
    em.parlamento_riuscito = False
    _carisma(sessione, 1)
    esito = tenta_parlamento(mob)
    assert esito is not None and not esito.riuscito
    assert not em.parlamento_riuscito and em.nome not in nomi_in_tregua(), (
        "il rifiutato non è in tregua: il gate fallito non protegge nessuno"
    )


def test_il_parlamentato_non_ti_imbosca(run_pulita) -> None:
    """Il feel del playtest: il mob parlamentato con successo ti IMBOSCAVA al
    tick dopo (il compositore non conosceva la scena). Stesso tick e stesso
    seed: senza tregua l'agguato pesca un nome; con quel nome in tregua ne
    pesca UN ALTRO (filtro duro su tabella e cast, sagoma di budget in fondo
    — l'imboscata resta, cambia l'imboscatore)."""
    from contracts import Grado
    from motore import EntitaMob, nome_nemico_incontro
    from motore.incontri import componi_imboscata_scena

    _sessione_con_mob()
    incontro = componi_imboscata_scena()
    nome_pescato = nome_nemico_incontro(incontro)
    assert nome_pescato, "l'agguato di riferimento deve avere un nemico"
    esper.create_entity(EntitaMob(
        archetipo="zombie", grado=Grado.BRONZO, nome=nome_pescato,
        descrizione="", livello=1, stanza=3, parlamento_riuscito=True,
    ))
    ribattuto = componi_imboscata_scena()  # stesso tick, stesso stream seeded
    assert nome_nemico_incontro(ribattuto) != nome_pescato, (
        "il compositore d'imboscata ha ignorato la tregua del parlamentato"
    )


def test_la_tregua_sopravvive_al_giro_di_zona(run_pulita) -> None:
    """Gemello del lucchetto sui tentativi spesi: la tregua viaggia nella
    fotografia dello StatoTerritorio (`parlamenti_riusciti`) — senza, il giro
    di zona rimaterializzava il mob dal seed con la tregua azzerata e il
    personaggio che ti aveva ascoltato tornava a imboscarti."""
    from motore import (
        EntitaMob,
        mob_corrente,
        nomi_in_tregua,
        stato_territorio,
        tenta_parlamento,
    )
    from motore.piano import livello_corrente
    from motore.territorio import (
        _fotografa_vivi_di_zona,
        _rimaterializza_vivi,
        zona_da_chiave,
    )

    sessione, _snap = _sessione_con_mob()
    _carisma(sessione, 40)
    mob = mob_corrente()
    stanza_del_mob = esper.component_for_entity(mob, EntitaMob).stanza
    esito = tenta_parlamento(mob)
    assert esito is not None and esito.riuscito
    stato = stato_territorio()
    assert stato is not None
    zona = stato.zona_corrente
    _fotografa_vivi_di_zona()
    assert stanza_del_mob in stato.parlamenti_riusciti.get(zona, []), (
        "la fotografia non registra la tregua"
    )
    esper.delete_entity(mob, immediate=True)
    _rimaterializza_vivi(livello_corrente(), zona_da_chiave(zona), stato)
    rinato = mob_corrente()
    assert rinato is not None, "il vivo fotografato deve tornare"
    em = esper.component_for_entity(rinato, EntitaMob)
    assert em.parlamento_riuscito and em.nome in nomi_in_tregua(), (
        "il mob rimaterializzato ha dimenticato la tregua"
    )


# --- Il rifiuto lascia traccia (playtest giro 3, 2026-08-16) -------------------

def test_il_rifiuto_scrive_la_memoria_interazione(run_pulita) -> None:
    """Il finding del giro 3: il rifiuto al gate non apre scena e quindi non
    passava da [fascicolo/esito-scena] né dalla memoria — il GM poteva narrare
    il mob «disponibile» un tick dopo il voltafaccia. La traccia DURATURA è il
    documento INTERAZIONE, durevole quanto `parlamento_tentato`."""
    from contracts import TipoDocumento
    from motore import nome_mob_corrente

    sessione, snap = _sessione_con_mob()
    nome = nome_mob_corrente()
    _carisma(sessione, 1)
    sessione.coda.accoda(PlayerChoseOption(_indice(snap, TipoAzione.PARLAMENTA)))
    sessione.avanza()
    docs = sessione.memoria_lunga.recupera(nome, tipi=(TipoDocumento.INTERAZIONE,))
    doc = next((d for d in docs if d.id.startswith("parlamento-rifiutato-")), None)
    assert doc is not None, "il rifiuto al gate deve scrivere la memoria INTERAZIONE"
    assert "carisma" in doc.testo, "il documento porta la riga-fatto del motore"
    assert "non ascolterà" in doc.testo, "l'anti-pesca sociale è parte del fatto"


def test_il_rifiuto_entra_nel_fascicolo_del_turno_gm(run_pulita) -> None:
    """Il gemello minimo dell'esito-scena: la riga-fatto del gate arriva al
    prompt del turno GM successivo ([fascicolo/rifiuto-parlamento]) e si
    consuma con la stessa disciplina dei gemelli (mai ri-iniettata)."""
    from contracts import TurnoNarrazione

    sessione, snap = _sessione_con_mob()
    _carisma(sessione, 1)
    sessione.coda.accoda(PlayerChoseOption(_indice(snap, TipoAzione.PARLAMENTA)))
    sessione.avanza()
    assert sessione._rifiuto_parlamento and "carisma" in sessione._rifiuto_parlamento
    fake = FakeProvider([])
    sessione.provider = fake
    riepilogo = sessione.riepiloga_azione("provo di nuovo un cenno di pace")
    asyncio.run(sessione.esegui_azione(riepilogo))
    prompt_gating = next(
        (p for p, schema in fake.chiamate if schema is TurnoNarrazione), None
    )
    assert prompt_gating is not None and "[fascicolo/rifiuto-parlamento]" in prompt_gating
    assert sessione._rifiuto_parlamento == "", (
        "il turno fresco consuma il rifiuto come consuma i gemelli"
    )


# --- La scena aperta: battute, chiusura offline, fascicolo ---------------------

def test_la_battuta_scorre_e_il_menu_vuoto_non_chiama_il_gm(run_pulita) -> None:
    """La mina del menu-vuoto: a scena aperta lo snapshot DICE `scena_aperta`
    e l'host instrada le battute alla porta di scena, mai al turno GM."""
    sessione, snap = _sessione_con_mob()
    _carisma(sessione, 40)
    sessione.coda.accoda(PlayerChoseOption(_indice(snap, TipoAzione.PARLAMENTA)))
    snap = sessione.avanza()
    assert snap.scena_aperta
    sessione.provider = FakeProvider([dict(blocco="battuta", prosa="«Parla in fretta.»")])
    prosa = asyncio.run(sessione.battuta_parlamento("Chi comanda qui?"))
    assert "Parla in fretta" in prosa
    assert sessione.avanza().scena_aperta, "una battuta non chiude la scena"


def test_offline_la_scena_si_chiude_al_secondo_muto(run_pulita) -> None:
    """La mina delle 12 righe mute: col copione (che degrada ogni battito) la
    scena si chiude d'ufficio al SECONDO muto consecutivo."""
    sessione, snap = _sessione_con_mob()
    _carisma(sessione, 40)
    sessione.coda.accoda(PlayerChoseOption(_indice(snap, TipoAzione.PARLAMENTA)))
    assert sessione.avanza().scena_aperta
    # Il provider di sessione è il ProviderCopione: ogni battuta degrada.
    asyncio.run(sessione.battuta_parlamento("Ehi."))
    assert sessione.avanza().scena_aperta, "il primo muto non chiude"
    prosa = asyncio.run(sessione.battuta_parlamento("Mi senti?"))
    assert "muore lì" in prosa
    assert not sessione.avanza().scena_aperta, "al secondo muto la scena è chiusa"


def test_i_fatti_della_scena_entrano_nel_fascicolo_gm(run_pulita) -> None:
    """Il vicolo cieco del rilievo, chiuso: il turno GM successivo EREDITA la
    scena conclusa ([fascicolo/esito-scena])."""
    sessione, snap = _sessione_con_mob()
    _carisma(sessione, 40)
    sessione.coda.accoda(PlayerChoseOption(_indice(snap, TipoAzione.PARLAMENTA)))
    sessione.avanza()
    fake = FakeProvider([dict(blocco="chiudi", prosa="«Vattene.»", esito="conclusa")])
    sessione.provider = fake
    asyncio.run(sessione.battuta_parlamento("Me ne vado."))
    assert not sessione.avanza().scena_aperta
    assert sessione._fatti_scena is not None
    # Il prossimo turno GM (azione libera) porta l'esito nel prompt gating.
    from contracts import TurnoNarrazione

    riepilogo = sessione.riepiloga_azione("proseguo con cautela")
    asyncio.run(sessione.esegui_azione(riepilogo))
    prompt_gating = next(
        (p for p, schema in fake.chiamate if schema is TurnoNarrazione), None
    )
    assert prompt_gating is not None and "[fascicolo/esito-scena]" in prompt_gating


def test_combatti_a_scena_aperta_abbandona_la_scena(run_pulita) -> None:
    """Il rilievo del playtest (giro 2): a scena aperta il menu mostra ancora
    «Combatti» — sceglierlo apriva lo scontro CON la scena appesa
    (`fase=combattimento` E `scena_aperta=True` nello stesso snapshot, segnali
    contraddittori per l'host). L'abbandono ha UN proprietario: l'azione di
    menu che lascia la conversazione."""
    sessione, snap = _sessione_con_mob()
    _carisma(sessione, 40)
    sessione.coda.accoda(PlayerChoseOption(_indice(snap, TipoAzione.PARLAMENTA)))
    snap = sessione.avanza()
    assert snap.scena_aperta
    sessione.coda.accoda(PlayerChoseOption(_indice(snap, TipoAzione.COMBATTI)))
    snap = sessione.avanza()
    assert snap.fase == "combattimento"
    assert not snap.scena_aperta, (
        "lo scontro e la scena aperta non convivono mai nello snapshot"
    )
    assert sessione._fatti_scena is None, (
        "la scena abbandonata non lascia fatti (contratto S1)"
    )


def test_scappi_a_scena_aperta_abbandona_la_scena(run_pulita) -> None:
    """Stessa regola per la ritirata: chi arretra nell'adiacente ha lasciato
    l'interlocutore — mai una scena «aperta» verso una stanza vuota."""
    sessione, snap = _sessione_con_mob()
    _carisma(sessione, 40)
    sessione.coda.accoda(PlayerChoseOption(_indice(snap, TipoAzione.PARLAMENTA)))
    snap = sessione.avanza()
    assert snap.scena_aperta
    sessione.coda.accoda(PlayerChoseOption(_indice(snap, TipoAzione.SCAPPA)))
    snap = sessione.avanza()
    assert not snap.scena_aperta, "la ritirata abbandona la conversazione"


# --- La voce e l'identità vestono il prompt ------------------------------------

def test_la_voce_del_png_veste_il_prompt_di_scena(run_pulita) -> None:
    from contracts import RuoloMob
    from motore import EntitaMob, apri_scena_con_mob

    ent = esper.create_entity(EntitaMob(
        archetipo="zombie", grado=Grado.BRONZO, nome="L'Archivista",
        descrizione="cataloga i caduti", livello=1, stanza=2,
        ruolo=RuoloMob.PNG, categoria="maestro_gilda",
        voce="burocratese d'archivio: frasi da modulo, timbri a metà frase",
    ))
    istanza = apri_scena_con_mob(ent)
    from motore.scena import _prompt_scena

    prompt = _prompt_scena(istanza, "Buongiorno.")
    assert "[scena/png/voce]" in prompt and "burocratese" in prompt
    assert "cadenza" in prompt, "l'istruzione impone la voce, non la suggerisce"


def test_l_interpellabile_esige_la_voce_come_asset(run_pulita) -> None:
    import pytest
    from contracts import MobAsset

    dati = dict(
        slug="manager-muto", nome="Il Manager", archetipo="zombie",
        grado="bronzo", prosa_stanza="Sorride da un contratto.",
        categoria="manager",
    )
    with pytest.raises(Exception, match="voce"):
        MobAsset.model_validate(dati)


def test_il_png_materializzato_dall_asset_e_interpellabile(run_pulita) -> None:
    """L'exploit del playtest 2026-08-16: `MobAsset.categoria` è un ENUM e
    `str(CategoriaPng.MAESTRO_GILDA)` dà "CategoriaPng.MAESTRO_GILDA" — il PNG
    materializzato da un asset vero non era MAI interpellabile (i test
    costruivano `EntitaMob` a mano con la stringa già giusta e non lo
    vedevano). Il canale si prova dall'ASSET, come in gioco."""
    from contracts import MobAsset
    from motore import EntitaMob, materializza_png
    from motore.png import INTERPELLABILI

    sessione, _snap = _sessione_con_mob()
    asset = MobAsset.model_validate(dict(
        slug="archivista-di-prova", nome="L'Archivista", archetipo="zombie",
        grado="bronzo", prosa_stanza="Timbra una scheda.",
        categoria="maestro_gilda", voce="burocratese: frasi da modulo",
    ))
    ent = materializza_png(asset, 1, 0)
    em = esper.component_for_entity(ent, EntitaMob)
    assert em.categoria in INTERPELLABILI, (
        f"la categoria dell'asset deve arrivare come VALORE: {em.categoria!r}"
    )
    assert em.voce == "burocratese: frasi da modulo"


def test_l_ordinario_non_compone_il_menu(run_pulita) -> None:
    """Il verbale 2026-08-10 regge: il PNG ORDINARIO resta GM-pilotato — la
    voce Parlamenta non si compone per lui (e mai per il NARRATORE)."""
    from motore import png_interpellabile_in_stanza
    from motore.png import INTERPELLABILI

    assert CategoriaPng.ORDINARIO.value not in INTERPELLABILI
    assert CategoriaPng.NARRATORE.value not in INTERPELLABILI
    assert png_interpellabile_in_stanza() is None  # nessun PNG in stanza: None pulito
