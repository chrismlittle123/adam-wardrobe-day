"""His actual sourcing plan: which shop, for which garment, on what terms.

This is the difference between a ranking and a decision. `retailers.suggest`
works out where a garment of this type at this price could sensibly come from;
this file records where he has already decided it comes from, and why.

A route is finer-grained than a garment type, which is the whole difficulty. A
heavyweight tee and a plain tee are both "T-shirt" and come from different shops;
a dress shirt and a linen shirt are both "Shirt". So a route is selected on three
optional axes rather than by guessing at words in a name:

  grade    what kind of thing it is within its type. Heavyweight, Dress, Smart,
           Branded, Knitted, Everyday.
  fabric   either an exact cloth ("Oxford cotton") or a whole family ("Wool"),
           so one line covers flannel, worsted and hopsack at once.
  fit      Slim, Regular, Relaxed, Oversized.

A route states only the constraints it cares about, and matches only if the
garment satisfies every one of them. Among the routes that match, the one
stating the most constraints wins, so a route with none is simply the default
for its type. Nothing is inferred from spelling, which means a garment named
badly still goes to the right shop and a garment nobody has classified says so.

Everything here is his list, encoded. Where the plan says a condition ("Very
Good or above") or a timing ("on sale") or a specification ("200 gsm"), it is
carried through to the product page rather than left in his head.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

from . import paths
from .retailers import Catalogue, Retailer

VINTED_VG = "Very Good condition or above"
VINTED_NWT = "New with tags only"
ON_SALE = "wait for the sale"


@dataclass
class Route:
    label: str = ""                  # how he says it: "Heavyweight t-shirt"
    garment: str = ""                # the type the app tracks
    stores: list[str] = field(default_factory=list)   # retailer ids, in preference order
    id: str = ""
    grade: str = ""                  # "" means the grade does not matter
    fabric: str = ""                 # an exact cloth
    family: str = ""                 # or a whole fabric family
    fit: str = ""                    # Slim, Regular, Relaxed, Oversized
    condition: str = ""              # what to accept, on the secondhand sites
    timing: str = ""                 # when to buy
    spec: str = ""                   # what to insist on in the product
    note: str = ""

    def shops(self, catalogue: Catalogue) -> list[Retailer]:
        """The shops this route names, in order, skipping any that were deleted
        from the catalogue since the route was written."""
        found = catalogue.lookup()
        return [found[i] for i in self.stores if i in found]

    @property
    def retailers(self) -> list[Retailer]:
        return self.shops(Catalogue.load())

    def where_in(self, catalogue: Catalogue) -> str:
        return " or ".join(r.name for r in self.shops(catalogue)) or "unset"

    @property
    def where(self) -> str:
        return self.where_in(Catalogue.load())

    @property
    def constraints(self) -> dict[str, str]:
        """The axes this route actually cares about."""
        return {k: v for k, v in (("Grade", self.grade), ("Fabric", self.fabric),
                                  ("Family", self.family), ("Fit", self.fit)) if v}

    @property
    def precision(self) -> int:
        return len(self.constraints)

    @property
    def terms(self) -> str:
        return ", ".join(b for b in (self.condition, self.timing, self.spec) if b)

    @property
    def summary(self) -> str:
        return f"{self.where}{f' · {self.terms}' if self.terms else ''}"

    def matches(self, item) -> bool:
        """Every stated constraint must hold. Unstated ones are not consulted."""
        if item.garment != self.garment:
            return False
        if self.grade and item.grade != self.grade:
            return False
        if self.fabric and item.fabric != self.fabric:
            return False
        if self.family and item.family != self.family:
            return False
        return not (self.fit and item.fit != self.fit)


# The plan he started from. Editable in the app; this is what a fresh install
# gets and what the file is seeded with the first time it is saved.
DEFAULT_ROUTES: tuple[Route, ...] = (
    Route("Heavyweight t-shirt", "T-shirt", ["next"], grade="Heavyweight",
          spec="100% cotton, 200 gsm or heavier",
          note="The weight is the whole point. Anything thinner drapes like a vest."),
    Route("Plain t-shirt", "T-shirt", ["uniqlo"],
          spec="Supima cotton",
          note="The default tee. Cheap enough to replace rather than nurse."),

    Route("Blazer", "Blazer", ["vinted"], condition=VINTED_VG),
    Route("Jacket", "Jacket", ["vinted"], condition=VINTED_VG),
    Route("Dress shoes", "Derbies", ["vinted"], condition=VINTED_VG,
          note="Goodyear-welted if you can, so they can be resoled."),
    Route("Boots", "Boots", ["vinted"], condition=VINTED_VG),
    Route("Overcoat", "Overcoat", ["vinted"], condition=VINTED_VG),

    Route("Dress shirt", "Shirt", ["tyrwhitt"], grade="Dress", timing=ON_SALE,
          note="Sized by collar and sleeve, which is the only sane way to buy one."),
    Route("Linen shirt", "Shirt", ["mango"], family="Linen and hemp", timing=ON_SALE),
    Route("Linen trousers", "Trousers", ["mango"], family="Linen and hemp", timing=ON_SALE),
    Route("Wool trousers", "Trousers", ("marks", "next"), family="Wool",
          note="The nine months of the year linen cannot do. Check the composition: "
               "a wool blend below about 60% drapes like a school trouser."),
    Route("Knitted polo", "Polo", ["mango"], grade="Knitted", timing=ON_SALE),

    Route("Polo", "Polo", ["uniqlo"], spec="Piqué cotton"),
    Route("Chinos", "Chinos", ("uniqlo",)),
    Route("Jeans", "Jeans", ("uniqlo",)),
    Route("Overshirt", "Overshirt", ("uniqlo",)),
    Route("Jumper", "Knitwear", ("marks", "uniqlo")),

    # Trainers no longer carry a grade, so smart and branded cannot be told
    # apart by the plan. One route, and the condition does the work.
    Route("Trainers", "Trainers", ["vinted"], condition=VINTED_NWT,
          note="New with tags only. A worn sole has already taken someone else's "
               "gait. For a specific pair from a brand's own sale, put the link on "
               "the piece rather than a route."),

    Route("Suit", "Suit", ["marks"], timing="then have it altered",
          note="Off the peg for the cloth, a tailor for the fit. The alteration is "
               "what makes it look like a suit rather than a costume."),
)

@dataclass
class Plan:
    """The sourcing plan, as editable data.

    Defaults come from DEFAULT_ROUTES until the file is written, so a fresh
    install arrives with a sensible plan rather than an empty page, and editing
    any of it persists the lot.
    """

    routes: list[Route] = field(default_factory=list)
    path: Path = field(default_factory=paths.sourcing)

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Plan":
        path = Path(path) if path else paths.sourcing()
        plan = cls(routes=[], path=path)
        if not path.is_file():
            source = [Route(**asdict(r)) for r in DEFAULT_ROUTES]
        else:
            allowed = {f.name for f in fields(Route)}
            source = [Route(**{k: v for k, v in row.items() if k in allowed})
                      for row in tomllib.loads(path.read_text()).get("routes", [])]
        # Ids are assigned on the way in, not on the way out. They key the edit
        # widgets, and two routes sharing a blank id collide on the page.
        for route in source:
            route.id = ""
            plan.add(route)
        return plan

    def save(self) -> Path:
        for route in self.routes:
            route.id = route.id or self.unique_id(route.label or route.garment)
        self.path.write_text(tomli_w.dumps({"routes": [asdict(r) for r in self.routes]}))
        return self.path

    def by_id(self, route_id: str) -> Route | None:
        return next((r for r in self.routes if r.id == route_id), None)

    def add(self, route: Route) -> Route:
        route.id = route.id or self.unique_id(route.label or route.garment)
        self.routes.append(route)
        return route

    def remove(self, route_id: str) -> None:
        self.routes = [r for r in self.routes if r.id != route_id]

    def unique_id(self, label: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", (label or "route").lower()).strip("-")[:36] or "route"
        taken = {r.id for r in self.routes}
        if base not in taken:
            return base
        n = 2
        while f"{base}-{n}" in taken:
            n += 1
        return f"{base}-{n}"

    def by_garment(self) -> dict[str, list[Route]]:
        out: dict[str, list[Route]] = {}
        for route in self.routes:
            out.setdefault(route.garment, []).append(route)
        return {k: sorted(v, key=lambda r: -r.precision) for k, v in sorted(out.items())}

    def covered(self) -> set[str]:
        return {r.garment for r in self.routes}

    def uncovered(self, garments) -> list[str]:
        covered = self.covered()
        return [g for g in garments if g not in covered]

    def restore_defaults(self) -> "Plan":
        self.routes = []
        for route in DEFAULT_ROUTES:
            fresh = Route(**asdict(route))
            fresh.id = ""
            self.add(fresh)
        self.save()
        return self


def route_for(item, plan: Plan | None = None) -> Route | None:
    """The route this garment follows, or None if the plan does not cover it.

    The most constrained matching route wins. A dress shirt satisfies both the
    dress route and the type's default, and the dress route states more, so it
    takes it.
    """
    plan = plan if plan is not None else Plan.load()
    matching = [r for r in plan.routes if r.matches(item)]
    if not matching:
        return None
    return max(matching, key=lambda r: r.precision)


def why(item, route: Route) -> str:
    """Which constraints put this garment on this route. Shown on the page, so
    the choice can be argued with rather than trusted."""
    if not route.constraints:
        return f"the default for {item.garment.lower()}"
    return ", ".join(f"{axis.lower()} {value}" for axis, value in route.constraints.items())


def covered(plan: Plan | None = None) -> set[str]:
    return (plan or Plan.load()).covered()


def uncovered(garments, plan: Plan | None = None) -> list[str]:
    """Garment types with no route at all, so the gaps stay visible."""
    return (plan or Plan.load()).uncovered(garments)
