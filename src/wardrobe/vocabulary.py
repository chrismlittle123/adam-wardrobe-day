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
_collar = SizeField("collar", "Collar", (NONE, *_range(13.5, 18.5, 0.5, '"')),
                    "UK shirts are labelled by collar in inches. 15\" is about 38 cm, "
                    "15.5\" about 39 cm, 16\" about 41 cm.")
_sleeve = SizeField("sleeve", "Sleeve", (NONE, *_range(31, 37, 1, '"')),
                    "Dress shirts only, in inches on the label. Casual shirts rarely "
                    "quote it.")
_chest = SizeField("chest", "Chest", (NONE, *_range(34, 48, 2)),
                   "The number on a UK jacket label. It is a size, not a chest "
                   "measurement: the finished garment measures rather more.")
_jkt_len = SizeField("length", "Length", (NONE, "Short", "Regular", "Long"),
                     "38S, 38R and 38L share a chest and differ in body and sleeve length.")
_waist = SizeField("waist", "Waist", (NONE, *_range(26, 44, 1, '"')),
                   "Inches on the label. Rarely the same as your actual waist.")
_leg = SizeField("leg", "Leg", (NONE, *_range(28, 38, 1, '"')),
                 "Inside leg in inches, the half of trouser sizing shops most often "
                 "ignore. 30\" is about 76 cm, 32\" about 81 cm.")
_uk_shoe = SizeField("uk", "UK", (NONE, *_range(5, 14, 0.5)))
_width = SizeField("width", "Width", (NONE, "Narrow", "Standard", "Wide", "D", "E", "F", "G"))

_head = SizeField("head", "Head", (NONE, "S/M", "L/XL", *_range(54, 62, 1, "cm")))
_socks = SizeField("socks", "Size", (NONE, "UK 6-8", "UK 8-11", "UK 11-14"))
_case = SizeField("case", "Case", (NONE, *_range(34, 46, 1, "mm")))
_free = SizeField("size", "Size", (), "However this one happens to be sized.")

# Every scheme a British label might use. A garment points at the ones that can
# apply to it; an item records which one its own label actually used.
SCHEMES: dict[str, tuple[SizeField, ...]] = {
    "Alpha": (_alpha,),
    "Chest and length": (_chest, _jkt_len),
    "Collar and sleeve": (_collar, _sleeve),
    "Waist and leg": (_waist, _leg),
    "Shoe": (_uk_shoe, _width),
    "Head": (_head,),
    "Sock": (_socks,),
    "Watch case": (_case,),
    "One size": (),
    "Free text": (_free,),
}

# There used to be a "Chest" as well as a "Chest and length", and the same for
# collar and for waist. They were the same scheme with the second field taken
# away, and that field was already optional, so a label that does not quote a
# length is entered by leaving the length blank. Three schemes for nothing.
SCHEME_ALIASES: dict[str, str] = {
    "Chest": "Chest and length",
    "Collar": "Collar and sleeve",
    "Waist": "Waist and leg",
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


# The colours a menswear wardrobe is built from, grouped the way they are
# chosen. Fifty to start with, and addable like everything else here. Typed free-hand this list became "chocolate", "Chocolate" and
# "dark brown", which are one colour wearing three names.
DEFAULT_COLOURS: dict[str, tuple[tuple[str, str], ...]] = {
    "Whites and neutrals": (
        ("White", "#F6F4EF"), ("Off-white", "#EFEAE0"), ("Bone", "#E7E0D4"),
        ("Cream", "#F2E9D8"), ("Ecru", "#E8DFC8"), ("Oatmeal", "#DDD3C0"),
        ("Sand", "#D9C9A8"), ("Stone", "#C9BCA4"), ("Beige", "#C8B79A"),
        ("Putty", "#B9AC96"), ("Taupe", "#A2917E"), ("Mushroom", "#9C9184"),
    ),
    "Greys": (
        ("Silver", "#D8D8D6"), ("Light grey", "#C4C3BF"), ("Mid grey", "#7A7A78"),
        ("Slate", "#5A6270"), ("Charcoal", "#3C3B3A"), ("Graphite", "#2B2B2E"),
        ("Black", "#1B1918"),
    ),
    "Blues": (
        ("Powder blue", "#D3E0EC"), ("Pale blue", "#BFD3E6"), ("Sky blue", "#8FB3D0"),
        ("Air force", "#5C7B95"), ("Mid blue", "#4A6E96"), ("Denim", "#3E5C79"),
        ("Petrol", "#2E5561"), ("Navy", "#26303F"), ("Ink", "#1D2430"),
        ("Midnight", "#171E2B"),
    ),
    "Greens": (
        ("Mint", "#BFD6C4"), ("Sage", "#A3AF97"), ("Khaki", "#8A8560"),
        ("Moss", "#6F7A4E"), ("Olive", "#5F6146"), ("Forest", "#2F4032"),
        ("Bottle", "#1F3A2C"),
    ),
    "Browns": (
        ("Biscuit", "#D2B48C"), ("Camel", "#C19A6B"), ("Cognac", "#9C5A2D"),
        ("Tan", "#A9743F"), ("Chestnut", "#8B5A2B"), ("Tobacco", "#7E5835"),
        ("Chocolate", "#6B4426"), ("Espresso", "#3E2A1E"),
    ),
    "Warm accents": (
        ("Dusty pink", "#C9A29B"), ("Terracotta", "#B5613F"),
        ("Mustard", "#C08A2E"), ("Rust", "#8E3B2E"), ("Burgundy", "#6E2C33"),
        ("Oxblood", "#4A1F23"),
    ),
}


# Which schemes can apply to each garment, most specific first. The first is
# what a new item defaults to; the rest are there because the next label will
# disagree with the last one. A trouser is 32/32 from one maker and M from the
# next, and both are true.
DEFAULT_SCHEMES: dict[str, tuple[str, ...]] = {
    "Bag": ("One size",), "Jewellery": ("One size",), "Scarf": ("One size",),
    "Sunglasses": ("One size",),
    "Watch": ("Watch case",), "Socks": ("Sock",),
    "Belt": ("Waist and leg", "Alpha"), "Hat": ("Head", "Alpha"),
    "Blazer": ("Chest and length", "Alpha"),
    "Suit": ("Chest and length",),
    "Overcoat": ("Chest and length", "Alpha"),
    "Jacket": ("Alpha", "Chest and length"),
    "Waistcoat": ("Chest and length", "Alpha"),
    "Overshirt": ("Alpha",), "Gilet": ("Alpha",),
    "Chinos": ("Waist and leg", "Alpha"),
    "Jeans": ("Waist and leg",),
    "Trousers": ("Waist and leg", "Alpha"),
    "Shorts": ("Waist and leg", "Alpha"),
    "Boots": ("Shoe",), "Derbies": ("Shoe",), "Loafers": ("Shoe",),
    "Sandals": ("Shoe",), "Trainers": ("Shoe",),
    "Knitwear": ("Alpha", "Chest and length"), "Polo": ("Alpha",),
    "Sweatshirt": ("Alpha",), "T-shirt": ("Alpha",),
    "Shirt": ("Collar and sleeve", "Alpha"),
}


@dataclass
class Garment:
    name: str = ""
    category: str = "Top"
    schemes: list[str] = field(default_factory=lambda: ["Free text"])

    @property
    def default_scheme(self) -> str:
        return self.schemes[0] if self.schemes else "Free text"


@dataclass
class Fabric:
    name: str = ""
    family: str = ""


@dataclass
class NamedColour:
    name: str = ""
    hex: str = "#CCCCCC"
    group: str = ""


@dataclass
class Vocabulary:
    garments: list[Garment] = field(default_factory=list)
    fabrics: list[Fabric] = field(default_factory=list)
    colours: list[NamedColour] = field(default_factory=list)
    fits: list[str] = field(default_factory=list)
    grades: list[str] = field(default_factory=list)
    path: Path = field(default_factory=lambda: paths.vocabulary())

    @classmethod
    def defaults(cls, path: Path | None = None) -> "Vocabulary":
        garments = [
            Garment(name=name, category=category,
                    schemes=list(DEFAULT_SCHEMES.get(name, ("Free text",))))
            for category, names in DEFAULT_CATEGORIES.items() for name in names
        ]
        fabrics = [Fabric(name=name, family=family)
                   for family, names in DEFAULT_FABRICS.items() for name in names]
        colours = [NamedColour(name=name, hex=code, group=group)
                   for group, rows in DEFAULT_COLOURS.items() for name, code in rows]
        return cls(garments=sorted(garments, key=lambda g: g.name),
                   fabrics=sorted(fabrics, key=lambda f: f.name), colours=colours,
                   fits=list(DEFAULT_FITS), grades=list(DEFAULT_GRADES),
                   path=path or paths.vocabulary()).tidy()

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Vocabulary":
        path = Path(path) if path else paths.vocabulary()
        if not path.is_file():
            return cls.defaults(path)
        raw = tomllib.loads(path.read_text())
        allowed_g = {f.name for f in fields(Garment)}
        allowed_f = {f.name for f in fields(Fabric)}
        allowed_c = {f.name for f in fields(NamedColour)}
        return cls(
            garments=sorted((Garment(**{k: v for k, v in row.items() if k in allowed_g})
                             for row in raw.get("garments", [])), key=lambda g: g.name),
            fabrics=sorted((Fabric(**{k: v for k, v in row.items() if k in allowed_f})
                            for row in raw.get("fabrics", [])), key=lambda f: f.name),
            colours=[NamedColour(**{k: v for k, v in row.items() if k in allowed_c})
                     for row in raw.get("colours", [])] or [
                NamedColour(name=n, hex=c, group=g)
                for g, rows in DEFAULT_COLOURS.items() for n, c in rows],
            fits=list(raw.get("fits", DEFAULT_FITS)),
            grades=list(raw.get("grades", DEFAULT_GRADES)),
            path=path,
        ).tidy()

    def save(self) -> Path:
        self.garments.sort(key=lambda g: g.name)
        self.fabrics.sort(key=lambda f: f.name)
        self.path.write_text(tomli_w.dumps({
            "garments": [asdict(g) for g in self.garments],
            "fabrics": [asdict(f) for f in self.fabrics],
            "colours": [asdict(c) for c in self.colours],
            "fits": self.fits,
            "grades": self.grades,
        }))
        return self.path

    def restore_defaults(self) -> "Vocabulary":
        fresh = Vocabulary.defaults(self.path)
        self.garments, self.fabrics = fresh.garments, fresh.fabrics
        self.colours = fresh.colours
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

    def tidy(self) -> "Vocabulary":
        """Point any garment at a scheme that has since been merged away."""
        for garment in self.garments:
            garment.schemes = list(dict.fromkeys(
                SCHEME_ALIASES.get(s, s) for s in garment.schemes))
        return self

    def schemes_for(self, name: str) -> tuple[str, ...]:
        """Every scheme that can apply to this garment, most specific first."""
        found = self.garment(name)
        return tuple(found.schemes) if found and found.schemes else ("Free text",)

    def scheme_for(self, name: str, scheme: str = "") -> tuple[SizeField, ...]:
        """The boxes to show for this garment sized in this scheme.

        An item naming a scheme its garment does not offer falls back to the
        garment's first, which is what happens when a piece is re-classified.
        """
        applicable = self.schemes_for(name)
        chosen = scheme if scheme in applicable else applicable[0]
        return SCHEMES.get(chosen, SCHEMES["Free text"])

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

    def colour_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.colours)

    def colour_hex(self) -> dict[str, str]:
        return {c.name: c.hex for c in self.colours}

    def colour_group(self, name: str) -> str:
        found = next((c for c in self.colours if c.name == name), None)
        return found.group if found else ""

    def colour_groups(self) -> dict[str, tuple[tuple[str, str], ...]]:
        out: dict[str, list[tuple[str, str]]] = {}
        for colour in self.colours:
            out.setdefault(colour.group or "Unfiled", []).append((colour.name, colour.hex))
        return {k: tuple(v) for k, v in out.items()}

    def add_colour(self, colour: NamedColour) -> NamedColour:
        self.colours.append(colour)
        return colour

    def remove_colour(self, name: str) -> None:
        self.colours = [c for c in self.colours if c.name != name]

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
