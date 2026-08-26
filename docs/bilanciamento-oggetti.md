# Bilanciamento oggetti — il modello di rarità (nodo B, dal dataset di riferimento)

Fonte: `docs/Fine Tuning Oggetti/DCC_dataset_rarita_oggetti.*` — 144 oggetti del
riferimento classificati per tier di box (6), qualità nel tier (3) e punteggio
di potenza (2–95). **Nota IP (vincolante, come per il nodo O)**: dal dataset si
estraggono le CURVE e le REGOLE STRUTTURALI, mai i nomi o i testi — il registro
si imita, il contenuto no. Nessun nome del dataset entra nel repo di gioco.

## Cosa dice il dataset (il modello, ripulito)

**Le due assi sono indipendenti.** Il tier della box (Bronze→Celestial) NON è
la qualità dell'oggetto: ogni tier ha un ventaglio interno Bad/Mid/Good, e i
ventagli si SOVRAPPONGONO — un Good di bronzo (13–30) batte un Mid d'oro
(13–22). È la sovrapposizione a rendere il loot leggibile ma mai scontato.

**La curva di potenza per (tier, qualità)** — mediane del dataset:

| tier | Bad | Mid | Good |
|---|---|---|---|
| 1 Bronze | 3.5 | 9 | 17 |
| 2 Silver | 3 | 11 | 15.5 |
| 3 Gold | 12 | 18.5 | 26 |
| 4 Platinum | — | 32.5 | 46 |
| 5 Legendary | — | 46 | 62 |
| 6 Celestial | 45 | 76 | 88.5 |

**La distribuzione di qualità per tier** (conteggi del dataset, da leggere come
pesi): Bronze 8/7/8 (un terzo ciascuna), Silver 4/8/12, Gold 1/12/22,
Platinum 0/12/11, Legendary 0/5/17, Celestial 2/3/12. Il pavimento «Bad»
esiste nei tier bassi (junk e joke item: metà del tono), sparisce al
Platinum/Legendary, e RITORNA al Celestial come rischio catastrofico.

**Le regole nelle note di bilanciamento del dataset:**
1. Ogni tier basso ha un pavimento Bad puro (junk di consolazione, joke item).
2. Benefactor = moltiplicatore ×2 tier (una Benefactor Bronze batte una
   Adventurer Gold).
3. Tier più alto = stesso consumabile × N (quantità, non solo qualità).
4. Stessa box, piano più profondo = contenuto migliore (scaling per piano).
5. Gli artefatti di quest sono EVENTO, mai nel pool casuale.
6. Il valore può superare il tier per sinergia (crafting) — potenza ≠ prezzo.

## La mappa sul motore (cosa esiste, cosa manca)

Esiste già: `Grado` a 6 valori = i 6 tier; fabbrica basi×famiglie×affissi con
affissi per rango (bronzo 0, argento 1, oro+ 2); numeri = fascia × rango
(§11); `OGGETTO.DANNO_ARMA.{grado}` in calibrazione; `Arma.danno_base`
valorizzato dal grado alla traduzione (`oggetto_da_asset`).

Manca (i due buchi che il power-play del 2026-08-26 ha misurato):
- **Il layer impugnato è DORMIENTE**: `atk_eff` = solo Forza — l'arma coniata
  non aggiunge danno; `misura_run` sceglie perfino «l'arma col danno più
  alto», che oggi non fa nulla. È la radice del muro dei tier alti (il gear
  difensivo scala via fascia×rango e `MOLT_COSTITUZIONE`, l'offesa no).
- **La qualità nel grado non esiste**: due coni dello stesso grado sono
  equivalenti — niente ventaglio, niente sovrapposizione fra gradi, niente
  pavimento junk. Il loot è piatto dentro il tier.

## Le fasi

- **B1 — La review-armi: il layer impugnato si sveglia.** `atk_eff` legge il
  `danno_base` dell'arma INDOSSATA (via manifest equip: i mob senza equip non
  si muovono — il loro scaling resta `K_RANGO_DANNO`). La curva
  `OGGETTO.DANNO_ARMA.{grado}` si ricalibra CONVESSA derivandola da
  `K_RANGO_HP` (l'arma attesa insegue il pool atteso del suo grado — stessa
  logica del corredo di riferimento): `round(base × (1 + K_RANGO_HP·(rango−1)))`.
  *Uscita: armato colpisce più forte di esattamente danno_base; TTK in banda;
  suite verde.*
- **B2 — La qualità del conio (scarto / onesto / pregiato).** Vocabolario
  ORIGINALE del ventaglio Bad/Mid/Good. Pescata seeded in `conia_procedurale`
  con pesi §11 per grado (derivati dal dataset). Effetti (composizione, mai
  traduzione): SCARTO = zero affissi + arma un grado sotto (floor bronzo) —
  il junk di consolazione; ONESTO = il comportamento attuale; PREGIATO = un
  affisso in più (cap 3) + arma un grado sopra (cap celestiale) — la
  sovrapposizione coi gradi vicini per costruzione. `qualita` viaggia
  sull'`OggettoAttivo` (default "onesto": i save vecchi non cambiano).
  *Uscita: distribuzione seeded conforme ai pesi; scarto/pregiato visibili
  su descrizione; replay identico; suite verde.*
- **B3 — La misura di chiusura.** `misura_run` + il driver power-player
  ripetuti sulla nuova curva: il muro provincia/paese deve spostarsi — il
  bersaglio dichiarato è che il power player VEDA la scala (piano 2).
  Le foglie si ritoccano QUI, sui numeri misurati, non a tavolino.

## Decisioni §B (stato al 2026-08-26)

1. **Scaling per territorio delle box — RATIFICATA E FATTA**: il grado del
   conio-box = max(grado della box, minimo della finestra-loot corrente —
   la stessa dei drop, `finestra_gradi_loot`). Aprire tardi PAGA: è una
   scelta del giocatore (tenersi la box per il territorio profondo), non un
   exploit — il conio resta deterministico per-box nella timeline in cui
   apri. `BoxAperta.grado` dice il grado CONIATO.
2. **Il dato agli host — FATTA (backend completo, §B-4 chiuso 2026-08-26)**:
   `OggettoTrovato` trasporta `grado`+`qualita`, `BoxAperta` la `qualita`
   ("" = non detto); la cronaca annuncia la fattura («— fattura di scarto /
   pregiata», l'onesto tace). I pezzi vivi (Arma/PezzoArmatura/Accessorio)
   portano grado/fattura/descrizione; `EquipVista` li espone per slot e la
   porta NUOVA `zaino_vista()` dà l'inventario TIPATO (`OggettoVista`: tipo,
   grado, fattura, effetto del consumabile, indossato) — i badge e il
   bottone «Usa» della SPA nascono da lì, mai da sniffing sul nome. Il NOME
   resta pulito (identità del pezzo): la fattura è vista+cronaca, non un
   suffisso col problema del genere. E le DESCRIZIONI ora si COMPONGONO:
   voce di fattura da POOL autorali (5/4/5 varianti, pescata seeded in coda
   allo stream — mai un prefisso fisso, il timbro ripetuto era déjà-vu) +
   riga di manifattura della famiglia (asset) + nota dell'ELEMENTO
   (`ParteAffisso.descrizione`, campo NUOVO d'asset, note scritte per la
   catena-dei-morti). Tre registri, tutti dato autorale o pool del motore —
   mai testo generato a runtime.
3. **Box Benefactor** (moltiplicatore ×2 tier): oggi non esistono box
   benefactor — quando arriveranno (sponsor/fan, strato sovra-run), il
   moltiplicatore è la regola. Dichiarata ora, si implementa allora.
4. **Consumabili — CANALE FATTO (2026-08-26)**: `OggettoAsset` tipo
   "consumabile" con `effetto` dal vocabolario CHIUSO (`EffettoConsumabile`:
   cura, ristoro_mana, antidoto — un effetto nuovo = un membro + una riga
   nell'esecutore, pattern SPEC_STATUS); numeri §11 come quote del MASSIMO
   per grado (`CONSUMABILE.CURA_PCT.*` / `MANA_PCT.*` — la pozione scala col
   pool, il «almeno il 50%» del riferimento); monouso, uso via INVENTARIO
   (porta `sessione.usa(fonte)` → `PlayerUsaOggetto` → `SistemaConsumabili`
   solo-narrazione: in combattimento l'intento resta in coda, come l'equip);
   il rifiuto (HP pieni, niente da purgare) NON consuma e non è un fatto;
   l'antidoto purga i dannosi APPLICATI, mai gli innati; `OggettoUsato` in
   cronaca col dettaglio composto. Dato demo originale (3 pezzi, uno per
   effetto) nel catalogo della run → girano nei drop dal pool. DICHIARATI
   post-MVP: uso in combattimento (costo AP + cooldown: muove il TTK, va
   misurato), consumabili dalla fabbrica/box (le parti non hanno vocabolario
   d'effetto), «stesso consumabile ×N» ai tier alti.
5. **Joke item**: il pavimento scarto è già la metà comica; testi joke
   AUTORALI (asset) possono arrivare come contenuto, mai generati dal motore.
