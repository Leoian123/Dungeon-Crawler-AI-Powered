# Fasi Narrazione ⇄ Combattimento — Contratto di autorità e ciclo di gioco

> Spec normativa per Claude Code. Fissa il **punto B** (asse narrazione/meccanica) risolvendolo come architettura a due fasi, e fa da ponte verso E (macchina a stati), F (contratto AI↔motore) e G (combattimento).
> Presuppone e **non duplica** `esper-implementazione.md`. In caso di conflitto, vale `esper-implementazione.md` per tutto ciò che riguarda l'API e le regole ECS.

---

## 0. Premesse ereditate (non rinegoziabili qui)

Questo documento dà per acquisito quanto già deciso:

- **ECS = esper**, vendorizzato, versione di Python pinnata, **solo API a livello di modulo** (mai `esper.World()`).
- **I componenti sono dati puri**; la logica sta solo nei Processor.
- **I sistemi non si chiamano tra loro**: comunicano per componenti ed eventi.
- Gli **eventi di dominio passano sul bus tipizzato del progetto** (dataclass, riferimenti forti, registrazione esplicita), **non** sul dispatcher nativo di esper.
- Dipendenze a senso unico verso il nucleo; i moduli si agganciano, non si innestano a forza.

Se una di queste premesse non è chiara, fermarsi e rileggere `esper-implementazione.md` prima di implementare quanto segue.

---

## 1. Principio guida (invariante del progetto)

**L'AI propone, il motore dispone** — ma va inteso bene, perché è facile fraintenderlo come "narrazione = fase morbida, combattimento = fase dura". Non è così.

**Il motore arbitra SEMPRE l'esito**, in entrambe le fasi. Nessuna conseguenza con poste in gioco (colpo a segno, fuga riuscita, danno, interazione, chi vince) è mai decisa da prosa dell'AI. Questo non cambia mai — vale anche dentro la narrazione (vedi §5.3: "Scappi" è una prova su stat, non una concessione del modello).

Ciò che cambia tra le fasi è **quanta autorità generativa ha l'AI sul *contenuto*** — non sull'esito:

| Fase | Autorità generativa dell'AI (sul contenuto) | Chi arbitra l'esito |
|------|----------------------------------------------|----------------------|
| Narrazione | **Alta**: genera il mondo — stanze, voce, e **entità composte da blocchi noti** (archetipo, rarità, abilità) che diventano reali nell'ECS. Le **statistiche le deriva il motore**, non l'AI (§5.5) | **Il motore** (ogni scelta con poste in gioco → evento di sistema) |
| Combattimento | **Nulla sul piano meccanico**: solo flavor a valle della risoluzione | **Il motore** (tiri, danni, status, vittoria/sconfitta) |

In una riga: l'AI è la **sorgente di varietà del contenuto** (massima in narrazione, solo cosmetica in combattimento); il motore è l'**arbitro degli esiti** (sempre, ovunque). Il combattimento non è il punto in cui *inizia* l'arbitraggio del motore — è il punto in cui l'autorità generativa dell'AI crolla a zero. Vedi §5 per i flussi e §5.3 per l'anatomia di un turno.

---

## 2. Perché il combattimento NON è testo libero (razionale normativo)

Quando l'esito del combattimento è prosa generata, l'arbitro diventa l'LLM — e un arbitro persuadibile è un arbitro rotto. Due patologie note:

1. **Stupro del sistema**: il giocatore negozia ("schivo e contrattacco al punto debole") e il modello, addestrato ad accomodare, concede.
2. **Allungamento del brodo**: niente forza la fine — nessun contatore di turni, nessun HP che precipita.

Il combattimento a turni **non è "più profondità meccanica"**: è lo **spostamento dell'autorità dall'LLM al motore**. Numeri finali, struttura a turni che forza l'avanzamento, esito calcolato e non raccontato.

> **Regola per chi implementa:** non reintrodurre, in nessuna forma, un percorso in cui l'output testuale dell'LLM influenzi lo stato del combattimento. Se ti accorgi di passare al modello lo stato del combattimento *prima* della risoluzione, ti sei sbagliato.

> **Lo stesso rischio si nasconde nella narrazione**, nel punto in cui il giocatore inserisce testo libero (l'opzione `Altro`): se l'AI *risolve* il testo libero invece di convertirlo in un evento per il motore, l'arbitro persuadibile rientra dalla finestra. Vedi §5.4.

---

## 3. L'insieme e i due sottoinsiemi

- **Insieme = la run** (il ciclo di gioco).
- **Sottoinsiemi = due fasi-stato**, ciascuna proprietaria del proprio set di Processor:
  - `NARRAZIONE` (esplorazione + testo generato)
  - `COMBATTIMENTO` (turni, risoluzione deterministica)

Le due fasi sono **mutuamente esclusive nel tempo**: o esplori/narri, o combatti. Mai in parallelo. È una macchina a stati al livello più alto; il confine tra le fasi è un **confine di autorità**.

---

## 4. Il confine = evento sul bus tipizzato

Le fasi non si chiamano tra loro. Si passano il controllo via eventi tipizzati sul bus del progetto:

- `EncounterStarted` → entra in `COMBATTIMENTO`. Payload: partecipanti dello scontro e contesto (chi attacca, dove, eventuale aggancio narrativo).
- `CombatResolved` → torna in `NARRAZIONE`. Payload: esito (vittoria/sconfitta/fuga), stato finale del protagonista, loot/conseguenze.

`EncounterStarted` è solo l'evento di **transizione di fase**. La narrazione produce anche eventi che **restano dentro la sua fase** — prove su stat, interazioni col mondo derivate dal testo libero (§5.3, §5.4). **Non ogni scelta del giocatore cambia fase**: passare al combattimento è uno fra più esiti possibili.

> **Due "fughe" distinte, da non confondere:** il **disimpegno** (§5.3) è una prova in narrazione *prima* di ingaggiare e, se riesce, **non** apre il combattimento; la **fuga dal combattimento** è un'azione *dentro* lo scontro che, se riesce, emette `CombatResolved` con esito `fuga`. Meccaniche diverse: un agente deve implementarle entrambe.

Lo **stato condiviso è l'unico World ECS**: il protagonista (HP, inventario, status) vive lì e attraversa il confine senza migrazioni (vedi §6). Il payload degli eventi trasporta solo *ciò che serve ad aprire/chiudere la fase*, non lo stato persistente.

---

## 5. Flusso dati per fase (il meccanismo, non lo slogan)

L'asimmetria di autorità si traduce in due ordinamenti **opposti** del flusso dati.

### 5.1 Narrazione — AI a monte, gate di validazione a valle

```
input giocatore
   → il MOTORE prepara il contesto: tira l'anomalia (seeded), calcola budget + set ammissibile (§5.5)
      → 1 chiamata LLM strutturata (async, §7), col **budget/set ammissibile NEL prompt** → { prosa, entità:{archetipo, rarità, blocchi}, opzioni }
         → VALIDAZIONE: schema + appartenenza al catalogo + budget   ← gate: ciò che non passa non tocca lo stato
            → il motore istanzia l'entità (stat derivate dalla formula) e applica al World
               → render (prosa + menu)
```

L'AI ha libertà creativa reale sul *contenuto*, ma è incorniciata ai due capi: il motore fissa il budget **a monte** e lo **mette nel prompt** (l'AI lo rispetta solo se glielo dici — senza, non può pescare "dentro" nulla), e valida **a valle** (ciò che non passa si scarta o ripiega, §10). **Una sola chiamata, non tre** — vedi §5.3.

### 5.2 Combattimento — risoluzione a monte, AI a valle

```
azione del giocatore (scelta tra opzioni discrete)
   → motore RISOLVE (deterministico): tiri, danni, status, morte
      → fatti dell'esito (es. "critico, 40 danni, nemico morto")
         → l'AI veste i fatti già decisi di prosa  ← downstream, puramente cosmetico
            → render
```

> L'AI in combattimento **non riceve mai lo stato per decidere**: riceve i **fatti già risolti** per descriverli. È questa precedenza (risolvi → poi narra) che rende lo scontro non-negoziabile, non un divieto astratto.

### 5.3 Anatomia di un turno di narrazione (esempio lavorato)

La fase di narrazione **non è "un blocco di testo"**: è un piccolo ciclo di chiamate AI e risoluzioni di sistema. L'AI ricopre più ruoli nello stesso turno, e solo uno di questi produce dati di gioco.

1. **L'AI masterizza** — prosa d'ingresso nella stanza (il corridoio con le torce, la sala esagonale, l'altare con la Vespa del '98 esposta come un grimorio vivisezionato...). → *output: prosa.*
2. **L'AI genera** — produce l'entità "Slime Mangiascarti": **archetipo, rarità e descrizione**, non statistiche grezze. L'output è **strutturato** (JSON conforme allo schema), validato contro il **catalogo** dei blocchi noti, e istanziato come entità ECS; le **statistiche le calcola il motore** da `(archetipo, rarità, livello)` — §5.5. → *output: scelte categoriali + flavor; i numeri sono del motore.*
3. **L'AI riprende** — prosa che presenta l'incontro (i tre slime, il Rolex digerito nella massa, il crawler in digestione) e **propone le opzioni**: `Combatti`, `Scappi`, `Altro` (testo libero). → *output: prosa + menu di azioni.*
4. **Il giocatore sceglie. Ogni scelta con poste in gioco è risolta da un evento di sistema, mai dalla prosa:**
   - `Combatti` → emette `EncounterStarted` → passa alla fase di combattimento (§4, §6).
   - `Scappi` → **disimpegno**: una prova su stat (giocatore vs slime) *prima* di ingaggiare; **il motore tira e dispone**, e in caso di riuscita si resta in narrazione (il combattimento non si apre). L'AI, al più, *narra* l'esito già deciso. Da non confondere con la *fuga dal combattimento* a scontro iniziato (§4).
   - `Altro` (testo libero) → **fuori dall'MVP** come azione pienamente risolta; nell'MVP è gestito da disclaimer (§5.6). Bersaglio post-MVP: l'AI **non risolve**, classifica e parametrizza in un evento tipizzato che dispone il motore.

Il ciclo (masterizza → genera → riprende → scelta → risoluzione per evento) si ripete finché una scelta non produce `EncounterStarted` — che è **uno** soltanto degli esiti possibili.

> **I tre ruoli sono UNA chiamata, non tre.** "Masterizza / genera / riprende" non sono tre richieste API: sono tre campi di **una sola risposta strutturata** (§5.1), agganciata allo schema del contratto (F). Tre chiamate separate triplicherebbero latenza e costo token — la stessa preoccupazione già sollevata in §5.6.

### 5.4 Due modalità di output AI, due modalità di input giocatore

Per tutto il gioco l'AI ha **esattamente due modalità di output**:

- **Generativo-strutturato** (solo in narrazione): produce dati di gioco (entità, contenuto della stanza) → **schema** → ECS. È un **contratto**, non testo libero. L'AI **non emette numeri**: seleziona da un **catalogo chiuso** di blocchi e i numeri li deriva il motore. Dettaglio in §5.5.
- **Prosa/flavor** (in entrambe le fasi): produce testo → **non tocca mai lo stato meccanico**.

Il giocatore ha **due modalità di input**:

- **Scelta discreta** (`Combatti`, `Scappi`): mappa direttamente su un evento noto.
- **Testo libero** (`Altro`): **fuori dall'MVP** come azione pienamente risolta — vedi §5.6 per la gestione MVP (disclaimer) e il bersaglio post-MVP (classificazione in evento tipizzato). **Vincolo che resta valido in ogni caso**: anche avvisato, il testo libero non deve mai scavalcare l'autorità del combattimento (§1, §2) — può ammorbidire la narrazione, non azzerare gli HP di un nemico.

### 5.5 Generazione di entità: catalogo chiuso, non numeri liberi (Generics + Interfacce)

Il modo ECS-nativo per rendere la generazione un contratto è **togliere i numeri all'AI**. L'AI non scrive statistiche: **sceglie da un catalogo chiuso** e il motore calcola.

Cosa produce l'AI per un'entità:

- **Archetipo** (es. `slime`, `scheletro`) — da un enum registrato.
- **Rarità** e **livello** — categorie discrete ed esclusive (l'eredità diretta delle classificazioni rigide di DCC: il genere ci regala la tassonomia già fatta).

> **Aggiornamento (G §8.1/§8.2).** Il `livello` **non** è più una scelta dell'AI: è la **profondità del piano, posseduta dal motore**, e avanza solo su `DiscesaPiano`. Dove qui sotto si parla dell'AI che "sceglie rarità e livello" o si elenca `livello` fra i campi selezionati dall'AI, va letto come **stato del motore**: l'AI sceglie `archetipo`/`rarità`/`blocchi`, mai il livello. Il campo `livello` è **rimosso dallo schema** (F §2; criterio G-17).
- **Blocchi** di abilità/status, scelti tra **componenti registrati** che soddisfano contratti noti (le "interfacce"): `Veleno`, `Rigenerazione`, `Stordito`... L'AI li **compone**, non li inventa.
- **Campi narrativi**: nome, descrizione, voce. L'**unica** parte davvero libera.

Cosa fa il motore:

- **Deriva matematicamente** le statistiche da `(archetipo, rarità, livello)` tramite formula. Quanto picchia un mob è funzione di rarità e livello, **non** una scelta dell'AI.
- **Istanzia** i blocchi scelti come componenti ECS (la chimera "veleno + stordito + rigenerazione" è solo una somma di componenti).

In termini Java (**analogia didattica, non istruzione di implementazione**): le **Interfacce** ≈ il catalogo di blocchi che implementano contratti noti; il "parametrizzare per archetipo/rarità/livello" ricorda i **Generics**, ma in pratica è una **factory parametrica** + un catalogo di componenti registrati. Per implementare conta la sostanza ECS (factory + catalogo), non l'etichetta. La validazione cambia natura: non *"il numero è nel range?"* ma **"ogni blocco scelto esiste nel catalogo?"**. Selezione fuori catalogo → rifiuto/fallback (§10).

**Guardrail che sopravvive — il budget.** Il clamp non sparisce, sale di livello. Se l'AI sceglie *liberamente* rarità e livello, la superficie negoziabile si sposta soltanto: da "slime da 999999 danni" a "slime **Leggendario livello 99** al piano 1". Quindi anche la scelta categoriale è **bordata da un budget imposto dal motore** — un set ammissibile per contesto (profondità del piano, budget d'incontro). **L'AI pesca dentro il budget, mai a mano libera.**

**Eccezione di genere — l'anomalia (il budget che "impazzisce").** È DCC: ogni tanto l'ingiustizia assurda *deve* capitare — lo scontro fuori scala, il mob che non dovrebbe essere lì. Il budget non è una camicia di forza. La chiave è **chi decide di sforare**: il **motore**, non l'AI. Con bassa probabilità il motore tira un'**anomalia** e sostituisce il budget normale con uno gonfiato, pescato da una **tabella di anomalie definita** — non numeri arbitrari: anche il delirio ha un soffitto, il caos sta nel *quando* e nel *quale*, non in valori a caso. L'AI continua a pescare dentro il budget che riceve; semplicemente, ogni tanto ne riceve uno mostruoso. Due proprietà la tengono coerente col resto:

- È un **tiro del motore, seeded** → resta deterministico e riproducibile in debug (§9): è RNG del motore, non nondeterminismo dell'LLM.
- È **il momento della voce**, ma va emesso bene: il tiro avviene a monte (prep del contesto, §5.1), però l'anomalia **non resta silenziosa lì**. Al momento del *reveal* il motore **pubblica un evento `AnomalyTriggered` sul bus**, e lo showrunner (Canale B, §8) lo narra come lo spettacolo che è (fire-and-forget, read-only). Due canali distinti: il prompt della chiamata principale **sa già** dell'anomalia (così la stanza generata è all'altezza), e il **bus** la annuncia perché la voce reagisca. Il motore decide l'esito, l'AI fa il numero da palcoscenico — il principio del documento nel suo caso più vistoso.

> **Regola:** l'AI non decide **mai** quando il budget salta. Può proporre entità dentro il budget (normale o anomalo) e **narrare** l'anomalia; non può **invocarla**.

### 5.6 Testo libero (`Altro`): MVP via disclaimer, classificazione post-MVP

Il testo libero è ottimo per l'agency ma è il punto da cui rientrerebbe l'arbitro persuadibile (§2). Gestirlo bene richiede valutazione caso per caso ed è **fuori dall'MVP**.

- **Bersaglio (post-MVP):** l'AI **non risolve**; classifica e parametrizza l'intento in un evento tipizzato noto (prova su stat / transizione di fase / interazione col mondo / continuazione narrativa) che **risolve il motore**. Es.: "convinco lo slime a non attaccarmi" → al più una prova (Carisma vs soglia) che **tira il motore**, mai un "ok, non ti attacca".
- **MVP:** l'opzione, se presente, è **gated da disclaimer** e la sua risoluzione resta volutamente non-blindata (può appoggiarsi all'AI). Il disclaimer, mostrato prima dell'uso:

  > **[Attenzione]** Usare questa opzione potrebbe rendere il gioco più semplice e allo stesso tempo alzare drasticamente la spesa di token! **[Attenzione]**

- **Confine duro, valido anche nell'MVP:** per quanto avvisato, il testo libero **non può scavalcare l'autorità del combattimento** (§1, §2). Può ammorbidire la narrazione; non può toccare la risoluzione meccanica di uno scontro (niente HP azzerati, niente loot fabbricato dal nulla).

---

## 6. Strategia World: World unico + **phase-gate** dei Processor (tre bucket)

`switch_world` crea contesti che **non condividono entità, componenti né eventi**. Ma narrazione e combattimento **condividono il protagonista vivo** (HP, inventario, status). Usare un World per fase costringerebbe a serializzare/migrare il giocatore a ogni transizione: attrito inutile e rischio sul determinismo. **Decisione: un solo World per l'intera run**, dove il protagonista persiste.

### 6.1 Come si cambia fase: phase-gate, non "swap"

esper espone **solo** `add_processor(instance, priority)` e `remove_processor(type)`: **non esiste "sospendi"**. Quindi "swap/sospendi" va sciolto in una scelta precisa, altrimenti l'agente improvvisa. Due strade:

- **Remove/re-add** — a ogni transizione rimuovi i Processor di una fase e aggiungi quelli dell'altra. Costo: ri-passi la priorità a ogni `add` (bookkeeping) e **ricostruisci l'ordine dei sistemi a ogni confine** — fragile proprio dove §9 pretende ordine stabile.
- **Phase-gate (SCELTO)** — tutti i Processor restano registrati **una volta sola all'avvio** (ordine fissato una volta → determinismo §9 stabile). Ogni Processor legge la fase corrente e fa `return` immediato se non è attivo in quella fase. Costo: i sistemi non attivi girano a vuoto un tick — irrilevante in un gioco a turni.

Per un turn-based il phase-gate è più sicuro da specificare per un agente e più solido sul determinismo. **Lo adottiamo.**

La **fase corrente è stato di gioco nel World**, non una variabile globale nascosta: vive in un **componente-singleton** (`FaseCorrente`) su un'entità dedicata, così si serializza naturalmente col salvataggio (H). Solo gli eventi `EncounterStarted`/`CombatResolved` (§4) ne cambiano il valore.

**Il check di fase non si replica a mano.** Se ogni `process()` si scrivesse da solo `if fase != ...: return`, la logica del gate sarebbe duplicata su ogni sistema, e un sistema che dimentica il check girerebbe nella fase sbagliata — bug silenzioso, proprio il tipo che §9 vuole escludere. Quindi il gate è **strutturale**: una base-class `PhasedProcessor` tiene `fasi_attive`, e il suo `process()` legge il singleton `FaseCorrente` e delega a un `run()` astratto **solo** se la fase è attiva. I sistemi concreti implementano `run()` e **non sovrascrivono mai** `process()`. Così un sistema non *può* dimenticare il gate.

### 6.2 Tre bucket, non due

La dicotomia "set narrazione / set combattimento" è **incompleta**, perché il protagonista persiste oltre il confine (§4) e con lui i suoi status. Caso secco: ti avveleni in combattimento, `CombatResolved` ti riporta in narrazione — il veleno deve continuare a fare tick? Se `SistemaVeleno` fosse "solo-combattimento", il veleno si **congelerebbe** appena esci dallo scontro. Quindi ogni Processor dichiara **in quali fasi è attivo**, e i bucket sono **tre**:

- **Solo-narrazione**: generazione stanze, parsing dell'input narrativo, ecc.
- **Solo-combattimento**: turni, iniziativa, risoluzione, ecc.
- **Sempre-attivo**: i sistemi che operano sul **protagonista persistente** — tick degli status (veleno, rigenerazione) e, in futuro, fame/timer. Girano in **entrambe** le fasi.

Sotto phase-gate è gratis: "sempre-attivo" = il gate è vero in ogni fase.

**Regola di partizione (un solo proprietario per componente con stato).** I tre bucket aprono una trappola: se `SistemaVeleno` è sempre-attivo e *anche* esistesse un handler di status nel bucket solo-combattimento, in combattimento il veleno ticcherebbe **due volte**. La difesa, esplicita: per ogni componente **con stato che avanza** (es. i turni rimanenti di `Veleno`), **un solo sistema ne possiede l'avanzamento**, attraverso tutti e tre i bucket. Altri sistemi possono *leggerlo*; nessun altro lo muta. (Leggere è libero — sia il combattimento sia il render leggono `Posizione`; il problema è solo chi *avanza* lo stato.) In concreto: il tick degli status vive **esclusivamente** nel bucket sempre-attivo, e il combattimento **non** ha handler di status paralleli.

### 6.3 Entità di combattimento effimere

Le entità di combattimento (nemici, posizioni) sono create su `EncounterStarted` e distrutte su `CombatResolved`: non inquinano lo stato di esplorazione. Il **protagonista non è effimero** — è l'entità persistente su cui lavorano i sistemi sempre-attivi. `switch_world` resta riservato a contesti **realmente separati** (menù, schermate fuori-run), non alle fasi della run.

> **Decisione di gameplay collegata (→ §12):** *cosa* conta come "passo di tempo" in narrazione (ogni azione? ogni stanza?) determina **quando** i sistemi sempre-attivi avanzano (es. quando il veleno ticca fuori dal combattimento). L'architettura a tre bucket lo regge in ogni caso; il valore va fissato in G.

### 6.4 `process()` è guidato dal turno, non dall'orologio

Conseguenza dura del phase-gate combinato con l'async di §7, da inchiodare: su Textual/asyncio un loop ingenuo `while True: esper.process()` farebbe ticcare i sistemi **sempre-attivi sul tempo di parete**, non sui turni di gioco — e il veleno ticcherebbe N volte *mentre aspetti la risposta async dell'LLM*. Quindi:

- In **entrambe** le fasi, `esper.process()` è invocato **una volta per turno/azione risolta**, mai da un timer a frame liberi.
- Il `dt` nella firma `process(self, dt)` è **simbolico** in un turn-based (un "tick di turno", non secondi di parete).
- L'attesa async dell'LLM (§7) tiene viva la UI ma **non fa avanzare il gioco**: nessun `process()` parte finché l'azione non è risolta.

Questo chiude il fianco che l'async aprirebbe: il tempo di gioco scorre per **turni**, non per **frame**.

---

## 7. Concorrenza: async sì, thread no

Due distinzioni da non confondere:

- **Due flussi logici → sì, obbligatori.** Sono le due fasi-stato di §3. Questo è l'unico senso in cui esistono "due flussi".
- **Due thread di sistema operativo → no.** Le fasi sono sequenziali ed esclusive: niente da parallelizzare tra loro. Thread che toccano l'unico World = race condition sullo stato condiviso = distruzione del determinismo imposto da `esper-implementazione.md`. **Vietato.**

Il bisogno reale di concorrenza è **solo la latenza dell'LLM** (non bloccare la UI mentre il dungeon "pensa"). È un problema **interno alla fase di narrazione**, e si risolve con **async/await**, non con un thread. Su Textual (asyncio) lo si ottiene in modo idiomatico: la richiesta è in volo, la UI resta viva, e quando arriva il JSON **validato** la stanza si popola.

> L'async tiene viva la UI ma **non è un clock**: non fa partire `process()`. Il gioco avanza per turni, non per frame (§6.4).

---

## 8. Lo showrunner in combattimento (Canale B)

Il commento sarcastico mentre meni **non è una fase parallela autoritativa**. È un **ascoltatore reattivo sul Canale B**:

- **Read-only** sullo stato: legge eventi di combattimento (danno, critico, morte), non scrive mai sul World.
- **Fire-and-forget**: emette flavor text in modo asincrono.
- Il combattimento **non attende mai** il commento. Se il commento è lento o fallisce, lo scontro procede.

> La voce commenta; non arbitra. Nessun percorso dal Canale B alla risoluzione.

---

## 9. Determinismo (dove vive, dove no)

- Il **motore è deterministico**: ordine dei sistemi, risoluzione, canali deterministici (vedi `esper-implementazione.md`). Per il debug, seed riproducibile.
- L'**unica sorgente di nondeterminismo è l'LLM**, ed è **confinata**:
  - In **narrazione**, il suo output entra solo dopo il gate di validazione (§5.1), entro i limiti dello schema.
  - In **combattimento**, **zero nondeterminismo entra nello stato**: l'LLM tocca solo il flavor a valle (§5.2).

Quindi "determinismo" non significa "LLM deterministico" (impossibile): significa che lo **stato di gioco** evolve in modo deterministico dati gli input, e l'LLM è una sorgente di varietà *bordata e validata*, mai un decisore di stato.

> **Riproducibilità della run ≠ seed da solo.** Il seed rende deterministico il *motore* (tiro dell'anomalia, tiri di combattimento, ordine dei sistemi). Ma *quale* entità nasce dipende dall'output dell'LLM, che è un **input non-deterministico a monte** del tiro. Quindi: riproducibilità piena della run = **seed + cache degli output LLM validati** (§12). Col solo seed è deterministico il motore, non la run.

---

## 10. Gestione dei fallimenti LLM (il gioco non si congela mai)

La latenza è gestita da async (§7); il **fallimento** va gestito esplicitamente. Politica minima:

1. **Timeout** sulla chiamata LLM.
2. **Retry** limitato (es. 1–2 tentativi) su errore di rete o JSON non conforme allo schema.
3. **Fallback deterministico** se i retry falliscono, **distinto per tipo di output**:
   - *Prosa* (masterizza/riprende, flavor di combattimento): testo neutro pre-confezionato; in combattimento il flavor può anche mancare — la risoluzione è del motore e prosegue intatta.
   - *Generazione strutturata* (l'entità della stanza, §5.3 step 2): il testo neutro **non basta**, mancherebbe un'entità valida. Il motore **pesca un archetipo di default dal catalogo, dentro il budget corrente** (§5.5), e procede. Il percorso strutturato non resta mai scoperto.

> Invariante: nessuna fase resta bloccata in attesa dell'LLM oltre il timeout. Il fallimento dell'LLM degrada la *forma*, mai la *giocabilità*.

---

## 11. Invarianti — checklist per chi implementa

**MAI**
- far decidere all'LLM l'esito di un colpo, di uno status o di uno scontro;
- passare al modello lo stato del combattimento *prima* della risoluzione;
- far attendere la risoluzione (o l'avanzamento) del combattimento a testo o commento;
- **permettere che il testo libero scavalchi l'autorità del combattimento** (anche nell'MVP con disclaimer — §5.6);
- **lasciare che l'AI emetta statistiche numeriche grezze**, o scelga archetipo/rarità/livello/blocchi fuori dal catalogo o dal budget d'incontro (§5.5);
- **lasciare che sia l'AI a decidere quando sforare il budget**: l'anomalia è un tiro del motore, seeded (l'AI la narra, non la invoca — §5.5);
- usare thread che toccano il World;
- usare `switch_world` per passare tra narrazione e combattimento;
- **sospendere i sistemi *sempre-attivi* uscendo dal combattimento** (gli status del protagonista devono continuare a ticcare — §6.2);
- **spezzare un turno di narrazione in più chiamate LLM** (è **una** chiamata strutturata — §5.1);
- **duplicare il check di fase dentro i singoli `process()`** (sta nella base `PhasedProcessor` — §6.1);
- **avere due sistemi che fanno avanzare lo stesso componente con stato** (doppio-tick — §6.2);
- **chiamare `process()` da un timer a frame liberi** / far avanzare i sistemi sul tempo di parete (§6.4);
- applicare output LLM allo stato senza validazione di schema.

**SEMPRE**
- ricordare che **il motore arbitra l'esito in entrambe le fasi** (anche in narrazione: la fuga è una prova, non una concessione del modello);
- in combattimento, **risolvere prima, narrare dopo** (l'AI riceve fatti, non stato);
- in narrazione, far **selezionare all'AI** dal catalogo (archetipo/rarità/livello/blocchi) dentro il budget d'incontro, e far **calcolare le statistiche al motore** (§5.5);
- (post-MVP) convertire il testo libero in evento tipizzato risolto dal motore; nell'MVP gestirlo con disclaimer e tenerlo **fuori dall'autorità del combattimento** (§5.6);
- effettuare le transizioni di fase **solo** via evento tipizzato sul bus del progetto;
- usare **phase-gate**: ogni Processor eredita da `PhasedProcessor`, dichiara `fasi_attive` e implementa `run()` (mai sovrascrivere `process()`); la fase vive in un componente-singleton nel World (§6.1);
- garantire **un solo proprietario dell'avanzamento** per ogni componente con stato; il tick degli status sta solo nel bucket sempre-attivo (§6.2);
- invocare `process()` **una volta per turno/azione risolta**; il `dt` è simbolico (§6.4);
- creare le entità di combattimento su `EncounterStarted` e distruggerle su `CombatResolved`;
- passare **budget + set ammissibile nel prompt** della chiamata strutturata (§5.1);
- emettere **`AnomalyTriggered` sul bus al reveal** perché lo showrunner la narri (§5.5, §8);
- su fallimento della generazione strutturata, pescare un **archetipo di default dal catalogo dentro il budget** (§10);
- usare **una sola chiamata LLM strutturata** per turno di narrazione (§5.1);
- gestire latenza con async dentro la narrazione e fallimento con timeout → retry → fallback.

---

## 12. Decisioni ancora aperte (da fissare prima di G — Combattimento)

- **Turn cap / escalation**: meccanismo che garantisce la terminazione di uno scontro (cap di turni, danno crescente, o simile). Da definire in G.
- **Catalogo, formula e budget** (§5.5): l'elenco dei blocchi registrati (archetipi, abilità, status), la formula `(archetipo, rarità, livello) → statistiche`, e il budget d'incontro per contesto. Più la **tabella delle anomalie**, la loro **probabilità** e il **soffitto** del budget gonfiato. Da riempire con G.
- **Classificazione del testo libero** (§5.6): post-MVP, è essa stessa una chiamata LLM strutturata "intento → evento". Robusta solo se il menu degli eventi su cui mappa è **chiuso e noto**; serve una via d'uscita deterministica per gli intenti non mappabili (rifiuto in-fiction o default a continuazione narrativa). Stessa famiglia del turn cap: garantire che ogni input converga su un esito gestibile dal motore.
- **Cadenza del tempo in narrazione** (§6.3): cosa conta come "passo" fuori dal combattimento (ogni azione? ogni stanza?), da cui dipende **quando** i sistemi *sempre-attivi* avanzano (tick degli status). L'architettura a tre bucket lo regge; il valore si fissa in G.
- **Politica di fallback esatta**: numero di retry, durata del timeout, forma del testo neutro di ripiego, e l'archetipo di default per la generazione (§10).
- **Caching delle stanze già generate**: memorizzare l'output validato per non rigenerare al ritorno, e abilitare il replay riproducibile (§9). Tocca anche H — Persistenza.

Questi punti non bloccano l'architettura di questo documento: la confermano e ne sono conseguenze naturali. I nodi 3 e 5 della peer review (chiamata unica, fallback strutturato) sono già **risolti** sopra, perché vincolano direttamente F.
