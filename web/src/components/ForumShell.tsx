// Il FORUM sovra-run: la community diegetica dei crawler. La BACHECA è ora
// VERA (sovra-run Fase B): i necrologi proiettati dal ledger degli esiti via
// GET /api/bacheca — muori in una run, il tuo post appare qui. Thread e blog
// restano segnaposto: il sistema sociale completo è una spec a parte.

import { useBacheca } from "../api/query";
import type { NecrologioCrawler } from "../api/tipi";

function CardNecrologio({ post }: { post: NecrologioCrawler }) {
  return (
    <article className="rounded-lg border border-pergamena/20 bg-pietra px-4 py-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-bold text-torcia">{post.titolo}</span>
        {post.ts && (
          <span className="shrink-0 text-xs text-pergamena/50">{post.ts}</span>
        )}
      </div>
      <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-pergamena/85">
        {post.corpo}
      </p>
    </article>
  );
}

function BachecaCaduti() {
  const bacheca = useBacheca();
  const necrologi = bacheca.data?.necrologi ?? [];
  return (
    <section>
      <h2 className="mb-2 text-lg font-bold">La bacheca dei caduti</h2>
      {necrologi.length === 0 ? (
        <p className="rounded-lg border border-pergamena/20 bg-pietra px-4 py-3 text-sm italic text-pergamena/50">
          Nessun necrologio ancora: il dungeon attende i suoi primi caduti (o i
          suoi primi vincitori).
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {[...necrologi].reverse().map((post) => (
            <CardNecrologio key={post.uuid_run + post.titolo} post={post} />
          ))}
        </div>
      )}
    </section>
  );
}

const THREAD_SEGNAPOSTO = [
  {
    titolo: "【GUIDA】 Sopravvivere al Piano 1 senza piangere (troppo)",
    autore: "VeteranoDelBuio",
    risposte: 342,
    fissato: true,
  },
  {
    titolo: "Lo Slime Mangiascarti ha digerito il mio Rolex. AMA",
    autore: "CrawlerSfortunato_77",
    risposte: 128,
    fissato: false,
  },
  {
    titolo: "Teoria: il GM ci ascolta. Prove nei commenti.",
    autore: "Tinfoil_Tina",
    risposte: 891,
    fissato: false,
  },
  {
    titolo: "[MERCATO] Scambio mappa del Piano 1 per razioni",
    autore: "MercanteMuto",
    risposte: 23,
    fissato: false,
  },
] as const;

const BLOG_SEGNAPOSTO = [
  {
    titolo: "Diario della discesa #12 — la scala non era dove dicevano",
    autore: "Cartografa_K",
  },
  {
    titolo: "Perché continuo a scendere (una confessione)",
    autore: "UltimoDeiRimasti",
  },
] as const;

export function ForumShell() {
  return (
    <div className="flex flex-col gap-5">
      <BachecaCaduti />

      <div className="rounded-lg border border-torcia/40 bg-torcia/10 px-4 py-2 text-center text-sm text-torcia">
        🚧 Thread e blog qui sotto sono segnaposto: la bacheca dei caduti, sopra,
        è vera.
      </div>

      <section>
        <h2 className="mb-2 text-lg font-bold">Bacheca dei crawler</h2>
        <div className="flex flex-col divide-y divide-pergamena/10 rounded-lg border border-pergamena/20 bg-pietra">
          {THREAD_SEGNAPOSTO.map((thread) => (
            <div
              key={thread.titolo}
              className="flex items-center justify-between gap-3 px-4 py-3 opacity-80"
            >
              <div className="flex min-w-0 flex-col">
                <span className="truncate">
                  {thread.fissato && <span className="text-torcia">📌 </span>}
                  {thread.titolo}
                </span>
                <span className="text-xs text-pergamena/50">di {thread.autore}</span>
              </div>
              <span className="shrink-0 rounded-full border border-pergamena/20 px-2 py-0.5 text-xs text-pergamena/60">
                {thread.risposte} risposte
              </span>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-bold">Blog dal dungeon</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {BLOG_SEGNAPOSTO.map((blog) => (
            <div
              key={blog.titolo}
              className="rounded-lg border border-pergamena/20 bg-pietra px-4 py-3 opacity-80"
            >
              <p className="italic">{blog.titolo}</p>
              <p className="mt-1 text-xs text-pergamena/50">di {blog.autore}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
