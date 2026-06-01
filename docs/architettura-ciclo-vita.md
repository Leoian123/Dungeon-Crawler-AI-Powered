# Architettura e ciclo vita — Nodo **E** (regole strutturali del programma + indice del runtime)

> **Spec normativa per Claude Code.** Chiude il nodo **E**. Non descrive meccanismi: fissa le **regole architetturali/strutturali** del programma e fa da **indice del runtime**, puntando ai documenti che possiedono i singoli meccanismi. È il documento di **rango più alto** sull'asse architettura: gli altri lo ereditano come IC/PLK ereditano da ESP/FNC.
>
> **Presuppone e non duplica** `esper-implementazione.md` (ESP), `fasi-narrazione-combattimento.md` (FNC), `interfaccia-contratto.md` (IC), `provider-llm-key.md` (PLK). In caso di conflitto, valgono quei documenti per ciò che è di loro competenza; questo fissa solo E. **Eccezione dichiarata:** E **qualifica** FNC §4 sul punto degli esiti di `CombatResolved` (§5.1) — non è un conflitto da risolvere a favore di FNC, è un raffinamento che FNC non aveva scritto.
>
> **Convenzione di rimando.** `§N` *senza prefisso* = sezione di questo documento. Rimandi prefissati: **ESP §N**, **FNC §N**, **IC §N**, **PLK §N**.
>
> **Principio guida di questo documento:** *colloca e punta, non descrivere.* E dice **cosa vive, in che contesto, con quale primitiva di transizione** — e per il *come* rimanda al proprietario del meccanismo. Dove un altro documento possiede il meccanismo, E ci punta; non lo rispecifica. Ciò che E possiede in proprio è il **ciclo vita cross-World** — il frame *dentro cui una run esiste* — che nessun altro documento modella.

---

## 0. Premesse ereditate (non rinegoziabili qui)

- **ECS = esper**, vendorizzato, Python pinnato, solo API a livello di modulo (`esper.World()` vietato). *(ESP §0)*
- **Stato globale isolato**; il livello save/load è l'**unica autorità su `current_world`**; non si elimina il contesto attivo → si **switcha *poi* si elimina**. *(ESP §0.1)*
- **Bus tipizzato di progetto** sopra esper: eventi come dataclass, handler con riferimenti forti, sottoscrizione per tipo; la logica di dominio non vede mai il dispatcher nativo di esper. Lo **scope** del bus è una scelta di progetto, non eredita dal dispatcher di esper → la fissa E (§5.2). *(ESP §5)*
- **Due fasi sequenziali ed esclusive** dentro la run, transizione **solo** via evento tipizzato sul bus; **World unico** per l'intera run, phase-gate, tre bucket; il protagonista persiste oltre il confine di fase. *(FNC §3, §4, §6)*
- La **fase corrente** è un componente-singleton (`FaseCorrente`) nel World, che si serializza col save. *(FNC §6.1)*
- `switch_world` è **riservato a contesti realmente separati** (menù, schermate fuori-run), non alle fasi della run. *(FNC §6.3)*
- **Async sì, thread no**; Textual possiede il loop; logica di orchestrazione in **coroutine host-agnostiche**, schedulazione/lifecycle a un worker sottile; `process()` guidato dal **turno**, non dall'orologio. *(IC §6, FNC §7, §6.4)*

Se una di queste non è chiara, fermarsi e rileggere i documenti a monte prima di implementare quanto segue.

---

## 1. La premessa fondante (perché E esiste)

Il programma non è "il gioco" più qualche schermata di contorno: **è l'interezza dei componenti e di come dialogano, attraverso i contesti.** Quel dialogo ha **due regimi**, e solo uno è già posseduto.

- **Intra-World — emergente.** Pull sui componenti, bus tipizzato, phase-gate (ESP, FNC §6). Non è un oggetto "macchina a stati" a sé: è ciò che **accade** girando i Processor con `FaseCorrente`. La macchina `NARRAZIONE ⇄ COMBATTIMENTO` di FNC §3 vive interamente qui ed è **legittimamente assorbita** da ESP/FNC. **E non la rispecifica: ci punta.**
- **Inter-World / ciclo vita — non-emergente.** Boot, nascita e teardown dei World, nascita/deserializzazione del protagonista, `switch_world`, e le **cuciture run→guscio** (sconfitta, vittoria/piano-completato, uscita volontaria). **Nessun Processor lo possiede**, perché i Processor vivono *dentro* un World e queste transizioni **attraversano i contesti**. Questo control flow è senza proprietario, ed è **prior** a F/G/H/IC, che presuppongono tutti che una run *esista già*. **È il territorio proprio di E.**

> La macchina-guscio è: **boot → menu/slot → run → (sconfitta | piano-completato | uscita volontaria) → menu.** Una versione precedente di questo documento aveva solo l'uscita di perdita: era un'asimmetria, perché l'MVP è "una fetta verticale **completa** di un singolo piano" (nodo A) e *completare il piano* è il terminale di successo — anch'esso una transizione run→guscio.

> FNC §3 dice "macchina a stati al livello più alto" riferendosi alle due fasi — ma quella è la macchina *dentro* la run ("Insieme = la run; sottoinsiemi = le due fasi"). Il livello davvero più alto non era modellato da nessun documento. E lo modella.

---

## 2. I due criteri di attribuzione (la procedura decidibile)

Le due regole che decidono, per **qualsiasi** stato o transizione — anche futuri, non ancora immaginati — a quale macchina appartiene e quale primitiva usa. Sono decidibili: un agente le applica senza interpretare.

**Criterio 1 — primitiva di transizione.**
> Si usa `switch_world` **se e solo se** lo stato condiviso **non deve** sopravvivere alla transizione. Altrimenti (deve sopravvivere) la transizione resta **nello stesso World** e passa per un **evento tipizzato sul bus**.

Questo unifica i due passaggi di FNC che sembravano scollegati. Fra fasi, il protagonista deve sopravvivere → World unico, mai `switch_world` (FNC §6). Fra guscio e run, *vuoi* il taglio netto: nuova partita = nessuno stato di run precedente deve restare; caricamento = la run si ricostituisce da disco in un contesto pulito (FNC §6.3). Stessa primitiva, regola opposta, **un solo principio**.

**Criterio 2 — attribuzione di uno stato.**
> Uno stato è **in-run** **se e solo se** si serializza col save della run. Se non finisce nel blob salvato, è **stato del guscio**.

`FaseCorrente` è un componente-singleton nel World e per costruzione si serializza col save (FNC §6.1) → **in-run**. Lo stato del guscio (in quale schermata sei, quale run esiste, se sei a game-over) **non può** stare nel blob salvato: è la cosa che *decide* di caricare quel blob → **guscio**. Il test è secco: *si serializza col save di una run?*

---

## 3. Le due primitive di transizione (e dove ciascuna è legittima)

Conseguenza diretta del Criterio 1, scritta come divieto perché è il punto dove un agente sbaglia:

| Primitiva | Legittima **solo** per | Vietata per |
|---|---|---|
| **Evento tipizzato sul bus** | transizioni **intra-run**: confine di fase (`EncounterStarted`, e `CombatResolved` con esito **vittoria/fuga** → ritorno a `NARRAZIONE`, §5.1): il protagonista sopravvive, World unico | il confine guscio↔run (lo stato condiviso non deve sopravvivere → serve `switch_world`) |
| **`switch_world`** | il **confine guscio↔run** (nuova partita, caricamento, teardown ai terminali della run): unico posto legittimo, FNC §6.3 | le fasi `NARRAZIONE ⇄ COMBATTIMENTO` (violerebbe FNC §6) |

> **Le due violazioni-tipo da bloccare.** Modellare il save-menu, la sconfitta o il piano-completato come "una fase con un evento sul bus" viola FNC §6.3. Modellare `NARRAZIONE ⇄ COMBATTIMENTO` con `switch_world` viola FNC §6. Sono lo stesso errore visto dai due lati: scambiare le primitive.

---

## 4. La spina del runtime (indice, non meccanica)

La macchina-guscio + la run, come **tabella di puntatori**: una riga per stazione, taggata col **regime** (guscio / in-run, e le transizioni che li attraversano), la primitiva di transizione in ingresso, il proprietario del meccanismo, e l'eventuale valore aperto. E **colloca e punta**; non descrive i meccanismi (vivono dai proprietari).

| # | Stazione | Regime | Transizione in ingresso (primitiva) | Proprietario del meccanismo | Valore aperto |
|---|---|---|---|---|---|
| 1 | **Boot** | guscio | — (process start) | Textual possiede il loop; **bus process-global costruito qui**, app-level (§5.2) — *IC §6* | — |
| 2 | **Menu / slot** | guscio | transizione di **orchestrazione** (non `switch_world` — §7) | save/load → **H** | slot singolo vs multipli → **H** |
| 3a | **Ingresso run — nuova partita** | guscio → run | **`switch_world("run")` dal default World** (Crit. 1: nessuno stato di run precedente sopravvive) | E *colloca*; il protagonista **nasce** (§6) | profondità creazione personaggio → **G** |
| 3b | **Ingresso run — caricamento** | guscio → run | **`switch_world("run")`** + deserializzazione nel contesto pulito | **H** (deserializzazione + autorità su `current_world`); il protagonista è **deserializzato**, `FaseCorrente` torna col save | formato/slot save → **H** |
| 4 | **In-run** (`NARRAZIONE ⇄ COMBATTIMENTO`) | in-run | **evento tipizzato sul bus** (`EncounterStarted`; `CombatResolved` vittoria/fuga → `NARRAZIONE`) | *FNC §6 + IC §7.1* (emergente: phase-gate, tre bucket, coda intenti) — **E non rispecifica** | cadenza del tempo in narrazione → **G** |
| 5 | **Save mid-run** | in-run | **nessuna** transizione di contesto: il run-World **sopravvive** (Crit. 1) | seam → **H**; `FaseCorrente` serializzata col resto | quando si salva (comando / checkpoint) → **H** |
| 6a | **Terminale — sconfitta** | in-run → guscio | detection in-run (`CombatResolved(sconfitta)` sul bus) → **cede il controllo alla shell** → §7 | **E possiede l'hand-off** (§5) | destinazione: game-over→menu vs reload → **G/H** |
| 6b | **Terminale — piano completato** (vittoria) | in-run → guscio | detection in-run (condizione di successo, trigger di **G**) → **cede il controllo alla shell** → §7 | **E possiede l'hand-off** (§5); il trigger è di **G** | destinazione: schermata vittoria / menu → **G/H** |
| 6c | **Terminale — uscita volontaria** (salva-ed-esci) | in-run → guscio | intento del giocatore → save → **cede il controllo alla shell** → §7 | **E possiede l'hand-off** (§5) | **se è nell'MVP** → **H/scope** (§8) |
| 7 | **Teardown run** | run → guscio | **`switch_world(default)` *poi* `delete_world("run")`** (Crit. 1; ESP §0.1: non si elimina il contesto attivo) | *ESP §0.1* disciplina; E *colloca* il bersaglio (il default World, §7) | — |
| 8 | **Process end** | guscio | cancellazione dei worker in volo | *IC §6* | — |

Lettura del taglio, sulla riga 5: E dice *"è in-run (Crit. 2), il run-World sopravvive (Crit. 1), seam posseduto da H"* — tre puntatori, **zero** meccanica di serializzazione. Quella è di H.

---

## 5. I terminali della run e le cuciture run→guscio

### 5.1 Quali esiti restano in-run, quali escalano (qualifica di FNC §4)

FNC §4 scrive `CombatResolved → torna in NARRAZIONE` con l'esito (vittoria/sconfitta/fuga) come payload. Preso alla lettera, *tutti* gli esiti tornerebbero in narrazione e nessun terminale di run scatterebbe mai. E **qualifica** FNC §4 (e lo dichiara, §0):

| Esito | Conseguenza | Macchina / primitiva |
|---|---|---|
| `CombatResolved(vittoria)` | torna a **`NARRAZIONE`** (hai vinto lo scontro, continui a esplorare) | in-run, **bus** — *FNC §4 vale* |
| `CombatResolved(fuga)` | torna a **`NARRAZIONE`** (fuga dal combattimento riuscita, FNC §5.3) | in-run, **bus** — *FNC §4 vale* |
| `CombatResolved(sconfitta)` | **run→guscio** (terminale di perdita) | cucitura, **`switch_world`** (§5.3) — *E qualifica FNC §4* |

> **Vittoria-di-scontro ≠ piano-completato.** Vincere un *combattimento* (`CombatResolved(vittoria)`) ti rimette in `NARRAZIONE`. Completare il *piano* — il contenuto dell'intera fetta verticale (nodo A) — è un'altra cosa: è il **terminale di successo della run**, una condizione in-run il cui *trigger* è di **G** (raggiungi l'uscita, batti il boss di piano, …) e la cui *conseguenza* è run→guscio (stazione 6b). E possiede la **forma** di questo terminale, non il trigger né la destinazione.

In sintesi: i terminali della run sono **tre** (sconfitta, piano-completato, uscita volontaria), tutti run→guscio via teardown (stazione 7); gli esiti di combattimento **vittoria/fuga** non sono terminali — tornano a `NARRAZIONE`.

### 5.2 Il bus è process-global (commit)

Lo scope del bus di progetto è plumbing cross-World → lo fissa E. **Decisione:** il bus è **process-global**, **costruito al boot** (stazione 1) come oggetto a livello app, **fuori da ogni run-World**, e **sopravvive** alla nascita e al teardown dei run-World. Non eredita lo scope dal dispatcher nativo di esper (ESP §5: la logica di dominio non lo vede; lo strato di progetto può anche non appoggiarvisi per gli eventi cross-World).

Conseguenza: un sottoscrittore vive dove serve — gli ascoltatori di dominio in-run sono registrati/rimossi col ciclo vita della run (meccanismo di H/G, non di E); gli ascoltatori cross-cutting che devono durare (es. lo showrunner, FNC §8) stanno a livello app. La detection di un terminale in-run avviene **su questo bus**.

### 5.3 La cucitura della sconfitta (caso lavorato) e l'hand-off

La sconfitta è il caso da lavorare perché il parallelo inganna:

- `EncounterStarted` entra in combattimento: **in-World, sul bus** (Crit. 1: il protagonista sopravvive → niente `switch_world`).
- `CombatResolved(sconfitta)` **non** entra nel game-over allo stesso modo: la sua conseguenza è una **transizione di guscio** (Crit. 1: lo stato di run **non** deve sopravvivere → `switch_world`). **Stesso *trigger-shape*, autorità opposta.**

L'evento e la sua conseguenza vivono su **macchine diverse**; il punto che li ricuce è l'**hand-off**, ed è di E. La sua forma — valida per tutti e tre i terminali (6a/6b/6c):

1. **Detection in-run.** Il terminale è rilevato *dentro* la run, sul bus process-global (§5.2): `CombatResolved(sconfitta)`, la condizione di piano-completato (G), o l'intento di uscita volontaria.
2. **Il run-World non si auto-distrugge.** È il contesto attivo, ed ESP §0.1 vieta di eliminare il contesto attivo e fa del save/load l'unica autorità su `current_world`. Quindi **la run non chiama `switch_world` di se stessa**.
3. **Il teardown lo esegue la shell.** Il run loop, guidato dal turno (FNC §6.4), **cede il controllo** alla coroutine d'orchestrazione che lo aveva avviato (IC §6); è la **shell orchestration** a eseguire il teardown (stazione 7) — `switch_world(default)` poi `delete_world("run")` — **su un confine pulito**, fuori da ogni `process()` in volo.

> **Perché non un handler di guscio che fa `switch_world` dentro il dispatch.** Un handler che reagisse all'evento eliminando il run-World scatterebbe *mentre quel World è attivo e dentro un `process()`*: distruggeresti a metà turno il contesto il cui Processor ha appena emesso l'evento — proprio ciò che ESP §0.1 e FNC §6.4 escludono. Perciò la **detection è in-run** ma l'**esecuzione del teardown è nella shell**, dopo che il loop le ha ceduto il controllo. Che la shell apprenda il terminale via valore di ritorno della run-coroutine o via un proprio handler che ne provoca solo l'uscita dal loop (non lo `switch_world`) è dettaglio sotto il livello di E; il vincolo strutturale è che `switch_world`/`delete_world` **non** compaiano mai dentro un Processor o un dispatch di evento.

### 5.4 Cosa resta ai proprietari

*Cosa significa* morire / completare il piano e *dove si va* (game-over→menu vs reload; schermata vittoria; se l'uscita volontaria è nell'MVP) sono **valori aperti** di G/H (§8). E possiede solo la **forma** delle cuciture, non i trigger di gameplay né le destinazioni.

---

## 6. Lifecycle del protagonista

Il protagonista è l'entità **persistente** su cui lavorano i sistemi *sempre-attivi* (FNC §6.2, §6.3): non è effimero, attraversa il confine `NARRAZIONE ↔ COMBATTIMENTO` **senza migrazioni** (FNC §4, §6). Il suo ciclo vita è **cross-World** → di E:

- **Nasce** al confine guscio→run su **nuova partita** (stazione 3a): il run-World pulito viene creato (`switch_world("run")` dal default) e il protagonista vi è istanziato. *Se* la creazione personaggio avrà effetto meccanico (archetipo/stat di partenza), quella parte tocca catalogo/formula ed è di **G** (§8): E colloca lo *spawn*, non ne fissa il contenuto.
- **Si deserializza** al confine guscio→run su **caricamento** (stazione 3b): il protagonista è ricostruito dal save insieme a `FaseCorrente`; meccanismo di **H**.
- **Esce di scena** a un **terminale** della run (stazioni 6a/6b/6c → teardown 7), col World che lo contiene.

> Invariante: il protagonista **non** viene ricreato a una transizione di *fase*. La nascita/deserializzazione avviene **solo** al confine guscio→run. Una fase che re-istanzia il protagonista è un bug (violerebbe FNC §6).

---

## 7. Dove vive lo stato del guscio — **decisione strutturale**

La macchina in-run ha una risposta elegante per la sua "fase": un componente-singleton nel World (`FaseCorrente`). La macchina-guscio **non può riusarla**: tra una run e l'altra il run-World non esiste (distrutto al teardown), quindi `FaseCorrente` **non ha analogo** al livello guscio. Le due opzioni strutturali:

- **(a) World-menu dedicato** — lo stato del guscio in un singleton dentro un World separato. Conseguenza: le transizioni *interne* al guscio (menu → lista slot → conferma load) diventerebbero altri `switch_world`, e si terrebbe in vita un World che **non fa lavoro ECS** (nessun Processor di dominio) — un World usato come contenitore di variabili.
- **(b) Variabile di orchestrazione a livello app** — lo stato del guscio vive nelle **coroutine host-agnostiche** che IC §6 ha già stabilito come sede del control flow d'orchestrazione. Le transizioni interne al guscio sono semplici transizioni di orchestrazione, **non** `switch_world`.

**Decisione: (b).** Razionale, tutto coerente coi criteri:

1. **Criterio 2.** Lo stato del guscio non si serializza col save della run → è guscio per definizione; non ha motivo di abitare un World (che è l'unità *serializzabile* della run).
2. **Criterio 1 / FNC §6.3.** `switch_world` è per contesti *realmente separati*. Menu → lista slot **non** separa entità/componenti/eventi da isolare: è navigazione di UI/orchestrazione. Usarvi `switch_world` ne diluirebbe il significato proprio (entrare/uscire da una run).
3. **IC §6.** Il guscio è control flow d'app, ed è già lì che il progetto mette il control flow portabile e testabile headless. Un World-menu introdurrebbe un secondo posto dove vive l'orchestrazione.

### 7.1 Il default World è il contesto residente del guscio

esper ha **sempre** un contesto attivo. Fuori da una run, quel contesto è il **default World**: vuoto, **nessun Processor e nessuno stato di guscio** dentro (lo stato del guscio è nell'orchestrazione, decisione (b)). Serve solo perché esper richiede un contesto attivo — è il **parcheggio**, non un contenitore.

Ne discende il flusso preciso, che chiude le stazioni 3a/7:

- **Ingresso run** (3a/3b): dal default, `switch_world("run")` entra nel run-World (creato vuoto al primo switch — ESP §0.1).
- **Teardown** (7): non potendo eliminare il contesto attivo, si fa `switch_world(default)` **poi** `delete_world("run")` (ESP §0.1).
- **Nuova partita dopo un teardown:** `switch_world("run")` con `"run"` già eliminato **ricrea un contesto vuoto** (ESP §0.1) — isolamento garantito tra run successive, esattamente come tra i test.

---

## 8. Cosa E **non** copre (buchi dichiarati, alla FNC §12)

Restano ai proprietari; E li *colloca* nella spina (§4) ma non ne fissa il valore:

- **Profondità della creazione personaggio** (fisso / solo nome / archetipo con effetto meccanico) → **G** (se ha effetto, tocca catalogo+formula). E fissa solo *che* lo spawn avviene al confine guscio→run.
- **Formato e slot di save** (singolo vs multipli; a comando vs checkpoint) → **H**.
- **Destinazione della sconfitta** (game-over→menu vs reload dall'ultimo save) → **G/H**.
- **Destinazione del piano-completato/vittoria** (schermata di vittoria, ritorno al menu, …) → **G/H**. Il *trigger* del piano-completato (cosa conta come "piano finito") è di **G**.
- **Se l'uscita volontaria (salva-ed-esci, stazione 6c) è nell'MVP** → **H/scope**. (IC §7 mette il *prompt salva/carica* in v1; abbandonare una run a metà per tornare al menu è una decisione distinta, accoppiata al modello di save di H e a quello di morte.)

> Questi non bloccano l'architettura di E: la confermano. Sono manopole di gameplay che cambiano il *valore* nelle righe della spina, mai la *struttura* della spina. La struttura dei terminali (tre trigger, una cucitura run→guscio) regge qualunque valore.

---

## 9. Criteri di accettazione (verificabili)

- **E-1** Le due primitive non si scambiano mai: nessun `switch_world` per `NARRAZIONE ↔ COMBATTIMENTO`; nessun evento di bus usato per *entrare/uscire* dalla run. *(Crit. 1; FNC §6/§6.3)*
- **E-2** `switch_world`/`delete_world` compaiono **solo** nel modulo guscio/orchestrazione, ai confini guscio↔run (ingresso, teardown) — **mai** dentro un Processor, un handler di dominio o la logica di fase (statico, grep). *(§3, §5.3, §7)*
- **E-3** Lo stato del guscio **non** è serializzato col save della run: il blob salvato contiene il solo run-World (con `FaseCorrente`); lo stato della macchina-guscio non vi compare. *(Crit. 2)*
- **E-4** I terminali sono un **hand-off**: la detection è in-run (sul bus process-global), ma l'esecuzione del teardown (`switch_world(default)` → `delete_world("run")`) è nella **shell orchestration**, dopo che il run loop le cede il controllo — **mai** uno `switch_world` da dentro un `process()`/dispatch in volo. *(§5.2, §5.3; ESP §0.1, FNC §6.4)*
- **E-5** Il protagonista è istanziato (nuova partita) o deserializzato (caricamento) **esattamente** al confine guscio→run; non è mai ricreato a una transizione di fase. *(§6)*
- **E-6** Il teardown fa **`switch_world(default)` *poi* `delete_world("run")`**, mai delete del contesto attivo; il default World è il contesto residente del guscio (vuoto). *(§7.1; ESP §0.1)*
- **E-7** Lo stato del guscio vive come **orchestrazione a livello app** (coroutine host-agnostica, IC §6), **non** in un World dedicato: nessun World-menu, nessun Processor di guscio. *(§7)*
- **E-8** Ogni "fine run" passa per la **stessa cucitura** run→guscio (stazioni 6a/6b/6c → 7): nessun esito terminale resta in-run senza terminale. Gli esiti di combattimento **vittoria/fuga** tornano invece a `NARRAZIONE` (bus, in-run). *(§5.1)*
- **E-9** Il bus di dominio è **uno, process-global, costruito al boot, fuori da ogni run-World** e sopravvive ai run-World. *(§5.2)*

---

## 10. Cosa NON facciamo (anti-over-engineering)

- ❌ Modellare le fasi `NARRAZIONE`/`COMBATTIMENTO` con `switch_world` (viola FNC §6).
- ❌ Modellare save-menu, sconfitta o piano-completato come transizioni di bus "intra-run" (viola FNC §6.3).
- ❌ Mettere stato di guscio nel save della run (viola Crit. 2).
- ❌ Far fare alla run lo `switch_world`/`delete_world` di se stessa, o eseguirlo dentro un handler di evento mentre il run-World è il contesto attivo (viola ESP §0.1 / E-4).
- ❌ Un World-menu come contenitore di variabili senza lavoro ECS (§7).
- ❌ Lasciare la **vittoria/piano-completato** senza terminale (l'asimmetria del rilievo: solo l'uscita di perdita modellata — §5.1).
- ❌ Un secondo bus, o un bus che muore/si ricrea col run-World (viola E-9 / §5.2).
- ❌ **Rispecificare** in E i meccanismi di ESP/FNC/IC/G/H — E *colloca e punta*. Se ti accorgi di descrivere *come* si serializza, *come* si risolve un colpo, *come* gira il phase-gate, sei nel documento sbagliato.
- ❌ Riempire in E i valori di gameplay (creazione / slot / morte / destinazione vittoria) — sono buchi dichiarati di G/H (§8).

---

## 11. Invarianti rafforzati da questo documento

- **Due macchine annidate, due primitive di transizione.** `switch_world` **solo** al confine guscio↔run (lo stato condiviso non sopravvive); evento tipizzato sul bus **solo** intra-run (il protagonista sopravvive). Mai scambiarle. *(rafforza FNC §6/§6.3, ESP §0.1)*
- **Attribuzione decidibile.** Uno stato è *in-run* sse si serializza col save della run; una transizione usa `switch_world` sse lo stato condiviso non deve sopravvivere.
- **Tre terminali, una cucitura.** Sconfitta, piano-completato e uscita volontaria sono transizioni run→guscio via teardown; gli esiti di combattimento vittoria/fuga tornano a `NARRAZIONE`. **E qualifica FNC §4** su quali esiti di `CombatResolved` escalano. *(§5.1)*
- **Hand-off, non auto-switch.** Detection del terminale in-run; esecuzione del teardown nella shell orchestration, su confine pulito; mai `switch_world` dentro un `process()`. *(§5.3)*
- **Il ciclo vita del protagonista è cross-World.** Nasce/deserializza **solo** al confine guscio→run; mai a una transizione di fase.
- **`switch_world` ha un solo luogo legittimo.** Il confine guscio↔run; il default World è il contesto residente del guscio. Lo stato del guscio è orchestrazione a livello app, non un World. *(traspone FNC §6.3)*
- **Un solo bus, process-global.** Costruito al boot, fuori dai run-World, sopravvive a essi. *(§5.2)*
- **E colloca e punta.** Il documento di rango più alto sull'asse architettura non possiede meccanismi: indicizza i proprietari.

---

### Nota per l'aggiornamento dell'indice

In `progetto-indice-decisioni.md`:

- **Cruscotto dei nodi:** **E** da 🟡 a ✅. Sintesi: *"Regole strutturali (due regimi di dialogo, due criteri di attribuzione, due primitive di transizione) + indice del runtime come spina di puntatori; macchina-guscio (boot→menu/slot→run→sconfitta|piano-completato|uscita volontaria→menu); tre terminali con una cucitura run→guscio (hand-off: detection in-run, teardown nella shell); E qualifica FNC §4 (vittoria/fuga tornano in NARRAZIONE, sconfitta escala); bus process-global costruito al boot; default World = contesto residente del guscio; stato del guscio = orchestrazione a livello app. Valori di gameplay (creazione/slot/morte/destinazione vittoria/uscita volontaria) rimandati a G/H. Dettaglio in `architettura-ciclo-vita.md`."*
- **Documenti del progetto:** `architettura-ciclo-vita.md` (ACV) da ⬜ a ✅.
- **Nodi aperti → E:** spostare in "Nodi chiusi"; l'unica aperta strutturale interna ("dove vive lo stato del guscio") è **decisa** (orchestrazione a livello app — §7).
- **Punti minori in sospeso → "Bus: process-global o World-scoped?":** **risolto in E** (process-global, costruito al boot, app-level — §5.2). La verifica sul dispatcher di esper resta una nota d'implementazione, ma non cambia la decisione.
- **Ordine di lavoro consigliato:** barrare il punto 3 ("E"). Prossimo: **F** (indipendente da E, contratto in-run); poi **G/H**, che ereditano i buchi di gameplay dichiarati (§8) e, per H, il confine guscio↔run con l'autorità su `current_world`.
