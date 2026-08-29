"""Saving the style guide, and keeping what each save replaced.

The guide is edited by hand, which means a bad afternoon can overwrite a good
one. So every write copies the previous version into .guide-versions first, and
any of them can be restored. Restoring keeps the current version too, so the
history only ever grows and nothing here can lose work.

Saving an unchanged document makes no version, or the list fills with identical
copies and stops being readable.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from . import paths

STAMP = "%Y%m%d-%H%M%S"

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
