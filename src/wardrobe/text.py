"""Wording. No dependencies, so anything may import it.

It exists for one job. The app printed "1 piece(s)", "17 colour(s)", "2 file(s)"
in nineteen places, which reads as a shrug: the code knew the number and still
would not commit to the word.
"""

from __future__ import annotations


def plural(count: int, singular: str, many: str = "") -> str:
    """1 piece, 2 pieces. Pass `many` for the ones English refuses to regularise."""
    return f"{count} {count_of(count, singular, many)}"


def count_of(count: int, singular: str, many: str = "") -> str:
    """The word alone, for when the number is already on the page."""
    return singular if abs(count) == 1 else (many or f"{singular}s")
