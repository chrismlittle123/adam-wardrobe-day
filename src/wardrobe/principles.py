"""Guiding principles: the short rules used to invent outfits.

Deliberately not the style guide. The guide is a document you read once; these
are the eight or twelve lines you hold in your head while putting an outfit
together, so they are short, testable, and phrased as instructions.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

from .gemini_text import generate_text
from .philosophy import Answers, transcript
from .profile import Profile
from .prompts import appearance, physique

DEFAULT_PATH = Path("principles.toml")

GROUPS: tuple[str, ...] = ("Silhouette", "Colour", "Fabric", "Proportion", "Restraint", "Occasion")

SYSTEM = """You write guiding principles for one man's wardrobe.

A principle is not advice and not a description. It is a short instruction he can
apply while standing in front of a wardrobe, and it must be possible to look at
an outfit and say whether it obeys the principle or breaks it.

Good: "Never more than one loud thing. If the jacket is the event, everything
else is quiet."
Bad: "Embrace timeless elegance." That cannot be checked against an outfit.

Each principle: one imperative sentence, then one sentence of reason. Ground
every one in something he actually said or in his physical proportions. Do not
invent facts about his life."""


@dataclass
class Principle:
    id: str = ""
    text: str = ""
    reason: str = ""
    group: str = "Silhouette"

    def line(self) -> str:
        return f"{self.text} {self.reason}".strip()


@dataclass
class Principles:
    principles: list[Principle] = field(default_factory=list)
    path: Path = DEFAULT_PATH

    @classmethod
    def load(cls, path: Path | str = DEFAULT_PATH) -> "Principles":
        path = Path(path)
        if not path.is_file():
            return cls(path=path)
        raw = tomllib.loads(path.read_text())
        allowed = {f.name for f in fields(Principle)}
        rows = [Principle(**{k: v for k, v in r.items() if k in allowed})
                for r in raw.get("principles", [])]
        return cls(principles=rows, path=path)

    def save(self) -> Path:
        self.path.write_text(tomli_w.dumps({"principles": [asdict(p) for p in self.principles]}))
        return self.path

    def add(self, principle: Principle) -> Principle:
        principle.id = principle.id or self.unique_id(principle.text)
        self.principles.append(principle)
        return principle

    def remove(self, principle_id: str) -> None:
        self.principles = [p for p in self.principles if p.id != principle_id]

    def unique_id(self, text: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", (text or "principle").lower()).strip("-")[:36] or "principle"
        taken = {p.id for p in self.principles}
        if base not in taken:
            return base
        n = 2
        while f"{base}-{n}" in taken:
            n += 1
        return f"{base}-{n}"

    def by_group(self) -> dict[str, list[Principle]]:
        out: dict[str, list[Principle]] = {}
        for p in self.principles:
            out.setdefault(p.group, []).append(p)
        return out

    def as_prompt_block(self, limit: int = 14) -> str:
        if not self.principles:
            return ""
        return "\n".join(f"- {p.line()}" for p in self.principles[:limit])


def build_prompt(profile: Profile, answers: Answers, guide: str = "", count: int = 12) -> str:
    guide_block = f"\n# The style guide already written\n\n{guide[:6000]}\n" if guide.strip() else ""
    return f"""# The man

{physique(profile)}.
{appearance(profile)}.

# What he said

{transcript(answers)}
{guide_block}
# Your task

Write exactly {count} guiding principles, spread across these groups:
{", ".join(GROUPS)}.

Return them as a markdown list, one per line, in this exact format and nothing else:

GROUP | INSTRUCTION | REASON

Where GROUP is one of the groups above, INSTRUCTION is one imperative sentence,
and REASON is one sentence. No numbering, no headings, no other text."""


def parse(raw: str) -> list[Principle]:
    """Read back the GROUP | INSTRUCTION | REASON lines, forgiving stray markdown."""
    out: list[Principle] = []
    for line in raw.splitlines():
        line = line.strip().lstrip("-*0123456789. ").strip()
        if line.count("|") < 2:
            continue
        group, text, reason = (part.strip().strip("*_`") for part in line.split("|", 2))
        group = next((g for g in GROUPS if g.lower() == group.lower()), group.title() or "Silhouette")
        if text:
            out.append(Principle(text=text, reason=reason, group=group))
    return out


def generate(profile: Profile, answers: Answers, guide: str = "", count: int = 12) -> list[Principle]:
    raw = generate_text(build_prompt(profile, answers, guide, count), system=SYSTEM, temperature=0.7)
    parsed = parse(raw)
    if not parsed:
        raise ValueError(f"Could not read any principles out of the reply:\n\n{raw[:500]}")
    return parsed
