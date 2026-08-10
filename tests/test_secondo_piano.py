"""Il multi-piano: scendere non è vincere, e sotto c'è davvero qualcosa (G §8, G-L2).

Finché la stagione aveva **un piano solo**, tre pezzi di codice davano per scontato che
la prima discesa fosse la fine della run, e nessun test poteva accorgersene perché il
ramo "si continua" era irraggiungibile:

  1. il **terminale** scattava a ogni `DiscesaPiano`, incondizionatamente;
  2. la **mappa** si generava una volta sola, all'ingresso della run;
  3. il **copione offline** si costruiva dal solo piano 1 → sceso, la coda del
     FakeProvider era esaurita e il piano 2 si raccontava col testo neutro di fallback.

Questi test tengono i tre pezzi insieme. Il tetto ai numeri autorati sta qui perché è
lo stesso momento: il secondo piano è quando qualcuno comincia a scrivere asset nuovi.
"""

from __future__ import annotations

import asyncio

import pytest

from contracts import DiscesaPiano, PlayerDiscende, Terminale
from main import costruisci_sessione, risolvi_stagione
from motore import livello_corrente, mappa_corrente
from tests.contenuti_sintetici import stagione_sintetica


def _scendi(sessione):
    """Porta il giocatore sulla scala e la attiva (la discesa vuole il primitivo
    strutturale, non la parola "scala" nella prosa — G §8.3)."""
    _ent, mappa = mappa_corrente()
    mappa.stanza_corrente = next(iter(mappa.piano.discese))
    sessione.coda.accoda(PlayerDiscende())
    return sessione.avanza()


# --- 1. La stagione pubblicata risolve (sanity content-agnostic) ---------------
# I MECCANISMI multi-piano si provano qui sotto su stagioni SINTETICHE: il
# numero di piani della stagione pubblicata è contenuto dell'utente, non un
# vincolo del motore (perimetro: forma, non contenuto — 2026-08-10).

def test_la_stagione_ufficiale_risolve_ed_e_giocabile() -> None:
    stagione = risolvi_stagione("stagione-1")
    assert stagione.piani, "una stagione senza piani non è giocabile"
    slugs = [p.slug for p in stagione.piani]
    assert len(set(slugs)) == len(slugs), "due piani con lo stesso slug"
    for piano in stagione.piani:
        assert piano.cast, f"{piano.slug}: un piano senza cast non è giocabile"


# --- 2. Scendere dal primo piano NON conclude la run --------------------------

def test_scendere_dal_primo_piano_continua_la_run(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(
        nome="Giu", seed=3, directory=tmp_path, stagione=stagione_sintetica(2)
    )
    discese: list[DiscesaPiano] = []
    sessione.bus.registra(DiscesaPiano, discese.append)
    try:
        asyncio.run(sessione.prossima_narrazione())
        snap = _scendi(sessione)

        assert discese and discese[-1].piano == 2
        assert livello_corrente() == 2
        assert snap.terminale is None, (
            "la run si è chiusa alla prima discesa: il secondo piano è irraggiungibile"
        )
        assert sessione.guscio.stato.name == "IN_RUN"
    finally:
        sessione.bus.deregistra(DiscesaPiano, discese.append)


def test_scendere_dallultimo_piano_conclude_la_run(run_pulita, tmp_path) -> None:
    stagione = stagione_sintetica(2)
    sessione = costruisci_sessione(
        nome="Vinc", seed=3, directory=tmp_path, stagione=stagione
    )
    asyncio.run(sessione.prossima_narrazione())

    snap = None
    for _ in range(len(stagione.piani)):
        snap = _scendi(sessione)
    assert snap is not None and snap.terminale is Terminale.PIANO_COMPLETATO, (
        "uscire dall'ultimo piano È la vittoria della run (G §6.7)"
    )
    assert snap.run_conclusa is True


# --- 3. Il piano nuovo è una mappa nuova --------------------------------------

def test_la_discesa_rigenera_la_mappa(run_pulita, tmp_path) -> None:
    stagione = stagione_sintetica(2, n_stanze=4)
    sessione = costruisci_sessione(
        nome="Mappa", seed=3, directory=tmp_path, stagione=stagione
    )
    asyncio.run(sessione.prossima_narrazione())

    _e1, prima = mappa_corrente()
    visitate_prima = set(prima.visitate)
    assert visitate_prima, "la prima stanza dev'essere già visitata a questo punto"

    _scendi(sessione)
    _e2, dopo = mappa_corrente()

    assert not dopo.visitate, "il piano 2 non può nascere già esplorato"
    assert dopo.stanza_corrente == dopo.piano.partenza
    assert len(dopo.piano.adiacenze) == stagione.piani[1].n_stanze, (
        "la scala del piano nuovo viene dal SUO cast, non da quella del piano 1"
    )


def test_la_mappa_del_piano_due_e_seeded_non_casuale(run_pulita, tmp_path) -> None:
    """Due run con lo stesso seme producono lo stesso piano 2: è la condizione del
    replay (FNC §9). Se qui comparisse un `random.Random()` senza seme, o l'orologio,
    questo test lo scoprirebbe."""
    def _adiacenze_dopo_la_discesa(directory):
        sessione = costruisci_sessione(
            nome="Seed", seed=11, directory=directory, stagione=stagione_sintetica(2)
        )
        asyncio.run(sessione.prossima_narrazione())
        _scendi(sessione)
        _ent, mappa = mappa_corrente()
        return {k: sorted(v) for k, v in mappa.piano.adiacenze.items()}

    prima = _adiacenze_dopo_la_discesa(tmp_path / "a")
    seconda = _adiacenze_dopo_la_discesa(tmp_path / "b")
    assert prima == seconda


# --- 4. Sotto c'è contenuto, non il testo di ripiego ---------------------------

def test_il_copione_offline_copre_anche_il_secondo_piano(run_pulita, tmp_path) -> None:
    """Il piano 2 deve raccontarsi col SUO cast.

    Prima il copione si costruiva dal solo piano 1: sceso, la coda FIFO del
    FakeProvider era esaurita e ogni stanza degradava alla prosa neutra. Giocabile, ma
    vuoto — il tipo di buco che non fa fallire nessun test e si nota solo giocando."""
    from main import _fake_da_piani, turni_da_piano

    stagione = stagione_sintetica(2)
    nomi_piano2 = {t.entita.nome for t in turni_da_piano(stagione.piani[1])}
    assert nomi_piano2, "il secondo piano non ha turni scriptati"

    # Il copione completo mappa OGNI piano alla sua profondità (keyed, non FIFO):
    # nessuna chiamata può "consumare" il contenuto di un'altra stanza.
    copione = _fake_da_piani(stagione.piani)
    for profondita, piano in enumerate(stagione.piani, start=1):
        assert len(copione._turni_per_livello[profondita]) == len(turni_da_piano(piano))

    sessione = costruisci_sessione(
        nome="Sotto", seed=3, directory=tmp_path, stagione=stagione
    )
    asyncio.run(sessione.prossima_narrazione())
    _scendi(sessione)
    snap = asyncio.run(sessione.prossima_narrazione())
    assert snap.prosa, "il piano 2 non ha prodotto prosa"


def test_scendere_alla_prima_scala_non_ruba_il_copione_del_piano_2(
    run_pulita, tmp_path
) -> None:
    """Regression (giro 2026-08-07): con la coda FIFO, scendere PRIMA di aver
    visitato tutte le stanze lasciava in coda le voci residue del piano 1 — i
    reveal del piano 2 le consumavano, il gate le respingeva (mob fuori cast) e
    il piano 2 si congelava in prosa neutra. Col copione keyed la profondità
    corrente pesca il SUO cast, a qualunque punto della visita."""
    from main import turni_da_piano
    from motore.narrazione import PROSA_NEUTRA

    stagione = stagione_sintetica(2)
    sessione = costruisci_sessione(
        nome="Presto", seed=3, directory=tmp_path, stagione=stagione
    )
    asyncio.run(sessione.prossima_narrazione())    # UNA sola stanza del piano 1
    _scendi(sessione)                              # discesa anticipata
    snap = asyncio.run(sessione.prossima_narrazione())
    assert snap.prosa != PROSA_NEUTRA, "il piano 2 è degradato al testo neutro"
    _ent, mappa = mappa_corrente()
    attesa = turni_da_piano(stagione.piani[1])[mappa.stanza_corrente].prosa
    assert snap.prosa == attesa, "il piano 2 non sta usando il SUO copione"


def test_offline_e_live_condividono_la_scala_del_piano(run_pulita, tmp_path) -> None:
    """Regression (giro 2026-08-07): offline il piano 1 aveva len(cast) stanze,
    live ripiegava su MAPPA_STANZE — lo stesso contenuto produceva geometrie
    diverse (mob senza stanza in live, misure non trasferibili)."""
    from provider import FakeProvider

    stagione = stagione_sintetica(2)
    sessione = costruisci_sessione(
        nome="Live", seed=3, directory=tmp_path, provider=FakeProvider(),
        stagione=stagione,
    )
    _ent, mappa = mappa_corrente()
    assert len(mappa.piano.adiacenze) == stagione.piani[0].n_stanze, (
        "la scala live deve venire dal CAST, come offline (una stanza per mob)"
    )
    assert sessione is not None


def test_lazione_libera_non_shifta_il_copione(run_pulita, tmp_path) -> None:
    """Regression (giro 2026-08-07): con la FIFO un'azione libera consumava le 4
    voci della stanza successiva — risposta non-sequitur ORA (la prosa di
    un'altra stanza) e ogni reveal successivo shiftato. Col copione keyed
    l'azione riceve la voce della stanza in cui avviene, e la stanza dopo
    riceve la propria."""
    from main import turni_da_piano
    from motore.narrazione import PROSA_NEUTRA

    stagione = stagione_sintetica(2)
    attesi = [t.prosa for t in turni_da_piano(stagione.piani[0])]
    sessione = costruisci_sessione(
        nome="Agisce", seed=3, directory=tmp_path, stagione=stagione
    )
    snap0 = asyncio.run(sessione.prossima_narrazione())
    assert snap0.prosa == attesi[0]

    riepilogo = sessione.riepiloga_azione("osservo con calma le pareti")
    snap_azione = asyncio.run(sessione.esegui_azione(riepilogo))
    assert snap_azione.prosa != attesi[1], (
        "la risposta all'azione è la prosa della stanza SUCCESSIVA: copione shiftato"
    )
    assert snap_azione.prosa != PROSA_NEUTRA

    _ent, mappa = mappa_corrente()
    mappa.stanza_corrente = 1                      # harness: si sposta senza menu
    snap1 = asyncio.run(sessione.prossima_narrazione())
    assert snap1.prosa == attesi[1], (
        "dopo un'azione libera la stanza successiva deve ricevere la SUA voce"
    )


# --- 5. Il tetto ai numeri autorati -------------------------------------------

def test_un_asset_fuori_banda_e_un_errore_di_authoring() -> None:
    """`pv_base=99999` non deve produrre un mob con 99.999 HP.

    Era l'ultimo punto scoperto dell'invariante «i numeri li deriva il motore»: difeso
    sulla porta in-run (l'AI sceglie nomi), aperto su quella di authoring."""
    from contracts import ProfiloArchetipoDati
    from motore import lint_profilo

    errori = lint_profilo("mostro-gonfio", ProfiloArchetipoDati(pv_base=99999))
    assert errori and "fuori banda" in errori[0]


def test_il_tetto_e_derivato_dal_catalogo_non_cablato() -> None:
    """Alzare deliberatamente la scala del gioco (calibrazione) deve allargare la banda
    da sé: un tetto scritto a mano diventerebbe un ostacolo al bilanciamento invece che
    una guardia contro i refusi."""
    from contracts import ProfiloArchetipoDati
    from motore import lint_profilo
    from motore.calibrazione import REGISTRY_ARCHETIPI, TETTO_AUTHORING

    massimo_storico = max(p.pv_base for p in REGISTRY_ARCHETIPI.values())
    al_limite = int(massimo_storico * TETTO_AUTHORING)
    assert not lint_profilo("giusto", ProfiloArchetipoDati(pv_base=al_limite))
    assert lint_profilo("troppo", ProfiloArchetipoDati(pv_base=al_limite + 1))


def test_i_profili_pubblicati_stanno_tutti_in_banda() -> None:
    """Il contenuto del repo passa il proprio lint: se un asset ufficiale fosse fuori
    banda, il tetto sarebbe tarato male (o l'asset sbagliato) — meglio saperlo qui."""
    from motore import lint_profilo

    stagione = risolvi_stagione("stagione-1")
    for archetipo in stagione.archetipi:
        assert not lint_profilo(archetipo.slug, archetipo.profilo), archetipo.slug


@pytest.mark.parametrize("campo", ["pv_base", "danno_base", "destrezza_base"])
def test_il_tetto_copre_ogni_stat_non_solo_gli_hp(campo: str) -> None:
    from contracts import ProfiloArchetipoDati
    from motore import lint_profilo

    assert lint_profilo("gonfio", ProfiloArchetipoDati(**{campo: 99999}))


# --- 6. La difficoltà è legata alla profondità (F9) ---------------------------

def test_i_gradi_ammessi_salgono_scendendo() -> None:
    """Prima il budget senza-piano offriva `{bronzo, argento}` a QUALUNQUE profondità:
    un piano 10 era facile quanto il primo, e il `livello` che la formula-madre riceveva
    non aveva corrispettivo nel contenuto ammesso."""
    from contracts import Grado
    from motore import gradi_per_profondita
    from motore.catalogo import RANGO_GRADO

    minimi = [min(RANGO_GRADO[g] for g in gradi_per_profondita(l)) for l in range(1, 7)]
    assert minimi == sorted(minimi), f"la finestra non sale scendendo: {minimi}"
    assert Grado.BRONZO in gradi_per_profondita(1)
    assert Grado.BRONZO not in gradi_per_profondita(4), (
        "a profondità 4 gli slime di bronzo non sono più una minaccia credibile"
    )


def test_la_finestra_non_sfonda_la_scala_dei_gradi() -> None:
    """A profondità assurde la finestra si ferma sul grado massimo invece di svuotarsi:
    un piano molto profondo dev'essere difficile, non VUOTO (nessun grado ammesso
    significherebbe nessun nemico generabile)."""
    from contracts import Grado
    from motore import gradi_per_profondita

    for livello in (10, 100, 1000):
        finestra = gradi_per_profondita(livello)
        assert finestra, f"profondità {livello}: nessun grado ammesso"
        assert finestra <= set(Grado)


def test_hp_e_danno_hanno_curve_separate() -> None:
    """La causa strutturale che rendeva impossibile il TTK oltre l'argento: un `fattore`
    unico faceva salire HP e danno insieme, quindi ogni grado in più rendeva lo scontro
    *più lungo* E *più letale* — e nessun equipaggiamento poteva compensare due curve
    appaiate."""
    from contracts import Grado, StatId
    from motore.calibrazione import K_RANGO_DANNO, K_RANGO_HP, primarie_da_archetipo

    assert K_RANGO_HP > K_RANGO_DANNO, (
        "gli HP devono crescere più del danno: i nemici di grado alto sono più DURI, "
        "non più LETALI"
    )
    bronzo = primarie_da_archetipo("scheletro", Grado.BRONZO, 1)
    celeste = primarie_da_archetipo("scheletro", Grado.CELESTIALE, 1)
    crescita_hp = celeste[StatId.COSTITUZIONE] / bronzo[StatId.COSTITUZIONE]
    crescita_danno = celeste[StatId.FORZA] / bronzo[StatId.FORZA]
    assert crescita_hp > crescita_danno, (
        f"HP ×{crescita_hp:.1f} contro danno ×{crescita_danno:.1f}: le curve sono "
        "tornate appaiate"
    )
