"""Colour: the palette, and the rules for combining it.

A palette is not a list of colours, it is a set of roles. Navy is a different
garment depending on whether it is the ground under everything or the field next
to the face, and a colour that works as one is often wrong as the other. So each
colour carries a role and the garment categories it is allowed on, and every
rule below is expressed in those terms.

Coordination then stops being taste and becomes two measurable things:

  value contrast   how far apart two colours are in lightness. Top and bottom
                   within a hair of each other reads as a tracksuit, whatever
                   the hues are.
  temperature      where a hue sits relative to his skin. Warm medium-brown skin
                   at hue 22 carries warm colour easily; cold greys next to the
                   face drain it. Blue is the interesting exception: at roughly
                   the opposite side of the wheel it flatters by contrast, which
                   is why navy is the one cold colour everybody looks well in.

Everything here is plain arithmetic on HSL. No model calls, nothing to wait for.
"""

from __future__ import annotations

import colorsys
import itertools
import re
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

from . import paths

# --- roles --------------------------------------------------------------------

# His skin, measured rather than guessed. Every warmth verdict is relative to
# it, so it lives in one place; the app passes the profile's value in, and this
# is only the fallback for calling the maths directly.
DEFAULT_SKIN = "#A0583C"

# A colour has to stand off his skin on at least one axis, and either will do.
# These are the distances at which each one is enough on its own: sixty degrees
# of hue, or twenty points of lightness.
HUE_GAP = 60.0
VALUE_GAP = 0.20

GROUND, FIELD, ACCENT = "Ground", "Field", "Accent"

ROLES: dict[str, str] = {
    GROUND: "The base of the outfit: trousers, coats, shoes. Mid to dark, and quiet.",
    FIELD: "The large area next to the face: shirts, knitwear. Usually lighter.",
    ACCENT: "Small doses only: a scarf, socks, one knit. Where the chroma lives.",
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

# Twelve equal sectors, used only as labels around the wheel.
HUE_NAMES: tuple[str, ...] = (
    "red", "orange", "amber", "yellow", "lime", "green",
    "teal", "azure", "blue", "indigo", "violet", "magenta",
)

# Naming a colour is a different job from drawing the wheel. Equal sectors put
# navy in "cyan" and olive in "amber", which no tailor would say, so the names
# come from uneven bands that match how cloth is actually described. Blue is
# wide because half of menswear lives in it.
HUE_BANDS: tuple[tuple[float, str], ...] = (
    (15, "red"), (45, "orange"), (70, "amber"), (95, "yellow"), (150, "green"),
    (195, "teal"), (255, "blue"), (285, "indigo"), (320, "violet"), (345, "magenta"),
)

# The fifty colours a menswear wardrobe is actually built from, grouped the way
# they are chosen. Typed free-hand this list became "chocolate", "Chocolate" and
# "dark brown", which are one colour wearing three names.
NAMED_COLOURS: dict[str, tuple[tuple[str, str], ...]] = {
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

COLOUR_NAMES: tuple[str, ...] = tuple(
    name for group in NAMED_COLOURS.values() for name, _ in group
)
COLOUR_HEX: dict[str, str] = {
    name: hex_code for group in NAMED_COLOURS.values() for name, hex_code in group
}


def hex_for(colour: str) -> str:
    return COLOUR_HEX.get(colour, "#CCCCCC")


def colour_group(colour: str) -> str:
    return next((g for g, rows in NAMED_COLOURS.items()
                 if any(n == colour for n, _ in rows)), "")


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


def contrast(a: str, b: str) -> float:
    """Difference in lightness, 0 to 1. The only number that decides whether a
    top and a bottom read as two garments or as one."""
    return abs(lightness(a) - lightness(b))


def value_gap(hex_code: str, skin_hex: str = DEFAULT_SKIN) -> float:
    """How far a colour sits from his own lightness.

    A separate question from hue, and the one that decides whether something
    next to the face reads as contrast or as a tonal blur. At 0.43 he is
    mid-deep, so a mid-brown can be perfectly harmonious in family and still
    disappear against him.
    """
    return abs(lightness(hex_code) - lightness(skin_hex))


def separation(hex_code: str, skin_hex: str = DEFAULT_SKIN) -> float:
    """How far a colour stands off his skin, on whichever axis does the work.

    Two axes, and either is enough on its own. Far round the wheel separates a
    colour whatever its lightness: cobalt sits as close to his lightness as
    chocolate does and reads as a garment, because at 162 degrees it could not
    be mistaken for him. Far in lightness separates it whatever its hue: cream
    is the same warm family and reads as a garment because it is half a scale
    lighter.

    What fails is being close on both, which is exactly brown. One is enough;
    neither is a blur.

    Returns a ratio: one and above separates, below one does not.
    """
    by_hue = hue_distance(hex_code, skin_hex) / HUE_GAP
    by_value = value_gap(hex_code, skin_hex) / VALUE_GAP
    return max(by_hue, by_value)


def separates_from_skin(hex_code: str, skin_hex: str = DEFAULT_SKIN) -> bool:
    return separation(hex_code, skin_hex) >= 1.0


def blurs_at_the_collar(hex_code: str, skin_hex: str = DEFAULT_SKIN) -> bool:
    return not separates_from_skin(hex_code, skin_hex)


def separation_reason(hex_code: str, skin_hex: str = DEFAULT_SKIN) -> str:
    """Which axis is doing the work, or why neither is."""
    hue = hue_distance(hex_code, skin_hex)
    gap = value_gap(hex_code, skin_hex)
    if hue / HUE_GAP >= 1.0:
        return (f"{hue:.0f}° round the wheel from his skin, which separates it "
                "whatever its lightness")
    if gap / VALUE_GAP >= 1.0:
        lighter = "lighter" if lightness(hex_code) > lightness(skin_hex) else "darker"
        return (f"{gap:.2f} {lighter} than his skin, which separates it whatever "
                "its hue")
    return (f"only {hue:.0f}° from his skin hue and {gap:.2f} from his lightness, "
            "so it blurs on both axes at once")


def hue_distance(a: str, b: str) -> float:
    """Shortest way round the wheel, in degrees."""
    difference = abs(hsl(a)[0] - hsl(b)[0]) % 360
    return min(difference, 360 - difference)


def warmth(hex_code: str, skin_hex: str = DEFAULT_SKIN) -> tuple[str, str]:
    """How a colour sits against his skin. Returns (verdict, why).

    Near his skin hue is harmonious, the far side is flattering by contrast, and
    the awkward zone is the near-miss: close enough to relate, far enough to
    argue. That is where sallow greens and cold mauves live.
    """
    saturation, light = hsl(hex_code)[1], hsl(hex_code)[2]
    if saturation < 0.10:
        if light > 0.82:
            return "flattering", "off-white lifts warm skin without competing"
        if light < 0.22:
            return "careful", "near-black drains warm skin; keep it below the waist"
        return "careful", "flat grey next to warm skin reads cold"
    distance = hue_distance(hex_code, skin_hex)
    if distance <= 45:
        return "harmonious", f"{round(distance)}° from his skin hue, the same warm family"
    if distance >= 140:
        return "flattering", f"{round(distance)}° away, flatters by contrast, as navy does"
    return "careful", f"{round(distance)}° away: close enough to relate, far enough to argue"


def harmonies(hex_code: str) -> dict[str, list[str]]:
    """Neighbours on the wheel, as swatches to steal.

    Chroma and lightness are pulled towards wearable ranges on the way out. A
    mathematically perfect complement at full saturation is a traffic cone.
    """
    hue, saturation, light = hsl(hex_code)
    wearable_s = min(saturation, 0.55)

    def at(offset: float, s_scale: float = 1.0, l_shift: float = 0.0) -> str:
        return from_hsl(hue + offset, wearable_s * s_scale, light + l_shift)

    return {
        "Analogous": [at(-30), at(30)],
        "Complementary": [at(180, 0.75)],
        "Split complementary": [at(150, 0.75), at(210, 0.75)],
        "Triadic": [at(120, 0.8), at(240, 0.8)],
        "Shades": [at(0, 1.0, -0.22), at(0, 1.0, 0.22)],
        "Muted": [at(0, 0.45), at(0, 0.25, 0.12)],
    }


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

    def verdict(self, skin_hex: str = DEFAULT_SKIN) -> tuple[str, str]:
        return warmth(self.hex, skin_hex)


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


# --- combining ----------------------------------------------------------------

# The thresholds are the whole argument, so they are named rather than buried.
MIN_TOP_BOTTOM_CONTRAST = 0.18   # below this a top and bottom read as one garment
MUDDY_CONTRAST = 0.10            # and below this it looks like a mistake
LOUD = 0.45                      # saturation above which a colour counts as an event
MAX_FAMILIES = 3                 # distinct hue families before an outfit gets busy

SLOTS: tuple[str, ...] = ("Top", "Bottom", "Outerwear", "Shoes")


@dataclass
class Combination:
    pieces: dict[str, Colour]
    score: int
    reasons: list[str] = field(default_factory=list)
    faults: list[str] = field(default_factory=list)

    @property
    def families(self) -> list[str]:
        seen: list[str] = []
        for colour in self.pieces.values():
            if colour.family not in seen:
                seen.append(colour.family)
        return seen

    @property
    def name(self) -> str:
        return " · ".join(c.name or c.family for c in self.pieces.values())

    @property
    def separation(self) -> float:
        top, bottom = self.pieces.get("Top"), self.pieces.get("Bottom")
        return contrast(top.hex, bottom.hex) if top and bottom else 0.0

    @property
    def verdict(self) -> str:
        return ("wear it" if self.score >= 80 else
                "works" if self.score >= 65 else
                "borderline" if self.score >= 50 else "no")


def score_combination(pieces: dict[str, Colour], skin_hex: str = DEFAULT_SKIN) -> Combination:
    """Score one colour recipe out of 100, and say why.

    Every rule here is a real menswear rule expressed as arithmetic, and every
    one of them can be argued with, which is the point of printing the reason
    next to the number.
    """
    score = 100
    reasons: list[str] = []
    faults: list[str] = []

    top, bottom = pieces.get("Top"), pieces.get("Bottom")
    shoes, coat = pieces.get("Shoes"), pieces.get("Outerwear")

    # 1. Value contrast between top and bottom. The one that matters most.
    if top and bottom:
        gap = contrast(top.hex, bottom.hex)
        if gap < MUDDY_CONTRAST:
            score -= 35
            faults.append(f"top and bottom are {gap:.2f} apart in lightness: reads as one garment")
        elif gap < MIN_TOP_BOTTOM_CONTRAST:
            score -= 15
            faults.append(f"only {gap:.2f} of contrast top to bottom, a shade flat")
        else:
            if gap < 0.30:
                score -= 6      # acceptable, but it could be crisper
            reasons.append(f"{gap:.2f} of light-to-dark between top and bottom, cleanly separated")

    # 2. How many hue families are in play.
    families = {c.family for c in pieces.values()}
    if len(families) > MAX_FAMILIES:
        score -= 12 * (len(families) - MAX_FAMILIES)
        faults.append(f"{len(families)} hue families at once: {', '.join(sorted(families))}")
    elif len(families) == MAX_FAMILIES:
        score -= 6
    elif len(families) <= 2:
        reasons.append(f"held to {len(families)} hue famil{'y' if len(families) == 1 else 'ies'}")

    # 3. What sits next to the face. Two separate questions: is the hue right,
    # and is it far enough from his own lightness to read as a garment rather
    # than as more of him.
    if top:
        verdict, why = warmth(top.hex, skin_hex)
        if verdict == "careful":
            score -= 18
            faults.append(f"next to the face: {why}")
        else:
            reasons.append(f"next to the face: {why}")
        if blurs_at_the_collar(top.hex, skin_hex):
            score -= 14
            faults.append(f"at the collar it {separation_reason(top.hex, skin_hex)}")
        else:
            reasons.append(f"stands off his skin: {separation_reason(top.hex, skin_hex)}")

    # 4. Chroma budget. One loud thing may be interesting; two argue. Shoes are
    # exempt: a chestnut shoe is saturated by the numbers and is never the event.
    loud = [c for c in pieces.items()
            if c[0] != "Shoes" and chroma(c[1].hex) > LOUD]
    loud = [c for _, c in loud]
    if len(loud) > 1:
        score -= 20
        faults.append(f"{len(loud)} loud colours competing: "
                      + ", ".join(c.name or c.family for c in loud))
    elif loud:
        reasons.append(f"one thing is the event: {loud[0].name or loud[0].family}")

    # 5. Shoes against trousers. Near-but-not-equal is the classic mistake.
    if shoes and bottom:
        gap = contrast(shoes.hex, bottom.hex)
        hue_gap = hue_distance(shoes.hex, bottom.hex)
        if gap < 0.08 and 12 < hue_gap < 90:
            score -= 15
            faults.append("shoes nearly match the trousers but not quite, which reads as an accident")
        elif shoes.light <= bottom.light + 0.05:
            reasons.append("shoes anchor the outfit at or below the trousers in weight")

    # 6. Outerwear should sit under everything, not fight the trousers.
    if coat and bottom and contrast(coat.hex, bottom.hex) < MUDDY_CONTRAST \
            and hue_distance(coat.hex, bottom.hex) > 20:
        score -= 10
        faults.append("coat and trousers are the same weight in different hues")

    return Combination(pieces=pieces, score=max(0, min(100, score)),
                       reasons=reasons, faults=faults)


def combinations(palette: Palette, *, with_outerwear: bool = False,
                 skin_hex: str = DEFAULT_SKIN, limit: int = 12,
                 minimum: int = 55, season: str = "") -> list[Combination]:
    """Every colour recipe the palette allows, best first.

    Enumerated rather than invented: the palette is small enough that every
    combination can be scored, so nothing plausible gets missed and nothing
    implausible gets a free pass.
    """
    slots = ["Top", "Bottom", "Shoes"] + (["Outerwear"] if with_outerwear else [])
    options = [palette.for_category(slot, season) for slot in slots]
    if not all(options):
        return []

    scored = [
        score_combination(dict(zip(slots, choice)), skin_hex)
        for choice in itertools.product(*options)
    ]
    scored = [c for c in scored if c.score >= minimum]
    # Among equally clean recipes, the better separated one is the better outfit,
    # so contrast breaks the tie rather than the alphabet.
    scored.sort(key=lambda c: (-c.score, -c.separation, c.name))
    return scored[:limit]


def coverage(palette: Palette, season: str = "") -> dict[str, int]:
    """How many colours each garment category has to choose from. A zero here is
    why the combination list is empty."""
    return {category: len(palette.for_category(category, season))
            for category in CATEGORIES}
