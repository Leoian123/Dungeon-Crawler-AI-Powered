# STATO DEL PROGETTO — cosa è vero oggi, cosa manca, qual è il prossimo passo

> **Cos'è questo file.** Non è una spec normativa (quelle stanno in `docs/`, vedi
> `progetto-indice-decisioni.md`) e **non è un changelog** (la cronistoria vive nel git
> log e nei messaggi di commit). È il **documento di stato**: descrive il sistema *come
> è adesso* — invarianti che reggono, superfici complete, superfici spente — tiene il
> **registro del debito** in un posto solo, e dichiara **lo step successivo**. Vive alla
> radice del repo ed è versionato (a differenza di `docs/`, in `.gitignore`).
>
> **Come si aggiorna.** Quando un punto si chiude, si **integra** nella sezione a cui
> appartiene (e sparisce dal registro del debito); non si appende una voce di diario.
> Quando emerge un difetto o una decisione da prendere, entra nel registro §4.2 con la
> sua priorità. Ultima revisione: **2026-08-07** — suite **755 verdi + 3 skip**,
> `python -m main` gioca capo-a-fine, due piani pubblicati.
>
> **Divisione del lavoro fra i branch** (decisione dell'utente, 2026-08-04):
> `react-ecosystem` è il **laboratorio** — ci si gioca, ci si vede l'evoluzione, ci vive
> la SPA React e il suo host HTTP. `headless-game-engine` è il **prodotto**: il motore
> di gioco, che qui si porta avanti fino a diventare vendibile. Dal laboratorio al
> prodotto passa **solo il sistema di gioco**, mai la presentazione (regola in §3).

---

## ⚠️ 1. Avviso: il codice diverge dalla documentazione normativa (nodo C / Textual)

La documentazione in `docs/` è **chiusa e validata** sul **nodo C = "rendering con Textual"**:

- `interfaccia-contratto.md` (IC) descrive l'adattatore Textual come il layer di presentazione.
- `progetto-indice-decisioni.md` elenca fra gli **invarianti trasversali**: *«Una sola
  dipendenza viva (Textual), pinnata e marcata»* e *«il motore non importa Textual;
  l'adattatore non importa il World»*.

**Il branch corrente (`headless-game-engine`) diverge da tutto questo di proposito:**
il pacchetto `src/adattatore/` è stato **rimosso** e il game engine è **headless** e
**indipendente da qualunque UI**. La presentazione futura (web, Electron, TUI, …) non è
ancora scelta: si innesterà più avanti, *fuori* dal motore (vedi §4.4).

> **Precisazione, per non far cancellare file vivi a nessuno:** Textual NON è sparito
> dal repo — sopravvive in **due host/tool opt-in** fuori dal motore:
> `src/gioco_textual.py` (la UI di gioco lanciata da `gioca.bat`, vedi §6) e
> `src/calibratore.py` (console admin). Entrambi importano Textual **lazy**, pilotano il
> motore solo via porte/`contracts`, sono testati (`test_gioco_textual.py`,
> `test_calibratore_console.py`) e sono **esentati esplicitamente** dal lint di membrana
> (`_HOST_OPZIONALI` in `test_membrana_vista.py`). "Headless" significa: il MOTORE non
> dipende da alcuna UI — non che nessun file sotto `src/` la tocchi.

### Cosa resta valido e cosa è superato su questo branch

| Principio dei docs | Stato sul branch `headless-game-engine` |
|---|---|
| Membrana motore ⇄ vista via `contracts` (DTO/eventi/intenti) | ✅ **Invariato e rafforzato.** Resta l'unico canale verso un host. |
| Il motore non importa una UI; è host-agnostico | ✅ **Rafforzato.** Nessun modulo di `motore/contracts/guscio/provider` importa una libreria di UI (`test_membrana_vista.py`); sotto `src/` restano solo i due host/tool opt-in esentati. |
| "L'adattatore non importa il World" | ⚪ **Non più applicabile:** non esiste più un adattatore. Il principio sopravvive come *"il motore è pilotabile solo via contracts/porte"*. |
| Textual = unica dipendenza viva, pinnata | ❌ **Superato.** Nessuna libreria di UI fra le dipendenze; resta solo **Pydantic** (+ esper vendorizzato). |
| Worker Textual `exclusive` per la chiamata LLM | ⚪ **Spostato all'host futuro.** La coroutine host-agnostica `prossima_narrazione` resta `await`-abile; chi la schedula lo decide l'host. |

> **Finché i docs non vengono ritoccati, su questo branch vale questo file** per il
> nodo C. Checklist di riallineamento in §5.

---

## 2. Stato dei sistemi

Il pre-MVP è completo e **i due gate di release sono chiusi**: **G-L1** (ogni scontro
termina) verificato sull'intera matrice archetipi × 6 gradi, **G-L2** (ogni piano
completabile) su ogni piano realmente pubblicato. Quello che segue è lo stato per
sistema: cosa regge, con quale lucchetto, e cosa è dichiaratamente spento.

### 2.1 Contratto AI↔motore e pipeline GM

**Il turno di narrazione è una coroutine a stadi** (`motore/gm.py`, `esegui_turno_gm`):
ideazione (consultiva, ≤1, degrado silenzioso) → composizione (**una sola chiamata
gating**, 1 retry max) → inquadramento-prova ≤1 → limatura + distillazione-memoria in
parallelo. Un'unità `await` cancellabile: se cade prima della scrittura, nessuno stato è
mutato; la `guardia_scrittura` protegge dal cambio di World sotto la coroutine sospesa.

- **Gate a 4 strati** (`narrazione.valida_turno`): schema Pydantic → registry archetipi
  (chiusura per-run, congelata nella stagione) → budget (gradi/blocchi/archetipi
  ammessi, con `gradi_per_profondita` che lega la finestra alla discesa) →
  `riferimento` al cast del piano. Ciò che non passa → fallback atomico deterministico
  (prosa neutra + Sagoma indistinta), **mai** stato scritto da output non validato.
- **Firma di turno = chiave d'Archivio** (`firma_turno`, H §8): `seed:piano:stanza:fase`
  (+ tick **e hash SHA-256 del testo dell'azione** per la fase azione — il tick da solo
  non discrimina quando un'azione spende 0 tick). Congela-una-volta-rileggi-sempre: la
  stanza rivisitata e l'azione ripetuta rileggono a **zero chiamate**; la memoria di
  run è **derivata** dall'Archivio, mai persistita come chat (H §11).
- **Economia del tempo**: l'AI propone una `Durata` dal vocabolario chiuso, il
  `gate_beneficio` applica il pavimento della classe di beneficio (§11) e la durata
  **dichiarata dal giocatore** (`parse_durata_dichiarata`, forme esatte con `\b` —
  «2 orecchini» non sono 2 ore); clamp solo verso l'alto, beffa solo sull'arbitraggio.
  I tick li spende il motore (`spendi_tempo` via le API di J); su ingresso in
  combattimento la spesa è 0 (il tempo lo brucia il loop di scontro).
- **Schemi AI-facing snelli**: le docstring dei modelli/enum restano per chi legge il
  codice ma NON viaggiano come `description` nel JSON schema (erano ~40% dell'input di
  ogni chiamata; `TurnoNarrazione` 4.635 → 1.959 char). Meccanismo: `_senza_docstring`
  nella config condivisa + mixin `SchemaSnello` per gli enum (`contracts/schema.py`);
  una descrizione *pensata per l'AI* si dichiara con `Field(description=...)` e si
  registra nel lucchetto (`test_lo_schema_ai_non_trasporta_docstring`).
- **Osservabilità del degrado**: un turno in fallback viene **detto al giocatore**
  (riga ⚠ nella cronaca della TUI) e `ConsumoProvider` (token in/out, cache, refusal,
  errori di trasporto — condiviso fra backend forte e veloce) è stampato **all'uscita**
  dal gioco: trasporto vs generazione si distinguono, l'errore di setup non è più muto.
- **Struttura I/O per il caching**: il prefisso statico viaggia nel canale `sistema`
  byte-identico su ogni chiamata, marcato `cache_control` — oggi **sotto i minimi di
  cache** (vedi debito §4.2-C).

Lucchetti principali: `test_gm_pipeline` (budget chiamate, firma, cache, memoria
derivata), `test_narrazione_gate`, `test_tributo_beneficio` (gate avversariale con
provider "già compromesso"), `test_contracts_schema`, `test_contracts_purity`
(contracts = stdlib+Pydantic e basta).

### 2.2 Combattimento

**Due check, e nessuno dei due è un dado da JRPG**: check 1 = il *se* colpisci (gate
stocastico-ma-seeded a banda, esito pieno/graze/schivata — con la geometria di default
è auto-hit deterministico a zero pescate); check 2 = il *quanto*, deterministico
(`max(1, round(m·(atk−def/100)·mult))`, un solo round, resistenze tipate nel `mult`).

- **La schivata esiste in partita** via contenuto, non via default: `K_EVA` dà la scala,
  l'archetipo `felino` (taglia infima, veste, DEX alta, PV bassi) è l'eccezione che
  entra in banda — due file JSON, zero codice. Guardia gemella: contro un mob ordinario
  le pescate del check 1 sono **zero** (`test_dodger`, RNG-spia).
- **TTK e liveness separati**: G-L1 è «ogni scontro termina», non «Carl vince» — un
  celestiale che uccide È una terminazione (permadeath). La banda TTK 2–8 colpi vale su
  tutti i **6 gradi a parità di `CORREDO_RIFERIMENTO`** (l'equip atteso per grado: in
  assenza di XP **è l'equipaggiamento la progressione**, dichiarata prima che il loot
  esista). Curve separate `K_RANGO_HP=0.7 > K_RANGO_DANNO=0.4` (disuguaglianza imposta
  da test): i gradi alti sono più *duri*, non più *letali*.
- **Fuga a tre corsie** (prova a margine, deterministica — FNC §4): pulita
  (`margine ≥ MARGINE_FUGA_PULITA`) / con colpo d'opportunità di ogni nemico vivo **e
  capace di agire** (lo stordito non colpisce nemmeno qui) / negata (margine < 0, turno
  speso, narrata come fuga negata — non come stordimento). Il colpo d'opportunità passa
  dal check 1 come ogni colpo e **non salva per decreto**: se uccide, è
  `MortePersonaggio`, mai `CombatResolved(fuga=True)` a un cadavere.
- **Status = una tabella** (`SPEC_STATUS`): innato (capacità, trasmessa col colpo che
  connette) vs afflizione (ticka, scade, muove HP); durate e `delta_per_rango` sono
  foglie §11 generate dall'enum `Blocco` — uno status nuovo è una riga, e un membro
  senza foglia è un `KeyError` all'import.
- **Azzardo opt-in, mitigato**: vive solo in `motore/azzardo.py`, dietro consenso
  esplicito della voce di catalogo (senza consenso: zero pescate, percorso
  inesistente). La pescata sostituisce la **magnitudine**, non il risolutore: verso il
  bersaglio passa dal check 1 (il dodger schiva anche i dadi) e dal layer dei tipi;
  la faccia negativa è secca su chi ha tirato (la propria sfortuna non si schiva);
  `def_eff` resta fuori (la pescata rimpiazza `atk−def`, non le si somma uno sconto).
  La **Fortuna** inclina le pescate, con tetto.
- **Economia delle mosse**: il giocatore **sceglie la mossa** (menu dal `Repertorio`
  persistente, canale `mossa_richiesta` gemello della fuga); `Mana` posseduto con
  massimo derivato da Intelligenza; `Ricariche` effimero per-scontro. Il rifiuto non
  spende mai il turno (doppia cintura: porta + degrado ad attacco base).
- **Equip nel risolutore: zero righe.** Difesa e resistenze da gear passano dai canali
  che già esistono (`Modificatori`/`Resistenze`); test statici impongono che
  `combattimento`/`derivate`/`statistiche` non nominino mai l'equip.

Lucchetti principali: `test_ttk` (banda per grado, il lucchetto del feel),
`test_liveness` (G-L1 sulla matrice, G-L2 sui piani pubblicati), `test_fuga_canale`,
`test_azzardo_optin` (5 lucchetti statici contro il fraintendimento «questo è il tiro
del danno»), `test_calibrazione_check1` (property-test su entità vere).

### 2.3 Contenuti e design

**I contenuti sono dato**: archetipi, mob, piani e stagioni sono asset JSON in
`contenuti/` (`contracts/contenuti.py` + `motore/design.py`). L'identità di un
archetipo è uno **slug con chiusura per-run**: il registry viene congelato nella
`StagioneAttiva` al freeze e viaggia col save — le run non vedono le modifiche di
authoring successive.

- **Porta di authoring chiusa**: `design.lint_profilo` + `TETTO_AUTHORING` (banda
  derivata dal catalogo §11) — `pv_base=99999` non passa; alzare deliberatamente la
  scala del gioco allarga la banda da sé. Punto scoperto residuo: il
  `mitigazione_cent` esplicito di `PezzoArmatura` (gli oggetti non hanno ancora un
  canale-asset — arriva col loot).
- **Due piani pubblicati**: la *Falsa Idra* (9 teste, tre archetipi + il dodger) e
  *Sotto il Palco* (il retro del baraccone, 4 mob). La mappa si **rigenera alla
  discesa** (seeded da `master_seed + livello`, mai dall'orologio); il terminale di
  vittoria è condizionato alla stagione congelata, non alla libreria su disco.
- **Tutti i numeri §11 vivono in `motore/calibrazione.py`** (catalogo + override), con
  la console (`calibra.bat`, TUI/CLI/web) come superficie di taratura. I default del
  protagonista (`CARL.*`, `HP_DEFAULT`) arrivano al gioco reale lungo tutta la catena
  (`crea_protagonista` → `nuova_partita` → `SessioneGioco.nuova`): nessun literal nel
  composition root.

### 2.4 Equipaggiamento (forma completa, canale SPENTO)

La forma ADR-1 F1–F3 è atterrata: `ComponenteEquip` come manifest durevole (effetti
sempre **derivati**, rimozione per fonte), un solo enum `SlotEquip` (9 slot + mount),
`coeff_eva` a media pesata con `m_armatura_di` **unico proprietario** della geometria
(cascata manifest → `Corredo` → default, degenerazione esatta bit-per-bit), mosse
concesse con **provenienza** (`mosse_concesse`: sfilare un anello non cancella una
mossa innata né quella del gemello ancora indosso).

**Ma il canale è spento, ed è il punto del prossimo passo (§4.1):** `SistemaEquip` non
è registrato da nessun host, `PlayerEquipaggia/Toglie` non hanno produttori,
`ComponenteEquip` **non è persistente** (lucchettato: si registra il tag *insieme*
all'hook di re-equip di ADR-1 F5, mai prima — il desync manifest-senza-modificatori è
peggio dell'assenza), e `CATALOGO_OGGETTI` (provvisorio e dichiarato, in attesa del
canale-asset del loot) è raggiungibile solo dai test.

### 2.5 Persistenza e ciclo di vita

Due artefatti separati (stato effimero in chiaro + Archivio sidecar compresso),
identità uuid = slot = crawler, invalidazione a fine-run (morte E vittoria: permadeath
H-20). Le **guardie delle fondamenta** reggono: scrittura atomica temp+rename con
backup; rollback completo al load se il payload tradisce la busta (mai un World
parziale attivo); sonda della busta prima del boot (un save illeggibile non costa
nulla); una sola run per processo, rumorosa (registro weakref — anche il turno GM già
in volo cade alla barriera senza scrivere nel World altrui); guardia contro il save a
scontro aperto; `rng_state` davvero serializzato e ripristinato.

- **Il reload non riscrive la storia e non la shifta**: le stanze già narrate rileggono
  l'Archivio; il copione offline riparte dal piano corrente **e dalla prima stanza non
  narrata** (`_fake_da_piani(salta_stanze=...)`) — l'oracolo del test è la run gemella
  senza reload.
- **Versionamento dei save**: `SCHEMA_VERSION` fermo a 1 di proposito — un bump è
  l'identità di un formato, non un esercizio. Il meccanismo di migrazione è **provato
  per iniezione** (8 lucchetti: ordine, cumulatività, rifiuto del futuro, buco nella
  catena, divieto di migrazioni inerti).
- **Confini**: `switch_world`/`delete_world` vivono SOLO nel livello save/load
  (`motore/persistenza/salvataggio.py`); il guscio orchestra il *quando*, mai il
  *come*; phase-gate strutturale (`PhasedProcessor`) e bucket dei sistemi verificati a
  runtime (`run._verifica_bucket`).

### 2.6 Verifica

**755 verdi + 3 skip** (2 = integrazione live Anthropic senza chiave; 1 = lint di
`src/host_web`, che su questo branch non esiste — skip **esplicito**, mai verde per
vacuità). La suite è headless, senza rete, con contesto esper isolato per test
(ESP §0.1). Oltre ai lucchetti citati nei sistemi: membrana e purezza import (con
guardie di non-vuotezza su ogni lint a glob — un path spostato fa rosso, non verde
vuoto), eventi mai muti (`_MAPPA_EVENTI` completa per costruzione), sicurezza chiave
(mai in URL/log/codice, scan del repo), vendor esper senza `World()`.

---

## 3. Mappa dei branch

Remote: **`origin`** → https://github.com/Leoian123/Dungeon-Crawler-AI-Powered.git
(tutti e tre i branch sono pushati su origin.)

```
649fe95  Fetta verticale MVP: fasi 0-7 (scaffolding -> guscio), headless e seeded
   │
5b8bfc7  Aggiungi docs a gitignore ............................ ◀── main
   │
1250879  Implementazione del motore del tempo e di Textual UI .. ◀── v1-textual-implementation
   │
e09f27e  Ritorno a headless: rimozione dell'adattatore Textual
   │
6d4ab35  Backend Anthropic e OpenAI + gestione chiavi API ..... ◀── main
   ├───────────────┐
   │               │
   │           8d37ffa..  React ecosystem: host web + SPA ...... ◀── react-ecosystem  (LABORATORIO)
   │
[travaso del solo sistema di gioco] ......................... ◀── headless-game-engine  ★ ATTUALE (PRODOTTO)
```

| Branch | Contenuto | Ruolo |
|---|---|---|
| **`headless-game-engine`** ★ | Il **motore di gioco** e nient'altro: `contracts` + `motore` + `guscio` + composition root + contenuti + i suoi test. Unica dipendenza viva: **Pydantic**. | **Il prodotto.** È qui che il motore si porta avanti fino a diventare vendibile. |
| `react-ecosystem` | Tutto il motore **+** host HTTP (`src/host_web`, FastAPI) **+** SPA React (`web/`). | **Il laboratorio.** Ci si gioca e si vede l'evoluzione. Il motore che matura qui viene travasato nel prodotto; la presentazione resta. |
| `main` | Allineato a `6d4ab35`. | **Indietro** rispetto a entrambi. Va portato avanti quando il motore è accettato. |
| `v1-textual-implementation` | `main` storico + **UI Textual** (nodo C, fasi 9–10). | **Archivio.** Riferimento se si volesse riesumare una TUI. |

> **La regola del travaso:** dal laboratorio al prodotto passano solo `src/contracts`,
> `src/motore`, `src/guscio`, `src/main.py`, gli strumenti del motore a sole stdlib
> (`banco_nemici.py`, `calibratore_web.py`), gli host opt-in (`gioco_textual.py`,
> `calibratore.py`), `contenuti/` e i test **non** `test_host_web_*`. Non passano mai:
> `src/host_web/`, `web/`, e le dipendenze che si portano dietro. Se un giorno un test
> del motore avesse bisogno di `httpx`, quello è il segnale che qualcosa di host è
> colato dentro. Modello di consegna deciso: **web app** (Steam rimandato); licenza
> **proprietaria** (`LICENSE` + `THIRD-PARTY-NOTICES.md`, su tutti i branch).

---

## 4. Il prossimo passo, il registro del debito, il post-MVP

### 4.1 LO STEP SUCCESSIVO: accendere il ciclo di sostentamento

I gate di release sono chiusi, ma **il gioco consegnato gioca la matrice "nudo"**: il
TTK è tarato a parità di `CORREDO_RIFERIMENTO` e **non esiste alcun canale in partita
per ottenere quel corredo**; il mana speso **non si recupera mai** (`RIPOSA` è solo
contratto); la fuga contro i due mob ORO del piano 2 è deterministicamente impossibile
a DEX base. Combinato: **il piano 2 pubblicato è win-or-die per il personaggio di
partenza.** Nessun singolo pezzo è un bug — insieme sono il divario fra "i gate
passano" e "il gioco è coerente".

> **Misurato in partita (2026-08-07, 40 run automatiche via porte, offline):** quattro
> politiche — combatti-sempre, fuga sotto 12 HP, fuga sotto 20 HP, scappa-sempre —
> su 10 seed ciascuna: **zero vittorie, 40 permadeath**. Combattendo sempre si muore
> al 6° scontro del piano 1 senza vedere la scala; scappando si arriva al piano 2 e
> si muore lì (colpi d'opportunità + fuga negata contro gli ORO). Il budget di danno
> dell'intera run è i 30 HP di partenza, e ogni stanza ne costa 1–5 comunque la
> giochi: la vittoria è oggi **matematicamente irraggiungibile**, non solo difficile. È il lavoro da fare **prima** di qualsiasi taratura
fine dei numeri §11 (tararli sul gioco nudo significherebbe tararli due volte).

Ordine proposto (ogni passo sblocca il successivo):

1. **Riposo vero** — comporre `TipoAzione.RIPOSA` dalla mappa quando è vera (stanza
   senza nemici, nessuno status ostativo), produrre `RiposoConcluso` (la riga di
   cronaca esiste già), recuperare HP/mana da foglie §11, e **collegare il seam
   dell'imboscata** (`componi_imboscata` → `fast_forward`: il dado-evento gira già a
   vuoto, e la console ne promette il rischio). È il pezzo più piccolo e ripaga subito:
   il mana smette di essere una risorsa a esaurimento irreversibile.
2. **Equip acceso** — registrare `SistemaEquip` nel bucket di narrazione, dare un
   produttore a `PlayerEquipaggia/Toglie`, e rendere `ComponenteEquip` persistente
   **insieme** all'hook di re-equip (ADR-1 F5 — il lucchetto che oggi vieta il tag
   esiste esattamente per pretendere questa contemporaneità).
3. **Loot minimo (ADR-2 ridotto)** — un canale-asset per gli oggetti e un drop
   deterministico-seeded alla vittoria, quanto basta perché `CORREDO_RIFERIMENTO` sia
   *raggiungibile* scendendo. `CATALOGO_OGGETTI` diventa la lettura del canale, come
   già dichiarato.
4. **Ri-misura** — win-rate e TTK del piano 2 col personaggio che si sostenta;
   POI la taratura fine dei numeri §11 (che resta l'ultimo miglio dell'MVP).

### 4.2 Registro del debito (unico, in ordine di priorità dentro ogni gruppo)

**A. Coerenza del motore**
- **Doppio proprietario della mutazione HP**: `status._applica_delta_hp` (clampa la
  cura) e `combattimento.infliggi_danno` (sottrazione secca) scrivono lo stesso campo
  con clamp diversi; la logica "dove vivono gli HP" è replicata in quattro funzioni.
- **`SistemaCrollo` muto**: l'escalation infligge danno senza eventi di bus — HP che
  calano senza una riga di cronaca, contro il principio "eventi di colpo".
- **Contratti dormienti senza produttore** (posati prima delle feature, da accendere o
  espungere quando §4.1 decide): `RiposoConcluso`/`RIPOSA`, `PlayerEquipaggia/Toglie`,
  `PlayerTentaProva`, `TiroAzzardo`/`EsitoAzzardo.etichetta`, `SistemaRinforzi`
  registrato ma senza componenti in produzione.
- **`main.py` ~1.620 righe**: il composition root ha assorbito la libreria contenuti.
  Va spaccato in pacchetto (taglio di file, non refactor): `libreria/`, `authoring/`,
  `sessione.py`.

**B. Duplicazioni note** (divergeranno al primo ritocco; da unificare passandoci)
- Nome diegetico degli eventi: `combattimento._nome_pubblico` ≡ `status._nome_diegetico`.
- Nome di uno status: tre convenzioni (`nome_status()`, `cls.__name__.lower()` in due
  moduli) + la tabella participi in `main` — reggono solo finché classe e blocco
  coincidono; nessun test di sincronia.
- La tripla mischia/fuoco/veleno mappata in tre moduli (`calibrazione`, `design`,
  `main`); il menu Combatti/Scappa in tre posti; il clamp dell'indice piano in tre posti.
- `main._collezione` riscandisce e ri-valida l'intera libreria per ogni asset risolto
  (O(P·M) al boot): invisibile oggi, quadratico con una libreria vera.

**C. Economia LLM** (il tally ora è visibile: misurare prima di ottimizzare)
- **Prompt caching di fatto spento**: il prefisso `sistema` (~617 tok) è sotto i minimi
  (Opus 1024 / Haiku 4096) — le 4 chiamate Haiku lo ripagano pieno ogni turno. Leve:
  prefisso ridotto per gli stadi ancillari (limatura/distillazione non hanno bisogno di
  cast/lore per «riscrivi 80 parole») o superamento deliberato della soglia sulla gating.
- **Retry di troncatura identico**: su `max_tokens` si ributta lo stesso prompt con lo
  stesso limite → ritronca quasi certamente; distinguere troncatura da guasto di rete e
  alzare il limite nel retry.
- Fascicolo inviato 3 volte per turno; ideazione chiamata anche al reveal dove la sua
  unica influenza meccanica è impossibile; campo `TurnoNarrazione.opzioni` generato a
  ogni gating e **mai letto** (il menu lo compone la mappa) — da togliere dallo schema.

**D. Test e taratura**
- `test_banco_nemici` è diventato uno **specchio della formula** (ricalcola l'atteso con
  le stesse costanti del motore): ripristinare un oracolo indipendente.
- Helper duplicati fra i file combat (builder di stagione-monomob ×4, `_indice` ×3,
  `_SpiaRng` ×2): estrarli in `tests/combat_helpers.py`.
- **Gate anti-inflazione di classe** (G §7.3): `gm.py` accetta la `ClasseProva` proposta
  senza tetto di coerenza con la profondità. G §7.3 ammette che nell'MVP può bastare
  l'enum chiuso: **scelta consapevole**, da rivedere quando le prove peseranno di più.
- **Taratura fine dei numeri §11** (l'ultimo miglio dell'MVP, DOPO §4.1): costanti del
  check 1, curva HP/TTK, soglia escalation, cap-resistenze, budget/anomalie, soglie
  prove, carichi-tick. I property-test di `test_calibrazione_check1` sono la rete.

### 4.3 Post-MVP dichiarato (forma predisposta, da accendere)
- **Replay deterministico completo** — oggi "solo-formato": i marcatori di fallback non
  vengono popolati (annotazioni F-13/G-21 nell'indice decisioni). Prerequisito del dono NieR.
- **Memoria generativa ("wiki")** — meta-store a livello di guscio; recupero semantico,
  non riproduzione esatta (≠ cache delle stanze).
- **Dono NieR (cross-giocatore)** — alla vittoria, promozione dell'Archivio nello store
  condiviso. Richiede il replay completo.
- **AI master** — compone primitivi chiusi (skill/oggetti/PNG) senza coniare atomi o numeri.
- **Testo libero (`Altro`)** — classificazione "intento → evento tipizzato" su menu chiuso.

### 4.4 Il nodo aperto vero: scegliere la UI (ex-nodo C, riaperto di fatto)
La membrana `contracts` + le porte di `SessioneGioco` (`prossima_narrazione`, `avanza`,
`coda.accoda`, `salva`, `bus`) sono il punto d'innesto: una UI futura (web/Electron/TUI)
consuma gli **stessi DTO** che il driver headless usa oggi. La scelta non blocca §4.1
(che è tutto motore); quando si sceglierà, aggiornare i docs del nodo C (vedi §5).

---

## 5. Disallineamenti docs ↔ codice da sanare (checklist)

Quando si deciderà di consolidare, questi sono i punti dove la documentazione normativa
va ritoccata per rispecchiare la realtà del branch headless:

- [x] **IC / nodo C** — *(banner di divergenza, 2026-06-04)*: rendering "Textual"
      superato; membrana valida (non riscritta).
- [x] **`progetto-indice-decisioni.md`** — *(banner + reword invarianti, 2026-06-04;
      asse d'implementazione aggiornato 2026-08-07)*: gate G-L1/G-L2 chiusi, step
      successivo = ciclo di sostentamento (rimando a questo file §4.1).
- [x] **`CLAUDE.md`** — *(2026-06-04)*: architettura a tre strati senza `adattatore/`.
- [x] **Pipeline GM (2026-07-31)** — estensione di spec conforme a G §9.2–9.3:
      coroutine a stadi, una sola chiamata gating, firma di turno = chiave d'Archivio,
      memoria derivata, combattimento come istanza separata.
- [ ] **Gruppo 2 / gruppo-3 equip** — quando parte §4.1: ADR-1 F5 (persistenza+re-equip)
      e ADR-2 (loot) passano da "rinviato" a "in corso"; aggiornare
      `equipaggiamento-stato-e-forma.md` con la forma F1–F3 già atterrata.
- [ ] **Branch** — decidere il destino di `v1-textual-implementation` (archivio o
      cancellazione) e **portare avanti `main`** quando il branch headless è accettato
      (fast-forward possibile). *(Lasciato all'utente.)*

---

## 6. Comandi utili

```bash
# Giocare con la UI Textual (host opt-in) / calibrare dal browser — launcher a un click
./gioca.bat
./calibra.bat

# Giocare un incontro headless (driver di riferimento)
PYTHONPATH="src;vendor" .venv/Scripts/python.exe -m main   # Windows/PowerShell: usa ; nel PYTHONPATH

# Suite completa (headless, senza rete)
.venv/Scripts/python.exe -m pytest -q

# Integrazione live Anthropic (opzionale): imposta la chiave PRIMA (mai in repo/log/URL)
#   $env:ANTHROPIC_API_KEY = "..."   poi   pytest -q
# A fine sessione di gioco la TUI stampa il consumo LLM (token, cache, guasti):
# se i turni degradano a "Sagoma indistinta", quella riga dice se è trasporto o generazione.
```
