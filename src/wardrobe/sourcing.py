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

from dataclasses import dataclass, field

from .retailers import BY_ID, Retailer

VINTED_VG = "Very Good condition or above"
VINTED_NWT = "New with tags only"
ON_SALE = "wait for the sale"


@dataclass(frozen=True)
class Route:
    label: str                       # how he says it: "Heavyweight t-shirt"
    garment: str                     # the type the app tracks
    stores: tuple[str, ...]          # retailer ids, in order of preference
    grade: str = ""                  # "" means the grade does not matter
    fabric: str = ""                 # an exact cloth
    family: str = ""                 # or a whole fabric family
    fit: str = ""                    # Slim, Regular, Relaxed, Oversized
    condition: str = ""              # what to accept, on the secondhand sites
    timing: str = ""                 # when to buy
    spec: str = ""                   # what to insist on in the product
    note: str = ""

    @property
    def retailers(self) -> list[Retailer]:
        return [BY_ID[i] for i in self.stores if i in BY_ID]

    @property
    def where(self) -> str:
        return " or ".join(r.name for r in self.retailers) or "unset"

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


# His plan. Order within a garment does not matter; specificity decides.
ROUTES: tuple[Route, ...] = (
    Route("Heavyweight t-shirt", "T-shirt", ("asos", "next"), grade="Heavyweight",
          spec="100% cotton, 200 gsm or heavier",
          note="The weight is the whole point. Anything thinner drapes like a vest."),
    Route("Plain t-shirt", "T-shirt", ("uniqlo",),
          spec="Supima cotton",
          note="The default tee. Cheap enough to replace rather than nurse."),

    Route("Blazer", "Blazer", ("vinted",), condition=VINTED_VG),
    Route("Jacket", "Jacket", ("vinted",), condition=VINTED_VG),
    Route("Dress shoes", "Derbies", ("vinted",), condition=VINTED_VG,
          note="Goodyear-welted if you can, so they can be resoled."),
    Route("Boots", "Boots", ("vinted",), condition=VINTED_VG),
    Route("Overcoat", "Overcoat", ("vinted",), condition=VINTED_VG),

    Route("Dress shirt", "Shirt", ("tyrwhitt",), grade="Dress", timing=ON_SALE,
          note="Sized by collar and sleeve, which is the only sane way to buy one."),
    Route("Linen shirt", "Shirt", ("mango",), family="Linen and hemp", timing=ON_SALE),
    Route("Linen trousers", "Trousers", ("mango",), family="Linen and hemp", timing=ON_SALE),
    Route("Wool trousers", "Trousers", ("marks", "next"), family="Wool",
          note="The nine months of the year linen cannot do. Check the composition: "
               "a wool blend below about 60% drapes like a school trouser."),
    Route("Knitted polo", "Polo", ("mango",), grade="Knitted", timing=ON_SALE),

    Route("Polo", "Polo", ("uniqlo",), spec="Piqué cotton"),
    Route("Chinos", "Chinos", ("uniqlo",)),
    Route("Jeans", "Jeans", ("uniqlo",)),
    Route("Overshirt", "Overshirt", ("uniqlo",)),
    Route("Jumper", "Knitwear", ("marks", "uniqlo")),

    Route("Smart trainers", "Trainers", ("vinted",), grade="Smart", condition=VINTED_NWT,
          note="New with tags only. A worn sole has already taken someone else's gait."),
    Route("Branded trainers", "Trainers", ("adidas", "newbalance", "nike"),
          grade="Branded", timing=ON_SALE,
          note="Check the outlet section before the sale section."),

    Route("Suit", "Suit", ("marks",), timing="then have it altered",
          note="Off the peg for the cloth, a tailor for the fit. The alteration is "
               "what makes it look like a suit rather than a costume."),
)

BY_GARMENT: dict[str, list[Route]] = {}
for _route in ROUTES:
    BY_GARMENT.setdefault(_route.garment, []).append(_route)


def route_for(item) -> Route | None:
    """The route this garment follows, or None if the plan does not cover it.

    The most constrained matching route wins. A dress shirt satisfies both the
    dress route and the type's default, and the dress route states more, so it
    takes it.
    """
    matching = [r for r in BY_GARMENT.get(item.garment, []) if r.matches(item)]
    if not matching:
        return None
    return max(matching, key=lambda r: r.precision)


def why(item, route: Route) -> str:
    """Which constraints put this garment on this route. Shown on the page, so
    the choice can be argued with rather than trusted."""
    if not route.constraints:
        return f"the default for {item.garment.lower()}"
    return ", ".join(f"{axis.lower()} {value}" for axis, value in route.constraints.items())


def covered() -> set[str]:
    return set(BY_GARMENT)


def uncovered(garments) -> list[str]:
    """Garment types with no route at all, so the gaps stay visible."""
    return [g for g in garments if g not in BY_GARMENT]


def plan() -> list[Route]:
    """The whole list, grouped the way he wrote it."""
    return list(ROUTES)
