"""pytest wrapper over the same checks the app runs.

One suite, two front doors: `uv run pytest` here, or the Diagnostics tab in the
app. Keeping a single definition means the button and CI can never drift apart.

The live group is skipped unless WARDROBE_LIVE=1, since it calls Vertex AI for
real and costs money. The browser group is skipped unless WARDROBE_BROWSER=1,
since it starts a server and drives Chromium, which is slow.
"""

from __future__ import annotations

import os

import pytest

from wardrobe import checks

SLOW = {checks.LIVE, checks.BROWSER}
OFFLINE = [(g, n) for g, n, _ in checks.CHECKS if g not in SLOW]
LIVE = [(g, n) for g, n, _ in checks.CHECKS if g == checks.LIVE]
BROWSER = [(g, n) for g, n, _ in checks.CHECKS if g == checks.BROWSER]
BY_NAME = {name: fn for _, name, fn in checks.CHECKS}


def _run(name: str) -> None:
    with checks.scratch_home():
        detail = BY_NAME[name]()
    print(f"\n  {name}: {detail}")


@pytest.mark.parametrize("group,name", OFFLINE, ids=[n for _, n in OFFLINE])
def test_offline(group: str, name: str) -> None:
    _run(name)


@pytest.mark.skipif(os.environ.get("WARDROBE_LIVE") != "1",
                    reason="set WARDROBE_LIVE=1 to call Vertex AI for real")
@pytest.mark.parametrize("group,name", LIVE, ids=[n for _, n in LIVE])
def test_live(group: str, name: str) -> None:
    _run(name)


@pytest.mark.skipif(os.environ.get("WARDROBE_BROWSER") != "1",
                    reason="set WARDROBE_BROWSER=1 to drive a real browser")
@pytest.mark.parametrize("group,name", BROWSER, ids=[n for _, n in BROWSER])
def test_browser(group: str, name: str) -> None:
    _run(name)
