# Interfaccia-contratto — Nodo **C** (rendering) e membrana motore ⇄ vista

> **Spec normativa per Claude Code.** Chiude il nodo **C** (motore di rendering) e fissa la **membrana** tra motore di gioco e interfaccia: come dialogano, attraverso cosa, e cosa è vietato far passare. Risolve C non come "scelta di un framework" ma come *conseguenza* di **FNC §7** (`fasi-narrazione-combattimento.md`), e ne deriva il vincolo di disaccoppiamento.
>
> **Presuppone e non duplica** `esper-implementazione.md` (regole ECS, bus tipizzato) e `fasi-narrazione-combattimento.md` (due fasi, autorità asimmetrica, async, showrunner). In caso di conflitto, valgono quei documenti per ciò che è di loro competenza; questo fissa solo C e la membrana.
>
> **Convenzione di rimando (importante per un agente che legge più documenti insieme).** In questo file `§N` *senza prefisso* indica una sezione **di questo documento**. I rimandi agli altri documenti sono **sempre prefissati**: **FNC §N** = `fasi-narrazione-combattimento.md`; **ESP §N** = `esper-implementazione.md`. Così il "§7 async" di FNC non si confonde mai col §7 di questo file (portata della vista).
>
> **Principio guida di questo documento:** *spezzare l'atomo.* Prendere il meglio della separazione a strati — il **contratto** stabile e isolato — senza pagarne il costo che non serve ancora — il **trasporto** stile client-server. Contratto adesso, trasporto come opzione futura.

---

## 0. Premesse ereditate (non rinegoziabili qui)

- **ECS = esper**, vendorizzato, Python pinnato, solo API a livello di modulo (`esper.World()` vietato). *(ESP)*
- **Componenti = dati puri**; la logica sta nei Processor; i sistemi non si chiamano tra loro.
- **Eventi di dominio sul bus tipizzato del progetto** (dataclass, riferimenti forti, registrazione esplicita), **non** sul dispatcher nativo di esper. *(FNC §4)*
- **Due fasi sequenziali ed esclusive**, transizione **solo** via evento tipizzato. *(FNC §3, §4)*
- **L'AI propone, il motore dispone**; autorità asimmetrica; *risolvi prima, narra dopo*. *(FNC §1, §5)*
- **Async sì, thread no**; `process()` guidato dal turno, non dall'orologio. *(FNC §7, §9)*

Se una di queste non è chiara, fermarsi e rileggere i due documenti a monte prima di implementare quanto segue.

---

## 1. Decisione C — **Textual**, conseguenza di FNC §7

### 1.1 È una conseguenza, non una scelta in tabella

FNC §7 ha fissato `async`/`await` come modello di concorrenza per la latenza dell'LLM. Il livello di rendering deve quindi essere **nativo asyncio**, o riapri il problema che FNC §7 chiudeva: o blocchi il loop mentre il dungeon "pensa", o innesti l'async a mano su un loop sincrono — cioè ti costruisci il loop a mano, l'altra cosa che FNC §7 evitava. **Textual è asyncio.** Il pattern di FNC §7 — richiesta in volo, UI viva, la stanza si popola all'arrivo del JSON validato — è il suo idioma nativo, non un innesto.

### 1.2 Cosa compra, mappato sulle superfici reali della v1

- **Scroll della narrazione** (log scrollabile, markup ricco) — il protagonista dell'MVP.
- **Menù a opzioni discrete** — la "scelta tra opzioni discrete" di FNC §5.2: focus, keybinding, niente parsing dell'input a mano.
- **Pannelli di stato reattivi** (HP, status, budget di FNC §5.5) — re-render al cambio di stato.
- **Testo ricco** per la voce dello showrunner — Rich sotto il cofano.
- **Layout dichiarativo** (CSS-like) — niente geometrie calcolate a mano.

Ogni widget che Textual fornisce è una pagina di spec in meno da scrivere per l'agente.

### 1.3 Textual si **pinna**, non si vendorizza

Il rigore di ESP §0 (esper vendorizzato) **si traspone, non sparisce.** esper si vendorizza perché piccolo, stabile, quasi senza transitive. Textual **non si può** vendorizzare: grande, con un albero di dipendenze proprio (Rich e altro) e una cadenza di rilascio viva. Vendorizzarlo = possedere un fork che non vuoi.

| Vincolo | Forma |
|---|---|
| Pin esatto | `textual==X.Y.Z` in `requirements`. Mai `>=`, `~=`, range aperti. |
| Transitive bloccate | Lockfile versionato (`pip-compile` / `pip freeze`). |
| Aggiornamento | Evento **deliberato e revisionato**, con criterio di accettazione (§10). Mai `pip install -U` silenzioso. |

> **Textual è l'unica dipendenza "viva" del progetto.** Va marcata come tale: è l'unico punto in cui il mondo esterno si muove, e muoverlo è un'azione revisionata.

---

## 2. La membrana — modulo `contracts` (l'interfaccia-contratto)

### 2.1 Cos'è

Un modulo a sé — `contracts` (o `protocol`) — con **zero dipendenze**: né Textual, né esper, né provider AI. È il **vocabolario** condiviso: le dataclass di evento e di intento, più lo schema del contratto AI↔motore (nodo F). Motore e vista importano *questo*, e **non si importano mai a vicenda.**

È la versione corretta dell'analogia col layer DB di un'app legacy: l'interfaccia è **stretta**, e ciò che la attraversa sono **DTO semplici**, non oggetti vivi con comportamento.

### 2.2 Cosa attraversa, cosa no

| Attraversa la membrana | Vietato attraversarla |
|---|---|
| Dataclass di dominio (prosa come `str`, lista di opzioni, snapshot di stato) | Renderable di Rich, istanze di widget Textual |
| Intenti tipizzati (`PlayerChoseOption`) | Keystroke grezzi interpretati |
| Fatti d'esito già risolti (FNC §5.2) | Riferimenti al `World`, entità esper vive |

> **Lo "snapshot di stato" è un *input di rendering*, non una verità.** Attraversa la membrana già confezionato, viene **rimpiazzato in blocco** a ogni emissione e **mai accumulato né diffato** lato vista. La fonte di verità resta il `World` (§5, vettore 1): la parola "snapshot" non autorizza la vista a tenerlo e calcolare differenze.

Se il motore consegna un oggetto Textual, l'hai **saldato**. Se la vista riceve un'entità esper, la membrana non esiste più.

### 2.3 Le due direzioni

```
motore → vista     il motore emette EVENTI DI DOMINIO sul bus
                   (RoomRevealed, DamageDealt, CombatResolved)
                   il motore NON importa mai Textual
                       → un adattatore di presentazione sottile si sottoscrive
                         e traduce in chiamate Textual

vista  → motore    i widget emettono INTENTI TIPIZZATI sul bus
                   (PlayerChoseOption(2)), non keystroke
                   i widget NON mutano mai il World
                       → l'intento entra in una coda lato motore (§7)
                         e viene processato sul turno del motore, nella fase corrente
```

> La UI intera è il pattern dello **showrunner** (FNC §8) scalato: consumatore *read-only* di eventi di dominio + produttore di intenti. La prova di concetto del disaccoppiamento è già in casa.

### 2.4 L'adattatore di presentazione è il modulo più pericoloso — blindalo su entrambi i lati

L'adattatore è l'**unico** punto che importa Textual *e* si sottoscrive agli eventi di dominio: è l'asimmetria della membrana, ed è esattamente lì che un agente, "per comodità", infila un accesso al `World`. Il suo profilo di dipendenze va vincolato al millimetro come quello di `contracts`:

- L'adattatore importa **solo `contracts` + Textual**. **Mai** esper / `World` / Processor.
- Traffica in eventi e intenti (DTO del contratto), non in entità vive.
- È stateful in modo legittimo (tiene i riferimenti ai widget), ma quel suo stato è **proiezione**, mai fonte di verità (§5, vettore 1).

Verificabile staticamente quanto C-2 (vedi C-2b in §10). Così la membrana è a tenuta sui **due** lati: il motore non conosce Textual, e l'adattatore non conosce il `World`.

---

## 3. Spezzare l'atomo — **contratto sì, trasporto no**

L'analogia col layer DB impacchetta due cose che vanno separate: un **contratto** (interfaccia narrow e stabile) e un **trasporto** (processo separato, rete, serializzazione). Vogliamo il primo. **Non** vogliamo il secondo — non ora.

| | Cosa | Quando | Perché |
|---|---|---|---|
| **Contratto** | Modulo `contracts` dependency-free; unico canale di dialogo | **Adesso** | Costa poco, disaccoppia subito, è il repository fatto bene |
| **Trasporto** | Serializzazione, envelope, RPC, request/response, processo a sé | **Differito** (opzione, se mai servirà) | Per due oggetti **nello stesso processo, nello stesso loop asyncio** è cosplay di sistema distribuito |

**Il guadagno è asimmetrico e questo è il punto:** il contratto pulito è *esattamente* ciò che rende economico il trasporto domani. Il giorno in cui serve un confine vero (motore-come-servizio, frontend multipli, narrazione come processo), implementi **lo stesso contratto su un trasporto nuovo** e il modulo `contracts` non cambia di una riga.

> **Prendi l'opzione adesso (contratto isolato), eserciti l'opzione dopo (trasporto), se mai servirà.** Costruire il trasporto ora non compra nulla che il contratto pulito non dia già, e costa tutto l'elenco di §8.

---

## 4. Il bus resta **stupido**

Il bus **instrada tipi**. Non decide, non trasforma, non conserva stato, non valida.

- La validazione dell'output LLM sta nel **gate di FNC §5**, non nel bus.
- L'arbitraggio dell'esito sta nel **motore** (FNC §1), non nel bus.
- Se la membrana inizia a validare/tradurre/instradare con logica/tenere stato, è diventata una **terza autorità** — violazione diretta dell'invariante "il motore arbitra". La membrana espone contratti; non li *interpreta*.

> **"Il bus non conserva stato" ≠ "niente conserva stato".** I *sottoscrittori* sono legittimamente stateful: l'adattatore tiene i riferimenti ai widget, lo showrunner una coda di flavor, e il **motore** tiene la coda degli intenti (§7). Lo stato vive negli endpoint, non nel canale. Ciò che è vietato è che lo stato si sposti *nel* bus o che diventi una seconda fonte di verità accanto al `World`.

---

## 5. I cinque vettori di accoppiamento da tenere chiusi

1. **Stato nella vista.** Il `World` esper è l'unica fonte di verità (FNC §6). I widget sono **proiezioni**, mai depositi. Una HP-bar non *è* l'HP.
2. **Motore che chiama il widget.** Nel momento in cui un Processor fa `widget.update()`, il motore conosce Textual. **Vietato** — passa per evento.
3. **Forma dei dati.** Sul bus viaggiano dataclass di dominio, non renderable né widget (§2.2).
4. **Modello dell'input.** La vista traduce l'input grezzo in **intento** prima di metterlo sul bus. Cambi vista, gli intenti restano.
5. **Proprietà del loop async.** Vedi §6.

> Il rischio non arriva tutto insieme: arriva **una riga alla volta**. La reattività di Textual *invoglia* a mettere stato e logica nei widget; ogni scorciatoia salda un pezzetto di motore alla vista. La difficoltà futura di separazione è precisamente quanti `if` di gameplay lasci colare nei callback.

---

## 6. Proprietà del loop asyncio — **logica portabile, schedulazione via worker**

In Textual è **Textual a possedere il loop** asyncio. È l'unico punto davvero appiccicoso, e la regola va spaccata in due — non risolta con un assoluto.

**La logica di orchestrazione vive in coroutine `asyncio` host-agnostiche.** Dipendono solo dalla libreria standard, non da costrutti Textual. Sono portabili e — soprattutto — **testabili headless** (C-5). Questo era il cuore giusto della regola e va tenuto: il flusso "attendo l'LLM → valido → popolo la stanza" non deve sapere cosa lo ospita.

**La schedulazione al confine con Textual passa per un worker sottile.** Un wrapper `@work` / `run_worker` che si limita a fare `await` della coroutine host-agnostica. Non è una contraddizione del punto sopra: separa *dove vive la logica* (coroutine pura) da *come viene schedulata e ripulita* (worker). Senza il worker perdi due cose che servono al progetto:

- **Lifecycle/cleanup.** I worker Textual sono legati al nodo del DOM dove nascono: rimosso il widget o usciti dallo schermo, i task si ripuliscono; all'uscita dell'app i task in corso vengono cancellati. Una `asyncio.create_task()` nuda dentro un'app Textual resta **orfana** allo shutdown.
- **Cancellazione della richiesta superata.** `exclusive=True` (per gruppo, sullo stesso nodo) cancella i worker precedenti prima di avviarne uno nuovo: è il modo idiomatico per **abortire una chiamata LLM in volo** quando il giocatore va avanti mentre il dungeon "pensa". Col plain asyncio te lo gestisci a mano — ed è proprio la classe di bug ("ogni tanto resta appeso") che il resto del progetto combatte.

```
coroutine host-agnostica  (asyncio std-lib, NESSUN import textual)   ← logica, testabile headless
        ▲ await
worker sottile  (@work/run_worker, exclusive per cancellare la richiesta superata)   ← solo schedulazione + lifecycle
        ▲
adattatore di presentazione  (l'unico che importa Textual)
```

> La coroutine host-agnostica deve essere **cancellation-aware ai suoi punti di `await`**: la cancellazione di un worker solleva `CancelledError` al primo `await`, quindi un `await llm_call()` si interrompe pulito, ma un blocco di lavoro sincrono no. In headless, lo stesso flusso gira senza worker (lo invoca direttamente il test/arnia).
>
> **Quando l'agente implementa, verifica l'API Worker corrente di Textual** (`@work` / `run_worker` / `exclusive` / `group` / `cancel`) sulla doc attuale — stessa disciplina imposta per esper e per l'API di Claude: si verifica, non si va a memoria.

> Distinzione critica da non confondere: un *request/response* nel sistema **esiste** — è la chiamata all'LLM **dentro** la narrazione (FNC §7) — ma **non** è la relazione motore↔vista. Quella è asimmetrica ed event-based (FNC §5). Dare semantica RPC al seam motore↔vista significa combattere "risolvi-poi-narra".

---

## 7. Confine, portata della vista (v1) e **coda degli intenti**

- La vista è **solo** rendering + sorgente di input. Non risolve combattimento, non muta il `World`, non chiama l'LLM direttamente.
- L'async vive **dentro la fase di narrazione** (FNC §7), non nei callback dei widget.
- **Portata v1:** scroll narrazione, menù opzioni, pannello di stato, prompt salva/carica. La seduzione del TUI ricco verso decorazione e widget di contorno è **creep** — fuori dalla fetta verticale.

### 7.1 Dove sta l'intento tra l'emissione e il turno — la coda degli intenti

Il widget emette l'intento in un certo istante; il motore lo processa sul **suo** turno. Tra i due momenti l'intento deve stare da qualche parte — e **non** nel bus, che è stateless (§4). Quindi:

- **Coda degli intenti lato motore.** I widget vi accodano intenti tipizzati; il motore la **drena una volta per turno** tramite un **Processor ad alta priorità** che la svuota all'inizio del giro, prima degli altri sistemi.
- Questo rende **C-8 implementabile**: senza un meccanismo dichiarato, "gli intenti sono serviti sul turno, nella fase" è un proposito, non codice.
- In combattimento la coda **non** serve intenti di narrazione al volo: il drenaggio rispetta il phase-gate. Il modello "server sempre in ascolto" (che processa appena arriva) è esattamente ciò che questa coda **evita**.

> **Questa coda non è il "clock parassita" vietato da §8.** La distinzione è la sorgente del drenaggio: questa è **drenata dal turno** (un Processor, una volta per giro) → **legittima**. La coda vietata è quella **drenata sul tempo di parete** (un timer a frame liberi che svuota messaggi mentre aspetti l'LLM) → quella è il clock parassita. Stessa struttura dati, sorgente di avanzamento opposta.

---

## 8. Cosa NON facciamo (anti-over-engineering, esplicito)

Per la membrana **in-process** di un MVP, sono tutti costo senza ritorno:

- ❌ Serializzazione / envelope / formato di messaggio per dati che restano nello stesso processo.
- ❌ RPC o request/response come modello del dialogo motore↔vista.
- ❌ Broker di messaggi, o code **drenate sul tempo di parete** (= clock parassita, collide con FNC §7/§9). *Distinta dalla coda degli intenti drenata dal turno di §7.1, che è legittima.*
- ❌ Concorrenza propria del layer (thread — vietato da FNC §7).
- ❌ Lifecycle di connessione, retry/timeout per chiamate in-process che non possono fallire.
- ❌ Logica/stato/validazione dentro la membrana (§4).

> Ogni strato di indirezione è anche **superficie di spec in più** e altri punti dove l'agente improvvisa. Il deliverable è un documento per Claude Code: l'indirezione non necessaria si paga due volte.

---

## 9. Alternative scartate

- **`prompt_toolkit` + loop asyncio sottile** — async-capace ma più in basso; widget/layout/focus li costruisci tu: molto più codice d'interfaccia *da specificare*.
- **asyncio + ANSI a mano** — dipendenze minime, codice massimo, race input/repaint facili: è il loop a mano che FNC §7 evitava.
- **python-tcod** (l'altro finalista) — orientato a griglia/tile, loop non asyncio-nativo: combatteresti FNC §7. Giusto se la mappa fosse protagonista; qui lo è la narrazione.

Per un MVP narrazione-primaria, il costo di una dipendenza viva (Textual) **abbatte** un costo molto maggiore di spec-e-codice. Il trade è corretto *proprio perché* il deliverable è una spec per un agente.

---

## 10. Criteri di accettazione (verificabili)

- **C-1** `textual` pinnato a versione esatta; transitive bloccate in lockfile.
- **C-2a** Il motore **non importa** Textual in nessun punto (statico: nessun `import textual` fuori dall'adattatore di presentazione).
- **C-2b** L'adattatore di presentazione importa **solo `contracts` + Textual**: nessun `import` di esper / `World` / Processor (statico, simmetrico a C-2a). La membrana è a tenuta su entrambi i lati.
- **C-3** Esiste il modulo `contracts` **dependency-free**; motore e vista importano solo quello, mai l'uno l'altro.
- **C-4** Sul bus viaggiano solo dataclass di dominio/intento: nessun renderable, widget o riferimento al `World`. Lo snapshot di stato è rimpiazzato in blocco, mai diffato lato vista.
- **C-5 (la prova del seam) Modalità headless.** Il motore gira contro il contratto con un adattatore nullo o un'arnia che inietta intenti scriptati e fa `assert` sugli eventi emessi — **senza Textual e senza trasporto**. Se gira headless, il contratto **è** l'unico canale, per costruzione.
- **C-6** La UI **non si blocca mai** durante una chiamata LLM in volo (invariante FNC §7, verificabile al livello di vista); una chiamata superata è **cancellabile** (worker `exclusive`, §6).
- **C-7** Nessun widget muta il `World` né chiama l'LLM.
- **C-8** Gli intenti sono serviti **sul turno del motore nella fase corrente**, mai fuori fase — tramite la **coda degli intenti drenata da un Processor ad alta priorità** (§7.1), non sul tempo di parete.

> **C-5 ha doppio uso:** è lo stesso seam che serve per il **replay riproducibile** (seed + cache degli output LLM validati, invariante di progetto). Stesso test, due garanzie. Per questo è criterio di accettazione e deliverable di fase 1, non un *nice to have*.

---

## 11. Invarianti rafforzati da questo documento

- Il motore arbitra; la membrana **non**. *(rafforza FNC §1)*
- Confine di fase e consegna degli intenti **solo via evento tipizzato, sul turno, nella fase**, attraverso una coda drenata dal turno. *(rafforza FNC §4, §7, §9)*
- Disaccoppiamento **dimostrato** dalla modalità headless, non solo dichiarato. Membrana a tenuta sui due lati (C-2a + C-2b).
- Logica di orchestrazione portabile (coroutine host-agnostiche), schedulazione e lifecycle delegati a un worker sottile.
- Una sola dipendenza viva (Textual), marcata e pinnata; tutto il resto fermo. *(traspone la disciplina di vendoring, ESP §0)*

---

### Nota per l'aggiornamento dell'indice

Alla chiusura di questo nodo, in `progetto-indice-decisioni.md`: **C → ✅**, dettaglio = `interfaccia-contratto.md`; aggiungere il documento alla tabella "Documenti del progetto". Il prossimo nodo naturale è **F** (schema del contratto AI↔motore), che questo documento ha già vincolato (modulo `contracts`, DTO, gate di validazione nel motore).
