# Dungeon Crawler AI-powered — il motore (headless)

RPG a turni ispirato a *Dungeon Crawler Carl*. Due fasi esclusive — NARRAZIONE
(l'AI genera mondo ed entità) ⇄ COMBATTIMENTO (turni deterministici) — con un
principio invariante: **l'AI propone, il motore dispone**. Lo scopo: un motore
dove **determinismo e randomicità AI convivono** in una struttura replicabile
e modulare — ogni esito è arbitrato, seeded, replay-safe.

> Questo è il branch-**prodotto**: il cuore tecnico (motore + contracts +
> host di riferimento), senza il sovrastrato web. La presentazione completa
> (host FastAPI + SPA React) vive sul branch-laboratorio `react-ecosystem` e
> consuma questo motore per travaso. Punto di situazione, mappa dei branch e
> nodi aperti: **`STATO.md`**.

## Avvio rapido

| Comando | Cosa fa |
|---|---|
| `start.bat` | Primo setup (venv + dipendenze) e demo headless (driver di riferimento). |
| `gioca.bat` | La TUI Textual (host opt-in; `pip install textual`). Flag: `--seed N`, `--riprendi [uuid]`, `--daily`, `--infestata`, `--live`/`--fake`. Tasti: `a` azione libera, `z` zaino, `c` scheda, `b` bacheca, `s` salva. |
| `calibra.bat` | Console di calibrazione web (catalogo §11, stdlib). |
| `banco_nemici.bat` | Banco di prova generazione nemici (confronto fra modelli LLM). |
| `misura_run.bat` | Misura della vincibilità: politiche × seed, offline, riproducibile. |
| `genera_stagione.bat` | Authoring AI del piano-mondo (dry-run; `--applica` scrive). |
| `python -m pytest` | Suite completa headless, senza rete, in un lancio. |

GM: **live** (Anthropic) se `ANTHROPIC_API_KEY` è presente — corsia forte per
il turno, corsia veloce per le rifiniture, prompt caching attivo — altrimenti
**offline** con contenuto scriptato dalla stagione congelata: il motore
funziona per intero senza rete.

## Architettura (la membrana)

- `motore/` — la logica di gioco. Non importa MAI una UI.
- `contracts/` — DTO, eventi, intenti e schema AI↔motore (Pydantic). Zero
  dipendenze di progetto: è il vocabolario condiviso.
- Gli host (TUI qui; web sul laboratorio) pilotano il motore SOLO via le
  porte di `SessioneGioco` e i contratti — motore e vista non si importano
  mai a vicenda. esper è vendorizzato; Pydantic è l'unica dipendenza viva.

Le linee rosse (dal cruscotto delle decisioni): l'LLM non decide mai un
esito; l'AI non emette numeri (sceglie da enum chiusi dentro un budget);
risolvi prima, narra dopo; phase-gate strutturale; permadeath con
death-check seeded; la chiave LLM mai in URL, log, codice o documenti.

## Sicurezza della chiave API

La chiave vive **solo nell'ambiente** (`ANTHROPIC_API_KEY`) o in un `.env`
locale gitignored (template: `.env.example`; i launcher lo caricano senza
stamparla). Mai in argv, URL, log, prompt o repo — guardrail verificati da
`tests/test_sicurezza_chiave.py`. Il default è **offline anche con la chiave
presente**: il live è un'iniezione esplicita dell'host.
