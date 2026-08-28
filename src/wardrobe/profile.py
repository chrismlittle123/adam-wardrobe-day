"""The subject: who we are dressing, loaded from profile.toml.

Body measurements live here too, in the full tailoring set, because every
garment target in fitspec is derived from them.

One file describes the man, and everything else reads from it. The app renders
it, the prompt builder folds it into every request, and the edit panel writes it
back. Nothing about the subject is hard-coded anywhere else.
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

from .fitspec import Body

DEFAULT_PROFILE_PATH = Path("profile.toml")

CM_PER_INCH = 2.54


@dataclass
class Style:
    direction: str = ""
    avoid: str = ""


@dataclass
class Subject:
    name: str = "Subject"
    height_cm: int = 0
    build: str = ""
    body_fat_pct: int = 0
    skin_tone_hex: str = "#000000"
    skin_tone: str = ""
    hair: str = ""
    facial_hair: str = ""
    eyes: str = ""
    details: str = ""

    @property
    def height_imperial(self) -> str:
        """1.76 m as 5 ft 9 in, for the benefit of the shops that still think so."""
        if not self.height_cm:
            return ""
        total_inches = round(self.height_cm / CM_PER_INCH)
        return f"{total_inches // 12} ft {total_inches % 12} in"

    @property
    def height_metric(self) -> str:
        return f"{self.height_cm / 100:.2f} m" if self.height_cm else ""


@dataclass
class Profile:
    subject: Subject = field(default_factory=Subject)
    photos: dict[str, str] = field(default_factory=dict)
    measurements: Body = field(default_factory=Body)
    style: Style = field(default_factory=Style)
    path: Path = DEFAULT_PROFILE_PATH

    @classmethod
    def load(cls, path: Path | str = DEFAULT_PROFILE_PATH) -> "Profile":
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(
                f"No subject profile at {path}. Copy profile.toml from the repo root, "
                "or run the app from the project directory."
            )
        raw = tomllib.loads(path.read_text())
        return cls(
            subject=_build(Subject, raw.get("subject", {})),
            photos=dict(raw.get("photos", {})),
            measurements=_build(Body, raw.get("measurements", {})),
            style=_build(Style, raw.get("style", {})),
            path=path,
        )

    def save(self) -> Path:
        payload = {
            "subject": asdict(self.subject),
            "photos": self.photos,
            "measurements": asdict(self.measurements),
            "style": asdict(self.style),
        }
        self.path.write_text(tomli_w.dumps(payload))
        return self.path

    def photo(self, which: str = "neutral") -> Path | None:
        """The named reference photo, or the first one that actually exists."""
        candidate = self.photos.get(which)
        if candidate and Path(candidate).is_file():
            return Path(candidate)
        for value in self.photos.values():
            if value and Path(value).is_file():
                return Path(value)
        return None


def _build(cls, data: dict):
    """Instantiate a dataclass from TOML, ignoring keys it does not declare."""
    allowed = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in allowed})
