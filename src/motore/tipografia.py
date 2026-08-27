"""Rifinitura tipografica della prosa AI — deterministica, mai semantica.

Playtest live 2026-08-27 (finding cinico): la prosa di scena chiudeva un
dialogo aperto con «caporale» usando il doppio apice dritto («…ogni tanto.").
Il modello mischia i delimitatori; il motore NON riscrive mai il contenuto,
ma la punteggiatura dei dialoghi è FORMA — e la forma si arbitra al gate,
come tutto il resto (l'AI propone, il motore dispone).

Regola unica, a bilancio: se il testo usa i caporali, ogni doppio apice
(dritto o curvo) diventa il caporale che il bilancio corrente chiede —
chiusura se un « è aperto, apertura altrimenti. Un testo SENZA caporali
resta intatto: uno stile uniforme non è un errore.
"""

from __future__ import annotations

# I doppi apici che il modello mischia ai caporali (mai gli apostrofi).
_APICI = '"“”'


def rifinisci_caporali(testo: str) -> str:
    """Normalizza i delimitatori di dialogo sul caporale, a bilancio.

    No-op se il testo non contiene alcun caporale (stile uniforme) o è vuoto.
    Non aggiunge e non toglie mai un carattere: sostituisce soltanto.
    """
    if not testo or ("«" not in testo and "»" not in testo):
        return testo
    out: list[str] = []
    aperte = 0
    for ch in testo:
        if ch == "«":
            aperte += 1
        elif ch == "»":
            aperte = max(0, aperte - 1)
        elif ch in _APICI:
            if aperte > 0:
                ch = "»"
                aperte -= 1
            else:
                ch = "«"
                aperte += 1
        out.append(ch)
    return "".join(out)
