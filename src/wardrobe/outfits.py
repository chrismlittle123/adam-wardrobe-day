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

    def cover(self) -> str | None:
        return next((p for p in self.images if Path(p).is_file()), None)


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
            bits.append(f"{len(self.dangling)} deleted piece(s)")
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


def reference_photos(outfit: Outfit, inventory: Inventory, limit: int = 4) -> list[Path]:
    """Item photos to pass alongside the subject portrait, most specific first.

    The model takes only so many references before it starts blending them, so
    the ones that carry the look (tops, outerwear, shoes) go in ahead of a belt.
    """
    order = {"Outerwear": 0, "Top": 1, "Bottom": 2, "Shoes": 3, "Accessory": 4}
    items = [i for i in inventory.resolve(outfit.item_ids) if i.has_photo]
    items.sort(key=lambda i: order.get(i.category, 9))
    return [Path(i.photo) for i in items[:limit]]


def aspirational_in(outfit: Outfit, inventory: Inventory) -> list[Item]:
    return [i for i in inventory.resolve(outfit.item_ids) if i.status == ASPIRATIONAL]
