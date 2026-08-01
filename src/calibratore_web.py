"""Console di calibrazione **web locale** (host-tool, fuori dal motore).

Una UI da browser — non da terminale — per *distribuire e calibrare* tutta la parte numerica
del gioco senza toccare il codice: i profili per-entità dei nemici (statistiche base +
geometria + resistenze) **e** i coefficienti globali §11. Ogni voce mostra la **spiegazione
del proprio impatto** (il campo `Param.spiegazione`), con default, range, unità, stato di
override e reset; per un'entità un pannello **Anteprima** calcola i numeri risultanti.

Architettura (C-2a/C-5): il motore resta headless; questo è un host/tool fuori dal motore.
Il grosso passa da `motore.calibrazione`; l'**anteprima** riusa le derivate/risolutore reali
(`derivate`, `combattimento.mult_resistenza`, i componenti `Primarie`/`Corredo`/`Resistenze`)
su un'entità **usa-e-getta** nel World corrente — creata e subito eliminata, mai un
`switch_world` (invariante E-2). Zero nuove dipendenze: solo stdlib (`http.server`, `json`,
`webbrowser`). La logica sta in funzioni testabili; l'HTTP è un guscio sottile. Server
**single-thread** su `127.0.0.1` (solo locale): le richieste sono serializzate. Gli override
scritti valgono **dal prossimo avvio del motore** (le costanti pubbliche di `calibrazione`
sono derivate all'import).
"""

from __future__ import annotations

import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from contracts import Archetipo, Grado
from motore import calibrazione as cal

# --- Backend: funzioni pure-ish sopra cal.* (testabili senza HTTP) -------------

_SOTTO_GEOMETRIA = ("armatura", "taglia", "arma")


def _e_override(chiave: str) -> bool:
    """Vero se il valore effettivo diverge dal default (badge 'modificato')."""
    return cal.valore(chiave) != cal.CATALOGO[chiave].default


def _voce(p: cal.Param) -> dict:
    """Serializza un `Param` per la UI, con classificazione sezione/gruppo/sotto."""
    d: dict = {
        "chiave": p.chiave,
        "valore": cal.valore(p.chiave),
        "default": p.default,
        "spiegazione": p.spiegazione,
        "dominio": p.dominio,
        "unita": p.unita,
        "tipo": p.tipo,
        "scelte": list(p.scelte),
        "override": _e_override(p.chiave),
    }
    if p.chiave.startswith("ARCH."):
        _, arch, *resto = p.chiave.split(".")
        d["sezione"] = "nemico"
        d["gruppo"] = arch
        d["etichetta"] = ".".join(resto)
        d["sotto"] = (
            "Resistenze" if resto[0] == "res"
            else "Geometria" if resto[0] in _SOTTO_GEOMETRIA
            else "Statistiche"
        )
    else:
        d["sezione"] = "globale"
        d["gruppo"] = p.categoria
        d["etichetta"] = p.chiave
        d["sotto"] = p.categoria
    return d


def costruisci_vista() -> dict:
    """Stato completo per il frontend: tutte le voci + l'elenco degli archetipi."""
    archetipi = [
        {"archetipo": a.value, "nome": nome, "titolo": nome.capitalize()}
        for a, nome in cal._NOME_ARCHETIPO.items()
    ]
    return {
        "voci": [_voce(p) for p in cal.elenco()],
        "archetipi": archetipi,
        "gradi": [g.value for g in Grado],
        "percorso_override": str(cal.PERCORSO_OVERRIDE),
    }


def applica(chiave: str, grezzo: object) -> dict:
    """Imposta un override (validato/coerced da `cal.imposta`). Non persiste su disco."""
    try:
        v = cal.imposta(chiave, grezzo)
    except ValueError as e:
        return {"ok": False, "errore": f"valore non valido: {e}"}
    except KeyError:
        return {"ok": False, "errore": f"chiave sconosciuta: {chiave}"}
    return {"ok": True, "valore": v, "override": _e_override(chiave)}


def azzera(chiave: str) -> dict:
    """Rimuove l'override di `chiave` (torna al default)."""
    if chiave not in cal.CATALOGO:
        return {"ok": False, "errore": f"chiave sconosciuta: {chiave}"}
    cal.azzera(chiave)
    return {"ok": True, "valore": cal.valore(chiave), "override": False}


def salva() -> dict:
    """Persiste su disco i soli override divergenti dal default."""
    percorso = cal.salva_override()
    n = sum(1 for k, v in cal.override_correnti().items() if v != cal.CATALOGO[k].default)
    return {"ok": True, "percorso": str(percorso), "n": n}


def anteprima(archetipo: str, grado: str, livello: int) -> dict:
    """Numeri risultanti per un'entità coi valori **freschi** (override in memoria).

    Riusa le derivate reali (nessuna formula duplicata): istanzia un'entità **usa-e-getta**
    nel World corrente e la elimina subito (`delete_entity`). Niente `switch_world` — quello
    vive solo al confine save/load (invariante trasversale)."""
    import esper

    from contracts import TipoDanno
    from motore.combattimento import mult_resistenza
    from motore.corredo import Corredo
    from motore.derivate import acc_eff, atk_eff, def_eff, eva_eff, max_hp
    from motore.modificatori import ResistenzaMod, Resistenze
    from motore.statistiche import Primarie

    arch = Archetipo(archetipo)
    grad = Grado(grado)
    profilo = cal.profilo_corrente(arch)  # fresco, non da REGISTRY_ARCHETIPI (cache-ato)
    primarie = cal.primarie_da_archetipo(arch, grad, livello, profilo=profilo)
    res = {t: v for t, v in profilo.resistenze.items() if v != 0}

    comps: list[object] = [
        Primarie(valori=dict(primarie)),
        Corredo(armatura=profilo.armatura, taglia=profilo.taglia, arma=profilo.arma),
    ]
    if res:
        comps.append(Resistenze(voci=[
            ResistenzaMod(contro=t, valore=v, fonte="anteprima") for t, v in res.items()
        ]))
    ent = esper.create_entity(*comps)
    try:
        return {
            "primarie": {k.value: v for k, v in primarie.items()},
            "max_hp": max_hp(ent),
            "atk_eff": atk_eff(ent),
            "def_eff_centesimi": def_eff(ent),
            "eva_eff": round(eva_eff(ent), 4),
            "acc_eff": round(acc_eff(ent), 4),
            "resistenze_mult": {
                t.value: round(mult_resistenza(ent, t), 4)
                for t in (TipoDanno.MISCHIA, TipoDanno.FUOCO, TipoDanno.VELENO)
            },
            "geometria": {
                "armatura": profilo.armatura, "taglia": profilo.taglia, "arma": profilo.arma,
            },
        }
    finally:
        esper.delete_entity(ent, immediate=True)


# --- Pagina (autonoma: CSS/JS inline, nessuna risorsa esterna) -----------------

PAGINA_HTML = """<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Calibrazione — DCC</title>
<style>
:root{--bg:#12141a;--panel:#1c1f27;--panel2:#232733;--bd:#333a48;--fg:#e6e9ef;--mut:#9aa3b2;
--acc:#5aa0ff;--ok:#3ecf8e;--warn:#ffb454;--err:#ff6b6b}
*{box-sizing:border-box}body{margin:0;font:14px/1.5 system-ui,Segoe UI,sans-serif;background:var(--bg);color:var(--fg)}
header{display:flex;align-items:center;gap:12px;padding:10px 16px;background:var(--panel);border-bottom:1px solid var(--bd);position:sticky;top:0;z-index:5}
header h1{font-size:15px;margin:0;font-weight:600}
header .sp{flex:1}
button{font:inherit;background:var(--panel2);color:var(--fg);border:1px solid var(--bd);border-radius:8px;padding:6px 12px;cursor:pointer}
button:hover{border-color:var(--acc)}button.primary{background:var(--acc);border-color:var(--acc);color:#08101f;font-weight:600}
.wrap{display:flex;min-height:calc(100vh - 49px)}
nav{width:230px;flex:none;background:var(--panel);border-right:1px solid var(--bd);padding:10px;overflow:auto}
nav h2{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);margin:14px 6px 6px}
nav a{display:block;padding:6px 10px;border-radius:8px;color:var(--fg);text-decoration:none;cursor:pointer}
nav a:hover{background:var(--panel2)}nav a.on{background:var(--acc);color:#08101f;font-weight:600}
main{flex:1;padding:16px 20px;overflow:auto}
.hint{color:var(--mut);font-size:12.5px;margin:0 0 14px}
.sub{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);margin:18px 0 8px;border-bottom:1px solid var(--bd);padding-bottom:4px}
.card{background:var(--panel);border:1px solid var(--bd);border-radius:12px;padding:12px 14px;margin:10px 0}
.card .top{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.card .nm{font-weight:600}
.card input,.card select{font:inherit;background:var(--panel2);color:var(--fg);border:1px solid var(--bd);border-radius:8px;padding:5px 8px;min-width:120px}
.badge{font-size:11px;padding:2px 7px;border-radius:999px;border:1px solid var(--bd);color:var(--mut)}
.badge.mod{color:var(--warn);border-color:var(--warn)}
.meta{color:var(--mut);font-size:12px}
.exp{margin:8px 0 0;color:#cfd6e2}
.u{color:var(--mut);font-size:12px}
#prev{background:var(--panel2);border:1px solid var(--bd);border-radius:12px;padding:12px 14px;margin:6px 0 16px}
#prev .row{display:flex;gap:18px;flex-wrap:wrap;margin-top:8px}
#prev .kv{background:var(--panel);border:1px solid var(--bd);border-radius:8px;padding:6px 10px;min-width:96px}
#prev .kv b{display:block;font-size:11px;color:var(--mut);font-weight:500}
#toast{position:fixed;right:16px;bottom:16px;background:var(--panel2);border:1px solid var(--ok);color:var(--fg);padding:10px 14px;border-radius:10px;opacity:0;transition:.2s;pointer-events:none}
#toast.show{opacity:1}#toast.err{border-color:var(--err)}
.err{color:var(--err);font-size:12px;margin-top:4px}
</style></head><body>
<header>
  <h1>⚙️ Calibrazione — Distribuzione &amp; Coefficienti</h1>
  <span class="sp"></span>
  <span class="meta" id="ovpath"></span>
  <button class="primary" id="save">Salva su disco</button>
</header>
<div class="wrap">
  <nav id="nav"></nav>
  <main id="main"></main>
</div>
<div id="toast"></div>
<script>
let VISTA=null, SEL=null;
const $=(s,r=document)=>r.querySelector(s);
async function j(url,opts){const r=await fetch(url,opts);return r.json();}
function toast(msg,err){const t=$('#toast');t.textContent=msg;t.className='show'+(err?' err':'');setTimeout(()=>t.className='',2200);}

async function carica(){
  VISTA=await j('/api/vista');
  $('#ovpath').textContent='override → '+VISTA.percorso_override;
  const nav=$('#nav');nav.innerHTML='';
  const h1=document.createElement('h2');h1.textContent='Nemici';nav.appendChild(h1);
  VISTA.archetipi.forEach(a=>nav.appendChild(voceNav('nemico:'+a.archetipo,a.titolo)));
  const cats=[...new Set(VISTA.voci.filter(v=>v.sezione==='globale').map(v=>v.gruppo))];
  const h2=document.createElement('h2');h2.textContent='Coefficienti globali §11';nav.appendChild(h2);
  cats.forEach(c=>nav.appendChild(voceNav('globale:'+c,c)));
  seleziona(SEL||('nemico:'+VISTA.archetipi[0].archetipo));
}
function voceNav(id,label){const a=document.createElement('a');a.textContent=label;a.dataset.id=id;
  a.onclick=()=>seleziona(id);return a;}
function seleziona(id){SEL=id;document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('on',a.dataset.id===id));render();}

function render(){
  const [sez,key]=SEL.split(/:(.*)/s);
  const main=$('#main');main.innerHTML='';
  const nota=document.createElement('p');nota.className='hint';
  nota.textContent='Ogni voce spiega il proprio impatto. Le modifiche valgono dal prossimo avvio del motore; premi “Salva su disco” per renderle persistenti.';
  main.appendChild(nota);
  if(sez==='nemico'){
    const a=VISTA.archetipi.find(x=>x.archetipo===key);
    const t=document.createElement('h2');t.style.margin='0 0 4px';t.textContent='Nemico — '+a.titolo;main.appendChild(t);
    main.appendChild(pannelloAnteprima(key));
    const voci=VISTA.voci.filter(v=>v.sezione==='nemico'&&v.gruppo===key);
    ['Statistiche','Geometria','Resistenze'].forEach(s=>{
      const gr=voci.filter(v=>v.sotto===s);if(!gr.length)return;
      main.appendChild(sub(s));gr.forEach(v=>main.appendChild(card(v)));
    });
  }else{
    const voci=VISTA.voci.filter(v=>v.sezione==='globale'&&v.gruppo===key);
    const t=document.createElement('h2');t.style.margin='0 0 8px';t.textContent=key;main.appendChild(t);
    voci.forEach(v=>main.appendChild(card(v)));
  }
}
function sub(txt){const d=document.createElement('div');d.className='sub';d.textContent=txt;return d;}

function card(v){
  const c=document.createElement('div');c.className='card';c.dataset.chiave=v.chiave;
  const top=document.createElement('div');top.className='top';
  const nm=document.createElement('span');nm.className='nm';nm.textContent=v.etichetta;top.appendChild(nm);
  let inp;
  if(v.tipo==='scelta'){inp=document.createElement('select');
    v.scelte.forEach(s=>{const o=document.createElement('option');o.value=o.textContent=s;inp.appendChild(o);});
    inp.value=v.valore;}
  else{inp=document.createElement('input');inp.type='number';inp.step=(v.tipo==='int')?'1':'any';inp.value=v.valore;}
  top.appendChild(inp);
  if(v.unita){const u=document.createElement('span');u.className='u';u.textContent=v.unita;top.appendChild(u);}
  const badge=document.createElement('span');badge.className='badge'+(v.override?' mod':'');
  badge.textContent=v.override?'modificato':'default';top.appendChild(badge);
  const meta=document.createElement('span');meta.className='meta';
  meta.textContent='default '+v.default+' · '+v.dominio;top.appendChild(meta);
  const rst=document.createElement('button');rst.textContent='Reset';top.appendChild(rst);
  c.appendChild(top);
  const errln=document.createElement('div');errln.className='err';errln.style.display='none';c.appendChild(errln);
  const exp=document.createElement('p');exp.className='exp';exp.textContent=v.spiegazione;c.appendChild(exp);

  const setBadge=(ov)=>{badge.className='badge'+(ov?' mod':'');badge.textContent=ov?'modificato':'default';v.override=ov;};
  const commit=async()=>{errln.style.display='none';
    const r=await j('/api/imposta',{method:'POST',headers:{'content-type':'application/json'},
      body:JSON.stringify({chiave:v.chiave,valore:inp.value})});
    if(!r.ok){errln.textContent=r.errore;errln.style.display='';return;}
    inp.value=r.valore;setBadge(r.override);if(SEL.startsWith('nemico:'))aggiornaAnteprima();};
  inp.onchange=commit;
  rst.onclick=async()=>{const r=await j('/api/azzera',{method:'POST',headers:{'content-type':'application/json'},
      body:JSON.stringify({chiave:v.chiave})});if(r.ok){inp.value=r.valore;setBadge(false);errln.style.display='none';
      if(SEL.startsWith('nemico:'))aggiornaAnteprima();}};
  return c;
}

function pannelloAnteprima(archetipo){
  const p=document.createElement('div');p.id='prev';
  const head=document.createElement('div');head.style.display='flex';head.style.alignItems='center';head.style.gap='10px';
  const t=document.createElement('b');t.textContent='Anteprima numeri risultanti';head.appendChild(t);
  const gl=document.createElement('label');gl.className='meta';gl.textContent='grado';head.appendChild(gl);
  const gsel=document.createElement('select');gsel.id='pv-grado';
  VISTA.gradi.forEach(g=>{const o=document.createElement('option');o.value=o.textContent=g;gsel.appendChild(o);});head.appendChild(gsel);
  const ll=document.createElement('label');ll.className='meta';ll.textContent='livello';head.appendChild(ll);
  const linp=document.createElement('input');linp.id='pv-liv';linp.type='number';linp.min='1';linp.value='1';linp.style.width='72px';head.appendChild(linp);
  p.appendChild(head);
  const body=document.createElement('div');body.id='pv-body';body.className='row';p.appendChild(body);
  p.dataset.archetipo=archetipo;
  gsel.onchange=aggiornaAnteprima;linp.onchange=aggiornaAnteprima;
  setTimeout(aggiornaAnteprima,0);
  return p;
}
async function aggiornaAnteprima(){
  const p=$('#prev');if(!p)return;
  const r=await j('/api/anteprima',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({archetipo:p.dataset.archetipo,grado:$('#pv-grado').value,livello:parseInt($('#pv-liv').value||'1')})});
  const b=$('#pv-body');b.innerHTML='';
  if(r.errore){b.textContent=r.errore;return;}
  const kv=(k,val)=>{const d=document.createElement('div');d.className='kv';d.innerHTML='<b>'+k+'</b>'+val;return d;};
  const P=r.primarie;
  b.appendChild(kv('Primarie','FRZ '+P.forza+' · DES '+P.destrezza+' · COS '+P.costituzione+' · INT '+P.intelligenza+' · DIF '+P.difesa+' · SAG '+P.saggezza+' · FRT '+P.fortuna));
  b.appendChild(kv('max_hp',r.max_hp));
  b.appendChild(kv('atk_eff',r.atk_eff));
  b.appendChild(kv('def_eff (cent.)',r.def_eff_centesimi));
  b.appendChild(kv('eva_eff',r.eva_eff));
  b.appendChild(kv('acc_eff',r.acc_eff));
  b.appendChild(kv('geometria',r.geometria.armatura+' / '+r.geometria.taglia+' / '+r.geometria.arma));
  const R=r.resistenze_mult;
  b.appendChild(kv('mult danno','mischia '+R.mischia+' · fuoco '+R.fuoco+' · veleno '+R.veleno));
}

$('#save').onclick=async()=>{const r=await j('/api/salva',{method:'POST'});
  if(r.ok)toast('Salvati '+r.n+' override → '+r.percorso);else toast('errore salvataggio',true);};
carica();
</script></body></html>
"""


# --- Guscio HTTP ---------------------------------------------------------------

_ROTTE_POST = {
    "/api/imposta": lambda d: applica(d["chiave"], d["valore"]),
    "/api/azzera": lambda d: azzera(d["chiave"]),
    "/api/salva": lambda d: salva(),
    "/api/anteprima": lambda d: anteprima(d["archetipo"], d["grado"], int(d.get("livello", 1))),
}


class _Handler(BaseHTTPRequestHandler):
    def _json(self, obj: object, code: int = 200) -> None:
        corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self) -> None:  # noqa: N802 (nome imposto da BaseHTTPRequestHandler)
        if self.path in ("/", "/index.html"):
            corpo = PAGINA_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
        elif self.path == "/api/vista":
            self._json(costruisci_vista())
        else:
            self._json({"errore": "non trovato"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        rotta = _ROTTE_POST.get(self.path)
        if rotta is None:
            self._json({"errore": "non trovato"}, 404)
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            dati = json.loads(self.rfile.read(n) or b"{}") if n else {}
            self._json(rotta(dati))
        except (ValueError, KeyError, TypeError) as e:
            self._json({"ok": False, "errore": str(e)}, 400)

    def log_message(self, *args: object) -> None:  # silenzia il log per-richiesta
        pass


def avvia(port: int = 8765, *, apri: bool = True) -> None:
    """Avvia il server locale (127.0.0.1) e apre il browser. Porta occupata → effimera."""
    try:
        server = HTTPServer(("127.0.0.1", port), _Handler)
    except OSError:
        server = HTTPServer(("127.0.0.1", 0), _Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"[calibratore-web] in ascolto su {url}  (Ctrl-C per uscire)")
    if apri:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[calibratore-web] chiuso.")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:  # pragma: no cover (entry point)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    port = 8765
    if "--port" in argv:
        i = argv.index("--port")
        port = int(argv[i + 1])
    avvia(port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
