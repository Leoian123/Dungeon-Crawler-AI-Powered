"""Entry point dell'host web: `python -m host_web [--porta N] [--fake]`.

UN SOLO worker e MAI reload: il World esper è process-global (una partita per
processo) e il reloader di uvicorn forkerebbe un figlio con un secondo mondo.
Bind solo su loopback: l'host è locale, la chiave LLM resta nell'ambiente del
processo e non attraversa mai la rete verso il client (PLK §4).
"""

from __future__ import annotations

import argparse
import sys

import uvicorn

from .app import crea_app
from .stato import StatoHost


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

    stato = StatoHost(directory=args.dir)
    stato.live_vietato = args.fake
    app = crea_app(stato)
    print(f"[gioca_web] API su http://127.0.0.1:{args.porta}/api — SPA: web/ (npm run dev)")
    uvicorn.run(app, host="127.0.0.1", port=args.porta, workers=1, log_level="info")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
