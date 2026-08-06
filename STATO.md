# STATO DEL PROGETTO — dove siamo, i branch, come proseguire oltre il pre-MVP

> **Cos'è questo file.** Non è una spec normativa (quelle stanno in `docs/`, vedi
> `progetto-indice-decisioni.md`). È il **punto di situazione operativo**: ti dice in che
> stato è il codice *rispetto* alla documentazione, tiene la mappa dei branch, e fa da
> **base di ripartenza** per continuare verso (e oltre) l'MVP. Vive alla radice del repo
> ed è **versionato** (a differenza di `docs/`, che è in `.gitignore`).
>
> **Aggiornalo** quando: chiudi una fase, crei/fondi un branch, o prendi una decisione che
> diverge da `docs/`. Ultima revisione: **2026-08-06** — **Mossa 2**: scelta della mossa,
> economia mana/cooldown, e i contratti posati prima delle feature che romperebbero
> l'MVP (vedi §2.3). Prima: le guardie delle fondamenta (§2.2) e il travaso del sistema
> di gioco (§2.1 — contenuti come asset, tick degli status, TTK tarato, persistenza
> riparata). Il delta più vecchio (calibrazione per-entità, console web, drenaggio
> unificato, Mappa) resta tracciato in **`README.md`**.
>
> **Divisione del lavoro fra i branch** (decisione dell'utente, 2026-08-04):
> `react-ecosystem` è il **laboratorio** — ci si gioca, ci si vede l'evoluzione, ci vive la
> SPA React e il suo host HTTP. `headless-game-engine` è il **prodotto**: il motore di
> gioco, che qui si porta avanti fino a diventare vendibile. Dal laboratorio al prodotto
> passa **solo il sistema di gioco**, mai la presentazione (vedi §2.1 per cosa resta fuori).

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

**Verifica:** **497 test verdi + 2 skip** (i 2 skip = integrazione live Anthropic, saltata senza `ANTHROPIC_API_KEY`). "Giocabile capo-a-fine" dimostrato headless con provider deterministico: `python -m main` fa narrazione → scontro → status → vittoria → stanza successiva.

**Fuori scope per scelta (non ancora fatto):** i **numeri** d'economia ancora da tarare oltre il TTK (Gruppo 2 §11), il **replay completo**, e le feature **post-MVP** dichiarate (vedi §4).

---

## 2.1 Travaso del sistema di gioco da `react-ecosystem` (2026-08-04)

`react-ecosystem` aveva accumulato 5 commit sopra questo branch, misti motore + front-end.
Qui è atterrato **solo il sistema di gioco**; l'host HTTP e la SPA sono rimasti là.

**Cos'è entrato** (~1.900 righe di motore, +71 test → 497):

- **I contenuti diventano dato.** Archetipi, mob, piani e stagioni sono asset JSON in
  `contenuti/` (`contracts/contenuti.py` + `motore/design.py`): l'enum compilato
  `Archetipo` lascia il posto a uno **slug con chiusura per-run** (registry congelato nella
  `StagioneAttiva`, F-6 validato a runtime dal gate — emendamento D1). Un archetipo nuovo è
  un file, non una riga di codice, ed è dimostrato da un test di fetta verticale.
- **Quarto strato di gate** (D5): `EntitaGenerata.riferimento` permette all'AI di
  *reclutare* un mob dal cast del piano — un nome da un set chiuso, mai un numero; fuori
  cast → fallback F-13.
- **Il tick degli status non è più un no-op** (era il primo punto aperto di §4.1): tabella
  unica `SPEC_STATUS`, innato vs afflizione, trasmissione col colpo, durate come foglie §11
  generate dall'enum `Blocco`.
- **Mosse come catalogo-dato** (`motore/mosse.py`) eseguito dai system via componente
  `Repertorio`: gli asset scelgono chiavi, i numeri restano del motore.
- **TTK tarato** (`pv_base` 6/8/5 → 15/18/12) con `tests/test_ttk.py` come lucchetto.
- **Persistenza riparata:** `ActionPoint` nel registry dei tag, `rng_state` davvero
  serializzato, guardia contro il save a scontro aperto, mob di scena persistente col
  legame stanza↔mob passato dal dato.
- **Fix della fuga** (FNC §4): non distrugge più il mob della stanza — fuggire non è più
  strettamente migliore che vincere.
- `SistemaCrollo` finalmente **cablato** nel bucket dei sistemi: la rete di terminazione
  G-L1 è attiva in run, non solo nei test.

**Cosa NON è entrato, di proposito:** `src/host_web/` (host FastAPI), `web/` (SPA React),
i 7 file `tests/test_host_web_*.py`, e le dipendenze `fastapi`/`uvicorn`/`httpx`.
`requirements.txt` resta quindi **Pydantic e basta** — l'invariante "nessuna dipendenza di
UI nel motore" regge per costruzione, non per disciplina.

**Debito noto entrato col travaso** (da un audit del delta, in ordine di peso):

1. **I numeri autorati non hanno tetto.** `ProfiloArchetipoDati` valida la *presenza* dei
   campi, mai la *magnitudine*: chi scrive un asset può mettere `pv_base=99999`.
   L'invariante "l'AI non emette numeri" è difeso sulla porta in-run, non su quella di
   authoring. Serve una banda derivata dal catalogo §11.
2. **Due proprietari della mutazione HP**: `status._applica_delta_hp` e
   `combattimento.infliggi_danno` scrivono lo stesso campo con clamp diversi.
3. **Il lucchetto TTK copre 2 gradi su 6**; dal platino in su il protagonista muore senza
   chiudere lo scontro, e nulla lega il `Grado` alla profondità del piano (rischio G-L2).
4. **`src/main.py` è passato da 508 a 1360 righe**: il composition root ha assorbito la
   gestione della libreria contenuti. Va spaccato in pacchetto (taglio di file, non
   refactor): `libreria/`, `authoring/`, `sessione.py`.
5. Gli **alias storici** dei sistemi-status (`SistemaVeleno`, …) sopravvivono accanto a
   `sistemi_status()`: cablarli insieme farebbe ticcare due volte lo stesso status.
6. ~~`SCHEMA_VERSION` fermo a 1~~ — **chiarito** (§2.3): il numero non si alza per
   esercizio, e il meccanismo di migrazione è ora *provato*. Si alzerà col primo
   cambio di forma reale.

---

## 2.3 Mossa 2 — il loop di gioco: scelta, economia, contratti (2026-08-06)

Il travaso successivo dal laboratorio. La valutazione di prodotto aveva misurato che
il gioco non aveva un loop: combattere era puro costo (95% di morti giocando da
dungeon crawler, contro 90% di vittorie fuggendo sempre), il combattimento era un
bottone senza input, non esisteva progressione. Qui atterrano i primi due sblocchi
e la superficie contrattuale che regge il resto.

**IL GIOCATORE SCEGLIE LA MOSSA.** Il menu di combattimento non è più una costante:
lo compone `IstanzaCombattimento` dal `Repertorio` del protagonista (una voce per
mossa + "Fuggi" sempre ultima). Prima `_scegli_azione` risolveva il repertorio e lo
SCARTAVA alla riga dopo con `mossa = "attacco"`. Il canale è il gemello esatto della
fuga: `StatoCombattimento.mossa_richiesta` + `richiedi_mossa(chiave)`, che valida
catalogo E repertorio E pagabilità. Il protagonista ora PORTA le sue mosse
(`Repertorio` persistente): il repertorio crescerà con la run e viaggia nel save.

**L'ECONOMIA DELLE MOSSE.** `Mana(attuale)` posseduto e persistente, col massimo
DERIVATO da Intelligenza (`max_mana`, stessa dottrina di `max_hp`); `Ricariche`
effimero per-scontro (mai nei save, si azzera da solo). `attacco_pesante` costa 2
mana e 2 turni di ricarica: smette di essere strettamente dominante. Nuovo
incantesimo `dardo_arcano` (3 mana, danno FUOCO — nessun tipo nuovo nel vocabolario
chiuso). Il rifiuto ha DUE cinture e non spende mai il turno: la porta respinge il
click non pagabile, e il risolutore degrada all'attacco base se lo stato è cambiato
fra click e risoluzione. GR2-14 emendato: il divieto proteggeva dal *corpo
anticipato*, non dalla feature — resta vietato un `SistemaSkill` separato, e un test
verifica staticamente che nessun modulo fuori dal risolutore scriva `Mana.attuale`.

**I CONTRATTI, PRIMA DELLE FEATURE CHE ROMPEREBBERO L'MVP.** Criterio dell'utente:
«facciamo spazio prima di chiudere i bocconi, così evitiamo di dover rompere il
pavimento per rifare le tubature».
- `Terminale` passa da `guscio.macchina` a `contracts`; `SnapshotVista` porta
  `terminale` e `profondita`. È ciò che permetterà di distinguere «sceso di un
  piano» da «vinto» — prima l'unico accesso era `guscio._terminale`, un privato.
- `SkillVista`, `EquipVista` + `SlotEquip` (enum chiuso), `ProgressioneVista`:
  la scheda dichiara skill, equipaggiamento e progressione. **Alcuni sono vuoti di
  proposito** — non esistono oggetti né esperienza — ma il contratto c'è: quando
  arriverà il contenuto si riempie un campo, non si rinegozia un'interfaccia.
- `TipoAzione.RIPOSA` + la foglia §11 obbligatoria (trappola: `DURATA_AZIONE` itera
  tutto l'enum all'import); `RiposoConcluso` con la sua riga di cronaca.
- **Un lucchetto nuovo per gli eventi**: ogni sottoclasse di `EventoDominio` deve
  avere una riga in `_MAPPA_EVENTI`. Un evento dichiarato e non raccontato nasce
  MUTO. Le azioni avevano già questa rete, gli eventi no.

**Sul versionamento dei save** — la lezione più utile del ciclo. Un primo tentativo
aveva alzato `SCHEMA_VERSION` a 2 con una migrazione che dava `livello` ai mob privi
del campo: ma `livello` è obbligatorio senza default in `EntitaMob` dal primo
commit, quindi il ramo era irraggiungibile. Il bump avrebbe timbrato a v2 ogni save
esistente senza cambiarne un byte, **bruciando lo slot v1→v2** per la migrazione vera
che un giorno servirà. Il numero è tornato a 1: **un bump è l'identità di un formato,
non un esercizio**. Il meccanismo si prova per INIEZIONE (`migra` accetta già
`migrazioni=`/`versione_corrente=`) — 8 lucchetti su ordine dei passi, cumulatività,
rifiuto del futuro, buco nella catena, più `test_nessuna_migrazione_inerte` che vieta
di ripetere l'errore.

**Verifica:** **574 verdi + 2 skip** sul prodotto (611 sul laboratorio, la differenza
sono i 37 test dell'host). `python -m main` gioca capo-a-fine. Il save reale scritto
prima di questo ciclo si carica ancora, con gli HP preservati e il mana riparato lazy.

**Cosa resta della Mossa 2** (sul laboratorio, poi qui): fuga con prova vera e colpo
d'opportunità; secondo piano; riposo che costa tempo + imboscata; il playtest che
misura se combattere ha smesso di essere una perdita.

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
e09f27e  Ritorno a headless: rimozione dell'adattatore Textual
   │
6d4ab35  Backend Anthropic e OpenAI + gestione chiavi API ..... ◀── main
   ├───────────────┐
   │               │
   │           8d37ffa..  React ecosystem: host web + SPA ...... ◀── react-ecosystem  (LABORATORIO)
   │                       (5 commit: asset, combat feel, fuga, archetipi)
   │
[travaso del solo sistema di gioco] ......................... ◀── headless-game-engine  ★ ATTUALE (PRODOTTO)
```

| Branch | Contenuto | Ruolo |
|---|---|---|
| **`headless-game-engine`** ★ | Il **motore di gioco** e nient'altro: `contracts` + `motore` + `guscio` + composition root + contenuti + i suoi test. Unica dipendenza viva: **Pydantic**. | **Il prodotto.** È qui che il motore si porta avanti fino a diventare vendibile. Nessun host, nessuna UI, nessun framework web. |
| `react-ecosystem` | Tutto il motore **+** host HTTP (`src/host_web`, FastAPI) **+** SPA React (`web/`). | **Il laboratorio.** Ci si gioca e si vede l'evoluzione del gioco. Il motore che matura qui viene travasato nel prodotto; la presentazione resta. |
| `main` | Allineato a `6d4ab35`. | **Indietro** rispetto a entrambi. Va portato avanti quando il motore è accettato. |
| `v1-textual-implementation` | `main` storico + **UI Textual** (nodo C, fasi 9–10). | **Archivio.** Riferimento se si volesse riesumare una TUI. |

> **La regola del travaso:** dal laboratorio al prodotto passano solo `src/contracts`,
> `src/motore`, `src/guscio`, `src/main.py`, gli strumenti del motore a sole stdlib
> (`banco_nemici.py`, `calibratore_web.py`), `contenuti/` e i test **non** `test_host_web_*`.
> Non passano mai: `src/host_web/`, `web/`, e le dipendenze che si portano dietro. Se un
> giorno un test del motore avesse bisogno di `httpx`, quello è il segnale che qualcosa di
> host è colato dentro.

---

## 4. Base per continuare oltre il pre-MVP

### 4.1 Da fare per *chiudere* l'MVP (resta dentro lo scope dichiarato)
- **Gruppo 2 — economia: i NUMERI.** La *forma* (2a+2b+tipi) è atterrata (vedi §2); restano i
  **valori §11**, centralizzati e marcati in `motore/calibrazione.py`: costanti del check 1
  (`s`, `F`, `δ`, `g`, `MIN_COLPO`), curva HP/TTK, soglia escalation, cap-resistenze, basi-archetipo,
  + tabelle di budget/anomalie, numeri degli status, soglie classi di prova, `Durata → carico-tick`.
  Vincolo: l'AI non emette numeri — il motore li deriva (gate catalogo+budget). I due **property-test**
  del check 1 (`tests/test_calibrazione_check1.py`) sono la rete che li vincola.
- ~~**Tick degli status**~~ — **FATTO** col travaso (§2.1): tabella unica `SPEC_STATUS`, un
  system per riga generato da `sistemi_status()`, durate come foglie §11. Resta da portare a
  §11 anche il `delta_per_rango` (oggi letterale nella tabella) e da ritirare gli alias storici.
- **Calibrazione del gate del nodo A** (G-L1 "ogni scontro termina", G-L2 "ogni piano
  completabile") con i numeri reali del Gruppo 2, non solo con gli stub. Il TTK è tarato per
  bronzo/argento; **dal platino in su lo scontro non termina** (vedi debito §2.1 punto 3).
- **Chiudere la porta numerica dell'authoring** (debito §2.1 punto 1): finché un asset può
  scrivere `pv_base=99999`, "i numeri li deriva il motore" vale solo per l'AI in-run.

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
