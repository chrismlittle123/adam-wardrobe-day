"""Where to actually buy each thing, and how not to pay retail for it.

The strategy has one governing idea: **anything over about £70 new gets looked
for secondhand first**. Not out of thrift for its own sake, but because the
garments that cost that much are usually the ones worn least, and a blazer worn
twenty times a year spends most of its life in a wardrobe whether it was bought
new or not. Vinted is full of them, barely worn, at a third of the price.

Below that line the calculation flips. A £25 t-shirt secondhand saves eight
pounds and costs a week of waiting, so it is bought new from whoever cuts that
garment well.

Nothing here places an order. It ranks the sensible places to look, explains
why, and builds the search link. The alerts are described but deliberately not
wired up: the point is to know exactly what you are waiting for before you start
waiting for it.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass, field

# Above this, look secondhand before paying retail.
SECONDHAND_THRESHOLD = 70.0

# Garments that are expensive per wear: worn rarely, kept for years, and so the
# secondhand market is full of them in near-new condition.
RARELY_WORN: frozenset[str] = frozenset({
    "Blazer", "Overcoat", "Waistcoat", "Derbies", "Boots", "Jacket",
})

HIGH_STREET, ONLINE, TAILORING, SHOES, SECONDHAND, OFF_PRICE = (
    "High street", "Online", "Tailoring", "Shoes", "Secondhand", "Off-price",
)


@dataclass(frozen=True)
class Retailer:
    id: str
    name: str
    kind: str
    strengths: tuple[str, ...]
    price_low: float          # what a middling piece there tends to cost
    price_high: float
    search: str               # URL template, {q} is the escaped query
    note: str = ""

    def url(self, query: str) -> str:
        return self.search.format(q=urllib.parse.quote_plus(query))

    def covers(self, price: float) -> bool:
        return self.price_low <= price <= self.price_high if price else True


TOPS = ("Shirt", "T-shirt", "Polo", "Knitwear", "Sweatshirt", "Overshirt")
BOTTOMS = ("Trousers", "Chinos", "Jeans", "Shorts")
OUTER = ("Blazer", "Jacket", "Overcoat", "Overshirt", "Gilet")
FOOTWEAR = ("Loafers", "Derbies", "Boots", "Trainers", "Sandals")
ACCESSORIES = ("Belt", "Bag", "Scarf", "Hat", "Socks", "Sunglasses", "Watch", "Jewellery")
EVERYTHING = TOPS + BOTTOMS + OUTER + FOOTWEAR + ACCESSORIES

RETAILERS: tuple[Retailer, ...] = (
    # Secondhand first, because that is the order the strategy uses.
    Retailer("vinted", "Vinted", SECONDHAND, EVERYTHING, 5, 400,
             "https://www.vinted.co.uk/catalog?search_text={q}",
             "Best for anything expensive and rarely worn. Filter by size and brand, "
             "then save the search so it tells you when one lands."),
    Retailer("ebay", "eBay", SECONDHAND, EVERYTHING, 5, 600,
             "https://www.ebay.co.uk/sch/i.html?_nkw={q}",
             "Deeper than Vinted for shoes and tailoring. Sort by ending soonest."),
    Retailer("depop", "Depop", SECONDHAND, TOPS + BOTTOMS + ("Jacket", "Overshirt", "Gilet"), 10, 250,
             "https://www.depop.com/search/?q={q}",
             "Younger stock, better for casual pieces than tailoring."),
    Retailer("vestiaire", "Vestiaire Collective", SECONDHAND, OUTER + FOOTWEAR, 60, 900,
             "https://www.vestiairecollective.com/search/?q={q}",
             "Authenticated, so worth it only above roughly £150."),

    Retailer("uniqlo", "Uniqlo", HIGH_STREET, TOPS + BOTTOMS + ("Gilet",), 15, 100,
             "https://www.uniqlo.com/uk/en/search?q={q}",
             "Unbeatable on plain basics and merino. Cuts run slim and short."),
    Retailer("zara", "Zara", HIGH_STREET, TOPS + BOTTOMS + OUTER + FOOTWEAR, 20, 160,
             "https://www.zara.com/uk/en/search?searchTerm={q}",
             "Strong silhouettes, inconsistent cloth. Try before committing."),
    Retailer("hm", "H&M", HIGH_STREET, TOPS + BOTTOMS + OUTER, 10, 90,
             "https://www2.hm.com/en_gb/search-results.html?q={q}",
             "Cheap, and the linen is better than it has any right to be."),
    Retailer("mango", "Mango", HIGH_STREET, TOPS + BOTTOMS + OUTER, 25, 180,
             "https://shop.mango.com/gb/en/search?q={q}",
             "The best of the high street for relaxed tailoring and warm neutrals."),
    Retailer("cos", "COS", HIGH_STREET, TOPS + BOTTOMS + OUTER, 45, 250,
             "https://www.cos.com/en_gbp/search.html?q={q}",
             "Clean shapes, good cloth. Wait for the sale, it is reliable."),
    Retailer("arket", "Arket", HIGH_STREET, TOPS + BOTTOMS + OUTER, 35, 220,
             "https://www.arket.com/en_gbp/search.html?q={q}",
             "Quiet colours and honest fabrics. Overlaps COS, softer cuts."),
    Retailer("massimo", "Massimo Dutti", HIGH_STREET, TOPS + BOTTOMS + OUTER + FOOTWEAR, 40, 300,
             "https://www.massimodutti.com/gb/search?searchTerm={q}",
             "Italian-leaning tailoring at high-street prices in the sale."),
    Retailer("next", "Next", HIGH_STREET, TOPS + BOTTOMS + OUTER + FOOTWEAR, 15, 120,
             "https://www.next.co.uk/search?w={q}",
             "Wide sizing and fast delivery. Quality is a lottery, so read the composition."),
    Retailer("marks", "Marks & Spencer", HIGH_STREET, TOPS + BOTTOMS + OUTER, 20, 150,
             "https://www.marksandspencer.com/search?q={q}",
             "Better than its reputation for knitwear and chinos."),

    Retailer("moss", "Moss", TAILORING, ("Blazer", "Waistcoat", "Trousers", "Shirt"), 60, 350,
             "https://www.moss.co.uk/search?q={q}",
             "Hire and buy. The sale rail is where the value is."),
    Retailer("suitsupply", "Suitsupply", TAILORING, ("Blazer", "Trousers", "Waistcoat", "Overcoat"),
             150, 600, "https://suitsupply.com/en-gb/search?q={q}",
             "Proper construction and free alterations. Worth it once, for one jacket."),
    Retailer("tyrwhitt", "Charles Tyrwhitt", TAILORING, ("Shirt", "Blazer", "Trousers"), 30, 200,
             "https://www.charlestyrwhitt.com/uk/search?q={q}",
             "Shirts by collar and sleeve, which is the only sane way to buy one."),

    Retailer("clarks", "Clarks", SHOES, FOOTWEAR, 50, 180,
             "https://www.clarks.co.uk/c/search?q={q}",
             "Wide fittings as standard. Desert boots are the obvious buy."),
    Retailer("base", "Base London", SHOES, ("Loafers", "Derbies", "Boots"), 45, 130,
             "https://www.baselondon.com/search?q={q}",
             "Cheap leather loafers and brogues. Fine for a season or three."),
    Retailer("loake", "Loake", SHOES, ("Loafers", "Derbies", "Boots"), 130, 400,
             "https://www.loake.co.uk/search?q={q}",
             "Goodyear welted, so resoleable. Buy once, secondhand if you can."),
    Retailer("grenson", "Grenson", SHOES, ("Loafers", "Derbies", "Boots"), 150, 450,
             "https://www.grenson.com/uk/catalogsearch/result/?q={q}",
             "Chunkier last than Loake. Very common on Vinted."),
    Retailer("solovair", "Solovair", SHOES, ("Boots", "Derbies"), 130, 250,
             "https://www.nps-solovair.com/search?q={q}",
             "The original Doc Martens factory. Built to be resoled."),

    Retailer("percival", "Percival", ONLINE, TOPS + BOTTOMS + OUTER, 60, 300,
             "https://percivalclo.com/search?q={q}",
             "London-made-ish, playful knits and camp collars."),
    Retailer("universal", "Universal Works", ONLINE, TOPS + BOTTOMS + OUTER, 70, 350,
             "https://www.universalworks.co.uk/search?q={q}",
             "Relaxed workwear tailoring. Exactly the unstructured shape to aim at."),
    Retailer("oliver", "Oliver Spencer", ONLINE, TOPS + BOTTOMS + OUTER, 90, 450,
             "https://oliverspencer.co.uk/search?q={q}",
             "Soft shoulders and good cloth. Sale twice a year, wait for it."),
    Retailer("community", "Community Clothing", ONLINE, TOPS + BOTTOMS + OUTER, 30, 200,
             "https://communityclothing.co.uk/search?q={q}",
             "UK factories, no marketing budget, honest prices. Plain by design."),
    Retailer("sunspel", "Sunspel", ONLINE, ("T-shirt", "Polo", "Knitwear"), 60, 250,
             "https://www.sunspel.com/uk/search?q={q}",
             "The t-shirt worth paying for, once, in the sale."),
    Retailer("carhartt", "Carhartt WIP", ONLINE, TOPS + BOTTOMS + ("Jacket", "Overshirt"), 40, 200,
             "https://www.carhartt-wip.com/en/search?q={q}",
             "Workwear cuts that hold their shape and their resale value."),
    Retailer("levis", "Levi's", ONLINE, ("Jeans", "Jacket", "Shorts"), 50, 140,
             "https://www.levi.com/GB/en_GB/search?q={q}",
             "For denim, start here and work outwards."),
    Retailer("end", "End Clothing", ONLINE, EVERYTHING, 50, 800,
             "https://www.endclothing.com/gb/search?q={q}",
             "Aggregates a lot of brands. The sale section is the reason to visit."),

    Retailer("acetate", "Ace & Tate", ONLINE, ("Sunglasses",), 60, 180,
             "https://www.aceandtate.com/uk/search?q={q}",
             "Own-brand frames at one price. Home try-on before committing."),
    Retailer("cubitts", "Cubitts", ONLINE, ("Sunglasses",), 125, 350,
             "https://www.cubitts.com/search?q={q}",
             "London-made, and they will reglaze a secondhand frame for you."),
    Retailer("sunglasshut", "Sunglass Hut", HIGH_STREET, ("Sunglasses",), 90, 300,
             "https://www.sunglasshut.com/uk/search?q={q}",
             "The big brands under one roof. Almost never discounted."),
    Retailer("christopherward", "Christopher Ward", ONLINE, ("Watch",), 400, 2000,
             "https://www.christopherward.com/search?q={q}",
             "Swiss movements without the marketing markup."),
    Retailer("watchfinder", "Watchfinder", SECONDHAND, ("Watch",), 250, 5000,
             "https://www.watchfinder.co.uk/search?q={q}",
             "Serviced and warrantied pre-owned. The sane way to buy a good watch."),
    Retailer("timex", "Timex", ONLINE, ("Watch",), 70, 300,
             "https://www.timex.co.uk/search?q={q}",
             "Where a good-looking watch costs less than a jacket."),

    Retailer("tkmaxx", "TK Maxx", OFF_PRICE, EVERYTHING, 15, 200,
             "https://www.tkmaxx.com/uk/en/search?q={q}",
             "A lottery, but the only place good tailoring turns up at high-street money."),
)

# Order to try the secondhand sites in. Vinted leads because it is by far the
# deepest in ordinary menswear; Vestiaire is authenticated and only earns its
# margin on genuinely expensive things.
SECONDHAND_ORDER: dict[str, int] = {
    "vinted": 12, "ebay": 8, "watchfinder": 6, "vestiaire": 3, "depop": 2,
}

BY_ID: dict[str, Retailer] = {r.id: r for r in RETAILERS}
KINDS: tuple[str, ...] = (SECONDHAND, HIGH_STREET, ONLINE, TAILORING, SHOES, OFF_PRICE)


@dataclass
class Suggestion:
    retailer: Retailer
    score: int
    reason: str
    query: str

    @property
    def url(self) -> str:
        return self.retailer.url(self.query)


def query_for(item) -> str:
    """The search string. Colour and fabric first, because that is how the
    listings are actually titled."""
    bits = [b for b in (item.colour, item.fabric, item.garment) if b]
    return " ".join(dict.fromkeys(w for b in bits for w in b.split()))


def suggest(item, *, limit: int = 8) -> list[Suggestion]:
    """Rank the places worth looking, best first, each with its reason."""
    price = float(item.price or 0)
    dear = price >= SECONDHAND_THRESHOLD
    rare = item.garment in RARELY_WORN
    query = query_for(item)

    out: list[Suggestion] = []
    for retailer in RETAILERS:
        if item.garment not in retailer.strengths:
            continue
        score = 50
        reasons: list[str] = []

        if retailer.kind == SECONDHAND:
            if rare and dear:
                score += 45
                garment = item.garment.lower()
                reasons.append(f"{_article(garment)} {garment} at {_money(price)} is worn rarely "
                               "and kept for years, which is exactly what fills this site")
            elif dear:
                score += 30
                reasons.append(f"over £{SECONDHAND_THRESHOLD:.0f} new, so look here first")
            else:
                score -= 20
                reasons.append("cheap enough new that the wait is not worth it")
        else:
            if dear:
                score -= 12
                reasons.append("full price on something worn seldom")
            if retailer.covers(price):
                score += 18
                reasons.append(f"sits in your {_money(price)} band")
            else:
                score -= 10
                reasons.append(f"typically {_money(retailer.price_low)}"
                               f" to {_money(retailer.price_high)}")

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
    price = float(item.price or 0)
    query = query_for(item)
    sizes = item.size_line()
    out: list[Tactic] = []

    if price >= SECONDHAND_THRESHOLD:
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
        "Set a walk-away price",
        f"Decide now what this is worth to you. "
        f"{_money(price * 0.6) if price else 'Roughly 60% of retail'} is a realistic "
        "secondhand target, and having the number written down is what stops a sale "
        "email turning into an impulse.",
        ""))
    return out


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def _money(amount: float) -> str:
    return f"£{amount:,.0f}" if amount == round(amount) else f"£{amount:,.2f}"
