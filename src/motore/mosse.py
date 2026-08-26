"""Catalogo delle MOSSE: la mappa `chiave → composizione di Effetto` come DATO.

È il "motore-skill in miniatura" promesso da `azione.py` §7.3: una mossa è **una voce
di catalogo + righe di `Effetto`** — zero righe nel loop/risolutore. Il system di
combattimento (`_scegli_azione`) SCEGLIE una chiave dal `Repertorio` dell'entità
(componente-dato, `mob.py`) con l'RNG seeded del motore (G-4, mai l'LLM) e la
traduce in `Azione` qui. Aggiungere una mossa = una voce in questo catalogo;
aggiungere un *primitivo* nuovo (`Effetto`) = un handler nel risolutore.

Il catalogo è CHIUSO e del motore (G-22: il contratto porta i nomi, il motore
possiede i numeri): gli asset e l'AI selezionano chiavi, mai numeri né codice.
I numeri (moltiplicatori) vengono da `calibrazione` (§11, tarabili da console).
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts import Blocco, StileAttacco, TipoDanno

from .azione import ApplicaStatus, Azione, Danno, Effetto, QuantitaDa
from .azzardo import DannoVariabile
from .calibrazione import (
    COOLDOWN_MOSSA,
    COSTO_MANA_MOSSA,
    MOLT_ATTACCO_PESANTE,
    MOLT_DARDO_ARCANO,
)


@dataclass(frozen=True)
class Mossa:
    """Una voce del catalogo: composizione di primitivi + costo. Gli `Effetto` sono
    già liberi da sorgente/bersaglio (li lega `azione_da_mossa` nel giro).

    `etichetta` è il nome DIEGETICO per il menu del giocatore: contenuto, non un
    numero (niente §11). Vuota → la deriva `etichetta_mossa` dalla chiave."""

    chiave: str
    effetti: tuple[Effetto, ...]
    costo_ap: int = 1
    etichetta: str = ""
    costo_mana: int = 0   # §11: la risorsa che limita le mosse forti
    cooldown: int = 0     # §11: turni di ricarica (N=2 blocca un proprio turno; N=1 è nullo)
    # DICHIARAZIONE d'azzardo: questa mossa vuole un esito incerto (`azzardo.py`). È
    # l'unico modo di accendere il consenso sull'`Azione`, ed è per questo che sta nel
    # CATALOGO e non nell'effetto: la scelta di giocare d'azzardo è della mossa, non del
    # primitivo — un `DannoVariabile` finito per errore in una mossa non dichiarata viene
    # semplicemente saltato dal risolutore.
    azzardo: bool = False


# Le due mosse storiche dell'MVP. Il danno base è TIPATO (MISCHIA): attiva il layer
# resistenze — coi profili default (res 0) il moltiplicatore è identità, TTK invariato.
CATALOGO_MOSSE: dict[str, Mossa] = {
    m.chiave: m
    for m in (
        Mossa("attacco", (Danno(quantita_da=QuantitaDa.ATK_EFF, tipo=TipoDanno.MISCHIA),),
              etichetta="Attacca"),
        Mossa("attacco_pesante", (
            Danno(quantita_da=QuantitaDa.ATK_EFF, tipo=TipoDanno.MISCHIA,
                  moltiplicatore=MOLT_ATTACCO_PESANTE),
        ), etichetta="Colpo pesante",
            costo_mana=COSTO_MANA_MOSSA["attacco_pesante"],
            cooldown=COOLDOWN_MOSSA["attacco_pesante"]),
        # Primitivi componibili dimostrati (G-23): mosse che colpiscono E applicano
        # un blocco. Non sono nel repertorio di default: le porta chi le dichiara
        # nei dati (archetipo-asset o mob-asset).
        Mossa("morso_velenoso", (
            Danno(quantita_da=QuantitaDa.ATK_EFF, tipo=TipoDanno.VELENO),
            ApplicaStatus(blocco=Blocco.VELENO),
        ), etichetta="Morso velenoso", cooldown=COOLDOWN_MOSSA["morso_velenoso"]),
        Mossa("sputo_infuocato", (
            Danno(quantita_da=QuantitaDa.ATK_EFF, tipo=TipoDanno.FUOCO),
            ApplicaStatus(blocco=Blocco.BRUCIA),
        ), etichetta="Sputo infuocato", cooldown=COOLDOWN_MOSSA["sputo_infuocato"]),
        # --- AZZARDO OPT-IN (F10) — la sola voce del catalogo che PESCA. ---------
        # ⚠️ Non è "il tiro del danno": il danno del gioco è deterministico (check 2).
        # Questa è la *magia dall'esito incerto* di Gr2 §5.2, e per esistere deve
        # dichiararsi con `azzardo=True` — senza, il risolutore la salta senza pescare.
        # NON sta in `MOSSE_DEFAULT` né nel repertorio iniziale del protagonista: la
        # porta chi se la procura, ed è un test statico a impedire che ci finisca.
        Mossa("roulette_del_sistema", (
            DannoVariabile(minimo=1, massimo=20, tipo=TipoDanno.GENERICO,
                           stile=StileAttacco.MAGICO),  # «magia dall'esito incerto» (Gr2 §5.2)
        ), etichetta="Roulette del Sistema", costo_mana=COSTO_MANA_MOSSA["roulette_del_sistema"],
            azzardo=True),
        # L'INCANTESIMO del protagonista: nessuna ricarica, il limite è la risorsa.
        # Danno FUOCO e non un tipo nuovo — `TipoDanno` è un vocabolario chiuso e
        # il fuoco incrocia le resistenze già calibrate degli archetipi. Stile MAGICO:
        # mira con Intelligenza (acc_mag_eff), non con Destrezza.
        Mossa("dardo_arcano", (
            Danno(quantita_da=QuantitaDa.ATK_EFF, tipo=TipoDanno.FUOCO,
                  moltiplicatore=MOLT_DARDO_ARCANO, stile=StileAttacco.MAGICO),
        ), etichetta="Dardo arcano", costo_mana=COSTO_MANA_MOSSA["dardo_arcano"]),
    )
}


def _fascia(valore) -> str:
    """str | Enum → il `.value` (le due sorgenti: asset Pydantic, attivo congelato)."""
    return getattr(valore, "value", valore)


def mossa_da_dati(dati) -> Mossa:
    """La traduzione mossa-asset → `Mossa` viva (T3a): QUI vive la membrana —
    contracts possiede la FORMA (`EffettoDati`, fasce), il motore i numeri
    (fasce §11) e i primitivi (`Effetto`). Duck-typed sulle due forme
    (`MossaAsset` con enum, `MossaAttiva` congelata con stringhe). Il
    risolutore continua a vedere solo `Mossa`: zero righe nel loop."""
    from contracts import Blocco as _Blocco
    from contracts import TipoDanno as _TipoDanno

    from .calibrazione import (
        FASCIA_COSTO_MOSSA,
        FASCIA_POTENZA_MOSSA,
        FASCIA_RICARICA_MOSSA,
        FASCIA_RISCHIO_MOSSA,
    )

    effetti: list[Effetto] = []
    for e in dati.effetti:
        tipo = _TipoDanno(_fascia(e.tipo_danno)) if e.tipo_danno else _TipoDanno.GENERICO
        stile = StileAttacco(_fascia(e.stile)) if e.stile else StileAttacco.FISICO
        if e.primitivo == "danno":
            effetti.append(Danno(
                quantita_da=QuantitaDa.ATK_EFF, tipo=tipo, stile=stile,
                moltiplicatore=FASCIA_POTENZA_MOSSA[_fascia(e.potenza) or "standard"],
            ))
        elif e.primitivo == "danno_variabile":
            minimo, massimo = FASCIA_RISCHIO_MOSSA[_fascia(e.rischio) or "contenuto"]
            effetti.append(DannoVariabile(minimo=minimo, massimo=massimo, tipo=tipo, stile=stile))
        elif e.primitivo == "applica_status":
            effetti.append(ApplicaStatus(blocco=_Blocco(_fascia(e.blocco))))
    chiave = getattr(dati, "chiave", None) or dati.slug
    return Mossa(
        chiave=chiave,
        effetti=tuple(effetti),
        etichetta=dati.etichetta,
        costo_mana=FASCIA_COSTO_MOSSA[_fascia(dati.costo)],
        cooldown=FASCIA_RICARICA_MOSSA[_fascia(dati.ricarica)],
        azzardo=dati.azzardo,
    )


def catalogo_mosse_correnti() -> dict[str, Mossa]:
    """Il catalogo mosse DELLA RUN: lo storico più le mosse-asset congelate
    nella stagione (freeze batte catalogo). Senza stagione: lo storico."""
    from .design import stagione_corrente

    catalogo = dict(CATALOGO_MOSSE)
    stagione = stagione_corrente()
    if stagione is not None:
        for attiva in getattr(stagione, "mosse", ()):
            catalogo[attiva.chiave] = mossa_da_dati(attiva)
    return catalogo


def mossa_di(chiave: str) -> Mossa | None:
    """L'UNICO punto di lookup runtime di una mossa: storico, poi le congelate
    della stagione. `None` = chiave ignota (il chiamante decide il degrado)."""
    mossa = CATALOGO_MOSSE.get(chiave)
    if mossa is not None:
        return mossa
    from .design import stagione_corrente

    stagione = stagione_corrente()
    if stagione is not None:
        for attiva in getattr(stagione, "mosse", ()):
            if attiva.chiave == chiave:
                return mossa_da_dati(attiva)
    return None


def etichetta_mossa(chiave: str) -> str:
    """Il nome diegetico della mossa per il menu ("" o chiave ignota → derivata
    dalla chiave: mai un buco nel menu per un dato incompleto)."""
    mossa = mossa_di(chiave)
    if mossa is not None and mossa.etichetta:
        return mossa.etichetta
    return chiave.replace("_", " ").capitalize()

# Il repertorio di chi non dichiara nulla: il comportamento storico, ora come dato.
MOSSE_DEFAULT: tuple[str, ...] = ("attacco", "attacco_pesante")


# --- Seam: fonti AGGIUNTIVE di mosse (chi concede si registra, il risolutore
# legge fonti anonime). Serve all'equip — le mosse degli oggetti sono DERIVATE
# alla lettura, mai scritte nel Repertorio persistente — senza che il risolutore
# nomini mai l'equip (il lucchetto di ADR-1 F2 resta intatto).
_FONTI_MOSSE: list = []


def registra_fonte_mosse(fonte) -> None:
    """Registra un lettore `entita -> tuple[chiavi]` (idempotente)."""
    if fonte not in _FONTI_MOSSE:
        _FONTI_MOSSE.append(fonte)


def mosse_concesse(entita: int) -> tuple[str, ...]:
    """Le mosse concesse dalle fonti registrate, in ordine e senza duplicati."""
    viste: set[str] = set()
    out: list[str] = []
    for fonte in _FONTI_MOSSE:
        for chiave in fonte(entita):
            if chiave not in viste:
                viste.add(chiave)
                out.append(chiave)
    return tuple(out)


def mosse_note() -> frozenset[str]:
    """Le chiavi del catalogo STORICO (lint di authoring e vocabolario base).
    Il chiamante d'authoring che conosce la libreria vi somma le mosse-asset
    (il motore non scandisce mai il disco: la libreria è del composition root);
    a runtime l'autorità è `mossa_di`/`mosse_note_correnti` (il congelato)."""
    return frozenset(CATALOGO_MOSSE)


def mosse_note_correnti() -> frozenset[str]:
    """Le chiavi note ALLA RUN: storico + mosse-asset congelate nella stagione."""
    from .design import stagione_corrente

    note = set(CATALOGO_MOSSE)
    stagione = stagione_corrente()
    if stagione is not None:
        note |= {attiva.chiave for attiva in getattr(stagione, "mosse", ())}
    return frozenset(note)


def azione_da_mossa(chiave: str, *, sorgente: int, bersaglio: int | None) -> Azione:
    """Traduce una chiave nell'`Azione` transitoria del giro (le tre giunture
    di GR2-12/13 restano nel risolutore; qui solo la composizione). Il lookup
    passa da `mossa_di`: anche una mossa-asset congelata si esegue identica."""
    mossa = mossa_di(chiave)
    if mossa is None:
        raise KeyError(chiave)
    return Azione(
        sorgente=sorgente,
        bersaglio=bersaglio,
        effetti=list(mossa.effetti),
        costo={"AP": mossa.costo_ap, "MANA": mossa.costo_mana},
        mossa=chiave,
        consenso_azzardo=mossa.azzardo,   # solo chi lo dichiara può pescare
    )
