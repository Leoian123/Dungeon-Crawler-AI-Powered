"""Host web — canale SSE: progresso della pipeline GM + segnale "nuovo post".

Il flusso viene consumato DIRETTAMENTE dal generatore (`flusso_eventi`) sullo
stesso event loop in cui gira il turno: `httpx.ASGITransport` bufferizza le
risposte, quindi uno stream infinito non è testabile via trasporto — il cablaggio
endpoint→StreamingResponse è verificato sulla rotta. Il ping è keep-alive di
trasporto, mai un tick di gioco (IC §7.1).
"""

from __future__ import annotations

import asyncio

import httpx

from host_web import StatoHost, crea_app
from host_web.sse import flusso_eventi, formatta


def test_formato_sse() -> None:
    testo = formatta("progresso", {"etichetta": "Il GM scrive…", "frazione": 0.35})
    assert testo == 'event: progresso\ndata: {"etichetta": "Il GM scrive…", "frazione": 0.35}\n\n'


def test_rotta_eventi_esposta() -> None:
    app = crea_app(StatoHost())
    assert any(getattr(r, "path", "") == "/api/partita/eventi" for r in app.routes)


def test_sse_trasporta_progresso_e_post(run_pulita) -> None:
    stato = StatoHost()

    async def scenario() -> None:
        trasporto = httpx.ASGITransport(app=crea_app(stato))
        async with httpx.AsyncClient(transport=trasporto, base_url="http://test") as client:
            assert (await client.post("/api/partita", json={"seed": 1})).status_code == 201
            flusso = flusso_eventi(stato)  # un abbonato collegato PRIMA del turno
            assert (await anext(flusso)).startswith(": collegato")
            turno = asyncio.create_task(
                client.post("/api/partita/narrazione", json={"versione": 0})
            )
            visti: set[str] = set()
            try:
                while not {"progresso", "post"} <= visti:
                    blocco = await anext(flusso)
                    if blocco.startswith("event: "):
                        visti.add(blocco.split("\n", 1)[0].removeprefix("event: "))
            finally:
                await flusso.aclose()
            risposta = await turno
            assert risposta.status_code == 200
            assert {"progresso", "post"} <= visti
            assert not stato._abbonati  # aclose() ha disdetto l'abbonato

    try:
        asyncio.run(asyncio.wait_for(scenario(), timeout=30))
    finally:
        stato.chiudi()
