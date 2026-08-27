"""Bonifica della prosa (2026-08-27) — il gate di FORMA sul canale unico.

Un solo dato (`REGOLE_SLOP`), quattro consumatori che non possono divergere:
la clausola nei prefissi è DERIVATA dalla tabella, il gate misura la stessa
tabella, la telemetria conta le violazioni sopravvissute, e questi lucchetti
applicano la bonifica AI NOSTRI STESSI testi (esemplari del prefisso e
fallback deterministici): il sistema che non vale per chi lo scrive non è
un sistema.
"""

from __future__ import annotations

import asyncio

from contracts import Flavor
from motore import (
    Fase,
    MasterEngine,
    PREFISSO_GM,
    PREFISSO_RIFINITURA,
    REGOLE_SLOP,
    avvia_run,
    crea_seme,
    misura_slop,
    prima_frase,
    riga_stile_derivata,
    righe_regia,
)
from provider import FakeProvider

# --- Le misure: una regola, un caso -------------------------------------------


def _slugs(violazioni) -> set[str]:
    return {v.slug for v in violazioni}


def test_similitudine_seriale() -> None:
    testo = ("Il pavimento cede come se respirasse. Le pareti sudano come se "
             "avessero febbre. La porta geme come se ricordasse.")
    assert "similitudine-seriale" in _slugs(misura_slop(testo))
    assert misura_slop("Il pavimento cede come se respirasse. Poi tace.") == ()


def test_numero_di_stanza_in_prosa() -> None:
    assert "numero-di-stanza" in _slugs(misura_slop("La stanza 4 puzza di colla."))
    assert misura_slop("La sala prove puzza di colla.") == ()


def test_frammento_eco() -> None:
    testo = "Aspetta. Ce l'ha. Si volta. La sala respira piano intorno a lui."
    assert "frammento-eco" in _slugs(misura_slop(testo))


def test_retorica_non() -> None:
    testo = ("Il custode non entra: materializza. La luce non illumina: "
             "interroga. Il resto della sala aspetta in silenzio.")
    assert "retorica-non" in _slugs(misura_slop(testo))


def test_cliche_e_lineette() -> None:
    assert "cliche" in _slugs(misura_slop("Un silenzio di tomba riempie la sala."))
    testo = ("Il bancone — lungo — trattiene — a stento — cinque lineette "
             "— di troppo, e la frase non finisce mai davvero qui.")
    assert "lineette" in _slugs(misura_slop(testo))


def test_le_soglie_scalano_sulla_lunghezza() -> None:
    """Due «come se» in un testo LUNGO (oltre una finestra §11) sono densità
    lecita: la severità non punisce la scena piena."""
    riempitivo = "La sala si allunga oltre la luce e ogni asse racconta. " * 60
    testo = riempitivo + ("Il legno cede come se respirasse. " * 2)
    assert "similitudine-seriale" not in _slugs(misura_slop(testo))


def test_frase_fiume_e_grappolo_di_che() -> None:
    """La «prosa confusa e pesante» del playtest live 2026-08-27, resa
    misurabile: l'apnea oltre le 40 parole e la sintassi che si avvita
    (tre «che» nella stessa frase)."""
    fiume_unica = ("La stanza si allunga oltre la luce dei bracieri spenti "
                   "mentre il fango sale in creste basse lungo le assi e i "
                   "manifesti scoloriti guardano un nemico dimenticato e la "
                   "pala continua a mordere la terra a intervalli regolari "
                   "senza fretta e senza stanchezza in un conteggio muto.")
    # UNA frase lunga per finestra è un respiro legittimo…
    assert "frase-fiume" not in _slugs(misura_slop(fiume_unica))
    # …DUE sono l'apnea.
    assert "frase-fiume" in _slugs(misura_slop(fiume_unica + " " + fiume_unica))
    avvitata = ("Dalla crepa viene un suono che potrebbe essere una risata "
                "che fuoriesce da polmoni che non respirano più.")
    assert "grappolo-di-che" in _slugs(misura_slop(avvitata))
    assert misura_slop("Un suono che raschia sale dal solco. Poi tace.") == ()


def test_la_voce_dei_personaggi_non_e_slop_del_narratore() -> None:
    """Riscontro utente 2026-08-27 («forse è figlia del personaggio…»): le
    regole di RITMO misurano solo la narrazione — il telegrafico del Fante
    dentro le virgolette è cadenza autorata, non slop. Fuori dalle
    virgolette, la stessa raffica resta violazione."""
    in_voce = ("«Guerra finita? No. Guerra cambia forma. Scavi profondi.» "
               "La pala riprende il suo ritmo contro la terra battuta.")
    assert "frammento-eco" not in _slugs(misura_slop(in_voce))
    da_narratore = ("La guerra è finita. No. Cambia forma. Scava ancora. "
                    "La pala riprende il suo ritmo contro la terra battuta.")
    assert "frammento-eco" in _slugs(misura_slop(da_narratore))


def test_il_filo_di_scena_conserva_la_coda_coi_fatti() -> None:
    """Il Tenente Kross del playtest live: la lore atterra in CODA alla
    battuta, e il taglio di testa (`prosa[:160]`) la troncava via — il turno
    dopo la re-inventava in un'altra versione. Il filo ora tiene la coda su
    confine di frase: il nome resta nel contesto del turno successivo."""
    from motore.tipografia import coda_su_frase

    scenografia = ("La pala cade nel fango e la maschera emette un sibilo "
                   "lungo mentre la voce arriva da lontano, filtrata "
                   "attraverso strati di membrana e di ruggine vecchia. " * 3)
    prosa = scenografia + ("Il Tenente Kross mi disse di scavare fino al "
                           "fondo, fino al silenzio.")
    coda = coda_su_frase(prosa, 360)
    assert "Tenente Kross" in coda, "la coda conserva il fatto, la testa no"
    assert prosa[:160].find("Kross") == -1, "il taglio vecchio lo perdeva"
    # E il testo corto passa intero, senza tagli.
    assert coda_su_frase("Breve e completa.", 360) == "Breve e completa."


def test_incipit_fotocopia() -> None:
    prima = "La porta si chiude alle tue spalle con uno schiocco molle."
    dopo = "Il saloon si chiude alle tue spalle con un cigolio secco."
    v = misura_slop(dopo + " Il resto della sala tace.", incipit_precedente=prima)
    assert "incipit-fotocopia" in _slugs(v)
    diverso = "Un odore di cuoio ti arriva prima della luce. Il resto tace."
    assert misura_slop(diverso, incipit_precedente=prima) == ()
    assert prima_frase(dopo).startswith("Il saloon")


# --- I consumatori derivati: un solo dato -------------------------------------


def test_la_clausola_dei_prefissi_deriva_dalla_tabella() -> None:
    """Prompt e gate non possono divergere: la clausola è generata dalla
    tabella e vive in ENTRAMBI i prefissi (corsia forte e corsia veloce)."""
    clausola = riga_stile_derivata()
    assert clausola.startswith("[stile/forma]")
    assert clausola in PREFISSO_GM
    assert clausola in PREFISSO_RIFINITURA
    for regola in REGOLE_SLOP:
        assert regola.stile in clausola


def test_righe_regia_nominano_le_violazioni() -> None:
    v = misura_slop("La stanza 4 puzza. Un silenzio di tomba la riempie.")
    regia = righe_regia(v)
    assert regia.startswith("[regia]")
    assert "dato di mappa" in regia and "cliché" in regia
    assert righe_regia(()) == ""


# --- Auto-coerenza: la bonifica vale anche per i NOSTRI testi ------------------


def test_gli_esemplari_del_prefisso_passano_la_bonifica() -> None:
    """Il few-shot è l'attrattore più forte del registro: un tic
    nell'esemplare è un tic serializzato in ogni scena (qui viveva
    «La stanza 4…», ritrovato tale e quale nel playtest live)."""
    from motore.gm import STILE_CINEMA

    esemplari = [r for r in STILE_CINEMA.split("\n") if r.startswith("[esempio/")]
    assert esemplari, "la guida deve avere i suoi esemplari"
    for riga in esemplari:
        testo = riga.split("] ", 1)[1]
        assert misura_slop(testo) == (), f"esemplare fuori bonifica: {riga[:40]}…"


def test_i_fallback_deterministici_passano_la_bonifica() -> None:
    from contracts import FattiScontro
    from motore import PROSA_NEUTRA
    from motore.gm import _resoconto_fallback

    assert misura_slop(PROSA_NEUTRA) == ()
    for fatti in (
        FattiScontro(nemico="il Fante", vittoria=True, turni=3, hp_persi=4),
        FattiScontro(nemico="il Fante", vittoria=True, turni=3, hp_persi=0),
        FattiScontro(nemico="il Fante", vittoria=False, turni=2, hp_persi=1, fuga=True),
    ):
        assert misura_slop(_resoconto_fallback(fatti)) == ()


# --- Il gate nel canale unico: retry di regia e telemetria ---------------------

_SPORCO = ("La stanza 4 trattiene il fiato come se aspettasse, e un silenzio "
           "di tomba pesa sul bancone del saloon.")
_PULITO = ("La sala del saloon trattiene il fiato. Sul bancone, la polvere "
           "disegna il contorno di bicchieri che nessuno ha spostato.")


def _arma(fase: Fase = Fase.NARRAZIONE) -> None:
    crea_seme(7)
    avvia_run(crea_singleton_fase=True, fase_iniziale=fase)


def test_engine_regia_su_violazione(mondo_isolato) -> None:
    """Rotta con bonifica: la prima bozza viola → UN giro con le note di
    regia → si tiene il testo pulito; il tally conta il giro, zero slop."""
    _arma()
    prov = FakeProvider([dict(testo=_SPORCO), dict(testo=_PULITO)])
    engine = MasterEngine.avvolgi(prov)
    esito = asyncio.run(engine.genera("gm.limatura", "p"))
    assert esito is not None and esito.testo == _PULITO
    assert len(prov.chiamate) == 2
    assert "[regia]" in prov.chiamate[1][0], "il retry porta le note di regia"
    conto = engine.tally["gm.limatura"]
    assert conto.regie == 1 and conto.slop == 0 and conto.chiamate == 2


def test_engine_accetta_e_conta_se_la_regia_non_migliora(mondo_isolato) -> None:
    """La forma non blocca mai il gioco: se anche il secondo giro viola, si
    tiene il testo migliore e la telemetria conta le violazioni."""
    _arma()
    prov = FakeProvider([dict(testo=_SPORCO), dict(testo=_SPORCO)])
    engine = MasterEngine.avvolgi(prov)
    esito = asyncio.run(engine.genera("gm.limatura", "p"))
    assert esito is not None and esito.testo == _SPORCO
    assert engine.tally["gm.limatura"].slop > 0


def test_engine_gate_passivo_con_retry_zero(mondo_isolato, monkeypatch) -> None:
    """`BONIFICA.retry = 0` (§11): zero chiamate extra — il gate osserva e
    conta soltanto (la leva di costo è calibrazione, non codice)."""
    from motore import calibrazione

    _arma()
    monkeypatch.setitem(calibrazione._OVERRIDE, "BONIFICA.retry", 0)
    prov = FakeProvider([dict(testo=_SPORCO)])
    engine = MasterEngine.avvolgi(prov)
    esito = asyncio.run(engine.genera("gm.limatura", "p"))
    assert esito is not None and esito.testo == _SPORCO
    assert len(prov.chiamate) == 1
    assert engine.tally["gm.limatura"].slop > 0


def test_rotta_senza_bonifica_non_paga_giri(mondo_isolato) -> None:
    """Le rotte strutturali (qui la distillazione-memoria) restano fuori dal
    gate: nessuna chiamata extra anche su testo sporco."""
    _arma()
    prov = FakeProvider([dict(testo=_SPORCO)])
    engine = MasterEngine.avvolgi(prov)
    esito = asyncio.run(engine.genera("gm.distilla", "p"))
    assert esito is not None and len(prov.chiamate) == 1
    assert engine.tally["gm.distilla"].regie == 0


def test_procura_turno_regia_sul_turno_gating(mondo_isolato) -> None:
    """Il turno GM (via `procura_turno`, fuori dall'engine): stesso gate,
    stessa regia — e l'incipit-fotocopia si accende col contesto del reveal."""
    from motore import procura_turno
    from motore.catalogo import prepara_contesto
    from motore.master.engine import ConsumoRotta
    from motore.narrazione import proietta_scheda
    from motore.scheda import protagonista
    import random

    from motore import crea_protagonista

    _arma()
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    budget = prepara_contesto(1, random.Random(3))
    entita = dict(archetipo="slime", grado="bronzo", blocchi=[],
                  nome="Sagoma", descrizione="d")
    apertura_vecchia = "La porta si chiude alle tue spalle con uno schiocco."
    prov = FakeProvider([
        dict(prosa="La porta si chiude alle tue spalle di nuovo, identica.",
             entita=entita, durata="turno"),
        dict(prosa="Un odore di cuoio arriva prima della luce.",
             entita=entita, durata="turno"),
    ])
    conto = ConsumoRotta()
    risultato = asyncio.run(procura_turno(
        prov, budget, proietta_scheda(protagonista()[0]),
        incipit_precedente=apertura_vecchia, conto=conto,
    ))
    assert risultato.fallback is False
    assert risultato.turno.prosa.startswith("Un odore di cuoio")
    assert conto.regie == 1 and conto.slop == 0
    assert "[regia]" in prov.chiamate[1][0]
