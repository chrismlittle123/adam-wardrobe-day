"""Outfits: a name, a set of item ids, some tags, and whatever images we made.

An outfit holds ids, never copies of the garments. So when a wanted item is
bought and flips to owned, every outfit built on it becomes wearable at once,
with nothing to migrate.
"""

from __future__ import annotations

import datetime as dt
import re
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

from . import paths
from .text import plural

from .inventory import ASPIRATIONAL, RETIRED, Inventory, Item

# Starting tags. Anything typed in the gallery joins the list for next time.
SEED_TAGS: tuple[str, ...] = (
    "work", "weekend", "dinner", "date", "summer", "winter", "rain",
    "travel", "smart", "casual", "evening", "wedding",
)


@dataclass
class Outfit:
    id: str = ""
    name: str = ""
    item_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    images: list[str] = field(default_factory=list)
    loved: bool = False
    created: str = ""
    prompt: str = ""
    # The settings it was generated with, kept so a variation can start from them
    # rather than from a blank form. Storing only the finished prompt meant the
    # options had to be guessed back out of it, or retyped.
    shot: str = ""
    background: str = ""
    extra: str = ""
    parent: str = ""            # the outfit this was varied from

    def cover(self) -> str | None:
        return next((p for p in self.images if Path(p).is_file()), None)

    @property
    def shots(self) -> list[Path]:
        return [Path(p) for p in self.images if Path(p).is_file()]


@dataclass
class Wearability:
    """What is stopping this outfit being worn today.

    Three different things can stop it, and collapsing them loses information.
    `missing` is buyable. `retired` and `dangling` are not: they make the outfit
    broken rather than incomplete, and no shopping trip fixes them.
    """

    wearable: bool
    missing: list[Item]          # wanted, and buying it fixes this outfit
    retired: list[Item] = field(default_factory=list)
    dangling: list[str] = field(default_factory=list)   # ids of deleted garments
    empty: bool = False          # no garments in it at all

    @property
    def broken(self) -> bool:
        """Money cannot fix this one. A piece was deleted, retired, or never added."""
        return bool(self.retired or self.dangling or self.empty)

    @property
    def fault(self) -> str:
        bits = []
        if self.empty:
            bits.append("no garments in it")
        if self.dangling:
            bits.append(f"{plural(len(self.dangling), 'deleted piece')}")
        if self.retired:
            bits.append(", ".join(i.name or i.garment for i in self.retired) + " retired")
        return "; ".join(bits)


@dataclass
class Outfits:
    outfits: list[Outfit] = field(default_factory=list)
    path: Path = field(default_factory=paths.outfits)

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Outfits":
        path = Path(path) if path else paths.outfits()
        if not path.is_file():
            return cls(path=path)
        raw = tomllib.loads(path.read_text())
        allowed = {f.name for f in fields(Outfit)}
        rows = [Outfit(**{k: v for k, v in r.items() if k in allowed}) for r in raw.get("outfits", [])]
        return cls(outfits=rows, path=path)

    def save(self) -> Path:
        self.path.write_text(tomli_w.dumps({"outfits": [asdict(o) for o in self.outfits]}))
        return self.path

    def by_id(self, outfit_id: str) -> Outfit | None:
        return next((o for o in self.outfits if o.id == outfit_id), None)

    def add(self, outfit: Outfit) -> Outfit:
        outfit.id = outfit.id or self.unique_id(outfit.name)
        outfit.created = outfit.created or dt.datetime.now().isoformat(timespec="seconds")
        self.outfits.append(outfit)
        return outfit

    def update(self, outfit: Outfit) -> None:
        for index, existing in enumerate(self.outfits):
            if existing.id == outfit.id:
                self.outfits[index] = outfit
                return
        self.outfits.append(outfit)

    def remove(self, outfit_id: str) -> None:
        self.outfits = [o for o in self.outfits if o.id != outfit_id]

    def unique_id(self, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", (name or "outfit").lower()).strip("-")[:36] or "outfit"
        taken = {o.id for o in self.outfits}
        if base not in taken:
            return base
        n = 2
        while f"{base}-{n}" in taken:
            n += 1
        return f"{base}-{n}"

    def forget_item(self, item_id: str) -> list[Outfit]:
        """Drop a deleted garment from every outfit that used it.

        Called when an item is deleted. Without it the id lingers and the outfit
        quietly loses a piece instead of admitting it is broken.
        """
        touched = [o for o in self.outfits if item_id in o.item_ids]
        for outfit in touched:
            outfit.item_ids = [i for i in outfit.item_ids if i != item_id]
        return touched

    def using(self, item_id: str) -> list[Outfit]:
        return [o for o in self.outfits if item_id in o.item_ids]

    def all_tags(self) -> list[str]:
        used = {t for o in self.outfits for t in o.tags}
        return sorted(used | set(SEED_TAGS))

    def variations_of(self, outfit_id: str) -> list[Outfit]:
        return [o for o in self.outfits if o.parent == outfit_id]

    def family(self, outfit: Outfit) -> list[Outfit]:
        """The original and every variation of it, oldest first.

        A variation of a variation belongs to the same conversation, so the
        family is walked back to its root rather than one step up.
        """
        root = outfit
        seen = {root.id}
        while root.parent:
            parent = self.by_id(root.parent)
            if not parent or parent.id in seen:
                break
            root, _ = parent, seen.add(parent.id)
        out = [root]
        queue = [root.id]
        while queue:
            for child in self.variations_of(queue.pop()):
                if child.id not in {o.id for o in out}:
                    out.append(child)
                    queue.append(child.id)
        return sorted(out, key=lambda o: o.created)

    def loved(self) -> list["Outfit"]:
        return [o for o in self.outfits if o.loved]

    def filter(self, *, tags: list[str] | None = None, loved_only: bool = False,
               match_all: bool = False, query: str = "") -> list[Outfit]:
        out = self.outfits
        if loved_only:
            out = [o for o in out if o.loved]
        if tags:
            wanted = set(tags)
            out = [o for o in out if (
                wanted <= set(o.tags) if match_all else bool(wanted & set(o.tags))
            )]
        if query.strip():
            needle = query.strip().lower()
            out = [o for o in out
                   if needle in " ".join([o.name, o.notes, *o.tags]).lower()]
        return out


def wearability(outfit: Outfit, inventory: Inventory) -> Wearability:
    """Cost split and what is blocking it.

    Dangling ids are counted explicitly. Resolving them away silently would make
    an outfit look wearable the moment one of its garments was deleted, which is
    the opposite of true.
    """
    items = inventory.resolve(outfit.item_ids)
    found = {i.id for i in items}
    dangling = [i for i in outfit.item_ids if i not in found]
    missing = [i for i in items if i.status == ASPIRATIONAL]
    retired = [i for i in items if i.status == RETIRED]
    return Wearability(
        # An outfit with nothing in it is not something he can wear, and counting
        # it as wearable quietly inflates the only number the plan reports.
        wearable=bool(items) and not (missing or retired or dangling),
        missing=missing, retired=retired, dangling=dangling,
        empty=not outfit.item_ids,
    )


def describe_outfit(outfit: Outfit, inventory: Inventory) -> str:
    """The garment list as a sentence, for the image prompt."""
    items = inventory.resolve(outfit.item_ids)
    return ". ".join(i.describe() for i in items) + ("." if items else "")


REFERENCE_LIMIT = 6

CARRIES_THE_LOOK = {"Outerwear": 0, "Top": 1, "Bottom": 2, "Shoes": 3, "Accessory": 4}


def reference_items(items: list[Item], limit: int = REFERENCE_LIMIT) -> tuple[list[Item], list[Item]]:
    """Which garments get shown to the model, and which do not fit.

    A model takes only so many references before it starts blending them, so the
    pieces that carry the look go in ahead of a belt. Returns both halves,
    because dropping a garment silently is how an outfit comes back wearing
    something nobody chose.
    """
    usable = [i for i in items if i.has_reference]
    usable.sort(key=lambda i: CARRIES_THE_LOOK.get(i.category, 9))
    return usable[:limit], usable[limit:]


def reference_photos(items: list[Item], limit: int = REFERENCE_LIMIT) -> list[Path]:
    """Just the paths, most specific first."""
    shown, _ = reference_items(items, limit)
    return [i.reference_photo for i in shown]


@dataclass
class Difference:
    """What changed between two outfits, so a comparison says something."""

    added: list[Item] = field(default_factory=list)
    removed: list[Item] = field(default_factory=list)
    kept: list[Item] = field(default_factory=list)
    settings: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def identical(self) -> bool:
        return not (self.added or self.removed or self.settings)

    @property
    def summary(self) -> str:
        bits = []
        if self.added:
            bits.append(f"+{len(self.added)}")
        if self.removed:
            bits.append(f"-{len(self.removed)}")
        if self.settings:
            bits.append(f"{plural(len(self.settings), 'setting')}")
        return ", ".join(bits) or "no difference"


def compare(left: Outfit, right: Outfit, inventory: Inventory) -> Difference:
    """What the right one changed relative to the left."""
    before = {i.id: i for i in inventory.resolve(left.item_ids)}
    after = {i.id: i for i in inventory.resolve(right.item_ids)}
    settings = [
        (label, getattr(left, key) or "—", getattr(right, key) or "—")
        for label, key in (("Framing", "shot"), ("Background", "background"),
                           ("Extra direction", "extra"))
        if getattr(left, key, "") != getattr(right, key, "")
    ]
    return Difference(
        added=[i for k, i in after.items() if k not in before],
        removed=[i for k, i in before.items() if k not in after],
        kept=[i for k, i in after.items() if k in before],
        settings=settings,
    )


def aspirational_in(outfit: Outfit, inventory: Inventory) -> list[Item]:
    return [i for i in inventory.resolve(outfit.item_ids) if i.status == ASPIRATIONAL]
