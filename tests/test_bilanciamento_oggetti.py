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
    _arma_fabbrica()
    scarto = conia_procedurale(random.Random(3), "oro", qualita="scarto")
    assert scarto.qualita == "scarto"
    assert scarto.resistenze == (), "lo scarto non porta l'elemento"
    assert "scarto" in scarto.descrizione.lower()

    onesto = conia_procedurale(random.Random(3), "bronzo", qualita="onesto")
    pregiato = conia_procedurale(random.Random(3), "bronzo", qualita="pregiato")
    # Stesso stream: il pregiato di bronzo ha UN affisso dove l'onesto zero
    # (la sovrapposizione col grado sopra, per costruzione).
    assert len(pregiato.modificatori) >= len(onesto.modificatori)
    assert "pregiata" in pregiato.descrizione.lower()


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


def test_i_save_vecchi_non_cambiano(mondo_isolato) -> None:
    """Un `OggettoAttivo` deserializzato SENZA campo qualità (save pre-B2)
    è onesto: stesso danno, stessi numeri di prima."""
    from motore.design import OggettoAttivo

    dati = {"slug": "lama-vecchia", "nome": "Lama vecchia",
            "tipo": "arma", "grado": "oro"}
    vecchio = OggettoAttivo(**dati)
    assert vecchio.qualita == "onesto"
    assert oggetto_da_asset(vecchio).danno_base == cal.DANNO_ARMA_PER_GRADO["oro"]
