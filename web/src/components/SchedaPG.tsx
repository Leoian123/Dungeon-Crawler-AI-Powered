// La scheda del PG (SchedaVista) + il pannello party A SLOT: oggi il motore ha
// il solo protagonista (singleton), gli slot vuoti sono il seam per il party
// futuro — la UI è pronta, il motore non si tocca.

import type { SchedaVista } from "../api/tipi";
import { useScheda } from "../api/query";

function BarraHp({ hp, hpMax }: { hp: number; hpMax: number }) {
  const frazione = hpMax > 0 ? hp / hpMax : 0;
  const colore =
    frazione > 0.5 ? "bg-muschio" : frazione > 0.25 ? "bg-torcia" : "bg-sangue";
  return (
    <div className="flex items-center gap-2">
      <div className="h-2.5 flex-1 overflow-hidden rounded bg-abisso">
        <div
          className={`h-full ${colore} transition-all duration-300`}
          style={{ width: `${Math.round(frazione * 100)}%` }}
        />
      </div>
      <span className="font-mono text-xs text-pergamena/80">
        {hp}/{hpMax}
      </span>
    </div>
  );
}

export function SchedaPG({ scheda }: { scheda: SchedaVista }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-pergamena/20 bg-pietra p-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-bold text-torcia">{scheda.nome}</span>
        <span className="text-xs text-pergamena/60">
          Piano {scheda.livello} · t{scheda.tick_piano}
        </span>
      </div>
      <BarraHp hp={scheda.hp} hpMax={scheda.hp_max} />
      {scheda.descrittori.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {scheda.descrittori.map((d, i) => (
            <span
              key={i}
              className="rounded-full border border-pergamena/25 px-2 py-0.5 text-xs text-pergamena/80"
            >
              {d}
            </span>
          ))}
        </div>
      )}
      <div className="grid grid-cols-3 gap-x-3 gap-y-0.5 font-mono text-xs">
        {Object.entries(scheda.primarie).map(([nome, valore]) => (
          <span key={nome} className="text-pergamena/80">
            {nome.slice(0, 3).toUpperCase()} <b className="text-pergamena">{valore}</b>
          </span>
        ))}
        {scheda.primarie_occulte.map((nome) => (
          <span key={nome} className="text-pergamena/50">
            {nome.slice(0, 3).toUpperCase()} <b>?</b>
          </span>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-x-3 gap-y-0.5 border-t border-pergamena/10 pt-1 font-mono text-xs text-pergamena/60">
        {Object.entries(scheda.derivate).map(([nome, valore]) => (
          <span key={nome}>
            {nome} <b className="text-pergamena/80">{valore}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

// Dimensione del party (gioco single player: più personaggi, un solo giocatore).
// L'API restituisce `party` come LISTA: la UI rende tutti i membri che il motore
// consegna — oggi il protagonista, domani i compagni — e riempie il resto di
// slot liberi fino a questo tetto.
const SLOT_PARTY = 4;

export function PannelloParty() {
  const scheda = useScheda(true);
  const party = scheda.data?.party ?? [];
  const liberi = Math.max(0, SLOT_PARTY - party.length);
  return (
    <div className="flex flex-col gap-2">
      <h2 className="text-sm font-bold uppercase tracking-wider text-pergamena/60">
        Party {party.length}/{SLOT_PARTY}
      </h2>
      {party.map((pg) => (
        <SchedaPG key={pg.uuid} scheda={pg} />
      ))}
      {Array.from({ length: liberi }, (_, i) => (
        <div
          key={i}
          className="flex min-h-14 items-center justify-center rounded-lg border border-dashed border-pergamena/15 text-xs text-pergamena/40"
        >
          slot libero
        </div>
      ))}
    </div>
  );
}
