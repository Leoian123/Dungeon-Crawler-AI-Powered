"""tests/harness — l'arnia headless.

Fa girare il motore SENZA Textual e SENZA rete (criterio C-5): un adattatore nullo
che raccoglie gli eventi di dominio emessi, un punto d'iniezione per intenti
scriptati, e un aggancio per un provider fake (da riempire al nodo F).

NOTA: in questa fase il motore non ha ancora logica né `contracts` veri. L'arnia è
quindi uno *scheletro* a tenuta di contratto: non importa Textual né apre socket,
e non dipende dal motore di gioco (che non esiste ancora). I tipi placeholder qui
sotto verranno rimpiazzati dai DTO di `contracts` quando il nodo F atterra.
"""

from .null_adapter import NullAdapter
from .fake_provider import FakeProvider
from .runner import HeadlessRun

__all__ = ["NullAdapter", "FakeProvider", "HeadlessRun"]
