# Sistema Skill (nodo S) — lo strato di COMPETENZA

Fonte: `docs/Dataset/Skill/DCC_skill_dataset_rarita.*` (107 skill del canone).
**Nota IP**: dal dataset si estraggono modello e regole, mai nomi o testi.

## La correzione di rotta (ratifica 2026-08-27)

La prima stesura aveva ridotto la skill a un contatore con un ritocco
percentuale. **Sbagliato per difetto**: nel canone il livello è la
MAGNITUDINE del potere («il moltiplicatore percentuale per livello è la base
della build», «doppio effetto per livello», «effetto nullo oggi, dominante
fra dieci livelli») — un Calpestare 15 non è un Calpestare 10 con più
tacche. E per questo progetto la skill è di più: è **lo strato di
competenza su cui gireranno i sistemi complessi** — magia, crafting,
sopravvivenza, combattimento avanzato. La sintesi è a tre:
- **canone**: le skill crescono con l'USO, il sistema conta tutto, il junk
  ad alto livello è metà del tono;
- **JRPG**: la skill è un POTERE con una curva — il livello scala effetti
  reali, i tomi insegnano, il gear costruisce la build;
- **master AI**: il GM legge le competenze dal fascicolo e ci narra sopra —
  ma il livello lo deriva il motore, mai il modello.

## Il modello a tre strati

**1. La COMPETENZA (dato).** `SkillAsset`: slug, nome, testo, `dominio`
(enum CHIUSO — la mappa dei sistemi futuri: `combattimento`, `magia`,
`artigianato`, `sopravvivenza`, `movimento`, `mondana`), `tipo`
(attiva|passiva), `pratica` (vocabolario chiuso sui fatti del bus),
**`effetto`** (vocabolario CHIUSO `EffettoCompetenza` — che cosa il livello
muove) e **`intensita`** (la `Fascia` lieve/marcata/potente: QUANTO per
livello — i numeri stanno in §11, mai nell'asset). `effetto` assente =
skill di puro tono (metà del canone): il junk resta legittimo, ma è una
dichiarazione, non un default.

**2. Il LIVELLO (derivata + canali).** Il livello resta una DERIVATA
deterministica — mai XP depositata — ma il conteggio degli usi è UN canale,
non l'identità: `livello = pavimento(dotazione) ∨ derivato(usi)`, con i
canali del dataset: dotazione iniziale (Earth — la valuta d'ingresso), la
pratica (Trained), i tomi che CREANO la competenza (GearTome), e il gear
che ne ALZA il livello finché indosso (dichiarato: fase S7 — «stessa skill
a +1 o +5», la build JRPG). Curva §11 triangolare, cap §11.

**3. La SUPERFICIE (il substrato dei sistemi).** L'API che i sistemi
presenti e futuri interrogano — questa è la parte che regge magia e
crafting:
- `livello_competenza(slug)` — il livello effettivo di una skill;
- `livello_dominio(dominio)` — la competenza di un DOMINIO (la migliore):
  il gate dei sistemi futuri («ricetta d'artigianato ≥ 5», «tomo di magia
  di cerchio ≥ livello del dominio»);
- `bonus_competenza(effetto, …)` — il valore vivo che un consumatore
  applica, derivato da (livello − 1) × fascia §11.

## Gli effetti (vocabolario chiuso, un consumatore ciascuno)

| `EffettoCompetenza` | dove morde | scala §11 per livello (l/m/p) |
|---|---|---|
| `potenza_mossa` | la mossa governata, dentro l'unico arrotondamento del check 2 | +3% / +6% / +10% |
| `margine_fuga` | il margine delle tre corsie del disimpegno | +0.5 / +1 / +1.5 punti |
| `resa_riposo` | HP per tick di riposo | +0.2 / +0.35 / +0.5 |
| `esca_agguati` | il dado-imboscata nel downtime | −2% / −4% / −6% (pavimento ×0.5) |

Il test del Calpestare: a fascia marcata, livello 10 = +54% sulla mossa —
contro il +24% del livello 5. Il livello È la build. DICHIARATI (una riga
d'enum + un consumatore quando il fatto esiste): `prova_sociale` (il
parlamento oggi non pubblica il suo fatto sul bus — prima l'evento, poi la
skill), `resa_crafting` e `potenza_magia` (i domini arriveranno coi loro
sistemi e leggeranno QUESTA superficie), `gradini` di sblocco a soglia di
livello (la skill-evolution JRPG: a livello N la mossa guadagna un effetto
— vocabolario mosse-asset, non codice).

## Il master AI

Le competenze NOTEVOLI (livello ≥ soglia, domini non mondani) entrano nel
FASCICOLO del turno GM come riga dati: il master narra un crawler che È
quelle competenze («fuga 7» = un fuggitore di mestiere), senza mai
deciderne i numeri. La skill è anche il canale con cui i sistemi AI-gated
futuri (magia proposta dal GM, ricette) verranno ARBITRATI: la proposta
passa, il gate chiede `livello_dominio`.

## Le fasi

- **S1–S4 (fatte, prima stesura)**: registro+osservatore, effetto attive,
  tomo, catalogo demo. Restano il pavimento.
- **S5 — La competenza**: `dominio`/`effetto`/`intensita` sul contratto,
  la superficie (`livello_competenza`, `livello_dominio`,
  `bonus_competenza`), foglie §11 effetto×fascia. *Uscita: il livello ha
  una magnitudine dichiarata per-skill, non un knob globale.*
- **S6 — I quattro consumatori**: mossa, fuga, riposo, agguati — ognuno
  cablato nel SUO punto unico (check 2, margine, resa, dado), livello 1 =
  storico byte-identico, lucchetti.
- **S7 — Il gear che porta la skill in sé — FATTA (2026-08-27)**: «non
  tutti gli oggetti possono avere skill, ma alcuni sì» — SOLO gli
  indossabili portano la coppia `skill` (slug del catalogo) +
  `skill_livelli` (1–5, «+1 o +5»); il consumabile mai (lui INSEGNA, col
  tomo). Il livello EFFETTIVO = derivata degli usi (cap §11) + bonus dei
  pezzi indosso — derivato alla lettura dal manifest, mai depositato:
  togli il pezzo, il livello torna suo. Il bonus può superare il cap: è la
  build. Vista, fattori, dominio e fascicolo lo seguono da soli (punto
  unico `_livello_di`). Lint chiuso su ENTRAMBI i canali: il tomo che
  insegna una mossa ignota e il pezzo che porta una skill fuori catalogo
  falliscono al GATE d'authoring, non in mano al giocatore. Demo: Anello
  del Suggeritore (+2 filo-di-mana), Schinieri del Disertore (+2
  gambe-in-spalla). Dichiarati: affissi di fabbrica con skill (il conio
  che pesca competenza), skill da pozione (canale Potion del canone).
- **S8 — Il fascicolo**: la riga-competenze nel prompt GM.
- **S9+ (dichiarate)**: prova sociale (prima l'evento sul bus), magia e
  artigianato come SISTEMI-consumatori di `livello_dominio`, gradini di
  sblocco, skill dei mob.
