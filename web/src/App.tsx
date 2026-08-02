// La SPA del forum play-by-post. Verità remota in TanStack Query (snapshot
// sostituito in blocco, C-4), segnali live via SSE, stato effimero in Zustand.

import { useSse } from "./api/useSse";
import {
  partitaAssente,
  usePartita,
  useProssimaNarrazione,
  useSalva,
  useThread,
} from "./api/query";
import type { StatoPartita } from "./api/tipi";
import { useGioco } from "./store/gioco";
import { BarraOpzioni } from "./components/BarraOpzioni";
import { ComposerAzione } from "./components/ComposerAzione";
import { NuovaPartita } from "./components/NuovaPartita";
import {
  Avviso,
  BannerFase,
  BannerMorte,
  PannelloStato,
  ProgressoGM,
} from "./components/Pannelli";
import { ThreadForum } from "./components/ThreadForum";

function Partita({ stato }: { stato: StatoPartita }) {
  useSse(true);
  const thread = useThread(true);
  const narrazione = useProssimaNarrazione();
  const salva = useSalva();
  const progresso = useGioco((s) => s.progresso);
  const bloccata =
    stato.morto || stato.occupato || progresso !== null || narrazione.isPending;

  return (
    <div className="mx-auto flex min-h-screen max-w-3xl flex-col gap-4 px-4 py-6">
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-pergamena/15 pb-3">
        <h1 className="text-xl font-bold text-torcia">
          Dungeon Crawler — forum di gioco
        </h1>
        <div className="flex items-center gap-3">
          <span className="text-xs italic text-pergamena/60">{stato.gm}</span>
          <button
            disabled={bloccata}
            onClick={() => salva.mutate({ versione: stato.versione })}
            className="rounded border border-pergamena/30 px-3 py-1 text-sm text-pergamena/80 transition hover:bg-pergamena/10 disabled:opacity-40"
          >
            Salva
          </button>
        </div>
      </header>

      <PannelloStato stato={stato.snapshot?.stato ?? []} />
      <BannerFase fase={stato.fase} />

      <main className="flex-1">
        <ThreadForum post={thread.data?.post ?? []} />
      </main>

      <footer className="sticky bottom-0 flex flex-col gap-3 border-t border-pergamena/15 bg-abisso/95 py-3 backdrop-blur">
        <ProgressoGM progresso={progresso} />
        {stato.morto ? (
          <BannerMorte />
        ) : stato.snapshot && stato.snapshot.opzioni.length > 0 ? (
          <>
            <BarraOpzioni
              snapshot={stato.snapshot}
              versione={stato.versione}
              bloccata={bloccata}
            />
            {stato.fase === "narrazione" && (
              <ComposerAzione versione={stato.versione} bloccato={bloccata} />
            )}
          </>
        ) : (
          <button
            disabled={bloccata}
            onClick={() => narrazione.mutate({ versione: stato.versione })}
            className="rounded border border-torcia/60 bg-torcia/10 px-4 py-2 font-bold text-torcia transition hover:bg-torcia/25 disabled:opacity-40"
          >
            Chiedi al GM il prossimo turno
          </button>
        )}
      </footer>
    </div>
  );
}

export default function App() {
  const partita = usePartita();

  if (partita.isPending) {
    return (
      <main className="flex min-h-screen items-center justify-center italic text-pergamena/60">
        Bussando alla porta del dungeon…
      </main>
    );
  }
  if (partita.isError && partitaAssente(partita.error)) {
    return (
      <>
        <NuovaPartita />
        <Avviso />
      </>
    );
  }
  if (partita.isError) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-2 px-4 text-center">
        <p className="text-sangue">L'host web non risponde.</p>
        <p className="text-sm text-pergamena/60">
          Avvia <code className="text-torcia">gioca_web.bat</code> e ricarica la
          pagina. ({String(partita.error)})
        </p>
      </main>
    );
  }
  return (
    <>
      <Partita stato={partita.data} />
      <Avviso />
    </>
  );
}
