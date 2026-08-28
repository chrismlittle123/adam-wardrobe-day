"""Turn a subject profile plus an outfit idea into a prompt Gemini can dress.

The whole point of the profile is that the model keeps getting told the same
true things about the man: his height, his build, his colouring. Left to itself
an image model will quietly hand a lean 1.76 m subject the proportions of a
2 m fashion-week mannequin, so the physique line is repeated as an instruction,
not just as description.
"""

from __future__ import annotations

from .profile import Profile

SHOTS: dict[str, str] = {
    "Full length": (
        "Full-length shot, head to feet, standing square to the camera. "
        "The entire outfit including the shoes is in frame with room above the head"
    ),
    "Three quarter": "Three-quarter shot, framed from mid-thigh up",
    "Upper body": "Upper-body shot, framed from the waist up",
    "Detail": "Close detail shot of the upper garment, fabric and stitching filling the frame",
}

BACKGROUNDS: dict[str, str] = {
    "White studio": "Plain seamless pure white studio background",
    "Warm grey studio": "Plain seamless warm mid-grey studio background",
    "Street": "Blurred European city street behind him, shallow depth of field, background well out of focus",
    "Interior": "Warm domestic interior behind him, softly out of focus",
}

MEASUREMENT_LABELS: dict[str, str] = {
    "chest_cm": "chest",
    "waist_cm": "waist",
    "inseam_cm": "inseam",
    "shoulder_cm": "shoulder width",
    "shoe_eu": "shoe size EU",
}


def physique(profile: Profile) -> str:
    """One sentence of ground truth about the body the clothes have to fit."""
    s = profile.subject
    parts = [p for p in (s.height_metric and f"{s.height_metric} ({s.height_imperial})", s.build) if p]
    if s.body_fat_pct:
        parts.append(f"around {s.body_fat_pct}% body fat")
    for key, value in profile.measurements.known().items():
        label = MEASUREMENT_LABELS.get(key, key)
        parts.append(f"{label} {value}" + ("" if key == "shoe_eu" else " cm"))
    return ", ".join(parts)


def appearance(profile: Profile) -> str:
    """One sentence of ground truth about colouring and features."""
    s = profile.subject
    bits = []
    if s.skin_tone:
        bits.append(f"{s.skin_tone} skin ({s.skin_tone_hex})")
    bits += [b for b in (s.hair, s.facial_hair, s.eyes and f"{s.eyes} eyes", s.details) if b]
    return ", ".join(bits)


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

    lines = [
        "Ultra photorealistic, high-definition full-colour fashion photograph of "
        "the man in the reference image.",
        "",
        f"THE MAN. {body}. {look}.",
        "",
        "Keep his face, head shape, hair, skin tone and facial hair exactly as the "
        "reference image. This must read as the same person. Do not restyle his face.",
        f"Keep his body exactly as described: he is {s.height_metric} and "
        f"{s.build.lower() or 'lean'}, so the clothes hang on a lean frame. Do not "
        "elongate him into a fashion-model silhouette and do not broaden him.",
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
