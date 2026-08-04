"""L'`Azione` — atomo spezzato per il futuro motore-skill (Gruppo 2 §7; GR2-12/13/14/17).

Struttura **interna al motore, transitoria**: NON è un DTO di `contracts`, NON è
serializzata nel save, NON attraversa la membrana (GR2-17, IC). Per questo `sorgente`/
`bersaglio` possono essere **riferimenti vivi** (id di entità esper risolti *dentro il
turno*): vita brevissima, costruita e scartata nel giro. Vincolo assoluto: nessun ref vivo
di `Azione` finisce in un componente persistente, nel save o in un DTO.

"Spezzare l'atomo" (§7.2): il colpo MVP **passa già** dalle tre giunture — (1) selezione da
un insieme disponibile, (2) costo/disponibilità, (3) lista di `Effetto` iterata — con **un
solo abitante** (`[Danno]`, `costo={"AP": 1}`). Il giorno del motore-skill, "Palla di Fuoco"
sarà *una voce di catalogo + righe di Effetto*, zero righe nel loop/risolutore (§7.3).

⚠️ Il componente AP (`ActionPoint`) **NON** vive qui: è **stato posseduto per-entità** e sta
in `scheda.py` / nella factory mob (guida §6.1). `costo` lo referenzia **per chiave**.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from contracts import Blocco, TipoDanno


class QuantitaDa(str, Enum):
    """Come un `Danno` ricava la propria magnitudine dalla sorgente (FORMA, §7).

    Chiave minimale — **nessun nuovo schema inventato**: il risolutore la mappa a una
    derivata (`ATK_EFF → atk_eff(sorgente)`). Domani altre chiavi (una skill-stat, una
    risorsa) si aggiungono qui, senza toccare il risolutore."""

    ATK_EFF = "atk_eff"


@dataclass
class Effetto:
    """Base degli atomi-effetto componibili (Danno, e in futuro Cura/ApplicaStatus/Spingi…).

    FORMA dell'atomo di §7: il risolutore **itera** `effetti` (giuntura "itera-una-lista"),
    non chiama "infliggi danno". Il comportamento per-effetto è **dato** (composizione di
    primitivi registrati), non un sistema per tipo (§7.3)."""


@dataclass
class Danno(Effetto):
    """Primitivo di danno: la quantità (`atk_eff`) è quella di sempre; il `tipo` è solo una
    **chiave** per il filtro delle resistenze (Type Object, layer tipi DT-1) — default
    `GENERICO` (= danno agnostico odierno). **Vietato** sottotipi (`DannoFuoco`) o metodi
    per-tipo: il tipo è una **variabile membro**, non un override.

    `moltiplicatore` scala la magnitudine (mossa pesante = 1.5, §11): entra nel
    check 2 DENTRO lo stesso `round` di graze e resistenze — un solo arrotondamento."""

    quantita_da: QuantitaDa
    tipo: TipoDanno = TipoDanno.GENERICO
    moltiplicatore: float = 1.0


@dataclass
class ApplicaStatus(Effetto):
    """Primitivo: applica al bersaglio l'afflizione di un `Blocco` del catalogo.

    Il blocco è una **chiave** del vocabolario chiuso (Type Object, come `Danno.tipo`),
    mai una classe né un numero: rango COPIATO dal grado della sorgente (G §4.3) e
    durata dalla tabella-dato delle afflizioni — entrambi risolti dal system al
    momento del colpo, non qui."""

    blocco: Blocco


@dataclass
class Azione:
    """`{sorgente, bersaglio, effetti, costo}` (§7.1). L'attacco base è l'**unica istanza**
    dell'MVP: `effetti=[Danno(...)]`, `costo={"AP": 1}`. Il loop AP **esegue una `Azione`**,
    non "un attacco" (G §2.1, scritto generale fin da subito)."""

    sorgente: int                  # entità esper (ref vivo OK perché transitorio)
    bersaglio: int | None
    effetti: list[Effetto]
    costo: dict[str, int] = field(default_factory=lambda: {"AP": 1})  # referenzia l'AP per CHIAVE
    mossa: str = "attacco"         # chiave diegetica della mossa (per la cronaca)
