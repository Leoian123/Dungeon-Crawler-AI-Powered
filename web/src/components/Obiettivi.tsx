// Il pannello Obiettivi (nodo O4): l'elenco VELATO della run. Il velo lo mette
// il backend (ObiettivoVista: titolo sempre, testo/ricompensa solo a sblocco
// avvenuto) — qui si mostra e basta, nessuna logica di deduzione. In coda, il
// promemoria delle box che aspettano una safe room (si aprono SOLO lì).

import { useObiettivi } from "../api/query";

export function PannelloObiettivi() {
  const query = useObiettivi(true);
  const obiettivi = query.data?.obiettivi ?? [];
  const inCoda = query.data?.box_in_coda ?? 0;
  const sbloccati = obiettivi.filter((o) => o.sbloccato).length;

  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-pergamena/20 bg-pietra p-3">
      <h3 className="etichetta-hud text-pergamena/60">
        Obiettivi{" "}
        <span className="text-pergamena/35">
          · {sbloccati}/{obiettivi.length}
        </span>
      </h3>
      {obiettivi.length === 0 && (
        <p className="font-hud text-[0.7rem] italic text-pergamena/40">
          Il sistema non ha annunciato obiettivi per questa run.
        </p>
      )}
      {obiettivi.map((o) => (
        <div key={o.slug} className="min-w-0">
          <span
            className={`block truncate text-sm ${
              o.sbloccato ? "font-bold text-torcia/90" : "text-pergamena/50"
            }`}
            title={o.titolo}
          >
            {o.sbloccato ? "★ " : "☆ "}
            {o.titolo}
          </span>
          {o.sbloccato && (
            <p className="font-hud text-[0.7rem] leading-snug text-pergamena/65">
              {o.testo}{" "}
              <span className="text-muschio/90">{o.ricompensa_testo}</span>
            </p>
          )}
        </div>
      ))}
      {inCoda > 0 && (
        <p className="mt-1 rounded border border-torcia/40 bg-torcia/10 px-2 py-1 font-hud text-[0.7rem] text-torcia/90">
          Box in coda: {inCoda} — si aprono in safe room
        </p>
      )}
    </div>
  );
}
