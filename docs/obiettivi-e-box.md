# Obiettivi e Box — il piano (nodo O, bozza per ratifica)

Il sistema di achievement dello show: **il dungeon ti guarda e commenta**.
Ogni obiettivo è una notifica di sistema — sarcastica, nel registro
dark-comico dello show — con una ricompensa che spesso è una **Box** (loot
box per categoria e grado) e a volte è una beffa dichiarata. Le box si
aprono **solo nei luoghi quieti**.

> **Nota IP (vincolante).** Il riferimento di meccanica e registro è il
> romanzo; i TESTI del catalogo sono **originali al 100%**: mai righe, nomi
> di obiettivo o battute del libro nel repo. Il registro si imita, il testo
> no. (Rischio IP già a registro in STATO: questo sistema non lo aggrava.)

## Il principio (le linee rosse applicate)

- **Il trigger è un FATTO del motore**: gli obiettivi ascoltano il bus
  tipizzato (mai l'LLM, mai il testo della prosa). Se l'evento non esiste,
  l'obiettivo non esiste.
- **Il testo è DATO autorale** (asset), deterministico: la notifica arriva
  identica offline e live. L'AI potrà *proporre* obiettivi nuovi solo via
  canale di authoring gated (vocabolario di trigger chiuso), mai deciderne
  lo sblocco.
- **I numeri della ricompensa li deriva il motore**: una Box è un conio
  *ritardato* della fabbrica esistente (categoria + grado → base × famiglia
  × affissi), su stream RNG **isolato** (`master_seed:box:{id}`) — replay-
  safe, lo stream di sessione non si muove.
- **Niente orologio, niente XP**: la progressione del motore oggi è vuota
  per contratto; le ricompense sono box, oggetti o beffe testuali — mai
  "esperienza" inventata per l'occasione.

## Cosa si riusa (il sistema è quasi tutto già in casa)

| Pezzo | Già esiste | Uso |
|---|---|---|
| Bus tipizzato + eventi di dominio | `CombatResolved`, `MortePersonaggio`, `OggettoTrovato`, `TransizioneZona`, `DiscesaPiano`, `ColpoInferto`, `StatusApplicato`, `RiposoConcluso`, `EncounterStarted`, `DisimpegnoScena`… | I trigger. L'osservatore è un ascoltatore del bus, intra-run. |
| Fabbrica del loot | `conia_procedurale` (basi × famiglie × affissi × grado) | L'apertura della box = conio vincolato a (categoria, grado). |
| Luoghi quieti | `stanza_quieta()` (safe room, bagno) | «Apri box» è un'azione di scena composta dal motore SOLO lì — la regola del riferimento coincide con la meccanica che abbiamo. |
| Possesso persistente | Zaino + `OggettiConiati` (tag H-3) | Le box chiuse sono possesso; sopravvivono al save. |
| Cronaca tipata + prosa fuori banda | `CronacaBus.preleva_tipata`, registri host | La notifica arriva agli host col SUO tipo: la TUI la scrive, la SPA la veste (il riquadro-achievement esiste già). |
| Asset con chiusura per-run | `contenuti/` + freeze in `StagioneAttiva` | Il catalogo obiettivi è dato, congelato alla nascita della run. |
| Ledger sovra-run | `esiti.jsonl` (pattern outbox) | Gli obiettivi cross-run (Fase O5) riusano il pattern, non lo reinventano. |

## Il modello

**`AchievementAsset`** (contenuti, `contenuti/obiettivi/*.json`):
`slug`, `titolo`, `testo` (la notifica, registro show), `trigger`
(dichiarativo: `evento` dal vocabolario chiuso + `condizioni` tipate, es.
`{"evento": "combat_risolto", "vittoria": true, "hp_persi_max": 0}`),
`ricompensa` (`{"box": {"categoria": "...", "grado": "bronzo|…"}}` oppure
`{"beffa": "testo"}` — la beffa è una ricompensa dichiarata, non un campo
vuoto), `ripetibile: false` (default: una volta per run).

**`ObiettivoRaggiunto`** (contracts, evento di dominio): `slug`, `titolo`,
`testo`, `ricompensa_testo` — la notifica viaggia TIPATA sul bus; gli host
la rendono col loro registro, mai ricostruendola dal testo.

**`BoxChiusa`** (possesso): vive in `ObiettiviRun.box` — NON nello Zaino
(quello è il canale dell'equipaggiabile: una box lì inquinerebbe il flusso
equip). Id deterministico `{slug}#{n}`: sarà la chiave dello stream di
conio. L'azione «Apri box» (nuovo `TipoAzione.APRI_BOX`, composto dal
motore solo in quiete) conia e deposita nello zaino l'OGGETTO, con cronaca
tipata.

**`ObiettiviRun`** (componente World, persistente): gli slug sbloccati —
il dedup degli unlock e la colonna-notifiche al load.

**Categorie box → fabbrica**: `armi` (basi tipo arma), `indumenti`
(armatura), `accessori` (accessorio), `avventuriero` (qualunque base).
Categorie senza contenuto (es. compagni animali) NON si dichiarano finché
il contenuto non esiste: mai una box che non può aprire nulla.

## Le fasi (verticali, ognuna si chiude con test verdi)

- **O1 — Contratto + osservatore.** `AchievementAsset` e `ObiettivoRaggiunto`
  in contracts; `motore/obiettivi.py`: valutatore dichiarativo dei trigger
  sugli eventi del bus, `ObiettiviRun` persistente (tag), pubblicazione
  della notifica, deposito della box nello zaino. Catalogo demo di 3 voci
  sintetiche nei test. *Uscita: uccidi un mob → notifica tipata sul bus +
  box nello zaino; reload → niente doppio sblocco.*
- **O2 — Le box si aprono.** `TipoAzione.APRI_BOX` in quiete; conio
  vincolato (categoria, grado) su stream isolato; cronaca `BoxAperta`.
  *Uscita: box aperta in safe room → oggetto della categoria giusta nello
  zaino; fuori dalla quiete l'azione non si compone; replay identico.*
- **O3 — Il catalogo autorale.** 15–20 obiettivi ORIGINALI (`contenuti/
  obiettivi/`), congelati per-run: primo sangue, prima uccisione, vittoria
  senza graffi, fuga pulita, parlamento riuscito, tregua rispettata, primo
  varco di zona, discesa, riposo nel bagno, morte (postumo, via epitaffio),
  drop leggendario, dungeon infestato accettato, daily giocato… Trigger dal
  vocabolario, mai casi speciali nel codice. *Uscita: catalogo lintato
  (trigger noti, categorie box esistenti), playtest TUI.*
- **O4 — Gli host.** TUI: notifiche nel log col registro + elenco (`o`?);
  poi travaso al lab: endpoint + colonna-notifiche nella SPA (il riquadro
  achievement c'è già come stile). *Uscita: pilot TUI + (dopo travaso) test
  host web.*
- **O5 — Sovra-run (dopo, dichiarata).** Obiettivi cross-run nel guscio
  (ledger pattern, «postumi» inclusi nel necrologio); i «primi al mondo»
  SOLO col server-classifica (Fase C/E): senza server niente finti
  contatori globali.

## Decisioni da ratificare (§O)

1. **Casa del catalogo**: obiettivi di SISTEMA (`contenuti/obiettivi/`,
   validi per ogni stagione) + le stagioni possono aggiungerne di propri?
   (proposta: sì, stesso pattern degli altri asset)
2. **Apertura solo in quiete**: confermi la regola? (proposta: sì — fedele
   al riferimento e alla meccanica esistente; dà valore alle safe room)
3. **Beffe**: ricompensa-testo senza oggetto, dichiarata nel dato —
   confermi che è un tipo di ricompensa legittimo? (proposta: sì, è metà
   del registro comico)
4. **`TipoAzione.APRI_BOX`**: nuovo membro d'enum del contratto (schema
   chiuso: è un'aggiunta consapevole).
5. **Notifiche al load**: la colonna-notifiche arretrate (stile
   riferimento) o solo live? (proposta: `ObiettiviRun` tiene le non-lette,
   l'host le drena — stessa disciplina della prosa fuori banda)
