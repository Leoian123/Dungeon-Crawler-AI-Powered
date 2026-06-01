"""Round-trip di `Primarie`/`Modificatori` attraverso il serializzatore generico di H.

La metà difficile è il "e ritorno": ricostruire `StatId.FORZA` da "forza" (mappa a
chiave-enum) e `Modificatore` da un dict (lista di dataclass con tre campi-enum). Le
asserzioni sono **tipizzate** dopo il giro (`is StatId.FORZA`), non per uguaglianza di
stringa — altrimenti il test passerebbe anche se la ricostruzione enum mancasse.
"""

from __future__ import annotations

import json

from contracts import StatId
from motore import Modificatore, Modificatori, Origine, Primarie, TipoMod
from motore.persistenza.tag import deserializza_componente, serializza_componente


def _giro(comp):
    """Serializza, passa per JSON (chiavi/valori reali su disco) e deserializza."""
    tag, dati = serializza_componente(comp)
    dati = json.loads(json.dumps(dati))  # forza la realtà del transito su disco
    return deserializza_componente(tag, dati)


def test_primarie_roundtrip_tipizzato() -> None:
    orig = Primarie(valori={StatId.FORZA: 11, StatId.COSTITUZIONE: 30})
    ric = _giro(orig)
    assert isinstance(ric, Primarie)
    # Chiavi ricostruite come ENUM, non come stringhe.
    chiavi = set(ric.valori)
    assert StatId.FORZA in chiavi and StatId.COSTITUZIONE in chiavi
    assert all(isinstance(k, StatId) for k in chiavi)
    assert ric.valori[StatId.COSTITUZIONE] == 30


def test_modificatori_roundtrip_tipizzato() -> None:
    orig = Modificatori(voci=[
        Modificatore(StatId.FORZA, TipoMod.PCT, 0.25, "buff", Origine.PRIVILEGIATA),
        Modificatore(StatId.DESTREZZA, TipoMod.FLAT, 3, "equip"),
    ])
    ric = _giro(orig)
    assert isinstance(ric, Modificatori)
    assert len(ric.voci) == 2
    primo = ric.voci[0]
    # Ogni campo-enum dentro la dataclass annidata è ricostruito tipizzato.
    assert primo.stat is StatId.FORZA
    assert primo.tipo is TipoMod.PCT
    assert primo.origine is Origine.PRIVILEGIATA
    assert primo.valore == 0.25
    assert primo.fonte == "buff"
    # Il default di `origine` regge anche quando non era esplicito.
    assert ric.voci[1].origine is Origine.NORMALE
