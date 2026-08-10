"""Contenuti SINTETICI per i test — stagioni e piani costruiti al volo.

I lucchetti del motore provano MECCANISMI (copione keyed, discesa, freeze, gate,
arruolamento), mai il contenuto pubblicato: legare un test al cast di una
stagione vera trasforma «aggiungere una testa» in «rompere cinque test» e
vincola l'authoring dell'utente (perimetro: forma, non contenuto). Da qui in
poi il contenuto del repo è LIBERO di cambiare: i test costruiscono il proprio.

Gli archetipi sono RISOLTI per la stessa strada di `risolvi_stagione`
(`_risolvi_archetipo`: merge con la calibrazione per gli storici, profilo
dall'asset di libreria per gli slug nuovi come `felino`) — mai profili cuciti
su misura nel test: ciò che si prova deve restare raggiungibile dal contenuto.
"""

from __future__ import annotations

from contracts import (
    ArchetipoAsset,
    Blocco,
    BudgetDesign,
    Grado,
    MobAsset,
    PianoRisolto,
    StagioneRisolta,
)

ARCHETIPI_DEFAULT = ("slime", "scheletro", "goblin")


def archetipi_sintetici(slugs=ARCHETIPI_DEFAULT) -> list[ArchetipoAsset]:
    """Archetipi risolti (profilo pieno) senza passare dalla stagione pubblicata."""
    from main import _risolvi_archetipo, carica_asset

    risolti: list[ArchetipoAsset] = []
    errori: list[str] = []
    for slug in slugs:
        asset = carica_asset("archetipi", slug)
        risolto = _risolvi_archetipo(slug, asset, errori)
        assert risolto is not None and not errori, (slug, errori)
        risolti.append(risolto)
    return risolti


def mob_sintetico(
    slug: str,
    *,
    nome: str | None = None,
    archetipo: str = "slime",
    grado: Grado = Grado.BRONZO,
    blocchi=(),
    prosa: str | None = None,
    tags=(),
    mosse=(),
) -> MobAsset:
    return MobAsset(
        slug=slug,
        nome=nome or slug.replace("-", " ").title(),
        archetipo=archetipo,
        grado=grado,
        blocchi=list(blocchi),
        descrizione=f"Comparsa sintetica {slug}.",
        prosa_stanza=prosa or f"La scena di {slug}: qualcosa si muove.",
        tags=list(tags),
        mosse=list(mosse),
    )


def piano_sintetico(
    n: int = 1,
    *,
    n_stanze: int = 3,
    cast: list[MobAsset] | None = None,
    gradi=(Grado.BRONZO, Grado.ARGENTO),
    blocchi=(Blocco.VELENO, Blocco.RIGENERAZIONE),
    archetipi=ARCHETIPI_DEFAULT,
    slug: str | None = None,
    stanze: int | None = None,
    **extra,
) -> PianoRisolto:
    """Un piano di comparse: senza `cast` esplicito, `n_stanze` slime di bronzo
    (una stanza per voce, come il copione keyed si aspetta)."""
    if cast is None:
        cast = [
            mob_sintetico(
                f"comparsa-{n}-{i}",
                nome=f"Comparsa {n}.{i}",
                prosa=f"La stanza {i} del piano {n} borbotta di slime.",
            )
            for i in range(n_stanze)
        ]
    return PianoRisolto(
        slug=slug or f"sintetico-{n}",
        versione=1,
        titolo=f"Sintetico {n}",
        tema="cablaggio",
        budget=BudgetDesign(
            gradi=list(gradi), blocchi=list(blocchi), archetipi=list(archetipi)
        ),
        cast=cast,
        stanze=stanze,
        **extra,
    )


def territorio_sintetico(prefisso: str = "t"):
    """Un territorio RISOLTO minimo e coerente: un boss per tier nominato (grado
    = grado del tier, per costruzione), tabelle procedurali per distretto e
    quartiere, una tabella di spawn per il quartiere."""
    from contracts import (
        Frequenza,
        TabellaBossProcedurali,
        TabellaSpawnRisolta,
        TerritorioRisolto,
        TierTerritorio,
        VoceSpawnRisolta,
    )

    def _boss(tier: TierTerritorio) -> "MobAsset":
        return mob_sintetico(
            f"{prefisso}-boss-{tier.value}", grado=tier.grado, archetipo="slime",
            prosa=f"Il boss di {tier.value} ti aspetta al varco.",
        )

    nominati = (
        TierTerritorio.PIANO, TierTerritorio.PAESE,
        TierTerritorio.PROVINCIA, TierTerritorio.CITTA,
    )
    return TerritorioRisolto(
        conteggi={
            TierTerritorio.PAESE: 2, TierTerritorio.PROVINCIA: 10,
            TierTerritorio.CITTA: 40, TierTerritorio.DISTRETTO: 4,
            TierTerritorio.QUARTIERE: 4,
        },
        boss={tier: [_boss(tier)] for tier in nominati},
        procedurali=[
            TabellaBossProcedurali(
                tier=tier,
                nomi=[f"{prefisso}-n{i}" for i in range(4)],
                gimmick=[f"gimmick {i}" for i in range(4)],
                archetipi=["slime", "scheletro"],
            )
            for tier in (TierTerritorio.DISTRETTO, TierTerritorio.QUARTIERE)
        ],
        spawn=[
            TabellaSpawnRisolta(
                tier=TierTerritorio.QUARTIERE,
                voci=[
                    VoceSpawnRisolta(
                        mob=mob_sintetico(f"{prefisso}-riempitivo-{i}"),
                        frequenza=Frequenza.COMUNE if i else Frequenza.RARO,
                    )
                    for i in range(3)
                ],
            )
        ],
        stanze_per_zona=3,
    )


def piano_territoriale(n: int = 1, *, prefisso: str = "t"):
    """Un piano-mondo sintetico: budget su TUTTI i gradi + territorio minimo."""
    from contracts import Grado as _G

    return piano_sintetico(
        n,
        gradi=tuple(_G),
        slug=f"mondo-{n}",
        territorio=territorio_sintetico(prefisso),
    )


def stagione_sintetica(
    n_piani: int = 2,
    *,
    n_stanze: int = 3,
    slug: str = "s-sintetica",
    piani: list[PianoRisolto] | None = None,
    archetipi_slugs=ARCHETIPI_DEFAULT,
) -> StagioneRisolta:
    """Una stagione risolta pronta per `costruisci_sessione(stagione=...)`."""
    return StagioneRisolta(
        slug=slug,
        versione=1,
        numero=1,
        titolo="Stagione sintetica",
        mondo="X",
        piani=piani or [piano_sintetico(i + 1, n_stanze=n_stanze) for i in range(n_piani)],
        archetipi=archetipi_sintetici(archetipi_slugs),
    )
