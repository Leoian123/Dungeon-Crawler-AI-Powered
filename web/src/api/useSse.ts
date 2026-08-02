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
    return () => sorgente.close();
  }, [attivo, qc, setProgresso]);
}
