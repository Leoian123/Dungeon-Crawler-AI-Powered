# Contratto AI↔motore — Nodo **F** (schema, gate di validazione, mappatura sull'interfaccia `genera`)

> **Spec normativa per Claude Code.** Chiude il nodo **F**: lo **schema concreto** del dialogo AI↔motore, il **gate** che ne garantisce la conformità (e dove vive), e la **mappatura** di ogni chiamata all'AI sull'unica interfaccia `genera`. Non sceglie un provider (è D), non descrive il meccanismo nativo di output strutturato (è del backend, PLK §5): fissa il *contratto* che il motore e il provider onorano.
>
> **Presuppone e non duplica** `esper-implementazione.md` (ESP), `fasi-narrazione-combattimento.md` (FNC), `interfaccia-contratto.md` (IC), `provider-llm-key.md` (PLK). In caso di conflitto, valgono quei documenti per ciò che è di loro competenza; questo fissa solo lo schema, il gate e la mappatura. **F è indipendente da E** (ACV): è il contratto *in-run*, non tocca il ciclo vita cross-World.
>
> **Convenzione di rimando.** `§N` *senza prefisso* = sezione di questo documento. Rimandi prefissati: **ESP §N**, **FNC §N**, **IC §N**, **PLK §N**.
>
> **Principio guida di questo documento:** *lo schema è il contratto, il gate è l'autorità, il provider è solo trasporto.* L'AI sceglie **nomi** da un vocabolario chiuso; il motore **lega** quei nomi a componenti (registry), **calcola** i numeri (formula) e **valida** la scelta (gate). In una riga: **il contratto porta i nomi, il motore possiede il significato.**
>
> **Ritocco post-chiusura (da J, cambiali C1/C3 — vedi `saldo-cambiali-J.md`).** Lo schema acquista il campo categoriale `durata: Durata` su `TurnoNarrazione` (non su `Flavor`), e il gate clampa a `TURNO` la battuta che emette `EncounterStarted`. È una *estensione additiva*, coerente con "nomi non numeri": non cambia il gate a tre strati né la mappatura su `genera`. Punti toccati: §2, §4 (innesto gate→tick), F-1, F-14, §9.

---

## 0. Premesse ereditate (non rinegoziabili qui)

- **L'AI propone, il motore dispone.** L'AI è sorgente di varietà del *contenuto*; il motore arbitra ogni *esito*. *(FNC §1)*
- **Una sola chiamata LLM strutturata per turno di narrazione** → `{ prosa, entità:{archetipo, rarità, blocchi}, opzioni }`. Mai spezzata in più chiamate. **Il `livello` non è fra i campi emessi:** è profondità del piano, posseduta dal motore (G §8.1/§8.2), legata all'entità dopo il gate. *(FNC §5.1, §5.3; override G §8.2)*
- **L'AI non emette statistiche numeriche grezze:** seleziona da un **catalogo chiuso** dentro un **budget** imposto dal motore; le statistiche le **deriva il motore** da `(archetipo, rarità, livello)`. *(FNC §5.5)*
- **Il gate di validazione (schema + appartenenza al catalogo + budget) sta nel motore**, mai nella membrana né nel bus. *(FNC §5.1, IC §4)*
- **I tipi dello schema vivono nel modulo `contracts`**, dependency-free dai layer del progetto (sono DTO, non oggetti vivi). *(IC §2, IC §3, PLK §0)*
- **Interfaccia provider unica:** `genera(prompt, schema) → candidato | None`. Il `prompt` è costruito dal motore (dominio) ed è **opaco** al provider; lo `schema` pilota l'output strutturato; il ritorno è un **candidato conforme allo schema oppure `None`**. *(PLK §2)*
- **Il provider possiede il trasporto, non il dominio:** chiamata API, meccanismo nativo di output strutturato, timeout/retry, pin del modello, lettura della key. **Non** costruisce il prompt, **non** valida catalogo/budget, **non** sceglie il fallback. *(PLK §3, §4)*
- **Fallimento LLM gestito esplicitamente:** timeout → retry limitato → fallback deterministico, distinto per tipo di output; refusal trattato come generazione fallita senza retry; troncatura ≠ JSON malformato. *(FNC §10, PLK §6)*
- **L'unica sorgente di nondeterminismo è l'LLM, ed è bordata** dal gate; replay riproducibile = **seed + cache degli output validati**. *(FNC §9)*

Se una di queste non è chiara, fermarsi e rileggere i quattro documenti a monte prima di implementare quanto segue.

---

## 1. Decisione F (sintesi)

| Aspetto | Decisione | Dove vive | Razionale |
|---|---|---|---|
| Linguaggio dello schema | **Pydantic** | `contracts` | Doppio uso: i modelli *generano* lo schema da dare al meccanismo nativo del backend **e** *validano* il candidato nel gate. Un'unica fonte di verità per la forma. |
| Forma del catalogo | **enum chiusi (contratto) + registry/formula (motore)** | enum in `contracts`; registry e formula nel motore | Il contratto porta i *nomi*; il binding nome→componente ECS e la formula `(archetipo,rarità,livello)→stat` importano esper → restano nel motore. |
| Chiamate all'AI | **una sola funzione** `genera(prompt, schema)` | provider (PLK) | La differenza fra "genera entità" e "vesti di prosa" non è nella funzione: è nello *schema* e in *cosa fa il motore col risultato*. |
| Costruzione del prompt | **del motore**, opaco al provider | motore | Già fissato da PLK §2/§3 (dominio). F ne fissa solo l'*anatomia*, non il testo. |
| Gate di validazione | **tre strati nel motore**: schema · catalogo · budget | motore | IC §4 / FNC §5.1. Sotto grammatica, schema e catalogo sono garantiti per costruzione; **il budget no** → il gate è obbligatorio. |
| Fallimento | **due owner, un fallback** | trasporto: provider · dominio: motore | `None` (trasporto) e rifiuto-di-gate (dominio) collassano sullo **stesso** fallback atomico, locale e deterministico. |

I **contenuti** degli enum (quali archetipi, quali rarità, quali blocchi), la **formula** e le **tabelle di budget/anomalie** **non** sono di F: sono buchi dichiarati di **G** (§9). F fissa la *forma* (che ci sono enum chiusi, un registry, un gate), non le *voci*.

---

## 2. Lo schema della chiamata di narrazione

I modelli vivono in `contracts`. Sono **dati**, non comportamento: nessuna logica di dominio, nessun import di esper/Textual/provider.

```python
# modulo `contracts` — schema/DTO, dependency-free dai layer del progetto.
# (solo stdlib + Pydantic, vedi §3.1). I VALORI degli enum sono SEGNAPOSTO: i
# contenuti del catalogo sono di G (§9).

from enum import Enum
from pydantic import BaseModel

class Archetipo(str, Enum):        # vocabolario chiuso — contenuti in G
    SLIME = "slime"
    SCHELETRO = "scheletro"
    # ...

class Rarita(str, Enum):
    COMUNE = "comune"
    # ...

class Blocco(str, Enum):           # le "interfacce" di FNC §5.5: contratti noti
    VELENO = "veleno"
    RIGENERAZIONE = "rigenerazione"
    STORDITO = "stordito"
    # ...

class TipoAzione(str, Enum):       # spazio d'azione chiuso → mappa su intento noto (IC §2.3)
    COMBATTI = "combatti"
    SCAPPA = "scappa"
    ALTRO = "altro"

class Durata(str, Enum):           # vocabolario del tempo (J §3.1) — ordine totale; carico-tick nel catalogo (motore)
    TURNO = "turno"                # minimo = cadenza base; in esplorazione = una stanza (J §4)
    UN_ATTIMO = "un_attimo"
    UN_POCHINO = "un_pochino"
    UN_BEL_PO = "un_bel_po"
    # ... estendibile (composizione aperta). I VALORI (Durata→carico-tick, etichette diegetiche) sono di G/Gruppo 2.

class EntitaGenerata(BaseModel):
    archetipo: Archetipo
    rarita: Rarita
    # NIENTE `livello`: è profondità del piano, dato di stato del motore,
    # legato all'entità dopo il gate (§4.2; G §8.1/§8.2). L'AI non lo emette.
    blocchi: list[Blocco]
    nome: str                      # libero (flavor)
    descrizione: str               # libero (flavor)
    # NESSUN campo di statistica numerica: niente hp, danno, difesa, durate…

class Opzione(BaseModel):
    tipo: TipoAzione               # categoriale, chiuso
    etichetta: str                 # flavor, libero

class TurnoNarrazione(BaseModel):  # il "candidato" di PLK §2 per la narrazione
    prosa: str
    entita: EntitaGenerata
    opzioni: list[Opzione]
    durata: Durata                 # quanto tempo simulato costa la battuta (J §3.4); il motore la mappa a carico-tick via gate

class Flavor(BaseModel):           # schema banale per la chiamata di sola prosa (§5) — NESSUN `durata`
    testo: str
```

Tre proprietà strutturali, tutte verificabili staticamente:

- **Zero campi numerici in `EntitaGenerata`.** Non c'è `hp`, `danno`, `difesa`, né alcun `int`. I numeri li deriva il motore (FNC §5.5); il `livello` (profondità del piano) **non è emesso dall'AI** — è dato di stato del motore, legato all'entità dopo il gate (§4.2; G §8.1/§8.2).
- **Tutto ciò che ha conseguenza meccanica è un enum chiuso** (`Archetipo`, `Rarità`, `Blocco`, `TipoAzione`). Solo `nome`, `descrizione`, `etichetta`, `prosa` sono testo libero — la parte davvero creativa (FNC §5.4, §5.5).
- **Nessun campo per invocare l'anomalia o chiedere più budget.** Lo schema non offre all'AI alcun modo per segnalare "questo è uno scontro fuori scala" o per alzarsi il tetto. L'anomalia entra **solo** come budget gonfiato dal motore nel prompt (§4.3, FNC §5.5): *l'AI la narra, non la invoca*.

> **Un solo campo `prosa`, due momenti narrativi.** FNC §5.3 descrive l'AI in tre ruoli nello stesso turno — *masterizza* (prosa d'ingresso nella stanza) e *riprende* (prosa che presenta l'incontro) sono i due momenti narrativi, *genera* è il terzo (l'entità). I due momenti narrativi **rendono entrambi nel singolo campo `prosa`**: lo schema segue FNC §5.1 (`{prosa, entità, opzioni}`), la fonte più precisa sulla *forma*. Non esiste un secondo campo di prosa, e un agente non deve aspettarselo.

> **Le `opzioni`.** Nell'MVP convergono sul menu noto (`Combatti` / `Scappi` / `Altro`): l'AI ne autora l'`etichetta` (flavor), non lo *spazio d'azione* (il `tipo`, chiuso). Se il menu sia sempre il terzetto fisso o un suo sottoinsieme scelto dall'AI è una manopola di gameplay → **G**. F fissa che il `tipo` è **categoriale, mai testo grezzo**, e che ogni `tipo` corrisponde a un'azione nota del motore; l'**intento** vero e proprio nasce a valle, dalla *scelta del giocatore* (`PlayerChoseOption(N)`, IC §2.3), non dal campo in sé — l'AI propone opzioni tipizzate, il giocatore le trasforma in intento scegliendone una.

> **Il campo `durata`** *(ritocco da J, cambiale C1).* È l'unico `int`-equivalente che l'AI emette, ma **non è un numero**: è una **categoria** dall'enum chiuso `Durata`, come `Rarità` o `Blocco`. Esprime quanto **tempo simulato** costa la battuta narrata (la cadenza base = `TURNO` = una stanza in esplorazione; valori più alti comprimono più tick — riposo, attraversamenti). Il motore la mappa a un **carico-tick** via catalogo (mai nel contratto) e la fa passare per il **gate** (`durata → gate → carico-tick`): nell'MVP la riconduzione è identità, ma il punto d'innesto esiste (il clamp serio è per il crollo post-1.0). `Flavor` **non** porta `durata`: in combattimento il costo è fisso `TURNO`, cablato nel loop AP (G §2). *La semantica del tempo è di J (`tempo-modello-scansione.md`); F fissa solo che il campo è una categoria chiusa, gated come gli altri.*

> **Clamp della battuta d'ingresso al combattimento** *(cambiale C3).* Una `TurnoNarrazione` che compone/innesca un incontro (emette `EncounterStarted`) ha **`durata = TURNO`** dopo il gate: l'imboscata è una singola battuta, non comprime tempo. È l'**unico** punto in cui il gate non è identità già nell'MVP. Il *timing* (la composizione avviene in `NARRAZIONE`, al confine di tick, prima del flip) è di **G §5.1**.

---

## 3. Il catalogo: nomi nel contratto, significato nel motore

È FNC §5.5 reso concreto. Il catalogo ha **due facce**, e la linea fra loro è la stessa di IC/PLK (contratto vs implementazione):

- **Faccia-contratto (in `contracts`): il vocabolario.** Gli enum sopra. Sono ciò su cui AI e motore *devono accordarsi*: l'insieme chiuso di nomi legali. Attraversano la membrana, pilotano lo schema, sono validati per appartenenza.
- **Faccia-motore (nel motore): la realizzazione.** Il **registry** che mappa `Blocco → classe componente ECS` (la chimera "veleno+stordito+rigenerazione" è una somma di componenti — FNC §5.5) e la **formula** `(archetipo, rarità, livello) → statistiche`. Importano esper e la matematica del gioco → **non** possono stare in `contracts`.

> Analogia di FNC §5.5 (didattica, non istruzione): le **Interfacce** ≈ il vocabolario di blocchi che soddisfano contratti noti; la realizzazione è una **factory parametrica + registry**. F fissa che esistono *entrambe le facce* e dove vivono; **non** ne riempie le voci.

**Sincronia fra le due facce (invariante).** Ogni membro di enum del catalogo-contratto deve avere una **voce corrispondente** nel registry del motore. Un nome legale nello schema ma senza binding sarebbe un valore che il gate accetta e che il motore non sa istanziare — un buco silenzioso. Verificabile staticamente (F-6).

### 3.1 Pydantic in `contracts` e la disciplina di IC §1.3

IC §1.3 dichiara Textual "l'unica dipendenza **viva**" e `contracts` "dependency-free". Pydantic è una dipendenza in più: la frizione va sciolta, non assunta.

- `contracts` resta libero dai **layer del progetto** (Textual, esper, provider): è quello il senso di "dependency-free" in IC §2. Pydantic non è un layer architetturale: è una **libreria di validazione fondazionale**, allo stesso rango di `dataclasses`/`enum` della stdlib.
- Pydantic è **pinnato e congelato** in lockfile (transitive incluse), trattato come **vendorizzato di fatto**: non lo si insegue. Non è "vivo" nel senso di IC §1.3 — il suo aggiornamento non sta sul percorso critico del progetto come quello di Textual (la superficie UI che si muove). L'affermazione di IC ("una sola dipendenza viva") **regge**: Pydantic è fermo, non vivo.
- È l'**unica** dipendenza di `contracts` oltre la stdlib. Verificabile staticamente (F-2).

Il doppio uso che giustifica la scelta: lo **stesso** modello Pydantic (a) *emette* lo schema (JSON Schema) che il backend dà al proprio meccanismo nativo di output strutturato, e (b) *valida* il candidato in ingresso al gate. Una sola fonte di verità per la forma, ai due capi della membrana.

> **Lo schema emesso deve stare dentro i limiti del meccanismo del backend** (nota d'implementazione, alla PLK §5). I meccanismi a grammatica hanno vincoli su ciò che lo schema può esprimere — profondità di annidamento, keyword supportate, union, numero di campi — e **non impongono comunque vincoli di valore numerico** (cosa che F sfrutta tenendo i numeri fuori dallo schema: §2, §4). Quindi: lo schema Pydantic va tenuto entro quei limiti, e ciò che la grammatica non esprime (il budget, i futuri vincoli inter-campo) resta al gate (§4). Quali siano esattamente i limiti **si verifica sulla doc API attuale all'implementazione, non a memoria** (F-12).

---

## 4. Il gate: tre strati nel motore

Il gate è il punto in cui "ciò che non passa non tocca lo stato" (FNC §5.1). Vive nel **motore** (mai membrana, mai bus — IC §4). Tre strati, in quest'ordine:

1. **Conformità di schema.** Il candidato parsa nel modello Pydantic: tipi giusti, campi presenti, enum sintatticamente validi. Sotto il meccanismo a grammatica del backend (PLK §5) questo è **garantito per costruzione**; il parse Pydantic lo ri-afferma comunque, perché è la garanzia *backend-agnostica* (un backend senza grammatica — il locale, assente nell'MVP — produrrebbe testo da parsare).
2. **Appartenenza al catalogo.** Ogni `Blocco`/`Archetipo`/`Rarità` scelto è un membro legale **e** ha un binding nel registry (§3). Anche questo è in larga parte garantito dalla grammatica (gli enum *sono* la grammatica), ma il gate lo controlla: è l'autorità che non dipende dal backend.
3. **Rispetto del budget.** Rarità e insieme di blocchi cadono dentro il **set ammissibile per il contesto** — definito dalla **profondità del piano** (il `livello`, posseduto dal motore), dal budget d'incontro, o dal budget **anomalo** se il motore ha tirato (§4.3). **Questo strato è obbligatorio e insostituibile:** la grammatica vincola il *vocabolario*, **non** i *valori* (PLK §5). Il budget è un vincolo di valore → solo il gate lo garantisce.

> **La validazione cambia natura** (FNC §5.5): non più *"il numero è nel range?"* ma *"ogni blocco scelto esiste nel catalogo?"* **più** *"la combinazione categoriale rientra nel budget?"*. Lo strato 3 è l'erede del vecchio clamp numerico, salito di livello.

> **Perché il budget NON si spinge dentro lo schema/grammatica** (scorciatoia da chiudere). Un implementatore potrebbe pensare di iniettare il budget nello schema per-chiamata (es. restringere l'enum `Rarità` ai valori ammessi) così che lo imponga la grammatica. **Non si fa, per due ragioni.** *(a) Espressività:* il budget è in generale un vincolo **fra campi** — il "costo" d'incontro è funzione di `(rarità, livello, blocchi)` insieme — e la grammatica di uno schema **non esprime aritmetica fra campi** (può vincolare un singolo campo, non "la somma dei campi ≤ tetto"). È la stessa famiglia dei vincoli inter-campo annotati in §9. *(b) Trasporto vs dominio:* uno schema che incorpora il budget farebbe **colare il dominio nel percorso del provider** (PLK §3/§4) e cambierebbe a ogni chiamata col contesto/anomalia — proprio ciò che la firma `genera(prompt, schema)` con prompt opaco tiene separato. Il budget resta un **vincolo di valore arbitrato dal gate**, sempre; lo schema vincola il *vocabolario*, non i *valori*.

### 4.1 I due canali del budget (perché compare due volte, ed è voluto)

Il budget raggiunge l'AI per **due vie distinte e complementari**:

- **Nel prompt, come testo** (soft). Il motore inietta il budget/set ammissibile nel prompt (FNC §5.1): *l'AI lo rispetta solo se glielo dici*. Necessario — senza, l'AI non sa entro cosa pescare — ma **mai sufficiente**: è una richiesta, non una garanzia.
- **Nel gate, come controllo di valore** (hard). Lo strato 3. È **l'unica garanzia vera**.

Il prompt rende l'output *probabilmente* in-budget; il gate lo rende *certamente* in-budget (o lo respinge). Cintura e bretelle: il primo riduce i rifiuti, il secondo li rende impossibili da superare.

### 4.2 `livello` non è nello schema: è profondità di piano, del motore

Una versione precedente di F teneva `livello: int` fra i campi emessi dall'AI, delegando a G *chi lo decide*. **G ha deciso** (G §8.1): il `livello` è la **profondità del piano**, un contatore di stato posseduto dal motore che avanza **solo** su `DiscesaPiano`. L'AI **non lo emette affatto** — non "lo emette e il gate lo sovrascrive". Il campo è perciò **rimosso da `EntitaGenerata`** (§2): il motore lega l'entità generata al `livello` corrente al momento della materializzazione, dopo il gate. Resta vero che l'AI non emette alcuna **statistica numerica**; ora non emette **nessun** `int`. La leva del budget (strato 3) usa la profondità come **contesto**, non come campo scelto dall'AI. *(Autorità: G §8.1/§8.2; forma dello schema: qui.)*

### 4.3 L'anomalia non passa per lo schema

L'anomalia (FNC §5.5) è un **tiro del motore, seeded**, deciso **prima** della chiamata. Quando scatta, il motore sostituisce il budget normale con uno gonfiato (da tabella, soffitto definito — valori in G) e lo inietta nel prompt come qualunque altro budget. Conseguenze per F:

- Per lo schema e il gate, un'anomalia è **solo un budget diverso**. Nessun campo, nessun ramo speciale: l'AI pesca dentro il budget che riceve, e il gate valida contro *quel* budget.
- Quindi **un candidato fuori dal budget corrente è sempre una violazione, mai un'anomalia mancata.** Se il motore non ha tirato l'anomalia, non c'è nulla da "ripromuovere ad anomalia" a posteriori: l'autorità sullo sforamento è del motore, a monte (FNC §5.5, invariante). Questo chiude la porta a qualunque "giudice a valle" che reinterpreti un fuori-budget (vedi §6.2).
- Al *reveal*, il motore pubblica `AnomalyTriggered` sul bus perché lo showrunner la narri (FNC §5.5, §8): è un evento di dominio (Canale B), **non** un campo dello schema.

---

## 5. Una sola funzione: la chiamata di sola prosa

Tutte le chiamate all'AI passano per `genera(prompt, schema) → candidato | None` (PLK §2). Non c'è un secondo verbo.

- **Narrazione** → `genera(prompt, TurnoNarrazione)`: output ricco, validato dal gate (§4), che diventa stato ECS.
- **Flavor di combattimento e voce dello showrunner** (FNC §5.2, §8) → `genera(prompt, Flavor)`: output degenere a un campo, `{ testo: str }`. Il provider non sa né gli importa che lo schema sia banale — trasporta e basta (PLK §2). Niente secondo metodo da specificare e mantenere.
- **`Altro` nell'MVP, se presente** (FNC §5.6) → **anch'esso modalità-prosa**, `genera(prompt, Flavor)`: produce **continuazione narrativa**, non dati di gioco. Per costruzione **non tocca lo stato meccanico** (è prosa, non `TurnoNarrazione`): è il confine duro di FNC §5.6 reso strutturale — il testo libero può ammorbidire la narrazione, non azzerare HP o fabbricare loot. Eredita la politica della modalità-prosa (può mancare: se fallisce, il motore degrada a una continuazione neutra, lo stato non cambia). Così l'affermazione "ogni chiamata all'AI passa per `genera`" **regge anche per l'MVP**, non solo per narrazione e flavor.

> La genericità del verbo è proprio ciò che PLK §2 chiedeva: lo `schema` rende `genera` non-cablato sulla generazione-stanza. La differenza fra `Altro`-MVP (sopra) e `Altro`-post-MVP è lo **schema**, non il verbo: nell'MVP è la modalità-prosa (non risolve, narra); **post-MVP** diventa lo stesso verbo con uno schema strutturato "intento → evento" che il motore *risolve* (FNC §5.6, §9).

### 5.1 Lo schema seleziona l'intera politica di fallimento (retry, timeout e fallback) — lato motore

Conseguenza da inchiodare, altrimenti l'agente — vedendo *un* verbo — applica *un* trattamento a tutto. **La funzione è una; la politica di fallimento è selezionata dallo schema, e copre retry, timeout *e* fallback, non solo il fallback:**

- **Narrazione (atomica, e vale la pena ritentare).** Produce `prosa + entità + opzioni` *insieme* (FNC §5.1). È il percorso che alimenta lo stato del gioco: un errore transitorio **ritenta** (con backoff, §6.1), poi, esaurito, fa cadere i tre campi insieme e il motore applica i tre fallback **contemporaneamente** (§6.3). Non esiste lo stato "prosa valida ma entità no" come esito accettato.
- **Modalità-prosa (cosmetica, fallisce in fretta).** Flavor di combattimento, voce dello showrunner, `Altro`-MVP. La risoluzione meccanica è **già avvenuta** o **non è in gioco**: il testo è cosmetico (FNC §5.2, §8). Qui la politica è **opposta**: timeout breve, **retry minimo o nullo**, e al fallimento si **salta** — il motore non ripiega su niente (flavor) o degrada a una continuazione neutra (`Altro`-MVP). Ritentare ≈5 volte una battuta dello showrunner sprecherebbe token (cosa che PLK tiene d'occhio) e remerebbe contro l'invariante FNC §8 "il combattimento non attende mai il commento".

Il provider vede sempre `genera(prompt, schema) → candidato | None`, identico. È il **motore** — l'unico che sa *che tipo* di chiamata è, perché è lui che ha scelto prompt e schema — a decidere quanto ritentare, quanto attendere e su cosa ripiegare. **Retry e fallback sono selezionati dallo stesso criterio** (lo schema), non trattati uniformemente.

---

## 6. Fallimento: due owner, un fallback

Ogni fallimento appartiene a una di **due categorie**, separate dal confine **trasporto vs dominio** di PLK §3. Non c'è una terza categoria, e non si introduce un secondo modello-giudice (§6.2).

### 6.1 Fallimento di trasporto (lo possiede il provider)

Il candidato non arriva conforme per cause **fuori dal dominio**: rete, rate-limit / IP temporaneamente bloccato (es. HTTP 429), 5xx, timeout, troncatura, refusal. È territorio del layer provider (PLK §3, §6). F fissa solo la **forma** dei rami (quale ritenta, quale no), **non i valori** (numero di retry, durata del timeout) — quelli sono il buco "politica di fallback" → §9. La forma è selezionata per tipo di chiamata (§5.1):

- **Transitorio** (rete / 429 / 5xx / timeout) → **retry con backoff**, che **onora l'header `Retry-After`** quando presente (un'attesa cieca contro un rate-limit lo ri-colpirebbe). *Quanto* ritentare dipende dal tipo: la narrazione ritenta, la modalità-prosa quasi no (§5.1). Il *valore* (tentativi, backoff, timeout) → §9.
- **Troncatura / incompleto** (`stop_reason: "max_tokens"`) → **non** è JSON malformato (sotto grammatica non esiste): si **alza il limite di token o si accorcia la richiesta**; un retry a parità di richiesta ri-troncherebbe identico (PLK §6).
- **Refusal** (`stop_reason: "refusal"`) → trattato come generazione fallita, **senza retry** (sullo stesso prompt si ripeterebbe deterministicamente; va anzi rimosso il turno rifiutato dal contesto prima di proseguire) (PLK §6).

Esaurito il trasporto, `genera` ritorna **`None`** e la palla passa al dominio (§6.3).

> **Nessun turno parziale tocca il save.** Un turno muta lo stato **solo alla risoluzione**; il World è l'unità di salvataggio (ESP §0.1, FNC §6). Una chiamata in volo — fallita, in retry, o cancellata dal worker `exclusive` quando il giocatore va avanti (IC §6) — **non scrive nulla**: lo stato resta quello del turno precedente, e durante l'attesa la UI è viva via async (FNC §7). Tornare "al messaggio precedente" non è un meccanismo da costruire: è la conseguenza del fatto che il fallimento avviene *prima* della risoluzione. Né si addebita uno stato a metà.

### 6.2 Fallimento di dominio (lo possiede il motore) — e perché niente secondo modello-giudice

Il candidato **arriva e parsa** (schema ok), ma il **gate** lo respinge. Sotto la grammatica del backend Anthropic, schema e catalogo sono garantiti per costruzione (§4, PLK §6): nell'MVP **l'unico** rifiuto-di-gate possibile è il **budget** (strato 3).

Un retry qui è quasi sempre inutile — il budget era *già* nel prompt (§4.1) — ma è ammesso al più una volta dentro la politica di §9. Il terminale è il **fallback strutturato deterministico** (§6.3).

**Niente modello-giudice a valle.** Si è valutato e **scartato** interpellare un modello economico (es. Haiku) per decidere se un fuori-budget "possa passare come anomalia" o per "suggerire lo schema giusto". Tre ragioni dirimenti:

1. **Lo schema è già garantito** dalla grammatica: non c'è uno schema sbagliato da "suggerire". Il solo fallimento reale è il budget.
2. **Far decidere a un modello se un budget sforato diventa anomalia significa far *invocare l'anomalia all'AI*** — l'invariante vietato da FNC §5.5 (§4.3). L'autorità sullo sforamento è del motore, a monte e seeded; non c'è nulla da ri-giudicare dopo.
3. Un secondo modello **raddoppia i rami di fallback** che PLK ha evitato di proposito (PLK §6) e introduce una sorgente di nondeterminismo **non-seeded** che deciderebbe stato → rompe il replay riproducibile (FNC §9).

### 6.3 Il fallback unico (atomico, locale, deterministico)

`None` (trasporto, §6.1) e rifiuto-di-gate (dominio, §6.2) **convergono sullo stesso fallback atomico** per il turno di narrazione. F qui **estende PLK §6**: PLK aveva dichiarato atomico il solo caso `None`; F porta sotto la stessa via anche il rifiuto-di-gate, e lo fa per un motivo di coerenza narrativa — tenere prosa+opzioni valide e sostituire *solo* l'entità (l'opzione "Y") produrrebbe testo che descrive "uno slime Leggendario" mentre nei fatti c'è un comune. Quindi:

- `prosa` → **testo neutro pre-confezionato**.
- `entità` → il motore **designa (deterministicamente) un archetipo di default, dentro il budget corrente** (FNC §5.5, §10). "Designa", non "pesca a caso": il default è scelto in modo deterministico (un archetipo designato per il tier di budget), così il fallback **non consuma il seed stream del gioco** (§8). *Quale* archetipo sia il default è un valore della politica di fallback (§9); il *vincolo* (deterministico, niente RNG di gioco) è di F.
- `opzioni` → il **menu fisso di default** (`Combatti` / `Scappi` / `Altro`).

I tre si applicano **insieme**. Tre proprietà lo rendono l'"inossidabile" richiesto:

- **Atomico** — niente turni mezzi-validi, niente incoerenza prosa↔entità.
- **Locale** — catalogo, formula e testo neutro sono **in casa**: il fallback non fa rete. Anche del tutto offline o rate-limitati, il gioco produce un turno **giocabile e in-budget**.
- **Deterministico** — l'archetipo di default è *designato* (non un'estrazione) e il testo neutro non è un'altra chiamata LLM: nessuna nuova sorgente di nondeterminismo, e **nessun consumo del seed stream** (FNC §9, §8).

> **La distinzione di FNC §10 vale *tra fasi*, non dentro la chiamata di narrazione.** Generazione strutturata di narrazione = **atomica** (tutto-o-niente, sopra). Flavor di combattimento = prosa separata, a valle della risoluzione, che può **mancare** (§5.1). Sono due casi diversi perché stanno in due punti diversi del flusso, non perché abbiano due interfacce.

---

## 7. Anatomia del prompt (forma, non testo)

La *costruzione* del prompt è dominio del motore ed è già fissata (PLK §2, §3): F non scrive il testo. Fissa solo i **tre ingredienti** che il motore assembla, perché l'agente sappia *cosa* deve contenere:

1. **Voce / tono** — l'identità narrativa (il dungeon che parla, la voce dello showrunner). È la parte "di voce", i cui *valori* maturano in G.
2. **Contesto + budget** — stato rilevante (piano, profondità, situazione) e il **budget/set ammissibile iniettato come testo** (§4.1, FNC §5.1), anomalia inclusa se già tirata (§4.3).
3. **Schema** — il modello Pydantic (§2) che pilota il formato dell'output strutturato.

Il provider riceve l'1+2+3 già fusi in una stringa **opaca** e lo `schema` separato; non interpreta né riformatta (PLK §2). Il motore è l'**unico** punto che conosce il *tipo* di chiamata, e di conseguenza sceglie prompt, schema e intera politica di fallimento — retry, timeout e fallback (§5.1).

---

## 8. Determinismo e cache (seam verso H, non meccanismo)

L'output **validato** (post-gate) è l'unità che abilita il **replay riproducibile**: seed + cache degli output LLM validati (FNC §9, IC C-5). F **annota** il seam ma non lo possiede:

- La **chiave plausibile** è il prompt *seeded* (anomalia inclusa, perché è già nel budget iniettato — §4.3); il **valore** è il candidato validato.
- **Proprietà, chiave esatta e formato della cache si fissano in H** (PLK §7), non qui. F garantisce solo che esiste un punto netto — l'uscita del gate — dove l'output è validato e quindi cacheable.

**Ma "cache degli output validati" da sola non basta al replay fedele, e F deve dichiararlo** (altrimenti consegna a H un seam che *sembra* netto e non lo è):

- **I turni in fallback vanno registrati anch'essi.** Un turno andato in fallback (§6.3) **non ha** un output validato da cacheare. Se al replay si trovasse solo la cache degli output validati, quel turno darebbe **cache-miss** → il motore richiamerebbe l'LLM → che stavolta potrebbe riuscire → la run replayata **diverge** da quella registrata. Quindi il fatto stesso che T sia andato in fallback è informazione da registrare: il replay deve **riprodurre il fallback**, non ritentare la chiamata. (Il record è "output validato *oppure* marcatore di fallback", non "output validato o niente".)
- **Il fallback non deve consumare il seed stream del gioco.** Se al record il fallback estraesse RNG dallo stream condiviso e al replay (dove T magari riesce, o è marcato) non lo facesse, **tutti i tiri seeded successivi si desincronizzerebbero**. Per questo l'archetipo di default è **designato, non pescato** (§6.3): zero consumo di RNG di gioco. Se mai un fallback dovesse pescare, userebbe un RNG separato dallo stream del gioco.

> Il **meccanismo** (formato del log, chiave, marcatore di fallback) è di **H**. Ma il **vincolo** è di F, perché F possiede il framing "l'uscita del gate è il punto cacheable": senza queste due righe, quel punto sembra l'unico da registrare, e non lo è. F-13 lo rende verificabile.

---

## 9. Dipendenze annotate e buchi dichiarati (alla FNC §12)

Restano ai proprietari; F li *colloca*, non ne fissa il valore:

- **Contenuti del catalogo** (archetipi, rarità, blocchi registrati) → **G** + fase di popolazione MVP. F fissa che sono enum chiusi con registry; non le voci.
- **Formula `(archetipo, rarità, livello) → statistiche`, tabelle di budget per contesto, tabella anomalie (voci, probabilità, soffitto)** → **G** (FNC §12).
- **Autorità su `livello`** → **risolta da G** (G §8.1): è la profondità del piano, posseduta dal motore; l'AI non lo emette. Conseguenza sullo schema applicata: il campo è **rimosso da `EntitaGenerata`** (§2, §4.2). Non più un buco aperto.
- **Politica di fallimento esatta** (numero di retry per tipo, forma del backoff/`Retry-After`, durata dei timeout, forma del testo neutro, archetipo di default designato) → buco di FNC §10. F fissa la *forma* (retry e fallback selezionati dallo schema, §5.1; refusal senza retry; default deterministico), non i *valori*. Eventuali manopole di degrado per il giocatore (avvisare? ri-tentabile?) sono valori su questa spina, non nuova architettura.
- **Testo libero `Altro`** → nell'**MVP**, se presente, è modalità-prosa via `genera` (continuazione narrativa, mai stato meccanico — §5, FNC §5.6); **post-MVP**, stesso verbo con schema strutturato "intento → evento tipizzato" su un menu **chiuso e noto**, con via d'uscita deterministica per gli intenti non mappabili (FNC §5.6). F garantisce che l'interfaccia regge entrambi; specifica la mappatura MVP, non lo schema post-MVP.
- **Vincoli fra campi del catalogo** (es. un blocco legale solo per certi archetipi) → per ora **moot** (FNC §5.5: ogni combinazione legale, "nessun caso speciale"). Se introdotti, **sfuggono alla grammatica e cadono nel gate** (strato 2/3), non nello schema → promemoria per **G** (PLK §5).
- **Mappa `Durata → carico-tick` ed etichette diegetiche** → **G/Gruppo 2** (J §3.2/§3.3). F fissa che `Durata` è un enum chiuso con ordine totale; i *valori* (quanti tick vale ogni durata, e i "secondi" di finzione) vivono nel catalogo del motore, calibrati sulla cadenza per-stanza (J §4). *(buco aggiunto dal ritocco C1)*
- **Cache** (chiave/formato/proprietà) → **H** (§8).

> Questi non bloccano F: lo confermano. Sono valori sulle righe del contratto, mai la struttura del contratto.

---

## 10. Criteri di accettazione (verificabili)

- **F-1** Esiste **uno** schema `TurnoNarrazione { prosa, entità{archetipo, rarità, blocchi, nome, descrizione}, opzioni, durata }` (senza `livello`: profondità del motore, §4.2; `durata` = categoria da enum chiuso, mappata a carico-tick dal motore — J §3.4, C1); un turno di narrazione = **una** chiamata `genera`, mai più d'una (FNC §5.1). `Flavor { testo }` **non** porta `durata`.
- **F-2** Lo schema/DTO vivono in `contracts`; `contracts` importa **solo** stdlib + Pydantic (pinnato e congelato in lockfile), **mai** esper / Textual / provider (statico). *(§3.1, IC §2)*
- **F-3** `EntitaGenerata` **non** ha campi numerici: né statistiche (hp/danno/difesa/durate) né `livello` (rimosso — profondità di piano, del motore: §2/§4.2). I numeri li deriva/lega il motore (statico). *(§2, §4.2, FNC §5.5; allineato a G-17)*
- **F-4** I campi a conseguenza meccanica sono **enum chiusi**; **non** esiste campo con cui l'AI possa invocare l'anomalia o alzarsi il budget (statico). *(§2, §4.3)*
- **F-5** Il gate vive nel **motore** (non membrana, non bus) e applica i tre strati **schema · catalogo · budget**; lo strato budget è presente e obbligatorio anche sotto grammatica. *(§4, IC §4)*
- **F-6** Ogni membro di enum del catalogo-contratto ha un binding nel **registry** del motore: nessun nome accettabile dal gate ma non istanziabile (statico). *(§3)*
- **F-7** Le chiamate di **sola prosa** (flavor combattimento, showrunner, **`Altro`-MVP**) usano lo **stesso verbo** `genera` con schema `Flavor { testo }`; **nessun** secondo metodo sul provider; l'`Altro`-MVP non muta mai lo stato meccanico (statico/comportamentale). *(§5)*
- **F-8** Il fallimento del turno di narrazione è **atomico**: sia `None` (trasporto) sia rifiuto-di-gate (dominio) collassano sul **medesimo** fallback (testo neutro + archetipo di default *designato* nel budget + menu fisso), applicato **insieme**. La modalità-prosa, invece, può **mancare**. **Retry/timeout sono selezionati dallo schema** come il fallback: narrazione ritenta, modalità-prosa fallisce in fretta (§5.1). *(§5.1, §6.1, §6.3)*
- **F-9** Nessun **secondo modello** decide stato o reinterpreta un fuori-budget; l'anomalia è decisa a monte dal motore (seeded), mai da un giudice a valle. *(§4.3, §6.2)*
- **F-10** Il budget raggiunge l'AI **due volte** — iniettato nel prompt (soft) **e** controllato dal gate (hard); l'iniezione nel prompt non sostituisce mai il gate. *(§4.1)*
- **F-11** Nessun turno parziale tocca il save: lo stato muta solo alla risoluzione; una chiamata fallita/cancellata non scrive nulla. *(§6.1)*
- **F-12** Il meccanismo nativo di output strutturato **non** è cablato in F: è confinato nel backend Anthropic (PLK §5) e verificato sulla doc API attuale all'implementazione. F specifica lo **schema**, non l'API. *(§3.1, PLK §5)*
- **F-13** Il seam di replay è **completo**: un turno andato in fallback è registrato come tale (il replay lo riproduce, non richiama l'LLM), e il fallback **non consuma il seed stream del gioco** (archetipo di default designato, non pescato). Vincolo imposto da F a H; il meccanismo è di H. *(§8, §6.3)*
- **F-14** Il campo `durata` di `TurnoNarrazione` è una **categoria** (`Durata`, enum chiuso), **mai** un numero; il motore la mappa a carico-tick via catalogo (non in `contracts`) e via gate (`durata→gate→carico-tick`); `Flavor` **non** ha `durata`; una `TurnoNarrazione` che emette `EncounterStarted` ha `durata == TURNO` dopo il gate (clamp d'ingresso, C3). *(§2, J §3.4; ritocco C1/C3)*

---

## 11. Invarianti rafforzati da questo documento

- **Il contratto porta i nomi, il motore possiede il significato.** L'AI sceglie da enum chiusi; binding (registry) e numeri (formula) sono del motore. *(rafforza FNC §5.5)*
- **Una sola interfaccia verso l'AI** (`genera(prompt, schema)`); l'**intera** politica di fallimento — retry, timeout *e* fallback — è decisa dallo schema **lato motore**, mai dal provider. *(rafforza PLK §2)*
- **Il gate è l'unica autorità sulla validità**; il budget passa per il gate **sempre**, perché la grammatica vincola il catalogo e non i valori. *(rafforza FNC §5.1, IC §4)*
- **L'anomalia è un tiro del motore (seeded), invisibile allo schema.** L'AI la narra, non la invoca; nessun giudice a valle la reinterpreta. *(rafforza FNC §5.5)*
- **Fallback atomico, locale, deterministico:** il gioco produce sempre un turno giocabile e in-budget, anche offline; degrada la forma, mai la giocabilità; il fallback non consuma il seed stream. *(rafforza FNC §10, PLK §6, §9)*
- **Replay completo:** si registrano gli output validati **e** i fallback; il punto cacheable (uscita del gate) non è l'unico da registrare. *(rafforza FNC §9; vincolo verso H)*
- **Trasporto vs dominio:** il provider possiede la chiamata API; il motore possiede gate, scelta del fallback e *politica* di retry. Nessuna terza autorità, nessun secondo modello. *(rafforza PLK §3)*

---

## 12. Cosa NON facciamo (anti-over-engineering)

- ❌ Far emettere all'AI **statistiche numeriche** (hp/danno/…): emette categorie, il motore deriva i numeri. *(§2)*
- ❌ Un **secondo metodo** sul provider per la prosa: è `genera` con schema banale. *(§5)*
- ❌ Applicare **un trattamento uniforme** a tutte le chiamate perché la funzione è una: retry *e* fallback sono selezionati dallo schema (narrazione ritenta ed è atomica; modalità-prosa fallisce in fretta e si salta). *(§5.1)*
- ❌ Un **secondo modello-giudice** (Haiku o altro) che decide se un fuori-budget "passa come anomalia" o suggerisce lo schema: viola FNC §5.5 e FNC §9, e risolve un problema (schema sbagliato) che sotto grammatica non esiste. *(§6.2)*
- ❌ Tenere prosa+opzioni e sostituire **solo** l'entità su rifiuto-di-gate (incoerenza narrativa): il fallback è atomico. *(§6.3)*
- ❌ **Pescare** l'archetipo di fallback dallo stream RNG del gioco: è *designato* (deterministico), o il replay si desincronizza. *(§6.3, §8)*
- ❌ Registrare per il replay **solo** gli output validati, dimenticando i turni in fallback: al replay darebbero cache-miss e divergerebbero. *(§8)*
- ❌ Mettere il **gate** (o parte di esso) nella membrana o nel bus: sta nel motore. *(§4, IC §4)*
- ❌ Mettere **registry/formula** in `contracts`: importerebbero esper. In `contracts` vivono solo gli enum (vocabolario). *(§3)*
- ❌ **Cablare** in F la firma del meccanismo di structured output a memoria: si verifica all'implementazione, confinata nel backend. *(§3.1, F-12)*
- ❌ Riempire in F i **contenuti** del catalogo, la formula, le tabelle di budget/anomalie: sono di G. *(§9)*
- ❌ Far scrivere a una chiamata **in volo** sul save, o costruire un meccanismo apposta per "tornare indietro": il fallimento è già *prima* della risoluzione. *(§6.1)*

---

### Nota per l'aggiornamento dell'indice

In `progetto-indice-decisioni.md`:

- **Cruscotto dei nodi:** **F** da ⬜ a ✅. Sintesi: *"Schema del contratto AI↔motore in Pydantic (modulo `contracts`); catalogo = enum chiusi nel contratto + registry/formula nel motore (contenuti rimandati a G); una sola funzione `genera(prompt, schema)` per ogni chiamata all'AI (prosa, flavor e `Altro`-MVP = schema banale `{testo}`); gate a tre strati nel motore (schema · catalogo · budget), budget obbligatorio perché la grammatica non lo impone; retry e fallback selezionati dallo schema (narrazione ritenta ed è atomica, modalità-prosa fallisce in fretta); fallimento a due owner (trasporto: provider; dominio: motore) con fallback unico atomico, locale e deterministico (testo neutro + archetipo di default **designato** nel budget + menu fisso); niente secondo modello-giudice; l'anomalia resta tiro seeded del motore, invisibile allo schema; il seam di replay registra anche i turni in fallback e non consuma il seed stream. Dettaglio in `contratto-ai-motore.md`."*
- **Documenti del progetto:** aggiungere `contratto-ai-motore.md` (F) — *Schema AI↔motore, gate, mappatura su `genera`, fallback* — ✅.
- **Nodi aperti → F:** spostare in "Nodi chiusi"; aggiungere il paragrafo di razionale.
- **Ordine di lavoro consigliato:** barrare il punto 4 ("F"). Prossimo: **G** (combattimento), che eredita i buchi di gameplay dichiarati (§9: contenuti catalogo, formula, budget, anomalie, autorità su `livello`, politica di fallback) più le voci di FNC §12 e i valori delegati da E.

> **Per G e H, conseguenze dirette di F:** G riempie catalogo/formula/budget/anomalie e decide l'autorità su `livello`; H possiede la cache degli output validati (chiave = prompt seeded) di cui §8 fissa solo il seam.
