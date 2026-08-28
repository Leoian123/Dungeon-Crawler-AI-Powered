// CALIBRAZIONE (GM mode): il pannello di bilanciamento — TUTTI i numeri §11 del
// gioco (coefficienti di combattimento, tabelle, probabilità, tempo, prove,
// protagonista, profili dei nemici) come dato editabile. Ogni voce mostra la
// SPIEGAZIONE del proprio impatto (dal catalogo del motore), default, dominio e
// stato di override; per i nemici un pannello Anteprima calcola i numeri
// risultanti coi valori freschi. La verità della validazione è il server (422):
// il client manda il valore grezzo e rilegge. Gli override applicati valgono
// dal PROSSIMO avvio dell'host; "Salva su disco" li rende persistenti.

import { useMemo, useState } from "react";
import type { VoceCalibrazione } from "../api/tipi";
import {
  useAnteprimaCalibrazione,
  useAzzeraCalibrazione,
  useCalibrazione,
  useImpostaCalibrazione,
  useSalvaCalibrazione,
} from "../api/query";

import { CLS_INPUT } from "./ui";

// --- Una voce del catalogo -------------------------------------------------------

function CardVoce({ voce }: { voce: VoceCalibrazione }) {
  const imposta = useImpostaCalibrazione();
  const azzera = useAzzeraCalibrazione();
  const [testo, setTesto] = useState(String(voce.valore));

  const commit = (valore: string) => {
    if (valore === String(voce.valore)) return;
    imposta.mutate({ chiave: voce.chiave, valore });
  };

  return (
    <div className="flex flex-col gap-1 rounded-lg border border-pergamena/20 bg-pietra p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-bold text-pergamena">{voce.etichetta}</span>
        {voce.tipo === "scelta" ? (
          <select
            value={String(voce.valore)}
            onChange={(e) => commit(e.target.value)}
            className={CLS_INPUT}
          >
            {voce.scelte.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        ) : (
          <input
            type={voce.tipo === "testo" ? "text" : "number"}
            step={voce.tipo === "int" ? 1 : "any"}
            value={testo}
            onChange={(e) => setTesto(e.target.value)}
            onBlur={() => commit(testo)}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
            className={`${CLS_INPUT} w-36`}
          />
        )}
        {voce.unita && <span className="text-xs text-pergamena/50">{voce.unita}</span>}
        <span
          className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider ${
            voce.override
              ? "border-torcia/60 text-torcia"
              : "border-pergamena/30 text-pergamena/50"
          }`}
        >
          {voce.override ? "modificato" : "default"}
        </span>
        <span className="text-xs text-pergamena/50">
          default {String(voce.default)} · {voce.dominio}
        </span>
        <button
          disabled={!voce.override || azzera.isPending}
          onClick={() => azzera.mutate({ chiave: voce.chiave })}
          className="ml-auto rounded border border-pergamena/30 px-2 py-0.5 text-xs text-pergamena/70 transition hover:bg-pergamena/10 disabled:opacity-30"
        >
          Reset
        </button>
      </div>
      <p className="text-sm text-pergamena/70">{voce.spiegazione}</p>
    </div>
  );
}

// --- Anteprima dei numeri risultanti (solo nemici) -------------------------------

function Kv({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="rounded border border-pergamena/20 bg-pietra px-2.5 py-1.5">
      <span className="block text-[10px] uppercase tracking-wider text-pergamena/50">{k}</span>
      <span className="text-sm text-pergamena">{v}</span>
    </div>
  );
}

function AnteprimaNemico({ archetipo, gradi }: { archetipo: string; gradi: string[] }) {
  const [grado, setGrado] = useState(gradi[0] ?? "bronzo");
  const [livello, setLivello] = useState(1);
  const anteprima = useAnteprimaCalibrazione(archetipo, grado, livello);
  const a = anteprima.data;

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-muschio/40 bg-abisso p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-bold text-muschio">Anteprima numeri risultanti</span>
        <label className="text-pergamena/60">grado</label>
        <select value={grado} onChange={(e) => setGrado(e.target.value)} className={CLS_INPUT}>
          {gradi.map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </select>
        <label className="text-pergamena/60">livello</label>
        <input
          type="number"
          min={1}
          value={livello}
          onChange={(e) => setLivello(Math.max(1, Number(e.target.value) || 1))}
          className={`${CLS_INPUT} w-20`}
        />
      </div>
      {a ? (
        <div className="flex flex-wrap gap-2">
          <Kv
            k="Primarie"
            v={`FRZ ${a.primarie.forza} · DES ${a.primarie.destrezza} · COS ${a.primarie.costituzione} · INT ${a.primarie.intelligenza} · DIF ${a.primarie.difesa} · SAG ${a.primarie.saggezza} · FRT ${a.primarie.fortuna}`}
          />
          <Kv k="max HP" v={a.max_hp} />
          <Kv k="atk_eff" v={a.atk_eff} />
          <Kv k="def_eff (cent.)" v={a.def_eff_centesimi} />
          <Kv k="eva_eff" v={a.eva_eff} />
          <Kv k="acc_fis_eff" v={a.acc_fis_eff} />
          <Kv k="acc_mag_eff" v={a.acc_mag_eff} />
          <Kv
            k="geometria"
            v={`${a.geometria.armatura} / ${a.geometria.taglia} / ${a.geometria.arma}`}
          />
          <Kv
            k="mult danno"
            v={`mischia ${a.resistenze_mult.mischia} · fuoco ${a.resistenze_mult.fuoco} · veleno ${a.resistenze_mult.veleno}`}
          />
        </div>
      ) : (
        <p className="text-sm italic text-pergamena/50">
          {anteprima.isError ? "Anteprima non disponibile." : "Calcolo in corso…"}
        </p>
      )}
    </div>
  );
}

// --- La pagina -------------------------------------------------------------------

const SOTTO_NEMICO = ["Statistiche", "Geometria", "Resistenze"] as const;

export function Calibrazione() {
  const vista = useCalibrazione();
  const salva = useSalvaCalibrazione();
  const [gruppo, setGruppo] = useState<string | null>(null);

  const dati = vista.data;
  const gruppiGlobali = useMemo(() => {
    const visti: string[] = [];
    for (const v of dati?.voci ?? [])
      if (v.sezione === "globale" && !visti.includes(v.gruppo)) visti.push(v.gruppo);
    return visti;
  }, [dati]);

  if (vista.isPending)
    return <p className="py-16 text-center italic text-pergamena/60">Apro il catalogo §11…</p>;
  if (vista.isError || !dati)
    return (
      <p className="py-16 text-center italic text-pergamena/60">
        L'host web non risponde: la calibrazione vive sul server.
      </p>
    );

  const sel = gruppo ?? `nemico:${dati.archetipi[0]?.archetipo ?? ""}`;
  const [sezione, chiave] = sel.split(/:(.*)/s);
  const nModificati = dati.voci.filter((v) => v.override).length;
  const voci = dati.voci.filter((v) => v.sezione === sezione && v.gruppo === chiave);

  const vociNav = (id: string, etichetta: string) => (
    <button
      key={id}
      onClick={() => setGruppo(id)}
      className={`rounded px-2.5 py-1 text-left text-sm transition ${
        sel === id
          ? "bg-torcia/15 font-bold text-torcia"
          : "text-pergamena/70 hover:bg-pergamena/10"
      }`}
    >
      {etichetta}
    </button>
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-pergamena/20 bg-pietra px-3 py-2">
        <p className="text-sm text-pergamena/70">
          Ogni voce spiega il proprio impatto; le modifiche valgono dal{" "}
          <b className="text-pergamena">prossimo avvio dell'host</b> (l'anteprima dei nemici è
          invece immediata). Override → <code className="text-xs">{dati.percorso_override}</code>
        </p>
        <button
          disabled={salva.isPending}
          onClick={() => salva.mutate()}
          className="ml-auto shrink-0 rounded bg-torcia px-4 py-1.5 font-bold text-abisso transition hover:bg-torcia/90 disabled:opacity-40"
        >
          Salva su disco{nModificati > 0 ? ` (${nModificati})` : ""}
        </button>
      </div>

      <div className="flex flex-col gap-4 md:flex-row md:items-start">
        <aside className="flex shrink-0 flex-col gap-0.5 md:sticky md:top-4 md:w-60">
          <h3 className="px-2.5 pt-1 text-xs uppercase tracking-wider text-pergamena/50">
            Nemici
          </h3>
          {dati.archetipi.map((a) => vociNav(`nemico:${a.archetipo}`, a.titolo))}
          <h3 className="px-2.5 pt-3 text-xs uppercase tracking-wider text-pergamena/50">
            Coefficienti globali §11
          </h3>
          {gruppiGlobali.map((c) => vociNav(`globale:${c}`, c))}
        </aside>

        <div className="flex min-w-0 flex-1 flex-col gap-2">
          {sezione === "nemico" && (
            <AnteprimaNemico archetipo={chiave} gradi={dati.gradi} />
          )}
          {sezione === "nemico"
            ? SOTTO_NEMICO.map((sotto) => {
                const gr = voci.filter((v) => v.sotto === sotto);
                if (gr.length === 0) return null;
                return (
                  <section key={sotto} className="flex flex-col gap-2">
                    <h3 className="border-b border-pergamena/15 pb-1 text-xs uppercase tracking-wider text-pergamena/50">
                      {sotto}
                    </h3>
                    {gr.map((v) => (
                      <CardVoce key={`${v.chiave}=${String(v.valore)}`} voce={v} />
                    ))}
                  </section>
                );
              })
            : voci.map((v) => <CardVoce key={`${v.chiave}=${String(v.valore)}`} voce={v} />)}
        </div>
      </div>
    </div>
  );
}
