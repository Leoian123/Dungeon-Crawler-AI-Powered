"""Il canale dei CONSUMABILI (canale B, ratifica 2026-08-26) — monouso, solo
in narrazione, a specchio del canale equip.

Il dataset di riferimento è per metà consumabile (pozioni, pergamene): questo
è il CANALE, col dato demo originale — il contenuto vero è lavoro d'authoring
(`OggettoAsset` tipo "consumabile", vocabolario `EffettoConsumabile` chiuso).

Le regole (linee rosse applicate):
- l'asset NOMINA l'effetto, i numeri li deriva il motore: quote del MASSIMO
  per grado (§11, `CONSUMABILE.CURA_PCT.*` / `MANA_PCT.*`) — la pozione scala
  col pool, come «almeno il 50%» del riferimento;
- l'uso è un INTENTO tipizzato (`PlayerUsaOggetto`) servito da un sistema
  SOLO-narrazione: in combattimento resta in coda (phase-gate strutturale,
  mai un `if fase ==`). L'uso in scontro (costo AP + cooldown) è dichiarato
  post-MVP: muove il TTK e va misurato;
- l'uso RIFIUTATO non è un fatto: a HP pieni la pozione NON si consuma
  (niente feel-bad da click), e niente evento; l'uso riuscito pubblica
  `OggettoUsato` col dettaglio già composto;
- l'ANTIDOTO purga i soli DANNOSI **applicati** — mai gli innati (quelli sono
  capacità dell'entità, non afflizioni) — e narra la fine con lo stesso
  `StatusSvanito` della scadenza naturale;
- il canale dell'inventario, mai un menu di scena: un'opzione per pozione
  affollerebbe la scena — l'host chiama la porta (`sessione.usa(fonte)`),
  come per indossa/togli.
"""

from __future__ import annotations

from dataclasses import dataclass

import esper

from contracts import EffettoConsumabile, PlayerUsaOggetto

from .intenti_coda import consuma_messaggi
from .phased import SistemaSoloNarrazione


@dataclass(frozen=True)
class Consumabile:
    """Un consumabile VIVO del canale loot (il gemello di Arma/PezzoArmatura:
    la forma che `oggetto_da_asset` produce per tipo "consumabile"). Non è
    indossabile per costruzione: `equipaggia()` non lo riconosce e rifiuta."""

    fonte: str
    nome: str
    effetto: str                 # EffettoConsumabile.value
    grado: str = "bronzo"
    descrizione: str = ""
    insegna_mossa: str = ""      # solo effetto TOMO (nodo S, canale GearTome)


# --- Il dato DEMO del canale (contenuto originale, pattern CATALOGO_OGGETTI) ---
# Tre pezzi, uno per effetto: entrano nel catalogo della run e quindi nel
# giro dei drop dal pool — il canale è vivo in partita senza aspettare
# l'authoring. Il contenuto vero li affiancherà come asset.
CATALOGO_CONSUMABILI: dict[str, Consumabile] = {
    "tonico-di-latta": Consumabile(
        fonte="tonico-di-latta", nome="Tonico di Latta",
        effetto=EffettoConsumabile.CURA.value, grado="bronzo",
        descrizione="Sa di ruggine e di promesse. Funziona, che è più di "
                    "quanto si possa dire del resto del piano.",
    ),
    "fiala-di-china": Consumabile(
        fonte="fiala-di-china", nome="Fiala di China",
        effetto=EffettoConsumabile.RISTORO_MANA.value, grado="bronzo",
        descrizione="Amara al punto giusto: la mente torna in fila per non "
                    "berne un altro sorso.",
    ),
    "controveleno-da-banco": Consumabile(
        fonte="controveleno-da-banco", nome="Controveleno da Banco",
        effetto=EffettoConsumabile.ANTIDOTO.value, grado="argento",
        descrizione="L'etichetta elenca dodici veleni che non esistono più "
                    "e ne dimentica tre che esistono ancora. Media bene.",
    ),
    "quaderno-del-morso": Consumabile(
        fonte="quaderno-del-morso", nome="Quaderno del Morso",
        effetto=EffettoConsumabile.TOMO.value, grado="argento",
        insegna_mossa="morso_velenoso",
        descrizione="Appunti di qualcuno che ha studiato i morsi da vicino. "
                    "Troppo da vicino: le ultime pagine sono scritte con "
                    "l'altra mano.",
    ),
}


# --- Gli esecutori: UN effetto = UNA riga (pattern SPEC_STATUS) -----------------

def _cura(entita: int, oggetto: "Consumabile", bus) -> tuple[bool, str]:
    from .calibrazione import CONSUMABILE_CURA_PCT
    from .derivate import max_hp
    from .salute import muovi_hp
    from .scheda import Scheda

    grado = oggetto.grado
    scheda = esper.component_for_entity(entita, Scheda)
    massimo = max_hp(entita)
    prima = scheda.punti_vita
    if prima >= massimo:
        return False, "sei già intero"
    quota = max(1, round(massimo * float(CONSUMABILE_CURA_PCT.get(grado, 0.0))))
    # L'unica scrittura degli HP è `muovi_hp` (un solo proprietario): la cura
    # è clampata al massimo lì, non qui.
    dopo = muovi_hp(entita, quota)
    return True, f"+{(dopo or prima) - prima} HP"


def _ristoro_mana(entita: int, oggetto: "Consumabile", bus) -> tuple[bool, str]:
    from .calibrazione import CONSUMABILE_MANA_PCT
    from .derivate import max_mana
    from .scheda import assicura_mana

    grado = oggetto.grado
    mana = assicura_mana(entita)
    massimo = max_mana(entita)
    if mana.attuale >= massimo:
        return False, "la mente è già piena"
    quota = max(1, round(massimo * float(CONSUMABILE_MANA_PCT.get(grado, 0.0))))
    nuovo = min(massimo, mana.attuale + quota)
    guadagno = nuovo - mana.attuale
    mana.attuale = nuovo
    return True, f"+{guadagno} mana"


def _tomo(entita: int, oggetto: "Consumabile", bus) -> tuple[bool, str]:
    """Il TOMO insegna una mossa (canale GearTome, nodo S): la chiave entra
    nel `Repertorio` PERSISTENTE — permanente, save-safe. Il gate: la mossa
    deve esistere nel catalogo della run, e chi la conosce già (innata o
    concessa dal gear) non consuma il tomo — niente feel-bad da click."""
    from .combattimento import MOSSE_DEFAULT, mosse_di
    from .mob import Repertorio
    from .mosse import mossa_di

    chiave = oggetto.insegna_mossa
    if not chiave or mossa_di(chiave) is None:
        return False, "il tomo è illeggibile: la tecnica non esiste quaggiù"
    if chiave in mosse_di(entita):
        return False, "la conosci già: il tomo resta chiuso"
    rep = esper.try_component(entita, Repertorio)
    base = tuple(rep.mosse) if rep is not None and rep.mosse else MOSSE_DEFAULT
    nuovo = Repertorio(mosse=tuple(base) + (chiave,))
    esper.add_component(entita, nuovo)  # sostituisce il componente (esper)
    return True, f"appresa: {chiave.replace('_', ' ')}"


def _antidoto(entita: int, oggetto: "Consumabile", bus) -> tuple[bool, str]:
    """Purga i DANNOSI applicati (mai gli innati: sono capacità, non
    afflizioni). La fine si narra con lo stesso evento della scadenza."""
    from contracts import StatusSvanito

    from .status import SPEC_STATUS, Valenza, nome_status

    purgati: list[str] = []
    for spec in SPEC_STATUS:
        if spec.valenza is not Valenza.DANNOSO:
            continue
        comp = esper.try_component(entita, spec.componente)
        if comp is None or getattr(comp, "innato", False):
            continue
        esper.remove_component(entita, spec.componente)
        nome = nome_status(spec.componente)
        purgati.append(nome)
        if bus is not None:
            bus.pubblica(StatusSvanito(bersaglio="", status=nome))
    if not purgati:
        return False, "niente da purgare"
    return True, f"{', '.join(purgati)}: svanito" if len(purgati) == 1 \
        else f"{', '.join(purgati)}: svaniti"


_IMPLEMENTAZIONI = {
    EffettoConsumabile.CURA.value: _cura,
    EffettoConsumabile.RISTORO_MANA.value: _ristoro_mana,
    EffettoConsumabile.ANTIDOTO.value: _antidoto,
    EffettoConsumabile.TOMO.value: _tomo,
}
# Completezza per costruzione: un membro nuovo dell'enum senza esecutore è un
# KeyError QUI, all'import — mai un effetto che valida e poi non fa nulla.
_ESECUTORI = {e.value: _IMPLEMENTAZIONI[e.value] for e in EffettoConsumabile}


def usa_consumabile(entita: int, fonte: str, bus=None) -> tuple[bool, str]:
    """USA un consumabile posseduto: (successo, dettaglio).

    Gate in ordine: possesso (Zaino), il pezzo è un consumabile, l'effetto ha
    qualcosa da fare. Solo a successo: la fonte esce dallo zaino (monouso) e
    `OggettoUsato` va in cronaca. Il rifiuto non consuma e non è un fatto."""
    from contracts import OggettoUsato

    from .equip import Zaino
    from .oggetti import catalogo_oggetti_correnti

    zaino = esper.try_component(entita, Zaino)
    if zaino is None or fonte not in zaino.fonti:
        return False, "non lo possiedi"
    oggetto = catalogo_oggetti_correnti().get(fonte)
    if not isinstance(oggetto, Consumabile):
        return False, "non si beve e non si lancia: non è un consumabile"
    esegui = _ESECUTORI.get(oggetto.effetto)
    if esegui is None:
        return False, "effetto sconosciuto: il pezzo resta chiuso"
    successo, dettaglio = esegui(entita, oggetto, bus)
    if not successo:
        return False, dettaglio
    zaino.fonti.remove(fonte)
    if bus is not None:
        bus.pubblica(OggettoUsato(
            nome=oggetto.nome, fonte=fonte,
            effetto=oggetto.effetto, dettaglio=dettaglio,
        ))
    return True, dettaglio


# --- Il sistema: consuma gli intenti, SOLO in narrazione (phase-gate) ----------

class SistemaConsumabili(SistemaSoloNarrazione):
    """Serve `PlayerUsaOggetto` dalla coda intenti — specchio di `SistemaEquip`:
    vive nel bucket solo-narrazione, in combattimento l'intento resta in coda.
    Un intento non onorabile (fonte ignota, effetto senza presa) è consumato
    senza effetto: la disciplina è quella dell'equip."""

    def __init__(self, bus=None) -> None:
        self.bus = bus

    def run(self, dt: int) -> None:
        from .scheda import Protagonista

        for intento in consuma_messaggi(PlayerUsaOggetto):
            for ent, _ in esper.get_component(Protagonista):
                usa_consumabile(ent, intento.fonte, self.bus)
