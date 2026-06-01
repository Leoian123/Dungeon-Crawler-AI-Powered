# Modello del tempo e scansione — Nodo **J**

> **Spec normativa per Claude Code.** Chiude la **forma** del nodo **J**: come scorre il tempo nel gioco, come l'AI ne propone la durata, come il giocatore lo fa avanzare e con quali garanzie. Fissa la *struttura* (i due tempi, il primitivo della durata, il tick come unità di avanzamento, le condizioni di scorrimento) e lascia ai proprietari i *valori* (cadenza, mappe, tabelle = Gruppo 2). Non descrive il combattimento (è G), né la persistenza (è H), né il ciclo vita (è E): vi si appoggia.
>
> **Presuppone e non duplica** `esper-implementazione.md` (ESP), `fasi-narrazione-combattimento.md` (FNC), `interfaccia-contratto.md` (IC), `provider-llm-key.md` (PLK), `architettura-ciclo-vita.md` (ACV), `contratto-ai-motore.md` (F), `combattimento-forma-run.md` (G), `persistenza-salvataggio.md` (H). In caso di conflitto, valgono quei documenti per ciò che è di loro competenza; questo fissa solo il tempo. **Conseguenza dichiarata:** J **aggiunge un campo allo schema** che è di F (`durata`, §3.4) — non è un conflitto, è un ritocco che F non aveva scritto, da applicare a F con lo stesso rigore dell'annotazione `livello` (rimosso) e di G §6.4.
>
> **Convenzione di rimando.** `§N` *senza prefisso* = sezione di questo documento. Rimandi prefissati: **ESP §N**, **FNC §N**, **IC §N**, **PLK §N**, **ACV §N** (= E), **F §N**, **G §N**, **H §N**.
>
> **Principio guida di questo documento:** *il tempo scorre per tick risolti, mai per orologio; l'AI propone una durata, il motore la dispone in tick.* J non inventa un secondo motore del tempo: riusa la primitiva di avanzamento che FNC ha già inchiodato (un `process()` per turno risolto) e ci posa sopra un vocabolario di durate, esattamente come G ha posato le classi di difficoltà sopra il tiro seeded.

---

## 0. Premesse ereditate (non rinegoziabili qui)

- **`process()` è guidato dal turno, non dall'orologio.** In entrambe le fasi si invoca **una volta per turno/azione risolta**, mai da un timer a frame liberi; il `dt` è **simbolico**; l'attesa async dell'LLM tiene viva la UI ma **non fa avanzare il gioco**. *(FNC §6.4, IC §6)*
- **Un solo proprietario dell'avanzamento.** Ogni componente con stato che avanza ha **un solo** sistema che lo muta; il tick degli status vive **esclusivamente** nel bucket sempre-attivo. *(FNC §6.2, G §4)*
- **L'AI propone, il motore dispone; l'AI emette categorie, non numeri.** Tutto ciò che ha conseguenza meccanica è un enum chiuso validato dal gate; i numeri li deriva il motore. *(F §2, FNC §5.5)*
- **Determinismo confinato.** L'unica sorgente di nondeterminismo è l'LLM, bordata dal gate; replay = seed + cache degli output validati; il fallback **non consuma il seed stream** ed è registrato. *(FNC §9, F §8, F-13)*
- **Nessun turno parziale tocca lo stato risolto.** Lo stato muta solo alla risoluzione di un tick; una chiamata fallita/cancellata non scrive nulla. *(F §6.1, F-11)*
- **Mutare lo stato di gioco è motore-arbitrato, a confine di turno**, mai durante la risoluzione/iterazione. *(G §5)*
- **`MortePersonaggio` è il terminale di morte, su death-check seeded; morte ≠ sconfitta.** *(G §6.2)*
- **Le transizioni di fase avvengono solo via evento tipizzato sul bus** (`EncounterStarted` / `CombatResolved`); le entità di combattimento nascono su `EncounterStarted` e muoiono su `CombatResolved`. *(FNC §4, §6.3)*
- **Il dado del motore (anomalia e affini) è un tiro seeded del motore, invisibile allo schema: l'AI lo narra, non lo invoca.** *(FNC §5.5, F §4.3)*
- **Il contatore di tempo-piano si serializza in H** come slot intero forward-compatible, **senza** logica temporale in H. *(H §14, H-18)*
- **Primitivi chiusi, composizione aperta.** Il vocabolario meccanico è del motore; estendere = aggiungere una voce, non rifare l'architettura. *(G §10)*

Se una di queste non è chiara, fermarsi e rileggere i documenti a monte prima di implementare quanto segue.

---

## 1. I due tempi — la tesi di J

Il gioco ha **due orologi distinti**, e J esiste per definire il cambio fra l'uno e l'altro:

- **Tempo simulato** — turni, tick. È il tempo del motore: seeded, deterministico, l'unità in cui avanzano gli status e si tira il death-check. È la *sostanza*.
- **Tempo narrato** — scandito dalle chiamate all'AI e dalla finzione che produce ("passa la notte", "cammini a lungo"). È la *vernice diegetica*.

> **Regola-cardine.** Il gioco avanza **solo** in tempo simulato (tick risolti). Il tempo narrato è una *lettura* del tempo simulato per il giocatore, **mai** un avanzamento autonomo. I "secondi" della finzione non sono mai tempo di parete e non muovono mai lo stato: muove lo stato il tick. *(eredita FNC §6.4)*

Tutto il resto di J è conseguenza di come si agganciano: la **durata** (§3) è il ponte — il modo in cui una battuta narrata dichiara *quanti tick simulati* costa.

---

## 2. Il tick come primitiva di avanzamento

Il **tick** è l'unità unica di avanzamento del tempo simulato. Un tick = un `process()` risolto (FNC §6.4). Avanzare il tempo significa **eseguire tick**, mai consultare un orologio. Ma il tick ha **due strati**, e tenerli distinti è ciò che evita di cablare il dado-evento nel loop di combattimento (dove la mutazione è di G, non di un dado generico).

### 2.1 Il tick condiviso (core) — universale, anche in combattimento

> **Il *core* del tick è: avanza gli status → death-check.** Gira a **ogni turno risolto**, in **entrambe** le fasi:
> 1. **Avanza gli status** — un solo proprietario, bucket sempre-attivo (FNC §6.2): il `SistemaVeleno` applica il suo delta qui, una volta.
> 2. **Death-check seeded** (G §6.2): se è morte, emetti `MortePersonaggio` e **il tick finisce**.
>
> **In combattimento il core è posseduto da G, non da J.** Lo scontro fa scorrere status e death-check **al confine di turno risolto come lo definisce G** (loop AP-driven, G §2; `process()` per azione risolta, FNC §6.4). J **non fissa *quante volte*** il core gira in uno scontro: se uno status ticca **per attivazione o per round** (in una mischia a più attori cambia il tasso di burn del veleno) è **semantica G-owned**. *(Valore deciso e **consegnato a G** in §15: per-turno-dell'entità — invariante al numero di nemici, accoppiato alla cadenza base per-stanza di §4.)* J **non aggiunge nulla** a questo strato in combattimento: lo eredita e lo lascia a G. *(Lo strato 2.2 — sotto — è ciò che J posa **solo fuori** combattimento.)*

### 2.2 Il tick di scorrimento — solo fuori combattimento

> Fuori combattimento (passa-turno §6, fast-forward §5), il tick **estende** il core con due passi che J possiede:
> 3. **Dado-evento** (§8): tiro seeded del motore.
> 4. **Effetto a confine di tick**: se l'esito cambia stato/fase (es. imboscata), lo si emette **ora**, a tick chiuso (§9).
>
> **I passi 3–4 NON girano in combattimento.** Lì, "modificare lo scontro in corsa" è il **binario di mutazione di G §5** — un sistema seeded del motore (`PianoRinforzi`: stato via Canale A, reveal via Canale B), a confine di turno — **non** un dado-evento generico. Un dado di scorrimento dentro il loop AP calpesterebbe l'autorità di G §5 e duplicherebbe la mutazione. Per costruzione, i passi 3–4 sono disabilitati in combattimento perché i meccanismi che li portano (passa-turno, fast-forward) sono disabilitati lì (§13, J-13).

J **non** avanza gli status per conto suo, in nessuno dei due strati: orchestra *quante volte* girare lo scorrimento (2.2), non mette le mani sui componenti-status (li avanza il loro unico proprietario). Reintrodurre un tick di status dentro J sarebbe il doppio-tick che FNC §6.2 vieta.

---

## 3. Il primitivo `Durata`

### 3.1 Forma: enum chiuso in `contracts`

> La durata è una **classe nominata da enum chiuso**, non un numero. Vive in `contracts` come **solo vocabolario** (nomi, zero valori numerici), alla pari di `Blocco` o delle classi di difficoltà `bronzo…celestiale`:
>
> ```python
> # modulo `contracts` — vocabolario, dependency-free. I VALORI sono di G/Gruppo 2.
> class Durata(str, Enum):
>     TURNO       = "turno"        # la cadenza base (1 passo)
>     UN_ATTIMO   = "un_attimo"
>     UN_POCHINO  = "un_pochino"
>     UN_BEL_PO   = "un_bel_po"
>     # ... estendibile (§3.7)
> ```
>
> **Presupposto strutturale (come G §4 per le rarità):** la `Durata` ha un **ordine totale**, e la mappa `Durata → carico-tick` nel catalogo è **non-decrescente** rispetto a quell'ordine (`TURNO` è il minimo = la cadenza base). I *valori* sono Gruppo 2; l'**esistenza** dell'ordine totale e della monotonìa è **forma, qui** — senza di essa "≥ base" (§3.4) e il clamp del crollo (§11) non hanno semantica.

### 3.2 Doppia natura: etichetta diegetica + carico-tick

> Ogni voce di `Durata` porta, **nel catalogo del motore** (non nello schema), due cose:
> - un'**etichetta diegetica** — i "secondi di finzione" (`TURNO ≈ 6 s`, `UN_ATTIMO ≈ 30 s`, `UN_POCHINO ≈ 1 min`, …): **flavour** che lo showrunner usa per narrare;
> - un **carico-tick** — il numero di tick di cadenza che la durata comprime: **la sostanza** che il motore esegue.
>
> I secondi sono **finzione**; i tick sono **gioco**. Cablare i secondi come tempo reale reintrodurrebbe il bug clock-vs-turno che FNC §6.4 ha chiuso.
>
> **Le etichette diegetiche sono illustrative e si fissano *dopo* la cadenza (§4/§15).** I valori `≈ 6 s / 30 s / 1 min` qui sopra presumono una cadenza fine: sotto cadenza per-stanza un tick fuori combattimento vale minuti, e le etichette cambiano. Non vanno letti come un impegno: sono Gruppo 2, calibrati una volta scelta la cadenza.

### 3.3 La traduzione vive nel catalogo, non nel componente

> La mappa `Durata → (etichetta diegetica, carico-tick)` è **formula del motore** e vive nel **catalogo/registry di dominio**, **mai** nello schema `contracts` né nel componente. Lo schema porta **solo l'etichetta** (la voce dell'enum), come l'entità-prova porta solo la classe (G §7.4). È la spaccatura nomi/numeri di F: `UN_BEL_PO` è un nome come `celestiale`; la tabella che lo trasforma in tick è la formula, e sta nel motore.

### 3.4 La durata è un campo dell'output (conseguenza su F)

> Quando l'AI **valuta la risoluzione di un'azione o inquadra un turno di narrazione**, dichiara una `Durata` come **campo dell'output**. Concretamente: il campo `durata: Durata` vive su `TurnoNarrazione` (lo schema della **fase di narrazione**), non su ogni chiamata.
> - **Fuori combattimento**, l'AI può dichiarare una `Durata` ≥ base per le battute comprimenti (riposo, attraversamento).
> - **In combattimento non c'è override da fare, perché non c'è campo.** Le chiamate AI in combattimento sono **sola prosa** — `genera(prompt, Flavor)` con schema banale `{testo}` (F §5), che **non porta `durata`**. Il costo-tick di un turno di combattimento è **fisso = `TURNO`**, cablato nel loop AP-driven (G §2) come carico del tick condiviso (§2.1), **non** un campo emesso. Così "un solo verbo `genera`, comportamento per schema" (F §5.1) regge: il campo esiste dove serve (narrazione), è assente dove non deve esistere (combattimento).
> - **La battuta che *entra* in combattimento è un caso di bordo (apertura, §15).** Quando il dado-evento evoca un'imboscata (§8), comporre/presentare lo scontro può richiedere una `TurnoNarrazione` al confine di tick *mentre sei ancora in `NARRAZIONE`* — che porta il campo `durata`. **Semantica voluta: la battuta d'ingresso non comprime tempo → `durata = TURNO`** (un'imboscata è una singola battuta, non un "passa la notte"). Nell'MVP è **inerte per costruzione**: appena `FaseCorrente == COMBATTIMENTO` lo scorrimento è off (J-13), quindi una `durata` lunga **non fa partire alcun fast-forward**. Non è un buco di sicurezza, è un buco di *semantica* (il campo c'è e non significa nulla in quell'istante). La **chiusura pulita** (il gate, anche se altrove identità, clampa la battuta d'ingresso a `TURNO`) e l'esatto **timing della composizione rispetto al flip di fase** sono **territorio di G §5.1**; J fissa solo la semantica voluta e deferisce il meccanismo.
>
> Questo è un **ritocco allo schema di F** (territorio di F), da annotare come l'annotazione `livello`: finché F non è ritoccato, vale J per il campo `durata`. La nota provvisoria copre l'**aggiunta del campo a `TurnoNarrazione`**; non c'è un secondo meccanismo d'override da specificare. *(provvisoria sul confine F/J)*

### 3.5 Il gate sulla durata (punto d'innesto preso ora)

> La `Durata` proposta dall'AI **passa per un gate**: `Durata proposta → gate del motore → carico-tick`, **mai** `Durata → tick diretto`. Il motore **accetta o riconduce** la durata, come la classe di prova passa per il gate-di-classe (G §7.3) e l'entità per il budget-gate.
> - Nell'MVP il gate è **identità** (ci si fida dell'enum chiuso, nessun tetto): in 1.0 una durata lunga **non salta nessun pericolo** — più tick = più tiri di dado-evento (§8) = più esposizione, non meno; e il fast-forward è comunque bloccato in presenza di status (§5). Coerente con §10/§15: *senza cap, non c'è exploit*.
> - L'innesto si prende **ora soltanto** per due ragioni *post-MVP*: fornire l'**aggancio** dove il clamp della fase di crollo (§11) ricondurrà le durate, ed **evitare il retrofit** (lezione di G §7.5). Non risolve un problema della 1.0; predispone il post-1.0.

### 3.6 Determinismo della durata — *forma ora, beneficio replay post-MVP*

> La durata di un **turno in fallback** (F §6.3) è **designata e deterministica** (es. `TURNO`), **mai** pescata dallo stream RNG del gioco. Stessa disciplina dell'archetipo di default.
>
> **Scope (annotazione obbligatoria, come H l'ha imposta per F-13/G-21).** Questa regola è della stessa famiglia di F-13: nell'MVP ne vale **solo la metà "forma"** — *il fallback non consuma il seed stream*, vera e verificabile già ora (J-16). La motivazione completa ("senza, un fallback al replay desincronizza i tiri successivi") si appoggia alla **macchina di replay, che è post-MVP** (H §8.3): quindi nell'MVP la durata-designata è **forma presa ora** per non desincronizzare *quando* il replay sarà acceso, non un beneficio live. Senza questa riga, J introdurrebbe un invariante della famiglia F-13/G-21 senza lo scope che H ha reso obbligatorio.

### 3.7 Estendibilità (composizione aperta)

> Aggiungere una durata (es. la *routine mattutina da 15 minuti* richiesta dalla player base) = **una voce all'enum + una riga al catalogo**. Non si tocca né l'interfaccia dell'AI né la logica di risoluzione. È l'invariante "primitivi chiusi, composizione aperta" (G §10): lo stesso meccanismo che domani l'AI master userà per *vestire* ciò che genera.

---

## 4. Cadenza base — *(il valore delegato da G; **CHIUSA: per-stanza**)*

> La **cadenza base** è cosa conta come "un passo" (= un tick, = `TURNO`) **fuori dal combattimento**. **Decisione: per-stanza.** Una stanza è una *battuta* (ritmo DCC); i sistemi sempre-attivi avanzano **una volta per stanza** in esplorazione (es. il veleno scorre per ambiente, non per singola azione). *In combattimento la cadenza è semantica di G — vedi sotto e §15.*
>
> G l'aveva **delegata a J** come "valore di J" (G §13.2); J la **chiude qui** come per-stanza.

**Perché per-stanza, e accoppiata alla cadenza di combattimento.** La scelta è presa **in coppia** con la cadenza del core in combattimento (§2.1/§15, deferita a G): per-stanza fuori **+ per-turno-dell'entità dentro** (una volta a round per entità, invariante al numero di nemici). Così il burn-rate di uno status è un *beat* coerente nei due regimi:

| Veleno "3 cariche" | Esplorazione (per-stanza) | Combattimento (per-turno-entità) |
|---|---|---|
| dura | 3 stanze | 3 turni del protagonista (≈ 3 round) |

La combinazione opposta (per-azione fuori + per-attivazione dentro) farebbe evaporare il veleno in un singolo round affollato e scorrere troppo finemente in esplorazione: asimmetria evitata. La traduzione `Durata → carico-tick` (es. `UN_BEL_PO` = N stanze) e le etichette diegetiche (§3.2) si calibrano su questa scelta (Gruppo 2).

> **Nota:** la cadenza non cambia la *forma* di J (il tick resta l'unità, la `Durata` resta l'enum): fissa solo *a cosa corrisponde un tick fuori combattimento*. Il lato combattimento resta semantica di G (§2.1), chiusa nello stesso passo decisionale (§15).

---

## 5. Fast-forward (downtime narrato)

Il **fast-forward** è la compressione narrata di più tick in una sola battuta: l'AI dichiara una `Durata` (§3.4), il motore esegue il relativo carico-tick **uno per uno**, fermandosi su interrupt.

> **Condizione di abilitazione (forte): il downtime richiede un momento davvero tranquillo.** Il fast-forward narrato si avvia **solo** se:
> - `FaseCorrente == NARRAZIONE` (fuori combattimento), **e**
> - **nessuno status dannoso** è attivo sul protagonista, **e**
> - **nessuno status unsafe** è attivo (§7).
>
> *Razionale:* **i tick negativi non permettono il downtime** — non si riposa mentre il veleno morde. Se hai uno status dannoso, il downtime è bloccato; la valvola in quel caso è il **passa-turno** (§6).

> **Interruzione.** Il fast-forward esegue **fino a** N tick (il carico della `Durata`) e si **interrompe** al primo tick in cui scatta:
> - `MortePersonaggio` (la morte tronca — §9), oppure
> - un **evento del dado** (§8) che richiede attenzione (es. imboscata).
>
> Allo stop, lo stato dei tick **già eseguiti è reale e atomico** (F-11): non si annulla nulla, semplicemente i tick restanti non girano. Al replay l'interruzione si riproduce identica (il tiro che l'ha causata è seeded a un tick deterministico).

> **Aborto della richiesta in volo.** La cancellazione di una chiamata LLM superata (giocatore che agisce mentre il dungeon "pensa") è **trasporto**, gestita dal worker `exclusive=True` (IC §6) — è **distinta** dall'interruzione *di dominio* del loop di tick (sopra), che vive sul bus. Non confonderle.

---

## 6. Passa-turno (tick manuale, token-zero)

Il **passa-turno** è la valvola che fa avanzare **un singolo tick** senza spendere una chiamata LLM. Esiste perché, quando il downtime è bloccato da uno status dannoso (§5), il giocatore deve poter far **scorrere** quello status (es. aspettare che il veleno scada) senza bruciare token a ogni tick.

> **Condizione di abilitazione (debole): safe = fuori combattimento e senza status *unsafe*.** Il passa-turno si abilita se:
> - `FaseCorrente == NARRAZIONE`, **e**
> - **nessuno status unsafe** è attivo (§7).
>
> Gli **status dannosi a risoluzione-motore (veleno, brucia, …) NON bloccano** il passa-turno: anzi è lì che serve. Solo gli **status unsafe** (§7) lo bloccano, perché quel tempo va *giocato*, non saltato.

> **Non è una `genera` degenere.** Il passa-turno **non riempie alcuno schema**: è la **procedura del tick** (§2) invocata **una volta**. Token-zero **salvo evento**: la narrazione parte solo nel tick in cui il dado (§8) produce qualcosa; altrimenti la UI mostra il delta deterministico ("−4 HP, veleno: 2 turni rimasti") senza passare dal modello.

> **Granularità MVP: un click = un tick** (= un tiro di dado-evento). Coerente con l'esempio: *Turno 1 → click skip → il dado evoca un'imboscata → Turno 2 → "combatti o scappi?"*. *(Un "tieni-premuto interrompibile" muto è una **convenienza post-MVP**: stesso costo-token, riusa il loop di §5 con narrazione spenta; non in 1.0.)*

---

## 7. Gli assi degli status: `valenza` e `risoluzione`

Lo status ha **due proprietà di tipo, ortogonali**, entrambe nel catalogo e di sola lettura. Insieme determinano se blocca il downtime e/o il passa-turno.

- **`valenza: BENEFICO | DANNOSO | NEUTRO`** — il *segno* dello status. È un **flag del tipo-status nel catalogo**, **non** derivato dal segno del delta: un `Stordito` o un `Rallentato` sono **DANNOSI** pur non avendo un delta-HP, e derivare "dannoso" da `delta < 0` li mancherebbe. Il flag è esplicito, con lo stesso rigore di `risoluzione`.
- **`risoluzione: MOTORE | AI`** (`AI` ⟺ **unsafe**) — *come* si risolve il tick. `MOTORE` = deterministico, zero LLM (veleno, brucia, rigenerazione). `AI` = il tick **richiede l'LLM** perché altera *come* agisci (berserk, confusione): è ciò che chiamiamo **unsafe**.

| Esempio | `valenza` | `risoluzione` | Blocca downtime (§5)? | Blocca passa-turno (§6)? |
|---|---|---|:--:|:--:|
| rigenerazione | BENEFICO | MOTORE | no | no |
| veleno, brucia | DANNOSO | MOTORE | **sì** (dannoso) | no |
| stordito, rallentato | DANNOSO | MOTORE | **sì** (dannoso) | no |
| berserk, confusione | DANNOSO | AI (**unsafe**) | **sì** | **sì** |

> **Entrambi i flag vivono sul *tipo* nel catalogo**, non sul componente vivo (sono proprietà del tipo, non dell'istanza), come `unsafe` e come le ancore delle classi di prova (G §7.4). *Forma* presa ora; i *valori* (quali status sono DANNOSO/AI) = Gruppo 2.

> **Non toccano lo stacking.** `valenza` e `risoluzione` sono di **sola lettura** e alimentano i predicati di §5/§6. La regola di G §4 resta intatta: un'istanza per tipo, **competizione per rango**; il vincitore porta i flag del proprio tipo (stanno nel catalogo), niente da ricalcolare.

I due predicati, leggibili dal motore senza alcun giudizio dell'AI:
- **downtime** ⟺ `NARRAZIONE ∧ nessuno status DANNOSO ∧ nessuno status unsafe`;
- **passa-turno** ⟺ `NARRAZIONE ∧ nessuno status unsafe`.

*(Nota: ogni status `unsafe` dell'MVP è anche `DANNOSO`, quindi blocca già il downtime per la prima clausola; il "nessuno status unsafe" nel predicato-downtime è ridondante oggi ma esplicito per robustezza — un ipotetico buff `BENEFICO ∧ unsafe` deve comunque bloccare il downtime perché va giocato.)*

---

## 8. Il dado-evento (tiro del motore)

> Ogni tick di scorrimento del tempo (passa-turno e fast-forward) include un **dado-evento**: un **tiro seeded del motore**, della **stessa famiglia dell'anomalia** (FNC §5.5, F §4.3). Il dungeon non è un luogo ospitale: il tempo che passa può attirare guai.

- **Dominio del motore, non dell'AI.** Il dado **decide il fatto**; l'AI, semmai, ne **veste il verdetto** dopo (risolvi prima, narra dopo). L'AI non valuta "è rischioso qui": è un tiro, seeded.
- **Token-zero salvo evento.** Il dado che **non** scatta è muto (nessuna chiamata). La `genera` parte **solo** nel tick in cui l'evento c'è.
- **Replay-safe.** Stesso seed, stesso tick → stesso esito del dado → stessa eventuale transizione.
- **Probabilità contestuale.** La **tabella** del dado-evento per contesto (riposo vs skip vs zona pericolosa), con probabilità e voci, è **Gruppo 2**: la *forma* (un tiro seeded a ogni tick) è qui; i *numeri* no.

> **Può innescare un cambio di fase.** Un esito del dado può essere un'**imboscata**, che emette `EncounterStarted` — ma **solo a confine di tick** (§9), mai a metà.

---

## 9. Ordine dentro il tick e precedenza della morte

L'ordine interno del **tick di scorrimento** (§2.2) è **normativo**, non incidentale:

> **avanza status → death-check seeded → (se morte: `MortePersonaggio`, fine tick) → dado-evento → effetto a confine di tick.**

Le ragioni:

- **La morte ha precedenza e tronca il tick.** `MortePersonaggio` è un **terminale di run** (G §6.2): una volta scattato, il protagonista non è più soggetto di gioco. Tirare il dado o emettere un'imboscata *dopo* significherebbe creare entità di combattimento (FNC §6.3) attorno a un cadavere e flippare `FaseCorrente` per poi doverlo disfare — mezzo-stato sporco, contro F-11. *Se il tick di veleno ti uccide, niente imboscata: sei morto al tick, hand-off al guscio.*
- **L'evento agisce solo a confine, e solo su un vivo.** Far comparire nemici *durante* la risoluzione di un tick è vietato da G §5 (mutazione a confine di turno). Il dado **deposita** un esito; a tick chiuso, se è un'imboscata, il motore emette `EncounterStarted` sul bus (l'unica via di transizione, FNC §4).
- **Auto-disabilitazione gratuita.** Appena `FaseCorrente == COMBATTIMENTO`, i predicati di §5/§6 sono falsi → passa-turno e fast-forward **si disabilitano da soli**, senza una riga dedicata. Non puoi skippare dentro l'imboscata che lo skip ha evocato.

> **Simmetria da preservare in I.** La morte tronca l'avanzamento **ovunque** il tempo scorra (fast-forward §5, passa-turno §6, combattimento G): un solo terminale, trattato in modo identico. Non scrivere un "death handling" per ogni meccanismo: c'è *la morte tronca il tick*, punto.

---

## 10. Il contatore di tempo-piano (slot di H)

> Il **contatore di tempo-piano** è stato del World, **serializzato in H** come slot intero forward-compatible (H §14, H-18). **J possiede la semantica; H la serializzazione.** Nessuna logica temporale vive in H; J non spinge logica dentro H.

- Avanza secondo la cadenza (§4), per **un solo proprietario** nel bucket sempre-attivo (FNC §6.2), come ogni componente con stato.
- **Avanza in entrambe le fasi.** Vivendo nel bucket sempre-attivo, il contatore avanza al tick condiviso (§2.1) *anche in combattimento*: uno scontro lungo brucia tempo-piano. **Conseguenza:** il contatore somma unità **non omogenee** — turni in combattimento vs passi di cadenza (stanze/azioni, §4) fuori. **Irrilevante in 1.0** (nessun cap, §10), ma il crollo post-1.0 (§11) leggerebbe un contatore di unità ambigue: **da disambiguare quando si scrive il crollo** (es. contare solo i tick di esplorazione, o normalizzare le due unità). Annotato qui perché I non erediti l'ambiguità tacitamente.
- **Nella 1.0 il contatore avanza ma non gatekeepa nulla.** È predisposizione: **nessun cap di tempo** (decisione di G, non omissione — senza cap il fast-forward non è un exploit). Ciò che lo *consuma* (il crollo del piano) è post-1.0 (§11).

---

## 11. Post-1.0: fase di crollo del piano

> Oltre la 1.0, il contatore di tempo-piano acquista un **soglia + fase di crollo**: una *corsa vincibile ma spietata*. Il crollo non si annulla; si batte sul tempo **raggiungendo la `DiscesaPiano`** (G §8). Se non esci in tempo → `MortePersonaggio`.

- È il **binario di mutazione (G §5) esteso all'esplorazione**: il motore muta il mondo a soglia + un secondo contatore, **additivo** sul contatore della 1.0, **motore-arbitrato a confine**, mai un percorso parallelo.
- Il **gate sulla durata (§3.5) è il punto d'aggancio del clamp**: durante il crollo, il motore può ricondurre le durate proposte (niente `UN_BEL_PO` mentre il piano cede).
- Simmetria: il crollo è all'esplorazione ciò che l'escalation (fallback "b") è al combattimento (G §3) — la rete che garantisce che il piano **si chiuda** (liveness, G §8.4).

---

## 12. Criteri di accettazione (verificabili)

Tag: **statico/grep** (ispezione di codice/schema) o **comportamentale** (test).

- **J-1** *(grep)* — `Durata` vive in `contracts`, è **solo vocabolario** (nessun `int`/valore numerico); la mappa `Durata → (etichetta, tick)` vive nel **catalogo del motore**, non nello schema né nel componente. *(§3.1, §3.3)*
- **J-2** *(statico)* — Il campo `durata` è di tipo `Durata` (enum), **mai** un intero di secondi/tick emesso dall'AI, e vive **solo su `TurnoNarrazione`** (fase di narrazione); lo schema `Flavor` (chiamate di combattimento, F §5) **non** porta `durata`. *(§3.4)*
- **J-3** *(comportamentale)* — La durata proposta dall'AI **passa per un gate** (`durata → gate → tick`, mai diretto); nell'MVP il gate può essere identità, ma il punto d'innesto esiste. *(§3.5)*
- **J-4** *(grep)* — **Nessun** avanzamento del tempo è guidato dall'orologio di parete: niente `sleep`/timer che muove lo stato di gioco; ogni avanzamento è un `process()` per tick risolto, `dt` simbolico. *(§1, §2; FNC §6.4)*
- **J-5** *(statico)* — Il tick degli status è avanzato da **un solo proprietario** nel bucket sempre-attivo; J **non** avanza status per conto suo. *(§2; FNC §6.2, G §4)*
- **J-6** *(comportamentale)* — Il fast-forward (downtime) si avvia **solo** se `NARRAZIONE ∧ nessuno status dannoso ∧ nessuno status unsafe`; comprime **fino a** N tick (la `Durata`) e si **interrompe** su morte o evento, lasciando reali i tick eseguiti (atomico). *(§5)*
- **J-7** *(comportamentale)* — Il passa-turno si abilita **solo** se `NARRAZIONE ∧ nessuno status unsafe`; gli status dannosi a risoluzione-motore **non** lo bloccano; avanza **esattamente un** tick. *(§6, §7)*
- **J-8** *(statico)* — Il passa-turno **non** è una chiamata `genera`: nessuno schema viene riempito; è `process()` invocato una volta; **token-zero salvo evento**. *(§6)*
- **J-9** *(statico)* — Sia `valenza` (`BENEFICO|DANNOSO|NEUTRO`) sia `risoluzione` (`MOTORE|AI`=unsafe) sono proprietà del **tipo**-status nel **catalogo**, **non** campi del componente vivo, e **non** alterano lo stacking (un'istanza per tipo, competizione per rango). In particolare `valenza` è un **flag esplicito**, **non** derivato da `delta < 0` (uno `Stordito` senza delta-HP è comunque `DANNOSO`). *(§7)*
- **J-10** *(comportamentale)* — Il dado-evento è un **tiro seeded del motore** (famiglia anomalia); l'AI non lo decide (semmai narra il verdetto); al replay stesso seed → stesso esito. *(§8)*
- **J-11** *(comportamentale)* — Ordine del **tick di scorrimento** (§2.2, fuori combattimento): **status → death-check → (morte ⇒ `MortePersonaggio` e fine tick, niente dado) → dado-evento → effetto a confine**. La **morte tronca** prima dell'evento. *(§9)*
- **J-12** *(comportamentale)* — Un esito del dado che cambia fase (es. imboscata) emette `EncounterStarted` **solo a confine di tick**, mai durante la risoluzione, e **solo su protagonista vivo**. *(§8, §9; G §5, FNC §4)*
- **J-13** *(comportamentale)* — Appena `FaseCorrente == COMBATTIMENTO`, passa-turno e fast-forward sono **disabilitati automaticamente** (predicato-safe falso), senza logica dedicata. *(§9)*
- **J-17** *(statico/comportamentale)* — Il **tick condiviso** (status → death-check) gira a ogni turno risolto **in entrambe le fasi** (in combattimento è posseduto da G, al confine di turno come lo definisce G; J **non** fissa la cadenza per-attivazione vs per-round — §15); il **dado-evento e l'effetto a confine (§2.2) NON girano in combattimento** — lì la mutazione dello scontro è il binario di G §5 (`PianoRinforzi`, Canale A/B), non un dado generico. Nessun dado-evento è cablato nel loop AP. *(§2.1, §2.2; G §2, §5)*

> *J-17 è elencato qui per adiacenza tematica con J-11–J-13 (lo split del tick); è numerato in coda per stabilità degli ID.*
- **J-14** *(statico)* — Il contatore di tempo-piano è un campo dello stato del World serializzato in H (slot H §14/H-18); J vi pone la semantica, **nessuna** logica temporale vive in H; avanzato da un solo proprietario. *(§10)*
- **J-15** *(comportamentale)* — **Nessun cap di tempo nella 1.0**: il contatore avanza ma non gatekeepa nulla; il crollo che lo consuma è post-1.0. *(§10, §11)*
- **J-16** *(statico)* — La durata di un turno andato in **fallback** è **designata e deterministica** (es. `TURNO`), **mai** pescata dallo stream RNG del gioco. *(§3.6; F-13)*

> **Liveness di tempo (collegata al nodo A):** **J-L1** — non esiste percorso in cui lo stato di gioco avanza **senza** un tick risolto (no avanzamento "a orologio"); **J-L2** — ogni meccanismo di scorrimento (downtime, passa-turno) si **arresta** su `MortePersonaggio` (nessuna morte "fuori campo" non terminale). Insieme assicurano che il tempo non possa né scappare al controllo né uccidere senza chiudere la run.

---

## 13. Invarianti rafforzati da questo documento

- **Il tempo scorre per tick risolti, mai per orologio.** Il tempo narrato è lettura, non avanzamento. *(rafforza FNC §6.4)*
- **L'AI propone una durata (categoria), il motore dispone (tick).** Nomi nello schema, numeri nel catalogo, gate nel motore. *(rafforza F §2, G §7.2)*
- **La morte tronca il tick prima di ogni evento.** Un solo terminale, trattato identico ovunque il tempo avanzi. *(rafforza G §6.2, F-11)*
- **Mutare la fase è motore-arbitrato, a confine di tick.** L'imboscata nasce come tiro dentro il tick, come evento solo al confine. *(rafforza G §5, FNC §4)*
- **Primitivi chiusi, composizione aperta — anche nel tempo.** Estendere = una voce all'enum + una riga al catalogo. *(rafforza G §10)*
- **Determinismo confinato anche nel tempo.** Durata e dado-evento sono seeded/registrati; il replay riproduce compressioni e interruzioni; il fallback non consuma il seed stream. *(rafforza FNC §9, F §8, F-13)*

---

## 14. Cosa NON facciamo (anti-over-engineering)

- ❌ Cablare i "secondi" come tempo reale, o usare `sleep`/timer per avanzare il gioco. *(§3.2; FNC §6.4)*
- ❌ Far emettere all'AI un numero di tick/secondi: emette una `Durata` (categoria), il motore deriva. *(§3.4)*
- ❌ Far **valutare all'AI** se sei "safe" o se "stai per morire": il predicato-safe è del motore, la morte è seeded. *(§7, §9)*
- ❌ Fermarsi "N tick prima della morte" **guardando il futuro del seed**: sbirciare desincronizza il replay. La morte si gestisce **reattiva**, troncando il tick in cui scatta. *(§9; F-13)*
- ❌ Permettere downtime/fast-forward **con status dannosi attivi**: sarebbe una zona franca dal pericolo. La valvola è il passa-turno, non il riposo. *(§5)*
- ❌ Far ticcare gli status **dentro J**: un solo proprietario, bucket sempre-attivo. *(§2; FNC §6.2)*
- ❌ Emettere `EncounterStarted` **a metà tick** o attorno a un personaggio già morto. *(§9)*
- ❌ Mettere la mappa `Durata → tick` o i flag di status (`valenza`, `risoluzione`/`unsafe`) nel **componente** o in `contracts`: vivono nel **catalogo** del motore. *(§3.3, §7)*
- ❌ Derivare "dannoso" da `delta < 0`: `valenza` è un **flag esplicito** del tipo (mancherebbe gli status di controllo senza delta-HP). *(§7)*
- ❌ Mettere **logica temporale in H**: H serializza il contatore, J lo interpreta. *(§10; H §14)*
- ❌ Far girare il dado-evento come **chiamata LLM** o **non-seeded**. *(§8)*
- ❌ Cablare il **dado-evento / effetto a confine (§2.2) nel loop di combattimento**: in combattimento gira **solo** il tick condiviso (status → death-check, §2.1); la mutazione dello scontro è il binario di G §5, non un dado generico. *(§2.2, J-17)*
- ❌ Trattare il passa-turno come una `genera` con schema banale: **non c'è schema**, è un tick. *(§6)*

---

## 15. Decisioni ancora aperte

> **Aggiornamento (saldo cambiali).** La cadenza base (§4) è **chiusa: per-stanza**, accoppiata alla cadenza di combattimento. Le due voci sotto sono ora **consegne a G** (valore deciso, da recepire in G), non più aperture indecise.

- **Cadenza del core in combattimento → consegna a G: *per-turno-dell'entità*.** Uno status avanza al confine del turno *dell'entità che lo porta* (una volta a round per entità), **non** a ogni `process()` globale: il burn-rate è invariante al numero di nemici (§2.1, §4). È semantica G-owned: **valore deciso, da recepire in G** (loop di turno / bucket sempre-attivo in combattimento).
- **`durata` della battuta d'ingresso al combattimento → consegna a G §5.1.** Semantica `TURNO` (di J); meccanismo deciso: il **gate clampa a `TURNO`** la `TurnoNarrazione` che emette `EncounterStarted`, e la **composizione avviene in `NARRAZIONE` al confine di tick, prima del flip**. Da recepire in G §5.1 (timing) e nel gate di F (clamp). Nell'MVP comunque inerte per costruzione (J-13).
- **Granularità del vocabolario `Durata`** *(ancora aperta, Gruppo 2)* — scala generica piccola + **attività che referenziano una `Durata`** (raccomandato: tiene l'enum ortogonale e stabile, come il rango sta nell'applicatore non nello status) **vs** durate attività-specifiche di prima classe nell'enum.
- **Contenuti (Gruppo 2):** la mappa `Durata → (secondi diegetici, carico-tick)` (con ordine totale e monotonìa, §3.1, calibrata su per-stanza); la **tabella del dado-evento per contesto** (riposo / skip / esplorazione) con probabilità e voci; i flag di status (`valenza`, `risoluzione`/`unsafe`) per ogni tipo; i parametri del **clamp** di crollo e la **disambiguazione dell'unità del contatore** in combattimento vs esplorazione (§10, post-1.0).

---

## Nota per l'aggiornamento dell'indice

In `progetto-indice-decisioni.md`:

- **Cruscotto dei nodi:** **J** da ⬜ a ✅ *(forma chiusa; cadenza base chiusa = per-stanza)*. Sintesi: *"Due tempi (simulato/narrato); il tempo avanza solo per tick risolti (eredita FNC §6.4). **Tick a due strati:** core condiviso (status → death-check) a ogni turno risolto, anche in combattimento (lì posseduto da G, al confine come lo definisce G; cadenza in combattimento = per-turno-dell'entità, consegnata a G, §15); strato di scorrimento (+ dado-evento + effetto a confine) **solo fuori combattimento** — in combattimento la mutazione è il binario di G §5, non un dado. **Cadenza base in esplorazione = per-stanza** (§4), accoppiata a per-turno-entità in combattimento → burn-rate dello status coerente e invariante alla folla. `Durata` = enum chiuso in `contracts` (vocabolario, ordine totale + carico-tick monotòno), mappa nel catalogo del motore; l'AI dichiara `durata` su `TurnoNarrazione` (non su `Flavor`/combattimento), passa per un gate (`durata→gate→tick`, innesto preso solo per il clamp post-1.0; in 1.0 niente exploit perché niente cap); fallback con durata designata (forma ora, replay post-MVP). Fast-forward (downtime) abilitato solo se NARRAZIONE ∧ nessuno status DANNOSO ∧ nessuno unsafe; interrotto da morte o dado-evento, tick eseguiti reali (F-11). Passa-turno = tick manuale token-zero, abilitato se NARRAZIONE ∧ nessuno unsafe (gli status DANNOSI a risoluzione-motore NON lo bloccano); non è una `genera`. Status: due flag di tipo nel catalogo — `valenza` (BENEFICO|DANNOSO|NEUTRO, esplicita, non da delta) e `risoluzione` (MOTORE|AI=unsafe); non toccano lo stacking. Dado-evento = tiro seeded del motore (famiglia anomalia), token-zero salvo evento, può innescare `EncounterStarted` a confine di tick. Ordine del tick di scorrimento: status → death-check (morte tronca) → dado-evento → effetto a confine; la morte ha precedenza ovunque il tempo avanzi. Contatore di tempo-piano = slot di H (J la semantica, H la serializzazione), avanza in entrambe le fasi (unità da disambiguare per il crollo), nessun cap nella 1.0; crollo del piano post-1.0 = binario di mutazione esteso. Criteri J-1…J-17 + gate J-L1/J-L2. Dettaglio in `tempo-modello-scansione.md`."*
- **Documenti del progetto:** aggiungere `tempo-modello-scansione.md` (J) come ✅.
- **Convenzione di rimando:** aggiungere **J** = `tempo-modello-scansione.md`.
- **Conseguenza su F (RITOCCO APPLICATO):** **`TurnoNarrazione` acquista il campo `durata: Durata`** (enum chiuso in `contracts`); l'AI lo seleziona, il motore lo mappa via gate→tick. **`Flavor` invariato** (nessun `durata`): in combattimento il costo-tick è fisso `TURNO`. Il **gate clampa a `TURNO`** la battuta che emette `EncounterStarted` (C3). *(Cambiale C1+C3 saldata in F; vedi `saldo-cambiali-J.md`.)*
- **Consegna a G (RITOCCO APPLICATO):** cadenza status in combattimento = **per-turno-dell'entità** (C2); composizione dell'incontro in `NARRAZIONE` al confine di tick prima del flip, con clamp `durata=TURNO` sulla battuta d'ingresso (C3). *(Saldate in G §5.1 e nel loop di turno.)*
- **Buchi chiusi/informati da J:** la "cadenza del tempo in narrazione" (ex-FNC §12) ha ora **forma chiusa e cadenza decisa** (per-stanza fuori, per-turno-entità dentro). Lo **slot del contatore di tempo-piano** (H §14) è riempito di semantica. Restano solo aperture di calibrazione (Gruppo 2): granularità del vocabolario `Durata`, mappe e tabelle, unità del contatore per il crollo post-1.0.
- **Nodi aperti → J:** spostare in "Nodi chiusi"; aggiungere il paragrafo di razionale; barrare il punto 7 ("J") nell'Ordine di lavoro.
- **Ordine di lavoro:** prossimo e **ultimo**: **I** (documento finale per Claude Code) — raccoglie A→J. **Niente più gate decisionali aperti** sul modello del tempo (cadenze chiuse, cambiali saldate); I parte da `saldo-cambiali-J.md` come checklist.
- **Nodi post-I / post-1.0 annotati (da J):** fase di crollo del piano (binario di mutazione esteso, §11); "tieni-premuto interrompibile" del passa-turno (convenienza, §6); probabilità/difficoltà adattiva del dado-evento (Gruppo 2, §8).
