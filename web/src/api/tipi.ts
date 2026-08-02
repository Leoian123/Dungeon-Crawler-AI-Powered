// Tipi TS SPECULARI ai DTO Pydantic di src/contracts/vista.py e alle risposte
// dell'host web (src/host_web/app.py). Scritti a mano nel primo taglio (niente
// codegen): le tuple Pydantic arrivano come array JSON. Lo SnapshotVista si
// sostituisce in blocco, mai diffato (C-4).

export type Fase = "narrazione" | "combattimento";

export interface OpzioneVista {
  indice: number;
  etichetta: string;
  tipo: string;
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
  snapshot: SnapshotVista | null;
  gm: string;
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
