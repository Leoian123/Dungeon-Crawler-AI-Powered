// Creazione di un nuovo crawler: nome (l'etichetta dello slot) + seed + GM.
// La chiave LLM non passa MAI di qui: "live" è solo un'etichetta, la chiave
// vive nell'ambiente del server (PLK §4).

import { useState } from "react";
import type { GmScelta } from "../api/tipi";
import { useApriPartita } from "../api/query";

export function CreaCrawler({
  gm,
  onAnnulla,
}: {
  gm: GmScelta;
  onAnnulla: () => void;
}) {
  const [nome, setNome] = useState("");
  const [seed, setSeed] = useState(1);
  const apri = useApriPartita();
  const valido = nome.trim().length > 0;

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-torcia/40 bg-pietra p-4">
      <h3 className="font-bold text-torcia">Nuovo crawler</h3>
      <label className="flex flex-col gap-1 text-sm">
        Nome (l'etichetta dello slot)
        <input
          autoFocus
          value={nome}
          disabled={apri.isPending}
          onChange={(e) => setNome(e.target.value)}
          placeholder="Es. Donut"
          className="rounded border border-pergamena/25 bg-abisso px-3 py-2 text-pergamena placeholder:text-pergamena/40 focus:border-torcia/60 focus:outline-none"
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Seed della discesa
        <input
          type="number"
          value={seed}
          disabled={apri.isPending}
          onChange={(e) => setSeed(Number(e.target.value) || 0)}
          className="rounded border border-pergamena/25 bg-abisso px-3 py-2 text-pergamena focus:border-torcia/60 focus:outline-none"
        />
      </label>
      <div className="flex gap-2">
        <button
          disabled={!valido || apri.isPending}
          onClick={() => apri.mutate({ gm, nuovo: { nome: nome.trim(), seed } })}
          className="rounded bg-torcia px-4 py-2 font-bold text-abisso transition hover:bg-torcia/90 disabled:opacity-40"
        >
          {apri.isPending ? "Discesa in corso…" : "Scendi nel dungeon"}
        </button>
        <button
          disabled={apri.isPending}
          onClick={onAnnulla}
          className="rounded border border-pergamena/30 px-4 py-2 text-pergamena/70 transition hover:bg-pergamena/10 disabled:opacity-40"
        >
          Annulla
        </button>
      </div>
    </div>
  );
}
