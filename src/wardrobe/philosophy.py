"""Answers to the style questionnaire, and the guide they turn into.

Answers live in style-answers.toml, one key per question id, so the file stays
readable and diffable. The guide is synthesised by Gemini from the answers plus
the subject profile and written to STYLE-GUIDE.md.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

from .gemini_text import generate_text
from .profile import Profile
from .prompts import appearance, physique
from .questions import ALL_QUESTIONS, SECTIONS, Question

DEFAULT_ANSWERS_PATH = Path("style-answers.toml")
DEFAULT_GUIDE_PATH = Path("STYLE-GUIDE.md")

SYSTEM = """You are a personal stylist writing a wardrobe style guide for one man.

You are opinionated and specific. You name garments, colours, cuts, fabrics and
rough price bands. You never pad. You never write marketing copy. You do not
hedge with "consider" and "perhaps"; you make the call and give the reason in a
short clause.

Two hard rules:
1. Everything must trace back to something the man actually said, or to his
   physical profile. Do not invent facts about his life, his job, his budget or
   what he owns.
2. Where an answer is missing and it matters, say so plainly in the Open
   questions section rather than filling the gap with a guess.

Write British English. Use markdown. No preamble, no sign-off, no emoji.

If he has allocated points across practicality, comfort, aesthetics and cost, that allocation is the tie-breaker. Whenever two recommendations conflict, side with whichever he scored higher, and say so in the clause. A man who put 8 on aesthetics and 2 on cost is told to buy the better coat; one who scored it the other way is not."""

GUIDE_SHAPE = """Write the guide with exactly these top-level sections:

# Style Guide: {name}

## The thesis
One short paragraph. What this wardrobe is, in plain words. If you cannot say it
in five sentences it is not a thesis.

## What it should say
Broken down by the contexts he actually named. One short paragraph each.

## What it must never say
The anti-goals, as a short list. Blunt.

## Palette
The colours this wardrobe is built from. Give each a name and a hex code, and
group them as base, mid, and accent. Ground the choices in his skin tone
({skin_hex}, {skin_words}) and in the colours he told you he feels good in. Say
explicitly which colours to stop buying.

## Silhouette and fit
How things should sit on a {height} frame at roughly {body_fat}% body fat, given
the fit preferences and the fit problems he described. Be concrete: rise, break,
shoulder, sleeve, where volume goes and where it does not.

## Fabric and texture
What the wardrobe is made of, and what to avoid, accounting for his climate and
how much upkeep he will genuinely do.

## The core wardrobe
The pieces this wardrobe is built from, as a table with columns: Piece, Detail,
Why. Cover tops, trousers, outerwear, shoes. Include anything he already owns
and loves, marked as kept.

## Uniforms
Between five and eight named, repeatable outfits, each mapped to a context he
named. Give each a short name and list the pieces. These should combine from the
core wardrobe, not require new one-offs.

## Retire
What to remove from the current wardrobe, and the reason for each. Only name
things he actually mentioned owning.

## Shopping list
Prioritised, numbered, most urgent first. Each line: the piece, what to look for,
a rough price band, and what it unlocks. Respect the budget he gave and any
deadline he named.

## Rules of thumb
Six to ten short lines he can remember in a shop.

## Open questions
What you still need to know, and why each one would change the guide."""


@dataclass
class Answers:
    values: dict[str, str] = field(default_factory=dict)
    path: Path = DEFAULT_ANSWERS_PATH

    @classmethod
    def load(cls, path: Path | str = DEFAULT_ANSWERS_PATH) -> "Answers":
        path = Path(path)
        if not path.is_file():
            return cls(path=path)
        raw = tomllib.loads(path.read_text())
        return cls(values=dict(raw.get("answers", {})), path=path)

    def save(self) -> Path:
        kept = {k: v.strip() for k, v in self.values.items() if v and v.strip()}
        self.path.write_text(tomli_w.dumps({"answers": kept}))
        self.values = kept
        return self.path

    def get(self, question_id: str) -> str:
        return self.values.get(question_id, "")

    def answered(self, questions=ALL_QUESTIONS) -> list[Question]:
        return [q for q in questions if self.get(q.id)]

    def progress(self, core_only: bool = False) -> tuple[int, int]:
        pool = [q for q in ALL_QUESTIONS if q.core] if core_only else list(ALL_QUESTIONS)
        return len(self.answered(pool)), len(pool)

    def is_empty(self) -> bool:
        return not any(v.strip() for v in self.values.values())


def transcript(answers: Answers) -> str:
    """The answered questions, grouped by section, as plain text for the model."""
    blocks: list[str] = []
    for section in SECTIONS:
        answered = [q for q in section.questions if answers.get(q.id)]
        if not answered:
            continue
        lines = [f"## {section.title}"]
        for q in answered:
            lines.append(f"\nQ: {q.prompt}\nA: {answers.get(q.id)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) if blocks else "(No questions answered yet.)"


def unanswered(answers: Answers) -> list[Question]:
    return [q for q in ALL_QUESTIONS if not answers.get(q.id)]


def build_guide_prompt(profile: Profile, answers: Answers) -> str:
    s = profile.subject
    gaps = unanswered(answers)
    gap_text = (
        "\n".join(f"- {q.prompt}" for q in gaps) if gaps else "(All questions answered.)"
    )
    shape = GUIDE_SHAPE.format(
        name=s.name,
        skin_hex=s.skin_tone_hex,
        skin_words=s.skin_tone or "not recorded",
        height=s.height_metric or "unrecorded",
        body_fat=s.body_fat_pct or "unrecorded",
    )
    return f"""# The man

{physique(profile)}.
{appearance(profile)}.

# What he said

{transcript(answers)}

# Not yet answered

{gap_text}

# Your task

{shape}"""


def synthesise_guide(
    profile: Profile,
    answers: Answers,
    *,
    out_path: Path = DEFAULT_GUIDE_PATH,
    temperature: float = 0.6,
) -> tuple[Path, str]:
    """Generate the guide and write it to disk. Returns (path, markdown)."""
    markdown = generate_text(
        build_guide_prompt(profile, answers), system=SYSTEM, temperature=temperature
    )
    out_path.write_text(markdown + "\n")
    return out_path, markdown
