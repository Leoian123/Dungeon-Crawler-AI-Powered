// L'HUB: la vista sovra-run di gestione dei crawler (impianto di mezzo).
// Slot = crawler (H §1): ogni card è un save vivo; morte e vittoria RITIRANO
// lo slot (permadeath). L'elenco viene dallo scan delle intestazioni (H §5).

import { useState } from "react";
import type { CrawlerVista, GmScelta } from "../api/tipi";
import { useApriPartita, useCrawlers, useEliminaCrawler } from "../api/query";
import { useGioco } from "../store/gioco";
import { CreaCrawler } from "./CreaCrawler";

/** "Elimina" con conferma inline: il permadeath volontario merita un ripensamento. */
function EliminaSlot({ uuid, bloccata }: { uuid: string; bloccata: boolean }) {
  const [conferma, setConferma] = useState(false);
  const elimina = useEliminaCrawler();
  if (!conferma) {
    return (
      <button
        disabled={bloccata}
        onClick={() => setConferma(true)}
        className="text-xs text-sangue/70 transition hover:text-sangue disabled:opacity-40"
      >
        Elimina
      </button>
    );
  }
  return (
    <span className="flex items-center gap-2 text-xs">
      <span className="text-sangue">Per sempre?</span>
      <button
        disabled={elimina.isPending}
        onClick={() => elimina.mutate({ uuid })}
        className="font-bold text-sangue hover:underline disabled:opacity-40"
      >
        Sì, elimina
      </button>
      <button
        onClick={() => setConferma(false)}
        className="text-pergamena/60 hover:text-pergamena"
      >
        Annulla
      </button>
    </span>
  );
}

function dataUltimoAccesso(timestamp: number): string {
  if (!timestamp) return "—";
  return new Date(timestamp * 1000).toLocaleString("it-IT", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function CardCrawler({
  crawler,
  gm,
  bloccata,
}: {
  crawler: CrawlerVista;
  gm: GmScelta;
  bloccata: boolean;
}) {
  const apri = useApriPartita();
  if (crawler.corrotta) {
    return (
      <div className="flex flex-col gap-1 rounded-lg border border-sangue/40 bg-pietra/60 p-4">
        <span className="font-bold text-sangue">{crawler.etichetta}</span>
        <span className="text-xs text-pergamena/60">salvataggio corrotto</span>
        <EliminaSlot uuid={crawler.uuid} bloccata={bloccata} />
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-pergamena/20 bg-pietra p-4">
      <span className="text-lg font-bold text-torcia">{crawler.etichetta}</span>
      <span className="text-sm text-pergamena/80">Piano {crawler.profondita}</span>
      <span className="text-xs text-pergamena/60">
        Ultimo accesso: {dataUltimoAccesso(crawler.timestamp)}
      </span>
      <button
        disabled={bloccata || apri.isPending}
        onClick={() => apri.mutate({ gm, carica: { uuid: crawler.uuid } })}
        className="mt-1 rounded border border-torcia/60 bg-torcia/10 px-3 py-1.5 font-bold text-torcia transition hover:bg-torcia/25 disabled:opacity-40"
      >
        {apri.isPending ? "Discesa…" : "Riprendi la discesa"}
      </button>
      <EliminaSlot uuid={crawler.uuid} bloccata={bloccata} />
    </div>
  );
}

export function HubCrawler() {
  const crawlers = useCrawlers();
  const [gm, setGm] = useState<GmScelta>("fake");
  const [creazione, setCreazione] = useState(false);
  const setSezione = useGioco((s) => s.setSezione);

  if (crawlers.isPending) {
    return (
      <p className="py-16 text-center italic text-pergamena/60">
        Consultando il registro dei crawler…
      </p>
    );
  }
  if (crawlers.isError) {
    return (
      <div className="py-16 text-center">
        <p className="text-sangue">L'host web non risponde.</p>
        <p className="text-sm text-pergamena/60">
          Avvia <code className="text-torcia">gioca_web.bat</code> e ricarica.
        </p>
      </div>
    );
  }

  const { crawlers: elenco, attiva } = crawlers.data;
  const runAperta = attiva !== null;

  return (
    <div className="flex flex-col gap-5">
      {runAperta && (
        <div className="flex items-center justify-between rounded-lg border border-torcia/50 bg-torcia/10 px-4 py-3">
          <span>
            Run in corso: <b className="text-torcia">{attiva.nome}</b>
          </span>
          <button
            onClick={() => setSezione("gioco")}
            className="rounded bg-torcia px-4 py-1.5 font-bold text-abisso transition hover:bg-torcia/90"
          >
            Riprendi
          </button>
        </div>
      )}

      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-bold">I tuoi crawler</h2>
        <fieldset className="flex gap-1" disabled={runAperta}>
          {(["fake", "live"] as const).map((scelta) => (
            <button
              key={scelta}
              onClick={() => setGm(scelta)}
              className={`rounded border px-3 py-1 text-xs transition ${
                gm === scelta
                  ? "border-torcia bg-torcia/15 text-torcia"
                  : "border-pergamena/25 text-pergamena/60 hover:bg-pergamena/10"
              }`}
            >
              {scelta === "fake" ? "GM offline" : "GM live"}
            </button>
          ))}
        </fieldset>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {elenco.map((crawler) => (
          <CardCrawler
            key={crawler.uuid}
            crawler={crawler}
            gm={gm}
            bloccata={runAperta}
          />
        ))}
        {!creazione && (
          <button
            disabled={runAperta}
            onClick={() => setCreazione(true)}
            className="flex min-h-32 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-pergamena/30 text-pergamena/60 transition hover:border-torcia/50 hover:text-torcia disabled:opacity-40"
          >
            <span className="text-2xl">＋</span>
            <span>Nuovo crawler</span>
          </button>
        )}
      </div>

      {creazione && !runAperta && (
        <CreaCrawler gm={gm} onAnnulla={() => setCreazione(false)} />
      )}

      {elenco.length === 0 && !creazione && (
        <p className="text-center italic text-pergamena/50">
          Nessun crawler nel registro: il dungeon attende il primo volontario.
        </p>
      )}
    </div>
  );
}
