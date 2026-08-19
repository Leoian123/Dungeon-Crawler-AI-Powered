"""Il CONTRATTO della scheda: skill, equipaggiamento, progressione.

Questi test guardano la FORMA, non il contenuto. Il contratto deve esistere ed
essere stabile anche dove oggi nessun sistema lo riempie (non ci sono oggetti, non
c'è esperienza): è ciò che rende additivo il lavoro futuro — quando il contenuto
arriverà si popola un campo, non si rinegozia un'interfaccia con ogni host già
scritto.

Il valore di questi lucchetti è precisamente che restano verdi quando il contenuto
arriva: se un giorno `esperienza` diventa > 0, qui non cambia una riga.
"""

from __future__ import annotations

import asyncio

import esper
import pytest
from pydantic import ValidationError

import contracts
from contracts import (
    EquipVista,
    ProgressioneVista,
    SchedaVista,
    SkillVista,
    SLOT_ARMATURA,
    SLOT_IMPUGNATI,
    SlotEquip,
)
from motore import CATALOGO_MOSSE, Mana, Repertorio, cooldown_residuo, protagonista
from motore.scheda import MOSSE_INIZIALI_PROTAGONISTA
from main import costruisci_sessione


# --- La forma esiste, è chiusa, ed è esportata dalla membrana -------------------

def test_i_dto_sono_esportati_dalla_membrana() -> None:
    """Un host parla col motore SOLO via `contracts`: se il DTO non è lì, non esiste."""
    for nome in ("SkillVista", "EquipVista", "SlotEquip", "ProgressioneVista"):
        assert nome in contracts.__all__, f"{nome} non attraversa la membrana"
        assert hasattr(contracts, nome)


def test_i_dto_sono_immutabili_e_chiusi() -> None:
    """`frozen` + `extra=forbid` come ogni DTO di vista: nessun campo di soppiatto,
    nessuna mutazione lato host."""
    for modello in (SkillVista, EquipVista, ProgressioneVista):
        assert modello.model_config.get("frozen") is True, modello.__name__
        assert modello.model_config.get("extra") == "forbid", modello.__name__

    skill = SkillVista(chiave="x", etichetta="X")
    with pytest.raises(ValidationError):
        SkillVista(chiave="x", etichetta="X", campo_inventato=1)
    with pytest.raises(ValidationError):
        skill.costo_mana = 99  # type: ignore[misc]


def test_gli_slot_equip_sono_un_vocabolario_chiuso() -> None:
    """Come ogni cosa con conseguenza meccanica (F-4): gli slot si dichiarano ORA,
    così gli oggetti futuri entreranno in caselle già esistenti.

    Il vocabolario è passato da 2 membri (`arma`/`armatura` = le due *leve di geometria*)
    ai 9 slot fisici dell'armatura + il mount impugnato (ADR-1 D5), perché ora gli
    oggetti esistono davvero e si indossano in un posto. **Un solo enum di slot**: la
    famiglia armatura è il sottoinsieme `SLOT_ARMATURA`, non un secondo enum che
    divergerebbe da questo."""
    assert {s.value for s in SlotEquip} == {
        "arma",
        "testa", "busto", "braccio_dx", "braccio_sx",
        "mano_dx", "mano_sx", "gambe", "piede_dx", "piede_sx",
    }
    with pytest.raises(ValidationError):
        EquipVista(slot="cappello")  # type: ignore[arg-type]


def test_le_due_famiglie_di_slot_partizionano_il_vocabolario() -> None:
    """`SLOT_ARMATURA` e `SLOT_IMPUGNATI` sono una partizione, non due liste scritte a
    mano che si sovrappongono: la media pesata di `m_armatura` itera la prima e un
    mount impugnato finito lì dentro falserebbe il denominatore (ADR-1 D5)."""
    assert set(SLOT_ARMATURA) | set(SLOT_IMPUGNATI) == set(SlotEquip)
    assert not (set(SLOT_ARMATURA) & set(SLOT_IMPUGNATI))
    assert len(SLOT_ARMATURA) == 9, "il denominatore della media pesata è fisso a 9"


def test_la_scheda_regge_senza_i_campi_nuovi() -> None:
    """Tutti i campi nuovi hanno un default: un costruttore vecchio (o un host che
    non li conosce) continua a funzionare — è la condizione perché il contratto
    possa crescere senza rompere nulla."""
    scheda = SchedaVista(uuid="u", nome="Carl", vivo=True, hp=10, hp_max=10)
    assert scheda.mana == 0 and scheda.mana_max == 0
    assert scheda.skills == () and scheda.equip == ()
    assert scheda.progressione == ProgressioneVista()


# --- I campi VUOTI PER ORA: il contratto c'è, il contenuto no -------------------

def test_la_progressione_e_dichiarata_e_ferma_a_zero() -> None:
    """Nessuna fonte di esperienza esiste: il contratto lo dice con zeri, non
    con l'assenza del campo. Quando arriverà l'XP questo test resterà verde
    (cambierà solo ciò che il motore ci mette dentro)."""
    p = ProgressioneVista()
    assert (p.esperienza, p.esperienza_al_prossimo, p.punti_da_spendere) == (0, 0, 0)
    assert p.livello_piano == 1  # la PROFONDITÀ, non un livello di personaggio


def test_lo_slot_equip_vuoto_si_riconosce_dal_nome_vuoto(run_pulita, tmp_path) -> None:
    """Oggi il motore non ha oggetti: `nome=""` è lo slot vuoto, e `categoria`
    porta comunque la geometria ATTIVA (quella che muove le derivate)."""
    sessione = costruisci_sessione(nome="Nudo", seed=1, directory=tmp_path)
    asyncio.run(sessione.prossima_narrazione())
    equip = {e.slot: e for e in sessione.scheda().equip}

    assert set(equip) == set(SlotEquip), "ogni slot dichiarato dev'essere rappresentato"
    for voce in equip.values():
        assert voce.nome == "", "nessun oggetto esiste ancora: lo slot è vuoto"
        assert voce.categoria, "ma la geometria attiva c'è sempre (default §11)"


# --- I campi POPOLATI: il contratto dice la verità del motore -------------------

def test_le_skill_vengono_dal_repertorio_e_dal_catalogo(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(nome="Mago", seed=1, directory=tmp_path)
    asyncio.run(sessione.prossima_narrazione())
    skills = {s.chiave: s for s in sessione.scheda().skills}

    assert tuple(skills) == MOSSE_INIZIALI_PROTAGONISTA
    for chiave, vista in skills.items():
        mossa = CATALOGO_MOSSE[chiave]
        assert vista.costo_mana == mossa.costo_mana
        assert vista.cd_totale == mossa.cooldown
        assert vista.etichetta


def test_fuori_scontro_il_cd_residuo_e_zero_per_costruzione(run_pulita, tmp_path) -> None:
    """`Ricariche` è effimero: fuori dallo scontro non esiste, quindi la scheda non
    può mostrare un cooldown stantio."""
    sessione = costruisci_sessione(nome="Fuori", seed=1, directory=tmp_path)
    asyncio.run(sessione.prossima_narrazione())
    assert all(s.cd_residuo == 0 for s in sessione.scheda().skills)


def test_pronta_riflette_il_mana_anche_in_narrazione(run_pulita, tmp_path) -> None:
    """Il mana è POSSEDUTO e persiste fuori dallo scontro: a secco la scheda dice
    "non pronta" già in narrazione — ed è l'informazione che spingerà a riposare."""
    sessione = costruisci_sessione(nome="Secco", seed=1, directory=tmp_path)
    asyncio.run(sessione.prossima_narrazione())
    assert all(s.pronta for s in sessione.scheda().skills)

    esper.component_for_entity(protagonista()[0], Mana).attuale = 0
    per_chiave = {s.chiave: s for s in sessione.scheda().skills}
    assert per_chiave["attacco"].pronta, "il fallback gratuito è sempre pronto"
    assert not per_chiave["dardo_arcano"].pronta
    assert not per_chiave["attacco_pesante"].pronta


def test_il_mana_nella_scheda_e_corrente_su_massimo(run_pulita, tmp_path) -> None:
    sessione = costruisci_sessione(nome="Pieno", seed=1, directory=tmp_path)
    asyncio.run(sessione.prossima_narrazione())
    scheda = sessione.scheda()
    assert scheda.mana == scheda.mana_max > 0


def test_una_chiave_fuori_catalogo_non_inventa_una_skill(run_pulita, tmp_path) -> None:
    """Dato incompleto (un repertorio che cita una mossa che non esiste): la scheda
    la SALTA invece di fabbricare una voce fantasma."""
    sessione = costruisci_sessione(nome="Rotto", seed=1, directory=tmp_path)
    asyncio.run(sessione.prossima_narrazione())
    pent = protagonista()[0]
    esper.remove_component(pent, Repertorio)
    esper.add_component(pent, Repertorio(mosse=("attacco", "mossa_che_non_esiste")))

    chiavi = [s.chiave for s in sessione.scheda().skills]
    assert chiavi == ["attacco"]
