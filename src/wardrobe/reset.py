"""The backup store: nothing is deleted without a copy being kept first.

A button that deletes a man's wardrobe is a cliff, so this is built as a ledge.
Every destructive action in the app calls `before()` with a reason and the data
it is about to touch, a copy goes into .wardrobe-backups/<timestamp>/, and any
snapshot can be put back whole or one part at a time.

Two things make it usable rather than merely present. Snapshots carry a reason,
because "before deleting Camel wool overcoat" tells you what you are restoring
and a timestamp does not. And they are targeted: deleting one outfit copies the
outfit list, not the two hundred megabytes of generated images that the deletion
was never going to touch.

The subject profile is excluded from the default selection when clearing. His
height and skin tone are not test data and losing them to a stray click would be
maddening.
"""

from __future__ import annotations

import datetime as dt
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

from . import paths

STAMP = "%Y%m%d-%H%M%S"


# Automatic snapshots pile up fast. Kept generously, since they are small once
# the image directories are left out of them.
KEEP = 60


@dataclass
class Snapshot:
    path: Path
    when: dt.datetime
    keys: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def label(self) -> str:
        return f"{self.when:%d %b %Y, %H:%M:%S}"

    @property
    def what(self) -> str:
        return ", ".join(paths.DATA.get(k, k).lower() for k in self.keys) or "nothing"

    @property
    def bytes(self) -> int:
        return sum(f.stat().st_size for f in self.path.rglob("*") if f.is_file())

    @property
    def size(self) -> str:
        n = self.bytes
        return f"{n / 1_048_576:.1f} MB" if n >= 1_048_576 else f"{max(n // 1024, 1)} KB"


def _count(path: Path, table: str) -> int:
    try:
        return len(tomllib.loads(path.read_text()).get(table, []))
    except Exception:
        return 0


def describe(key: str) -> str:
    """One line saying what is currently stored under this key, or "" if nothing."""
    target = paths.resolve(key)
    if not target.exists():
        return ""
    if target.is_dir():
        files = [f for f in target.rglob("*") if f.is_file()]
        return f"{len(files)} file(s)" if files else ""
    if key == "answers":
        return f"{_count(target, 'answers') or len(tomllib.loads(target.read_text()).get('answers', {}))} answered"
    if key == "inventory":
        return f"{_count(target, 'items')} item(s)"
    if key == "outfits":
        return f"{_count(target, 'outfits')} outfit(s)"
    if key == "palette":
        return f"{_count(target, 'colours')} colour(s)"
    if key == "principles":
        return f"{_count(target, 'principles')} principle(s)"
    if key == "guide":
        return f"{len(target.read_text().split()):,} words"
    return "present"


def present() -> dict[str, str]:
    """Every key that currently holds something, with a one-line summary."""
    return {key: text for key in paths.DATA if (text := describe(key))}


def snapshot(keys: list[str] | None = None, reason: str = "") -> Snapshot | None:
    """Copy the named data into a timestamped backup. None if there is nothing."""
    keys = [k for k in (keys or list(paths.DATA)) if paths.resolve(k).exists()]
    if not keys:
        return None
    when = dt.datetime.now()
    # Two wipes inside the same second would otherwise land in one directory and
    # the second would overwrite the first, silently losing a backup.
    base = when.strftime(STAMP)
    destination = paths.backups() / base
    suffix = 2
    while destination.exists():
        destination = paths.backups() / f"{base}.{suffix}"
        suffix += 1
    destination.mkdir(parents=True, exist_ok=True)
    for key in keys:
        source = paths.resolve(key)
        target = destination / key
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target.with_suffix(source.suffix))
    (destination / "manifest.toml").write_text(tomli_w.dumps({
        "when": when.isoformat(timespec="seconds"),
        "reason": reason,
        "keys": keys,
    }))
    prune()
    return Snapshot(destination, when, keys, reason)


def before(reason: str, *keys: str) -> Snapshot | None:
    """Take a copy of exactly what is about to change, and say why.

    Called by every destructive action. Targeted on purpose: deleting one outfit
    copies the outfit list, not the generated images it was never going to touch.
    """
    return snapshot([k for k in keys if k in paths.DATA], reason)


def prune(keep: int = KEEP) -> list[Snapshot]:
    """Drop the oldest snapshots past the limit. Returns what went."""
    everything = snapshots()
    dropped = everything[keep:]
    for old in dropped:
        forget(old)
    return dropped


def store_size() -> str:
    root = paths.backups()
    if not root.is_dir():
        return "0 KB"
    total = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
    return (f"{total / 1_048_576:.1f} MB" if total >= 1_048_576
            else f"{max(total // 1024, 1)} KB")


def wipe(keys: list[str], *, snapshot_first: bool = True,
         reason: str = "") -> tuple[Snapshot | None, list[str]]:
    """Delete the named data. Returns the snapshot taken and what was removed."""
    taken = snapshot(keys, reason or "before clearing " +
                     ", ".join(paths.DATA.get(k, k).lower() for k in keys)) \
        if snapshot_first else None
    removed: list[str] = []
    for key in keys:
        target = paths.resolve(key)
        if not target.exists():
            continue
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        removed.append(key)
    return taken, removed


def snapshots() -> list[Snapshot]:
    """Newest first."""
    root = paths.backups()
    if not root.is_dir():
        return []
    out: list[Snapshot] = []
    for directory in root.iterdir():
        if not directory.is_dir():
            continue
        try:
            when = dt.datetime.strptime(directory.name.split(".")[0], STAMP)
        except ValueError:
            continue
        manifest, keys, reason = directory / "manifest.toml", [], ""
        if manifest.is_file():
            try:
                read = tomllib.loads(manifest.read_text())
                keys, reason = list(read.get("keys", [])), read.get("reason", "")
            except Exception:
                pass
        else:                                   # written before manifests existed
            legacy = directory / "KEYS"
            keys = legacy.read_text().split() if legacy.is_file() else []
        out.append(Snapshot(directory, when, keys, reason))
    return sorted(out, key=lambda s: (s.when, s.path.name), reverse=True)


def restore(snap: Snapshot, keys: list[str] | None = None) -> list[str]:
    """Put a snapshot back, whole or in part, over whatever is there now.

    Takes a copy of the current state first, so restoring is itself reversible
    and going back to the wrong point is not the end of it.
    """
    wanted = keys if keys is not None else (snap.keys or list(paths.DATA))
    before(f"before restoring {snap.label}", *wanted)
    restored: list[str] = []
    for key in wanted:
        target = paths.resolve(key)
        directory_source = snap.path / key
        file_source = next((p for p in snap.path.glob(f"{key}.*") if p.is_file()), None)
        if directory_source.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(directory_source, target)
        elif file_source:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_source, target)
        else:
            continue
        restored.append(key)
    return restored


def forget(snap: Snapshot) -> None:
    if snap.path.is_dir():
        shutil.rmtree(snap.path)
