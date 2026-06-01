# Implementazione di Esper — regole di progetto

Questo documento fissa **come** si usa Esper nel progetto. Non è introduttivo: presuppone la scelta architetturale A-bis (ECS forte + event bus) e A-ter (libreria `esper`, non scritto a mano). È scritto come vincolo per l'agente che implementa: ogni regola qui è normativa, non un consiglio.

## 0. Dipendenza: versione fissata e vendorizzata

Esper ha rotto l'API in modo profondo alla versione 3.0 (l'oggetto `World` è stato rimosso e i suoi metodi sono diventati funzioni a livello di modulo). Gran parte della documentazione e degli esempi in circolazione — e con ogni probabilità i dati su cui l'agente è stato addestrato — usano ancora il vecchio idioma `world = esper.World()`, che **non è più valido**.

Regole:

- La dipendenza è **pinnata** a una versione esplicita della serie 3.x (es. `esper==3.7`). Mai un range aperto.
- Esper è **vendorizzato**: copiato dentro il repository, non risolto a build-time da un indice esterno. È puro Python senza dipendenze, quindi questo è gratuito e dà riproducibilità totale del build.
- Si pinna anche la **versione di Python** (es. `3.12`). Esper insegue solo le versioni di Python non-EOL, e dato che vendorizzi la riproducibilità del build dipende anche dall'interprete, non solo dalla libreria.
- Si usa **solo l'API a livello di modulo** (`esper.create_entity()`, `esper.add_component()`, `esper.get_components()`, …). L'idioma `esper.World()` è **vietato**: se compare nel codice generato, è un errore da correggere.

### 0.1 Lo stato globale è implicito: isolarlo nei test e nel save

L'API a livello di modulo opera su un **contesto World di default implicito**, attivo all'import. Per il gioco va benissimo — c'è un mondo solo — ma lo stato globale morde in due punti che ci riguardano.

**Test.** Ogni test eredita il contesto del precedente. Senza isolamento, l'agente scriverà test che passano in isolamento e falliscono in sequenza: la flakiness peggiore da diagnosticare. Regola: ogni test gira su un **contesto dedicato e azzerato**, mai sul default. In setup `esper.switch_world("<nome-test>")` crea un mondo isolato (uno World inesistente viene creato al primo switch); in teardown si torna al default e si elimina il contesto di test con `esper.delete_world(...)`. Nota: non si può eliminare il contesto attivo, quindi si switcha via *prima* di eliminarlo. Eliminandolo a fine test, lo switch del test successivo lo ricrea vuoto — isolamento garantito.

**Save/load.** Serializzare e ricaricare lo stato significa fare i conti con quale contesto è attivo. Regola: il livello di save/load è l'**unica autorità** su `esper.current_world`; nessun altro modulo cambia contesto. Quando si arriverà al punto H (salvataggio), questa è la premessa da cui parte.

## 1. I componenti sono dati puri

Un componente è una struttura dati. Nessun metodo che "fa" qualcosa, nessuna logica di dominio, nessuna chiamata ad altri componenti o sistemi. Al più un `__init__` o, idiomaticamente, un `@dataclass`.

```python
from dataclasses import dataclass

@dataclass
class Salute:
    attuale: int
    massima: int

@dataclass
class Veleno:
    danno_per_turno: int
    turni_rimanenti: int
```

Nel momento in cui un componente ha un metodo che trasforma il proprio stato o quello di altri, l'oggetto monolitico è tornato sotto mentite spoglie. Il binario dato/logica è strutturale e non negoziabile.

## 2. Tutta la logica vive nei sistemi (Processor)

Un sistema è una sottoclasse di `esper.Processor` con un metodo `process`. Legge componenti tramite query e li trasforma. È l'unico posto dove vive la logica.

```python
class SistemaVeleno(esper.Processor):
    def process(self, dt):
        for ent, (salute, veleno) in esper.get_components(Salute, Veleno):
            salute.attuale -= veleno.danno_per_turno
            veleno.turni_rimanenti -= 1
            if veleno.turni_rimanenti <= 0:
                esper.remove_component(ent, Veleno)
```

L'ordine di esecuzione dei sistemi è **deterministico** e dichiarato esplicitamente tramite la priorità dei Processor (numeri più alti per primi). Quest'ordine è parte della specifica, non un dettaglio implementativo: cambiarlo cambia il comportamento del gioco.

## 3. Il contratto entità↔sistema è il componente, non l'evento

Un sistema dichiara su cosa agisce attraverso la firma dei componenti che interroga: `get_components(Veleno, Salute)` *è* il contratto. È statico, strutturale, ed è **pull** — il sistema interroga, l'entità non sa di essere interrogata.

Questo è ciò che rende gratuita la composizione: "boss + veleno + stordito + rigenerazione + contenitore-loot" è semplicemente un'entità con quei componenti. Nessun caso speciale: ogni sistema raccoglie le entità che hanno la sua combinazione e fa il suo lavoro. Aggiungere un nuovo effetto = aggiungere un componente + un sistema, senza toccare i sistemi esistenti.

## 4. I sistemi non si chiamano tra loro: due canali di comunicazione

Un sistema non invoca mai un altro sistema direttamente. Comunica in uno di due modi, e **la scelta del canale è normativa**, non lasciata all'improvvisazione.

### Canale A — componente-come-messaggio (in-loop, deterministico)

Quando la reazione **è essa stessa un sistema dentro il loop** che lavora sullo stato di un'entità, il "messaggio" è un componente-tag. Persistente, interrogabile, raccolto al turno successivo nell'ordine deterministico dei sistemi.

```python
# SistemaCombattimento, alla morte dell'entità: NON chiama il sistema loot.
esper.add_component(ent, DroppaLoot())

# SistemaLoot, al suo turno, raccoglie il tag E LO RIMUOVE nello stesso process:
for ent, (drop, posizione) in esper.get_components(DroppaLoot, Posizione):
    genera_loot(posizione)
    esper.remove_component(ent, DroppaLoot)   # senza questo, droppa a ogni ciclo
```

Due regole non negoziabili su questo canale, perché sono entrambe omissioni che un agente replica fedelmente dall'esempio:

**Il consumatore rimuove il tag.** Un componente-messaggio che non viene tolto dopo l'uso non è un messaggio: è stato permanente, e il sistema lo riprocessa a ogni ciclo (loot infinito). Chi raccoglie un tag-messaggio lo **rimuove nello stesso `process`**, oppure l'entità viene distrutta. La semantica voluta è *edge-triggered* — succede una volta — non *level-triggered*.

**La latenza di un turno è intenzionale.** Il tag viene messo ora e raccolto al ciclo successivo, nell'ordine di priorità dei sistemi. In un gioco a turni questo è il comportamento deterministico voluto, non un ritardo da correggere: se il loot "non droppa subito", **non** si reintroduce la chiamata diretta vietata — la latenza è di design e va lasciata.

Usa questo canale quando la reazione è interna al gioco e tocca lo stato dell'entità. Tutto resta dentro l'ordine deterministico.

### Canale B — evento sul bus tipizzato (push, trasversale, esterno)

Quando la reazione è **trasversale, esterna al loop, o ha molti ascoltatori scorrelati** (showrunner, log, audio, achievement…), si usa un evento. È transitorio, **push**, fire-and-forget: chi pubblica non sa chi ascolta né quando.

Questo è il canale su cui si innesta lo showrunner: un osservatore esterno che reagisce a "è successo qualcosa" senza essere cablato dentro il sistema che lo ha generato.

### La regola di scelta

> Se la reazione è un sistema che opera su stato di entità → **componente** (Canale A), e resta nell'ordine deterministico.
> Se la reazione è trasversale, esterna al loop, o ha molti ascoltatori indipendenti → **bus** (Canale B).

Questa linea va tracciata esplicitamente perché è il punto in cui un'implementazione lasciata libera mescola i due canali e fa passare **stato di gioco** attraverso eventi non deterministici. È da lì che nascono i bug "ogni tanto non parte".

## 5. Il bus di dominio è uno strato sopra Esper, non il dispatcher di Esper

Esper offre un dispatcher di eventi nativo (`dispatch_event`, `set_handler`, `remove_handler`). **Non lo si usa direttamente per gli eventi di dominio.** Ha tre limiti che in un giocattolo sono accettabili ma in un sistema dove il bus è load-bearing sono fonti di bug sottili:

- gli eventi sono identificati per **stringa** (nessun controllo a compile-time, refuso = evento muto);
- **nessun controllo di tipo** sugli argomenti;
- gli handler sono tenuti per **weak-reference**: un handler senza un riferimento forte altrove può essere garbage-collected e sparire silenziosamente.

Regola: sopra Esper va un **bus tipizzato di progetto**, sottile:

- ogni evento è una **classe / `dataclass`** (es. `EntitaMorta(entita: int, causa: str)`), non una stringa;
- gli handler sono registrati esplicitamente e tenuti con **riferimenti forti**;
- la sottoscrizione è per **tipo di evento**, non per nome.

Internamente questo strato può anche appoggiarsi al dispatcher di Esper, ma la logica di dominio vede solo l'interfaccia tipizzata. Il dispatcher nativo di Esper non compare mai nel codice di gioco.

## Riepilogo delle regole

1. Versione di esper **e di Python** pinnate; esper vendorizzato; solo API a livello di modulo; `esper.World()` vietato.
2. Stato globale isolato: i test girano su un contesto dedicato e azzerato (`switch_world` / `delete_world`); il save/load è l'unica autorità su `current_world`.
3. Componenti = dati puri, zero logica.
4. Logica solo nei Processor; ordine dei sistemi deterministico e dichiarato.
5. Contratto entità↔sistema = firma dei componenti (pull).
6. I sistemi non si chiamano: Canale A (componente, in-loop) o Canale B (bus, trasversale), secondo la regola di scelta. Chi consuma un tag-messaggio lo rimuove nello stesso `process`; la latenza di un turno è intenzionale.
7. Eventi di dominio sul bus tipizzato di progetto, mai sul dispatcher nativo di Esper.
