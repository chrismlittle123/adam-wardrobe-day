"""Colour: the palette, and the one rule.

There is exactly one rule here, and it is the only one that cannot be broken:

    A colour worn on top must sit far enough from his skin.

That is it. Everything else is preference, and preference belongs to him, not to
this file. There used to be a warmth verdict calling colours harmonious, or
flattering, or careful, on the strength of how many degrees round the hue wheel
they sat from his skin. It was invented rather than observed, it dressed taste up
as arithmetic, and it is gone.

The one rule is measured, not guessed: straight distance in CIELAB, where a step
of a given size looks like the same size wherever it is taken. Under TOO_CLOSE a
colour at the collar reads as more of him than as a garment. Anything else
passes, including close-toned choices like burgundy, which are a deliberate look
and not a mistake.

A colour still carries a role and the garments it is allowed on, because a
trouser colour is not a shirt colour. That is bookkeeping, not a verdict.
"""

from __future__ import annotations

import colorsys
import math
import re
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

from . import paths

# --- roles --------------------------------------------------------------------

# His skin, measured rather than guessed. The rule is relative to it, so it lives
# in one place; the app passes the profile's value in, and this is only the
# fallback for calling the maths directly.
DEFAULT_SKIN = "#A0583C"

# The only threshold in this file. Under it, a colour at the collar reads as more
# of him than as a garment. Over it, it passes: there is no second band and no
# grade of approval, because the rule is a rule and not an opinion.
TOO_CLOSE = 20.0

# Where the rule applies. A jumper and a shirt sit at the face; trousers, shoes
# and a belt do not, and a colour too near his skin is perfectly good on those.
NEAR_THE_FACE: tuple[str, ...] = ("Top",)

GROUND, FIELD, ACCENT = "Ground", "Field", "Accent"

ROLES: dict[str, str] = {
    ACCENT: "Small doses only: a scarf, socks, one knit. Where the chroma lives.",
    FIELD: "The large area next to the face: shirts, knitwear. Usually lighter.",
    GROUND: "The base of the outfit: trousers, coats, shoes. Mid to dark, and quiet.",
}

# What each role is allowed on unless overridden per colour.
ROLE_CATEGORIES: dict[str, tuple[str, ...]] = {
    GROUND: ("Bottom", "Outerwear", "Shoes"),
    FIELD: ("Top", "Outerwear"),
    ACCENT: ("Accessory", "Top"),
}

# A wardrobe is not worn all year, and a palette that ignores that produces
# linen colours in February. Every colour belongs to at least one season; the
# ones that belong to all four are the spine of the thing.
SEASONS: tuple[str, ...] = ("Spring", "Summer", "Autumn", "Winter")

CATEGORIES: tuple[str, ...] = ("Top", "Bottom", "Outerwear", "Shoes", "Accessory")

# Naming a colour is a different job from drawing the wheel. Equal sectors put
# navy in "cyan" and olive in "amber", which no tailor would say, so the names
# come from uneven bands that match how cloth is actually described. Blue is
# wide because half of menswear lives in it.
HUE_BANDS: tuple[tuple[float, str], ...] = (
    (15, "red"), (45, "orange"), (70, "amber"), (95, "yellow"), (150, "green"),
    (195, "teal"), (255, "blue"), (285, "indigo"), (320, "violet"), (345, "magenta"),
)

# The colour list lives in the garment catalogue with the other vocabularies, so
# it can be added to. What stays here is the arithmetic done on it.
def _vocab():
    from . import vocabulary
    return vocabulary.current()


def named_colours() -> dict[str, tuple[tuple[str, str], ...]]:
    return _vocab().colour_groups()


def colour_names() -> tuple[str, ...]:
    return _vocab().colour_names()


def colour_hex() -> dict[str, str]:
    return _vocab().colour_hex()


def hex_for(colour: str) -> str:
    return _vocab().colour_hex().get(colour, "#CCCCCC")


def colour_group(colour: str) -> str:
    return _vocab().colour_group(colour)


# --- colour arithmetic --------------------------------------------------------

def to_rgb(hex_code: str) -> tuple[float, float, float]:
    value = hex_code.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02X}" for c in rgb)


def hsl(hex_code: str) -> tuple[float, float, float]:
    """Hue in degrees, saturation and lightness 0 to 1."""
    r, g, b = to_rgb(hex_code)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s, l


def from_hsl(hue: float, saturation: float, lightness: float) -> str:
    r, g, b = colorsys.hls_to_rgb((hue % 360) / 360, max(0.0, min(1.0, lightness)),
                                  max(0.0, min(1.0, saturation)))
    return to_hex((r, g, b))


def lightness(hex_code: str) -> float:
    return hsl(hex_code)[2]


def chroma(hex_code: str) -> float:
    return hsl(hex_code)[1]


def hue_name(hex_code: str) -> str:
    hue, saturation, light = hsl(hex_code)
    if saturation < 0.10:
        return "grey" if 0.15 < light < 0.85 else ("white" if light >= 0.85 else "black")
    # Brown is not a hue, it is a dark warm orange, so it never falls out of the
    # wheel on its own. Without this a chocolate shoe is filed under "red".
    if 15 <= hue <= 45 and light < 0.45:
        return "brown"
    # Cream and ecru are warm near-whites. Calling them orange is technically
    # defensible and would look ridiculous on the page.
    if 15 <= hue <= 70 and light > 0.85 and saturation < 0.55:
        return "cream"
    # Olive is a dark, quiet yellow-green. Like brown, it is a cloth colour that
    # never falls out of the wheel on its own.
    if 45 <= hue <= 95 and light < 0.45 and saturation < 0.45:
        return "olive"
    return next((name for edge, name in HUE_BANDS if hue < edge), "red")


def to_lab(hex_code: str) -> tuple[float, float, float]:
    """sRGB to CIELAB, D65.

    Distances are meant to be taken in this space: a step of a given size looks
    like the same size wherever in the space it is taken, which is not true of
    RGB or of HSL.
    """
    def linear(channel: float) -> float:
        return (channel / 12.92 if channel <= 0.04045
                else ((channel + 0.055) / 1.055) ** 2.4)

    r, g, b = (linear(c) for c in to_rgb(hex_code))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


# --- the one rule -------------------------------------------------------------

def skin_distance(hex_code: str, skin_hex: str = DEFAULT_SKIN) -> float:
    """How far this colour sits from his skin, perceptually.

    Straight Euclidean distance in CIELAB. Roughly: under 20 the two are more
    alike than not, over 50 nobody would group them.
    """
    return math.dist(to_lab(hex_code), to_lab(skin_hex))


def clears_the_face(hex_code: str, skin_hex: str = DEFAULT_SKIN) -> bool:
    """The rule, as a yes or a no. Nothing in between."""
    return skin_distance(hex_code, skin_hex) >= TOO_CLOSE


def blurs_at_the_collar(hex_code: str, skin_hex: str = DEFAULT_SKIN) -> bool:
    return not clears_the_face(hex_code, skin_hex)


def face_rule(hex_code: str, skin_hex: str = DEFAULT_SKIN) -> tuple[bool, str]:
    """(passes, why). The only judgement this module makes about a colour."""
    distance = skin_distance(hex_code, skin_hex)
    if distance < TOO_CLOSE:
        return False, (f"{distance:.0f} from his skin, under the {TOO_CLOSE:.0f} "
                       "minimum: at the collar this reads as more of him than as "
                       "a garment")
    return True, f"{distance:.0f} from his skin, clear of the {TOO_CLOSE:.0f} minimum"


def breaks_the_rule(palette: "Palette", skin_hex: str = DEFAULT_SKIN) -> list["Colour"]:
    """Every colour in the palette allowed near the face that sits too close."""
    return [c for c in palette.colours
            if any(c.allows(category) for category in NEAR_THE_FACE)
            and blurs_at_the_collar(c.hex, skin_hex)]


# --- the palette --------------------------------------------------------------

@dataclass
class Colour:
    id: str = ""
    name: str = ""
    hex: str = "#888888"
    role: str = GROUND
    categories: list[str] = field(default_factory=list)
    seasons: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def allowed(self) -> tuple[str, ...]:
        return tuple(self.categories) or ROLE_CATEGORIES.get(self.role, ())

    def allows(self, category: str) -> bool:
        return category in self.allowed

    @property
    def wears(self) -> tuple[str, ...]:
        """Seasons this colour is for. None recorded means all of them."""
        return tuple(self.seasons) if self.seasons else SEASONS

    def in_season(self, season: str) -> bool:
        return season in self.wears

    @property
    def season_line(self) -> str:
        return "all year" if len(self.wears) == len(SEASONS) else ", ".join(self.wears)

    @property
    def light(self) -> float:
        return lightness(self.hex)

    @property
    def family(self) -> str:
        return hue_name(self.hex)

    @property
    def near_the_face(self) -> bool:
        """Whether the rule applies to this colour at all."""
        return any(self.allows(category) for category in NEAR_THE_FACE)


@dataclass
class Palette:
    colours: list[Colour] = field(default_factory=list)
    path: Path = field(default_factory=paths.palette)

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Palette":
        path = Path(path) if path else paths.palette()
        if not path.is_file():
            return cls(path=path)
        raw = tomllib.loads(path.read_text())
        allowed = {f.name for f in fields(Colour)}
        colours = [Colour(**{k: v for k, v in row.items() if k in allowed})
                   for row in raw.get("colours", [])]
        return cls(colours=colours, path=path)

    def save(self) -> Path:
        self.path.write_text(tomli_w.dumps({"colours": [asdict(c) for c in self.colours]}))
        return self.path

    def add(self, colour: Colour) -> Colour:
        colour.id = colour.id or self.unique_id(colour.name or colour.hex)
        colour.categories = colour.categories or list(ROLE_CATEGORIES.get(colour.role, ()))
        self.colours.append(colour)
        return colour

    def remove(self, colour_id: str) -> None:
        self.colours = [c for c in self.colours if c.id != colour_id]

    def by_id(self, colour_id: str) -> Colour | None:
        return next((c for c in self.colours if c.id == colour_id), None)

    def unique_id(self, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", (name or "colour").lower()).strip("-")[:32] or "colour"
        taken = {c.id for c in self.colours}
        if base not in taken:
            return base
        n = 2
        while f"{base}-{n}" in taken:
            n += 1
        return f"{base}-{n}"

    def for_category(self, category: str, season: str = "") -> list[Colour]:
        return sorted(
            (c for c in self.colours
             if c.allows(category) and (not season or c.in_season(season))),
            key=lambda c: -c.light,
        )

    def for_season(self, season: str) -> list[Colour]:
        return sorted((c for c in self.colours if c.in_season(season)),
                      key=lambda c: (c.role, -c.light))

    def by_season(self) -> dict[str, list[Colour]]:
        return {season: self.for_season(season) for season in SEASONS}

    def by_role(self) -> dict[str, list[Colour]]:
        out: dict[str, list[Colour]] = {}
        for colour in self.colours:
            out.setdefault(colour.role, []).append(colour)
        return out

    def has(self, hex_code: str) -> bool:
        return any(c.hex.upper() == hex_code.upper() for c in self.colours)


def for_category(palette: "Palette", category: str, season: str = "") -> list["Colour"]:
    return palette.for_category(category, season)


def coverage(palette: "Palette", season: str = "") -> dict[str, int]:
    """How many colours each garment category has to choose from, in a season.
    A zero is why a seasonal palette has a hole in it."""
    return {category: len(palette.for_category(category, season))
            for category in CATEGORIES}
