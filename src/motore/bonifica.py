"""Bonifica della prosa — il gate di FORMA sul canale unico (2026-08-27).

Lo slop non si cura con prompt mirati: si cura con un SISTEMA. Qui vive la
TABELLA UNICA (`REGOLE_SLOP`) — ogni regola è una riga: slug, misura
deterministica, soglia, nota di regia. Dalla stessa tabella derivano TUTTI i
consumatori, che così non possono divergere (dottrina SPEC_STATUS):

  1. la riga di stile nei prefissi (`riga_stile_derivata`) — il prompt DICE
     esattamente ciò che il gate MISURA;
  2. il gate con retry di regia (`misura_slop` + `righe_regia`) — engine e
     `procura_turno` ripetono UNA chiamata con le violazioni come note;
  3. la telemetria (le violazioni sopravvissute si contano per rotta);
  4. i lucchetti di auto-coerenza (test): gli esemplari del prefisso e i
     fallback deterministici passano la loro stessa bonifica.

Dottrina del gate: la forma non blocca MAI il gioco. A violazione si ritenta
(`BONIFICA.retry`, §11); se il secondo giro non migliora, si accetta il testo
migliore e si conta. Zero RNG, zero rete: ogni misura è una funzione pura.

Aggiungere una regola = aggiungere una riga alla tabella (e il suo test).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

# --- Le misure: funzioni pure testo → conteggio ---------------------------------

_RE_PAROLE = re.compile(r"[a-zà-ù0-9]+", re.IGNORECASE)
# Frase = segmento chiuso da .!?… (l'ellissi conta come chiusura).
_RE_FRASI = re.compile(r"[^.!?…]+[.!?…]+")
_RE_TOKEN = re.compile(r"[a-zà-ù0-9]{3,}")
# Il PARLATO dei personaggi: gli span fra caporali (o fra apici dritti, per
# la prosa non ancora rifinita). Le regole con ambito "narrazione" lo tolgono
# prima di misurare: la voce di un personaggio è VOCE — un fante che parla
# telegrafico («Guerra cambia forma. No.») non è slop del narratore, e il
# gate non deve stirare le cadenze autorate (riscontro utente 2026-08-27).
_RE_PARLATO = re.compile(r"«[^»]*»|\"[^\"]*\"")


def _solo_narrazione(testo: str) -> str:
    return _RE_PARLATO.sub(" ", testo)


def _parole(testo: str) -> int:
    return len(_RE_PAROLE.findall(testo))


def _frasi(testo: str) -> list[str]:
    return [f.strip() for f in _RE_FRASI.findall(testo) if f.strip()]


def _conta_come_se(testo: str) -> int:
    return len(re.findall(r"\bcome se\b", testo, re.IGNORECASE))


def _conta_lineette(testo: str) -> int:
    return testo.count("—")


def _conta_frammenti_eco(testo: str) -> int:
    """Frasi-frammento di 1-2 parole («Ce l'ha.», «Aspetta.»): il tic del
    ritmo staccato che il modello serializza quando piace troppo. Contano i
    token di almeno 2 lettere: l'elisione («l'») non fa parola."""
    return sum(
        1 for f in _frasi(testo)
        if len([p for p in _RE_PAROLE.findall(f) if len(p) >= 2]) <= 2
    )


def _conta_numero_stanza(testo: str) -> int:
    """«La stanza 4 puzza di colla»: il dato di mappa recitato in prosa — il
    tell più gamey di tutti. Il numero vive nei descrittori, mai nella scena."""
    return len(re.findall(r"\bstanz[ae]\s+\d+", testo, re.IGNORECASE))


def _conta_retorica_non(testo: str) -> int:
    """Il pattern «non entra: materializza» — efficace una volta, tic alla
    seconda. Si misura la forma `non <parola>: <parola>`."""
    return len(re.findall(r"\bnon\s+\w+\s*:\s*\w", testo, re.IGNORECASE))


def _conta_frasi_fiume(testo: str) -> int:
    """Frasi oltre le ~40 parole: l'apnea che il playtest live 2026-08-27 ha
    chiamato «prosa pesante» — immagini impilate senza un punto a dividerle."""
    return sum(1 for f in _frasi(testo) if len(_RE_PAROLE.findall(f)) > 40)


def _conta_grappoli_di_che(testo: str) -> int:
    """Tre o più «che» nella STESSA frase: il grappolo di relative («un suono
    che potrebbe essere l'aria che fuoriesce da polmoni che non respirano») —
    la sintassi che si avvita è la faccia misurabile della prosa confusa."""
    return sum(
        1 for f in _frasi(testo)
        if len(re.findall(r"\bche\b", f, re.IGNORECASE)) >= 3
    )


# Lessico dei cliché da dungeon generico: la lista È il dato — estenderla è
# una riga. Confronto case-insensitive su testo normalizzato.
CLICHE = (
    "torce tremolanti",
    "torcia tremolante",
    "aria pesante",
    "silenzio di tomba",
    "brivido lungo la schiena",
    "sangue si gela",
    "puzza di morte",
    "odore di morte",
    "buio impenetrabile",
    "oscurità impenetrabile",
)


def _conta_cliche(testo: str) -> int:
    basso = testo.lower()
    return sum(basso.count(c) for c in CLICHE)


# --- La tabella unica ------------------------------------------------------------

@dataclass(frozen=True)
class RegolaSlop:
    """Una regola della bonifica: dato puro, congelato.

    `soglia` = occorrenze ammesse nella finestra di parole (§11,
    `BONIFICA.parole_finestra`); `scala_su_lunghezza` = la soglia cresce coi
    testi lunghi (densità), altrimenti è assoluta. `regia` è la nota che il
    retry mostra al modello; `stile` la clausola che finisce nel prefisso."""

    slug: str
    conta: Callable[[str], int]
    soglia: int
    regia: str
    stile: str
    scala_su_lunghezza: bool = True
    # "tutto" misura il testo intero; "narrazione" toglie prima il PARLATO
    # (gli span fra virgolette): le regole di ritmo non giudicano mai la
    # voce di un personaggio — quella è cadenza autorata, non slop.
    ambito: str = "tutto"


REGOLE_SLOP: tuple[RegolaSlop, ...] = (
    RegolaSlop(
        "similitudine-seriale", _conta_come_se, 1,
        "troppe similitudini con «come se»: al massimo una, le altre diventano "
        "immagini dirette",
        "massimo UN «come se» per scena — l'immagine diretta vale più della similitudine",
    ),
    RegolaSlop(
        "lineette", _conta_lineette, 4,
        "troppe lineette (—): sciogli gli incisi in frasi",
        "lineette (—) con parsimonia",
    ),
    RegolaSlop(
        "frammento-eco", _conta_frammenti_eco, 2,
        "troppe frasi-frammento di una o due parole nella narrazione: il "
        "ritmo staccato è un colpo, non una raffica",
        "frasi-frammento («Aspetta.») come colpi rari, mai in raffica",
        ambito="narrazione",
    ),
    RegolaSlop(
        "frase-fiume", _conta_frasi_fiume, 1,
        "frasi-fiume oltre le 40 parole nella narrazione: spezzale — il "
        "ritmo è lunghezza variata, non apnea",
        "le frasi respirano: spezza quelle oltre le ~40 parole",
        ambito="narrazione",
    ),
    RegolaSlop(
        "grappolo-di-che", _conta_grappoli_di_che, 0,
        "tre o più «che» nella stessa frase: sciogli il grappolo di "
        "relative in frasi piene",
        "mai tre «che» nella stessa frase — una frase, un'immagine",
        scala_su_lunghezza=False,
        ambito="narrazione",
    ),
    RegolaSlop(
        "numero-di-stanza", _conta_numero_stanza, 0,
        "il numero della stanza è un dato di mappa: in prosa la stanza si "
        "nomina per ciò che è",
        "MAI il numero della stanza in prosa: la stanza si nomina per ciò che è",
        scala_su_lunghezza=False,
    ),
    RegolaSlop(
        "retorica-non", _conta_retorica_non, 1,
        "il costrutto «non X: Y» è già stato speso: riformula",
        "il costrutto «non X: Y» al massimo una volta",
    ),
    RegolaSlop(
        "cliche", _conta_cliche, 0,
        "cliché da dungeon generico nel testo: sostituisci con un dettaglio "
        "concreto di QUESTO luogo",
        "niente cliché da dungeon generico (torce tremolanti, aria pesante, "
        "silenzio di tomba…)",
        scala_su_lunghezza=False,
    ),
)


# --- Le violazioni e la misura ---------------------------------------------------

@dataclass(frozen=True)
class ViolazioneSlop:
    slug: str
    conteggio: int
    ammesse: int
    regia: str


def _soglia_effettiva(regola: RegolaSlop, parole: int) -> int:
    if not regola.scala_su_lunghezza:
        return regola.soglia
    from .calibrazione import valore

    finestra = max(50, int(valore("BONIFICA.parole_finestra")))
    # La soglia scala per finestre INTERE (pavimento 1× soglia): un testo di
    # mezza finestra non scende sotto la soglia base — la severità non
    # punisce la brevità.
    return regola.soglia * max(1, parole // finestra)


def misura_slop(testo: str, *, incipit_precedente: str = "") -> tuple[ViolazioneSlop, ...]:
    """Le violazioni della tabella su UN testo. Pura e deterministica.

    `incipit_precedente`: la prima frase dell'ultima scena mostrata — se il
    chiamante la possiede, la regola dell'incipit-fotocopia si accende (due
    scene di fila che si aprono con lo stesso gesto sono il déjà-vu di forma:
    playtest 2026-08-27, «La porta si chiude alle tue spalle» ×2)."""
    if not testo:
        return ()
    parole = _parole(testo)
    narrazione = _solo_narrazione(testo)
    violazioni = []
    for regola in REGOLE_SLOP:
        bersaglio = narrazione if regola.ambito == "narrazione" else testo
        conteggio = regola.conta(bersaglio)
        ammesse = _soglia_effettiva(regola, parole)
        if conteggio > ammesse:
            violazioni.append(ViolazioneSlop(regola.slug, conteggio, ammesse, regola.regia))
    if incipit_precedente:
        eco = _incipit_fotocopia(testo, incipit_precedente)
        if eco is not None:
            violazioni.append(eco)
    return tuple(violazioni)


def prima_frase(testo: str) -> str:
    """La prima frase di un testo (per il registro d'incipit). "" se non c'è."""
    frasi = _frasi(testo)
    return frasi[0] if frasi else ""


def _incipit_fotocopia(testo: str, incipit_precedente: str) -> ViolazioneSlop | None:
    """Fotocopia d'incipit: la prima frase condivide troppi token con quella
    della scena precedente (>60% dei token della più corta)."""
    apertura = prima_frase(testo)
    if not apertura:
        return None
    a = frozenset(_RE_TOKEN.findall(apertura.lower()))
    b = frozenset(_RE_TOKEN.findall(incipit_precedente.lower()))
    if not a or not b:
        return None
    comuni = len(a & b)
    if comuni / min(len(a), len(b)) > 0.6:
        return ViolazioneSlop(
            "incipit-fotocopia", comuni, 0,
            "la scena si apre con lo stesso gesto della precedente: "
            "cambia attacco — un altro senso, un altro punto della stanza",
        )
    return None


# --- I consumatori derivati ------------------------------------------------------

def righe_regia(violazioni: tuple[ViolazioneSlop, ...]) -> str:
    """Le note di regia per il giro di retry: la bozza c'è stata, il gate
    dice COSA correggere. Vuota senza violazioni."""
    if not violazioni:
        return ""
    note = "; ".join(v.regia for v in violazioni)
    return (f"[regia] La bozza precedente è stata scartata dal gate di forma: "
            f"{note}. Riscrivi la scena intera correggendo SOLO questo: "
            "stessi fatti, stessa lunghezza.")


def riga_stile_derivata() -> str:
    """La clausola di stile DERIVATA dalla tabella, per i prefissi: prompt e
    gate leggono lo stesso dato. Byte-stabile (la tabella è una costante)."""
    return "[stile/forma] " + "; ".join(r.stile for r in REGOLE_SLOP) + "."


def retry_bonifica() -> int:
    """I giri di regia concessi (§11): 0 = gate passivo, solo telemetria."""
    from .calibrazione import valore

    return max(0, int(valore("BONIFICA.retry")))
