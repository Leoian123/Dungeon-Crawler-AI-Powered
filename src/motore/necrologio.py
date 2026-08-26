"""Il NECROLOGIO del crawler — la bacheca come PROIEZIONE del ledger (Fase B).

Nessun secondo artefatto: il necrologio si COMPONE dai fatti dell'`EsitoRun`
a ogni lettura, deterministico (stesso esito = stesso post, per sempre). Così
non esiste alcun problema di sincronia ledger↔bacheca, e la storia sopravvive
esattamente quanto il ledger. I `momenti` salienti sono già nell'esito perché
l'Archivio muore con la run (`invalida` rimuove il sidecar): tutto ciò che il
necrologio racconta è stato raccolto PRIMA, al terminale.

Il motore compone, l'AI (un domani) al più VESTE dentro il canale
proposta→gate — mai inventare i fatti. Composizione senza LLM = la bacheca
funziona offline, nel prototipo, da subito.
"""

from __future__ import annotations

from contracts import EsitoRun, NecrologioCrawler, Terminale


def componi_necrologio(esito: EsitoRun) -> NecrologioCrawler:
    """Un esito → un post. Deterministico, fattuale, registro asciutto."""
    if esito.terminale is Terminale.SCONFITTA:
        titolo = f"† {esito.nome} — piano {esito.profondita}"
        righe = [
            f"Caduto per mano di {esito.causa}." if esito.causa
            else "Caduto nel dungeon.",
        ]
        if esito.tick:
            righe.append(
                f"Ha tenuto il piano {esito.profondita} per {esito.tick} tick."
            )
        righe.extend(f"· {momento}" for momento in esito.momenti)
    else:  # PIANO_COMPLETATO: anche l'ascesa fa bacheca
        titolo = f"⚑ {esito.nome} — piano {esito.profondita} completato"
        righe = [f"Ha battuto il piano {esito.profondita} ed è sceso oltre."]
        if esito.tick:
            righe.append(f"In {esito.tick} tick.")
    righe.append(f"Run del seed {esito.seed}, stagione {esito.stagione}.")
    return NecrologioCrawler(
        uuid_run=esito.uuid_run,
        nome=esito.nome,
        titolo=titolo,
        corpo="\n".join(righe),
        stagione=esito.stagione,
        profondita=esito.profondita,
        ts=esito.ts,
    )


def necrologi_da_ledger(righe: list[dict]) -> list[NecrologioCrawler]:
    """Le righe del ledger → i post, in ordine di deposito. LASCO: una riga
    che non valida il contratto si salta (il ledger è tollerante per disegno,
    la bacheca lo è di conseguenza — spazzatura muta, mai un crash)."""
    post = []
    for riga in righe:
        try:
            esito = EsitoRun.model_validate(
                {k: v for k, v in riga.items() if k != "id"}
            )
        except Exception:
            continue
        post.append(componi_necrologio(esito))
    return post
