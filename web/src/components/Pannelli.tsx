// Pannelli di contorno: progresso del GM (i 5 stadi della pipeline — l'unico
// segnale di latenza), banner di fase/morte, descrittori di stato, avvisi.

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Fase, Progresso } from "../api/tipi";
import { useChiudi } from "../api/query";
import { useGioco } from "../store/gioco";

/** Il cerchio morte→necrologio (sovra-run B): l'esito è già nel ledger quando
 *  il banner compare — il link porta alla bacheca con la query fresca. */
function LinkBacheca({ etichetta }: { etichetta: string }) {
  const qc = useQueryClient();
  const setSezione = useGioco((s) => s.setSezione);
  return (
    <button
      onClick={() => {
        void qc.invalidateQueries({ queryKey: ["bacheca"] });
        setSezione("forum");
      }}
      className="mt-2 ml-2 rounded border border-pergamena/40 px-4 py-1.5 font-hud text-xs font-bold uppercase tracking-wider text-pergamena/80 transition hover:bg-pergamena/10"
    >
      {etichetta}
    </button>
  );
}

export function ProgressoGM({ progresso }: { progresso: Progresso | null }) {
  if (!progresso) return null;
  return (
    <div className="flex items-center gap-3 rounded-lg border border-torcia/40 bg-pietra px-4 py-2">
      <span className="shrink-0 font-hud text-xs italic text-torcia">
        {progresso.etichetta}
      </span>
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
    <div className="rounded-lg border-2 border-sangue/60 bg-sangue/10 px-4 py-2 text-center shadow-[0_0_18px_rgba(248,113,113,0.2)]">
      <span className="titolo-insegna text-sm text-sangue">⚔ Combattimento</span>
      <span className="ml-3 font-hud text-xs uppercase tracking-widest text-sangue/70">
        risolvi prima · il GM narra dopo
      </span>
    </div>
  );
}

function BottoneTornaAllHub({ etichetta }: { etichetta: string }) {
  const chiudi = useChiudi();
  return (
    <button
      disabled={chiudi.isPending}
      onClick={() => chiudi.mutate({})}
      className="mt-2 rounded bg-torcia px-4 py-1.5 font-bold text-abisso transition hover:bg-torcia/90 disabled:opacity-40"
    >
      {etichetta}
    </button>
  );
}

export function BannerMorte() {
  return (
    <div className="rounded-lg border-2 border-sangue bg-sangue/15 px-4 py-3 text-center shadow-[0_0_24px_rgba(248,113,113,0.25)]">
      <p className="titolo-insegna text-xl text-sangue">💀 Sei morto.</p>
      <p className="text-sm text-pergamena/70">
        Permadeath: la run è terminata e lo slot verrà ritirato; il thread resta
        in sola lettura finché non torni all'hub. Il tuo necrologio è già in
        bacheca — lo show non dimentica nessuno.
      </p>
      <BottoneTornaAllHub etichetta="Torna all'hub" />
      <LinkBacheca etichetta="Leggi il tuo necrologio" />
    </div>
  );
}

export function BannerVittoria() {
  return (
    <div className="rounded-lg border border-muschio bg-muschio/10 px-4 py-3 text-center">
      <p className="titolo-insegna text-xl text-muschio">🏆 Piano completato!</p>
      <p className="text-sm text-pergamena/70">
        La discesa è la vittoria della run (MVP a un piano). Il crawler si ritira
        vittorioso: lo slot viene archiviato — e l'ascesa fa bacheca.
      </p>
      <BottoneTornaAllHub etichetta="Concludi e torna all'hub" />
      <LinkBacheca etichetta="Leggi la bacheca" />
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
          className="rounded-full border border-pergamena/25 bg-pietra px-2.5 py-0.5 font-hud text-[0.7rem] uppercase tracking-wider text-pergamena/80"
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
