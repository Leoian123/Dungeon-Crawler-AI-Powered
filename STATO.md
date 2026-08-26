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
> sua priorità. Ultima revisione: **2026-08-16** (branch `narrative-system`) — suite
> **1117 verdi + 3 skip**, `python -m main` gioca capo-a-fine sul piano-mondo
> territoriale «Pianoterra dei Morti» (stagione «Nascondino con il Morto»);
> l'authoring AI dei roster (`genera_stagione`) è verificato LIVE (dry-run 8/8
> boss, cache attiva, zero guasti). La vincibilità è MISURABILE (`misura_run.py`,
> §4.1) e — taratura 2026-08-13 — **MISURATA > 0: 3 vittorie su 40** (combatti,
> seed 12/13/27: tutta la spina, nascondino in tana, scala). Le leve: politica
> «pieno prima della porta-boss» nell'harness + `RIPOSO.hp_per_tick` 3 +
> `OGGETTO.MOLT_COSTITUZIONE` 4 + `PROB_DROP` 0.7 + pesi-grado riequilibrati.
> Resta la rifinitura (§4.1).
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
`scena.blocco` + `banco.nemico`.

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
`epitaffio` (permadeath, dai fatti, senza Archivio) restano le porte async che
generano; **quando** un battito è dovuto lo dichiara però il MOTORE, non l'host.
La sequenza fuori-banda (apertura → vestizione del premio → epitaffio) viveva nella
TUI, ricostruita confrontando la fase prima/dopo `avanza()` più un flag di host per
l'epitaffio: il driver headless e `misura_run` non la ricostruivano affatto e
giravano su un gioco **senza prosa di scontro** — e un host nuovo (web) avrebbe
dovuto ricopiarla per non perdere metà della narrazione. Ora il motore segna il
battito dove il fatto accade (`_segna_prosa`) e l'host **drena** una porta sola,
`prossima_prosa() -> ProsaFuoriBanda | None` (`tipo` chiuso = solo registro
tipografico). Proprietà bloccate: un battito si consuma una volta sola, il degrado
lo consuma comunque (un host che drena in ciclo non si impianta su un provider
guasto), la vestizione è dovuta **solo se un drop c'è davvero** (mai una chiamata a
vuoto per scontro vinto), e a run chiusa sopravvive **solo** l'epitaffio — gli altri
decadono senza pagare una chiamata. `misura_run` drena come un host vero: offline
i battiti degradano tutti (baseline bit-per-bit invariata, verificata), con `--live`
la misura esercita e paga anche le tre rotte di scontro (`prose_fuori_banda`
nell'esito). Lucchetti: `test_prosa_fuori_banda` (8, incluso il lint statico che
impedisce all'host di tornare a dedurre la sequenza). Entrambe ricevono la **lore dell'avversario** come
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

**L'economia del rischio è del CHUNK (riscontri playtest 2026-08-12)**: il
dado-imboscata scala con le **minacce della zona** (`minacce_zona` = ostili
vivi + stanze non rivelate non-quiete **scontate** da
`IMBOSCATA.peso_non_rivelate` — §11, default 0.5; round 3: a peso pieno
l'ingresso in zona partiva sopra il riferimento e gli agguati arrivavano a
catena, il nemico potenziale ora pesa meno del nemico vero; `PROB_EFF =
PROB_IMBOSCATA × minacce/IMBOSCATA.minacce_riferimento × fattore-stanza) —
«più nemici ci sono, più è alta la probabilità di imboscata; meno nemici, più
è semplice riposare»: **il riposo in campo si GUADAGNA ripulendo** (e anche
solo RIVELARE abbassa il dado). Le altre chiusure dello stesso
giro: la **ritirata è universale** («Scappi» non dissolve MAI il mob — tu
arretri nell'adiacente, lui resta alla sua stanza, ferite comprese; FNC §5.3
«si dissolve» è SUPERATA: era un room-clear gratuito, la fuga migliore della
vittoria); il **backtracking paga un tick** (la porta salda il debito dopo il
tick di servizio; la stanza nuova paga col solo reveal — mai due volte) e il
marcatore `TurnoAttivo` si AZZERA a fine tick di scorrimento (prima restava
appeso e l'economia del tempo dipendeva dal caso); la voce **«Aspetta»**
(`TipoAzione.PASSA`, il dormiente J §6 acceso): un tick secco, composta quando
lecita — col veleno addosso è l'unica via di downtime (la tenaglia si apre,
insieme al backtracking che ora smaltisce); il **custode battuto garantisce il
drop** (`BOSS.drop_garantito`, §11); «Sei avvelenato!» si annuncia UNA volta
(`applica_status` dichiara se lo status è nuovo — il rinfresco tace).
L'equip che spende il tick è SCELTA (anti-arbitraggio), non un difetto.

**Round 2 (collaudo dei fix, stessa data)**: il **zone-hopping è chiuso** — la
fotografia all'uscita (`StatoTerritorio.stanze_con_vivi`, persistente) registra
le stanze con un ostile VIVO e il rientro rimaterializza SOLO quelle dal seed
del copione (stesso mob): il congedato torna, il morto resta morto (niente
farming di resurrezione). La **ritirata parla** (`DisimpegnoScena.ritirata_in`
→ «Ti ritiri nella stanza N: X resta dov'è») e il menu **dice chi c'è**
(«Combatti — Scheletro del Saloon»: il nome è verità del World). L'**azzardo
racconta l'azzardo**: il dormiente `EsitoAzzardo.etichetta` è acceso — il
risolutore espone la FACCIA pescata, `ColpoInferto.azzardo` la porta, la
cronaca la premette («⚄ Jackpot del Sistema! …»). L'**anomalia si annuncia
solo se MANIFESTA** (grado fuori dalla finestra del contesto: offline il
copione col mob normale non fa più promesse vuote). La **tempra del custode**
(`BOSS.molt_hp`, §11, default 1.5): pool moltiplicato al primo arruolamento
del boss di zona, e dal round 3 **mai sotto il miglior gregario del tier**
(`pavimento_hp_custode`: il molt sull'archetipo gracile non bastava —
12×1.5=18 restava sotto il Fante da 24; il pavimento è derivato con la stessa
formula-madre dei mob veri, dalla tabella di spawn della zona).
L'**imboscata non fa déjà-vu** (il nemico appena ucciso → una ri-pescata
seeded) e lo **snapshot porta l'orologio vivo** (`SnapshotVista.tick` +
descrittore `tN`: mai più il tempo congelato dell'ultimo messaggio GM).

**Round 3 (playtest percezioni, stessa data)**: l'**agguato è cucito alla
prosa** — quando la spesa del tempo di un turno GM innesca l'imboscata,
`spendi_tempo` risale l'entità-incontro (`SpesaTempo.incontro`, plumbing
`RisultatoTick`/`RisultatoFastForward`) e il motore appende al SOLO messaggio
il segnaposto che nomina l'ambusher («Prima che tu possa guardarti intorno,
X ti piomba addosso…» al reveal) — prima si leggeva la prosa del mob di stanza
sopra la barra di un nemico diverso; l'Archivio congela la prosa PULITA (la
rilettura non ripete l'agguato di un tick passato) e la memoria riparte dalla
prosa di stanza. Il **peso delle non rivelate** e il **pavimento del custode**
sono integrati sopra nei loro paragrafi. **«Riposa» a risorse piene non si
compone** (era un «niente» selezionabile): l'opzione è vera solo con HP o mana
sotto il massimo derivato — stessa dottrina «l'opzione compare quando è VERA».
Restano di CONTENUTO (authoring, non codice): l'ampiezza delle tabelle
d'imboscata (déjà-vu residuo su 3-4 nomi), il salto percepito di tier
(distretto coi gregari bronze del quartiere), la faccia della Roulette mai
vista in play. Lucchetti: `test_playtest_fix` (15).

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
  col disimpegno: ritirata; e **torna in scena al rientro in zona** —
  `rimaterializza_custode`, chiamato dalla rilettura del reveal: l'uscita di
  zona lo despawnava e il varco restava chiuso per sempre, scovato da
  `misura_run`), `boss_procedurale` (nome×gimmick×archetipo seeded),
  `pesca_spawn` pesata con fallback di tier. `firma_turno` porta la ZONA
  (chiave legacy byte-identica: niente collisioni d'Archivio fra zone).
- **Tipi di stanza (T1 — «Borderlands della mappa»)**: `TipoStanza` è vocabolario
  chiuso nel contratto (8 tipi: normale, boss, corridoio, bagno, safe_room,
  zona_personale, gilda_tutorial, gilda_skill); la **stampa** è del motore
  (`stampa_tipi`, seeded su stream dedicato `…:tipi` — topologia pubblicata
  byte-identica), a vincoli: partenza/scala mai speciali, boss = stanza del
  custode, SAFE ROOM al più una — **garantita per quota di spina**
  (`STANZE.safe_ogni_zone`, rara e da trovare) o a pescata nei vicoli laterali
  (`STANZE.prob_safe_laterale`: il premio della deviazione) — bagno raro,
  corridoi su stanze connettive. Frequenze = foglie §11 (`STANZE.*`). Il tipo è
  dato del `Piano`, round-trippa nel save (assente = normale: i save storici
  migrano gratis) e al reveal entra nel fascicolo (`[fascicolo/stanza]` con
  glossa diegetica): l'AI lo NARRA, mai lo sceglie. **La QUIETE è meccanica
  (T2)**: safe room e bagno non materializzano mai un mob al reveal (la stanza
  è la scena — pipeline live E copione offline, con istruzione esplicita al GM)
  e il dado-imboscata lì non tira (`stanza_quieta` → fattore 0: il riposo in
  safe room non è interrompibile PER COSTRUZIONE); il corridoio moltiplica il
  dado (`STANZE.molt_imboscata_corridoio`, §11). La pescata del dado avviene
  comunque una volta per tick: lo stream replay-safe non cambia forma col tipo.
  I tipi dormienti sono contratti (registro §4.2-A). Lucchetti:
  `test_tipi_stanza`, `test_stanze_quiete`.
- **Il menu non degrada in silenzio**: `componi_opzioni_scena` decide *cosa il
  giocatore può fare*, e la sua tolleranza al World parziale (gli harness montano
  World senza fase/protagonista/territorio) passava da cinque `except Exception`
  muti — un guasto vero vi si manifestava come «l'opzione non c'era»,
  indistinguibile dal comportamento corretto e invisibile a qualunque test. La
  tolleranza resta (comporre è una LETTURA e non deve esplodere) ma passa da
  `_lettura_tollerante`, che REGISTRA punto + errore + conteggio
  (`degradi_scena()`); il default di un degrado non toglie mai al giocatore
  un'opzione che il gate precedente ha già dichiarato lecita. Lucchetto
  simmetrico: su un World completo il registro è **vuoto**, su uno parziale la
  composizione regge e lascia traccia (`test_scena_degradi`). Nella stessa sede
  l'etichetta delle deviazioni è tornata DIEGETICA: portava `percorso[-1]` fra
  parentesi — «Deviazione: quartiere vicino (0)», una struttura dati stampata al
  giocatore — e ora passa da `insegna_laterale` (vocabolario chiuso segnaposto,
  offset seeded sul genitore × indice del figlio: stabile per zona, **distinta fra
  sorelle** per costruzione, «Deviazione: quartiere dei Neon Spenti»).
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
  run è **derivata** dall'Archivio, mai persistita come chat (H §11). La rilettura di
  un reveal **segna la visita** (`segna_visitata`): al rientro in una zona la mappa
  rinasce con `visitate` vuoto e senza quel segno il cache-hit lasciava il menu vuoto
  per sempre (soft-lock scovato da `misura_run`, lucchetto in `test_misura_run`).
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

**La tassonomia NPC (decisione utente 2026-08-11)**: NPC di combattimento =
`RuoloMob.OSTILE` (spawn/cast); amichevoli = `RuoloMob.PNG`; importanti = i
custodi/boss. La lore è un OBBLIGO DI FORMA: ogni `MobAsset` ha `prosa_stanza`
obbligatoria (nessun mob senza narrazione) e ora porta anche
`aspetto`/`tratto` (l'identità che dialogo e reveal vestono).

**ELITÉ — i contratti sono ATTIVI, la meccanica è futura**: l'Elité è **il PNG
che tutti idolatrano** — il nome dell'ambientazione (i Garrosh/Arthas di questo
mondo). È IDENTITÀ sopra il comportamento (`MobAsset.elite` → `MobAttivo` →
`EntitaMob.elite`, default False: save storici invariati; il ruolo resta PNG).
Contratti imposti per costruzione: **lore piena obbligatoria** (descrizione +
aspetto + tratto: un Elité senza biografia non può esistere come asset); **mai
nei posti-boss** (nessun tier — e mai boss di piano), **mai nelle spawn, mai
nel cast** (l'idolo si incontra, non spawna: vive in libreria, solo canale
PNG); **gate di profondità** — incontrabile dal piano `ELITE.piano_minimo`
(§11, default 3; `materializza_png` rifiuta sotto). Il dialogo annuncia al GM
chi ha davanti (`[png/elite]`: parla da leggenda vivente). **Futuro
dichiarato**: mortalità/scontro con un Elité, apparizioni pilotate dal GM.
Lucchetti: `test_elite` (10).

### 2.1-quater Scene narrative: il canale a BLOCCHI (S1 — pronto, senza pilota)

**La grammatica di Baldur's Gate ridotta all'osso** (decisione utente
2026-08-11): il dialogo scorre a blocchi, **l'AI compone la sequenza, il
motore decide i valori di verità** — il flusso emerge dal prodotto dei due
(stessa famiglia di mob e loot: enum chiusi × arbitro deterministico =
varietà organica). `motore/scena.py`: `IstanzaScena` (partecipanti — lista
dal giorno uno, mai 1-vs-1 cablato — posta opzionale, quattro campi di stato)
+ rotta `scena.blocco` (VELOCE, phase-gated a NARRAZIONE, retry 1) con schema
`BattutaScena` a tre blocchi: `battuta` (prosa), `snodo` (l'AI inquadra
classe+stat dagli enum — il TIRO è del motore: `esito_prova` a margine, riga
del fatto SEMPRE visibile «⚄ prova argento su saggezza: …»), `chiudi`
(proposta d'esito). **I tre gate del motore**: chiusura onesta (`vinta` solo
con snodo superato — mai vittorie a parole; la chiusura illegale degrada a
prosa e la scena continua), anti-pesca (il check fallito è FALLITO: niente
secondo tiro sulla stessa posta), tetto `SCENA.max_battute` (§11: al tetto il
motore chiude d'ufficio sui fatti). Zero mutazioni dall'output LLM; unica
scrittura la memoria INTERAZIONE dai fatti; chiusura → `FattiScena` (gemello
sociale di `FattiScontro`). Il momento-dado per la UI futura è già nel
contratto (`ProvaVista`: classe/stat/esito/margine/grado). **Senza pilota per
scelta** (come fu per i PNG): l'apertura in gioco — menu «Parlamenta» (il
dormiente `PlayerTentaProva` aspetta), ideazione GM (`IntenzioneScena` +
`DIALOGO`), dado-evento — è la decisione S2, insieme al prezzo della posta
sul listino beneficio/tributo e allo sbocco in scontro. Lucchetti:
`test_scena` (11).

**S2 — IL PILOTA È ACCESO (decisioni utente 2026-08-16, implementate lo stesso
giorno)**. Le decisioni a verbale: (1) il divieto del menu (2026-08-10) RESTA la
regola — lo rompono SOLO le categorie interpellabili: **maestro di gilda**,
**manager**, il **narratore AI** (che però parla SENZA possibilità di replica:
mai un dialogo) e categorie future da decidere. Vocabolario chiuso
`CategoriaPng` nel contratto; l'ORDINARIO resta GM-pilotato. (2) I mob OSTILI
parlamentano solo superando un **margine di CARISMA** contro la classe del loro
grado (`classe_da_grado`: parlare con un mob d'oro è una prova d'oro) — carisma
è la PRIMARIA nuova (`StatId.CARISMA`, palese, `CARL.carisma` 8 §11: il crawler
nudo convince il bronzo, dall'argento serve corredo sociale); il tentativo è
**UNO per mob** (`EntitaMob.parlamento_tentato`, persiste nel save: il rifiutato
resta rifiutato) e la riga-fatto del motore non è mai muta. (3) La resa del
personaggio (decisione C): il dato persiste nel backend e VESTE il frontend —
campo **`voce`** su MobAsset→MobAttivo→EntitaMob (cadenza, registro, frasario;
~1-2 frasi: budget token minimo) con **obbligo di forma** per interpellabili ed
Elité (un asset senza voce non esiste), iniettato imperativo nei prompt di
dialogo (`[png/voce]`) e scena (`[scena/png/voce]` via `righe_identita_scena`:
il ponte identità→scena che il rilievo dava per mancante).

Il cablaggio (tutte le mine del rilievo disinnescate): `TipoAzione.PARLAMENTA`
con la sua foglia `DURATA_AZIONE` (niente KeyError all'import); voce di menu
composta quando è VERA (ostile mai tentato — anche accanto a Combatti/Scappi —
o PNG interpellabile in stanza) e ramo ESPLICITO in `_agisci_narrazione` prima
del fall-through (parlare non apre mai uno scontro); porte di sessione
`battuta_parlamento`/`abbandona_parlamento` con barriera post-await;
**l'abbandono ha UN proprietario** (playtest giro 2, 2026-08-16): qualunque
azione di menu a scena aperta — e l'apertura dello scontro d'imboscata —
abbandona la scena PRIMA di agire, così `fase=combattimento` e
`scena_aperta=True` non convivono mai nello snapshot (la barriera dentro
`battuta_parlamento` resta come cintura sui flip fuori banda);
**`scena_aperta` nello `SnapshotVista`** (la convenzione «menu
vuoto ⇒ turno GM» è sospesa a scena aperta: l'host raccoglie battute); OFFLINE
la scena si chiude d'ufficio al secondo battito muto (mai 12 righe identiche);
`FattiScena` entra nel **fascicolo del turno GM successivo**
(`[fascicolo/esito-scena]`: il vicolo cieco è chiuso); **il rifiuto al gate
non è invisibile** (playtest giro 3, 2026-08-16 — il gate non apre scena e
non lasciava nulla): doppio canale — la riga-fatto va al fascicolo del turno
successivo (`[fascicolo/rifiuto-parlamento]`, handoff effimero consumato coi
gemelli) e alla memoria INTERAZIONE (`registra_rifiuto_parlamento`, documento
`parlamento-rifiutato-<slug>` durevole quanto `parlamento_tentato`); **la
tregua del parlamentato** (stesso giro): chi ha ASCOLTATO il crawler (gate
superato → `EntitaMob.parlamento_riuscito`, fotografato per zona in
`StatoTerritorio.parlamenti_riusciti` come i tentativi spesi) non lo imbosca —
il compositore d'imboscata esclude i nomi in tregua con un filtro DURO su
tabella di spawn (`pesca_spawn(escludi=…)`) e cast, sagoma di budget in fondo
(l'imboscata resta, cambia l'imboscatore; il rifiutato NON è in tregua); la
TUI ha la modalità scena sull'input dell'azione libera. La scena non spende tempo
né RNG (replay intatto). Il canale PNG è provato **dall'asset** (playtest:
`MobAsset.categoria` è un enum — l'estrazione del `.value` in
`materializza_png` è il fix che rende interpellabile il PNG materializzato da
libreria). Lucchetti: `test_parlamento`
(18, incluse le mine e gli exploit dei playtest come oracoli).
**Piazzatore PNG — P1 FATTO** (2026-08-17, progetto in
`docs/future/piazzatore-png.md`): roster congelato `PianoAttivo.png`
auto-riempito dal risolutore per affinità di tag (categoria ≠ ordinario o
Elité — l'archivista entra nel pianoterra senza authoring); modulo
`motore/piazzatore.py` — pescata SEEDED (`master_seed:png:{piano}:{zona}`),
slot per tipo di stanza (canone DCC: manager nel bagno, maestro nelle gilde,
safe room riservata alla troupe P3), idempotente, un personaggio per nome,
tetto `PNG.per_zona` §11 — agganciato a `rigenera_mappa_zona`; il vincolo
giro-3 (mai un interpellabile dietro un custode) è STRUTTURALE e tenuto DA
DUE LATI: gli slot esistono solo nei tipi quieti/gilda, e — falla F1 dello
stress-test 2026-08-17: le gilde non sono «quiete», il reveal materializzava
un ostile davanti al maestro — la stanza dell'interpellabile è RISERVATA
(`stanza_riservata_al_png`: soppressione dello spawn al reveal identica al
luogo quieto, mai nella stanza-boss). Altre falle chiuse dallo stress: F2 le
chiavi di zona si ripetono tra piani e la discesa non elimina i PNG del
piano lasciato → il sensore e gli slot filtrano per LIVELLO (niente
interpellabili fantasma sul piano nuovo); F3 un personaggio (categoria ≠
ordinario) nel cast/spawn/boss esisterebbe due volte → validator del
risolutore; F4 (playtest in-game 2026-08-17) `stampa_tipi` non stampava MAI
le gilde → il piazzatore era verde nei lucchetti e MORTO in partita (lo slot
del maestro non esisteva, e la lore promette gilde «nei piani 1-3») → foglie
`STANZE.prob_gilda_tutorial` (0.25/zona) + `STANZE.gilda_fino_al_piano` (3),
pescata in CODA allo stream `…:tipi` (stampe storiche byte-identiche a prob
0) e la gilda VINCE sul corridoio (flavor) ma mai su safe/bagno/boss.
Playtest headless del piazzamento (driver, offline): 6 seed su 12 piazzano
l'archivista nelle prime 3 zone; reveal pulito nella sua stanza, menu
«Parlamenta — L'Archivista del Sesto», fascicolo con png+stanza, parlamento
offline che degrada e chiude, PNG mai consumato, memoria scena scritta,
unicità tra zone E tra piani (la gilda del piano 2 resta vuota finché lui è
vivo al piano 1 — la ricorrenza è P3), zero fantasmi. Migliorie incassate: il fascicolo GM non è più cieco sui PNG
(`[fascicolo/png]` + regia interpellabile/pilotato, e al reveal
`[fascicolo/png/scena]` con la `prosa_stanza` finora inutilizzata);
`materializza_png` su archetipo fuori registry = rifiuto dichiarato, mai
KeyError (mina #7 chiusa); gli archetipi del roster entrano nel vocabolario
chiuso della run. Lucchetti: `test_piazzatore` (14, inclusi il giro di zona
completo senza duplicati, la stampa gilda e l'oracolo del playtest: seed 9
piazza l'archivista dal solo seed, senza laboratori).
Fuori dal pilota, dichiarato: prezzo della posta (le scene aprono a posta
vuota), sbocco in scontro, spinta GM/narratore — il §5 del documento li
copre come P2 (agenda come dato che unifica posta e sbocco) e P3 (troupe
ricorrente, respiro post-boss), in attesa delle decisioni §7.

### 2.1-quinquies Wiki del Master: gli appunti persistenti del GM (W1 FATTO)

**Studio in `docs/future/wiki-master.md`** (rev. 3: confutazione utente +
panel avversario macchina, tutte le falle integrate) — **W1 implementato**
in versione da sviluppo, gratuita per costruzione (stdlib+Pydantic, zero
SQLite/embeddings/rete). Gli organi: porta `WikiMaster` e DTO in
`contracts/wiki.py` (contratto per-corsia: motore+lessicale deterministiche,
semantica W3 best-effort-congelata); store file-based `src/wiki_master.py`
(voci per-slug in `wiki/`, API sole scrittrici, revisioni append-only,
gate proposta→approvata STRUTTURALE: l'estrazione vede solo le approvate);
**slice congelata nel save** al freeze (`motore/wiki.py` + terzo artefatto
`<uuid>.wiki.gz` a contratto VITALE — `SliceWikiIlleggibile` al load se
corrotto col marcatore presente; master mutato ≠ run mutata, F-6 per
costruzione); **outbox** `<uuid>.proposte.jsonl` FUORI dalla coppia save
(sopravvive a `invalida`/permadeath, id deterministici anti save-scumming,
taint di regia ereditato, drenata a salva/esci/terminale PRIMA di
invalidare); iniezione: voci costanti nel prefisso (cache intatta), voci
dinamiche in `[fascicolo/wiki]` con regia resa (velato/solo-contesto),
foglia `WIKI.voci_per_turno` §11; primo produttore vivo: il mob memorabile
del reveal diventa proposta. Segretezza: `admin` non esce MAI dal master
(property-test). 4 voci demo in `wiki/`. Lucchetti: `test_wiki_master`
(15). **Playtest approfondito 2026-08-18** (driver in-game): la
verifica-stella regge — nel reveal della gilda di seed 9 il canone
dell'Archivista si innesca dalla CORSIA DI MOTORE (l'entità in scena,
zero keyword digitate) accanto a `[fascicolo/png]`; il turno con la riga
wiki si congela e si rilegge identico dopo il load; il CERCHIO COMPLETO
funziona (reveal → proposta del Fante nell'outbox → consuma → promozione
a voce → la run nuova la vede in slice e la innesca per nome); dedup
reale sotto save-scumming. DUE falle trovate e chiuse: F-W2 le STOPWORD
innescavano tutto («L'Archivista DEL Sesto» matchava «Fante DEL Fronte
Fermo» sull'articolo: il canone scattava su ogni azione → stopword
italiane fuori dalla tokenizzazione, attivazioni da 8/8 a 4/8 pertinenti);
F-W3 lo scan freddo del master costava ~7 ms/voce (1.5 s a 200 voci a
ogni creazione di run) → cache per firma mtime/size (pattern
`_collezione`): estrazione in cache 14 ms, retrieval 1 ms.
**Avversariale di scrittura esterna 2026-08-18** (driver: master mutato
sotto run viva, tampering artefatti, sabotaggio outbox, master avvelenato):
F-6 regge su tutti i fronti — prefisso byte-identico dopo revisione+
approvazione esterna, voce cancellata dal master viva in slice, voce
intrusa fuori dalla run in corso ma dentro la run nuova; tampering del
terzo artefatto a sessione viva INERTE (la run gioca sul World) e
auto-risanato al salvataggio; riga spazzatura nell'outbox saltata senza
perdere le vere. DUE falle chiuse: F-W4 l'outbox inscrivibile (lock/AV/
sabotaggio) faceva esplodere `salva()` DOPO la scrittura del save →
drenaggio best-effort con ri-accodamento (`riaccoda_proposte`, la coda è
persistente: si riconsegna al confine successivo); F-W5 un file del master
con slug interno diverso dal nome creava DOPPIONI in slice → il nome del
file è l'identità, mismatch scartato lasco. Threat model dichiarato nel
doc §3.1: il contratto vitale protegge dalla corruzione, non dal
proprietario (H §10.4, nessun DRM); lucchetti a 17.
**Stress-test 2026-08-18** (driver headless): morte REALE via bus →
il funnel drena l'outbox prima di `invalida`, le proposte sopravvivono e
`salva()` rifiuta post-mortem; scope di piano tagliente (piano_a=3 sparisce
al piano 4, la costante resta); prefisso byte-identico; scan lasco su voce
corrotta; move-on-read del consumo; `elimina_crawler` pulisce tutto. UNA
falla trovata e chiusa: la coppia di backup non era diventata TERNA —
ora `backup_coppia` copia anche la slice (stesso istante, mai
auto-ripristino: il contratto vitale resta un rifiuto dichiarato). Nota di
design a verbale per W2: la SCENA che interpreta un PNG non riceve il
canone wiki (il canone alimenta il turno GM, non `_prompt_scena`) — il
GM sa chi è l'Archivista, la scena che gli dà voce no: candidata
«wiki nella scena» accanto al cruscotto. Restano W2 (indice SQLite
derivato, cruscotto SPA, bundle/export a estrazione, importer lorebook,
wiki-nella-scena) e W3 (corsia semantica, consolidamento offline, vincoli
cablati sulle pescate, scrub) — decisioni §11 del doc pendenti, ratifica
verità-nei-file inclusa (il W1 è già file-based).

### 2.1-sexies Strato sovra-run: esiti, bacheca, daily, fantasmi (A/B/C/D lato motore FATTE)
La direzione «online asincrono» decisa il 2026-08-19: run rigorosamente
single-player, strato sociale sopra — necrologi, seed del giorno, classifiche,
fantasmi come lore. Attraverso il confine viaggiano solo ESITI (piccoli dati),
mai stato di gioco, mai chiamate LLM, mai la chiave. Fase A operativa:
`EsitoRun` (`contracts/esito.py`) depositato da `_onora_permadeath` nel ledger
`esiti.jsonl` (`motore/persistenza/esiti.py` — gemello dell'outbox wiki:
fuori dalla coppia save, sopravvive all'invalidazione, dedup per chiave
deterministica, scrittura best-effort F-W4, lettura tollerante senza
move-on-read). Solo morte/vittoria producono un esito (l'uscita volontaria è
rifiutata dal contratto); `causa`/`momenti` vengono dai fatti dell'epitaffio.
GIRO AVVERSARIALE fatto (2026-08-19, `test_esiti_avversariale.py`): una falla
trovata e chiusa — chiave del dedup portata da (run, terminale) a PER-RUN,
così la «vittoria» di una run resuscitata da copia esterna non affianca la
morte già a ledger (la prima chiusura fa storia). Verificati muti: martello
sulle porte post-terminale, resurrezione esterna (il save ripristinato CARICA
— no-DRM — ma non fa storia due volte), doppia sessione sullo slot, iniezione
JSONL dal nome del crawler, ledger sabotato (file→directory: il ritiro dello
slot non va MAI in ostaggio del ledger, F-W4), ledger forgiato (nessun
percorso di caricamento lo legge: non resuscita e non sporca).
Secondo giro avversariale sulla BACHECA (stesso giorno): 1 crash REALE trovato
e chiuso — `leggi_esiti` su ledger inapribile (directory al suo posto)
buttava giù bacheca() e fantasmi_locali(); ora storia vuota, mai un crash
(byte non-UTF-8 inclusi). Aggiunto il CLAMP dei testi nel contratto
(normalizza whitespace + tronca, mai rifiuta): un newline nel nome non forgia
righe o titoli, una riga da 1 MB rientra a taglia sana, e l'epitaffio del
fantasma — che entra nel PROMPT del GM — arriva sempre come UNA riga corta.
Residuo DICHIARATO fuori scope locale: l'escaping HTML dei post è dell'host
che li renderizza (il contratto porta testo piano), e la falsificazione
diretta del ledger resta no-DRM finché la classifica non è remota (Fase E).
Le fasi B/C/D sono FATTE lato motore (2026-08-19, `test_sovra_run.py`):
- **B bacheca**: il necrologio è una PROIEZIONE del ledger (`motore/
  necrologio.py`, composizione deterministica dai fatti — nessun secondo
  artefatto, zero sync); porta host `bacheca(directory)` in `main`. L'AI un
  domani VESTE nel canale proposta→gate, mai inventa.
- **C daily**: `seed_del_giorno` → `costruisci_sessione(seed=…)`; la verifica
  server-side è `esito.seed == seed_del_giorno(data)` — nessun campo in più.
  Derivazione cablata da test golden: cambiarla romperebbe le classifiche.
- **D fantasmi**: `motore/fantasmi.py` — input ESPLICITO dell'host
  (`fantasmi=` in `nuova`/`costruisci_sessione`, mai un default implicito;
  sorgente locale `fantasmi_locali(directory)` = le sconfitte del ledger),
  congelati nel World come la stagione e PERSISTENTI col save (tag
  `fantasmi`); stanza DERIVATA (sha256 fantasma+master seed, mai un secondo
  stato); unica uscita = riga `[fascicolo/fantasma]` che il GM veste come
  reperto (lore mai stato); consumo a turno SCRITTO (disciplina dei gemelli)
  e il `consumato` attraversa il save — il reload non fa tornare la traccia.
RESTANO fuori dal motore, per i branch/progetti dedicati: la UI della bacheca
(react-ecosystem) e il server classifica (progetto separato, importa solo
`contracts`); Fase E (verifica per replay) solo se le classifiche si fanno serie.

### 2.1-septies Obiettivi e Box (nodo O: O1–O4 FATTE, O5 dichiarata)
Il dungeon ti guarda e commenta (piano ratificato: docs/obiettivi-e-box.md).
Trigger = FATTI del bus tipizzato su vocabolario CHIUSO (mai LLM, mai prosa);
testi = dato autorale ORIGINALE (16 voci in `contenuti/obiettivi/`, registro
dark-comico, nota IP nel piano); ricompense = BOX della fabbrica (conio
ritardato per categoria×grado su stream isolato `master_seed:box:{id}`,
replay-safe) o BEFFA dichiarata — mai vuota e muta. Un solo componente
persistente (`ObiettiviRun`: catalogo congelato per-run + sbloccati +
non-letti + box). Le box si aprono SOLO in SAFE ROOM (ratifica 2026-08-26:
il bagno è privacy, non servizi) via `TipoAzione.APRI_BOX` composto quando è
VERO; la box esce dalla coda solo a conio riuscito. Default-on: ogni
sessione monta il catalogo di sistema (`obiettivi=()` esplicito = run
pulita). Host (O4): notifiche ★ in cronaca tipata, elenco velato-finché-
chiuso (`obiettivi_vista`), arretrate drenate-una-volta al load (§O-5),
tasto `o` in TUI. DISACCOPPIAMENTO ratificato (2026-08-26): obiettivi =
TITOLI per imprese mid-run, mai legati alla vittoria di run (che sarà SOLO
il 18° piano, non ancora configurato — il terminale attuale è segnaposto);
vocabolario esteso coi fatti da impresa su `CombatResolved` (custode,
senza_graffi, grado_nemico fotografati all'apertura) + SERIE a `soglia` con
contatori persistenti; catalogo a 20 voci (4 titoli nuovi). BREAKER
2026-08-26 (giro avversariale giocato): anti-scum delle box regge (esci =
salva-ed-esci; crash-scum inutile, stesso pezzo dallo stream per-box);
chiusi i tre trovati — `custode` ora identifica il custode IN PERSONA fra
gli arruolati (mai la stanza), la garanzia di drop del boss segue lo stesso
fatto (`FattiScontro.custode` — il bancomat per-stanza a minacce vive è
chiuso), e il contratto rifiuta `ripetibile` con box (stampante di loot).
RESTA O5
(cross-run col pattern ledger; «primi al mondo» solo col server); il
travaso al lab della SPA è FATTO (commit a21a38b) — questo arricchimento
andrà travasato al prossimo giro.

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
   `LOOT.PESO_GRADO`, dentro `finestra_gradi_loot`: sul piano-mondo la finestra
   segue il **tier della zona corrente** — `gradi_del_tier`, il bottino insegue
   il territorio — sui piani piatti la profondità) e con `LOOT.PROB_FABBRICA`
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
H-20) — e l'invalidazione è del MOTORE, non dell'host: `_onora_permadeath` ritira lo
slot nel funnel dello snapshot, appena il terminale esiste. **Le TRE vie di
resurrezione trovate dalla caccia avversariale (2026-08-16, tutte chiuse)**:
`salva()` dopo il terminale RICREAVA lo slot ritirato (ora la guardia di
salvataggio onora il permadeath per prima e rifiuta con `RunConclusa` — tipizzata,
l'host la rende); `esci()` dopo la vittoria lo RISALVAVA (il guscio sovrascriveva
il terminale con USCITA_VOLONTARIA e `concludi` prendeva il ramo `salva_run` — ora
`esci_volontariamente` non rinegozia un terminale rilevato, ed `esci()` a run
conclusa delega a `chiudi_terminale`); il **`.bak` di recovery** era caricabile
come slot (`carica_sessione(uuid=f"{uuid}.bak")` componeva il path del backup — ora
`carica_da_disco` rifiuta il mismatch identità intestazione↔file: il .bak protegge
dalla corruzione, mai dal permadeath). Lucchetti: `test_permadeath_slot` (7 —
l'oracolo è sempre l'exploit). Prima il ritiro era appeso
a `chiudi_terminale()`, un atto dell'host: la TUI scriveva «💀 Permadeath, run
terminata», montava «Esci» e non lo chiamava mai — **salva → muori → ricarica
funzionava**, col protagonista di nuovo vivo. Nessun test lo vedeva perché l'unico
chiamante della porta era `misura_run`, che la chiama. Il teardown del World resta
l'atto esplicito dell'host, idempotente. Lucchetto: `test_permadeath_slot` — l'oracolo
è l'**exploit** (si gioca fino alla morte senza che l'host chiuda nulla e si prova a
ricaricare), non l'esistenza della porta. Le **guardie delle fondamenta** reggono: scrittura atomica temp+rename con
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

**1056 verdi + 3 skip** (2 = integrazione live Anthropic senza chiave; 1 = lint di
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
| `react-ecosystem` | Tutto il motore **+** host HTTP (`src/host_web`, FastAPI — serve anche la SPA compilata: `gioca_web.bat` = un click e giochi) **+** SPA React (`web/`: gioco play-by-post con scena/zaino/prosa fuori banda, hub, forum con bacheca sovra-run, GM mode con authoring/calibrazione/cruscotto wiki). | **Il laboratorio.** Ci si gioca e si vede l'evoluzione. Il motore che matura qui viene travasato nel prodotto; la presentazione resta. |
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

### 4.1 LO STEP SUCCESSIVO: la taratura §11 contro il muro della provincia

La **struttura del ciclo di sostentamento è completa e misurata**: riposo in gioco,
equip F5 e loot chiusi (§2.4), **finestra dei drop agganciata al tier di zona**
(`finestra_gradi_loot`/`gradi_del_tier`: sul piano-mondo il bottino insegue il
territorio, non la profondità che resta 1 per tutta la spina — lucchetti in
`test_loot_a_tier`), e la **misura della vincibilità è uno strumento del repo**:
`misura_run.py` (launcher `misura_run.bat`) gioca run automatiche via porte —
offline, seeded, riproducibili run-per-run (`test_misura_run`) — con politiche ×
seed e riporta win-rate, zone, scontri, drop, equip, riposi. La storica «40 run,
zero vittorie» (pre-loot, harness mai versionato) si rilancia oggi con un comando.

> **Misurato il 2026-08-11 (4 politiche × 10 seed, max 600 interazioni, col
> loot a tier): 0 vittorie su 40 — e il muro è nitido.** La run migliore
> (fuga-sotto-12, seed 9) vince **40 scontri**, raccoglie 25 drop, indossa 14
> pezzi, riposa 31 volte, attraversa 3 zone — e muore in **provincia (tier 4)**
> come ogni altra politica che progredisce: nessuna run supera le 3 zone.
> `scappa-sempre` non avanza mai (i boss-gate esigono la vittoria: corretto per
> design). Il sostentamento, la ritirata e il riposo FUNZIONANO tutti: quello
> che resta non è struttura, sono i **numeri** — curve `K_RANGO_HP/DANNO` ai
> gradi alti, recupero del riposo, `PROB_DROP`/pesi, margine di fuga — cioè
> esattamente la **taratura fine §11**, tarabile da console (`calibra.bat`)
> senza toccare codice, con `misura_run.bat` come oracolo del prima/dopo.
> (Nota di lettura: `test_corredo_di_riferimento_raggiungibile` verifica la
> filiera in vitro con `PROB_DROP=1` — la vincibilità in partita la dice solo
> questa misura.)

La fetta «tipi di stanza» è ATTERRATA (T1+T2, §2.1-bis: tarare prima della safe
room avrebbe significato tarare due volte) e la ri-misura post-T2 dice che il
muro ARRETRA: la run migliore (combatti/seed 7) batte 4 custodi — quartiere,
distretto, città e PROVINCIA — e cade nel paese (tier 5) con 30 scontri vinti,
15 drop e 18 riposi; fuga-sotto-12 tiene le medie migliori mai misurate (20.9
scontri, 11.7 drop per run). Ancora 0/40: il gap residuo non è più struttura.

> **La vittoria attesa non passa dal celestiale.** Il punto della run è
> raggiungere la SCALA: si battono i custodi fino al paese (leggendario), poi
> nella tana si gioca il nascondino — il cammino che EVITA il Lich esiste per
> lucchetto (BFS, GL-2). Le politiche di `misura_run` lo giocano: nella tana la
> stanza-boss non si imbocca mai e davanti al custode della tana qualunque
> politica arretra (`test_la_politica_gioca_il_nascondino`) — così, quando la
> taratura sbloccherà il paese, la misura proverà la vittoria FURTIVA, non un
> suicidio contro il celestiale.

**Il win-rate è > 0 (taratura 2026-08-13, leve in ordine, misurate una alla
volta su 40 seed di `combatti`)**: la prima vittoria l'ha portata la POLITICA,
non il gioco — l'harness entrava dal custode «quando capita», anche ferito; la
clausola «davanti alla stanza-boss nota fai il pieno, poi entra di proposito»
(`_porta_del_boss` + tie-break Costituzione nella vestizione greedy, lucchetti
in `test_misura_run`) misura il gioco che esiste davvero e da sola vale 0→1/40.
Da lì lo STACK misurato, ora default §11: `RIPOSO.hp_per_tick` 2→3 (feel:
neutro sulla misura, le morti sono in scontro, non da logoramento fra riposi);
`OGGETTO.MOLT_COSTITUZIONE` (foglia NUOVA, 4): il modificatore COSTITUZIONE da
oggetto vale fascia × rango × molt — il corredo porta HP oltre che armor (con
la Piastra: Carl 30→46 max), le stat d'attacco restano sulla scala di sempre;
`PROB_DROP` 0.5→0.7 e `LOOT.PESO_GRADO` 3/4/4/3/1/1 (era 6/4/3/2/1/1): il
corredo argento/oro arriva QUANDO i custodi lo esigono. Le tre componenti
compongono e nessuna basta da sola (drop da solo 1/40, drop+molt senza pesi
1/40, stack completo **3/40** — seed 12/13/27 vincono l'intera spina con
vittoria FURTIVA in tana, 5 zone, ~20 riposi). Il ramo «`CARL.hp` che cresce
col piano» è ESCLUSO dai dati: la spina resta a profondità 1, il muro è dentro
il piano 1 — la progressione è l'equip, come da design.

**Nodo B (2026-08-26, bilanciamento oggetti dal dataset di riferimento —
piano in docs/bilanciamento-oggetti.md, modello estratto da docs/Fine Tuning
Oggetti, curve e regole MAI nomi: la nota IP vale anche qui).** Due leve
strutturali, misurate in stack:
- **B1, la review-armi**: il layer impugnato è SVEGLIO — `atk_eff` somma il
  `danno_base` dell'arma indossata (i mob senza manifest non si muovono:
  il loro scaling resta `K_RANGO_DANNO`); la curva `OGGETTO.DANNO_ARMA.*` è
  convessa, derivata da `K_RANGO_HP` (2/3/5/6/8/9): l'offesa da equip insegue
  i pool come la difesa già faceva. Era la radice del muro provincia/paese
  misurato dal power-play del 2026-08-26.
- **B2, la qualità del conio**: il ventaglio DENTRO il grado
  (scarto/onesto/pregiato, vocabolario motore, mai AI-facing) pescato in coda
  allo stream (i draw storici non si spostano) con pesi §11 per grado derivati
  dal dataset (`LOOT.QUALITA.*`); scarto = zero affissi + arma un grado sotto
  (il junk di consolazione dei tier bassi), pregiato = un affisso in più +
  arma un grado sopra (la sovrapposizione fra gradi del riferimento);
  `qualita` sull'`OggettoAttivo`, default onesto = save vecchi intatti.
Misura di chiusura (stessa `misura_run`, 40 seed): **combatti 3/40 → 7/40,
fuga20 11/40 (28%)** — la spina intera + discesa (prof. 2) è un esito
regolare, non un colpo di fortuna; `scappa` resta 0/40 (vincere richiede
combattere). Restano da ratificare (§B del piano): scaling per piano delle
box, moltiplicatore benefactor, canale consumabili (dichiarato, non
progettato), qualità nel nome/vista.

Il passo ora è la RIFINITURA: il giocatore vero sceglie gli scontri e usa i
vicoli — le run manuali arrivano più in là della politica; leve residue in
canna: `K_RANGO_DANNO` 0.4→0.3 (con `test_ttk` come rete), fasce del canale
mosse, margine di fuga. Tutte da console (`calibra.bat`) con `misura_run.bat`
come oracolo del prima/dopo.

Più avanti, sull'asse mappa: la **generazione a chunk «stile sudoku»** (zone
enormi per costruzione lazy: griglia di chunk seeded per cella, vincoli di zona
risolti come quote per chunk al freeze — la garanzia c'è senza generare nulla;
alla scala chunk la quota safe torna PER ZONA). Costi noti: refactor della
`Mappa`, chunk nella firma di turno, lucchetti di attraversabilità per chunk.

### 4.2 Registro del debito (unico, in ordine di priorità dentro ogni gruppo)

**A. Coerenza del motore**
- ~~Doppio proprietario della mutazione HP~~ **CHIUSO (2026-08-16)**: la mutazione
  vive in `motore/salute.py` (`muovi_hp`: cura clampata al massimo derivato, danno
  secco — il death-check legge `<= 0` e il margine negativo è informazione);
  status/combattimento/riposo delegano. Le copie erano CINQUE, non quattro
  (`combattimento._hp_di`, scovata dal lucchetto). Lucchetto statico:
  `test_sincronia_nomi.test_gli_hp_hanno_un_solo_proprietario_di_mutazione` — una
  scrittura diretta di `punti_vita`/`attuali` fuori da salute/derivate è un rosso.
- ~~`SistemaCrollo` muto~~ **GIÀ CHIUSO** (il registro era indietro): l'escalation
  pubblica `CrolloDungeon` dal giro 2026-08-07; senza bus (harness) resta muta per
  scelta dichiarata nel costruttore.
- **Contratti dormienti senza produttore** (posati prima delle feature, da accendere o
  espungere quando §4.1 decide): `RiposoConcluso`/`RIPOSA`, `PlayerEquipaggia/Toglie`,
  `PlayerTentaProva`, `TiroAzzardo`/`EsitoAzzardo.etichetta`, `SistemaRinforzi`
  registrato ma senza componenti in produzione; i **tipi di stanza dormienti**
  (decisione utente 2026-08-11, regola d'oro: contratto ora, meccanica col sistema
  proprietario): `BAGNO` → sponsor system, `ZONA_PERSONALE` → economia (dal 4°
  piano), `GILDA_TUTORIAL`/`GILDA_SKILL` → sistema skill + piazzamento garantito
  (la gilda tutorial sarà la prima utenza del canale PNG, GM-pilotata).
- **`main.py` ~2.200 righe**: il composition root ha assorbito la libreria contenuti.
  Va spaccato in pacchetto (taglio di file, non refactor): `libreria/`, `authoring/`,
  `sessione.py`.

**B. Duplicazioni note**
- ~~Nome diegetico degli eventi~~ **CHIUSO (2026-08-16)**: copia unica
  `mob.nome_diegetico` (modulo foglia, import pigro di `Protagonista`);
  `_nome_pubblico`/`_nome_diegetico` delegano. Lucchetto statico in
  `test_sincronia_nomi` (il segno della ricopia è `em.nome` nel modulo).
- ~~Nome di uno status senza test di sincronia~~ **CHIUSO (2026-08-16)**:
  `test_sincronia_nomi` lega le tre convenzioni (`nome_status()` ≡
  `cls.__name__.lower()` per ogni riga di `SPEC_STATUS`; la tabella participi di
  `main` deve coprire ogni status con sistema — uno status nuovo senza participio
  è un rosso, non un «Sei veleno_nero!» a video).
- ~~`main._collezione` O(P·M)~~ **CHIUSO (2026-08-16)**: cache keyed sui metadati
  dei file (nome, mtime_ns, size) — l'authoring che scrive invalida da sé, lo scan
  dei metadati resta, sparisce il ri-parse Pydantic per chiamata.
- Restano (da unificare passandoci): la tripla mischia/fuoco/veleno in tre moduli;
  il menu Combatti/Scappa in tre posti (attenuato: `misura_run` sceglie ormai per
  `TipoAzione`, non per etichetta); il clamp dell'indice piano in tre posti.

**C. Economia LLM** (caching attivo, retry di troncatura a limite crescente,
`opzioni` rimosso, ideazione solo sui turni-azione, prompt ancillari sfoltiti —
tutto in §2.1; il caching in AUTHORING è misurato live: `cache_letti > 0`, §2.1-bis)
- **Misura live della sessione di GIOCO mancante**: la baseline `ConsumoProvider`
  di una run reale non è ancora registrata (attesa ~35-45% in meno per sessione)
  — serve una sessione di gioco con chiave.
- ~~Il tally per rotta non mostrato~~ **CHIUSO (2026-08-16)** — e la verità era
  peggiore del registro: per un provider nudo `avvolgi` creava un engine fresco a
  OGNI chiamata, quindi il tally nasceva e moriva nel giro di un turno (non era
  «non mostrato»: non esisteva). Ora l'engine è memoizzato per identità di
  provider sulla sessione (`_engine`), i turni GM ci passano, la porta
  `tally_rotte()` lo espone e la TUI lo stampa all'uscita, rotta per rotta con i
  degradi.

**C-bis. Il ciclo di gioco è più povero dei sistemi che lo servono** (misurato
giocando, 2026-08-15 — non dedotto dai doc)
- ~~Il verbo «parla» non esiste in partita~~ **PILOTA ACCESO (2026-08-16)**:
  Parlamenta con gate di carisma sui mob ostili e categorie interpellabili
  (dettaglio in §2.1-quater). Restano di S2-pieno: prezzo della posta, sbocco
  in scontro, piazzamento PNG in stanza, spinta narratore. Il testo storico:
  **Il verbo «parla» non esisteva in partita.** `motore/png.py` e `motore/scena.py`
  hanno **zero chiamanti in produzione** (compaiono solo come re-export in
  `motore/__init__.py`); la rotta `scena.blocco` è dichiarata e mai eseguita. È
  la scelta dichiarata «contratto ora, pilota poi» (§2.1-ter/quater), ma il conto
  del giocatore è questo: entra in stanza, legge un paragrafo, combatte o scappa,
  si muove, riposa. Su un gioco a tema DCC — dove l'interazione con PNG, gilde e
  voce del sistema è metà dell'identità — è il gap di ciclo più grosso.
  Sbloccarlo chiede DUE decisioni, non codice: chi materializza un PNG (il GM
  server-side, §2.1-ter) e il **prezzo della posta** sul listino
  beneficio/tributo. Una scena a `posta=None` è già giocabile senza la seconda.
- **L'azione libera è un costo senza esito possibile.** `esegui_azione` è esplicita:
  «il testo libero NON tocca mai lo stato». La prova esiste solo se l'ideazione
  (consultiva, LLM) inquadra `IntenzioneScena.PROVA`, e il suo esito entra SOLO nel
  prompt di limatura: zero conseguenze meccaniche. Offline l'ideazione degrada, quindi
  la prova non esiste mai e il copione risponde con la prosa della STANZA — misurato:
  «frugo tra le macerie» costa 4 tick e restituisce la descrizione della stanza. Il
  saldo per il giocatore è netto: l'azione libera può solo far male (tempo speso,
  status che tickano, e il turno gated può materializzare un'entità), mai bene. Un
  giocatore razionale non la usa. `PlayerTentaProva` è il contratto dormiente che la
  chiuderebbe — ed è coerente col frame roguelike: un'azione che PUÒ pagare
  (perlustrare, prepararsi, rifornirsi) è una decisione *prima* dello scontro, cioè
  dove il design vuole che stiano le decisioni.
- **`misura_run` non esercita l'azione libera**: il verbo AI-driven è raggiungibile
  solo dalla TUI. La prosa fuori-banda ora la misura la drena (§2.1); l'azione libera
  no — il win-rate resta il win-rate dello scheletro a menu.
- **Una sola run per processo, verificato in esecuzione**: aprire una seconda
  `SessioneGioco` invalida la prima, che non può più né giocare né **salvare** (la
  guardia è rumorosa e corretta — meglio dell'alternativa). È l'invariante che il
  modello di consegna deciso (web app, §3) dovrà affrontare: un processo per
  giocatore, oppure spezzare il legame `switch_world` globale ↔ sessione. Peso su
  disco misurato: ~42 KB di stato all'avvio (la stagione congelata viaggia col save)
  → ~52 KB dopo 575 turni; l'Archivio sidecar cresce solo coi turni GM.
- ~~Il boss procedurale a template unico~~ **ATTENUATO (2026-08-16)**: la
  `prosa_stanza` del custode passa da `_prosa_custode` — cornici a vocabolario
  CHIUSO (6, stile regia-dello-show) pescate seeded dallo stesso stream del boss,
  DOPO nome/gimmick/archetipo: il boss di un save in corso resta identico, cambia
  solo la riga che lo presenta; il gimmick autorato resta il cuore. Il pieno
  «vestito dal GM live» resta il canale già esistente (`[fascicolo/mob-atteso]`).

**C-ter. Reperti della caccia avversariale 2026-08-16** (workflow 6 cacciatori ×
verifica, 22 reperti unici, 8 verificati → 8 confermati → 8 CORRETTI; lucchetti in
`test_caccia_2026_08` + `test_permadeath_slot`). Corretti anche 6 minori sotto il
tetto di verifica (a lettura confermata): exploit del boss-gate via imboscata vinta
nella stanza-boss (si marca battuto solo a stanza vuota), drop live pendente perso
da `esci()`, `clampa_mana` gemello di `clampa_hp` (gate allargato a `_tocca_massimi`),
`scontri_persi` sempre 0 in `misura_run`, HP negativi in `SchedaVista`, doppio
orologio nel pannello. **Restano da verificare/correggere** (dimostrati da sonda dei
cacciatori, non passati dalla verifica avversariale — sonde conservate nello
scratchpad di sessione):
- `FattiScontro` pendenti non persistiti: vinci → salva-ed-esci SUBITO (prima del
  turno di resoconto) → al reload lo scontro non viene mai narrato, niente memoria.
- Turno GM spurio su run conclusa: la TUI chiede una narrazione del piano
  inesistente prima della riga di vittoria.
- Cancellazione del turno GM: il tiro-anomalia consuma lo stream RNG di sessione
  PRIMA del primo await (F-11 formalmente violato sul rng, non sullo stato World).
- Il filo di continuità dopo un load può divergere dall'ultima scena LETTA (le
  riletture da cache muovono il filo vivo ma non l'Archivio).
- Id documento-memoria `mob-p{livello}-s{stanza}` senza la zona: collisione fra
  zone del piano-mondo.
- `conia_procedurale` può coniare due slug identici (stat diverse) nella stessa run.

**C-quater. Caccia-2 sul terreno social (2026-08-16, sera)** — workflow 6
cacciatori × verifica avversariale sulla superficie appena costruita + residui
C-ter. 22 reperti unici, 8 verificati → **8 confermati → 8 CORRETTI** (lucchetti
in `test_caccia2_social`, 7): save legacy col carisma al floor 1 (crawler muto a
vita — riparazione lasca in `_ripara_protagonista`, `setdefault` dal
profilo-base: le stat personalizzate sopravvivono); anti-pesca sociale aggirabile
col giro di zona (la rimaterializzazione dal seed azzerava `parlamento_tentato`
— ora il marker viaggia nella fotografia `StatoTerritorio.parlamenti_spesi`,
riempitivi E custode); TUI in modo-scena dopo un'azione di menu (Invio → panic
Textual — uscita speculare in `_agisci`); chiusura offline al 2° muto senza
memoria (estratta `registra_interazione`, ora con ancore piano/tick);
`_fatti_scena` mai consumato da `prossima_narrazione` (la scena chiusa
ri-narrata a ogni reveal); PNG fantasma cross-zona (ancora `EntitaMob.zona`).

**Residui della caccia-2 (dimostrati, non verificati — il prossimo lotto)**:
il prompt di scena non dice che il mob convinto era OSTILE né la categoria;
doppio Invio rapido sulla battuta (la guardia `_occupato` non copre); snodo di
scena su stat=DIFESA (scala centesimi vs soglie in unità: l'AI che sceglie la
stat decide di fatto l'esito — valutare un vocabolario di stat PROVABILI);
«Parlamenta — Sagoma indistinta» (il fallback compone la voce sul segnaposto e
brucia il tentativo); il calibratore web non mostra CARISMA; e i C-ter storici
che RESISTONO: FattiScontro persi dal salva-esci immediato, turno GM spurio a
run vinta (TUI), RNG consumato pre-await, filo post-load divergente, id memoria
`mob-p{L}-s{S}` senza zona, slug duplicati del conio.

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
- **Strato sovra-run, consumo remoto** (il MOTORE è pronto: A/B/C/D fatte, §2.1-sexies) —
  restano la UI della bacheca sul forum (react-ecosystem, legge `bacheca()`), il
  server-classifica minimale come progetto SEPARATO fuori dal repo (importa solo
  `contracts`; invio esiti best-effort dal ledger), e la E (solo se le classifiche
  diventano serie): verifica anti-cheat per replay — log intenti + rigioco headless
  seeded, il dividendo del determinismo.

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

# Misura della vincibilità (§4.1): politiche × seed, offline, riproducibile
./misura_run.bat


# Giocare un incontro headless (driver di riferimento)
PYTHONPATH="src;vendor" .venv/Scripts/python.exe -m main   # Windows/PowerShell: usa ; nel PYTHONPATH

# Suite completa (headless, senza rete)
.venv/Scripts/python.exe -m pytest -q

# Integrazione live Anthropic (opzionale): imposta la chiave PRIMA (mai in repo/log/URL)
#   $env:ANTHROPIC_API_KEY = "..."   poi   pytest -q
# A fine sessione di gioco la TUI stampa il consumo LLM (token, cache, guasti):
# se i turni degradano a "Sagoma indistinta", quella riga dice se è trasporto o generazione.
```
