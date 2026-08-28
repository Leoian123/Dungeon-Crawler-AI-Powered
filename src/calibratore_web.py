"""BACKEND della calibrazione (host-tool, fuori dal motore): il servizio che le
console admin vestono.

Le funzioni qui — vista, override (applica/azzera/salva), anteprima — sono la
SUPERFICIE UNICA con cui si *distribuisce e calibra* la parte numerica del gioco
senza toccare il codice: i profili per-entità dei nemici (statistiche base +
geometria + resistenze) **e** i coefficienti globali §11, ognuno con la
**spiegazione del proprio impatto** (`Param.spiegazione`), default, range, unità
e stato di override. Su questo branch il consumatore è l'host web
(`host_web/app.py` → `/api/calibrazione/*`) e la UI è la pagina Calibrazione del
GM mode nella SPA — una sola console admin, la migliore (`gioca_web.bat`).

Architettura (C-2a/C-5): il motore resta headless; questo è un host/tool fuori
dal motore. Il grosso passa da `motore.calibrazione`; l'**anteprima** riusa le
derivate/risolutore reali (`derivate`, `combattimento.mult_resistenza`, i
componenti `Primarie`/`Corredo`/`Resistenze`) su un'entità **usa-e-getta** nel
World corrente — creata e subito eliminata, mai uno `switch_world` (invariante
E-2). Gli override scritti valgono **dal prossimo avvio del motore** (le
costanti pubbliche di `calibrazione` sono derivate all'import).
"""

from __future__ import annotations

from contracts import Grado
from motore import calibrazione as cal

# --- Backend: funzioni pure-ish sopra cal.* (testabili senza HTTP) -------------

_SOTTO_GEOMETRIA = ("armatura", "taglia", "arma")


def _e_override(chiave: str) -> bool:
    """Vero se il valore effettivo diverge dal default (badge 'modificato')."""
    return cal.valore(chiave) != cal.CATALOGO[chiave].default


def esiste(chiave: str) -> bool:
    """Vero se `chiave` è una voce del catalogo — per gli host (es. `host_web`) che
    parlano alla calibrazione SOLO via questo backend, senza importare il motore."""
    return chiave in cal.CATALOGO


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
        {"archetipo": slug, "nome": slug, "titolo": slug.capitalize()}
        for slug in cal.ARCHETIPI_BASE
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
    from motore.derivate import acc_fis_eff, acc_mag_eff, atk_eff, def_eff, eva_eff, max_hp
    from motore.modificatori import ResistenzaMod, Resistenze
    from motore.statistiche import Primarie

    if archetipo not in cal.REGISTRY_ARCHETIPI:
        raise ValueError(f"archetipo sconosciuto: {archetipo!r}")
    grad = Grado(grado)
    profilo = cal.profilo_corrente(archetipo)  # fresco, non da REGISTRY_ARCHETIPI (cache-ato)
    primarie = cal.primarie_da_archetipo(archetipo, grad, livello, profilo=profilo)
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
            "acc_fis_eff": round(acc_fis_eff(ent), 4),
            "acc_mag_eff": round(acc_mag_eff(ent), 4),
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


# ⛔ La PAGINA standalone (HTML inline + `http.server` + `python -m calibratore_web`)
# è stata RITIRATA su questo branch: era il DOPPIONE in vanilla-JS della pagina
# Calibrazione del GM mode nella SPA (stesso backend, queste funzioni; stessa
# copertura: vista, override, salva, anteprima). Una sola superficie admin —
# `gioca_web.bat` → GM mode → Calibrazione. Sul branch del cuore (headless,
# senza SPA) la console standalone resta: qui sarebbe solo drift che diverge.
