// Il REGISTRO delle competenze (nodo S) — vista secondaria della Partita,
// per lo standard di architettura (2026-08-26): la consultazione ha la sua
// superficie piena, mai un riquadro appeso alla sidebar. Livello e usi li
// DERIVA il motore; qui si veste il conto — junk compreso, che è metà del
// tono («Respirare in discesa, Lv 3»).

import { useSkillRun } from "../api/query";
import type { SkillRiga } from "../api/tipi";

/** La tavolozza dei DOMINI (vestizione: la mappa dei sistemi). */
const COLORE_DOMINIO: Record<string, string> = {
  combattimento: "border-sangue/50 text-sangue/90",
  magia: "border-show/50 text-show",
  artigianato: "border-torcia/50 text-torcia/90",
  sopravvivenza: "border-muschio/50 text-muschio",
  movimento: "border-cyan-300/50 text-cyan-200",
  mondana: "border-pergamena/25 text-pergamena/45",
};

function CartaSkill({ riga }: { riga: SkillRiga }) {
  const colore =
    COLORE_DOMINIO[riga.dominio] ?? "border-pergamena/25 text-pergamena/60";
  return (
    <article
      className={`rounded-lg border bg-pietra p-3 ${
        riga.dominio === "mondana" ? "opacity-70" : ""
      } ${colore.split(" ")[0]}`}
      title={riga.testo}
    >
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <h3 className="min-w-0 truncate font-bold text-pergamena/90">
          {riga.nome}
        </h3>
        <span className="shrink-0 font-hud text-sm font-bold text-torcia">
          Lv {riga.livello}
        </span>
      </div>
      <p className="mb-2 font-hud text-xs leading-snug text-pergamena/60">
        {riga.testo}
      </p>
      <div className="flex items-center gap-2 font-hud text-[0.65rem] uppercase tracking-wider">
        <span className={`rounded border px-1.5 ${colore}`}>{riga.dominio}</span>
        {riga.tipo === "attiva" && riga.mossa && (
          <span className="text-pergamena/45">
            governa {riga.mossa.replace(/_/g, " ")}
          </span>
        )}
        {riga.usi > 0 && (
          <span className="ml-auto text-pergamena/40">usi {riga.usi}</span>
        )}
      </div>
    </article>
  );
}

export function RegistroSkill() {
  const query = useSkillRun(true);
  const righe = query.data?.skill ?? [];
  const ordinate = [...righe].sort(
    (a, b) => b.livello - a.livello || a.nome.localeCompare(b.nome),
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="titolo-insegna text-lg text-torcia">
          Registro delle competenze
        </h2>
        <span className="font-hud text-sm text-pergamena/50">
          {righe.length} skill
        </span>
      </div>
      {righe.length === 0 && (
        <p className="font-hud text-sm italic text-pergamena/40">
          Il sistema non ha annunciato skill per questa run.
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {ordinate.map((r) => (
          <CartaSkill key={r.slug} riga={r} />
        ))}
      </div>
      <p className="font-hud text-[0.7rem] italic text-pergamena/35">
        Il sistema conta tutto. Anche quello che preferiresti non sapesse.
      </p>
    </div>
  );
}
