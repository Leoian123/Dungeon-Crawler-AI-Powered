// Creazione di un nuovo crawler: nome (l'etichetta dello slot) + seed + GM.
// La chiave LLM non passa MAI di qui: "live" è solo un'etichetta, la chiave
// vive nell'ambiente del server (PLK §4).

import { useState } from "react";
import type { GmScelta } from "../api/tipi";
import { useApriPartita, useAssets } from "../api/query";

// Interruttore ESPLICITO al posto della checkbox nativa (playtest a 3 persone
// 2026-08-27, P2: lo stato visivo della checkbox sul tema scuro veniva letto
// al contrario — un giocatore ha giocato la daily credendo di avere il SUO
// seed, altri due il contrario). Lo stato è una parola, non un pixel.
function Interruttore({
  attivo,
  su,
  disabled,
  children,
}: {
  attivo: boolean;
  su: (v: boolean) => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => su(!attivo)}
      className={`flex items-center gap-2 rounded border px-3 py-2 text-left text-sm transition disabled:opacity-40 ${
        attivo
          ? "border-torcia bg-torcia/15"
          : "border-pergamena/25 hover:bg-pergamena/10"
      }`}
    >
      <span
        className={`shrink-0 rounded-full border px-2 py-0.5 font-hud text-[10px] font-bold uppercase tracking-wider ${
          attivo
            ? "border-torcia text-torcia"
            : "border-pergamena/40 text-pergamena/50"
        }`}
      >
        {attivo ? "attiva" : "spenta"}
      </span>
      <span>{children}</span>
    </button>
  );
}

export function CreaCrawler({
  gm,
  onAnnulla,
}: {
  gm: GmScelta;
  onAnnulla: () => void;
}) {
  const [nome, setNome] = useState("");
  const [seed, setSeed] = useState(1);
  const [stagione, setStagione] = useState<string>("");
  const [daily, setDaily] = useState(false);
  const [infestata, setInfestata] = useState(false);
  const stagioni = useAssets("stagioni");
  const disponibili = (stagioni.data?.asset ?? []).filter((s) => s.valido);
  const apri = useApriPartita();
  const valido = nome.trim().length > 0;

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-torcia/40 bg-pietra p-4">
      <h3 className="font-bold text-torcia">Nuovo crawler</h3>
      <label className="flex flex-col gap-1 text-sm">
        Nome (l'etichetta dello slot)
        <input
          autoFocus
          value={nome}
          disabled={apri.isPending}
          onChange={(e) => setNome(e.target.value)}
          placeholder="Es. Donut"
          className="rounded border border-pergamena/25 bg-abisso px-3 py-2 text-pergamena placeholder:text-pergamena/40 focus:border-torcia/60 focus:outline-none"
        />
      </label>
      {/* Col daily attivo il campo seed SPARISCE (non solo disabilitato):
          un numero visibile ma ignorato dal server è una promessa falsa. */}
      {daily ? (
        <p className="rounded border border-torcia/30 bg-torcia/5 px-3 py-2 text-xs text-pergamena/70">
          Il seed lo calcola il server dalla data di oggi: stesso dungeon per
          tutti i crawler del giorno. Il numero effettivo apparirà nella card.
        </p>
      ) : (
        <label className="flex flex-col gap-1 text-sm">
          Seed della discesa
          <input
            type="number"
            value={seed}
            disabled={apri.isPending}
            onChange={(e) => setSeed(Number(e.target.value) || 0)}
            className="rounded border border-pergamena/25 bg-abisso px-3 py-2 text-pergamena focus:border-torcia/60 focus:outline-none disabled:opacity-40"
          />
        </label>
      )}
      <Interruttore attivo={daily} su={setDaily} disabled={apri.isPending}>
        <b className="text-torcia">Run del giorno</b> — il seed lo detta la
        data: stesso dungeon per tutti i crawler di oggi
      </Interruttore>
      <Interruttore attivo={infestata} su={setInfestata} disabled={apri.isPending}>
        <b className="text-torcia">Dungeon infestato</b> — le tracce dei tuoi
        crawler caduti appaiono come lore
      </Interruttore>
      <label className="flex flex-col gap-1 text-sm">
        Stagione dello show
        <select
          value={stagione}
          disabled={apri.isPending}
          onChange={(e) => setStagione(e.target.value)}
          className="rounded border border-pergamena/25 bg-abisso px-3 py-2 text-pergamena focus:border-torcia/60 focus:outline-none"
        >
          <option value="">— quella di default —</option>
          {disponibili.map((s) => (
            <option key={s.slug} value={s.slug}>
              {s.etichetta} ({s.origine})
            </option>
          ))}
        </select>
      </label>
      <div className="flex gap-2">
        <button
          disabled={!valido || apri.isPending}
          onClick={() =>
            apri.mutate({
              gm,
              nuovo: {
                nome: nome.trim(),
                seed,
                stagione: stagione || null,
                daily,
                infestata,
              },
            })
          }
          className="rounded bg-torcia px-4 py-2 font-bold text-abisso transition hover:bg-torcia/90 disabled:opacity-40"
        >
          {apri.isPending ? "Discesa in corso…" : "Scendi nel dungeon"}
        </button>
        <button
          disabled={apri.isPending}
          onClick={onAnnulla}
          className="rounded border border-pergamena/30 px-4 py-2 text-pergamena/70 transition hover:bg-pergamena/10 disabled:opacity-40"
        >
          Annulla
        </button>
      </div>
    </div>
  );
}
