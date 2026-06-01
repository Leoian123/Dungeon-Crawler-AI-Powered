"""guscio — il confine guscio↔run e l'orchestrazione a livello app (nodo E).

La macchina-guscio (`Guscio`) **orchestra** i confini guscio↔run: decide il *quando* e
**chiama** le operazioni di contesto del livello save/load (H), che è l'unica autorità su
`current_world` (ESP §0.1) e possiede il *come*. Perciò `switch_world`/`delete_world`
**non vivono qui** ma in H; il guscio non li mette mai in un Processor/handler/`process()`
(E-2/E-4). Gli eventi di bus sono intra-run; il bus è process-global, costruito al boot,
fuori da ogni run-World (E-9).

È **orchestrazione a livello app** (E-7): non è un World, non ha Processor di guscio.
Importa `contracts` + `motore` (per assemblare i sistemi della run e chiamare il
meccanismo di persistenza), **mai** Textual: è host-agnostica.
"""

from .macchina import NOME_DEFAULT, NOME_RUN, Guscio, StatoGuscio, Terminale

__all__ = ["Guscio", "StatoGuscio", "Terminale", "NOME_RUN", "NOME_DEFAULT"]
