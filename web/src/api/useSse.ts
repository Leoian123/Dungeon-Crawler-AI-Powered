// Canale SSE dall'host: progresso della pipeline GM (i 5 stadi — l'unico segnale
// di latenza: niente streaming token), segnale `post` (nuovo post → ri-fetch:
// copre più schede aperte), `morte`. EventSource si riconnette da solo.

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useGioco } from "../store/gioco";
import type { Progresso } from "./tipi";

export function useSse(attivo: boolean) {
  const qc = useQueryClient();
  const setProgresso = useGioco((s) => s.setProgresso);

  useEffect(() => {
    if (!attivo) return;
    const sorgente = new EventSource("/api/partita/eventi");
    sorgente.addEventListener("progresso", (evento) => {
      setProgresso(JSON.parse((evento as MessageEvent).data) as Progresso);
    });
    sorgente.addEventListener("post", () => {
      setProgresso(null);
      void qc.invalidateQueries({ queryKey: ["partita"] });
      void qc.invalidateQueries({ queryKey: ["thread"] });
    });
    sorgente.addEventListener("morte", () => {
      void qc.invalidateQueries({ queryKey: ["partita"] });
    });
    sorgente.addEventListener("vittoria", () => {
      void qc.invalidateQueries({ queryKey: ["partita"] });
    });
    sorgente.addEventListener("run_chiusa", () => {
      // La run si è chiusa (esci/chiudi, anche da un'altra scheda): stop allo
      // stream — riaprirà con la prossima run — e risincronizzazione.
      sorgente.close();
      setProgresso(null);
      void qc.invalidateQueries({ queryKey: ["partita"] });
      void qc.invalidateQueries({ queryKey: ["crawlers"] });
    });
    // RIAGGANCIO (playtest a 3 persone, P2): al riavvio dell'host l'EventSource
    // si riconnette da solo ma gli eventi persi nel buco non tornano — la tab
    // mostrava «attende il primo turno» con la partita già avanti, finché non
    // ricaricavi a mano. `open` scatta anche a ogni ri-connessione: si
    // risincronizza TUTTO lo stato remoto, che gli eventi siano arrivati o no.
    sorgente.addEventListener("open", () => {
      void qc.invalidateQueries({ queryKey: ["partita"] });
      void qc.invalidateQueries({ queryKey: ["thread"] });
      void qc.invalidateQueries({ queryKey: ["crawlers"] });
    });
    return () => sorgente.close();
  }, [attivo, qc, setProgresso]);
}
