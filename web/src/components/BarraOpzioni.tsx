// Le azioni disponibili in calce al thread: i bottoni del menu di SCENA composto
// dal motore. Si sceglie per INDICE, valido solo per lo snapshot corrente: il
// click porta anche `versione` e un click stantio viene risincronizzato.

import type { SnapshotVista } from "../api/tipi";
import { useScegliOpzione } from "../api/query";

export function BarraOpzioni({
  snapshot,
  versione,
  bloccata,
}: {
  snapshot: SnapshotVista;
  versione: number;
  bloccata: boolean;
}) {
  const scelta = useScegliOpzione();
  const disabilitata = bloccata || scelta.isPending;

  if (snapshot.opzioni.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {snapshot.opzioni.map((opzione) => (
        // `abilitata === false` = mossa senza mana o in ricarica: la voce RESTA
        // (gli indici non devono ballare fra snapshot), spenta. Il rifiuto vero
        // lo fa comunque il motore.
        <button
          key={opzione.indice}
          disabled={disabilitata || opzione.abilitata === false}
          onClick={() => scelta.mutate({ indice: opzione.indice, versione })}
          className="rounded border border-torcia/60 bg-torcia/10 px-4 py-2 font-bold text-torcia transition hover:bg-torcia/25 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {opzione.etichetta}
        </button>
      ))}
    </div>
  );
}
