"""adattatore — UNICO modulo che importa Textual (nodo C).

Importa SOLO `contracts` + Textual. MAI esper / World / Processor / motore (criterio
C-2b: membrana a tenuta anche da questo lato). L'app riceve il motore **iniettato** come
porte (callable sui DTO di `contracts`); il cablaggio vive nel composition root.
"""

from .app import GiocoApp

__all__ = ["GiocoApp"]
