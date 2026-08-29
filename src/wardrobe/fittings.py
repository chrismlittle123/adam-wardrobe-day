"""What size he is in each shop.

A size is not a fact about a man, it is a fact about a man and a shop. He is a
Uniqlo M, an M&S 38 and a Tyrwhitt 15.5 with a 33 sleeve, and none of those
numbers converts into the others. The measurements say what his body is; the
shop says what to ask for.

So this records the answer per shop and per garment, and it is filled in the way
it is actually learned: by trying something on, or by reading a shop's own
garment measurements against his. A fitting he has confirmed in a changing room
outranks anything derived from a table, and is marked as such.
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

from . import paths

# How much a fitting can be trusted, worst first, so sorting puts the ones he
# has actually worn at the top.
GUESSED, DERIVED, TRIED = "Guessed", "From the size chart", "Tried on"
CONFIDENCE: tuple[str, ...] = (GUESSED, DERIVED, TRIED)

VERDICTS: tuple[str, ...] = ("Perfect", "Good", "Too big", "Too small", "Wrong shape")


@dataclass
class Fitting:
    id: str = ""
    retailer: str = ""              # retailer id
    garment: str = ""
    line: str = ""                  # which range, where a shop has more than one
    size: dict[str, str] = field(default_factory=dict)
    fit: str = ""
    confidence: str = GUESSED
    verdict: str = ""
    note: str = ""

    @property
    def size_line(self) -> str:
        return " · ".join(f"{k} {v}" for k, v in self.size.items() if v and v != "—")

    @property
    def settled(self) -> bool:
        return self.confidence == TRIED and self.verdict in ("Perfect", "Good")


@dataclass
class Fittings:
    fittings: list[Fitting] = field(default_factory=list)
    path: Path = field(default_factory=paths.fittings)

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Fittings":
        path = Path(path) if path else paths.fittings()
        book = cls(fittings=[], path=path)
        if not path.is_file():
            return book
        allowed = {f.name for f in fields(Fitting)}
        for row in tomllib.loads(path.read_text()).get("fittings", []):
            fitting = Fitting(**{k: v for k, v in row.items() if k in allowed})
            fitting.id = ""
            book.add(fitting)
        return book

    def save(self) -> Path:
        self.path.write_text(tomli_w.dumps(
            {"fittings": [asdict(f) for f in self.fittings]}))
        return self.path

    def add(self, fitting: Fitting) -> Fitting:
        fitting.id = fitting.id or self.unique_id(fitting)
        self.fittings.append(fitting)
        return fitting

    def remove(self, fitting_id: str) -> None:
        self.fittings = [f for f in self.fittings if f.id != fitting_id]

    def by_id(self, fitting_id: str) -> Fitting | None:
        return next((f for f in self.fittings if f.id == fitting_id), None)

    def unique_id(self, fitting: Fitting) -> str:
        base = f"{fitting.retailer}-{fitting.garment}".lower().replace(" ", "-")
        taken = {f.id for f in self.fittings}
        if base not in taken:
            return base
        n = 2
        while f"{base}-{n}" in taken:
            n += 1
        return f"{base}-{n}"

    def for_garment(self, garment: str) -> list[Fitting]:
        """Every shop he knows his size in for this garment, best-known first."""
        return sorted((f for f in self.fittings if f.garment == garment),
                      key=lambda f: -CONFIDENCE.index(f.confidence))

    def find(self, retailer: str, garment: str) -> Fitting | None:
        return next((f for f in self.fittings
                     if f.retailer == retailer and f.garment == garment), None)

    def by_retailer(self) -> dict[str, list[Fitting]]:
        out: dict[str, list[Fitting]] = {}
        for fitting in self.fittings:
            out.setdefault(fitting.retailer, []).append(fitting)
        return {k: sorted(out[k], key=lambda f: f.garment) for k in sorted(out)}

    def settled(self) -> list[Fitting]:
        return [f for f in self.fittings if f.settled]


def reference_shops(plan, catalogue, garment: str) -> list[str]:
    """The shops his own sourcing plan sends him to for this garment.

    A size is only worth recording where he actually shops, and he has already
    written that down. This reads it rather than asking again.
    """
    known = catalogue.lookup()
    out: list[str] = []
    for route in plan.routes:
        if route.garment != garment:
            continue
        out += [s for s in route.stores if s in known and s not in out]
    return out
