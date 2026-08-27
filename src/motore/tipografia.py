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


def coda_su_frase(testo: str, max_chars: int = 320) -> str:
    """La CODA di un testo (ultime frasi, ~max_chars), con taglio su confine
    di frase: quanto basta a riprendere il filo senza ripagare il testo
    intero. Deterministica.

    È il taglio GIUSTO per la memoria di conversazione: la scenografia sta
    in testa, i FATTI atterrano in coda (playtest live 2026-08-27: il filo
    di scena tagliava `prosa[:160]` e il Tenente Kross — introdotto a metà
    battuta — spariva dal contesto del turno dopo, che lo re-inventava)."""
    testo = " ".join(testo.split())
    if len(testo) <= max_chars:
        return testo
    coda = testo[-max_chars:]
    # Riparti dalla prima frase completa dentro la finestra (se ce n'è una).
    for sep in (". ", "! ", "? "):
        i = coda.find(sep)
        if i != -1:
            return coda[i + len(sep):]
    return coda


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
