"""DTO dell'hub (guscio → host): l'elenco dei crawler salvati (H §1, H §5).

Slot = crawler: un crawler vivo = un save unico. L'elenco viene dallo scan delle
sole intestazioni (`indice_crawler`, mai deep-parse); questo DTO ne esprime la
forma verso un host, senza esporre `VoceIndice` del motore. Un'intestazione
illeggibile diventa `corrotta=True`: si mostra, non si carica (H-22).

Dipendenze: solo stdlib + Pydantic (F-2).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CrawlerVista(BaseModel):
    """Una voce dell'elenco crawler per la schermata di selezione run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uuid: str
    etichetta: str
    profondita: int
    timestamp: float = 0.0  # epoch dell'ultimo salvataggio; 0.0 = save legacy
    corrotta: bool = False
