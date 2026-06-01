# Nodo I — Piano di build per Claude Code

> **Cos'è questo documento.** È il nodo **I** dell'indice: la spec implementativa che raccoglie A→J e la traduce in **lavoro eseguibile**. Non riapre nessuna decisione (non ci sono gate aperti): le decisioni vivono nei documenti di dettaglio (ESP, FNC, IC, PLK, ACV, F, G, H, J) e lì restano normative. Questo file le **ordina in fasi** e per ciascuna fornisce un **prompt pronto da incollare in Claude Code**, i deliverable, i **criteri di accettazione già esistenti** da verificare, e una **stima**.
>
> **Regola d'oro.** Il guinzaglio contro la deriva dell'agente non è la sorveglianza: sono i **criteri di accettazione verificabili** + l'**arnia headless (C-5)**. Ogni fase si chiude solo quando i suoi criteri sono verdi nell'arnia. L'autonomia è sicura *dentro* questo recinto, non fuori.
>
> **Convenzione.** I riferimenti ai criteri usano i tag originali: **C-n** (IC), **F-n** (contratto), **G-n** (combattimento), **E-n** (ciclo vita), **H-n** (persistenza), **J-n** (tempo). I gate di release sono **G-L1/G-L2** (liveness) e **C-5** (seam headless).

---

## Parte 0 — Setup e regole operative (da fare una volta)

### 0.1 Il `CLAUDE.md` alla radice del repo

Claude Code carica automaticamente un `CLAUDE.md` alla radice a ogni sessione. È lì che vive l'orientamento permanente. Contenuto consigliato (sintesi normativa, **non** copia dei documenti — quelli stanno in `docs/`):

```markdown
# Progetto: RPG a turni AI-empowered (MVP — fetta verticale di un piano)

## Identità
RPG a turni ispirato a Dungeon Crawler Carl. Due fasi esclusive:
NARRAZIONE (AI genera mondo/entità) ⇄ COMBATTIMENTO (turni deterministici).
Principio invariante: **l'AI propone, il motore dispone** — l'AI è varietà di
contenuto, il motore arbitra OGNI esito, in entrambe le fasi.

## Le spec normative stanno in docs/ — leggile, non andare a memoria
ESP esper-implementazione · FNC fasi-narrazione-combattimento · IC interfaccia-contratto
PLK provider-llm-key · ACV architettura-ciclo-vita · F contratto-ai-motore
G combattimento-forma-run · H persistenza-salvataggio · J tempo-modello-scansione
progetto-indice-decisioni = cruscotto + invarianti trasversali.

## Architettura a tre strati (membrana a tenuta sui due lati)
- `motore/`     logica di gioco. NON importa MAI Textual.
- `contracts/`  DTO/eventi/intenti/schema Pydantic + interfaccia provider. ZERO
                dipendenze di progetto (solo stdlib + Pydantic). Non importa esper,
                Textual, provider.
- `adattatore/` UNICO modulo che importa Textual. Importa SOLO contracts + Textual,
                MAI esper/World/Processor.
Motore e vista si parlano solo via `contracts`, mai a vicenda. (C-2a, C-2b, C-3)

## Disciplina delle dipendenze
- Python pinnato (es. 3.12). esper VENDORIZZATO nel repo, pinnato 3.x, SOLO API a
  livello di modulo (`esper.World()` VIETATO). Textual pinnato esatto + lockfile
  (unica dipendenza "viva"). Pydantic pinnato. Nessun `pip install -U` silenzioso.

## Verifica, non ricordare (l'agente sbaglia a memoria su queste tre)
- API esper 3.x (modulo, non `World()`) — verifica sul codice vendorizzato.
- Output strutturato nativo Anthropic — verifica sulla doc API attuale.
- Worker API di Textual (`@work`/`run_worker`/`exclusive`/`group`/`cancel`) — doc attuale.

## Workflow di ogni task
1. Leggi i documenti citati nel prompt della fase.
2. Implementa SOLO ciò che la fase chiede (no scope creep, no widget di contorno).
3. Auto-verifica contro i criteri nominati (C-/F-/G-/E-/H-/J-). Scrivi i test.
4. Test headless verdi → fermati e riporta. Non procedere alla fase successiva.

## Test = contesto esper isolato (NON il default)
Ogni test: setup `esper.switch_world("<nome-test>")`; teardown `switch_world(default)`
POI `delete_world(...)`. Mai eliminare il contesto attivo. (ESP §0.1)

## Le linee rosse (dal cruscotto — invarianti trasversali, non si rinegoziano)
- L'LLM non decide MAI un esito; in combattimento: risolvi prima, narra dopo.
- L'AI non emette numeri: sceglie da enum chiusi dentro un budget; i numeri li
  deriva il motore. Mai applicare output LLM allo stato senza gate di validazione.
- async sì, thread no. `process()` guidato dal turno, mai dall'orologio/frame.
- Phase-gate strutturale (`PhasedProcessor`), mai check di fase a mano nei process().
- Un solo proprietario dell'avanzamento per ogni componente con stato.
- `switch_world` SOLO al confine guscio↔run; eventi di bus SOLO intra-run. Mai scambiarli.
- Bus tipizzato di progetto (dataclass, riferimenti forti), MAI il dispatcher nativo esper.
- Permadeath: terminale di run = `MortePersonaggio` (death-check seeded), non sconfitta.
- La chiave LLM non finisce MAI in URL, log, codice o documenti.
```

### 0.2 Layout del repo

```
repo/
├── CLAUDE.md
├── docs/                      # i 10 .md di progetto (sola lettura per l'agente)
├── pyproject.toml / requirements.txt + lockfile
├── vendor/esper/              # esper copiato, pinnato
├── src/
│   ├── contracts/             # DTO, eventi, intenti, schema F, interfaccia provider
│   ├── motore/                # ECS, sistemi, gate, combat, narrazione, save
│   ├── provider/              # backend LLM (fake + Anthropic), dietro contracts
│   ├── adattatore/            # Textual (unico import di Textual)
│   └── guscio/                # boot, macchina-guscio, orchestrazione app-level
└── tests/
    └── harness/               # arnia headless (C-5): adattatore nullo + provider fake
```

### 0.3 Come usare i prompt qui sotto

Ogni fase è un blocco ` ``` ` da incollare in Claude Code in una sessione dedicata, dopo il setup. I prompt presuppongono il `CLAUDE.md` già attivo (quindi non ripetono tutte le linee rosse: richiamano solo quelle critiche per quella fase). Chiudi una fase — criteri verdi, revisione fatta — prima di aprire la successiva.

---

## Parte 1 — Le fasi

L'ordine è quello di **costruzione** (sbloccare le dipendenze), che non coincide col rango architettonico: il guscio (E) è fondante ma si cabla a metà, perché ha bisogno del meccanismo di save (H). Intuizione di build chiave: **il motore si costruisce contro un provider FAKE deterministico** (fasi 3–4); il backend Anthropic reale si innesta dietro la stessa interfaccia solo alla fase 5. È esattamente lo "slot innestabile" di D/PLK, e tiene tutto seeded e testabile headless fino a che la rete non serve davvero.

---

### Fase 0 — Scaffolding, pinning, arnia headless

**Obiettivo.** Repo riproducibile + l'arnia headless (C-5) che farà da substrato di test a tutte le fasi successive. **Dipende da:** niente. **Documenti:** ESP §0–§0.1, IC §10 (C-5).

```
Sei all'inizio di un nuovo repo. Leggi docs/esper-implementazione.md (§0, §0.1) e
docs/interfaccia-contratto.md (§10, criterio C-5).

Compito:
1. Imposta il progetto Python con versione pinnata (3.12). Vendorizza esper: copia
   una versione 3.x pinnata in vendor/esper/, importabile, e VERIFICA sul codice
   vendorizzato che l'API a livello di modulo sia quella usata (esper.create_entity,
   add_component, get_components, switch_world, delete_world). `esper.World()` è
   vietato: aggiungi un test/grep che fallisce se compare nel sorgente.
2. Crea la struttura di cartelle: src/contracts, src/motore, src/provider,
   src/adattatore, src/guscio, tests/harness. File __init__ vuoti dove serve.
3. Costruisci l'arnia headless minima (tests/harness): un runner che può far girare
   il motore SENZA Textual e SENZA rete — un "adattatore nullo" che raccoglie gli
   eventi di dominio emessi e permette di iniettare intenti scriptati, più un punto
   d'aggancio per un provider fake (lo riempiremo dopo). Per ora basta lo scheletro
   con un test fumo che parte e si chiude pulito.
4. Configura pytest con isolamento del contesto esper: una fixture che in setup fa
   switch_world su un nome di test e in teardown switcha al default e poi
   delete_world. Scrivi due test che, eseguiti in sequenza, dimostrano che lo stato
   NON trapela tra l'uno e l'altro.
5. Lockfile delle dipendenze (per ora solo Pydantic + Textual placeholder, pinnati
   esatti). Niente range aperti.

NON costruire ancora logica di gioco, contracts veri, né UI. Solo fondamenta + arnia.
Al termine elenca cosa hai creato e conferma: grep `esper.World(` vuoto, i due test
di isolamento verdi, il test fumo dell'arnia verde.
```

**Criteri:** isolamento contesto (ESP §0.1), embrione di C-5. **Stima:** M · 1–2 sessioni.

---

### Fase 1 — `contracts`: DTO, bus tipizzato, schema F, interfaccia provider

**Obiettivo.** Il vocabolario condiviso, dependency-free, su cui tutto si aggancia. **Dipende da:** 0. **Documenti:** ESP §5; IC §2–§2.3; F §2–§3, §10 (F-1…F-7, F-12, F-14); PLK §2.

```
Leggi docs/esper-implementazione.md (§5, bus tipizzato), docs/interfaccia-contratto.md
(§2), docs/contratto-ai-motore.md (§2, §3, §10) e docs/provider-llm-key.md (§2).

Compito, tutto dentro src/contracts (ZERO dipendenze di progetto: solo stdlib + Pydantic):
1. Bus tipizzato di progetto: ogni evento è una dataclass; sottoscrizione PER TIPO;
   handler tenuti con riferimenti FORTI; registrazione/deregistrazione esplicite.
   NON usare il dispatcher nativo di esper. (ESP §5)
2. Eventi di dominio e intenti come dataclass DTO: almeno EncounterStarted,
   CombatResolved, MortePersonaggio, AnomalyTriggered, DiscesaPiano, e gli intenti
   tipizzati del giocatore (es. PlayerChoseOption). Solo dati semplici: niente
   renderable, niente widget, niente riferimenti al World. (IC §2.2)
3. Schema Pydantic del contratto AI↔motore: TurnoNarrazione { prosa, entità{archetipo,
   rarità, blocchi, nome, descrizione}, opzioni, durata } e Flavor { testo }.
   - EntitaGenerata NON ha campi numerici: niente hp/danno/difesa/durate, niente
     `livello`. (F-3, G-17)
   - Gli enum del catalogo (Archetipo, Rarita, Blocco) sono enum chiusi con valori
     SEGNAPOSTO (i contenuti veri sono di G/Gruppo 2): mettine 2–3 ciascuno.
   - `durata: Durata` è un enum chiuso con ordine totale; sta su TurnoNarrazione,
     NON su Flavor. (F-1, F-14)
4. Interfaccia provider: la firma `genera(prompt, schema) -> candidato | None`. Solo
   la firma/Protocol qui; nessuna implementazione. (PLK §2)

Vincoli da verificare: contracts importa SOLO stdlib + Pydantic (grep: nessun import
di esper/textual/anthropic) — F-2. Nessun campo numerico in EntitaGenerata — F-3.
Nessun campo con cui l'AI possa invocare anomalia o alzare il budget — F-4. Flavor
senza `durata` — F-1.

Scrivi test che verificano F-1, F-3, F-4 e l'import-purity di contracts (F-2).
```

**Criteri:** C-3, C-4 (parziale), F-1, F-2, F-3, F-4, F-14. **Stima:** M · 1 sessione.

---

### Fase 2 — Nucleo ECS: phase-gate, `FaseCorrente`, tre bucket, coda intenti

**Obiettivo.** Lo scheletro in-run su cui montare combattimento e narrazione. **Dipende da:** 1. **Documenti:** ESP §1–§4; FNC §6 (phase-gate, bucket), §6.4 (turno≠orologio); IC §7.1 (coda intenti).

```
Leggi docs/esper-implementazione.md (§1–§4), docs/fasi-narrazione-combattimento.md
(§6, §6.4) e docs/interfaccia-contratto.md (§7.1).

Compito, in src/motore:
1. Componente-singleton FaseCorrente nel World (NARRAZIONE | COMBATTIMENTO),
   serializzabile col save. (FNC §6.1)
2. Base PhasedProcessor: i sistemi dichiarano `fasi_attive` e implementano `run()`;
   il check di fase è NELLA base (legge FaseCorrente), MAI duplicato nei singoli
   sistemi. I sistemi NON sovrascrivono process(). (FNC §6.1)
3. I tre bucket di Processor con priorità deterministica DICHIARATA: sempre-attivo,
   solo-narrazione, solo-combattimento. L'ordine dei sistemi è parte della spec.
4. Coda degli intenti lato motore, drenata UNA volta per turno da un Processor ad
   ALTA priorità all'inizio del giro, nella fase corrente. NON drenata sul tempo di
   parete. I widget (futuri) vi accodano intenti tipizzati. (IC §7.1, C-8)
5. Un "tick" del gioco = una chiamata al giro dei sistemi guidata dal TURNO/azione
   risolta; il dt è simbolico. Nessun timer a frame. (FNC §6.4)

Tutto verificabile nell'arnia headless: inietta intenti scriptati, fai assert sugli
eventi emessi e sull'ordine dei sistemi.

Verifica: nessun check di fase a mano fuori da PhasedProcessor (grep); la coda è
drenata da un Processor sul turno, non da un timer (C-8); un componente con stato ha
un solo sistema che lo avanza (lo dimostreremo con gli status alla fase 3).
```

**Criteri:** C-8, fondamenta di FNC §6/§11. **Stima:** L · 1–2 sessioni.

---

### Fase 3 — Combattimento: loop, iniziativa, IA nemici, status, death-check, mutazione

**Obiettivo.** La fase deterministica completa, seeded, testabile senza LLM. **Dipende da:** 2. **Documenti:** G §2–§6 (loop, status, mutazione, morte), §14 (G-1…G-12, G-24); FNC §2, §9 (determinismo).

```
Leggi docs/combattimento-forma-run.md (§2 loop, §3 terminazione, §4 status+§4.4
cadenza tick, §5 mutazione intra-fase, §6 forma della run/morte) e i criteri §14
(G-1…G-12, G-24). Leggi docs/fasi-narrazione-combattimento.md §2 e §9.

Compito, in src/motore (fase COMBATTIMENTO, bucket solo-combattimento + sempre-attivo):
1. Loop a Action Point scritto `while ap > 0`, con AP max clampato a 1 nell'MVP
   (struttura che regge l'espansione coi talenti dopo). (G-1)
2. Iniziativa derivata da `destrezza`; tiebreak con CHIAVE STABILE seeded (ordine di
   spawn seeded / id di dominio), MAI l'id di entità esper. (G-3)
3. Decisione dei nemici prodotta dal MOTORE, seeded e deterministica (euristiche =
   contenuto/placeholder). NESSUNA chiamata LLM nel percorso di risoluzione. (G-4)
4. Sistema status: un'istanza per TIPO per entità (componente per tipo); riapplicare
   lo stesso tipo => competizione per RANGO (vince il rango alto, rinfresca durata;
   rango ≤ rinfresca ma non diluisce); tipi diversi coesistono e ticcano in parallelo.
   Il componente-status porta `rango: int` COPIATO dall'applicatore all'applicazione,
   senza alcun riferimento alla fonte. (G-6, G-7, G-8)
5. Il tick degli status vive SOLO nel bucket sempre-attivo, un solo proprietario per
   tipo; cadenza in combattimento = per-turno-dell'ENTITÀ (burn-rate invariante al
   numero di nemici). Nessun handler di status nel bucket solo-combattimento. (G-5, G-24)
6. Entità di combattimento EFFIMERE: create su EncounterStarted, distrutte su
   CombatResolved. Il protagonista persiste.
7. Death-check seeded → emette MortePersonaggio (NON CombatResolved(sconfitta)); morte
   ≠ sconfitta; nell'MVP sconfitta → morte. (G-11)
8. Mutazione intra-fase (aggiungere nemici a scontro in corso) SOLO a confine di turno,
   da un sistema a priorità dichiarata, mai durante l'iterazione di un'azione; NON
   ri-emettere EncounterStarted per aggiungere nemici. (G-9, G-10)
9. Placeholder-scheda del protagonista con almeno: destrezza, stato-vita del
   death-check, e i campi che alimenteranno la proiezione DTO. (G-2)

Numeri/contenuti d'economia (Gruppo 2) restano SEGNAPOSTO: non bloccano. Tutto seeded
e testato nell'arnia. Scrivi test per G-1, G-3, G-4, G-5, G-6, G-7, G-8, G-9, G-10,
G-11, G-24.
```

**Criteri:** G-1…G-12, G-24. **Stima:** XL · 2–3 sessioni.

---

### Fase 4 — Narrazione + gate + registry/formula + prove + livello (con provider FAKE)

**Obiettivo.** La fase generativa col gate a tre strati, contro un provider fake deterministico. **Dipende da:** 3. **Documenti:** FNC §5 (flusso narrazione, §5.5 catalogo/budget/anomalia, §5.3 anatomia turno); F §4 (gate a tre strati), §6 (fallimento); G §7 (prove), §8 (livello/DiscesaPiano), §9 (socket generativo); criteri F-5…F-11, G-13…G-22, G-25.

```
Leggi docs/fasi-narrazione-combattimento.md (§5, §5.3, §5.5, §10),
docs/contratto-ai-motore.md (§4 gate a tre strati, §6 fallimento; criteri F-5…F-11),
docs/combattimento-forma-run.md (§7 prove, §8 livello/DiscesaPiano, §9 socket;
criteri G-13…G-22, G-25).

Prima: in src/provider crea un PROVIDER FAKE deterministico che implementa
genera(prompt, schema) restituendo candidati scriptati (e, su richiesta del test, None).
Serve a costruire e testare la narrazione headless senza rete. Stessa interfaccia che
userà il backend reale.

Compito, in src/motore (fase NARRAZIONE):
1. Preparazione del contesto dal motore: tira l'anomalia SEEDED, calcola budget + set
   ammissibile, e INIETTA budget/set ammissibile NEL prompt (soft). (FNC §5.1, §5.5)
2. UNA sola chiamata genera() strutturata per turno di narrazione (mai spezzata in tre);
   i tre ruoli (masterizza/genera/riprende) sono tre CAMPI di una sola risposta. (FNC §5.3)
3. Gate a tre strati NEL MOTORE (mai nella membrana/bus): schema · catalogo · budget;
   lo strato budget è obbligatorio anche sotto grammatica (hard, oltre al soft del
   prompt). (F-5, F-10)
4. Registry (nome→componente ECS) e formula (archetipo,rarità,livello)→statistiche nel
   MOTORE; ogni membro di enum del catalogo ha un binding nel registry (niente nome
   accettabile dal gate ma non istanziabile). Istanzia l'entità validata nel World con
   le stat DERIVATE dal motore. (F-6, FNC §5.5)
5. Fallback del turno di narrazione ATOMICO: sia None (trasporto) sia rifiuto-di-gate
   (dominio) collassano sullo STESSO fallback applicato INSIEME (testo neutro +
   archetipo di default DESIGNATO nel budget + menu fisso). Il fallback è deterministico
   e NON consuma il seed stream. La modalità sola-prosa, invece, può mancare; retry e
   fallback sono selezionati dallo SCHEMA. (F-8, F-9, F-11)
6. Disimpegno ("Scappi" in narrazione) = prova su stat PRIMA di ingaggiare, tirata dal
   motore seeded; se riesce non si apre il combattimento. Distinto dalla fuga DENTRO il
   combattimento. (FNC §5.3)
7. Prove di abilità: l'AI inquadra/veste, il motore TIRA seeded; difficoltà = CLASSE da
   enum chiuso, scelta PRIMA del tiro e immutabile dopo; la soglia la calcola il motore;
   le ancore testuali delle classi vivono nel CATALOGO, non nel componente-prova. (G-14, G-15)
8. Livello = profondità del piano, del motore; avanza SOLO all'attivazione di una
   DiscesaPiano per intento del giocatore; nessun altro evento lo incrementa. Ogni piano
   generato contiene almeno UNA DiscesaPiano raggiungibile; il gate rifiuta/ripara un
   piano senza uscita. (G-16, G-18)
9. Socket generativo: UNA sola firma verso il provider, genera(prompt, schema); nessun
   secondo metodo per tipo di chiamata; prompt e gate nel motore; orchestrazione in una
   coroutine host-agnostica (stdlib, nessun import textual). Una genera in volo
   (fallita/cancellata/in retry) NON scrive sul save. (G-19, G-20, G-22)
10. L'AI riceve la scheda del protagonista SOLO via DTO di proiezione read-only in
    contracts; nessun componente ECS vivo passato al provider/prompt. (G-13)
11. La TurnoNarrazione che emette EncounterStarted è prodotta in NARRAZIONE e il gate
    le clampa la durata a TURNO; nessuna entità di combattimento prima del confine. (G-25)

Tutto headless col provider fake. Test per F-5, F-6, F-8, F-9, F-10, F-11, G-13, G-14,
G-15, G-16, G-18, G-19, G-20, G-22, G-25.
```

**Criteri:** F-5…F-11, G-13…G-22, G-25. **Stima:** XL · 2–3 sessioni.

---

### Fase 5 — Astrazione provider + backend Anthropic reale

**Obiettivo.** Innestare il backend reale dietro la stessa `genera()`, col provider fake che resta per i test. **Dipende da:** 4. **Documenti:** PLK (tutto, in particolare §2–§6); F §5, §6 (mappatura/fallimento), F-12, F-13.

```
Leggi docs/provider-llm-key.md (per intero, specie §2 interfaccia, §3 trasporto vs
dominio, §4 key, §5 output strutturato, §6 fallimento) e docs/contratto-ai-motore.md
(§5, §6; criteri F-12, F-13).

VERIFICA sulla doc API Anthropic ATTUALE il meccanismo nativo di output strutturato:
non andare a memoria. Confina quel meccanismo dentro il backend Anthropic; non deve
comparire in contracts, motore o membrana. (F-12)

Compito, in src/provider:
1. Backend Anthropic che implementa genera(prompt, schema) -> candidato | None. Possiede
   SOLO il trasporto: chiamata API, output strutturato nativo, timeout/retry, pin del
   modello, lettura della KEY da config/env. NON costruisce il prompt, NON valida
   catalogo/budget, NON sceglie il fallback (restano nel motore). (PLK §2, §3)
2. Tre rami di fallimento che convergono su None gestibile dal motore: rete/timeout,
   troncatura (max_tokens; NON "JSON malformato"), refusal (trattato come generazione
   fallita, senza retry). (PLK §6)
3. La KEY non finisce MAI in URL, log, codice o documenti. Letta da config/env. (PLK §4)
4. Selezione dell'implementazione (fake | anthropic) via config, NON una stringa per un
   client generico "OpenAI-compatible". Il fake resta il provider di default nei test.
5. Il replay registra anche i turni andati in fallback (vincolo verso H; qui esponi solo
   l'informazione che H consumerà). (F-13)

Test: con backend fake tutta la suite resta verde; con backend anthropic, un test di
integrazione OPZIONALE (saltato se manca la key) che fa una sola chiamata e verifica
che un candidato conforme allo schema passi il gate. Verifica F-12 (structured output
confinato nel backend), grep: nessun segreto nei log.
```

**Criteri:** F-12, F-13, criteri D di PLK. **Stima:** L · 1–2 sessioni.

---

### Fase 6 — Persistenza: stato + Archivio, identità uuid, atomicità

**Obiettivo.** Il save che è il run-World + l'Archivio degli output validati, con load valida-e-degrada. **Dipende da:** 4 (stato in-run esiste), 5 (cache degli output validati). **Documenti:** H (per intero; criteri H-1…H-22, gate H-L1/H-L2); ESP §0.1 (autorità su `current_world`); F §8 (seam cache/replay).

```
Leggi docs/persistenza-salvataggio.md (per intero; criteri H-1…H-22),
docs/esper-implementazione.md §0.1 e docs/contratto-ai-motore.md §8.

Compito, in src/motore (livello save/load — UNICA autorità su esper.current_world):
1. DUE artefatti separati per file e ciclo vita:
   - Stato (run-World effimero): JSON-family IN CHIARO; entità via
     components_for_entity, singleton (FaseCorrente + contatore di profondità), stato
     d'esplorazione, uuid d'identità, schema_version, model id, MASTER SEED, tag di tipo.
     La TRADUZIONE dato↔formato vive QUI, non nei componenti (dataclass ignare). NESSUN
     id di entità esper come riferimento durevole. (H: stato; ESP §0.1)
   - Archivio degli output validati: sidecar COMPRESSO, autosufficiente e promovibile;
     master seed duplicato nei metadati (sopravvive all'invalidazione). (H: Archivio)
2. Identità del crawler = uuid (NON id esper); i save sono keyati sull'uuid; un solo
   contesto run-World ("run") e un solo run-World vivo. (G-12 lato persistenza)
3. Cadenza a EVENTO/comando (mai a timer); il save scatta SEMPRE prima dello
   switch_world e MAI dentro un process(). (H)
4. Load valida-e-DEGRADA su corruzione/versione (migrazione v→v+1); NON muta
   current_world su fallimento. Scritture ATOMICHE temp+rename + ordine di durabilità +
   backup di sola recovery (coppia coerente stato+sidecar). (H)
5. Indice dei crawler = scan della cartella su intestazione di metadati (no deep-parse).
6. Cache delle stanze = sidecar lasco replay-capace IN FORMA ma non esercitato nell'MVP
   (miss = rigenera). Niente persistenza della chat. (H, F §8)

Test headless: salva → ricarica → lo stato (entità, FaseCorrente, status col rango
copiato, profondità, seed) è identico; un save corrotto degrada senza crash e senza
toccare current_world; temp+rename atomico. Verifica i criteri H applicabili.
```

**Criteri:** H-1…H-22, gate H-L1/H-L2. **Stima:** L · 1–2 sessioni.

---

### Fase 7 — Guscio e ciclo vita: macchina-guscio, tre terminali, cablaggio del save

**Obiettivo.** Il frame attorno alla run e la cucitura run→guscio, con save/invalidazione cablati ai terminali. **Dipende da:** 6 (meccanismo di save), 2 (bus/fasi). **Documenti:** ACV/E (per intero; criteri E-1…E-9); G §6 (morte/vittoria come terminali).

```
Leggi docs/architettura-ciclo-vita.md (per intero; criteri E-1…E-9) e
docs/combattimento-forma-run.md §6.

Compito, in src/guscio (orchestrazione a livello app, coroutine host-agnostica — NON un
World, nessun Processor di guscio):
1. Macchina-guscio: boot → menu/slot → run → (sconfitta | piano-completato | uscita
   volontaria) → menu. Lo stato del guscio NON è serializzato col save della run. (E-3, E-7)
2. Bus di dominio UNO, process-global, costruito al BOOT, fuori da ogni run-World,
   sopravvive ai run-World. Gli handler in-run si deregistrano al teardown. (E-9)
3. Ingresso run = switch_world("run") al confine guscio→run; il protagonista nasce
   (nuova partita, Carl predefinito) o si deserializza (caricamento) ESATTAMENTE lì,
   mai a una transizione di fase. (E-5)
4. Tre terminali, una cucitura: la detection del terminale è IN-RUN (sul bus), ma il
   teardown è nella SHELL — switch_world(default) POI delete_world("run") — dopo che il
   run loop cede il controllo. MAI switch_world dentro un process()/handler in volo.
   (E-4, E-6) Gli esiti di combattimento vittoria/fuga tornano invece a NARRAZIONE
   (bus, in-run): non confonderli coi terminali. (E-8)
5. Cablaggio del save ai terminali: uscita volontaria/menu salvano; morte (6a) E
   vittoria/piano-completato (6b) INVALIDANO. Il save avviene PRIMA dello switch_world.
6. switch_world/delete_world compaiono SOLO in questo modulo, mai in un Processor o
   handler di dominio (grep). (E-2)

Test: nessun switch_world fuori dal guscio (grep, E-2); le due primitive non si
scambiano (E-1); ogni fine-run passa per la stessa cucitura (E-8); un giro completo
boot→nuova partita→morte→menu→carica-altro-slot gira nell'arnia. Verifica E-1…E-9.
```

**Criteri:** E-1…E-9. **Stima:** M · 1 sessione.

---

### Fase 8 — Modello del tempo (J): scorrimento, `Durata`→tick, fast-forward, passa-turno

**Obiettivo.** Lo strato di tempo in esplorazione e la mappa delle durate. **Dipende da:** 3 (tick core/status già costruito in combattimento), 4 (narrazione/cadenza per-stanza), 6 (contatore di tempo-piano serializzato). **Documenti:** J (per intero; criteri J-1…J-17); G §4.4 (cadenza tick), F-14 (campo `durata`).

```
Leggi docs/tempo-modello-scansione.md (per intero; criteri J-1…J-17). Il tick core
condiviso (status → death-check) è GIÀ stato costruito nelle fasi 3–4: qui aggiungi lo
strato di scorrimento e le primitive di tempo.

Compito, in src/motore:
1. Due tempi distinti: SIMULATO (tick seeded) e NARRATO (chiamate AI come lettura del
   simulato, non avanzamento). Il tempo avanza SOLO per tick risolti, mai per orologio. (J)
2. Tick a due strati: il core condiviso (status → death-check) a ogni turno risolto,
   ovunque (anche in combattimento, lì già posseduto da G); lo strato di SCORRIMENTO
   (+ dado-evento + effetto a confine) SOLO fuori combattimento. (J)
3. Cadenza base in esplorazione = per-STANZA (accoppiata al per-turno-entità del
   combattimento → burn-rate dello status invariante alla folla). (J)
4. Mappa Durata→carico-tick nel CATALOGO del motore (non in contracts), con gate
   durata→tick (identità nell'MVP); l'AI dichiara la durata su TurnoNarrazione. (F-14, J)
5. Fast-forward (downtime): solo se SAFE (nessuno status dannoso/unsafe attivo),
   interrotto da morte o evento. (J)
6. Passa-turno: tick manuale token-zero (nessuno status unsafe), tira un DADO-EVENTO
   seeded che può innescare EncounterStarted a confine. (J)
7. Ordine del tick: status → death-check (la MORTE TRONCA il tick) → dado-evento →
   effetto a confine. Asse safe/unsafe degli status = due flag di tipo nel catalogo
   (valenza; risoluzione/unsafe). (J)
8. Contatore di tempo-piano = slot serializzato in H; avanza in entrambe le fasi;
   nessun cap nella 1.0.

Test headless: il burn-rate di uno status sul protagonista è invariante al numero di
nemici (riusa/estendi G-24); la morte tronca il tick ovunque; fast-forward si ferma se
c'è uno status unsafe; passa-turno può innescare un incontro col seed giusto. Verifica
J-1…J-17.
```

**Criteri:** J-1…J-17. **Stima:** L · 1–2 sessioni.

---

### Fase 9 — Adattatore Textual + UI della v1

**Obiettivo.** L'unico strato che importa Textual; rende giocabile a mano ciò che l'arnia testava headless. **Dipende da:** 2–8 (motore completo). **Documenti:** IC §1, §6, §7 (worker, coda, portata v1), §10 (C-1…C-7).

```
Leggi docs/interfaccia-contratto.md (§1 Textual, §6 worker/coroutine, §7 portata v1 +
coda intenti, §10 criteri C-1…C-7).

VERIFICA sulla doc Textual ATTUALE l'API Worker (@work / run_worker / exclusive /
group / cancel): non andare a memoria.

Compito, in src/adattatore (UNICO modulo che importa Textual; importa SOLO contracts +
Textual, MAI esper/World/Processor):
1. Adattatore di presentazione: si sottoscrive agli eventi di dominio e li traduce in
   chiamate Textual; i widget emettono INTENTI tipizzati sulla coda lato motore, mai
   keystroke grezzi e MAI mutano il World né chiamano l'LLM. (C-2b, C-4, C-7)
2. Worker SOTTILE che fa solo `await` della coroutine host-agnostica di orchestrazione
   (quella della fase 4); exclusive per CANCELLARE la chiamata LLM superata quando il
   giocatore va avanti mentre il dungeon "pensa". La logica resta nella coroutine, non
   nel worker. (IC §6, C-6)
3. UI della v1, niente di più (no widget di contorno = creep): scroll della narrazione,
   menù a opzioni discrete, pannello di stato (HP/status/budget), prompt salva/carica.
   Lo snapshot di stato è un input di rendering rimpiazzato in blocco, mai diffato lato
   vista. (IC §7, C-4)
4. La UI NON si blocca mai durante una chiamata LLM in volo. (C-6)

Verifica: il motore non importa Textual (grep, C-2a); l'adattatore non importa
esper/World (grep, C-2b); textual pinnato + lockfile (C-1); C-5 resta verde (l'arnia
headless gira ancora senza Textual). Gioca a mano un incontro completo.
```

**Criteri:** C-1, C-2a, C-2b, C-4, C-6, C-7. **Stima:** L · 2 sessioni.

---

### Fase 10 — Gate di liveness + integrazione della fetta verticale

**Obiettivo.** Dimostrare che la slice è giocabile capo-a-fine: i due gate di release. **Dipende da:** tutte. **Documenti:** G §3, §8.4 (G-L1/G-L2); A (fetta verticale completa); progetto-indice (invarianti).

```
Leggi i criteri di release in docs/combattimento-forma-run.md (G-L1 ogni scontro
termina; G-L2 ogni piano è completabile, §3 e §8.4) e la "Visione in tre righe" + gli
invarianti trasversali in docs/progetto-indice-decisioni.md.

Compito:
1. G-L1 — ogni scontro TERMINA: dimostra la garanzia di fine (verifica (a) dimostrata
   oppure escalation (b) presente). Test che nessuno scontro può ciclare all'infinito.
2. G-L2 — ogni piano è COMPLETABILE: almeno una DiscesaPiano raggiungibile dallo stato
   iniziale; il gate rifiuta/ripara un piano senza uscita. (G-18)
3. Integrazione end-to-end col backend Anthropic reale: boot → nuova partita → esplora
   (narrazione, prove, incontri) → combatti → vittoria/morte → terminale → menu →
   carica. Un piano intero, giocato a mano e in un test d'integrazione scriptato.
4. Passa in rassegna gli invarianti trasversali dell'indice e aggiungi i test/grep
   mancanti che li rendono verificabili (le linee "MAI/SEMPRE").
5. Aggiorna il cruscotto: nodo I → in lavorazione/chiuso secondo lo stato reale.

Questo è il gate del nodo A: senza G-L1 e G-L2 verdi, "giocabile capo-a-fine" non è
vero. Riporta lo stato di OGNI criterio (C-/F-/G-/E-/H-/J- + L1/L2).
```

**Criteri:** G-L1, G-L2, C-5 (finale), tutti gli invarianti. **Stima:** M · 1–2 sessioni.

---

## Parte 2 — Cosa la v1 NON fa (non-goal espliciti)

Dichiararlo è parte del nodo I: tiene l'agente (e te) fuori dallo scope creep. Tutto questo è **fuori** dalla fetta verticale, ed è architettura già predisposta come *slot non esercitato*, non codice da scrivere ora.

- **Nessun secondo backend LLM.** Locale = slot innestabile non implementato; un secondo backend raddoppierebbe i rami di fallback. (D/PLK §9)
- **Nessuna risoluzione del testo libero (`Altro`).** Nell'MVP è gated da disclaimer, mai sopra l'autorità del combattimento. La classificazione "intento→evento tipizzato" è post-MVP. (FNC §5.4/§5.6)
- **Nessuna creazione personaggio meccanica.** Carl predefinito; nessuna scelta con effetto su catalogo/formula. (G §6)
- **Replay riproducibile non esercitato.** La *forma* c'è (seed + cache degli output validati, fallback registrati), ma il replay completo è post-MVP; la cache delle stanze è un sidecar *lasco* (miss = rigenera). (F-13/G-21, H)
- **Nessun "dono" cross-giocatore** (NieR) né **memoria generativa / wiki** né **AI master**. Sentieri aperti a livello di formato/placement, non di contenuto; post-I. (G §13.3, H)
- **Nessun cap né fase di crollo del piano-tempo.** Il contatore avanza, ma niente soglia/crollo nella 1.0. (J, G §13.2)
- **Nessun AP > 1, nessun talento.** Loop scritto `while ap > 0` ma clampato a 1. (G §2)
- **Nessun trasporto/serializzazione della membrana motore↔vista, niente RPC/broker/thread.** Contratto sì, trasporto no; in-process. (IC §8)
- **Contenuti d'economia (Gruppo 2) come segnaposto.** Quali archetipi/rarità/blocchi, formule, tabelle di budget/anomalie, numeri degli status, soglie delle classi di prova: entrano come placeholder e si calibrano dopo l'MVP; **non** bloccano l'implementazione. (G §13.1)
- **Nessuna persistenza della chat**; nessun widget di contorno TUI oltre i quattro della portata v1. (H; IC §7)

---

## Parte 3 — Quadro di stima complessivo

Le stime sono in **sessioni di Claude Code** (un blocco di lavoro focalizzato + la tua revisione, ~1–3 ore). Le stime per il coding agentico sono per natura ruvide: dipendono molto da quanto a fondo revisioni a ogni chiusura di fase. La taglia (S/M/L/XL) indica il rischio/ampiezza più che le ore.

| Fase | Nodo/i | Taglia | Sessioni | Sblocca |
|---|---|:--:|:--:|---|
| 0 Scaffolding + arnia headless | ESP, C-5 | M | 1–2 | tutto |
| 1 `contracts` + bus + schema F | ESP, IC, F, PLK | M | 1 | 2,3,4 |
| 2 Nucleo ECS + phase-gate + coda | ESP, FNC, IC | L | 1–2 | 3,4 |
| 3 Combattimento + status + morte | G, FNC | XL | 2–3 | 7,8,10 |
| 4 Narrazione + gate (provider fake) | FNC, F, G | XL | 2–3 | 5,6,9 |
| 5 Provider Anthropic reale | PLK, F | L | 1–2 | 10 |
| 6 Persistenza (stato + Archivio) | H, ESP, F | L | 1–2 | 7,8 |
| 7 Guscio + terminali + save | E/ACV, G | M | 1 | 10 |
| 8 Modello del tempo | J, G, F | L | 1–2 | 10 |
| 9 Adattatore Textual + UI | IC | L | 2 | 10 |
| 10 Liveness + fetta verticale | G-L1/L2, A | M | 1–2 | release |

**Totale indicativo: ~15–22 sessioni** per la fetta verticale completa. Il percorso critico è 0→1→2→3→4, poi i rami 5/6 convergono su 7/8, e 9/10 chiudono. Le fasi 3 e 4 sono i blocchi più corposi e dove conviene revisionare con più cura.

### Consiglio di metodo per l'autonomia
Puoi lasciare Claude Code procedere autonomamente **dentro una fase** (ha i criteri e l'arnia come recinto), ma **fermati al confine di ogni fase** per revisionare: criteri verdi, niente scope creep, le linee rosse rispettate. È la stessa filosofia del progetto — *l'AI propone, tu disponi* — applicata al build. Un giro di review a fase chiusa costa poco e impedisce alla deriva di accumularsi.
