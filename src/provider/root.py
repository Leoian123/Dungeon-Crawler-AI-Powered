"""Composition root del provider live — costruzione e selezione, ZERO dominio.

Prima viveva in `gioco_textual._scegli_provider` (host TUI): la scelta fake/live,
il cablaggio forte+veloce e il tally condiviso erano raggiungibili solo passando
dalla UI. Qui diventano riusabili da QUALUNQUE host (TUI, driver headless, web
futuro) — questo modulo importa solo `provider/*` e `contracts`, MAI `motore`
(il motore riceve il provider per iniezione, membrana C-2).

Le CORSIE sono profili di trasporto nominati ("forte"/"veloce"): il motore — via
il Master-Engine — parla per corsie astratte; il binding corsia→modello/limiti
vive qui, in un dato sostituibile. L'`instradamento` schema→corsia è un DATO che
il chiamante può iniettare; il default (gating→forte, resto→veloce) referenzia
solo tipi di `contracts` (il layer condiviso, importabile da tutti).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .anthropic_backend import MODELLO_DEFAULT, MODELLO_VELOCE
from .composito import ProviderPerSchema
from .consumo import ConsumoProvider


@dataclass(frozen=True)
class ProfiloCorsia:
    """Il profilo di trasporto di UNA corsia: dati, nessun comportamento."""

    modello: str
    max_tokens: int
    timeout: float


# Binding di default corsia→profilo. Il FORTE serve la chiamata gating (il turno);
# il VELOCE gli stadi ancillari non-gating: output brevi per contratto, quindi
# max_tokens stretto (fallisce presto invece di generare a vuoto) e timeout corto
# — gli stadi non-gating degradano, non bloccano.
CORSIE_DEFAULT: dict[str, ProfiloCorsia] = {
    # 4096: la prosa cinematografica dei momenti chiave (250-400 parole) + il JSON
    # dell'entità con margine; il retry di troncatura del backend copre le code.
    "forte": ProfiloCorsia(modello=MODELLO_DEFAULT, max_tokens=4096, timeout=30.0),
    # 1024: la limatura ora PRESERVA la lunghezza della bozza (stadio di qualità),
    # quindi deve poter riscrivere anche una bozza lunga senza troncare.
    "veloce": ProfiloCorsia(modello=MODELLO_VELOCE, max_tokens=1024, timeout=15.0),
}


def costruisci_backend_live(
    *,
    corsie: Mapping[str, ProfiloCorsia] = None,
    consumo: ConsumoProvider | None = None,
) -> dict[str, object]:
    """Un backend Anthropic per corsia, con UN tally condiviso.

    Il consumo (token, chiamate, guasti) è per-run, non per-modello: lo stesso
    `ConsumoProvider` viaggia in ogni backend — l'usage non si butta via."""
    from provider import AnthropicBackend  # pigro: monkeypatchabile dai test

    corsie = dict(CORSIE_DEFAULT if corsie is None else corsie)
    consumo = consumo if consumo is not None else ConsumoProvider()
    return {
        nome: AnthropicBackend(
            modello=p.modello, max_tokens=p.max_tokens, timeout=p.timeout,
            consumo=consumo,
        )
        for nome, p in corsie.items()
    }


def _instradamento_default() -> dict[type, str]:
    """Gating→forte; tutto il resto→veloce. Solo tipi di `contracts` (mai motore)."""
    from contracts import TurnoNarrazione

    return {TurnoNarrazione: "forte"}


def scegli_corsie(
    argv: list[str],
    *,
    corsie: Mapping[str, ProfiloCorsia] | None = None,
) -> tuple[dict[str, object] | None, str, ConsumoProvider | None]:
    """Seleziona i backend PER CORSIA ("forte"/"veloce") con UN tally condiviso.
    Ritorna `(backend, etichetta, consumo)`; backend `None` = offline/fake.

    È il mattone sotto `scegli_provider`: chi parla per corsie astratte (il
    Master-Engine, che riceve `Mapping[Corsia, provider]`) usa QUESTA, così la
    corsia dichiarata dalla rotta arriva davvero al modello giusto — senza
    passare dall'instradamento per-schema. Le chiavi restano stringhe: questo
    modulo non importa mai `motore` (membrana C-2).

    Politica (PLK §4 + best practice chiavi API):
      - la chiave vive SOLO nell'ambiente (`ANTHROPIC_API_KEY`): qui se ne controlla
        la PRESENZA, mai il valore — lo legge esclusivamente l'SDK;
      - mai la chiave in argv/URL/log; nessun degrado silenzioso: se il live non è
        possibile lo si DICE (niente fallback muto che maschera un errore di setup);
      - `--fake` forza l'offline; `--live` esige il live (errore chiaro se manca
        chiave o SDK); default: live se la chiave c'è, altrimenti offline.
    """
    from provider import chiave_presente, sdk_disponibile  # pigri: monkeypatchabili

    if "--fake" in argv:
        return None, "GM offline (contenuto scriptato)", None
    presente, sdk = chiave_presente(), sdk_disponibile()
    if "--live" in argv:
        if not presente:
            raise SystemExit(
                "--live richiede ANTHROPIC_API_KEY nell'ambiente (o in .env: "
                "copia .env.example → .env e compila). La chiave non va MAI in argv o nel repo."
            )
        if not sdk:
            raise SystemExit(
                "--live richiede l'SDK: .venv\\Scripts\\pip install anthropic"
            )
    if not presente:
        return None, "GM offline (nessuna ANTHROPIC_API_KEY: vedi .env.example)", None
    if not sdk:
        return None, "GM offline (SDK anthropic non installato)", None

    consumo = ConsumoProvider()
    backend = costruisci_backend_live(corsie=corsie, consumo=consumo)
    profili = dict(CORSIE_DEFAULT if corsie is None else corsie)
    etichetta = (f"GM live — {profili['forte'].modello} (turni) + "
                 f"{profili['veloce'].modello} (rifiniture)")
    return backend, etichetta, consumo


def scegli_provider(
    argv: list[str],
    *,
    instradamento: Mapping[type, str] | None = None,
    corsie: Mapping[str, ProfiloCorsia] | None = None,
) -> tuple[object | None, str]:
    """Seleziona il provider del GM. Ritorna `(provider, etichetta)`; `None` = fake.

    È `scegli_corsie` + l'adattatore per-schema: serve agli host che parlano con
    UN provider composito (la porta storica). La politica chiave/fake/live vive
    in `scegli_corsie` — una sola copia."""
    backend, etichetta, consumo = scegli_corsie(argv, corsie=corsie)
    if backend is None:
        return None, etichetta

    rotte = dict(_instradamento_default() if instradamento is None else instradamento)
    per_schema = {schema: backend[corsia] for schema, corsia in rotte.items()}
    provider = ProviderPerSchema(per_schema, predefinito=backend["veloce"])
    # Il tally viaggia col provider: l'host lo mostra a fine sessione (e può
    # leggerlo quando un turno degrada) senza cambiare la firma di questa funzione.
    provider.consumo = consumo
    return provider, etichetta
