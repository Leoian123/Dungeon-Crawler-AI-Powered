// L'azione libera col DOPPIO GIRO della TUI: testo → anteprima deterministica
// (zero LLM: "Stai per…, ti prenderà ~N tick") → il testo resta EDITABILE →
// conferma → il turno GM. Vuoto = annulla. Solo in narrazione, da vivi.

import { useState } from "react";
import { useAnteprimaAzione, useEseguiAzione } from "../api/query";
import { useGioco } from "../store/gioco";

export function ComposerAzione({
  versione,
  bloccato,
}: {
  versione: number;
  bloccato: boolean;
}) {
  const [testo, setTesto] = useState("");
  const composer = useGioco((s) => s.composer);
  const setComposer = useGioco((s) => s.setComposer);
  const anteprima = useAnteprimaAzione();
  const azione = useEseguiAzione();
  const occupato = bloccato || anteprima.isPending || azione.isPending;

  const annulla = () => {
    setTesto("");
    setComposer({ modo: "chiuso" });
  };

  if (composer.modo === "chiuso") {
    return (
      <button
        disabled={bloccato}
        onClick={() => setComposer({ modo: "scrittura" })}
        className="rounded border border-pergamena/30 px-4 py-2 text-pergamena/80 transition hover:bg-pergamena/10 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Azione libera…
      </button>
    );
  }

  const chiediAnteprima = () => {
    const pulito = testo.trim();
    if (!pulito) return annulla();
    anteprima.mutate(
      { testo: pulito },
      {
        onSuccess: ({ riepilogo }) => setComposer({ modo: "conferma", riepilogo }),
      },
    );
  };

  const conferma = () => {
    const pulito = testo.trim();
    if (!pulito) return annulla();
    // Il riepilogo viene RICALCOLATO dal server sul testo eventualmente editato.
    azione.mutate({ testo: pulito, versione }, { onSuccess: annulla });
  };

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-pergamena/20 bg-pietra p-3">
      <textarea
        autoFocus
        rows={3}
        value={testo}
        disabled={occupato}
        onChange={(e) => setTesto(e.target.value)}
        placeholder="Cosa fai? (vuoto = annulla)"
        className="w-full resize-y rounded border border-pergamena/20 bg-abisso px-3 py-2 text-pergamena placeholder:text-pergamena/40 focus:border-torcia/60 focus:outline-none"
      />
      {composer.modo === "conferma" && (
        <div className="rounded bg-abisso/60 px-3 py-2 text-sm">
          <p>
            <span className="font-bold text-torcia">Stai per:</span>{" "}
            {composer.riepilogo.testo_proposto} — corretto? (
            {composer.riepilogo.contesto})
          </p>
          <p className="italic text-pergamena/70">
            Questa azione ti prenderà {composer.riepilogo.stima.forbice} (~
            {composer.riepilogo.stima.tick} tick). Conferma, modifica il testo, o
            annulla.
          </p>
        </div>
      )}
      <div className="flex gap-2">
        {composer.modo === "scrittura" ? (
          <button
            disabled={occupato}
            onClick={chiediAnteprima}
            className="rounded bg-torcia/90 px-4 py-1.5 font-bold text-abisso transition hover:bg-torcia disabled:opacity-40"
          >
            Anteprima
          </button>
        ) : (
          <button
            disabled={occupato}
            onClick={conferma}
            className="rounded bg-torcia/90 px-4 py-1.5 font-bold text-abisso transition hover:bg-torcia disabled:opacity-40"
          >
            Conferma
          </button>
        )}
        <button
          disabled={occupato}
          onClick={annulla}
          className="rounded border border-pergamena/30 px-4 py-1.5 text-pergamena/70 transition hover:bg-pergamena/10 disabled:opacity-40"
        >
          Annulla
        </button>
      </div>
    </div>
  );
}
