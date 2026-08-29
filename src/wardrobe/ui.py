"""Shared rendering: the styling, and the small pieces every tab reuses.

The palette is taken off the reference photograph rather than chosen: walnut
ground, the brass of the gold chain-stitch on his collar, the cream of the
Four faces, one job each, and never more than one job. Mono was doing three of
them at once, which is why everything small looked the same weight and nothing
told you what it was.

  --display  Bodoni Moda, the only serif in the app. Every title and header, and
             nothing else. A fashion masthead face, so it does the announcing.
  --chrome   Jost, geometric, for the small uppercase furniture: labels, buttons,
             tabs, badges, captions. Futura-descended caps are a fashion staple
             and it is unreadable in paragraphs, which is a feature: it cannot
             creep into the body text.
  --prose    IBM Plex Sans, humanist, for anything read as sentences. Open at
             small sizes as light text on a dark ground, where a geometric closes
             up and goes muddy.
  --data     IBM Plex Mono, for numbers, measurements, hex codes and sizes. Fixed
             width because the docket and the tables have to line up.

Prose and data are siblings by the same designer on the same skeleton, so a
measurement and the sentence explaining it sit together rather than merely
coexisting.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

import streamlit as st
from PIL import Image, UnidentifiedImageError

from .text import count_of, plural  # noqa: F401  (re-exported for the tabs)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bodoni+Moda:opsz,wght@6..96,400;6..96,600&family=Jost:wght@300;400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@300;400;500&display=swap');

:root {
  --ground: #17110E; --panel: #211915; --raise: #2C211B;
  --brass: #C9A227; --cream: #F0E6DB; --muted: #8A7767;
  --line: rgba(201,162,39,.22); --good: #7FA86B; --bad: #B4574A;

  --display: 'Bodoni Moda', Georgia, serif;
  --chrome:  'Jost', system-ui, sans-serif;
  --prose:   'IBM Plex Sans', system-ui, sans-serif;
  --data:    'IBM Plex Mono', ui-monospace, monospace;
}

.stApp { background: var(--ground); }
html, body, [class*="css"], .stMarkdown, p, li, label, td, th, [data-testid="stWidgetLabel"] {
  font-family: var(--prose); color: var(--cream);
}
[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }
[data-testid="stSidebar"] { background: var(--panel); border-right: 1px solid var(--line); }

.masthead { padding: 1.6rem 0 1rem; border-bottom: 1px solid var(--line); margin-bottom: 1.4rem; }
.masthead h1 {
  font-family: var(--display); font-weight: 400;
  font-size: clamp(2rem, 4vw, 3rem); letter-spacing: .01em; line-height: 1; margin: 0;
}
.masthead h1 em { font-style: italic; color: var(--brass); }
.masthead .sub {
  font-family: var(--chrome); font-size: 0.74rem; letter-spacing: .22em;
  text-transform: uppercase; color: var(--muted); margin-top: .6rem;
  margin-bottom: .2rem;
}

.eyebrow {
  font-family: var(--display); font-size: .95rem; letter-spacing: .14em;
  text-transform: uppercase; color: var(--brass); margin: 1.8rem 0 .9rem;
  display: flex; align-items: center; gap: .9rem;
}
.eyebrow::after { content: ""; flex: 1 1 auto; height: 1px; background: var(--line); }
.blurb { color: var(--muted); font-size: .86rem; line-height: 1.6; margin: 0 0 1.2rem; }

/* Docket ------------------------------------------------------------------ */
.docket { background: var(--panel); border: 1px solid var(--line); padding: 1.1rem 1.2rem .9rem; }
.docket .name { font-family: var(--display); font-size: 1.5rem; margin: 0 0 1rem; }
.docket dl { margin: 0; }
.docket .row { display: flex; align-items: baseline; margin: 0 0 .55rem; }
.docket dt {
  font-family: var(--chrome); font-size: 0.70rem; letter-spacing: .13em;
  text-transform: uppercase; color: var(--muted); white-space: nowrap;
}
.docket .leader {
  flex: 1 1 auto; border-bottom: 1px dotted rgba(240,230,219,.22);
  margin: 0 .5rem; transform: translateY(-.28rem); min-width: .8rem;
}
.docket dd {
  margin: 0; font-family: var(--data); font-size: 0.82rem; text-align: right;
}
.docket dd.prose { font-family: var(--prose); font-size: 0.82rem; max-width: 64%; }
.docket .note {
  margin: .9rem 0 0; padding-top: .8rem; border-top: 1px solid var(--line);
  font-size: 0.82rem; color: var(--muted); line-height: 1.5;
}
.chip {
  display: inline-block; width: .78rem; height: .78rem; margin-right: .45rem;
  border: 1px solid rgba(240,230,219,.35); vertical-align: -1px;
}

/* Plates ------------------------------------------------------------------ */
.plate { border: 1px solid var(--line); padding: .4rem; background: var(--panel); }
.plate img { display: block; width: 100%; }
.plate .cap {
  font-family: var(--chrome); font-size: 0.70rem; letter-spacing: .14em;
  text-transform: uppercase; color: var(--muted); padding: .55rem .2rem .1rem;
  display: flex; justify-content: space-between; gap: .6rem;
}

/* Controls ---------------------------------------------------------------- */
.stTextArea textarea, .stTextInput input, .stNumberInput input {
  background: var(--panel) !important; color: var(--cream) !important;
  border: 1px solid var(--line) !important; border-radius: 0 !important;
  font-family: var(--prose);
}
.stTextArea textarea:focus, .stTextInput input:focus { border-color: var(--brass) !important; box-shadow: none !important; }
/* Streamlit stopped exposing data-baseweb on these, so the old rule quietly
   matched nothing and the boxes reverted to the framework's own grey. */
[data-testid="stSelectbox"] > div > div,
[data-testid="stMultiSelect"] > div > div,
[data-testid="stTextInputRootElement"],
[data-testid="stTextAreaRootElement"],
[data-testid="stNumberInputContainer"] {
  background: var(--panel) !important; border: 1px solid var(--line) !important;
  border-radius: 0 !important;
}
[data-testid="stSelectbox"] > div > div:focus-within,
[data-testid="stMultiSelect"] > div > div:focus-within,
[data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stNumberInputContainer"]:focus-within { border-color: var(--brass) !important; }
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
  background: var(--brass); color: #17110E; border: none; border-radius: 0;
  font-family: var(--chrome); font-size: 0.74rem; letter-spacing: .12em;
  text-transform: uppercase; padding: .6rem .9rem; font-weight: 500;
  /* A label must never wrap. "Drop" came back as "DR / OP" in a narrow column,
     and a two-line button reads as two buttons. */
  white-space: nowrap; min-width: 0;
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
  font-family: var(--chrome); font-size: 0.74rem !important;
  letter-spacing: .14em !important; text-transform: uppercase !important; color: var(--muted) !important;
}
details summary { font-family: var(--chrome); font-size: 0.74rem !important;
  letter-spacing: .14em !important; text-transform: uppercase !important; }
.stCode, pre, code { font-family: var(--data); font-size: 0.82rem !important; }

/* Tabs, still used inside a page for sub-sections. Streamlit renamed these
   from data-baseweb to data-testid, so the old rules matched nothing and the
   sub-tabs had drifted back to sentence-case body text. */
[data-testid="stTabs"] [role="tablist"] {
  gap: 1.6rem; border-bottom: 1px solid var(--line); flex-wrap: wrap;
}
[data-testid="stTab"] {
  font-family: var(--chrome) !important; font-size: 0.78rem; letter-spacing: .16em;
  text-transform: uppercase; color: var(--muted); background: transparent;
  padding: .3rem 0 .8rem;
}
[data-testid="stTab"] p {
  font-family: var(--chrome) !important; font-size: 0.78rem !important;
  letter-spacing: .16em; text-transform: uppercase; color: inherit; margin: 0;
}
[data-testid="stTab"][aria-selected="true"], 
[data-testid="stTab"][aria-selected="true"] p { color: var(--brass) !important; }
/* The underline goes on the selected tab itself. It was briefly written as
   [role="tablist"] + div, meaning "the highlight bar after the tabs", which is
   in fact the tab panel: it painted the entire contents of the page brass. */
[data-testid="stTab"][aria-selected="true"] { box-shadow: inset 0 -2px 0 var(--brass); }
[data-testid="stTabPanel"] { background: transparent !important; }

/* Navigation: a running order, not a row of tabs -------------------------- */
/* Ten pages will not fit across the top without wrapping into an ugly second
   row, and the number matters as much as the name, so it reads as a contents
   page down the side. The radio dots are hidden: the brass rule does the work. */
[data-testid="stSidebar"] [role="radiogroup"] { gap: 0; margin: 0 0 1.5rem; }
[data-testid="stSidebar"] [role="radiogroup"] label {
  padding: .34rem 0 .34rem .85rem; margin: 0; border-left: 2px solid transparent;
  transition: border-color .15s ease, color .15s ease;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover { border-left-color: var(--line); }
/* Kill the radio dot itself. The brass rule down the left says which page you
   are on far more quietly than a filled circle does. The dot is three divs deep
   inside the label, after a visually-hidden span holding the real input. */
[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div > div:first-child {
  display: none !important;
}
[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div { gap: 0; }
[data-testid="stSidebar"] [role="radiogroup"] label p {
  font-family: var(--chrome); font-size: 0.80rem; letter-spacing: .13em;
  text-transform: uppercase; color: var(--muted); margin: 0; white-space: nowrap;
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
  border-left-color: var(--brass);
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {
  color: var(--brass); font-weight: 500;
}

/* The masthead, in the sidebar where it belongs -------------------------- */
.brand { padding: .2rem 0 1.3rem; margin-bottom: 1.2rem; border-bottom: 1px solid var(--line); }
.brand h1 {
  font-family: var(--display); font-weight: 400; font-size: 1.72rem;
  color: var(--cream); margin: 0; line-height: 1.05; letter-spacing: .01em;
}
.brand h1 em { font-style: italic; color: var(--brass); }
.brand .sub {
  font-family: var(--chrome); font-size: 0.60rem; letter-spacing: .17em;
  text-transform: uppercase; color: var(--muted); margin-top: .55rem; line-height: 1.7;
}

/* Streamlit's own chrome. The deploy button and the hamburger belong to the
   framework, not to this app, and they sit on top of the masthead.

   Hide them one by one, never the whole toolbar: the button that puts a
   collapsed sidebar back lives inside it, so display:none on the bar left no
   way of getting the navigation back short of reloading the page. */
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"],
[data-testid="stToolbarActions"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], #MainMenu, footer { display: none !important; }
[data-testid="stToolbar"] { display: flex !important; background: transparent; }
[data-testid="stExpandSidebarButton"] {
  display: flex !important; visibility: visible !important;
  color: var(--brass) !important; opacity: 1;
}
[data-testid="stExpandSidebarButton"]:hover { color: var(--cream) !important; }
.stAppHeader, header[data-testid="stHeader"] { background: transparent; height: 0; }
.stMainBlockContainer, [data-testid="stMainBlockContainer"] { padding-top: 2.4rem; }

/* Alerts. Streamlit paints stAlertContainer a translucent yellow, which in this
   walnut palette looks like a hi-vis vest at a funeral. The panel does the work
   instead, and the left edge carries the severity: brass for something to know,
   red for something wrong. */
[data-testid="stAlert"] { background: transparent !important; }
[data-testid="stAlertContainer"] {
  background: var(--panel) !important; border: 1px solid var(--line);
  border-left: 2px solid var(--brass); border-radius: 0;
  padding: .85rem 1rem; gap: 0;
}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]),
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) {
  border-left-color: var(--bad);
}
[data-testid="stAlertContainer"] p {
  font-family: var(--prose); font-size: .86rem; line-height: 1.6;
  color: var(--cream); margin: 0;
}
[data-testid="stAlertContainer"] svg { display: none; }

/* The page you are on, announced once at the top ------------------------- */
.page-head {
  display: flex; align-items: baseline; gap: .85rem;
  margin: 0 0 1.5rem; padding-bottom: .7rem; border-bottom: 1px solid var(--line);
}
.page-head h2 {
  font-family: var(--display); font-weight: 400; font-size: 1.9rem;
  color: var(--cream); margin: 0; line-height: 1.1;
}
.alarm {
  font-family: var(--chrome); font-size: 0.72rem; letter-spacing: .14em;
  text-transform: uppercase; color: var(--bad); margin: 0 0 .9rem;
  padding-left: .7rem; border-left: 2px solid var(--bad);
}
.page-no {
  font-family: var(--data); font-size: 0.8rem; color: var(--brass);
  border: 1px solid var(--line); border-radius: 2px;
  padding: .18rem .5rem; line-height: 1;
}

/* Meter ------------------------------------------------------------------- */
.meter { margin: 0 0 1.4rem; }
.meter .track { height: 2px; background: rgba(240,230,219,.12); }
.meter .fill { height: 2px; background: var(--brass); }
/* Past the target is not a failure, just a different fact. */
.meter .fill.over { background: var(--good); }
.meter .read {
  font-family: var(--chrome); font-size: 0.74rem; letter-spacing: .14em;
  text-transform: uppercase; color: var(--muted); display: flex;
  justify-content: space-between; padding-bottom: .45rem;
}
.meter .read b { color: var(--cream); font-weight: 500; }

/* Stats ------------------------------------------------------------------- */
.stats { display: flex; gap: 2.2rem; flex-wrap: wrap; margin: 0 0 1.4rem; }
.stat .k {
  font-family: var(--chrome); font-size: 0.70rem; letter-spacing: .16em;
  text-transform: uppercase; color: var(--muted);
}
.stat .v { font-family: var(--display); font-size: 1.7rem; line-height: 1.2; }
.stat .v.brass { color: var(--brass); }

/* Item card --------------------------------------------------------------- */
.item { background: var(--panel); border: 1px solid var(--line); padding: .8rem .9rem; height: 100%; }
.item .top { display: flex; align-items: center; gap: .6rem; margin-bottom: .5rem; }
.item .nm { font-family: var(--display); font-size: 1.05rem; line-height: 1.2; }
.item .meta {
  font-family: var(--chrome); font-size: 0.70rem; color: var(--muted);
  letter-spacing: .08em; line-height: 1.7;
}
.item .price { color: var(--cream); }
.badge {
  font-family: var(--chrome); font-size: 0.70rem; letter-spacing: .14em;
  text-transform: uppercase; padding: .12rem .4rem; border: 1px solid var(--line);
  color: var(--muted); white-space: nowrap;
}
.badge.want { color: var(--brass); border-color: var(--brass); }
.badge.ok { color: var(--good); border-color: rgba(127,168,107,.5); }
.badge.no { color: var(--bad); border-color: rgba(180,87,74,.5); }
.swatch { width: 100%; height: 5.2rem; border: 1px solid var(--line); }

/* Tables ------------------------------------------------------------------ */
.tbl { width: 100%; border-collapse: collapse; font-family: var(--data); font-size: 0.82rem; }
.tbl th {
  text-align: left; color: var(--muted); font-weight: 400; letter-spacing: .12em;
  text-transform: uppercase; font-family: var(--chrome); font-size: 0.74rem;
  padding: .45rem .6rem; border-bottom: 1px solid var(--line);
}
.tbl td { padding: .45rem .6rem; border-bottom: 1px solid rgba(240,230,219,.07); }
.tbl td.num { text-align: right; color: var(--cream); }
.tbl tr:hover td { background: rgba(201,162,39,.05); }
.est { color: var(--brass); }

/* Plan -------------------------------------------------------------------- */
.step { background: var(--panel); border: 1px solid var(--line); border-left: 2px solid var(--brass);
        padding: .9rem 1.1rem; margin-bottom: .7rem; }
.step .hd { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
.step .n { font-family: var(--display); font-size: 1.2rem; color: var(--brass); }
.step .pieces { font-size: .92rem; }
.step .cost { font-family: var(--data); font-size: .95rem; }
.step .why { font-family: var(--prose); font-size: 0.70rem; color: var(--muted);
             letter-spacing: .08em; margin-top: .45rem; line-height: 1.7; }

.guide-body { background: var(--panel); border: 1px solid var(--line); padding: 1.6rem 1.8rem; }
.guide-body h1 { font-family: var(--display); font-weight: 400; font-size: 2rem; margin: 0 0 1rem; }
.guide-body h2 { font-family: var(--display); font-size: 1rem; letter-spacing: .13em;
                 text-transform: uppercase; color: var(--brass); margin: 2rem 0 .7rem; }
.guide-body h3 { font-family: var(--display); font-size: .95rem; letter-spacing: .04em;
                 color: var(--cream); margin: 1.4rem 0 .5rem; }
.guide-body table { border-collapse: collapse; width: 100%; font-size: .84rem; }
.guide-body th, .guide-body td { border-bottom: 1px solid var(--line); padding: .45rem .6rem; text-align: left; }

.empty { border: 1px dashed var(--line); padding: 2.4rem 1.6rem; text-align: center;
         color: var(--muted); font-size: .88rem; }
/* Standing in for a picture, not for a paragraph. A short dashed box where a
   full-length plate should be left every gallery row ragged: the card beside a
   real photograph sat a third of the way up its own column. */
.no-plate {
  border: 1px dashed var(--line); aspect-ratio: 3 / 4; width: 100%;
  box-sizing: border-box;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--chrome); font-size: 0.70rem; letter-spacing: .14em;
  text-transform: uppercase; color: var(--muted);
}
/* Small text sits above things: an expander, a plate, a table. Without a bottom
   margin it presses against the box below and reads as part of it. */
.look-cap { font-family: var(--chrome); font-size: 0.70rem; letter-spacing: .1em;
            color: var(--muted); padding-top: .45rem; margin-bottom: .55rem;
            line-height: 1.6; }
/* Except as the last line inside a card, where it would pad the card instead. */
.item .look-cap:last-child, .product .look-cap:last-child,
.step .look-cap:last-child, .docket .look-cap:last-child { margin-bottom: 0; }
.look-cap a, .answer-nav a { color: var(--brass); text-decoration: none; border-bottom: 1px solid transparent; }
.look-cap a:hover, .answer-nav a:hover { border-bottom-color: var(--brass); }

/* Single-answer view ------------------------------------------------------ */
.answer-q {
  font-family: var(--display); font-size: clamp(1.5rem, 3vw, 2.2rem);
  font-weight: 400; line-height: 1.25; margin: 0 0 1.4rem; max-width: 34ch;
}
.answer-a {
  font-size: 1.06rem; line-height: 1.75; white-space: pre-wrap; max-width: 62ch;
  border-left: 2px solid var(--brass); padding: .2rem 0 .2rem 1.4rem;
}
.answer-nav {
  font-family: var(--chrome); font-size: 0.74rem; letter-spacing: .12em;
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
  font-family: var(--chrome); font-size: 0.70rem; letter-spacing: .14em;
  text-transform: uppercase; color: var(--muted); display: flex;
  justify-content: space-between; margin-bottom: .6rem;
}
.alloc-read b { color: var(--cream); font-weight: 500; }
.alloc-read.off b { color: var(--bad); }

/* Catalogue lists. These are read down a page rather than glanced at, so they
   are set at reading size rather than at caption size. */
.dict-h {
  font-family: var(--display); font-size: 1.05rem; letter-spacing: .05em;
  color: var(--cream); margin: 1.4rem 0 .5rem; padding-bottom: .35rem;
  border-bottom: 1px solid var(--line);
}
.dict-h span { font-family: var(--chrome); font-size: 0.82rem; color: var(--muted);
               letter-spacing: .12em; text-transform: uppercase; margin-left: .6rem; }
/* These are read down a page, one line per thing, so they are set at reading
   size. They were at caption size and looked like footnotes to themselves. */
.dict-row { font-family: var(--prose); font-size: 0.95rem; color: var(--cream);
            padding: .38rem 0; line-height: 1.55; }
.dict-row .meta { font-family: var(--chrome); font-size: 0.86rem; color: var(--muted);
                  letter-spacing: .04em; }
.dict-row .unused { color: var(--muted); }
.dict-chip {
  display: inline-block; font-family: var(--chrome); font-size: 0.82rem;
  letter-spacing: .06em; color: var(--muted); border: 1px solid var(--line);
  padding: .2rem .55rem; margin: 0 .3rem .3rem 0;
}
.dict-chip.on { color: var(--brass); border-color: var(--brass); }

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


def no_plate(text: str = "no photograph yet") -> None:
    """A placeholder the shape of a picture, so a grid row stays level.

    It sits inside the same frame a real plate uses, so the border, the padding
    and the column width are identical and only the picture is missing.
    """
    st.markdown(f'<div class="plate"><div class="no-plate">{text}</div></div>',
                unsafe_allow_html=True)


def meter(done: int, total: int, label: str) -> None:
    """A target, not a limit.

    The bar used to be set to done/total with no ceiling, so fourteen principles
    against a target of ten drew a fill 140% wide that ran off the right of the
    page and read as a rendering fault. Past the target it fills and says so.
    """
    pct = min(100, round(100 * done / total)) if total else 0
    reading = (f"<b>{done}</b> of {total}" if done <= total
               else f"<b>{done}</b> &middot; past the {total} aimed for")
    over = " over" if done > total else ""
    st.markdown(
        f'<div class="meter"><div class="read"><span>{label}</span>'
        f'<span>{reading}</span></div>'
        f'<div class="track"><div class="fill{over}" style="width:{pct}%"></div>'
        '</div></div>',
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
  color: #8A7767; font-family: var(--chrome); font-size: 0.74rem;
  letter-spacing: .16em; text-transform: uppercase; background: var(--raise);
}
.product .body { padding: 1rem 1.1rem 1.2rem; }
.product .nm {
  font-family: var(--display); font-size: 1.25rem; line-height: 1.25;
  margin-bottom: .2rem;
}
.product .kind {
  font-family: var(--chrome); font-size: 0.70rem; letter-spacing: .18em;
  text-transform: uppercase; color: var(--muted);
}
.product .price {
  font-family: var(--data); font-size: 1.05rem; color: var(--cream);
  margin: .6rem 0 .3rem;
}
.product .route {
  font-family: var(--chrome); font-size: 0.70rem; letter-spacing: .1em;
  color: var(--brass); border-top: 1px solid var(--line); padding-top: .5rem;
  margin-top: .5rem; line-height: 1.6;
}
.product .route.none { color: var(--bad); }
.product .size {
  font-family: var(--data); font-size: 0.70rem; color: var(--muted);
  line-height: 1.7;
}
.product .flag {
  position: absolute; top: .6rem; left: .6rem; background: var(--brass); color: #17110E;
  font-family: var(--chrome); font-size: 0.70rem; letter-spacing: .14em;
  text-transform: uppercase; padding: .2rem .5rem;
}
.product .example {
  font-family: var(--chrome); font-size: 0.82rem; letter-spacing: .04em;
  border-top: 1px solid var(--line); padding-top: .5rem; margin-top: .5rem;
  display: flex; gap: .7rem; align-items: baseline; flex-wrap: wrap;
}
.product .example a { color: var(--brass); text-decoration: none; }
.product .example a:hover { border-bottom: 1px solid var(--brass); }
.product .example .sale { color: var(--bad); }
.product a.view {
  display: block; text-align: center; padding: .7rem; margin-top: .9rem;
  background: var(--brass); color: #17110E; text-decoration: none;
  font-family: var(--chrome); font-size: 0.74rem; letter-spacing: .16em;
  text-transform: uppercase;
}
.product a.view:hover { background: var(--cream); }

.shopfront { display: flex; gap: 1.2rem; align-items: flex-start; }
.buy {
  background: var(--panel); border: 1px solid var(--line); border-left: 2px solid var(--brass);
  padding: .85rem 1.1rem; margin-bottom: .6rem;
}
.buy .hd { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
.buy .who { font-family: var(--display); font-size: 1.15rem; }
.buy .kind {
  font-family: var(--chrome); font-size: 0.70rem; letter-spacing: .14em;
  text-transform: uppercase; color: var(--muted);
}
.buy .why {
  font-family: var(--prose); font-size: 0.82rem; color: var(--muted);
  margin-top: .35rem; line-height: 1.6;
}
.buy a {
  font-family: var(--chrome); font-size: 0.70rem; letter-spacing: .14em;
  text-transform: uppercase; color: var(--brass); text-decoration: none;
}
.buy a:hover { border-bottom: 1px solid var(--brass); }
.route-card {
  background: var(--raise); border: 1px solid var(--brass); padding: 1rem 1.2rem;
  margin-bottom: 1.2rem;
}
.route-card .hd { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
.route-card .who { font-family: var(--display); font-size: 1.35rem; }
.route-card .kind {
  font-family: var(--chrome); font-size: 0.70rem; letter-spacing: .16em;
  text-transform: uppercase; color: var(--brass);
}
.route-card .term {
  font-family: var(--data); font-size: 0.74rem; color: var(--cream);
  letter-spacing: .06em; margin-top: .5rem;
}
.route-card .term b { color: var(--muted); font-weight: 400; margin-right: .5rem; }
.route-card .why { color: var(--muted); font-size: .85rem; line-height: 1.6; margin-top: .7rem; }
.route-card .links { margin-top: .9rem; display: flex; gap: 1.2rem; flex-wrap: wrap; }
.route-card .links a {
  font-family: var(--chrome); font-size: 0.70rem; letter-spacing: .14em;
  text-transform: uppercase; color: #17110E; background: var(--brass);
  padding: .5rem .9rem; text-decoration: none;
}
.route-card .links a:hover { background: var(--cream); }
.tactic { border-left: 2px solid rgba(201,162,39,.35); padding: .1rem 0 .1rem 1rem; margin: .8rem 0; }
.tactic .t { font-family: var(--display); font-size: 1.05rem; }
.tactic .d { color: var(--muted); font-size: .84rem; line-height: 1.65; margin-top: .2rem; }
.tactic .w {
  font-family: var(--chrome); font-size: 0.70rem; letter-spacing: .14em;
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
