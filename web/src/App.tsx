// La SPA a tre sezioni: HUB (gestione crawler, sovra-run) / GIOCO (la run,
// forum play-by-post) / FORUM (community diegetica, shell). Navigazione a
// stato (Zustand), niente router. Verità remota in TanStack Query (snapshot
// sostituito in blocco, C-4), segnali live via SSE.

import { useState } from "react";

import { useSse } from "./api/useSse";
import {
  partitaAssente,
  usePartita,
  useProssimaNarrazione,
  useEsci,
  useSalva,
  useThread,
} from "./api/query";
import type { StatoPartita } from "./api/tipi";
import { useGioco, type Sezione } from "./store/gioco";
import { BarraOpzioni } from "./components/BarraOpzioni";
import { ComposerAzione } from "./components/ComposerAzione";
import { ComposerScena } from "./components/ComposerScena";
import { ForumShell } from "./components/ForumShell";
import { GameMaster } from "./components/GameMaster";
import { HubCrawler } from "./components/HubCrawler";
import {
  Avviso,
  BannerFase,
  BannerMorte,
  BannerVittoria,
  PannelloStato,
  ProgressoGM,
} from "./components/Pannelli";
import { PannelloParty } from "./components/SchedaPG";
import { PannelloZaino } from "./components/Zaino";
import { AlboObiettivi, ChipObiettivi } from "./components/Obiettivi";
import { RegistroSkill } from "./components/RegistroSkill";
import { ThreadForum } from "./components/ThreadForum";

// STANDARD di architettura della Partita (2026-08-26): la sidebar è il
// CRUSCOTTO DI STATO VIVO — solo ciò che serve a decidere la prossima azione
// (scheda, zaino operativo, chip di stato). Ogni CONSULTAZIONE (elenchi
// lunghi: l'albo obiettivi) è una VISTA SECONDARIA con la sua superficie
// piena, mai un riquadro in più appeso alla colonna.
type VistaPartita = "diario" | "albo" | "registro";

function Partita({ stato }: { stato: StatoPartita }) {
  useSse(true);
  const thread = useThread(true);
  const narrazione = useProssimaNarrazione();
  const salva = useSalva();
  const esci = useEsci();
  const progresso = useGioco((s) => s.progresso);
  const [vista, setVista] = useState<VistaPartita>("diario");
  const terminata = stato.morto || stato.vittoria;
  const bloccata =
    terminata || stato.occupato || progresso !== null || narrazione.isPending;
  // In combattimento non si salva (soft-lock al ricarico): il server risponde
  // comunque 409, qui si spengono i bottoni per non far sbattere il giocatore.
  const salvataggioVietato = bloccata || stato.fase === "combattimento";

  return (
    <div className="flex flex-col gap-4">
      {/* Comandi di run SEMPRE in vista (playtest 2026-08-27: Salva scrollava
          fuori schermo col thread lungo): la riga è sticky in testa. */}
      <div className="sticky top-0 z-20 -mx-4 flex flex-wrap items-center justify-between gap-2 border-b border-pergamena/15 bg-abisso/95 px-4 py-2 backdrop-blur">
        <div className="flex items-center gap-3">
          <nav className="flex gap-1 rounded border border-pergamena/20 p-0.5">
            {(["diario", "albo", "registro"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setVista(v)}
                className={`rounded px-3 py-0.5 font-hud text-xs font-bold uppercase tracking-wider transition ${
                  vista === v
                    ? "bg-torcia/20 text-torcia"
                    : "text-pergamena/50 hover:text-pergamena/80"
                }`}
              >
                {v}
              </button>
            ))}
          </nav>
          <span className="text-sm italic text-pergamena/60">{stato.gm}</span>
        </div>
        <div className="flex gap-2">
          <button
            disabled={salvataggioVietato}
            onClick={() => salva.mutate({ versione: stato.versione })}
            className="rounded border border-pergamena/30 px-3 py-1 text-sm text-pergamena/80 transition hover:bg-pergamena/10 disabled:opacity-40"
          >
            Salva
          </button>
          <button
            disabled={salvataggioVietato || esci.isPending}
            onClick={() => esci.mutate({ versione: stato.versione })}
            className="rounded border border-torcia/50 px-3 py-1 text-sm text-torcia transition hover:bg-torcia/10 disabled:opacity-40"
          >
            Salva ed esci
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
        {/* Colonna sinistra: il party (sticky su desktop, sopra al thread su mobile). */}
        <aside className="flex flex-col gap-3 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:w-72 lg:shrink-0 lg:overflow-y-auto xl:w-80">
          <PannelloParty />
          {/* Indossa/Togli solo in narrazione: in scontro il server rifiuta (409). */}
          <PannelloZaino
            versione={stato.versione}
            bloccato={bloccata || stato.fase === "combattimento"}
          />
          {/* Stato vivo, non elenco: l'albo pieno è la vista secondaria. */}
          <ChipObiettivi apri={() => setVista("albo")} />
        </aside>

        {vista === "albo" ? (
          <main className="min-w-0 flex-1">
            <AlboObiettivi />
          </main>
        ) : vista === "registro" ? (
          <main className="min-w-0 flex-1">
            <RegistroSkill />
          </main>
        ) : (
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <BannerFase fase={stato.fase} />
          {stato.fase === "combattimento" && stato.snapshot && (
            // In scontro i descrittori portano anche il NEMICO coi suoi HP.
            <PannelloStato stato={stato.snapshot.stato} />
          )}

          <main className="flex-1">
            <ThreadForum post={thread.data?.post ?? []} />
          </main>

          <footer className="sticky bottom-0 flex flex-col gap-3 border-t border-pergamena/15 bg-abisso/95 py-3 backdrop-blur">
            <ProgressoGM progresso={progresso} />
            {stato.morto ? (
              <BannerMorte />
            ) : stato.vittoria ? (
              <BannerVittoria />
            ) : stato.snapshot && stato.snapshot.opzioni.length > 0 ? (
              <>
                <BarraOpzioni
                  snapshot={stato.snapshot}
                  versione={stato.versione}
                  bloccata={bloccata}
                />
                {stato.fase === "narrazione" &&
                  (stato.snapshot.scena_aperta ? (
                    // Scena sociale aperta: l'input è la BATTUTA (porta di
                    // scena), non l'azione libera (turno GM) — mai entrambe.
                    <ComposerScena versione={stato.versione} bloccato={bloccata} />
                  ) : (
                    <ComposerAzione versione={stato.versione} bloccato={bloccata} />
                  ))}
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
        )}
      </div>
    </div>
  );
}

function SezioneGioco() {
  const partita = usePartita();
  const setSezione = useGioco((s) => s.setSezione);

  if (partita.isPending) {
    return (
      <p className="py-16 text-center italic text-pergamena/60">
        Bussando alla porta del dungeon…
      </p>
    );
  }
  if (partita.isError) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center">
        <p className="text-pergamena/70">
          {partitaAssente(partita.error)
            ? "Nessuna run in corso."
            : "L'host web non risponde."}
        </p>
        <button
          onClick={() => setSezione("hub")}
          className="rounded bg-torcia px-4 py-1.5 font-bold text-abisso transition hover:bg-torcia/90"
        >
          Vai all'hub
        </button>
      </div>
    );
  }
  return <Partita stato={partita.data} />;
}

const TAB: { id: Sezione; etichetta: string }[] = [
  { id: "hub", etichetta: "Hub" },
  { id: "gioco", etichetta: "Partita" },
  { id: "forum", etichetta: "Forum" },
  { id: "gm", etichetta: "Game Master" },
];

export default function App() {
  const sezione = useGioco((s) => s.sezione);
  const setSezione = useGioco((s) => s.setSezione);

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-4 px-4 py-5">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-torcia/20 pb-3">
        <div className="flex min-w-0 flex-col">
          <h1 className="titolo-insegna text-2xl text-torcia">Dungeon Crawler</h1>
          <span className="etichetta-hud text-pergamena/45">
            la discesa è lo show · 150.000 ingressi
          </span>
        </div>
        <nav className="flex gap-1">
          {TAB.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setSezione(tab.id)}
              className={`rounded border px-3 py-1.5 font-hud text-xs font-bold uppercase tracking-wider transition ${
                sezione === tab.id
                  ? "border-torcia/50 bg-torcia/15 text-torcia"
                  : "border-transparent text-pergamena/60 hover:bg-pergamena/10"
              }`}
            >
              {tab.etichetta}
            </button>
          ))}
        </nav>
      </header>

      {sezione === "hub" && <HubCrawler />}
      {sezione === "gioco" && <SezioneGioco />}
      {sezione === "forum" && <ForumShell />}
      {sezione === "gm" && <GameMaster />}
      <Avviso />
    </div>
  );
}
