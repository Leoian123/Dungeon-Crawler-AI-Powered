"""ELITÉ — i contratti (decisione utente 2026-08-11): il PNG che tutti idolatrano.

Identità sopra il comportamento (il ruolo resta PNG): lore piena OBBLIGATORIA,
mai nei posti-boss/spawn/cast (un idolo non custodisce varchi — e mai, per
costruzione, boss di piano), incontrabile solo dal piano minimo §11
(`ELITE.piano_minimo`). La mortalità è dichiaratamente futura.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts import BusEventi, Frequenza, RuoloMob, TierTerritorio
from tests.contenuti_sintetici import (
    mob_sintetico,
    piano_territoriale,
    stagione_sintetica,
)


def _elite(slug: str = "vetusto-re-del-multisala", **extra):
    """Un Elité valido: lore piena, per contratto. Costruito via
    `model_validate` (mai `model_copy`: quello NON riesegue i validator)."""
    from contracts import MobAsset

    base = mob_sintetico(slug, prosa="Il Re del Multisala concede un'udienza.")
    dati = base.model_dump() | dict(
        elite=True,
        descrizione="Il primo crawler a superare dieci piani: nessuno l'ha più visto salire.",
        aspetto="mantello di locandine cucite, corona di biglietti strappati",
        tratto="parla di sé in terza persona, come lo show gli ha insegnato",
        # Obbligo di forma della VOCE (2026-08-16): l'idolo ha una voce per
        # definizione — un Elité senza non può esistere come asset.
        voce="periodi lunghi da cerimonia di premiazione, pause teatrali, "
             "mai una domanda: il Re non chiede, concede",
    ) | extra
    return MobAsset.model_validate(dati)


# --- Contratto: la lore piena è obbligatoria ------------------------------------

def test_elite_esige_lore_piena() -> None:
    with pytest.raises(ValidationError, match="tratto"):
        _elite(tratto="   ")
    with pytest.raises(ValidationError, match="aspetto"):
        _elite(aspetto="")
    with pytest.raises(ValidationError, match="descrizione"):
        _elite(descrizione="")
    assert _elite().elite is True  # con la lore piena l'asset esiste


def test_il_mob_ordinario_resta_com_era() -> None:
    """Retro-compatibilità: default elite=False, lore minima = prosa_stanza
    (già obbligatoria per ogni MobAsset: nessun mob è senza narrazione)."""
    mob = mob_sintetico("comparsa", prosa="Una comparsa qualunque.")
    assert mob.elite is False and mob.aspetto == "" and mob.tratto == ""


# --- Contratto: mai nei posti-boss, mai spawn, mai cast --------------------------

def _territorio_con_boss_elite(tier: TierTerritorio):
    from contracts import TerritorioRisolto

    base = piano_territoriale(1).territorio.model_dump()
    base["boss"][tier] = [_elite(grado=tier.grado).model_dump()]
    return TerritorioRisolto.model_validate(base)


def test_un_elite_non_custodisce_varchi() -> None:
    with pytest.raises(ValidationError, match="non custodisce varchi"):
        _territorio_con_boss_elite(TierTerritorio.CITTA)


def test_un_elite_non_e_boss_di_piano() -> None:
    with pytest.raises(ValidationError, match="non custodisce varchi"):
        _territorio_con_boss_elite(TierTerritorio.PIANO)


def test_un_elite_non_spawna() -> None:
    from contracts import TabellaSpawnRisolta, TerritorioRisolto, VoceSpawnRisolta

    base = piano_territoriale(1).territorio
    guasto = dict(
        conteggi=base.conteggi, boss=base.boss, procedurali=base.procedurali,
        spawn=[TabellaSpawnRisolta(
            tier=TierTerritorio.QUARTIERE,
            voci=[VoceSpawnRisolta(mob=_elite(), frequenza=Frequenza.RARO)],
        )],
        stanze_per_zona=base.stanze_per_zona,
    )
    with pytest.raises(ValidationError, match="si incontra, non spawna"):
        TerritorioRisolto(**guasto)


def test_un_elite_non_sta_nel_cast() -> None:
    from contracts import PianoRisolto

    dati = piano_territoriale(1).model_dump()
    dati["cast"] = [_elite().model_dump()]
    with pytest.raises(ValidationError, match="non è un incontro"):
        PianoRisolto.model_validate(dati)


# --- Gate di profondità: l'idolo non scende sotto il piano minimo ----------------

def _arma_mondo(seed: int = 7) -> BusEventi:
    from main import _stagione_a_attiva
    from motore import (
        avvia_territorio,
        crea_profondita,
        crea_protagonista,
        crea_seme,
        crea_stagione,
        crea_tempo_piano,
    )

    crea_profondita()
    crea_seme(seed)
    crea_tempo_piano()
    crea_stagione(_stagione_a_attiva(
        stagione_sintetica(piani=[piano_territoriale(1)], slug="s-elite")
    ))
    crea_protagonista(destrezza=10, punti_vita=30, id_dominio="carl")
    avvia_territorio(1)
    return BusEventi()


def _attivo_elite():
    from main import _mob_a_attivo

    return _mob_a_attivo(_elite())


def test_gate_di_profondita(mondo_isolato) -> None:
    import esper

    from motore import EntitaMob, materializza_png
    from motore.calibrazione import ELITE_PIANO_MINIMO

    _arma_mondo()
    attivo = _attivo_elite()
    assert attivo.elite is True  # la conversione porta l'identità

    assert materializza_png(attivo, 1, stanza=0) is None  # sotto il minimo: rifiuto
    assert materializza_png(attivo, int(ELITE_PIANO_MINIMO) - 1, stanza=0) is None

    ent = materializza_png(attivo, int(ELITE_PIANO_MINIMO), stanza=0)
    assert ent is not None  # dal piano minimo in su l'idolo si incontra
    em = esper.component_for_entity(ent, EntitaMob)
    assert em.ruolo is RuoloMob.PNG and em.elite is True
    assert em.aspetto and em.tratto  # la lore piena viaggia fino al componente


def test_il_png_ordinario_non_ha_gate(mondo_isolato) -> None:
    import esper

    from motore import EntitaMob, materializza_png

    _arma_mondo()
    from main import _mob_a_attivo

    comune = _mob_a_attivo(mob_sintetico("archivista", prosa="Un archivista."))
    ent = materializza_png(comune, 1, stanza=0)
    assert ent is not None  # nessun gate per il PNG qualunque
    assert esper.component_for_entity(ent, EntitaMob).elite is False


# --- Il dialogo dice al GM chi ha davanti ----------------------------------------

def test_il_dialogo_annuncia_l_idolo(mondo_isolato) -> None:
    import asyncio

    from motore import materializza_png
    from motore.calibrazione import ELITE_PIANO_MINIMO
    from motore.png import dialoga

    _arma_mondo()
    ent = materializza_png(_attivo_elite(), int(ELITE_PIANO_MINIMO), stanza=0)
    assert ent is not None

    prompt_visti: list[str] = []

    class _EngineSpia:
        async def genera(self, rotta, prompt, *, sistema=""):
            prompt_visti.append(prompt)
            return None  # degrado deterministico: la riga muta

    risposta = asyncio.run(dialoga(_EngineSpia(), ent, "Sei davvero tu?"))
    assert risposta  # il degrado non è mai muto
    assert "[png/elite]" in prompt_visti[0]
    assert "idolatrano" in prompt_visti[0]


def test_la_foglia_elite_e_in_console() -> None:
    from motore import calibrazione as cal

    assert "ELITE.piano_minimo" in cal.CATALOGO
    assert int(cal.valore("ELITE.piano_minimo")) >= 1
