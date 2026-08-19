"""Entry point dell'host web: `python -m host_web [--porta N] [--fake]`.

UN SOLO worker e MAI reload: il World esper è process-global (una partita per
processo) e il reloader di uvicorn forkerebbe un figlio con un secondo mondo.
Bind solo su loopback: l'host è locale, la chiave LLM resta nell'ambiente del
processo e non attraversa mai la rete verso il client (PLK §4).

Con la SPA COSTRUITA (`web/dist`, da `npm run build`) l'host la serve lui:
un solo processo, una sola origine (niente proxy, niente CORS) — è la corsia
del «doppio click e giochi» di `gioca_web.bat`. Senza build resta l'API nuda
e la SPA gira su Vite (corsia dev, proxy in `web/vite.config.ts`).
"""

from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path

import uvicorn

from .app import crea_app
from .stato import StatoHost

# src/host_web/__main__.py → la radice del repo → web/dist (la SPA compilata).
_DIST_DEFAULT = Path(__file__).resolve().parents[2] / "web" / "dist"


def monta_spa(app, dist: Path | None = None) -> bool:
    """Monta la SPA compilata sull'app FastAPI ("/" e asset). Le rotte /api/*
    sono registrate PRIMA del mount e vincono sempre; `html=True` serve
    index.html alla radice (la SPA non ha router: basta quella). `False`
    senza build — l'host resta API-only, mai un errore."""
    from fastapi.staticfiles import StaticFiles

    dist = Path(dist) if dist is not None else _DIST_DEFAULT
    if not (dist / "index.html").exists():
        return False
    app.mount("/", StaticFiles(directory=dist, html=True), name="spa")
    return True


def _porta_libera(porta: int) -> bool:
    """Pre-check del bind: uvicorn fallirebbe comunque, ma DOPO l'avvio dell'app
    e con un traceback winsock poco leggibile — meglio dirlo subito e in chiaro."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sonda:
        try:
            sonda.bind(("127.0.0.1", porta))
        except OSError:
            return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="host_web", description="Host HTTP di gioco (forum play-by-post)."
    )
    parser.add_argument("--porta", type=int, default=8017, help="porta locale (default 8017)")
    parser.add_argument(
        "--fake", action="store_true",
        help="vieta il GM live anche se richiesto via API (solo contenuto offline)",
    )
    parser.add_argument(
        "--dir", default=None,
        help="cartella dei crawler salvati (default: salvataggi/ o DCC_SAVE_DIR)",
    )
    args = parser.parse_args(argv)

    if not _porta_libera(args.porta):
        print(
            f"[gioca_web] La porta {args.porta} è già occupata: un altro host web "
            "è probabilmente in esecuzione (una finestra precedente, o l'anteprima "
            "dell'editor). Chiudi l'altro processo o avvia con --porta N "
            "(ricordando il proxy di web/vite.config.ts)."
        )
        return 1

    stato = StatoHost(directory=args.dir)
    stato.live_vietato = args.fake
    app = crea_app(stato)
    if monta_spa(app):
        print(
            f"[gioca_web] GIOCA su http://127.0.0.1:{args.porta} "
            "(SPA compilata + API, stessa origine)"
        )
    else:
        print(
            f"[gioca_web] API su http://127.0.0.1:{args.porta}/api — SPA non "
            "compilata: npm --prefix web run build (un click) "
            "oppure npm --prefix web run dev (sviluppo, proxy su questa porta)"
        )
    uvicorn.run(app, host="127.0.0.1", port=args.porta, workers=1, log_level="info")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
