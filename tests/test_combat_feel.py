"""Il feel del combattimento: eventi di colpo, round in un click, status attivi,
trasmissione on-hit, fuga, crollo registrato. Tutto via porte, offline, seeded."""

from __future__ import annotations

import asyncio

import esper

from contracts import (
    Blocco,
    BudgetDesign,
    ColpoInferto,
    CombatResolved,
    EffettoStatus,
    Grado,
    MobAsset,
    PianoRisolto,
    PlayerChoseOption,
    StagioneRisolta,
    StatusApplicato,
)
from guscio import Guscio
from main import CronacaBus, costruisci_sessione
from motore import (
    ActionPoint,
    Combattente,
    Nemico,
    PuntiVita,
    SistemaCrollo,
    Veleno,
    componi_opzioni_scena,
    mob_corrente,
    nome_mob_corrente,
    protagonista,
)


def _stagione(mob: MobAsset) -> StagioneRisolta:
    piano = PianoRisolto(
        slug="p", versione=1, titolo="Feel", tema="prova",
        budget=BudgetDesign(
            gradi=[mob.grado], blocchi=list(mob.blocchi), archetipi=[mob.archetipo]
        ),
        cast=[mob],
    )
    return StagioneRisolta(
        slug="s-feel", versione=1, numero=1, titolo="Feel", mondo="X", piani=[piano]
    )


def _mob_argento(blocchi: list[Blocco]) -> MobAsset:
    # ARGENTO: sopravvive al primo colpo → il nemico RISPONDE nello stesso click.
    return MobAsset(
        slug="spugna", nome="Spugna Argentata", archetipo="slime",
        grado=Grado.ARGENTO, blocchi=blocchi, prosa_stanza="La spugna ribolle.",
    )


def _apri_scontro(sessione):
    snap = asyncio.run(sessione.prossima_narrazione())
    indice = next(o.indice for o in snap.opzioni if o.etichetta == "Combatti")
    sessione.coda.accoda(PlayerChoseOption(indice))
    return sessione.avanza()


def test_un_click_e_un_round_intero(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(
        nome="Round", seed=1, directory=tmp_path, stagione=_stagione(_mob_argento([]))
    )
    cronaca = CronacaBus(sessione.bus)
    try:
        snap = _apri_scontro(sessione)
        assert snap.fase == "combattimento"
        righe_apertura = cronaca.preleva()
        assert any("scontro ha inizio" in r for r in righe_apertura)
        # Il PRIMO click: il mio colpo E la risposta del nemico, nella stessa cronaca.
        sessione.coda.accoda(PlayerChoseOption(0))
        snap = sessione.avanza()
        righe = cronaca.preleva()
        assert any(r.startswith("Colpisci ") for r in righe), righe
        assert any("ti colpisce" in r or "stordito" in r for r in righe), righe
        # E lo stato mostra il nemico con i suoi HP.
        assert any("Spugna Argentata" in s and "/" in s for s in snap.stato), snap.stato
    finally:
        cronaca.chiudi()


def test_veleno_trasmesso_dal_colpo_e_ticka(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(
        nome="Tossico", seed=1, directory=tmp_path,
        stagione=_stagione(_mob_argento([Blocco.VELENO])),
    )
    applicati: list[StatusApplicato] = []
    effetti: list[EffettoStatus] = []
    sessione.bus.registra(StatusApplicato, applicati.append)
    sessione.bus.registra(EffettoStatus, effetti.append)
    try:
        snap = _apri_scontro(sessione)
        guardia = 0
        while snap.fase == "combattimento" and guardia < 20:
            sessione.coda.accoda(PlayerChoseOption(0))
            snap = sessione.avanza()
            guardia += 1
        # Il mob velenoso ha colpito almeno una volta → il colpo AVVELENA il
        # protagonista (afflizione, non capacità)…
        assert any(a.bersaglio == "" and a.status == "veleno" for a in applicati), applicati
        pent, _m, _s = protagonista()
        import esper

        veleno = esper.try_component(pent, Veleno)
        # …e l'afflizione TICKA sui turni del protagonista (HP mossi dal veleno).
        assert any(e.bersaglio == "" and e.delta_hp < 0 for e in effetti), effetti
        if veleno is not None:  # può essere già scaduto: l'evento sopra basta
            assert veleno.innato is False
    finally:
        sessione.bus.deregistra(StatusApplicato, applicati.append)
        sessione.bus.deregistra(EffettoStatus, effetti.append)


def test_rigenerazione_innata_cura_il_mob(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(
        nome="Rigenerante", seed=1, directory=tmp_path,
        stagione=_stagione(_mob_argento([Blocco.RIGENERAZIONE])),
    )
    effetti: list[EffettoStatus] = []
    sessione.bus.registra(EffettoStatus, effetti.append)
    try:
        snap = _apri_scontro(sessione)
        guardia = 0
        while snap.fase == "combattimento" and guardia < 20:
            sessione.coda.accoda(PlayerChoseOption(0))
            snap = sessione.avanza()
            guardia += 1
        # La capacità PASSIVA cura il portatore nel suo turno (delta positivo).
        assert any(e.bersaglio == "Spugna Argentata" and e.delta_hp > 0 for e in effetti), effetti
        assert snap.fase == "narrazione"  # e lo scontro termina comunque (TTK/crollo)
    finally:
        sessione.bus.deregistra(EffettoStatus, effetti.append)


def test_fuga_dal_combattimento(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(
        nome="Fuggiasco", seed=1, directory=tmp_path,
        stagione=_stagione(_mob_argento([])),
    )
    risolti: list[CombatResolved] = []
    sessione.bus.registra(CombatResolved, risolti.append)
    try:
        snap = _apri_scontro(sessione)
        assert [o.etichetta for o in snap.opzioni] == ["Attacca", "Fuggi"]
        guardia = 0
        while snap.fase == "combattimento" and guardia < 10:
            sessione.coda.accoda(PlayerChoseOption(1))  # Fuggi (riprova finché riesce)
            snap = sessione.avanza()
            guardia += 1
        assert snap.fase == "narrazione"
        assert risolti and risolti[-1].fuga is True and risolti[-1].vittoria is False
        # Il prossimo turno GM riceve i FATTI della fuga (risolvi prima, narra dopo).
        assert sessione._fatti_scontro is not None and sessione._fatti_scontro.fuga
    finally:
        sessione.bus.deregistra(CombatResolved, risolti.append)


def _fuggi_finche_riesce(sessione, snap, guardia_max: int = 10):
    """Ripete "Fuggi" finché la prova riesce (il motore tira, FNC §4)."""
    guardia = 0
    while snap.fase == "combattimento" and guardia < guardia_max:
        sessione.coda.accoda(PlayerChoseOption(1))
        snap = sessione.avanza()
        guardia += 1
    assert snap.fase == "narrazione", "la fuga non è mai riuscita in 10 tentativi"
    return snap


def test_la_fuga_non_distrugge_il_mob_della_stanza(run_pulita, tmp_path) -> None:
    """FNC §4: la fuga INTERROMPE lo scontro, non cancella il nemico dalla stanza.

    Il bug: `_smonta` eliminava ogni entità con `Nemico`, arruolati compresi — quindi
    fuggire svuotava la stanza a costo zero (meglio che vincere) e consumava il cast
    del piano. Il mob arruolato è un'entità di scena, non un'effimera di scontro."""
    sessione = costruisci_sessione(
        nome="Fuggiasco", seed=1, directory=tmp_path, stagione=_stagione(_mob_argento([]))
    )
    snap = _apri_scontro(sessione)
    ent = mob_corrente()
    assert ent is not None, "il mob della stanza dev'essere arruolato nello scontro"

    snap = _fuggi_finche_riesce(sessione, snap)

    assert esper.entity_exists(ent), "la fuga ha DISTRUTTO il mob della stanza"
    assert mob_corrente() == ent, "il mob ha perso il legame con la sua stanza"
    assert nome_mob_corrente() == "Spugna Argentata"
    # Il nemico è ancora lì: la stanza resta bloccata, non liberata.
    assert [o.etichetta for o in componi_opzioni_scena()] == ["Combatti", "Scappi"]
    # Congedato però non è più un combattente ingaggiato (nessuna effimera residua).
    assert not esper.has_component(ent, Nemico)
    assert not esper.has_component(ent, Combattente)
    assert not esper.has_component(ent, ActionPoint)


def test_le_ferite_del_mob_sopravvivono_alla_fuga(run_pulita, tmp_path) -> None:
    """Fuggire non è una cura: il mob ferito resta ferito fino al prossimo ingaggio."""
    sessione = costruisci_sessione(
        nome="Ferite", seed=1, directory=tmp_path, stagione=_stagione(_mob_argento([]))
    )
    snap = _apri_scontro(sessione)
    ent = mob_corrente()
    sessione.coda.accoda(PlayerChoseOption(0))  # un round di botte
    snap = sessione.avanza()
    feriti = esper.component_for_entity(ent, PuntiVita)
    assert feriti.attuali < feriti.massimi, "il round non ha ferito il mob"
    ferita = feriti.attuali

    snap = _fuggi_finche_riesce(sessione, snap)

    assert esper.component_for_entity(ent, PuntiVita).attuali == ferita
    # E al RI-ingaggio il pool non torna pieno.
    indice = next(o.indice for o in snap.opzioni if o.etichetta == "Combatti")
    sessione.coda.accoda(PlayerChoseOption(indice))
    sessione.avanza()
    assert esper.component_for_entity(ent, PuntiVita).attuali == ferita


def test_la_vittoria_toglie_comunque_il_mob_dalla_stanza(run_pulita, tmp_path) -> None:
    """Il complemento del fix: preservare l'arruolato VIVO non deve far sopravvivere
    l'arruolato MORTO — vincere libera la stanza, come prima."""
    sessione = costruisci_sessione(
        nome="Vincitore", seed=1, directory=tmp_path,
        stagione=_stagione(
            MobAsset(
                slug="fragile", nome="Bolla", archetipo="slime",
                grado=Grado.BRONZO, blocchi=[], prosa_stanza="Una bolla trema.",
            )
        ),
    )
    snap = _apri_scontro(sessione)
    ent = mob_corrente()
    guardia = 0
    while snap.fase == "combattimento" and guardia < 20:
        sessione.coda.accoda(PlayerChoseOption(0))  # Attacca
        snap = sessione.avanza()
        guardia += 1
    assert snap.fase == "narrazione"
    assert not esper.entity_exists(ent), "il mob sconfitto deve sparire dalla scena"
    assert mob_corrente() is None
    assert "Combatti" not in [o.etichetta for o in componi_opzioni_scena()]


def test_crollo_registrato_in_produzione(run_pulita, tmp_path) -> None:
    # G-L1: la rete di terminazione è ATTIVA nella run vera, non solo nei test.
    guscio = Guscio(tmp_path)
    sistemi = guscio._sistemi_run()
    assert any(isinstance(s, SistemaCrollo) for s in sistemi["solo_combattimento"])


def test_colpo_del_protagonista_non_oneshotta_bronzo(run_pulita, tmp_path) -> None:
    # La regressione madre: il bronzo NON muore al primo colpo (pv_base tarati).
    sessione = costruisci_sessione(nome="NoOneShot", seed=1, directory=tmp_path)
    colpi: list[ColpoInferto] = []
    sessione.bus.registra(ColpoInferto, colpi.append)
    try:
        snap = _apri_scontro(sessione)  # Slime Mangiascarti (bronzo)
        sessione.coda.accoda(PlayerChoseOption(0))
        snap = sessione.avanza()
        primo = next(c for c in colpi if c.attaccante == "")
        assert primo.hp_rimasti > 0, "one-shot: il mob bronzo è morto al primo colpo"
        assert snap.fase == "combattimento"
    finally:
        sessione.bus.deregistra(ColpoInferto, colpi.append)
