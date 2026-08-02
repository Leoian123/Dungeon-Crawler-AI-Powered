"""Host web — il motore NON è rientrante: un ingresso alla volta (409, mai coda).

Il lock è `asyncio.Lock` con check non-bloccante: la seconda richiesta durante un
turno viene RIFIUTATA subito (`motore_occupato`), mai accodata in silenzio (un
accodamento riordinerebbe i turni all'insaputa del giocatore).
"""

from __future__ import annotations

import asyncio

import httpx

from host_web import StatoHost, crea_app


def _client(stato: StatoHost) -> httpx.AsyncClient:
    trasporto = httpx.ASGITransport(app=crea_app(stato))
    return httpx.AsyncClient(transport=trasporto, base_url="http://test")


def test_motore_occupato_rifiuto_immediato(run_pulita) -> None:
    stato = StatoHost()

    async def scenario() -> None:
        async with _client(stato) as client:
            assert (await client.post("/api/partita", json={"seed": 1})).status_code == 201
            # Un "turno in corso": il lock è tenuto, come durante prossima_narrazione.
            async with stato.lock:
                r = await client.post("/api/partita/narrazione", json={"versione": 0})
                assert r.status_code == 409
                assert r.json()["codice"] == "motore_occupato"
                r = await client.post(
                    "/api/partita/opzioni", json={"indice": 0, "versione": 0}
                )
                assert r.status_code == 409
            # A lock rilasciato il turno passa.
            r = await client.post("/api/partita/narrazione", json={"versione": 0})
            assert r.status_code == 200

    try:
        asyncio.run(asyncio.wait_for(scenario(), timeout=30))
    finally:
        stato.chiudi()


def test_due_richieste_concorrenti_una_sola_entra(run_pulita) -> None:
    stato = StatoHost()

    async def scenario() -> None:
        async with _client(stato) as client:
            assert (await client.post("/api/partita", json={"seed": 1})).status_code == 201
            r1, r2 = await asyncio.gather(
                client.post("/api/partita/narrazione", json={"versione": 0}),
                client.post("/api/partita/narrazione", json={"versione": 0}),
            )
            # Comunque si intreccino: UNA sola entra nel motore; l'altra è respinta
            # (motore_occupato se in volo, turno_stantio se arrivata dopo).
            assert sorted([r1.status_code, r2.status_code]) == [200, 409]
            respinta = r1 if r1.status_code == 409 else r2
            assert respinta.json()["codice"] in {"motore_occupato", "turno_stantio"}

    try:
        asyncio.run(asyncio.wait_for(scenario(), timeout=30))
    finally:
        stato.chiudi()
