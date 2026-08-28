"""Every garment, owned or merely wanted, in one list.

The important decision: owned and aspirational items are the same kind of
object, separated only by `status`. An outfit is a set of item ids and does not
care which is which. That is what makes the shopping maths work: a loved outfit
is blocked by exactly the items in it that are not owned, so "what should I buy"
becomes a coverage problem over blocked outfits rather than a matter of opinion.

Photos exist for the pieces that words cannot pin down. A prompt saying "green
jacket" produces a different jacket every time; the photograph produces that one.
"""

from __future__ import annotations

import re
import shutil
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

DEFAULT_PATH = Path("wardrobe.toml")
PHOTO_DIR = Path("inventory/photos")

OWNED, ASPIRATIONAL, RETIRED = "owned", "aspirational", "retired"
STATUSES: tuple[str, ...] = (OWNED, ASPIRATIONAL, RETIRED)

# Category drives the outfit slots. Only one item per slot, except accessories.
CATEGORIES: dict[str, tuple[str, ...]] = {
    "Top": ("Shirt", "T-shirt", "Polo", "Knitwear", "Sweatshirt", "Waistcoat"),
    "Bottom": ("Trousers", "Jeans", "Shorts", "Chinos"),
    "Outerwear": ("Blazer", "Overcoat", "Jacket", "Overshirt", "Gilet"),
    "Shoes": ("Loafers", "Derbies", "Boots", "Trainers", "Sandals"),
    "Accessory": ("Belt", "Watch", "Jewellery", "Bag", "Scarf", "Hat", "Sunglasses", "Socks"),
}
GARMENTS: tuple[str, ...] = tuple(g for group in CATEGORIES.values() for g in group)
SINGLE_SLOT: tuple[str, ...] = ("Top", "Bottom", "Outerwear", "Shoes")

# Which finished dimensions matter per garment, for the size record.
TRACKED_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "Shirt": ("chest", "waist", "shoulder", "sleeve", "neck", "length"),
    "T-shirt": ("chest", "shoulder", "sleeve", "length"),
    "Polo": ("chest", "shoulder", "sleeve", "length"),
    "Knitwear": ("chest", "shoulder", "sleeve", "length"),
    "Sweatshirt": ("chest", "shoulder", "sleeve", "length"),
    "Waistcoat": ("chest", "waist", "length"),
    "Blazer": ("chest", "waist", "shoulder", "sleeve", "length"),
    "Jacket": ("chest", "shoulder", "sleeve", "length"),
    "Overshirt": ("chest", "shoulder", "sleeve", "length"),
    "Overcoat": ("chest", "waist", "shoulder", "sleeve", "length"),
    "Gilet": ("chest", "length"),
    "Trousers": ("waist", "seat", "thigh", "knee", "ankle", "rise", "inseam"),
    "Chinos": ("waist", "seat", "thigh", "knee", "ankle", "rise", "inseam"),
    "Jeans": ("waist", "seat", "thigh", "knee", "ankle", "rise", "inseam"),
    "Shorts": ("waist", "seat", "thigh", "ankle", "rise", "inseam"),
}

FIT_VERDICTS: tuple[str, ...] = ("Perfect", "Good", "Too big", "Too small", "Wrong shape", "Not assessed")


@dataclass
class Item:
    id: str = ""
    name: str = ""
    category: str = "Top"
    garment: str = "Shirt"
    colour: str = ""
    colour_hex: str = "#CCCCCC"
    fabric: str = ""
    pattern: str = "Solid"
    brand: str = ""
    size_label: str = ""
    status: str = OWNED
    price: float = 0.0
    photo: str = ""
    description: str = ""
    fit_verdict: str = "Not assessed"
    fit_note: str = ""
    starred: bool = False   # marked for purchase in the shopping guide
    tags: list[str] = field(default_factory=list)
    measurements: dict[str, float] = field(default_factory=dict)

    @property
    def owned(self) -> bool:
        return self.status == OWNED

    @property
    def label(self) -> str:
        """What the search boxes show. Brand and colour make near-duplicates distinct."""
        bits = [self.name or self.garment]
        if self.brand:
            bits.append(f"({self.brand})")
        if self.status == ASPIRATIONAL:
            bits.append("· wanted")
        elif self.status == RETIRED:
            bits.append("· retired")
        return " ".join(bits)

    @property
    def has_photo(self) -> bool:
        return bool(self.photo) and Path(self.photo).is_file()

    def describe(self) -> str:
        """One line for the image prompt. Photographs beat adjectives, but when
        there is no photograph the adjectives have to carry it."""
        bits = [b for b in (
            self.pattern if self.pattern and self.pattern != "Solid" else "",
            self.colour, self.fabric, self.garment.lower(),
        ) if b]
        line = " ".join(bits) or self.name
        if self.description:
            line = f"{line} ({self.description})"
        return line

    def searchable(self) -> str:
        return " ".join(
            [self.name, self.brand, self.colour, self.fabric, self.garment,
             self.category, self.pattern, self.description, *self.tags]
        ).lower()


@dataclass
class Inventory:
    items: list[Item] = field(default_factory=list)
    path: Path = DEFAULT_PATH

    @classmethod
    def load(cls, path: Path | str = DEFAULT_PATH) -> "Inventory":
        path = Path(path)
        if not path.is_file():
            return cls(path=path)
        raw = tomllib.loads(path.read_text())
        allowed = {f.name for f in fields(Item)}
        items = [Item(**{k: v for k, v in row.items() if k in allowed}) for row in raw.get("items", [])]
        return cls(items=items, path=path)

    def save(self) -> Path:
        self.path.write_text(tomli_w.dumps({"items": [asdict(i) for i in self.items]}))
        return self.path

    # --- lookup ---------------------------------------------------------------

    def by_id(self, item_id: str) -> Item | None:
        return next((i for i in self.items if i.id == item_id), None)

    def resolve(self, ids: list[str]) -> list[Item]:
        found = [self.by_id(i) for i in ids]
        return [i for i in found if i]

    def filter(
        self,
        *,
        status: str | None = None,
        category: str | None = None,
        query: str = "",
    ) -> list[Item]:
        out = self.items
        if status:
            out = [i for i in out if i.status == status]
        if category:
            out = [i for i in out if i.category == category]
        if query.strip():
            needle = query.strip().lower()
            out = [i for i in out if needle in i.searchable()]
        return out

    def owned(self) -> list[Item]:
        return [i for i in self.items if i.status == OWNED]

    def owned_ids(self) -> set[str]:
        return {i.id for i in self.items if i.status == OWNED}

    def counts(self) -> dict[str, int]:
        return {s: sum(1 for i in self.items if i.status == s) for s in STATUSES}

    # --- mutation -------------------------------------------------------------

    def add(self, item: Item) -> Item:
        item.id = item.id or self.unique_id(item.name or item.garment)
        self.items.append(item)
        return item

    def update(self, item: Item) -> None:
        for index, existing in enumerate(self.items):
            if existing.id == item.id:
                self.items[index] = item
                return
        self.items.append(item)

    def remove(self, item_id: str) -> None:
        self.items = [i for i in self.items if i.id != item_id]

    def unique_id(self, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", (name or "item").lower()).strip("-")[:36] or "item"
        taken = {i.id for i in self.items}
        if base not in taken:
            return base
        n = 2
        while f"{base}-{n}" in taken:
            n += 1
        return f"{base}-{n}"


def save_photo(item_id: str, uploaded, photo_dir: Path = PHOTO_DIR) -> str:
    """Write an uploaded photo next to the inventory. Returns the stored path."""
    photo_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(getattr(uploaded, "name", "photo.png")).suffix.lower() or ".png"
    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
        raise ValueError(f"{suffix} is not an image this app will store.")
    for stale in photo_dir.glob(f"{item_id}.*"):
        stale.unlink()
    destination = photo_dir / f"{item_id}{suffix}"
    data = uploaded.getvalue() if hasattr(uploaded, "getvalue") else uploaded.read()
    destination.write_bytes(data)
    return str(destination)


def drop_photo(item: Item) -> None:
    if item.photo and Path(item.photo).is_file():
        Path(item.photo).unlink()
    item.photo = ""


def category_for(garment: str) -> str:
    return next((c for c, group in CATEGORIES.items() if garment in group), "Accessory")
