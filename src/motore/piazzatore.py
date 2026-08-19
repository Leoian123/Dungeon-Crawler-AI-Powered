"""Il PIAZZATORE PNG (P1) — il casting del piano, non il contenuto.

«Un PNG piazzato è una scena promessa»: il piazzatore distribuisce i
personaggi del roster congelato (`PianoAttivo.png`) sugli SLOT che i tipi di
stanza dichiarano — il manager nel bagno (l'unica sala senza occhi addosso:
il posto canonico della proposta), il maestro nelle gilde. La safe room è
RISERVATA (P3: troupe/narratore). Vedi `docs/future/piazzatore-png.md`.

Le linee rosse incassate per costruzione:
- l'interpellabile sta SOLO nei tipi quieti/gilda, dove l'ostile non spawna
  per design (vincolo playtest giro 3: mai un PNG a funzione dietro un
  custode) — la stanza-boss e le stanze normali non hanno slot;
- UN interpellabile per stanza; un personaggio (nome) esiste UNA volta nel
  mondo (il PNG sopravvive al despawn di zona: niente doppioni al rientro);
- zero autorità AI: pescata SEEDED su stream dedicato
  `master_seed:png:{piano}:{zona}` (F-13: lo stream di sessione non si
  muove), stessa zona → stesso casting, per sempre.

Il piazzamento è idempotente (il rientro in zona è un no-op sui vivi) e
degrada senza crash: il gate Elité e la guardia-archetipo di
`materializza_png` rifiutano, il piazzatore salta.
"""

from __future__ import annotations

import random

from contracts import CategoriaPng, TipoStanza

# Slot per tipo di stanza (canone DCC, default P1 — tarabile in futuro se
# la decisione §7.1 vorrà la mappa come dato): la SAFE ROOM non compare
# perché è riservata alla troupe/narratore (P3).
SLOT_CATEGORIA: dict[TipoStanza, str] = {
    TipoStanza.BAGNO: CategoriaPng.MANAGER.value,
    TipoStanza.GILDA_TUTORIAL: CategoriaPng.MAESTRO_GILDA.value,
    TipoStanza.GILDA_SKILL: CategoriaPng.MAESTRO_GILDA.value,
}


def _pesca_affine(candidati: list, tags_piano: list[str], rng: random.Random):
    """UN candidato dal roster: il più affine ai tag del piano (sovrapposizione,
    poi slug — stessa metrica deterministica di `affini`); a parità di
    punteggio massimo decide lo stream seeded. Mai vuoto per contratto del
    chiamante."""
    richiesti = {t.strip().lower() for t in tags_piano if t.strip()}

    def punteggio(mob) -> int:
        return len(richiesti & ({t.lower() for t in mob.tags}
                                | {mob.archetipo, mob.grado.value}))

    in_classifica = sorted(candidati, key=lambda m: (-punteggio(m), m.slug))
    migliore = punteggio(in_classifica[0])
    testa = [m for m in in_classifica if punteggio(m) == migliore]
    return rng.choice(testa)


def piazza_png_di_zona(livello: int, zona) -> list[int]:
    """Piazza i PNG del roster negli slot della zona appena montata. Ritorna
    le entità piazzate (vuoto = niente slot, niente roster, o tutto già in
    scena). Chiamato dal montaggio della mappa di zona (`rigenera_mappa_zona`):
    il piazzamento è un fatto del territorio, come la stampa dei tipi."""
    import esper

    from contracts import RuoloMob

    from .calibrazione import PNG_PER_ZONA
    from .design import design_piano_corrente
    from .mappa import mappa_corrente
    from .mob import EntitaMob
    from .png import materializza_png
    from .seme import master_seed

    piano = design_piano_corrente()
    m = mappa_corrente()
    if piano is None or not piano.png or m is None:
        return []
    mappa = m[1]
    rng = random.Random(f"{master_seed()}:png:{livello}:{zona.chiave}")

    # Il mondo com'è: un personaggio esiste UNA volta (per nome — l'identità
    # diegetica, come per tregua e déjà-vu), una stanza ospita UN PNG.
    vivi = {em.nome for _ent, em in esper.get_component(EntitaMob)
            if em.ruolo is RuoloMob.PNG}
    # Filtro anche per LIVELLO (F2): le chiavi di zona si ripetono tra piani —
    # il PNG del piano lasciato non deve occupare gli slot del piano nuovo.
    stanze_occupate = {em.stanza for _ent, em in esper.get_component(EntitaMob)
                       if em.ruolo is RuoloMob.PNG and em.zona == zona.chiave
                       and em.livello == livello}

    piazzati: list[int] = []
    budget = int(PNG_PER_ZONA)
    for stanza in sorted(mappa.piano.tipi):
        if budget <= 0:
            break
        categoria = SLOT_CATEGORIA.get(mappa.piano.tipi[stanza])
        if categoria is None or stanza in stanze_occupate:
            continue
        candidati = [mob for mob in piano.png
                     if mob.categoria == categoria and mob.nome not in vivi]
        if not candidati:
            continue
        scelto = _pesca_affine(candidati, piano.tags, rng)
        ent = materializza_png(scelto, livello, stanza)
        if ent is None:
            continue  # rifiuto dichiarato (gate Elité / archetipo ignoto): si salta
        vivi.add(scelto.nome)
        stanze_occupate.add(stanza)
        piazzati.append(ent)
        budget -= 1
    return piazzati
