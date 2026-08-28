"""Text generation on the same Vertex AI project as the image tool.

Shares Settings and credentials with `gemini_image`, so a single `gcloud auth
login` covers both.
"""

from __future__ import annotations

import os

from google.genai import errors, types

from .gemini_image import Settings, build_client

DEFAULT_TEXT_MODEL = "gemini-2.5-pro"


class GeminiTextError(RuntimeError):
    """Anything that stops us getting words back."""


def generate_text(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    settings: Settings | None = None,
) -> str:
    settings = settings or Settings.from_env(
        model or os.getenv("GEMINI_TEXT_MODEL", DEFAULT_TEXT_MODEL)
    )
    client = build_client(settings)
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        # No tools are ever passed, and leaving AFC on just emits a noisy warning.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    try:
        response = client.models.generate_content(
            model=settings.model, contents=prompt, config=config
        )
    except errors.APIError as exc:
        raise GeminiTextError(f"Vertex AI rejected the request: {exc}") from exc

    text = (response.text or "").strip()
    if not text:
        finish = [c.finish_reason for c in (response.candidates or [])]
        raise GeminiTextError(
            f"No text came back. Finish reasons: {finish}. The prompt may have been blocked."
        )
    return text
