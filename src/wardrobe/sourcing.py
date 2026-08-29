"""His actual sourcing plan: which shop, for which garment, on what terms.

This is the difference between a ranking and a decision. `retailers.suggest`
works out where a garment of this type at this price could sensibly come from;
this file records where he has already decided it comes from, and why.

A route is finer-grained than a garment type, which is the whole difficulty. A
heavyweight tee and a plain tee are both "T-shirt" and come from different
shops; a dress shirt and a linen shirt are both "Shirt". So a route carries
keywords, and the most specific match wins. Where a garment has one route with
no keywords, that route is simply the default for the type.

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
    match: tuple[str, ...] = ()      # keywords that pick this over the default
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
    def terms(self) -> str:
        """Condition, timing and specification as one readable clause."""
        return ", ".join(b for b in (self.condition, self.timing, self.spec) if b)

    @property
    def summary(self) -> str:
        return f"{self.where}{f' · {self.terms}' if self.terms else ''}"


# His plan. Order within a garment does not matter; specificity decides.
ROUTES: tuple[Route, ...] = (
    Route("Heavyweight t-shirt", "T-shirt", ("asos", "next"),
          match=("heavy", "heavyweight", "gsm", "thick", "boxy"),
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

    Route("Dress shirt", "Shirt", ("tyrwhitt",),
          match=("dress", "poplin", "oxford", "formal", "business", "twill"),
          timing=ON_SALE,
          note="Sized by collar and sleeve, which is the only sane way to buy one."),
    Route("Linen shirt", "Shirt", ("mango",), match=("linen",), timing=ON_SALE),
    Route("Linen trousers", "Trousers", ("mango",), match=("linen",), timing=ON_SALE),
    Route("Knitted polo", "Polo", ("mango",),
          match=("knit", "knitted", "merino", "wool"), timing=ON_SALE),

    Route("Polo", "Polo", ("uniqlo",), spec="Piqué cotton"),
    Route("Chinos", "Chinos", ("uniqlo",)),
    Route("Jeans", "Jeans", ("uniqlo",)),
    Route("Overshirt", "Overshirt", ("uniqlo",)),
    Route("Jumper", "Knitwear", ("marks", "uniqlo")),

    Route("Smart trainers", "Trainers", ("vinted",), condition=VINTED_NWT,
          match=("smart", "leather", "white", "minimal", "plain"),
          note="New with tags only. A worn sole has already taken someone else's gait."),
    Route("Branded trainers", "Trainers", ("adidas", "newbalance", "nike"),
          match=("adidas", "nike", "new balance", "samba", "gazelle", "branded", "suede"),
          timing=ON_SALE,
          note="Check the outlet section before the sale section."),

    Route("Suit", "Suit", ("marks",), timing="then have it altered",
          note="Off the peg for the cloth, a tailor for the fit. The alteration is "
               "what makes it look like a suit rather than a costume."),
)

BY_GARMENT: dict[str, list[Route]] = {}
for _route in ROUTES:
    BY_GARMENT.setdefault(_route.garment, []).append(_route)


def route_for(item) -> Route | None:
    """The route this specific garment follows.

    Keyword matches beat the garment's default, and the default beats a keyword
    route whose keywords are absent. So a "linen shirt" goes to Mango, a "white
    oxford" to Tyrwhitt, and a shirt described as neither still lands somewhere.
    """
    candidates = BY_GARMENT.get(item.garment)
    if not candidates:
        return None
    haystack = " ".join(
        str(x) for x in (item.name, item.fabric, item.description, item.colour)
    ).lower()

    def score(route: Route) -> int:
        if not route.match:
            return 1                                    # the default for the type
        hits = sum(1 for keyword in route.match if keyword in haystack)
        return 2 + hits if hits else 0                  # matched, or ruled out

    ranked = sorted(candidates, key=score, reverse=True)
    return ranked[0] if score(ranked[0]) else None


def covered() -> set[str]:
    return set(BY_GARMENT)


def uncovered(garments) -> list[str]:
    """Garment types with no route at all, so the gaps stay visible."""
    return [g for g in garments if g not in BY_GARMENT]


def plan() -> list[Route]:
    """The whole list, grouped the way he wrote it."""
    return list(ROUTES)
