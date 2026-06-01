"""Snapshot di stato per la vista — **input di rendering**, non verità (IC §2.2).

L'adattatore di presentazione rende ciò che il motore gli consegna già confezionato:
prosa, opzioni del menu, descrittori di stato (HP/status/budget), fase corrente. È un
**DTO** che attraversa la membrana, **rimpiazzato in blocco** a ogni emissione e **mai
accumulato né diffato** lato vista (C-4): la fonte di verità resta il `World`.

Niente renderable di Rich, niente widget Textual, niente riferimenti al `World`: solo
dati semplici (IC §2.2). Dipendenze: solo stdlib + Pydantic (come tutto `contracts`).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .schema import TipoAzione


class OpzioneVista(BaseModel):
    """Una voce del menu a opzioni discrete (IC §1.2): indice + etichetta + tipo chiuso.

    Il giocatore la sceglie per **indice** (→ `PlayerChoseOption(indice)`, IC §2.3); il
    `tipo` è categoriale (mai testo grezzo). L'`etichetta` è flavour, da rendere a video.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    indice: int
    etichetta: str
    tipo: TipoAzione


class SnapshotVista(BaseModel):
    """Lo stato corrente confezionato per il render (sostituito in blocco, C-4).

    - `prosa`: testo della narrazione/flavour da appendere allo scroll;
    - `opzioni`: il menu discreto corrente (vuoto ⇒ "in attesa di un turno");
    - `stato`: descrittori diegetici per il pannello (es. `("ferito", "avvelenato")`);
    - `fase`: `"narrazione" | "combattimento"` (per il titolo/contesto del pannello).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    prosa: str = ""
    opzioni: tuple[OpzioneVista, ...] = ()
    stato: tuple[str, ...] = ()
    fase: str = "narrazione"
