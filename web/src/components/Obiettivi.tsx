// Obiettivi (nodo O4) — due superfici, per lo STANDARD di architettura della
// Partita (2026-08-26): la sidebar è il CRUSCOTTO DI STATO VIVO (solo ciò che
// serve a decidere la prossima azione), la CONSULTAZIONE vive in una vista
// secondaria con la sua superficie piena. Quindi: un CHIP compatto in sidebar
// (conteggio + box in coda, apre l'albo) e l'ALBO a tutta pagina (vista
// "albo" della Partita). Il velo lo mette il backend (ObiettivoVista): qui si
// mostra e basta, nessuna deduzione.

import { useObiettivi } from "../api/query";

/** Il chip di sidebar: una riga di stato, mai un elenco. */
export function ChipObiettivi({ apri }: { apri: () => void }) {
  const query = useObiettivi(true);
  const obiettivi = query.data?.obiettivi ?? [];
  const inCoda = query.data?.box_in_coda ?? 0;
  const sbloccati = obiettivi.filter((o) => o.sbloccato).length;
  if (obiettivi.length === 0) return null;

  return (
    <button
      onClick={apri}
      className="flex items-center justify-between gap-2 rounded-lg border border-pergamena/20 bg-pietra px-3 py-2 text-left transition hover:border-torcia/40 hover:bg-pietra/80"
      title="Apri l'albo degli obiettivi"
    >
      <span className="etichetta-hud text-pergamena/60">
        Obiettivi{" "}
        <span className="text-torcia/80">
          {sbloccati}/{obiettivi.length}
        </span>
      </span>
      <span className="flex items-center gap-2">
        {inCoda > 0 && (
          <span className="rounded border border-torcia/40 bg-torcia/10 px-1.5 font-hud text-[0.65rem] text-torcia/90">
            ◇ {inCoda} box
          </span>
        )}
        <span className="font-hud text-xs text-pergamena/40">→</span>
      </span>
    </button>
  );
}

/** L'albo a superficie piena: la consultazione, non un riquadro appeso. */
export function AlboObiettivi() {
  const query = useObiettivi(true);
  const obiettivi = query.data?.obiettivi ?? [];
  const inCoda = query.data?.box_in_coda ?? 0;
  const sbloccati = obiettivi.filter((o) => o.sbloccato);
  const velati = obiettivi.filter((o) => !o.sbloccato);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="titolo-insegna text-lg text-torcia">
          Albo degli obiettivi
        </h2>
        <span className="font-hud text-sm text-pergamena/50">
          {sbloccati.length}/{obiettivi.length}
        </span>
      </div>
      {inCoda > 0 && (
        <p className="rounded border border-torcia/40 bg-torcia/10 px-3 py-2 font-hud text-sm text-torcia/90">
          ◇ Box in coda: {inCoda} — si aprono solo in una safe room.
        </p>
      )}
      {obiettivi.length === 0 && (
        <p className="font-hud text-sm italic text-pergamena/40">
          Il sistema non ha annunciato obiettivi per questa run.
        </p>
      )}

      {sbloccati.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {sbloccati.map((o) => (
            <article
              key={o.slug}
              className="rounded-lg border border-torcia/40 bg-torcia/5 p-3 shadow-[0_0_12px_rgba(245,158,11,0.12)]"
            >
              <h3 className="mb-1 font-bold text-torcia/90">★ {o.titolo}</h3>
              <p className="font-hud text-xs leading-snug text-pergamena/75">
                {o.testo}
              </p>
              <p className="mt-1.5 font-hud text-xs text-muschio/90">
                {o.ricompensa_testo}
              </p>
            </article>
          ))}
        </div>
      )}

      {velati.length > 0 && (
        <div>
          <h3 className="etichetta-hud mb-2 text-pergamena/45">
            Ancora velati · {velati.length}
          </h3>
          <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
            {velati.map((o) => (
              <span
                key={o.slug}
                className="truncate rounded border border-pergamena/10 bg-pietra px-2 py-1 font-hud text-xs text-pergamena/50"
                title={o.titolo}
              >
                ☆ {o.titolo}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
