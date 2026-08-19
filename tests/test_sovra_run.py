"""Lo strato sovra-run, fasi B/C/D lato motore: bacheca, daily, fantasmi.

B — il necrologio è una PROIEZIONE del ledger: composizione deterministica dai
fatti, nessun secondo artefatto, porta `bacheca()` per gli host.
C — la run del giorno: `seed_del_giorno` → `costruisci_sessione(seed=…)` dà lo
stesso dungeon a chiunque, e l'esito porta quel seed (la via di verifica del
futuro server: seed == seed_del_giorno(data) ⇒ è una run del daily).
D — i fantasmi: input ESPLICITO dell'host, congelati nel World come la
stagione, persistenti col save; assegnazione alla stanza DERIVATA (mai un
secondo stato); una traccia si narra UNA volta (consumo a turno scritto);
lore soltanto — l'unica uscita è una riga di fascicolo.
"""

from __future__ import annotations

import asyncio

from contracts import FantasmaRun, PlayerChoseOption, Terminale, seed_del_giorno
from main import bacheca, carica_sessione, costruisci_sessione, fantasmi_locali
from motore.fantasmi import (
    FantasmiAttivi,
    _stanza_assegnata,
    consuma_fantasma_corrente,
    fantasmi_correnti,
    traccia_fantasma_corrente,
)
from motore.mappa import mappa_corrente
from motore.persistenza.esiti import path_esiti, scrivi_esito


async def _gioca_fino_alla_morte(sessione, max_turni: int = 200):
    """La morte certa (gemello di test_permadeath_slot): 1 HP, politica suicida."""
    from motore import protagonista

    _ent, _marker, scheda = protagonista()
    scheda.punti_vita = 1
    turni = 0
    while turni < max_turni:
        snap = sessione.avanza()
        if snap.run_conclusa:
            return snap.terminale
        turni += 1
        if not snap.opzioni:
            await sessione.prossima_narrazione()
            continue
        etichette = [o.etichetta for o in snap.opzioni]
        indice = next(
            (i for i, e in enumerate(etichette) if e.startswith(("Combatti", "Attacca"))),
            None,
        )
        if indice is None:
            indice = next(
                (i for i, e in enumerate(etichette) if e.startswith("Vai")), 0
            )
        sessione.coda.accoda(PlayerChoseOption(indice))
    return None


# --- B. Il necrologio e la bacheca ---------------------------------------------

def test_il_necrologio_compone_dai_fatti() -> None:
    from contracts import EsitoRun
    from motore.necrologio import componi_necrologio

    esito = EsitoRun(
        uuid_run="abc12345", nome="Donut", seed=3,
        terminale=Terminale.SCONFITTA, profondita=1, tick=42,
        causa="Scheletro del Saloon",
        momenti=("primo sangue: lo Scheletro colpisce Donut",),
    )
    post = componi_necrologio(esito)
    assert post.titolo == "† Donut — piano 1"
    assert "Scheletro del Saloon" in post.corpo
    assert "42 tick" in post.corpo
    assert "primo sangue" in post.corpo
    assert "seed 3" in post.corpo
    assert componi_necrologio(esito) == post, "proiezione: stesso esito, stesso post"

    vittoria = EsitoRun(
        uuid_run="abc12345", nome="Donut", seed=3,
        terminale=Terminale.PIANO_COMPLETATO, profondita=1,
    )
    assert componi_necrologio(vittoria).titolo.startswith("⚑")


def test_la_bacheca_proietta_il_ledger(run_pulita, tmp_path) -> None:
    """Integrazione: muori → il tuo necrologio è in bacheca. E la spazzatura
    nel ledger resta muta (composizione lasca)."""
    sessione = costruisci_sessione(seed=3, directory=tmp_path, nome="Donut")
    asyncio.run(sessione.prossima_narrazione())
    sessione.salva()
    assert asyncio.run(_gioca_fino_alla_morte(sessione)) is Terminale.SCONFITTA

    with path_esiti(tmp_path).open("a", encoding="utf-8") as f:
        f.write('{"id": "spazzatura", "nome": 42}\n')  # riga che non valida
    post = bacheca(tmp_path)
    assert len(post) == 1
    assert post[0].nome == "Donut"
    assert post[0].titolo.startswith("†")


# --- C. La run del giorno -------------------------------------------------------

def test_il_daily_da_lo_stesso_dungeon_a_chiunque(run_pulita, tmp_path) -> None:
    """Due «giocatori» (due run, stessa data): topologia identica. E l'esito
    porta il seed del giorno — la verifica del server è `seed ==
    seed_del_giorno(data)`, nessun campo in più."""
    daily = seed_del_giorno("2026-08-19", 1)

    prima = costruisci_sessione(seed=daily, directory=tmp_path / "a", nome="Donut")
    topo_prima = dict(mappa_corrente()[1].piano.adiacenze)
    prima.esci()

    seconda = costruisci_sessione(seed=daily, directory=tmp_path / "b", nome="Katia")
    topo_seconda = dict(mappa_corrente()[1].piano.adiacenze)
    assert topo_prima == topo_seconda, "stesso seed = stesso dungeon"

    asyncio.run(seconda.prossima_narrazione())
    seconda.salva()
    assert asyncio.run(_gioca_fino_alla_morte(seconda)) is Terminale.SCONFITTA
    from motore.persistenza.esiti import leggi_esiti

    esiti = leggi_esiti(tmp_path / "b")
    assert len(esiti) == 1
    assert esiti[0]["seed"] == daily, "l'esito è verificabile come run del daily"


# --- D. I fantasmi --------------------------------------------------------------

def _fantasma(nome: str = "Katia") -> FantasmaRun:
    return FantasmaRun(
        nome=nome, causa="La Regina Scaduta", profondita=1, stagione=1, seed=7
    )


def test_il_fantasma_appare_nella_sua_stanza_e_una_volta_sola(run_pulita, tmp_path) -> None:
    """L'assegnazione è derivata (fantasma+master seed → stanza) e il consumo
    è uno: narrata la traccia, non torna — nemmeno ripassando di lì."""
    from motore.seme import master_seed

    sessione = costruisci_sessione(
        seed=3, directory=tmp_path, nome="Donut", fantasmi=(_fantasma(),)
    )
    componente = fantasmi_correnti()
    assert componente is not None and len(componente.lista) == 1

    mappa = mappa_corrente()[1]
    n_stanze = len(mappa.piano.adiacenze)
    stanza = _stanza_assegnata(componente.lista[0], n_stanze, master_seed())
    assert stanza == _stanza_assegnata(
        componente.lista[0], n_stanze, master_seed()
    ), "derivazione stabile"

    mappa.stanza_corrente = stanza  # l'harness si porta sulla stanza della traccia
    riga = traccia_fantasma_corrente()
    assert "Katia" in riga and "La Regina Scaduta" in riga
    consuma_fantasma_corrente()
    assert traccia_fantasma_corrente() == "", "narrata una volta: non torna"
    assert componente.lista[0].consumato is True
    sessione.esci()


def test_il_fantasma_entra_nel_fascicolo_come_lore(run_pulita, tmp_path) -> None:
    """L'UNICA uscita del fantasma è la riga [fascicolo/fantasma]: niente
    entità, niente menu, niente numeri — la mappa e le opzioni di scena non
    cambiano di un bit rispetto alla run gemella senza fantasmi."""
    from motore.gm import MemoriaTurni, componi_fascicolo, sezione_fascicolo
    from motore.seme import master_seed

    sessione = costruisci_sessione(
        seed=3, directory=tmp_path, nome="Donut", fantasmi=(_fantasma(),)
    )
    componente = fantasmi_correnti()
    mappa = mappa_corrente()[1]
    stanza = _stanza_assegnata(
        componente.lista[0], len(mappa.piano.adiacenze), master_seed()
    )
    mappa.stanza_corrente = stanza
    fascicolo = componi_fascicolo(MemoriaTurni())
    assert "Katia" in fascicolo.fantasma_riga
    testo = sezione_fascicolo(fascicolo)
    assert "[fascicolo/fantasma]" in testo
    assert "mai come presenza viva" in testo.lower() or "MAI come presenza viva" in testo
    sessione.esci()


def test_il_fantasma_persiste_col_save(run_pulita, tmp_path) -> None:
    """Il set è congelato nel World e attraversa il save (tag `fantasmi`):
    al reload la traccia consumata resta consumata — il reload non la fa
    tornare (determinismo del racconto)."""
    sessione = costruisci_sessione(
        seed=3, directory=tmp_path, nome="Donut", fantasmi=(_fantasma(),)
    )
    componente = fantasmi_correnti()
    componente.lista[0].consumato = True  # come dopo una narrazione
    asyncio.run(sessione.prossima_narrazione())
    sessione.salva()
    uuid = sessione.uuid
    sessione.esci()

    riaperta = carica_sessione(uuid=uuid, directory=tmp_path)
    assert riaperta is not None
    ricaricato = fantasmi_correnti()
    assert ricaricato is not None and len(ricaricato.lista) == 1
    assert ricaricato.lista[0].nome == "Katia"
    assert ricaricato.lista[0].consumato is True, "il reload non resuscita la traccia"
    riaperta.esci()


def test_il_turno_gm_scritto_consuma_la_traccia(run_pulita, tmp_path) -> None:
    """Il filo di sessione: un turno GM FRESCO nella stanza della traccia la
    consuma (disciplina dei gemelli scontro/scena) — senza che nessuno chiami
    a mano `consuma_fantasma_corrente`."""
    from motore.seme import master_seed

    sessione = costruisci_sessione(
        seed=3, directory=tmp_path, nome="Donut", fantasmi=(_fantasma(),)
    )
    componente = fantasmi_correnti()
    mappa = mappa_corrente()[1]
    stanza = _stanza_assegnata(
        componente.lista[0], len(mappa.piano.adiacenze), master_seed()
    )
    mappa.stanza_corrente = stanza
    assert traccia_fantasma_corrente() != ""
    asyncio.run(sessione.prossima_narrazione())  # turno fresco (copione offline)
    assert componente.lista[0].consumato is True, (
        "il turno scritto consuma la traccia: nessun consumo manuale"
    )
    sessione.esci()


def test_senza_fantasmi_zero_footprint(run_pulita, tmp_path) -> None:
    """Il default resta il comportamento storico: nessun componente nel World,
    nessuna riga nel fascicolo."""
    sessione = costruisci_sessione(seed=3, directory=tmp_path, nome="Donut")
    assert fantasmi_correnti() is None
    assert traccia_fantasma_corrente() == ""
    sessione.esci()


def test_fantasmi_locali_proietta_le_sconfitte(run_pulita, tmp_path) -> None:
    """La sorgente locale del prototipo: le morti nel ledger diventano
    fantasmi per la prossima run — le più recenti prima, cap a `massimo`,
    spazzatura muta."""
    sessione = costruisci_sessione(seed=3, directory=tmp_path, nome="Donut")
    asyncio.run(sessione.prossima_narrazione())
    sessione.salva()
    assert asyncio.run(_gioca_fino_alla_morte(sessione)) is Terminale.SCONFITTA
    scrivi_esito(tmp_path, {"id": "rotto", "nome": 42})  # spazzatura

    fantasmi = fantasmi_locali(tmp_path)
    assert len(fantasmi) == 1
    assert fantasmi[0].nome == "Donut"
    assert fantasmi_locali(tmp_path, massimo=0) == ()
