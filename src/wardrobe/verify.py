"""Look at a generated photograph and say whether it is actually of him.

An image model asked for a man in specific clothes on a white background will
usually produce one, and occasionally produce a different man, in a room, in
clothes it preferred. Nothing downstream can tell: a PNG is a PNG. So every look
is shown back to Gemini with the references it was built from and asked three
questions.

  Is this the same face?    The portrait is the point. A look that is not of him
                            is not a look, it is a stock photo.
  Is the background right?  White means white and empty. Not a wall, not a
                            shadow gradient, not a chair at the edge of frame.
  Are these the garments?   Compared against the catalogue shot of each piece,
                            not against the words, because the words were what
                            the model was already given and ignored.

A failure is not thrown away. The picture goes back with the references and a
correction naming only what was wrong, which is a far smaller job than drawing
it again from nothing, and the face usually survives it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from google.genai import errors, types

from .gemini_image import (GeminiImageError, Settings, _part_from_image,
                           build_client, generate_images)

DEFAULT_JUDGE_MODEL = "gemini-2.5-pro"

# Three attempts: the first draw, and two chances to be corrected. Past that the
# model is not converging and another go is spending money to no purpose.
MAX_ATTEMPTS = 3

SYSTEM = """You are checking a generated fashion photograph against the references it was built from.

You are not judging whether it is a good photograph. You are answering three factual questions, strictly, and a thing you are unsure about is a failure.

Answer with JSON and nothing else:

{"face": {"ok": true|false, "why": "one short sentence"},
 "background": {"ok": true|false, "why": "one short sentence"},
 "garments": {"ok": true|false, "why": "one short sentence"}}"""


@dataclass
class Report:
    """What the judge saw. `ok` only when all three hold."""

    face: bool = False
    background: bool = False
    garments: bool = False
    notes: dict[str, str] = field(default_factory=dict)
    raw: str = ""

    @property
    def ok(self) -> bool:
        return self.face and self.background and self.garments

    @property
    def failures(self) -> list[str]:
        return [name for name, held in (("face", self.face),
                                        ("background", self.background),
                                        ("garments", self.garments)) if not held]

    def summary(self) -> str:
        if self.ok:
            return "his face, a white background, and the garments as photographed"
        return "; ".join(f"{name}: {self.notes.get(name, 'wrong')}" for name in self.failures)

    def correction(self, background: str = "plain seamless pure white, empty") -> str:
        """What to tell the model, naming only what was wrong."""
        asks: list[str] = []
        if not self.face:
            asks.append(
                "The face is wrong. Reference image 1 is the man. Reproduce his face, "
                "head shape, hair, facial hair and skin tone exactly from it. This must "
                "be recognisably the same person and not merely a similar one.")
        if not self.background:
            asks.append(
                f"The background is wrong. It must be {background}: no wall, no floor "
                "line, no horizon, no furniture, no props, no shadow gradient and no "
                "texture. Nothing behind him at all.")
        if not self.garments:
            asks.append(
                "The garments are wrong. The reference images after the first are the "
                "actual garments. Reproduce each one exactly: its colour, its cloth, "
                "its cut and its length. Do not substitute a similar piece.")
        told = " ".join(asks)
        return (f"Correct this photograph. Keep everything that is already right and "
                f"change only what is named. {told}\n\nReturn the corrected photograph.")


def _questions(garments: list[str], background: str) -> str:
    listed = "\n".join(f"- {g}" for g in garments) or "- (none named)"
    return f"""The first image is the generated photograph being checked.
The second image is the reference portrait of the man.
Every image after that is a reference photograph of one garment he should be wearing.

FACE. Compare the man in the first image with the portrait. Same person, or not? Judge the bone structure, the hair, the facial hair and the skin tone. A different man who looks similar is a failure.

BACKGROUND. The background should be: {background}. It must be completely empty. A wall, a floor, a horizon line, furniture, a prop, a shadow falling on a surface behind him, or any texture at all is a failure. Only the man and his clothes should be in the frame.

GARMENTS. He should be wearing exactly these, and nothing else:
{listed}

Compare each against its reference photograph. Wrong colour, wrong cloth, wrong cut, a missing piece or an added piece is a failure."""


def _read(text: str) -> Report:
    """Pull the verdict out, tolerating a model that wraps JSON in prose."""
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise GeminiImageError(f"The judge did not answer in JSON:\n\n{text[:400]}")
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError as exc:
        raise GeminiImageError(f"Could not read the judge's answer: {exc}") from exc

    report = Report(raw=text)
    for key in ("face", "background", "garments"):
        block = data.get(key) or {}
        if isinstance(block, bool):        # a terser model than we asked for
            block = {"ok": block, "why": ""}
        setattr(report, key, bool(block.get("ok")))
        report.notes[key] = str(block.get("why", "")).strip()
    return report


def inspect(image: Path, portrait: Path, garment_photos: list[Path], *,
            garments: list[str], background: str = "plain seamless pure white, empty",
            settings: Settings | None = None) -> Report:
    """Ask Gemini whether the photograph is of him, on white, in those clothes."""
    settings = settings or Settings.from_env(DEFAULT_JUDGE_MODEL)
    client = build_client(settings)

    parts = [_part_from_image(image), _part_from_image(portrait)]
    parts += [_part_from_image(p) for p in garment_photos]
    parts.append(types.Part.from_text(text=_questions(garments, background)))

    try:
        response = client.models.generate_content(
            model=settings.model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM,
                temperature=0.0,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
    except errors.APIError as exc:
        raise GeminiImageError(f"The judge could not be reached: {exc}") from exc
    return _read(response.text or "")


@dataclass
class Attempt:
    """One go at the picture, and what the judge made of it."""

    path: Path
    report: Report
    corrected: bool = False


def ensure(prompt: str, *, out_prefix: Path, portrait: Path,
           garment_photos: list[Path], garments: list[str],
           background: str = "plain seamless pure white, empty",
           attempts: int = MAX_ATTEMPTS, settings: Settings | None = None,
           on_step=None) -> tuple[Path | None, list[Attempt]]:
    """Draw it, check it, and correct it until it passes or the attempts run out.

    Returns the accepted picture and every attempt made, so a caller can show
    the failures rather than pretending the first one was fine. The picture is
    None when nothing passed: better to say so than to hand back a photograph of
    a different man in a kitchen.
    """
    history: list[Attempt] = []
    references = [portrait, *garment_photos]
    current_prompt, current_refs = prompt, references

    for n in range(1, max(1, attempts) + 1):
        written = generate_images(
            current_prompt,
            out_prefix=out_prefix if n == 1 else out_prefix.with_name(f"{out_prefix.name}-fix{n - 1}"),
            reference_images=current_refs,
            count=1,
            settings=settings,
        )
        if not written:
            break
        picture = written[0]
        report = inspect(picture, portrait, garment_photos,
                         garments=garments, background=background)
        history.append(Attempt(path=picture, report=report, corrected=n > 1))
        if on_step:
            on_step(n, picture, report)
        if report.ok:
            return picture, history
        # Correct the picture itself rather than redrawing from nothing: the
        # face is usually the part that survived, and redrawing risks losing it.
        current_prompt = report.correction(background)
        current_refs = [picture, portrait, *garment_photos]

    return None, history
