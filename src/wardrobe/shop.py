"""The product page: a photograph of the exact garment, and the words for it.

Nobody buys from a spreadsheet row reading "Overcoat, camel, £420". They buy
from a photograph and a paragraph, so the shopping guide generates both: a
studio product shot of that specific garment, and copy that says what the cloth
is, how it is cut, and which size to look for on his measurements.

The size is the part a real shop cannot tell him. Zara knows what it made; only
this knows that his blazer needs to measure 106 cm round the chest.
"""

from __future__ import annotations

from pathlib import Path

from . import fitspec, paths
from .gemini_image import Settings, generate_images
from .gemini_text import generate_text
from .inventory import Inventory, Item
from .profile import Profile

# Garment types the fit engine can produce a target for.
SPEC_GARMENTS = set(fitspec.EASE)

COPY_SYSTEM = """You write product copy for one man's shopping list.

You are describing a garment he has decided he wants but does not own yet, so
the copy has to be specific enough to recognise the right one on a rail or in a
listing. Say what the cloth is and how it behaves, how the garment is cut, and
what to check before buying. Name the failure mode: the thing that makes the
wrong version of this garment wrong.

You are not selling. No superlatives, no "elevate", no "essential", no
"timeless", no "wardrobe staple". British English. Plain words.

Return markdown with exactly these sections and nothing else:

**The cloth** — one short paragraph on fabric, weight and how it wears.
**The cut** — one short paragraph on shape, and how it should sit on him.
**What to check** — three or four bullets, each a specific thing to look at
before buying, in the order you would look at them.
**Wrong version** — one sentence naming how this garment most often goes wrong."""


def size_targets(profile: Profile, item: Item, *, fit: str = "Regular") -> list[fitspec.Target]:
    """The finished measurements to look for in this garment, on his body."""
    if item.garment not in SPEC_GARMENTS:
        return []
    return fitspec.target_spec(
        item.garment, profile.measurements, profile.subject.height_cm,
        fit=fit, build=profile.subject.build, arms=profile.subject.arms,
    )


def size_line(profile: Profile, item: Item) -> str:
    """The targets as one line, for the product card."""
    targets = size_targets(profile, item)
    keep = ("chest", "waist", "shoulder", "sleeve", "length", "inseam", "ankle")
    return " · ".join(f"{t.label} {t.value:g}" for t in targets if t.key in keep) or ""


def copy_prompt(profile: Profile, item: Item, principles: str = "") -> str:
    subject = profile.subject
    targets = size_targets(profile, item)
    measurements = ("\n".join(f"- {t.label}: {t.value:g} cm ({t.note})" for t in targets)
                    or "- not applicable to this garment")
    labels = item.size_line() or "no size recorded yet"
    return f"""# The garment

{item.name or item.garment}
Type: {item.garment}
Colour: {item.colour_line or "unspecified"}
Cloth: {item.fabric or "unspecified"}
Size label he is after: {labels}
His own note: {item.description or "none"}

# The man wearing it

{subject.height_metric}, {subject.build}, around {subject.body_fat_pct}% body fat.
{subject.skin_tone} skin ({subject.skin_tone_hex}).

# The finished measurements it needs to hit

{measurements}

{f"# Standing principles{chr(10)}{chr(10)}{principles}{chr(10)}" if principles.strip() else ""}
# Your task

Write the copy for this garment, in the format given."""


def generate_copy(profile: Profile, item: Item, principles: str = "") -> str:
    return generate_text(copy_prompt(profile, item, principles),
                         system=COPY_SYSTEM, temperature=0.6)


# Shared by both prompts: what a catalogue shot looks like, said the way the
# model reliably follows.
PRESENTATION = (
    "Ghost mannequin presentation: the garment holds its shape as if worn, with "
    "no person, no mannequin and no hanger visible. Centred, front view, filling "
    "the frame with even margins.\n\n"
    "Plain seamless pure white background. Soft even studio lighting from both "
    "sides, a soft natural shadow beneath. Sharp focus throughout, true-to-life "
    "colour, visible weave and texture in the cloth, natural drape at the seams. "
    "High-resolution catalogue photograph in the style of a good online shop.\n\n"
    "No text, no watermark, no logos, no labels, no props, no person, no hands, "
    "no second garment, no collage."
)


def photo_prompt(item: Item) -> str:
    """A catalogue shot built from the description, when there is no photograph.

    Product photography is a genre with rules, and the model follows them better
    when they are named: one garment, centred, seamless white, soft even light.
    """
    described = " ".join(b for b in (item.colour_line, item.fabric, item.garment.lower()) if b)
    detail = f" {item.description.strip()}" if item.description.strip() else ""
    return (
        f"E-commerce product photograph of a single {described}, and nothing else."
        f"{detail}\n\n{PRESENTATION}"
    )


def restage_prompt(item: Item) -> str:
    """A catalogue shot of the garment in the reference photograph.

    A different job from drawing one from a description, and the difference has
    to be stated or the model treats the photograph as inspiration and invents a
    nicer garment. This is a restaging: the same piece, the same cloth, the same
    cut, the same wear, moved onto a white background.
    """
    described = " ".join(b for b in (item.colour_line, item.fabric, item.garment.lower()) if b)
    detail = f"\n\nWhat it is: {item.description.strip()}" if item.description.strip() else ""
    return (
        "Photograph THE EXACT GARMENT in the reference image, restaged as an "
        "e-commerce product shot. This is not a new garment inspired by the "
        f"reference; it is that {described or item.garment.lower()}, the same "
        "piece, photographed again.\n\n"
        "Reproduce it faithfully: its exact colour and shade, its cloth and weave, "
        "its cut and proportions, its collar, buttons, pockets, seams and any "
        "pattern, exactly as they appear. Do not tidy it, do not restyle it, do "
        "not make it smarter or newer than it is. If it is faded or creased or "
        "worn, it stays that way.\n\n"
        "Take only the garment from the reference. Discard the background, the "
        "room, the lighting, the hanger and any person wearing it."
        f"{detail}\n\n{PRESENTATION}"
    )


def generate_photo(item: Item, *, count: int = 1) -> list[Path]:
    """A catalogue shot: restaged from his photograph if there is one, drawn from
    the description if there is not."""
    from_photo = item.has_photo
    return generate_images(
        restage_prompt(item) if from_photo else photo_prompt(item),
        out_prefix=paths.products() / item.id,
        reference_images=[Path(item.photo)] if from_photo else None,
        count=count,
        settings=Settings.from_env(),
    )


def refresh(profile: Profile, item: Item, inventory: Inventory, *,
            principles: str = "", photo: bool = True, words: bool = True) -> Item:
    """Fill in whichever of the two is missing, and persist."""
    if words:
        item.product_copy = generate_copy(profile, item, principles)
    if photo:
        written = generate_photo(item)
        if written:
            item.product_photo = str(written[0])
    inventory.update(item)
    inventory.save()
    return item


def to_buy(inventory: Inventory, *, starred_only: bool = False) -> list[Item]:
    """The shopping list: wanted pieces, starred first, then by name."""
    items = [i for i in inventory.items if i.status == "aspirational"]
    if starred_only:
        items = [i for i in items if i.starred]
    return sorted(items, key=lambda i: (not i.starred, i.name or i.garment))
