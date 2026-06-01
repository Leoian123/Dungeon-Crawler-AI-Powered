# esper — dipendenza VENDORIZZATA

- **Versione pinnata:** `esper==3.7` (serie 3.x — API a livello di modulo, `World` rimosso).
- **Origine:** sdist ufficiale `esper-3.7.tar.gz` da PyPI, `pip download --no-deps --no-binary :all:`.
- **Cosa è stato copiato:** solo il package `esper/` (`__init__.py`, `py.typed`) + `LICENSE`.
- **Perché vendorizzato:** puro Python, zero dipendenze transitive → riproducibilità totale
  del build senza risoluzione a build-time. (ESP §0)

## Regole d'uso (ESP §0, §0.1 — normative)

- Si usa **solo l'API a livello di modulo**: `esper.create_entity()`, `esper.add_component()`,
  `esper.get_components()`, `esper.switch_world()`, `esper.delete_world()`, ...
- `esper.World()` è **VIETATO** (non esiste più in 3.x). Un test/grep fallisce se compare
  nel sorgente di progetto (`tests/test_vendor_esper.py`).
- Lo stato globale (contesto World di default implicito) va isolato nei test
  (`switch_world`/`delete_world`, vedi `tests/conftest.py`).

## Aggiornamento

Non è una dipendenza "viva": non si aggiorna con `pip install -U`. Per cambiare versione,
ri-vendorizzare deliberatamente e rivedere l'API contro queste regole.
