// Il post del forum = un MessaggioGM: intestazione di scena (dove/come), corpo
// narrativo, esito della prova (tirata dal MOTORE, mai dall'AI), costo in tempo.
//
// Registro visivo alla Dungeon Crawler Carl: il GM è la VOCE DELLO SHOW
// (finestra con la sua insegna), la cronaca del bus è il LOG DI SISTEMA
// (monospazio, riga per riga), il bottino è il riquadro «OGGETTO OTTENUTO»
// (il momento-achievement dei LitRPG), i battiti fuori onda sono banner al
// neon. Prosa in serif: si legge come un romanzo, il resto come un HUD.

import type { MessaggioGM } from "../api/tipi";

function BadgeProva({ messaggio }: { messaggio: MessaggioGM }) {
  const prova = messaggio.prova;
  if (!prova) return null;
  const esito =
    prova.esito === null ? "in sospeso" : prova.esito ? "riuscita" : "fallita";
  const colore =
    prova.esito === null
      ? "border-pergamena/30 text-pergamena/70"
      : prova.esito
        ? "border-muschio/50 text-muschio"
        : "border-sangue/50 text-sangue";
  return (
    <span className={`rounded-full border px-2 py-0.5 font-hud text-[0.65rem] uppercase tracking-wider ${colore}`}>
      Prova {prova.classe} · {prova.stat} · {esito}
    </span>
  );
}

export function PostGM({ id, messaggio }: { id: number; messaggio: MessaggioGM }) {
  return (
    <article className="overflow-hidden rounded-lg border border-torcia/25 bg-pietra shadow-lg shadow-black/40">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-torcia/20 bg-torcia/10 px-4 py-2">
        <span className="titolo-insegna text-xs text-torcia">Il GM</span>
        <span className="font-hud text-xs tabular-nums text-pergamena/50">#{id + 1}</span>
        <span className="min-w-0 flex-1 truncate text-sm italic text-pergamena/75">
          {messaggio.dove} — {messaggio.come}
        </span>
        {messaggio.fallback && (
          <span className="etichetta-hud shrink-0 rounded border border-pergamena/30 px-2 py-0.5 text-pergamena/55">
            ripiego
          </span>
        )}
      </header>
      <div className="whitespace-pre-wrap px-5 py-4 text-[1.02rem] leading-relaxed">
        {messaggio.prosa}
      </div>
      {messaggio.snapshot.length > 0 && (
        <ul className="mx-4 mb-3 rounded border border-pergamena/10 bg-abisso/60 px-3 py-2 font-hud text-xs text-pergamena/70">
          {messaggio.snapshot.map((riga, i) => (
            <li key={i}>▸ {riga}</li>
          ))}
        </ul>
      )}
      <footer className="flex flex-wrap items-center gap-2 border-t border-torcia/15 px-4 py-2">
        <span className="rounded-full border border-torcia/40 px-2 py-0.5 font-hud text-[0.65rem] uppercase tracking-wider text-torcia/90">
          {messaggio.tempo.etichetta} · t{messaggio.tempo.tick_correnti}
          {messaggio.tempo.tick_spesi > 0 && ` (+${messaggio.tempo.tick_spesi})`}
        </span>
        <BadgeProva messaggio={messaggio} />
      </footer>
    </article>
  );
}

/** Una riga di cronaca del bus. Le righe SPECIALI hanno il loro riquadro:
 *  «✦ Bottino» = OGGETTO OTTENUTO (il momento-achievement), «➤» = varco. */
function RigaEvento({ riga }: { riga: string }) {
  if (riga.startsWith("✦")) {
    return (
      <div className="mx-auto w-fit max-w-full rounded border-2 border-torcia/60 bg-torcia/10 px-4 py-2 text-center shadow-[0_0_16px_rgba(245,158,11,0.25)]">
        <span className="etichetta-hud block text-torcia">Oggetto ottenuto</span>
        <span className="font-hud text-sm text-pergamena/90">{riga.slice(1).trim()}</span>
      </div>
    );
  }
  if (riga.startsWith("➤")) {
    return (
      <div className="mx-auto w-fit max-w-full rounded border border-show/50 bg-show/5 px-4 py-1.5 text-center font-hud text-sm text-show shadow-[0_0_14px_rgba(34,211,238,0.18)]">
        {riga.slice(1).trim()}
      </div>
    );
  }
  return (
    <p className="text-center font-hud text-xs text-pergamena/55">
      <span className="text-show/60">»</span> {riga}
    </p>
  );
}

export function PostEvento({ righe }: { righe: string[] }) {
  return (
    <div className="flex flex-col gap-1.5 px-6">
      {righe.map((riga, i) => (
        <RigaEvento key={i} riga={riga} />
      ))}
    </div>
  );
}

// I battiti FUORI ONDA (trailer d'apertura, targhetta del premio, epitaffio):
// prosa che non accompagna uno snapshot — il banner al neon della regia.
const ETICHETTE_PROSA: Record<string, string> = {
  apertura: "Trailer",
  premio: "Premio",
  epitaffio: "Epitaffio",
};

export function PostProsa({ righe, tipo }: { righe: string[]; tipo?: string }) {
  const etichetta = ETICHETTE_PROSA[tipo ?? ""] ?? "Fuori onda";
  return (
    <article className="rounded-lg border border-show/40 bg-show/5 px-4 py-3 shadow-[0_0_18px_rgba(34,211,238,0.12)]">
      <span className="etichetta-hud text-show">◤ {etichetta} · in onda ◢</span>
      {righe.map((riga, i) => (
        <p key={i} className="mt-1.5 whitespace-pre-wrap italic leading-relaxed text-pergamena/90">
          {riga}
        </p>
      ))}
    </article>
  );
}

/** Uno scambio del parlamentare: la battuta del crawler («…») + la risposta
 *  del canale scena. Dialogo, non cronaca. */
export function PostScena({ righe }: { righe: string[] }) {
  return (
    <article className="rounded-lg border border-muschio/30 bg-muschio/5 px-4 py-3">
      <span className="etichetta-hud text-muschio/90">Scena · dialogo</span>
      {righe.map((riga, i) => (
        <p
          key={i}
          className={`mt-1.5 whitespace-pre-wrap leading-relaxed ${
            riga.startsWith("«") ? "font-bold text-pergamena" : "italic text-pergamena/85"
          }`}
        >
          {riga}
        </p>
      ))}
    </article>
  );
}
