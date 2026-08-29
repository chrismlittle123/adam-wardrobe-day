"""Talking to the guide, rather than regenerating it.

A style guide written in one shot is a first draft that happens to be finished.
The useful version is the one argued with: "the palette is too safe", "drop the
uniforms section", "why navy and not charcoal". So the guide is a document you
can edit by hand and a document you can talk to, and both write to the same file.

The model answers in prose and, when it has actually changed something, follows
with the complete revised guide after a marker. Complete, never a diff: the file
is replaced wholesale, and a model asked for a patch will produce something that
looks like one and is not. When he only asked a question, no marker comes back
and the guide is left alone, which is what makes it safe to think out loud here.

Every revision copies the previous guide into .guide-versions first, so nothing
said in a chat window can lose an afternoon's work.
"""

from __future__ import annotations

import datetime as dt
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

from . import paths
from .gemini_text import generate_text
from .philosophy import Answers, transcript
from .profile import Profile
from .prompts import appearance, physique

MARKER = "===GUIDE==="
STAMP = "%Y%m%d-%H%M%S"

SYSTEM = f"""You are revising a wardrobe style guide together with the man it is for.

He will ask questions about it and ask for changes to it. Answer in British
English, in one short paragraph, plainly. No preamble, no restating his request
back at him, no "certainly".

When he asks a QUESTION, answer it and stop. Do not output the guide.

When he asks for a CHANGE, make it, say in one or two sentences what you changed
and what it cost, then output a line containing only {MARKER}, then the COMPLETE
revised guide in markdown.

The guide after the marker replaces the file wholesale, so it must always be the
entire document, never a fragment and never a diff. Keep every section he has
not asked you to touch exactly as it was, word for word.

Two standing rules. Everything must trace back to something he actually said or
to his physical proportions; do not invent facts about his life. And where he
asks for something that will not work on him, say so in one clause and then do
it anyway, because it is his wardrobe."""


@dataclass
class Message:
    role: str = "user"          # user or guide
    text: str = ""
    at: str = ""
    revised: bool = False       # did this exchange rewrite the guide

    @property
    def when(self) -> str:
        try:
            return f"{dt.datetime.fromisoformat(self.at):%d %b, %H:%M}"
        except ValueError:
            return ""


@dataclass
class Conversation:
    messages: list[Message] = field(default_factory=list)
    path: Path = field(default_factory=paths.guide_chat)

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Conversation":
        path = Path(path) if path else paths.guide_chat()
        if not path.is_file():
            return cls(path=path)
        allowed = {f.name for f in fields(Message)}
        raw = tomllib.loads(path.read_text())
        return cls(
            messages=[Message(**{k: v for k, v in row.items() if k in allowed})
                      for row in raw.get("messages", [])],
            path=path,
        )

    def save(self) -> Path:
        self.path.write_text(tomli_w.dumps({"messages": [asdict(m) for m in self.messages]}))
        return self.path

    def add(self, role: str, text: str, revised: bool = False) -> Message:
        message = Message(role=role, text=text,
                          at=dt.datetime.now().isoformat(timespec="seconds"),
                          revised=revised)
        self.messages.append(message)
        return message

    def clear(self) -> None:
        self.messages = []

    def recent(self, limit: int = 12) -> list[Message]:
        """The tail of the conversation, which is all the model needs and all it
        can be trusted to weigh evenly."""
        return self.messages[-limit:]


def build_prompt(profile: Profile, answers: Answers, guide: str,
                 conversation: Conversation, instruction: str) -> str:
    history = "\n\n".join(
        f"{'He' if m.role == 'user' else 'You'}: {m.text}" for m in conversation.recent()
    ) or "(nothing yet)"
    return f"""# The man

{physique(profile)}.
{appearance(profile)}.

# What he said in the questionnaire

{transcript(answers)}

# The guide as it stands

{guide or "(not written yet)"}

# The conversation so far

{history}

# What he is asking now

{instruction}"""


def talk(profile: Profile, answers: Answers, instruction: str,
         conversation: Conversation | None = None,
         guide_path: Path | None = None) -> tuple[str, bool]:
    """Answer him, and revise the guide if that is what he asked for.

    Returns (reply, whether the guide changed).
    """
    conversation = conversation if conversation is not None else Conversation.load()
    guide_path = Path(guide_path) if guide_path else paths.guide()
    current = guide_path.read_text() if guide_path.is_file() else ""

    raw = generate_text(
        build_prompt(profile, answers, current, conversation, instruction),
        system=SYSTEM, temperature=0.5,
    )

    reply, revised = raw, ""
    if MARKER in raw:
        reply, revised = (part.strip() for part in raw.split(MARKER, 1))

    changed = False
    if revised and revised != current.strip():
        if current:
            snapshot(current, guide_path)
        guide_path.parent.mkdir(parents=True, exist_ok=True)
        guide_path.write_text(revised + "\n")
        changed = True

    conversation.add("user", instruction)
    conversation.add("guide", reply or "(no reply)", revised=changed)
    conversation.save()
    return reply, changed


def snapshot(markdown: str, guide_path: Path | None = None) -> Path:
    """Keep the version being replaced, so a bad instruction is not fatal."""
    directory = paths.guide_versions()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime(STAMP)
    target = directory / f"{stamp}.md"
    n = 2
    while target.exists():
        target = directory / f"{stamp}.{n}.md"
        n += 1
    target.write_text(markdown)
    return target


@dataclass
class Version:
    path: Path
    when: dt.datetime

    @property
    def label(self) -> str:
        return f"{self.when:%d %b %Y, %H:%M:%S}"

    @property
    def words(self) -> int:
        return len(self.path.read_text().split())


def versions() -> list[Version]:
    """Newest first."""
    directory = paths.guide_versions()
    if not directory.is_dir():
        return []
    out: list[Version] = []
    for path in directory.glob("*.md"):
        try:
            when = dt.datetime.strptime(path.name.split(".")[0], STAMP)
        except ValueError:
            continue
        out.append(Version(path, when))
    return sorted(out, key=lambda v: (v.when, v.path.name), reverse=True)


def restore(version: Version, guide_path: Path | None = None) -> Path:
    """Put an earlier version back, keeping the current one first."""
    guide_path = Path(guide_path) if guide_path else paths.guide()
    if guide_path.is_file():
        snapshot(guide_path.read_text(), guide_path)
    guide_path.write_text(version.path.read_text())
    return guide_path


def save_edit(markdown: str, guide_path: Path | None = None) -> Path:
    """Write a hand edit, keeping what it replaced."""
    guide_path = Path(guide_path) if guide_path else paths.guide()
    if guide_path.is_file():
        current = guide_path.read_text()
        if current.strip() == markdown.strip():
            return guide_path
        snapshot(current, guide_path)
    guide_path.parent.mkdir(parents=True, exist_ok=True)
    guide_path.write_text(markdown.rstrip() + "\n")
    return guide_path
