# Progetto: RPG a turni AI-empowered (MVP — fetta verticale di un piano)

## Identità
RPG a turni ispirato a Dungeon Crawler Carl. Due fasi esclusive:
NARRAZIONE (AI genera mondo/entità) ⇄ COMBATTIMENTO (turni deterministici).
Principio invariante: **l'AI propone, il motore dispone** — l'AI è varietà di
contenuto, il motore arbitra OGNI esito, in entrambe le fasi.

## Le spec normative stanno in docs/ — leggile, non andare a memoria
ESP esper-implementazione · FNC fasi-narrazione-combattimento · IC interfaccia-contratto
PLK provider-llm-key · ACV architettura-ciclo-vita · F contratto-ai-motore
G combattimento-forma-run · H persistenza-salvataggio · J tempo-modello-scansione
progetto-indice-decisioni = cruscotto + invarianti trasversali.

## Architettura a tre strati (membrana a tenuta sui due lati)
- `motore/`     logica di gioco. NON importa MAI Textual.
- `contracts/`  DTO/eventi/intenti/schema Pydantic + interfaccia provider. ZERO
                dipendenze di progetto (solo stdlib + Pydantic). Non importa esper,
                Textual, provider.
- `adattatore/` UNICO modulo che importa Textual. Importa SOLO contracts + Textual,
                MAI esper/World/Processor.
Motore e vista si parlano solo via `contracts`, mai a vicenda. (C-2a, C-2b, C-3)

## Disciplina delle dipendenze
- Python pinnato (es. 3.12). esper VENDORIZZATO nel repo, pinnato 3.x, SOLO API a
  livello di modulo (`esper.World()` VIETATO). Textual pinnato esatto + lockfile
  (unica dipendenza "viva"). Pydantic pinnato. Nessun `pip install -U` silenzioso.

## Verifica, non ricordare (l'agente sbaglia a memoria su queste tre)
- API esper 3.x (modulo, non `World()`) — verifica sul codice vendorizzato.
- Output strutturato nativo Anthropic — verifica sulla doc API attuale.
- Worker API di Textual (`@work`/`run_worker`/`exclusive`/`group`/`cancel`) — doc attuale.

## Workflow di ogni task
1. Leggi i documenti citati nel prompt della fase.
2. Implementa SOLO ciò che la fase chiede (no scope creep, no widget di contorno).
3. Auto-verifica contro i criteri nominati (C-/F-/G-/E-/H-/J-). Scrivi i test.
4. Test headless verdi → fermati e riporta. Non procedere alla fase successiva.

## Test = contesto esper isolato (NON il default)
Ogni test: setup `esper.switch_world("<nome-test>")`; teardown `switch_world(default)`
POI `delete_world(...)`. Mai eliminare il contesto attivo. (ESP §0.1)

## Le linee rosse (dal cruscotto — invarianti trasversali, non si rinegoziano)
- L'LLM non decide MAI un esito; in combattimento: risolvi prima, narra dopo.
- L'AI non emette numeri: sceglie da enum chiusi dentro un budget; i numeri li
  deriva il motore. Mai applicare output LLM allo stato senza gate di validazione.
- async sì, thread no. `process()` guidato dal turno, mai dall'orologio/frame.
- Phase-gate strutturale (`PhasedProcessor`), mai check di fase a mano nei process().
- Un solo proprietario dell'avanzamento per ogni componente con stato.
- `switch_world` SOLO al confine guscio↔run; eventi di bus SOLO intra-run. Mai scambiarli.
- Bus tipizzato di progetto (dataclass, riferimenti forti), MAI il dispatcher nativo esper.
- Permadeath: terminale di run = `MortePersonaggio` (death-check seeded), non sconfitta.
- La chiave LLM non finisce MAI in URL, log, codice o documenti.