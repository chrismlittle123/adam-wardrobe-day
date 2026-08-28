"""The wardrobe studio: see the man, brief the look, get the photograph back.

Run it with `uv run wardrobe-app`, or directly:
    uv run streamlit run src/wardrobe/app.py

Everything the model is told about the subject comes from profile.toml, which is
rendered on the left as a tailor's docket and editable in place.
"""

from __future__ import annotations

import base64
import datetime as dt
import io
import re
from pathlib import Path

import streamlit as st
from PIL import Image

from wardrobe.gemini_image import GeminiImageError, Settings, generate_images
from wardrobe.profile import Profile
from wardrobe.prompts import BACKGROUNDS, SHOTS, build_prompt

LOOKS_DIR = Path("out/looks")

# Pulled off the reference photo itself: walnut ground, the brass of the gold
# chain-stitch on his collar, the cream of the shirt.
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bodoni+Moda:opsz,wght@6..96,400;6..96,600&family=Karla:wght@300;400;500;700&family=IBM+Plex+Mono:wght@300;400;500&display=swap');

:root {
  --ground: #17110E;
  --panel:  #211915;
  --raise:  #2C211B;
  --brass:  #C9A227;
  --cream:  #F0E6DB;
  --muted:  #8A7767;
  --line:   rgba(201,162,39,.22);
}

.stApp { background: var(--ground); }
html, body, [class*="css"], .stMarkdown, p, li, label, div[data-baseweb] {
  font-family: 'Karla', system-ui, sans-serif;
  color: var(--cream);
}
[data-testid="stAppViewContainer"] > .main { padding-top: 0; }
[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }

/* Masthead ---------------------------------------------------------------- */
.masthead { padding: 2.2rem 0 1.1rem; border-bottom: 1px solid var(--line); margin-bottom: 2rem; }
.masthead h1 {
  font-family: 'Bodoni Moda', Georgia, serif;
  font-weight: 400; font-size: clamp(2.4rem, 5vw, 3.6rem);
  letter-spacing: .01em; line-height: 1; margin: 0; color: var(--cream);
}
.masthead h1 em { font-style: italic; color: var(--brass); }
.masthead .sub {
  font-family: 'IBM Plex Mono', monospace; font-size: .7rem; letter-spacing: .22em;
  text-transform: uppercase; color: var(--muted); margin-top: .7rem;
}

/* Section eyebrows -------------------------------------------------------- */
.eyebrow {
  font-family: 'IBM Plex Mono', monospace; font-size: .68rem; letter-spacing: .22em;
  text-transform: uppercase; color: var(--brass); margin: 0 0 .9rem;
  display: flex; align-items: center; gap: .8rem;
}
.eyebrow::after { content: ""; flex: 1 1 auto; height: 1px; background: var(--line); }

/* The docket -------------------------------------------------------------- */
.docket { background: var(--panel); border: 1px solid var(--line); padding: 1.4rem 1.5rem 1.1rem; }
.docket .name {
  font-family: 'Bodoni Moda', Georgia, serif; font-size: 1.9rem; font-weight: 400;
  margin: 0 0 1.2rem; line-height: 1;
}
.docket dl { margin: 0; }
.docket .row { display: flex; align-items: baseline; margin: 0 0 .62rem; }
.docket dt {
  font-family: 'IBM Plex Mono', monospace; font-size: .68rem; letter-spacing: .13em;
  text-transform: uppercase; color: var(--muted); white-space: nowrap;
}
.docket .leader {
  flex: 1 1 auto; border-bottom: 1px dotted rgba(240,230,219,.22);
  margin: 0 .6rem; transform: translateY(-.28rem); min-width: 1rem;
}
.docket dd {
  margin: 0; font-family: 'IBM Plex Mono', monospace; font-size: .82rem;
  color: var(--cream); text-align: right;
}
.docket dd.prose {
  font-family: 'Karla', sans-serif; font-size: .84rem; color: var(--cream);
  text-align: right; max-width: 62%;
}
.chip {
  display: inline-block; width: .78rem; height: .78rem; margin-right: .45rem;
  border: 1px solid rgba(240,230,219,.35); vertical-align: -1px;
}
.docket .note {
  margin: 1.1rem 0 0; padding-top: .9rem; border-top: 1px solid var(--line);
  font-size: .8rem; color: var(--muted); line-height: 1.5;
}

/* Reference photo --------------------------------------------------------- */
.plate { border: 1px solid var(--line); padding: .45rem; background: var(--panel); }
.plate img { display: block; width: 100%; }
.plate .cap {
  font-family: 'IBM Plex Mono', monospace; font-size: .64rem; letter-spacing: .16em;
  text-transform: uppercase; color: var(--muted); padding: .6rem .2rem .15rem;
  display: flex; justify-content: space-between;
}

/* Controls ---------------------------------------------------------------- */
.stTextArea textarea, .stTextInput input {
  background: var(--panel) !important; color: var(--cream) !important;
  border: 1px solid var(--line) !important; border-radius: 0 !important;
  font-family: 'Karla', sans-serif !important; font-size: .95rem !important;
}
.stTextArea textarea:focus, .stTextInput input:focus {
  border-color: var(--brass) !important; box-shadow: none !important;
}
div[data-baseweb="select"] > div {
  background: var(--panel) !important; border: 1px solid var(--line) !important;
  border-radius: 0 !important;
}
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
  background: var(--brass); color: #17110E; border: none; border-radius: 0;
  font-family: 'IBM Plex Mono', monospace; font-size: .72rem; letter-spacing: .18em;
  text-transform: uppercase; padding: .72rem 1.4rem; font-weight: 500;
  transition: background .18s ease, transform .18s ease;
}
.stButton > button:hover, .stFormSubmitButton > button:hover, .stDownloadButton > button:hover {
  background: var(--cream); color: #17110E; transform: translateY(-1px);
}
.stButton > button:focus-visible, .stFormSubmitButton > button:focus-visible {
  outline: 2px solid var(--cream); outline-offset: 3px;
}
label, .stSlider label, .stSelectbox label {
  font-family: 'IBM Plex Mono', monospace !important; font-size: .68rem !important;
  letter-spacing: .16em !important; text-transform: uppercase !important;
  color: var(--muted) !important;
}
.streamlit-expanderHeader, details summary {
  font-family: 'IBM Plex Mono', monospace !important; font-size: .68rem !important;
  letter-spacing: .16em !important; text-transform: uppercase !important;
}
.stCode, pre, code { font-family: 'IBM Plex Mono', monospace !important; font-size: .78rem !important; }

/* Gallery ----------------------------------------------------------------- */
.look-cap {
  font-family: 'IBM Plex Mono', monospace; font-size: .66rem; letter-spacing: .1em;
  color: var(--muted); padding-top: .5rem; line-height: 1.6;
}
.empty {
  border: 1px dashed var(--line); padding: 3rem 2rem; text-align: center;
  color: var(--muted); font-size: .9rem;
}

@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
"""


# --- helpers -----------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _thumb_b64(path: str, mtime: float, width: int = 640) -> str:
    """Downscaled base64 PNG. `mtime` is in the signature so the cache busts
    when the file on disk changes."""
    img = Image.open(path).convert("RGB")
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def plate(path: Path, label: str) -> None:
    b64 = _thumb_b64(str(path), path.stat().st_mtime)
    img = Image.open(path)
    st.markdown(
        f'<div class="plate"><img src="data:image/png;base64,{b64}" alt="{label}">'
        f'<div class="cap"><span>{label}</span><span>{img.width}&times;{img.height}</span></div></div>',
        unsafe_allow_html=True,
    )


def row(label: str, value: str, prose: bool = False) -> str:
    if not value:
        return ""
    cls = "prose" if prose else ""
    return (
        f'<div class="row"><dt>{label}</dt><span class="leader"></span>'
        f'<dd class="{cls}">{value}</dd></div>'
    )


def docket(profile: Profile) -> None:
    s = profile.subject
    height = f"{s.height_metric} &middot; {s.height_imperial}" if s.height_cm else ""
    swatch = (
        f'<span class="chip" style="background:{s.skin_tone_hex}"></span>{s.skin_tone_hex}'
        if s.skin_tone_hex else ""
    )
    rows = [
        row("Height", height),
        row("Build", s.build, prose=True),
        row("Body fat", f"~{s.body_fat_pct}%" if s.body_fat_pct else ""),
        row("Skin", swatch),
        row("Hair", s.hair, prose=True),
        row("Face", s.facial_hair, prose=True),
        row("Eyes", s.eyes),
        row("Wears", s.details, prose=True),
    ]
    labels = {
        "chest_cm": "Chest", "waist_cm": "Waist", "inseam_cm": "Inseam",
        "shoulder_cm": "Shoulder", "shoe_eu": "Shoe EU",
    }
    for key, value in profile.measurements.known().items():
        rows.append(row(labels.get(key, key), f"{value} cm" if key != "shoe_eu" else str(value)))

    note = f'<p class="note">{s.skin_tone}</p>' if s.skin_tone else ""
    st.markdown(
        f'<div class="docket"><div class="name">{s.name}</div><dl>{"".join(rows)}</dl>{note}</div>',
        unsafe_allow_html=True,
    )


def slug(text: str, limit: int = 34) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (out[:limit].rstrip("-") or "look")


def saved_looks() -> list[Path]:
    if not LOOKS_DIR.is_dir():
        return []
    return sorted(LOOKS_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)


# --- the page ----------------------------------------------------------------

def render() -> None:
    st.set_page_config(page_title="Wardrobe Studio", page_icon="👔", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)

    try:
        profile = Profile.load()
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()

    st.markdown(
        '<div class="masthead"><h1>Wardrobe <em>Studio</em></h1>'
        '<div class="sub">Describe a look &middot; see it on him &middot; keep the ones that work</div></div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns([5, 7], gap="large")

    with left:
        st.markdown('<div class="eyebrow">The subject</div>', unsafe_allow_html=True)
        photo = profile.photo("neutral")
        if photo:
            plate(photo, photo.name)
        else:
            st.markdown(
                '<div class="empty">No reference photo found. Check the [photos] '
                'paths in profile.toml.</div>', unsafe_allow_html=True)
        st.write("")
        docket(profile)
        edit_panel(profile)

    with right:
        st.markdown('<div class="eyebrow">The brief</div>', unsafe_allow_html=True)
        brief_panel(profile, photo)

    st.write("")
    st.markdown('<div class="eyebrow">Looks</div>', unsafe_allow_html=True)
    gallery()


def edit_panel(profile: Profile) -> None:
    s = profile.subject
    with st.expander("Edit subject"):
        with st.form("subject"):
            s.name = st.text_input("Name", s.name)
            c1, c2 = st.columns(2)
            s.height_cm = c1.number_input("Height (cm)", 120, 230, s.height_cm or 176)
            s.body_fat_pct = c2.number_input("Body fat (%)", 0, 50, s.body_fat_pct)
            s.build = st.text_input("Build", s.build)
            c3, c4 = st.columns([1, 2])
            s.skin_tone_hex = c3.color_picker("Skin", s.skin_tone_hex)
            s.skin_tone = c4.text_input("Skin, in words", s.skin_tone)
            s.hair = st.text_input("Hair", s.hair)
            s.facial_hair = st.text_input("Facial hair", s.facial_hair)
            c5, c6 = st.columns(2)
            s.eyes = c5.text_input("Eyes", s.eyes)
            s.details = c6.text_input("Always wears", s.details)

            st.write("Measurements in cm. Leave at 0 until measured.")
            m = profile.measurements
            m1, m2, m3 = st.columns(3)
            m.chest_cm = m1.number_input("Chest", 0, 200, m.chest_cm)
            m.waist_cm = m2.number_input("Waist", 0, 200, m.waist_cm)
            m.inseam_cm = m3.number_input("Inseam", 0, 150, m.inseam_cm)
            m4, m5 = st.columns(2)
            m.shoulder_cm = m4.number_input("Shoulder", 0, 100, m.shoulder_cm)
            m.shoe_eu = m5.number_input("Shoe EU", 0, 60, m.shoe_eu)

            profile.style.direction = st.text_area("Style direction", profile.style.direction, height=68)
            profile.style.avoid = st.text_area("Avoid", profile.style.avoid, height=68)

            if st.form_submit_button("Save subject"):
                st.success(f"Saved to {profile.save()}")
                st.rerun()


def brief_panel(profile: Profile, photo: Path | None) -> None:
    outfit = st.text_area(
        "The outfit",
        placeholder="Navy linen camp-collar shirt, cream wide-leg trousers, tan suede loafers.",
        height=120,
    )
    c1, c2, c3 = st.columns([2, 2, 1])
    shot = c1.selectbox("Framing", list(SHOTS))
    background = c2.selectbox("Background", list(BACKGROUNDS))
    count = c3.number_input("Variations", 1, 4, 1)
    extra = st.text_input("Extra direction", placeholder="Sleeves rolled twice. Overcast daylight.")

    prompt = build_prompt(profile, outfit or "…", shot=shot, background=background, extra=extra)
    with st.expander("Prompt sent to Gemini"):
        st.code(prompt, language=None)

    if not photo:
        st.warning("No reference photo, so nothing to generate from.")
        return

    if st.button("Generate look", type="primary"):
        if not outfit.strip():
            st.warning("Describe the outfit first.")
            return
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        prefix = LOOKS_DIR / f"{stamp}-{slug(outfit)}"
        with st.spinner(f"Dressing {profile.subject.name}…"):
            try:
                paths = generate_images(
                    prompt,
                    out_prefix=prefix,
                    reference_images=[photo],
                    count=int(count),
                    settings=Settings.from_env(),
                )
            except GeminiImageError as exc:
                st.error(str(exc))
                return
        st.success(f"{len(paths)} image{'s' if len(paths) != 1 else ''} saved to {LOOKS_DIR}/")
        st.rerun()


def gallery() -> None:
    looks = saved_looks()
    if not looks:
        st.markdown(
            '<div class="empty">No looks yet. Describe an outfit above and generate one.</div>',
            unsafe_allow_html=True,
        )
        return
    for chunk in (looks[i:i + 3] for i in range(0, len(looks), 3)):
        for col, path in zip(st.columns(3, gap="medium"), chunk):
            with col:
                plate(path, path.stem[:16])
                when = dt.datetime.fromtimestamp(path.stat().st_mtime).strftime("%d %b %H:%M")
                title = path.stem.split("-", 2)[-1].replace("-", " ")
                st.markdown(f'<div class="look-cap">{title}<br>{when}</div>', unsafe_allow_html=True)
                st.download_button("Download", path.read_bytes(), path.name, "image/png",
                                   key=f"dl-{path.name}")


def main() -> int:
    """Console-script entry point: `uv run wardrobe-app`."""
    import sys

    from streamlit.web import cli as stcli

    sys.argv = ["streamlit", "run", str(Path(__file__).resolve()),
                "--server.port", "8501", "--server.headless", "true"]
    return stcli.main()


if __name__ == "__main__":
    render()
