# Combattimento, forma della run e gameplay — Nodo **G**

> **Spec normativa per Claude Code.** Chiude il nodo **G**: il loop di combattimento, la forma della run (genere, morte, crawler), le prove di abilità in esplorazione, l'autorità sul livello, e il socket generativo. Raccoglie tutte le voci aperte di **FNC §12** e i buchi di gameplay delegati da **E** (ACV §8) e **F** (contratto-ai-motore §9).
>
> **Presuppone e non duplica** `esper-implementazione.md` (ESP), `fasi-narrazione-combattimento.md` (FNC), `interfaccia-contratto.md` (IC), `provider-llm-key.md` (PLK), `contratto-ai-motore.md` (F) e `architettura-ciclo-vita.md` (ACV). In caso di conflitto, valgono quei documenti per ciò che è di loro competenza; questo fissa solo G.
>
> **Convenzione di rimando.** `§N` *senza prefisso* = sezione di questo documento. Rimandi prefissati: **ESP §N**, **FNC §N**, **IC §N**, **PLK §N**, **F §N**, **ACV §N**.
>
> **Principio guida di questo documento:** *la forma ora, i numeri dopo.* G fissa la **struttura** del gameplay (la shape dei dati, le autorità, i punti d'innesto); i **valori** (formule, tabelle, contenuti del catalogo) sono buchi dichiarati dell'economia — il **Gruppo 2** — che entrano come placeholder e **non** bloccano l'implementazione. Dove una scelta di G chiede di violare un paletto a monte, è la scelta a essere sbagliata, non il paletto.
>
> **Ritocco post-chiusura (da J, cambiali C2/C3 — vedi `saldo-cambiali-J.md`).** Due deleghe che J aveva lasciato a G sono ora **recepite**: la **cadenza del tick status in combattimento** = per-turno-dell'entità (§4.4, G-24), e il **timing + clamp della battuta d'ingresso** evocata dal dado-evento di J (§5.1, G-25). Entrambe additive, coerenti con le autorità esistenti (single-owner §4; "l'AI compone a monte" §5.1); non riaprono il loop né il binario di mutazione.

---

## 0. Premesse ereditate (non rinegoziabili qui)

- **L'AI propone, il motore dispone.** L'AI è sorgente di varietà del contenuto; il motore arbitra ogni esito. *(FNC §1)*
- **Combattimento deterministico e seeded.** Nessun LLM nella risoluzione; risolvi prima, narra dopo; `process()` una volta per turno/azione risolta. *(FNC §2, §6.4, §9)*
- **Tre bucket, un solo proprietario per componente con stato.** Il tick degli status vive **esclusivamente** nel bucket sempre-attivo; nessun handler di status parallelo in combattimento. *(FNC §6.2)*
- **Entità di combattimento effimere; protagonista persistente.** Create su `EncounterStarted`, distrutte su `CombatResolved`. *(FNC §6.3)*
- **Composizione gratis.** "boss + veleno + stordito + rigenerazione + loot" è una somma di componenti, non un caso speciale; aggiungere un effetto = un componente + un sistema, senza toccare i sistemi esistenti. *(A-bis, ESP §3)*
- **Il contratto porta i nomi, il motore possiede i numeri.** L'AI seleziona da enum chiusi dentro un budget; le statistiche le deriva il motore. Il gate (schema + catalogo + budget) sta nel motore. *(FNC §5.5, F §11, IC §4)*
- **Una sola interfaccia verso l'AI:** `genera(prompt, schema) → candidato | None`; l'intera politica di fallimento è decisa dallo schema, lato motore. *(PLK §2, F §11)*

Se una di queste non è chiara, fermarsi e rileggere i documenti a monte prima di implementare quanto segue.

---

## 1. Decisione G (sintesi)

| Aspetto | Decisione | Dove vive | § |
|---|---|---|---|
| Economia d'azione | **Action Point**, clampato a `1` nell'MVP; talenti lo espandono dopo | componente-dato + sistema-turno | §2 |
| Iniziativa | derivata da **destrezza**, tiebreak deterministico (seeded/stabile) | sistema-turno | §2 |
| Decisione dei nemici | **motore**, deterministica e seeded — **mai** LLM | sistema-IA-nemici (euristiche = contenuto) | §2 |
| Terminazione | "morte di una squadra" = *condizione di vittoria*; la *garanzia di fine* è un **vincolo sull'economia** | invariante su Gruppo 2; fallback = escalation via §5 | §3 |
| Status — stacking | **un'istanza per tipo di primitivo**; stesso tipo → **competizione per rango**; tipi diversi → coesistono | componente-status (dato puro) | §4 |
| Status — rango | = **rango dell'applicatore** (rarità se composto dall'AI; assegnato dal motore se seeded/anomalia), *copiato* nel componente all'applicazione | campo `rango` sul componente | §4 |
| Mutazione del combattimento in corsa | **una nozione**: mutazione intra-fase, motore-arbitrata, a confine di turno | regola + contatore-turni ora; sistemi additivi | §5 |
| Genere della run | **permadeath**: il crawler muore, muore | — | §6 |
| Terminale di morte | `MortePersonaggio`, alimentato da un **death-check** seeded; morte ≠ sconfitta | bus + cucitura ACV | §6 |
| Identità del crawler | **id di dominio** (uuid / contatore di H), **non** l'id di entità esper | componente + metadato del save | §6 |
| Save | il save **è** il run-World; **un solo run-World vivo** alla volta; slot = crawler | H possiede il meccanismo | §6 |
| Creazione personaggio | **Carl predefinito** (DCC), nessuna scelta meccanica nell'MVP | additivo post-I | §6 |
| Lettura della scheda da parte dell'AI | **proiezione di sola lettura** (DTO derivato), mai l'oggetto-scheda vivo | `contracts` | §6 |
| Prove di abilità | l'AI **inquadra e veste**, il motore **tira** seeded; difficoltà = **classe** da enum chiuso | §7 | §7 |
| Livello | = **profondità del piano**, derivata dal motore; avanza **solo** su `DiscesaPiano` | dato di stato (serializzato) | §8 |
| Socket generativo | **un verbo per schema**; provider sottile + **orchestrazione lato motore** | `contracts` + coroutine host-agnostica | §9 |
| Catalogo | **primitivi chiusi, composizione aperta** | vincolo su Gruppo 2 | §10 |

I **contenuti** (quali archetipi/rarità/blocchi, le formule, le tabelle di budget e anomalie, i numeri degli status, le soglie delle classi di prova) **non** sono di G: sono buchi dichiarati del **Gruppo 2 — economia** (§13). G fissa la *forma*, non le *voci*.

---

## 2. Il loop di combattimento

**Un solo protagonista contro N nemici.** Turni discreti, risoluzione deterministica sotto phase-gate (FNC §6.1), bucket *solo-combattimento*.

### 2.1 Economia d'azione — Action Point clampato

L'economia d'azione è a **Action Point (AP)**, una **risorsa**, con `max = 1` nell'MVP; i talenti, post-MVP, alzano il max o concedono azioni bonus. L'AP è un **componente-dato**; i talenti sono **componenti** che il sistema-turno legge.

> **Il loop si scrive guidato dagli AP fin da subito** — `while ap > 0: spendi` — anche con `max = 1`. Scriverlo come "una azione e stop" *non* prende la forma: aggiungere AP dopo sarebbe la riscrittura del control-flow che vogliamo evitare. Si incastra con FNC §6.4: l'unità di `process()` è l'**azione risolta** — a 1 AP è una `process()` per combattente, a N sono N; la struttura generalizza già.

### 2.2 Iniziativa

L'iniziativa è derivata da **destrezza** (stat di velocità). Conseguenza per il placeholder-stat: il contenitore-stat deve **già portare il campo `destrezza`** — è l'unico campo che il placeholder non può lasciare vuoto, o il sistema-iniziativa non ha cosa leggere.

> **Tiebreak deterministico** a parità di destrezza: ordine **stabile o seeded**, mai arbitrario. Il combattimento è deterministico (FNC §9); un tiebreak non-deterministico romperebbe il replay. **Vincolo collegato a §6.3:** se "stabile", la chiave dev'essere **stabile per davvero** (seeded, o l'id di dominio del protagonista) — **mai** l'`id` di entità esper, che è sequenziale e **riciclato** (§6.3) e quindi cambierebbe attraverso un save/load, rompendo il replay esattamente come per l'identità del crawler. In pratica, per i nemici effimeri la chiave è l'**ordine di spawn seeded**, non l'id.

### 2.3 La decisione dei nemici è del motore

> La scelta delle azioni dei nemici è **logica del motore, deterministica e seeded** — **mai** l'LLM (FNC §2/§9). Le *euristiche* (come scelgono il bersaglio, quando usano un blocco) sono **contenuto** e si rimandano; ma "l'AI muove i mostri" è un'idea da **scartare a priori**: l'AI narrativa non tocca la risoluzione.

### 2.4 Risoluzione e formule — placeholder

Colpo a segno, danno, applicazione degli status e la formula-madre `(archetipo, rarità, livello) → statistiche` sono **contenuto stubbato**: contenitori dato puro ECS (ESP §1) con formula nel factory del motore. Rimandati al Gruppo 2. *La sola struttura non rimandabile è il campo `destrezza` (§2.2) e la shape degli status (§4).*

---

## 3. Terminazione

> **"Morte di una squadra" è la *condizione di vittoria*, non la funzione che forza la fine.** Dice *quando* hai vinto o perso; non garantisce che quel momento arrivi. Uno stallo (rigenerazione ≥ danno in arrivo, build puramente difensivo) lascia le due squadre a picchiarsi all'infinito — è la seconda patologia di FNC §2, "allungamento del brodo".

La garanzia di terminazione **non è risolvibile senza l'economia**: dipende interamente dalla relazione fra sostentamento e danno, che sono numeri del Gruppo 2. Decidere ora una difesa contro uno stallo che non si può ancora caratterizzare è prematuro. Quindi:

> **Terminazione (vincolo su Gruppo 2).** La garanzia di fine è un **vincolo sull'economia**, verificato quando catalogo+formula esistono. Default **(a)**: si verifica che l'economia MVP non ammetta stallo (nessun build con sostentamento ≥ danno). **Il metodo di (a) non è gratuito:** su primitivi componibili (§10) l'assenza di stallo è una **proprietà combinatoria del catalogo**, non un'ispezione a occhio — il *come* (analisi statica della funzione-costo, o **property test** sull'insieme dei blocchi) è **esso stesso un compito dichiarato del Gruppo 2**. Fallback **(b)**: una **escalation** (il dungeon interviene a soglia) entra come sistema nel bucket solo-combattimento — economica da aggiungere grazie a §6.4, ed è il **binario di mutazione** di §5. **(b) non richiede prova:** garantisce la terminazione **per costruzione** (dopo la soglia, la pressione cresce finché qualcuno muore) — è la rete di sicurezza se (a) si rivela impraticabile. La garanzia di fine **gatekeepa la slice** (nodo A, "giocabile capo-a-fine") — soddisfatta da (a) dimostrata **o** da (b) presente; non è post-MVP.

Nota di coerenza col design ("i giocatori rompono il gioco, il gioco rompe i giocatori"): un build difensivo-immortale è *esattamente* il caso che produce lo stallo. L'ambizione aumenta il rischio di non-terminazione, non lo riduce — ragione in più perché la garanzia (a-o-b) ci sia prima della release. È una delle **due liveness dell'MVP**: lo scontro **finisce** (qui), e il piano si **chiude** (§8.4, completabilità). Senza entrambe, "giocabile capo-a-fine" (nodo A) non regge.

---

## 4. Status: shape, stacking, rango

Gli status (Veleno, Brucia, Rigenerazione, Stordito…) sono componenti **dato puro** (ESP §1). Il loro avanzamento ha **un solo proprietario** nel bucket sempre-attivo (FNC §6.2): un `SistemaVeleno` possiede tutti i `Veleno`, un `SistemaBrucia` tutti i `Brucia`. Altri sistemi leggono; nessun altro avanza.

### 4.1 Un'istanza per tipo di primitivo

> **Stacking = un'istanza per tipo di primitivo, sulla stessa entità.** Lo stesso primitivo riapplicato **non** affianca una seconda copia; **compete** con la residente (§4.2). Primitivi **diversi** coesistono come componenti distinti, con tick in parallelo. Questo è il **comportamento di default dell'ECS** (un componente per tipo per entità: `add_component` sovrascrive) — *zero* codice di gestione-stack, e il single-owner tick regge senza sforzo.

Concretamente: Carl ha **un solo** `Veleno`, mai due; `Veleno` + `Brucia` sono due componenti che convivono. Lo "scontro" fra due veleni **non** è fra due componenti coesistenti — è una **regola di applicazione**: il nuovo arrivato si confronta con la residente *nell'istante dell'applicazione*, e uno solo sopravvive. Non sono mai compresenti. Pensare "due componenti che si scontrano" reintroduce di soppiatto la versione a lista-di-istanze, scartata.

### 4.2 Competizione per rango

> Status dello stesso tipo **non si fondono coi numeri** (niente max/somma/sovrascrivi): **competono per rango**. Il rango più alto **vince**, resta attivo e **rinfresca la propria durata**; il perdente è **cancellato senza residui**. Una riapplicazione di rango ≤ rinfresca comunque il timer del vincitore (non lo **diluisce**: non puoi indebolire un veleno alto prendendone uno basso).

Il confronto è **int vs int**, fissato all'applicazione, **immutabile dopo** — deterministico, non tocca il seed.

### 4.3 Il rango è dell'applicatore, copiato all'applicazione

> Il **rango** non è un attributo intrinseco dello status: è il **rango dell'applicatore**, **copiato dentro il componente al momento dell'applicazione** (denormalizzazione voluta). **Mai un riferimento alla fonte**: le entità di combattimento sono effimere (FNC §6.3) — la fonte (es. il drago) muore a metà scontro, e il veleno sopravvive in narrazione. Un puntatore alla fonte penzolerebbe; il valore copiato rende lo status **autosufficiente**.

Sorgenti del rango (convergono sullo stesso campo a valle):

- applicatore **composto dall'AI** (mostro, trappola ambientale, terreno) → rango = la sua **rarità** (la scala già esistente `{archetipo, rarità, blocchi}`);
- applicatore **del motore** (anomalia, e qualunque effetto iniettato seeded) → rango **assegnato dal motore** nella stessa logica seeded. *L'anomalia è un tiro del motore, non una selezione dell'AI (FNC §5.5): il suo rango non viene da una composizione, viene dal motore.*

Il `SistemaVeleno` non sa né gli importa da dove venga il rango: confronta due interi. *(Quali ranghi/effetti esistono — incluso se e quando un veleno è "letale a fine timer" — è contenuto del Gruppo 2.)*

> **Presupposto strutturale:** il confronto int-vs-int implica un **ordine totale sulle rarità** e una mappa `rango(rarità) → int` **lato motore**. I *valori* della scala sono Gruppo 2 (§13.1); l'**esistenza dell'ordine totale** e della mappa è forma, qui.

### 4.4 Cadenza del tick in combattimento — per-turno-dell'entità

> **Quando** uno status avanza in combattimento: **al confine del turno *dell'entità che lo porta*** — una volta per round per entità — **non** a ogni `process()` globale. Il `SistemaVeleno`, quando gira, avanza **solo** gli status dell'entità che si sta attivando (gating sul possessore), non tutti i `Veleno` del World a ogni tick.

Razionale (cambiale C2 da J §2.1/§15). Il bucket sempre-attivo gira a ogni `process()` risolto (FNC §6.4), e in un loop AP-driven (§2) "un turno" è un'**attivazione**: senza questo gating, in una mischia a N combattenti il `Veleno` del protagonista ticcherebbe **N volte a round**, legando il burn-rate alla *folla* invece che al tempo. Con la cadenza per-turno-dell'entità, un veleno "3 cariche" dura **3 turni del protagonista** (≈ 3 round), **invariante al numero di nemici**.

Questo **chiude la delega** che J aveva lasciato a G (J §2.1: "J non fissa per-attivazione vs per-round"). È accoppiato alla **cadenza base per-stanza** in esplorazione (J §4): fuori, lo status avanza una volta per stanza; dentro, una volta per turno dell'entità — lo stesso *beat* nei due regimi (3 cariche = 3 stanze fuori, 3 round dentro). *(La forma — single-owner, dato puro, competizione per rango §4.1–4.3 — non cambia; questo fissa solo il **quando**.)*

Criterio **G-24** *(comportamentale)*: il burn-rate di uno status sul protagonista è **invariante al numero di nemici** in campo (uno status "k cariche" dura k turni del protagonista, sia in 1-vs-1 sia in 1-vs-N).

---

## 5. Il binario di mutazione del combattimento

"Modificare il combattimento in corsa" (aggiungere nemici, rinforzi, far intervenire il dungeon) **non è una feature**: in ECS è mutare l'insieme di entità dello scontro attivo, e la composizione (ESP §3) lo rende **gratis**. Quello che rompe non è la capacità — è farlo dal **canale**, nel **momento**, con l'**autorità** sbagliati. La disciplina sta in **quattro binari**.

### 5.1 Autorità (chi)

> In combattimento l'autorità generativa dell'AI è **zero** (FNC §2). Due fonti legittime, **asimmetriche**:
> - il **motore** (un sistema seeded) può mutare lo scontro — è il "dungeon che interviene", deterministico;
> - l'**AI** può solo aver **composto** lo scontro **a monte**, su `EncounterStarted`, in fase di narrazione, selezionando dal catalogo dentro budget (FNC §5.5) — incluse eventuali ondate programmate che il motore poi rilascia.
>
> "L'AI aggiunge nemici" è ammesso **solo** come "l'AI ha composto uno scontro con un'ondata che il motore libera al turno N", **mai** come iniezione live mid-combat.

> **Ingresso in combattimento dal dado-evento di J (cambiale C3).** Quando lo scorrimento del tempo evoca un'imboscata (J §8), la composizione dell'incontro è una `TurnoNarrazione` emessa **mentre `FaseCorrente == NARRAZIONE`**, **al confine di tick, *prima* del flip** a `COMBATTIMENTO` — coerente con "l'AI compone a monte, su `EncounterStarted`, in fase di narrazione" (sopra). Su quella battuta d'ingresso il **gate di F clampa `durata = TURNO`** (l'imboscata è una singola battuta, non comprime tempo; F §2/F-14). Ordine fissato: *composizione in narrazione → gate (clamp `durata=TURNO`) → `EncounterStarted` → flip*. Dopo il flip lo scorrimento è off (J-13), quindi nessun fast-forward parte in combattimento.

> Criterio **G-25** *(comportamentale)*: una `TurnoNarrazione` che emette `EncounterStarted` è prodotta in fase di narrazione e ha `durata == TURNO` dopo il gate; nessuna entità di combattimento viene materializzata prima del confine di tick.

### 5.2 Canale (come)

La mutazione di stato è roba da **Canale A** (ESP §4): un sistema deterministico, nell'ordine. Modo idiomatico: un **componente-programma** sull'entità-scontro (es. `PianoRinforzi`: ondate con turno-trigger), letto da un sistema a confine di turno. Il **bus (Canale B)** serve **solo** per il reveal narrativo — un evento al rilascio dell'ondata perché lo showrunner la racconti, come `AnomalyTriggered` (FNC §5.5/§8). Stato via A, narrazione via B.

### 5.3 Timing (quando)

> `process()` una volta per turno risolto (FNC §6.4). **Non** mutare l'insieme dei combattenti *mentre* risolvi un'azione o iteri l'iniziativa (bug del mutare-durante-iterazione). Le mutazioni strutturali avvengono a un **confine di turno**, da un sistema a **priorità nota** (come il drenaggio della coda intenti gira per primo, IC §7.1).

### 5.4 Invarianti ereditati (cosa)

I combattenti aggiunti sono combattenti come gli altri: **effimeri** (FNC §6.3, distrutti su `CombatResolved`, non inquinano l'esplorazione); status **single-owner** (§4); stat e slot d'iniziativa **seeded** (FNC §9) con tiebreak deterministico; contano sul **budget** (FNC §5.5).

> **Rinforzi senza tetto = allungamento del brodo.** Ondate infinite sono una sorgente di non-terminazione. Il meccanismo dei rinforzi e l'invariante di terminazione (§3) sono lo stesso problema visto due volte.

### 5.5 Forma da prendere ora; corpo additivo

> **Forma (ora):** esiste **una** nozione — la **mutazione intra-fase dello scontro**, distinta dagli eventi di transizione (`EncounterStarted`/`CombatResolved` cambiano *fase*; questa **resta dentro `COMBATTIMENTO`**). Richiesta da un sistema seeded o composta dall'AI a monte; mai dall'AI live; applicata a confine di turno; materializzata dal motore; entità che ereditano gli invarianti §5.4. Il costo concreto **ora** è: una **regola** (questa) + un **contatore di turni** sullo scontro (campo `int`, dato ECS).
>
> **Corpo (additivo, Gruppo 2):** i sistemi concreti — `PianoRinforzi`, il watchdog di terminazione, la curva di escalation. Entrano come "registra un Processor / aggiungi un dataclass", senza editare i sistemi esistenti (ESP §3).

### 5.6 Tutoraggio del combattimento da parte dell'AI

La frase "l'AI sorveglia lo scontro e reagisce" si scompone in **vietato** e **legittimo**:

- **Vietato:** l'AI come *giudice/watchdog* che aggiusta lo stato, cura, depotenzia, o decide la terminazione. Rilevare uno stallo è un **check deterministico** (contatore, delta-danno), non un giudizio dell'LLM. È anche la versione **bloata** (chiamata LLM su timer, ricorrente).
- **Legittimo:** *rilevazione + risposta* = **motore** (il binario §5, gratis); *narrazione del verdetto* = **AI dopo il fatto** — quando il check scatta, un evento sul bus e lo showrunner lo racconta, via la chiamata di sola prosa **async e non-gating** (FNC §5.2/§8). Zero chiamate a vuoto; l'AI parla solo quando qualcosa scatta. L'output è **presentazione, non stato**: cache-abile per il replay (IC C-5), fuori dal seed.

> **Quale MVP?** Il *rilevatore-di-stallo runtime* descritto qui (motore che misura e reagisce a soglia) è il **percorso (b)** di §3 — **corpo additivo (Gruppo 2)**, non il default MVP. Il default MVP per la terminazione è la **verifica statica (a)** (§3). Questa sezione descrive la *forma* del watchdog, non un sistema spedito nella 1.0: nell'MVP esiste come slot sul binario §5, non necessariamente acceso.

*(Il QA di bilanciamento offline — far guardare all'AI i replay per segnalare build sbilanciati — è tooling separato, fuori dal loop seeded, post-MVP.)*

---

## 6. La forma della run

Riempie i buchi delegati da E (ACV §8): genere, morte, creazione personaggio, save, trigger dei terminali.

### 6.1 Genere — permadeath

> **Il crawler muore: muore.** Finché vive ha il proprio save state e può salvare/ricaricare. La **morte è permanente**.

Semantica del save coerente con la permadeath (meccanismo posseduto da H): **suspend-on-load** — un singolo stato che avanza, **non** un checkpoint ripristinabile a piacere (che renderebbe la permadeath cosmetica e riaprirebbe il save-scum). Non "salva in N slot liberi": vedi §6.4.

### 6.2 Morte ≠ sconfitta — il terminale è `MortePersonaggio`

ACV §5.1 aveva cablato `CombatResolved(sconfitta) → run→guscio` come terminale di perdita ("solo la sconfitta escala"). G inserisce uno strato: la sconfitta è un *esito di combattimento* che di norma porta alla morte, ma può essere **aggirata** in casi estremi.

> Il **terminale di run** è un evento `MortePersonaggio`, **non** `CombatResolved(sconfitta)`. La sconfitta **alimenta** un **death-check** deterministico e seeded (mai LLM — FNC §2/§9), che nell'MVP mappa **sconfitta → morte sempre**; l'aggiramento entra dopo come **hook additivo** su quel check. La detection è in-run sul bus, l'hand-off alla shell è di E (ACV §5).
>
> **Rettifica di ACV §5.1** (da annotare nell'indice): l'evento che escala non è `sconfitta` ma `MortePersonaggio`; la sconfitta ne è il trigger principale, **non automatico**. È autorità legittima di G (la morte è gameplay; E possedeva la *cucitura*, non il *trigger*).

### 6.3 Identità del crawler — id di dominio, non id di entità

> L'identità di un crawler **non** è l'`id` di entità esper. Quell'id è un **intero sequenziale interno al World**, un handle runtime: **si ricicla** (al teardown `delete_world`, alla nuova partita `switch_world("run")` ricrea vuoto e il contatore riparte — ESP §0.1), quindi crawler di run diverse collidono sulla stessa chiave. È fragile anche attraverso serializza/deserializza.
>
> Il crawler ha un'**identità di dominio** (uuid o contatore-crawler **posseduto da H**), assegnata alla **nascita del protagonista** al confine guscio→run (ACV stazione 3a), salvata sia in un **componente** sia come **metadato del save**. Il death-check emette `MortePersonaggio` con il crawler-id di dominio; H invalida il save keyato su quello. **Death-check e invalidazione = stesso seam.**

### 6.4 Save = World; un solo run-World vivo; slot = crawler

> Il save **non** è taggato dall'entità giocatore: il save **è** il run-World (che contiene l'entità giocatore, `FaseCorrente`, lo stato d'esplorazione, la cache delle stanze). La morte **invalida il save della run corrente** — nessuna ricerca per id.
>
> **Multi-crawler.** Il giocatore gestisce più crawler; i due **non interagiscono** — proprietà **gratis** dal modello: più crawler = più run-World **indipendenti** (isolati alla radice, come fra test, ESP §0.1). Regola: **un solo run-World vivo alla volta**; gli altri crawler sono **file inerti su disco**, non contesti residenti. Caricare il crawler B = teardown del corrente → load di B nel contesto `"run"` (ACV stazione 3b), non una primitiva nuova. Il contesto si chiama **sempre `"run"`**, uno solo; l'identità sta nel **save**, mai nel nome del World (niente `run-A`/`run-B` residenti, che reintrodurrebbero due World vivi).
>
> **Risolve il buco di H** "slot singolo vs multipli" (ACV stazione 2): **multipli, ma gli slot *sono* i crawler** — un crawler vivo = un save unico, suspend-on-load. Non slot di salvataggio liberi.

### 6.5 Creazione personaggio — Carl predefinito

> **Creazione personaggio = protagonista predefinito ("Carl"), assegnato dal dungeon (DCC), nessuna scelta con effetto meccanico nell'MVP.** Archetipo-con-effetto resta additivo (post-I). Tiene G piccolo e non tira dentro catalogo+formula adesso.

*Quali stat, quali abilità, la curva di livello sono contenuto, post-I.* Ma **la scheda esiste** come stato del protagonista (entità persistente, bucket sempre-attivo).

> **La scheda-placeholder non è del tutto vuota: G ne rende obbligatori adesso tre pezzi**, imposti altrove e qui consolidati perché l'implementatore non li scopra sparpagliati:
> - **`destrezza`** (o stat di velocità) — letta dall'iniziativa (§2.2);
> - lo **stato-vita** letto dal **death-check** (§6.2) — ciò che distingue "vivo" da "morto";
> - i **campi che alimentano la proiezione DTO** (§6.6) — la sorgente da cui il motore deriva `"ferito"`, `"avvelenato"`, ecc.
>
> Tutto il resto (curva di livello, abilità, stat secondarie) resta contenuto rimandato. *Quanti* e *quali* campi oltre questi tre = Gruppo 2; il **minimo** sopra = forma.

### 6.6 Lettura della scheda da parte dell'AI — proiezione di sola lettura

L'AI deve *leggere* lo stato del protagonista per narrarlo ("Carl barcolla, ferito"). Rischio simmetrico al §2: passare l'oggetto-scheda **vivo** (i componenti ECS) fa vedere all'AI numeri che potrebbe pretendere di spiegare (e domani negoziare) e lega il prompt alla shape interna dei componenti (rompe la membrana `contracts`).

> L'AI riceve una **proiezione di sola lettura** della scheda — un **DTO derivato** (es. `"ferito"`, `"avvelenato"`, non `hp: 7/30`), **costruito dal motore**, che vive in `contracts`. L'AI narra una *vista*, non legge il *registro*. È "risolvi prima, narra dopo" applicato allo stato persistente. *Quali* campi e *quanto ricca* è la proiezione = contenuto; il **fatto** che esiste la proiezione = forma, presa ora.

### 6.7 Trigger del piano-completato

> Il **trigger del piano-completato** è raggiungere e attivare la `DiscesaPiano` del piano (§8). Nell'MVP (un piano solo, nodo A), la `DiscesaPiano` non porta a un piano 2 inesistente: **è il terminale di vittoria** della run. La destinazione di vittoria (schermata / ritorno al menu) è un valore minore (G/H). La destinazione della **sconfitta** sotto permadeath: game-over → guscio → altro crawler, via `MortePersonaggio` (§6.2).

---

## 7. Prove di abilità in esplorazione

In esplorazione l'AI **può e deve** proporre prove e dialogare con il giocatore — ma "negoziare" significa **inquadrare la prova prima del tiro**, non arbitrare l'esito. ACV lo dice già: *"la fuga è una prova, non una concessione del modello"*. L'AI negozia l'**inquadramento**, mai il **risultato**.

### 7.1 Il flusso di una prova

1. **L'AI propone** la prova (narrazione; può dialogare su *come* il giocatore tenta).
2. **L'intento del giocatore → evento tipizzato** (FNC §5.4/§5.6), **non** prosa che l'AI risolve.
3. **Il motore tira**, seeded e deterministico (FNC §9): `stat rilevante + soglia → successo/fallimento`. Mai l'LLM.
4. **L'AI veste il risultato** prodotto dal motore (risolvi prima, narra dopo).

L'AI legge la scheda (via la proiezione §6.6) e modula *cosa* propone; non tocca il passo 3.

### 7.2 Difficoltà = classe nominata, non numero

> La difficoltà di una prova è una **classe nominata da enum chiuso** (`bronzo … celestiale`), **non** un numero. L'AI **seleziona la classe** inquadrando la prova, **prima del tiro**, e **non può mutarla dopo** (né rinominarla in risposta a un fallimento, né abbassarla perché il giocatore ha argomentato bene). Il motore mappa `classe → soglia` (seeded) e risolve. È la spaccatura nomi/numeri di F: "celestiale" è un nome, come "Leggendario"; la tabella `classe → soglia` è la formula, e vive nel motore.

### 7.3 Inflazione di classe — gate

> La classe **proposta dall'AI passa per un gate** (coerenza col contesto, eventuale tetto legato a dove sei nel piano), come l'entità passa per il budget-gate. L'AI propone la classe; il motore l'**accetta o la riconduce**. Gate pieno **post-MVP**; nell'MVP può bastare fidarsi dell'enum chiuso senza tetto.

### 7.4 Le ancore vivono nel catalogo, non nel componente

> Gli **esempi-ancora** ("celestiale = sedurre un dio; bronzo = scappare da una blatta mannara") sono **materiale di calibrazione del prompt**, **non** dato dell'entità. La definizione `classe → (soglia seeded, ancore testuali)` vive nel **catalogo** (registry di dominio). Le **ancore** alimentano il costruttore del prompt (e frenano l'inflazione di classe); la **soglia** è del motore. L'**entità-prova** porta **solo** la classe scelta (etichetta dall'enum), **mai** gli esempi — resta dato puro, serializzabile, non duplicato.

*(Le ancore sono il primo contenuto del Gruppo 2 già impostato.)*

### 7.5 Difficoltà adattiva — post-MVP, innesto nel gate-di-classe

> La prova **tarata su misura** (scheda del giocatore + storia del playthrough) è **post-MVP**, e si innesta nel **gate-di-classe** già previsto: `classe proposta → gate del motore (oggi: tetto di contesto; domani: ricalibrazione su scheda/storia) → soglia seeded → tiro`. È una **funzione deterministica del motore**, **mai** un giudizio dell'AI, e **seeded** come il resto (un'adattività non seeded romperebbe il replay). Prendere ora il **punto d'innesto** (classe → gate → soglia, non classe → tiro diretto) evita il retrofit.

*(Distinzione: la prova si **confronta** già con la scheda — il motore tira `stat vs soglia`, le stat di Carl entrano nell'esito. Quello c'è. È la *taratura adattiva della soglia* a essere rimandata.)*

### 7.6 Scope MVP

> L'MVP ha un **set chiuso di prove da menu** (Forza, Destrezza, Percezione…), strutturate. La **conversione del testo libero** (`Altro` → prova tipizzata) resta **post-MVP** (FNC §5.6). Le prove strutturate si appoggiano sul `genera` per la sola **narrazione** di inquadramento ed esito.

---

## 8. Livello e `DiscesaPiano`

### 8.1 Il livello è la profondità del piano, derivato dal motore

Autorità su `livello` (delegata da F §4.2): **il motore**, non l'AI — l'AI non sceglie numeri, nemmeno il livello.

> Il **livello è la profondità del piano**: un **contatore discreto** che parte da `1` e avanza **solo** per un atto fisico nel mondo — attivare una `DiscesaPiano`. Non è ricalcolato per incontro: è **dato di stato** (componente/singleton nel World), serializzato col save come `FaseCorrente`. Quando il budget d'incontro (Gruppo 2) legge "il livello", legge **questo** contatore.

Spaccatura d'autorità (FNC §2/§5.5 vista da un terzo lato — l'AI non *risolve*, non *conia numeri*, e ora non *muove il progresso*):

- l'AI può **far esistere** la via verso il basso (contenuto del piano);
- l'AI **non** può imporre la discesa né toccare il contatore;
- **scendere è un atto del giocatore**; l'incremento del livello è una **conseguenza posseduta dal motore**, scatenata dall'intento-di-discesa (evento tipizzato), seeded.

### 8.2 Conseguenza sullo schema (G esercita l'autorità delegata da F §4.2)

F tiene `livello: int` come campo che l'AI emette in `EntitaGenerata`, e **delega a G chi lo decide** (F §4.2). G ha deciso (§8.1: del motore). Resta la conseguenza sul contratto, che G **deve chiudere** — non lasciarla inferire — perché un implementatore che la inferisce sceglie la lettura sbagliata ("tengo il campo e lo sovrascrivo nel gate") il più delle volte, e quella contraddice §8.1.

> **Il `livello` non è un input dell'AI: lo schema di generazione non lo porta.** Poiché il livello è profondità di piano, dato di stato del motore (§8.1), l'AI non lo emette affatto — non "lo emette e il gate lo sovrascrive". Il campo `livello` è **rimosso da `EntitaGenerata`**; il motore lega l'entità generata al `livello` corrente (il contatore di profondità) **al momento della materializzazione**, dopo il gate. Le tre letture possibili — *campo rimosso* / *campo ignorato-e-sovrascritto* / *hint non vincolante* — collassano sulla prima: le altre due sprecano superficie e token (PLK) o riaprono l'autorità che §8.1 toglie all'AI.
>
> **Propagazione (non è di G):** la rimozione del campo vive **nello schema**, cioè in F (`EntitaGenerata`). G **possiede la decisione**, F **possiede la forma**; chi mantiene lo schema applica la rimozione. G la dichiara qui perché è il documento che ha l'autorità sul livello, e l'agente legge G per sapere cosa fare del campo. *(Eco in §13.1.)*

### 8.3 "Scala" (arredo) ≠ `DiscesaPiano` (primitivo)

> Una **scala** generica è **arredo** — contenuto narrativo, dominio dell'AI, **zero** effetto meccanico (come torce o porte). La **`DiscesaPiano`** è un **primitivo strutturale**: l'unico oggetto che, attivato dall'intento del giocatore, emette l'evento che avanza la profondità. La differenza **non sta nella fiction, sta nel tipo**: l'AI può **vestire** una `DiscesaPiano` da scala, botola, crepa, ascensore arrugginito — la veste è libera, il primitivo è uno. **Non basta la parola "scala"** perché ci sia una `DiscesaPiano`: il primitivo è piazzato dal **gate di contenuto**, non evocato dalla prosa.

Nell'MVP (un piano), `DiscesaPiano` **è** il trigger del piano-completato → terminale di vittoria (§6.7). Stesso primitivo, due letture a seconda che il piano sotto esista o no: pura questione di scope.

### 8.4 Completabilità del piano (liveness dell'esplorazione)

> **Ogni piano generato deve contenere almeno una `DiscesaPiano` raggiungibile.** È la **gemella della terminazione** (§3): §3 garantisce che lo *scontro* finisce, §8.4 che il *piano* si **chiude**. Senza, la run è **invincibile** — il contrario di "giocabile capo-a-fine" (nodo A). Poiché la `DiscesaPiano` è piazzata dal **gate di contenuto** (§8.3), la garanzia è del **motore**, non dell'AI: il gate non accetta un piano la cui topologia non espone almeno un'uscita raggiungibile dallo stato iniziale del giocatore. *(Come si verifica la raggiungibilità — controllo di connettività sulla mappa generata — è meccanismo; i parametri di generazione che la rendono probabile sono Gruppo 2. La garanzia, però, è forma: il gate rifiuta o ripara un piano senza uscita, non lo lascia passare.)*

---

## 9. Il socket generativo

L'architettura **ha già il socket**: non va costruito, va riconosciuto e **non allargato**. Il **protocollo** è il DTO in `contracts` (schema Pydantic in ingresso, candidato in uscita); il **socket** è l'interfaccia provider `genera(prompt, schema) → candidato | None`. PLK lo dice: *il churn dell'API è assorbito nel trasporto dietro il contratto, e non tocca `contracts` né il gate*. Una chiamata sopra il socket; 1 o N chiamate sotto, fatti del trasporto.

### 9.1 Un verbo per schema

> **Un solo verbo generativo**, distinto dallo **schema** — mai un metodo dedicato per tipo (F §12 lo vieta). La **chiamata di sola prosa** è lo **stesso verbo** con schema banale (`Flavor`), **non** un percorso fratello: ciò è **già deciso da F** (F §5) — G lo **conferma** e rimanda lì, non lo riapre. Il comportamento-per-tipo (retry, timeout, fallback) è deciso dallo **schema, lato motore** (F §11), non dal provider.

### 9.2 Provider sottile + orchestrazione lato motore

> Il **fan-out** (1 o 200 chiamate API, eventuali loop genera→critica→raffina) **non** vive dentro il provider — lo ingrasserebbe e tirerebbe la **costruzione del prompt** fuori dal motore, dove PLK/F la inchiodano. Il provider resta **sottile**: una chiamata strutturata per invocazione. Il fan-out vive in una **coroutine di orchestrazione host-agnostica** (IC C-5, testabile headless), **guidata dal motore**, che chiama il provider N volte e assembla. **Prompt e gate restano dominio.** Questo è il placement che **preserva l'AI master** (§10) mentre scala: più l'AI diventa potente, più il dominio deve stare nel motore, non meno.

### 9.3 Determinismo, async, cadenza

- **Replay:** il punto cacheable è l'**uscita del gate** (candidato validato); replay = **seed + cache** (F-13). Così **1-vs-N è invisibile al replay** — si rigioca dalla cache, non si ri-chiama. Si congela il *risultato*, non il *processo*.
- **Async/cancellazione:** un fan-out deve essere **una sola unità async cancellabile** — le N chiamate dentro un solo `await`, abortibile dal worker `exclusive` (IC §6), coroutine cancellation-aware ai punti di `await`. Senza questo torna il bug "ogni tanto resta appeso". `genera` in volo — fallita, in retry o cancellata — **non scrive nulla** sul save (F §6.1): lo stato resta al turno precedente.
- **Cadenza:** dal punto di vista del turno resta **una chiamata *gating* per turno** — la chiamata di narrazione che fa avanzare lo stato (drenata una volta, IC §7.1); il fan-out sotto il socket **non** tocca la coda intenti. Le altre chiamate AI dello stesso turno — la **narrazione d'inquadramento/esito di una prova** (§7) e il **flavor** (§5.6) — sono **modalità-prosa non-gating** (F §5.1): non bloccano la risoluzione e non contano contro questo limite. *(Più richieste **gating** turn-visibili nello stesso turno resta un seam distinto, ancora rimandato — il socket rende quella sicura il default.)*

### 9.4 Indirezione "procura"

> Il motore non chiama "**genera** contenuto nuovo", chiama "**procura** un'entità per questo budget". Nell'MVP, dietro quel verbo, c'è **sempre** generazione fresca. Domani la **memoria generativa** (la wiki, nodo post-I) diventa un **secondo ramo** dietro lo stesso verbo (prima prova a pescare, poi genera). Prendendo la *forma del verbo* ora, il ramo-wiki entra additivo senza toccare il call-site.

### 9.5 Forma ora / corpo dopo / non costruire

- **Forma (ora):** contratto **narrow** confermato (non si allarga la firma `genera`); uno **slot** di orchestrazione async-cancellabile dietro il socket; **cache all'uscita del gate**. Provider sottile, una chiamata per invocazione.
- **Corpo (additivo):** il fan-out reale, il ramo-wiki ("procura"), i loop genera→critica→raffina, i tipi futuri (intento→evento, FNC §5.6).
- **Non costruire ora:** un framework di pipeline/orchestrazione. Il corpo dell'MVP è *una* chiamata + il retry/fallback già specificato (PLK §6). È lo "spezza l'atomo" di C: *si prende il contratto ora, si lascia il trasporto come opzione futura*; una pipeline da N chiamate è solo trasporto più ricco.

---

## 10. Primitivi chiusi, composizione aperta (vincolo su Gruppo 2)

> I **blocchi** del catalogo nascono come **primitivi componibili** — atomi che il motore sa risolvere (`infliggi danno`, `applica status`, `cura`, …) — **non** come effetti monolitici. Anche i pochi dell'MVP **seguono il pattern**.

È la tesi ECS di A-bis portata all'autoria: un effetto è una *somma di primitivi*, mai un caso speciale. Abilita, **post-I**, l'**AI master** (che crea skill/abilità/oggetti/classi/PNG) senza riscrivere il catalogo:

- l'AI **compone** primitivi e li **veste** di nome/prosa; **mai** inventa un atomo meccanico o un numero. Una "nuova skill" è una **frase nuova** in un linguaggio le cui parole (i primitivi) e la cui grammatica (formula, costo) sono del motore;
- una skill/classe/oggetto/PNG generati = un fascio di primitivi con le stat calcolate dalla **formula-madre**; il motore valida la composizione (gate) e ricalcola i numeri;
- un **PNG** si crea (composizione + persona) e si **interpreta** (l'AI recita la voce; ogni azione che tocca lo stato passa per intento→evento o per la risoluzione deterministica);
- **asimmetria voluta:** il nucleo deterministico cresce **deliberatamente** (un primitivo nuovo = componente + sistema, atto ingegneristico — ESP §3); la superficie generativa cresce **liberamente** sopra. Si limita il **vocabolario** dell'AI, non la sua creatività.

L'enum delle **classi di difficoltà** (§7) è anch'esso un primitivo riusabile: la stessa scala da cui l'AI master, domani, pesca per vestire le prove che genera.

---

## 11. Invarianti rafforzati da G

- **L'AI propone, il motore dispone — anche sul progresso.** L'AI non risolve (combattimento), non conia numeri (stat, livello, difficoltà), non muove il progresso (livello via `DiscesaPiano`). *(rafforza FNC §2/§5.5)*
- **Lo stato è autosufficiente, non per riferimento.** Il rango di uno status è **copiato** dall'applicatore all'applicazione; nessun puntatore a entità effimere. *(rafforza FNC §6.3)*
- **Un componente per tipo per entità.** Lo stacking è competizione all'ingresso, non lista di istanze; il single-owner tick regge per costruzione. *(rafforza FNC §6.2, ESP §3)*
- **Mutare il combattimento è motore-arbitrato, a confine di turno, seeded.** L'AI compone a monte; mai inietta live. *(rafforza FNC §2/§6.4)*
- **L'AI legge una vista, non il registro.** La scheda raggiunge l'AI solo via proiezione DTO di sola lettura in `contracts`. *(rafforza IC, "risolvi prima, narra dopo")*
- **Un verbo verso l'AI, comportamento per schema.** Il fan-out è trasporto sotto il socket; prompt, gate e fallback restano dominio. *(rafforza PLK §3, F §11)*
- **Primitivi chiusi, composizione aperta.** Il vocabolario meccanico è del motore; la creatività dell'AI compone, non conia. *(estende A-bis, FNC §5.5)*

---

## 12. Cosa NON facciamo (anti-over-engineering)

- ❌ Scrivere il loop come "una azione e stop": si scrive **AP-driven** (`while ap > 0`) anche con `max = 1`. *(§2.1)*
- ❌ Far **muovere i mostri all'AI**: la decisione dei nemici è motore, seeded. *(§2.3)*
- ❌ Trattare "morte di una squadra" come **garanzia di terminazione**: è la condizione di vittoria; la garanzia è un vincolo sull'economia. *(§3)*
- ❌ Modellare lo stacking come **lista di istanze** che convivono e si sommano: un'istanza per tipo, competizione per rango. *(§4)*
- ❌ Tenere nello status un **riferimento alla fonte**: il rango si **copia** all'applicazione. *(§4.3)*
- ❌ Lasciare che l'AI **inietti nemici live** o muti lo stato mid-combat: compone a monte; il motore esegue. *(§5.1)*
- ❌ Un **watchdog LLM** che valuta lo scontro su timer: il check è del motore; l'AI narra solo il verdetto. *(§5.6)*
- ❌ Keyare i save sull'**id di entità esper**: si usa un id di dominio (H). *(§6.3)*
- ❌ **Slot di salvataggio liberi** (riaprirebbe il save-scum): gli slot sono i crawler, suspend-on-load. *(§6.4)*
- ❌ Passare all'AI l'**oggetto-scheda vivo**: proiezione DTO di sola lettura. *(§6.6)*
- ❌ Far **fissare all'AI la soglia** di una prova, o ritoccare la **classe dopo il tiro**: classe da enum, immutabile, soglia del motore. *(§7.2)*
- ❌ Mettere le **ancore** delle classi **nel componente-prova**: vivono nel catalogo. *(§7.4)*
- ❌ Far avanzare il livello sulla **parola "scala"**: solo `DiscesaPiano`, atto del giocatore. *(§8)*
- ❌ Un **secondo metodo** sul provider per ogni tipo di chiamata, o un **provider grasso** che costruisce il prompt: un verbo, orchestrazione lato motore. *(§9)*
- ❌ Costruire ora un **framework di pipeline** generativa: forma del verbo ora, corpo dopo. *(§9.5)*
- ❌ Far **coniare primitivi meccanici all'AI**: compone primitivi chiusi, non ne inventa. *(§10)*

---

## 13. Buchi dichiarati e nodi a valle

### 13.1 Economia (Gruppo 2) — placeholder, non bloccanti

Entrano come segnaposto; la struttura di G li regge già:

- **Contenuti del catalogo**: quali archetipi, rarità, blocchi nell'MVP (pochi — un piano solo — ma **nati come primitivi componibili**, §10).
- **Formula-madre** `(archetipo, rarità, livello) → statistiche` e formule di to-hit/danno.
- **Tabelle di budget per contesto** e **funzione-costo** `(rarità, livello, blocchi) → costo d'incontro`.
- **Tabella delle anomalie**: voci, **probabilità** (tiro del motore, seeded), **soffitto** del budget gonfiato.
- **Numeri degli status**: durate, danni, e la **scala dei ranghi** (= scala di rarità) con la politica esatta di refresh.
- **Soglie delle classi di prova** e relative **ancore** (§7.4).
- **Verifica di terminazione (a)** o la **curva di escalation (b)** (§3) — gatekeepa la slice.

**Override di G su F (da applicare dove vive lo schema, non un buco di contenuto):** il campo `livello` è **rimosso da `EntitaGenerata`** — l'AI non lo emette, il motore lo lega alla profondità corrente dopo il gate (§8.2). Decisione di G (autorità delegata da F §4.2); forma da applicare in F.

**Conseguenze su `contracts` (da enumerare in I):** G introduce membri del contratto che F non elenca — la **proiezione di sola lettura della scheda** (§6.6) e l'**evento-intento di prova** (§7.1). Rientrano nel "Contesto" di F §7 (non sono un conflitto), ma sono DTO da definire esplicitamente quando si scrive I.

### 13.2 Nodo **J — Modello del tempo** (nuovo, a valle di G)

Promosso dalla ex-"cadenza del tempo": è il modello temporale del gioco, non un valore di G. **Due tempi**: *simulato* (turni/tick, motore seeded) vs *narrato* (chiamate AI).

- **1.0:** i due tempi; **fast-forward comprimente e interrompibile** (riposo, attraversamenti narrati: l'AI dichiara una **durata** come campo dell'output; il motore esegue i tick, fermandosi se scatta un evento — morte, fine status); **durata come campo dell'output narrativo**; **contatore di tempo-piano** (stato del World, serializzato). **Nessun cap di tempo nella 1.0** (decisione, non omissione: senza cap il fast-forward non è exploit). La **cadenza base** (stanza vs azione) è un valore **di J**, non deciso qui.
- **Post-1.0:** soglia + **fase di crollo** del piano — *corsa vincibile ma spietata*: il crollo non si annulla, ma si può batterlo sul tempo raggiungendo la `DiscesaPiano`; esito `MortePersonaggio` se non esci in tempo. È il **binario di mutazione (§5) esteso all'esplorazione** (motore muta il mondo a soglia + un secondo contatore), additivo sul contatore che la 1.0 ha già.
- **Aggancio a G:** G possiede solo il gancio "gli status ticcano per `process()` risolto (§4, FNC §6.4); il **valore** della cadenza è delegato a J". **Dipende da G** (binario di mutazione, status, bucket sempre-attivo); **accoppiato a H** (serializzazione del contatore).

### 13.3 Nodi **post-I**

- **Memoria generativa** (la "wiki"): meta-store a livello di **guscio** (app-level). Paletti: riciclo **solo di selezione+narrazione, mai stat** (il motore ricalcola); **replay = seed + snapshot wiki** congelato in cache; **doppio gate** (promozione in scrittura + ri-validazione in rilettura). MVP: il verbo **"procura"** (§9.4).
- **AI master** (§10): crea skill/abilità/oggetti/classi/PNG componendo primitivi; abilitato dal vincolo §10 e dal placement §9.2. Post-I.

---

## 14. Criteri di accettazione (verificabili)

Come ESP/F/IC/E, G chiude con criteri che un agente può **verificare di aver implementato**, non solo capire. Tag: **statico/grep** (ispezione del codice/schema) o **comportamentale** (test). I valori d'economia (Gruppo 2) non sono qui: questi verificano la **forma**.

- **G-1** *(grep)* — Il loop di combattimento è scritto `while ap > 0`, **non** "una azione e stop", anche con AP `max = 1`. *(§2.1)*
- **G-2** *(statico)* — Il placeholder-scheda porta **almeno**: `destrezza` (iniziativa), lo **stato-vita** del death-check, e i **campi che alimentano la proiezione DTO**. *(§2.2, §6.2, §6.5, §6.6)*
- **G-3** *(statico)* — Il tiebreak d'iniziativa usa una **chiave stabile** (seeded o ordine-di-spawn seeded / id di dominio), **mai** l'`id` di entità esper. *(§2.2, §6.3)*
- **G-4** *(comportamentale)* — La scelta delle azioni dei nemici è prodotta dal **motore** (seeded); **nessuna** chiamata LLM nel percorso di risoluzione del combattimento. *(§2.3, FNC §2)*
- **G-5** *(statico)* — **Nessun** handler di status nel bucket solo-combattimento; **un solo** sistema avanza ogni componente-status, nel bucket sempre-attivo. *(§4, FNC §6.2)*
- **G-6** *(statico)* — Il componente-status porta un campo `rango: int` e **nessun** riferimento/puntatore alla fonte. *(§4.3)*
- **G-7** *(comportamentale)* — Riapplicare lo **stesso** primitivo-status non crea una seconda istanza: residente e nuovo **competono per rango**, sopravvive uno (vincitore rinfresca la durata; rango ≤ rinfresca, non diluisce). *(§4.1, §4.2)*
- **G-8** *(comportamentale)* — Un'entità ha **al più un** componente per tipo di status; tipi diversi coesistono e ticcano in parallelo. *(§4.1)*
- **G-9** *(comportamentale)* — Aggiungere combattenti a uno scontro attivo avviene **a confine di turno**, da un sistema a priorità dichiarata, **mai** durante la risoluzione/iterazione di un'azione; le entità aggiunte sono distrutte su `CombatResolved`. *(§5.2, §5.3, §5.4)*
- **G-10** *(statico)* — La mutazione intra-fase è **distinta** dagli eventi di transizione: nessun `EncounterStarted` è (ri)emesso per aggiungere nemici a uno scontro in corso. *(§5.5)*
- **G-11** *(comportamentale)* — Il terminale di perdita è emesso da `MortePersonaggio`, **non** da `CombatResolved(sconfitta)`; nell'MVP il death-check mappa **sconfitta → morte**. *(§6.2)*
- **G-12** *(statico)* — I save sono keyati su un **id di dominio** del crawler, **mai** sull'id di entità esper; esiste **un solo** contesto run-World (`"run"`) e **un solo** run-World vivo alla volta. *(§6.3, §6.4)*
- **G-13** *(statico)* — L'AI riceve lo stato del protagonista **solo** via DTO di proiezione in `contracts`; **nessun** componente ECS vivo è passato al provider/prompt. *(§6.6)*
- **G-14** *(comportamentale)* — La **classe** di difficoltà di una prova è scelta **prima del tiro** ed è **immutabile dopo**; la **soglia** è calcolata dal motore (seeded), **mai** fissata dall'AI. *(§7.2)*
- **G-15** *(statico)* — Le **ancore** testuali delle classi vivono nel **catalogo**, non nel componente-prova (che porta solo l'etichetta di classe). *(§7.4)*
- **G-16** *(comportamentale)* — Il livello (profondità) avanza **solo** all'attivazione di una `DiscesaPiano` per intento del giocatore; **nessun** altro evento lo incrementa; la parola "scala" da sola non fa nulla. *(§8.1, §8.3)*
- **G-17** *(statico)* — Il campo `livello` **non** è un input dell'AI (assente da `EntitaGenerata`); il motore lo lega dopo il gate. *(§8.2)*
- **G-18** *(comportamentale)* — Ogni piano generato contiene **almeno una `DiscesaPiano` raggiungibile** dallo stato iniziale del giocatore; il gate rifiuta/ripara un piano senza uscita. *(§8.4)*
- **G-19** *(statico)* — **Una sola** firma verso il provider, `genera(prompt, schema) → candidato | None`; **nessun** secondo metodo per tipo di chiamata; prompt e gate vivono nel **motore**. *(§9.1, §9.2)*
- **G-20** *(comportamentale)* — Una `genera` in volo (fallita / cancellata / in retry) **non scrive** sul save; lo stato resta al turno precedente. *(§9.3, F §6.1)*
- **G-21** *(comportamentale)* — Il replay rigioca dalla **cache degli output validati** (uscita del gate) + seed, **senza** ri-chiamare l'LLM; il numero di chiamate interne al fan-out è invisibile al replay. *(§9.3)*
- **G-22** *(comportamentale)* — Le chiamate AI **non-gating** dello stesso turno (flavor §5.6, narrazione di prova §7) non bloccano la risoluzione; resta **una** sola chiamata **gating** per turno. *(§9.3)*
- **G-23** *(statico)* — I blocchi del catalogo sono **primitivi componibili**, non effetti monolitici. *(§10)*
- **G-24** *(comportamentale)* — Il burn-rate di uno status sul protagonista è **invariante al numero di nemici** in campo (uno status "k cariche" dura k turni del protagonista, sia in 1-vs-1 sia in 1-vs-N). *(§4.4)*
- **G-25** *(comportamentale)* — Una `TurnoNarrazione` che emette `EncounterStarted` è prodotta **in fase di narrazione** e ha `durata == TURNO` dopo il gate; nessuna entità di combattimento è materializzata prima del confine di tick. *(§5.1, F §2/F-14)*

> **Due liveness obbligatorie (gate di release, nodo A):** **G-L1** — ogni scontro **termina** (verifica (a) dimostrata *o* escalation (b) presente, §3); **G-L2** — ogni piano è **completabile** (G-18, §8.4). Sono le due condizioni senza cui "giocabile capo-a-fine" non è vero.

---

## Nota per l'aggiornamento dell'indice

In `progetto-indice-decisioni.md`:

- **Cruscotto dei nodi:** **G** da ⬜ a ✅. Sintesi: *"Loop AP-driven (clamp 1, talenti dopo) + iniziativa su destrezza, tiebreak seeded; decisione nemici = motore. Terminazione: 'morte squadra' = vittoria, garanzia di fine = vincolo su Gruppo 2 (verifica (a) o escalation (b)). Status: un'istanza per tipo, competizione per rango = rarità dell'applicatore copiata all'applicazione. Binario di mutazione del combattimento (motore-arbitrato, a confine di turno) = regola+contatore ora, sistemi additivi. Run: permadeath; morte ≠ sconfitta → terminale `MortePersonaggio` (death-check seeded); identità crawler = id di dominio (H), non id esper; save = World, un solo run-World vivo, slot = crawler (suspend-on-load); creazione = Carl predefinito; AI legge la scheda via proiezione DTO di sola lettura. Prove: AI inquadra/veste, motore tira seeded; difficoltà = classe da enum chiuso + gate; ancore nel catalogo; adattiva post-MVP nel gate-classe. Livello = profondità, motore, avanza solo su `DiscesaPiano` (≠ scala-arredo); il campo `livello` esce da `EntitaGenerata`. **Due liveness (gate di release):** lo scontro termina (§3) e il piano è completabile (§8.4, almeno una `DiscesaPiano` raggiungibile). Socket generativo = un verbo per schema, provider sottile + orchestrazione lato motore, cache all'uscita del gate, async-cancellabile; indirezione 'procura'. Vincolo su Gruppo 2: primitivi chiusi, composizione aperta. **Porta criteri di accettazione verificabili (G-1…G-25) + i gate G-L1/G-L2.** Dettaglio in `combattimento-forma-run.md`."*
- **Documenti del progetto:** aggiungere `combattimento-forma-run.md` (G) come ✅.
- **Rettifica di ACV §5.1:** l'evento di terminale che escala non è `CombatResolved(sconfitta)` ma **`MortePersonaggio`**; la sconfitta ne è il trigger principale, non automatico (autorità di G — §6.2).
- **Buchi di H risolti/informati da G:** slot save = **crawler** (multipli, suspend-on-load); destinazione sconfitta = `MortePersonaggio` → guscio → altro crawler; identità del crawler = id di dominio posseduto da H.
- **Buco di F risolto + override su F da applicare:** autorità su `livello` (F §4.2) = **motore** (profondità via `DiscesaPiano`); conseguenza sullo schema (§8.2, §13.1): il campo `livello` è **rimosso da `EntitaGenerata`** — F §2 (schema), F §4.2 (sottosezione, ora rovesciata) e F-3 (carve-out) vanno riscritti/semplificati di conseguenza. Chiamata di sola prosa = **stesso verbo** `genera` con schema banale (non percorso fratello).
- **Seam `livello` (era "da chiarire in I"):** **risolto da G** — campo rimosso da `EntitaGenerata`, applicato in F (vedi sopra). Non più un punto aperto.
- **Nuovo nodo aperto:** **J — Modello del tempo** (⬜), a valle di G, accoppiato a H. Voci in §13.2.
- **Nodi post-I annotati:** memoria generativa, AI master (§13.3).
- **Ordine di lavoro consigliato:** prossimo nodo strutturale **H** (persistenza/save — eredita slot=crawler, id di dominio, save=World); poi **J**; **I** per ultimo.
