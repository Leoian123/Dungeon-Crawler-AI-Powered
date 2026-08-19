"""Composition root del provider (`provider/root.py`): la selezione fake/live, il
cablaggio delle corsie e il tally condiviso vivono nel pacchetto provider — fuori
dall'host TUI — e la chiave non viene MAI letta (solo la sua presenza).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import provider as pacchetto
from contracts import TurnoNarrazione
from provider import (
    CORSIE_DEFAULT,
    NOME_VAR_CHIAVE,
    ProfiloCorsia,
    costruisci_backend_live,
    scegli_corsie,
    scegli_provider,
)

_SRC = Path(__file__).resolve().parents[1] / "src"


def test_fake_forzato(monkeypatch) -> None:
    monkeypatch.setenv(NOME_VAR_CHIAVE, "chiave-di-test-mai-vera")
    prov, etichetta = scegli_provider(["--fake"])
    assert prov is None and "scriptato" in etichetta


def test_senza_chiave_offline_con_motivo(monkeypatch) -> None:
    monkeypatch.delenv(NOME_VAR_CHIAVE, raising=False)
    prov, etichetta = scegli_provider([])
    assert prov is None and "offline" in etichetta and NOME_VAR_CHIAVE in etichetta


def test_sdk_assente_offline_con_motivo(monkeypatch) -> None:
    monkeypatch.setattr(pacchetto, "chiave_presente", lambda: True)
    monkeypatch.setattr(pacchetto, "sdk_disponibile", lambda: False)
    prov, etichetta = scegli_provider([])
    assert prov is None and "SDK" in etichetta


def test_live_esplicito_fallisce_rumorosamente(monkeypatch) -> None:
    # Nessun degrado silenzioso: `--live` senza chiave è un errore DETTO, mai un
    # fallback muto che maschera un errore di setup.
    monkeypatch.delenv(NOME_VAR_CHIAVE, raising=False)
    with pytest.raises(SystemExit):
        scegli_provider(["--live"])


def test_live_cabla_corsie_e_tally_condiviso(monkeypatch) -> None:
    monkeypatch.setattr(pacchetto, "chiave_presente", lambda: True)
    monkeypatch.setattr(pacchetto, "sdk_disponibile", lambda: True)
    prov, etichetta = scegli_provider([])
    forte = prov._per_schema[TurnoNarrazione]
    veloce = prov._predefinito
    # UN tally per la run, non per-modello — e viaggia col provider per l'host.
    assert forte.consumo is veloce.consumo is prov.consumo
    assert forte.modello == CORSIE_DEFAULT["forte"].modello
    assert veloce.modello == CORSIE_DEFAULT["veloce"].modello
    assert "live" in etichetta


def test_corsie_e_instradamento_iniettabili(monkeypatch) -> None:
    # Il binding corsia→profilo e schema→corsia sono DATI del chiamante.
    monkeypatch.setattr(pacchetto, "chiave_presente", lambda: True)
    monkeypatch.setattr(pacchetto, "sdk_disponibile", lambda: True)
    corsie = {
        "forte": ProfiloCorsia(modello="m-forte", max_tokens=4096, timeout=60.0),
        "veloce": ProfiloCorsia(modello="m-veloce", max_tokens=1024, timeout=10.0),
    }
    prov, _e = scegli_provider([], corsie=corsie)
    assert prov._per_schema[TurnoNarrazione].modello == "m-forte"
    assert prov._per_schema[TurnoNarrazione].max_tokens == 4096
    assert prov._predefinito.modello == "m-veloce"


def test_scegli_corsie_offline_e_fake(monkeypatch) -> None:
    # Stessa politica di `scegli_provider`: --fake e assenza chiave → offline DETTO.
    monkeypatch.setenv(NOME_VAR_CHIAVE, "chiave-di-test-mai-vera")
    backend, etichetta, consumo = scegli_corsie(["--fake"])
    assert backend is None and consumo is None and "scriptato" in etichetta
    monkeypatch.delenv(NOME_VAR_CHIAVE, raising=False)
    backend, etichetta, consumo = scegli_corsie([])
    assert backend is None and NOME_VAR_CHIAVE in etichetta


def test_scegli_corsie_live_cabla_i_modelli_col_tally_condiviso(monkeypatch) -> None:
    # Il mattone sotto scegli_provider: backend PER CORSIA (chi parla col
    # Master-Engine li inietta per corsia, e la rotta seleziona il modello).
    monkeypatch.setattr(pacchetto, "chiave_presente", lambda: True)
    monkeypatch.setattr(pacchetto, "sdk_disponibile", lambda: True)
    backend, etichetta, consumo = scegli_corsie([])
    assert set(backend) == {"forte", "veloce"}
    assert backend["forte"].modello == CORSIE_DEFAULT["forte"].modello
    assert backend["veloce"].modello == CORSIE_DEFAULT["veloce"].modello
    assert backend["forte"].consumo is backend["veloce"].consumo is consumo
    assert "live" in etichetta


def test_costruisci_backend_condivide_il_tally() -> None:
    backend = costruisci_backend_live()
    assert set(backend) == set(CORSIE_DEFAULT)
    tally = {id(b.consumo) for b in backend.values()}
    assert len(tally) == 1, "i backend delle corsie devono condividere UN ConsumoProvider"


def test_root_non_legge_mai_la_chiave() -> None:
    """PLK §4: il root controlla la PRESENZA della chiave (via `chiave_presente`),
    mai il valore — niente `os.environ` nel modulo."""
    src = (_SRC / "provider" / "root.py").read_text(encoding="utf-8")
    assert "environ" not in src and "getenv" not in src
    assert "chiave_presente" in src


def test_la_tui_delega_al_root() -> None:
    """`gioco_textual._scegli_provider` è un alias sottile: importa dal root, non
    ricopia il cablaggio (una copia divergerebbe in silenzio)."""
    src = (_SRC / "gioco_textual.py").read_text(encoding="utf-8")
    assert "scegli_provider" in src
    assert "AnthropicBackend" not in src and "ProviderPerSchema" not in src
