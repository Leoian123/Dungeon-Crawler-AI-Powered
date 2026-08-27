// Tipi TS SPECULARI ai DTO Pydantic di src/contracts/vista.py e alle risposte
// dell'host web (src/host_web/app.py). Scritti a mano nel primo taglio (niente
// codegen): le tuple Pydantic arrivano come array JSON. Lo SnapshotVista si
// sostituisce in blocco, mai diffato (C-4).

export type Fase = "narrazione" | "combattimento";

export interface OpzioneVista {
  indice: number;
  etichetta: string;
  tipo: string;
  /** false = voce mostrata ma non giocabile ora (mossa senza mana o in ricarica). */
  abilitata?: boolean;
}

/** Come una run è finita. `null` = in corso. */
export type Terminale = "sconfitta" | "piano_completato" | "uscita_volontaria";

export interface SnapshotVista {
  prosa: string;
  opzioni: OpzioneVista[];
  stato: string[];
  fase: Fase;
  /** `null` finché la run è in corso. Distingue «sceso di un piano» (null, con
   *  `profondita` cresciuta) da «ho vinto» ("piano_completato"). La comodità
   *  `run_conclusa` non è un campo: è `terminale !== null` — un dato derivato
   *  non si serializza, si calcola. */
  terminale: Terminale | null;
  /** Il piano in cui ci si trova ORA (sale a ogni discesa). */
  profondita: number;
  /** Scena sociale APERTA (parlamentare riuscito): l'input raccoglie BATTUTE
   *  (porta di scena), non azioni libere. Scegliere un'opzione del menu la
   *  abbandona nel motore. */
  scena_aperta: boolean;
}

export interface TempoVista {
  tick_correnti: number;
  tick_spesi: number;
  etichetta: string;
}

export interface ProvaVista {
  classe: string;
  stat: string;
  esito: boolean | null;
}

export interface MessaggioGM {
  prosa: string;
  dove: string;
  come: string;
  tempo: TempoVista;
  snapshot: string[];
  prova: ProvaVista | null;
  opzioni: OpzioneVista[];
  fallback: boolean;
}

export interface StimaAzione {
  durata: string;
  tick: number;
  forbice: string;
  skill_riferimento: string | null;
}

export interface RiepilogoAzione {
  testo_proposto: string;
  contesto: string;
  stima: StimaAzione;
}

/** Una riga di cronaca TIPATA: `tipo` = nome della classe dell'evento di
 *  dominio (lo stesso identificatore del canale SSE). Il client sceglie il
 *  registro visivo dal TIPO — mai annusando i prefissi del testo. */
export interface RigaEvento {
  tipo: string;
  testo: string;
}

/** Una battuta dello scambio di scena: `chi` è dato, le «» sono vestizione. */
export interface BattutaThread {
  chi: "crawler" | "canale";
  testo: string;
}

export interface PostThread {
  id: number;
  /** "gm" turno del GM · "evento" cronaca del bus · "prosa" battito fuori
   *  banda (trailer/premio/epitaffio) · "scena" scambio del parlamentare. */
  genere: "gm" | "evento" | "prosa" | "scena";
  messaggio: MessaggioGM | null;
  /** Solo genere="prosa": il testo puro del battito. */
  righe: string[];
  /** Solo genere="evento": la cronaca tipata. */
  eventi: RigaEvento[];
  /** Solo genere="scena": lo scambio del parlamentare. */
  battute: BattutaThread[];
  /** Solo per genere="prosa": "apertura" | "premio" | "epitaffio". */
  tipo_prosa?: string;
}

export interface StatoPartita {
  versione: number;
  fase: Fase;
  occupato: boolean;
  morto: boolean;
  vittoria: boolean;
  /** `seed` = quello EFFETTIVO (post «run del giorno»), solo per run nuove. */
  crawler: { uuid: string; nome: string; seed?: number } | null;
  snapshot: SnapshotVista | null;
  gm: string;
}

export interface CrawlerVista {
  uuid: string;
  etichetta: string;
  profondita: number;
  timestamp: number; // epoch secondi; 0 = save legacy senza data
  corrotta: boolean;
}

export interface RispostaCrawlers {
  crawlers: CrawlerVista[];
  attiva: { uuid: string; nome: string } | null;
}

/** Una skill/mossa: cosa costa, se è pronta e perché no. */
export interface SkillVista {
  chiave: string;
  etichetta: string;
  descrizione: string;
  costo_mana: number;
  cd_totale: number;
  cd_residuo: number;
  pronta: boolean;
  /** Il livello della skill che governa la mossa (nodo S): 1 = base. */
  livello: number;
}

/** Uno slot di equipaggiamento. `nome` vuoto = slot vuoto (nessun oggetto: il
 *  motore non ne ha ancora); `categoria` è la geometria che muove le derivate. */
export interface EquipVista {
  slot: "arma" | "armatura";
  nome: string;
  categoria: string;
  descrizione: string;
  /** Dato di vestizione (§B-4): "" = non detto (storici, pre-ventaglio). */
  grado: string;
  /** scarto | pregiato | "" — l'onesto tace, come in cronaca. */
  qualita: string;
}

/** L'avanzamento dentro la run. CONTRATTO VUOTO per ora: nessuna fonte di XP
 *  esiste, i campi restano a zero — la forma c'è perché il giorno che arriverà
 *  il contenuto la UI non cambi. `livello_piano` è la PROFONDITÀ, non un livello
 *  di personaggio. */
export interface ProgressioneVista {
  livello_piano: number;
  esperienza: number;
  esperienza_al_prossimo: number;
  punti_da_spendere: number;
}

export interface SchedaVista {
  uuid: string;
  nome: string;
  vivo: boolean;
  hp: number;
  hp_max: number;
  descrittori: string[];
  primarie: Record<string, number>;
  primarie_occulte: string[];
  derivate: Record<string, number>;
  livello: number;
  tick_piano: number;
  mana: number;
  mana_max: number;
  skills: SkillVista[];
  equip: EquipVista[];
  progressione: ProgressioneVista;
  /** Le FONTI possedute (loot degli scontri): il dettaglio vive in
   *  GET /api/partita/zaino (etichette diegetiche + stato indossata). */
  zaino: string[];
}

/** Una voce dell'inventario (SPECULARE a `OggettoVista` del backend, §B-4):
 *  il dato — tipo, grado, fattura, effetto — arriva TIPATO dal motore; la UI
 *  veste (badge, bottone «Usa»), mai deduce dal nome. L'etichetta diegetica
 *  (Guardaroba) vince sul catalogo per il display. */
export interface VoceZaino {
  fonte: string;
  etichetta: string;
  indossata: boolean;
  nome: string;
  /** armatura | arma | accessorio | consumabile | "" */
  tipo: string;
  grado: string;
  /** scarto | pregiato | "" — l'onesto tace. */
  qualita: string;
  /** Solo consumabili: la chiave del vocabolario chiuso (cura, …). */
  effetto: string;
  descrizione: string;
  indossato: boolean;
}

export interface RispostaZaino {
  fonti: VoceZaino[];
}

/** Una riga del REGISTRO delle competenze (nodo S, speculare a
 *  `SkillRigaVista`): livello e usi li deriva il motore — la UI mostra il
 *  conto, junk compreso (che è metà del tono). */
export interface SkillRiga {
  slug: string;
  nome: string;
  tipo: string;        // attiva | passiva
  livello: number;
  usi: number;
  testo: string;
  mossa: string;       // per le attive: la chiave che governa
  dominio: string;     // combattimento | magia | … | mondana
  effetto: string;     // cosa muove il livello ("" = tono)
}

export interface RispostaSkill {
  skill: SkillRiga[];
}

/** Una riga dell'elenco obiettivi (nodo O4), SPECULARE a ObiettivoVista: il
 *  dato arriva GIÀ velato dal backend — titolo sempre, `testo` e
 *  `ricompensa_testo` vuoti finché `sbloccato` è false. Il client mostra,
 *  mai deduce. */
export interface ObiettivoVista {
  slug: string;
  titolo: string;
  testo: string;
  sbloccato: boolean;
  ricompensa_testo: string;
}

/** GET /api/partita/obiettivi: l'elenco + le box che aspettano una safe room. */
export interface RispostaObiettivi {
  obiettivi: ObiettivoVista[];
  box_in_coda: number;
}

/** Un necrologio della bacheca sovra-run: PROIEZIONE del ledger degli esiti
 *  (composizione deterministica dai fatti — l'AI al più veste, mai inventa). */
export interface NecrologioCrawler {
  uuid_run: string;
  nome: string;
  titolo: string;
  corpo: string;
  stagione: number;
  profondita: number;
  ts: string;
}

export interface RispostaBacheca {
  necrologi: NecrologioCrawler[];
}

// --- Wiki del Master (cruscotto W2): l'outbox delle run → il canone ------------

export interface RevisioneVoceWiki {
  n: number;
  testo: string;
  provenienza: string;
  ts: string;
}

export interface VoceWikiVista {
  slug: string;
  tipo: string;
  regia: string;
  segretezza: string;
  costante: boolean;
  inneschi: string[];
  revisioni: RevisioneVoceWiki[];
  approvazioni: { revisione_n: number; autore: string; ts: string }[];
}

/** Una proposta in coda nell'outbox di una run (id deterministico: firma del
 *  fatto). `taint` = la regia più restrittiva vista in run. */
export interface PropostaWikiVista {
  id: string;
  tipo: string;
  titolo: string;
  testo: string;
  taint: string;
  uuid_run: string;
  ts: string;
}

export type GmScelta = "fake" | "live";

export type ApriPartita =
  | {
      gm: GmScelta;
      nuovo: {
        nome: string;
        seed: number;
        stagione?: string | null;
        /** Run del giorno: il server deriva il seed dalla data (sovra-run C). */
        daily?: boolean;
        /** Dungeon infestato: le morti del ledger locale come fantasmi-lore. */
        infestata?: boolean;
      };
    }
  | { gm: GmScelta; carica: { uuid: string } };

// --- Contenuti dello show (asset riusabili, speculari a contracts/contenuti.py) --

export const GRADI = ["bronzo", "argento", "oro", "platino", "leggendario", "celestiale"] as const;
export const DURATE = ["turno", "un_attimo", "un_pochino", "un_bel_po"] as const;

export type Grado = (typeof GRADI)[number];
// Blocchi e archetipi sono vocabolari VIVI del motore (SPEC_STATUS / registry
// per-run): arrivano da GET /api/vocabolario, mai da una lista cablata nel client
// (un blocco nuovo appare nei form da solo).
export type Blocco = string;
export type Archetipo = string;
export type DurataTurno = (typeof DURATE)[number];

export type TipoAsset = "stagioni" | "piani" | "mob" | "archetipi";

/** GET /api/vocabolario: enum del contratto + cataloghi del motore (una sola fonte). */
export interface Vocabolario {
  gradi: string[];
  blocchi: string[];
  durate: string[];
  tipi_danno: string[];
  mosse: string[];
  archetipi: string[];
  armature: string[];
  taglie: string[];
  armi: string[];
}

/** Profilo numerico di un archetipo (authoring: null = eredita, solo storici). */
export interface ProfiloArchetipoDati {
  destrezza_base?: number | null;
  pv_base?: number | null;
  danno_base?: number | null;
  intelligenza_base?: number | null;
  difesa_base?: number | null;
  saggezza_base?: number | null;
  fortuna_base?: number | null;
  armatura?: string | null;
  taglia?: string | null;
  arma?: string | null;
  res_mischia?: number | null;
  res_fuoco?: number | null;
  res_veleno?: number | null;
}

export interface ArchetipoAsset {
  slug: string;
  versione: number;
  tags: string[];
  nome: string;
  descrizione: string;
  profilo: ProfiloArchetipoDati | null;
  mosse: string[];
}

export interface BudgetDesign {
  gradi: Grado[];
  blocchi: Blocco[];
  archetipi: Archetipo[];
}

export interface MobAsset {
  slug: string;
  versione: number;
  tags: string[];
  nome: string;
  archetipo: Archetipo;
  grado: Grado;
  blocchi: Blocco[];
  descrizione: string;
  prosa_stanza: string;
  durata: DurataTurno;
  /** Mosse proprie (vuoto = quelle dell'archetipo, poi il default del motore). */
  mosse: string[];
  /** Override parziale del profilo d'archetipo (vince campo-per-campo). */
  override: ProfiloArchetipoDati | null;
}

export interface PianoAsset {
  slug: string;
  versione: number;
  tags: string[];
  titolo: string;
  tema: string;
  stile: string[];
  lore: string;
  budget: BudgetDesign;
  cast: string[]; // slug di MobAsset, in ordine di apparizione
  stanze: number | null;
}

export interface StagioneAsset {
  slug: string;
  versione: number;
  tags: string[];
  numero: number;
  titolo: string;
  tagline: string;
  mondo: string;
  stile: string[];
  lore: string;
  piani: string[]; // slug di PianoAsset, per profondità
}

export interface AssetVista {
  slug: string;
  tipo: "stagione" | "piano" | "mob" | "archetipo";
  etichetta: string;
  tags: string[];
  origine: "ufficiale" | "locale";
  valido: boolean;
}

// --- Calibrazione (GM mode): catalogo §11 + override, speculare a
// src/calibratore_web.costruisci_vista() e agli endpoint /api/calibrazione/*. --

export interface VoceCalibrazione {
  chiave: string;
  valore: string | number;
  default: string | number;
  spiegazione: string;
  dominio: string;
  unita: string;
  tipo: "int" | "float" | "scelta" | "testo";
  scelte: string[];
  override: boolean;
  sezione: "nemico" | "globale";
  gruppo: string; // archetipo (nemico) o categoria §11 (globale)
  etichetta: string;
  sotto: string; // sottosezione: Statistiche/Geometria/Resistenze o la categoria
}

export interface VistaCalibrazione {
  voci: VoceCalibrazione[];
  archetipi: { archetipo: string; nome: string; titolo: string }[];
  gradi: string[];
  percorso_override: string;
}

export interface VoceAggiornata {
  chiave: string;
  valore: string | number;
  override: boolean;
}

export interface AnteprimaMob {
  primarie: Record<string, number>;
  max_hp: number;
  atk_eff: number;
  def_eff_centesimi: number;
  eva_eff: number;
  acc_eff: number;
  resistenze_mult: Record<string, number>;
  geometria: { armatura: string; taglia: string; arma: string };
}

export interface RispostaTurno extends StatoPartita {
  post: PostThread[];
}

export interface RispostaThread {
  versione: number;
  post: PostThread[];
}

export interface CorpoErrore {
  codice: string;
  dettaglio: string;
  versione_corrente?: number;
}

export interface Progresso {
  etichetta: string;
  frazione: number;
}
