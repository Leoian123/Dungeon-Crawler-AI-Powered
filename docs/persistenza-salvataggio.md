# Persistenza e salvataggio — Nodo **H**

> **Spec normativa per Claude Code.** Chiude il nodo **H**: come una run sopravvive allo spegnimento e come si ricostituisce. Fissa la **forma** della persistenza (cosa si serializza, in che formato, quando, con quali garanzie) e i **confini** che la scrittura su disco non deve perforare. Non descrive il gameplay (è G), non il ciclo vita cross-World (è E): vi si appoggia.
>
> **Presuppone e non duplica** `esper-implementazione.md` (ESP), `fasi-narrazione-combattimento.md` (FNC), `interfaccia-contratto.md` (IC), `provider-llm-key.md` (PLK), `architettura-ciclo-vita.md` (ACV), `contratto-ai-motore.md` (F), `combattimento-forma-run.md` (G). In caso di conflitto, valgono quei documenti per ciò che è di loro competenza; questo fissa solo la persistenza. **Eccezione dichiarata:** H **ri-categorizza** G §6.4 sul punto della cache delle stanze (§2/§8) — G la collocava *dentro* il save, H la promuove a **store separato**. F §8 delega a H "formato/chiave/proprietà" della cache; H **interpreta** quella delega come comprensiva dell'**identificazione** fra cache delle stanze (G) e cache di replay (F) — identificazione che è **inferenza di H, non testo esplicito di F** (§2). La collocazione *dentro-il-save vs sidecar* è propriamente sul **confine G/H** e resta **provvisoria** fino al ritocco di G.
>
> **Convenzione di rimando.** `§N` *senza prefisso* = sezione di questo documento. Rimandi prefissati: **ESP §N**, **FNC §N**, **IC §N**, **PLK §N**, **ACV §N**, **F §N**, **G §N**.
>
> **Principio guida di questo documento:** *la persistenza tocca i dati, mai conosce i sistemi.* H serializza e deserializza **stato** — componenti dato-puro, singleton, metadati — e non sa nulla di *come* quei dati nascono o vengono consumati. E una seconda riga, perché regge metà delle decisioni: *lo stato è il World, effimero come il crawler; il contenuto validato è patrimonio, e vive altrove.*

---

## 0. Premesse ereditate (non rinegoziabili qui)

- **Il save *è* il run-World.** Contiene il protagonista, `FaseCorrente`, lo stato d'esplorazione (e — vedi §2 — un *riferimento* alla cache, non la cache stessa). Non è taggato dall'entità giocatore. *(G §6.4)*
- **Un solo run-World vivo, contesto sempre `"run"`.** Caricare il crawler B = teardown del corrente → load di B nello stesso contesto. L'identità sta nel save, mai nel nome del World. *(G §6.4, ACV stazione 3b)*
- **Slot = crawler, suspend-on-load.** Multipli, ma gli slot *sono* i crawler: un crawler vivo = un save unico, non slot liberi. Niente save-scum. *(G §6.1/§6.4)*
- **Permadeath: la morte invalida il save corrente.** `MortePersonaggio` (death-check seeded) e invalidazione sono lo **stesso seam**. *(G §6.2/§6.3)*
- **Identità del crawler = id di dominio posseduto da H** (vedi §5: **uuid**), assegnato alla nascita del protagonista, salvato sia in un componente sia come metadato del save — **mai** l'id di entità esper. *(G §6.3)*
- **H possiede il meccanismo, E colloca le stazioni.** Il guscio è dove `current_world` cambia; E piazza nuova-partita/load/teardown, H possiede il *come*; il livello save/load è l'**unica autorità su `current_world`**. *(ESP §0.1, ACV §8)*
- **Aggancio di serializzazione = `components_for_entity()`; `FaseCorrente` si serializza col resto** (è stato di gioco nel World). *(FNC §6.1)*
- **Seam di replay da F:** il record cacheable è "output validato **oppure** marcatore di fallback"; il fallback **non consuma il seed stream**; chiave plausibile = **prompt seeded**. *(F §8, F-13)*
- **Gli handler in-run si deregistrano al teardown** (il bus è process-global e dura più della run). *(ACV §5.2)*
- **`switch_world`/`delete_world` mai dentro un `process()`;** la scrittura della persistenza precede il teardown, su confine pulito. *(ESP §0.1, E-4, ACV §5.3)*

Se una di queste non è chiara, fermarsi e rileggere i documenti a monte prima di implementare quanto segue.

---

## 1. Decisione H (sintesi)

| Aspetto | Decisione | Dove vive | § |
|---|---|---|---|
| Formato dello stato | **JSON-family** (leggibile, debuggabile); pickle **scartato**; MessagePack/CBOR come slot di compattazione futuro | file di stato | §3 |
| Due artefatti | **stato** (World effimero) e **Archivio degli Output Validati** (patrimonio), separati per file e ciclo vita | §2 | §2, §8 |
| Forma del blob di stato | entità via `components_for_entity`, singleton (`FaseCorrente`, contatore di profondità), stato d'esplorazione, metadato d'identità, `schema_version`, model id; **tag di tipo** per il round-trip | motore/H | §4 |
| Serializzazione dei componenti | responsabilità di **H**, non dei componenti (i componenti restano dataclass ignare) | H | §4.3 |
| Identità del crawler | **uuid**, non contatore (tiene vuota la categoria «stato di guscio persistente») | metadato + componente | §5 |
| Cadenza | **a evento/comando**: uscita, ritorno al menu, morte, salvataggio a mano; **scrittura prima dello `switch_world`** | guscio + H | §6, §7 |
| Morte | **invalida** lo stato (non salva); terminale `MortePersonaggio` | §7 | §7 |
| Uscita volontaria (6c) | **nell'MVP**, come caso del save-on-exit, non primitiva nuova | §7 | §7 |
| Cache delle stanze | **sidecar** (separato dallo stato), **lasco** per il gameplay, **replay-capace** in forma | Archivio (§8) | §8 |
| Compressione | **solo sul sidecar** (stato in chiaro) | §3, §8 | §3 |
| Contratto di load | **valida e degrada con grazia** su corruzione/versione; load a tre fasi solo se servono referenze | H | §9 |
| Atomicità | **temp + rename** per file; **ordine di durabilità**; **backup di sola recovery** invisibile al giocatore | H | §10 |
| Persistenza della chat | **nessuna**: la chat è derivata (stato + Archivio) | — | §11 |
| Stato di guscio persistente | **categoria nominata, non implementata** (sentiero per wiki / dono NieR) | §12 | §12 |
| prompt caching | **trasporto**, vive nel provider, **fuori da H** | PLK | §13 |

I **valori** (path esatti, soglie di compressione, numero di retry sul load) e la **semantica del tempo** (contatore di profondità → §14) non sono di H come *principio*: H ne fissa la forma, J e l'implementazione il resto.

---

## 2. Due artefatti, due nature (ri-categorizzazione di G §6.4)

G §6.4 dichiarava che la cache delle stanze sta *dentro* il save. H la **separa**, e il motivo non è solo tecnico: i due hanno **nature diverse**.

- **Lo stato** è il run-World: protagonista, `FaseCorrente`, stato d'esplorazione, contatore di profondità, metadato d'identità. È **effimero come il crawler** — muore con lui (permadeath, G §6.2). È l'unità che il *load* ricostruisce.
- **L'Archivio degli Output Validati** (§8; *nome di lavoro:* «Ananas Cabaret») è contenuto generato dall'AI, **validato dal motore, congelato**, keyed sul prompt seeded. È **patrimonio**: può sopravvivere alla run che l'ha prodotto (dono NieR, §12) e promuoversi a scope più ampi.

> **Decisione.** Stato e Archivio sono **due artefatti separati per file e per ciclo vita**. Il save di stato contiene un *riferimento* alla porzione di Archivio della run (es. il nome del file sidecar), **non** il contenuto. La cache non è un sottocampo del save: è un cittadino di un livello diverso dell'architettura.

Questo risolve la tensione con "save = run-World": il **run-World è il save** (effimero), l'**Archivio è uno store** (potenzialmente più longevo). Coabitano per una run, ma non si fondono.

> **Base d'autorità (onesta sui limiti).** F §8 delega a H "proprietà, chiave esatta e formato della cache" (e "formato del log, chiave, marcatore di fallback") — quindi **formato/chiave/proprietà sono delegati esplicitamente**, e "layout" ne è una glossa ragionevole. Ma F §8 parla della *cache degli output validati per il replay* e G §6.4 della *cache delle stanze*, e **lascia aperto se siano lo stesso oggetto**. **H interpreta** la delega di formato/layout di F §8 come **comprensiva di questa identificazione** (le due cache sono un unico Archivio) e ne decide la collocazione (sidecar, non dentro il save). Questa è **inferenza di H**, non testo esplicito di F: la collocazione *dentro-il-save vs sidecar* è propriamente sul **confine G/H**.
>
> **Annotazione cross-documento (da applicare quando si ritocca G) — §2 è provvisorio fino ad allora.** G §6.4 ("la cache delle stanze sta dentro il save") va annotato con un rimando a H §2/§8: la cache è **sidecar**, ri-categorizzata come Archivio. Finché G non è ritoccato, **vale H** per il layout (eccezione dichiarata in testa), ma la decisione resta **provvisoria** sul confine G/H e va confermata al ritocco di G.

---

## 3. Formato

> **Lo stato si serializza in un formato JSON-family** (testo strutturato, leggibile, debuggabile, con nomi di campo espliciti). **Pickle è scartato.**

Razionale, dalle pratiche consolidate ⟨peerdh, GearBlocks⟩ e dalla documentazione Python ⟨pydocs-pickle⟩:

- **Pickle accoppia il save al codice.** La definizione della classe dev'essere importabile e vivere nello stesso modulo di quando l'oggetto è stato serializzato ⟨pydocs-pickle⟩: un save fatto la settimana scorsa si rompe quando rinomini o sposti un componente. Sotto **permadeath + suspend-on-load** (un solo save, irrecuperabile, riscritto in posto) un save che non si carica più è una run morta. I componenti del gioco **cambiano spesso** in sviluppo → pickle è la persistenza che si rompe ai refactor.
- **Pickle è opaco e insicuro.** Non ispezionabile a occhio (cruciale sotto permadeath, dove la riparabilità è una proprietà di sicurezza, non un vezzo), e deserializzare dati non fidati è un vettore di esecuzione di codice arbitrario; JSON no ⟨pydocs-pickle⟩.
- **I componenti sono dato-puro** (ESP §1): mappano in modo pulito su dict → JSON, con un piccolo serializzatore per tipo (§4.3). Il costo "JSON non serializza classi custom" ⟨peerdh⟩ qui è **meccanico**, non un ostacolo.

> **Il bloat non è un problema di formato, è un problema di *testo*, e si combatte dove vive.** Il contro di JSON è la dimensione ⟨peerdh⟩, ma lo stato è minuscolo e limitato (un protagonista + singleton): non cresce con la run. Ciò che cresce è il **testo della prosa** nell'Archivio — grosso in *qualsiasi* formato. Si schiaccia con la **compressione** (l'approccio che in pratica ha battuto perfino il binario: JSON/BSON + Deflate ⟨GearBlocks⟩), non scegliendo pickle.

> **Compressione: solo sul sidecar (§8).** Lo **stato resta in chiaro** (piccolo, e lo si vuole ispezionabile sotto permadeath); l'**Archivio viaggia compresso** (è lì che vive il testo che cresce, e lo si ispeziona di rado). La ri-validazione in rilettura e il dono decomprimono prima di leggere — un passo, non un problema.

> **Via di fuga, non esercitata (spezza l'atomo, come C/PLK).** Se mai dimensione o performance dovessero mordere, la migrazione è **JSON → MessagePack/CBOR** (binario ma *stesso modello dati*, quasi drop-in ⟨thatonegamedev⟩), **non** un binario posizionale. Si prende il contratto leggibile ora, il trasporto compatto resta opzione futura. Schema-based (flatbuffers/protobuf) è fuori scope: più ottimale ma più oneroso ⟨thatonegamedev⟩, e l'MVP non ne ha bisogno.

---

## 4. Forma del blob di stato

Il save di stato è un documento JSON-family con queste parti.

### 4.1 Contenuto

- **Le entità persistenti**, ciascuna come i suoi componenti via `components_for_entity()` (FNC §6.1). Nell'MVP la sola entità persistente è il **protagonista** (le entità di combattimento sono effimere, distrutte su `CombatResolved` — FNC §6.3, G §6.3); la forma generalizza comunque a N entità.
- **I singleton del World**: `FaseCorrente` (FNC §6.1) e il **contatore di profondità** (il `livello`, G §8.1; semantica del tempo rimandata a J — §14).
- **Lo stato d'esplorazione** (topologia del piano visitato, posizione, ciò che serve a ricostruire dove sei).
- **Il master seed della run** *(distinto dal "prompt seeded" di §8)*: il seme RNG da cui derivano deterministicamente tiri, spawn, death-check, iniziativa (G, FNC §9). È **ciò che si duplica nei metadati dell'Archivio** (§8.1), perché il replay/dono rigioca **da turno 0** e gli basta il seme. Separatamente, lo **stato/posizione dell'RNG** (a che punto dello stream sei) serve **solo al resume mid-run** ed è dettaglio d'implementazione (stato interno dell'RNG vs seed + contatore di estrazioni): vive **solo nel blob di stato**, **non** va duplicato nell'Archivio — il dono non riprende da metà run. **Attenzione:** il *prompt seeded* (chiave di lookup dell'Archivio, §8) **non è** il master seed; sono cose diverse e vivono in posti diversi.
- **Il metadato d'identità**: l'**uuid** del crawler (§5).
- Un **`schema_version`** (intero) per le migrazioni (§9).
- Un **model id / versione** del modello LLM sotto cui la run è stata generata (§8, §12): forward-compatibility a costo zero per replay/dono ⟨jenova⟩.
- Un **riferimento** al sidecar dell'Archivio della run (§2), non il suo contenuto.

### 4.2 Tag di tipo per il round-trip

> Ogni componente serializzato porta un **tag di tipo** (una stringa stabile) che mappa, in deserializzazione, sulla classe componente da istanziare. Un **registry tag→tipo** vive in H (è l'equivalente del *type registry / object factory* che la serializzazione ECS reale usa per istanziare dinamicamente i componenti ⟨godot-ecs⟩). Il tag è **stabile** e disaccoppiato dal nome della classe Python, così un rename del componente non rompe i save (si aggiorna la mappa, non il dato).

### 4.3 La traduzione è di H, non dei componenti

> **Responsabilità.** La traduzione dato↔JSON appartiene al **livello di persistenza**, non ai componenti. **Niente `to_dict()`/`from_dict()` dentro i componenti** (sporcherebbe i dati con conoscenza del formato di salvataggio — la membrana si crepa dal lato opposto). I componenti restano **dataclass ignare**; H possiede un serializzatore per tipo (o un dispatch sul tag). I dati non sanno di essere salvati; H sa come salvarli. La freccia di dipendenza punta in una sola direzione.

### 4.4 Nessun riferimento esper durevole (invariante)

> **Nessun `id` di entità esper viene mai serializzato come riferimento durevole.** L'id esper è un intero sequenziale interno al World, **riciclato** al teardown/nuova-partita (G §6.3): un riferimento salvato penzolerebbe o collegherebbe l'entità sbagliata al reload. Estende G-3 (tiebreak su id di dominio, mai esper) e G §4.3 (il rango è **copiato** dall'applicatore, mai un puntatore alla fonte effimera) alla persistenza.

> **Conseguenza, se mai l'invariante dovesse cedere.** Il problema dominante della serializzazione ECS reale è proprio la **rottura delle referenze fra entità** al reload, perché gli id si riciclano ⟨marcin, godot-ecs⟩. La soluzione standard è il **load a tre fasi**: creare i gusci di tutte le entità (rimappando gli id), attaccare i componenti vuoti, poi popolarli — così le referenze si risolvono ⟨godot-ecs⟩. **Nell'MVP non serve** (stato = un'entità + singleton, zero referenze inter-entità per costruzione). Va implementato **solo se** un componente futuro introducesse una referenza durevole; finché l'invariante §4.4 regge, il load è diretto.

---

## 5. Identità del crawler — uuid

> L'identità di dominio del crawler è un **uuid**, generato alla nascita del protagonista (ACV stazione 3a), salvato come metadato del save **e** in un componente del protagonista (G §6.3).

Perché **uuid** e non contatore — la scelta non è cosmetica, è coerenza con la decisione di §12:

- Un **contatore** ("prossimo id crawler") deve vivere **fuori da ogni save di crawler**, o riusi gli id fra run. Questo obbliga a un inquilino reale della categoria «stato di guscio persistente» (§12) **già nell'MVP**.
- Lo **uuid** lo genera indipendente e collision-free, senza stato app-level condiviso. Tiene quella categoria un **sentiero vuoto** per la wiki/dono, esattamente come deciso (§12).

> **Conseguenze pratiche.** Il **filename del save** può essere l'uuid stesso. L'**indice dei crawler** (cosa mostra il menu) si ottiene con uno **scan della cartella dei save**, **non** uno store esplicito — nessun registro app-level da mantenere. Allinearsi all'uso, da pratiche su sistemi persistenti, di **id immutabili e stabili come ancora di sessione** ⟨alibaba-dm⟩, qui senza derivarli da hash perché l'uuid basta.
>
> **Perché lo scan non deve fare deep-parse.** Ogni file di stato porta in testa un **piccolo blocco di metadati di elenco** (uuid, nome/etichetta, profondità, timestamp dell'ultima sessione), così il menu legge **solo l'intestazione** per elencare, senza deserializzare l'intero save (in chiaro, potenzialmente grande). **Degrado in scan** (gemello del contratto di load, §9): un save la cui intestazione **non parsa** compare nel menu come voce **«illeggibile/corrotta»** — non fa crashare lo scan né scompare in silenzio. (Il degrado in *load* di §9 riguarda il caricamento; questo riguarda l'*elenco*.)

---

## 6. Cadenza del save

> Lo snapshot del World si scatta **a evento/comando**, mai a timer: **uscita dal gioco, ritorno al menu, morte, salvataggio a mano** (più, come caso, l'uscita volontaria — §7). Nessuna scrittura guidata dall'orologio.

Conseguenze, tutte volute:

- **"Save = World intero" costa poco**, perché è **raro** (a evento, non a tick). La preoccupazione "snapshot dell'intero World a ogni salvataggio è bloat/costo" si dissolve: salvi di rado.
- **Si scollega da J.** Non salvi sui tick del tempo: il contatore di tempo-piano finisce *dentro* lo snapshot, ma **non guida** la cadenza. H non dipende dalla semantica temporale di J (§14).
- **Il salvataggio a mano è il meccanismo di scrittura vero**; gli altri terminali (§7) lo richiamano. È l'unico trigger **in-run**: il World **sopravvive**, snapshot in posto, nessuna transizione di contesto (ACV stazione 5, Crit. 1).

Questo è anche coerente con la tradizione del genere: i roguelike usano tipicamente **un solo save per personaggio, ricaricabile solo per riprendere** una partita in corso, proprio per impedire il save-scum ⟨tvtropes-roguelike⟩ — che è il nostro suspend-on-load (G §6.1).

---

## 7. I terminali e la persistenza

> **Regola unificata.** Al **confine run→guscio** la persistenza **agisce**, sempre **prima** dello `switch_world` (mai dentro un `process()` — ESP §0.1, ACV §5.3): **salva** (uscita / menu / 6c) oppure **invalida** (morte 6a, **vittoria/piano-completato 6b**). Il salvataggio a mano è invece **in-run** (il World sopravvive, §6). I **tre terminali** run→guscio di ACV (sconfitta, piano-completato, uscita volontaria) hanno **tutti** un'azione di persistenza definita; nessun esito terminale resta in-run senza azione.

| Terminale | Regime | Azione di persistenza | § di E |
|---|---|---|---|
| Salvataggio a mano | in-run | **salva** (snapshot in posto, World sopravvive) | ACV stazione 5 |
| Uscita dal gioco | run→guscio | **salva** prima del teardown | — |
| Ritorno al menu | run→guscio (6c) | **salva** prima del teardown | ACV 6c |
| Uscita volontaria (salva-ed-esci) | run→guscio (6c) | **salva** prima del teardown | ACV 6c |
| **Vittoria / piano-completato** | run→guscio (6b) | **invalida** lo stato (run conclusa, §9.4); il dono resta post-MVP (§12) | ACV 6b |
| Morte (`MortePersonaggio`; in MVP trigger sconfitta→morte, G-11) | run→guscio (6a) | **invalida** lo stato (§9.4) | ACV 6a / G §6.2 |

> **La scrittura precede lo switch, non lo accompagna.** Non si "salva allo `switch_world`": si salva *mentre il run-World è ancora vivo e attivo*, poi la **shell** esegue il teardown su confine pulito (hand-off di E, ACV §5.3). Il flush del save è l'**ultima** azione in-run, non la prima del guscio. Dopo `switch_world(default)→delete_world("run")` il World non esiste più: salvarlo dopo è impossibile.

> **Uscita volontaria 6c — nell'MVP.** Sotto suspend-on-load + un-solo-run-World, "abbandonare la run per tornare al menu" **collassa** in "salva ed esci": non c'è una semantica di abbandono distinta. 6c entra in v1 come **caso del save-on-exit**, **non** come primitiva nuova. Chiude il buco delegato da ACV §8 ("se 6c è nell'MVP").

> **Morte ≠ salvataggio.** Stesso confine, azione **opposta**: la morte **invalida** (permadeath, G §6.2/§6.3), non salva. Death-check e invalidazione sono lo stesso seam.

---

## 8. L'Archivio degli Output Validati (sidecar)

> **L'Archivio** (*nome di lavoro:* «Ananas Cabaret») è uno **store di record discreti**, ciascuno un contenuto generato dall'AI e **validato dal motore** (uscito dal gate), **congelato**, **keyed sul prompt seeded** (F §8). Vive in un **file sidecar**, separato dallo stato (§2), **compresso** (§3). Nell'MVP ha **un solo inquilino**: la cache delle stanze.

### 8.1 Forma del record

> Ogni record contiene **solo selezione + narrazione, mai statistiche** (le stat le ricalcola sempre il motore — paletto del doppio gate ⟨indice-progetto §nodi-post-I⟩). Il record è **autosufficiente** (replayabile senza il blob di stato del crawler che l'ha prodotto) e **promovibile** (§12). Forma F-13: "output validato **oppure** marcatore di fallback" — anche se nell'MVP il ramo-marcatore **non viene popolato** (§8.3).

> **Metadati dell'Archivio (distinti dai record).** L'Archivio porta un piccolo blocco di metadati a livello di store: una **copia del master seed della run** (§4.1) e il **model id** (§4.1). Vivono qui *oltre* che nel blob di stato per una ragione precisa: alla fine-run lo stato viene **invalidato** (§7, §9.4), quindi se il seed stesse *solo* nello stato, al momento del dono (§12) sarebbe già perso. Duplicarlo nei metadati dell'Archivio fa sì che l'Archivio promosso porti con sé tutto ciò che serve a rigiocare la run — il seed **viaggia con la storia**, non solo con lo stato effimero.

### 8.2 La cache è la sede della coerenza narrativa

> **Coerenza = congela-una-volta, rileggi-sempre.** Una stanza già visitata **non si rigenera** (otterresti contenuto diverso da una macchina probabilistica), si **rilegge** dal record congelato (G §6.4: "non rigenerare al ritorno"). Il determinismo qui è quello di una **memoization**, **non** del modello LLM (che non è riproducibile): il prompt seeded è la **chiave di lookup**, non una promessa che ri-chiamando otterresti lo stesso testo.

Questo allinea il progetto al consenso dei sistemi LLM-DM, che identificano nella **statelessness** del modello la causa della perdita di coerenza ("dice sì a tutto", sbaglia l'AC, confonde i nomi) ⟨jenova⟩, e la curano **separando la memoria a lungo termine dall'inferenza** e iniettando i fatti ⟨alibaba-dm⟩ — esattamente "risolvi prima, narra dopo" (FNC) applicato allo stato.

### 8.3 Lasco per il gameplay, replay-capace in forma

> La cache MVP è **lasca**: un cache-miss **degrada a "rigenera"**. Per il **gameplay** è tollerabile (ottieni una stanza giocabile); ma va detto con gli occhi aperti — **un miss su una stanza *già vista* è una rottura di coerenza** (i "Tubi Singhiozzanti" diventano altro), **accettata nell'MVP** (un piano, run breve, backtrack limitato). Non è un costo di performance: è un costo di coerenza, esplicito.

> Il replay deterministico **si consuma solo a fine run, e nell'MVP nemmeno quello** (è post-MVP). Quindi nell'MVP **non si scrivono marcatori di fallback** e il salvataggio **non porta alcun obbligo di replay**: la cache è pura convenienza. Il *formato* resta replay-capace (F-13), ma il ramo-completezza non è esercitato. Forma ora, completezza dopo.

> **Conseguenza cross-documento (da annotare in F e G con lo stesso rigore di G §6.4).** Questo rinvio **sospende parte di F-13 e di G-21 nell'MVP**, e va dichiarato lì, non solo qui:
> - **F-13** ha due metà. La metà "il fallback **non consuma il seed stream**" (archetipo designato, non pescato — F §6.3) **vale già nell'MVP** (è forma del fallback). La metà "il seam di replay è **completo** — un turno in fallback è **registrato** come tale" è **solo-formato nell'MVP**: il record *può* portare un marcatore, ma non viene popolato finché il replay non è acceso (post-MVP).
> - **G-21** ("il replay rigioca dalla cache + seed, senza ri-chiamare l'LLM") è **comportamentale e post-MVP**: su un build MVP, un turno andato in fallback senza marcatore darebbe cache-miss → ri-chiamata → divergenza. Va quindi marcato come **non verificabile nell'MVP** (replay fuori scope), non eseguito sul build MVP come se fosse vivo.
>
> Senza questa annotazione, un tester che esegue G-21/F-13 sul build MVP li vedrebbe fallire, e uno dei tre documenti (F, G, H) resterebbe in conflitto. L'istruzione precisa è nella nota d'indice in coda.

> **Il seed stream resta intatto comunque.** Anche con miss e rigenerazione il determinismo del **motore** non si tocca: il fallback è *designato* non pescato (F §6.3), e gli esiti meccanici sono seeded a prescindere dalla prosa. Una cache lasca cambia al più la *prosa* di una stanza rivisitata, mai un tiro.

### 8.4 Tre cerchi (promozione), non tre meccanismi diversi *per ora*

L'Archivio è progettato come **store promovibile** a scope crescente; la *forma del record* non cambia tra i cerchi, cambia **chi lo vede** e **chi decide di promuoverlo**:

- **In-run** (MVP): la cache di *questa* run.
- **Cross-run, per-giocatore**: la **wiki** / memoria generativa (post-I).
- **Cross-giocatore**: il **dono NieR** (post-MVP, §12).

> **Avvertenza di scope (correzione importante).** Non si assuma che la wiki sia "il Cabaret a scope più ampio" sul piano del **meccanismo**. La cache delle stanze è **frozen-by-key** (riproduzione esatta). Ma i sistemi LLM-DM reali realizzano la memoria narrativa con un **vector database** a recupero semantico (NPC, fatti, relazioni, con ranking per similarità/recency) ⟨persistentdm, dnd-ai⟩ — un meccanismo **diverso**, per un lavoro diverso: il *richiamo rilevante* ("l'NPC ricorda che l'ho risparmiato"), non la *riproduzione esatta*. Il flavour **trasversale** (un soprannome riusato ovunque, un NPC ricorrente) è territorio di **recupero**, che il frozen-by-key **non** dà. Cabaret (replay) e wiki (recupero) sono **fratelli, non lo stesso primitivo promosso**. Nell'MVP non cambia nulla (costruiamo solo la cache frozen-by-key); ma H **non deve incardinare** "wiki = Cabaret scalato" come assunto.

---

## 9. Contratto di load

> Il **load valida e degrada con grazia.** Deserializzare un save **non** è fidarsi del file: ogni valore letto va controllato per coerenza, e un file corrotto, troncato o di versione incompatibile **non deve caricare spazzatura nel World né far crashare** il programma.

Discende dalla saggezza roguelike sui savefile: in caricamento **il codice deve controllare ogni valore per sanità e reagire se ne legge uno impossibile** ⟨roguebasin-save⟩. Sotto permadeath + save unico è critico (il terrore del "save corrotto" dopo decine d'ore ⟨mewgenics⟩).

### 9.1 Strati del load

1. **Conformità di formato/schema.** Il JSON parsa e i campi sono dei tipi attesi (validazione Pydantic, come per il contratto F — riuso della stessa disciplina).
2. **Coerenza interna.** I valori sono nel dominio del possibile (HP non negativi, `FaseCorrente` un valore legale, profondità ≥ 1, ogni tag di tipo ha un binding nel registry §4.2). Un valore impossibile → load rifiutato, non applicato.
3. **Versione.** Se `schema_version` < corrente, **migrazione** (§9.2). Se > corrente (save da una versione futura), rifiuto pulito con messaggio.

### 9.2 Migrazione di versione

> Le migrazioni sono **funzioni incrementali** `v→v+1` applicate in catena fino alla versione corrente, sul documento deserializzato. È il pattern della serializzazione ECS con versioning: controllare la versione e **convertire iterativamente fino alla corrente** prima di popolare ⟨godot-ecs⟩. Nell'MVP `schema_version = 1` e nessuna migrazione esiste ancora — ma il **campo è presente da subito** (longevità: le migrazioni diventano gratis sul lungo termine, e nomi di campo espliciti le rendono trattabili, cosa che un binario posizionale non darebbe).

### 9.3 Fallimento del load

> Un load fallito (qualsiasi strato) **non muta `current_world`** e **non distrugge il save**: si rimane nel guscio, si segnala l'errore. Nessun caricamento parziale viene applicato.

### 9.4 Invalidazione a fine-run (morte e vittoria)

> A **fine-run** lo stato del crawler è **invalidato**: vale per la **morte** (`MortePersonaggio`, 6a) *e* per la **vittoria / piano-completato** (6b) — entrambe concludono la run, che non è più ripristinabile come partita in corso (suspend-on-load: non c'è "continua dopo la fine"). Nell'MVP: il file di stato è **rimosso**.
>
> **La sorte dell'Archivio differisce per terminale.** Alla **morte** l'Archivio non ha futuro: può essere rimosso insieme allo stato (nessun orfano). Alla **vittoria** l'Archivio è il **candidato al dono** (§12): post-MVP viene promosso; nell'MVP, in assenza dell'UI di dono, può essere rimosso. È pronto il **formato** a sopravvivere (autosufficiente, col master seed nei metadati, §8.1) — **non** il *contenuto* delle run MVP, che è lasco e non replay-completo (§8.3, e l'onestà di scope in §12). *(La micro-scelta "rimuovi vs tombstone inerte" è la stessa per morte e vittoria, e resta una manopola minore; l'MVP rimuove.)*
>
> Il *backup di sola recovery* (§10.3) non è un aggiramento della permadeath: serve la corruzione, non il ripristino volontario.

---

## 10. Atomicità e non-entanglement

### 10.1 Scrittura atomica

> Ogni file (stato, sidecar) si scrive con **temp + rename**: scrivi su un file temporaneo, `fsync`, poi `rename` atomico sul nome finale. Il rename atomico del filesystem ridà la proprietà **tutto-o-niente** *all'interno* di ciascun file. Sotto permadeath il file di stato non dev'essere **mai** mezzo-scritto.

### 10.2 Ordine di durabilità (i due file restano d'accordo)

> Stato e sidecar sono due file che devono restare coerenti, e l'accordo lo costruisce H, non il filesystem. Regola: il **sidecar è reso durevole *prima*** che lo stato vi faccia riferimento. Se vedi un riferimento nello stato, la voce di Archivio **c'è già**. (Senza, un crash lascerebbe lo stato che punta a una voce non ancora scritta.)

### 10.3 Backup di sola recovery

> Si tiene **un** backup dell'ultimo save buono, **a sola scopo di recovery da corruzione**, **invisibile al giocatore** e **non ripristinabile a comando**. Poiché lo stato referenzia il sidecar (§10.2), il backup è la **coppia coerente stato + sidecar** scattata insieme: ripristinare uno stato vecchio con un sidecar diverso o troncato farebbe penzolare il riferimento. Protegge dal disastro del file unico (un bug del *writer*, non solo un crash, può distruggere l'unico save) senza riaprire il save-scum. È la pratica dei roguelike che prendono sul serio il permadeath, distinta dal ripristino volontario.

### 10.4 Permadeath è in-gioco, non anti-utente (non-goal)

> La permadeath si applica **in-gioco** (suspend-on-load, invalidazione alla morte), **non** contro chi copia la cartella dei save: un utente determinato può sempre fare backup manuali del filesystem per "ripristinare" un crawler ⟨unrealworld⟩, e non lo si previene a livello FS. Coerente con la filosofia del progetto (è il *tuo* save, la tua eredità — §12): H non costruisce DRM contro il giocatore.

### 10.5 Non-entanglement (la membrana della persistenza)

> **La persistenza è il terzo lato della membrana a tenuta** (oltre a "il motore non importa Textual" e "l'adattatore non importa il World"). Tre divisioni che la scrittura su disco **non** deve perforare:
> - **persistenza ↔ sistemi:** H tocca i **dati**, non conosce i sistemi né la logica di dominio (non importa i Processor, non la logica di fase, non il provider).
> - **stato ↔ Archivio:** due file, due cicli vita, **nessuna contaminazione** (niente prosa dell'Archivio nei componenti del World, niente componenti del World nei record dell'Archivio).
> - **dati ↔ formato:** la traduzione vive in H (§4.3), non nei componenti.

---

## 11. Coerenza narrativa senza persistenza della chat

> **La cronologia della chat non si salva: è derivata.** La prosa non *è* lo stato — è il **vestito** dello stato ("risolvi prima, narra dopo", FNC). La conversazione che il giocatore ha letto ha **due genitori**, entrambi già persistiti: lo **stato** (i fatti: HP, posizione, `FaseCorrente`, profondità, status) e l'**Archivio** (la prosa già validata delle stanze viste). Salvare la chat sarebbe salvare uno screenshot invece dei dati.

> Al reload, l'LLM **riprende coerente** non perché ha riletto la conversazione, ma perché il motore gli **ri-inietta i fatti correnti** (proiezione DTO di sola lettura, G §6.6) come ha sempre fatto: per il modello non c'è differenza fra "turno 21 di ieri" e "turno 21 dopo un reload". Il flavour locale già visto è coerente perché **riletto dall'Archivio**, non ri-immaginato.

Questo è il modello che ogni progetto LLM-DM serio adotta per battere la statelessness ⟨jenova, alibaba-dm⟩. La sola coerenza che questo modello **non** copre automaticamente è il **flavour trasversale** (NPC ricorrenti, fili narrativi cross-stanza): non è un buco di H, è territorio della **wiki a recupero** (§8.4, §12), post-I.

---

## 12. Stato di guscio persistente — categoria nominata, non implementata

> Esiste una **categoria nuova di persistenza**: **stato di guscio persistente** — app-level, fuori da ogni run-World, sopravvive a tutti i crawler. È distinta dal run-save (che è il World, per-crawler, in-run) e oggi non ha inquilini. **H la nomina, non la implementa.** È "opzione presa, non esercitata" (spezza l'atomo).

> **Nell'MVP è un sentiero vuoto**, di proposito: la scelta **uuid** (§5) evita di darle un inquilino (un contatore l'avrebbe riempita). I suoi inquilini futuri:
> - la **wiki** / memoria generativa (cross-run, per-giocatore) — meccanismo di **recupero** semantico ⟨persistentdm, dnd-ai⟩, distinto dal Cabaret frozen-by-key (§8.4);
> - il **dono NieR** (cross-giocatore): alla **vittoria** (§6.7 di G, raggiungere la `DiscesaPiano`), post-MVP, il giocatore potrà sacrificare la propria run — invalidare lo **stato** *e* **promuovere l'Archivio** nello store condiviso, perché un altro crawler la rigiochi **senza spendere token**.

> **Cosa H impegna *oggi* perché il dono sia possibile domani senza riscritture** (sola forma, nessun meccanismo):
> 1. l'Archivio (sidecar) è **autosufficiente e promovibile** — replayabile **senza** il blob di stato del crawler che l'ha prodotto (§8.1);
> 2. il **master seed della run** (§4.1) è **dato di prima classe** ed è **duplicato nei metadati dell'Archivio** (§8.1), non solo nel blob di stato: poiché alla fine-run lo stato è invalidato (§7), il seed deve **viaggiare con l'Archivio** o il dono non rigioca la run (narrerebbe stanze sciolte). È il master seed, *non* il prompt-seeded di lookup (§8);
> 3. il **model id** è nei metadati (§4.1): un dono con cache-miss rigenererebbe col modello del *ricevente* — magari un'altra versione — quindi il dono pretende cache **completa** (rigore di replay), e registrare il modello permette di rilevare il drift ⟨jenova⟩;
> 4. la **vittoria** è annotata come **futuro punto-di-dono**.

> **Il doppio gate proteggerà il dono** (post-I): si ricicla **solo selezione + narrazione, mai stat** — chi riceve **ri-valida** il record contro il *proprio* catalogo/budget e il motore **ricalcola i numeri** (la membrana F applicata alla persistenza condivisa). Un dono non può importare "uno slime da 999999 danni": importa "uno slime fatto così", e il motore del ricevente decide cosa significa.

> **Onestà di scope: gli Archivi nati nell'MVP non sono donabili così come sono.** Il sentiero del dono è lasciato aperto a **livello di formato** (record autosufficienti, master seed nei metadati, model id, vittoria annotata), **non** a livello di contenuto. Il dono "pretende cache **completa**" — rigore di replay, marcatori di fallback inclusi — ma l'Archivio prodotto sotto l'MVP è **lasco** e **non popola i marcatori** (§8.3): un suo turno andato in fallback non è registrato, quindi al replay del ricevente darebbe cache-miss → divergenza. Conseguenza da dichiarare, perché nessuno assuma "qualsiasi Archivio salvato sarà donabile più tardi": **diventano donabili solo gli Archivi prodotti *dopo* che la completezza-replay è accesa** (lavoro post-MVP). L'MVP rende l'infrastruttura pronta, non i suoi dati retroattivamente donabili.

> **L'indirezione "procura" (G §9.4) è il call-site narrow** che domani prende un secondo ramo (prima pesca dall'Archivio promosso, poi genera) senza che H lo tocchi.

---

## 13. prompt caching = trasporto, fuori da H

> Il **prompt caching** dell'API (cache del prefisso del prompt per ridurre costo/latenza) è **trasporto**, vive nel **provider** (PLK §3/§4), **fuori da H**. **Non** è il Cabaret: non cambia l'output, non lo rende deterministico, non persiste nulla fra sessioni — è solo uno sconto su una chiamata che fai comunque, e **non** contribuisce alla coerenza (quella è Archivio + motore, §8/§11). Come il meccanismo di output strutturato (PLK §5, F-12), i suoi dettagli (eleggibilità, durata, prezzo) **si verificano sui doc API correnti all'implementazione, non a memoria**, confinati nel backend. L'unica accortezza di *design* (non di H) è impaginare il prompt col **prefisso statico davanti** (F §7) per offrire un prefisso lungo e stabile da cachare.

---

## 14. Cosa H non copre / rimanda a J

> Il **contatore di tempo-piano** si **serializza in H** (è stato del World, §4.1), ma la sua **semantica** è di **J** (modello del tempo). H lascia uno **slot di serializzazione forward-compatible** senza presupporre J: un campo intero nel blob di stato, che J riempirà di significato (cadenza, fast-forward, crollo del piano post-1.0). H non dipende da J; J si appoggia a questo slot.

Restano a valle, non a H: la cadenza temporale (J), i path esatti su disco (implementazione, cross-platform), le soglie di compressione e i parametri di retry sul load (implementazione).

---

## 15. Criteri di accettazione (verificabili)

Tag: **statico/grep** (ispezione di codice/save) o **comportamentale** (test).

- **H-1** *(grep)* — Lo stato si serializza in **JSON-family**; **nessun** uso di `pickle`/`marshal` sul percorso di save/load (statico). *(§3)*
- **H-2** *(statico)* — `EntitaGenerata`/i componenti **non** contengono `to_dict`/`from_dict`: la traduzione vive nel serializzatore di H. *(§4.3)*
- **H-3** *(statico)* — Ogni componente serializzato porta un **tag di tipo** con binding nel registry di H; nessun tag senza binding (statico). *(§4.2)*
- **H-4** *(grep)* — **Nessun `id` di entità esper** è serializzato come riferimento durevole; le chiavi/referenze usano l'**uuid** di dominio o valori copiati. *(§4.4, G §4.3/G-3)*
- **H-5** *(statico)* — L'identità del crawler è un **uuid**, in **un componente** *e* nel **metadato del save**; **nessun** contatore app-level di id. *(§5)*
- **H-6** *(comportamentale)* — Il save scatta **solo** a evento/comando (uscita, menu, morte, a mano), **mai** su timer/tick. *(§6)*
- **H-7** *(comportamentale)* — La scrittura del save avviene **prima** dello `switch_world`, **mai** dentro un `process()`/dispatch; a **fine-run** (morte 6a **e** vittoria/piano-completato 6b) si **invalida** (non si salva). *(§7, §9.4, ESP §0.1, ACV §5.3)*
- **H-8** *(statico)* — Stato e Archivio sono **file separati**; lo stato contiene un **riferimento** al sidecar, non il suo contenuto. *(§2)*
- **H-9** *(comportamentale)* — Il sidecar dell'Archivio è **compresso**; il file di stato è **in chiaro**. *(§3, §8)*
- **H-10** *(comportamentale)* — Una stanza già in Archivio è **riletta**, non rigenerata; un **cache-miss** degrada a "rigenera" senza crash (lasco). *(§8.2, §8.3)*
- **H-11** *(statico)* — I record d'Archivio contengono **solo selezione + narrazione**, **nessuna statistica**; sono autosufficienti (replayabili senza il blob di stato). *(§8.1)*
- **H-12** *(comportamentale)* — Un load di un file **corrotto/troncato/di versione incompatibile** **non** muta `current_world`, **non** crasha, e **non** applica stato parziale. *(§9)*
- **H-13** *(statico)* — Il blob di stato porta `schema_version` (presente già a v1) e un **model id**; la migrazione è una catena di funzioni `v→v+1`. *(§4.1, §9.2)*
- **H-14** *(comportamentale)* — Le scritture sono **temp + rename**; il **sidecar** è reso durevole **prima** che lo stato vi faccia riferimento (ordine di durabilità). *(§10.1, §10.2)*
- **H-15** *(statico)* — Esiste **un** backup di **sola recovery** dell'ultimo save buono, **non** ripristinabile a comando dal giocatore. *(§10.3)*
- **H-16** *(grep)* — Il livello di persistenza **non importa** sistemi/Processor/provider/Textual: tocca dati e World, nulla più. *(§10.5)*
- **H-17** *(statico)* — **Nessun** "log di conversazione/chat" è serializzato: la chat è derivata da stato + Archivio. *(§11)*
- **H-18** *(statico)* — Il **contatore di tempo-piano** è serializzato come campo dello stato, **senza** logica temporale in H (slot per J). *(§14)*
- **H-19** *(grep)* — Il **prompt caching** non compare in H: vive nel provider. *(§13)*
- **H-20** *(comportamentale)* — **Ogni** terminale run→guscio ha un'azione di persistenza definita: uscita/menu/6c **salvano**, morte 6a **e** vittoria 6b **invalidano**; nessun esito terminale (in particolare la **vittoria/piano-completato**) resta senza azione. *(§7, §9.4, ACV §5.1/6b)*
- **H-21** *(statico)* — Il **master seed della run** è serializzato nel blob di stato **e** duplicato nei metadati dell'Archivio (sopravvive all'invalidazione di fine-run per il dono); è **distinto** dal *prompt seeded* di lookup dell'Archivio. *(§4.1, §8.1, §12)*
- **H-22** *(comportamentale)* — Lo **scan** dell'elenco crawler legge **solo** l'intestazione di metadati di ogni save (no deep-parse); un save con intestazione illeggibile compare come voce **«corrotta»**, senza far crashare il menu. *(§5, §9)*

> **Liveness di persistenza (gate di release, nodo A):** **H-L1** — una run **salvata** si **ricarica** in uno stato giocabile identico (round-trip fedele dello stato meccanico); **H-L2** — un crash durante una scrittura **non** lascia un save inservibile (atomicità + backup di recovery). Senza queste due, "giocabile capo-a-fine con salvataggio" (nodo A) non regge.

---

## 16. Invarianti rafforzati da questo documento

- **La persistenza tocca i dati, mai conosce i sistemi.** Terzo lato della membrana a tenuta; la serializzazione non perfora le divisioni del progetto. *(§10.5)*
- **Lo stato è il World effimero; il contenuto validato è patrimonio.** Due artefatti, due nature, due cicli vita — separati per file. *(§2)*
- **Nessun id di entità esper è un riferimento durevole.** Estende G §4.3/G-3 alla persistenza. *(§4.4)*
- **Il formato è leggibile per disciplina, non per comodità.** JSON-family + nomi di campo + `schema_version` = riparabilità sotto permadeath e migrazioni nel tempo; il binario compatto è una via di fuga, non il default. *(§3, §9.2)*
- **La coerenza non vive nella chat: vive nel motore (fatti) e nell'Archivio (flavour congelato).** Il determinismo dell'Archivio è memoization, **non** riproducibilità del modello. *(§8.2, §11)*
- **La cache lasca è un trade-off di coerenza esplicito, non un dettaglio operativo.** Miss su stanza già vista = rottura accettata nell'MVP. *(§8.3)*
- **Il load valida e degrada; non si fida del file.** *(§9)*
- **Permadeath è in-gioco, non DRM.** Suspend-on-load + invalidazione; non si combatte la copia del filesystem. *(§10.4)*
- **L'Archivio è uno store promovibile a tre cerchi; la forma del record è una, gli atti di promozione (wiki, dono) sono post-I.** Wiki ≠ Cabaret sul meccanismo (recupero vs frozen-by-key). *(§8.4, §12)*
- **prompt caching è trasporto, fuori da H.** *(§13)*

---

## 17. Cosa NON facciamo (anti-over-engineering)

- ❌ **Pickle** (o qualsiasi serializzazione che accoppi il save alla forma delle classi): si rompe ai refactor, opaco, insicuro. *(§3)*
- ❌ **Cache dentro il blob di stato** (G §6.4 originale): è sidecar, ri-categorizzata come Archivio. *(§2, §8)*
- ❌ **`to_dict`/`from_dict` nei componenti**: la traduzione è di H. *(§4.3)*
- ❌ **Serializzare id di entità esper** come referenze durevoli. *(§4.4)*
- ❌ **Contatore app-level di id crawler**: si usa uuid (tiene vuota la categoria §12). *(§5)*
- ❌ **Save su timer/tick**: a evento/comando, scollegato da J. *(§6)*
- ❌ **`switch_world`/`delete_world` per salvare**, o salvare dentro un `process()`: si salva in-run prima del teardown. *(§7)*
- ❌ **Comprimere lo stato** (perderebbe la leggibilità che serve sotto permadeath): si comprime **solo** il sidecar. *(§3)*
- ❌ **Trattare la cache MVP come replay-completa**: è lasca, niente marcatori di fallback nell'MVP. *(§8.3)*
- ❌ **Fidarsi del file in load**: si valida e si degrada. *(§9)*
- ❌ **Persistere la cronologia di chat**: è derivata. *(§11)*
- ❌ **Lasciare la vittoria/piano-completato senza azione di persistenza** (asimmetria col terminale di perdita): a fine-run si **invalida**, vittoria come morte; il dono è post-MVP. *(§7, §9.4)*
- ❌ **Confondere il master seed con il prompt-seeded**, o tenere il seed **solo** nello stato (al dono sarebbe già perso): il master seed vive nello stato **e** nei metadati dell'Archivio. *(§4.1, §8.1, §12)*
- ❌ **Costruire wiki / dono NieR / replay** nell'MVP: si lascia il **sentiero** (Archivio promovibile, seed first-class, model id, vittoria annotata), non il meccanismo. *(§12)*
- ❌ **Assumere che un Archivio nato nell'MVP sarà donabile** più tardi: è **lasco / non replay-completo** (niente marcatori, §8.3). Donabili solo gli Archivi prodotti **dopo** che la completezza-replay è accesa (post-MVP). *(§8.3, §12)*
- ❌ **Duplicare la posizione-RNG nei metadati dell'Archivio**: solo il **master seed** vi si duplica (il dono rigioca da turno 0); la posizione-RNG resta nel solo blob di stato (resume mid-run). *(§4.1, §8.1)*
- ❌ **Assumere "wiki = Cabaret scalato"**: sono meccanismi diversi (recupero vs frozen-by-key). *(§8.4)*
- ❌ **Cablare il prompt caching in H**: è trasporto del provider. *(§13)*
- ❌ **DRM anti-copia** contro il giocatore: la permadeath è in-gioco. *(§10.4)*

---

## Fonti esterne consultate

Materiale online usato nelle sezioni §3, §4, §5, §8, §9, §10, §11, §12 (consultato a maggio 2026). Sono pratiche e resoconti di terzi, citati a supporto di decisioni che restano del progetto.

- ⟨roguebasin-save⟩ *Save Files* — RogueBasin. https://www.roguebasin.com/index.php/Save_Files (sanity-checking di ogni valore in load).
- ⟨tvtropes-roguelike⟩ *Roguelike* (Suspend Save) — TV Tropes. https://tvtropes.org/pmwiki/pmwiki.php/Main/Roguelike (un solo save, ricaricabile solo per riprendere → anti-save-scum).
- ⟨unrealworld⟩ Thread "Death / saves" — UnReal World, Steam Community. https://steamcommunity.com/app/351700/discussions/2/392183857621340376 (backup manuale della cartella aggira la permadeath a livello FS).
- ⟨mewgenics⟩ *Where to Find Mewgenics Save File* — XMODhub. https://www.xmodhub.com/info/blog/mewgenics-save-file-location/ (corruzione del save come timore primario sotto permadeath).
- ⟨godot-ecs⟩ *Serialization and Persistence* — godothub/godot-ecs, DeepWiki. https://deepwiki.com/godothub/godot-ecs/9-serialization-and-persistence (load a tre fasi per risolvere referenze; versioning con conversione iterativa; type registry/factory).
- ⟨marcin⟩ *Entity Component System: Entity* — Marcin's Musings. https://www.mikemarcin.com/upcoming/ecs_entity/ (riciclo degli id di entità e rottura delle referenze).
- ⟨pydocs-pickle⟩ *pickle — Python object serialization* — docs.python.org. https://docs.python.org/3/library/pickle.html (fragilità: classe importabile/stesso modulo; non portabile; insicuro su dati non fidati; JSON non crea di per sé esecuzione di codice).
- ⟨peerdh⟩ *Implementing Efficient Serialization Formats For Game Save Data* — peerdh.com. https://peerdh.com/blogs/programming-insights/implementing-efficient-serialization-formats-for-game-save-data (JSON: leggibile/debuggabile ma file più grandi e parse più lento).
- ⟨GearBlocks⟩ *Saved game serialization* — GearBlocks devblog. https://www.gearblocksgame.com/2019/10/07/saved-game-serialization/ (bloat e lentezza di JSON a scala; passaggio a BSON + compressione Deflate).
- ⟨thatonegamedev⟩ *JSON vs Binary Serialization* — That One Game Dev. https://thatonegamedev.com/cpp/json-vs-binary-serialization/ (BSON/CBOR come miglioramenti di JSON; flatbuffers/protobuf più ottimali ma più onerosi).
- ⟨persistentdm⟩ *PersistentDM* — tarnvaal/PersistentDM, GitHub. https://github.com/tarnvaal/PersistentDM (memoria persistente di un DM via vector database; reply world-aware; recupero per similarità/recency).
- ⟨dnd-ai⟩ *dnd-ai* — chungs10/dnd-ai, GitHub. https://github.com/chungs10/dnd-ai (ChromaDB per memoria semantica + grafo relazioni; meccaniche deterministiche separate).
- ⟨alibaba-dm⟩ *Creating A Custom AI Dungeon Master That Remembers Player Choices Across Sessions* — alibaba.com product-insights. https://www.alibaba.com/product-insights/step-by-step-creating-a-custom-ai-dungeon-master-that-remembers-player-choices-across-sessions.html (separare memoria a lungo termine dall'inferenza; ancorare a id di sessione immutabili).
- ⟨jenova⟩ *AI Dungeon Master Bot* — jenova.ai. https://www.jenova.ai/en/resources/ai-dungeon-master-bot (statelessness architetturale dell'LLM → perdita di coerenza, "dice sì a tutto").

---

### Nota per l'aggiornamento dell'indice

In `progetto-indice-decisioni.md`:

- **Cruscotto dei nodi:** **H** da ⬜ a ✅. Sintesi: *"Persistenza. Formato JSON-family (pickle scartato; MessagePack/CBOR come via di fuga). Due artefatti separati: stato (run-World effimero, in chiaro) e Archivio degli Output Validati (sidecar compresso, patrimonio promovibile — nome di lavoro «Ananas Cabaret»). Blob di stato: entità via `components_for_entity`, singleton (`FaseCorrente` + contatore di profondità), stato d'esplorazione, uuid d'identità, `schema_version`, model id, tag di tipo; traduzione di H non dei componenti; nessun id esper durevole. Identità = uuid (tiene vuota la categoria «stato di guscio persistente»); indice crawler = scan cartella. Cadenza a evento/comando (uscita, menu, morte, a mano), scrittura prima dello `switch_world`; **fine-run = invalida** (morte 6a **e** vittoria/piano-completato 6b — il dono resta post-MVP); 6c (uscita volontaria) nell'MVP come save-on-exit. **Master seed della run** serializzato nello stato **e** duplicato nei metadati dell'Archivio (sopravvive all'invalidazione per il dono), distinto dal prompt-seeded di lookup. Cache = sidecar lasco (miss = rigenera, rottura di coerenza accettata nell'MVP), replay-capace in forma ma non esercitato (replay solo a fine run, post-MVP → annotare F-13/G-21). Coerenza nel motore (fatti ri-iniettati) + Archivio (flavour congelato); niente persistenza della chat. Contratto di load: valida e degrada su corruzione/versione, migrazione `v→v+1`; scan dell'elenco via intestazione di metadati. Atomicità temp+rename + ordine di durabilità + backup di sola recovery (coppia coerente stato+sidecar); permadeath in-gioco non anti-copia. Stato di guscio persistente nominato non implementato (sentiero per wiki/dono NieR; wiki ≠ Cabaret sul meccanismo, recupero vs frozen-by-key). prompt caching = trasporto, fuori da H. Criteri H-1…H-22 + gate H-L1/H-L2. Dettaglio in `persistenza-salvataggio.md`."*
- **Documenti del progetto:** aggiungere `persistenza-salvataggio.md` (H) come ✅.
- **Convenzione di rimando:** aggiungere **H** = `persistenza-salvataggio.md`.
- **Annotazione su G §6.4 (da applicare quando si ritocca G):** la cache delle stanze **non** sta dentro il save — è **sidecar**, ri-categorizzata come Archivio (H §2/§8). Stesso pattern delle annotazioni `livello` e `MortePersonaggio`: finché G non è ritoccato, vale H per il layout della cache (decisione **provvisoria** sul confine G/H — H §2).
- **Annotazione su F-13 e G-21 (da applicare con lo stesso rigore):** il **replay è post-MVP** (H §8.3). Conseguenza: **F-13** — la metà "fallback non consuma il seed stream" vale già nell'MVP, ma "il seam di replay è completo / il fallback è registrato come marcatore" è **solo-formato nell'MVP** (il marcatore non viene popolato finché il replay non è acceso). **G-21** ("il replay rigioca dalla cache + seed, senza ri-chiamare l'LLM") è **comportamentale e non verificabile nell'MVP** (replay fuori scope): da non eseguire sul build MVP come criterio vivo. Senza questa annotazione, F/G/H restano in conflitto sul punto.
- **Buchi di H risolti:** formato (JSON), slot save (crawler/uuid), destinazione sconfitta (invalida), **destinazione vittoria/piano-completato (invalida a fine-run, dono post-MVP)**, uscita volontaria 6c (sì, MVP), layout cache (sidecar), caching (Archivio frozen-by-key; prompt caching = trasporto), **casa del master seed (stato + metadati Archivio)**.
- **Nodi aperti → H:** spostare in "Nodi chiusi"; aggiungere il paragrafo di razionale.
- **Ordine di lavoro consigliato:** barrare il punto 6 ("H"). Prossimo: **J** (modello del tempo) — accoppiato a H tramite lo slot del contatore di tempo-piano (§14); poi **I** per ultimo.
- **Nodi post-I annotati (da H):** dono NieR (cross-giocatore, sullo stesso sentiero della wiki) — **ma solo gli Archivi prodotti dopo la completezza-replay sono donabili; quelli nati nell'MVP sono laschi**, sentiero aperto a livello di formato non di contenuto (H §8.3/§12); wiki come store a **recupero** distinto dal Cabaret frozen-by-key.
