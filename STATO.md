# STATO DEL PROGETTO — dove siamo, i branch, come proseguire oltre il pre-MVP

> **Cos'è questo file.** Non è una spec normativa (quelle stanno in `docs/`, vedi
> `progetto-indice-decisioni.md`). È il **punto di situazione operativo**: ti dice in che
> stato è il codice *rispetto* alla documentazione, tiene la mappa dei branch, e fa da
> **base di ripartenza** per continuare verso (e oltre) l'MVP. Vive alla radice del repo
> ed è **versionato** (a differenza di `docs/`, che è in `.gitignore`).
>
> **Aggiornalo** quando: chiudi una fase, crei/fondi un branch, o prendi una decisione che
> diverge da `docs/`. Ultima revisione: **2026-08-04** — refactor **"mob componibili"**
> (branch `react-ecosystem`): l'enum `Archetipo` è stato sostituito da slug con chiusura
> PER-RUN (emendamenti D1/D5 su F-1/F-4/F-5/F-6, G-23 — vedi i docs); gli archetipi sono
> **asset** (`contenuti/archetipi/`, collezione anche via API/SPA), le mosse un
> **catalogo-dato** (`motore/mosse.py`) eseguito dai system via componente `Repertorio`,
> il danno è tipato (layer resistenze attivo), i mob per-asset portano `mosse`/`override`
> e il contratto AI ha il `riferimento` (reclutamento dal cast, 4° strato di gate).
> Un agente crea archetipi/mob via `POST /api/contenuti/*` e il motore li mette in scena:
> zero codice. Il delta precedente (calibrazione per-entità, console web, Mappa) resta
> tracciato in **`README.md`**.

---

## ⚠️ 1. Avviso: il codice diverge dalla documentazione normativa (nodo C / Textual)

La documentazione in `docs/` è **chiusa e validata** sul **nodo C = "rendering con Textual"**:

- `interfaccia-contratto.md` (IC) descrive l'adattatore Textual come il layer di presentazione.
- `progetto-indice-decisioni.md` elenca fra gli **invarianti trasversali**: *«Una sola
  dipendenza viva (Textual), pinnata e marcata»* e *«il motore non importa Textual;
  l'adattatore non importa il World»*.
- `CLAUDE.md` ripete: *«Textual pinnato esatto + lockfile (unica dipendenza "viva")»*.

**Il branch corrente (`headless-game-engine`) diverge da tutto questo di proposito:**
Textual e l'intero pacchetto `src/adattatore/` sono stati **rimossi**. Il game engine torna
**headless** e **indipendente da qualunque UI**. La presentazione futura (web, Electron, TUI,
…) non è ancora scelta: si innesterà più avanti, *fuori* dal motore.

### Cosa resta valido e cosa è superato su questo branch

| Principio dei docs | Stato sul branch `headless-game-engine` |
|---|---|
| Membrana motore ⇄ vista via `contracts` (DTO/eventi/intenti) | ✅ **Invariato e rafforzato.** Resta l'unico canale verso un host. |
| Il motore non importa una UI; è host-agnostico | ✅ **Rafforzato.** Ora *nessun* modulo sotto `src/` importa una libreria di UI (test `test_membrana_vista.py`). |
| "L'adattatore non importa il World" | ⚪ **Non più applicabile:** non esiste più un adattatore. Il principio sopravvive come *"il motore è pilotabile solo via contracts/porte"*. |
| Textual = unica dipendenza viva, pinnata | ❌ **Superato.** Nessuna libreria di UI fra le dipendenze; resta solo **Pydantic** (+ esper vendorizzato). |
| Worker Textual `exclusive` per la chiamata LLM | ⚪ **Spostato all'host futuro.** La coroutine host-agnostica `prossima_narrazione` resta `await`-abile; chi la schedula (worker UI o `asyncio.run`) lo decide l'host. |

> **In sintesi:** la *forma* della membrana (contratto sì, trasporto no — IC) è intatta e
> più pulita di prima. È cambiata solo la **scelta del rendering**: da "Textual ora" a
> "UI da decidere, motore indipendente". **Finché i docs non vengono ritoccati, su questo
> branch vale questo file** per il nodo C. Vedi §5 per la checklist di riallineamento.

---

## 2. Dove siamo: fase pre-MVP completata, headless

Implementazione realizzata fino al **gate del nodo A** (slice verticale giocabile capo-a-fine,
headless e seeded). Le fasi 0–10 del piano (`docs/I-piano-build-claude-code.md`) sono atterrate:

- **`contracts/`** — bus tipizzato, schema F (Pydantic), proiezione scheda, snapshot vista. Zero dipendenze di progetto.
- **`motore/`** — nucleo ECS (esper vendorizzato) + phase-gate (`PhasedProcessor`) + coda intenti; combattimento (status, death-check seeded, mutazione); narrazione (gate a 3 strati, registry/formula, fallback atomico, prove, livello/`DiscesaPiano`, socket); **motore del tempo J** (scorrimento, dado-evento, fast-forward, passa-turno).
- **`provider/`** — `FakeProvider` (offline, scriptato) + backend **Anthropic** reale dietro `genera` (slot, live opzionale).
- **`guscio/`** — macchina-guscio (nodo E), tre terminali, confine `switch_world` guscio↔run.
- **`src/main.py`** — composition root **headless**: cabla il motore e lo pilota con un **driver di riferimento** (`gioca_un_incontro`) via le sole porte + eventi di bus. Nessuna dipendenza di presentazione.

**Gruppo 2 — economia (FORMA fatta).** Sopra il pre-MVP sono atterrate le fasi **2a + 2b + layer
tipi di danno** (`docs/gruppo 2/`): modello-stat a vettore `Primarie` + fold `stat_eff` con
finalizzazione per-stat da registry; `Azione`/`Effetto`/`Danno` (atomo spezzato, interno al
motore); risolutore di combattimento **a due check** (danno deterministico + colpire
stocastico-ma-seeded a banda/graze); `ActionPoint` posseduto; nemici e mob di narrazione con
`Primarie` (una sola strada-stat, §16.4); escalation a contatore (`SistemaCrollo`); `TipoDanno` +
resistenze tipate (`ResistenzaMod`). **Tutti i numeri §11 in `motore/calibrazione.py`** (placeholder
marcati). Restano **solo i numeri** da calibrare (la *forma* è completa).

**Verifica:** **401 test verdi + 2 skip** (i 2 skip = integrazione live Anthropic, saltata senza `ANTHROPIC_API_KEY`). "Giocabile capo-a-fine" dimostrato headless con provider deterministico — e ora anche **dalla UI di gioco** (host Textual opt-in) attraverso la mappa: esplora → combatti → scala → discesa (vittoria). Delta dettagliato in `README.md`.

**Fuori scope per scelta (non ancora fatto):** i **numeri** d'economia (Gruppo 2 §11, da calibrare), il **tick degli status** (`applica_effetto` ancora no-op), il **replay completo**, e le feature **post-MVP** dichiarate (vedi §4).

---

## 2.2 Fondamenta — le guardie della "Mossa 1" (2026-08-04)

Dopo un audit delle fondamenta (sessione/run, osservabilità, persistenza, confini) sono
atterrate le prime **guardie**: ciò che prima corrompeva in silenzio ora fallisce
rumorosamente, e la spesa LLM è misurabile. Modello di consegna deciso: **web app**
(Steam rimandato); licenza **proprietaria** (`LICENSE` + `THIRD-PARTY-NOTICES.md`,
propagata su tutti i branch).

- **Consumo del provider** (`provider/consumo.py`): `AnthropicBackend` non butta più via
  `risposta.usage` — token in/out, cache, chiamate, refusal ed errori di trasporto in un
  `ConsumoProvider` condivisibile fra backend (in `_scegli_provider` forte+veloce ne
  condividono uno: totale per-run). Solo TOKEN, mai valute: il costo lo deriva l'host.
- **Death-check rumoroso**: con N>1 protagonisti `SistemaDeathCheck` solleva invece di
  restituire in silenzio (prima la permadeath G-11 si spegneva zitta — il party dovrà
  passare di lì di proposito). Il caso simmetrico è chiuso al load: un save con N≠1
  protagonisti muore in `_verifica_coerenza` (H-12), non al primo tick.
- **Una sola run per processo, rumorosa**: aprire una `SessioneGioco` invalida la
  precedente ancora aperta (registro weakref in `main.py`); ogni porta della sessione
  invalidata solleva — comprese `riepiloga_azione` e, via la barriera
  `guardia_scrittura` di `esegui_turno_gm`, il turno GM **già in volo**: la coroutine
  sospesa sul provider cade alla barriera senza scrivere nel World altrui.
  L'invalidazione scatta PRIMA di toccare il World (anche se l'ingresso poi fallisce);
  una busta illeggibile invece non costa nulla a nessuno (sonda prima del boot).
  *Limite dichiarato:* la guardia copre le porte di `SessioneGioco`; chi costruisce un
  `Guscio` direttamente è fuori contratto.
- **Rollback sul load**: se il payload di un componente tradisce la busta (campo
  rinominato senza migrazione), `carica_crawler` fa teardown e ritorna `False` — il
  contesto torna al default, mai un World parziale attivo, save intatto su disco.
- **Radici dei percorsi**: installazione (read-only, `contenuti/`) separata dai dati
  utente (scrivibili, `salvataggi/` + `contenuti_locali/`), default consapevoli del
  congelamento PyInstaller (`sys.frozen`/`_MEIPASS`); le variabili `DCC_*` restano
  l'override esplicito per il deploy.

Lucchetti: `tests/test_guardie_fondamenta.py` + `tests/test_provider_consumo.py`
(**516 verdi + 2 skip**; il delta ha passato una review avversariale a tre lenti che
ha trovato — e fatto chiudere — il buco del turno in volo e i due dell'ordine di
invalidazione). Restano dall'audit (non ancora fatti): terminale di run
esposto nel contratto, token di turno + id-opzione stabile, eventi con id di entità,
snapshot a dati (non stringhe impaginate), logging sul bus, tassonomia errori in
`contracts`, CI.

---

## 3. Mappa dei branch

Remote: **`origin`** → https://github.com/Leoian123/Dungeon-Crawler-AI-Powered.git
(tutti e tre i branch sono pushati su origin.)

```
649fe95  Fetta verticale MVP: fasi 0-7 (scaffolding -> guscio), headless e seeded
   │
5b8bfc7  Aggiungi docs a gitignore ............................ ◀── main
   │
1250879  Implementazione del motore del tempo e di Textual UI .. ◀── v1-textual-implementation
   │
e09f27e  Ritorno a headless: rimozione dell'adattatore Textual . ◀── headless-game-engine  ★ ATTUALE
```

| Branch | Commit | Contenuto | Ruolo |
|---|---|---|---|
| **`headless-game-engine`** ★ | `e09f27e` | Tutto `main` **+ motore del tempo (J) + main headless**, **senza** Textual. | **Canonico.** Base di lavoro corrente, la più avanzata (2 commit avanti a `main`, 0 indietro). |
| `v1-textual-implementation` | `1250879` | `main` + motore del tempo (J) + **UI Textual** (nodo C, fasi 9–10). | **Archivio storico** dell'esperimento con UI. Non più la linea di sviluppo; conservato come riferimento se si volesse riesumare una TUI. |
| `main` | `5b8bfc7` | Solo fasi 0–7 (scaffolding → guscio), headless+seeded. **Niente** motore del tempo, niente UI. | **Indietro.** Va portato avanti (vedi §5). |

> **Nota:** `headless-game-engine` è strettamente **avanti** a `main` (nessun commit di
> `main` manca qui) e contiene tutto il valore di `v1-textual-implementation` **tranne** il
> layer Textual. È quindi il candidato naturale a diventare la nuova linea principale.

---

## 4. Base per continuare oltre il pre-MVP

### 4.1 Da fare per *chiudere* l'MVP (resta dentro lo scope dichiarato)
- **Gruppo 2 — economia: i NUMERI.** La *forma* (2a+2b+tipi) è atterrata (vedi §2); restano i
  **valori §11**, centralizzati e marcati in `motore/calibrazione.py`: costanti del check 1
  (`s`, `F`, `δ`, `g`, `MIN_COLPO`), curva HP/TTK, soglia escalation, cap-resistenze, basi-archetipo,
  + tabelle di budget/anomalie, numeri degli status, soglie classi di prova, `Durata → carico-tick`.
  Vincolo: l'AI non emette numeri — il motore li deriva (gate catalogo+budget). I due **property-test**
  del check 1 (`tests/test_calibrazione_check1.py`) sono la rete che li vincola.
- **Tick degli status** (`status.applica_effetto` oggi no-op): un solo `SistemaStatus` generico
  guidato dalla lista di `Effetto` (Gr2 §16.1), ora che l'atomo `Azione`/`Effetto` esiste.
- **Calibrazione del gate del nodo A** (G-L1 "ogni scontro termina", G-L2 "ogni piano
  completabile") con i numeri reali del Gruppo 2, non solo con gli stub.

### 4.2 Post-MVP dichiarato (forma predisposta, da accendere)
- **Replay deterministico completo** — oggi "solo-formato": i marcatori di fallback non
  vengono popolati (vedi annotazioni F-13/G-21 nell'indice decisioni). Accenderlo è
  prerequisito del **dono NieR**.
- **Memoria generativa ("wiki")** — meta-store a livello di guscio; recupero semantico, non
  riproduzione esatta (≠ cache delle stanze). Abilitata dall'indirezione del verbo "procura".
- **Dono NieR (cross-giocatore)** — alla vittoria, promozione dell'Archivio nello store
  condiviso. Richiede replay completo (donabili solo gli Archivi nati *dopo* l'accensione).
- **AI master** — compone primitivi chiusi (skill/oggetti/PNG) senza coniare atomi o numeri.
- **Testo libero (`Altro`)** — classificazione "intento → evento tipizzato" su menu chiuso.

### 4.3 Il nodo aperto vero: scegliere la UI (ex-nodo C, ora riaperto di fatto)
Avendo rimosso Textual, **la scelta del layer di presentazione è di nuovo aperta**. La
membrana `contracts` + le porte di `SessioneGioco` (`prossima_narrazione`, `avanza`,
`coda.accoda`, `salva`, `bus`) sono il punto d'innesto: una Ui futura (web/Electron/TUI)
consuma gli **stessi DTO** (`SnapshotVista`, `OpzioneVista`, eventi del bus) che il driver
headless usa oggi. Quando si sceglierà, **aggiornare i docs del nodo C** (vedi §5).

---

## 5. Disallineamenti docs ↔ codice da sanare (checklist)

Quando si deciderà di consolidare, questi sono i punti dove la documentazione normativa va
ritoccata per rispecchiare la realtà del branch headless:

- [x] **IC / nodo C** — *(banner di divergenza in cima, 2026-06-04)*: il rendering non è più
      "Textual" sul branch headless → la sezione "Decisione C" è **superata**; aggiunto un
      rimando a questo file (§1 tabella valido/superato). La parte sulla **membrana** resta valida
      (non riscritta).
- [x] **`progetto-indice-decisioni.md`** — *(banner + reword invarianti, 2026-06-04)*: «unica
      dipendenza viva (Textual)» → «nessuna dipendenza di UI nel motore; Pydantic unica viva, esper
      vendorizzato»; «l'adattatore non importa il World» → «il motore è pilotabile solo via
      contracts/porte»; nodo C marcato 🔄 riaperto.
- [x] **`CLAUDE.md`** — *(2026-06-04)*: tolta "Textual pinnato (unica dipendenza viva)";
      architettura a tre strati aggiornata (l'`adattatore/` non esiste più su questo branch);
      tolto il punto "Worker API di Textual" da "verifica, non ricordare".
- [x] **Pipeline GM (2026-07-31)** — estensione di spec, conforme a G §9.2–9.3: il turno di
      narrazione passa da una **coroutine di orchestrazione a stadi** (`motore/gm.py`,
      `esegui_turno_gm`): ideazione (nuova chiamata strutturata **non-gating** per turno,
      schema `Ideazione`, consultiva, 0 retry, degrado silenzioso — G-22 resta rispettato:
      **una sola chiamata gating**, `procura_turno` invariata) + inquadramento-prova ≤1 +
      limatura ≤1 + distillazione-memoria ≤1 (tutte `Flavor`/non-gating). La **firma di
      turno** (`firma_turno`) è il generatore della chiave d'Archivio H §8 finora mancante
      (congela-una-volta-rileggi-sempre); la memoria di run è **derivata** (H §11), mai
      persistita come chat. Il combattimento resta **istanza separata** deterministica
      (`IstanzaCombattimento` nel composition root); i suoi FATTI rientrano nel fascicolo
      (risolvi prima, narra dopo). FNC §11 "mai spezzare il turno" resta vero: l'output di
      stato è UNA `TurnoNarrazione` da UNA `genera`.
- [ ] **Branch** — decidere il destino di `v1-textual-implementation` (tenere come archivio
      o cancellare) e **portare avanti `main`**: quando il branch headless è accettato,
      fonderlo in `main` (fast-forward possibile: `main` è 0 commit avanti). *(Lasciato all'utente:
      i commit 2b+pulizia sono su `headless-game-engine`, `main` non è stato toccato.)*

---

## 6. Comandi utili

```bash
# Giocare con la UI Textual (host opt-in) / calibrare dal browser — launcher a un click
./gioca.bat
./calibra.bat

# Giocare un incontro headless (driver di riferimento)
PYTHONPATH="src;vendor" .venv/Scripts/python.exe -m main   # Windows/PowerShell: usa ; nel PYTHONPATH

# Suite completa (headless, senza rete)
.venv/Scripts/python.exe -m pytest -q

# Integrazione live Anthropic (opzionale): imposta la chiave PRIMA (mai in repo/log/URL)
#   $env:ANTHROPIC_API_KEY = "..."   poi   pytest -q
```
