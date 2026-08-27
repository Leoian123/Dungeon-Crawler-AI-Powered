"""Sistema SKILL (nodo S): «il sistema conta tutto». Si prova: il contratto
(attive che governano mosse, pratiche dal vocabolario chiuso), la curva del
livello DERIVATO (triangolare, cap, dotazione come pavimento), l'osservatore
(conta solo il protagonista, pubblica i gradini), l'effetto delle attive nel
check 2 (livello 1 = byte-identico), il tomo che insegna (permanente), la
persistenza dei conteggi, il catalogo demo. Contenuto sintetico e originale."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts import (
    BusEventi,
    ColpoInferto,
    CombatResolved,
    PraticaSkill,
    RiposoConcluso,
    SkillAsset,
    SkillMigliorata,
    TransizioneZona,
)
from motore import calibrazione as cal
from motore import crea_protagonista, protagonista
from motore.skill import (
    attiva_osservatore_skill,
    fattore_skill,
    livello_da_usi,
    monta_skill,
    skill_correnti,
    skill_vista,
)


def _asset(slug: str = "lama-di-prova", **kw) -> SkillAsset:
    dati = {
        "slug": slug, "nome": "Lama di prova",
        "testo": "La pratica del ferro corto, contata un colpo alla volta.",
        "tipo": "attiva", "pratica": "mossa", "mossa": "attacco",
        "dominio": "combattimento", "intensita": "marcata",
    }
    dati.update(kw)
    # L'attiva dichiara la sua magnitudine; la passiva di default è tono.
    if dati["tipo"] == "attiva":
        dati.setdefault("effetto", "potenza_mossa")
    return SkillAsset.model_validate(dati)


def _mondo_con(assets) -> tuple:
    crea_protagonista(destrezza=5, punti_vita=30, id_dominio="prova")
    monta_skill(assets)
    bus = BusEventi()
    osservatore = attiva_osservatore_skill(bus)
    gradini: list[SkillMigliorata] = []
    bus.registra(SkillMigliorata, gradini.append)
    return bus, osservatore, gradini


# --- Il contratto ---------------------------------------------------------------

def test_il_contratto_e_coerente() -> None:
    with pytest.raises(ValidationError):
        _asset(mossa="")                    # pratica MOSSA senza chiave
    with pytest.raises(ValidationError):
        _asset(pratica="fuga")              # attiva su pratica non-mossa
    with pytest.raises(ValidationError):
        _asset(pratica="fuga", tipo="passiva")  # passiva fuga CON mossa
    _asset(pratica="fuga", tipo="passiva", mossa="")   # passiva pulita: ok
    _asset()                                            # attiva su mossa: ok


def test_il_contratto_della_competenza() -> None:
    """Ratifica 2026-08-27: la skill è una COMPETENZA — l'attiva dichiara
    potenza_mossa, gli effetti passivi stanno sulle passive, la mondana è
    tono e mai potere."""
    with pytest.raises(ValidationError):
        _asset(effetto="margine_fuga")      # attiva con effetto non suo
    with pytest.raises(ValidationError):
        _asset(tipo="passiva", pratica="fuga", mossa="",
               effetto="potenza_mossa")     # potenza_mossa è delle attive
    with pytest.raises(ValidationError):
        _asset(tipo="passiva", pratica="riposo", mossa="",
               dominio="mondana", effetto="resa_riposo")  # mondana con potere
    _asset(tipo="passiva", pratica="riposo", mossa="",
           dominio="mondana")               # mondana di tono: ok
    ok = _asset(tipo="passiva", pratica="fuga", mossa="",
                dominio="movimento", effetto="margine_fuga")
    assert ok.intensita.value == "marcata"


# --- La curva del livello (derivata, mai depositata) ----------------------------

def test_la_curva_e_triangolare_col_pavimento_e_il_cap(monkeypatch) -> None:
    monkeypatch.setattr(cal, "SKILL_USI_LIVELLO_BASE", 3)
    monkeypatch.setattr(cal, "SKILL_LIVELLO_CAP", 5)
    assert [livello_da_usi(u) for u in (0, 2, 3, 8, 9, 17, 18, 29, 30, 999)] == \
        [1, 1, 2, 2, 3, 3, 4, 4, 5, 5], "salire al livello n costa base·(n−1)"
    assert livello_da_usi(0, livello_iniziale=3) == 3, "la dotazione è un pavimento"
    assert livello_da_usi(30, livello_iniziale=3) == 5, "e non blocca la crescita"
    assert livello_da_usi(10**6) == 5, "il cap tiene"


# --- L'osservatore: conta i fatti, solo il protagonista -------------------------

def test_la_pratica_conta_solo_il_protagonista(mondo_isolato) -> None:
    bus, osservatore, gradini = _mondo_con((_asset(),))
    colpo = dict(bersaglio="Slime", danno=3, hp_rimasti=5, hp_max=8, mossa="attacco")
    for _ in range(3):
        bus.pubblica(ColpoInferto(attaccante="", **colpo))
    bus.pubblica(ColpoInferto(attaccante="Slime", **colpo))  # il mob non pratica
    bus.pubblica(ColpoInferto(attaccante="", bersaglio="Slime", danno=3,
                              hp_rimasti=5, hp_max=8, mossa="dardo_arcano"))
    comp = skill_correnti()
    assert comp.usi["lama-di-prova"] == 3, "tre colpi del crawler, con la SUA mossa"
    assert [g.livello for g in gradini] == [2], "il gradino suona una volta, al 2"
    osservatore.chiudi()


def test_le_pratiche_non_combat(mondo_isolato) -> None:
    bus, osservatore, _ = _mondo_con((
        _asset("gambe", tipo="passiva", pratica="fuga", mossa=""),
        _asset("sonno", tipo="passiva", pratica="riposo", mossa=""),
        _asset("passo", tipo="passiva", pratica="zona", mossa=""),
    ))
    bus.pubblica(CombatResolved(entita=0, vittoria=False, fuga=True))
    bus.pubblica(CombatResolved(entita=0, vittoria=True))          # non è fuga
    bus.pubblica(RiposoConcluso(
        tick_spesi=4, hp_recuperati=6, mana_recuperato=0, interrotto=False))
    bus.pubblica(RiposoConcluso(
        tick_spesi=1, hp_recuperati=1, mana_recuperato=0, interrotto=True))
    bus.pubblica(TransizioneZona(zona="d", tier="distretto"))
    comp = skill_correnti()
    assert comp.usi == {"gambe": 1, "sonno": 1, "passo": 1}, (
        "la vittoria non è una fuga, il riposo interrotto non è un riposo"
    )
    osservatore.chiudi()


# --- L'effetto delle attive (S2) ------------------------------------------------

def test_il_fattore_scala_con_livello_e_fascia(mondo_isolato, monkeypatch) -> None:
    """La magnitudine è dichiarata PER-SKILL (effetto × intensità × §11):
    «Calpestare 15 fa la differenza con Calpestare 10» — a fascia marcata il
    delta fra due livelli è la build, non una tacca."""
    import esper

    monkeypatch.setattr(cal, "SKILL_USI_LIVELLO_BASE", 3)
    monkeypatch.setattr(cal, "SKILL_LIVELLO_CAP", 20)
    bus, osservatore, _ = _mondo_con((_asset(),))  # marcata: 0.06/livello
    pent = protagonista()[0]
    assert fattore_skill(pent, "attacco") == 1.0, "livello 1 = storico intatto"
    assert fattore_skill(pent, "dardo_arcano") == 1.0, "mossa non governata"

    skill_correnti().usi["lama-di-prova"] = 9    # livello 3
    assert fattore_skill(pent, "attacco") == pytest.approx(1.12)
    rate = cal.COMPETENZA_RATE["potenza_mossa"]["marcata"]
    base = cal.SKILL_USI_LIVELLO_BASE
    skill_correnti().usi["lama-di-prova"] = base * 10 * 9 // 2   # livello 10
    a10 = fattore_skill(pent, "attacco")
    skill_correnti().usi["lama-di-prova"] = base * 15 * 14 // 2  # livello 15
    a15 = fattore_skill(pent, "attacco")
    assert a15 - a10 == pytest.approx(rate * 5), (
        "cinque livelli di pratica sono una differenza REALE, non una tacca"
    )
    mob = esper.create_entity()
    assert fattore_skill(mob, "attacco") == 1.0, "i mob non praticano"
    osservatore.chiudi()


def test_la_superficie_del_substrato(mondo_isolato) -> None:
    """`livello_competenza` e `livello_dominio`: l'API che i sistemi futuri
    (magia, artigianato) leggeranno come gate — mai numeri loro."""
    from motore.skill import livello_competenza, livello_dominio

    bus, osservatore, _ = _mondo_con((
        _asset(),
        _asset("filo", mossa="dardo_arcano", dominio="magia"),
        _asset("sonno", tipo="passiva", pratica="riposo", mossa="",
               dominio="sopravvivenza", effetto="resa_riposo"),
    ))
    assert livello_dominio("magia") == 1 and livello_dominio("artigianato") == 0
    skill_correnti().usi["filo"] = 9   # livello 3
    assert livello_competenza("filo") == 3
    assert livello_dominio("magia") == 3, "il dominio vale la sua skill migliore"
    assert livello_competenza("fantasma-inesistente") == 0
    osservatore.chiudi()


def test_i_consumatori_di_sopravvivenza_e_movimento(mondo_isolato) -> None:
    """Riposo, fuga e agguati leggono la competenza nel LORO punto: a livello
    1 tutto è identità (storico intatto), col livello la resa sale, il
    margine si sposta, il dado si attenua col pavimento 0.5."""
    from motore.skill import (
        bonus_margine_fuga,
        bonus_resa_riposo,
        fattore_esca_agguati,
    )

    bus, osservatore, _ = _mondo_con((
        _asset("gambe", tipo="passiva", pratica="fuga", mossa="",
               dominio="movimento", effetto="margine_fuga"),
        _asset("sonno", tipo="passiva", pratica="riposo", mossa="",
               dominio="sopravvivenza", effetto="resa_riposo"),
        _asset("passo", tipo="passiva", pratica="zona", mossa="",
               dominio="movimento", effetto="esca_agguati"),
    ))
    assert bonus_margine_fuga() == 0
    assert bonus_resa_riposo() == 0
    assert fattore_esca_agguati() == 1.0

    comp = skill_correnti()
    comp.usi["gambe"] = 9    # livello 3: marcata 1.0/livello → +2 margine
    comp.usi["sonno"] = 18   # livello 4: marcata 0.35 → floor(1.05) = +1 hp/tick
    comp.usi["passo"] = 9    # livello 3: marcata 0.04 → ×0.92
    assert bonus_margine_fuga() == 2
    assert bonus_resa_riposo() == 1
    assert fattore_esca_agguati() == pytest.approx(0.92)
    comp.usi["passo"] = 10**6  # oltre ogni cap: il pavimento tiene
    assert fattore_esca_agguati() >= 0.5
    osservatore.chiudi()


def test_la_resa_del_riposo_arriva_in_partita(mondo_isolato) -> None:
    """Cablaggio, non formula: `riposa` cura di più con la competenza alta —
    stesso harness dei test di quiete, differenza misurata sugli HP."""
    from contracts import TipoStanza
    from motore import mappa_corrente, riposa, segna_visitata
    from motore.fase import crea_entita_fase
    from tests.contenuti_sintetici import piano_territoriale, stagione_sintetica
    from main import _stagione_a_attiva
    from motore import (
        avvia_territorio, crea_profondita, crea_seme, crea_stagione,
        crea_tempo_piano,
    )

    crea_profondita()
    crea_seme(7)
    crea_tempo_piano()
    crea_stagione(_stagione_a_attiva(stagione_sintetica(
        piani=[piano_territoriale(1)], slug="s-skillriposo")))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    crea_entita_fase()
    avvia_territorio(1)
    segna_visitata()
    monta_skill((_asset("sonno", tipo="passiva", pratica="riposo", mossa="",
                        dominio="sopravvivenza", effetto="resa_riposo"),))
    bus = BusEventi()
    _e, mappa = mappa_corrente()
    mappa.piano.tipi[mappa.stanza_corrente] = TipoStanza.SAFE_ROOM  # riposo pieno

    scheda = protagonista()[2]
    scheda.punti_vita = 1
    base = riposa(bus)
    assert base is not None and not base.interrotto

    skill_correnti().usi["sonno"] = 18   # livello 4 → +1 hp/tick
    scheda.punti_vita = 1
    con_skill = riposa(bus)
    assert con_skill.hp_recuperati > base.hp_recuperati, (
        "la competenza di riposo deve rendere di più, in partita"
    )
    assert con_skill.hp_recuperati == base.hp_recuperati + con_skill.tick_spesi, (
        "+1 HP per ogni tick speso (marcata, livello 4)"
    )


def test_il_fattore_entra_nel_check2_in_un_solo_round(mondo_isolato) -> None:
    from motore.azione import Danno, QuantitaDa
    from motore.combattimento import check2

    crea_protagonista(destrezza=5, punti_vita=30, id_dominio="prova")
    pent = protagonista()[0]
    import esper

    from motore.statistiche import Primarie

    nudo = esper.create_entity(Primarie(valori={}))
    danno = Danno(quantita_da=QuantitaDa.ATK_EFF)
    base = check2(1.0, pent, nudo, danno)
    con_pratica = check2(1.0, pent, nudo, danno, fattore=1.5)
    assert con_pratica > base
    assert check2(1.0, pent, nudo, danno, fattore=1.0) == base, (
        "fattore 1.0 = byte-identico allo storico"
    )


# --- S7: la skill IN SÉ dell'oggetto (canale GearTome) --------------------------

def test_il_contratto_del_gear_che_porta_skill() -> None:
    """«Non tutti gli oggetti possono avere skill, ma alcuni sì»: gli
    indossabili la portano in coppia (slug + livelli), il consumabile mai."""
    from contracts import OggettoAsset

    with pytest.raises(ValidationError):
        OggettoAsset(slug="anello-muto", nome="Anello", tipo="accessorio",
                     grado="argento", sede="dita", skill="filo-di-mana")
    with pytest.raises(ValidationError):
        OggettoAsset(slug="anello-vuoto", nome="Anello", tipo="accessorio",
                     grado="argento", sede="dita", skill_livelli=2)
    with pytest.raises(ValidationError):
        OggettoAsset(slug="brodo-sapiente", nome="Brodo", tipo="consumabile",
                     grado="bronzo", effetto="cura",
                     skill="filo-di-mana", skill_livelli=2)
    ok = OggettoAsset(slug="anello-s", nome="Anello", tipo="accessorio",
                      grado="argento", sede="dita",
                      skill="filo-di-mana", skill_livelli=2)
    assert (ok.skill, ok.skill_livelli) == ("filo-di-mana", 2)


def test_il_pezzo_indossato_alza_il_livello_effettivo(mondo_isolato) -> None:
    """La build del canone: «la stessa skill a +1 o +5». Indossi → il livello
    effettivo sale (e con lui fattori, vista, dominio); togli → torna suo.
    Derivato alla lettura, mai depositato."""
    from contracts import OggettoAsset
    from motore import oggetto_da_asset
    from motore.equip import equipaggia, togli
    from motore.skill import livello_competenza, livello_dominio

    bus, osservatore, _ = _mondo_con((
        _asset("filo", mossa="dardo_arcano", dominio="magia"),
    ))
    pent = protagonista()[0]
    anello = oggetto_da_asset(OggettoAsset(
        slug="anello-s", nome="Anello del Suggeritore", tipo="accessorio",
        grado="argento", sede="dita", skill="filo", skill_livelli=2,
    ))
    assert livello_competenza("filo") == 1
    assert equipaggia(pent, anello)
    assert livello_competenza("filo") == 3, "1 di base + 2 dal pezzo"
    assert livello_dominio("magia") == 3, "il dominio segue il livello effettivo"
    assert fattore_skill(pent, "dardo_arcano") > 1.0, (
        "la mossa governata scala già: il gear È la build"
    )
    togli(pent, "anello-s")
    assert livello_competenza("filo") == 1, "sfilato il pezzo, il livello torna suo"
    osservatore.chiudi()


def test_il_lint_chiude_tomo_e_skill_ignote(mondo_isolato) -> None:
    """Punto 5 del censimento: gli errori d'authoring si dicono al GATE, non
    al giocatore che ha speso il drop."""
    from contracts import OggettoAsset
    from motore import lint_oggetto

    tomo_rotto = OggettoAsset(
        slug="tomo-rotto", nome="Tomo", tipo="consumabile", grado="argento",
        effetto="tomo", insegna_mossa="mossa-inventata",
    )
    assert any("insegna" in e or "catalogo mosse" in e
               for e in lint_oggetto(tomo_rotto))
    tomo_ok = OggettoAsset(
        slug="tomo-ok", nome="Tomo", tipo="consumabile", grado="argento",
        effetto="tomo", insegna_mossa="morso_velenoso",
    )
    assert lint_oggetto(tomo_ok) == []

    anello = OggettoAsset(
        slug="anello-x", nome="Anello", tipo="accessorio", grado="argento",
        sede="dita", skill="skill-inventata", skill_livelli=2,
    )
    assert any("catalogo skill" in e
               for e in lint_oggetto(anello, skill_ammesse={"filo-di-mana"}))
    assert lint_oggetto(anello) == [], "senza catalogo il check si dichiara saltato"


def test_la_stagione_seed_risolve_il_gear_con_skill(run_pulita) -> None:
    """I due demo (anello del suggeritore, schinieri del disertore) passano il
    lint del composition root e ATTRAVERSANO il freeze con la loro skill —
    il baco della conversione (effetto/skill persi) resta chiuso."""
    from main import risolvi_stagione, _stagione_a_attiva

    attiva = _stagione_a_attiva(risolvi_stagione("stagione-1"))
    per_slug = {o.slug: o for o in attiva.oggetti}
    anello = per_slug["anello-del-suggeritore"]
    assert (anello.skill, anello.skill_livelli) == ("filo-di-mana", 2)
    schinieri = per_slug["schinieri-del-disertore"]
    assert (schinieri.skill, schinieri.skill_livelli) == ("gambe-in-spalla", 2)


def test_l_affisso_di_fabbrica_imprime_la_skill_sul_conio(mondo_isolato) -> None:
    """S7, il conio che pesca competenza: l'affisso «Veterano» della fabbrica
    seed porta gambe-in-spalla +1 — il pezzo coniato con quell'affisso la
    imprime; lo scarto (che perde gli affissi) non la porta mai."""
    import random

    from main import _stagione_a_attiva, risolvi_stagione
    from motore import conia_procedurale, crea_stagione, fabbrica_attiva
    from tests.persist_helpers import costruisci_run

    costruisci_run()
    crea_stagione(_stagione_a_attiva(risolvi_stagione("stagione-1")))
    fabbrica = fabbrica_attiva()
    assert any(a.skill for a in fabbrica.affissi), (
        "la fabbrica seed deve avere un affisso con skill (Veterano)"
    )
    con_skill = None
    for i in range(300):
        o = conia_procedurale(random.Random(i), "oro", qualita="onesto")
        if o.skill:
            con_skill = o
            break
    assert con_skill is not None, "in 300 coni l'affisso con skill deve uscire"
    assert (con_skill.skill, con_skill.skill_livelli) == ("gambe-in-spalla", 1)
    scarto = conia_procedurale(random.Random(3), "oro", qualita="scarto")
    assert scarto.skill == "", "lo scarto perde gli affissi, e con loro la skill"


def test_le_competenze_notevoli_entrano_nel_fascicolo(mondo_isolato) -> None:
    """S8: dal livello-soglia in su la competenza (non mondana) è una riga
    del fascicolo GM — il master narra il mestiere, mai la statistica."""
    from motore.gm import _riga_competenze

    crea_protagonista(destrezza=5, punti_vita=30, id_dominio="prova")
    monta_skill((
        _asset("filo", mossa="dardo_arcano", dominio="magia"),
        _asset("resp", tipo="passiva", pratica="riposo", mossa="",
               dominio="mondana", livello_iniziale=5),
    ))
    assert _riga_competenze() == "", (
        "sotto soglia niente riga; la mondana non entra nemmeno a livello 5"
    )
    skill_correnti().usi["filo"] = 9   # livello 3 = soglia di default
    riga = _riga_competenze()
    assert "Lama di prova 3" in riga and "5" not in riga


# --- Persistenza: i conteggi attraversano il save -------------------------------

def test_i_conteggi_round_trippano_nel_save(mondo_isolato, tmp_path) -> None:
    import esper

    from motore import applica_stato, carica_da_disco, salva_run
    from tests.persist_helpers import costruisci_run

    costruisci_run()
    monta_skill((_asset(),))
    skill_correnti().usi["lama-di-prova"] = 7
    salva_run(tmp_path, model_id="m1", timestamp=1.0)
    esper.clear_database()
    applica_stato(carica_da_disco(tmp_path, "carl"))
    comp = skill_correnti()
    assert comp is not None and comp.usi["lama-di-prova"] == 7
    assert comp.catalogo[0].slug == "lama-di-prova", "il catalogo viaggia congelato"


# --- Il catalogo demo e il default-on -------------------------------------------

def test_il_catalogo_demo_e_lintato() -> None:
    from main import catalogo_skill
    from motore.mosse import mosse_note

    catalogo = catalogo_skill()
    assert len(catalogo) >= 6, f"catalogo magro: {len(catalogo)}"
    slugs = [a.slug for a in catalogo]
    assert len(slugs) == len(set(slugs))
    for a in catalogo:
        if a.tipo == "attiva":
            assert a.mossa in mosse_note(), (
                f"{a.slug}: un'attiva governa una mossa del catalogo, "
                f"{a.mossa!r} non esiste"
            )
    assert any(a.livello_iniziale > 1 for a in catalogo), (
        "il junk di dotazione ad alto livello è metà del tono (golden standard)"
    )
    assert any(a.tipo == "passiva" for a in catalogo)


def test_default_on_e_run_pulita(run_pulita, tmp_path) -> None:
    from main import catalogo_skill, costruisci_sessione

    sessione = costruisci_sessione(seed=3, directory=tmp_path / "a", nome="Roberta")
    comp = skill_correnti()
    assert comp is not None and len(comp.catalogo) == len(catalogo_skill())
    righe = sessione.skill_vista()
    assert righe and all(r.livello >= 1 for r in righe)
    assert any(r.livello >= 3 for r in righe), "la dotazione junk parte alta"
    # La scheda porta il livello della mossa governata (SkillVista.livello).
    scheda = sessione.scheda()
    assert all(s.livello >= 1 for s in scheda.skills)
    sessione.esci()

    pulita = costruisci_sessione(
        seed=3, directory=tmp_path / "b", nome="Roberta", skill=(),
    )
    assert skill_correnti() is None, "() esplicito = registro spento"
    pulita.esci()


def test_e2e_la_pratica_sale_giocando(run_pulita, tmp_path) -> None:
    """Via porte: uno scontro vero → i colpi del crawler contano, la vista
    porta usi e livello, e la cronaca annuncia i gradini quando arrivano."""
    import asyncio

    from contracts import PlayerChoseOption
    from main import CronacaBus, costruisci_sessione

    sessione = costruisci_sessione(nome="Pratica", seed=11, directory=tmp_path)
    cronaca = CronacaBus(sessione.bus)
    snap = asyncio.run(sessione.prossima_narrazione())
    combatti = next(
        (o.indice for o in snap.opzioni if o.etichetta.startswith("Combatti")),
        None,
    )
    assert combatti is not None, "il seed 11 apre con uno scontro noto"
    sessione.coda.accoda(PlayerChoseOption(combatti))
    snap = sessione.avanza()
    for _ in range(60):
        if snap.fase != "combattimento" or sessione.terminale is not None:
            break
        sessione.coda.accoda(PlayerChoseOption(0))  # la prima mossa del menu
        snap = sessione.avanza()

    usi_totali = sum(r.usi for r in sessione.skill_vista())
    assert usi_totali > 0, "i colpi a segno del crawler devono contare"
    tipi = {t for t, _ in cronaca.preleva_tipata()}
    # Il gradino può o meno essere arrivato (dipende dai colpi): se è arrivato,
    # è passato TIPATO dalla cronaca.
    if any(r.livello > max(1, _dotazione(r)) for r in sessione.skill_vista()):
        assert "SkillMigliorata" in tipi
    if sessione.terminale is None:
        sessione.esci()


def _dotazione(riga) -> int:
    from main import catalogo_skill

    for a in catalogo_skill():
        if a.slug == riga.slug:
            return a.livello_iniziale
    return 1


# --- Il tomo (S3, canale GearTome) ----------------------------------------------

def test_il_tomo_insegna_una_volta_sola(mondo_isolato) -> None:
    from motore import assicura_zaino, usa_consumabile
    from motore.combattimento import mosse_di

    crea_protagonista(destrezza=5, punti_vita=30, id_dominio="prova")
    pent = protagonista()[0]
    assert "morso_velenoso" not in mosse_di(pent)
    assicura_zaino(pent).fonti.append("quaderno-del-morso")
    ok, dettaglio = usa_consumabile(pent, "quaderno-del-morso", BusEventi())
    assert ok is True and "morso" in dettaglio
    assert "morso_velenoso" in mosse_di(pent), "la mossa è nel Repertorio"
    assert "quaderno-del-morso" not in assicura_zaino(pent).fonti, "monouso"

    # Un secondo tomo identico: rifiutato, NON consumato.
    assicura_zaino(pent).fonti.append("quaderno-del-morso")
    ok, dettaglio = usa_consumabile(pent, "quaderno-del-morso", BusEventi())
    assert ok is False and "conosci" in dettaglio
    assert "quaderno-del-morso" in assicura_zaino(pent).fonti


def test_la_mossa_insegnata_round_trippa(mondo_isolato, tmp_path) -> None:
    import esper

    from motore import applica_stato, assicura_zaino, carica_da_disco, salva_run, usa_consumabile
    from motore.combattimento import mosse_di
    from tests.persist_helpers import costruisci_run

    pent = costruisci_run()
    assicura_zaino(pent).fonti.append("quaderno-del-morso")
    assert usa_consumabile(pent, "quaderno-del-morso", BusEventi())[0]
    salva_run(tmp_path, model_id="m1", timestamp=1.0)
    esper.clear_database()
    applica_stato(carica_da_disco(tmp_path, "carl"))
    pent2 = protagonista()[0]
    assert "morso_velenoso" in mosse_di(pent2), "l'insegnamento è permanente"
