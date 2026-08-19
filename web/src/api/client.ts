// Client HTTP tipizzato verso l'host web. Ogni errore applicativo arriva come
// `{codice, dettaglio}`: qui diventa `ApiError` così i chiamanti ragionano sul
// codice (turno_stantio → risincronizza; motore_occupato → avviso), mai sul testo.

import type {
  AnteprimaMob,
  ApriPartita,
  Vocabolario,
  AssetVista,
  CorpoErrore,
  RiepilogoAzione,
  RispostaBacheca,
  RispostaCrawlers,
  RispostaThread,
  RispostaTurno,
  RispostaZaino,
  SchedaVista,
  StatoPartita,
  TipoAsset,
  VistaCalibrazione,
  VoceAggiornata,
} from "./tipi";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly corpo: CorpoErrore,
  ) {
    super(corpo.dettaglio);
  }

  get codice(): string {
    return this.corpo.codice;
  }
}

async function richiesta<T>(percorso: string, init?: RequestInit): Promise<T> {
  const risposta = await fetch(percorso, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const corpo = await risposta.json().catch(() => ({
    codice: "risposta_non_json",
    dettaglio: risposta.statusText,
  }));
  if (!risposta.ok) throw new ApiError(risposta.status, corpo as CorpoErrore);
  return corpo as T;
}

const post = (corpo: object): RequestInit => ({
  method: "POST",
  body: JSON.stringify(corpo),
});

export const api = {
  statoPartita: () => richiesta<StatoPartita>("/api/partita"),
  thread: () => richiesta<RispostaThread>("/api/partita/thread"),
  crawlers: () => richiesta<RispostaCrawlers>("/api/crawlers"),
  eliminaCrawler: (uuid: string) =>
    richiesta<{ eliminato: string }>(`/api/crawlers/${uuid}`, { method: "DELETE" }),
  apriPartita: (corpo: ApriPartita) =>
    richiesta<StatoPartita>("/api/partita", post(corpo)),
  esci: (versione: number) =>
    richiesta<{ messaggio: string }>("/api/partita/esci", post({ versione })),
  chiudi: () => richiesta<{ messaggio: string }>("/api/partita/chiudi", post({})),
  scheda: () => richiesta<{ party: SchedaVista[] }>("/api/partita/scheda"),
  narrazione: (versione: number) =>
    richiesta<RispostaTurno>("/api/partita/narrazione", post({ versione })),
  scegliOpzione: (indice: number, versione: number) =>
    richiesta<RispostaTurno>("/api/partita/opzioni", post({ indice, versione })),
  anteprimaAzione: (testo: string) =>
    richiesta<{ versione: number; riepilogo: RiepilogoAzione }>(
      "/api/partita/azione/anteprima",
      post({ testo }),
    ),
  eseguiAzione: (testo: string, versione: number) =>
    richiesta<RispostaTurno>("/api/partita/azione", post({ testo, versione })),
  battutaScena: (testo: string, versione: number) =>
    richiesta<RispostaTurno>(
      "/api/partita/scena/battuta",
      post({ testo, versione }),
    ),
  zaino: () => richiesta<RispostaZaino>("/api/partita/zaino"),
  equipaggia: (fonte: string, versione: number) =>
    richiesta<RispostaTurno>("/api/partita/equipaggia", post({ fonte, versione })),
  togli: (fonte: string, versione: number) =>
    richiesta<RispostaTurno>("/api/partita/togli", post({ fonte, versione })),
  bacheca: () => richiesta<RispostaBacheca>("/api/bacheca"),
  salva: (versione: number) =>
    richiesta<{ messaggio: string }>("/api/partita/salva", post({ versione })),
  // Libreria dei contenuti (GM mode). Gli asset viaggiano come oggetti grezzi:
  // la VERITÀ della validazione è il 422 del server (lint deterministico).
  assets: (tipo: TipoAsset) =>
    richiesta<{ asset: AssetVista[] }>(`/api/contenuti/${tipo}`),
  asset: <T>(tipo: TipoAsset, slug: string) =>
    richiesta<T>(`/api/contenuti/${tipo}/${slug}`),
  creaAsset: <T extends { slug: string }>(tipo: TipoAsset, corpo: T) =>
    richiesta<T>(`/api/contenuti/${tipo}`, post(corpo)),
  aggiornaAsset: <T extends { slug: string }>(tipo: TipoAsset, corpo: T) =>
    richiesta<T>(`/api/contenuti/${tipo}/${corpo.slug}`, {
      method: "PUT",
      body: JSON.stringify(corpo),
    }),
  eliminaAsset: (tipo: TipoAsset, slug: string) =>
    richiesta<{ eliminato: string }>(`/api/contenuti/${tipo}/${slug}`, {
      method: "DELETE",
    }),
  affini: (tipo: TipoAsset, tags: string[]) =>
    richiesta<{ affini: AssetVista[] }>(
      `/api/contenuti/affini?tipo=${tipo}&tags=${encodeURIComponent(tags.join(","))}`,
    ),
  vocabolario: () => richiesta<Vocabolario>("/api/vocabolario"),
  // Calibrazione (GM mode): il valore viaggia GREZZO (stringa dell'input) — il
  // coerce e la validazione sono del catalogo server-side, mai del client.
  calibrazione: () => richiesta<VistaCalibrazione>("/api/calibrazione"),
  calibrazioneImposta: (chiave: string, valore: string | number) =>
    richiesta<VoceAggiornata>(
      `/api/calibrazione/voci/${encodeURIComponent(chiave)}`,
      { method: "PUT", body: JSON.stringify({ valore }) },
    ),
  calibrazioneAzzera: (chiave: string) =>
    richiesta<VoceAggiornata>(
      `/api/calibrazione/voci/${encodeURIComponent(chiave)}`,
      { method: "DELETE" },
    ),
  calibrazioneSalva: () =>
    richiesta<{ percorso: string; n: number }>("/api/calibrazione/salva", post({})),
  calibrazioneAnteprima: (archetipo: string, grado: string, livello: number) =>
    richiesta<AnteprimaMob>(
      "/api/calibrazione/anteprima",
      post({ archetipo, grado, livello }),
    ),
};
