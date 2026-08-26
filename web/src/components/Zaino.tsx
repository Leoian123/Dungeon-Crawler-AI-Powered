// L'inventario nel pannello laterale: una riga per fonte posseduta. Il DATO
// (tipo, grado, fattura, effetto) arriva tipato dal backend (§B-4,
// `OggettoVista`): qui si VESTE — badge di grado, tacca di fattura, e
// l'azione giusta per tipo (Indossa/Togli per l'equipaggiabile, Usa per il
// consumabile). Mai sniffing sul nome.
//
// Layout anti-deformazione (playtest 2026-08-20): nome su UNA riga troncata
// (descrizione piena nel title), bottone shrink-0 — la colonna non si
// accartoccia mai, qualunque targhetta esca dalla fabbrica.

import { useEquipaggia, useTogli, useUsa, useZaino } from "../api/query";
import type { VoceZaino } from "../api/tipi";

/** La tavolozza dei GRADI (vestizione pura: il valore è dato del motore). */
const COLORE_GRADO: Record<string, string> = {
  bronzo: "border-amber-700/50 text-amber-500/90",
  argento: "border-slate-400/50 text-slate-300",
  oro: "border-yellow-500/60 text-yellow-400",
  platino: "border-cyan-300/50 text-cyan-200",
  leggendario: "border-orange-500/60 text-orange-400",
  celestiale: "border-fuchsia-400/60 text-fuchsia-300",
};

function BadgeGrado({ grado }: { grado: string }) {
  if (!grado) return null;
  const colore = COLORE_GRADO[grado] ?? "border-pergamena/30 text-pergamena/60";
  return (
    <span
      className={`shrink-0 rounded border px-1 font-hud text-[0.55rem] font-bold uppercase tracking-wider ${colore}`}
    >
      {grado}
    </span>
  );
}

/** La tacca di fattura (§B-2): scarto e pregiato si annunciano, l'onesto
 *  tace — il backend manda "" e qui non compare nulla. */
function TaccaFattura({ qualita }: { qualita: string }) {
  if (qualita === "pregiato")
    return <span className="shrink-0 text-torcia" title="Fattura pregiata">✦</span>;
  if (qualita === "scarto")
    return (
      <span className="shrink-0 text-pergamena/35" title="Fattura di scarto">▽</span>
    );
  return null;
}

function RigaZaino({
  voce,
  versione,
  occupato,
}: {
  voce: VoceZaino;
  versione: number;
  occupato: boolean;
}) {
  const indossa = useEquipaggia();
  const togli = useTogli();
  const usa = useUsa();
  const consumabile = voce.tipo === "consumabile";
  const indossata = voce.indossata;

  const azione = consumabile
    ? { verbo: "Usa", mutazione: usa }
    : indossata
      ? { verbo: "Togli", mutazione: togli }
      : { verbo: "Indossa", mutazione: indossa };

  return (
    <div
      className="flex min-w-0 items-center gap-1.5"
      title={voce.descrizione || voce.etichetta}
    >
      <span
        className={`min-w-0 flex-1 truncate text-sm ${
          indossata ? "font-bold text-torcia/90" : "text-pergamena/75"
        }`}
      >
        {indossata && <span className="text-muschio">▣ </span>}
        {voce.etichetta}
      </span>
      <TaccaFattura qualita={voce.qualita} />
      <BadgeGrado grado={voce.grado} />
      <button
        disabled={occupato}
        onClick={() => azione.mutazione.mutate({ fonte: voce.fonte, versione })}
        className={`shrink-0 rounded border px-2 py-0.5 font-hud text-[0.65rem] font-bold uppercase tracking-wider transition disabled:opacity-40 ${
          consumabile
            ? "border-show/50 text-show hover:bg-show/15"
            : indossata
              ? "border-pergamena/30 text-pergamena/70 hover:bg-pergamena/10"
              : "border-muschio/50 text-muschio hover:bg-muschio/15"
        }`}
      >
        {azione.verbo}
      </button>
    </div>
  );
}

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
  const usa = useUsa();
  const fonti = zaino.data?.fonti ?? [];
  const occupato =
    bloccato || indossa.isPending || togli.isPending || usa.isPending;

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
        <RigaZaino
          key={voce.fonte}
          voce={voce}
          versione={versione}
          occupato={occupato}
        />
      ))}
    </div>
  );
}
