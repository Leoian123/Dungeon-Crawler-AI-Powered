// L'inventario nel pannello laterale: una riga per fonte posseduta, con
// Indossa/Togli che passano dalle PORTE della sessione (il phase-gate resta
// del motore — in scontro l'host risponde 409 e i bottoni sono spenti).
//
// Layout anti-deformazione (playtest 2026-08-20): nome su UNA riga troncata
// (il titolo pieno vive nel title), bottone shrink-0 — la colonna non si
// accartoccia mai, qualunque targhetta esca dalla fabbrica.

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
    <div className="flex flex-col gap-1.5 rounded-lg border border-pergamena/20 bg-pietra p-3">
      <h3 className="etichetta-hud text-pergamena/60">
        Zaino <span className="text-pergamena/35">· {fonti.length}</span>
      </h3>
      {fonti.length === 0 && (
        <p className="font-hud text-[0.7rem] italic text-pergamena/40">
          Vuoto: il bottino arriva dagli scontri vinti.
        </p>
      )}
      {fonti.map((voce) => (
        <div
          key={voce.fonte}
          className="flex min-w-0 items-center gap-2"
          title={voce.etichetta}
        >
          <span
            className={`min-w-0 flex-1 truncate text-sm ${
              voce.indossata ? "font-bold text-torcia/90" : "text-pergamena/75"
            }`}
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
            className={`shrink-0 rounded border px-2 py-0.5 font-hud text-[0.65rem] font-bold uppercase tracking-wider transition disabled:opacity-40 ${
              voce.indossata
                ? "border-pergamena/30 text-pergamena/70 hover:bg-pergamena/10"
                : "border-muschio/50 text-muschio hover:bg-muschio/15"
            }`}
          >
            {voce.indossata ? "Togli" : "Indossa"}
          </button>
        </div>
      ))}
    </div>
  );
}
