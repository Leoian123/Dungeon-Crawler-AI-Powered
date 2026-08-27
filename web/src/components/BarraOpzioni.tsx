// Le azioni disponibili in calce al thread: i bottoni del menu di SCENA composto
// dal motore. Si sceglie per INDICE, valido solo per lo snapshot corrente: il
// click porta anche `versione` e un click stantio viene risincronizzato.
//
// Il COLORE è il tipo d'azione (contratto `TipoAzione`, mai il testo): rosso
// chiama lo scontro, verde il dialogo, ambra il movimento, azzurro il tempo —
// il menu si legge a colpo d'occhio, come un HUD.

import type { SnapshotVista } from "../api/tipi";
import { useScegliOpzione } from "../api/query";

const STILE_TIPO: Record<string, string> = {
  combatti: "border-sangue/60 bg-sangue/10 text-sangue hover:bg-sangue/20 hover:shadow-[0_0_12px_rgba(248,113,113,0.35)]",
  scappa: "border-pergamena/40 bg-pergamena/5 text-pergamena/85 hover:bg-pergamena/15",
  parlamenta: "border-muschio/60 bg-muschio/10 text-muschio hover:bg-muschio/20 hover:shadow-[0_0_12px_rgba(74,222,128,0.3)]",
  muovi: "border-torcia/60 bg-torcia/10 text-torcia hover:bg-torcia/20",
  scendi: "border-torcia/70 bg-torcia/15 text-torcia hover:bg-torcia/25 hover:shadow-[0_0_12px_rgba(245,158,11,0.35)]",
  attraversa: "border-show/60 bg-show/10 text-show hover:bg-show/20 hover:shadow-[0_0_12px_rgba(34,211,238,0.3)]",
  riposa: "border-sigillo/60 bg-sigillo/10 text-sigillo hover:bg-sigillo/20",
  passa: "border-sigillo/40 bg-sigillo/5 text-sigillo/85 hover:bg-sigillo/15",
  smaltisci: "border-sigillo/40 bg-sigillo/5 text-sigillo/85 hover:bg-sigillo/15",
};
const STILE_DEFAULT =
  "border-torcia/60 bg-torcia/10 text-torcia hover:bg-torcia/20";

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
    <div className="flex flex-col gap-1.5">
      {/* Scena sociale aperta (playtest 2026-08-27): il menu resta operativo
          — scegliere è LEGITTIMO e tronca la trattativa nel motore — ma lo
          stato va DETTO, non lasciato indovinare dal composer sotto. */}
      {snapshot.scena_aperta && (
        <span className="font-hud text-[0.7rem] uppercase tracking-widest text-muschio/80">
          ⚠ trattativa in corso — scegliere un'azione tronca la conversazione
        </span>
      )}
      <div
        className={`flex flex-wrap gap-2 ${
          snapshot.scena_aperta ? "opacity-70" : ""
        }`}
      >
      {snapshot.opzioni.map((opzione) => (
        // `abilitata === false` = mossa senza mana o in ricarica: la voce RESTA
        // (gli indici non devono ballare fra snapshot), spenta. Il rifiuto vero
        // lo fa comunque il motore.
        <button
          key={opzione.indice}
          disabled={disabilitata || opzione.abilitata === false}
          onClick={() => scelta.mutate({ indice: opzione.indice, versione })}
          className={`rounded border-2 px-4 py-2 font-hud text-sm font-bold uppercase tracking-wide transition disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:shadow-none ${
            STILE_TIPO[opzione.tipo] ?? STILE_DEFAULT
          }`}
        >
          {opzione.etichetta}
          {/* Il Lv della skill che governa la mossa (nodo S): DATO
              sull'opzione, vestito qui — la pratica si vede al momento
              della scelta. Lv 1 tace. */}
          {(opzione.livello ?? 1) > 1 && (
            <span className="ml-1.5 rounded border border-current/40 px-1 text-[0.65rem] opacity-80">
              Lv {opzione.livello}
            </span>
          )}
        </button>
      ))}
      </div>
    </div>
  );
}
