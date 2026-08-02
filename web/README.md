# SPA — Forum di gioco play-by-post (React + Vite)

Frontend del gioco in stile forum: ogni turno del GM è un **post** (prosa,
dove/come, tempo, prova), le azioni disponibili stanno in calce al thread,
l'azione libera passa dal doppio giro *anteprima → conferma → immissione*.
Parla SOLO con l'host web (`src/host_web`, FastAPI su `127.0.0.1:8017`): mai col
motore, mai con i provider — la chiave LLM resta nell'ambiente del server.

## Sviluppo

```bat
gioca_web.bat --fake     &REM 1) l'host web di gioco (API su 8017)
```

```bash
cd web && npm install && npm run dev   # 2) la SPA su http://localhost:5173
```

Il dev server inoltra `/api` verso 8017 (proxy in `vite.config.ts`): niente CORS.
`npm run build` produce `web/dist/` (gitignored).

## Stack

- **React 19 + Vite + TypeScript** — SPA chiusa, nessun SSR.
- **TanStack Query** — verità remota (`["partita"]`, `["thread"]`); lo
  `SnapshotVista` si sostituisce **in blocco** (C-4), il thread accumula post.
- **Zustand** (`src/store/gioco.ts`) — solo stato effimero: progresso SSE,
  avvisi, finestra del composer.
- **Tailwind 4** — componenti propri in `src/components/` (shadcn/ui innestabile
  in un secondo taglio).
- **SSE** (`src/api/useSse.ts`) — progresso della pipeline GM (i 5 stadi: è
  l'unico segnale di latenza, niente streaming token), segnale `post`, `morte`.

## Cose da sapere

- **Una partita per processo host**: per ricominciare, riavvia `gioca_web.bat`.
- **GM offline a copione esaurito**: il FakeProvider scripta il primo turno; i
  successivi degradano al *turno di ripiego* deterministico ("La stanza è
  silenziosa…"). Non è un bug: è il fallback del motore. Col GM live ogni turno
  è generato.
- **Click stantio** (es. seconda scheda): l'host risponde 409 `turno_stantio`,
  la SPA risincronizza da sola e avvisa.
- I tipi TS in `src/api/tipi.ts` sono SPECULARI ai DTO Pydantic di
  `src/contracts/vista.py`: se cambiano i contratti, aggiornali insieme.
