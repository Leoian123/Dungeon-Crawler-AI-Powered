// TanStack Query: query di risincronizzazione + mutations di turno.
// Ogni mutation di turno riceve una `RispostaTurno`: aggiorna la cache della
// partita (snapshot SOSTITUITO in blocco, C-4) e APPENDE i nuovi post al thread
// (il thread è accumulo di testo). Su `turno_stantio` si invalida e risincronizza.

import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { api, ApiError } from "./client";
import type { ApriPartita, RispostaTurno, StatoPartita, TipoAsset } from "./tipi";
import { useGioco } from "../store/gioco";

export function usePartita() {
  return useQuery({
    queryKey: ["partita"],
    queryFn: api.statoPartita,
    // 404 = "nessuna partita": è uno stato, non un guasto — niente retry.
    retry: (tentativi, errore) =>
      !(errore instanceof ApiError && errore.status === 404) && tentativi < 2,
  });
}

export function useThread(abilitata: boolean) {
  return useQuery({
    queryKey: ["thread"],
    queryFn: api.thread,
    enabled: abilitata,
  });
}

export function useCrawlers() {
  return useQuery({ queryKey: ["crawlers"], queryFn: api.crawlers });
}

export function useEliminaCrawler() {
  const qc = useQueryClient();
  const setAvviso = useGioco((s) => s.setAvviso);
  return useMutation({
    mutationFn: ({ uuid }: { uuid: string }) => api.eliminaCrawler(uuid),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["crawlers"] });
      setAvviso("Crawler eliminato: lo slot è stato ritirato per sempre.");
    },
    onError: (errore) =>
      setAvviso(errore instanceof Error ? errore.message : String(errore)),
  });
}

// --- Libreria dei contenuti (GM mode) ----------------------------------------

export function useAssets(tipo: TipoAsset) {
  return useQuery({ queryKey: ["contenuti", tipo], queryFn: () => api.assets(tipo) });
}

/** Il vocabolario (enum + cataloghi + archetipi noti): la fonte dei menu degli
 * editor — mai liste cablate nel client. */
export function useVocabolario() {
  return useQuery({ queryKey: ["vocabolario"], queryFn: api.vocabolario });
}

/** Mutation generica di authoring: successo → si rilegge la collezione dal
 * server (mai merge client-side); errore → avviso col lint del server. */
export function useSalvaAsset(tipo: TipoAsset) {
  const qc = useQueryClient();
  const setAvviso = useGioco((s) => s.setAvviso);
  return useMutation({
    mutationFn: ({ corpo, nuovo }: { corpo: { slug: string }; nuovo: boolean }) =>
      nuovo ? api.creaAsset(tipo, corpo) : api.aggiornaAsset(tipo, corpo),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["contenuti", tipo] });
      // Un archetipo nuovo allarga il vocabolario dei menu (mob/piani).
      void qc.invalidateQueries({ queryKey: ["vocabolario"] });
      setAvviso("Asset salvato nella libreria locale.");
    },
    onError: (errore) =>
      setAvviso(errore instanceof Error ? errore.message : String(errore)),
  });
}

export function useEliminaAsset(tipo: TipoAsset) {
  const qc = useQueryClient();
  const setAvviso = useGioco((s) => s.setAvviso);
  return useMutation({
    mutationFn: ({ slug }: { slug: string }) => api.eliminaAsset(tipo, slug),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["contenuti", tipo] }),
    onError: (errore) =>
      setAvviso(errore instanceof Error ? errore.message : String(errore)),
  });
}

export function useAffini(tipo: TipoAsset, tags: string[]) {
  return useQuery({
    queryKey: ["affini", tipo, tags.join(",")],
    queryFn: () => api.affini(tipo, tags),
    enabled: tags.length > 0,
  });
}

// --- Calibrazione (GM mode) ---------------------------------------------------
// Stessa regola di autorità: il server valida e coerce, il client invalida e
// rilegge la vista intera (mai merge locale del valore applicato).

export function useCalibrazione() {
  return useQuery({ queryKey: ["calibrazione"], queryFn: api.calibrazione });
}

function useMutazioneCalibrazione<V>(mutationFn: (variabili: V) => Promise<unknown>) {
  const qc = useQueryClient();
  const setAvviso = useGioco((s) => s.setAvviso);
  return useMutation({
    mutationFn,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["calibrazione"] });
      void qc.invalidateQueries({ queryKey: ["cal-anteprima"] });
    },
    onError: (errore) =>
      setAvviso(errore instanceof Error ? errore.message : String(errore)),
  });
}

export function useImpostaCalibrazione() {
  return useMutazioneCalibrazione(
    ({ chiave, valore }: { chiave: string; valore: string | number }) =>
      api.calibrazioneImposta(chiave, valore),
  );
}

export function useAzzeraCalibrazione() {
  return useMutazioneCalibrazione(({ chiave }: { chiave: string }) =>
    api.calibrazioneAzzera(chiave),
  );
}

export function useSalvaCalibrazione() {
  const setAvviso = useGioco((s) => s.setAvviso);
  return useMutation({
    mutationFn: () => api.calibrazioneSalva(),
    onSuccess: ({ n, percorso }) =>
      setAvviso(`Salvati ${n} override → ${percorso}`),
    onError: (errore) =>
      setAvviso(errore instanceof Error ? errore.message : String(errore)),
  });
}

export function useAnteprimaCalibrazione(
  archetipo: string,
  grado: string,
  livello: number,
) {
  return useQuery({
    queryKey: ["cal-anteprima", archetipo, grado, livello],
    queryFn: () => api.calibrazioneAnteprima(archetipo, grado, livello),
  });
}

export function useScheda(abilitata: boolean) {
  return useQuery({
    queryKey: ["scheda"],
    queryFn: api.scheda,
    enabled: abilitata,
  });
}

export function partitaAssente(errore: unknown): boolean {
  return errore instanceof ApiError && errore.status === 404;
}

// REGOLA DI AUTORITÀ: il backend è l'UNICA fonte di verità; il client non
// costruisce MAI dati fondendo incrementi. La cache viene (a) rimpiazzata in
// blocco con lo stato fresco appena consegnato dal server (C-4), oppure (b)
// invalidata e riletta dal server. Niente merge client-side: un merge è una
// seconda superficie di deposito che può divergere (e correrebbe con le
// invalidazioni SSE).
function applicaTurno(qc: QueryClient, risposta: RispostaTurno) {
  const { post: _post, ...stato } = risposta; // i post incrementali NON si fondono
  qc.setQueryData<StatoPartita>(["partita"], stato);
  void qc.invalidateQueries({ queryKey: ["thread"] }); // il thread si RILEGGE
  void qc.invalidateQueries({ queryKey: ["scheda"] }); // HP/status possono cambiare
}

function risincronizza(qc: QueryClient) {
  void qc.invalidateQueries({ queryKey: ["partita"] });
  void qc.invalidateQueries({ queryKey: ["thread"] });
}

/** Mutation di turno: successo → cache aggiornata; errore → avviso per codice. */
function useMutazioneTurno<V>(mutationFn: (variabili: V) => Promise<RispostaTurno>) {
  const qc = useQueryClient();
  const setAvviso = useGioco((s) => s.setAvviso);
  const setProgresso = useGioco((s) => s.setProgresso);
  return useMutation({
    mutationFn,
    onSuccess: (risposta) => applicaTurno(qc, risposta),
    onError: (errore) => {
      if (errore instanceof ApiError && errore.codice === "turno_stantio") {
        risincronizza(qc);
        setAvviso("La scena era cambiata: vista risincronizzata, riprova.");
      } else if (errore instanceof ApiError && errore.codice === "motore_occupato") {
        setAvviso("Il GM sta ancora scrivendo…");
      } else {
        setAvviso(errore instanceof Error ? errore.message : String(errore));
      }
    },
    onSettled: () => setProgresso(null),
  });
}

export function useApriPartita() {
  const qc = useQueryClient();
  const setAvviso = useGioco((s) => s.setAvviso);
  const setSezione = useGioco((s) => s.setSezione);
  return useMutation({
    mutationFn: (corpo: ApriPartita) => api.apriPartita(corpo),
    onSuccess: (stato) => {
      qc.setQueryData(["partita"], stato);
      // La query era in errore (404 = partita assente): il refetch la riporta
      // in stato di successo; il thread arriva dal server (pieno se caricata).
      void qc.invalidateQueries({ queryKey: ["partita"] });
      void qc.invalidateQueries({ queryKey: ["thread"] });
      void qc.invalidateQueries({ queryKey: ["crawlers"] });
      setSezione("gioco");
    },
    onError: (errore) =>
      setAvviso(errore instanceof Error ? errore.message : String(errore)),
  });
}

/** Ritorno all'hub (salva-ed-esci o chiusura del terminale): cache della run
 * rimossa, elenco crawler aggiornato. */
function useTornaAllHub<V>(mutationFn: (variabili: V) => Promise<{ messaggio: string }>) {
  const qc = useQueryClient();
  const setAvviso = useGioco((s) => s.setAvviso);
  const setSezione = useGioco((s) => s.setSezione);
  return useMutation({
    mutationFn,
    onSuccess: ({ messaggio }) => {
      qc.removeQueries({ queryKey: ["partita"] });
      qc.removeQueries({ queryKey: ["thread"] });
      qc.removeQueries({ queryKey: ["scheda"] });
      void qc.invalidateQueries({ queryKey: ["crawlers"] });
      setSezione("hub");
      setAvviso(messaggio);
    },
    onError: (errore) =>
      setAvviso(errore instanceof Error ? errore.message : String(errore)),
  });
}

export function useEsci() {
  return useTornaAllHub(({ versione }: { versione: number }) => api.esci(versione));
}

export function useChiudi() {
  return useTornaAllHub((_: Record<string, never>) => api.chiudi());
}

export function useProssimaNarrazione() {
  return useMutazioneTurno(({ versione }: { versione: number }) =>
    api.narrazione(versione),
  );
}

export function useScegliOpzione() {
  return useMutazioneTurno(
    ({ indice, versione }: { indice: number; versione: number }) =>
      api.scegliOpzione(indice, versione),
  );
}

export function useEseguiAzione() {
  return useMutazioneTurno(
    ({ testo, versione }: { testo: string; versione: number }) =>
      api.eseguiAzione(testo, versione),
  );
}

export function useAnteprimaAzione() {
  const setAvviso = useGioco((s) => s.setAvviso);
  return useMutation({
    mutationFn: ({ testo }: { testo: string }) => api.anteprimaAzione(testo),
    onError: (errore) =>
      setAvviso(errore instanceof Error ? errore.message : String(errore)),
  });
}

export function useSalva() {
  const setAvviso = useGioco((s) => s.setAvviso);
  return useMutation({
    mutationFn: ({ versione }: { versione: number }) => api.salva(versione),
    onSuccess: (r) => setAvviso(r.messaggio),
    onError: (errore) =>
      setAvviso(errore instanceof Error ? errore.message : String(errore)),
  });
}
