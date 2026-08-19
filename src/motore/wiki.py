"""Wiki del Master — il CONSUMO run-side della slice (W1).

Il motore non conosce il master né lo store: riceve la `WikiSlice`
congelata al freeze (specchi-dataclass, come StagioneAttiva) e la serve al
turno GM su due corsie DETERMINISTICHE (contratto in `contracts/wiki.py`):

- corsia di MOTORE: inneschi = fatti di scena (zona, tipo di stanza,
  entità in scena) — mai substring di chat;
- corsia LESSICALE: l'azione dichiarata del giocatore (la stessa query di
  `memoria_lunga`), con normalizzazione dei diacritici.

Le voci COSTANTI non passano di qui: entrano nel prefisso al freeze
(`costanti_prefisso`) — byte-identiche per piano, il regime di cache regge.

Il verso di RITORNO (run→master) è la coda `PropostePendenti` + l'outbox
su file (persistenza/outbox.py): id deterministici, taint di regia
ereditato (rev. 3 §4-bis). Il permadeath NON la tocca.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Token ≥3 caratteri, come la memoria narrativa; la normalizzazione dei
# diacritici (E1, ridotto) rende «città»/«citta» lo stesso token.
_RE_TOKEN = re.compile(r"[a-z0-9]{3,}")

# Le STOPWORD italiane di 3+ caratteri (playtest 2026-08-18, F-W2): «del»
# passa il filtro di lunghezza e «L'Archivista DEL Sesto» matchava «Fante
# DEL Fronte Fermo» — il canone scattava su OGNI azione in qualunque stanza
# con un nome composto. Articoli/preposizioni/congiunzioni pure: mai parole
# di contenuto (un innesco legittimo non deve sparire).
_STOPWORD = frozenset((
    "del della dello delle degli dei con per tra fra che nel nella nelle "
    "negli nei sul sulla sulle sugli sui dal dalla dalle dagli dai una uno "
    "gli allo alla alle agli anche come dove quando mentre presso oppure "
    "ovvero cioe essa esso essi esse loro"
).split())

_ETICHETTA_REGIA = {
    "velato": (" (VELATO: il GM lo sa e può lasciarlo trasparire — MAI "
               "citarlo o confermarlo testualmente)"),
    "solo_contesto": (" (SOLO CONTESTO: informa la tua composizione — mai "
                      "nominarlo nella prosa)"),
}


def _normalizza(testo: str) -> frozenset[str]:
    piatto = unicodedata.normalize("NFKD", testo.lower())
    piatto = "".join(c for c in piatto if not unicodedata.combining(c))
    return frozenset(_RE_TOKEN.findall(piatto)) - _STOPWORD


# --- Gli specchi-dataclass (il translator del save parla dataclass) ------------

@dataclass
class VoceSliceAttiva:
    slug: str
    tipo: str
    testo: str
    regia: str
    costante: bool = False
    inneschi: list[str] = field(default_factory=list)
    piano_da: int = 1
    piano_a: int | None = None
    zona: str = ""


@dataclass
class WikiSliceAttiva:
    """La slice montata nel World. NON è nel registry dei componenti
    persistenti: vive nel TERZO artefatto del save (`<uuid>.wiki.gz`,
    contratto VITALE — rev. 3 §3.1), mai nello stato in chiaro (sarebbe un
    canale-spoiler) né nel sidecar lasco (svanirebbe in silenzio)."""

    versione: int = 1
    voci: list[VoceSliceAttiva] = field(default_factory=list)


@dataclass
class MarcatoreWiki:
    """Il marcatore NEL SAVE (stato, minuscolo): dichiara che questa run è
    nata con una slice. Al load: marcatore presente + artefatto illeggibile
    o assente = RIFIUTO dichiarato — mai la sostituzione silenziosa del
    mondo. Assente = run senza wiki (legacy incluso), tutto come prima."""

    versione: int = 1


@dataclass
class PropostePendenti:
    """La coda in-World delle proposte non ancora drenate nell'outbox +
    il taint di regia (la più restrittiva SERVITA in run): una proposta
    nata dopo una voce `velato` non nasce mai `citabile` (§4-bis).
    Persistente: un save prima del drenaggio non perde nulla."""

    voci: list[dict] = field(default_factory=list)
    regia_massima_vista: str = "citabile"


# --- Montaggio e lettura --------------------------------------------------------

def monta_slice(slice_attiva: WikiSliceAttiva) -> int:
    """Monta la slice nel World (singleton) col suo marcatore. Chiamata dal
    composition root al freeze e al load — mai dal motore in corsa.
    Idempotente sui singleton: al load il marcatore arriva già dal save
    (round-trip del registry) e non deve duplicarsi."""
    import esper

    for tipo in (WikiSliceAttiva, MarcatoreWiki):
        for ent, _ in list(esper.get_component(tipo)):
            esper.delete_entity(ent, immediate=True)
    esper.create_entity(MarcatoreWiki(versione=slice_attiva.versione))
    return esper.create_entity(slice_attiva)


def slice_a_dict(slice_attiva: WikiSliceAttiva) -> dict:
    """Specchio-dataclass → JSON del terzo artefatto (per la riscrittura al
    salvataggio: la slice è immutabile per la run, la scrittura è idempotente)."""
    from dataclasses import asdict

    return asdict(slice_attiva)


def slice_da_dict(dati: dict) -> WikiSliceAttiva:
    """Il terzo artefatto (JSON) → specchio-dataclass, al load."""
    return WikiSliceAttiva(
        versione=int(dati.get("versione", 1)),
        voci=[VoceSliceAttiva(
            slug=v["slug"], tipo=v.get("tipo", "ambientazione"),
            testo=v.get("testo", ""), regia=v.get("regia", "citabile"),
            costante=bool(v.get("costante", False)),
            inneschi=list(v.get("inneschi", [])),
            piano_da=int(v.get("piano_da", 1)), piano_a=v.get("piano_a"),
            zona=v.get("zona", ""),
        ) for v in dati.get("voci", [])],
    )


def slice_corrente() -> WikiSliceAttiva | None:
    import esper

    trovate = esper.get_component(WikiSliceAttiva)
    return trovate[0][1] if trovate else None


def slice_da_contratto(slice_dto) -> WikiSliceAttiva:
    """WikiSlice (contracts) → specchio-dataclass (il pattern MobAsset→MobAttivo)."""
    return WikiSliceAttiva(
        versione=slice_dto.versione,
        voci=[VoceSliceAttiva(
            slug=v.slug, tipo=v.tipo.value, testo=v.testo, regia=v.regia.value,
            costante=v.costante, inneschi=list(v.inneschi),
            piano_da=v.piano_da, piano_a=v.piano_a, zona=v.zona,
        ) for v in slice_dto.voci],
    )


# --- Il retrieval (le due corsie deterministiche) -------------------------------

def _in_scope(voce: VoceSliceAttiva, piano: int, zona_tier: str) -> bool:
    if piano < voce.piano_da:
        return False
    if voce.piano_a is not None and piano > voce.piano_a:
        return False
    return voce.zona == "" or voce.zona == zona_tier


def _contesto_corrente() -> tuple[int, str, list[str]]:
    """I fatti di scena per gli inneschi di MOTORE: piano, tier di zona,
    nomi delle entità in scena (mob corrente, PNG in stanza) + tipo stanza."""
    from .mappa import nome_mob_corrente, tipo_stanza_corrente
    from .piano import livello_corrente
    from .png import dettagli_png_in_stanza
    from .territorio import zona_corrente

    piano = livello_corrente()
    zona = zona_corrente()
    tier = zona.tier.value if zona is not None else ""
    entita = []
    nome = nome_mob_corrente()
    if nome:
        entita.append(nome)
    png = dettagli_png_in_stanza()
    if png is not None:
        entita.append(png.nome)
    tipo = tipo_stanza_corrente()
    entita.append(tipo.value)
    return piano, tier, entita


def recupera_wiki(azione: str, *, limite: int = 2) -> list[VoceSliceAttiva]:
    """Le voci più rilevanti per il turno: corsia di motore (entità/stanza
    in scena) pesata FORTE + corsia lessicale (azione). Deterministico:
    spareggio totale (punteggio DESC, slug ASC). Aggiorna il taint."""
    corrente = slice_corrente()
    if corrente is None or limite <= 0:
        return []
    piano, tier, entita = _contesto_corrente()
    query_azione = _normalizza(azione)
    query_scena = _normalizza(" ".join(entita))
    candidate: list[tuple[int, str, VoceSliceAttiva]] = []
    for voce in corrente.voci:
        if voce.costante or not _in_scope(voce, piano, tier):
            continue
        chiavi = _normalizza(" ".join(voce.inneschi))
        corpo = _normalizza(voce.testo)
        punteggio = (
            3 * len(chiavi & query_scena)      # innesco di motore: il fatto in scena
            + 2 * len(chiavi & query_azione)   # innesco lessicale dichiarato
            + len(corpo & query_azione)        # eco nel corpo della voce
        )
        if punteggio > 0:
            candidate.append((punteggio, voce.slug, voce))
    candidate.sort(key=lambda t: (-t[0], t[1]))
    scelte = [voce for _p, _s, voce in candidate[:limite]]
    _aggiorna_taint(scelte)
    return scelte


def righe_wiki(azione: str, *, limite: int = 2) -> list[str]:
    """Le righe `[fascicolo/wiki]` pronte per il prompt, con la regia resa
    come istruzione (dichiaratamente non garantita — rev. 3 §5)."""
    righe = []
    for voce in recupera_wiki(azione, limite=limite):
        righe.append(
            f"[fascicolo/wiki] {voce.slug}: {voce.testo[:300]}"
            + _ETICHETTA_REGIA.get(voce.regia, "")
        )
    return righe


def costanti_prefisso() -> str:
    """Le voci COSTANTI in scope per il piano corrente, come blocco di
    prefisso ("" se niente): ordine per slug — byte-identico per piano, la
    cache del prefisso regge (verificato dal panel rev. 2)."""
    corrente = slice_corrente()
    if corrente is None:
        return ""
    from .piano import livello_corrente

    piano = livello_corrente()
    righe = [
        f"[wiki] {v.testo[:300]}" + _ETICHETTA_REGIA.get(v.regia, "")
        for v in sorted(corrente.voci, key=lambda v: v.slug)
        if v.costante and _in_scope(v, piano, "")
    ]
    _aggiorna_taint([v for v in corrente.voci if v.costante])
    return ("\n" + "\n".join(righe)) if righe else ""


# --- Il verso di ritorno: la coda delle proposte (rev. 3 §4-bis) ---------------

def _proposte_pendenti() -> PropostePendenti:
    import esper

    trovate = esper.get_component(PropostePendenti)
    if trovate:
        return trovate[0][1]
    coda = PropostePendenti()
    esper.create_entity(coda)
    return coda


def _aggiorna_taint(voci: list[VoceSliceAttiva]) -> None:
    if not voci:
        return
    ordine = {"citabile": 0, "velato": 1, "solo_contesto": 2}
    coda = _proposte_pendenti()
    massimo = max([coda.regia_massima_vista] + [v.regia for v in voci],
                  key=lambda r: ordine.get(r, 0))
    coda.regia_massima_vista = massimo


def accoda_proposta(*, tipo: str, titolo: str, testo: str, fatto: str) -> None:
    """UNA proposta dal motore, derivata DAI FATTI (mai dalla prosa). L'id è
    DETERMINISTICO (seed + firma del fatto): la raccolta ripetuta e il
    save-scumming deduplicano per costruzione. Il taint è quello corrente."""
    from .seme import master_seed

    coda = _proposte_pendenti()
    id_proposta = f"{master_seed()}:{fatto}"
    if any(v.get("id") == id_proposta for v in coda.voci):
        return
    coda.voci.append({
        "id": id_proposta, "tipo": tipo, "titolo": titolo,
        "testo": testo[:400], "taint": coda.regia_massima_vista,
    })


def drena_proposte() -> list[dict]:
    """Svuota la coda e ritorna le proposte (per l'outbox su file). Il
    chiamante è la sessione, ai confini che già esistono: salvataggio e
    terminale — PRIMA di `invalida` (il buco del panel, chiuso)."""
    coda = _proposte_pendenti()
    voci, coda.voci = list(coda.voci), []
    return voci


def riaccoda_proposte(voci: list[dict]) -> None:
    """Il drenaggio è BEST-EFFORT (avversariale 2026-08-18, F-W4): se
    l'outbox su file è inscrivibile (lock, antivirus, sabotaggio), le
    proposte TORNANO in coda — persistente nel save — e si riconsegnano al
    prossimo confine. Mai perdere, mai rompere il salvataggio."""
    coda = _proposte_pendenti()
    presenti = {v.get("id") for v in coda.voci}
    coda.voci.extend(v for v in voci if v.get("id") not in presenti)
