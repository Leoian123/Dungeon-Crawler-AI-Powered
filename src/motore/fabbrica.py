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


_DESCRIZIONE_QUALITA = {
    # Le due fatture VISIBILI (nodo B2, registro originale): lo scarto è metà
    # del tono del dungeon, il pregiato è la festa. L'onesto tace.
    "scarto": "Fattura di scarto: la catena l'ha sputato senza voltarsi.",
    "pregiato": "Fattura pregiata: la catena, per una volta, ha preso la mira.",
}


def _pesca_qualita(rng: random.Random, grado: str) -> str:
    """Il ventaglio DENTRO il grado (nodo B2): pescata pesata sui pesi §11
    (`LOOT.QUALITA.{grado}.*`, derivati dal dataset di riferimento). A pesi
    tutti nulli il ventaglio è spento: onesto, il comportamento storico."""
    from .calibrazione import LOOT_QUALITA_PESI, QUALITA_CONIO

    pesi = LOOT_QUALITA_PESI.get(grado, {})
    totale = sum(pesi.get(q, 0) for q in QUALITA_CONIO)
    if totale <= 0:
        return "onesto"
    tiro = rng.random() * totale
    cumulo = 0.0
    for q in QUALITA_CONIO:
        cumulo += pesi.get(q, 0)
        if tiro < cumulo:
            return q
    return "onesto"


def _assembla(base, famiglia, affissi, grado: str, suffisso: str,
              *, nome: str | None = None,
              descrizione: str | None = None,
              qualita: str = "onesto") -> OggettoAttivo:
    """L'UNICO assemblatore: dalle parti all'`OggettoAttivo`. Lo usano il conio
    procedurale (parti pescate seeded) e il pezzo UNICO (parti SCELTE dall'AI,
    gated): la meccanica esce sempre dalla stessa catena — merge per stat con
    la fascia più alta (cap 4), resistenze dagli affissi, numeri dal §11 alla
    traduzione. `nome`/`descrizione` espliciti = la targhetta del pezzo unico."""
    per_stat: dict[str, str] = {}
    for parte in (famiglia, *affissi):
        for stat, fascia in parte.modificatori:
            per_stat[stat] = (_fascia_maggiore(per_stat[stat], fascia)
                              if stat in per_stat else fascia)
    modificatori = tuple(sorted(per_stat.items()))[:4]
    resistenze = tuple(
        (a.res_contro, a.res_fascia) for a in affissi if a.res_contro is not None
    )
    composto = " ".join(x for x in (
        base.nome, affissi[0].nome if affissi else "", famiglia.nome,
    ) if x)
    descr = (descrizione or famiglia.descrizione
             or "Uscito dalla catena di montaggio del piano.")
    battuta = _DESCRIZIONE_QUALITA.get(qualita)
    if battuta:
        descr = f"{battuta} {descr}".strip()
    return OggettoAttivo(
        slug=f"{_slug(nome or composto)}-{suffisso}",
        nome=nome or composto,
        tipo=base.tipo,
        grado=grado,
        descrizione=descr,
        qualita=qualita,
        slot=base.slot,
        categoria=base.categoria,
        taglia=base.taglia,
        sede=base.sede,
        modificatori=modificatori,
        resistenze=resistenze,
    )


def conia_procedurale(
    rng: random.Random, grado: str, *, escludi_famiglia: str = "",
    tipi_base: tuple[str, ...] | None = None,
    qualita: str | None = None,
) -> OggettoAttivo | None:
    """UN oggetto dalla fabbrica, per il grado deciso dal motore. `None` senza
    fabbrica attiva. Deterministico: stesso stream RNG → stesso oggetto.

    `escludi_famiglia` (playtest 2026-08-19: tre «della Maschera» di fila): la
    manifattura dell'ULTIMO conio non si ripete se la fabbrica ne ha altre —
    SHIFT deterministico all'indice successivo, nessun draw in più: il resto
    dello stream (affissi, suffisso) resta byte-identico allo storico.

    `tipi_base` (nodo O2, le box a categoria): vincola la pescata della BASE
    ai soli tipi indicati (es. `("arma",)`); `None` = tutte — il drop storico
    resta byte-identico. `None` anche se il vincolo azzera i candidati (una
    box che non può aprire nulla è un errore di catalogo, non un crash).

    `qualita` (nodo B2, il ventaglio dentro il grado): `None` = pescata pesata
    §11 IN CODA allo stream (base/famiglia/affissi/suffisso restano
    byte-identici allo storico); una qualità esplicita è la dichiarazione del
    chiamante (test, box speciali future). SCARTO scarta gli affissi già
    pescati (il junk di consolazione); PREGIATO ne aggiunge uno in più."""
    from .catalogo import RANGO_GRADO
    from contracts import Grado

    fabbrica = fabbrica_attiva()
    if fabbrica is None:
        return None
    basi = (
        fabbrica.basi if tipi_base is None
        else [b for b in fabbrica.basi if b.tipo in tipi_base]
    )
    if not basi:
        return None
    base = basi[rng.randrange(len(basi))]
    indice = rng.randrange(len(fabbrica.famiglie))
    famiglia = fabbrica.famiglie[indice]
    if (escludi_famiglia and famiglia.nome == escludi_famiglia
            and len(fabbrica.famiglie) > 1):
        famiglia = fabbrica.famiglie[(indice + 1) % len(fabbrica.famiglie)]

    rango = RANGO_GRADO[Grado(grado)]
    affissi = []
    if fabbrica.affissi and rango >= 2:              # ARGENTO+: l'elemento
        affissi.append(fabbrica.affissi[rng.randrange(len(fabbrica.affissi))])
    if fabbrica.affissi and rango >= 3:              # ORO+: il secondo tratto
        secondo = fabbrica.affissi[rng.randrange(len(fabbrica.affissi))]
        if secondo.nome != affissi[0].nome:
            affissi.append(secondo)

    # Suffisso dallo STESSO stream seeded: due coni della stessa run non
    # collidono, e il replay riconia identico.
    suffisso = f"{rng.randrange(16 ** 4):04x}"

    # La qualità si pesca DOPO il suffisso: i draw storici non si spostano.
    if qualita is None:
        qualita = _pesca_qualita(rng, grado)
    if qualita == "scarto":
        affissi = []
    elif qualita == "pregiato" and fabbrica.affissi:
        extra = fabbrica.affissi[rng.randrange(len(fabbrica.affissi))]
        if all(a.nome != extra.nome for a in affissi):
            affissi.append(extra)
    return _assembla(base, famiglia, affissi, grado, suffisso, qualita=qualita)


def assembla_unico(scelte, grado: str, rng: random.Random):
    """Il PEZZO UNICO: l'AI ha SCELTO i componenti per nome (dalle tabelle
    della fabbrica) e la targhetta; il motore risolve i nomi, GATA e assembla
    con la stessa catena del procedurale. Ritorna (OggettoAttivo|None, motivo).

    È l'ottimizzazione del conio: schema e prompt portano NOMI DI PARTE, non
    un oggetto intero — l'AI propone dal catalogo-parti, il motore dispone."""
    fabbrica = fabbrica_attiva()
    if fabbrica is None:
        return None, "nessuna fabbrica attiva"
    per_nome_base = {b.nome: b for b in fabbrica.basi}
    per_nome_famiglia = {f.nome: f for f in fabbrica.famiglie}
    per_nome_affisso = {a.nome: a for a in fabbrica.affissi}

    base = per_nome_base.get(scelte.base)
    if base is None:
        return None, f"base ignota: {scelte.base!r}"
    famiglia = per_nome_famiglia.get(scelte.famiglia)
    if famiglia is None:
        return None, f"famiglia ignota: {scelte.famiglia!r}"
    affissi = []
    for nome_affisso in scelte.affissi:
        affisso = per_nome_affisso.get(nome_affisso)
        if affisso is None:
            return None, f"affisso ignoto: {nome_affisso!r}"
        if affisso not in affissi:
            affissi.append(affisso)
    if not scelte.nome.strip():
        return None, "nome del pezzo unico vuoto"

    suffisso = f"{rng.randrange(16 ** 4):04x}"
    return _assembla(
        base, famiglia, affissi, grado, suffisso,
        nome=scelte.nome, descrizione=scelte.descrizione,
    ), None
