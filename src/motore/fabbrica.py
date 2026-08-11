"""La FABBRICA del loot procedurale — Borderlands, in piccolo (T-fabbrica).

Il grosso del bottino non lo genera un'AI per-oggetto: lo CONIA il motore
combinando PARTI autorate (basi × famiglie × affissi × grado), seeded — come i
boss procedurali (nome × gimmick × archetipo). L'AI entra una volta sola, in
authoring, a scrivere le tabelle-parti (`authoring.fabbrica`); da lì in poi la
fabbrica sforna oggetti deterministici, gratuiti e disponibili anche offline.

Regole d'assemblaggio (la "rarità" di BL3, tradotta ai gradi):
  - BRONZO:  base × famiglia (il pezzo comune);
  - ARGENTO+: + un affisso (l'"elemento": resistenza tipata o tratto);
  - ORO+:    + un secondo affisso (solo contributo, il nome resta leggibile).
I modificatori si SOMMANO per stat tenendo la fascia più alta (cap 4: il
validator degli asset è la legge anche qui); i numeri restano del motore
(fascia × rango del grado, foglie §11). Il nome è composto —
«{base} {affisso} {famiglia}» — e lo slug porta un suffisso derivato dallo
stesso stream seeded: replay-safe per costruzione.
"""

from __future__ import annotations

import random
import re

from .design import FabbricaAttiva, OggettoAttivo, stagione_corrente


def fabbrica_attiva() -> FabbricaAttiva | None:
    """La fabbrica congelata nella run (None = stagione senza fabbrica o save
    legacy: il drop resta pool + conio AI)."""
    stagione = stagione_corrente()
    if stagione is None:
        return None
    fabbrica = getattr(stagione, "fabbrica", None)
    if fabbrica is None or not (fabbrica.basi and fabbrica.famiglie):
        return None
    return fabbrica


def _slug(testo: str) -> str:
    pulito = re.sub(r"[^a-z0-9]+", "-", testo.lower()).strip("-")
    return pulito[:48] or "conio"


def _fascia_maggiore(a: str, b: str) -> str:
    from .calibrazione import OGGETTO_MOD_FASCIA

    return a if OGGETTO_MOD_FASCIA[a] >= OGGETTO_MOD_FASCIA[b] else b


def conia_procedurale(rng: random.Random, grado: str) -> OggettoAttivo | None:
    """UN oggetto dalla fabbrica, per il grado deciso dal motore. `None` senza
    fabbrica attiva. Deterministico: stesso stream RNG → stesso oggetto."""
    from .catalogo import RANGO_GRADO
    from contracts import Grado

    fabbrica = fabbrica_attiva()
    if fabbrica is None:
        return None
    base = fabbrica.basi[rng.randrange(len(fabbrica.basi))]
    famiglia = fabbrica.famiglie[rng.randrange(len(fabbrica.famiglie))]

    rango = RANGO_GRADO[Grado(grado)]
    affissi = []
    if fabbrica.affissi and rango >= 2:              # ARGENTO+: l'elemento
        affissi.append(fabbrica.affissi[rng.randrange(len(fabbrica.affissi))])
    if fabbrica.affissi and rango >= 3:              # ORO+: il secondo tratto
        secondo = fabbrica.affissi[rng.randrange(len(fabbrica.affissi))]
        if secondo.nome != affissi[0].nome:
            affissi.append(secondo)

    # Merge dei modificatori: per stat vince la fascia più alta; cap 4 (la
    # stessa legge del validator degli asset).
    per_stat: dict[str, str] = {}
    for parte in (famiglia, *affissi):
        for stat, fascia in parte.modificatori:
            per_stat[stat] = (_fascia_maggiore(per_stat[stat], fascia)
                              if stat in per_stat else fascia)
    modificatori = tuple(sorted(per_stat.items()))[:4]

    resistenze = tuple(
        (a.res_contro, a.res_fascia) for a in affissi if a.res_contro is not None
    )

    nome = " ".join(x for x in (
        base.nome, affissi[0].nome if affissi else "", famiglia.nome,
    ) if x)
    # Suffisso dallo STESSO stream seeded: due coni della stessa run non
    # collidono, e il replay riconia identico.
    suffisso = f"{rng.randrange(16 ** 4):04x}"
    descrizione = famiglia.descrizione or "Uscito dalla catena di montaggio del piano."

    return OggettoAttivo(
        slug=f"{_slug(nome)}-{suffisso}",
        nome=nome,
        tipo=base.tipo,
        grado=grado,
        descrizione=descrizione,
        slot=base.slot,
        categoria=base.categoria,
        taglia=base.taglia,
        sede=base.sede,
        modificatori=modificatori,
        resistenze=resistenze,
    )
