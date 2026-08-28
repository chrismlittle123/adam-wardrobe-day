"""Body measurements, and the finished garment dimensions that follow from them.

Two different things live here and they are constantly confused in shops:

  BODY measurements   what a tape measure reads off the man.
  GARMENT measurements what the finished piece measures flat or round.

A garment is the body plus *ease*: the air you need to move, plus the air the
cut is supposed to have. Ease is where fit actually lives, so it is tabulated
per garment and per fit preference rather than hidden in a size label. A label
saying "medium" means nothing across two brands; a shirt measuring 106 cm round
the chest means the same thing everywhere.

Every number is centimetres. Zero means "not measured yet", and the estimator
fills the gap from height and build so the guide is useful before anyone finds
a tape measure. Estimates are always marked as estimates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields

# --- body ---------------------------------------------------------------------

# Anthropometric ratios against height, tuned for a lean athletic build. Rough
# by nature: they get a shopping list started, they do not fit a jacket.
HEIGHT_RATIOS: dict[str, float] = {
    "chest": 0.550,
    "waist": 0.442,
    "hip": 0.540,
    "shoulder": 0.255,
    "bicep": 0.175,
    "wrist": 0.095,
    "sleeve": 0.345,
    "neck": 0.215,
    "inseam": 0.455,
    "outseam": 0.605,
    # Not asked for, only derived: awkward to take on yourself, but the trouser
    # spec needs them for the thigh and the leg opening.
    "thigh": 0.310,
    "knee": 0.215,
    "ankle": 0.128,
}

# Multipliers on the estimate for builds away from athletic. "Lean athletic" is
# its own row rather than a compromise between two others: a man who is both
# carries an athletic chest on a lean waist, and averaging the two gets the
# chest wrong in one direction and the waist wrong in the other.
BUILD_FACTORS: dict[str, dict[str, float]] = {
    "lean":          {"chest": 0.97, "waist": 0.94, "hip": 0.97, "bicep": 0.93, "thigh": 0.95},
    "lean athletic": {"chest": 1.00, "waist": 0.94, "hip": 0.99, "bicep": 0.99, "thigh": 0.98},
    "athletic":      {"chest": 1.00, "waist": 1.00, "hip": 1.00, "bicep": 1.00, "thigh": 1.00},
    "average":       {"chest": 1.02, "waist": 1.09, "hip": 1.03, "bicep": 1.04, "thigh": 1.04},
    "solid":         {"chest": 1.06, "waist": 1.20, "hip": 1.07, "bicep": 1.10, "thigh": 1.09},
}

# The ten the form asks for, in the order you would take them: top down, then legs.
HOW_TO_MEASURE: dict[str, str] = {
    "neck": "Round the base of the neck where a collar sits. Leave one finger of slack.",
    "shoulder": "Across the back, from the bony point of one shoulder to the other.",
    "chest": "Round the fullest part, under the arms, tape level, arms down, breathe out.",
    "waist": "Round the natural waist, the narrowest point, roughly at the navel.",
    "hip": "Round the fullest part of the hips and seat, feet together.",
    "bicep": "Round the fullest part of the upper arm, arm relaxed at the side.",
    "wrist": "Round the wrist bone, where a cuff closes.",
    "sleeve": "From the shoulder point, over a slightly bent elbow, to the wrist bone.",
    "inseam": "From the crotch seam down the inside of the leg to the ankle bone.",
    "outseam": "From the waistband down the outside of the leg to the ankle bone.",
}

# All ten matter; none is optional. Kept as a name because the UI flags them.
CRITICAL: tuple[str, ...] = tuple(HOW_TO_MEASURE)


@dataclass
class Body:
    """The ten measurements worth taking, in centimetres. Zero means not measured.

    Deliberately only what a man can get on himself with a tape and a mirror.
    Thigh, knee and ankle are not asked for; they are derived from height so the
    trouser spec keeps its leg opening without demanding a second pair of hands.
    """

    chest: float = 0
    waist: float = 0
    hip: float = 0
    shoulder: float = 0
    bicep: float = 0
    wrist: float = 0
    sleeve: float = 0
    neck: float = 0
    inseam: float = 0
    outseam: float = 0

    def measured(self) -> dict[str, float]:
        return {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name)}

    def missing(self) -> list[str]:
        return [f.name for f in fields(self) if not getattr(self, f.name)]

    def missing_critical(self) -> list[str]:
        return self.missing()

    def resolved(self, height_cm: float, build: str = "athletic") -> tuple[dict[str, float], set[str]]:
        """Every dimension a garment target needs. Returns (values, estimated names).

        Starts from the estimate and lets real measurements overwrite it, so the
        derived-only dimensions are present without being asked for.
        """
        values = estimate(height_cm, build)
        taken = self.measured()
        values.update(taken)
        estimated = {k for k in values if k not in taken}
        return {k: round(float(v), 1) for k, v in values.items()}, estimated


def estimate(height_cm: float, build: str = "athletic") -> dict[str, float]:
    """Starting-point body measurements from height and build. Rough on purpose."""
    factors = BUILD_FACTORS.get(_build_key(build), BUILD_FACTORS["athletic"])
    return {k: round(height_cm * r * factors.get(k, 1.0), 1) for k, r in HEIGHT_RATIOS.items()}


def _build_key(build: str) -> str:
    """Which row of BUILD_FACTORS a free-text build description lands on.

    Checked most specific first. "Very lean and athletic" contains both words and
    must not resolve to plain "lean", which would shave three centimetres off the
    chest estimate and quietly hand him a jacket a size too small.
    """
    text = (build or "").lower()
    if "lean" in text and "athletic" in text:
        return "lean athletic"
    for key in ("solid", "average", "athletic", "lean"):
        if key in text:
            return key
    return "athletic"


# --- garments -----------------------------------------------------------------

FITS: tuple[str, ...] = ("Slim", "Regular", "Relaxed")

# Ease added to the body measurement, in cm, per garment and fit. Circumference
# values are the full round measure, not the flat half.
EASE: dict[str, dict[str, dict[str, float]]] = {
    "Shirt": {
        "Slim":    {"chest": 14, "waist": 12, "hip": 12, "shoulder": 0.5, "bicep": 8, "neck": 2},
        "Regular": {"chest": 18, "waist": 18, "hip": 16, "shoulder": 1.5, "bicep": 11, "neck": 2},
        "Relaxed": {"chest": 24, "waist": 26, "hip": 22, "shoulder": 3.0, "bicep": 15, "neck": 2.5},
    },
    "T-shirt": {
        "Slim":    {"chest": 10, "waist": 12, "shoulder": 0, "bicep": 7},
        "Regular": {"chest": 14, "waist": 16, "shoulder": 1, "bicep": 10},
        "Relaxed": {"chest": 20, "waist": 22, "shoulder": 2.5, "bicep": 14},
    },
    "Polo": {
        "Slim":    {"chest": 11, "waist": 12, "shoulder": 0, "bicep": 7, "neck": 2},
        "Regular": {"chest": 15, "waist": 17, "shoulder": 1, "bicep": 10, "neck": 2},
        "Relaxed": {"chest": 20, "waist": 22, "shoulder": 2.5, "bicep": 14, "neck": 2.5},
    },
    "Knitwear": {
        "Slim":    {"chest": 12, "waist": 12, "shoulder": 0.5, "bicep": 8},
        "Regular": {"chest": 16, "waist": 16, "shoulder": 1.5, "bicep": 11},
        "Relaxed": {"chest": 22, "waist": 22, "shoulder": 3.0, "bicep": 15},
    },
    "Blazer": {
        "Slim":    {"chest": 10, "waist": 8,  "hip": 10, "shoulder": 0.5, "bicep": 10},
        "Regular": {"chest": 14, "waist": 14, "hip": 14, "shoulder": 1.5, "bicep": 13},
        "Relaxed": {"chest": 18, "waist": 20, "hip": 18, "shoulder": 3.0, "bicep": 16},
    },
    "Overcoat": {
        "Slim":    {"chest": 20, "waist": 20, "hip": 18, "shoulder": 2.5, "bicep": 16},
        "Regular": {"chest": 25, "waist": 26, "hip": 24, "shoulder": 3.5, "bicep": 19},
        "Relaxed": {"chest": 30, "waist": 32, "hip": 30, "shoulder": 5.0, "bicep": 23},
    },
    "Trousers": {
        "Slim":    {"waist": 2, "hip": 6,  "thigh": 6,  "knee": 6,  "ankle": 12},
        "Regular": {"waist": 3, "hip": 10, "thigh": 9,  "knee": 9,  "ankle": 16},
        "Relaxed": {"waist": 4, "hip": 14, "thigh": 13, "knee": 13, "ankle": 21},
    },
    "Jeans": {
        "Slim":    {"waist": 1, "hip": 5,  "thigh": 5,  "knee": 5,  "ankle": 11},
        "Regular": {"waist": 2, "hip": 9,  "thigh": 8,  "knee": 8,  "ankle": 15},
        "Relaxed": {"waist": 3, "hip": 13, "thigh": 12, "knee": 12, "ankle": 20},
    },
}

# Lengths, as a fraction of height. A jacket that covers the seat on one man is
# a tunic on a shorter one, so length is never a fixed number.
LENGTH_RATIOS: dict[str, dict[str, float]] = {
    "Shirt":    {"Tucked": 0.435, "Untucked": 0.400},
    "T-shirt":  {"Body": 0.398},
    "Polo":     {"Body": 0.402},
    "Knitwear": {"Body": 0.395},
    "Blazer":   {"Body": 0.415},
    "Overcoat": {"Mid-thigh": 0.545, "Knee": 0.620},
}

RISES: dict[str, tuple[float, float]] = {"Low": (22, 24), "Mid": (25, 27), "High": (28, 31)}
BREAKS: dict[str, float] = {"No break": -2.0, "Quarter break": 0.0, "Half break": 2.0, "Full break": 4.0}

# Dimensions that read as a circumference, so a shop's flat measurement is half.
CIRCUMFERENCE: frozenset[str] = frozenset(
    {"chest", "waist", "hip", "neck", "bicep", "thigh", "knee", "ankle", "wrist"}
)

LABELS: dict[str, str] = {
    "chest": "Chest", "waist": "Waist", "hip": "Hip", "neck": "Neck",
    "shoulder": "Shoulder", "sleeve": "Sleeve", "bicep": "Bicep", "thigh": "Thigh",
    "knee": "Knee", "ankle": "Leg opening", "length": "Length", "inseam": "Inseam",
    "rise": "Rise", "outseam": "Outseam",
}


@dataclass
class Target:
    """One target dimension on a finished garment."""

    key: str
    label: str
    value: float
    note: str = ""
    estimated: bool = False

    @property
    def flat(self) -> float | None:
        """What a shop's flat measurement should read, for circumferences."""
        return round(self.value / 2, 1) if self.key in CIRCUMFERENCE else None


def target_spec(
    garment: str,
    body: Body,
    height_cm: float,
    *,
    fit: str = "Regular",
    build: str = "athletic",
    length_style: str | None = None,
    rise: str = "Mid",
    trouser_break: str = "Quarter break",
    show_cuff_cm: float = 1.5,
) -> list[Target]:
    """The finished measurements to look for in a garment of this type.

    This is what to take into a shop, or send to an alterations tailor. Every
    value is the finished garment, not the body.
    """
    values, estimated = body.resolved(height_cm, build)
    ease = EASE.get(garment, {}).get(fit, {})
    out: list[Target] = []

    def add(key: str, value: float, note: str = "", basis: str | None = None) -> None:
        out.append(
            Target(key, LABELS.get(key, key.title()), round(value, 1), note,
                   estimated=(basis or key) in estimated)
        )

    for key, amount in ease.items():
        if key not in values:
            continue
        sign = "+" if amount >= 0 else ""
        add(key, values[key] + amount, f"body {values[key]} {sign}{amount} ease")

    if garment in ("Shirt", "T-shirt", "Polo", "Knitwear", "Blazer", "Overcoat"):
        sleeve_adjust = -show_cuff_cm if garment in ("Blazer", "Overcoat") else 0.0
        note = f"body {values['sleeve']}" + (
            f" {sleeve_adjust} to show {show_cuff_cm} cm of cuff" if sleeve_adjust else ""
        )
        add("sleeve", values["sleeve"] + sleeve_adjust, note, basis="sleeve")

        ratios = LENGTH_RATIOS.get(garment, {})
        style = length_style if length_style in ratios else next(iter(ratios), None)
        if style:
            add("length", height_cm * ratios[style], f"{style.lower()}, from the collar seam")

    if garment in ("Trousers", "Jeans"):
        low, high = RISES.get(rise, RISES["Mid"])
        add("rise", (low + high) / 2, f"{rise.lower()} rise, front, {low}-{high} cm range")
        inseam = values["inseam"] + BREAKS.get(trouser_break, 0.0)
        add("inseam", inseam, f"body {values['inseam']} for a {trouser_break.lower()}", basis="inseam")
        add("outseam", inseam + (low + high) / 2, "inseam plus rise", basis="inseam")

    return out


def spec_table(targets: list[Target]) -> list[dict[str, str]]:
    """Rows ready to render: the round measure, the flat equivalent, the reason."""
    rows = []
    for t in targets:
        rows.append({
            "Dimension": t.label,
            "Target": f"{t.value} cm" + (" *" if t.estimated else ""),
            "Flat": f"{t.flat} cm" if t.flat else "—",
            "Derived from": t.note,
        })
    return rows


def to_dict(body: Body) -> dict[str, float]:
    return asdict(body)
