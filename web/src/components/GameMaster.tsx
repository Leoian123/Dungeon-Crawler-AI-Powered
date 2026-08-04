// GAME MASTER MODE: l'authoring della libreria dei contenuti (stagioni/piani/
// mob) — asset riusabili con tag e affinity matching, come gli architetti del
// dungeon. Gli UFFICIALI (repo) sono read-only: si duplicano; i LOCALI si
// creano/modificano/eliminano. La verità della validazione è il lint del
// server (422): il client evidenzia, non decide. L'authoring non tocca mai le
// run in corso (la stagione è congelata nel World alla creazione).

import { useState } from "react";
import {
  DURATE,
  GRADI,
  type ArchetipoAsset,
  type AssetVista,
  type MobAsset,
  type PianoAsset,
  type ProfiloArchetipoDati,
  type StagioneAsset,
  type TipoAsset,
} from "../api/tipi";
import { api } from "../api/client";
import {
  useAffini,
  useAssets,
  useEliminaAsset,
  useSalvaAsset,
  useVocabolario,
} from "../api/query";
import { Calibrazione } from "./Calibrazione";

type Editor =
  | { modo: "chiuso" }
  | { modo: "mob"; corpo: MobAsset; nuovo: boolean }
  | { modo: "piano"; corpo: PianoAsset; nuovo: boolean }
  | { modo: "stagione"; corpo: StagioneAsset; nuovo: boolean }
  | { modo: "archetipo"; corpo: ArchetipoAsset; nuovo: boolean };

const MOB_VUOTO: MobAsset = {
  slug: "", versione: 1, tags: [], nome: "", archetipo: "slime",
  grado: "bronzo", blocchi: [], descrizione: "", prosa_stanza: "", durata: "turno",
  mosse: [], override: null,
};
const ARCHETIPO_VUOTO: ArchetipoAsset = {
  slug: "", versione: 1, tags: [], nome: "", descrizione: "", profilo: null, mosse: [],
};
const PIANO_VUOTO: PianoAsset = {
  slug: "", versione: 1, tags: [], titolo: "", tema: "", stile: [], lore: "",
  budget: { gradi: ["bronzo"], blocchi: [], archetipi: ["slime"] },
  cast: [], stanze: null,
};
const STAGIONE_VUOTA: StagioneAsset = {
  slug: "", versione: 1, tags: [], numero: 1, titolo: "", tagline: "",
  mondo: "", stile: [], lore: "", piani: [],
};

// --- Campi riusabili -----------------------------------------------------------

function Campo({ etichetta, children }: { etichetta: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-pergamena/70">{etichetta}</span>
      {children}
    </label>
  );
}

import { CLS_INPUT } from "./ui";

function Testo({ valore, su, ...extra }: {
  valore: string; su: (v: string) => void; placeholder?: string; disabled?: boolean;
}) {
  return (
    <input value={valore} onChange={(e) => su(e.target.value)} className={CLS_INPUT} {...extra} />
  );
}

function Area({ valore, su, righe = 3 }: { valore: string; su: (v: string) => void; righe?: number }) {
  return (
    <textarea rows={righe} value={valore} onChange={(e) => su(e.target.value)}
      className={`${CLS_INPUT} resize-y`} />
  );
}

/** Righe di testo (stile) come textarea: una riga per voce. */
function Righe({ valore, su }: { valore: string[]; su: (v: string[]) => void }) {
  return (
    <Area valore={valore.join("\n")} righe={3}
      su={(t) => su(t.split("\n").map((r) => r.trim()).filter(Boolean))} />
  );
}

/** Tag come testo separato da virgole. */
function Tags({ valore, su }: { valore: string[]; su: (v: string[]) => void }) {
  return (
    <Testo valore={valore.join(", ")} placeholder="kebab-case, separati-da-virgola"
      su={(t) => su(t.split(",").map((x) => x.trim()).filter(Boolean))} />
  );
}

function Spunte<T extends string>({ opzioni, scelte, su }: {
  opzioni: readonly T[]; scelte: T[]; su: (v: T[]) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {opzioni.map((o) => (
        <button key={o} type="button"
          onClick={() => su(scelte.includes(o) ? scelte.filter((x) => x !== o) : [...scelte, o])}
          className={`rounded border px-2 py-0.5 text-xs transition ${
            scelte.includes(o)
              ? "border-torcia bg-torcia/15 text-torcia"
              : "border-pergamena/25 text-pergamena/60 hover:bg-pergamena/10"
          }`}>
          {o}
        </button>
      ))}
    </div>
  );
}

function Scelta<T extends string>({ opzioni, valore, su }: {
  opzioni: readonly T[]; valore: T; su: (v: T) => void;
}) {
  return (
    <select value={valore} onChange={(e) => su(e.target.value as T)} className={CLS_INPUT}>
      {opzioni.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}

// --- Editor: sequenza ordinabile di riferimenti (cast del piano, piani della stagione)

function Sequenza({ voci, opzioni, su, vuoto }: {
  voci: string[]; opzioni: string[]; su: (v: string[]) => void; vuoto: string;
}) {
  const [daAggiungere, setDaAggiungere] = useState("");
  return (
    <div className="flex flex-col gap-1">
      {voci.length === 0 && <p className="text-xs italic text-pergamena/40">{vuoto}</p>}
      {voci.map((slug, i) => (
        <div key={`${slug}-${i}`} className="flex items-center gap-1 text-sm">
          <span className="w-5 text-right text-xs text-pergamena/40">{i + 1}.</span>
          <span className="flex-1 truncate">{slug}</span>
          <button onClick={() => { const v = [...voci]; if (i > 0) { [v[i - 1], v[i]] = [v[i], v[i - 1]]; su(v); } }}
            className="px-1 text-pergamena/50 hover:text-torcia">↑</button>
          <button onClick={() => { const v = [...voci]; if (i < v.length - 1) { [v[i + 1], v[i]] = [v[i], v[i + 1]]; su(v); } }}
            className="px-1 text-pergamena/50 hover:text-torcia">↓</button>
          <button onClick={() => su(voci.filter((_x, j) => j !== i))}
            className="px-1 text-sangue/70 hover:text-sangue">✕</button>
        </div>
      ))}
      <div className="flex gap-1">
        <select value={daAggiungere} onChange={(e) => setDaAggiungere(e.target.value)}
          className={`${CLS_INPUT} flex-1`}>
          <option value="">— scegli —</option>
          {opzioni.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
        <button disabled={!daAggiungere}
          onClick={() => { su([...voci, daAggiungere]); setDaAggiungere(""); }}
          className="rounded border border-torcia/50 px-2 text-sm text-torcia disabled:opacity-40">
          Aggiungi
        </button>
      </div>
    </div>
  );
}

/** Suggerimenti per affinità sui tag correnti (il riuso: prima pesca, poi crea). */
function Affini({ tipo, tags, aggiungi }: {
  tipo: TipoAsset; tags: string[]; aggiungi: (slug: string) => void;
}) {
  const affini = useAffini(tipo, tags);
  const voci = affini.data?.affini ?? [];
  if (tags.length === 0 || voci.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1 text-xs">
      <span className="text-pergamena/50">Affini ai tag:</span>
      {voci.map((v) => (
        <button key={v.slug} onClick={() => aggiungi(v.slug)}
          className="rounded-full border border-muschio/40 px-2 py-0.5 text-muschio/90 hover:bg-muschio/10">
          + {v.slug}
        </button>
      ))}
    </div>
  );
}

// --- I tre editor ----------------------------------------------------------------

function AzioniEditor({ nuovo, tipo, corpo, chiudi }: {
  nuovo: boolean; tipo: TipoAsset; corpo: { slug: string }; chiudi: () => void;
}) {
  const salva = useSalvaAsset(tipo);
  return (
    <div className="flex gap-2 pt-1">
      <button disabled={salva.isPending}
        onClick={() => salva.mutate({ corpo, nuovo }, { onSuccess: chiudi })}
        className="rounded bg-torcia px-4 py-1.5 font-bold text-abisso transition hover:bg-torcia/90 disabled:opacity-40">
        Salva (locale)
      </button>
      <button onClick={chiudi}
        className="rounded border border-pergamena/30 px-4 py-1.5 text-pergamena/70 hover:bg-pergamena/10">
        Annulla
      </button>
    </div>
  );
}

function EditorMob({ iniziale, nuovo, chiudi }: {
  iniziale: MobAsset; nuovo: boolean; chiudi: () => void;
}) {
  const [m, setM] = useState(iniziale);
  const su = (patch: Partial<MobAsset>) => setM({ ...m, ...patch });
  const voc = useVocabolario().data;
  const archetipi = voc?.archetipi ?? [m.archetipo];
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-torcia/40 bg-pietra p-4">
      <h3 className="font-bold text-torcia">{nuovo ? "Nuovo mob" : `Mob: ${m.slug}`}</h3>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Campo etichetta="Slug"><Testo valore={m.slug} su={(v) => su({ slug: v })} disabled={!nuovo} /></Campo>
        <Campo etichetta="Nome"><Testo valore={m.nome} su={(v) => su({ nome: v })} /></Campo>
        <Campo etichetta="Archetipo"><Scelta opzioni={archetipi} valore={m.archetipo} su={(v) => su({ archetipo: v })} /></Campo>
        <Campo etichetta="Grado"><Scelta opzioni={GRADI} valore={m.grado} su={(v) => su({ grado: v })} /></Campo>
        <Campo etichetta="Durata della scena"><Scelta opzioni={DURATE} valore={m.durata} su={(v) => su({ durata: v })} /></Campo>
        <Campo etichetta="Tags"><Tags valore={m.tags} su={(v) => su({ tags: v })} /></Campo>
      </div>
      <Campo etichetta="Blocchi"><Spunte opzioni={voc?.blocchi ?? []} scelte={m.blocchi} su={(v) => su({ blocchi: v })} /></Campo>
      <Campo etichetta="Mosse proprie (vuoto = quelle dell'archetipo)">
        <Spunte opzioni={voc?.mosse ?? []} scelte={m.mosse} su={(v) => su({ mosse: v })} />
      </Campo>
      <Campo etichetta="Descrizione (flavor)"><Testo valore={m.descrizione} su={(v) => su({ descrizione: v })} /></Campo>
      <Campo etichetta="Prosa della stanza (copione offline)"><Area valore={m.prosa_stanza} su={(v) => su({ prosa_stanza: v })} righe={4} /></Campo>
      <AzioniEditor nuovo={nuovo} tipo="mob" corpo={m} chiudi={chiudi} />
    </div>
  );
}

function EditorPiano({ iniziale, nuovo, chiudi }: {
  iniziale: PianoAsset; nuovo: boolean; chiudi: () => void;
}) {
  const [p, setP] = useState(iniziale);
  const su = (patch: Partial<PianoAsset>) => setP({ ...p, ...patch });
  const mob = useAssets("mob");
  const slugMob = (mob.data?.asset ?? []).filter((a) => a.valido).map((a) => a.slug);
  const voc = useVocabolario().data;
  const archetipi = voc?.archetipi ?? p.budget.archetipi;
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-torcia/40 bg-pietra p-4">
      <h3 className="font-bold text-torcia">{nuovo ? "Nuovo piano" : `Piano: ${p.slug}`}</h3>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Campo etichetta="Slug"><Testo valore={p.slug} su={(v) => su({ slug: v })} disabled={!nuovo} /></Campo>
        <Campo etichetta="Titolo"><Testo valore={p.titolo} su={(v) => su({ titolo: v })} /></Campo>
        <Campo etichetta="Stanze (vuoto = una per mob del cast)">
          <Testo valore={p.stanze?.toString() ?? ""} su={(v) => su({ stanze: v ? Number(v) || null : null })} />
        </Campo>
        <Campo etichetta="Tags"><Tags valore={p.tags} su={(v) => su({ tags: v })} /></Campo>
      </div>
      <Campo etichetta="Tema di fondo"><Area valore={p.tema} su={(v) => su({ tema: v })} /></Campo>
      <Campo etichetta="Stile (una riga per voce)"><Righe valore={p.stile} su={(v) => su({ stile: v })} /></Campo>
      <Campo etichetta="Lore (opzionale)"><Area valore={p.lore} su={(v) => su({ lore: v })} righe={2} /></Campo>
      <fieldset className="flex flex-col gap-1 rounded border border-pergamena/15 p-2">
        <legend className="px-1 text-xs uppercase tracking-wider text-pergamena/50">Budget (vincolo hard del gate)</legend>
        <Campo etichetta="Gradi ammessi"><Spunte opzioni={GRADI} scelte={p.budget.gradi} su={(v) => su({ budget: { ...p.budget, gradi: v } })} /></Campo>
        <Campo etichetta="Blocchi ammessi"><Spunte opzioni={voc?.blocchi ?? []} scelte={p.budget.blocchi} su={(v) => su({ budget: { ...p.budget, blocchi: v } })} /></Campo>
        <Campo etichetta="Archetipi ammessi"><Spunte opzioni={archetipi} scelte={p.budget.archetipi} su={(v) => su({ budget: { ...p.budget, archetipi: v } })} /></Campo>
      </fieldset>
      <Campo etichetta="Cast (in ordine di apparizione)">
        <Sequenza voci={p.cast} opzioni={slugMob} su={(v) => su({ cast: v })}
          vuoto="Nessun mob nel cast: pescane uno o crealo nella collezione Mob." />
      </Campo>
      <Affini tipo="mob" tags={p.tags} aggiungi={(slug) => su({ cast: [...p.cast, slug] })} />
      <AzioniEditor nuovo={nuovo} tipo="piani" corpo={p} chiudi={chiudi} />
    </div>
  );
}

/** Numero opzionale: vuoto = null (eredita dalla calibrazione, solo storici). */
function NumeroOpz({ valore, su }: {
  valore: number | null | undefined; su: (v: number | null) => void;
}) {
  return (
    <input type="number" value={valore ?? ""} className={CLS_INPUT}
      onChange={(e) => su(e.target.value === "" ? null : Number(e.target.value))} />
  );
}

/** Scelta opzionale con voce vuota "eredita". */
function SceltaOpz({ opzioni, valore, su }: {
  opzioni: readonly string[]; valore: string | null | undefined;
  su: (v: string | null) => void;
}) {
  return (
    <select value={valore ?? ""} onChange={(e) => su(e.target.value || null)}
      className={CLS_INPUT}>
      <option value="">— eredita —</option>
      {opzioni.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}

function EditorArchetipo({ iniziale, nuovo, chiudi }: {
  iniziale: ArchetipoAsset; nuovo: boolean; chiudi: () => void;
}) {
  const [a, setA] = useState(iniziale);
  const voc = useVocabolario().data;
  const su = (patch: Partial<ArchetipoAsset>) => setA({ ...a, ...patch });
  const p: ProfiloArchetipoDati = a.profilo ?? {};
  const suP = (patch: Partial<ProfiloArchetipoDati>) => {
    const unito = { ...p, ...patch };
    const vuoto = Object.values(unito).every((v) => v === null || v === undefined);
    su({ profilo: vuoto ? null : unito });
  };
  const NUMERI: { campo: keyof ProfiloArchetipoDati; etichetta: string }[] = [
    { campo: "destrezza_base", etichetta: "Destrezza base" },
    { campo: "pv_base", etichetta: "PV base" },
    { campo: "danno_base", etichetta: "Danno base" },
    { campo: "intelligenza_base", etichetta: "Intelligenza base" },
    { campo: "difesa_base", etichetta: "Difesa base (centesimi)" },
    { campo: "saggezza_base", etichetta: "Saggezza base" },
    { campo: "fortuna_base", etichetta: "Fortuna base" },
    { campo: "res_mischia", etichetta: "Res. mischia (%)" },
    { campo: "res_fuoco", etichetta: "Res. fuoco (%)" },
    { campo: "res_veleno", etichetta: "Res. veleno (%)" },
  ];
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-torcia/40 bg-pietra p-4">
      <h3 className="font-bold text-torcia">
        {nuovo ? "Nuovo archetipo" : `Archetipo: ${a.slug}`}
      </h3>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Campo etichetta="Slug"><Testo valore={a.slug} su={(v) => su({ slug: v })} disabled={!nuovo} /></Campo>
        <Campo etichetta="Nome"><Testo valore={a.nome} su={(v) => su({ nome: v })} /></Campo>
        <Campo etichetta="Tags"><Tags valore={a.tags} su={(v) => su({ tags: v })} /></Campo>
      </div>
      <Campo etichetta="Descrizione"><Testo valore={a.descrizione} su={(v) => su({ descrizione: v })} /></Campo>
      <Campo etichetta="Mosse (repertorio di default; vuoto = attacco/attacco pesante)">
        <Spunte opzioni={voc?.mosse ?? []} scelte={a.mosse} su={(v) => su({ mosse: v })} />
      </Campo>
      <fieldset className="flex flex-col gap-2 rounded border border-pergamena/15 p-2">
        <legend className="px-1 text-xs uppercase tracking-wider text-pergamena/50">
          Profilo numerico — vuoto = eredita dalla calibrazione (solo per gli storici);
          per uno slug nuovo il profilo è obbligatorio (il server lo impone)
        </legend>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
          {NUMERI.map(({ campo, etichetta }) => (
            <Campo key={campo} etichetta={etichetta}>
              <NumeroOpz valore={p[campo] as number | null | undefined}
                su={(v) => suP({ [campo]: v })} />
            </Campo>
          ))}
          <Campo etichetta="Armatura">
            <SceltaOpz opzioni={voc?.armature ?? []} valore={p.armatura} su={(v) => suP({ armatura: v })} />
          </Campo>
          <Campo etichetta="Taglia">
            <SceltaOpz opzioni={voc?.taglie ?? []} valore={p.taglia} su={(v) => suP({ taglia: v })} />
          </Campo>
          <Campo etichetta="Arma">
            <SceltaOpz opzioni={voc?.armi ?? []} valore={p.arma} su={(v) => suP({ arma: v })} />
          </Campo>
        </div>
      </fieldset>
      <AzioniEditor nuovo={nuovo} tipo="archetipi" corpo={a} chiudi={chiudi} />
    </div>
  );
}

function EditorStagione({ iniziale, nuovo, chiudi }: {
  iniziale: StagioneAsset; nuovo: boolean; chiudi: () => void;
}) {
  const [s, setS] = useState(iniziale);
  const su = (patch: Partial<StagioneAsset>) => setS({ ...s, ...patch });
  const piani = useAssets("piani");
  const slugPiani = (piani.data?.asset ?? []).filter((a) => a.valido).map((a) => a.slug);
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-torcia/40 bg-pietra p-4">
      <h3 className="font-bold text-torcia">{nuovo ? "Nuova stagione" : `Stagione: ${s.slug}`}</h3>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Campo etichetta="Slug"><Testo valore={s.slug} su={(v) => su({ slug: v })} disabled={!nuovo} /></Campo>
        <Campo etichetta="Numero della stagione">
          <Testo valore={String(s.numero)} su={(v) => su({ numero: Number(v) || 1 })} />
        </Campo>
        <Campo etichetta="Titolo"><Testo valore={s.titolo} su={(v) => su({ titolo: v })} /></Campo>
        <Campo etichetta="Tagline"><Testo valore={s.tagline} su={(v) => su({ tagline: v })} /></Campo>
        <Campo etichetta="Mondo reclamato"><Testo valore={s.mondo} su={(v) => su({ mondo: v })} /></Campo>
        <Campo etichetta="Tags"><Tags valore={s.tags} su={(v) => su({ tags: v })} /></Campo>
      </div>
      <Campo etichetta="Voce editoriale (una riga per voce)"><Righe valore={s.stile} su={(v) => su({ stile: v })} /></Campo>
      <Campo etichetta="Lore di cornice"><Area valore={s.lore} su={(v) => su({ lore: v })} righe={2} /></Campo>
      <Campo etichetta="Piani (ordinati per profondità: 1° = piano 1)">
        <Sequenza voci={s.piani} opzioni={slugPiani} su={(v) => su({ piani: v })}
          vuoto="Nessun piano: la discesa non esiste ancora." />
      </Campo>
      <Affini tipo="piani" tags={s.tags} aggiungi={(slug) => su({ piani: [...s.piani, slug] })} />
      <AzioniEditor nuovo={nuovo} tipo="stagioni" corpo={s} chiudi={chiudi} />
    </div>
  );
}

// --- Elenco di collezione --------------------------------------------------------

// Le pagine del GM: le tre collezioni di asset + la calibrazione (catalogo §11).
type PaginaGM = TipoAsset | "calibrazione";

const PAGINE: { id: PaginaGM; etichetta: string }[] = [
  { id: "stagioni", etichetta: "Stagioni" },
  { id: "piani", etichetta: "Piani" },
  { id: "mob", etichetta: "Mob" },
  { id: "archetipi", etichetta: "Archetipi" },
  { id: "calibrazione", etichetta: "Calibrazione" },
];

function CardAsset({ vista, tipo, apri, duplica }: {
  vista: AssetVista; tipo: TipoAsset;
  apri: (slug: string) => void; duplica: (slug: string) => void;
}) {
  const elimina = useEliminaAsset(tipo);
  const locale = vista.origine === "locale";
  return (
    <div className={`flex flex-col gap-1 rounded-lg border bg-pietra p-3 ${
      vista.valido ? "border-pergamena/20" : "border-sangue/40 opacity-60"
    }`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate font-bold text-torcia">{vista.etichetta}</span>
        <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider ${
          !vista.valido ? "border-sangue/50 text-sangue"
          : locale ? "border-muschio/50 text-muschio" : "border-pergamena/30 text-pergamena/60"
        }`}>
          {vista.valido ? vista.origine : "corrotto"}
        </span>
      </div>
      <span className="truncate text-xs text-pergamena/50">{vista.slug}</span>
      {vista.tags.length > 0 && (
        <span className="truncate text-xs text-pergamena/40">#{vista.tags.join(" #")}</span>
      )}
      {vista.valido && (
        <div className="flex gap-2 pt-1 text-xs">
          <button onClick={() => duplica(vista.slug)} className="text-torcia/80 hover:text-torcia">Duplica</button>
          {locale && (
            <>
              <button onClick={() => apri(vista.slug)} className="text-pergamena/70 hover:text-pergamena">Modifica</button>
              <button onClick={() => elimina.mutate({ slug: vista.slug })} className="text-sangue/70 hover:text-sangue">Elimina</button>
            </>
          )}
          {!locale && <span className="text-pergamena/40">🔒 ufficiale</span>}
        </div>
      )}
    </div>
  );
}

function Libreria({ collezione }: { collezione: TipoAsset }) {
  const [editor, setEditor] = useState<Editor>({ modo: "chiuso" });
  const assets = useAssets(collezione);
  const chiudi = () => setEditor({ modo: "chiuso" });

  const apriEditor = async (slug: string | null, duplica: boolean) => {
    const nuovo = slug === null || duplica;
    const base = async <T,>(vuoto: T): Promise<T> => {
      if (slug === null) return vuoto;
      const asset = await api.asset<T & { slug: string }>(collezione, slug);
      return duplica ? { ...asset, slug: `${asset.slug}-copia` } : asset;
    };
    if (collezione === "mob") setEditor({ modo: "mob", corpo: await base(MOB_VUOTO), nuovo });
    if (collezione === "piani") setEditor({ modo: "piano", corpo: await base(PIANO_VUOTO), nuovo });
    if (collezione === "stagioni") setEditor({ modo: "stagione", corpo: await base(STAGIONE_VUOTA), nuovo });
    if (collezione === "archetipi") setEditor({ modo: "archetipo", corpo: await base(ARCHETIPO_VUOTO), nuovo });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <button onClick={() => void apriEditor(null, false)}
          className="rounded border border-torcia/60 bg-torcia/10 px-3 py-1 text-sm font-bold text-torcia hover:bg-torcia/25">
          ＋ Nuovo
        </button>
      </div>

      {editor.modo === "mob" && <EditorMob iniziale={editor.corpo} nuovo={editor.nuovo} chiudi={chiudi} />}
      {editor.modo === "piano" && <EditorPiano iniziale={editor.corpo} nuovo={editor.nuovo} chiudi={chiudi} />}
      {editor.modo === "stagione" && <EditorStagione iniziale={editor.corpo} nuovo={editor.nuovo} chiudi={chiudi} />}
      {editor.modo === "archetipo" && <EditorArchetipo iniziale={editor.corpo} nuovo={editor.nuovo} chiudi={chiudi} />}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {(assets.data?.asset ?? []).map((vista) => (
          <CardAsset key={vista.slug} vista={vista} tipo={collezione}
            apri={(slug) => void apriEditor(slug, false)}
            duplica={(slug) => void apriEditor(slug, true)} />
        ))}
      </div>
      {assets.data?.asset.length === 0 && (
        <p className="text-center italic text-pergamena/50">
          Collezione vuota: gli architetti del dungeon attendono il tuo primo asset.
        </p>
      )}
    </div>
  );
}

export function GameMaster() {
  const [pagina, setPagina] = useState<PaginaGM>("stagioni");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-1">
        {PAGINE.map((p) => (
          <button key={p.id}
            onClick={() => setPagina(p.id)}
            className={`rounded px-3 py-1 text-sm transition ${
              pagina === p.id
                ? "bg-torcia/15 font-bold text-torcia"
                : "text-pergamena/60 hover:bg-pergamena/10"
            }`}>
            {p.etichetta}
          </button>
        ))}
      </div>
      {pagina === "calibrazione"
        ? <Calibrazione />
        : <Libreria key={pagina} collezione={pagina} />}
    </div>
  );
}
