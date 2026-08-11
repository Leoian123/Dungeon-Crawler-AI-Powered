"""Equipaggiamento: il **manifest durevole** delle sorgenti, gli effetti restano derivati.

ADR-1 (F1). L'idea portante, da non perdere in un refactor: l'equip **non ha una
meccanica propria**. Un pezzo indossato è un fascio di `Modificatore` (e, da F2, di
`ResistenzaMod`) spinti nei canali che esistono già, etichettati con la `fonte` durevole
dell'oggetto. Il fold `stat_eff` li somma da solo, il risolutore non sa che esistono:
**zero righe nel loop di combattimento**. È il test a dimostrarlo, non questa frase.

Perché il componente porta *solo* le sorgenti (D1). Persistere sia gli slot sia le voci
da essi derivate crea due copie che divergono senza un punto di riconciliazione. Qui la
sorgente di verità è una sola — `ComponenteEquip` — e `Modificatori` è **derivato**:
togliere un pezzo è `rimuovi_per_fonte`, mai un `÷ 1.2` che "disfa" il bonus (Gr2 §4.1).

⚠️ **NON persistente, per scelta dichiarata.** Registrare `ComponenteEquip` nel registry
dei tag *senza* l'hook di re-equip (ADR-1 F5, fuori dal perimetro di questa fase)
produrrebbe il desync peggiore possibile: il manifest round-trippa, i suoi modificatori
no → al load l'equip **esiste ma non fa niente**, e nessun test se ne accorge. Meglio un
buco dichiarato e lucchettato (`test_equip_f1.py`) che un save che mente. Quando arriva
F5 si registra il tag *insieme* all'hook, mai prima.

Fase: si equipaggia **solo in NARRAZIONE** e gratis (D3). Non è un `if fase ==` nel
sistema — è `SistemaSoloNarrazione`, cioè il phase-gate **strutturale**: in combattimento
il sistema non gira affatto e gli intenti restano in coda.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import esper

from contracts import (
    SLOT_ARMATURA,
    CategoriaArmatura,
    PlayerEquipaggia,
    PlayerToglie,
    SedeAccessorio,
    SlotEquip,
    StatId,
    Taglia,
)

from .calibrazione import MITIGAZIONE_CENT
from .intenti_coda import consuma_messaggi
from .mosse import registra_fonte_mosse
from .modificatori import (
    Modificatore,
    Modificatori,
    ResistenzaMod,
    Resistenze,
    TipoMod,
    applica_modificatore,
    applica_resistenza,
    rimuovi_per_fonte,
    rimuovi_resistenza_per_fonte,
)
from .phased import SistemaSoloNarrazione

# `clampa_hp` si importa **dentro** le funzioni che lo usano, non qui: `derivate` legge
# il `ComponenteEquip` per la media pesata di `coeff_eva` (F3 dell'ADR), quindi un import
# a livello di modulo in questa direzione chiuderebbe il ciclo `derivate ↔ equip`. Il
# *dato* (i componenti) sta sotto, il *ciclo di vita* (che tocca gli HP) sta sopra.


# --- Gli oggetti: dato puro, nessun comportamento ------------------------------

@dataclass(frozen=True)
class PezzoArmatura:
    """Un pezzo indossabile in uno degli slot-armatura.

    `categoria` è la leva **spaccata sui due check**: abbassa `coeff_eva` (schivi meno,
    check 1) e, tramite `mitigazione_cent`, alza `DIFESA` (incassi meno, check 2). Due
    effetti opposti dallo stesso pezzo, ciascuno sul proprio check — è ciò che rende il
    trade-off tank/dodger una scelta e non un numero da massimizzare.

    `mitigazione_cent` è **derivata dalla categoria** quando vale `None` (il caso normale):
    chi scrive contenuto sceglie un *nome* — "pesante" — e il numero lo mette il motore
    (`MITIGAZIONE_CENT`, §11). È lo stesso principio per cui l'AI non emette numeri, esteso
    alla porta di authoring. Un intero esplicito resta possibile per l'oggetto unico, ed è
    l'unico posto dove un autore scrive una magnitudine: finché non c'è il tetto di F8,
    è anche l'unico punto scoperto.

    In **centesimi** perché `DIFESA` lo è (contratto di scala §6): metterci unità
    significherebbe un'armatura 100 volte più forte del previsto.

    `swappable` = costo in AP per cambiarlo mid-combat. **Campo dormiente in MVP** (D3):
    definito e popolato, nessun consumatore — in NARRAZIONE lo swap è gratis a
    prescindere. Esiste ora perché il giorno dello swap mid-combat il dato è già lì e la
    regola è per-item, non un ramo di fase.
    """

    fonte: str
    slot: SlotEquip
    categoria: CategoriaArmatura
    nome: str = ""
    taglia: Taglia = Taglia.MEDIA
    mitigazione_cent: int | None = None      # None = derivata dalla categoria (§11)
    modificatori: tuple[Modificatore, ...] = ()
    resistenze: tuple[ResistenzaMod, ...] = ()
    swappable: int = 0


@dataclass(frozen=True)
class Arma:
    """Ciò che si impugna nel mount `ARMA`. Mount vuoto = **armi naturali** (pugni,
    artigli), che non è un caso speciale ma la voce `naturale` di `COEFF_ACC`.

    Niente enum "tipo arma": `coeff_acc` è **size-based**, si ricava dalla *relazione*
    fra la taglia dell'arma e quella del portatore (ADR-1 D7). Un'arma piccola alza il
    *colpire*, non il danno — precisa ≠ forte.
    """

    fonte: str
    taglia: Taglia
    nome: str = ""
    danno_base: int = 0
    modificatori: tuple[Modificatore, ...] = ()
    resistenze: tuple[ResistenzaMod, ...] = ()
    swappable: int = 0


@dataclass(frozen=True)
class Accessorio:
    """Anelli, orecchini, ciondoli: **multiset aperto**, nessun cap, modifiers-only (D6).

    Fuori dalla media di `m_armatura` per costruzione: non stanno in uno slot-armatura.

    ⚠️ `fonte` deve essere un id di **istanza**, non di tipo: cinque anelli identici con
    la stessa `fonte` verrebbero rimossi tutti insieme dal primo `rimuovi_per_fonte`.
    """

    fonte: str
    sede: SedeAccessorio
    nome: str = ""
    modificatori: tuple[Modificatore, ...] = ()
    resistenze: tuple[ResistenzaMod, ...] = ()
    swappable: int = 0
    # Mosse CONCESSE dall'oggetto (chiavi del catalogo chiuso, mai comportamento). È il
    # canale che rende possibile «un oggetto che gioca d'azzardo nel suo component»
    # (Gr2 §5.2): l'oggetto non porta la casualità, porta la *mossa* che la dichiara —
    # e il consenso resta della voce di catalogo. Sfilando l'oggetto, la mossa se ne va.
    mosse: tuple[str, ...] = ()


@dataclass
class ComponenteEquip:
    """Il manifest durevole: *cosa* porta l'entità. Gli **effetti** vivono altrove
    (`Modificatori`/`Resistenze`) e sono derivati da qui (D1).

    `armatura` è una mappa slot → pezzo **esclusiva** (0-o-1 per slot); `accessori` è
    aperta. Uno slot assente = vuoto, che non è la stessa cosa di "nudo con penalità":
    per la media pesata di `coeff_eva` uno slot vuoto vale `VESTE` (F5).
    """

    armatura: dict[SlotEquip, PezzoArmatura] = field(default_factory=dict)
    arma: Arma | None = None
    accessori: list[Accessorio] = field(default_factory=list)

    def pezzo_per_fonte(self, fonte: str):
        """L'oggetto equipaggiato con quella `fonte`, o `None`. Unico punto di ricerca:
        i tre contenitori sono un dettaglio interno, non qualcosa su cui i chiamanti
        debbano ramificare."""
        for pezzo in self.armatura.values():
            if pezzo.fonte == fonte:
                return pezzo
        if self.arma is not None and self.arma.fonte == fonte:
            return self.arma
        for acc in self.accessori:
            if acc.fonte == fonte:
                return acc
        return None

    def fonti(self) -> tuple[str, ...]:
        return tuple(
            o.fonte for o in (
                *self.armatura.values(),
                *( (self.arma,) if self.arma is not None else () ),
                *self.accessori,
            )
        )


@dataclass
class Zaino:
    """L'inventario POSSEDUTO: fonti di dominio durevoli, mai oggetti vivi.

    Il possesso resta qui anche quando l'oggetto è INDOSSO (il manifest è
    l'indosso, non la proprietà). È il deposito del canale del loot: il drop
    scrive QUI, l'equip legge."""

    fonti: list[str] = field(default_factory=list)


@dataclass
class Guardaroba:
    """La VESTIZIONE dei premi (contratto premi, D-2): i nomi generati dei
    cimeli, keyed per fonte, e i ribattezzi delle mosse concesse. Solo PAROLE
    (il nome del cimelio È il gioco): la meccanica resta del catalogo — e
    viaggia nel save (il cimelio non torna anonimo al load)."""

    vesti: dict[str, tuple[str, str]] = field(default_factory=dict)   # fonte → (nome, descrizione)
    mosse_vesti: dict[str, str] = field(default_factory=dict)         # chiave mossa → nome


def assicura_guardaroba(entita: int) -> Guardaroba:
    comp = esper.try_component(entita, Guardaroba)
    if comp is None:
        comp = Guardaroba()
        esper.add_component(entita, comp)
    return comp


def guardaroba_attivo(entita: int) -> Guardaroba | None:
    return esper.try_component(entita, Guardaroba)


def assicura_zaino(entita: int) -> Zaino:
    """Lo `Zaino` dell'entità, montandolo vuoto se assente (save scritti prima
    che l'inventario esistesse: migrazione lazy, nessun cambio di formato)."""
    comp = esper.try_component(entita, Zaino)
    if comp is None:
        comp = Zaino()
        esper.add_component(entita, comp)
    return comp


def fonti_zaino(entita: int) -> tuple[str, ...]:
    """Lettura pura del posseduto (per proiezioni/host): assente → vuoto."""
    comp = esper.try_component(entita, Zaino)
    return tuple(comp.fonti) if comp is not None else ()


def equip_attivo(entita: int) -> ComponenteEquip | None:
    """Il manifest **se esiste**, senza crearlo — lettura pura, per chi proietta.

    Gemella di `equip_di` ma non-mutante: la proiezione della scheda non deve attaccare
    un componente all'entità solo per guardarla. Esiste anche perché il port non importa
    `esper` (il motore è pilotabile solo via porte, C-2b)."""
    return esper.try_component(entita, ComponenteEquip)


def equip_di(entita: int) -> ComponenteEquip:
    """Il manifest dell'entità, creandolo se assente. Un solo punto di accesso: chi
    scrive equip non deve mai decidere se il componente esista."""
    comp = esper.try_component(entita, ComponenteEquip)
    if comp is None:
        comp = ComponenteEquip()
        esper.add_component(entita, comp)
    return comp


# --- Ciclo di vita: spingi i modificatori, oppure toglili per fonte -------------

def _tocca_costituzione(oggetto) -> bool:
    return any(m.stat is StatId.COSTITUZIONE for m in oggetto.modificatori)


def mitigazione_di(pezzo: PezzoArmatura) -> int:
    """La mitigazione in centesimi del pezzo: esplicita se dichiarata, altrimenti
    **derivata dalla categoria** (§11). Unico punto di verità — chi legge la difesa di
    un pezzo non deve sapere se l'autore ha scritto un numero o scelto un nome."""
    if pezzo.mitigazione_cent is not None:
        return pezzo.mitigazione_cent
    return MITIGAZIONE_CENT[pezzo.categoria.value]


def mosse_da_equip(entita: int) -> tuple[str, ...]:
    """Le mosse CONCESSE da ciò che è INDOSSO — **derivate dal manifest a ogni
    lettura**, mai scritte nel `Repertorio`.

    Il `Repertorio` è PERSISTENTE: scriverci le concessioni lo inquinava — dopo
    un save/load con l'oggetto indosso la mossa concessa round-trippava nel
    repertorio mentre la provenienza (nel manifest, che di proposito non si
    salva) andava perduta: la mossa dell'anello diventava innata per sempre
    (giro 2026-08-07). Derivare alla lettura chiude PER COSTRUZIONE i tre casi
    che la scrittura doveva gestire a mano: la mossa innata non si tocca, due
    oggetti con la stessa mossa non si rubano la revoca, e il load torna pulito
    («da riequipaggiare») senza residui. Stessa dottrina D1 dei modificatori:
    il manifest è la sorgente, gli effetti si derivano."""
    comp = esper.try_component(entita, ComponenteEquip)
    if comp is None:
        return ()
    viste: set[str] = set()
    out: list[str] = []
    indossati = (
        *comp.armatura.values(),
        *((comp.arma,) if comp.arma is not None else ()),
        *comp.accessori,
    )
    for oggetto in indossati:
        for chiave in getattr(oggetto, "mosse", ()):
            if chiave not in viste:
                viste.add(chiave)
                out.append(chiave)
    return tuple(out)


# L'equip si INNESTA nel seam del catalogo mosse: il risolutore legge fonti
# anonime, la freccia di dipendenza resta equip → mosse (mai il contrario).
registra_fonte_mosse(mosse_da_equip)


def _immetti(entita: int, oggetto) -> None:
    """Spinge nei canali esistenti le voci che l'oggetto concede, con la sua `fonte`.

    Tre canali, **tutti già esistenti**, nessuno inventato per l'equip: `Modificatori`
    (il fold), `Resistenze` (il layer tipi), e — per l'armatura — un `Modificatore` su
    `DIFESA` derivato dalla categoria. Anche la mitigazione è una voce come le altre:
    così `rimuovi_per_fonte` la toglie insieme al resto, senza un secondo percorso di
    smontaggio che potrebbe dimenticarsene."""
    for mod in oggetto.modificatori:
        applica_modificatore(entita, mod)
    for res in oggetto.resistenze:
        applica_resistenza(entita, res)
    # Le MOSSE non si immettono: sono derivate alla lettura (`mosse_da_equip`) —
    # scriverle nel Repertorio persistente le rendeva innate dopo un save/load.
    if isinstance(oggetto, PezzoArmatura):
        cent = mitigazione_di(oggetto)
        if cent:
            applica_modificatore(entita, Modificatore(
                stat=StatId.DIFESA, tipo=TipoMod.FLAT, valore=cent, fonte=oggetto.fonte,
            ))


def filtrato_per_save(comp, manifest: ComponenteEquip):
    """La copia di `Modificatori`/`Resistenze` SENZA le voci derivate dall'equip
    (ADR-1 F5, D1): nel save viaggia la SORGENTE durevole (il manifest), mai le
    voci derivate — al load `re_equipaggia` le ri-immette. Filtro e hook sono
    una coppia: filtrare senza hook = equip morto al load; hookare senza filtro
    = voci doppie. Qualunque altro componente passa invariato."""
    fonti = set(manifest.fonti())
    if isinstance(comp, Modificatori):
        return Modificatori(voci=[v for v in comp.voci if v.fonte not in fonti])
    if isinstance(comp, Resistenze):
        return Resistenze(voci=[v for v in comp.voci if v.fonte not in fonti])
    return comp


def re_equipaggia(entita: int) -> None:
    """L'hook post-load (ADR-1 F5): ri-deriva dal manifest appena deserializzato
    le voci di `Modificatori`/`Resistenze` che il save ha filtrato, poi clampa
    gli HP (D2: un −COSTITUZIONE indossato abbassa il tetto anche dopo un load).
    NON idempotente: si chiama solo da `applica_stato`, su canali già filtrati."""
    comp = esper.try_component(entita, ComponenteEquip)
    if comp is None:
        return
    for oggetto in (
        *comp.armatura.values(),
        *((comp.arma,) if comp.arma is not None else ()),
        *comp.accessori,
    ):
        _immetti(entita, oggetto)
    from .derivate import clampa_hp
    clampa_hp(entita)


def equipaggia(entita: int, oggetto) -> bool:
    """Indossa/impugna un oggetto. Ritorna `False` se non c'era posto o era già indosso.

    Lo slot-armatura è **esclusivo**: equipaggiare su uno slot occupato *sostituisce*,
    togliendo prima il pezzo precedente — così non restano modificatori orfani di un
    oggetto che il giocatore non porta più.
    """
    comp = equip_di(entita)
    if comp.pezzo_per_fonte(oggetto.fonte) is not None:
        return False                                   # già equipaggiato: no-op

    if isinstance(oggetto, PezzoArmatura):
        if oggetto.slot not in SLOT_ARMATURA:
            return False                               # un pezzo d'armatura nel mount arma: rifiutato
        precedente = comp.armatura.get(oggetto.slot)
        if precedente is not None:
            togli(entita, precedente.fonte)
            comp = equip_di(entita)
        comp.armatura[oggetto.slot] = oggetto
    elif isinstance(oggetto, Arma):
        if comp.arma is not None:
            togli(entita, comp.arma.fonte)
            comp = equip_di(entita)
        comp.arma = oggetto
    elif isinstance(oggetto, Accessorio):
        comp.accessori.append(oggetto)
    else:
        return False

    _immetti(entita, oggetto)
    # Un pezzo che dà `+COSTITUZIONE` alza il MASSIMO, non cura il corrente (D2): il
    # clamp serve al caso simmetrico, ma va chiamato comunque — un `−COSTITUZIONE`
    # indossato abbassa il tetto e il corrente deve seguirlo, mai restare sopra.
    if _tocca_costituzione(oggetto):
        from .derivate import clampa_hp
        clampa_hp(entita)
    return True


def togli(entita: int, fonte: str) -> bool:
    """Sfila l'oggetto con quella `fonte`. Ritorna `False` se non era equipaggiato.

    **Rimozione per fonte, mai operazione inversa** (Gr2 §4.1): niente `÷ 1.2`, niente
    base corrotta dai float. La prossima `stat_eff` ricalcola da capo."""
    comp = esper.try_component(entita, ComponenteEquip)
    if comp is None:
        return False
    oggetto = comp.pezzo_per_fonte(fonte)
    if oggetto is None:
        return False

    if isinstance(oggetto, PezzoArmatura):
        comp.armatura.pop(oggetto.slot, None)
    elif isinstance(oggetto, Arma):
        comp.arma = None
    else:
        comp.accessori = [a for a in comp.accessori if a.fonte != fonte]

    rimuovi_per_fonte(entita, fonte)
    rimuovi_resistenza_per_fonte(entita, fonte)
    # Niente revoca di mosse: uscito l'oggetto dal manifest, `mosse_da_equip`
    # smette di derivarle — la rimozione è la stessa lettura.
    # Togliere un `+COSTITUZIONE` ABBASSA il massimo: il corrente va clampato verso il
    # basso (D2). È la perdita di HP che rende il cambio d'armatura una scelta, non un
    # ottimizzatore da riequipaggiare a ogni scontro.
    if _tocca_costituzione(oggetto):
        from .derivate import clampa_hp
        clampa_hp(entita)
    return True


# --- Catalogo dimostrativo: gli oggetti che esistono, in attesa del loot -------
#
# ⚠️ **Provvisorio e dichiarato.** Gli oggetti non hanno ancora un canale-asset come
# archetipi, mob e piani: quello arriva con la pipeline del bottino (ADR-2, rinviata).
# Finché non c'è, questo è il posto dove un oggetto *esiste* — pochi pezzi, scritti per
# dimostrare che i canali funzionano, non per essere il bestiario degli oggetti.
# Quando arriverà il loot, questo dizionario diventa la sua lettura e non un canale in più.

CATALOGO_OGGETTI: dict[str, object] = {
    # L'OGGETTO CHE GIOCA D'AZZARDO (Gr2 §5.2). Non porta la casualità nel proprio
    # component — porta la **mossa** che la dichiara: il consenso resta della voce di
    # catalogo, e l'oggetto è solo il modo di procurarsela. È la lettura letterale della
    # richiesta originale («un oggetto che gioca d'azzardo nel suo component»), col
    # vincolo che l'azzardo non diventi mai il percorso base.
    "dadi-truccati": Accessorio(
        fonte="dadi-truccati",
        sede=SedeAccessorio.DITA,
        nome="Dadi Truccati",
        mosse=("roulette_del_sistema",),
    ),
}


# --- Il sistema: consuma gli intenti, SOLO in narrazione (phase-gate) ----------

class SistemaEquip(SistemaSoloNarrazione):
    """Serve `PlayerEquipaggia`/`PlayerToglie` dalla coda intenti (D3).

    Vive nel bucket **solo-narrazione**: in combattimento non gira, quindi l'intento
    resta in coda invece di essere consumato dalla fase sbagliata. Nessun controllo di
    fase scritto a mano — la regola è la registrazione, non un `if`.

    L'inventario non esiste ancora: gli oggetti che il giocatore *possiede* vanno
    dichiarati in `catalogo_oggetti`, che l'host popola. Quando arriverà l'inventario
    vero questo diventa la sua lettura, non un canale nuovo.
    """

    def __init__(self, catalogo_oggetti: dict[str, object] | None = None) -> None:
        # Un catalogo ESPLICITO è una dichiarazione di possesso del chiamante
        # (harness, host con inventario proprio): nessun gate. Il catalogo
        # di default è «ciò che esiste NELLA RUN» (storico + oggetti-asset
        # congelati nella stagione, risolto a ogni run()): lì il possesso lo
        # decide lo Zaino — e il drop è il suo unico produttore.
        self._richiede_possesso = catalogo_oggetti is None
        self.catalogo_oggetti: dict[str, object] = dict(
            CATALOGO_OGGETTI if catalogo_oggetti is None else catalogo_oggetti
        )

    def run(self, dt: int) -> None:
        from .scheda import Protagonista  # locale: evita il ciclo equip↔scheda

        catalogo = self.catalogo_oggetti
        if self._richiede_possesso:
            from .oggetti import catalogo_oggetti_correnti  # locale: niente ciclo equip↔oggetti

            catalogo = catalogo_oggetti_correnti()
        for intento in consuma_messaggi(PlayerEquipaggia):
            oggetto = catalogo.get(intento.fonte)
            if oggetto is None:
                continue                               # fonte ignota: consumata senza effetto
            for ent, _ in esper.get_component(Protagonista):
                if self._richiede_possesso:
                    zaino = esper.try_component(ent, Zaino)
                    if zaino is None or intento.fonte not in zaino.fonti:
                        continue        # non lo possiedi: consumato senza effetto
                equipaggia(ent, oggetto)
        for intento in consuma_messaggi(PlayerToglie):
            for ent, _ in esper.get_component(Protagonista):
                togli(ent, intento.fonte)
