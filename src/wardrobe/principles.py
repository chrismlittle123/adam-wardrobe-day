"""Guiding principles: the short rules used to invent outfits.

Deliberately not the style guide. The guide is a document you read once; these
are the ten or so lines you hold in your head while putting an outfit together,
so they are short, testable, and phrased as instructions.

The model does not write the set, it offers five at a time as inspiration and
the good ones get confirmed. Generating ten in one go produces four that are true
and six that are padding, and padding in a list this short is worse than a gap.

Suggestions and confirmed principles live in the same file under a status, so a
round of ideas survives a refresh. Generating replaces the pending suggestions
rather than adding to them: there are never more than one batch on the table.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

from . import paths

from .gemini_text import generate_text
from .philosophy import Answers, transcript
from .profile import Profile
from .prompts import appearance, physique

GROUPS: tuple[str, ...] = ("Colour", "Fabric", "Occasion", "Proportion",
                           "Restraint", "Silhouette")

# Five suggestions a round; about ten confirmed is a set you can hold in mind.
BATCH = 5
TARGET = 10

SUGGESTED, CONFIRMED = "suggested", "confirmed"

SYSTEM = """You write guiding principles for one man's wardrobe.

A principle is not advice and not a description. It is a short instruction he can
apply while standing in front of a wardrobe, and it must be possible to look at
an outfit and say whether it obeys the principle or breaks it.

Good: "Never more than one loud thing. If the jacket is the event, everything
else is quiet."
Bad: "Embrace timeless elegance." That cannot be checked against an outfit.

Each principle: one imperative sentence, then one sentence of reason. Ground
every one in something he actually said or in his physical proportions. Do not
invent facts about his life.

If he has allocated points across practicality, comfort, aesthetics and cost, that allocation is the tie-breaker. Whenever two recommendations conflict, side with whichever he scored higher, and say so in the clause. A man who put 8 on aesthetics and 2 on cost is told to buy the better coat; one who scored it the other way is not."""


def key(text: str) -> str:
    """Two principles are the same principle if they say the same words."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


@dataclass
class Principle:
    id: str = ""
    text: str = ""
    reason: str = ""
    group: str = "Silhouette"
    status: str = CONFIRMED

    def line(self) -> str:
        return f"{self.text} {self.reason}".strip()


@dataclass
class Principles:
    principles: list[Principle] = field(default_factory=list)
    path: Path = field(default_factory=paths.principles)

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Principles":
        path = Path(path) if path else paths.principles()
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

    def confirmed(self) -> list[Principle]:
        return [p for p in self.principles if p.status != SUGGESTED]

    def suggested(self) -> list[Principle]:
        return [p for p in self.principles if p.status == SUGGESTED]

    def find_text(self, text: str) -> Principle | None:
        k = key(text)
        return next((p for p in self.principles if key(p.text) == k), None)

    def add(self, principle: Principle) -> Principle:
        """Idempotent by text. Seeding twice, or confirming a principle you already
        hold, must not double it up."""
        existing = self.find_text(principle.text)
        if existing is not None:
            if existing.status == SUGGESTED and principle.status == CONFIRMED:
                existing.status = CONFIRMED
            return existing
        principle.id = principle.id or self.unique_id(principle.text)
        self.principles.append(principle)
        return principle

    def offer(self, ideas: list[Principle]) -> list[Principle]:
        """Put a fresh batch on the table, replacing any pending suggestions.
        Anything already confirmed is not offered back."""
        self.principles = [p for p in self.principles if p.status != SUGGESTED]
        held = {key(p.text) for p in self.principles}
        for idea in ideas:
            if key(idea.text) in held:
                continue
            held.add(key(idea.text))
            self.principles.append(Principle(id=self.unique_id(idea.text), text=idea.text,
                                             reason=idea.reason, group=idea.group,
                                             status=SUGGESTED))
        return self.suggested()

    def confirm(self, principle_id: str) -> Principle | None:
        p = next((p for p in self.principles if p.id == principle_id), None)
        if p is not None:
            p.status = CONFIRMED
        return p

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
        """Confirmed only. Suggestions are not principles until you say so."""
        out: dict[str, list[Principle]] = {}
        for p in self.confirmed():
            out.setdefault(p.group, []).append(p)
        return out

    def as_prompt_block(self, limit: int = 14) -> str:
        """What the outfit prompts see: confirmed only, never a pending idea."""
        kept = self.confirmed()
        if not kept:
            return ""
        return "\n".join(f"- {p.line()}" for p in kept[:limit])


def build_prompt(profile: Profile, answers: Answers, guide: str = "",
                 count: int = BATCH, existing: list[Principle] | None = None) -> str:
    guide_block = f"\n# The style guide already written\n\n{guide[:6000]}\n" if guide.strip() else ""
    kept = existing or []
    kept_block = ""
    if kept:
        lines = "\n".join(f"- [{p.group}] {p.text}" for p in kept)
        kept_block = (
            f"\n# Principles he has already kept\n\n{lines}\n\n"
            "Do not repeat any of these, and do not restate one in different words. "
            "Cover ground they do not.\n"
        )
    return f"""# The man

{physique(profile)}.
{appearance(profile)}.

# What he said

{transcript(answers)}
{guide_block}{kept_block}
# Your task

Suggest exactly {count} guiding principles, drawn from these groups:
{", ".join(GROUPS)}.

These are suggestions, not a finished set. He will keep the ones that ring true
and discard the rest, so make each one earn its place on its own rather than
padding towards a number.

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


def generate(profile: Profile, answers: Answers, guide: str = "", count: int = BATCH,
             existing: list[Principle] | None = None) -> list[Principle]:
    """A batch of suggestions. Nothing is saved; the caller keeps what it likes."""
    raw = generate_text(build_prompt(profile, answers, guide, count, existing),
                        system=SYSTEM, temperature=0.85)
    parsed = parse(raw)
    if not parsed:
        raise ValueError(f"Could not read any principles out of the reply:\n\n{raw[:500]}")
    return parsed
