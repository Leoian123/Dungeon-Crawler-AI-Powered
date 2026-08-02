"""Sicurezza e isolamento della chiave API (PLK §4 + best practice Anthropic/OWASP):

  - nessuna chiave committata nel repo (scan del pattern `sk-ant-` sui sorgenti);
  - `.env` gitignored, `.env.example` senza valori;
  - il codice controlla solo la PRESENZA della chiave, mai il valore (niente copie);
  - il default di `costruisci_sessione` resta OFFLINE anche con la chiave
    nell'ambiente (il live è un'iniezione esplicita dell'host: mai rete implicita);
  - la chiave non finisce mai nei prompt della pipeline.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from main import costruisci_sessione
from provider import FakeProvider, NOME_VAR_CHIAVE, chiave_presente

_ROOT = Path(__file__).resolve().parent.parent

# Pattern delle chiavi Anthropic reali. Spezzato ("sk-ant" + "-") perché QUESTO file
# non diventi un falso positivo del proprio scan.
_PATTERN_CHIAVE = "sk-ant" + "-"


def _sorgenti() -> list[Path]:
    file: list[Path] = []
    for cartella in ("src", "tests"):
        file += (_ROOT / cartella).rglob("*.py")
    file += _ROOT.glob("*.bat")
    file += _ROOT.glob("*.md")
    file.append(_ROOT / ".env.example")
    return [f for f in file if f.is_file()]


def test_nessuna_chiave_nel_repo() -> None:
    """Secret-scanning minimale, offline: il pattern di una chiave reale non deve
    comparire in nessun sorgente/launcher/doc versionato."""
    offese = []
    for f in _sorgenti():
        testo = f.read_text(encoding="utf-8", errors="replace")
        if _PATTERN_CHIAVE in testo and f.name != Path(__file__).name:
            offese.append(str(f.relative_to(_ROOT)))
    assert not offese, f"possibile chiave API committata in: {offese}"


def test_env_gitignored_e_template_vuoto() -> None:
    gitignore = (_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "\n.env\n" in gitignore or gitignore.endswith(".env")
    esempio = (_ROOT / ".env.example").read_text(encoding="utf-8")
    riga = next(l for l in esempio.splitlines() if l.startswith(NOME_VAR_CHIAVE))
    assert riga.rstrip() == f"{NOME_VAR_CHIAVE}="  # template SENZA valore


def test_chiave_presente_controlla_solo_la_presenza(monkeypatch) -> None:
    monkeypatch.delenv(NOME_VAR_CHIAVE, raising=False)
    assert chiave_presente() is False
    monkeypatch.setenv(NOME_VAR_CHIAVE, _PATTERN_CHIAVE + "test-finta")
    assert chiave_presente() is True  # bool, mai il valore


def test_default_offline_anche_con_chiave_nell_ambiente(monkeypatch, run_pulita) -> None:
    """Il live non è MAI implicito: anche con la chiave impostata, senza iniezione
    esplicita il provider resta il fake (i test non toccano la rete per costruzione)."""
    monkeypatch.setenv(NOME_VAR_CHIAVE, _PATTERN_CHIAVE + "test-finta")
    sessione = costruisci_sessione(seed=3)
    assert isinstance(sessione.provider, FakeProvider)


def test_la_chiave_non_entra_mai_nei_prompt(monkeypatch, run_pulita) -> None:
    """Il prompt è costruito SOLO dallo stato di gioco: la chiave non ha alcun
    percorso verso il testo che parte (né verso log/URL)."""
    finta = _PATTERN_CHIAVE + "test-finta-123"
    monkeypatch.setenv(NOME_VAR_CHIAVE, finta)
    sessione = costruisci_sessione(seed=3)
    asyncio.run(sessione.prossima_narrazione())
    riep = sessione.riepiloga_azione("guardo meglio")
    asyncio.run(sessione.esegui_azione(riep))
    assert sessione.provider.prompt_ricevuti  # la pipeline ha parlato col provider
    assert all(finta not in p for p in sessione.provider.prompt_ricevuti)
    assert all(finta not in s for s in sessione.provider.sistemi)  # né nel canale system


def test_selezione_provider_esplicita(monkeypatch) -> None:
    """`gioco_textual._scegli_provider`: --fake forza offline; senza chiave resta
    offline con etichetta parlante (nessun degrado silenzioso)."""
    import gioco_textual

    monkeypatch.delenv(NOME_VAR_CHIAVE, raising=False)
    provider, etichetta = gioco_textual._scegli_provider([])
    assert provider is None and "offline" in etichetta
    monkeypatch.setenv(NOME_VAR_CHIAVE, _PATTERN_CHIAVE + "test-finta")
    provider, etichetta = gioco_textual._scegli_provider(["--fake"])
    assert provider is None and "scriptato" in etichetta
