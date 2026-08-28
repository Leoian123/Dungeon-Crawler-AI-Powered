# Dungeon Crawler AI-powered — RPG a turni

RPG a turni ispirato a *Dungeon Crawler Carl*. Due fasi esclusive — NARRAZIONE
(l'AI genera mondo ed entità) ⇄ COMBATTIMENTO (turni deterministici) — con un
principio invariante: **l'AI propone, il motore dispone**. L'AI è varietà di
contenuto; ogni esito lo arbitra il motore, seeded e replay-safe.

> Punto di situazione operativo, mappa dei branch e nodi aperti: **`STATO.md`**.
> Questo branch (`react-ecosystem`) è il **laboratorio completo**: motore +
> host web (FastAPI) + SPA React; il motore canonico matura qui e su
> `headless-game-engine` (il branch-prodotto, solo motore).

## Giocare (un click)

| Comando | Cosa fa |
|---|---|
| `start.bat` | Primo setup (venv + dipendenze) e demo headless (driver di riferimento). |
| `gioca_web.bat` | **GIOCA dal browser**: compila la SPA se manca, avvia l'host (127.0.0.1:8017, SPA + API sulla stessa origine) e apre il browser. Flag: `--dev` (Vite con HMR), `--fake` (vieta il GM live), `--porta N`, `--senza-browser`. |
| `gioca.bat` | La TUI Textual (host opt-in; `pip install textual`). Flag: `--seed N`, `--riprendi [uuid]`, `--daily`, `--infestata`, `--live`/`--fake`. Tasti: `a` azione libera, `z` zaino, `c` scheda, `b` bacheca, `s` salva. |
| *(calibrazione)* | Nel **GM mode della SPA** (`gioca_web.bat` → Game Master → Calibrazione): catalogo §11 completo, override, anteprima nemici. Unica console admin — `calibra.bat` è stato ritirato (era il doppione standalone della stessa pagina). |
| `banco_nemici.bat` | Banco di prova generazione nemici (confronto fra modelli LLM). |
| `misura_run.bat` | Misura della vincibilità: politiche × seed, offline, riproducibile. |
| `genera_stagione.bat` | Authoring AI del piano-mondo (dry-run; `--applica` scrive). |
| `python -m pytest` | Suite completa: **~1.240 test verdi + 2 skip** (skip = integrazione live senza chiave), headless e senza rete, in un lancio. |

GM: **live** (Anthropic) se `ANTHROPIC_API_KEY` è presente — corsia forte per il
turno, corsia veloce per le rifiniture, prompt caching attivo (~$0,10 per
scontro narrato misurato) — altrimenti **offline** con contenuto scriptato
dalla stagione congelata: il gioco funziona per intero senza rete.

## Cosa c'è (implementato e verificato)

- **Motore headless a tre strati**: `motore/` (logica, mai una UI), `contracts/`
  (DTO/eventi/intenti Pydantic, zero dipendenze di progetto), host fuori dal
  motore che parlano solo via porte di `SessioneGioco`. esper vendorizzato.
- **GM AI arbitrato**: pipeline a stadi con gate di validazione, firma di
  turno + Archivio (rileggere = zero chiamate), fallback deterministici,
  memoria su tre orizzonti, Wiki del Master (appunti persistenti del GM con
  slice congelata per-run e cruscotto di promozione nel GM mode).
- **Gioco**: reveal di stanza col menu composto dal motore, scene sociali
  (parlamentare gated sul carisma, battute, tregua), combattimento
  deterministico a turni (mosse/mana/ricariche, status con effetti, fuga a
  tre corsie col prezzo sul margine), mappa e territorio (zone, custodi dei
  varchi, nascondino), riposo nei luoghi quieti, equip e fabbrica del loot
  procedurale, permadeath a prova di save-scumming.
- **Sovra-run** (online asincrono, stile roguelike): ledger degli esiti,
  bacheca dei necrologi, run del giorno (stesso seed per tutti dalla data),
  dungeon infestato (le tue morti passate come fantasmi-lore). Contratti
  pronti per il server-classifica futuro.
- **Due UI**: SPA React (gioco play-by-post, hub crawler, forum con bacheca,
  GM mode con authoring/calibrazione/wiki) e TUI Textual, sulle stesse porte.

## Sicurezza della chiave API

La chiave vive **solo nell'ambiente** (`ANTHROPIC_API_KEY`) o in un `.env`
locale gitignored (template: `.env.example`; i launcher lo caricano senza
stamparla). Mai in argv, URL, log, prompt o repo — guardrail verificati da
`tests/test_sicurezza_chiave.py`. Il default è **offline anche con la chiave
presente**: il live è un'iniezione esplicita dell'host, mai una chiamata di
rete implicita.
