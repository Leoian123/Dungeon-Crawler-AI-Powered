// La scheda del PG (SchedaVista) + il pannello party A SLOT: oggi il motore ha
// il solo protagonista (singleton), gli slot vuoti sono il seam per il party
// futuro — la UI è pronta, il motore non si tocca.
//
// Registro tipografico HUD (best practice game-UI): numeri e sigle in
// monospazio tabellare, MAI nomi di dominio lunghi nelle celle — le derivate
// hanno etichette corte qui (playtest 2026-08-20: «accuratezza_fisica»
// sfondava la colonna e deformava il pannello).

import type { EquipVista, SchedaVista, SkillVista } from "../api/tipi";
import { useScheda } from "../api/query";

function BarraHp({ hp, hpMax }: { hp: number; hpMax: number }) {
  const frazione = hpMax > 0 ? hp / hpMax : 0;
  const colore =
    frazione > 0.5 ? "bg-muschio" : frazione > 0.25 ? "bg-torcia" : "bg-sangue";
  return (
    <div className="flex items-center gap-2">
      <span className="etichetta-hud w-7 shrink-0 text-pergamena/50">HP</span>
      <div className="h-3 flex-1 overflow-hidden rounded-sm border border-pergamena/15 bg-abisso">
        <div
          className={`h-full ${colore} transition-all duration-300`}
          style={{ width: `${Math.round(frazione * 100)}%` }}
        />
      </div>
      <span className="w-14 shrink-0 text-right font-hud text-xs tabular-nums text-pergamena/85">
        {hp}/{hpMax}
      </span>
    </div>
  );
}

function BarraMana({ mana, manaMax }: { mana: number; manaMax: number }) {
  if (manaMax <= 0) return null;
  return (
    <div className="flex items-center gap-2">
      <span className="etichetta-hud w-7 shrink-0 text-pergamena/50">MP</span>
      <div className="h-2 flex-1 overflow-hidden rounded-sm border border-pergamena/10 bg-abisso">
        <div
          className="h-full bg-sigillo transition-all duration-300"
          style={{ width: `${Math.round((mana / manaMax) * 100)}%` }}
        />
      </div>
      <span className="w-14 shrink-0 text-right font-hud text-xs tabular-nums text-pergamena/60">
        {mana}/{manaMax}
      </span>
    </div>
  );
}

// Le derivate hanno nomi di dominio lunghi: nel pannello entrano come SIGLE
// (il nome pieno resta nel title al passaggio del mouse).
const SIGLE_DERIVATE: Record<string, string> = {
  attacco: "ATK",
  difesa: "DEF",
  colpo: "COLPO",
  iniziativa: "INIZ",
  evasione: "EVA",
  accuratezza_fisica: "ACC·F",
  accuratezza_magica: "ACC·M",
};

function sigla(nome: string): string {
  return SIGLE_DERIVATE[nome] ?? nome.slice(0, 5).toUpperCase();
}

// Skill ed equipaggiamento: la UI legge il CONTRATTO, non lo stato del motore.
function Skills({ skills }: { skills: SkillVista[] }) {
  if (skills.length === 0) return null;
  return (
    <div className="flex flex-col gap-0.5 border-t border-pergamena/10 pt-1.5">
      {skills.map((s) => (
        <div
          key={s.chiave}
          className={`flex min-w-0 items-baseline justify-between gap-2 font-hud text-xs ${
            s.pronta ? "text-pergamena/80" : "text-pergamena/35"
          }`}
          title={s.descrizione || undefined}
        >
          <span className="min-w-0 truncate">{s.etichetta}</span>
          <span className="shrink-0 tabular-nums text-[0.7rem]">
            {s.cd_residuo > 0
              ? `↻${s.cd_residuo}`
              : s.costo_mana > 0
                ? `${s.costo_mana}◈`
                : "—"}
          </span>
        </div>
      ))}
    </div>
  );
}

function Equipaggiamento({ equip }: { equip: EquipVista[] }) {
  if (equip.length === 0) return null;
  return (
    <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 border-t border-pergamena/10 pt-1.5 font-hud text-[0.7rem]">
      {equip.map((e) => (
        <div
          key={e.slot}
          className="flex min-w-0 items-baseline justify-between gap-1"
          title={e.descrizione || e.nome || e.categoria}
        >
          <span className="shrink-0 text-pergamena/45">{e.slot.replace("_", " ")}</span>
          <span
            className={`min-w-0 truncate text-right ${
              e.nome ? "text-torcia/90" : "text-pergamena/50"
            }`}
          >
            {e.nome || e.categoria}
          </span>
        </div>
      ))}
    </div>
  );
}

export function SchedaPG({ scheda }: { scheda: SchedaVista }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-pergamena/20 bg-pietra p-3">
      <div className="flex min-w-0 items-baseline justify-between gap-2">
        <span className="titolo-insegna min-w-0 truncate text-sm text-torcia">
          {scheda.nome}
        </span>
        <span className="etichetta-hud shrink-0 text-pergamena/50">
          P{scheda.livello} · t{scheda.tick_piano}
        </span>
      </div>
      <BarraHp hp={scheda.hp} hpMax={scheda.hp_max} />
      <BarraMana mana={scheda.mana} manaMax={scheda.mana_max} />
      {scheda.descrittori.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {scheda.descrittori.map((d, i) => (
            <span
              key={i}
              className="rounded-full border border-pergamena/25 px-2 py-0.5 font-hud text-[0.65rem] uppercase tracking-wider text-pergamena/80"
            >
              {d}
            </span>
          ))}
        </div>
      )}
      <div className="grid grid-cols-3 gap-x-2 gap-y-0.5 font-hud text-xs tabular-nums">
        {Object.entries(scheda.primarie).map(([nome, valore]) => (
          <div key={nome} className="flex items-baseline justify-between gap-1" title={nome}>
            <span className="text-pergamena/50">{nome.slice(0, 3).toUpperCase()}</span>
            <b className="text-pergamena">{valore}</b>
          </div>
        ))}
        {scheda.primarie_occulte.map((nome) => (
          <div key={nome} className="flex items-baseline justify-between gap-1" title={nome}>
            <span className="text-pergamena/35">{nome.slice(0, 3).toUpperCase()}</span>
            <b className="text-pergamena/45">?</b>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 border-t border-pergamena/10 pt-1.5 font-hud text-xs tabular-nums">
        {Object.entries(scheda.derivate).map(([nome, valore]) => (
          <div key={nome} className="flex items-baseline justify-between gap-1" title={nome}>
            <span className="text-pergamena/45">{sigla(nome)}</span>
            <b className="text-pergamena/85">{valore}</b>
          </div>
        ))}
      </div>
      <Skills skills={scheda.skills ?? []} />
      <Equipaggiamento equip={scheda.equip ?? []} />
    </div>
  );
}

// Dimensione del party (gioco single player: più personaggi, un solo giocatore).
const SLOT_PARTY = 4;

export function PannelloParty() {
  const scheda = useScheda(true);
  const party = scheda.data?.party ?? [];
  const liberi = Math.max(0, SLOT_PARTY - party.length);
  return (
    <div className="flex flex-col gap-2">
      <h2 className="etichetta-hud text-pergamena/60">
        Party {party.length}/{SLOT_PARTY}
      </h2>
      {party.map((pg) => (
        <SchedaPG key={pg.uuid} scheda={pg} />
      ))}
      {Array.from({ length: liberi }, (_, i) => (
        <div
          key={i}
          className="flex min-h-10 items-center justify-center rounded-lg border border-dashed border-pergamena/15 font-hud text-[0.65rem] uppercase tracking-widest text-pergamena/35"
        >
          slot libero
        </div>
      ))}
    </div>
  );
}
