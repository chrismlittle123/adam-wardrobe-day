"""Generate (and edit) images with Gemini on Vertex AI.

Auth: uses Application Default Credentials if present, otherwise falls back to
the access token from the `gcloud` CLI you are already logged into. So a plain
`gcloud auth login` is enough, no ADC dance required.

CLI:
    uv run gemini-image "a navy overshirt on a plain background"
    uv run gemini-image "make the collar wider" --image inventory/shirt.jpg
    uv run gemini-image "three outfit flat-lays" -n 3 -o out/outfits
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

DEFAULT_MODEL = "gemini-2.5-flash-image"
DEFAULT_LOCATION = "us-central1"


class GeminiImageError(RuntimeError):
    """Anything that stops us getting pixels back."""


@dataclass(frozen=True)
class Settings:
    project: str
    location: str
    model: str

    @classmethod
    def from_env(cls, model: str | None = None) -> "Settings":
        load_dotenv()
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or _gcloud("config", "get-value", "project")
        if not project or project == "(unset)":
            raise GeminiImageError(
                "No Google Cloud project. Set GOOGLE_CLOUD_PROJECT in .env or run "
                "`gcloud config set project <project-id>`."
            )
        return cls(
            project=project,
            location=os.getenv("GOOGLE_CLOUD_LOCATION", DEFAULT_LOCATION),
            model=model or os.getenv("GEMINI_IMAGE_MODEL", DEFAULT_MODEL),
        )


def _gcloud(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["gcloud", *args], capture_output=True, text=True, timeout=30, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _credentials():
    """ADC if available, otherwise borrow the gcloud CLI's access token."""
    try:
        import google.auth

        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return creds
    except Exception:
        pass

    token = _gcloud("auth", "print-access-token")
    if not token:
        raise GeminiImageError(
            "Not authenticated. Run `gcloud auth login` (or "
            "`gcloud auth application-default login` for long-lived credentials)."
        )
    from google.oauth2.credentials import Credentials

    return Credentials(token=token)


def build_client(settings: Settings) -> genai.Client:
    return genai.Client(
        vertexai=True,
        project=settings.project,
        location=settings.location,
        credentials=_credentials(),
    )


def _part_from_image(path: Path) -> types.Part:
    mime, _ = mimetypes.guess_type(path.name)
    if not mime or not mime.startswith("image/"):
        raise GeminiImageError(f"{path} does not look like an image file.")
    return types.Part.from_bytes(data=path.read_bytes(), mime_type=mime)


def _generate_one(
    client: genai.Client,
    settings: Settings,
    contents: list[types.Content],
    out_path_stem: Path,
    index: int,
) -> list[Path]:
    config = types.GenerateContentConfig(
        response_modalities=["TEXT", "IMAGE"],
        # We never pass tools, and leaving AFC on just emits a noisy warning.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    try:
        response = client.models.generate_content(
            model=settings.model, contents=contents, config=config
        )
    except errors.APIError as exc:
        raise GeminiImageError(f"Vertex AI rejected the request: {exc}") from exc

    if not response.candidates:
        raise GeminiImageError(
            f"Model returned no candidates (prompt feedback: {response.prompt_feedback})."
        )

    written: list[Path] = []
    for candidate in response.candidates:
        if not candidate.content or not candidate.content.parts:
            continue
        for part in candidate.content.parts:
            if part.text:
                print(part.text.strip(), file=sys.stderr)
            inline = part.inline_data
            if not inline or not inline.data:
                continue
            ext = mimetypes.guess_extension(inline.mime_type or "image/png") or ".png"
            suffix = f"-{index}" if index else ""
            if written:
                suffix = f"{suffix}-{len(written) + 1}"
            path = out_path_stem.with_name(f"{out_path_stem.name}{suffix}{ext}")
            path.write_bytes(inline.data)
            written.append(path)

    if not written:
        finish = [c.finish_reason for c in response.candidates]
        raise GeminiImageError(
            f"No image data came back. Finish reasons: {finish}. "
            "The prompt may have been blocked by safety filters."
        )
    return written


def generate_images(
    prompt: str,
    *,
    out_prefix: Path,
    reference_images: list[Path] | None = None,
    count: int = 1,
    settings: Settings | None = None,
) -> list[Path]:
    """Generate `count` images and write them next to `out_prefix`.

    The image models only return one candidate per request, so `count` becomes
    `count` separate calls. Any text the model returns alongside an image goes to
    stderr, since it is usually a caption or an explanation of a refusal.

    Returns the paths written.
    """
    if count < 1:
        raise GeminiImageError("count must be at least 1.")

    settings = settings or Settings.from_env()
    client = build_client(settings)

    parts: list[types.Part] = [_part_from_image(p) for p in (reference_images or [])]
    parts.append(types.Part.from_text(text=prompt))
    contents = [types.Content(role="user", parts=parts)]

    out_prefix.parent.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for i in range(count):
        # Index of 0 keeps the single-image case as a bare `<prefix>.png`.
        written.extend(_generate_one(client, settings, contents, out_prefix, 0 if count == 1 else i + 1))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gemini-image",
        description="Generate or edit images with Gemini on Vertex AI.",
    )
    parser.add_argument("prompt", help="What to draw, or how to change the input images.")
    parser.add_argument(
        "-o",
        "--out",
        default="out/image",
        help="Output path prefix; the extension is chosen from the response (default: out/image).",
    )
    parser.add_argument(
        "-i",
        "--image",
        action="append",
        default=[],
        metavar="PATH",
        help="Reference image to edit or riff on. Repeatable.",
    )
    parser.add_argument("-n", "--count", type=int, default=1, help="How many images (default: 1).")
    parser.add_argument("-m", "--model", default=None, help=f"Override model (default: {DEFAULT_MODEL}).")
    args = parser.parse_args(argv)

    refs = [Path(p) for p in args.image]
    for ref in refs:
        if not ref.is_file():
            print(f"error: reference image not found: {ref}", file=sys.stderr)
            return 2

    try:
        settings = Settings.from_env(args.model)
        paths = generate_images(
            args.prompt,
            out_prefix=Path(args.out),
            reference_images=refs,
            count=args.count,
            settings=settings,
        )
    except GeminiImageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
