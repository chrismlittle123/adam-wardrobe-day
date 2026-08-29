"""Wardrobe Studio.

Six tabs, in the order the work actually happens: work out the style, record what
is in the wardrobe, distil the principles, play with outfits, keep the good ones,
then buy the pieces that unlock the most of them.

Run it:
    uv run wardrobe-app          # http://localhost:8501
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import streamlit as st

from wardrobe import (
    palette as pal_mod,
    revisions,
    fittings as fit_mod,
    retailers,
    vocabulary,
    shop as shop_mod,
    sourcing,
    fitspec, inventory as inv_mod, paths,
    principles as prin_mod, reset as reset_mod, shopping, ui, verify,
)
from wardrobe.gemini_image import GeminiImageError, Settings, generate_images
from wardrobe.gemini_text import GeminiTextError
from wardrobe.inventory import (
    ASPIRATIONAL, NONE, OWNED, RETIRED, STATUSES, Inventory, Item,
    categories, fabric_options, fits, garments, grades, schemes_for, size_scheme,
    takes_fit, takes_grade,
)
from wardrobe.outfits import (
    Outfit, Outfits, compare, describe_outfit, reference_items, reference_photos,
    wearability,
)
from wardrobe.palette import (
    ACCENT, CATEGORIES as COLOUR_CATEGORIES, FIELD, GROUND, ROLES, SEASONS,
    Colour, Palette, colour_names, hex_for, named_colours,
)
from wardrobe.philosophy import Answers, build_guide_prompt, synthesise_guide
from wardrobe.principles import BATCH, GROUPS, TARGET, Principle, Principles
from wardrobe.profile import Profile
from wardrobe.prompts import (
    BACKGROUNDS, DEFAULT_BACKGROUND, DEFAULT_SHOT, SHOTS, build_outfit_prompt,
)
from wardrobe.questions import (
    BY_ID, POINTS, SECTIONS, Question, format_points, parse_points,
)

GEMINI_ERRORS = (GeminiImageError, GeminiTextError)


def slug(text: str, limit: int = 34) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit].rstrip("-") or "look"


# --- the shell ----------------------------------------------------------------

def render() -> None:
    st.set_page_config(page_title="Wardrobe Studio", page_icon="👔", layout="wide")
    st.markdown(ui.CSS, unsafe_allow_html=True)

    try:
        profile = Profile.load()
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()

    answers = Answers.load()

    # A standalone read-only page, reached by a target="_blank" link from the
    # questionnaire. Rendered instead of the app, not inside it, so the browser
    # tab holds one answer and nothing else.
    focus = st.query_params.get("answer")
    if focus is not None:
        answer_view(profile, answers, focus)
        return

    # One garment on its own page, reached from the shop by a target="_blank"
    # link. Rendered instead of the app so the browser tab holds the product.
    wanted = st.query_params.get("item")
    if wanted is not None:
        item_view(profile, wanted)
        return

    if st.query_params.get("colours") is not None:
        colour_catalogue_view(Palette.load())
        return

    if st.query_params.get("shops") is not None:
        retailer_catalogue_view()
        return

    if st.query_params.get("garments") is not None:
        garment_catalogue_view()
        return

    looking = st.query_params.get("outfit")
    if looking is not None:
        outfit_view(profile, looking)
        return

    pair = st.query_params.get("compare")
    if pair is not None:
        compare_view(pair)
        return

    inventory = Inventory.load()
    outfits = Outfits.load()
    principles = Principles.load()

    sidebar(profile, inventory, outfits)

    here = current_page()
    draw = {
        "style-guide": lambda: style_guide_tab(profile, answers),
        "garments": garment_catalogue_panel,
        "inventory": lambda: inventory_tab(profile, inventory, outfits),
        "principles": lambda: principles_tab(profile, answers, principles),
        "colour": lambda: colour_tab(profile, Palette.load()),
        "generator": lambda: generator_tab(profile, inventory, outfits, principles),
        "gallery": lambda: gallery_tab(inventory, outfits),
        "where-to-buy": lambda: where_to_buy_tab(inventory),
        "measurements": lambda: body_tab(profile),
        "shop": lambda: shop_tab(profile, inventory, outfits, principles),
        "diagnostics": diagnostics_tab,
    }
    st.markdown(f'<div class="page-head"><span class="page-no">{page_number(here)}</span>'
                f'<h2>{PAGE_TITLES[here]}</h2></div>', unsafe_allow_html=True)
    draw[here]()
    remember_page()


# The ten pages in the order the work is actually done, plus the workshop.
# Order matters: it is the argument the app is making about how to dress well,
# so the numbers are shown and the sequence is not alphabetical.
PAGES: tuple[tuple[str, str], ...] = (
    ("style-guide", "Style Guide"),
    ("garments", "Garment Catalogue"),
    ("inventory", "Wardrobe Inventory"),
    ("principles", "Principles"),
    ("colour", "Colour"),
    ("generator", "Outfit Generator"),
    ("gallery", "Outfit Gallery"),
    ("where-to-buy", "Where to Buy"),
    ("measurements", "Body Measurements"),
    ("shop", "Shopping Guide"),
    ("diagnostics", "Diagnostics"),
)
PAGE_TITLES: dict[str, str] = dict(PAGES)

# Which page a standalone view belongs to. Coming back from a garment should
# land in the wardrobe, not on the front page, which is where every one of these
# used to drop you.
HOME_FOR: dict[str, str] = {
    "item": "inventory", "outfit": "gallery", "compare": "gallery",
    "garments": "garments", "colours": "colour", "shops": "where-to-buy",
    "answer": "style-guide",
}


def home_for(view: str) -> str:
    """Where the back link goes, honouring ?from= when a link supplied it."""
    asked = st.query_params.get("from", "")
    return asked if asked in PAGE_TITLES else HOME_FOR.get(view, "")
WORKSHOP = "diagnostics"


def page_number(slug: str) -> str:
    """Diagnostics is a workshop, not a step, so it carries a spanner."""
    if slug == WORKSHOP:
        return "&#9881;"
    return str([s for s, _ in PAGES].index(slug) + 1)


def current_page() -> str:
    """Which page we are on.

    Seeded from the URL on the first run of a session and owned by the radio
    afterwards. Writing the URL in response to a click, which is how this worked
    for a while, restarted the session: every widget further down the page lost
    its state, so the wardrobe search could not hold a word once you had reached
    it by clicking rather than by typing the address.
    """
    if "nav-page" not in st.session_state:
        asked = st.query_params.get("page", "")
        st.session_state["nav-page"] = asked if asked in PAGE_TITLES else PAGES[0][0]
    return st.session_state["nav-page"]


def navigation() -> None:
    """The page list. No index and no callback: the key is the whole of it."""
    slugs = [slug for slug, _ in PAGES]
    current_page()                       # seed the state before drawing
    st.radio(
        "Section", slugs, key="nav-page",
        format_func=lambda slug: f"{page_number(slug).replace('&#9881;', chr(9881))}  "
                                 f"{PAGE_TITLES[slug]}",
        label_visibility="collapsed")
    # The address bar is synced by remember_page() at the very end of the run.
    # Writing it here reruns the script from inside the sidebar, before the page
    # body has drawn, and every widget below loses its state on the way.


def remember_page() -> None:
    """Put the current page in the address bar, once the page itself has drawn.

    A refresh has to land back where you were, which means the URL has to follow
    the navigation. Writing it while the sidebar is drawing reruns the script
    before the page body exists, and Streamlit discards the state of every widget
    that did not get rendered: the wardrobe search would then arrive empty every
    time and filter nothing. Doing it last means everything has already been
    drawn and registered before the address changes.
    """
    here = st.session_state.get("nav-page", "")
    if here and st.query_params.get("page") != here:
        st.query_params["page"] = here


def sidebar(profile: Profile, inventory: Inventory, outfits: Outfits) -> None:
    with st.sidebar:
        # The masthead lives here rather than over the page. Repeating it above
        # every page pushed the actual content a third of the way down the
        # screen and said the same thing as the page title underneath it.
        st.markdown(
            '<div class="brand"><h1>Wardrobe <em>Studio</em></h1>'
            '<div class="sub">Work out the style &middot; know the wardrobe '
            '&middot; buy only what unlocks</div></div>', unsafe_allow_html=True)
        navigation()
        photo = profile.photo("neutral")
        if photo:
            ui.plate(photo, width=380)
        docket(profile)
        counts = inventory.counts()
        st.markdown(
            f'<div class="look-cap">{counts[OWNED]} owned &middot; '
            f'{counts[ASPIRATIONAL]} wanted &middot; {len(outfits.outfits)} outfits</div>',
            unsafe_allow_html=True,
        )
        subject_editor(profile)


def body_fat_line(profile: Profile) -> str:
    """The figure, and whether anyone actually worked it out.

    A flat "~10%" had been sitting in the profile since the day it was written,
    eyeballed and never revisited. Once the waist and the neck are on file it is
    not a guess any more, so the docket stops hedging and says so.
    """
    s = profile.subject
    derived = profile.measurements.body_fat(s.height_cm)
    if derived is None:
        return f"~{s.body_fat_pct}%, estimated" if s.body_fat_pct else ""
    return (f"{derived:.1f}%, from a {profile.measurements.waist:g} cm waist "
            f"and a {profile.measurements.neck:g} cm neck")


def docket(profile: Profile) -> None:
    s = profile.subject

    def row(label: str, value: str, prose: bool = False) -> str:
        if not value:
            return ""
        return (f'<div class="row"><dt>{label}</dt><span class="leader"></span>'
                f'<dd class="{"prose" if prose else ""}">{value}</dd></div>')

    height = f"{s.height_metric} &middot; {s.height_imperial}" if s.height_cm else ""
    swatch = (f'<span class="chip" style="background:{s.skin_tone_hex}"></span>{s.skin_tone_hex}'
              if s.skin_tone_hex else "")
    measured = profile.measurements.measured()
    rows = [
        row("Height", height),
        row("Build", s.build, prose=True),
        row("Body fat", body_fat_line(profile)),
        row("Skin", swatch),
        row("Hair", s.hair, prose=True),
        row("Face", s.facial_hair, prose=True),
        row("Wears", s.details, prose=True),
        row("Measured", f"{len(measured)} of {len(fitspec.HOW_TO_MEASURE)}"
            if measured else "none yet"),
    ]
    note = f'<p class="note">{s.skin_tone}</p>' if s.skin_tone else ""
    st.markdown(
        f'<div class="docket"><div class="name">{s.name}</div><dl>{"".join(rows)}</dl>{note}</div>',
        unsafe_allow_html=True,
    )


def subject_editor(profile: Profile) -> None:
    s = profile.subject
    with st.expander("Edit subject"):
        with st.form("subject"):
            s.name = st.text_input("Name", s.name)
            s.height_cm = st.number_input("Height (cm)", 120, 230, s.height_cm or 180)
            derived = profile.measurements.body_fat(s.height_cm)
            if derived is None:
                s.body_fat_pct = st.number_input(
                    "Body fat (%)", 0, 50, s.body_fat_pct,
                    help="A guess until the waist and the neck are measured, at "
                         "which point it is worked out instead.")
            else:
                s.body_fat_pct = round(derived)
                st.markdown(
                    f'<div class="look-cap">Body fat &middot; {derived:.1f}%, worked '
                    f'out from the waist and the neck rather than typed in</div>',
                    unsafe_allow_html=True)
            s.build = st.text_input("Build", s.build)
            s.skin_tone_hex = st.color_picker("Skin", s.skin_tone_hex)
            s.skin_tone = st.text_input("Skin, in words", s.skin_tone)
            s.hair = st.text_input("Hair", s.hair)
            s.facial_hair = st.text_input("Facial hair", s.facial_hair)
            s.eyes = st.text_input("Eyes", s.eyes)
            s.details = st.text_input("Always wears", s.details)
            s.arms = st.selectbox(
                "Arm length", ["", "long", "average", "short"],
                index=["", "long", "average", "short"].index(s.arms if s.arms in
                      ("", "long", "average", "short") else ""),
                help="Height alone puts everyone at the same reach. Long arms add "
                     "about 4% to every sleeve target; short arms take 4.5% off.")
            s.description = st.text_area("Description", s.description, height=110,
                                         help="Him in prose. It goes into every "
                                              "generated photograph.")
            profile.style.direction = st.text_area("Style direction", profile.style.direction, height=68)
            profile.style.avoid = st.text_area("Avoid", profile.style.avoid, height=68)
            if st.form_submit_button("Save subject"):
                profile.save()
                st.rerun()


def answer_view(profile: Profile, answers: Answers, focus: str) -> None:
    """One saved answer, on its own, in its own browser tab."""
    st.markdown(ui.CSS, unsafe_allow_html=True)
    ui.way_home(home_for("answer"), "Saved answers")
    answered = [q for q in BY_ID.values() if answers.get(q.id)]

    if focus == "all" or focus not in BY_ID:
        st.markdown(
            '<div class="masthead"><h1>Saved <em>answers</em></h1>'
            f'<div class="sub">{profile.subject.name} &middot; {len(answered)} of '
            f'{len(BY_ID)} answered</div></div>', unsafe_allow_html=True)
        if not answered:
            ui.empty("Nothing answered yet.")
            return
        for section in SECTIONS:
            rows = [q for q in section.questions if answers.get(q.id)]
            if not rows:
                continue
            ui.eyebrow(section.title)
            for q in rows:
                st.markdown(
                    f'<div class="answer-index"><a href="?answer={q.id}" target="_self">'
                    f'{q.prompt}</a></div>', unsafe_allow_html=True)
                st.markdown(f'<div class="look-cap">{answers.get(q.id)}</div>',
                            unsafe_allow_html=True)
        return

    question = BY_ID[focus]
    section = next((s for s in SECTIONS if question in s.questions), None)
    order = [q.id for q in answered]
    here = order.index(focus) if focus in order else -1

    st.markdown(
        f'<div class="masthead"><h1>{profile.subject.name}</h1>'
        f'<div class="sub">{section.title if section else "Answer"}'
        f'{f" &middot; {here + 1} of {len(order)}" if here >= 0 else ""}</div></div>',
        unsafe_allow_html=True)
    st.markdown(f'<div class="answer-q">{question.prompt}</div>', unsafe_allow_html=True)
    body = answers.get(focus)
    st.markdown(f'<div class="answer-a">{body or "Not answered yet."}</div>',
                unsafe_allow_html=True)
    if question.help:
        st.markdown(f'<div class="look-cap">{question.help}</div>', unsafe_allow_html=True)

    links = ['<a href="?answer=all" target="_self">All answers</a>']
    if here > 0:
        links.append(f'<a href="?answer={order[here - 1]}" target="_self">&larr; Previous</a>')
    if 0 <= here < len(order) - 1:
        links.append(f'<a href="?answer={order[here + 1]}" target="_self">Next &rarr;</a>')
    links.append('<a href="./" target="_self">Back to the app</a>')
    st.markdown(f'<div class="answer-nav">{"".join(links)}</div>', unsafe_allow_html=True)


# --- 1. style guide -----------------------------------------------------------

def style_guide_tab(profile: Profile, answers: Answers) -> None:
    ui.eyebrow("The questions")
    ui.blurb(
        "Everything here feeds the guide. Nothing is compulsory; the guide names its "
        "own gaps. Be specific: \"the three black going-out shirts\" is worth more than "
        "\"some shirts\". Each section saves on its own."
    )

    done, total = answers.progress()
    ui.meter(done, total, "Answered")
    if done:
        st.markdown('<div class="look-cap"><a href="?answer=all" target="_blank">'
                    'Open every saved answer in a new tab &#8599;</a></div>',
                    unsafe_allow_html=True)

    for section in SECTIONS:
        questions = list(section.questions)
        filled = sum(1 for q in questions if answers.get(q.id))
        mark = "✓" if filled == len(questions) else f"{filled}/{len(questions)}"
        with st.expander(f"{section.title}  ·  {mark}", expanded=filled == 0):
            ui.blurb(section.blurb)
            with st.form(f"sec-{section.id}"):
                draft: dict[str, str] = {}
                for q in questions:
                    if q.kind == POINTS:
                        draft[q.id] = points_input(q, answers.get(q.id))
                    else:
                        draft[q.id] = st.text_area(
                            q.prompt, value=answers.get(q.id), 
                            help=q.help or None, height=max(68, q.lines * 27), key=f"a-{q.id}",
                        )
                    if answers.get(q.id):
                        st.markdown(
                            f'<div class="look-cap"><a href="?answer={q.id}" '
                            f'target="_blank">Open this answer in a new tab &#8599;</a></div>',
                            unsafe_allow_html=True)
                if st.form_submit_button(f"Save {section.title.lower()}"):
                    answers.values.update(draft)
                    answers.save()
                    # Saved either way; a wrong total is still a real signal, so it
                    # is flagged rather than refused. No rerun, or the note vanishes.
                    off = [n for n in (points_warning(q, draft.get(q.id, "")) for q in questions) if n]
                    for note in off:
                        st.warning(note)
                    if not off:
                        st.rerun()

    guide_panel(profile, answers)


def guide_panel(profile: Profile, answers: Answers) -> None:
    """The guide, three ways: read it, edit it by hand, or argue with it."""
    ui.eyebrow("The guide")
    done, total = answers.progress()
    exists = paths.guide().is_file()

    if not exists:
        left, right = st.columns([3, 1], gap="large")
        with left:
            if done == 0:
                ui.empty("Nothing to build from yet. Answer a few questions above.")
            elif done < 8:
                st.warning(f"Only {done} answers. The guide will be thin and mostly gaps.")
        with right:
            build = st.button("Build style guide", type="primary", disabled=done == 0)
        with st.expander("Prompt sent to Gemini"):
            st.code(build_guide_prompt(profile, answers), language=None)
        if build:
            with st.spinner("Writing the guide…"):
                try:
                    synthesise_guide(profile, answers)
                except GEMINI_ERRORS as exc:
                    st.error(str(exc))
                    return
            st.rerun()
        return

    markdown = paths.guide().read_text()
    when = dt.datetime.fromtimestamp(paths.guide().stat().st_mtime)
    st.markdown(
        f'<div class="look-cap">{paths.guide()} &middot; {when:%d %b %H:%M} &middot; '
        f'{len(markdown.split()):,} words &middot; built from {done} of {total} answers'
        f'</div>', unsafe_allow_html=True)

    read, edit = st.tabs(["Read", "Edit"])
    with read:
        st.download_button("Download markdown", markdown, paths.guide().name, "text/markdown")
        st.markdown(f'<div class="guide-body">\n\n{markdown}\n\n</div>',
                    unsafe_allow_html=True)
    with edit:
        edit_guide_panel(markdown)

    version_panel()


def edit_guide_panel(markdown: str) -> None:
    ui.blurb(
        "The raw markdown. Change a word, delete a section, reorder the shopping "
        "list. Saving keeps what it replaced, so nothing here is final."
    )
    with st.form("edit-guide"):
        draft = st.text_area("Style guide", markdown, height=560, key="guide-raw",
                             label_visibility="collapsed")
        c1, c2 = st.columns([1, 3])
        saved = c1.form_submit_button("Save the guide")
        c2.markdown(f'<div class="look-cap">{len(draft.split()):,} words</div>',
                    unsafe_allow_html=True)
        if saved:
            if not draft.strip():
                st.warning("That would leave the guide empty. Delete the file if you "
                           "mean to start again.")
            else:
                revisions.save_edit(draft)
                st.rerun()


def version_panel() -> None:
    history = revisions.versions()
    if not history:
        return
    with st.expander(f"Earlier versions · {len(history)}"):
        ui.blurb("Every edit and every rewrite keeps what it replaced. Restoring one "
                 "also keeps the current version, so this only ever adds.")
        for version in history[:12]:
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            c1.markdown(f'<div class="look-cap">{version.label} &middot; '
                        f'{version.words:,} words</div>', unsafe_allow_html=True)
            if c2.button("Restore", key=f"gv-{version.path.name}", type="secondary"):
                revisions.restore(version)
                st.rerun()


def points_input(question: Question, stored: str) -> str:
    """A fixed budget spent across named buckets. Forcing a total makes the
    trade-off explicit; asking in prose gets you "both, really"."""
    st.markdown(f'<div class="qlabel">{question.prompt}</div>', unsafe_allow_html=True)
    if question.help:
        st.caption(question.help)

    current = parse_points(stored, question.buckets)
    cols = st.columns(len(question.buckets))
    scores = {
        bucket: int(col.number_input(
            bucket, 0, question.points_total, int(current[bucket]), step=1,
            key=f"a-{question.id}-{bucket}"))
        for col, bucket in zip(cols, question.buckets)
    }

    spent = sum(scores.values())
    total = question.points_total
    width = max(spent, total)
    bars = "".join(
        f'<span class="s{n}" style="width:{100 * v / width:.1f}%"></span>'
        for n, v in enumerate(scores.values()) if v
    )
    left = total - spent
    state = "" if spent == total else " off"
    tail = ("balanced" if left == 0 else
            f"{left} left" if left > 0 else f"{-left} over")
    st.markdown(
        f'<div class="alloc">{bars}</div>'
        f'<div class="alloc-read{state}"><span>{" · ".join(f"{k} {v}" for k, v in scores.items())}</span>'
        f'<span><b>{spent}</b> of {total} · {tail}</span></div>',
        unsafe_allow_html=True,
    )
    return format_points(scores)


def points_warning(question: Question, answer: str) -> str:
    if question.kind != POINTS:
        return ""
    spent = sum(parse_points(answer, question.buckets).values())
    if spent == question.points_total:
        return ""
    return (f"That is {spent} points, not {question.points_total}. Saved anyway, but the "
            "weighting only means something if the total is fixed.")


# --- 3. inventory -------------------------------------------------------------

def shape_row(item: Item, key: str) -> tuple[str, str, str]:
    """Garment, status and sizing scheme, chosen outside the form.

    All three change the shape of the form beneath: the garment decides which
    schemes apply, the scheme decides which size boxes exist. Inside a Streamlit
    form none of that takes effect until submit, so they sit above it.
    """
    c1, c2 = st.columns(2)
    garment = c1.selectbox(
        "Garment", garments(),
        index=garments().index(item.garment) if item.garment in garments() else 0,
        key=f"{key}-garment")
    status = c2.selectbox(
        "Status", STATUSES, index=STATUSES.index(item.status), key=f"{key}-status",
        help="Wanted pieces behave like owned ones in the generator, and are what "
             "the shopping plan spends money on.")

    applicable = schemes_for(garment)

    # Changing the garment has to reset the scheme beneath it. A Streamlit widget
    # keyed like this keeps its own value across a rerun, and most garments allow
    # Alpha, so picking Trousers while the box said Alpha left it saying Alpha:
    # the size boxes never changed and the form looked broken. Shoes only ever
    # hid it because they allow one scheme and so draw no box at all.
    was_key = f"{key}-garment-was"
    switched = st.session_state.get(was_key, garment) != garment
    st.session_state[was_key] = garment
    if switched:
        st.session_state.pop(f"{key}-scheme", None)
        # The size boxes belong to the old garment too. Left behind, a collar
        # size sits on a pair of trousers until something prunes it.
        for stale in [k for k in st.session_state if k.startswith(f"{key}-s-")]:
            st.session_state.pop(stale, None)

    scheme = applicable[0]
    if len(applicable) > 1:
        # After a switch the garment's own first scheme wins, not whatever the
        # last garment happened to be labelled with.
        index = 0 if switched else (applicable.index(item.scheme)
                                    if item.scheme in applicable else 0)
        scheme = st.selectbox(
            "Sized as", applicable, index=index, key=f"{key}-scheme",
            help="What this label uses. A trouser is 32/32 from one maker and M "
                 "from the next; both are true, so the garment allows both.")
    if switched:
        item.sizes = {}
    return garment, status, scheme


def item_fields(item: Item, key: str, garment: str, status: str, scheme: str) -> Item:
    """The shared add/edit form body. Returns the item with form values applied."""
    item.garment = garment
    item.status = status
    item.scheme = scheme
    item.category = inv_mod.category_for(garment)

    item.name = st.text_input("Name", item.name, key=f"{key}-name",
                              )
    c1, c3 = st.columns(2)
    item.colours = c1.multiselect(
        "Colours", colour_names(), default=[c for c in item.colours if c in colour_names()],
        key=f"{key}-colour",
        help="Pick as many as the garment actually has; the first is the one "
             "the swatch uses. From the catalogue only, because typed free-hand "
             "this became chocolate, Chocolate and dark brown, which is one "
             "colour wearing three names.")
    item.colour_hex = hex_for(item.colour) if item.colour else item.colour_hex
    item.fabric = c3.selectbox(
        "Fabric", fabric_options(),
        index=fabric_options().index(item.fabric) if item.fabric in fabric_options() else 0,
        key=f"{key}-fabric",
        help="Fixed list on purpose: free text gave three spellings of cotton and "
             "the image model three different shirts.")
    if item.fabric == NONE:
        item.fabric = ""

    # Grade and fit are what let a sourcing route be precise, but neither means
    # anything on every garment: there is no heavyweight belt, and a watch is not
    # cut to a shape. Which garments carry which is set in the catalogue.
    wants_grade, wants_fit = takes_grade(garment), takes_fit(garment)
    if wants_grade or wants_fit:
        columns = st.columns(2 if wants_grade and wants_fit else 1)
        column = iter(columns)
        if wants_grade:
            item.grade = next(column).selectbox(
                "Grade", grades(),
                index=grades().index(item.grade) if item.grade in grades() else 0,
                key=f"{key}-grade",
                help="What kind of thing it is within its type. This is what "
                     "separates a heavyweight tee from a plain one when both are "
                     "T-shirts.")
        if wants_fit:
            item.fit = next(column).selectbox(
                "Fit", fits(),
                index=fits().index(item.fit) if item.fit in fits() else 0,
                key=f"{key}-fit", help="How it is cut.")
    if not wants_grade:
        item.grade = ""
    if not wants_fit:
        item.fit = ""
    boxes = size_scheme(garment, scheme)
    if boxes:
        st.markdown(f'<div class="look-cap">Sizes, as this {garment.lower()} is '
                    f'labelled &middot; {scheme.lower()}</div>', unsafe_allow_html=True)
        cols = st.columns(min(len(boxes), 4))
        for n, field in enumerate(boxes):
            col = cols[n % len(cols)]
            current = item.sizes.get(field.key, "")
            if field.options:
                index = field.options.index(current) if current in field.options else 0
                item.sizes[field.key] = col.selectbox(
                    field.label, field.options, index=index,
                    help=field.help or None, key=f"{key}-s-{field.key}")
            else:
                item.sizes[field.key] = col.text_input(
                    field.label, current, help=field.help or None, key=f"{key}-s-{field.key}")

    if status == ASPIRATIONAL:
        item.link = st.text_input(
            "A link to one online", item.link, key=f"{key}-link",
            help="A specific thing that is the thing, or near enough. The sourcing "
                 "plan says which shop; this says which garment.").strip()
        found = retailers.match_url(item.link) if item.has_link else None
        item.wait_for_sale = st.checkbox(
            "Only buy this reduced", item.wait_for_sale, key=f"{key}-sale",
            help="Overrides the route. Some shops are worth full price for the right "
                 "piece and some never are.")
        if item.has_link:
            st.markdown(
                f'<div class="dict-row"><span class="meta">Points at </span>'
                f'{found.name if found else item.link_host}</div>',
                unsafe_allow_html=True)
        elif item.link:
            st.warning("That does not look like a link. It wants to start http.")

    item.description = st.text_area(
        "Description for the image model", item.description, key=f"{key}-desc", height=68,
        help="Only what a photograph would not show. Drape, weight, how it sits.")
    return item


def inventory_tab(profile: Profile, inventory: Inventory, outfits: Outfits) -> None:
    counts = inventory.counts()
    ui.stats([
        ("Owned", str(counts[OWNED])),
        ("Wanted", str(counts[ASPIRATIONAL])),
        ("Retired", str(counts[RETIRED])),
        ("Without a picture", str(sum(1 for i in inventory.items if not i.shop_photo))),
    ])
    ui.blurb(
        "Every piece, owned or merely wanted, lives here. Photograph anything words "
        "cannot pin down: \"green jacket\" gives the model a different jacket every "
        "time, the photograph gives it that one."
    )
    st.markdown(
        '<div class="look-cap">Every dropdown here is filled from the Garment '
        'Catalogue. <a href="?garments=all" target="_blank">Open it in its own tab '
        '&#8599;</a> to keep the dictionary beside the wardrobe.</div>',
        unsafe_allow_html=True)

    with st.expander("Add an item", expanded=not inventory.items):
        garment, status, scheme = shape_row(Item(), "new")
        with st.form("add-item", clear_on_submit=True):
            draft = item_fields(Item(), "new", garment, status, scheme)
            photo = st.file_uploader("Photo", type=list(inv_mod.UPLOAD_FORMATS), key="new-photo")
            if st.form_submit_button("Add to wardrobe"):
                if not draft.name.strip():
                    st.warning("Give it a name.")
                else:
                    added = inventory.add(draft)
                    if photo:
                        try:
                            added.photo = inv_mod.save_photo(added.id, photo)
                        except ValueError as exc:
                            st.warning(str(exc))
                    inventory.save()
                    restage(added, inventory)
                    st.rerun()

    if not inventory.items:
        ui.empty("Nothing in the wardrobe yet. Add the first piece above.")
        return

    ui.eyebrow("The wardrobe")
    f1, f2, f3 = st.columns([2, 1, 1])
    query = f1.text_input("Search", key="inv-q")
    category = f2.selectbox("Category", ["All", *categories()], key="inv-cat")
    status = f3.selectbox("Status", ["All", *STATUSES], key="inv-status")

    found = inventory.filter(
        query=query,
        category=None if category == "All" else category,
        status=None if status == "All" else status,
    )
    if not found:
        ui.empty("Nothing matches that.")
        return
    st.markdown(f'<div class="look-cap">{len(found)} of {len(inventory.items)} pieces</div>',
                unsafe_allow_html=True)

    for chunk in (found[i:i + 2] for i in range(0, len(found), 2)):
        for col, item in zip(st.columns(2, gap="large"), chunk):
            with col:
                item_card(item, inventory, outfits)


def restage(item: Item, inventory: Inventory) -> None:
    """Turn his snapshot of a garment into a catalogue shot of the same garment.

    Done on upload rather than on request, because a wardrobe photographed on a
    bedroom floor and a wardrobe photographed on white are two different things
    to look at, and only one of them is worth browsing.
    """
    if not item.has_photo:
        return
    with st.spinner("Putting it on a white background…"):
        try:
            written = shop_mod.generate_photo(item)
        except GEMINI_ERRORS as exc:
            st.warning(f"Kept your photograph; could not restage it. {exc}")
            return
    if written:
        item.product_photo = str(written[0])
        inventory.update(item)
        inventory.save()


def item_card(item: Item, inventory: Inventory, outfits: Outfits) -> None:
    """One garment in the grid: its picture, its spec, and a way into its page."""
    st.markdown(ui.SHOP_CSS, unsafe_allow_html=True)
    badge = {OWNED: "", ASPIRATIONAL: "wanted", RETIRED: "retired"}[item.status]
    shot = ui.product_shot(Path(item.shop_photo) if item.shop_photo else None, badge)
    detail = " · ".join(b for b in (item.garment, item.colour_line, item.fabric) if b)
    spec = " · ".join(b for b in (item.grade, item.fit) if b)
    sizes = item.size_line()
    st.markdown(
        f'<div class="product">{shot}<div class="body">'
        f'<div class="nm">{item.name or item.garment}</div>'
        f'<div class="kind">{detail}</div>'
        f'{f"<div class=size>{spec}</div>" if spec else ""}'
        f'<div class="size">{sizes or "no size recorded"}</div>'
        f'<a class="view" href="?item={item.id}" target="_blank">Open &#8599;</a>'
        f'</div></div>', unsafe_allow_html=True)

    if not item.product_photo:
        label = ("Put it on a white background" if item.has_photo
                 else "Draw it from the description")
        if st.button(label, key=f"draw-{item.id}",
                     type="secondary", use_container_width=True,
                     help="Restages your photograph as a catalogue shot, or draws one "
                          "from the colour and cloth if there is no photograph."):
            with st.spinner("Photographing…"):
                try:
                    written = shop_mod.generate_photo(item)
                except GEMINI_ERRORS as exc:
                    st.error(str(exc))
                    return
            if written:
                item.product_photo = str(written[0])
                inventory.update(item)
                inventory.save()
            st.rerun()

    with st.expander("Edit"):
        used = outfits.using(item.id)
        if used:
            st.caption(f"Worn in {ui.plural(len(used), 'outfit')}: "
                       f"{', '.join(o.name for o in used[:3])}"
                       f"{'…' if len(used) > 3 else ''}. Deleting takes it out of them.")
        garment, status, scheme = shape_row(item, f"e-{item.id}")
        with st.form(f"edit-{item.id}"):
            edited = item_fields(item, f"e-{item.id}", garment, status, scheme)
            new_photo = st.file_uploader("Replace photo", type=list(inv_mod.UPLOAD_FORMATS),
                                         key=f"ph-{item.id}")
            c1, c2 = st.columns(2)
            save = c1.form_submit_button("Save")
            delete = c2.form_submit_button("Delete")
            if save:
                uploaded = False
                if new_photo:
                    try:
                        edited.photo = inv_mod.save_photo(edited.id, new_photo)
                        uploaded = True
                    except ValueError as exc:
                        st.warning(str(exc))
                inventory.update(edited)
                inventory.save()
                if uploaded:
                    restage(edited, inventory)
                st.rerun()
            if delete:
                reset_mod.before(f"before deleting {item.name or item.garment}",
                                 "inventory", "outfits")
                # Cascade, or the outfits keep an id that resolves to nothing and
                # quietly report themselves as wearable.
                if outfits.forget_item(item.id):
                    outfits.save()
                inv_mod.drop_photo(item)
                inventory.remove(item.id)
                inventory.save()
                st.rerun()


# --- 4. principles ------------------------------------------------------------

def principles_tab(profile: Profile, answers: Answers, principles: Principles) -> None:
    ui.blurb(
        "Not the style guide. The guide is a document you read once; these are the "
        f"lines you hold in your head while getting dressed. Aim for about {TARGET}. "
        "Every one has to be checkable: you should be able to look at an outfit and "
        "say whether it obeys or breaks it. Only confirmed ones are fed into a "
        "generated look; a suggestion sits on the table until you say yes."
    )
    ui.meter(len(principles.confirmed()), TARGET, "Confirmed")

    ideas_panel(profile, answers, principles)
    kept_panel(principles)
    handwrite_panel(principles)


def ideas_panel(profile: Profile, answers: Answers, principles: Principles) -> None:
    ui.eyebrow("Suggestions")
    ui.blurb(
        f"{BATCH} at a time. Confirm the ones that ring true, bin the rest. Asking "
        "for ten in one go gets you four that are true and six that are padding, "
        "and padding in a list this short is worse than a gap. Each round is told "
        "what you have already confirmed, so it goes somewhere new. Generating "
        "replaces whatever is on the table rather than adding to it."
    )
    if st.button(f"Suggest {BATCH} more", type="primary"):
        guide = paths.guide().read_text() if paths.guide().is_file() else ""
        with st.spinner("Thinking…"):
            try:
                ideas = prin_mod.generate(profile, answers, guide, BATCH,
                                          principles.confirmed())
            except (ValueError, *GEMINI_ERRORS) as exc:
                st.error(str(exc))
                return
        reset_mod.before("before replacing the pending suggestions", "principles")
        principles.offer(ideas)
        principles.save()
        st.rerun()

    pending = principles.suggested()
    if not pending:
        st.markdown('<div class="look-cap">Nothing on the table.</div>',
                    unsafe_allow_html=True)
        return

    for p in pending:
        c1, c2, c3 = st.columns([8, 1, 1], vertical_alignment="center")
        c1.markdown(
            f'<div class="step"><div class="pieces">{p.text}</div>'
            f'<div class="why">{p.group} &middot; {p.reason}</div></div>',
            unsafe_allow_html=True)
        if c2.button("Confirm", key=f"confirm-{p.id}"):
            principles.confirm(p.id)
            principles.save()
            st.rerun()
        if c3.button("Bin", key=f"bin-{p.id}", type="secondary"):
            reset_mod.before(f"before binning the suggestion “{p.text[:48]}”", "principles")
            principles.remove(p.id)
            principles.save()
            st.rerun()


def kept_panel(principles: Principles) -> None:
    ui.eyebrow("Confirmed")
    if not principles.confirmed():
        ui.empty("Nothing confirmed yet. Take a suggestion above, or write your own below.")
        return
    for group, group_principles in principles.by_group().items():
        st.markdown(f'<div class="look-cap">{group}</div>', unsafe_allow_html=True)
        for p in group_principles:
            c1, c2 = st.columns([9, 1], vertical_alignment="center")
            c1.markdown(
                f'<div class="step"><div class="pieces">{p.text}</div>'
                f'<div class="why">{p.reason}</div></div>', unsafe_allow_html=True)
            if c2.button("Drop", key=f"drop-{p.id}", type="secondary"):
                reset_mod.before(f"before dropping the principle “{p.text[:48]}”",
                                 "principles")
                principles.remove(p.id)
                principles.save()
                st.rerun()


def handwrite_panel(principles: Principles) -> None:
    with st.expander("Write one by hand"):
        with st.form("add-principle", clear_on_submit=True):
            text = st.text_input("Instruction")
            reason = st.text_input("Reason")
            group = st.selectbox("Group", GROUPS)
            if st.form_submit_button("Add principle") and text.strip():
                principles.add(Principle(text=text.strip(), reason=reason.strip(), group=group))
                principles.save()
                st.rerun()


# --- 5. colour ----------------------------------------------------------------



def colour_tab(profile: Profile, palette: Palette) -> None:
    skin = profile.subject.skin_tone_hex
    ui.blurb(
        "One rule, and it is the only one that cannot be broken: <b>a colour worn "
        "on top must sit far enough from his skin</b>. Under "
        f"{pal_mod.TOO_CLOSE:.0f} units from {skin} in CIELAB it stops reading as a "
        "garment and starts reading as more of him. Everything below that line is "
        "bookkeeping: which colour goes on which garment, and which season it is "
        "worn in. There are no other verdicts here and nothing else is forbidden."
    )
    face_rule_panel(palette, skin)
    palette_panel(palette, skin)
    season_panel(palette)
    rules_panel(palette)


def face_rule_panel(palette: Palette, skin: str) -> None:
    ui.eyebrow("The one rule")
    breaks = pal_mod.breaks_the_rule(palette, skin)
    near = [c for c in palette.colours if c.near_the_face]
    if not near:
        ui.empty("No colour is allowed on Top yet, so there is nothing to check.")
        return
    if not breaks:
        st.markdown(
            f'<div class="look-cap"><span class="badge ok">all clear</span> '
            f'every one of the {len(near)} colours allowed on Top sits at least '
            f'{pal_mod.TOO_CLOSE:.0f} from his skin.</div>', unsafe_allow_html=True)
        return
    st.markdown(
        f'<div class="alarm">{len(breaks)} of {len(near)} colours allowed on Top '
        f'break the rule &middot; take Top off them, or drop them</div>',
        unsafe_allow_html=True)
    for colour in breaks:
        elsewhere = ", ".join(c for c in colour.allowed if c != "Top")
        st.markdown(
            f'<div class="step" style="border-left-color:{colour.hex}">'
            f'<div class="hd"><div class="pieces">'
            f'<span class="chip" style="background:{colour.hex}"></span>'
            f'{colour.name}</div><div class="cost">'
            f'{pal_mod.distance_line(colour.hex, skin)}</div></div>'
            f'<div class="why">Needs {pal_mod.TOO_CLOSE:.0f} from his skin and has '
            f'{pal_mod.distance_line(colour.hex, skin)}, so at the collar it '
            f'reads as more of him than as a garment. '
            f'Fine on {elsewhere or "nothing else"}.</div></div>',
            unsafe_allow_html=True)


def palette_panel(palette: Palette, skin: str) -> None:
    ui.eyebrow("The palette")
    st.markdown(
        '<div class="look-cap">Every colour carries a name, a role, the garments it '
        'is allowed on, and the seasons it is worn in. '
        '<a href="?colours=all" target="_blank">Open the full colour catalogue '
        '&#8599;</a></div>', unsafe_allow_html=True)

    # The catalogue picker sits outside the form: choosing from it fills the name
    # and the swatch, which inside a form would not happen until submit.
    picked = st.selectbox(
        "Start from the catalogue", ["Pick a colour of your own", *colour_names()],
        key="pal-pick",
        help="Fifty colours a wardrobe is built from. Or name your own and set "
             "the hex yourself.")
    custom = picked == "Pick a colour of your own"

    with st.form("add-colour", clear_on_submit=True):
        c1, c2 = st.columns([1, 3])
        hex_code = c1.color_picker("Hex", "#26303F" if custom else hex_for(picked),
                                   key="pal-hex")
        name = c2.text_input("Name", "" if custom else picked, key="pal-name",
                             )
        c3, c4 = st.columns([1, 2])
        role = c3.selectbox("Role", list(ROLES), key="pal-role",
                            help=" · ".join(f"{k}: {v}" for k, v in ROLES.items()))
        allowed = c4.multiselect("Allowed on", COLOUR_CATEGORIES, key="pal-cats",
                                 help="Leave empty to use the role's defaults.")
        seasons = st.multiselect("Seasons", SEASONS, key="pal-seasons",
                                 help="Leave empty for all year round.")
        note = st.text_input("Note", 
                             key="pal-note")
        passes, why = pal_mod.face_rule(hex_code, skin)
        if not pal_mod.measurable(name.strip() or picked):
            passes, why = True, ("not one colour, so there is nothing to measure "
                                 "against his skin")
        on_top = "Top" in allowed or (not allowed and
                                      "Top" in pal_mod.ROLE_CATEGORIES.get(role, ()))
        badge = "ok" if passes else ("no" if on_top else "want")
        label = ("clears the face" if passes
                 else "breaks the rule on Top" if on_top else "too close for Top")
        st.markdown(
            f'<div class="look-cap"><span class="badge {badge}">{label}</span> {why}'
            f' &middot; reads as {pal_mod.hue_name(hex_code)}</div>',
            unsafe_allow_html=True)
        if st.form_submit_button("Add to palette"):
            chosen = name.strip() or (picked if not custom else
                                      pal_mod.hue_name(hex_code).title())
            palette.add(Colour(name=chosen, hex=hex_code, role=role,
                               categories=list(allowed), seasons=list(seasons),
                               note=note.strip()))
            palette.save()
            st.rerun()

    if not palette.colours:
        ui.empty("No colours yet. Add one above, or start from the catalogue.")
        return

    for role, colours in palette.by_role().items():
        st.markdown(f'<div class="look-cap">{role} &middot; {ROLES[role]}</div>',
                    unsafe_allow_html=True)
        st.markdown(ui.swatch_strip(colours), unsafe_allow_html=True)
        for colour in colours:
            c1, c2 = st.columns([9, 1], vertical_alignment="center")
            note_line = f"<br>{colour.note}" if colour.note else ""
            if not pal_mod.measurable(colour.name):
                rule_line = ('<span class="badge">not one colour</span> nothing to '
                             'measure against his skin, so this one is your eye\'s call')
            elif not colour.near_the_face:
                rule_line = (f'<span class="badge">not worn on top</span> '
                             f'{pal_mod.distance_line(colour.hex, skin)} from his '
                             f'skin, which does not matter off the face')
            elif pal_mod.clears_the_face(colour.hex, skin):
                rule_line = (f'<span class="badge ok">clears the face</span> '
                             f'{pal_mod.distance_line(colour.hex, skin)} from his skin')
            else:
                rule_line = (f'<span class="badge no">breaks the rule</span> '
                             f'{pal_mod.face_rule(colour.hex, skin)[1]}')
            c1.markdown(
                f'<div class="step" style="border-left-color:{colour.hex}">'
                f'<div class="hd"><div class="pieces">'
                f'<span class="chip" style="background:{colour.hex}"></span>'
                f'{colour.name}</div><div class="cost">{colour.hex}</div></div>'
                f'<div class="why">{rule_line}<br>'
                f'{colour.family} &middot; '
                f'{", ".join(colour.allowed)} &middot; {colour.season_line}'
                f'{note_line}</div></div>',
                unsafe_allow_html=True)
            if c2.button("Drop", key=f"pdrop-{colour.id}", type="secondary"):
                reset_mod.before(f"before dropping the colour {colour.name}", "palette")
                palette.remove(colour.id)
                palette.save()
                st.rerun()


def season_panel(palette: Palette) -> None:
    ui.eyebrow("The four palettes")
    ui.blurb(
        "One wardrobe, four palettes. A colour with no seasons recorded is worn all "
        "year and appears in every one of these; the rest belong where the cloth and "
        "the light put them. Cream is a June colour and oatmeal is a February one "
        "even though both are pale."
    )
    if not palette.colours:
        ui.empty("Add some colours first.")
        return

    for chunk in (SEASONS[i:i + 2] for i in range(0, len(SEASONS), 2)):
        for column, season in zip(st.columns(2, gap="large"), chunk):
            with column:
                colours = palette.for_season(season)
                counts = pal_mod.coverage(palette, season)
                thin = [c for c, n in counts.items() if not n and c != "Accessory"]
                st.markdown(
                    f'<div class="look-cap">{season} &middot; {len(colours)} colours'
                    f'</div>', unsafe_allow_html=True)
                if colours:
                    st.markdown(ui.swatch_strip(colours, height="3.4rem"),
                                unsafe_allow_html=True)
                    st.markdown(
                        '<div class="look-cap">'
                        + " &middot; ".join(c.name for c in colours) + "</div>",
                        unsafe_allow_html=True)
                    if thin:
                        st.markdown(f'<div class="look-cap" style="color:var(--bad)">'
                                    f'nothing for {", ".join(thin).lower()}</div>',
                                    unsafe_allow_html=True)
                else:
                    ui.empty(f"Nothing for {season.lower()}")


def outfit_view(profile: Profile, outfit_id: str) -> None:
    """One outfit on its own page, with a way to vary it and a way to compare."""
    st.markdown(ui.CSS, unsafe_allow_html=True)
    ui.way_home(home_for("outfit"), "Outfit")
    st.markdown(ui.SHOP_CSS, unsafe_allow_html=True)
    inventory, outfits = Inventory.load(), Outfits.load()
    principles = Principles.load()
    outfit = outfits.by_id(outfit_id)
    if not outfit:
        st.markdown('<div class="masthead"><h1>Not <em>found</em></h1></div>',
                    unsafe_allow_html=True)
        ui.empty(f"No outfit with the id {outfit_id}.")
        st.markdown('<div class="answer-nav"><a href="./" target="_self">'
                    'Back to the app</a></div>', unsafe_allow_html=True)
        return

    state = wearability(outfit, inventory)
    pieces = inventory.resolve(outfit.item_ids)
    family = outfits.family(outfit)
    st.markdown(
        f'<div class="masthead"><h1>{outfit.name}</h1>'
        f'<div class="sub">{", ".join(outfit.tags) or "no tags"}'
        f'{f" &middot; one of {len(family)} in this family" if len(family) > 1 else ""}'
        f'</div></div>', unsafe_allow_html=True)

    left, right = st.columns([3, 2], gap="large")
    with left:
        shots = outfit.shots
        if shots:
            ui.plate(shots[0], outfit.name[:26])
            for row in (shots[1:][i:i + 2] for i in range(0, len(shots) - 1, 2)):
                for column, shot in zip(st.columns(2), row):
                    with column:
                        ui.plate(shot, width=380)
        else:
            ui.empty("No image on this one.")
    with right:
        badge = ('<span class="badge no">broken</span>' if state.broken
                 else '<span class="badge ok">wearable now</span>' if state.wearable
                 else f'<span class="badge want">{len(state.missing)} to find</span>')
        st.markdown(f'<div class="look-cap">{badge}</div>', unsafe_allow_html=True)
        ui.eyebrow("What is in it")
        for piece in pieces:
            st.markdown(
                f'<div class="look-cap"><span class="chip" '
                f'style="background:{piece.colour_hex}"></span>'
                f'<a href="?item={piece.id}" target="_blank">{piece.name or piece.garment}'
                f'</a> &middot; {piece.garment}'
                f'{" &middot; wanted" if not piece.owned else ""}</div>',
                unsafe_allow_html=True)
        if state.broken:
            st.warning(f"Cannot be worn: {state.fault}.")
        settings = [(k, v) for k, v in (("Framing", outfit.shot),
                                        ("Background", outfit.background),
                                        ("Extra direction", outfit.extra)) if v]
        if settings:
            ui.eyebrow("Generated with")
            ui.table([{"Setting": k, "Value": v} for k, v in settings])
        if outfit.notes:
            st.markdown(f'<div class="look-cap">{outfit.notes}</div>',
                        unsafe_allow_html=True)

    if len(family) > 1:
        ui.eyebrow("The family")
        ui.blurb("Every version of this outfit, oldest first. Pick any two to put "
                 "side by side.")
        for chunk in (family[i:i + 3] for i in range(0, len(family), 3)):
            for column, sibling in zip(st.columns(3, gap="medium"), chunk):
                with column:
                    cover = sibling.cover()
                    if cover:
                        ui.plate(Path(cover), width=320)
                    here = " · this one" if sibling.id == outfit.id else ""
                    st.markdown(
                        f'<div class="look-cap"><a href="?outfit={sibling.id}" '
                        f'target="_self">{sibling.name}</a>{here}</div>',
                        unsafe_allow_html=True)
        others = [o for o in family if o.id != outfit.id]
        if others:
            c1, c2 = st.columns([3, 1])
            against = c1.selectbox("Compare this one with", [o.id for o in others],
                                   format_func=lambda i: outfits.by_id(i).name,
                                   key="ov-compare")
            c2.markdown(
                f'<div class="look-cap"><a class="view" '
                f'href="?compare={outfit.id},{against}" target="_blank" '
                f'style="display:block;text-align:center;padding:.7rem;'
                f'background:var(--brass);color:#17110E;text-decoration:none">'
                f'Side by side &#8599;</a></div>', unsafe_allow_html=True)

    variation_panel(profile, outfit, inventory, outfits, principles)

    with st.expander("The prompt it was generated from"):
        st.code(outfit.prompt or "(not recorded)", language=None)

    st.markdown('<div class="answer-nav"><a href="./" target="_self">Back to the app</a>'
                '</div>', unsafe_allow_html=True)


def variation_panel(profile: Profile, outfit: Outfit, inventory: Inventory,
                    outfits: Outfits, principles: Principles) -> None:
    """Start from this outfit's settings, change one thing, generate the rival."""
    ui.eyebrow("Make a variation")
    ui.blurb(
        "Everything below starts where this outfit left off. Swap a piece, change "
        "the framing, add a note, and generate. The new one keeps this one as its "
        "parent so the two can be put side by side afterwards."
    )
    wearable_items = [i for i in inventory.items if i.status != RETIRED]
    current = {i.category: i for i in inventory.resolve(outfit.item_ids)}

    picked: list[str] = []
    cols = st.columns(4, gap="medium")
    for col, category in zip(cols, ("Outerwear", "Top", "Bottom", "Shoes")):
        with col:
            options = [i for i in wearable_items if i.category == category]
            if not options:
                continue
            ids = [i.id for i in options]
            here = current.get(category)
            index = ids.index(here.id) + 1 if here and here.id in ids else 0
            labels = {i.id: i.label for i in options}
            chosen = st.selectbox(category, [None, *ids], index=index,
                                  format_func=lambda i: labels.get(i, "—"),
                                  key=f"var-{category}")
            if chosen:
                picked.append(chosen)
    accessories = [i for i in wearable_items if i.category == "Accessory"]
    if accessories:
        ids = [i.id for i in accessories]
        labels = {i.id: i.label for i in accessories}
        picked += st.multiselect("Accessories", ids,
                                 default=[i for i in outfit.item_ids if i in ids],
                                 format_func=lambda i: labels[i], key="var-acc")

    items = inventory.resolve(picked)
    c1, c2, c3 = st.columns([2, 2, 1])
    shots = list(SHOTS)
    backgrounds = list(BACKGROUNDS)
    shot = c1.selectbox(
        "Framing", shots,
        index=shots.index(outfit.shot if outfit.shot in shots else DEFAULT_SHOT),
        key="var-shot")
    background = c2.selectbox(
        "Background", backgrounds,
        index=backgrounds.index(
            outfit.background if outfit.background in backgrounds else DEFAULT_BACKGROUND),
        key="var-bg")
    count = c3.number_input("Variations", 1, 4, 1, key="var-count")
    name = st.text_input("Name it", key="var-name")
    extra = st.text_input("Extra direction", outfit.extra, key="var-extra",
                          )
    use_principles = st.toggle("Apply the principles", value=bool(principles.principles),
                               key="var-prin")

    if not items:
        ui.empty("Pick at least one piece.")
        return

    photos = reference_photos(items)
    prompt = build_outfit_prompt(
        profile, [i.describe() for i in items], shot=shot, background=background,
        principles=principles.as_prompt_block() if use_principles else "",
        photo_count=len(photos), extra=extra)
    with st.expander("The prompt this would send"):
        st.code(prompt, language=None)

    portrait = profile.photo("neutral")
    if not portrait:
        st.warning("No reference portrait, so nothing to dress.")
        return

    if st.button("Generate the variation", type="primary"):
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        title = name.strip() or f"{outfit.name}, again"
        with st.spinner(f"Dressing {profile.subject.name}…"):
            try:
                written = generate_images(
                    prompt,
                    out_prefix=paths.looks() / f"{stamp}-{slug(title)}",
                    reference_images=[portrait, *photos],
                    count=int(count),
                    settings=Settings.from_env())
            except GEMINI_ERRORS as exc:
                st.error(str(exc))
                return
        made = outfits.add(Outfit(
            name=title, item_ids=[i.id for i in items], tags=list(outfit.tags),
            images=[str(w) for w in written], notes=outfit.notes, prompt=prompt,
            shot=shot, background=background, extra=extra, parent=outfit.id))
        outfits.save()
        st.success(f"Made “{title}”.")
        st.markdown(
            f'<div class="look-cap"><a href="?compare={outfit.id},{made.id}" '
            f'target="_self">Put them side by side &#8599;</a></div>',
            unsafe_allow_html=True)


def compare_view(pair: str) -> None:
    """Two outfits, side by side, with what changed named underneath."""
    st.markdown(ui.CSS, unsafe_allow_html=True)
    ui.way_home(home_for("compare"), "Comparison")
    inventory, outfits = Inventory.load(), Outfits.load()
    ids = [i.strip() for i in pair.split(",") if i.strip()][:2]
    chosen = [outfits.by_id(i) for i in ids]
    chosen = [o for o in chosen if o]

    if len(chosen) < 2:
        st.markdown('<div class="masthead"><h1>Nothing to <em>compare</em></h1></div>',
                    unsafe_allow_html=True)
        ui.empty("Needs two outfits, as ?compare=one,two.")
        st.markdown('<div class="answer-nav"><a href="./" target="_self">'
                    'Back to the app</a></div>', unsafe_allow_html=True)
        return

    left, right = chosen
    change = compare(left, right, inventory)
    st.markdown(
        f'<div class="masthead"><h1>{left.name} <em>or</em> {right.name}</h1>'
        f'<div class="sub">{change.summary}</div></div>', unsafe_allow_html=True)

    columns = st.columns(2, gap="large")
    for column, outfit in zip(columns, chosen):
        with column:
            cover = outfit.cover()
            if cover:
                ui.plate(Path(cover), outfit.name[:26])
            else:
                ui.no_plate("no photograph yet")
            state = wearability(outfit, inventory)
            st.markdown(
                f'<div class="look-cap">'
                f'{"wearable now" if state.wearable else f"{len(state.missing)} to find"}'
                f' &middot; <a href="?outfit={outfit.id}" target="_self">open it</a>'
                f'</div>', unsafe_allow_html=True)
            for piece in inventory.resolve(outfit.item_ids):
                mark = ""
                if piece in change.added:
                    mark = ' <span class="badge ok">new</span>'
                elif piece in change.removed:
                    mark = ' <span class="badge no">dropped</span>'
                st.markdown(
                    f'<div class="look-cap"><span class="chip" '
                    f'style="background:{piece.colour_hex}"></span>'
                    f'{piece.name or piece.garment}{mark}</div>', unsafe_allow_html=True)

    ui.eyebrow("What changed")
    if change.identical:
        ui.empty("Nothing. Same pieces, same settings, so any difference is the "
                 "model's alone.")
    else:
        rows = [{"Change": "Added", "Detail": i.name or i.garment} for i in change.added]
        rows += [{"Change": "Dropped", "Detail": i.name or i.garment}
                 for i in change.removed]
        rows += [{"Change": setting, "Detail": f"{was} → {now}"}
                 for setting, was, now in change.settings]
        ui.table(rows)
        st.markdown(f'<div class="look-cap">{ui.plural(len(change.kept), "piece")} unchanged</div>',
                    unsafe_allow_html=True)

    ui.eyebrow("Keep one")
    c1, c2 = st.columns(2)
    for column, outfit in zip((c1, c2), chosen):
        if column.button(f"♥ Love {outfit.name}", key=f"cmp-{outfit.id}",
                         use_container_width=True,
                         type="primary" if outfit.loved else "secondary"):
            outfit.loved = not outfit.loved
            outfits.update(outfit)
            outfits.save()
            st.rerun()

    st.markdown('<div class="answer-nav"><a href="./" target="_self">Back to the app</a>'
                '</div>', unsafe_allow_html=True)


def garment_catalogue_view() -> None:
    """The same dictionary, on a page of its own, for a second monitor."""
    st.markdown(ui.CSS, unsafe_allow_html=True)
    ui.way_home(home_for("garments"), "Garment catalogue")
    vocab = vocabulary.Vocabulary.load()
    st.markdown(
        '<div class="masthead"><h1>Garment <em>catalogue</em></h1>'
        f'<div class="sub">{len(vocab.garments)} garments &middot; '
        f'{len(vocab.fabrics)} fabrics &middot; {len(vocab.fits) - 1} fits &middot; '
        f'{len(vocab.grades) - 1} grades</div></div>', unsafe_allow_html=True)
    garment_catalogue_panel()
    st.markdown('<div class="answer-nav"><a href="./" target="_self">Back to the app</a>'
                '</div>', unsafe_allow_html=True)


# --- 2. garment catalogue -----------------------------------------------------

def garment_catalogue_panel() -> None:
    """The vocabularies the rest of the app is built from, editable.

    Three sections behind tabs rather than one long scroll: this page used to
    render twenty-nine expanders for the garments and forty-five rows for the
    fabrics, one after another, and finding anything meant scrolling past
    everything. Each section reads as a table by default and only shows its
    editing controls when asked, because most visits here are to look something
    up rather than to change it.
    """
    vocab = vocabulary.Vocabulary.load()
    inventory = Inventory.load()

    ui.stats([
        ("Garments", str(len(vocab.garments))),
        ("Fabrics", str(len(vocab.fabrics))),
        ("Colours", str(len(vocab.colours))),
        ("Grades", str(len([g for g in vocab.grades if g]))),
        ("Fits", str(len([f for f in vocab.fits if f]))),
    ], brass_first=True)
    ui.blurb(
        "Every list the rest of the app is built from. The garments, their "
        "categories and the schemes their labels use; the fabrics and their "
        "families; the grades and fits. Anything already in use says so and refuses "
        "to be deleted, because removing it leaves those pieces holding a word the "
        "app no longer knows."
    )

    garments_tab, fabrics_tab, colours_tab, words_tab = st.tabs(
        ["Garments", "Fabrics", "Colours", "Grades and fits"])
    with garments_tab:
        garment_section(vocab, inventory)
    with fabrics_tab:
        fabric_section(vocab, inventory)
    with colours_tab:
        colour_section(vocab, inventory)
    with words_tab:
        words_section(vocab, inventory)

    with st.expander("Start again"):
        ui.blurb("Throws away every change and reloads the vocabulary the app ships "
                 "with. Pieces naming a garment or fabric you added will be left "
                 "holding a word the catalogue no longer knows.")
        if st.button("Restore the default catalogue", type="secondary"):
            reset_mod.before("before restoring the default garment catalogue",
                             "vocabulary")
            vocab.restore_defaults()
            st.rerun()


def garment_section(vocab, inventory: Inventory) -> None:
    used = {i.garment for i in inventory.items}
    counts = {g.name: sum(1 for i in inventory.items if i.garment == g.name)
              for g in vocab.garments}

    ui.table([{
        "Garment": g.name,
        "Category": g.category,
        "Sized as": ", ".join(g.schemes) or "—",
        "Carries": ", ".join(
            a for a, on in (("grade", g.takes_grade), ("fit", g.takes_fit)) if on) or "—",
        "In the wardrobe": str(counts[g.name]) if counts[g.name] else "—",
    } for g in vocab.garments], numeric=("In the wardrobe",))

    if not st.toggle("Change the garments", key="cat-edit-g",
                     help="Add one, re-categorise one, change which schemes its "
                          "labels use, or remove one nothing is using."):
        return

    ui.eyebrow("Change one")
    names = [g.name for g in vocab.garments]
    chosen = st.selectbox("Which garment", names, key="cat-pick-g")
    garment = vocab.garment(chosen)
    in_use = counts.get(chosen, 0)
    with st.form(f"g-{chosen}"):
        c1, c2 = st.columns([1, 2])
        garment.category = c1.selectbox(
            "Category", vocab.category_names(),
            index=vocab.category_names().index(garment.category)
            if garment.category in vocab.category_names() else 0, key=f"gc-{chosen}")
        garment.schemes = c2.multiselect(
            "Size schemes its labels use", list(vocabulary.SCHEMES),
            default=[x for x in garment.schemes if x in vocabulary.SCHEMES],
            key=f"gs-{chosen}",
            help="Most specific first. The first is what a new piece defaults to.")
        a1, a2 = st.columns(2)
        garment.takes_grade = a1.checkbox(
            "Carries a grade", garment.takes_grade, key=f"gg-{chosen}",
            help="Knitted, heavyweight, fine. Tops only, as a rule: there is no "
                 "heavyweight belt.")
        garment.takes_fit = a2.checkbox(
            "Carries a fit", garment.takes_fit, key=f"gf-{chosen}",
            help="How it is cut. Tops, blazers and trousers.")
        st.markdown(
            '<div class="dict-row"><span class="meta">Boxes on the form: </span>'
            + " ".join(f'<span class="dict-chip on">{f.label}</span>'
                       for f in vocab.scheme_for(chosen)) + "</div>",
            unsafe_allow_html=True)
        b1, b2 = st.columns(2)
        if b1.form_submit_button("Save"):
            vocab.save()
            st.rerun()
        if b2.form_submit_button("Remove from the catalogue"):
            if in_use:
                st.warning(f"{ui.plural(in_use, 'piece')} in the wardrobe are {chosen}. "
                           "Re-classify them first.")
            else:
                reset_mod.before(f"before removing the garment {chosen}", "vocabulary")
                vocab.remove_garment(chosen)
                vocab.save()
                st.rerun()

    ui.eyebrow("Add one")
    with st.form("add-garment", clear_on_submit=True):
        c1, c2 = st.columns([2, 1])
        name = c1.text_input("Name")
        category = c2.selectbox("Category", vocab.category_names(), key="ag-cat")
        picked = st.multiselect("Size schemes its labels use", list(vocabulary.SCHEMES),
                                default=["Alpha"], key="ag-scheme")
        if st.form_submit_button("Add garment"):
            if not name.strip():
                st.warning("Give it a name.")
            elif vocab.garment(name.strip()):
                st.warning(f"{name.strip()} is already in the catalogue.")
            else:
                vocab.add_garment(vocabulary.Garment(
                    name=name.strip(), category=category,
                    schemes=list(picked) or ["Free text"]))
                vocab.save()
                st.rerun()


def fabric_section(vocab, inventory: Inventory) -> None:
    counts = {f.name: sum(1 for i in inventory.items if i.fabric == f.name)
              for f in vocab.fabrics}

    for family, fabrics in vocab.by_family().items():
        st.markdown(f'<div class="dict-h">{family}<span>{len(fabrics)}</span></div>',
                    unsafe_allow_html=True)
        # Three across, so forty-five fabrics are fifteen rows rather than forty-five.
        for chunk in (fabrics[i:i + 3] for i in range(0, len(fabrics), 3)):
            for column, fabric in zip(st.columns(3), chunk):
                n = counts.get(fabric.name, 0)
                column.markdown(
                    f'<div class="dict-row">{fabric.name}'
                    f'<span class="meta">{f" · on {n}" if n else ""}</span></div>',
                    unsafe_allow_html=True)

    if not st.toggle("Change the fabrics", key="cat-edit-f",
                     help="Add one, move one to a different family, or remove one "
                          "nothing is using."):
        return

    ui.eyebrow("Change one")
    names = [f.name for f in vocab.fabrics]
    chosen = st.selectbox("Which fabric", names, key="cat-pick-f")
    fabric = next(f for f in vocab.fabrics if f.name == chosen)
    in_use = counts.get(chosen, 0)
    with st.form(f"f-{chosen}"):
        families = list(vocab.families())
        fabric.family = st.selectbox(
            "Family", families,
            index=families.index(fabric.family) if fabric.family in families else 0,
            key=f"ff-{chosen}",
            help="What a sourcing route matches on, so one line can cover flannel, "
                 "worsted and hopsack at once.")
        b1, b2 = st.columns(2)
        if b1.form_submit_button("Save"):
            vocab.save()
            st.rerun()
        if b2.form_submit_button("Remove from the catalogue"):
            if in_use:
                st.warning(f"{ui.plural(in_use, 'piece')} are made of {chosen}.")
            else:
                reset_mod.before(f"before removing the fabric {chosen}", "vocabulary")
                vocab.remove_fabric(chosen)
                vocab.save()
                st.rerun()

    ui.eyebrow("Add one")
    with st.form("add-fabric", clear_on_submit=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name")
        family = c2.selectbox("Family", [*vocab.families(), "New family…"],
                              key="af-family")
        fresh = st.text_input("New family name", key="af-new")
        if st.form_submit_button("Add fabric"):
            picked = fresh.strip() if family == "New family…" else family
            if not name.strip():
                st.warning("Give it a name.")
            elif not picked:
                st.warning("Give it a family, or a route can never match it.")
            else:
                vocab.add_fabric(vocabulary.Fabric(name=name.strip(), family=picked))
                vocab.save()
                st.rerun()


def colour_section(vocab, inventory: Inventory) -> None:
    """The colour names every garment and every palette entry is drawn from."""
    counts = {c.name: sum(1 for i in inventory.items if c.name in i.colours)
              for c in vocab.colours}
    st.markdown('<div class="look-cap">The names a garment\'s colour is picked '
                'from, and the swatches the palette is built out of. '
                '<a href="?colours=all" target="_blank">Open in its own tab '
                '&#8599;</a></div>', unsafe_allow_html=True)

    for group, rows in vocab.colour_groups().items():
        st.markdown(f'<div class="dict-h">{group}<span>{len(rows)}</span></div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<div style="display:flex;border:1px solid var(--line)">'
            + "".join(f'<div style="flex:1;background:{h};height:2.6rem" '
                      f'title="{n} {h}"></div>' for n, h in rows) + "</div>",
            unsafe_allow_html=True)
        for chunk in (rows[i:i + 3] for i in range(0, len(rows), 3)):
            for column, (name, code) in zip(st.columns(3), chunk):
                n = counts.get(name, 0)
                column.markdown(
                    f'<div class="dict-row">'
                    f'<span class="chip" style="background:{code}"></span>{name}'
                    f'<span class="meta"> · {code}{f" · on {n}" if n else ""}</span>'
                    f'</div>', unsafe_allow_html=True)

    if not st.toggle("Change the colours", key="cat-edit-c",
                     help="Add one, move one to a different group, or remove one "
                          "nothing is using."):
        return

    ui.eyebrow("Change one")
    names = list(vocab.colour_names())
    chosen = st.selectbox("Which colour", names, key="cat-pick-c")
    colour = next(c for c in vocab.colours if c.name == chosen)
    in_use = counts.get(chosen, 0)
    with st.form(f"c-{chosen}"):
        c1, c2 = st.columns([1, 2])
        colour.hex = c1.color_picker("Swatch", colour.hex, key=f"ch-{chosen}")
        groups = list(vocab.colour_groups())
        colour.group = c2.selectbox(
            "Group", groups,
            index=groups.index(colour.group) if colour.group in groups else 0,
            key=f"cg-{chosen}")
        b1, b2 = st.columns(2)
        if b1.form_submit_button("Save"):
            vocab.save()
            st.rerun()
        if b2.form_submit_button("Remove from the catalogue"):
            if in_use:
                st.warning(f"{ui.plural(in_use, 'piece')} are {chosen}.")
            else:
                reset_mod.before(f"before removing the colour {chosen}", "vocabulary")
                vocab.remove_colour(chosen)
                vocab.save()
                st.rerun()

    ui.eyebrow("Add one")
    with st.form("add-colour-name", clear_on_submit=True):
        c1, c2, c3 = st.columns([1, 2, 2])
        code = c1.color_picker("Swatch", "#7A7A78", key="ac-hex")
        name = c2.text_input("Name")
        group = c3.selectbox("Group", [*vocab.colour_groups(), "New group…"],
                             key="ac-group")
        fresh = st.text_input("New group name", key="ac-new")
        if st.form_submit_button("Add colour"):
            picked = fresh.strip() if group == "New group…" else group
            if not name.strip():
                st.warning("Give it a name. That is the point of the list.")
            elif name.strip() in names:
                st.warning(f"{name.strip()} is already in the catalogue.")
            else:
                vocab.add_colour(vocabulary.NamedColour(
                    name=name.strip(), hex=code, group=picked or "Unfiled"))
                vocab.save()
                st.rerun()


def words_section(vocab, inventory: Inventory) -> None:
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown('<div class="dict-h">Grade</div>', unsafe_allow_html=True)
        ui.blurb(
            "What separates two garments of the same type that come from different "
            "shops. A heavyweight tee and a plain tee are both T-shirts; the grade "
            "is what sends one to Asos and the other to Uniqlo."
        )
        word_list_panel(vocab, "grades", inventory, "grade")
    with right:
        st.markdown('<div class="dict-h">Fit</div>', unsafe_allow_html=True)
        ui.blurb(
            "How the garment is cut, as the maker describes it. Recorded on the "
            "piece and available to the sourcing plan in the same way as grade."
        )
        word_list_panel(vocab, "fits", inventory, "fit")


def word_list_panel(vocab, field: str, inventory: Inventory, item_field: str) -> None:
    """A short editable vocabulary, with what uses each word and a guard on removal.

    This was two free-text boxes, one word a line, with a blank first line that
    had to be explained. Which meant deleting a word silently orphaned every
    piece carrying it: the form then showed blank for those pieces and the next
    save wiped the value. A list you can see the consequences of is both easier
    to read and harder to break.
    """
    words = [w for w in getattr(vocab, field) if w]
    counts: dict[str, int] = {}
    for item in inventory.items:
        value = getattr(item, item_field, "")
        if value:
            counts[value] = counts.get(value, 0) + 1

    if not words:
        ui.empty("Nothing here yet.")
    for word in words:
        used = counts.get(word, 0)
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        c1.markdown(
            f'<div class="dict-row">{word}'
            f'<span class="meta">{f" · on {ui.plural(used, 'piece')}" if used else " · unused"}'
            f'</span></div>', unsafe_allow_html=True)
        if c2.button("Drop", key=f"{field}-drop-{word}", type="secondary"):
            if used:
                st.warning(f"{ui.plural(used, 'piece')} are marked {word}. Change them first, "
                           "or they will be left holding a word the catalogue has "
                           "forgotten.")
            else:
                reset_mod.before(f"before removing the {item_field} {word}", "vocabulary")
                setattr(vocab, field, [w for w in getattr(vocab, field) if w != word])
                vocab.save()
                st.rerun()

    orphans = sorted(v for v in counts if v not in words)
    if orphans:
        st.warning(
            "Pieces are carrying " + ", ".join(f"**{o}** ({counts[o]})" for o in orphans)
            + ", which is not on this list. Add the word back, or edit those pieces.")

    with st.form(f"add-{field}", clear_on_submit=True):
        c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
        fresh = c1.text_input("Add one", key=f"{field}-new", label_visibility="collapsed")
        if c2.form_submit_button("Add") and fresh.strip():
            if fresh.strip() in words:
                st.warning(f"{fresh.strip()} is already there.")
            else:
                getattr(vocab, field).append(fresh.strip())
                vocab.save()
                st.rerun()


def retailer_catalogue_view() -> None:
    """Every shop the plan can point at, on its own page, editable."""
    st.markdown(ui.CSS, unsafe_allow_html=True)
    ui.way_home(home_for("shops"), "Retailer catalogue")
    catalogue = retailers.Catalogue.load()
    plan = sourcing.Plan.load()
    in_use = {store for route in plan.routes for store in route.stores}

    st.markdown(
        '<div class="masthead"><h1>Retailer <em>catalogue</em></h1>'
        f'<div class="sub">{len(catalogue.retailers)} shops &middot; '
        f'{len(in_use)} used by the plan</div></div>', unsafe_allow_html=True)
    ui.blurb(
        "Every shop a route can point at. Add the ones you actually use, drop the "
        "ones you never will. A shop still named by a route cannot be removed here "
        "without the route quietly losing it, so those say so."
    )

    with st.expander("Add a shop"):
        with st.form("add-shop", clear_on_submit=True):
            c1, c2 = st.columns([2, 1])
            name = c1.text_input("Name")
            kind = c2.selectbox("Kind", retailers.KINDS, key="as-kind")
            search = st.text_input(
                "Search link", 
                help="Put {q} where the search term goes. The app escapes it for you.")
            strengths = st.multiselect("Sells", garments(), key="as-sells")
            c3, c4 = st.columns(2)
            low = c3.number_input("Typical from £", 0, 5000, 30, step=5, key="as-low")
            high = c4.number_input("Typical to £", 0, 10000, 200, step=10, key="as-high")
            note = st.text_area("Note", height=68, key="as-note",
                                )
            if st.form_submit_button("Add to the catalogue"):
                if not name.strip():
                    st.warning("Give it a name.")
                elif "{q}" not in search:
                    st.warning("The search link needs {q} where the search term goes.")
                elif not strengths:
                    st.warning("Say what it sells, or no route can use it.")
                elif low >= high:
                    st.warning("The price band runs the wrong way.")
                else:
                    catalogue.add(retailers.Retailer(
                        name=name.strip(), kind=kind, strengths=list(strengths),
                        price_low=float(low), price_high=float(high),
                        search=search.strip(), note=note.strip()))
                    catalogue.save()
                    st.rerun()

    for kind, shops in catalogue.by_kind().items():
        ui.eyebrow(f"{kind} · {len(shops)}")
        for shop in shops:
            used_by = [r.label or r.garment for r in plan.routes if shop.id in r.stores]
            badge = (f'<span class="badge want">{ui.plural(len(used_by), "route")}</span>'
                     if used_by else "")
            st.markdown(
                f'<div class="step"><div class="hd"><div class="pieces">{shop.name}'
                f'</div>{badge}</div><div class="why">{shop.note or "no note"}<br>'
                f'{len(shop.strengths)} garment types &middot; typically £{shop.price_low:,.0f}'
                f' to £{shop.price_high:,.0f}'
                f'{"<br>Used by: " + ", ".join(used_by) if used_by else ""}</div></div>',
                unsafe_allow_html=True)
            with st.expander(f"Edit {shop.name}"):
                with st.form(f"shop-{shop.id}"):
                    e1, e2 = st.columns([2, 1])
                    shop.name = e1.text_input("Name", shop.name, key=f"sn-{shop.id}")
                    shop.kind = e2.selectbox(
                        "Kind", retailers.KINDS,
                        index=retailers.KINDS.index(shop.kind)
                        if shop.kind in retailers.KINDS else 0, key=f"sk-{shop.id}")
                    shop.search = st.text_input("Search link", shop.search,
                                                key=f"ss-{shop.id}")
                    shop.strengths = st.multiselect(
                        "Sells", garments(),
                        default=[g for g in shop.strengths if g in garments()],
                        key=f"sg-{shop.id}")
                    e3, e4 = st.columns(2)
                    shop.price_low = e3.number_input("Typical from £", 0, 5000,
                                                     int(shop.price_low), step=5,
                                                     key=f"sl-{shop.id}")
                    shop.price_high = e4.number_input("Typical to £", 0, 10000,
                                                      int(shop.price_high), step=10,
                                                      key=f"sh-{shop.id}")
                    shop.note = st.text_area("Note", shop.note, height=68,
                                             key=f"sno-{shop.id}")
                    b1, b2 = st.columns(2)
                    if b1.form_submit_button("Save"):
                        catalogue.save()
                        st.rerun()
                    if b2.form_submit_button("Remove from the catalogue"):
                        reset_mod.before(f"before removing the shop {shop.name}",
                                         "retailers")
                        catalogue.remove(shop.id)
                        catalogue.save()
                        if used_by:
                            st.warning(f"{shop.name} was named by {ui.plural(len(used_by), 'route')}; "
                                       "they have lost it.")
                        st.rerun()

    with st.expander("Start again"):
        if st.button("Restore the default catalogue", type="secondary"):
            reset_mod.before("before restoring the default retailer catalogue",
                             "retailers")
            catalogue.restore_defaults()
            st.rerun()

    st.markdown('<div class="answer-nav"><a href="./" target="_self">Back to the app</a>'
                '</div>', unsafe_allow_html=True)


def colour_catalogue_view(palette: Palette) -> None:
    """Every colour with a name, on its own page.

    It used to print lightness, which was left over from the warmth verdict and
    decided nothing once that went. What it prints instead is the only number
    the app actually rules on: how far the colour sits from his skin, and
    therefore whether he can wear it at the collar.
    """
    st.markdown(ui.CSS, unsafe_allow_html=True)
    ui.way_home(home_for("colours"), "Colour catalogue")
    skin = Profile.load().subject.skin_tone_hex
    mine = {c.hex.upper(): c for c in palette.colours}
    st.markdown(
        '<div class="masthead"><h1>Colour <em>catalogue</em></h1>'
        f'<div class="sub">{len(colour_names())} named colours &middot; '
        f'{len(palette.colours)} in the palette &middot; measured against his skin'
        '</div></div>', unsafe_allow_html=True)

    extras = [c for c in palette.colours if c.name not in colour_names()]
    if extras:
        ui.eyebrow("Yours, named by you")
        ui.table([{
            "": f'<span class="chip" style="background:{c.hex}"></span>',
            "Name": c.name, "Hex": c.hex, "Reads as": c.family,
            "Role": c.role, "Seasons": c.season_line,
        } for c in extras])

    for group, rows in named_colours().items():
        ui.eyebrow(group)
        st.markdown(
            '<div style="display:flex;border:1px solid var(--line)">'
            + "".join(f'<div style="flex:1;background:{h};height:3.2rem" '
                      f'title="{n} {h}"></div>' for n, h in rows)
            + "</div>", unsafe_allow_html=True)
        ui.table([{
            "": f'<span class="chip" style="background:{ui.swatch_for(n, h)}"></span>',
            "Name": n,
            # The placeholder hex is scaffolding for the swatch, not a fact
            # about the garment. Printing it, and calling it orange, is the
            # app inventing a colour that the shirt does not have.
            "Hex": h if pal_mod.measurable(n) else "&mdash;",
            "Reads as": pal_mod.hue_name(h) if pal_mod.measurable(n) else "several",
            "From his skin": (pal_mod.distance_line(h, skin)
                              if pal_mod.measurable(n) else "&mdash;"),
            "On top": ('<span class="badge">your call</span>' if not pal_mod.measurable(n)
                       else '<span class="badge ok">clears</span>'
                       if pal_mod.clears_the_face(h, skin)
                       else '<span class="badge no">too close</span>'),
            "In the palette": (f"yes &middot; {mine[h.upper()].role}"
                               if h.upper() in mine else "—"),
        } for n, h in rows], numeric=("From his skin",))

    st.markdown('<div class="answer-nav"><a href="./" target="_self">Back to the app</a>'
                '</div>', unsafe_allow_html=True)


def rules_panel(palette: Palette) -> None:
    ui.eyebrow("Which colour goes on which garment")
    if not palette.colours:
        ui.empty("Add some colours first.")
        return
    ui.blurb(
        "The grid is the rule. A colour ticked for Bottom is a trouser colour and "
        "not a shirt colour, which is what makes a seasonal palette a plan rather "
        "than a mood board: four colours are no use if none of them is a trouser."
    )
    with st.form("colour-rules"):
        header = st.columns([3] + [1] * len(COLOUR_CATEGORIES))
        header[0].markdown('<div class="look-cap">Colour</div>', unsafe_allow_html=True)
        for column, category in zip(header[1:], COLOUR_CATEGORIES):
            column.markdown(f'<div class="look-cap">{category}</div>', unsafe_allow_html=True)

        draft: dict[str, list[str]] = {}
        for colour in palette.colours:
            row = st.columns([3] + [1] * len(COLOUR_CATEGORIES))
            row[0].markdown(
                f'<div class="look-cap"><span class="chip" style="background:{colour.hex}">'
                f'</span>{colour.name}</div>', unsafe_allow_html=True)
            picked = []
            for column, category in zip(row[1:], COLOUR_CATEGORIES):
                if column.checkbox(category, value=colour.allows(category),
                                   key=f"rule-{colour.id}-{category}",
                                   label_visibility="collapsed"):
                    picked.append(category)
            draft[colour.id] = picked
        if st.form_submit_button("Save the grid"):
            for colour in palette.colours:
                colour.categories = draft.get(colour.id, [])
            palette.save()
            st.rerun()

    gaps = [c for c, n in pal_mod.coverage(palette).items() if not n]
    if gaps:
        st.info(f"Nothing is allowed on: {', '.join(gaps)}. A palette with no "
                "trouser colour or no shoe colour is not a wardrobe you can dress "
                "out of.")


def item_picker(label: str, options: list[Item], key: str, multi: bool = False):
    """A searchable box over inventory. Streamlit's select boxes filter as you type."""
    ids = [i.id for i in options]
    labels = {i.id: i.label for i in options}
    if multi:
        return st.multiselect(label, ids, default=[], format_func=lambda i: labels[i], key=key)
    chosen = st.selectbox(label, [None, *ids], format_func=lambda i: labels.get(i, "—"), key=key)
    return [chosen] if chosen else []


def checked_look(prompt: str, *, out_prefix, portrait, photos, items,
                 background: str, count: int):
    """Draw the look, have Gemini check it, and correct it until it holds.

    An image model asked for a man in named clothes on white will usually give
    you one and occasionally give you a different man in a kitchen. Nothing
    downstream can tell the difference, so each picture goes back to Gemini with
    the references it was built from and is asked whether the face is his, the
    background is empty, and the garments are the ones photographed.
    """
    wanted = [i.name or i.garment for i in items]
    described = BACKGROUNDS.get(background, background)
    kept, rejected = [], []
    for n in range(int(count)):
        prefix = out_prefix if count == 1 else out_prefix.with_name(f"{out_prefix.name}-{n + 1}")
        picture, history = verify.ensure(
            prompt, out_prefix=prefix, portrait=Path(portrait),
            garment_photos=[Path(x) for x in photos], garments=wanted,
            background=described, settings=Settings.from_env(),
        )
        for attempt in history:
            if attempt.path != picture:
                rejected.append(attempt)
        if picture:
            kept.append(picture)
    return kept, rejected


def report_rejections(rejected, kept_count: int) -> None:
    """Say what was thrown away and why, and let a near miss be kept anyway.

    Discarding every attempt threw away work the user had paid for and left them
    with nothing to look at. Nothing rejected is ever saved automatically, which
    was the point, but a picture that failed on one count out of three is often
    still worth having, and it is his eye that decides that, not the judge's.
    """
    if not rejected:
        return
    st.warning(f"{ui.plural(len(rejected), 'attempt')} rejected and redrawn.")
    for n, attempt in enumerate(rejected, 1):
        held = 3 - len(attempt.report.failures)
        st.markdown(
            f'<div class="look-cap">attempt {n} &middot; {held} of 3 held '
            f'&middot; {attempt.report.summary()}</div>', unsafe_allow_html=True)
    if kept_count:
        return

    st.error("Nothing passed the check, so nothing was saved automatically. The "
             "model kept returning a picture that is not him, not on white, or "
             "not in those clothes.")
    best = min(rejected, key=lambda a: len(a.report.failures))
    st.markdown('<div class="look-cap">The closest attempt, which failed on '
                f'{ui.plural(len(best.report.failures), "count")}:</div>',
                unsafe_allow_html=True)
    ui.plate(best.path, "rejected", width=420)
    st.markdown(
        '<div class="look-cap">Every attempt is on disk under the looks folder, '
        'so nothing is lost. Judge it yourself: the check is strict on purpose '
        'and a shadow it disliked may be one you do not mind.</div>',
        unsafe_allow_html=True)


def generator_tab(profile: Profile, inventory: Inventory, outfits: Outfits,
                  principles: Principles) -> None:
    ui.blurb(
        "Assemble a look from the wardrobe, or invent a piece you do not own yet. "
        "Wanted pieces behave exactly like owned ones here, which is the point: you "
        "can try the coat before you buy it, and the Shopping Guide will later work "
        "out whether it earns its place."
    )

    with st.expander("Invent a piece you do not own"):
        with st.form("quick-aspirational", clear_on_submit=True):
            c1, c2, c3 = st.columns([3, 2, 1])
            name = c1.text_input("Name")
            garment = c2.selectbox("Garment", garments(), key="asp-garment")
            grade = (c3.selectbox("Grade", grades(), key="asp-grade")
                     if takes_grade(garment) else "")
            c4, c6 = st.columns(2)
            colours = c4.multiselect("Colours", colour_names(), key="asp-colour")
            colour_hex = hex_for(colours[0]) if colours else "#CCCCCC"
            fabric = c6.selectbox("Fabric", fabric_options(), key="asp-fabric")
            fit = st.selectbox("Fit", fits(), key="asp-fit") if takes_fit(garment) else ""
            if st.form_submit_button("Add as wanted") and name.strip():
                inventory.add(Item(
                    name=name.strip(), garment=garment, category=inv_mod.category_for(garment),
                    colours=list(colours), colour_hex=colour_hex, grade=grade, fit=fit,
                    fabric="" if fabric == NONE else fabric,
                    status=ASPIRATIONAL,
                ))
                inventory.save()
                st.rerun()

    wearable_items = [i for i in inventory.items if i.status != RETIRED]
    if not wearable_items:
        ui.empty("Nothing to dress him in. Add pieces on the Wardrobe Inventory page first.")
        return

    ui.eyebrow("The pieces")
    picked: list[str] = []
    cols = st.columns(4, gap="medium")
    for col, category in zip(cols, ("Outerwear", "Top", "Bottom", "Shoes")):
        with col:
            options = [i for i in wearable_items if i.category == category]
            picked += item_picker(category, options, f"pick-{category}") if options else []
    accessories = [i for i in wearable_items if i.category == "Accessory"]
    if accessories:
        picked += item_picker("Accessories", accessories, "pick-acc", multi=True)

    items = inventory.resolve(picked)
    if not items:
        ui.empty("Pick at least one piece.")
        return

    shown, dropped = reference_items(items)
    photos = [i.reference_photo for i in shown]
    missing_now = [i for i in items if not i.owned]
    cost_note = (f"{ui.plural(len(missing_now), 'piece')} still to find"
                 if missing_now else "every piece already owned")
    st.markdown(
        f'<div class="look-cap">{len(items)} pieces &middot; '
        f'{ui.plural(len(photos), "photograph")} sent as reference '
        f'&middot; {cost_note}</div>', unsafe_allow_html=True)
    if dropped:
        st.warning(
            f"Too many pieces to show the model at once, so it will not see "
            f"{', '.join(i.name or i.garment for i in dropped)}. Those are "
            "described in words only, and it will invent them.")
    no_picture = [i for i in items if not i.has_reference]
    if no_picture:
        st.info(
            f"No photograph of {', '.join(i.name or i.garment for i in no_picture)}, "
            "so the model is working from the description alone for those.")

    ui.eyebrow("The shot")
    c1, c2, c3 = st.columns([2, 2, 1])
    # The lists are alphabetical, so the sensible default is chosen by name.
    shot = c1.selectbox("Framing", list(SHOTS), key="gen-shot",
                        index=list(SHOTS).index(DEFAULT_SHOT))
    background = c2.selectbox("Background", list(BACKGROUNDS), key="gen-bg",
                              index=list(BACKGROUNDS).index(DEFAULT_BACKGROUND))
    count = c3.number_input("Variations", 1, 4, 1, key="gen-count")
    c4, c5 = st.columns([2, 2])
    name = c4.text_input("Outfit name")
    tag_choice = c5.multiselect("Tags", outfits.all_tags(), key="gen-tags")
    extra = st.text_input("Extra direction")
    use_principles = st.toggle("Apply the principles", value=bool(principles.principles),
                               key="gen-prin")

    prompt = build_outfit_prompt(
        profile, [i.describe() for i in items], shot=shot, background=background,
        principles=principles.as_prompt_block() if use_principles else "",
        photo_count=len(photos), extra=extra,
    )
    with st.expander("Prompt sent to Gemini"):
        st.code(prompt, language=None)

    portrait = profile.photo("neutral")
    if not portrait:
        st.warning("No reference portrait, so nothing to dress.")
        return

    if st.button("Generate look", type="primary"):
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        title = name.strip() or ", ".join(i.name or i.garment for i in items[:3])
        with st.spinner(f"Dressing {profile.subject.name}, then checking it is him…"):
            try:
                # Not `paths`: that name is the module, and binding it here would
                # make it local for the whole function and break paths.looks() above.
                written, rejected = checked_look(
                    prompt,
                    out_prefix=paths.looks() / f"{stamp}-{slug(title)}",
                    portrait=portrait, photos=photos, items=items,
                    background=background, count=int(count),
                )
            except GEMINI_ERRORS as exc:
                st.error(str(exc))
                return
        report_rejections(rejected, len(written))
        if not written:
            return
        made = outfits.add(Outfit(
            name=title, item_ids=[i.id for i in items], tags=list(tag_choice),
            images=[str(w) for w in written], notes=extra, prompt=prompt,
            shot=shot, background=background, extra=extra,
        ))
        outfits.save()
        st.success(f"Saved as “{title}”.")
        st.markdown(f'<div class="look-cap"><a href="?outfit={made.id}" target="_blank">'
                    f'Open it, vary it, compare it &#8599;</a></div>',
                    unsafe_allow_html=True)


# --- 7. outfit gallery --------------------------------------------------------

def gallery_tab(inventory: Inventory, outfits: Outfits) -> None:
    if not outfits.outfits:
        ui.empty("No outfits yet. Build one in the Outfit Generator.")
        return

    loved = outfits.loved()
    all_costs = [wearability(o, inventory) for o in outfits.outfits]
    ui.stats([
        ("Outfits", str(len(outfits.outfits))),
        ("Loved", str(len(loved))),
        ("Wearable now", str(sum(1 for w in all_costs if w.wearable))),
    ])
    ui.blurb(
        "Tag them however you actually think about them. The Shopping Guide only "
        "counts the ones you love, so starring is not decoration: it decides what "
        "gets bought."
    )

    f1, f2, f3, f4 = st.columns([2, 2, 1, 1])
    query = f1.text_input("Search", key="gal-q")
    tags = f2.multiselect("Tags", outfits.all_tags(), key="gal-tags")
    match_all = f3.toggle("Match all tags", key="gal-all")
    loved_only = f4.toggle("Loved only", key="gal-loved")

    found = outfits.filter(tags=tags, loved_only=loved_only, match_all=match_all, query=query)
    if not found:
        ui.empty("Nothing matches that.")
        return
    st.markdown(f'<div class="look-cap">{len(found)} of {len(outfits.outfits)} outfits</div>',
                unsafe_allow_html=True)

    for chunk in (found[i:i + 2] for i in range(0, len(found), 2)):
        for col, outfit in zip(st.columns(2, gap="large"), chunk):
            with col:
                outfit_card(outfit, inventory, outfits)


def outfit_card(outfit: Outfit, inventory: Inventory, outfits: Outfits) -> None:
    cover = outfit.cover()
    if cover:
        ui.plate(Path(cover), outfit.name[:22], width=420)
    else:
        ui.no_plate("no photograph yet")

    w = wearability(outfit, inventory)
    if w.broken:
        badge = '<span class="badge no">broken</span>'
    elif w.wearable:
        badge = '<span class="badge ok">wearable now</span>'
    else:
        badge = f'<span class="badge want">{len(w.missing)} to buy</span>'
    pieces = ", ".join(i.name or i.garment for i in inventory.resolve(outfit.item_ids))
    tag_line = " ".join(f'<span class="badge">{t}</span>' for t in outfit.tags)
    st.markdown(
        f'<div class="item"><div class="top"><div class="nm">{outfit.name}</div>{badge}</div>'
        f'<div class="meta">{pieces}</div>'
        f'<div style="margin-top:.5rem">{tag_line}</div></div>',
        unsafe_allow_html=True,
    )

    if st.button("♥ Loved · counts towards the shopping plan" if outfit.loved
                 else "♡ Love this one", key=f"love-{outfit.id}",
                 type="primary" if outfit.loved else "secondary",
                 use_container_width=True):
        outfit.loved = not outfit.loved
        outfits.update(outfit)
        outfits.save()
        st.rerun()

    with st.expander("Edit"):
        with st.form(f"of-{outfit.id}"):
            outfit.name = st.text_input("Name", outfit.name, key=f"on-{outfit.id}")
            outfit.tags = st.multiselect("Tags", outfits.all_tags(), default=outfit.tags,
                                         key=f"ot-{outfit.id}")
            new_tag = st.text_input("New tag", key=f"nt-{outfit.id}",
                                    )
            outfit.notes = st.text_area("Notes", outfit.notes, height=68, key=f"onote-{outfit.id}")
            s1, s2 = st.columns(2)
            if s1.form_submit_button("Save"):
                if new_tag.strip():
                    outfit.tags = sorted(set(outfit.tags) | {new_tag.strip().lower()})
                outfits.update(outfit)
                outfits.save()
                st.rerun()
            if s2.form_submit_button("Delete"):
                reset_mod.before(f"before deleting the outfit {outfit.name}", "outfits")
                outfits.remove(outfit.id)
                outfits.save()
                st.rerun()

    if w.broken:
        st.markdown(f'<div class="look-cap">Cannot be worn: {w.fault}. Edit it to swap '
                    f'the piece out.</div>', unsafe_allow_html=True)
    if w.missing:
        st.markdown(
            '<div class="look-cap">Missing: ' +
            ", ".join(m.name or m.garment for m in w.missing) + "</div>",
            unsafe_allow_html=True)


# --- shared panels --------------------------------------------------------

def known_sizes_panel(profile: Profile) -> None:
    """His size in each shop, for each garment, and how much it is trusted.

    Organised by the shops his own sourcing plan already names, because a size is
    only worth knowing where he actually shops.
    """
    ui.eyebrow("What size he is, where he shops")
    book = fit_mod.Fittings.load()
    plan, catalogue = sourcing.Plan.load(), retailers.Catalogue.load()
    shops = catalogue.lookup()

    ui.blurb(
        "Filled in the way it is actually learned: by trying something on, or by "
        "reading a shop's own garment measurements against his. A size confirmed in "
        "a changing room outranks anything worked out from a table, and says so."
    )

    if book.fittings:
        ui.table([{
            "Shop": shops[f.retailer].name if f.retailer in shops else f.retailer,
            "Garment": f.garment + (f" · {f.line}" if f.line else ""),
            "Size": f.size_line or "—",
            "Fit": f.fit or "—",
            "How we know": f.confidence,
            "Verdict": f.verdict or "—",
        } for f in sorted(book.fittings,
                          key=lambda f: (f.garment, -fit_mod.CONFIDENCE.index(f.confidence)))])
    else:
        ui.empty("Nothing recorded yet. Start with the shop you buy most from.")

    if not st.toggle("Record a size", key="fit-edit"):
        return

    with st.form("add-fitting", clear_on_submit=True):
        c1, c2 = st.columns(2)
        garment = c1.selectbox("Garment", garments(), key="fit-garment")
        suggested = fit_mod.reference_shops(plan, catalogue, garment)
        options = suggested + [i for i in catalogue.ids() if i not in suggested]
        retailer = c2.selectbox(
            "Shop", options, format_func=lambda i: shops[i].name, key="fit-shop",
            help="The shops your sourcing plan already sends you to for this "
                 "garment come first.")
        line = st.text_input("Which range, if the shop has more than one",
                             key="fit-line")

        st.markdown('<div class="look-cap">The size on the label, in whatever this '
                    'garment is sized as</div>', unsafe_allow_html=True)
        scheme = schemes_for(garment)[0]
        boxes = size_scheme(garment, scheme)
        values: dict[str, str] = {}
        if boxes:
            columns = st.columns(min(len(boxes), 4))
            for n, field in enumerate(boxes):
                column = columns[n % len(columns)]
                values[field.key] = (
                    column.selectbox(field.label, field.options, key=f"fit-{field.key}")
                    if field.options else
                    column.text_input(field.label, key=f"fit-{field.key}"))

        c3, c4, c5 = st.columns(3)
        cut = c3.selectbox("Fit", fits(), key="fit-cut") if takes_fit(garment) else ""
        confidence = c4.selectbox("How we know", fit_mod.CONFIDENCE,
                                  index=len(fit_mod.CONFIDENCE) - 1, key="fit-conf")
        verdict = c5.selectbox("Verdict", ["", *fit_mod.VERDICTS], key="fit-verdict")
        note = st.text_input("Note", key="fit-note")

        if st.form_submit_button("Record it"):
            existing = book.find(retailer, garment)
            if existing:
                book.remove(existing.id)
            book.add(fit_mod.Fitting(
                retailer=retailer, garment=garment, line=line.strip(),
                size={k: v for k, v in values.items() if v and v != "—"},
                fit=cut, confidence=confidence, verdict=verdict, note=note.strip()))
            book.save()
            st.rerun()

    if book.fittings:
        ui.eyebrow("Forget one")
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        chosen = c1.selectbox(
            "Which", [f.id for f in book.fittings],
            format_func=lambda i: f"{book.by_id(i).garment} at "
                                  f"{shops.get(book.by_id(i).retailer, book.by_id(i)).name if book.by_id(i).retailer in shops else book.by_id(i).retailer}",
            key="fit-drop")
        if c2.button("Forget", type="secondary"):
            reset_mod.before("before forgetting a recorded size", "fittings")
            book.remove(chosen)
            book.save()
            st.rerun()


def measurements_panel(profile: Profile) -> None:
    ui.eyebrow("Body measurements")
    body = profile.measurements
    missing = body.missing_critical()
    if missing:
        st.warning(
            "Not measured yet: " + ", ".join(fitspec.LABELS.get(m, m) for m in missing) +
            ". Until then every size target below is derived from height and build, "
            "which is fine for a shortlist and useless for a blazer. Twenty minutes "
            "with a tape measure fixes it permanently."
        )
    ui.blurb(
        "Ten measurements, all of them takeable on yourself with a tape and a mirror. "
        "Thigh, knee and ankle are not asked for; they are derived from your height so "
        "the trouser targets keep their leg opening."
    )
    ui.meter(len(body.measured()), len(fitspec.HOW_TO_MEASURE), "Measured")

    with st.expander("Take the measurements", expanded=bool(missing) and not body.measured()):
        with st.form("measurements"):
            cols = st.columns(3)
            for n, dim in enumerate(fitspec.HOW_TO_MEASURE):
                label = fitspec.LABELS.get(dim, dim.replace("_", " ").title())
                setattr(body, dim, cols[n % 3].number_input(
                    label, 0.0, 300.0, float(getattr(body, dim, 0)), step=0.5,
                    help=fitspec.HOW_TO_MEASURE[dim], key=f"bm-{dim}"))
            if st.form_submit_button("Save measurements"):
                profile.save()
                st.rerun()

    values, estimated = body.resolved(profile.subject.height_cm, profile.subject.build,
                                      profile.subject.arms)
    rows = [{
        "Dimension": fitspec.LABELS.get(k, k.replace("_", " ").title()),
        "Value": f"{v:g} cm",
        "Source": ('<span class="est">estimated</span>' if k in estimated else "measured")
                  + ("" if k in fitspec.HOW_TO_MEASURE else " · derived only"),
    } for k, v in values.items()]
    ui.table(rows, numeric=("Value",))


def size_targets_panel(profile: Profile) -> None:
    ui.eyebrow("Size targets")
    ui.blurb(
        "What the finished garment should measure, not what the body measures. A size "
        "label means nothing across two brands; these numbers mean the same thing "
        "everywhere. Take them into a shop, or send them to an alterations tailor."
    )

    c1, c2, c3 = st.columns(3)
    garment = c1.selectbox("Garment", list(fitspec.EASE), key="sz-garment")
    fit = c2.selectbox("Fit", fitspec.FITS, index=1, key="sz-fit")
    lengths = list(fitspec.LENGTH_RATIOS.get(garment, {}))
    length_style = c3.selectbox("Length", lengths, key="sz-len") if lengths else None

    rise, trouser_break = "Mid", "Quarter break"
    if garment in ("Trousers", "Jeans"):
        c4, c5 = st.columns(2)
        rise = c4.selectbox("Rise", list(fitspec.RISES), index=1, key="sz-rise")
        trouser_break = c5.selectbox("Break", list(fitspec.BREAKS), index=1, key="sz-break")

    targets = fitspec.target_spec(
        garment, profile.measurements, profile.subject.height_cm, fit=fit,
        build=profile.subject.build, arms=profile.subject.arms, length_style=length_style,
        rise=rise, trouser_break=trouser_break,
    )
    rows = [{
        "Dimension": t.label,
        "Target": f'{t.value:g} cm' + (' <span class="est">*</span>' if t.estimated else ""),
        "Derived from": t.note,
    } for t in targets]
    ui.table(rows, numeric=("Target",))
    st.markdown(
        '<div class="look-cap">Full circumference, not the flat measure. '
        '<span class="est">*</span> means the number rests on an estimated body '
        'measurement rather than one off a tape.</div>', unsafe_allow_html=True)


def plan_panel(inventory: Inventory, outfits: Outfits) -> None:
    ui.eyebrow("What to buy next")

    loved = outfits.loved()
    if not loved:
        ui.empty("No loved outfits yet. Love a few in the gallery and the plan will "
                 "build itself from them.")

    c1, c2 = st.columns([1, 3])
    loved_only = c1.toggle("Loved outfits only", value=True, key="sh-loved")
    c2.markdown('<div class="look-cap">Built from the outfits you loved, in the order '
                'that unlocks the most of them per garment found.</div>',
                unsafe_allow_html=True)

    plan = shopping.purchase_plan(outfits, inventory, loved_only=loved_only)
    if plan.broken:
        st.warning(
            f"{ui.plural(len(plan.broken), 'outfit')} left out of the plan because money cannot fix "
            "them: " + "; ".join(f"**{o.name}** ({shopping.wearability(o, inventory).fault})"
                                 for o in plan.broken[:4]) + "."
        )
    if not plan.blocked:
        ui.empty("Every outfit under consideration is already wearable. "
                 "Nothing to buy, which is the best possible answer.")
        return

    ui.stats([
        ("Wearable now", str(len(plan.wearable_now))),
        ("Blocked", str(len(plan.blocked))),
        ("Plan unlocks", str(plan.outfits_unlocked)),
        ("Garments to find", str(plan.to_find)),
    ], brass_first=True)

    for n, step in enumerate(plan.steps, 1):
        pieces = ", ".join(i.name or i.garment for i in step.items)
        unlocked = ", ".join(o.name for o in step.unlocked) or "nothing on its own"
        st.markdown(
            f'<div class="step"><div class="hd"><div><span class="n">{n}</span> '
            f'<span class="pieces">{pieces}</span></div>'
            f'<div class="cost">{ui.plural(step.size, "piece")}</div></div>'
            f'<div class="why">Unlocks: {unlocked}<br>'
            f'{ui.plural(step.cumulative_bought, "garment")} found so far, '
            f'{ui.plural(step.cumulative_unlocked, "outfit")} unlocked</div></div>',
            unsafe_allow_html=True)

    if plan.still_blocked:
        st.info(f"Still blocked: {', '.join(o.name for o in plan.still_blocked)}.")

    with st.expander("How this is worked out"):
        st.markdown(
            "Each blocked outfit gives a *bundle*: the pieces still missing from it. "
            "Each round takes the bundle completing the most outfits per garment, and "
            "any other outfit whose gap is a subset of that bundle unlocks for free. "
            "Repeat until nothing is blocked.\n\n"
            "There is no money in this on purpose. Almost everything comes off a "
            "secondhand listing where the price is unknown until the thing appears, so "
            "a plan ranked on invented prices would rank on fiction. What can be known "
            "is how many garments it asks you to find.\n\n"
            "Scoring one garment at a time looks reasonable and behaves badly: an outfit "
            "missing two pieces is completed by neither alone, so both score zero and the "
            "plan stalls. Bundles avoid that.\n\n"
            "This is greedy weighted set cover, so it is an approximation, not the "
            "provably cheapest plan. Every step shows its own arithmetic so you can "
            "disagree with it."
        )

    ui.eyebrow("Every missing piece, ranked")
    ui.blurb("Independent of purchase order: how many blocked outfits each piece appears "
             "in, and how many it finishes single-handedly.")
    rows = [{
        "Piece": l.item.name or l.item.garment,
        "In blocked outfits": str(l.appearances),
        "Finishes alone": str(l.solo_unlocks),
        "Outfits": ", ".join(l.outfit_names[:4]),
    } for l in plan.leverage]
    ui.table(rows, numeric=("In blocked outfits", "Finishes alone"))

    ui.eyebrow("Star what you will actually buy")
    for l in plan.leverage:
        c1, c2 = st.columns([4, 1], vertical_alignment="center")
        c1.markdown(
            f'<div class="look-cap">{l.item.name or l.item.garment} &middot; '
            f'in {ui.plural(l.appearances, "blocked outfit")}</div>', unsafe_allow_html=True)
        label = "★ Starred" if l.item.starred else "☆ Star"
        if c2.button(label, key=f"star-{l.item.id}",
                     type="primary" if l.item.starred else "secondary"):
            l.item.starred = not l.item.starred
            inventory.update(l.item)
            inventory.save()
            st.rerun()
    starred = sum(1 for l in plan.leverage if l.item.starred)
    if starred:
        st.markdown(f'<div class="look-cap"><b>{starred}</b> starred</div>',
                    unsafe_allow_html=True)


# --- diagnostics --------------------------------------------------------------

def diagnostics_tab() -> None:
    ui.blurb(
        "Where the data lives, what is in it, and how to get it back. Clearing "
        "anything takes a snapshot first, and every snapshot can be put back whole "
        "or in part. The checks are not here: they belong at a terminal, where they "
        "can run against a throwaway copy rather than against this wardrobe. "
        "`uv run wardrobe-check`, or `uv run pytest`."
    )
    where = paths.home().resolve()
    st.markdown(
        f'<div class="look-cap">Data lives in <b>{where}</b>'
        f'{" · scratch directory" if paths.is_scratch() else ""}</div>',
        unsafe_allow_html=True)

    reset_panel()
    snapshots_panel()


def reset_panel() -> None:
    ui.eyebrow("Clear the data")
    here = reset_mod.present()
    if not here:
        ui.empty("Nothing stored. Already back where you started.")
        return

    ui.blurb(
        "Everything selected is copied into a snapshot before it is deleted, so this "
        "is reversible. The subject profile is unticked by default: his height and "
        "skin tone are not test data."
    )
    chosen: list[str] = []
    columns = st.columns(3)
    for n, (key, label) in enumerate(paths.DATA.items()):
        summary = here.get(key)
        with columns[n % 3]:
            ticked = st.checkbox(
                f"{label}" + (f" · {summary}" if summary else " · empty"),
                value=key in paths.DEFAULT_CLEAR and bool(summary),
                disabled=not summary, key=f"clr-{key}")
        if ticked and summary:
            chosen.append(key)

    c1, c2 = st.columns([1, 2])
    confirmed = c1.checkbox("I am sure", key="clr-confirm")
    if c2.button("Clear selected", type="primary", disabled=not (chosen and confirmed)):
        snap, removed = reset_mod.wipe(chosen)
        st.success(
            f"Cleared {', '.join(paths.DATA[k].lower() for k in removed)}. "
            + (f"Snapshot {snap.label} kept, restore it below." if snap else ""))
        st.rerun()
    if chosen and not confirmed:
        st.caption("Tick “I am sure” to enable the button.")


def snapshots_panel() -> None:
    ui.eyebrow("Snapshots")
    taken = reset_mod.snapshots()
    ui.blurb(
        "Nothing in this app deletes without leaving a copy here first. Every "
        "deletion, every restore-to-defaults and every clearing takes one, and says "
        "why it took it. They are targeted: deleting an outfit copies the outfit "
        "list, not the generated images the deletion was never going to touch, which "
        "is why they are kilobytes rather than megabytes. Restoring is itself "
        "snapshotted, so going back to the wrong point is not the end of it."
    )
    if not taken:
        ui.empty("No snapshots yet. One appears the first time anything is deleted.")
        return

    ui.stats([
        ("Snapshots", str(len(taken))),
        ("Store", reset_mod.store_size()),
        ("Oldest", taken[-1].label.split(",")[0]),
    ])
    st.markdown(f'<div class="look-cap">The most recent {reset_mod.KEEP} are kept; '
                f'older ones are dropped as new ones arrive.</div>',
                unsafe_allow_html=True)

    for snap in taken[:20]:
        with st.expander(f"{snap.label}  ·  {snap.reason or 'no reason recorded'}"):
            st.markdown(
                f'<div class="look-cap">{snap.size} &middot; holds {snap.what}</div>',
                unsafe_allow_html=True)
            with st.form(f"snap-{snap.path.name}"):
                wanted = st.multiselect(
                    "Put back", snap.keys, default=snap.keys,
                    format_func=lambda k: paths.DATA.get(k, k),
                    help="Restore the whole snapshot, or only the part you want.")
                c1, c2 = st.columns(2)
                if c1.form_submit_button("Restore"):
                    if not wanted:
                        st.warning("Pick at least one thing to put back.")
                    else:
                        back = reset_mod.restore(snap, list(wanted))
                        st.success("Restored "
                                   + ", ".join(paths.DATA.get(k, k).lower() for k in back)
                                   + ". The state it replaced was snapshotted first.")
                        st.rerun()
                if c2.form_submit_button("Forget this one"):
                    reset_mod.forget(snap)
                    st.rerun()


def body_tab(profile: Profile) -> None:
    ui.blurb(
        "A size is not a fact about a man, it is a fact about a man and a shop. He is "
        "a Uniqlo M, an M&S 38 and a Tyrwhitt 15.5 with a 33 sleeve, and none of those "
        "converts into the others. So this page comes after Where to Buy: the shops "
        "decide the vocabulary, and the measurements only say which word to pick.\n\n"
        "Everything measured here is centimetres. Everything a shop prints is a size. "
        "Confusing the two is most of why clothes do not fit."
    )
    known_sizes_panel(profile)
    measurements_panel(profile)
    size_targets_panel(profile)


# --- 8. where to buy ----------------------------------------------------------

def where_to_buy_tab(inventory: Inventory) -> None:
    plan = sourcing.Plan.load()
    shops = retailers.Catalogue.load()
    ui.blurb(
        "Which shops each kind of garment comes from, and on what terms. A route "
        "states only the constraints it cares about, on three optional axes: grade, "
        "fabric and fit. It matches only if the garment satisfies every one of them, "
        "and where several match, the one stating the most wins. A route stating "
        "nothing is simply the default for its type."
    )

    every = list(garments())
    ui.stats([
        ("Routes", str(len(plan.routes))),
        ("Types covered", f"{len(plan.covered())} of {len(every)}"),
        ("Shops in use", str(len({s for r in plan.routes for s in r.stores}))),
        ("In the catalogue", str(len(shops.retailers))),
    ], brass_first=True)
    st.markdown(
        '<div class="look-cap"><a href="?shops=all" target="_blank">'
        'Open the retailer catalogue &#8599;</a> to add a shop, change what it '
        'sells, or drop one you never use.</div>', unsafe_allow_html=True)

    stranded = [r for r in plan.routes if r.stores and not r.shops(shops)]
    if stranded:
        st.error(
            "These routes name shops that are no longer in the catalogue, so they "
            "point nowhere: "
            + "; ".join(f"**{r.label}**" for r in stranded)
            + ". Give each one a shop that exists, or delete it."
        )

    impossible = [
        r for r in plan.routes
        if (r.grade and not takes_grade(r.garment))
        or (r.fit and not takes_fit(r.garment))
    ]
    if impossible:
        st.error(
            "These routes can never match, because they ask for something the "
            "garment does not carry: "
            + "; ".join(
                f"**{r.label}** wants "
                + " and ".join(
                    f"{axis} on a {r.garment.lower()}"
                    for axis, on in (("a grade", r.grade and not takes_grade(r.garment)),
                                     ("a fit", r.fit and not takes_fit(r.garment))) if on)
                for r in impossible)
            + ". Either give that garment the axis in the Garment Catalogue, or "
              "match the route on something it does carry."
        )

    unrouted = [i for i in inventory.items
                if i.status == ASPIRATIONAL and not sourcing.route_for(i, plan)]
    if unrouted:
        st.warning(
            "On your shopping list with no route: "
            + "; ".join(f"**{i.name or i.garment}** ({i.spec_line() or i.garment})"
                        for i in unrouted)
            + ". Either add a route below, or set the garment's grade and fabric so an "
              "existing one matches it."
        )

    add_route_panel(plan, shops)

    ui.eyebrow("The plan")
    for garment, routes in plan.by_garment().items():
        st.markdown(f'<div class="look-cap">{garment}</div>', unsafe_allow_html=True)
        for route in routes:
            route_editor(plan, route, shops)

    empty_types = plan.uncovered(every)
    if empty_types:
        with st.expander(f"No route at all · {len(empty_types)} garment types"):
            ui.blurb("Not all of these need one. A watch and a pair of sandals can "
                     "reasonably be bought wherever they turn up.")
            st.markdown(f'<div class="look-cap">{", ".join(empty_types)}</div>',
                        unsafe_allow_html=True)

    with st.expander("Start again"):
        ui.blurb("Throws away every edit and reloads the plan the app ships with.")
        if st.button("Restore the default plan", type="secondary"):
            reset_mod.before("before restoring the default sourcing plan", "sourcing")
            plan.restore_defaults()
            st.rerun()


def route_editor(plan: sourcing.Plan, route: sourcing.Route,
                 catalogue: retailers.Catalogue) -> None:
    named = route.where_in(catalogue) if route.stores else "no shop set"
    matched = ", ".join(f"{k.lower()} {v}" for k, v in route.constraints.items()) or "any"
    terms = route.terms or "no conditions"
    with st.expander(f"{route.label or route.garment}  ·  {named}  ·  {matched}"):
        with st.form(f"route-{route.id or route.label}"):
            c1, c2 = st.columns([2, 1])
            route.label = c1.text_input("Name it", route.label, key=f"rl-{route.id}")
            route.garment = c2.selectbox(
                "Garment", garments(),
                index=garments().index(route.garment) if route.garment in garments() else 0,
                key=f"rg-{route.id}")

            book = catalogue.lookup()
            route.stores = st.multiselect(
                "Shops, in the order you would try them", catalogue.ids(),
                default=[s for s in route.stores if s in book],
                format_func=lambda i: f"{book[i].name} · {book[i].kind}",
                key=f"rs-{route.id}")

            st.markdown('<div class="look-cap">Match on, all optional. Leave every one '
                        'blank to make this the default for the garment.</div>',
                        unsafe_allow_html=True)
            m1, m2, m3, m4 = st.columns(4)
            route.grade = m1.selectbox(
                "Grade", grades(), index=grades().index(route.grade) if route.grade in grades() else 0,
                key=f"rgr-{route.id}")
            fabrics = ["", *fabric_options()[1:]]
            route.fabric = m2.selectbox(
                "Exact fabric", fabrics,
                index=fabrics.index(route.fabric) if route.fabric in fabrics else 0,
                key=f"rf-{route.id}")
            families = ["", *vocabulary.current().families()]
            route.family = m3.selectbox(
                "Fabric family", families,
                index=families.index(route.family) if route.family in families else 0,
                key=f"rfam-{route.id}",
                help="One line covering a whole family, so Wool catches flannel, "
                     "worsted and hopsack at once.")
            route.fit = m4.selectbox(
                "Fit", fits(), index=fits().index(route.fit) if route.fit in fits() else 0,
                key=f"rfit-{route.id}")

            t1, t2 = st.columns(2)
            route.condition = t1.text_input("Condition", route.condition,
                                            
                                            key=f"rc-{route.id}")
            route.timing = t2.text_input("Timing", route.timing,
                                         
                                         key=f"rt-{route.id}")
            route.spec = st.text_input("Insist on", route.spec,
                                       
                                       key=f"rsp-{route.id}")
            route.note = st.text_area("Note", route.note, height=68, key=f"rn-{route.id}")

            s1, s2 = st.columns(2)
            if s1.form_submit_button("Save this route"):
                if route.fabric and route.family:
                    st.warning("Set an exact fabric or a family, not both. The family "
                               "was kept.")
                    route.fabric = ""
                plan.save()
                st.rerun()
            if s2.form_submit_button("Delete"):
                reset_mod.before(f"before deleting the route {route.label}", "sourcing")
                plan.remove(route.id)
                plan.save()
                st.rerun()
        st.markdown(f'<div class="look-cap">Currently: {named} · {terms}</div>',
                    unsafe_allow_html=True)


def add_route_panel(plan: sourcing.Plan, catalogue: retailers.Catalogue) -> None:
    with st.expander("Add a route"):
        with st.form("add-route", clear_on_submit=True):
            c1, c2 = st.columns([2, 1])
            label = c1.text_input("Name it")
            garment = c2.selectbox("Garment", garments(), key="ar-garment")
            book = catalogue.lookup()
            stores = st.multiselect(
                "Shops, in the order you would try them", catalogue.ids(),
                format_func=lambda i: f"{book[i].name} · {book[i].kind}",
                key="ar-stores")
            m1, m2, m3, m4 = st.columns(4)
            grade = m1.selectbox("Grade", grades(), key="ar-grade")
            fabric = m2.selectbox("Exact fabric", ["", *fabric_options()[1:]], key="ar-fabric")
            family = m3.selectbox("Fabric family", ["", *vocabulary.current().families()],
                                  key="ar-family")
            fit = m4.selectbox("Fit", fits(), key="ar-fit")
            t1, t2 = st.columns(2)
            condition = t1.text_input("Condition")
            timing = t2.text_input("Timing")
            spec = st.text_input("Insist on")
            note = st.text_area("Note", height=68, key="ar-note")
            if st.form_submit_button("Add route"):
                if not stores:
                    st.warning("Pick at least one shop.")
                elif fabric and family:
                    st.warning("Set an exact fabric or a family, not both.")
                else:
                    plan.add(sourcing.Route(
                        label=label.strip() or garment, garment=garment, stores=list(stores),
                        grade=grade, fabric=fabric, family=family, fit=fit,
                        condition=condition.strip(), timing=timing.strip(),
                        spec=spec.strip(), note=note.strip()))
                    plan.save()
                    st.rerun()


# --- 10. shopping guide --------------------------------------------------------

def shop_tab(profile: Profile, inventory: Inventory, outfits: Outfits,
             principles: Principles) -> None:
    st.markdown(ui.SHOP_CSS, unsafe_allow_html=True)
    plan = sourcing.Plan.load()
    wanted = shop_mod.to_buy(inventory)
    if not wanted:
        ui.empty("Nothing on the list. Mark pieces as wanted in the Wardrobe Inventory, "
                 "or invent them in the Outfit Generator, and they appear here.")
        return

    starred = [i for i in wanted if i.starred]
    rare = [i for i in wanted if i.garment in retailers.RARELY_WORN]
    ui.stats([
        ("To find", str(len(wanted))),
        ("Starred", str(len(starred))),
        ("Look secondhand first", str(len(rare))),
    ], brass_first=True)
    ui.blurb(
        "The garments worn least are looked for secondhand first. A blazer worn "
        "twenty times a year spends most of its life in a wardrobe whether it was "
        "bought new or not, so the resale sites are full of them barely worn. There "
        "are no prices here: almost everything comes off a listing where the price is "
        "unknown until it appears. Open any piece for the cloth, the size to look for, "
        "and where to find it."
    )

    routeless = [i for i in wanted if not sourcing.route_for(i, plan)]
    if routeless:
        st.warning(
            "No route in the sourcing plan for: "
            + ", ".join(f"**{i.name or i.garment}** ({i.garment})" for i in routeless)
            + ". They fall back to the generic ranking until you add a line."
        )
    with st.expander("The sourcing plan"):
        ui.blurb("Where each kind of thing comes from, and on what terms. Routes are "
                 "selected on grade, fabric and fit, each optional. A route states only "
                 "what it cares about and matches only if the garment satisfies all of "
                 "it; the most constrained match wins, so a linen shirt goes to Mango "
                 "and a dress shirt to Tyrwhitt though both are shirts.")
        ui.table([{
            "Route": route.label,
            "Garment": route.garment,
            "Matched on": ", ".join(f"{k.lower()} {v}" for k, v in route.constraints.items())
                          or "any",
            "Where": route.where,
            "Terms": route.terms or "—",
        } for route in plan.routes])

    plan_panel(inventory, outfits)

    ui.eyebrow("The list")
    c1, c2 = st.columns([1, 3])
    only_starred = c1.toggle("Starred only", key="shop-star")
    shown = [i for i in wanted if i.starred] if only_starred else wanted
    missing_art = [i for i in shown if not i.has_product_photo]
    c2.markdown(
        f'<div class="look-cap">{ui.plural(len(shown), "piece")}'
        f'{f" · {len(missing_art)} without a photograph yet" if missing_art else ""}</div>',
        unsafe_allow_html=True)

    if not shown:
        ui.empty("Nothing starred yet. Star the pieces you actually intend to buy.")
        return

    for chunk in (shown[i:i + 2] for i in range(0, len(shown), 2)):
        for column, item in zip(st.columns(2, gap="large"), chunk):
            with column:
                product_card(profile, item, inventory, principles, plan)


def example_link(item: Item, plan: "sourcing.Plan") -> str:
    """The saved example, and whether it is only worth buying reduced.

    The route says which shop a kind of garment comes from. This says which
    garment, which is the part that is hard to hold in your head between one
    browsing session and the next.
    """
    route = sourcing.route_for(item, plan)
    on_sale = item.wait_for_sale or (route and "sale" in (route.timing or "").lower())
    bits = []
    if item.has_link:
        bits.append(f'<a href="{item.link}" target="_blank" rel="noopener">'
                    f'{item.link_host} &#8599;</a>')
    if on_sale:
        bits.append('<span class="sale">only reduced</span>')
    return f'<div class="example">{" ".join(bits)}</div>' if bits else ""


def product_card(profile: Profile, item: Item, inventory: Inventory,
                 principles: Principles, plan: "sourcing.Plan") -> None:
    flag = ("only reduced" if item.wait_for_sale
            else "look secondhand" if item.garment in retailers.RARELY_WORN else "")
    shot = ui.product_shot(Path(item.shop_photo) if item.shop_photo else None, flag)
    sizes = shop_mod.size_line(profile, item)
    detail = " · ".join(b for b in (item.fabric, item.colour_line) if b)
    st.markdown(
        f'<div class="product">{shot}<div class="body">'
        f'<div class="nm">{item.name or item.garment}</div>'
        f'<div class="kind">{item.garment}{" · " + detail if detail else ""}</div>'
        f'<div class="size">{sizes or "no size target for this garment"}</div>'
        f'{example_link(item, plan)}'
        f'<a class="view" href="?item={item.id}" target="_blank">View &#8599;</a>'
        f'</div></div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    if c1.button("★ Starred" if item.starred else "☆ Star", key=f"sstar-{item.id}",
                 type="primary" if item.starred else "secondary",
                 use_container_width=True):
        item.starred = not item.starred
        inventory.update(item)
        inventory.save()
        st.rerun()
    if c2.button("Photograph it" if not item.has_product_photo else "Reshoot",
                 key=f"sshot-{item.id}", type="secondary", use_container_width=True):
        with st.spinner("Photographing…"):
            try:
                shop_mod.refresh(profile, item, inventory,
                                 principles=principles.as_prompt_block(),
                                 photo=True, words=not item.product_copy)
            except GEMINI_ERRORS as exc:
                st.error(str(exc))
                return
        st.rerun()


def _buy_row(suggestion) -> None:
    st.markdown(
        f'<div class="buy"><div class="hd"><div class="who">{suggestion.retailer.name}'
        f' <span class="kind">{suggestion.retailer.kind}</span></div>'
        f'<a href="{suggestion.url}" target="_blank" rel="noopener">Search &#8599;</a>'
        f'</div><div class="why">{suggestion.reason}.<br>'
        f'{suggestion.retailer.note}</div></div>', unsafe_allow_html=True)


def item_view(profile: Profile, item_id: str) -> None:
    """One garment on its own page, in its own browser tab."""
    st.markdown(ui.CSS, unsafe_allow_html=True)
    ui.way_home(home_for("item"), "Garment")
    st.markdown(ui.SHOP_CSS, unsafe_allow_html=True)
    inventory = Inventory.load()
    item = inventory.by_id(item_id)
    if not item:
        st.markdown('<div class="masthead"><h1>Not <em>found</em></h1></div>',
                    unsafe_allow_html=True)
        ui.empty(f"No garment with the id {item_id}.")
        st.markdown('<div class="answer-nav"><a href="./" target="_self">'
                    'Back to the app</a></div>', unsafe_allow_html=True)
        return

    outfits = Outfits.load()
    principles = Principles.load()
    # Loaded once at the top: the example link needs it before the where-to-buy
    # section does, and assigning it lower down leaves it unbound up here.
    catalogue = retailers.Catalogue.load()
    detail = " · ".join(b for b in (item.garment, item.grade, item.fit,
                                    item.fabric, item.colour_line) if b)
    st.markdown(
        f'<div class="masthead"><h1>{item.name or item.garment}</h1>'
        f'<div class="sub">{detail}</div></div>', unsafe_allow_html=True)

    left, right = st.columns([1, 1], gap="large")

    with left:
        flag = "look secondhand" if item.garment in retailers.RARELY_WORN else ""
        st.markdown(f'<div class="product">'
                    f'{ui.product_shot(Path(item.shop_photo) if item.shop_photo else None, flag)}'
                    f'</div>', unsafe_allow_html=True)
        gallery = [p for p in (item.product_photo, item.photo)
                   if p and Path(p).is_file() and p != item.shop_photo]
        if gallery:
            st.markdown('<div class="look-cap">Also on file</div>', unsafe_allow_html=True)
            for column, path in zip(st.columns(len(gallery)), gallery):
                with column:
                    ui.plate(Path(path), width=360)
        c1, c2 = st.columns(2)
        if c1.button("Photograph it" if not item.has_product_photo else "Reshoot",
                     type="secondary", use_container_width=True, key="iv-shot"):
            with st.spinner("Photographing…"):
                try:
                    shop_mod.refresh(profile, item, inventory,
                                     principles=principles.as_prompt_block(),
                                     photo=True, words=False)
                except GEMINI_ERRORS as exc:
                    st.error(str(exc))
                    return
            st.rerun()
        if c2.button("Write the copy" if not item.product_copy else "Rewrite",
                     type="secondary", use_container_width=True, key="iv-copy"):
            with st.spinner("Writing…"):
                try:
                    shop_mod.refresh(profile, item, inventory,
                                     principles=principles.as_prompt_block(),
                                     photo=False, words=True)
                except GEMINI_ERRORS as exc:
                    st.error(str(exc))
                    return
            st.rerun()

    with right:
        ui.stats([
            ("Status", "starred" if item.starred else item.status),
            ("Garment", item.garment),
        ], brass_first=True)
        if item.product_copy:
            st.markdown(f'<div class="guide-body">\n\n{item.product_copy}\n\n</div>',
                        unsafe_allow_html=True)
        else:
            ui.empty("No description yet. Press “Write the copy”.")

        targets = shop_mod.size_targets(profile, item)
        if targets:
            ui.eyebrow("The size to look for")
            ui.table([{
                "Dimension": t.label,
                "Target": f'{t.value:g} cm' + (' <span class="est">*</span>' if t.estimated else ""),
            } for t in targets], numeric=("Target",))
            st.markdown('<div class="look-cap">Finished garment, full circumference, on '
                        'his measurements. <span class="est">*</span> rests on an '
                        'estimated body measurement.</div>', unsafe_allow_html=True)
        if item.size_line():
            st.markdown(f'<div class="look-cap">Label size wanted: {item.size_line()}</div>',
                        unsafe_allow_html=True)
        if item.has_link:
            found = retailers.match_url(item.link, catalogue)
            ui.eyebrow("One online")
            st.markdown(
                f'<div class="buy"><div class="hd">'
                f'<div class="who">{found.name if found else item.link_host}</div>'
                f'<a href="{item.link}" target="_blank" rel="noopener">Open &#8599;</a>'
                f'</div><div class="why">A specific one he found, kept as the example '
                f'of what he is after'
                f'{". Only worth buying reduced." if item.wait_for_sale else "."}'
                f'</div></div>', unsafe_allow_html=True)

    ui.eyebrow("Where to buy it")
    route = sourcing.route_for(item, sourcing.Plan.load())
    if route:
        terms = "".join(
            f'<div class="term"><b>{label}</b> {value}</div>'
            for label, value in (("Condition", route.condition), ("Timing", route.timing),
                                 ("Insist on", route.spec)) if value)
        if item.wait_for_sale:
            terms = ('<div class="term"><b>Only reduced</b> not at full price, '
                     'whatever the route says</div>') + terms
        shops = route.shops(catalogue)
        links = " ".join(
            f'<a href="{shop.url(retailers.query_for(item))}" target="_blank" '
            f'rel="noopener">{shop.name} &#8599;</a>' for shop in shops)
        st.markdown(
            f'<div class="route-card"><div class="hd"><div class="who">{route.where}</div>'
            f'<div class="kind">your plan · {route.label}</div></div>'
            f'<div class="term"><b>Matched on</b> {sourcing.why(item, route)}</div>'
            f'{terms}{f"<div class=why>{route.note}</div>" if route.note else ""}'
            f'<div class="links">{links}</div></div>', unsafe_allow_html=True)
    else:
        st.info(
            f"No line in the sourcing plan matches this {item.garment.lower()}"
            f"{f' ({item.spec_line()})' if item.spec_line() else ''}. Set its grade, "
            "fabric or fit in the inventory, or add a route. Falling back to the "
            "generic ranking below."
        )

    if route:
        with st.expander("Other shops that sell this"):
            ui.blurb("Only if the plan's shops come up empty. Ranked by garment: "
                     "the pieces worn least go to the resale sites first, the ones "
                     "worn constantly are bought new.")
            for suggestion in retailers.suggest(item, limit=6, catalogue=catalogue):
                _buy_row(suggestion)
    else:
        ui.eyebrow("Ranked options")
        ui.blurb(
            "No route covers this one, so these are ranked by garment rather than "
            "chosen. The pieces worn least go to the resale sites first, because "
            "those are the ones that turn up there barely worn; the ones worn "
            "constantly are bought new, because a used one has little life left."
        )
        for suggestion in retailers.suggest(item, limit=8, catalogue=catalogue):
            _buy_row(suggestion)

    ui.eyebrow("How to get it cheaply")
    for tactic in retailers.tactics(item):
        where = f'<div class="w">{tactic.where}</div>' if tactic.where else ""
        st.markdown(
            f'<div class="tactic"><div class="t">{tactic.name}</div>'
            f'<div class="d">{tactic.detail}</div>{where}</div>', unsafe_allow_html=True)

    using = outfits.using(item.id)
    ui.eyebrow("Outfits waiting on it")
    if not using:
        ui.empty("No outfit uses this yet, which is worth a thought before buying it.")
    else:
        for outfit in using:
            state = wearability(outfit, inventory)
            others = [i.name or i.garment for i in inventory.resolve(outfit.item_ids)
                      if i.id != item.id]
            badge = ('<span class="badge ok">this is the last piece</span>'
                     if len(state.missing) == 1 and state.missing[0].id == item.id
                     else f'<span class="badge want">{len(state.missing)} still missing</span>')
            st.markdown(
                f'<div class="step"><div class="hd"><div class="pieces">{outfit.name}'
                f'{" ♥" if outfit.loved else ""}</div>{badge}</div>'
                f'<div class="why">with {", ".join(others) or "nothing else yet"}</div></div>',
                unsafe_allow_html=True)

    st.markdown('<div class="answer-nav"><a href="./" target="_self">Back to the app</a>'
                '</div>', unsafe_allow_html=True)



def main() -> int:
    """Console-script entry point: `uv run wardrobe-app`."""
    import sys

    from streamlit.web import cli as stcli

    sys.argv = ["streamlit", "run", str(Path(__file__).resolve()),
                "--server.port", "8501", "--server.headless", "true"]
    return stcli.main()


if __name__ == "__main__":
    render()
