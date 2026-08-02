// Schermata iniziale (GET /api/partita → 404): seed + GM fake/live. La chiave
// LLM non passa MAI di qui: il client sceglie solo l'etichetta "fake"|"live",
// la chiave resta nell'ambiente del server (PLK §4). Dopo la creazione parte
// subito il primo turno di narrazione.

import { useState } from "react";
import { useCreaPartita, useProssimaNarrazione } from "../api/query";

export function NuovaPartita() {
  const [seed, setSeed] = useState(1);
  const [gm, setGm] = useState<"fake" | "live">("fake");
  const crea = useCreaPartita();
  const narrazione = useProssimaNarrazione();
  const occupato = crea.isPending || narrazione.isPending;

  const avvia = () =>
    crea.mutate(
      { seed, gm },
      { onSuccess: () => narrazione.mutate({ versione: 0 }) },
    );

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-6 px-4">
      <h1 className="text-center text-3xl font-bold text-torcia">
        Dungeon Crawler
      </h1>
      <p className="text-center italic text-pergamena/70">
        Un forum play-by-post dove il GM è un'AI — ma ogni esito lo decide il
        motore.
      </p>
      <label className="flex w-full flex-col gap-1 text-sm">
        Seed della discesa
        <input
          type="number"
          value={seed}
          disabled={occupato}
          onChange={(e) => setSeed(Number(e.target.value) || 0)}
          className="rounded border border-pergamena/25 bg-pietra px-3 py-2 text-pergamena focus:border-torcia/60 focus:outline-none"
        />
      </label>
      <fieldset className="flex w-full gap-2" disabled={occupato}>
        {(["fake", "live"] as const).map((scelta) => (
          <button
            key={scelta}
            onClick={() => setGm(scelta)}
            className={`flex-1 rounded border px-3 py-2 text-sm transition ${
              gm === scelta
                ? "border-torcia bg-torcia/15 text-torcia"
                : "border-pergamena/25 text-pergamena/70 hover:bg-pergamena/10"
            }`}
          >
            {scelta === "fake" ? "GM offline (scriptato)" : "GM live (Anthropic)"}
          </button>
        ))}
      </fieldset>
      <button
        onClick={avvia}
        disabled={occupato}
        className="w-full rounded bg-torcia px-4 py-3 text-lg font-bold text-abisso transition hover:bg-torcia/90 disabled:opacity-40"
      >
        {occupato ? "Il GM prepara la scena…" : "Scendi nel dungeon"}
      </button>
    </main>
  );
}
