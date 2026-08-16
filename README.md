# Dungeon Crawler AI-powered — RPG a turni (MVP, fetta verticale)

RPG a turni ispirato a *Dungeon Crawler Carl*. Due fasi esclusive — NARRAZIONE (l'AI
genera mondo/entità) ⇄ COMBATTIMENTO (turni deterministici) — con un principio
invariante: **l'AI propone, il motore dispone**. Il motore è **headless e
host-agnostico** (branch `headless-game-engine`): le UI sono host opzionali fuori dal
motore, che vi parlano solo via `contracts`/porte.

> Punto di situazione operativo, mappa dei branch e nodi aperti: **`STATO.md`**.
> Questo file traccia in dettaglio **cosa aggiunge il push corrente** rispetto alla
> testa precedente del branch (`2fb58f3`).

## Avvio rapido

| Comando | Cosa fa |
|---|---|
| `start.bat` | Primo setup (venv + dipendenze) e demo headless (driver di riferimento). |
| `gioca.bat` | **Gioca** con la UI Textual (host opt-in; richiede `pip install textual` nel venv). GM **live** (Anthropic) se `ANTHROPIC_API_KEY` è presente (ambiente o `.env` locale), altrimenti offline; `--live` lo esige, `--fake` forza l'offline. Richiede `pip install anthropic` per il live. |
| `calibra.bat` | **Console di calibrazione web** nel browser (stdlib, nessuna dipendenza). |
| `banco_nemici.bat` | Banco di prova generazione nemici (confronto fra modelli LLM). |
| `python -m pytest` | Suite completa: **401 verdi + 2 skip** (skip = integrazione live Anthropic senza chiave). |

Provider di gioco: **FakeProvider** (offline, un solo turno scriptato — esaurito quello,
le stanze successive usano il fallback neutro). Il collegamento del backend Anthropic
reale al gioco è il **prossimo passo dichiarato**, non incluso in questo push.

---

## Cosa aggiunge questo push (delta vs `2fb58f3`)

### 1. Profili numerici per-entità come dato (calibrazione)
Prima per-archetipo esistevano solo 3 leve; ora **tutta** la superficie numerica di un
nemico è nel catalogo §11, editabile senza toccare il codice: 13 foglie per archetipo
(`ARCH.<nome>.*` — stat base complete, geometria armatura/taglia/arma, resistenze per
tipo di danno). `primarie_da_archetipo` popola le **7 primarie** (via l'archetipo:
niente più proxy `intelligenza = destrezza//2`); nuovo componente effimero **`Corredo`**
(seam gear aperto: `derivate` legge armatura/taglia/arma per-entità con fallback ai
default globali); `istanzia_entita` attacca `Corredo` + `Resistenze` dopo il gate.
File: `motore/calibrazione.py`, `motore/corredo.py` (nuovo), `motore/derivate.py`,
`motore/narrazione.py`.

### 2. Console di calibrazione **web** (`calibratore_web.py` + `calibra.bat`)
UI da browser (stdlib: `http.server`, HTML/JS inline, solo `127.0.0.1`) per distribuire
e calibrare i profili per-entità e i coefficienti globali §11: ogni voce con la
**spiegazione del proprio impatto**, default, range, badge override, reset; pannello
**anteprima** che calcola i numeri risultanti (riusa le derivate reali su un'entità
usa-e-getta). La TUI/CLI esistente (`calibratore.py`) resta invariata.

### 3. Drenaggio **unificato** degli intenti (Canale A)
Eliminato il doppio drenatore che affamava il canale del motore: `travasa(coda)` è
l'unico travaso coda→World; i consumatori ritirano SOLO il proprio dominio via
`consuma_messaggi(tipo)`. Tassonomia in `contracts`: `IntentoEsplorazione`
(discesa/prova/disimpegno) e `IntentoCombattimento` (base dichiarata, post-MVP);
`PlayerChoseOption` resta intento di menu. La separazione esplorazione/combattimento è
il **phase-gate strutturale**: un intento nella fase sbagliata attende, non viene
scartato. File: `motore/intenti_coda.py`, `contracts/intenti.py`, `main.py`.

### 4. **Mappa** = autorità spaziale del motore (`motore/mappa.py`, nuovo)
Il `Piano` (topologia stanze/adiacenze/scale, prima dormiente) è ora **generato seeded**
e sempre validato completabile (G-18). La `Mappa` (singleton di run) dispone spazialità,
nemici e interazioni; lo stato scena-turno è la sua lettura sulla stanza corrente:
- il **menu di narrazione lo compone il motore** (`componi_opzioni_scena`), non più il
  port: nemico vivo → Combatti/Scappi; uscite → "Vai: stanza N"; **"Scendi la scala"
  SOLO dove la mappa mette la scala** (G §8.3: la prosa non concede nulla);
- movimento a intenti (`PlayerSiMuove` → `SistemaMovimento`), discesa gated sulla scala;
- **ultimo miglio chiuso**: "Combatti" **arruola l'entità rivelata della stanza**
  (`arruola_entita`): il nemico combattuto È il reveal, coi numeri calibrati
  (Primarie/Corredo/Resistenze). Lo `SpecNemico` scalare resta come fallback/rinforzi;
- persistenza nello **slot `esplorazione`** del save (topologia+posizione+visitate;
  i mob effimeri non si salvano);
- **vittoria raggiungibile dagli host**: esplora → combatti → scala → Scendi →
  `DiscesaPiano` → piano completato (testato end-to-end).
Nuovi membri d'enum (`TipoAzione.SCENDI/MUOVI`) e intento (`PlayerSiMuove`) in `contracts`.

### 5. UI di **gioco** Textual (`gioco_textual.py` + `gioca.bat`)
Host opt-in fuori dal motore: pilota `SessioneGioco` via le sole porte (importa
`main`+`contracts`, mai `motore`/esper); Textual lazy, non è dipendenza del progetto.
I bottoni sono lo snapshot della scena; permadeath chiude il menu.

### 6. Test: 340 → **401** (+2 skip invariati)
Nuovi file: `test_calibrazione_entita`, `test_corredo_seam`, `test_narrazione_corredo`,
`test_valori_mancanti`, `test_calibratore_web`, `test_gioco_textual`,
`test_drenaggio_unificato`, `test_mappa`. Fixture condivise deduplicate in `conftest.py`
(`cal_pulita`, `run_pulita`). Aggiornati al gate-scala: `test_guscio`,
`test_integrazione_e2e` (ora si portano sulla stanza-scala prima di scendere);
`gioco_textual.py` aggiunto agli host opt-in di `test_membrana_vista`.

### Invarianti: confermati, non toccati
Membrana `contracts` a tenuta (motore senza UI, C-2a/C-5); l'AI sceglie da enum chiusi,
i numeri li deriva il motore dopo il gate; `switch_world` solo al confine save/load
(l'anteprima web usa un'entità usa-e-getta, niente switch); bus tipizzato; permadeath.

---

## Segnalazioni (di troppo consapevole / debito dichiarato)

Cose **lasciate apposta** e da decidere in seguito — non rimosse in questo push:

- **`IntentoCombattimento`** (contracts): base senza membri — seam dichiarato per la
  fuga a scontro iniziato (FNC §4, post-MVP). `PlayerScappa`/`PlayerTentaProva` sono
  definiti ma non ancora consumati da nessun percorso (il disimpegno passa dal menu).
- **`TurnoNarrazione.opzioni` / `MENU_FISSO`**: il campo del DTO resta (schema chiuso)
  ma nessuno legge più le opzioni proposte dall'AI — il menu è la scena. Da valutare se
  fonderle (flavor) o ritirare il campo. `TipoAzione.ALTRO` è usato solo lì.
- **Due console di calibrazione** (`calibratore.py` TUI+CLI e `calibratore_web.py`):
  la web è un superset della TUI; candidate a consolidamento (la CLI non ha equivalente web).
- **Percorso nemici-da-scalari** (`SpecNemico`/`spawn_nemico`/`primarie_da_scalari`):
  vivo e necessario (rinforzi, fallback), ma con proxy (`FORZA=destrezza`) — da
  migrare verso profili quando i rinforzi diventeranno per-archetipo.
- Parametri-seam mai passati in produzione: `acc_eff_di(pct_precisione=…)`,
  `crea_mappa(n_stanze=…)` (solo test), `avvia(apri=…)` in `calibratore_web`.

**Bug noti pre-esistenti** (fuori dallo scope di questo push, già mappati):
`rng_state` salvato ma non riapplicato al load; `salva_run` senza `archivio` scrive un
sidecar vuoto sovrascrivendo l'esistente; status senza effetto (`applica_effetto` no-op);
attacchi sempre `TipoDanno.GENERICO` (le resistenze calibrate non vengono ancora
attivate dagli attacchi); mossa `attacco_pesante` scelta ma scartata; prosa vuota alla
rivisita di una stanza; nessun indicatore di posizione nella UI.

## Sicurezza della chiave API (PLK §4 + best practice Anthropic/OWASP)

La chiave vive **solo nell'ambiente** (`ANTHROPIC_API_KEY`) o in un **`.env` locale
gitignored** (template committato: `.env.example`; `gioca.bat` lo carica nel processo
senza stamparla). Il codice controlla solo la **presenza** della chiave, mai il valore
(lo consuma esclusivamente l'SDK); mai in argv/URL/log/prompt/repo. Il default di
`costruisci_sessione` è **offline anche con la chiave impostata**: il live è
un'iniezione esplicita dell'host, mai una chiamata di rete implicita (test inclusi).
Guardrail verificati da `tests/test_sicurezza_chiave.py` (secret-scan del repo,
template vuoto, chiave mai nei prompt). Buone pratiche lato account: chiave dedicata
al progetto con limite di spesa, rotazione periodica, revoca immediata dalla Console
in caso di sospetto leak, monitoraggio dell'uso.

## Collegamento live (fatto) e prossimi passi

`AnthropicBackend` è collegato alla pipeline GM via `gioco_textual` (selezione
esplicita del provider, etichetta visibile nella UI). Con la chiave, ogni stanza è
narrata dall'AI vera (ideazione→composizione→limatura→memoria) e il contenuto non si
esaurisce più.

**Latenza e attesa**: la chiamata gating (il turno) va al modello forte; gli stadi
ancillari non-gating al modello **veloce** (router per-schema `ProviderPerSchema`,
pin in `provider/anthropic_backend.py`); limatura e distillazione partono **in
parallelo** (un round-trip in meno); la rilettura dalla cache è a zero chiamate.
**Struttura I/O**: il prefisso statico del GM viaggia nel canale `sistema` di
`genera` (blocco `system` marcato `cache_control: ephemeral` — attivo quando il
prefisso supererà i minimi cacheabili: 1024 tok su Opus 4.8, 4096 su Haiku 4.5);
il corpo dinamico (fascicolo/istruzioni) sta nei `messages`. Gli output sono
**brevi per contratto** (prosa 3-5 frasi, limatura ≤80 parole, memoria 1-2 frasi):
i token di output dominano la latenza. Corsia veloce: `max_tokens=512`, timeout 15s.
Durante l'attesa la pipeline racconta i suoi stadi (`avanzamento(etichetta,
frazione)`) e la TUI mostra una **barra graduale** ("Il GM riflette…/scrive…/
rifinisce…") con l'input sospeso finché il GM lavora.

Prossimi passi naturali: tipo di danno negli attacchi (attivare le resistenze
calibrate), effetti degli status, imboscate collegate al dado-evento, prompt caching
esplicito lato trasporto (il prefisso statico è già in testa).
