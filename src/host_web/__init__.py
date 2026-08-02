"""Host web di gioco (opt-in, FUORI dal motore): FastAPI sopra le porte di
`SessioneGioco` + SSE per progresso/eventi. Il frontend (SPA in `web/`) parla solo
con questa API; il motore resta ignaro dell'host (C-2a/C-5)."""

from .app import ErroreApi, crea_app
from .stato import PostThread, StatoHost

__all__ = ["ErroreApi", "PostThread", "StatoHost", "crea_app"]
