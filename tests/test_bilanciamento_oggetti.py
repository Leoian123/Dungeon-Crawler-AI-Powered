"""Nodo B — il bilanciamento oggetti dal dataset di riferimento
(docs/bilanciamento-oggetti.md): B1 la review-armi (il layer impugnato è
sveglio: l'arma indossata entra in `atk_eff`), B2 la qualità del conio
(scarto/onesto/pregiato — il ventaglio DENTRO il grado, coi suoi effetti su
affissi e danno d'arma). I numeri restano §11; i contenuti dei test sono
sintetici e originali.
"""

from __future__ import annotations

import random
from collections import Counter

from contracts import Grado, StatId, Taglia
from motore import (
    calibrazione as cal,
    conia_procedurale,
    crea_protagonista,
    crea_stagione,
    oggetto_da_asset,
    protagonista,
)
from motore.derivate import atk_eff, danno_arma_impugnata
from motore.equip import Arma, equipaggia, togli
from motore.statistiche import stat_eff


def _arma_fabbrica():
    from main import _stagione_a_attiva, risolvi_stagione
    from motore import fabbrica_attiva
    from tests.persist_helpers import costruisci_run

    costruisci_run()
    crea_stagione(_stagione_a_attiva(risolvi_stagione("stagione-1")))
    assert fabbrica_attiva() is not None


# --- B1: la review-armi — il layer impugnato è sveglio --------------------------

def test_l_arma_impugnata_entra_in_atk_eff(mondo_isolato) -> None:
    """Armato colpisce più forte di ESATTAMENTE il danno dell'arma; sfilata,
    l'offesa torna quella nuda. Le entità senza manifest non si muovono."""
    import esper

    crea_protagonista(destrezza=5, punti_vita=30, id_dominio="prova")
    pent = protagonista()[0]
    nudo = atk_eff(pent)
    assert nudo == stat_eff(pent, StatId.FORZA)

    lama = Arma(fonte="lama-di-prova", taglia=Taglia.MEDIA,
                nome="Lama di prova", danno_base=5)
    assert equipaggia(pent, lama)
    assert danno_arma_impugnata(pent) == 5
    assert atk_eff(pent) == nudo + 5, "il layer impugnato è sveglio"
    togli(pent, "lama-di-prova")
    assert atk_eff(pent) == nudo, "sfilata l'arma, l'offesa torna nuda"

    # Un'entità qualunque senza equip: zero contributo, zero crash.
    ent = esper.create_entity()
    assert danno_arma_impugnata(ent) == 0


def test_la_curva_danno_arma_e_convessa_e_monotona() -> None:
    """La curva §11 insegue K_RANGO_HP: mai decrescente, e il salto complessivo
    bronzo→celestiale è almeno ×3 (l'offesa da equip scala con i pool)."""
    from motore.catalogo import RANGO_GRADO

    ordinati = [g.value for g in sorted(RANGO_GRADO, key=RANGO_GRADO.__getitem__)]
    valori = [cal.DANNO_ARMA_PER_GRADO[g] for g in ordinati]
    assert all(b >= a for a, b in zip(valori, valori[1:])), valori
    assert valori[-1] >= valori[0] * 3, valori


# --- B2: la qualità del conio ---------------------------------------------------

def test_scarto_e_pregiato_muovono_gli_affissi(mondo_isolato) -> None:
    """SCARTO = zero affissi anche dove il grado li darebbe (oro); PREGIATO =
    un affisso in più del dovuto. Il nome dello scarto perde l'affisso."""
    from motore.fabbrica import _VOCI_FATTURA

    _arma_fabbrica()
    scarto = conia_procedurale(random.Random(3), "oro", qualita="scarto")
    assert scarto.qualita == "scarto"
    assert scarto.resistenze == (), "lo scarto non porta l'elemento"
    assert any(scarto.descrizione.startswith(v) for v in _VOCI_FATTURA["scarto"]), (
        "la voce di scarto apre la descrizione (dal pool autorale)"
    )

    onesto = conia_procedurale(random.Random(3), "bronzo", qualita="onesto")
    pregiato = conia_procedurale(random.Random(3), "bronzo", qualita="pregiato")
    # Stesso stream: il pregiato di bronzo ha UN affisso dove l'onesto zero
    # (la sovrapposizione col grado sopra, per costruzione).
    assert len(pregiato.modificatori) >= len(onesto.modificatori)
    assert any(
        pregiato.descrizione.startswith(v) for v in _VOCI_FATTURA["pregiato"]
    )


def test_la_qualita_sposta_il_danno_dell_arma(mondo_isolato) -> None:
    """La lama pregiata d'argento colpisce come un'oro onesta; lo scarto
    scende di un grado; ai capi la scala si ferma (floor bronzo, cap cel.)."""
    from motore.design import OggettoAttivo

    def arma(grado: str, qualita: str):
        return oggetto_da_asset(OggettoAttivo(
            slug=f"l-{grado}-{qualita}", nome="Lama", tipo="arma",
            grado=grado, qualita=qualita,
        ))

    per_grado = cal.DANNO_ARMA_PER_GRADO
    assert arma("argento", "pregiato").danno_base == per_grado["oro"]
    assert arma("argento", "scarto").danno_base == per_grado["bronzo"]
    assert arma("bronzo", "scarto").danno_base == per_grado["bronzo"]
    assert arma("celestiale", "pregiato").danno_base == per_grado["celestiale"]
    assert arma("oro", "onesto").danno_base == per_grado["oro"]


def test_il_ventaglio_e_seeded_e_segue_i_pesi(mondo_isolato) -> None:
    """La pescata di qualità è deterministica (stesso stream → stessa qualità)
    e la distribuzione segue i pesi §11: al PLATINO lo scarto pesa zero e non
    esce mai; all'ORO il pregiato domina lo scarto; al BRONZO lo scarto esiste."""
    _arma_fabbrica()
    a = conia_procedurale(random.Random(11), "oro")
    b = conia_procedurale(random.Random(11), "oro")
    assert a == b and a.qualita == b.qualita, "replay: stessa qualità, sempre"

    conta = {g: Counter() for g in ("bronzo", "oro", "platino")}
    for g in conta:
        for i in range(200):
            conta[g][conia_procedurale(random.Random(i), g).qualita] += 1
    assert conta["platino"]["scarto"] == 0, "peso zero = mai (il §11 comanda)"
    assert conta["oro"]["pregiato"] > conta["oro"]["scarto"]
    assert conta["bronzo"]["scarto"] > 0, "il junk di consolazione esiste"


def test_il_conio_storico_resta_byte_identico_a_monte_della_qualita(
    mondo_isolato,
) -> None:
    """La qualità si pesca IN CODA allo stream: base, famiglia, affissi e
    SUFFISSO di un conio onesto sono quelli di sempre (slug identico allo
    storico pre-B2 a parità di stream)."""
    _arma_fabbrica()
    con_ventaglio = conia_procedurale(random.Random(42), "oro")
    dichiarato = conia_procedurale(random.Random(42), "oro", qualita="onesto")
    # Lo stesso stream produce lo stesso pezzo A MONTE della qualità: slug e
    # nome coincidono quando la pescata dà "onesto" o viene dichiarata tale.
    assert con_ventaglio.slug[-4:] == dichiarato.slug[-4:], (
        "il suffisso non deve spostarsi: la qualità è in coda allo stream"
    )


'''--- B4: le ratifiche del giro (scaling box per territorio, dato agli host) ---'''


def test_la_box_scala_col_territorio(mondo_isolato) -> None:
    """Ratifica §B-1: stessa box, territorio profondo = conio migliore. Il
    grado del conio non scende sotto il minimo della finestra-loot corrente
    (la stessa dei drop); una box già alta resta sua; senza territorio il
    grado stampato è legge."""
    from contracts import BusEventi
    from main import _stagione_a_attiva
    from motore import (
        attraversa,
        avvia_territorio,
        crea_entita_fase,
        crea_profondita,
        crea_seme,
        crea_tempo_piano,
        finestra_gradi_loot,
        mappa_corrente,
        registra_boss_sconfitto,
        segna_visitata,
        stanza_passaggio_di,
        zona_corrente,
    )
    from motore.catalogo import RANGO_GRADO
    from motore.obiettivi import _grado_conio_scalato
    from tests.contenuti_sintetici import piano_territoriale, stagione_sintetica

    # Harness nudo, senza territorio: nessuno scaling, nessun crash.
    assert _grado_conio_scalato("bronzo") == "bronzo"

    crea_profondita()
    crea_seme(5)
    crea_tempo_piano()
    crea_stagione(_stagione_a_attiva(stagione_sintetica(
        piani=[piano_territoriale(1)], slug="s-boxscala",
    )))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    crea_entita_fase()
    avvia_territorio(1)
    bus = BusEventi()

    # Quartiere (il tier minimo): il bronzo resta bronzo.
    assert _grado_conio_scalato("bronzo") == "bronzo"

    # Distretto: il minimo della finestra sale — e la box di bronzo con lui.
    registra_boss_sconfitto()
    _e, mappa = mappa_corrente()
    mappa.stanza_corrente = stanza_passaggio_di(zona_corrente(), mappa.piano)
    segna_visitata()
    assert attraversa(bus) is True
    minimo = min(finestra_gradi_loot(1), key=RANGO_GRADO.__getitem__)
    assert RANGO_GRADO[minimo] > RANGO_GRADO[Grado.BRONZO], (
        "il distretto deve alzare la finestra: senza, il test non prova nulla"
    )
    assert _grado_conio_scalato("bronzo") == minimo.value
    # Una box già sopra la finestra resta sua: lo scaling è un floor, non un cap.
    assert _grado_conio_scalato("celestiale") == "celestiale"


def test_gli_eventi_loot_portano_grado_e_fattura() -> None:
    """Ratifica §B-4 (metà backend): il dato vive nel backend, gli host lo
    vestono — `OggettoTrovato`/`BoxAperta` trasportano grado e qualità, coi
    default retro-compatibili ("" = non detto, gli eventi vecchi validano)."""
    from contracts import BoxAperta, OggettoTrovato
    from main import _nota_fattura

    vecchio = OggettoTrovato(nome="Lama", fonte="lama-x")
    assert vecchio.grado == "" and vecchio.qualita == ""
    nuovo = BoxAperta(categoria="armi", grado="argento",
                      nome="Lama", fonte="lama-y", qualita="pregiato")
    assert _nota_fattura(nuovo) == " — fattura pregiata"
    assert _nota_fattura(vecchio) == "", "il non-detto tace in cronaca"
    scarto = OggettoTrovato(nome="Chiodo", fonte="chiodo-z", qualita="scarto")
    assert _nota_fattura(scarto) == " — fattura di scarto"


def test_le_descrizioni_si_compongono_senza_timbro_fisso(mondo_isolato) -> None:
    """§B-4: la voce di fattura è un POOL autorale pescato seeded — mai un
    prefisso unico (il timbro ripetuto è déjà-vu). Stesso stream = stessa
    descrizione (replay-safe); su un campione le aperture variano."""
    from motore.fabbrica import _VOCI_FATTURA

    _arma_fabbrica()
    a = conia_procedurale(random.Random(21), "oro")
    b = conia_procedurale(random.Random(21), "oro")
    assert a.descrizione == b.descrizione, "stesso stream → stessa voce"

    aperture = set()
    for i in range(40):
        o = conia_procedurale(random.Random(i), "oro", qualita="pregiato")
        aperture.add(next(
            v for v in _VOCI_FATTURA["pregiato"] if o.descrizione.startswith(v)
        ))
    assert len(aperture) >= 3, "il timbro unico è tornato: la voce deve variare"


def test_la_nota_dell_affisso_e_tessuta_nel_pezzo(mondo_isolato) -> None:
    """La nota dell'ELEMENTO è dato d'asset (`ParteAffisso.descrizione`) e il
    compositore la tesse nella descrizione del conio che porta quell'affisso."""
    from motore import fabbrica_attiva

    _arma_fabbrica()
    fabbrica = fabbrica_attiva()
    assert any(a.descrizione for a in fabbrica.affissi), (
        "la stagione seed deve avere note d'affisso: sono dato autorale"
    )
    for i in range(60):
        o = conia_procedurale(random.Random(i), "oro", qualita="onesto")
        affisso = next(
            (a for a in fabbrica.affissi if f" {a.nome} " in f" {o.nome} "),
            None,
        )
        if affisso is not None and affisso.descrizione:
            assert affisso.descrizione in o.descrizione, (
                "l'elemento del nome deve raccontarsi nella descrizione"
            )
            return
    raise AssertionError("nessun conio con affisso nel campione: fabbrica rotta")


def test_la_vista_porta_grado_e_fattura(run_pulita, tmp_path) -> None:
    """§B-4, la vestizione: `zaino_vista` e `EquipVista` trasportano grado,
    fattura, descrizione (e l'effetto dei consumabili) — l'host veste, mai
    deduce dal nome."""
    import asyncio

    from main import costruisci_sessione
    from motore import assicura_zaino, protagonista
    from motore.oggetti import assicura_coniati

    sessione = costruisci_sessione(nome="Vetrina", seed=2, directory=tmp_path)
    asyncio.run(sessione.prossima_narrazione())
    pent = protagonista()[0]
    lama = conia_procedurale(
        random.Random(9), "argento", tipi_base=("arma",), qualita="pregiato",
    )
    assicura_coniati(pent).voci.append(lama)
    assicura_zaino(pent).fonti.append(lama.slug)

    riga = next(r for r in sessione.zaino_vista() if r.fonte == lama.slug)
    assert (riga.tipo, riga.grado, riga.qualita) == ("arma", "argento", "pregiato")
    assert riga.descrizione == lama.descrizione and riga.indossato is False
    # Un consumabile demo nello zaino porta il suo effetto (il bottone «Usa»).
    assicura_zaino(pent).fonti.append("tonico-di-latta")
    tonico = next(r for r in sessione.zaino_vista() if r.fonte == "tonico-di-latta")
    assert (tonico.tipo, tonico.effetto) == ("consumabile", "cura")

    sessione.equipaggia(lama.slug)
    from contracts import SlotEquip

    vista_arma = next(
        v for v in sessione.scheda().equip if v.slot is SlotEquip.ARMA
    )
    assert (vista_arma.grado, vista_arma.qualita) == ("argento", "pregiato")
    assert vista_arma.descrizione == lama.descrizione
    riga = next(r for r in sessione.zaino_vista() if r.fonte == lama.slug)
    assert riga.indossato is True
    sessione.esci()


def test_i_save_vecchi_non_cambiano(mondo_isolato) -> None:
    """Un `OggettoAttivo` deserializzato SENZA campo qualità (save pre-B2)
    è onesto: stesso danno, stessi numeri di prima."""
    from motore.design import OggettoAttivo

    dati = {"slug": "lama-vecchia", "nome": "Lama vecchia",
            "tipo": "arma", "grado": "oro"}
    vecchio = OggettoAttivo(**dati)
    assert vecchio.qualita == "onesto"
    assert oggetto_da_asset(vecchio).danno_base == cal.DANNO_ARMA_PER_GRADO["oro"]
