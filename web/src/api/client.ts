// Client HTTP tipizzato verso l'host web. Ogni errore applicativo arriva come
// `{codice, dettaglio}`: qui diventa `ApiError` così i chiamanti ragionano sul
// codice (turno_stantio → risincronizza; motore_occupato → avviso), mai sul testo.

import type {
  ApriPartita,
  CorpoErrore,
  RiepilogoAzione,
  RispostaCrawlers,
  RispostaThread,
  RispostaTurno,
  SchedaVista,
  StatoPartita,
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
  salva: (versione: number) =>
    richiesta<{ messaggio: string }>("/api/partita/salva", post({ versione })),
};
