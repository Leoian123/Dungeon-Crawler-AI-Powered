# Third-Party Notices

Questo progetto è proprietario (vedi `LICENSE`), ma incorpora o dipende da
componenti di terze parti, ciascuno sotto la propria licenza. Questo file DEVE
accompagnare ogni distribuzione del software (repo, eseguibile, immagine di
deploy): le licenze MIT/BSD lo richiedono espressamente.

## Componenti vendorizzati (spediti dentro questo repo)

### esper — `vendor/esper/`

Entity-Component-System library. MIT License.
Testo completo in `vendor/esper/LICENSE`.

> The MIT License (MIT)
>
> Copyright (c) 2024 Benjamin Moran
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in
> all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
> FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
> IN THE SOFTWARE.

## Dipendenze runtime (installate via pip, non incluse nel repo)

| Pacchetto | Licenza | Ruolo |
|---|---|---|
| pydantic (+ pydantic-core) | MIT | validazione dei contratti (unica dipendenza viva del motore) |

## Dipendenze opzionali degli host (non richieste dal motore)

| Pacchetto | Licenza | Ruolo |
|---|---|---|
| anthropic (SDK) | MIT | provider LLM live (import pigro, opt-in) |
| textual | MIT | host TUI opzionale (`gioco_textual.py`) |
| fastapi / uvicorn / httpx | MIT / BSD-3 / BSD-3 | host web (branch `react-ecosystem`) |

> Nota di manutenzione: quando una dipendenza entra o esce da
> `requirements.txt` (o dai requirements di un host), aggiornare questa
> tabella nello stesso commit.
