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

export interface SnapshotVista {
  prosa: string;
  opzioni: OpzioneVista[];
  stato: string[];
  fase: Fase;
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

export interface PostThread {
  id: number;
  genere: "gm" | "evento";
  messaggio: MessaggioGM | null;
  righe: string[];
}

export interface StatoPartita {
  versione: number;
  fase: Fase;
  occupato: boolean;
  morto: boolean;
  vittoria: boolean;
  crawler: { uuid: string; nome: string } | null;
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
}

/** Uno slot di equipaggiamento. `nome` vuoto = slot vuoto (nessun oggetto: il
 *  motore non ne ha ancora); `categoria` è la geometria che muove le derivate. */
export interface EquipVista {
  slot: "arma" | "armatura";
  nome: string;
  categoria: string;
  descrizione: string;
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
}

export type GmScelta = "fake" | "live";

export type ApriPartita =
  | { gm: GmScelta; nuovo: { nome: string; seed: number; stagione?: string | null } }
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
