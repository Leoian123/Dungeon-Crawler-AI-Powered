// L'inventario nel pannello laterale: una riga per fonte posseduta, con
// Indossa/Togli che passano dalle PORTE della sessione (il phase-gate resta
// del motore — in scontro l'host risponde 409 e i bottoni sono spenti).

import { useEquipaggia, useTogli, useZaino } from "../api/query";

export function PannelloZaino({
  versione,
  bloccato,
}: {
  versione: number;
  bloccato: boolean;
}) {
  const zaino = useZaino(true);
  const indossa = useEquipaggia();
  const togli = useTogli();
  const fonti = zaino.data?.fonti ?? [];
  const occupato = bloccato || indossa.isPending || togli.isPending;

  return (
    <div className="flex flex-col gap-1 rounded-lg border border-pergamena/20 bg-pietra p-3">
      <h3 className="text-xs font-bold uppercase tracking-wider text-pergamena/60">
        Zaino
      </h3>
      {fonti.length === 0 && (
        <p className="text-xs italic text-pergamena/40">
          Vuoto: il bottino arriva dagli scontri vinti.
        </p>
      )}
      {fonti.map((voce) => (
        <div
          key={voce.fonte}
          className="flex items-center justify-between gap-2 text-sm"
        >
          <span
            className={voce.indossata ? "font-bold text-pergamena" : "text-pergamena/75"}
          >
            {voce.indossata && <span className="text-muschio">▣ </span>}
            {voce.etichetta}
          </span>
          <button
            disabled={occupato}
            onClick={() =>
              (voce.indossata ? togli : indossa).mutate({
                fonte: voce.fonte,
                versione,
              })
            }
            className={`rounded border px-2 py-0.5 text-xs transition disabled:opacity-40 ${
              voce.indossata
                ? "border-pergamena/30 text-pergamena/70 hover:bg-pergamena/10"
                : "border-muschio/50 text-muschio hover:bg-muschio/10"
            }`}
          >
            {voce.indossata ? "Togli" : "Indossa"}
          </button>
        </div>
      ))}
    </div>
  );
}
