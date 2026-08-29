"""Where the data lives.

Every path in the app resolves through here, and here resolves through
WARDROBE_HOME. That one indirection is what makes the app testable: a check run
points WARDROBE_HOME at a scratch directory, fills it, exercises everything, and
throws it away without ever touching the real wardrobe.

Resolved on each call rather than at import, because a test that sets the
environment variable after importing the module should still be obeyed.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "WARDROBE_HOME"


def home() -> Path:
    return Path(os.environ.get(ENV_VAR, ".")).expanduser()


def profile() -> Path:
    return home() / "profile.toml"


def answers() -> Path:
    return home() / "style-answers.toml"


def guide() -> Path:
    return home() / "STYLE-GUIDE.md"


def inventory() -> Path:
    return home() / "wardrobe.toml"


def outfits() -> Path:
    return home() / "outfits.toml"


def principles() -> Path:
    return home() / "principles.toml"


def palette() -> Path:
    return home() / "palette.toml"


def sourcing() -> Path:
    return home() / "sourcing.toml"


def retailers() -> Path:
    return home() / "retailers.toml"


def vocabulary() -> Path:
    return home() / "garments.toml"


def fittings() -> Path:
    return home() / "fittings.toml"


def guide_versions() -> Path:
    return home() / ".guide-versions"


def photos() -> Path:
    return home() / "inventory" / "photos"


def looks() -> Path:
    return home() / "out" / "looks"


def products() -> Path:
    return home() / "out" / "products"


def backups() -> Path:
    return home() / ".wardrobe-backups"


# Everything the app writes, in the order a human would want it listed. The
# reset panel builds its checkboxes straight off this, so a new data file added
# here becomes resettable with no further work.
DATA: dict[str, str] = {
    "answers": "Questionnaire answers",
    "guide": "Style guide",
    "principles": "Principles",
    "palette": "Colour palette",
    "sourcing": "Where to buy",
    "retailers": "Retailer catalogue",
    "vocabulary": "Garment catalogue",
    "fittings": "Known sizes",
    "inventory": "Wardrobe inventory",
    "outfits": "Outfits",
    "photos": "Item photos",
    "looks": "Generated look images",
    "products": "Generated product shots",
    "profile": "Subject profile",
}

# Cleared by default. The subject profile is left alone: his height and skin
# tone are not test data, and losing them to a stray click would be maddening.
DEFAULT_CLEAR: tuple[str, ...] = tuple(k for k in DATA if k != "profile")


def resolve(key: str) -> Path:
    return globals()[key]()


def is_scratch() -> bool:
    """True when pointed somewhere other than the working directory."""
    return ENV_VAR in os.environ
