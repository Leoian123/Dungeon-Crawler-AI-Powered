"""Obiettivi e Box (nodo O, fase O1): il dungeon ti guarda e commenta.

L'osservatore ascolta il BUS TIPIZZATO e sblocca notifiche deterministiche
dal catalogo congelato. Qui si prova: il contratto (la ricompensa non è mai
vuota e muta), lo sblocco sul fatto vero (vittoria arbitrata dal motore),
le condizioni (la fuga non è una vittoria; una condizione su un campo che
l'evento non trasporta non è mai vera), l'idempotenza (non-ripetibile = una
volta per run), la box depositata con id deterministico, e la persistenza
(catalogo/sbloccati/box attraversano il save; il reload non ri-sblocca).

Il contenuto dei test è SINTETICO e ORIGINALE (nota IP del piano).
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from contracts import (
    AchievementAsset,
    BoxRicompensa,
    CategoriaBox,
    CombatResolved,
    EventoTrigger,
    Grado,
    ObiettivoRaggiunto,
    PlayerChoseOption,
    RicompensaObiettivo,
    TriggerObiettivo,
)
from motore import SpecNemico, tick
from motore.obiettivi import attiva_osservatore, monta_obiettivi, obiettivi_correnti
from tests.combat_helpers import avvia_scontro


def _asset(
    slug: str = "debutto-in-societa",
    *,
    evento: EventoTrigger = EventoTrigger.COMBAT_RISOLTO,
    vittoria: bool | None = True,
    fuga: bool | None = None,
    tier: str | None = None,
    custode: bool | None = None,
    senza_graffi: bool | None = None,
    grado_nemico_minimo: Grado | None = None,
    soglia: int | None = None,
    box: tuple[str, str] | None = ("armi", "bronzo"),
    beffa: str = "",
    ripetibile: bool = False,
) -> AchievementAsset:
    ricompensa = RicompensaObiettivo(
        box=BoxRicompensa(categoria=CategoriaBox(box[0]), grado=Grado(box[1]))
        if box is not None else None,
        beffa=beffa,
    )
    return AchievementAsset(
        slug=slug,
        titolo="Debutto in società",
        testo=(
            "Il tuo primo avversario non si rialza. Il pubblico applaude: "
            "qualcuno aveva già scommesso contro di te."
        ),
        trigger=TriggerObiettivo(
            evento=evento, vittoria=vittoria, fuga=fuga, tier=tier,
            custode=custode, senza_graffi=senza_graffi,
            grado_nemico_minimo=grado_nemico_minimo, soglia=soglia,
        ),
        ricompensa=ricompensa,
        ripetibile=ripetibile,
    )


def _vinci(bus, adapter, max_tick: int = 40) -> None:
    for _ in range(max_tick):
        if adapter.events_of(CombatResolved):
            return
        tick()
    raise AssertionError("lo scontro non si è risolto entro il budget di tick")


# --- Il contratto ---------------------------------------------------------------

def test_la_ricompensa_non_e_mai_vuota_e_muta() -> None:
    with pytest.raises(ValidationError):
        RicompensaObiettivo()  # né box né beffa: anche il «niente» si annuncia
    RicompensaObiettivo(beffa="Nessuna. E ridiamo insieme.")  # beffa sola: valida
    RicompensaObiettivo(
        box=BoxRicompensa(categoria=CategoriaBox.ARMI, grado=Grado.BRONZO)
    )


def test_il_ripetibile_con_box_e_rifiutato() -> None:
    """Il lucchetto anti-stampante (breaker 2026-08-26): un obiettivo
    ripetibile che paga una BOX sarebbe farm infinito per un refuso di
    authoring — il contratto lo rifiuta alla nascita. Con la beffa resta
    legittimo (metà del registro comico)."""
    with pytest.raises(ValidationError):
        _asset("stampante", ripetibile=True)  # box di default: rifiutato
    _asset("bis", ripetibile=True, box=None, beffa="Di nuovo. Bravo.")  # ok


# --- Lo sblocco sul fatto -------------------------------------------------------

def test_la_vittoria_sblocca_e_deposita_la_box(mondo_isolato: str) -> None:
    bus, adapter, _enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=1, punti_vita=5)],
        seed=1, hp_prot=10_000, destrezza_prot=50,
    )
    monta_obiettivi((_asset(),))
    osservatore = attiva_osservatore(bus)
    raccolti: list[ObiettivoRaggiunto] = []
    bus.registra(ObiettivoRaggiunto, raccolti.append)

    _vinci(bus, adapter)
    assert len(raccolti) == 1
    notifica = raccolti[0]
    assert notifica.slug == "debutto-in-societa"
    assert notifica.titolo == "Debutto in società"
    assert notifica.ricompensa_testo == "Hai ricevuto una Box Armi di Bronzo."

    comp = obiettivi_correnti()
    assert comp is not None
    assert comp.sbloccati == ["debutto-in-societa"]
    assert comp.non_letti == ["debutto-in-societa"]
    [box] = comp.box
    assert (box.id, box.categoria, box.grado) == (
        "debutto-in-societa#0", "armi", "bronzo",
    )
    osservatore.chiudi()


def test_le_condizioni_leggono_solo_i_fatti_dell_evento(mondo_isolato: str) -> None:
    """La fuga non è una vittoria; e una condizione su un campo che l'evento
    non trasporta (`tier` su un esito di scontro) non è MAI vera."""
    bus, adapter, _enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=1, punti_vita=5)],
        seed=1, hp_prot=10_000, destrezza_prot=50,
    )
    monta_obiettivi((
        _asset("ritirata-d-autore", vittoria=None, fuga=True, box=None,
               beffa="Il coraggio è sopravvalutato. Anche tu."),
        _asset("turista-di-zona", vittoria=None, tier="citta", box=None,
               beffa="Non sei mai stato lì."),
    ))
    osservatore = attiva_osservatore(bus)
    raccolti: list[ObiettivoRaggiunto] = []
    bus.registra(ObiettivoRaggiunto, raccolti.append)

    _vinci(bus, adapter)  # vittoria: fuga=False, e `tier` non esiste sull'evento
    assert raccolti == []
    comp = obiettivi_correnti()
    assert comp.sbloccati == [] and comp.box == []
    osservatore.chiudi()


def test_il_non_ripetibile_scatta_una_volta_il_ripetibile_no(mondo_isolato: str) -> None:
    bus, adapter, _enc = avvia_scontro(
        nemici=[SpecNemico(destrezza=1, punti_vita=5)],
        seed=1, hp_prot=10_000, destrezza_prot=50,
    )
    monta_obiettivi((
        _asset("debutto-in-societa"),
        _asset("mestiere-delle-armi", ripetibile=True,
               box=None, beffa="Vincere è il tuo lavoro. Nessun premio per il lavoro."),
    ))
    osservatore = attiva_osservatore(bus)
    raccolti: list[ObiettivoRaggiunto] = []
    bus.registra(ObiettivoRaggiunto, raccolti.append)

    _vinci(bus, adapter)
    # Un secondo esito di vittoria (il fatto ripassa sul bus): il non-ripetibile
    # tace, il ripetibile suona di nuovo.
    bus.pubblica(CombatResolved(entita=0, vittoria=True))
    slugs = [n.slug for n in raccolti]
    assert slugs.count("debutto-in-societa") == 1
    assert slugs.count("mestiere-delle-armi") == 2
    comp = obiettivi_correnti()
    assert comp.sbloccati.count("mestiere-delle-armi") == 1, "il registro non duplica"
    assert len(comp.box) == 1, "solo il debutto ha una box"
    osservatore.chiudi()


# --- La sessione vera: wiring e persistenza -------------------------------------

async def _vinci_il_primo_scontro(sessione, max_turni: int = 60):
    """Driver: apri il primo scontro dal menu e vincilo (seed 3, HP pieni)."""
    snap = await sessione.prossima_narrazione()
    turni = 0
    while turni < max_turni:
        if snap.fase == "narrazione" and any(
            o.etichetta.startswith("Combatti") for o in snap.opzioni
        ):
            indice = next(
                o.indice for o in snap.opzioni if o.etichetta.startswith("Combatti")
            )
            sessione.coda.accoda(PlayerChoseOption(indice))
            snap = sessione.avanza()
        elif snap.fase == "combattimento":
            indice = next(
                o.indice for o in snap.opzioni if o.etichetta.startswith("Attacca")
            )
            sessione.coda.accoda(PlayerChoseOption(indice))
            snap = sessione.avanza()
        else:
            return snap  # scontro chiuso: si torna alla scena
        turni += 1
    raise AssertionError("il primo scontro non si è chiuso entro il budget")


def test_sessione_sblocca_e_il_reload_non_ripete(run_pulita, tmp_path) -> None:
    """Il filo intero: `costruisci_sessione(obiettivi=…)` monta il catalogo,
    l'osservatore di sessione sblocca sulla vittoria vera, e il componente
    (catalogo + sbloccati + box + non letti) attraversa il save — al reload
    niente doppio sblocco, le box restano."""
    from main import carica_sessione, costruisci_sessione

    sessione = costruisci_sessione(
        seed=3, directory=tmp_path, nome="Donut", obiettivi=(_asset(),)
    )
    asyncio.run(_vinci_il_primo_scontro(sessione))
    comp = obiettivi_correnti()
    assert comp is not None and comp.sbloccati == ["debutto-in-societa"]
    assert len(comp.box) == 1

    sessione.salva()
    uuid = sessione.uuid
    sessione.esci()

    riaperta = carica_sessione(uuid=uuid, directory=tmp_path)
    assert riaperta is not None
    ricomposto = obiettivi_correnti()
    assert ricomposto is not None
    assert ricomposto.sbloccati == ["debutto-in-societa"], "lo sblocco persiste"
    assert [b.id for b in ricomposto.box] == ["debutto-in-societa#0"]
    assert ricomposto.non_letti == ["debutto-in-societa"], (
        "le notifiche non lette attendono l'host (decisione §O-5)"
    )
    assert [o.slug for o in ricomposto.catalogo] == ["debutto-in-societa"], (
        "il catalogo congelato viaggia col save"
    )
    riaperta.esci()


# --- Fase O2: l'apertura delle box nei luoghi quieti ----------------------------

def _sessione_con_box(tmp_path):
    """Una run (seed 3) con una box ARMI/ARGENTO nel catalogo e una SAFE
    ROOM DESIGNATA dall'harness: qui si prova il GATE dell'apertura (solo
    rifugio, ratifica 2026-08-26), non lo spawn-rate dei rifugi — quello ha
    i suoi test (test_tipi_stanza). Ritorna (sessione, stanza_sicura)."""
    from contracts import TipoStanza
    from main import costruisci_sessione
    from motore.mappa import mappa_corrente

    sessione = costruisci_sessione(
        seed=3, directory=tmp_path, nome="Donut",
        obiettivi=(_asset(box=("armi", "argento")),),
    )
    mappa = mappa_corrente()[1]
    sicura = next(
        s for s in sorted(mappa.piano.adiacenze) if s != mappa.piano.partenza
    )
    mappa.piano.tipi[sicura] = TipoStanza.SAFE_ROOM
    return sessione, sicura


def test_la_box_si_apre_solo_in_quiete_e_conia_la_categoria(
    run_pulita, tmp_path
) -> None:
    """Il filo O2: vinci → box in coda; fuori dalla quiete l'opzione non si
    compone e la cintura del motore rifiuta; nel luogo quieto l'opzione è
    VERA, l'apertura conia un'ARMA (categoria vincolata), deposita in
    coniati+zaino, svuota la coda e l'opzione sparisce."""
    from motore.mappa import mappa_corrente, segna_visitata
    from motore.obiettivi import apri_prossima_box, obiettivi_correnti

    sessione, quieta = _sessione_con_box(tmp_path)
    asyncio.run(_vinci_il_primo_scontro(sessione))
    comp = obiettivi_correnti()
    assert len(comp.box) == 1

    # Fuori dalla safe room: la cintura strutturale rifiuta, la box resta.
    mappa = mappa_corrente()[1]
    if mappa.stanza_corrente != quieta:
        assert apri_prossima_box(sessione.bus) is None
        assert len(comp.box) == 1, "fuori dal rifugio la box resta chiusa"

    # Nemmeno nel BAGNO (ratifica 2026-08-26: quiete ≠ servizi): l'harness
    # trasforma una stanza ordinaria in bagno — niente opzione, cintura chiusa.
    from contracts import TipoStanza
    from motore.mappa import segna_visitata as _segna

    bagno = next(
        s for s in sorted(mappa.piano.adiacenze)
        if s not in (quieta, mappa.piano.partenza)
    )
    tipo_originale = mappa.piano.tipi.get(bagno)
    mappa.piano.tipi[bagno] = TipoStanza.BAGNO
    mappa.stanza_corrente = bagno
    _segna()
    snap_bagno = sessione.avanza()
    assert all(
        not o.etichetta.startswith("Apri box") for o in snap_bagno.opzioni
    ), "nel bagno la box resta chiusa: privacy, non servizi"
    assert apri_prossima_box(sessione.bus) is None
    assert len(comp.box) == 1
    if tipo_originale is None:
        del mappa.piano.tipi[bagno]
    else:
        mappa.piano.tipi[bagno] = tipo_originale

    # L'harness si porta nel luogo quieto (visitato): l'opzione è VERA.
    mappa.stanza_corrente = quieta
    segna_visitata()
    snap = sessione.avanza()
    etichette = [o.etichetta for o in snap.opzioni]
    assert "Apri box — Armi di Argento" in etichette, etichette

    from contracts import BoxAperta

    aperture: list[BoxAperta] = []
    sessione.bus.registra(BoxAperta, aperture.append)
    indice = next(
        o.indice for o in snap.opzioni if o.etichetta.startswith("Apri box")
    )
    sessione.coda.accoda(PlayerChoseOption(indice))
    snap = sessione.avanza()

    comp = obiettivi_correnti()
    assert comp.box == [], "la box è stata consumata"
    [evento] = aperture
    assert (evento.categoria, evento.grado) == ("armi", "argento")
    from motore import protagonista
    from motore.equip import fonti_zaino
    from motore.oggetti import assicura_coniati

    pent = protagonista()[0]
    # Il drop della vittoria può aver coniato anche lui: il pezzo della BOX
    # si riconosce dal fatto dell'evento, mai per posizione.
    coniato = next(
        v for v in assicura_coniati(pent).voci if v.slug == evento.fonte
    )
    assert coniato.nome == evento.nome
    assert coniato.tipo == "arma", "la categoria ARMI vincola il conio"
    assert coniato.grado == "argento"
    assert coniato.slug in fonti_zaino(pent), "il pezzo è nello zaino"
    assert all(
        not o.etichetta.startswith("Apri box") for o in snap.opzioni
    ), "a coda vuota l'opzione sparisce"
    sessione.esci()


def test_l_apertura_e_deterministica_per_replay(run_pulita, tmp_path) -> None:
    """Stessa run (stesso seed, stessa box id) → stesso oggetto, sempre: lo
    stream del conio è isolato per-box (`master_seed:box:{id}`), il replay
    non può divergere."""
    slug_a = test_la_box_si_apre_solo_in_quiete_e_conia_la_categoria(
        run_pulita, tmp_path / "a"
    )
    slug_b = test_la_box_si_apre_solo_in_quiete_e_conia_la_categoria(
        run_pulita, tmp_path / "b"
    )
    assert slug_a == slug_b, "il conio della box non è replay-safe"


# --- Fase O3: il catalogo autorale di sistema -----------------------------------

def test_il_catalogo_ufficiale_carica_e_regge_il_lint() -> None:
    """Il catalogo di sistema: almeno 15 voci, tutte valide dal contratto,
    slug unici e uguali al nome del file (il rename silenzioso non entra),
    ogni categoria-box dichiarata è del vocabolario chiuso."""
    from main import DIRECTORY_CONTENUTI, catalogo_obiettivi

    catalogo = catalogo_obiettivi()
    assert len(catalogo) >= 15, f"catalogo magro: {len(catalogo)} voci"
    slugs = [a.slug for a in catalogo]
    assert len(slugs) == len(set(slugs)), "slug duplicati nel catalogo"
    file_presenti = {
        p.stem for p in (DIRECTORY_CONTENUTI / "obiettivi").glob("*.json")
    }
    assert set(slugs) == file_presenti, "ogni file valido entra, slug == file"
    assert any(a.ripetibile for a in catalogo), "serve almeno un ripetibile"
    assert any(a.ricompensa.box is None for a in catalogo), "serve almeno una beffa"
    assert any(
        a.trigger.evento.value == "morte" for a in catalogo
    ), "il postumo fa parte dello show"


def test_il_catalogo_rispetta_il_golden_standard() -> None:
    """Le regole MECCANICHE dal dataset di riferimento (docs/Dataset/
    Achievement, taratura 2026-08-26 — 58 achievement del canone censiti per
    `tipo_trigger` e ricompensa):
    1. un RIPETIBILE su un fatto frequente vuole una SOGLIA — il canone non
       annuncia mai a raffica (2 ripetibili su 58, entrambi eventi rari); lo
       screenshot del bug: «Un altro scontro» PRIMA del «primo avversario»;
    2. il riposo che premia l'abitudine conta i riposi COMPLETI
       (interrotto=false) — il trigger errato suonava quando l'imboscata ti
       svegliava: il contrario dell'abitudine;
    3. canali separati (regola esplicita del canone: «il loot dei boss passa
       dalla Boss Box keyed al rango, mai dall'achievement»): la vittoria sul
       CUSTODE non paga una box — il custode paga già col drop garantito."""
    from main import catalogo_obiettivi

    catalogo = catalogo_obiettivi()
    assert catalogo, "catalogo di sistema vuoto"
    per_slug = {a.slug: a for a in catalogo}
    for a in catalogo:
        if a.ripetibile:
            assert a.trigger.soglia is not None, (
                f"{a.slug}: ripetibile senza soglia = annuncio a raffica "
                "(golden standard, regola 1)"
            )
    cliente = per_slug["cliente-abituale"]
    assert cliente.trigger.interrotto is False, (
        "l'abitudine conta i riposi completi (regola 2)"
    )
    taglia = per_slug["taglia-sul-custode"]
    assert taglia.ricompensa.box is None, (
        "canali separati: il custode paga col drop garantito (regola 3)"
    )


def test_il_loader_e_lasco_sul_rotto_e_duro_sul_drift(tmp_path) -> None:
    """Un file corrotto si salta (il catalogo non muore per una voce); un
    file VALIDO col nome sbagliato è drift d'authoring e non entra."""
    import json
    import shutil

    from main import DIRECTORY_CONTENUTI, catalogo_obiettivi

    base = tmp_path / "obiettivi"
    base.mkdir()
    sorgente = DIRECTORY_CONTENUTI / "obiettivi" / "debutto-in-societa.json"
    shutil.copy2(sorgente, base / "debutto-in-societa.json")
    (base / "rotto.json").write_text("{spazzatura", encoding="utf-8")
    driftato = json.loads(sorgente.read_text(encoding="utf-8"))
    driftato["slug"] = "altro-slug"
    (base / "nome-diverso.json").write_text(
        json.dumps(driftato, ensure_ascii=False), encoding="utf-8"
    )

    catalogo = catalogo_obiettivi(ufficiali=tmp_path)
    assert [a.slug for a in catalogo] == ["debutto-in-societa"]


def test_il_catalogo_di_sistema_e_il_default_della_sessione(
    run_pulita, tmp_path
) -> None:
    """`obiettivi=None` (default) monta il catalogo di sistema; `()` esplicito
    lascia la run pulita — harness e misure non pagano lo show."""
    from main import catalogo_obiettivi, costruisci_sessione

    sessione = costruisci_sessione(seed=3, directory=tmp_path / "a", nome="Donut")
    comp = obiettivi_correnti()
    assert comp is not None
    assert len(comp.catalogo) == len(catalogo_obiettivi())
    sessione.esci()

    pulita = costruisci_sessione(
        seed=3, directory=tmp_path / "b", nome="Donut", obiettivi=(),
    )
    assert obiettivi_correnti() is None, "() esplicito = nessun obiettivo"
    pulita.esci()


# --- Fase O4: le porte per gli host ---------------------------------------------

def test_l_elenco_e_velato_finche_chiuso(run_pulita, tmp_path) -> None:
    """`obiettivi_vista`: titolo sempre visibile, testo e ricompensa SOLO a
    sblocco avvenuto — lo spoiler è metà del premio."""
    from main import costruisci_sessione

    sessione = costruisci_sessione(
        seed=3, directory=tmp_path, nome="Donut",
        obiettivi=(_asset(), _asset("ritirata-d-autore", vittoria=None,
                                    fuga=True, box=None, beffa="Anche no.")),
    )
    prima = {v.slug: v for v in sessione.obiettivi_vista()}
    assert prima["debutto-in-societa"].sbloccato is False
    assert prima["debutto-in-societa"].testo == "", "velato finché chiuso"
    assert prima["debutto-in-societa"].ricompensa_testo == ""

    asyncio.run(_vinci_il_primo_scontro(sessione))
    dopo = {v.slug: v for v in sessione.obiettivi_vista()}
    assert dopo["debutto-in-societa"].sbloccato is True
    assert dopo["debutto-in-societa"].testo, "sbloccato = in chiaro"
    assert dopo["debutto-in-societa"].ricompensa_testo.startswith("Hai ricevuto")
    assert dopo["ritirata-d-autore"].sbloccato is False, "l'altro resta velato"
    assert sessione.box_in_coda() == 1
    sessione.esci()


def test_le_notifiche_arretrate_si_drenano_una_volta(run_pulita, tmp_path) -> None:
    """§O-5: uno sblocco salvato e mai drenato torna al load come notifica
    arretrata — UNA volta sola; il drenaggio pre-save svuota per sempre."""
    from main import carica_sessione, costruisci_sessione

    sessione = costruisci_sessione(
        seed=3, directory=tmp_path, nome="Donut", obiettivi=(_asset(),),
    )
    asyncio.run(_vinci_il_primo_scontro(sessione))
    sessione.salva()  # NON drenata: l'host è "crashato" prima di mostrare
    uuid = sessione.uuid
    sessione.esci()

    riaperta = carica_sessione(uuid=uuid, directory=tmp_path)
    arretrate = riaperta.drena_notifiche_obiettivi()
    assert [n.slug for n in arretrate] == ["debutto-in-societa"]
    assert arretrate[0].ricompensa_testo, "la notifica torna GIÀ composta"
    assert riaperta.drena_notifiche_obiettivi() == (), "una volta sola"

    riaperta.salva()
    uuid2 = riaperta.uuid
    riaperta.esci()
    di_nuovo = carica_sessione(uuid=uuid2, directory=tmp_path)
    assert di_nuovo.drena_notifiche_obiettivi() == (), (
        "il drenaggio persiste col save: mai due volte la stessa notifica"
    )
    di_nuovo.esci()


def test_il_tasto_o_elenca_gli_obiettivi() -> None:
    pytest.importorskip("textual")
    import gioco_textual
    from textual.widgets import RichLog

    from main import costruisci_sessione

    async def run() -> None:
        app = gioco_textual._costruisci_app(
            costruisci_sessione(seed=1, obiettivi=(_asset(),))
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            rl = app.query_one("#log", RichLog)
            prima = len(rl.lines)
            await pilot.press("o")
            await pilot.pause()
            assert len(rl.lines) > prima, "O scrive l'elenco nel log"

    asyncio.run(run())


# --- Titoli mid-run (ratifica 2026-08-26): i fatti da impresa -------------------

def _mondo_con_catalogo(assets):
    """Osservatore su bus fresco + catalogo montato: i fatti si pubblicano a
    mano (l'arricchimento del motore è provato dal sito di pubblicazione;
    qui si prova la VALUTAZIONE)."""
    from contracts import BusEventi
    from motore.scheda import crea_protagonista

    bus = BusEventi()
    crea_protagonista(destrezza=10, punti_vita=30)
    monta_obiettivi(assets)
    osservatore = attiva_osservatore(bus)
    raccolti: list[ObiettivoRaggiunto] = []
    bus.registra(ObiettivoRaggiunto, raccolti.append)
    return bus, osservatore, raccolti


def test_i_fatti_da_impresa(mondo_isolato: str) -> None:
    """Custode, senza-graffi e rango minimo: scattano SOLO sul fatto vero —
    la vittoria ordinaria non è un'impresa."""
    bus, osservatore, raccolti = _mondo_con_catalogo((
        _asset("taglia", custode=True, box=None, beffa="Il varco ricorda."),
        _asset("pelle-intatta", senza_graffi=True, box=None, beffa="Noia."),
        _asset("rango", grado_nemico_minimo=Grado.ORO, box=None, beffa="Oh."),
    ))
    # Vittoria ordinaria: nessuna impresa.
    bus.pubblica(CombatResolved(entita=0, vittoria=True))
    assert raccolti == []
    # Vittoria d'impresa: custode + senza graffi + leggendario (≥ oro).
    bus.pubblica(CombatResolved(
        entita=0, vittoria=True, custode=True, senza_graffi=True,
        grado_nemico="leggendario",
    ))
    assert sorted(n.slug for n in raccolti) == ["pelle-intatta", "rango", "taglia"]
    # L'argento NON è ≥ oro; e il grado assente ("" = scalari) non è mai rango.
    raccolti.clear()
    bus.pubblica(CombatResolved(
        entita=0, vittoria=True, grado_nemico="argento",
    ))
    assert raccolti == []
    osservatore.chiudi()


def test_la_serie_conta_azzera_e_persiste(mondo_isolato: str) -> None:
    """Il titolo a SOGLIA: vale alla N-esima occorrenza, il contatore si
    azzera allo sblocco (il ripetibile suona a ogni multiplo)."""
    bus, osservatore, raccolti = _mondo_con_catalogo((
        _asset("terzetto", soglia=3, box=None, beffa="Tre. Contiamo insieme."),
        _asset("bis-continuo", soglia=2, ripetibile=True, box=None,
               beffa="Di nuovo. E ancora."),
    ))
    for _ in range(4):
        bus.pubblica(CombatResolved(entita=0, vittoria=True))
    slugs = [n.slug for n in raccolti]
    assert slugs.count("terzetto") == 1, "la soglia 3 suona alla terza, una volta"
    assert slugs.count("bis-continuo") == 2, "il ripetibile a soglia 2 suona a 2 e 4"
    comp = obiettivi_correnti()
    assert comp.conteggi["terzetto"] == 0, "azzerato allo sblocco"
    assert comp.conteggi["bis-continuo"] == 0
    # Un quinto fatto: il terzetto (non ripetibile) resta muto anche a
    # contatore ripartito — la guardia degli sbloccati vince.
    bus.pubblica(CombatResolved(entita=0, vittoria=True))
    assert [n.slug for n in raccolti].count("terzetto") == 1
    osservatore.chiudi()


def test_il_catalogo_ha_i_titoli_da_impresa() -> None:
    """Il catalogo di sistema copre i fatti nuovi: custode, rango, senza
    graffi e almeno una serie a soglia."""
    from main import catalogo_obiettivi

    catalogo = {a.slug: a for a in catalogo_obiettivi()}
    assert catalogo["taglia-sul-custode"].trigger.custode is True
    assert catalogo["fuori-categoria"].trigger.grado_nemico_minimo is Grado.ORO
    assert catalogo["senza-un-graffio"].trigger.senza_graffi is True
    assert catalogo["lavoro-in-serie"].trigger.soglia == 10
