// Il post del forum = un MessaggioGM: intestazione di scena (dove/come), corpo
// narrativo, esito della prova (tirata dal MOTORE, mai dall'AI), costo in tempo.

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
    <span className={`rounded-full border px-2 py-0.5 text-xs ${colore}`}>
      Prova {prova.classe} · {prova.stat} · {esito}
    </span>
  );
}

export function PostGM({ id, messaggio }: { id: number; messaggio: MessaggioGM }) {
  return (
    <article className="rounded-lg border border-pergamena/15 bg-pietra shadow-lg">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-pergamena/10 px-4 py-2">
        <span className="font-bold text-torcia">Il GM</span>
        <span className="text-sm text-pergamena/70">#{id + 1}</span>
        <span className="text-sm italic text-pergamena/80">
          {messaggio.dove} — {messaggio.come}
        </span>
        {messaggio.fallback && (
          <span className="rounded-full border border-pergamena/30 px-2 py-0.5 text-xs text-pergamena/60">
            turno di ripiego
          </span>
        )}
      </header>
      <div className="whitespace-pre-wrap px-4 py-3 leading-relaxed">
        {messaggio.prosa}
      </div>
      {messaggio.snapshot.length > 0 && (
        <ul className="mx-4 mb-3 list-inside list-disc rounded bg-abisso/50 px-3 py-2 text-sm text-pergamena/75">
          {messaggio.snapshot.map((riga, i) => (
            <li key={i}>{riga}</li>
          ))}
        </ul>
      )}
      <footer className="flex flex-wrap items-center gap-2 border-t border-pergamena/10 px-4 py-2">
        <span className="rounded-full border border-torcia/40 px-2 py-0.5 text-xs text-torcia/90">
          {messaggio.tempo.etichetta} · t{messaggio.tempo.tick_correnti}
          {messaggio.tempo.tick_spesi > 0 && ` (+${messaggio.tempo.tick_spesi})`}
        </span>
        <BadgeProva messaggio={messaggio} />
      </footer>
    </article>
  );
}

export function PostEvento({ righe }: { righe: string[] }) {
  return (
    <div className="px-6 text-center text-sm italic text-pergamena/60">
      {righe.map((riga, i) => (
        <p key={i}>— {riga} —</p>
      ))}
    </div>
  );
}
