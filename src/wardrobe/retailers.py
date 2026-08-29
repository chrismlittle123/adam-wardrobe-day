"""Where to actually buy each thing, and how not to pay retail for it.

The strategy has one governing idea: **the garments worn least get looked for
secondhand first**. A blazer worn twenty times a year spends most of its life in
a wardrobe whether it was bought new or not, so the secondhand market is full of
them barely worn, and paying retail for one is paying for the packaging.

This used to be a price threshold, and prices were the wrong handle. Almost
everything worth buying comes off a listing where the price is unknown until the
thing appears, so a rule keyed to money ranked on invented numbers. The property
that actually predicts a good secondhand buy is how often the garment is worn,
and that is knowable from the garment alone.

The other direction still holds: a tee is worn twice a week and wears out, so it
comes new from whoever cuts it well.

Nothing here places an order. It ranks the sensible places to look, explains
why, and builds the search link. The alerts are described but deliberately not
wired up: the point is to know exactly what you are waiting for before you start
waiting for it.
"""

from __future__ import annotations

import re
import tomllib
import urllib.parse
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

from . import paths

# Worn rarely, kept for years, so the secondhand market is full of them in
# near-new condition. These go to the resale sites before anywhere else.
RARELY_WORN: frozenset[str] = frozenset({
    "Blazer", "Overcoat", "Waistcoat", "Derbies", "Boots", "Jacket", "Suit",
    "Loafers", "Watch",
})

# Worn constantly and worn out, so a used one has little life left in it.
WORN_OUT: frozenset[str] = frozenset({
    "T-shirt", "Socks", "Jeans", "Sweatshirt", "Polo",
})

HIGH_STREET, ONLINE, TAILORING, SHOES, SECONDHAND, OFF_PRICE = (
    "High street", "Online", "Tailoring", "Shoes", "Secondhand", "Off-price",
)


@dataclass
class Retailer:
    id: str = ""
    name: str = ""
    kind: str = ""
    strengths: list[str] = field(default_factory=list)
    price_low: float = 0      # what a middling piece there tends to cost
    price_high: float = 0
    search: str = ""          # URL template, {q} is the escaped query
    note: str = ""

    def url(self, query: str) -> str:
        return self.search.format(q=urllib.parse.quote_plus(query))




TOPS = ("Shirt", "T-shirt", "Polo", "Knitwear", "Sweatshirt", "Overshirt",
        "Waistcoat")
BOTTOMS = ("Trousers", "Chinos", "Jeans", "Shorts")
OUTER = ("Blazer", "Jacket", "Overcoat", "Overshirt", "Gilet", "Suit")
FOOTWEAR = ("Loafers", "Derbies", "Boots", "Trainers", "Sandals")
ACCESSORIES = ("Belt", "Bag", "Scarf", "Hat", "Socks", "Sunglasses", "Watch", "Jewellery")
EVERYTHING = TOPS + BOTTOMS + OUTER + FOOTWEAR + ACCESSORIES

# Six shops, because six he actually uses beats forty he does not. A plan that
# names a shop he has never walked into is a plan he cannot follow, and the
# whole point of knowing his size somewhere is that it is somewhere he goes.
DEFAULT_RETAILERS: tuple[Retailer, ...] = (
    Retailer("vinted", "Vinted", SECONDHAND, EVERYTHING, 5, 400,
             "https://www.vinted.co.uk/catalog?search_text={q}",
             "Everything worn seldom and kept for years: blazers, coats, dress "
             "shoes, boots. Filter by size and brand, then save the search so it "
             "tells you when one lands."),
    Retailer("uniqlo", "Uniqlo", HIGH_STREET,
             TOPS + BOTTOMS + ("Gilet", "Jacket"), 15, 100,
             "https://www.uniqlo.com/uk/en/search?q={q}",
             "The baseline for plain things: tees, polos, chinos, jeans, "
             "overshirts, knitwear. Sizing is consistent across the range, which "
             "is why it is the shop to know your size in first."),
    Retailer("marks", "Marks and Spencer", HIGH_STREET,
             TOPS + BOTTOMS + OUTER + ("Trainers", "Belt", "Socks"), 20, 200,
             "https://www.marksandspencer.com/search?q={q}",
             "Jackets in numbered chest sizes, 36, 38, 40, which is the reference "
             "worth using. Also knitwear, wool trousers and a suit to alter."),
    Retailer("mango", "Mango", HIGH_STREET, TOPS + BOTTOMS + OUTER, 25, 180,
             "https://shop.mango.com/gb/en/search?q={q}",
             "Linen shirts and linen trousers, alpha sized. Warm neutrals and "
             "relaxed tailoring. Wait for the sale; it is reliable."),
    Retailer("next", "Next", HIGH_STREET,
             TOPS + BOTTOMS + OUTER + FOOTWEAR, 15, 120,
             "https://www.next.co.uk/search?w={q}",
             "Wide sizing and fast delivery. Heavyweight tees if you read the "
             "composition. Quality is a lottery, so check the fabric."),
    Retailer("tyrwhitt", "Charles Tyrwhitt", TAILORING,
             ("Shirt", "Blazer", "Trousers"), 30, 200,
             "https://www.charlestyrwhitt.com/uk/search?q={q}",
             "Shirts by collar and sleeve, which is the only sane way to buy one "
             "and the reason the fit can be exact. Wait for the sale."),
)

# Order to try the secondhand sites in, where there is more than one.
SECONDHAND_ORDER: dict[str, int] = {"vinted": 12}

KINDS: tuple[str, ...] = tuple(sorted(
    (SECONDHAND, HIGH_STREET, ONLINE, TAILORING, SHOES, OFF_PRICE)))


@dataclass
class Catalogue:
    """The shops, as editable data.

    Defaults ship with the app so nothing has to be typed before the plan works,
    and the first edit persists the lot. A route pointing at a shop that has been
    deleted simply drops it rather than breaking, which is why every lookup goes
    through here rather than through a module-level dict.
    """

    retailers: list[Retailer] = field(default_factory=list)
    path: Path = field(default_factory=paths.retailers)

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Catalogue":
        path = Path(path) if path else paths.retailers()
        book = cls(retailers=[], path=path)
        if not path.is_file():
            source = [Retailer(**asdict(r)) for r in DEFAULT_RETAILERS]
        else:
            allowed = {f.name for f in fields(Retailer)}
            source = [Retailer(**{k: v for k, v in row.items() if k in allowed})
                      for row in tomllib.loads(path.read_text()).get("retailers", [])]
        for retailer in source:
            retailer.strengths = list(retailer.strengths)
            book.add(retailer)
        return book

    def save(self) -> Path:
        self.path.write_text(tomli_w.dumps(
            {"retailers": [asdict(r) for r in self.retailers]}))
        return self.path

    def by_id(self, retailer_id: str) -> Retailer | None:
        return next((r for r in self.retailers if r.id == retailer_id), None)

    def add(self, retailer: Retailer) -> Retailer:
        retailer.id = retailer.id or self.unique_id(retailer.name)
        self.retailers.append(retailer)
        return retailer

    def remove(self, retailer_id: str) -> None:
        self.retailers = [r for r in self.retailers if r.id != retailer_id]

    def unique_id(self, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "", (name or "shop").lower())[:24] or "shop"
        taken = {r.id for r in self.retailers}
        if base not in taken:
            return base
        n = 2
        while f"{base}{n}" in taken:
            n += 1
        return f"{base}{n}"

    def ids(self) -> list[str]:
        return [r.id for r in self.retailers]

    def lookup(self) -> dict[str, Retailer]:
        return {r.id: r for r in self.retailers}

    def by_kind(self) -> dict[str, list[Retailer]]:
        out: dict[str, list[Retailer]] = {}
        for retailer in self.retailers:
            out.setdefault(retailer.kind, []).append(retailer)
        return {k: sorted(out[k], key=lambda r: r.name) for k in KINDS if k in out}

    def sells(self, garment: str) -> list[Retailer]:
        return [r for r in self.retailers if garment in r.strengths]

    def restore_defaults(self) -> "Catalogue":
        self.retailers = []
        for retailer in DEFAULT_RETAILERS:
            fresh = Retailer(**asdict(retailer))
            fresh.strengths = list(fresh.strengths)
            self.add(fresh)
        self.save()
        return self


@dataclass
class Suggestion:
    retailer: Retailer
    score: int
    reason: str
    query: str

    @property
    def url(self) -> str:
        return self.retailer.url(self.query)


def match_url(url: str, catalogue: "Catalogue | None" = None) -> Retailer | None:
    """Which shop a link points at, by its domain.

    Paste a Uniqlo link and the page can say Uniqlo rather than making him read
    the URL. Matched against the search templates already in the catalogue, so a
    shop he adds is recognised without a second list to maintain.
    """
    if "//" not in url:
        return None
    host = url.split("//", 1)[1].split("/", 1)[0].lower()
    host = host[4:] if host.startswith("www.") else host
    book = catalogue if catalogue is not None else Catalogue.load()
    for retailer in book.retailers:
        if "//" not in retailer.search:
            continue
        theirs = retailer.search.split("//", 1)[1].split("/", 1)[0].lower()
        theirs = theirs[4:] if theirs.startswith("www.") else theirs
        if host == theirs or host.endswith("." + theirs) or theirs.endswith("." + host):
            return retailer
    return None


def query_for(item) -> str:
    """The search string. Colour and fabric first, because that is how the
    listings are actually titled."""
    bits = [b for b in (item.colour, item.fabric, item.garment) if b]
    return " ".join(dict.fromkeys(w for b in bits for w in b.split()))


def suggest(item, *, limit: int = 8, catalogue: Catalogue | None = None) -> list[Suggestion]:
    """Rank the places worth looking, best first, each with its reason.

    This is the fallback for when the sourcing plan has no line for a garment.
    Where a plan exists it wins, because it is a decision and this is a guess.
    """
    rare = item.garment in RARELY_WORN
    consumable = item.garment in WORN_OUT
    query = query_for(item)

    book = catalogue if catalogue is not None else Catalogue.load()
    out: list[Suggestion] = []
    for retailer in book.retailers:
        if item.garment not in retailer.strengths:
            continue
        score = 50
        reasons: list[str] = []
        garment = item.garment.lower()

        if retailer.kind == SECONDHAND:
            if rare:
                score += 40
                reasons.append(f"{_article(garment)} {garment} is worn seldom and kept for "
                               "years, which is exactly what fills this site")
            elif consumable:
                score -= 25
                reasons.append(f"{_article(garment)} {garment} gets worn out, so a used "
                               "one has little life left in it")
            else:
                score += 5
                reasons.append("worth a look before paying retail")
        else:
            if rare:
                score -= 15
                reasons.append("retail, for something worn a handful of times a year")
            elif consumable:
                score += 15
                reasons.append("bought new and replaced when it goes")

        score += SECONDHAND_ORDER.get(retailer.id, 0)
        if item.garment in retailer.strengths[:6]:
            score += 8
        out.append(Suggestion(retailer, score, "; ".join(reasons), query))

    # Scored raw, then normalised against the best. Capping at 100 first would
    # flatten the top three into a tie and lose the order that matters most.
    out.sort(key=lambda s: (-s.score, s.retailer.name))
    if out:
        best = max(s.score for s in out) or 1
        for suggestion in out:
            suggestion.score = max(0, round(100 * suggestion.score / best))
    return out[:limit]


@dataclass
class Tactic:
    name: str
    detail: str
    where: str = ""


# When each thing is discounted. Buying a coat in October is paying for the
# weather; buying it in February is paying for the coat.
SEASON: dict[str, str] = {
    "Overcoat": "January and February, once the cold is nearly over",
    "Blazer": "late January, or July before the autumn stock lands",
    "Jacket": "late January or late July",
    "Trousers": "January and July, the two clearance windows",
    "Chinos": "January and July",
    "Shorts": "late August, for next summer",
    "Overshirt": "late August",
    "Knitwear": "late February, after the winter has been cleared",
    "Boots": "February",
    "Loafers": "August, after the summer run",
    "Derbies": "February",
    "Trainers": "any time; they are never really discounted",
}


def tactics(item) -> list[Tactic]:
    """How to get this particular thing without paying retail."""
    query = query_for(item)
    sizes = item.size_line()
    out: list[Tactic] = []

    if item.garment in RARELY_WORN:
        out.append(Tactic(
            "Save the Vinted search",
            f"Search “{query}”, filter to your size"
            f"{f' ({sizes})' if sizes else ''}, then save it. Vinted notifies you when "
            "something matching lands, which turns waiting into a background task.",
            "Vinted"))
    out.append(Tactic(
        "Wishlist it, do not buy it",
        "Every high-street site emails a wishlisted item when it is reduced. Add it, "
        "close the tab, and let the discount come to you.",
        "H&M, Zara, Mango, COS, Arket, Massimo Dutti"))
    if item.garment in SEASON:
        out.append(Tactic(
            "Buy it out of season",
            f"A {item.garment.lower()} is cheapest in {SEASON[item.garment]}. "
            "Buying one in the week you need it is the most expensive way to own it.",
            ""))
    if sizes:
        out.append(Tactic(
            "Be specific, or the alerts are noise",
            f"You already know the size: {sizes}. An alert without a size fires "
            "constantly and gets muted within a week.",
            ""))
    out.append(Tactic(
        "Decide what it is worth before you look",
        "Write down what you would pay for this, now, while nothing is in front of "
        "you. A number decided in advance is what stops a listing at midnight from "
        "becoming a decision.",
        ""))
    return out


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"



