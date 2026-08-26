// Il CRUSCOTTO della Wiki del Master (W2 minimo): le proposte raccolte dalle
// run (outbox, sopravvissute anche al permadeath) aspettano QUI l'atto
// dell'admin — Promuovi le sposta nel canone (voce del master, provenienza
// SISTEMA, approvata dal click), Scarta le toglie e basta. «L'AI propone,
// l'admin dispone» reso pagina.

import {
  useWikiPromuovi,
  useWikiProposte,
  useWikiScarta,
  useWikiVoci,
} from "../api/query";
import type { PropostaWikiVista, VoceWikiVista } from "../api/tipi";

function Chip({ testo, tono = "" }: { testo: string; tono?: string }) {
  return (
    <span
      className={`rounded-full border px-2 py-0.5 font-hud text-[0.65rem] uppercase tracking-wider ${
        tono || "border-pergamena/25 text-pergamena/60"
      }`}
    >
      {testo}
    </span>
  );
}

function CardProposta({ proposta }: { proposta: PropostaWikiVista }) {
  const promuovi = useWikiPromuovi();
  const scarta = useWikiScarta();
  const occupato = promuovi.isPending || scarta.isPending;
  const atto = { id: proposta.id, uuid_run: proposta.uuid_run };
  return (
    <article className="flex flex-col gap-2 rounded-lg border border-show/30 bg-pietra p-3">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="min-w-0 flex-1 truncate font-bold text-pergamena">
          {proposta.titolo}
        </span>
        <Chip testo={proposta.tipo} />
        <Chip
          testo={proposta.taint}
          tono={
            proposta.taint === "citabile"
              ? "border-muschio/40 text-muschio/90"
              : "border-torcia/40 text-torcia/90"
          }
        />
        <Chip testo={`run ${proposta.uuid_run}`} />
      </div>
      <p className="text-sm leading-relaxed text-pergamena/85">{proposta.testo}</p>
      <div className="flex gap-2">
        <button
          disabled={occupato}
          onClick={() => promuovi.mutate(atto)}
          className="rounded border border-muschio/60 bg-muschio/10 px-3 py-1 font-hud text-xs font-bold uppercase tracking-wider text-muschio transition hover:bg-muschio/20 disabled:opacity-40"
        >
          Promuovi nel canone
        </button>
        <button
          disabled={occupato}
          onClick={() => scarta.mutate(atto)}
          className="rounded border border-pergamena/30 px-3 py-1 font-hud text-xs uppercase tracking-wider text-pergamena/60 transition hover:bg-pergamena/10 disabled:opacity-40"
        >
          Scarta
        </button>
      </div>
    </article>
  );
}

function CardVoce({ voce }: { voce: VoceWikiVista }) {
  const ultima = voce.revisioni[voce.revisioni.length - 1];
  const approvate = new Set(voce.approvazioni.map((a) => a.revisione_n));
  return (
    <article className="flex flex-col gap-1.5 rounded-lg border border-pergamena/20 bg-pietra p-3">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="min-w-0 flex-1 truncate font-hud text-sm font-bold text-torcia">
          {voce.slug}
        </span>
        <Chip testo={voce.tipo} />
        <Chip
          testo={voce.regia}
          tono={
            voce.regia === "citabile"
              ? "border-muschio/40 text-muschio/90"
              : "border-torcia/40 text-torcia/90"
          }
        />
        {voce.segretezza === "admin" && (
          <Chip testo="solo admin" tono="border-sangue/40 text-sangue/90" />
        )}
        {voce.costante && <Chip testo="costante" tono="border-show/40 text-show/90" />}
        <Chip
          testo={`rev ${ultima.n}${approvate.has(ultima.n) ? " ✓" : " (bozza)"}`}
        />
      </div>
      <p
        className="text-sm leading-relaxed text-pergamena/80"
        title={ultima.testo}
      >
        {ultima.testo.length > 220 ? `${ultima.testo.slice(0, 220)}…` : ultima.testo}
      </p>
    </article>
  );
}

export function CruscottoWiki() {
  const proposte = useWikiProposte();
  const voci = useWikiVoci();
  const inCoda = proposte.data?.proposte ?? [];
  const canone = voci.data?.voci ?? [];
  return (
    <div className="flex flex-col gap-5">
      <section>
        <h3 className="etichetta-hud mb-2 text-show">
          Proposte dalle run · {inCoda.length}
        </h3>
        {inCoda.length === 0 ? (
          <p className="rounded-lg border border-pergamena/15 bg-pietra px-4 py-3 text-sm italic text-pergamena/50">
            Nessuna proposta in coda: gli appunti del GM arrivano giocando (e
            sopravvivono anche al permadeath — è il loro scopo).
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {inCoda.map((p) => (
              <CardProposta key={`${p.uuid_run}-${p.id}`} proposta={p} />
            ))}
          </div>
        )}
      </section>

      <section>
        <h3 className="etichetta-hud mb-2 text-pergamena/60">
          Il canone del Master · {canone.length} voci
        </h3>
        {canone.length === 0 ? (
          <p className="rounded-lg border border-pergamena/15 bg-pietra px-4 py-3 text-sm italic text-pergamena/50">
            Il canone è vuoto: promuovi una proposta, o scrivi le voci nella
            directory della wiki.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {canone.map((v) => (
              <CardVoce key={v.slug} voce={v} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
