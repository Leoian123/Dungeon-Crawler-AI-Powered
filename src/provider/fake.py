"""Provider FAKE deterministico — offline, senza rete, senza chiave (PLK, nodo F).

Implementa la **stessa interfaccia** che userà il backend reale (il `Provider`
Protocol di `contracts`): `async genera(prompt, schema) -> candidato | None`. Serve a
costruire e testare la narrazione **headless**: niente socket, niente chiave LLM,
nessun nondeterminismo di rete.

Restituisce candidati **scriptati** (caricati in coda) e, su richiesta del test,
`None` — per esercitare i due rami del fallimento di trasporto (FNC §10, F §6.1):
  - `None` esplicito in coda → fallimento di trasporto su quella chiamata;
  - coda vuota → `None` (nessuna risposta disponibile).

Resta **sottile** (PLK §3, G §9.2): trasporta e basta. NON costruisce il prompt, NON
valida catalogo/budget, NON sceglie il fallback — quelli sono dominio del motore. Per
mimare la garanzia del meccanismo nativo di output strutturato, valida il candidato
scriptato contro lo `schema` (un candidato non conforme è un errore del *test*, non un
ramo di runtime).

`prompt` è **opaco**: il fake lo registra (`prompt_ricevuti`) per gli assert, ma non lo
interpreta. La chiave LLM non compare MAI qui (né altrove): non c'è rete da chiamare.
"""

from __future__ import annotations

from collections import deque

from pydantic import BaseModel

from contracts import TCandidato

# Sentinella di fallimento di trasporto: mettere `FALLISCI` in coda fa ritornare
# `None` a quella chiamata, senza ambiguità con "candidato assente".
FALLISCI = None


class FakeProvider:
    """Provider deterministico e offline. Stessa firma del backend reale.

    Uso:
        p = FakeProvider()
        p.accoda(turno_dict_o_modello)   # candidato scriptato
        p.accoda(None)                   # fallimento di trasporto scriptato
        cand = await p.genera(prompt, TurnoNarrazione)
    """

    def __init__(self, candidati: object = ()) -> None:
        # Coda di candidati scriptati: ognuno è un modello, un dict conforme, o None.
        self._coda: deque[object] = deque(candidati)
        # Tracciamento per gli assert dei test (il prompt è opaco ma osservabile).
        self.chiamate: list[tuple[str, type[BaseModel]]] = []
        # I prefissi statici (`sistema`) visti, uno per chiamata (in fase col resto).
        self.sistemi: list[str] = []

    @property
    def prompt_ricevuti(self) -> list[str]:
        """I prompt (opachi) visti finora, nell'ordine delle chiamate."""
        return [p for p, _ in self.chiamate]

    @property
    def schemi_ricevuti(self) -> list[type[BaseModel]]:
        """Gli schemi richiesti finora — utile per provare 'un solo verbo, lo schema
        seleziona la politica' (F §5.1) e 'nessun secondo modello-giudice' (F-9)."""
        return [s for _, s in self.chiamate]

    def accoda(self, candidato: object) -> None:
        """Carica il prossimo candidato scriptato (modello, dict conforme, o None)."""
        self._coda.append(candidato)

    async def genera(
        self, prompt: str, schema: type[TCandidato], *, sistema: str = ""
    ) -> TCandidato | None:
        """Ritorna il prossimo candidato scriptato conforme a `schema`, oppure `None`.

        È `async` come il backend reale (FNC §7: async sì, thread no), ma non attende
        nulla: nessuna rete. Un candidato non `None` viene validato contro `schema`
        per mimare la garanzia del meccanismo nativo di output strutturato.
        """
        if not isinstance(prompt, str):
            raise TypeError(
                f"il prompt verso il provider è una stringa opaca, non {type(prompt)!r} "
                "(nessun componente ECS vivo attraversa il socket — G-13)"
            )
        self.chiamate.append((prompt, schema))
        self.sistemi.append(sistema)

        if not self._coda:
            return None
        prossimo = self._coda.popleft()
        if prossimo is None:  # fallimento di trasporto scriptato
            return None
        if isinstance(prossimo, schema):
            return prossimo
        # dict (o simile) conforme: validalo, come farebbe il backend a grammatica.
        return schema.model_validate(prossimo)
