// MODALITÀ SCENA (parlamentare riuscito): l'input raccoglie BATTUTE — vanno
// alla porta di scena, MAI al turno GM (stessa separazione della TUI). Vuoto o
// «Tronca» = il giocatore chiude la conversazione. Il menu resta visibile:
// scegliere un'opzione abbandona la scena nel motore.

import { useState } from "react";
import { useBattutaScena } from "../api/query";

export function ComposerScena({
  versione,
  bloccato,
}: {
  versione: number;
  bloccato: boolean;
}) {
  const [testo, setTesto] = useState("");
  const battuta = useBattutaScena();
  const occupato = bloccato || battuta.isPending;

  const invia = (t: string) => {
    battuta.mutate(
      { testo: t, versione },
      { onSuccess: () => setTesto("") },
    );
  };

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-muschio/40 bg-pietra p-3">
      <span className="text-xs font-bold uppercase tracking-widest text-muschio/90">
        Scena aperta — cosa rispondi?
      </span>
      <div className="flex gap-2">
        <input
          autoFocus
          value={testo}
          disabled={occupato}
          onChange={(e) => setTesto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !occupato) invia(testo.trim());
          }}
          placeholder="La tua battuta (vuoto = tronchi la conversazione)"
          className="w-full rounded border border-muschio/30 bg-abisso px-3 py-2 text-pergamena placeholder:text-pergamena/40 focus:border-muschio/70 focus:outline-none"
        />
        <button
          disabled={occupato}
          onClick={() => invia(testo.trim())}
          className="rounded bg-muschio/80 px-4 py-1.5 font-bold text-abisso transition hover:bg-muschio disabled:opacity-40"
        >
          Parla
        </button>
        <button
          disabled={occupato}
          onClick={() => invia("")}
          className="rounded border border-pergamena/30 px-3 py-1.5 text-sm text-pergamena/70 transition hover:bg-pergamena/10 disabled:opacity-40"
        >
          Tronca
        </button>
      </div>
    </div>
  );
}
