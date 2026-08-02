"""Composizione di provider: instradamento PER SCHEMA (trasporto, zero dominio).

`ProviderPerSchema` smista ogni `genera` al provider associato allo schema della
chiamata (es. il turno gating → modello forte; gli stadi ancillari non-gating →
modello veloce). È il taglio di latenza permesso da G §9.2: il fan-out e la sua
composizione vivono SOTTO il socket; ogni provider composto resta sottile (una
chiamata strutturata per invocazione) e il ROUTING è configurato dal composition
root — questo modulo non conosce alcuno schema di dominio.
"""

from __future__ import annotations

from contracts import TCandidato


class ProviderPerSchema:
    """Un provider composto: `schema → provider`, con un predefinito per il resto.

    Stessa interfaccia `genera(prompt, schema)` (G-19: nessun secondo metodo): i
    chiamanti non sanno di parlare con una composizione.
    """

    def __init__(self, per_schema: dict[type, object], *, predefinito) -> None:
        self._per_schema = dict(per_schema)
        self._predefinito = predefinito

    async def genera(
        self, prompt: str, schema: type[TCandidato], *, sistema: str = ""
    ) -> TCandidato | None:
        provider = self._per_schema.get(schema, self._predefinito)
        return await provider.genera(prompt, schema, sistema=sistema)
