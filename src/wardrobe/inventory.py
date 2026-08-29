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

import io
import re
import shutil
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w
from PIL import Image, ImageOps, UnidentifiedImageError

# Pillow cannot read HEIC on its own, and every photograph off an iPhone is one
# unless somebody has gone into the settings. Registering the opener teaches
# Image.open the format, so the rest of this file does not have to care.
try:
    from pillow_heif import register_heif_opener
except ImportError:                                    # pragma: no cover
    register_heif_opener = None
else:
    register_heif_opener()

from . import paths

OWNED, ASPIRATIONAL, RETIRED = "owned", "aspirational", "retired"
STATUSES: tuple[str, ...] = tuple(sorted((OWNED, ASPIRATIONAL, RETIRED)))

# The vocabularies now live in the garment catalogue, which is editable. These
# are lookups rather than constants: a dropdown asking for the list on every
# rerun must get the list as it is now, not as it was when the module imported.
from .vocabulary import (          # noqa: E402
    NONE, SCHEMES, SizeField, Vocabulary, current,
)

SINGLE_SLOT: tuple[str, ...] = ("Top", "Bottom", "Outerwear", "Shoes")


def garments() -> tuple[str, ...]:
    return current().names()


def categories() -> dict[str, tuple[str, ...]]:
    return current().categories()


def category_names() -> tuple[str, ...]:
    return current().category_names()


def fits() -> tuple[str, ...]:
    return _sorted_words(current().fits)


def grades() -> tuple[str, ...]:
    return _sorted_words(current().grades)


def _sorted_words(words) -> tuple[str, ...]:
    """Alphabetical, with the blank "not set" option kept at the front."""
    return ("", *sorted(w for w in words if w)) if "" in words else tuple(sorted(words))


def fabric_options() -> tuple[str, ...]:
    return current().fabric_options()


def fabric_family(fabric: str) -> str:
    return current().fabric_family(fabric)


def schemes_for(garment: str) -> tuple[str, ...]:
    """Every sizing scheme that can apply to this garment, most specific first."""
    return current().schemes_for(garment)


def takes_grade(garment: str) -> bool:
    return current().takes_grade(garment)


def takes_fit(garment: str) -> bool:
    return current().takes_fit(garment)


def size_scheme(garment: str, scheme: str = "") -> tuple[SizeField, ...]:
    """The size boxes for this garment, in whichever scheme its label used."""
    return current().scheme_for(garment, scheme)


def category_for(garment: str) -> str:
    return current().category_for(garment)


@dataclass
class Item:
    id: str = ""
    name: str = ""
    category: str = "Top"
    garment: str = "Shirt"
    colour: str = ""
    colour_hex: str = "#CCCCCC"
    fabric: str = ""
    # The three axes a sourcing route matches on. Each is optional; the more of
    # them are set, the more precisely the right shop can be chosen.
    grade: str = ""
    fit: str = ""
    # Which sizing scheme this particular label used. Trousers are 32/32 from
    # one maker and M from the next, and the garment allows both.
    scheme: str = ""
    status: str = OWNED
    photo: str = ""
    description: str = ""
    starred: bool = False   # marked for purchase in the shopping guide
    # A specific thing online that is the thing, or near enough. The plan says
    # which shop a garment comes from; this says which garment.
    link: str = ""
    wait_for_sale: bool = False
    # Written by the shopping guide: a product shot and the copy to go with it.
    product_photo: str = ""
    product_copy: str = ""
    sizes: dict[str, str] = field(default_factory=dict)

    @property
    def owned(self) -> bool:
        return self.status == OWNED

    @property
    def label(self) -> str:
        """What the search boxes show. Colour separates near-duplicates."""
        bits = [self.name or self.garment]
        if self.colour and self.colour.lower() not in (self.name or "").lower():
            bits.append(f"({self.colour})")
        if self.status == ASPIRATIONAL:
            bits.append("· wanted")
        elif self.status == RETIRED:
            bits.append("· retired")
        return " ".join(bits)

    @property
    def has_photo(self) -> bool:
        return bool(self.photo) and Path(self.photo).is_file()

    @property
    def has_link(self) -> bool:
        return self.link.startswith(("http://", "https://"))

    @property
    def link_host(self) -> str:
        """The bare domain, for showing where a link goes without the URL."""
        if not self.has_link:
            return ""
        host = self.link.split("//", 1)[-1].split("/", 1)[0]
        return host[4:] if host.startswith("www.") else host

    @property
    def has_product_photo(self) -> bool:
        return bool(self.product_photo) and Path(self.product_photo).is_file()

    @property
    def shop_photo(self) -> str:
        """The generated product shot if there is one, else his own snap."""
        return (self.product_photo if self.has_product_photo
                else self.photo if self.has_photo else "")

    def describe(self) -> str:
        """One line for the image prompt. Photographs beat adjectives, but when
        there is no photograph the adjectives have to carry it."""
        bits = [b for b in (self.colour, self.fabric, self.garment.lower()) if b]
        line = " ".join(bits) or self.name
        if self.description:
            line = f"{line} ({self.description})"
        return line

    @property
    def family(self) -> str:
        """Which fabric family this cloth belongs to, for route matching."""
        return fabric_family(self.fabric)

    def spec_line(self) -> str:
        """Grade, fit and fabric as one line: what he is actually looking for."""
        return " · ".join(b for b in (self.grade, self.fit, self.fabric) if b)

    def size_line(self) -> str:
        """The sizes as one readable line, in this garment's own scheme."""
        labels = {f.key: f.label for f in size_scheme(self.garment, self.scheme)}
        return " · ".join(
            f"{labels.get(k, k)} {v}" for k, v in self.sizes.items()
            if v and v != NONE and k in labels
        )

    def prune_sizes(self) -> None:
        """Drop size keys and values that no longer belong to this garment.

        Two ways stale data gets in. Re-classify a shirt as a trouser and the
        collar would otherwise sit in the file forever, invisible but not gone.
        And when a scheme's options change, an old value survives as something
        the dropdown cannot select and nobody can correct. Both go.
        """
        scheme = {f.key: f for f in size_scheme(self.garment, self.scheme)}
        kept: dict[str, str] = {}
        for key, value in self.sizes.items():
            spec = scheme.get(key)
            if not spec or not value or value == NONE:
                continue
            if spec.options and value not in spec.options:
                continue
            kept[key] = value
        self.sizes = kept
        # The same for the axes: a grade on a belt is a value nothing will ever
        # read, and it would keep matching sourcing routes from beyond the grave.
        if not current().takes_grade(self.garment):
            self.grade = ""
        if not current().takes_fit(self.garment):
            self.fit = ""

    def searchable(self) -> str:
        return " ".join(
            [self.name, self.colour, self.fabric, self.garment, self.grade,
             self.fit, self.category, self.description, *self.sizes.values()]
        ).lower()


@dataclass
class Inventory:
    items: list[Item] = field(default_factory=list)
    path: Path = field(default_factory=paths.inventory)

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Inventory":
        path = Path(path) if path else paths.inventory()
        if not path.is_file():
            return cls(path=path)
        raw = tomllib.loads(path.read_text())
        allowed = {f.name for f in fields(Item)}
        items = [Item(**{k: v for k, v in row.items() if k in allowed}) for row in raw.get("items", [])]
        return cls(items=items, path=path)

    def save(self) -> Path:
        for item in self.items:
            item.prune_sizes()
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


# Guards on uploads. The first is a decompression-bomb stop before anything is
# decoded; the second is what actually keeps the repository small, since a phone
# photograph is fifteen times larger than anything this app needs.
# What the uploader will accept. HEIC is here because it is what an iPhone
# actually produces; it is decoded and re-encoded to JPEG like everything else,
# so nothing downstream ever meets one.
UPLOAD_FORMATS: tuple[str, ...] = ("png", "jpg", "jpeg", "webp", "heic", "heif")

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_EDGE_PX = 1600
JPEG_QUALITY = 88


def save_photo(item_id: str, uploaded, photo_dir: Path | None = None) -> str:
    """Store an uploaded photo, downscaled. Returns the stored path.

    Everything is re-encoded to JPEG at a bounded size rather than written
    through. A garment reference only needs to be recognisable, and writing a
    12 MB original straight to disk puts it in the repository forever.
    """
    photo_dir = Path(photo_dir) if photo_dir else paths.photos()
    photo_dir.mkdir(parents=True, exist_ok=True)

    data = uploaded.getvalue() if hasattr(uploaded, "getvalue") else uploaded.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"That file is {len(data) / 1_048_576:.0f} MB. The limit is "
            f"{MAX_UPLOAD_BYTES // 1_048_576} MB; take the photo again at a lower resolution."
        )
    try:
        Image.open(io.BytesIO(data)).verify()      # verify() exhausts the reader,
        image = Image.open(io.BytesIO(data))       # so open it again to use it
        # A phone writes the picture the way the sensor saw it and puts the
        # rotation in EXIF. Without this, every photo taken in portrait arrives
        # on its side, which on a hanging garment is not subtle.
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        hint = ""
        if not register_heif_opener and data[4:12] in (b"ftypheic", b"ftypheix",
                                                       b"ftyphevc", b"ftypmif1"):
            hint = " That looks like a HEIC; pillow-heif is not installed."
        raise ValueError(f"That file is not a readable image ({exc}).{hint}") from exc

    image.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX), Image.LANCZOS)
    for stale in photo_dir.glob(f"{item_id}.*"):
        stale.unlink()
    destination = photo_dir / f"{item_id}.jpg"
    image.save(destination, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return str(destination)


def drop_photo(item: Item) -> None:
    if item.photo and Path(item.photo).is_file():
        Path(item.photo).unlink()
    item.photo = ""



