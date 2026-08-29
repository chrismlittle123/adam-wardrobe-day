"""Look at the app in a real browser and complain about what you see.

Two CSS regressions shipped without a test noticing, because neither was a
broken selector: both matched something, just the wrong thing.

  1. Streamlit dropped data-baseweb, so four blocks matched nothing at all. The
     inputs went back to framework grey and the sub-tabs to sentence case.
  2. `[role="tablist"] + div` was written meaning "the highlight bar under the
     tabs". It is the tab panel. The entire garment catalogue turned brass.

Neither can be caught by reading the stylesheet, because both are about what a
selector lands on. That needs a browser, so this module drives one. It is not
in the normal suite: it needs a server and a Chromium, and it is slow. Run it
with `uv run wardrobe-check --browser`, or WARDROBE_BROWSER=1 under pytest.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

PORT = int(os.environ.get("WARDROBE_BROWSER_PORT", "8599"))
APP = Path(__file__).with_name("app.py")

# Every view the app can show, as a query string.
VIEWS: tuple[tuple[str, str], ...] = (
    ("style-guide", "page=style-guide"), ("garments", "page=garments"),
    ("inventory", "page=inventory"), ("principles", "page=principles"),
    ("colour", "page=colour"), ("generator", "page=generator"),
    ("gallery", "page=gallery"), ("where-to-buy", "page=where-to-buy"),
    ("measurements", "page=measurements"), ("shop", "page=shop"),
    ("diagnostics", "page=diagnostics"),
    ("catalogue:garments", "garments=all"), ("catalogue:colours", "colours=all"),
    ("catalogue:shops", "shops=all"), ("index:answers", "answer=all"),
)

# The accents. Small things may be painted in these; a whole panel may not.
ACCENTS = {"rgb(201, 162, 39)": "brass", "rgb(240, 230, 219)": "cream",
           "rgb(180, 87, 74)": "red", "rgb(127, 168, 107)": "green"}
FLOOD = 60000   # px², about a quarter of a laptop screen


def _free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


@contextmanager
def server(port: int = PORT) -> Iterator[str]:
    """A Streamlit on its own port, torn down afterwards."""
    if not _free(port):
        yield f"http://localhost:{port}"
        return
    proc = subprocess.Popen(
        ["streamlit", "run", str(APP), "--server.port", str(port),
         "--server.headless", "true", "--browser.gatherUsageStats", "false"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            if not _free(port):
                time.sleep(2)
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(f"streamlit never came up on {port}")
        yield f"http://localhost:{port}"
    finally:
        proc.terminate()
        proc.wait(timeout=20)


PROBE = """() => {
  const main = document.querySelector('[data-testid="stMain"]');
  const out = {flooded: [], unstyled: [], exception: '', text: ''};
  const exc = document.querySelector('[data-testid="stException"]');
  if (exc) out.exception = exc.innerText.slice(0, 140);
  out.text = document.body.innerText;
  if (!main) return out;
  main.querySelectorAll('*').forEach(e => {
    const r = e.getBoundingClientRect();
    const cs = getComputedStyle(e);
    if (r.width * r.height > FLOOD_PX && ACCENT_LIST.includes(cs.backgroundColor)) {
      out.flooded.push(`${e.tagName}[${e.dataset.testid || e.className.toString().slice(0,24)}] `
                     + `${Math.round(r.width)}x${Math.round(r.height)} ${cs.backgroundColor}`);
    }
  });
  main.querySelectorAll('p, h1, h2, h3, td, th, li, label').forEach(e => {
    const f = getComputedStyle(e).fontFamily;
    if (!/Bodoni|Jost|IBM Plex/.test(f)) out.unstyled.push(f.slice(0, 34));
  });
  out.flooded = [...new Set(out.flooded)];
  out.unstyled = [...new Set(out.unstyled)];
  return out;
}"""


def sweep(url: str, views=VIEWS, width: int = 1440, height: int = 950) -> dict[str, list[str]]:
    """Load every view and report what is wrong with it."""
    from playwright.sync_api import sync_playwright

    script = (PROBE.replace("FLOOD_PX", str(FLOOD))
                   .replace("ACCENT_LIST", repr(list(ACCENTS)).replace("'", '"')))
    faults: dict[str, list[str]] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        for name, query in views:
            page.goto(f"{url}/?{query}", wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(2500)
            seen = page.evaluate(script)
            bad: list[str] = []
            if seen["exception"]:
                bad.append(f"raised: {seen['exception']}")
            for patch in seen["flooded"]:
                bad.append(f"a whole panel painted an accent colour: {patch}")
            for font in seen["unstyled"]:
                bad.append(f"text in an unstyled font: {font}")
            if page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth + 2"):
                bad.append("the page scrolls sideways")
            if bad:
                faults[name] = bad
        browser.close()
    return faults
