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
            evento=evento, vittoria=vittoria, fuga=fuga, tier=tier
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

def _stanza_quieta_del_piano():
    """La prima stanza QUIETA della zona corrente (None se non ce n'è)."""
    from contracts import TipoStanza
    from motore.mappa import mappa_corrente, tipo_di

    mappa = mappa_corrente()[1]
    for stanza in sorted(mappa.piano.adiacenze):
        if tipo_di(mappa.piano, stanza) in (
            TipoStanza.SAFE_ROOM, TipoStanza.BAGNO,
        ):
            return stanza
    return None


def _sessione_con_box(tmp_path, seed_candidati=(3, 1, 5, 8)):
    """Una run con una box ARMI/ARGENTO guadagnata e una stanza quieta nel
    piano: il seed si sceglie deterministicamente fra i candidati (il primo
    la cui zona ha un luogo quieto)."""
    from main import costruisci_sessione

    for seed in seed_candidati:
        sessione = costruisci_sessione(
            seed=seed, directory=tmp_path / f"s{seed}", nome="Donut",
            obiettivi=(_asset(box=("armi", "argento")),),
        )
        if _stanza_quieta_del_piano() is not None:
            return sessione
        sessione.esci()
    raise AssertionError("nessun seed candidato ha una stanza quieta in zona")


def test_la_box_si_apre_solo_in_quiete_e_conia_la_categoria(
    run_pulita, tmp_path
) -> None:
    """Il filo O2: vinci → box in coda; fuori dalla quiete l'opzione non si
    compone e la cintura del motore rifiuta; nel luogo quieto l'opzione è
    VERA, l'apertura conia un'ARMA (categoria vincolata), deposita in
    coniati+zaino, svuota la coda e l'opzione sparisce."""
    from motore.mappa import mappa_corrente, segna_visitata
    from motore.obiettivi import apri_prossima_box, obiettivi_correnti

    sessione = _sessione_con_box(tmp_path)
    asyncio.run(_vinci_il_primo_scontro(sessione))
    comp = obiettivi_correnti()
    assert len(comp.box) == 1

    # Fuori dalla quiete: la cintura strutturale rifiuta, la box resta.
    quieta = _stanza_quieta_del_piano()
    mappa = mappa_corrente()[1]
    if mappa.stanza_corrente != quieta:
        assert apri_prossima_box(sessione.bus) is None
        assert len(comp.box) == 1, "fuori dal sicuro la box resta chiusa"

    # L'harness si porta nel luogo quieto (visitato): l'opzione è VERA.
    mappa.stanza_corrente = quieta
    segna_visitata()
    snap = sessione.avanza()
    etichette = [o.etichetta for o in snap.opzioni]
    assert "Apri box — Armi di Argento" in etichette, etichette

    indice = next(
        o.indice for o in snap.opzioni if o.etichetta.startswith("Apri box")
    )
    sessione.coda.accoda(PlayerChoseOption(indice))
    snap = sessione.avanza()

    comp = obiettivi_correnti()
    assert comp.box == [], "la box è stata consumata"
    from motore import protagonista
    from motore.equip import fonti_zaino
    from motore.oggetti import assicura_coniati

    pent = protagonista()[0]
    [coniato] = assicura_coniati(pent).voci
    assert coniato.tipo == "arma", "la categoria ARMI vincola il conio"
    assert coniato.grado == "argento"
    assert coniato.slug in fonti_zaino(pent), "il pezzo è nello zaino"
    assert all(
        not o.etichetta.startswith("Apri box") for o in snap.opzioni
    ), "a coda vuota l'opzione sparisce"
    sessione.esci()
    return coniato.slug


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
