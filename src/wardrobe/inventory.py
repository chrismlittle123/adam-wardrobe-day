"""Every garment, owned or merely wanted, in one list.

The important decision: owned and aspirational items are the same kind of
object, separated only by `status`. An outfit is a set of item ids and does not
care which is which. That is what makes the shopping maths work: a loved outfit
is blocked by exactly the items in it that are not owned, so "what should I buy"
becomes a coverage problem over blocked outfits rather than a matter of opinion.

Photos exist for the pieces that words cannot pin down. A prompt saying "green
jacket" produces a different jacket every time; the photograph produces that one.
"""

from __future__ import annotations

import io
import re
import shutil
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w
from PIL import Image, UnidentifiedImageError

from . import paths

OWNED, ASPIRATIONAL, RETIRED = "owned", "aspirational", "retired"
STATUSES: tuple[str, ...] = (OWNED, ASPIRATIONAL, RETIRED)

# Category drives the outfit slots. Only one item per slot, except accessories.
# Both the categories and the garments inside them are alphabetical, because the
# dropdown is scanned by eye and no other order is defensible.
CATEGORIES: dict[str, tuple[str, ...]] = {
    "Accessory": ("Bag", "Belt", "Hat", "Jewellery", "Scarf", "Socks", "Sunglasses", "Watch"),
    "Bottom": ("Chinos", "Jeans", "Shorts", "Trousers"),
    "Outerwear": ("Blazer", "Gilet", "Jacket", "Overcoat", "Overshirt", "Suit"),
    "Shoes": ("Boots", "Derbies", "Loafers", "Sandals", "Trainers"),
    "Top": ("Knitwear", "Polo", "Shirt", "Sweatshirt", "T-shirt", "Waistcoat"),
}
GARMENTS: tuple[str, ...] = tuple(sorted({g for group in CATEGORIES.values() for g in group}))
SINGLE_SLOT: tuple[str, ...] = ("Top", "Bottom", "Outerwear", "Shoes")


# --- sizing -------------------------------------------------------------------

# A shirt is sized by the collar, a jacket by the chest and a length letter, a
# trouser by waist and leg, a shoe by three competing national systems that do
# not agree with each other. One shared set of boxes would be wrong for all of
# them, so each garment declares its own.

@dataclass(frozen=True)
class SizeField:
    key: str
    label: str
    options: tuple[str, ...] = ()   # empty means a free text box
    help: str = ""


def _range(start: float, stop: float, step: float, suffix: str = "") -> tuple[str, ...]:
    out, value = [], start
    while value <= stop + 1e-9:
        out.append(f"{value:g}{suffix}")
        value += step
    return tuple(out)


NONE = "—"
ALPHA = (NONE, "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL")
CUT = (NONE, "Slim", "Regular", "Relaxed", "Oversized")

_alpha = SizeField("alpha", "Size", ALPHA)
_cut = SizeField("cut", "Cut", CUT, "How the maker describes it, not how it fits you.")
_collar = SizeField("collar", "Collar", (NONE, *_range(13.5, 18.5, 0.5, '"')),
                    "Neck measurement on the label. The number that matters on a shirt.")
_sleeve = SizeField("sleeve", "Sleeve", (NONE, *_range(31, 37, 1, '"')),
                    "Dress shirts only. Casual shirts rarely quote it.")
_chest = SizeField("chest", "Chest", (NONE, *_range(34, 48, 2, '"')),
                   "UK and US jackets are sized by chest in inches.")
_jkt_len = SizeField("length", "Length", (NONE, "Short", "Regular", "Long"),
                     "38S, 38R and 38L share a chest and differ in body and sleeve length.")
_eu_jkt = SizeField("eu", "EU", (NONE, *_range(42, 62, 2)),
                    "Italian and French jackets. Roughly the chest in inches plus 10.")
_waist = SizeField("waist", "Waist", (NONE, *_range(26, 44, 1, '"')))
_leg = SizeField("leg", "Leg", (NONE, *_range(28, 38, 1, '"')),
                 "Inside leg. The half of trouser sizing shops most often ignore.")
_uk_shoe = SizeField("uk", "UK", (NONE, *_range(5, 14, 0.5)))
_eu_shoe = SizeField("eu", "EU", (NONE, *_range(38, 49, 0.5)))
_us_shoe = SizeField("us", "US", (NONE, *_range(6, 15, 0.5)))
_width = SizeField("width", "Width", (NONE, "Narrow", "Standard", "Wide", "D", "E", "F", "G"))

SHOE_SCHEME = (_uk_shoe, _eu_shoe, _us_shoe, _width)
JACKET_SCHEME = (_chest, _jkt_len, _eu_jkt, _cut)
TROUSER_SCHEME = (_waist, _leg, _cut)
TOP_SCHEME = (_alpha, _cut)
DEFAULT_SCHEME = (SizeField("size", "Size", (), "However this one happens to be sized."),)

SIZE_SCHEMES: dict[str, tuple[SizeField, ...]] = {
    "Bag": (), "Jewellery": (), "Scarf": (), "Sunglasses": (),
    "Watch": (SizeField("case", "Case", (NONE, *_range(34, 46, 1, "mm"))),),
    "Belt": (SizeField("waist", "Waist", (NONE, *_range(26, 44, 1, '"'))), _alpha),
    "Hat": (SizeField("hat", "Size", (NONE, "S/M", "L/XL", *_range(54, 62, 1, "cm"))),),
    "Socks": (SizeField("socks", "Size", (NONE, "UK 6-8", "UK 8-11", "UK 11-14")),),
    "Blazer": JACKET_SCHEME, "Overcoat": JACKET_SCHEME, "Suit": JACKET_SCHEME,
    "Jacket": (_alpha, _chest, _cut), "Overshirt": TOP_SCHEME, "Gilet": (_alpha,),
    "Waistcoat": (_chest, _alpha),
    "Chinos": TROUSER_SCHEME, "Jeans": TROUSER_SCHEME, "Trousers": TROUSER_SCHEME,
    "Shorts": (_waist, _cut),
    "Boots": SHOE_SCHEME, "Derbies": SHOE_SCHEME, "Loafers": SHOE_SCHEME,
    "Sandals": SHOE_SCHEME, "Trainers": SHOE_SCHEME,
    "Knitwear": TOP_SCHEME, "Polo": TOP_SCHEME, "Sweatshirt": TOP_SCHEME, "T-shirt": TOP_SCHEME,
    "Shirt": (_collar, _alpha, _sleeve, _cut),
}


# Cloth, by family. Typing it free-hand produced "cotton", "Cotton" and "100%
# cotton" as three different fabrics, which made the inventory unsearchable and
# gave the image model three different answers for the same shirt.
FABRICS: dict[str, tuple[str, ...]] = {
    "Cotton": (
        "Chambray", "Corduroy", "Cotton canvas", "Cotton jersey", "Cotton piqué",
        "Cotton poplin", "Cotton twill", "Moleskin", "Oxford cotton", "Seersucker",
        "Terry towelling",
    ),
    "Wool": (
        "Boiled wool", "Cashmere", "Donegal tweed", "Fresco", "Harris tweed",
        "Lambswool", "Merino wool", "Mohair", "Wool flannel", "Wool hopsack",
        "Wool melton", "Worsted wool",
    ),
    "Linen and hemp": ("Hemp", "Irish linen", "Linen", "Linen-cotton", "Linen-wool"),
    "Denim": ("Raw denim", "Selvedge denim", "Washed denim"),
    "Leather": ("Calf leather", "Cordovan", "Nubuck", "Shearling", "Suede"),
    "Silk and fine": ("Cotton-silk", "Silk", "Wool-silk-linen"),
    "Technical": ("Fleece", "Nylon", "Polyester", "Ripstop", "Technical shell", "Waxed cotton"),
}

# Flat, alphabetical, with the placeholder first. The grouping above is for
# reading; the dropdown is for finding.
FABRIC_OPTIONS: tuple[str, ...] = (NONE, *sorted({f for g in FABRICS.values() for f in g}))


def fabric_family(fabric: str) -> str:
    return next((name for name, group in FABRICS.items() if fabric in group), "")


def size_scheme(garment: str) -> tuple[SizeField, ...]:
    return SIZE_SCHEMES.get(garment, DEFAULT_SCHEME)


@dataclass
class Item:
    id: str = ""
    name: str = ""
    category: str = "Top"
    garment: str = "Shirt"
    colour: str = ""
    colour_hex: str = "#CCCCCC"
    fabric: str = ""
    status: str = OWNED
    photo: str = ""
    description: str = ""
    starred: bool = False   # marked for purchase in the shopping guide
    # Written by the shopping guide: a product shot and the copy to go with it.
    product_photo: str = ""
    product_copy: str = ""
    sizes: dict[str, str] = field(default_factory=dict)
    # Only wanted pieces carry a price: it is what the shopping plan spends. What
    # an owned garment once cost is sunk and changes no decision.
    price: float = 0.0

    @property
    def owned(self) -> bool:
        return self.status == OWNED

    @property
    def label(self) -> str:
        """What the search boxes show. Colour separates near-duplicates."""
        bits = [self.name or self.garment]
        if self.colour and self.colour.lower() not in (self.name or "").lower():
            bits.append(f"({self.colour})")
        if self.status == ASPIRATIONAL:
            bits.append("· wanted")
        elif self.status == RETIRED:
            bits.append("· retired")
        return " ".join(bits)

    @property
    def has_photo(self) -> bool:
        return bool(self.photo) and Path(self.photo).is_file()

    @property
    def has_product_photo(self) -> bool:
        return bool(self.product_photo) and Path(self.product_photo).is_file()

    @property
    def shop_photo(self) -> str:
        """The generated product shot if there is one, else his own snap."""
        return (self.product_photo if self.has_product_photo
                else self.photo if self.has_photo else "")

    def describe(self) -> str:
        """One line for the image prompt. Photographs beat adjectives, but when
        there is no photograph the adjectives have to carry it."""
        bits = [b for b in (self.colour, self.fabric, self.garment.lower()) if b]
        line = " ".join(bits) or self.name
        if self.description:
            line = f"{line} ({self.description})"
        return line

    def size_line(self) -> str:
        """The sizes as one readable line, in this garment's own scheme."""
        labels = {f.key: f.label for f in size_scheme(self.garment)}
        return " · ".join(
            f"{labels.get(k, k)} {v}" for k, v in self.sizes.items()
            if v and v != NONE and k in labels
        )

    def prune_sizes(self) -> None:
        """Drop size keys that do not belong to this garment.

        Re-classify a shirt as a trouser and the collar measurement would
        otherwise sit in the file forever, invisible but not gone.
        """
        allowed = {f.key for f in size_scheme(self.garment)}
        self.sizes = {k: v for k, v in self.sizes.items()
                      if k in allowed and v and v != NONE}

    def searchable(self) -> str:
        return " ".join(
            [self.name, self.colour, self.fabric, self.garment,
             self.category, self.description, *self.sizes.values()]
        ).lower()


@dataclass
class Inventory:
    items: list[Item] = field(default_factory=list)
    path: Path = field(default_factory=paths.inventory)

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Inventory":
        path = Path(path) if path else paths.inventory()
        if not path.is_file():
            return cls(path=path)
        raw = tomllib.loads(path.read_text())
        allowed = {f.name for f in fields(Item)}
        items = [Item(**{k: v for k, v in row.items() if k in allowed}) for row in raw.get("items", [])]
        return cls(items=items, path=path)

    def save(self) -> Path:
        for item in self.items:
            item.prune_sizes()
        self.path.write_text(tomli_w.dumps({"items": [asdict(i) for i in self.items]}))
        return self.path

    # --- lookup ---------------------------------------------------------------

    def by_id(self, item_id: str) -> Item | None:
        return next((i for i in self.items if i.id == item_id), None)

    def resolve(self, ids: list[str]) -> list[Item]:
        found = [self.by_id(i) for i in ids]
        return [i for i in found if i]

    def filter(
        self,
        *,
        status: str | None = None,
        category: str | None = None,
        query: str = "",
    ) -> list[Item]:
        out = self.items
        if status:
            out = [i for i in out if i.status == status]
        if category:
            out = [i for i in out if i.category == category]
        if query.strip():
            needle = query.strip().lower()
            out = [i for i in out if needle in i.searchable()]
        return out

    def owned(self) -> list[Item]:
        return [i for i in self.items if i.status == OWNED]

    def owned_ids(self) -> set[str]:
        return {i.id for i in self.items if i.status == OWNED}

    def counts(self) -> dict[str, int]:
        return {s: sum(1 for i in self.items if i.status == s) for s in STATUSES}

    # --- mutation -------------------------------------------------------------

    def add(self, item: Item) -> Item:
        item.id = item.id or self.unique_id(item.name or item.garment)
        self.items.append(item)
        return item

    def update(self, item: Item) -> None:
        for index, existing in enumerate(self.items):
            if existing.id == item.id:
                self.items[index] = item
                return
        self.items.append(item)

    def remove(self, item_id: str) -> None:
        self.items = [i for i in self.items if i.id != item_id]

    def unique_id(self, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", (name or "item").lower()).strip("-")[:36] or "item"
        taken = {i.id for i in self.items}
        if base not in taken:
            return base
        n = 2
        while f"{base}-{n}" in taken:
            n += 1
        return f"{base}-{n}"


# Guards on uploads. The first is a decompression-bomb stop before anything is
# decoded; the second is what actually keeps the repository small, since a phone
# photograph is fifteen times larger than anything this app needs.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_EDGE_PX = 1600
JPEG_QUALITY = 88


def save_photo(item_id: str, uploaded, photo_dir: Path | None = None) -> str:
    """Store an uploaded photo, downscaled. Returns the stored path.

    Everything is re-encoded to JPEG at a bounded size rather than written
    through. A garment reference only needs to be recognisable, and writing a
    12 MB original straight to disk puts it in the repository forever.
    """
    photo_dir = Path(photo_dir) if photo_dir else paths.photos()
    photo_dir.mkdir(parents=True, exist_ok=True)

    data = uploaded.getvalue() if hasattr(uploaded, "getvalue") else uploaded.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"That file is {len(data) / 1_048_576:.0f} MB. The limit is "
            f"{MAX_UPLOAD_BYTES // 1_048_576} MB; take the photo again at a lower resolution."
        )
    try:
        Image.open(io.BytesIO(data)).verify()      # verify() exhausts the reader,
        image = Image.open(io.BytesIO(data))       # so open it again to use it
        image = image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError(f"That file is not a readable image ({exc}).") from exc

    image.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX), Image.LANCZOS)
    for stale in photo_dir.glob(f"{item_id}.*"):
        stale.unlink()
    destination = photo_dir / f"{item_id}.jpg"
    image.save(destination, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return str(destination)


def drop_photo(item: Item) -> None:
    if item.photo and Path(item.photo).is_file():
        Path(item.photo).unlink()
    item.photo = ""


def category_for(garment: str) -> str:
    return next((c for c, group in CATEGORIES.items() if garment in group), "Accessory")
