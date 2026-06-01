# Provider LLM — Nodo **D** (astrazione provider) e gestione della key

> **Spec normativa per Claude Code.** Chiude il nodo **D**: quale provider AI usa l'MVP, dietro quale interfaccia, e come la chiave/configurazione seleziona il backend. Risolve D non come "scegliere un'API" ma come *confine di astrazione* che possiede il trasporto verso l'LLM e nient'altro.
>
> **Presuppone e non duplica** `esper-implementazione.md` (ESP), `fasi-narrazione-combattimento.md` (FNC) e `interfaccia-contratto.md` (IC). In caso di conflitto, valgono quei documenti per ciò che è di loro competenza; questo fissa solo D.
>
> **Convenzione di rimando.** `§N` *senza prefisso* = sezione di questo documento. Rimandi prefissati: **ESP §N**, **FNC §N**, **IC §N**.
>
> **Principio guida di questo documento:** *l'astrazione possiede il trasporto, non il dominio.* Il provider è uno strato sottile che traduce "genera un dato conforme allo schema" in una chiamata API concreta. Il giudizio su *cosa è valido* (catalogo + budget) e *cosa fare quando fallisce* resta nel motore.

---

## 0. Premesse ereditate (non rinegoziabili qui)

- **L'AI propone, il motore dispone.** L'AI è sorgente di varietà del contenuto; il motore arbitra ogni esito. *(FNC §1)*
- **Una sola chiamata LLM strutturata per turno di narrazione** → `{ prosa, entità:{archetipo, rarità, blocchi}, opzioni }`. *(FNC §5.1)*
- **Il gate di validazione (schema + catalogo + budget) sta nel motore**, mai nella membrana né nel bus. *(FNC §5.1, IC §4)*
- **L'AI non emette numeri**: seleziona da un catalogo chiuso dentro un budget imposto dal motore; le statistiche le deriva il motore. *(FNC §5.5)*
- **I tipi dello schema vivono nel modulo `contracts`**, dependency-free (sono DTO, non oggetti vivi). *(IC §2, IC §3)*
- **Fallimento LLM gestito esplicitamente**: timeout → retry limitato → fallback deterministico distinto per tipo di output. *(FNC §10)*
- **L'unica sorgente di nondeterminismo è l'LLM, ed è bordata** dal gate. *(FNC §9)*

Se una di queste non è chiara, fermarsi e rileggere i tre documenti a monte prima di implementare quanto segue.

---

## 1. Decisione D

**Astrazione provider** con interfaccia uniforme. Un solo backend reale nell'MVP — **Anthropic (Claude)** — scelto per resa narrativa. Il backend locale resta uno **slot innestabile non implementato**.

| Aspetto | Decisione | Razionale |
|---|---|---|
| Forma | Astrazione provider (interfaccia + implementazioni) | Disaccoppia il dominio dal provider; tiene il locale sostituibile senza toccare il contratto |
| Default e unico backend MVP | **Claude API** | Migliore aderenza allo schema e qualità della prosa per la voce narrativa/showrunner |
| Backend locale (es. Ollama) | **Slot innestabile, non implementato nell'MVP** | Un backend con aderenza allo schema peggiore aprirebbe un secondo set di rami di fallback da specificare e validare — fuori dalla fetta verticale di A. (Contingenza che ha fatto da innesco: nessun hardware locale adeguato a disposizione ora; ma a reggere la decisione è la ragione architetturale, non l'hardware, che cambia.) |

> **Opzione presa, non esercitata.** Esattamente come IC "spezza l'atomo" (contratto sì, trasporto no): qui si prende l'*astrazione* (che rende il locale innestabile domani a costo zero sul contratto) e **non** si esercita l'opzione *locale* adesso. Il giorno in cui serve un backend diverso, si scrive una nuova implementazione dell'interfaccia; il resto del progetto non cambia di una riga.

---

## 2. L'interfaccia

L'astrazione è **sottile** ed espone un solo verbo:

```
genera(prompt, schema) → candidato_conforme_allo_schema | None
```

- **`prompt` arriva già assemblato dal motore, ed è opaco per il provider.** La costruzione del prompt (voce/tono + contesto + **budget iniettato nel testo**, FNC §5.1) è **dominio**: la fa il motore, non il provider. Il provider riceve la stringa/messaggi già pronti e **non la formatta né la interpreta** — la trasporta e basta. Per questo `budget` e `contesto` **non** compaiono nella firma: sono ciò *da cui* il motore ha costruito il prompt, non argomenti che il provider deve maneggiare. Se comparissero, il provider dovrebbe sapere *come* il budget entra nel testo — la fuga di dominio che §3/§4 vietano.
- **`schema` resta esplicito** perché è ciò che pilota il meccanismo nativo di output strutturato del backend (§5); è anche ciò che rende il verbo **generico**, non cablato sulla generazione-stanza: lo stesso `genera` serve la futura classificazione del testo libero (FNC §5.6), stessa famiglia "intento → schema".
- **Contratto di ritorno uniforme.** Ogni backend restituisce un **candidato conforme allo schema, oppure `None`**. "None" = generazione non andata a buon fine (qualunque causa). Normalizza le differenze di qualità fra provider dietro un unico contratto.
- **Nessuna autorità di dominio.** L'astrazione **non** costruisce il prompt, **non** valida il catalogo, **non** controlla il budget, **non** sceglie il fallback. Conformità sintattica allo schema sì (è parte del "candidato"); appartenenza al catalogo e rispetto del budget no — quelli sono giudizi del motore (§4).

---

## 3. Cosa possiede l'astrazione (il trasporto) e cosa no (il dominio)

**Possiede (trasporto):**

- la chiamata API concreta e il **meccanismo nativo di output strutturato** del backend;
- timeout, retry limitato (FNC §10), pin del modello;
- la **lettura della chiave/configurazione** da config/env;
- la normalizzazione a "candidato conforme o `None`".

**Non possiede (dominio, resta nel motore):**

- la **costruzione del prompt** (voce/tono + contesto + budget iniettato nel testo — FNC §5.1); il provider riceve `prompt` già pronto e opaco (§2);
- il gate di validazione **catalogo + budget** (FNC §5.1, §5.5);
- la scelta del **fallback** (archetipo di default dentro il budget, o prosa neutra — FNC §10);
- l'arbitraggio di qualsiasi esito (FNC §1).

> Se l'astrazione iniziasse a validare il catalogo, a imporre il budget o a decidere il fallback, diventerebbe una **terza autorità** accanto al motore — violazione diretta di IC §4. La regola è netta: **l'astrazione possiede il trasporto, il motore possiede il dominio.**

---

## 4. Cosa significa "indipendente dalla key"

"Indipendente dalla key" significa **interfaccia uniforme**, **non** un client HTTP generico in cui si cambia solo la stringa della chiave.

- La **key/config seleziona *quale implementazione*** del provider usare, non *"quale stringa passo allo stesso client generico"*. *(Nell'MVP esiste una sola implementazione: nessun dispatch avviene davvero — è la **forma** del punto di estensione, non un selettore già esercitato. §1, D-2.)*
- Le differenze fra provider — in primis il meccanismo di output strutturato — vivono **dentro l'implementazione del backend**, dietro il contratto di §2. (Claude usa il proprio meccanismo nativo di structured output; un backend privo di grammatica userebbe prompt + parsing, con più fallback.)
- La key sta in **config/env**, letta dal layer; **mai** hard-coded nel codice o nei documenti. Mai in URL, mai nei log (coerente con le regole su dati sensibili).

> **Perché la formulazione conta.** Un client "OpenAI-compatible universale" farebbe colare le differenze di provider proprio nel punto — gate + fallback (FNC §10) — dove il progetto è più sensibile. Tenerle dietro l'interfaccia è ciò che mantiene il dominio pulito.

---

## 5. Output strutturato: meccanismo nel trasporto, verificato all'implementazione

Il meccanismo nativo di output strutturato di Claude esiste ed è il mezzo con cui il backend Anthropic onora il contratto "candidato conforme allo schema". **Vincoli normativi:**

- È **interno all'implementazione Anthropic** dell'astrazione, dietro `genera(...)`. Non compare nel motore, né in `contracts`, né nella membrana.
- **Si verifica sulla doc API attuale al momento dell'implementazione**, non a memoria — stessa disciplina già imposta per esper (ESP §0) e per l'API Worker di Textual (IC §6). In particolare: nome esatto dei parametri, header beta richiesto, helper di parsing/validazione, e **quali modelli supportano la feature** (la lista si muove).
- **Pin del modello e supporto allo structured output sono un vincolo *congiunto*, non due voci indipendenti.** Il modello scelto per la resa narrativa (la ragione di §1 per Claude) deve **anche** essere fra quelli che supportano la feature di output strutturato: il pin va posto su un modello che sia *insieme* forte in prosa **e** structured-output-capable. È il punto in cui la motivazione di §1 e il meccanismo di §5 potrebbero confliggere; dalle verifiche il supporto si è allargato nella famiglia, quindi in pratica probabilmente nessun conflitto — ma il vincolo si **scrive**, non si assume, e si **ri-verifica all'implementazione** (la lista dei modelli supportati si muove).
- **La grammatica garantisce il catalogo, non il budget.** L'AI emette solo campi categoriali (archetipo, rarità, blocchi = enum/registry): la grammatica li vincola. Il `livello` **non è emesso dall'AI** (profondità del piano, posseduta dal motore — G §8.1/§8.2; rimosso dallo schema, F §2). I **numeri non passano mai per lo schema** (li deriva il motore). Il budget ("rarità/blocchi entro il set ammissibile per la profondità del contesto") è un **vincolo di valore** che la grammatica non impone → il gate del motore resta obbligatorio comunque (FNC §5.5). *(Promemoria per G: se mai si introdurranno vincoli **fra campi** — es. un blocco legale solo per certi archetipi — anche quelli sfuggono alla grammatica e cadono nel gate. Per ora moot: FNC §5.5 dichiara ogni combinazione legale, "nessun caso speciale".)*

> **Il churn dell'API è assorbito qui.** Il meccanismo di structured output dell'API è cambiato nel tempo (parametri e helper si sono evoluti, il supporto modelli si è allargato). Poiché vive nel **trasporto** dietro il contratto, ogni cambiamento di questo tipo è assorbito nell'implementazione del backend e **non tocca** `contracts` né il gate del motore. È IC "contratto sì, trasporto no" verificato sul campo.

---

## 6. Fallimento: un solo backend, un solo set di rami

Con **un solo backend attivo** nell'MVP, F non deve specificare percorsi di fallback divergenti per provider. Sotto il meccanismo a grammatica scelto in §5, l'output è **conforme per costruzione** (il modello non può emettere JSON sintatticamente invalido): i rami reali sono **tre**.

1. **Errore di rete / timeout** → retry limitato; se persiste → fallback (vedi sotto).
2. **Output troncato / incompleto** (`stop_reason: "max_tokens"` → prefisso valido ma incompleto). **Non** è "JSON malformato": sotto grammatica quel caso non esiste. Il rimedio è diverso da un retry cieco — si **alza il limite di token o si accorcia la richiesta**; un retry a parità di richiesta ri-troncherebbe identico. Se non recuperabile → fallback. *(Il ramo "JSON non conforme" generico tornerebbe pertinente solo per un backend **senza** grammatica — il locale, assente nell'MVP.)*
3. **Refusal di sicurezza** (il modello rifiuta) → trattato come **generazione fallita**, **senza** retry (un refusal sullo stesso prompt si ripeterebbe deterministicamente) → fallback.

**Il fallback è tutto-o-niente, perché la chiamata è atomica.** La chiamata di narrazione è **una sola** e produce `{prosa, entità, opzioni}` insieme (FNC §5.1); §2 restituisce `candidato | None` per *quella* chiamata. Quindi non esiste lo stato "prosa valida ma entità no": un `None` fa cadere i tre campi **insieme**, e il motore applica i fallback **contemporaneamente**:

- `prosa` → testo neutro pre-confezionato.
- `entità` → il motore **pesca un archetipo di default dal catalogo, dentro il budget corrente** (FNC §5.5).
- `opzioni` → il **menu fisso di default** (`Combatti` / `Scappi` / `Altro`), così l'agente non lo inventa.

> **La distinzione di FNC §10 vale *tra fasi*, non dentro la chiamata di narrazione.** FNC §10 separa la *generazione strutturata di narrazione* (atomica: tutto-o-niente, sopra) dal *flavor di combattimento* (prosa separata, a valle della risoluzione): lì il flavor può semplicemente **mancare** e la risoluzione del motore prosegue intatta. Dentro la singola chiamata di narrazione, invece, il fallimento è atomico.

> Invariante (eredita FNC §10): nessuna fase resta bloccata oltre il timeout. Il fallimento dell'LLM degrada la *forma*, mai la *giocabilità*.

---

## 7. Dipendenze lasciate annotate (non si aprono qui)

- **Vincola F.** L'interfaccia dell'astrazione (§2) è **parte del contratto AI↔motore**; la sostanza di D viene portata dentro F, senza che F ridiscuta la scelta del provider. Il terzo ramo di fallback (refusal, §6) è un input per F.
- **Tocca H.** La cache degli output LLM validati (replay riproducibile = seed + cache) si appoggia naturalmente a questo confine — chiave plausibile = prompt seeded (anomalia inclusa, FNC §5.5) — ma **la proprietà e la chiave esatta della cache si fissano in H**, non qui.

---

## 8. Criteri di accettazione (verificabili)

- **D-1** Esiste un'astrazione provider con interfaccia uniforme `genera(prompt, schema) → candidato | None`; il motore dipende da questa interfaccia, mai da un client di provider concreto.
- **D-2** Esiste **una** implementazione reale (Anthropic). Il backend locale, se presente, è un punto di estensione dichiarato e non implementato; nell'MVP non avviene alcun dispatch fra backend.
- **D-3** L'astrazione **non** costruisce il prompt, **non** valida catalogo/budget e **non** sceglie il fallback (statico: il layer provider non importa il registry del catalogo né la tabella del budget, e non assembla il testo del prompt). Quei giudizi stanno nel motore.
- **D-4** La chiave/config è letta da config/env; nessuna chiave hard-coded nel codice o nei documenti; nessuna chiave in URL o log.
- **D-5** Il meccanismo nativo di output strutturato è confinato nell'implementazione Anthropic; non compare in `contracts`, nel motore o nella membrana. Il modello pinnato è insieme adatto alla prosa e structured-output-capable (§5).
- **D-6** I tre rami di fallimento (rete/timeout, **troncatura/incompleto**, refusal) convergono tutti su un esito gestibile dal motore; il refusal è trattato come generazione fallita senza retry; su `None` il motore applica i fallback dei tre campi (prosa neutra + archetipo di default + menu fisso) **insieme**.

---

## 9. Cosa NON facciamo (anti-over-engineering)

- ❌ Implementare un backend locale "perché un giorno servirà" — è uno slot, non codice MVP.
- ❌ Un client HTTP generico "OpenAI-compatible" come membrana del provider (§4).
- ❌ Far costruire il prompt, o validare il catalogo o il budget, al layer provider (§2, §3, §4).
- ❌ Cablare in F/I la firma esatta della chiamata di structured output a memoria, invece di verificarla all'implementazione (§5).
- ❌ Mettere la chiave in URL, log, codice o documenti (§4).

---

### Nota per l'aggiornamento dell'indice

In `progetto-indice-decisioni.md`:

- Tabella "Cruscotto dei nodi": **D** da 🟡 a ✅. Sintesi: *"Astrazione provider con interfaccia uniforme; Anthropic default e unico backend MVP; locale come slot innestabile non implementato; key da config/env; dettaglio in `provider-llm-key.md`."*
- Tabella "Documenti del progetto": aggiungere `provider-llm-key.md` (D) — *Astrazione provider, scelta backend MVP, gestione key* — ✅.
- Sezione "Nodi chiusi — decisione e razionale": aggiungere il paragrafo di D.
- "Ordine di lavoro consigliato": barrare il punto 2 ("Chiudere D").

Il prossimo nodo naturale è **F** (schema del contratto AI↔motore), che questo documento vincola (interfaccia dell'astrazione come parte del contratto, terzo ramo di fallback, dipendenza-cache annotata verso H).
