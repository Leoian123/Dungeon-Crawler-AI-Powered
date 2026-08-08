"""Helper condivisi per i test di narrazione (non è un modulo di test).

Costruttori rapidi di candidati `TurnoNarrazione`/budget, per non ripetere la
boilerplate Pydantic in ogni test.
"""

from __future__ import annotations

from contracts import (
    Blocco,
    Durata,
    EntitaGenerata,
    Grado,
    TurnoNarrazione,
)
from motore import Budget, ARCHETIPO_DEFAULT


def budget(
    *,
    livello: int = 1,
    gradi=(Grado.BRONZO, Grado.ARGENTO),
    blocchi=(Blocco.VELENO, Blocco.RIGENERAZIONE),
    archetipo_default: str = ARCHETIPO_DEFAULT,
    anomala: bool = False,
) -> Budget:
    return Budget(
        livello=livello,
        gradi_ammessi=frozenset(gradi),
        blocchi_ammessi=frozenset(blocchi),
        archetipo_default=archetipo_default,
        anomala=anomala,
    )


# --- Code FIFO della pipeline GM (`esegui_turno_gm`) ---------------------------
# La FORMA delle code (numero e ordine degli stadi) vive QUI, in un punto solo:
# quando la pipeline cambia gli stadi, si aggiornano questi helper, non N test.
# `None` in un elemento = fallimento di trasporto scriptato di QUELLO stadio.

IDEA_QUIETE = dict(intenzione="quiete", tono="ironico", focus="una stanza umida",
                   ganci=["gocciolio"], durata_proposta="turno")

# Sentinella "stadio assente dalla coda" (≠ None, che è un degrado scriptato).
_ASSENTE = object()


def _voce_flavor(v):
    """str → payload `Flavor`; None/dict passano invariati."""
    return dict(testo=v) if isinstance(v, str) else v


def coda_reveal(turno, *, limata=None, memoria=None) -> list:
    """FIFO di un turno-REVEAL: [gating, limatura, distillazione].

    Nessuno stadio di ideazione: al reveal non c'è azione da inquadrare (skip
    della dieta token 2026-08)."""
    return [turno, _voce_flavor(limata), _voce_flavor(memoria)]


def coda_azione(turno, *, idea=IDEA_QUIETE, prova=_ASSENTE, limata=None, memoria=None) -> list:
    """FIFO di un turno-AZIONE: [ideazione, gating, (prova), limatura, distillazione].

    L'elemento `prova` entra in coda solo se passato: lo stadio esiste solo quando
    l'ideazione inquadra una prova (e la FIFO deve rispecchiarlo)."""
    coda = [idea, turno]
    if prova is not _ASSENTE:
        coda.append(prova)
    coda += [_voce_flavor(limata), _voce_flavor(memoria)]
    return coda


def coda_post_scontro(resoconto=None) -> list:
    """FIFO del turno post-scontro: dal 2026-08 è il ramo RESOCONTO — UNA sola
    chiamata `Flavor` che veste i fatti (niente ideazione, niente gating)."""
    return [_voce_flavor(resoconto)]


def turno(
    *,
    archetipo: str = "slime",
    grado: Grado = Grado.BRONZO,
    blocchi=(Blocco.VELENO,),
    durata: Durata = Durata.TURNO,
    prosa: str = "Una stanza.",
    nome: str = "Slime Mangiascarti",
    descrizione: str = "Verde, viscido.",
) -> TurnoNarrazione:
    return TurnoNarrazione(
        prosa=prosa,
        entita=EntitaGenerata(
            archetipo=archetipo,
            grado=grado,
            blocchi=list(blocchi),
            nome=nome,
            descrizione=descrizione,
        ),
        durata=durata,
    )
