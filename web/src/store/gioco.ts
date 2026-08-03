// Store Zustand: SOLO stato locale/effimero della UI. La verità remota (partita,
// thread) vive nella cache di TanStack Query; qui stanno le cose che il server
// non conosce: il progresso SSE del GM, l'avviso corrente, la finestra del
// composer dell'azione libera.

import { create } from "zustand";
import type { Progresso, RiepilogoAzione } from "../api/tipi";

export type StatoComposer =
  | { modo: "chiuso" }
  | { modo: "scrittura" }
  | { modo: "conferma"; riepilogo: RiepilogoAzione };

export type Sezione = "hub" | "gioco" | "forum";

interface StatoGioco {
  sezione: Sezione;
  progresso: Progresso | null;
  avviso: string | null;
  composer: StatoComposer;
  setSezione: (s: Sezione) => void;
  setProgresso: (p: Progresso | null) => void;
  setAvviso: (a: string | null) => void;
  setComposer: (c: StatoComposer) => void;
}

export const useGioco = create<StatoGioco>((set) => ({
  sezione: "hub",
  progresso: null,
  avviso: null,
  composer: { modo: "chiuso" },
  setSezione: (sezione) => set({ sezione }),
  setProgresso: (progresso) => set({ progresso }),
  setAvviso: (avviso) => set({ avviso }),
  setComposer: (composer) => set({ composer }),
}));
