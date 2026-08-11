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
> sua priorità. Ultima revisione: **2026-08-10** (branch `narrative-system`) — suite
> **925 verdi + 3 skip**, `python -m main` gioca capo-a-fine sul piano-mondo
> territoriale «Pianoterra dei Morti» (stagione «Nascondino con il Morto»);
> l'authoring AI dei roster (`genera_stagione`) è verificato LIVE (dry-run 8/8
> boss, cache attiva, zero guasti).
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

### 2.1 Contratto AI↔motore, Master-Engine e pipeline GM

**Il Master-Engine è il canale unico delle chiamate AI** (`motore/master/`): ogni
percorso è una **Rotta dichiarata** nel registro (schema, corsia astratta
FORTE/VELOCE, retry, phase-gate per chiamata, flag gating) e il dispatcher la esegue
con tally per rotta (chiamate/degradi). Un percorso nuovo = una riga di registro + un
costruttore di prompt (+ gate/fallback propri se tocca stato), mai una pipeline
nuova. Il binding corsia→modello è del composition root (`provider/root.py`,
iniettato: il motore non importa mai `provider` — lint AST). Due vie di cablaggio:
`scegli_corsie` dà i backend **per corsia** (è la via che fa valere la
`Corsia` dichiarata dalle rotte: la usa l'authoring, con un profilo a timeout
da batch); `scegli_provider` resta la porta storica per-schema degli host di
gioco; `MasterEngine.avvolgi` tiene compatibile qualunque provider nudo.
**Nessuna chiamata AI nel repo bypassa il Master-Engine.** Rotte attive: le 5
della pipeline GM + `scontro.apertura`/`scontro.resoconto`/`scontro.epitaffio` +
`authoring.boss`/`authoring.tabella`/`authoring.spawn` + `png.dialogo` +
`banco.nemico`.

**Il turno di narrazione è una coroutina a stadi** (`motore/gm.py`, `esegui_turno_gm`):
ideazione (consultiva, ≤1, **solo sui turni-azione** — al reveal non gira) →
composizione (**una sola chiamata gating**, 1 retry max, istruzione
**per momento**: reveal cinematografico 250-400 parole / azione asciutta) →
inquadramento-prova ≤1 → limatura **solo sui turni-azione** (rifonde i dati nella
bozza asciutta; al reveal la prosa gated è DEFINITIVA — farla riscrivere alla corsia
veloce degraderebbe il registro del modello forte) + distillazione-memoria.
Il corpo del prompt è il **PROMPT EVENTO canonico** (`PromptEvento`): sezioni nominate
in ordine fisso — contesto (`[fascicolo/*]`) → filo (`[filo/prima]`: la coda della
prosa precedente, derivata da `MemoriaTurni.ultima_prosa` e ricostruita al load) →
guida (`[ideazione]`) → evento (la natura del turno) → compito (`[istruzione]`) —
così ogni scena RIPRENDE dalla precedente invece di ripartire da zero. Sui
piani-mondo il fascicolo del reveal porta anche il **MOB ATTESO della stanza**
(`[fascicolo/mob-atteso]`): la lore AUTORATA del custode (imperativa, col
`riferimento` obbligato) o del riempitivo pescato con lo **stesso seed del
copione offline** (`master_seed:copione:…` — offline e live convergono sullo
stesso mob per stanza) — il GM mette in scena un mob che esiste invece di
re-inventarlo; la riga è dinamica e vive SOLO nel prompt utente, mai nel
prefisso cacheato. Il prefisso
statico porta anche **esemplari originali del registro DCC** (`[esempio/*]` in
`STILE_CINEMA`, few-shot in cache); estratti d'autore, se forniti, entrano dal canale
già esistente `stagione.stile` (righe `[stagione/stile]`, congelate per run). Il turno **post-scontro senza azione** è il
ramo RESOCONTO: una sola chiamata `Flavor` che veste i FATTI deterministici
(`FattiScontro` + momenti salienti raccolti dal bus), zero tick spesi, fallback a
template — niente più entità generate e mai materializzate. Un'unità `await`
cancellabile: se cade prima della scrittura, nessuno stato è mutato; la
`guardia_scrittura` protegge dal cambio di World sotto la coroutine sospesa.

**Lo scontro è narrato ai bordi** (Sit.1/Probl.3): `prosa_apertura_scontro` (trailer
non bloccante: la riga deterministica esce subito, la prosa arriva quando arriva) e
`epitaffio` (permadeath, dai fatti, senza Archivio) sono porte async della sessione;
la TUI le cabla in `_agisci`. Entrambe ricevono la **lore dell'avversario** come
`[scena/nemico]` (descrizione/aspetto/tratto dell'`EntitaMob` ingaggiato, catturati
all'apertura dell'istanza; nell'epitaffio con guardia sul nome — mai lore stantia di
un altro scontro): il prompt non porta più il solo nome. **Nessun click muto**: `IstanzaCombattimento.agisci`
ritorna il motivo di un rifiuto (mossa non pagabile, scelta invalida, scontro
concluso) e la sessione lo espone (`ultimo_rifiuto`, azzerato a ogni `avanza`).
La TUI è **una sola finestra-chat**: narrazione (blocco pieno con
separatore), cronaca meccanica (⚔ gialla) e sistema/flavor (corsivi) scorrono
nello stesso log, distinti dal registro tipografico.

**Memoria narrativa** (porta — decisione "porta ora, vettoriale dopo"):
`contracts/memoria.py` (`DocumentoMemoria` + Protocol `MemoriaNarrativa`, recupero
deterministico per contratto) con `MemoriaSuArchivio` sul sidecar esistente
(persistenza gratis, ricostruzione al load). Alimenta `[fascicolo/memoria-lunga]`
(≤3 voci, solo se rilevanti alla query = azione / nemico dell'esito / **mob atteso
del reveal** — anche il momento in cui un nemico entra in scena ha memoria).
Produttori: il resoconto di scontro (EVENTO); il mob memorabile (PERSONAGGIO, con
`aspetto`/`tratto`) = ORO+/anomalia **o reclutato dal cast** — col `riferimento`
l'id è ancorato allo SLUG (`mob-<slug>`, stabile fra stanze e zone: il boss
ricorrente aggiorna lo stesso documento, e l'istruzione del reveal lo tratta da
RITORNO); il dialogo PNG (INTERAZIONE, `dialogo-<slug>`, scritto dai fatti).

**Il sistema degli incontri è cucito** (Sit.5): `motore/incontri.py` compone
l'imboscata (con territorio: dalla tabella di spawn della zona; altrimenti dal
cast) con RNG isolato `master_seed:imboscata:tick` (replay-safe); `spendi_tempo`
e `riposa` passano il compositore, `RiposoConcluso.interrotto` è valorizzato,
`EncounterStarted.imboscata` distingue la cronaca e la sessione apre l'istanza
anche su un incontro non suo. Nella suite il dado è spento di default
(`conftest`), riacceso dai lucchetti dedicati.

### 2.1-bis Territorio: il piano-mondo procedurale

**La scelta di fondo**: procedurale seeded con ancore autorate — la run
attraversa una **spina campionata** (quartiere→distretto→città→provincia→paese→
tana), ogni zona una mini-mappa (riuso di `genera_topologia`, seed
`master_seed:piano:L:zona:{chiave}`) col suo **boss a custodire il passaggio**;
zone **laterali lazy** (0-2 sorelle seeded per zona di spina, vicoli con ritorno
libero) nascono alla prima entrata. Il miliardo di reclusi è telecronaca nel
fascicolo, mai stato.

- **Modello**: `TierTerritorio` (6 tier ↔ 6 gradi, PER INDICE — `GRADO_DA_TIER`
  con lucchetto di sincronia); `PianoAsset.territorio` (conteggi, roster boss
  nominati per PIANO/PAESE/PROVINCIA/CITTA, tabelle procedurali per
  distretto/quartiere, tabelle di spawn a `Frequenza` categoriale — pesi §11).
  Coerenza PER COSTRUZIONE: grado boss == grado del tier, boss di piano
  esattamente 1, **CELESTIALE riservato a lui** (mai in cast/spawn/anomalia sui
  piani-mondo).
- **Runtime**: `motore/territorio.py` — `spina_del_piano` derivata pura (mai
  persistita), `StatoTerritorio` persistente (zona, boss battuti, zone viste),
  `SistemaAttraversamento` unico proprietario dell'avanzamento (gate:
  stanza-passaggio ∧ boss sconfitto), anti-softlock (il custode non si dissolve
  col disimpegno: ritirata), `boss_procedurale` (nome×gimmick×archetipo seeded),
  `pesca_spawn` pesata con fallback di tier. `firma_turno` porta la ZONA
  (chiave legacy byte-identica: niente collisioni d'Archivio fra zone).
- **Copione offline zona-aware**: `ProviderCopione` COMPUTA il turno dalla zona
  on-demand (stanza-boss → IL custode; ordinaria → riempitivo seeded) — identico
  dopo un load, zero liste precompilate.
- **Contenuto**: stagione-1 = «Nascondino con il Morto», piano
  `pianoterra-dei-morti` (non-morti d'epoca/cult): Il Lich Cinefilo (celestiale),
  Leon della Casa del Male + Evil Ash (paese), La Regina Scaduta e DJ Rigor
  Mortis (segnaposto provincia/città), 6 riempitivi, tabelle a tema. I
  lucchetti girano su stagioni sintetiche (`tests/contenuti_sintetici.py` —
  perimetro: forma, non contenuto).
- **GL-2 a 3 clausole**: spina attraversabile (per seed, con custode per ogni
  zona); battibilità = TTK/G-L1 a corredo del grado (la vincibilità nuda resta
  §4.1); **clausola del nascondino** — nella tana esiste sempre un cammino
  partenza→scala che EVITA il Lich (lucchetto BFS): la tagline è meccanica.
- **`genera_stagione.py`** (authoring AI, **verificato live**): rotte
  `authoring.boss/tabella/spawn` (FORTE, fuori-run, gating=lint), cablate via
  `scegli_corsie` con profilo **da batch** (stesso modello forte del gioco,
  timeout 240s: una risposta da 5 boss con prosa non è un turno). Il contesto
  condiviso (canone few-shot + vocabolari) viaggia nel blocco `sistema=`
  cacheato, byte-identico per tutta la sessione; vietati/feedback/mob-disponibili
  (dinamici) SOLO nel prompt utente. I lotti di un giro partono in parallelo
  (`gather`) con gate seriale post-gather (dedup slug) e **un giro di top-up**
  per i tier sotto quota, col motivo dello scarto nel prompt; ogni scarto resta
  RIPORTATO (umano nel loop), mai fallback-contenuto. Il boss dichiara il TIER,
  mai il grado; `--applica` scrive con gate finale `risolvi_stagione` e ROLLBACK
  completo — il diff git è la promozione. CLI argparse
  (`--provincia/--citta/--stagione/--piano/--sovrascrivi/--fake/--live`),
  launcher `genera_stagione.bat`. Dry-run live: 8/8 boss accettati, 2 tabelle,
  2 spawn, zero guasti, `cache_letti > 0`. **Resta da lanciare a quote piene**
  (10 province, 40 città) per riempire i roster.

- **Gate a 4 strati** (`narrazione.valida_turno`): schema Pydantic → registry archetipi
  (chiusura per-run, congelata nella stagione) → budget (gradi/blocchi/archetipi
  ammessi, con `gradi_per_profondita` che lega la finestra alla discesa) →
  `riferimento` al cast del piano. Ciò che non passa → fallback atomico deterministico
  (prosa neutra + Sagoma indistinta), **mai** stato scritto da output non validato.
  Le regole condivise (catalogo+budget+mosse) vivono in **una sola implementazione**
  (`motivi_fuori_budget`, con motivi leggibili): la riusano `valida_turno`, il
  `gate_boss` dell'authoring e la diagnosi del banco — niente copie che divergono.
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
- **Struttura I/O per il caching — ATTIVA**: prefissi differenziati per stadio
  (`prefisso_gm` pieno su gating/ideazione/prova; `PREFISSO_RIFINITURA` corto su
  limatura/distillazione) e guida `STILE_CINEMA` statica DENTRO il prefisso della
  corsia FORTE, che supera deliberatamente la soglia di cache di Opus (≈1400 token
  > 1024, lucchetto di soglia + byte-identità). Il retry di troncatura del trasporto
  raddoppia `max_tokens` invece di ripetere il limite. `TurnoNarrazione` ha perso il
  campo `opzioni` (write-only: il menu lo compone la mappa) e i prompt ancillari il
  fascicolo intero.

Lucchetti principali: `test_gm_pipeline` (budget chiamate, firma, cache, memoria
derivata, resoconto, soglia di cache), `test_master_engine` (rotte, corsie, guardia
di fase, sincronia retry), `test_narrazione_gate`, `test_tributo_beneficio` (gate
avversariale con provider "già compromesso"), `test_contracts_schema`,
`test_contracts_purity` (contracts = stdlib+Pydantic e basta), `test_provider_root`
(incluso il cablaggio effettivo delle corsie, non la sola dichiarazione),
`test_genera_stagione` (cache/parallelo/top-up), `test_memoria_narrativa`,
`test_nemici_in_gioco` (mob atteso + recupero al reveal), `test_incontri`,
`test_scontro_narrato`.

### 2.1-ter PNG: canale pronto nel motore, pilotaggio GM (spento lato giocatore)

Un PNG è un mob a tutti gli effetti senza ostilità: `EntitaMob.ruolo`
(`RuoloMob.OSTILE|PNG`, default OSTILE — i save precedenti deserializzano
invariati) lo esenta dal **despawn di zona** e dal registro nemici della mappa
(`mappa_da_dict` non lo ricollega a `mob_stanza`: mai menu Combatti, mai varco
chiuso); lo trova `png_in_stanza_corrente()` (scansione ECS, nessun registro
nuovo da persistere). `motore/png.py`: `materializza_png` (stessa
`istanzia_entita` del mob: profilo calibrato, override, mosse) e `dialoga` sulla
rotta `png.dialogo` — **sola prosa** (`Flavor`), phase-gated a NARRAZIONE
(parlare in combattimento è strutturalmente impossibile), degrado deterministico,
**zero mutazioni dall'output LLM**: l'unica scrittura è il documento INTERAZIONE
della memoria, derivato dalla battuta del giocatore. Asset demo:
`contenuti/mob/archivista-del-sesto.json` (tag `png`, non referenziato dal cast:
inerte finché non arruolato).

**Chi lo pilota (decisione utente 2026-08-10): il GM lato server, mai un menu
del giocatore.** Il canale è volutamente senza chiamanti: l'aggancio futuro è la
pipeline GM / l'host web (il GM decide quando un PNG entra in scena e ne conduce
il dialogo; il giocatore al più risponde). Fuori scope dichiarato: spawn
automatico, commercio, quest. Lucchetti: `test_png` (materializzazione,
esenzioni, roundtrip del ruolo, phase-gate, zero-mutazioni, memoria).

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
- **Un piano pubblicato**: *Pianoterra dei Morti* (piano-mondo territoriale,
  §2.1-bis) nella stagione «Nascondino con il Morto». Le mappe sono **per zona**
  (seed `master_seed:piano:L:zona:{chiave}`) sul territorio, e si rigenerano alla
  discesa (seeded, mai dall'orologio) sui piani piatti; il terminale di vittoria è
  condizionato alla stagione congelata, non alla libreria su disco.
- **Tutti i numeri §11 vivono in `motore/calibrazione.py`** (catalogo + override), con
  la console (`calibra.bat`, TUI/CLI/web) come superficie di taratura. I default del
  protagonista (`CARL.*`, `HP_DEFAULT`) arrivano al gioco reale lungo tutta la catena
  (`crea_protagonista` → `nuova_partita` → `SessioneGioco.nuova`): nessun literal nel
  composition root.

### 2.4 Equipaggiamento e loot (filiera COMPLETA: fabbrica → conio → vestizione)

La forma ADR-1 è atterrata **fino a F5**: `ComponenteEquip` come manifest durevole
(effetti sempre **derivati**, rimozione per fonte) che **round-trippa nel save**
con la coppia filtro-di-provenienza (scrittura) + hook `re_equipaggia` +
`clampa_hp` (load) — oracolo save→load→save byte-identico (`test_equip_f5`);
un solo enum `SlotEquip`, `coeff_eva` a media pesata, mosse concesse con
provenienza. Il canale in partita è acceso end-to-end (`SistemaEquip` con gate
di possesso sullo `Zaino`, porte `equipaggia/togli`, menu Zaino in TUI —
`test_canale_equip`).

**Il loot è una FILIERA a tre stadi, un solo assemblatore** (`motore/fabbrica.py`):

1. **Authoring — l'AI suggerisce i componenti**: la `FabbricaAsset`
   (`contenuti/fabbriche/`, basi × famiglie × affissi a FASCE, mai numeri) è
   generabile con `authoring.fabbrica`; una stagione senza fabbrica se la fa
   proporre da sola (`genera_stagione`, bootstrap automatico). In più:
   `authoring.oggetto` per i pezzi curati del pool e le mosse-asset per gli
   accessori che le concedono.
2. **Runtime, il grosso — conio PROCEDURALE** (stile Borderlands, in piccolo):
   a chance vinta (`PROB_DROP`) il motore fissa il GRADO (pesato,
   `LOOT.PESO_GRADO`, finestra della profondità) e con `LOOT.PROB_FABBRICA`
   assembla seeded base × famiglia × affissi (bronzo=liscio, argento+=elemento,
   oro+=doppio tratto; merge per stat con fascia alta, cap 4; nome composto
   «Lama Fumante del Becchino») — deterministico, gratuito, identico offline e
   live, replay che riconia identico (`test_fabbrica`).
3. **Runtime, il raro — PEZZO UNICO AI** (`premi.unico`, gated): col GM live
   l'AI **sceglie i componenti PER NOME** dalle tabelle della fabbrica e firma
   la targhetta — schema minuscolo (5 campi stringa), stesso assemblatore, il
   grado non è nemmeno nel contratto; fallback = conio procedurale (un drop
   non si perde MAI: flush anche in `salva()`). Senza fabbrica resta il conio
   libero (`premi.conio`, `OggettoAutorato` + `gate_conio`) con fallback pool.

A valle: la **vestizione** (`premi.oggetto`, anti-arbitraggio su base/grado/slot)
battezza i drop da pool nel `Guardaroba` persistente e `premi.skill` ribattezza le
mosse concesse (solo parole); i coniati vivono in `OggettiConiati` (persistente) e
si equipaggiano come pezzi di libreria. Il catalogo della run =
storico ∪ pool congelato ∪ coniati (`catalogo_oggetti_correnti`). Il criterio di
sostentamento è falsificabile: `test_corredo_di_riferimento_raggiungibile`.

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

**925 verdi + 3 skip** (2 = integrazione live Anthropic senza chiave; 1 = lint di
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
| **`narrative-system`** ★ | `headless-game-engine` + l'asse AI: Master-Engine (rotte), composition root del provider (corsie), prosa cinematografica + cache, scontro narrato, porta memoria narrativa, incontri/imboscata, **territorio procedurale** («Pianoterra dei Morti»), **authoring AI dei roster** (`genera_stagione`, live-verificato), canale PNG. | **Il branch di lavoro corrente**: la "ciccia" AI del gioco. Confluirà in `headless-game-engine` quando accettato. |
| `headless-game-engine` | Il **motore di gioco** e nient'altro: `contracts` + `motore` + `guscio` + composition root + contenuti + i suoi test. Unica dipendenza viva: **Pydantic**. | **Il prodotto.** È qui che il motore si porta avanti fino a diventare vendibile. |
| `react-ecosystem` | Tutto il motore **+** host HTTP (`src/host_web`, FastAPI) **+** SPA React (`web/`). | **Il laboratorio.** Ci si gioca e si vede l'evoluzione. Il motore che matura qui viene travasato nel prodotto; la presentazione resta. |
| `main` | Allineato a `6d4ab35`. | **Indietro** rispetto a entrambi. Va portato avanti quando il motore è accettato. |
| `v1-textual-implementation` | `main` storico + **UI Textual** (nodo C, fasi 9–10). | **Archivio.** Riferimento se si volesse riesumare una TUI. |

> **La regola del travaso:** dal laboratorio al prodotto passano solo `src/contracts`,
> `src/motore`, `src/guscio`, `src/main.py`, gli strumenti del motore a sole stdlib
> (`banco_nemici.py`, `calibratore_web.py`, `genera_stagione.py`), gli host opt-in (`gioco_textual.py`,
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
per ottenere quel corredo** — la progressione dichiarata (in assenza di XP, l'equip)
non è raggiungibile giocando. Nessun singolo pezzo è un bug — insieme sono il divario
fra "i gate passano" e "il gioco è coerente".

> **Misurato in partita (40 run automatiche via porte, offline, sul contenuto
> pre-territorio):** quattro politiche — combatti-sempre, fuga sotto 12/20 HP,
> scappa-sempre — su 10 seed ciascuna: **zero vittorie, 40 permadeath**. Il budget
> di danno dell'intera run è i 30 HP di partenza e ogni stanza ne costa 1–5
> comunque la giochi: senza sostentamento la vittoria è **matematicamente
> irraggiungibile**, non solo difficile. Il contenuto da allora è cambiato
> (piano-mondo territoriale, riposo acceso) ma il buco strutturale — nessun
> equip/loot in partita — è lo stesso; la ri-misura è il passo 3 qui sotto.
> È il lavoro da fare **prima** di qualsiasi taratura fine dei numeri §11
> (tararli sul gioco nudo significherebbe tararli due volte).

Il **riposo vero** è già in gioco (l'opzione `RIPOSA` è di scena, recupero HP/mana
dalle foglie §11, seam dell'imboscata collegato — vedi §2.1: il mana non è a
esaurimento irreversibile). La **persistenza equip (F5)** e il **loot** sono
CHIUSI e integrati in §2.4: l'equip round-trippa nel save, il drop per grado
esce dalla filiera fabbrica→conio→pool e il corredo di riferimento è
raggiungibile scendendo (test falsificabile). Resta UN passo:

1. **Ri-misura** — win-rate e TTK sul piano-mondo col personaggio che ora si
   sostenta (equip persistente + loot vivo); POI la taratura fine dei numeri
   §11 — incluse le fasce nuove del canale oggetti/mosse (tarabili da console
   senza codice) — che resta l'ultimo miglio dell'MVP.

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
- **`main.py` ~2.200 righe**: il composition root ha assorbito la libreria contenuti.
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

**C. Economia LLM** (caching attivo, retry di troncatura a limite crescente,
`opzioni` rimosso, ideazione solo sui turni-azione, prompt ancillari sfoltiti —
tutto in §2.1; il caching in AUTHORING è misurato live: `cache_letti > 0`, §2.1-bis)
- **Misura live della sessione di GIOCO mancante**: la baseline `ConsumoProvider`
  di una run reale non è ancora registrata (attesa ~35-45% in meno per sessione)
  — serve una sessione di gioco con chiave.
- Il tally per rotta del Master-Engine esiste ma nessun host di gioco lo mostra
  ancora (il riassunto stampa solo il totale `ConsumoProvider`; il banco nemici
  invece il consumo per modello lo stampa già).

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
- **AI master** — compone primitivi chiusi (skill/oggetti/PNG) senza coniare atomi o
  numeri. Il substrato PNG del motore esiste già (§2.1-ter: ruolo, esenzioni, rotta
  dialogo); qui resta la parte GENERATIVA e il pilotaggio GM server-side.
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

# Authoring AI del piano-mondo (dry-run; --applica scrive, il diff git è la promozione)
./genera_stagione.bat

# Giocare un incontro headless (driver di riferimento)
PYTHONPATH="src;vendor" .venv/Scripts/python.exe -m main   # Windows/PowerShell: usa ; nel PYTHONPATH

# Suite completa (headless, senza rete)
.venv/Scripts/python.exe -m pytest -q

# Integrazione live Anthropic (opzionale): imposta la chiave PRIMA (mai in repo/log/URL)
#   $env:ANTHROPIC_API_KEY = "..."   poi   pytest -q
# A fine sessione di gioco la TUI stampa il consumo LLM (token, cache, guasti):
# se i turni degradano a "Sagoma indistinta", quella riga dice se è trasporto o generazione.
```
