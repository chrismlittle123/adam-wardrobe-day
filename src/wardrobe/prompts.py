"""Turn a subject profile plus an outfit idea into a prompt Gemini can dress.

The whole point of the profile is that the model keeps getting told the same
true things about the man: his height, his build, his colouring. Left to itself
an image model will quietly hand a lean 1.80 m subject the proportions of a
2 m fashion-week mannequin, so the physique line is repeated as an instruction,
not just as description.
"""

from __future__ import annotations

from .text import count_of, plural

from .fitspec import LABELS
from .profile import Profile

# Alphabetical, because these fill a dropdown. The sensible default is chosen by
# name where they are used, not by being first in the list.
DEFAULT_SHOT = "Full length"
DEFAULT_BACKGROUND = "White studio"

SHOTS: dict[str, str] = {
    "Detail": "Close detail shot of the upper garment, fabric and stitching filling the frame",
    "Full length": (
        "Full-length shot, head to feet, standing square to the camera. "
        "The entire outfit including the shoes is in frame with room above the head"
    ),
    "Three quarter": "Three-quarter shot, framed from mid-thigh up",
    "Upper body": "Upper-body shot, framed from the waist up",
}

BACKGROUNDS: dict[str, str] = {
    "Interior": "Warm domestic interior behind him, softly out of focus",
    "Street": "Blurred European city street behind him, shallow depth of field, background well out of focus",
    "Warm grey studio": "Plain seamless warm mid-grey studio background",
    "White studio": "Plain seamless pure white studio background",
}

CIRCUMFERENCE_FREE = {"shoe_eu"}


def physique(profile: Profile) -> str:
    """One sentence of ground truth about the body the clothes have to fit."""
    s = profile.subject
    parts = [p for p in (s.height_metric and f"{s.height_metric} ({s.height_imperial})", s.build) if p]
    if s.body_fat_pct:
        parts.append(f"around {s.body_fat_pct}% body fat")
    # Proportion, not size. An image model given only a height draws average
    # arms every time, and then the sleeves in the picture are not his sleeves.
    if s.arms:
        parts.append(f"{s.arms} arms for his height")
    for key, value in profile.measurements.measured().items():
        label = LABELS.get(key, key.replace("_", " "))
        parts.append(f"{label.lower()} {value:g}" + ("" if key in CIRCUMFERENCE_FREE else " cm"))
    return ", ".join(parts)


def appearance(profile: Profile) -> str:
    """One sentence of ground truth about colouring and features."""
    s = profile.subject
    bits = []
    if s.skin_tone:
        bits.append(f"{s.skin_tone} skin ({s.skin_tone_hex})")
    bits += [b for b in (s.hair, s.facial_hair, s.eyes and f"{s.eyes} eyes", s.details) if b]
    return ", ".join(bits)


def description_of(profile: Profile) -> str:
    """His own description, if one has been written. Prose, not a list."""
    return (profile.subject.description or "").strip()


def build_prompt(
    profile: Profile,
    outfit: str,
    *,
    shot: str = "Full length",
    background: str = "White studio",
    extra: str = "",
) -> str:
    """Assemble the full prompt. Reads top to bottom: who, then what, then how."""
    s = profile.subject
    body = physique(profile)
    look = appearance(profile)

    prose = description_of(profile)
    lines = [
        "Ultra photorealistic, high-definition full-colour fashion photograph of "
        "the man in the reference image.",
        "",
        f"THE MAN. {body}. {look}.",
    ]
    if prose:
        lines.append(prose)
    lines += [
        "",
        "Keep his face, head shape, hair, skin tone and facial hair exactly as the "
        "reference image. This must read as the same person. Do not restyle his face.",
        f"Keep his body exactly as described: he is {s.height_metric} and "
        f"{s.build.lower() or 'lean'}, so the clothes hang on a lean frame. Do not "
        "elongate him into a fashion-model silhouette and do not broaden him."
        + (f" His arms are {s.arms} for his height: with his hands at his sides the "
           "sleeves should sit accordingly, and the cuffs must not ride up his "
           "forearms." if s.arms else ""),
        "",
        f"THE OUTFIT. {outfit.strip()}",
    ]

    if profile.style.direction:
        lines.append(f"Standing style direction: {profile.style.direction}")
    if profile.style.avoid:
        lines.append(f"Avoid: {profile.style.avoid}")
    if extra.strip():
        lines.append(extra.strip())

    lines += [
        "",
        f"THE SHOT. {SHOTS.get(shot, SHOTS['Full length'])}. "
        f"{BACKGROUNDS.get(background, BACKGROUNDS['White studio'])}. "
        "Soft even professional studio lighting, sharp focus throughout the garments, "
        "natural skin texture, visible weave and drape in the fabric, true-to-life "
        "colour, 50mm lens, high-resolution editorial photograph.",
        "",
        "No text, no watermark, no logos, no collage, no extra people, no mirror.",
    ]
    return "\n".join(lines)


def build_outfit_prompt(
    profile: Profile,
    garments: list[str],
    *,
    shot: str = "Full length",
    background: str = "White studio",
    principles: str = "",
    photo_count: int = 0,
    extra: str = "",
) -> str:
    """Prompt for a specific outfit assembled from inventory items.

    When garment photographs are supplied they lead, because "green jacket"
    produces a different jacket every time and the photograph produces that one.
    The model is told explicitly which reference is the man and which are cloth,
    otherwise it happily puts the jacket's photographer in the picture.
    """
    outfit = "\n".join(f"- {g}" for g in garments) if garments else "…"
    notes: list[str] = []
    if photo_count:
        notes.append(
            f"Reference image 1 is the man. The next "
            f"{plural(photo_count, 'reference image')} "
            f"{'is' if photo_count == 1 else 'are'} the actual "
            f"{count_of(photo_count, 'garment')}. Reproduce "
            f"{'it' if photo_count == 1 else 'them'} faithfully: the exact colour, "
            "cloth, pattern and cut. Take only the clothing, never the background, "
            "the lighting or any person in the picture."
        )
    if principles.strip():
        notes.append("Follow these wardrobe principles:\n" + principles.strip())
    if extra.strip():
        notes.append(extra.strip())

    return build_prompt(
        profile,
        f"He is wearing exactly these pieces and nothing else:\n{outfit}",
        shot=shot,
        background=background,
        extra="\n\n".join(notes),
    )
