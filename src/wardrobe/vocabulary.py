"""The garment catalogue: the vocabularies the rest of the app is built from.

Garments and their categories, the size scheme each one uses, the fabrics and
their families, the fits and the grades. Everything that was a fixed list in the
source and is now a list he can change, because a wardrobe vocabulary that
cannot take a new word is wrong for somebody within a week.

The defaults below are what the app ships with. The moment anything is edited the
whole vocabulary is written to garments.toml and read from there instead.

Lookups go through `current()`, which caches on the file's timestamp. Every
dropdown in the app asks for this on every rerun, and re-reading a TOML forty
times a page for a file that changes twice a month is a waste.
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

from . import paths

# Category drives the outfit slots. Only one item per slot, except accessories.
# Both the categories and the garments inside them are alphabetical, because the
# dropdown is scanned by eye and no other order is defensible.
DEFAULT_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Accessory": ("Bag", "Belt", "Hat", "Jewellery", "Scarf", "Socks", "Sunglasses", "Watch"),
    "Bottom": ("Chinos", "Jeans", "Shorts", "Trousers"),
    "Outerwear": ("Blazer", "Gilet", "Jacket", "Overcoat", "Overshirt", "Suit"),
    "Shoes": ("Boots", "Derbies", "Loafers", "Sandals", "Trainers"),
    "Top": ("Knitwear", "Polo", "Shirt", "Sweatshirt", "T-shirt", "Waistcoat"),
}
SINGLE_SLOT: tuple[str, ...] = ("Top", "Bottom", "Outerwear", "Shoes")


# --- sizing -------------------------------------------------------------------

# A shirt is sized by the collar, a jacket by the chest and a length letter, a
# trouser by waist and leg, a shoe by a number that means something different in
# every country. One shared set of boxes would be wrong for all of them, so each
# garment declares its own.
#
# Everything here is a UK SIZE: the number printed on the label, in whatever unit
# the shop chose to print it. That is not a measurement, and the two get confused
# constantly. A jacket labelled 38 is not 38 of anything you could put a tape
# across; it is a size that happens to have started life as a chest in inches.
# Every actual measurement in this app, body and garment alike, is centimetres,
# and lives in the Body Measurements tab. EU sizes are kept alongside the UK ones
# only because half of Vinted is listed in them.

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

# Grade says what kind of thing it is within its type: the axis that separates a
# heavyweight tee from a plain one, or a dress shirt from a casual one. Together
# with fabric and fit it is what makes a sourcing route precise instead of a
# guess at keywords in a name.
DEFAULT_GRADES: tuple[str, ...] = (
    "", "Everyday", "Heavyweight", "Knitted", "Smart", "Dress", "Branded",
)

# How it is cut. Kept on the item rather than in the size scheme, because it is
# a property of the garment and not a number on a label.
DEFAULT_FITS: tuple[str, ...] = ("", "Slim", "Regular", "Relaxed", "Oversized")

_alpha = SizeField("alpha", "Size", ALPHA)
_collar = SizeField("collar", "Collar (UK)", (NONE, *_range(13.5, 18.5, 0.5, '"')),
                    "UK shirts are labelled by collar in inches. 15\" is about 38 cm, "
                    "15.5\" about 39 cm, 16\" about 41 cm.")
_sleeve = SizeField("sleeve", "Sleeve (UK)", (NONE, *_range(31, 37, 1, '"')),
                    "Dress shirts only, in inches on the label. Casual shirts rarely "
                    "quote it.")
_chest = SizeField("chest", "UK size", (NONE, *_range(34, 48, 2)),
                   "The number on a UK jacket label. It is a size, not a chest "
                   "measurement: the finished garment measures rather more.")
_jkt_len = SizeField("length", "Length", (NONE, "Short", "Regular", "Long"),
                     "38S, 38R and 38L share a chest and differ in body and sleeve length.")
_eu_jkt = SizeField("eu", "EU size", (NONE, *_range(42, 62, 2)),
                    "Half of Vinted is listed in these. Roughly the UK size plus 10.")
_waist = SizeField("waist", "Waist (UK)", (NONE, *_range(26, 44, 1, '"')),
                   "Inches on the label. Rarely the same as your actual waist.")
_leg = SizeField("leg", "Leg (UK)", (NONE, *_range(28, 38, 1, '"')),
                 "Inside leg in inches, the half of trouser sizing shops most often "
                 "ignore. 30\" is about 76 cm, 32\" about 81 cm.")
_uk_shoe = SizeField("uk", "UK", (NONE, *_range(5, 14, 0.5)))
_eu_shoe = SizeField("eu", "EU", (NONE, *_range(38, 49, 0.5)),
                     "For listings from the continent. Roughly UK plus 33.")
_width = SizeField("width", "Width", (NONE, "Narrow", "Standard", "Wide", "D", "E", "F", "G"))

SHOE_SCHEME = (_uk_shoe, _eu_shoe, _width)
JACKET_SCHEME = (_chest, _jkt_len, _eu_jkt)
TROUSER_SCHEME = (_waist, _leg)
TOP_SCHEME = (_alpha,)
DEFAULT_SCHEME = (SizeField("size", "Size", (), "However this one happens to be sized."),)

# Named so a garment can point at one by name and the catalogue can offer the
# list without anyone typing a tuple of field definitions into a form.
SCHEMES: dict[str, tuple[SizeField, ...]] = {
    "Shoes": SHOE_SCHEME,
    "Jacket": JACKET_SCHEME,
    "Trousers": TROUSER_SCHEME,
    "Top": TOP_SCHEME,
    "Shirt": (_collar, _alpha, _sleeve),
    "Alpha only": (_alpha,),
    "Waist only": (_waist,),
    "Watch": (SizeField("case", "Case", (NONE, *_range(34, 46, 1, "mm"))),),
    "Belt": (SizeField("waist", "Waist (UK)", (NONE, *_range(26, 44, 1, '"'))), _alpha),
    "Hat": (SizeField("hat", "Size", (NONE, "S/M", "L/XL", *_range(54, 62, 1, "cm"))),),
    "Socks": (SizeField("socks", "UK size", (NONE, "UK 6-8", "UK 8-11", "UK 11-14")),),
    "None": (),
    "Free text": (SizeField("size", "Size", (), "However this one happens to be sized."),),
}

DEFAULT_SIZE_SCHEMES: dict[str, tuple[SizeField, ...]] = {
    "Bag": (), "Jewellery": (), "Scarf": (), "Sunglasses": (),
    "Watch": (SizeField("case", "Case", (NONE, *_range(34, 46, 1, "mm"))),),
    "Belt": (SizeField("waist", "Waist (UK)", (NONE, *_range(26, 44, 1, '"'))), _alpha),
    "Hat": (SizeField("hat", "Size", (NONE, "S/M", "L/XL", *_range(54, 62, 1, "cm"))),),
    "Socks": (SizeField("socks", "UK size", (NONE, "UK 6-8", "UK 8-11", "UK 11-14")),),
    "Blazer": JACKET_SCHEME, "Overcoat": JACKET_SCHEME, "Suit": JACKET_SCHEME,
    "Jacket": (_alpha, _chest), "Overshirt": TOP_SCHEME, "Gilet": (_alpha,),
    "Waistcoat": (_chest, _alpha),
    "Chinos": TROUSER_SCHEME, "Jeans": TROUSER_SCHEME, "Trousers": TROUSER_SCHEME,
    "Shorts": (_waist,),
    "Boots": SHOE_SCHEME, "Derbies": SHOE_SCHEME, "Loafers": SHOE_SCHEME,
    "Sandals": SHOE_SCHEME, "Trainers": SHOE_SCHEME,
    "Knitwear": TOP_SCHEME, "Polo": TOP_SCHEME, "Sweatshirt": TOP_SCHEME, "T-shirt": TOP_SCHEME,
    "Shirt": (_collar, _alpha, _sleeve),
}


# Cloth, by family. Typing it free-hand produced "cotton", "Cotton" and "100%
# cotton" as three different fabrics, which made the inventory unsearchable and
# gave the image model three different answers for the same shirt.
DEFAULT_FABRICS: dict[str, tuple[str, ...]] = {
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


# Which named scheme each garment uses by default. A garment the catalogue has
# never heard of falls back to free text rather than to nothing.
DEFAULT_SCHEME_NAMES: dict[str, str] = {
    "Bag": "None", "Jewellery": "None", "Scarf": "None", "Sunglasses": "None",
    "Watch": "Watch", "Belt": "Belt", "Hat": "Hat", "Socks": "Socks",
    "Blazer": "Jacket", "Overcoat": "Jacket", "Suit": "Jacket",
    "Jacket": "Jacket", "Overshirt": "Top", "Gilet": "Alpha only",
    "Waistcoat": "Jacket",
    "Chinos": "Trousers", "Jeans": "Trousers", "Trousers": "Trousers",
    "Shorts": "Waist only",
    "Boots": "Shoes", "Derbies": "Shoes", "Loafers": "Shoes",
    "Sandals": "Shoes", "Trainers": "Shoes",
    "Knitwear": "Top", "Polo": "Top", "Sweatshirt": "Top", "T-shirt": "Top",
    "Shirt": "Shirt",
}


@dataclass
class Garment:
    name: str = ""
    category: str = "Top"
    scheme: str = "Free text"


@dataclass
class Fabric:
    name: str = ""
    family: str = ""


@dataclass
class Vocabulary:
    garments: list[Garment] = field(default_factory=list)
    fabrics: list[Fabric] = field(default_factory=list)
    fits: list[str] = field(default_factory=list)
    grades: list[str] = field(default_factory=list)
    path: Path = field(default_factory=lambda: paths.vocabulary())

    @classmethod
    def defaults(cls, path: Path | None = None) -> "Vocabulary":
        garments = [
            Garment(name=name, category=category,
                    scheme=DEFAULT_SCHEME_NAMES.get(name, "Free text"))
            for category, names in DEFAULT_CATEGORIES.items() for name in names
        ]
        fabrics = [Fabric(name=name, family=family)
                   for family, names in DEFAULT_FABRICS.items() for name in names]
        return cls(garments=sorted(garments, key=lambda g: g.name),
                   fabrics=sorted(fabrics, key=lambda f: f.name),
                   fits=list(DEFAULT_FITS), grades=list(DEFAULT_GRADES),
                   path=path or paths.vocabulary())

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Vocabulary":
        path = Path(path) if path else paths.vocabulary()
        if not path.is_file():
            return cls.defaults(path)
        raw = tomllib.loads(path.read_text())
        allowed_g = {f.name for f in fields(Garment)}
        allowed_f = {f.name for f in fields(Fabric)}
        return cls(
            garments=sorted((Garment(**{k: v for k, v in row.items() if k in allowed_g})
                             for row in raw.get("garments", [])), key=lambda g: g.name),
            fabrics=sorted((Fabric(**{k: v for k, v in row.items() if k in allowed_f})
                            for row in raw.get("fabrics", [])), key=lambda f: f.name),
            fits=list(raw.get("fits", DEFAULT_FITS)),
            grades=list(raw.get("grades", DEFAULT_GRADES)),
            path=path,
        )

    def save(self) -> Path:
        self.garments.sort(key=lambda g: g.name)
        self.fabrics.sort(key=lambda f: f.name)
        self.path.write_text(tomli_w.dumps({
            "garments": [asdict(g) for g in self.garments],
            "fabrics": [asdict(f) for f in self.fabrics],
            "fits": self.fits,
            "grades": self.grades,
        }))
        return self.path

    def restore_defaults(self) -> "Vocabulary":
        fresh = Vocabulary.defaults(self.path)
        self.garments, self.fabrics = fresh.garments, fresh.fabrics
        self.fits, self.grades = fresh.fits, fresh.grades
        self.save()
        return self

    # --- lookups --------------------------------------------------------------

    def names(self) -> tuple[str, ...]:
        return tuple(g.name for g in self.garments)

    def garment(self, name: str) -> Garment | None:
        return next((g for g in self.garments if g.name == name), None)

    def categories(self) -> dict[str, tuple[str, ...]]:
        out: dict[str, list[str]] = {}
        for g in self.garments:
            out.setdefault(g.category, []).append(g.name)
        return {k: tuple(sorted(out[k])) for k in sorted(out)}

    def category_names(self) -> tuple[str, ...]:
        return tuple(sorted({g.category for g in self.garments} | set(DEFAULT_CATEGORIES)))

    def category_for(self, name: str) -> str:
        found = self.garment(name)
        return found.category if found else "Accessory"

    def scheme_for(self, name: str) -> tuple[SizeField, ...]:
        found = self.garment(name)
        return SCHEMES.get(found.scheme, SCHEMES["Free text"]) if found else SCHEMES["Free text"]

    def fabric_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fabrics)

    def fabric_options(self) -> tuple[str, ...]:
        return (NONE, *self.fabric_names())

    def fabric_family(self, name: str) -> str:
        found = next((f for f in self.fabrics if f.name == name), None)
        return found.family if found else ""

    def families(self) -> tuple[str, ...]:
        return tuple(sorted({f.family for f in self.fabrics if f.family}))

    def by_family(self) -> dict[str, list[Fabric]]:
        out: dict[str, list[Fabric]] = {}
        for fabric in self.fabrics:
            out.setdefault(fabric.family or "Unfiled", []).append(fabric)
        return {k: out[k] for k in sorted(out)}

    def add_garment(self, garment: Garment) -> Garment:
        self.garments.append(garment)
        return garment

    def remove_garment(self, name: str) -> None:
        self.garments = [g for g in self.garments if g.name != name]

    def add_fabric(self, fabric: Fabric) -> Fabric:
        self.fabrics.append(fabric)
        return fabric

    def remove_fabric(self, name: str) -> None:
        self.fabrics = [f for f in self.fabrics if f.name != name]


# Cached on the file's timestamp. Every dropdown asks for this on every rerun,
# and re-reading a TOML forty times a page for a file that changes twice a month
# is a waste.
_cached: tuple[str, float, Vocabulary] | None = None


def current() -> Vocabulary:
    global _cached
    path = paths.vocabulary()
    stamp = path.stat().st_mtime if path.is_file() else 0.0
    if _cached and _cached[0] == str(path) and _cached[1] == stamp:
        return _cached[2]
    loaded = Vocabulary.load(path)
    _cached = (str(path), stamp, loaded)
    return loaded
