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

from contracts import Blocco, TipoDanno

from .azione import ApplicaStatus, Azione, Danno, Effetto, QuantitaDa
from .calibrazione import MOLT_ATTACCO_PESANTE


@dataclass(frozen=True)
class Mossa:
    """Una voce del catalogo: composizione di primitivi + costo. Gli `Effetto` sono
    già liberi da sorgente/bersaglio (li lega `azione_da_mossa` nel giro)."""

    chiave: str
    effetti: tuple[Effetto, ...]
    costo_ap: int = 1


# Le due mosse storiche dell'MVP. Il danno base è TIPATO (MISCHIA): attiva il layer
# resistenze — coi profili default (res 0) il moltiplicatore è identità, TTK invariato.
CATALOGO_MOSSE: dict[str, Mossa] = {
    m.chiave: m
    for m in (
        Mossa("attacco", (Danno(quantita_da=QuantitaDa.ATK_EFF, tipo=TipoDanno.MISCHIA),)),
        Mossa("attacco_pesante", (
            Danno(quantita_da=QuantitaDa.ATK_EFF, tipo=TipoDanno.MISCHIA,
                  moltiplicatore=MOLT_ATTACCO_PESANTE),
        )),
        # Primitivi componibili dimostrati (G-23): mosse che colpiscono E applicano
        # un blocco. Non sono nel repertorio di default: le porta chi le dichiara
        # nei dati (archetipo-asset o mob-asset).
        Mossa("morso_velenoso", (
            Danno(quantita_da=QuantitaDa.ATK_EFF, tipo=TipoDanno.VELENO),
            ApplicaStatus(blocco=Blocco.VELENO),
        )),
        Mossa("sputo_infuocato", (
            Danno(quantita_da=QuantitaDa.ATK_EFF, tipo=TipoDanno.FUOCO),
            ApplicaStatus(blocco=Blocco.BRUCIA),
        )),
    )
}

# Il repertorio di chi non dichiara nulla: il comportamento storico, ora come dato.
MOSSE_DEFAULT: tuple[str, ...] = ("attacco", "attacco_pesante")


def mosse_note() -> frozenset[str]:
    """Le chiavi del catalogo (per lint di authoring e vocabolario degli host)."""
    return frozenset(CATALOGO_MOSSE)


def azione_da_mossa(chiave: str, *, sorgente: int, bersaglio: int | None) -> Azione:
    """Traduce una chiave di catalogo nell'`Azione` transitoria del giro (le tre
    giunture di GR2-12/13 restano nel risolutore; qui solo la composizione)."""
    mossa = CATALOGO_MOSSE[chiave]
    return Azione(
        sorgente=sorgente,
        bersaglio=bersaglio,
        effetti=list(mossa.effetti),
        costo={"AP": mossa.costo_ap},
        mossa=chiave,
    )
