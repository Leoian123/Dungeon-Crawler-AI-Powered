"""Console admin di calibrazione — accesso prioritario ai **numeri vitali** (§11).

Una TUI Textual per gestire ogni placeholder del gioco (`motore/calibrazione.py`): vedi il
valore corrente, la **spiegazione** di *cosa dovrebbe essere*, il dominio suggerito; modifica,
salva. Le modifiche vanno in un **file di override gitignored** caricato dal motore al
prossimo avvio — il sorgente resta coi default (reversibile).

Questo modulo vive **fuori** dal motore (è un host/tool): importa `motore.calibrazione` e
Textual; il motore non importa né questo né una UI (invariante intatto).

Uso:
  python -m calibratore                 # apre la TUI
  python -m calibratore list            # elenca i parametri (chiave = valore)
  python -m calibratore get S_CONTEST   # stampa il valore effettivo
  python -m calibratore set S_CONTEST 3 # imposta + salva l'override
  python -m calibratore reset S_CONTEST # torna al default + salva
"""

from __future__ import annotations

import sys

from motore import calibrazione as cal


# --- CLI headless (utile senza TTY e per i test) ------------------------------

def _cli(argv: list[str]) -> int:
    cmd = argv[0]
    if cmd == "list":
        for p in cal.elenco():
            segno = "*" if p.chiave in cal.override_correnti() else " "
            print(f"{segno} {p.chiave:28} = {cal.valore(p.chiave)!r:>10}   [{p.categoria}]")
        return 0
    if cmd == "get" and len(argv) >= 2:
        print(cal.valore(argv[1]))
        return 0
    if cmd == "set" and len(argv) >= 3:
        val = cal.imposta(argv[1], argv[2])
        cal.salva_override()
        print(f"{argv[1]} = {val!r} (salvato)")
        return 0
    if cmd == "reset" and len(argv) >= 2:
        cal.azzera(argv[1])
        cal.salva_override()
        print(f"{argv[1]} → default {cal.CATALOGO[argv[1]].default!r} (salvato)")
        return 0
    print(__doc__)
    return 2


# --- TUI Textual --------------------------------------------------------------

def _costruisci_app():
    """Costruisce l'app Textual. Import locale: la TUI è opzionale (la CLI non la richiede)."""
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal
    from textual.widgets import DataTable, Footer, Header, Input, Static

    class Calibratore(App):
        TITLE = "Calibratore — numeri vitali (§11)"
        CSS = """
        Horizontal { height: 1fr; }
        #tabella { width: 3fr; }
        #dettaglio { width: 2fr; border: round $accent; padding: 1 2; }
        #editor { dock: bottom; display: none; }
        #editor.attivo { display: block; }
        """
        BINDINGS = [
            Binding("e,enter", "modifica", "Modifica"),
            Binding("r", "reset", "Reset default"),
            Binding("s", "salva", "Salva override"),
            Binding("q", "quit", "Esci"),
        ]

        def __init__(self) -> None:
            super().__init__()
            self._sel: str | None = None
            self._in_modifica: str | None = None

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal():
                yield DataTable(id="tabella")
                yield Static("", id="dettaglio")
            yield Input(id="editor")
            yield Footer()

        def on_mount(self) -> None:
            t = self.query_one("#tabella", DataTable)
            t.cursor_type = "row"
            t.add_columns("", "Parametro", "Valore", "Categoria")
            self._ricarica()
            t.focus()

        def _ricarica(self) -> None:
            t = self.query_one("#tabella", DataTable)
            riga_sel = t.cursor_row
            t.clear()
            over = cal.override_correnti()
            for p in cal.elenco():
                segno = "●" if p.chiave in over else ""
                t.add_row(segno, p.chiave, str(cal.valore(p.chiave)), p.categoria, key=p.chiave)
            if t.row_count:
                t.move_cursor(row=min(riga_sel, t.row_count - 1))

        def _mostra(self, chiave: str) -> None:
            p = cal.CATALOGO[chiave]
            over = cal.override_correnti()
            stato = "[yellow]override[/]" if chiave in over else "[dim]default[/]"
            scelte = f"\n[b]Scelte:[/b] {', '.join(p.scelte)}" if p.scelte else ""
            self.query_one("#dettaglio", Static).update(
                f"[b]{p.chiave}[/b]   {stato}\n[dim]{p.categoria}[/dim]\n\n"
                f"{p.spiegazione}\n\n"
                f"[b]Dominio:[/b] {p.dominio} {('('+p.unita+')') if p.unita else ''}\n"
                f"[b]Default:[/b] {p.default!r}    [b]Corrente:[/b] {cal.valore(chiave)!r}"
                f"{scelte}\n\n[dim]e=modifica · r=reset · s=salva[/dim]"
            )

        def on_data_table_row_highlighted(self, ev) -> None:
            self._sel = ev.row_key.value
            if self._sel is not None:
                self._mostra(self._sel)

        def action_modifica(self) -> None:
            if self._sel is None:
                return
            self._in_modifica = self._sel
            ed = self.query_one("#editor", Input)
            ed.value = str(cal.valore(self._sel))
            ed.placeholder = f"{self._sel} — {cal.CATALOGO[self._sel].dominio}"
            ed.add_class("attivo")
            ed.focus()

        def on_input_submitted(self, ev) -> None:
            chiave = self._in_modifica
            if chiave is None:
                return
            try:
                cal.imposta(chiave, ev.value)
            except (ValueError, KeyError) as exc:
                self.notify(f"Valore non valido: {exc}", severity="error")
                return
            ed = self.query_one("#editor", Input)
            ed.remove_class("attivo")
            self._in_modifica = None
            self._ricarica()
            self._mostra(chiave)
            self.query_one("#tabella", DataTable).focus()
            self.notify(f"{chiave} = {cal.valore(chiave)!r}  (premi 's' per salvare)")

        def action_reset(self) -> None:
            if self._sel is None:
                return
            cal.azzera(self._sel)
            self._ricarica()
            self._mostra(self._sel)
            self.notify(f"{self._sel} → default {cal.CATALOGO[self._sel].default!r}")

        def action_salva(self) -> None:
            percorso = cal.salva_override()
            n = len(cal.override_correnti())
            self.notify(f"Salvati {n} override in {percorso.name}")

    return Calibratore()


def main(argv: list[str] | None = None) -> int:
    # La console (e le categorie/spiegazioni) usano Unicode; forza UTF-8 sullo stdout così
    # la CLI non crasha su code-page legacy (Windows cp1252).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        return _cli(argv)
    _costruisci_app().run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
