"""Wiki del Master — W1 (docs/future/wiki-master.md rev. 3).

Le regole bloccate qui:
- `admin` non esce MAI dal master: né slice, né prompt (property-test, §5);
  le proposte non approvate sono fisicamente invisibili (gate strutturale).
- La slice è il MONDO della run: congelata al freeze, immutabile — mutare
  il master a run aperta non cambia nulla, la ripresa da save vede lo
  stesso mondo di ieri (rev. 3 §4).
- Il terzo artefatto è VITALE: corrotto/assente col marcatore nel save =
  rifiuto dichiarato, mai sostituzione silenziosa (§3.1); senza marcatore
  (legacy, master vuoto) tutto come prima.
- L'outbox è FUORI dalla coppia save: sopravvive a `invalida` (permadeath),
  deduplica per id deterministico, eredita il taint di regia (§4-bis).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from contracts import (
    ApprovazioneVoce,
    LinkVoce,
    RegiaVoce,
    RevisioneVoce,
    ScopeVoce,
    SegretezzaVoce,
    TipoVoce,
    VoceWiki,
)
from main import carica_sessione, costruisci_sessione
import wiki_master


def _voce(slug, testo, *, segretezza=SegretezzaVoce.IN_SLICE,
          regia=RegiaVoce.CITABILE, costante=False, inneschi=(),
          approvata=True, stagione=1, link=()):
    return VoceWiki(
        slug=slug, tipo=TipoVoce.AMBIENTAZIONE,
        scope=ScopeVoce(stagione=stagione),
        segretezza=segretezza, regia=regia, costante=costante,
        inneschi=tuple(inneschi),
        revisioni=(RevisioneVoce(n=1, testo=testo),),
        approvazioni=(ApprovazioneVoce(revisione_n=1),) if approvata else (),
        link=tuple(link),
    )


def _master(tmp_path: Path, *voci) -> Path:
    base = tmp_path / "wiki-master"
    for voce in voci:
        wiki_master.salva_voce(voce, directory=base)
    return base


# --- L'estrazione: il choke-point (admin mai fuori, proposte invisibili) --------

def test_l_estrazione_esclude_admin_e_le_proposte(tmp_path) -> None:
    base = _master(
        tmp_path,
        _voce("canone", "Il canone visibile."),
        _voce("segreto-produzione", "MAI in un prompt.",
              segretezza=SegretezzaVoce.ADMIN),
        _voce("bozza", "Proposta non approvata.", approvata=False),
    )
    fetta = wiki_master.estrai_slice(1, directory=base)
    slugs = {v.slug for v in fetta.voci}
    assert slugs == {"canone"}, (
        "admin non esce MAI dal master; la proposta è invisibile fino al gate"
    )


def test_la_supersessione_esclude_la_voce_sostituita(tmp_path) -> None:
    """«Lo scope racconta» (rev. 3 §3): il link `sostituisce` di una voce
    approvata toglie la bersaglio dalle slice FUTURE."""
    base = _master(
        tmp_path,
        _voce("fabbro-vivo", "Il fabbro batte il ferro."),
        _voce("fabbro-morto", "Il fabbro non c'è più.",
              link=(LinkVoce(verso="fabbro-vivo", tipo="sostituisce"),)),
    )
    fetta = wiki_master.estrai_slice(1, directory=base)
    slugs = {v.slug for v in fetta.voci}
    assert "fabbro-vivo" not in slugs and "fabbro-morto" in slugs


def test_lo_scope_di_stagione_filtra(tmp_path) -> None:
    base = _master(
        tmp_path,
        _voce("di-questa-stagione", "Vale ora.", stagione=1),
        _voce("di-un-altra", "Vale altrove.", stagione=2),
        _voce("di-sempre", "Vale sempre.", stagione=None),
    )
    fetta = wiki_master.estrai_slice(1, directory=base)
    assert {v.slug for v in fetta.voci} == {"di-questa-stagione", "di-sempre"}


# --- La slice nella run: freeze, immutabilità, contratto vitale -----------------

def _sessione_con_master(tmp_path, monkeypatch, *voci, seed=1):
    base = _master(tmp_path, *voci)
    monkeypatch.setattr(wiki_master, "DIRECTORY_WIKI", base)
    sessione = costruisci_sessione(seed=seed, directory=tmp_path / "salvataggi")
    asyncio.run(sessione.prossima_narrazione())
    return sessione


def test_la_slice_e_il_mondo_della_run_e_il_master_mutato_non_la_tocca(
    run_pulita, tmp_path, monkeypatch,
) -> None:
    from motore.wiki import recupera_wiki, slice_corrente

    sessione = _sessione_con_master(
        tmp_path, monkeypatch,
        _voce("legge-del-piano", "Il VECCHIO canone.", inneschi=["canone"]),
    )
    assert slice_corrente() is not None
    prima = recupera_wiki("consulto il canone", limite=2)
    assert prima and "VECCHIO" in prima[0].testo
    # Il master muta DOPO il freeze: nuova revisione approvata.
    wiki_master.aggiungi_revisione("legge-del-piano", "Il NUOVO canone.")
    wiki_master.approva("legge-del-piano", 2)
    dopo = recupera_wiki("consulto il canone", limite=2)
    assert "VECCHIO" in dopo[0].testo, (
        "F-6: una modifica del master non raggiunge la run in corso"
    )
    # E la RIPRESA da save vede lo stesso mondo di ieri.
    sessione.salva()
    uuid = sessione.uuid
    sessione.esci()
    ripresa = carica_sessione(uuid=uuid, directory=tmp_path / "salvataggi")
    assert ripresa is not None
    riprese = recupera_wiki("consulto il canone", limite=2)
    assert riprese and "VECCHIO" in riprese[0].testo


def test_la_slice_corrotta_rifiuta_il_load(run_pulita, tmp_path, monkeypatch) -> None:
    from motore.persistenza.salvataggio import SliceWikiIlleggibile

    sessione = _sessione_con_master(
        tmp_path, monkeypatch, _voce("canone", "Testo."),
    )
    sessione.salva()
    uuid = sessione.uuid
    sessione.esci()
    (tmp_path / "salvataggi" / f"{uuid}.wiki.gz").unlink()
    with pytest.raises(SliceWikiIlleggibile):
        carica_sessione(uuid=uuid, directory=tmp_path / "salvataggi")


def test_senza_wiki_tutto_come_prima(run_pulita, tmp_path, monkeypatch) -> None:
    """Master vuoto = zero footprint: nessun marcatore, nessun artefatto, il
    load è quello storico (i save legacy sono questo caso)."""
    from motore.wiki import slice_corrente

    monkeypatch.setattr(wiki_master, "DIRECTORY_WIKI", tmp_path / "vuota")
    sessione = costruisci_sessione(seed=1, directory=tmp_path / "salvataggi")
    asyncio.run(sessione.prossima_narrazione())
    assert slice_corrente() is None
    sessione.salva()
    uuid = sessione.uuid
    assert not (tmp_path / "salvataggi" / f"{uuid}.wiki.gz").exists()
    sessione.esci()
    assert carica_sessione(uuid=uuid, directory=tmp_path / "salvataggi") is not None


def test_la_coppia_di_backup_e_una_terna(run_pulita, tmp_path, monkeypatch) -> None:
    """Stress-test 2026-08-18: la slice ha il suo backup di recovery INSIEME
    a stato e sidecar (backup coerente = stesso istante). Mai auto-ripristino:
    il contratto vitale resta un rifiuto dichiarato."""
    sessione = _sessione_con_master(tmp_path, monkeypatch, _voce("canone", "Testo."))
    sessione.salva()
    sessione.salva()  # la seconda scrittura ruota la coppia buona precedente
    uuid = sessione.uuid
    salvataggi = tmp_path / "salvataggi"
    assert (salvataggi / f"{uuid}.bak.stato.json").exists()
    assert (salvataggi / f"{uuid}.bak.wiki.gz").exists(), (
        "la coppia deve diventare TERNA quando la run ha una slice"
    )


# --- Le corsie nel turno GM -----------------------------------------------------

def test_le_voci_dinamiche_entrano_nel_fascicolo_con_la_regia(
    run_pulita, tmp_path, monkeypatch,
) -> None:
    from motore.wiki import righe_wiki

    _sessione_con_master(
        tmp_path, monkeypatch,
        _voce("canone-citabile", "Fatto citabile.", inneschi=["schedari"]),
        _voce("segreto-velato", "Fatto da velare.", regia=RegiaVoce.VELATO,
              inneschi=["patto"]),
    )
    righe = righe_wiki("consulto gli schedari", limite=2)
    assert any("canone-citabile" in r for r in righe)
    velate = righe_wiki("chiedo del patto", limite=2)
    assert velate and "VELATO" in velate[0], "la regia viaggia con la voce"


def test_la_costante_sta_nel_prefisso_e_non_nel_fascicolo(
    run_pulita, tmp_path, monkeypatch,
) -> None:
    from motore.wiki import costanti_prefisso, righe_wiki

    _sessione_con_master(
        tmp_path, monkeypatch,
        _voce("tono-dello-show", "Il dungeon è AZIENDALE.", costante=True,
              inneschi=["aziendale"]),
    )
    prefisso = costanti_prefisso()
    assert "AZIENDALE" in prefisso, "la costante vive nel prefisso (cache)"
    assert righe_wiki("un gesto aziendale", limite=2) == [], (
        "la costante non passa MAI dalla corsia dinamica (doppio conto)"
    )


def test_il_prompt_del_turno_porta_la_riga_wiki(run_pulita, tmp_path, monkeypatch) -> None:
    from contracts import TurnoNarrazione
    from provider import FakeProvider

    sessione = _sessione_con_master(
        tmp_path, monkeypatch,
        _voce("canone-degli-schedari", "Gli schedari del piano mentono.",
              inneschi=["schedari"]),
    )
    fake = FakeProvider([])
    sessione.provider = fake
    riepilogo = sessione.riepiloga_azione("frugo tra gli schedari")
    asyncio.run(sessione.esegui_azione(riepilogo))
    prompt = next((p for p, s in fake.chiamate if s is TurnoNarrazione), None)
    assert prompt is not None and "[fascicolo/wiki] canone-degli-schedari" in prompt


# --- L'outbox: fuori dalla coppia save, dedup, taint ----------------------------

def test_l_outbox_sopravvive_all_invalidazione_e_deduplica(
    run_pulita, tmp_path, monkeypatch,
) -> None:
    from motore.persistenza.outbox import leggi_proposte
    from motore.persistenza.salvataggio import invalida
    from motore.wiki import accoda_proposta

    sessione = _sessione_con_master(tmp_path, monkeypatch, _voce("canone", "Testo."))
    accoda_proposta(tipo="personaggio", titolo="Il Fante", testo="bronzo", fatto="mob:fante")
    accoda_proposta(tipo="personaggio", titolo="Il Fante", testo="bronzo", fatto="mob:fante")
    sessione.salva()  # il primo drenaggio
    accoda_proposta(tipo="personaggio", titolo="Il Fante", testo="bronzo", fatto="mob:fante")
    sessione.salva()  # ri-drenaggio dello STESSO fatto: dedup su file
    salvataggi = tmp_path / "salvataggi"
    uuid = sessione.uuid
    proposte = leggi_proposte(salvataggi, uuid)
    # Il produttore VERO (mob memorabile al reveal) ha già accodato la sua:
    # è il canale che funziona da solo — qui si contano solo le nostre.
    nostre = [p for p in proposte if p["id"].endswith(":mob:fante")]
    assert len(nostre) == 1, "id deterministico: mai duplicati (save-scumming incluso)"
    invalida(salvataggi, uuid)  # il permadeath
    assert not (salvataggi / f"{uuid}.stato.json").exists()
    assert leggi_proposte(salvataggi, uuid), (
        "l'outbox sopravvive al permadeath: è il suo scopo (rev. 3 §4-bis)"
    )


def test_il_taint_di_regia_si_eredita(run_pulita, tmp_path, monkeypatch) -> None:
    """Una proposta nata dopo una voce `velato` non nasce mai citabile: la
    promozione può solo declassare con atto esplicito (§4-bis)."""
    from motore.wiki import accoda_proposta, drena_proposte, righe_wiki

    _sessione_con_master(
        tmp_path, monkeypatch,
        _voce("segreto", "Fatto velato.", regia=RegiaVoce.VELATO, inneschi=["patto"]),
    )
    righe_wiki("chiedo del patto", limite=2)  # la voce velata è stata SERVITA
    accoda_proposta(tipo="evento", titolo="Sintesi", testo="derivata", fatto="ev:1")
    proposte = drena_proposte()
    sintesi = next(p for p in proposte if p["id"].endswith(":ev:1"))
    assert sintesi["taint"] == "velato"


# --- Le falle del playtest approfondito (2026-08-18) ----------------------------

def test_le_stopword_non_innescano(run_pulita) -> None:
    """F-W2: «L'Archivista DEL Sesto» matchava «Fante DEL Fronte Fermo»
    sull'articolo — il canone scattava su ogni azione in qualunque stanza con
    un nome composto. Le stopword escono dalla tokenizzazione, i contenuti no."""
    from motore.wiki import _normalizza

    chiavi = _normalizza("L'Archivista del Sesto")
    assert "del" not in chiavi and "archivista" in chiavi and "sesto" in chiavi
    assert _normalizza("Fante del Fronte Fermo") & chiavi == frozenset(), (
        "due nomi composti senza contenuto comune non devono sovrapporsi"
    )


def test_la_cache_dello_scan_si_invalida_alla_scrittura(tmp_path) -> None:
    """F-W3: lo scan freddo costa (Pydantic+I/O) e va in cache per firma —
    ma una scrittura via API DEVE invalidarla (mtime cambia): mai servire
    un master stantio."""
    base = _master(tmp_path, _voce("prima", "Testo uno."))
    assert [v.slug for v in wiki_master.elenca_voci(directory=base)] == ["prima"]
    wiki_master.salva_voce(_voce("seconda", "Testo due."), directory=base)
    assert [v.slug for v in wiki_master.elenca_voci(directory=base)] == [
        "prima", "seconda",
    ], "la cache non si è invalidata alla scrittura"


# --- L'avversariale di scrittura esterna (2026-08-18) ---------------------------

def test_l_outbox_sabotata_non_rompe_il_salvataggio(
    run_pulita, tmp_path, monkeypatch,
) -> None:
    """F-W4: un outbox inscrivibile (lock/antivirus/sabotaggio: qui una
    directory col nome del file) faceva esplodere `salva()` DOPO la scrittura
    del save. Il drenaggio è best-effort: le proposte tornano in coda e si
    consegnano quando il canale torna."""
    from motore.persistenza.outbox import leggi_proposte, path_outbox
    from motore.wiki import accoda_proposta

    sessione = _sessione_con_master(tmp_path, monkeypatch, _voce("canone", "Testo."))
    salvataggi = tmp_path / "salvataggi"
    sabotaggio = path_outbox(salvataggi, sessione.uuid)
    if sabotaggio.exists():
        sabotaggio.unlink()
    sabotaggio.mkdir()
    accoda_proposta(tipo="evento", titolo="Trattenuta", testo="t", fatto="ev:lock")
    sessione.salva()  # non deve sollevare
    sabotaggio.rmdir()
    sessione.salva()  # il canale torna: la proposta si consegna ORA
    assert any(p["id"].endswith(":ev:lock")
               for p in leggi_proposte(salvataggi, sessione.uuid)), (
        "la proposta trattenuta doveva riconsegnarsi al confine successivo"
    )


def test_il_mismatch_slug_file_si_scarta(tmp_path) -> None:
    """F-W5: un file copiato sotto un altro nome dichiarava lo slug
    dell'originale — doppioni di slug nella slice. Il nome del file È
    l'identità: mismatch = voce invalida (scarto lasco)."""
    base = _master(tmp_path, _voce("onesta", "Voce onesta."))
    (base / "impostore.json").write_text(
        (base / "onesta.json").read_text(encoding="utf-8"), encoding="utf-8",
    )
    fetta = wiki_master.estrai_slice(1, directory=base)
    assert [v.slug for v in fetta.voci] == ["onesta"], (
        f"doppione di slug nella slice: {[v.slug for v in fetta.voci]}"
    )


# --- La validazione dei vincoli all'authoring -----------------------------------

def test_il_vincolo_con_slug_ignoto_e_un_errore_di_authoring() -> None:
    errori = wiki_master.lint_vincolo(
        {"archetipi": ["zombie", "archetipo-inventato"]},
        archetipi_noti={"zombie", "scheletro"},
    )
    assert errori and "archetipo-inventato" in errori[0]
