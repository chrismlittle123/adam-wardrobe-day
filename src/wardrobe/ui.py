"""Shared rendering: the styling, and the small pieces every tab reuses.

The palette is taken off the reference photograph rather than chosen: walnut
ground, the brass of the gold chain-stitch on his collar, the cream of the
shirt. Bodoni Moda appears only in the masthead and item names, IBM Plex Mono
carries every number, Karla does the rest.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

import streamlit as st
from PIL import Image, UnidentifiedImageError

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bodoni+Moda:opsz,wght@6..96,400;6..96,600&family=Karla:wght@300;400;500;700&family=IBM+Plex+Mono:wght@300;400;500&display=swap');

:root {
  --ground: #17110E; --panel: #211915; --raise: #2C211B;
  --brass: #C9A227; --cream: #F0E6DB; --muted: #8A7767;
  --line: rgba(201,162,39,.22); --good: #7FA86B; --bad: #B4574A;
}

.stApp { background: var(--ground); }
html, body, [class*="css"], .stMarkdown, p, li, label, div[data-baseweb] {
  font-family: 'Karla', system-ui, sans-serif; color: var(--cream);
}
[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }
[data-testid="stSidebar"] { background: var(--panel); border-right: 1px solid var(--line); }

.masthead { padding: 1.6rem 0 1rem; border-bottom: 1px solid var(--line); margin-bottom: 1.4rem; }
.masthead h1 {
  font-family: 'Bodoni Moda', Georgia, serif; font-weight: 400;
  font-size: clamp(2rem, 4vw, 3rem); letter-spacing: .01em; line-height: 1; margin: 0;
}
.masthead h1 em { font-style: italic; color: var(--brass); }
.masthead .sub {
  font-family: 'IBM Plex Mono', monospace; font-size: .68rem; letter-spacing: .22em;
  text-transform: uppercase; color: var(--muted); margin-top: .6rem;
}

.eyebrow {
  font-family: 'IBM Plex Mono', monospace; font-size: .68rem; letter-spacing: .22em;
  text-transform: uppercase; color: var(--brass); margin: 1.6rem 0 .9rem;
  display: flex; align-items: center; gap: .8rem;
}
.eyebrow::after { content: ""; flex: 1 1 auto; height: 1px; background: var(--line); }
.blurb { color: var(--muted); font-size: .86rem; line-height: 1.6; margin: 0 0 1.2rem; }

/* Docket ------------------------------------------------------------------ */
.docket { background: var(--panel); border: 1px solid var(--line); padding: 1.1rem 1.2rem .9rem; }
.docket .name { font-family: 'Bodoni Moda', Georgia, serif; font-size: 1.5rem; margin: 0 0 1rem; }
.docket dl { margin: 0; }
.docket .row { display: flex; align-items: baseline; margin: 0 0 .55rem; }
.docket dt {
  font-family: 'IBM Plex Mono', monospace; font-size: .64rem; letter-spacing: .13em;
  text-transform: uppercase; color: var(--muted); white-space: nowrap;
}
.docket .leader {
  flex: 1 1 auto; border-bottom: 1px dotted rgba(240,230,219,.22);
  margin: 0 .5rem; transform: translateY(-.28rem); min-width: .8rem;
}
.docket dd {
  margin: 0; font-family: 'IBM Plex Mono', monospace; font-size: .78rem; text-align: right;
}
.docket dd.prose { font-family: 'Karla', sans-serif; font-size: .8rem; max-width: 64%; }
.docket .note {
  margin: .9rem 0 0; padding-top: .8rem; border-top: 1px solid var(--line);
  font-size: .76rem; color: var(--muted); line-height: 1.5;
}
.chip {
  display: inline-block; width: .78rem; height: .78rem; margin-right: .45rem;
  border: 1px solid rgba(240,230,219,.35); vertical-align: -1px;
}

/* Plates ------------------------------------------------------------------ */
.plate { border: 1px solid var(--line); padding: .4rem; background: var(--panel); }
.plate img { display: block; width: 100%; }
.plate .cap {
  font-family: 'IBM Plex Mono', monospace; font-size: .62rem; letter-spacing: .14em;
  text-transform: uppercase; color: var(--muted); padding: .55rem .2rem .1rem;
  display: flex; justify-content: space-between; gap: .6rem;
}

/* Controls ---------------------------------------------------------------- */
.stTextArea textarea, .stTextInput input, .stNumberInput input {
  background: var(--panel) !important; color: var(--cream) !important;
  border: 1px solid var(--line) !important; border-radius: 0 !important;
  font-family: 'Karla', sans-serif !important;
}
.stTextArea textarea:focus, .stTextInput input:focus { border-color: var(--brass) !important; box-shadow: none !important; }
div[data-baseweb="select"] > div, div[data-baseweb="input"] {
  background: var(--panel) !important; border: 1px solid var(--line) !important; border-radius: 0 !important;
}
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
  background: var(--brass); color: #17110E; border: none; border-radius: 0;
  font-family: 'IBM Plex Mono', monospace; font-size: .68rem; letter-spacing: .16em;
  text-transform: uppercase; padding: .6rem 1.2rem; font-weight: 500;
  transition: background .18s ease, transform .18s ease;
}
.stButton > button:hover, .stFormSubmitButton > button:hover, .stDownloadButton > button:hover {
  background: var(--cream); transform: translateY(-1px);
}
.stButton > button:focus-visible, .stFormSubmitButton > button:focus-visible {
  outline: 2px solid var(--cream); outline-offset: 3px;
}
.stButton > button[kind="secondary"] {
  background: transparent; color: var(--muted); border: 1px solid var(--line);
}
.stButton > button[kind="secondary"]:hover { color: var(--cream); border-color: var(--brass); background: transparent; }
label, .stSlider label, .stSelectbox label, .stMultiSelect label, .stNumberInput label {
  font-family: 'IBM Plex Mono', monospace !important; font-size: .66rem !important;
  letter-spacing: .14em !important; text-transform: uppercase !important; color: var(--muted) !important;
}
details summary { font-family: 'IBM Plex Mono', monospace !important; font-size: .68rem !important;
  letter-spacing: .14em !important; text-transform: uppercase !important; }
.stCode, pre, code { font-family: 'IBM Plex Mono', monospace !important; font-size: .76rem !important; }

/* Tabs -------------------------------------------------------------------- */
.stTabs [data-baseweb="tab-list"] { gap: 1.6rem; border-bottom: 1px solid var(--line); flex-wrap: wrap; }
.stTabs [data-baseweb="tab"] {
  font-family: 'IBM Plex Mono', monospace; font-size: .7rem; letter-spacing: .16em;
  text-transform: uppercase; color: var(--muted); background: transparent; padding: .3rem 0 .8rem;
}
.stTabs [aria-selected="true"] { color: var(--brass) !important; }
.stTabs [data-baseweb="tab-highlight"] { background: var(--brass); }

/* Meter ------------------------------------------------------------------- */
.meter { margin: 0 0 1.4rem; }
.meter .track { height: 2px; background: rgba(240,230,219,.12); }
.meter .fill { height: 2px; background: var(--brass); }
.meter .read {
  font-family: 'IBM Plex Mono', monospace; font-size: .66rem; letter-spacing: .14em;
  text-transform: uppercase; color: var(--muted); display: flex;
  justify-content: space-between; padding-bottom: .45rem;
}
.meter .read b { color: var(--cream); font-weight: 500; }

/* Stats ------------------------------------------------------------------- */
.stats { display: flex; gap: 2.2rem; flex-wrap: wrap; margin: 0 0 1.4rem; }
.stat .k {
  font-family: 'IBM Plex Mono', monospace; font-size: .62rem; letter-spacing: .16em;
  text-transform: uppercase; color: var(--muted);
}
.stat .v { font-family: 'Bodoni Moda', Georgia, serif; font-size: 1.7rem; line-height: 1.2; }
.stat .v.brass { color: var(--brass); }

/* Item card --------------------------------------------------------------- */
.item { background: var(--panel); border: 1px solid var(--line); padding: .8rem .9rem; height: 100%; }
.item .top { display: flex; align-items: center; gap: .6rem; margin-bottom: .5rem; }
.item .nm { font-family: 'Bodoni Moda', Georgia, serif; font-size: 1.05rem; line-height: 1.2; }
.item .meta {
  font-family: 'IBM Plex Mono', monospace; font-size: .64rem; color: var(--muted);
  letter-spacing: .08em; line-height: 1.7;
}
.item .price { color: var(--cream); }
.badge {
  font-family: 'IBM Plex Mono', monospace; font-size: .56rem; letter-spacing: .14em;
  text-transform: uppercase; padding: .12rem .4rem; border: 1px solid var(--line);
  color: var(--muted); white-space: nowrap;
}
.badge.want { color: var(--brass); border-color: var(--brass); }
.badge.ok { color: var(--good); border-color: rgba(127,168,107,.5); }
.badge.no { color: var(--bad); border-color: rgba(180,87,74,.5); }
.swatch { width: 100%; height: 5.2rem; border: 1px solid var(--line); }

/* Tables ------------------------------------------------------------------ */
.tbl { width: 100%; border-collapse: collapse; font-family: 'IBM Plex Mono', monospace; font-size: .74rem; }
.tbl th {
  text-align: left; color: var(--muted); font-weight: 400; letter-spacing: .14em;
  text-transform: uppercase; font-size: .6rem; padding: .4rem .6rem; border-bottom: 1px solid var(--line);
}
.tbl td { padding: .45rem .6rem; border-bottom: 1px solid rgba(240,230,219,.07); }
.tbl td.num { text-align: right; color: var(--cream); }
.tbl tr:hover td { background: rgba(201,162,39,.05); }
.est { color: var(--brass); }

/* Plan -------------------------------------------------------------------- */
.step { background: var(--panel); border: 1px solid var(--line); border-left: 2px solid var(--brass);
        padding: .9rem 1.1rem; margin-bottom: .7rem; }
.step .hd { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
.step .n { font-family: 'Bodoni Moda', Georgia, serif; font-size: 1.2rem; color: var(--brass); }
.step .pieces { font-size: .92rem; }
.step .cost { font-family: 'IBM Plex Mono', monospace; font-size: .95rem; }
.step .why { font-family: 'IBM Plex Mono', monospace; font-size: .64rem; color: var(--muted);
             letter-spacing: .08em; margin-top: .45rem; line-height: 1.7; }

.guide-body { background: var(--panel); border: 1px solid var(--line); padding: 1.6rem 1.8rem; }
.guide-body h1 { font-family: 'Bodoni Moda', Georgia, serif; font-weight: 400; font-size: 2rem; margin: 0 0 1rem; }
.guide-body h2 { font-family: 'IBM Plex Mono', monospace; font-size: .7rem; letter-spacing: .2em;
                 text-transform: uppercase; color: var(--brass); margin: 1.8rem 0 .7rem; }
.guide-body table { border-collapse: collapse; width: 100%; font-size: .84rem; }
.guide-body th, .guide-body td { border-bottom: 1px solid var(--line); padding: .45rem .6rem; text-align: left; }

.empty { border: 1px dashed var(--line); padding: 2.4rem 1.6rem; text-align: center;
         color: var(--muted); font-size: .88rem; }
.look-cap { font-family: 'IBM Plex Mono', monospace; font-size: .64rem; letter-spacing: .1em;
            color: var(--muted); padding-top: .45rem; line-height: 1.6; }
.look-cap a, .answer-nav a { color: var(--brass); text-decoration: none; border-bottom: 1px solid transparent; }
.look-cap a:hover, .answer-nav a:hover { border-bottom-color: var(--brass); }

/* Single-answer view ------------------------------------------------------ */
.answer-q {
  font-family: 'Bodoni Moda', Georgia, serif; font-size: clamp(1.5rem, 3vw, 2.2rem);
  font-weight: 400; line-height: 1.25; margin: 0 0 1.4rem; max-width: 34ch;
}
.answer-a {
  font-size: 1.06rem; line-height: 1.75; white-space: pre-wrap; max-width: 62ch;
  border-left: 2px solid var(--brass); padding: .2rem 0 .2rem 1.4rem;
}
.answer-nav {
  font-family: 'IBM Plex Mono', monospace; font-size: .66rem; letter-spacing: .12em;
  text-transform: uppercase; color: var(--muted); display: flex; gap: 1.6rem;
  flex-wrap: wrap; padding: 1.2rem 0; border-top: 1px solid var(--line); margin-top: 2rem;
}
.answer-index a { display: block; padding: .35rem 0; border-bottom: 1px solid rgba(240,230,219,.07); }

/* Point allocation -------------------------------------------------------- */
.qlabel { font-size: .95rem; color: var(--cream); margin: .5rem 0 .1rem; line-height: 1.5; }
.alloc { display: flex; height: 6px; margin: .7rem 0 .4rem; background: rgba(240,230,219,.10); }
.alloc span { display: block; height: 6px; }
.alloc .s0 { background: var(--brass); }
.alloc .s1 { background: #A8862B; }
.alloc .s2 { background: #7E6626; }
.alloc .s3 { background: #584820; }
.alloc-read {
  font-family: 'IBM Plex Mono', monospace; font-size: .64rem; letter-spacing: .14em;
  text-transform: uppercase; color: var(--muted); display: flex; justify-content: space-between;
}
.alloc-read b { color: var(--cream); font-weight: 500; }
.alloc-read.off b { color: var(--bad); }

@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
"""


@st.cache_data(show_spinner=False)
def thumb_b64(path: str, mtime: float, width: int = 640) -> str:
    """Downscaled base64 PNG. mtime is in the signature so edits bust the cache."""
    img = Image.open(path).convert("RGB")
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def plate(path: Path, label: str = "", right: str = "", width: int = 640) -> None:
    """Render an image in a frame, or a placeholder if it cannot be read.

    A truncated or half-written file must not take the page down with it. One
    corrupt look in the gallery used to raise straight out of the render and
    kill every tab at once.
    """
    try:
        b64 = thumb_b64(str(path), path.stat().st_mtime, width)
    except (UnidentifiedImageError, OSError, ValueError):
        st.markdown(
            '<div class="plate"><div class="empty" style="padding:2rem 1rem">'
            f'{path.name}<br>could not be read</div></div>', unsafe_allow_html=True)
        return
    cap = (f'<div class="cap"><span>{label}</span><span>{right}</span></div>'
           if label or right else "")
    st.markdown(
        f'<div class="plate"><img src="data:image/png;base64,{b64}" alt="{label}">{cap}</div>',
        unsafe_allow_html=True,
    )


def eyebrow(text: str) -> None:
    st.markdown(f'<div class="eyebrow">{text}</div>', unsafe_allow_html=True)


def blurb(text: str) -> None:
    st.markdown(f'<p class="blurb">{text}</p>', unsafe_allow_html=True)


def empty(text: str) -> None:
    st.markdown(f'<div class="empty">{text}</div>', unsafe_allow_html=True)


def meter(done: int, total: int, label: str) -> None:
    pct = round(100 * done / total) if total else 0
    st.markdown(
        f'<div class="meter"><div class="read"><span>{label}</span>'
        f'<span><b>{done}</b> of {total}</span></div>'
        f'<div class="track"><div class="fill" style="width:{pct}%"></div></div></div>',
        unsafe_allow_html=True,
    )


def stats(pairs: list[tuple[str, str]], brass_first: bool = False) -> None:
    cells = "".join(
        f'<div class="stat"><div class="k">{k}</div>'
        f'<div class="v{" brass" if brass_first and n == 0 else ""}">{v}</div></div>'
        for n, (k, v) in enumerate(pairs)
    )
    st.markdown(f'<div class="stats">{cells}</div>', unsafe_allow_html=True)


def table(rows: list[dict[str, str]], numeric: tuple[str, ...] = ()) -> None:
    if not rows:
        return
    head = "".join(f"<th>{k}</th>" for k in rows[0])
    body = "".join(
        "<tr>" + "".join(
            f'<td class="num">{v}</td>' if k in numeric else f"<td>{v}</td>"
            for k, v in row.items()
        ) + "</tr>"
        for row in rows
    )
    st.markdown(f'<table class="tbl"><tr>{head}</tr>{body}</table>', unsafe_allow_html=True)



def swatch_strip(colours, height: str = "2.6rem") -> str:
    """A row of colours as one continuous band, the way a palette is presented."""
    cells = "".join(
        f'<div style="flex:1;background:{c.hex};height:{height}" title="{c.name or c.hex}"></div>'
        for c in colours)
    return f'<div style="display:flex;border:1px solid var(--line)">{cells}</div>'


SHOP_CSS = """
<style>
.product { background: var(--panel); border: 1px solid var(--line); height: 100%; }
.product .shot { position: relative; background: #F6F4EF; }
.product .shot img { display: block; width: 100%; }
.product .none {
  height: 16rem; display: flex; align-items: center; justify-content: center;
  color: #8A7767; font-family: 'IBM Plex Mono', monospace; font-size: .66rem;
  letter-spacing: .16em; text-transform: uppercase; background: var(--raise);
}
.product .body { padding: 1rem 1.1rem 1.2rem; }
.product .nm {
  font-family: 'Bodoni Moda', Georgia, serif; font-size: 1.25rem; line-height: 1.25;
  margin-bottom: .2rem;
}
.product .kind {
  font-family: 'IBM Plex Mono', monospace; font-size: .62rem; letter-spacing: .18em;
  text-transform: uppercase; color: var(--muted);
}
.product .price {
  font-family: 'IBM Plex Mono', monospace; font-size: 1.05rem; color: var(--cream);
  margin: .6rem 0 .3rem;
}
.product .route {
  font-family: 'IBM Plex Mono', monospace; font-size: .62rem; letter-spacing: .1em;
  color: var(--brass); border-top: 1px solid var(--line); padding-top: .5rem;
  margin-top: .5rem; line-height: 1.6;
}
.product .route.none { color: var(--bad); }
.product .size {
  font-family: 'IBM Plex Mono', monospace; font-size: .62rem; color: var(--muted);
  line-height: 1.7;
}
.product .flag {
  position: absolute; top: .6rem; left: .6rem; background: var(--brass); color: #17110E;
  font-family: 'IBM Plex Mono', monospace; font-size: .56rem; letter-spacing: .14em;
  text-transform: uppercase; padding: .2rem .5rem;
}
.product a.view {
  display: block; text-align: center; padding: .7rem; margin-top: .9rem;
  background: var(--brass); color: #17110E; text-decoration: none;
  font-family: 'IBM Plex Mono', monospace; font-size: .66rem; letter-spacing: .16em;
  text-transform: uppercase;
}
.product a.view:hover { background: var(--cream); }

.shopfront { display: flex; gap: 1.2rem; align-items: flex-start; }
.buy {
  background: var(--panel); border: 1px solid var(--line); border-left: 2px solid var(--brass);
  padding: .85rem 1.1rem; margin-bottom: .6rem;
}
.buy .hd { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
.buy .who { font-size: 1rem; }
.buy .kind {
  font-family: 'IBM Plex Mono', monospace; font-size: .58rem; letter-spacing: .14em;
  text-transform: uppercase; color: var(--muted);
}
.buy .why {
  font-family: 'Karla', sans-serif; font-size: .82rem; color: var(--muted);
  margin-top: .35rem; line-height: 1.6;
}
.buy a {
  font-family: 'IBM Plex Mono', monospace; font-size: .62rem; letter-spacing: .14em;
  text-transform: uppercase; color: var(--brass); text-decoration: none;
}
.buy a:hover { border-bottom: 1px solid var(--brass); }
.route-card {
  background: var(--raise); border: 1px solid var(--brass); padding: 1rem 1.2rem;
  margin-bottom: 1.2rem;
}
.route-card .hd { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
.route-card .who { font-family: 'Bodoni Moda', Georgia, serif; font-size: 1.35rem; }
.route-card .kind {
  font-family: 'IBM Plex Mono', monospace; font-size: .58rem; letter-spacing: .16em;
  text-transform: uppercase; color: var(--brass);
}
.route-card .term {
  font-family: 'IBM Plex Mono', monospace; font-size: .68rem; color: var(--cream);
  letter-spacing: .06em; margin-top: .5rem;
}
.route-card .term b { color: var(--muted); font-weight: 400; margin-right: .5rem; }
.route-card .why { color: var(--muted); font-size: .85rem; line-height: 1.6; margin-top: .7rem; }
.route-card .links { margin-top: .9rem; display: flex; gap: 1.2rem; flex-wrap: wrap; }
.route-card .links a {
  font-family: 'IBM Plex Mono', monospace; font-size: .64rem; letter-spacing: .14em;
  text-transform: uppercase; color: #17110E; background: var(--brass);
  padding: .5rem .9rem; text-decoration: none;
}
.route-card .links a:hover { background: var(--cream); }
.tactic { border-left: 2px solid rgba(201,162,39,.35); padding: .1rem 0 .1rem 1rem; margin: .8rem 0; }
.tactic .t { font-size: .95rem; }
.tactic .d { color: var(--muted); font-size: .84rem; line-height: 1.65; margin-top: .2rem; }
.tactic .w {
  font-family: 'IBM Plex Mono', monospace; font-size: .58rem; letter-spacing: .14em;
  text-transform: uppercase; color: var(--brass); margin-top: .3rem;
}
</style>
"""


def product_shot(path: Path | None, flag: str = "", width: int = 700) -> str:
    """The image half of a product card, as an HTML fragment."""
    tag = f'<div class="flag">{flag}</div>' if flag else ""
    if not path or not Path(path).is_file():
        return f'<div class="shot">{tag}<div class="none">no photograph yet</div></div>'
    try:
        b64 = thumb_b64(str(path), Path(path).stat().st_mtime, width)
    except (UnidentifiedImageError, OSError, ValueError):
        return f'<div class="shot">{tag}<div class="none">could not be read</div></div>'
    return f'<div class="shot">{tag}<img src="data:image/png;base64,{b64}" alt=""></div>'
