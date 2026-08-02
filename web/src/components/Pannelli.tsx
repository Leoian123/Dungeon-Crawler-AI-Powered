// Pannelli di contorno: progresso del GM (i 5 stadi della pipeline — l'unico
// segnale di latenza), banner di fase/morte, descrittori di stato, avvisi.

import { useEffect } from "react";
import type { Fase, Progresso } from "../api/tipi";
import { useGioco } from "../store/gioco";

export function ProgressoGM({ progresso }: { progresso: Progresso | null }) {
  if (!progresso) return null;
  return (
    <div className="flex items-center gap-3 rounded-lg border border-torcia/40 bg-pietra px-4 py-2">
      <span className="text-sm italic text-torcia">{progresso.etichetta}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded bg-abisso">
        <div
          className="h-full bg-torcia transition-all duration-300"
          style={{ width: `${Math.round(progresso.frazione * 100)}%` }}
        />
      </div>
    </div>
  );
}

export function BannerFase({ fase }: { fase: Fase }) {
  if (fase !== "combattimento") return null;
  return (
    <div className="rounded-lg border border-sangue/50 bg-sangue/10 px-4 py-2 text-center font-bold tracking-widest text-sangue">
      ⚔ COMBATTIMENTO — risolvi prima, il GM narra dopo
    </div>
  );
}

export function BannerMorte() {
  return (
    <div className="rounded-lg border border-sangue bg-sangue/15 px-4 py-3 text-center">
      <p className="text-lg font-bold text-sangue">💀 Sei morto.</p>
      <p className="text-sm text-pergamena/70">
        Permadeath: la run è terminata; il thread resta in sola lettura. Riavvia
        l'host per una nuova discesa.
      </p>
    </div>
  );
}

export function PannelloStato({ stato }: { stato: string[] }) {
  if (stato.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {stato.map((descrittore, i) => (
        <span
          key={i}
          className="rounded-full border border-pergamena/25 bg-pietra px-2.5 py-0.5 text-xs text-pergamena/80"
        >
          {descrittore}
        </span>
      ))}
    </div>
  );
}

export function Avviso() {
  const avviso = useGioco((s) => s.avviso);
  const setAvviso = useGioco((s) => s.setAvviso);
  useEffect(() => {
    if (!avviso) return;
    const timer = setTimeout(() => setAvviso(null), 6000);
    return () => clearTimeout(timer);
  }, [avviso, setAvviso]);
  if (!avviso) return null;
  return (
    <div
      role="status"
      className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-lg border border-torcia/50 bg-pietra px-4 py-2 text-sm shadow-xl"
    >
      {avviso}
    </div>
  );
}
