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
    retailers,
    shop as shop_mod,
    sourcing,
    checks as check_mod, fitspec, inventory as inv_mod, paths,
    principles as prin_mod, reset as reset_mod, seed as seed_mod, shopping, ui,
)
from wardrobe.gemini_image import GeminiImageError, Settings, generate_images
from wardrobe.gemini_text import GeminiTextError
from wardrobe.inventory import (
    ASPIRATIONAL, CATEGORIES, FABRIC_OPTIONS, FABRICS, FITS, GARMENTS, GRADES,
    NONE, OWNED, RETIRED, STATUSES, Inventory, Item, size_scheme,
)
from wardrobe.outfits import Outfit, Outfits, describe_outfit, reference_photos, wearability
from wardrobe.palette import (
    ACCENT, CATEGORIES as COLOUR_CATEGORIES, COLOUR_NAMES, FIELD, GROUND,
    NAMED_COLOURS, ROLES, SEASONS, Colour, Palette, hex_for,
)
from wardrobe.philosophy import Answers, build_guide_prompt, synthesise_guide
from wardrobe.principles import BATCH, GROUPS, TARGET, Principle, Principles
from wardrobe.profile import Profile
from wardrobe.prompts import BACKGROUNDS, SHOTS, build_outfit_prompt
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

    inventory = Inventory.load()
    outfits = Outfits.load()
    principles = Principles.load()

    sidebar(profile, inventory, outfits)

    st.markdown(
        '<div class="masthead"><h1>Wardrobe <em>Studio</em></h1>'
        '<div class="sub">Work out the style &middot; know the wardrobe &middot; '
        'buy only what unlocks the most</div></div>',
        unsafe_allow_html=True,
    )

    tabs = st.tabs([
        "1 · Style Guide", "2 · Wardrobe Inventory", "3 · Principles", "4 · Colour",
        "5 · Outfit Generator", "6 · Outfit Gallery", "7 · Body Measurements",
        "8 · Where to Buy", "9 · Shopping Guide", "⚙ Diagnostics",
    ])
    with tabs[0]:
        style_guide_tab(profile, answers)
    with tabs[1]:
        inventory_tab(profile, inventory, outfits)
    with tabs[2]:
        principles_tab(profile, answers, principles)
    with tabs[3]:
        colour_tab(profile, Palette.load())
    with tabs[4]:
        generator_tab(profile, inventory, outfits, principles)
    with tabs[5]:
        gallery_tab(inventory, outfits)
    with tabs[6]:
        body_tab(profile)
    with tabs[7]:
        where_to_buy_tab(inventory)
    with tabs[8]:
        shop_tab(profile, inventory, outfits, principles)
    with tabs[9]:
        diagnostics_tab()


def sidebar(profile: Profile, inventory: Inventory, outfits: Outfits) -> None:
    with st.sidebar:
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
        row("Body fat", f"~{s.body_fat_pct}%" if s.body_fat_pct else ""),
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
            s.height_cm = st.number_input("Height (cm)", 120, 230, s.height_cm or 176)
            s.body_fat_pct = st.number_input("Body fat (%)", 0, 50, s.body_fat_pct)
            s.build = st.text_input("Build", s.build)
            s.skin_tone_hex = st.color_picker("Skin", s.skin_tone_hex)
            s.skin_tone = st.text_input("Skin, in words", s.skin_tone)
            s.hair = st.text_input("Hair", s.hair)
            s.facial_hair = st.text_input("Facial hair", s.facial_hair)
            s.eyes = st.text_input("Eyes", s.eyes)
            s.details = st.text_input("Always wears", s.details)
            profile.style.direction = st.text_area("Style direction", profile.style.direction, height=68)
            profile.style.avoid = st.text_area("Avoid", profile.style.avoid, height=68)
            if st.form_submit_button("Save subject"):
                profile.save()
                st.rerun()


def answer_view(profile: Profile, answers: Answers, focus: str) -> None:
    """One saved answer, on its own, in its own browser tab."""
    st.markdown(ui.CSS, unsafe_allow_html=True)
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
                            q.prompt, value=answers.get(q.id), placeholder=q.placeholder,
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
            c1, c2 = st.columns([4, 1])
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


# --- 2. inventory -------------------------------------------------------------

def shape_row(item: Item, key: str) -> tuple[str, str]:
    """Garment and status, chosen outside the form.

    Both change the shape of the form beneath: the garment decides which size
    boxes exist. Inside a Streamlit form that would not take effect until submit,
    so they sit above it.
    """
    c1, c2 = st.columns(2)
    garment = c1.selectbox(
        "Garment", GARMENTS,
        index=GARMENTS.index(item.garment) if item.garment in GARMENTS else 0,
        key=f"{key}-garment")
    status = c2.selectbox(
        "Status", STATUSES, index=STATUSES.index(item.status), key=f"{key}-status",
        help="Wanted pieces behave like owned ones in the generator, and are what "
             "the shopping plan spends money on.")
    return garment, status


def item_fields(item: Item, key: str, garment: str, status: str) -> Item:
    """The shared add/edit form body. Returns the item with form values applied."""
    item.garment = garment
    item.status = status
    item.category = inv_mod.category_for(garment)

    item.name = st.text_input("Name", item.name, key=f"{key}-name",
                              placeholder="Cream camp-collar shirt")
    c1, c2, c3 = st.columns([2, 1, 2])
    options = ["", *COLOUR_NAMES]
    item.colour = c1.selectbox(
        "Colour", options,
        index=options.index(item.colour) if item.colour in options else 0,
        key=f"{key}-colour",
        help="Thirty colours a wardrobe is actually built from. Typed free-hand "
             "this became chocolate, Chocolate and dark brown, which is one colour "
             "wearing three names.")
    item.colour_hex = hex_for(item.colour) if item.colour else item.colour_hex
    c2.markdown(
        f'<div class="look-cap">Swatch</div>'
        f'<div style="height:2.1rem;background:{item.colour_hex};'
        f'border:1px solid var(--line)"></div>'
        f'<div class="look-cap">{item.colour_hex}</div>', unsafe_allow_html=True)
    item.fabric = c3.selectbox(
        "Fabric", FABRIC_OPTIONS,
        index=FABRIC_OPTIONS.index(item.fabric) if item.fabric in FABRIC_OPTIONS else 0,
        key=f"{key}-fabric",
        help="Fixed list on purpose: free text gave three spellings of cotton and "
             "the image model three different shirts.")
    if item.fabric == NONE:
        item.fabric = ""

    # Grade and fit are what let a sourcing route be precise. Without them a
    # heavyweight tee and a plain one are the same garment to the plan.
    g1, g2 = st.columns(2)
    item.grade = g1.selectbox(
        "Grade", GRADES, index=GRADES.index(item.grade) if item.grade in GRADES else 0,
        key=f"{key}-grade",
        help="What kind of thing it is within its type. This is what separates a "
             "heavyweight tee from a plain one when both are T-shirts.")
    item.fit = g2.selectbox(
        "Fit", FITS, index=FITS.index(item.fit) if item.fit in FITS else 0,
        key=f"{key}-fit", help="How it is cut.")
    scheme = size_scheme(garment)
    if scheme:
        st.markdown(f'<div class="look-cap">Sizes, as {garment.lower()} are actually '
                    f'sized</div>', unsafe_allow_html=True)
        cols = st.columns(min(len(scheme), 4))
        for n, field in enumerate(scheme):
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

    with st.expander("Add an item", expanded=not inventory.items):
        garment, status = shape_row(Item(), "new")
        with st.form("add-item", clear_on_submit=True):
            draft = item_fields(Item(), "new", garment, status)
            photo = st.file_uploader("Photo", type=["png", "jpg", "jpeg", "webp"], key="new-photo")
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
                    st.rerun()

    if not inventory.items:
        ui.empty("Nothing in the wardrobe yet. Add the first piece above.")
        return

    ui.eyebrow("The wardrobe")
    f1, f2, f3 = st.columns([2, 1, 1])
    query = f1.text_input("Search", "", key="inv-q", placeholder="brown, linen, Uniqlo…")
    category = f2.selectbox("Category", ["All", *CATEGORIES], key="inv-cat")
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


def item_card(item: Item, inventory: Inventory, outfits: Outfits) -> None:
    """One garment in the grid: its picture, its spec, and a way into its page."""
    st.markdown(ui.SHOP_CSS, unsafe_allow_html=True)
    badge = {OWNED: "", ASPIRATIONAL: "wanted", RETIRED: "retired"}[item.status]
    shot = ui.product_shot(Path(item.shop_photo) if item.shop_photo else None, badge)
    detail = " · ".join(b for b in (item.garment, item.colour, item.fabric) if b)
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

    if not item.shop_photo:
        if st.button("Draw it from the description", key=f"draw-{item.id}",
                     type="secondary", use_container_width=True,
                     help="Generates a catalogue photograph from the colour, cloth and "
                          "description. Upload a real photo instead if you have one."):
            with st.spinner("Drawing…"):
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
            st.caption(f"Worn in {len(used)} outfit(s): "
                       f"{', '.join(o.name for o in used[:3])}"
                       f"{'…' if len(used) > 3 else ''}. Deleting takes it out of them.")
        garment, status = shape_row(item, f"e-{item.id}")
        with st.form(f"edit-{item.id}"):
            edited = item_fields(item, f"e-{item.id}", garment, status)
            new_photo = st.file_uploader("Replace photo", type=["png", "jpg", "jpeg", "webp"],
                                         key=f"ph-{item.id}")
            c1, c2 = st.columns(2)
            save = c1.form_submit_button("Save")
            delete = c2.form_submit_button("Delete")
            if save:
                if new_photo:
                    try:
                        edited.photo = inv_mod.save_photo(edited.id, new_photo)
                    except ValueError as exc:
                        st.warning(str(exc))
                inventory.update(edited)
                inventory.save()
                st.rerun()
            if delete:
                # Cascade, or the outfits keep an id that resolves to nothing and
                # quietly report themselves as wearable.
                if outfits.forget_item(item.id):
                    outfits.save()
                inv_mod.drop_photo(item)
                inventory.remove(item.id)
                inventory.save()
                st.rerun()


# --- 3. principles ------------------------------------------------------------

def principles_tab(profile: Profile, answers: Answers, principles: Principles) -> None:
    ui.blurb(
        "Not the style guide. The guide is a document you read once; these are the "
        f"lines you hold in your head while getting dressed. Aim for about {TARGET}. "
        "Every one has to be checkable: you should be able to look at an outfit and "
        "say whether it obeys or breaks it. They are fed into every generated look."
    )
    ui.meter(len(principles.principles), TARGET, "Kept")

    ideas_panel(profile, answers, principles)
    kept_panel(principles)
    handwrite_panel(principles)


def ideas_panel(profile: Profile, answers: Answers, principles: Principles) -> None:
    ui.eyebrow("Inspiration")
    ui.blurb(
        f"{BATCH} suggestions at a time. Keep the ones that ring true, bin the rest. "
        "Asking for ten in one go gets you four that are true and six that are "
        "padding, and padding in a list this short is worse than a gap. Each round "
        "is told what you have already kept, so it goes somewhere new."
    )
    if st.button(f"Suggest {BATCH} more", type="primary"):
        guide = paths.guide().read_text() if paths.guide().is_file() else ""
        with st.spinner("Thinking…"):
            try:
                st.session_state["principle_ideas"] = prin_mod.generate(
                    profile, answers, guide, BATCH, principles.principles)
            except (ValueError, *GEMINI_ERRORS) as exc:
                st.error(str(exc))
                return
        st.rerun()

    ideas: list[Principle] = st.session_state.get("principle_ideas", [])
    if not ideas:
        st.markdown('<div class="look-cap">No suggestions on the table. '
                    'Generating again replaces whatever is here.</div>',
                    unsafe_allow_html=True)
        return

    for n, idea in enumerate(ideas):
        c1, c2, c3 = st.columns([8, 1, 1])
        c1.markdown(
            f'<div class="step"><div class="pieces">{idea.text}</div>'
            f'<div class="why">{idea.group} &middot; {idea.reason}</div></div>',
            unsafe_allow_html=True)
        if c2.button("Keep", key=f"keep-{n}"):
            principles.add(Principle(text=idea.text, reason=idea.reason, group=idea.group))
            principles.save()
            st.session_state["principle_ideas"] = [i for i in ideas if i is not idea]
            st.rerun()
        if c3.button("Bin", key=f"bin-{n}", type="secondary"):
            st.session_state["principle_ideas"] = [i for i in ideas if i is not idea]
            st.rerun()


def kept_panel(principles: Principles) -> None:
    ui.eyebrow("Kept")
    if not principles.principles:
        ui.empty("Nothing kept yet. Take a suggestion above, or write your own below.")
        return
    for group, group_principles in principles.by_group().items():
        st.markdown(f'<div class="look-cap">{group}</div>', unsafe_allow_html=True)
        for p in group_principles:
            c1, c2 = st.columns([9, 1])
            c1.markdown(
                f'<div class="step"><div class="pieces">{p.text}</div>'
                f'<div class="why">{p.reason}</div></div>', unsafe_allow_html=True)
            if c2.button("Drop", key=f"drop-{p.id}", type="secondary"):
                principles.remove(p.id)
                principles.save()
                st.rerun()


def handwrite_panel(principles: Principles) -> None:
    with st.expander("Write one by hand"):
        with st.form("add-principle", clear_on_submit=True):
            text = st.text_input("Instruction", placeholder="Keep the volume in one place only.")
            reason = st.text_input("Reason", placeholder="Loose on top and below reads as swamped.")
            group = st.selectbox("Group", GROUPS)
            if st.form_submit_button("Add principle") and text.strip():
                principles.add(Principle(text=text.strip(), reason=reason.strip(), group=group))
                principles.save()
                st.rerun()


# --- 4. colour ----------------------------------------------------------------

VERDICT_BADGE = {"harmonious": "ok", "flattering": "ok", "careful": "no"}


def colour_tab(profile: Profile, palette: Palette) -> None:
    skin = profile.subject.skin_tone_hex
    ui.blurb(
        "A palette is not a list of colours, it is a set of roles. Navy is a "
        "different garment as the ground under everything than as the field next to "
        "the face, so every colour carries a role and the garments it is allowed on. "
        "Coordination then stops being taste and becomes two things that can be "
        "measured: how far apart two colours sit in lightness, and where a hue sits "
        f"relative to his skin at {skin}."
    )
    palette_panel(palette, skin)
    season_panel(palette)
    harmony_panel(palette, skin)
    rules_panel(palette)
    combination_panel(palette, skin)


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
        "Start from the catalogue", ["Pick a colour of your own", *COLOUR_NAMES],
        key="pal-pick",
        help="Fifty colours a wardrobe is built from. Or name your own and set "
             "the hex yourself.")
    custom = picked == "Pick a colour of your own"

    with st.form("add-colour", clear_on_submit=True):
        c1, c2 = st.columns([1, 3])
        hex_code = c1.color_picker("Hex", "#26303F" if custom else hex_for(picked),
                                   key="pal-hex")
        name = c2.text_input("Name", "" if custom else picked, key="pal-name",
                             placeholder="Give it a name, whatever you call it")
        c3, c4 = st.columns([1, 2])
        role = c3.selectbox("Role", list(ROLES), key="pal-role",
                            help=" · ".join(f"{k}: {v}" for k, v in ROLES.items()))
        categories = c4.multiselect("Allowed on", COLOUR_CATEGORIES, key="pal-cats",
                                    help="Leave empty to use the role's defaults.")
        seasons = st.multiselect("Seasons", SEASONS, key="pal-seasons",
                                 help="Leave empty for all year round.")
        note = st.text_input("Note", placeholder="Only in flannel, never in cotton",
                             key="pal-note")
        verdict, why = pal_mod.warmth(hex_code, skin)
        st.markdown(
            f'<div class="look-cap"><span class="badge {VERDICT_BADGE[verdict]}">'
            f'{verdict}</span> {why} &middot; reads as {pal_mod.hue_name(hex_code)}, '
            f'lightness {pal_mod.lightness(hex_code):.2f}</div>', unsafe_allow_html=True)
        if st.form_submit_button("Add to palette"):
            chosen = name.strip() or (picked if not custom else
                                      pal_mod.hue_name(hex_code).title())
            palette.add(Colour(name=chosen, hex=hex_code, role=role,
                               categories=list(categories), seasons=list(seasons),
                               note=note.strip()))
            palette.save()
            st.rerun()

    if not palette.colours:
        ui.empty("No colours yet. Pick one above, or steal a harmony below.")
        return

    for role, colours in palette.by_role().items():
        st.markdown(f'<div class="look-cap">{role} &middot; {ROLES[role]}</div>',
                    unsafe_allow_html=True)
        st.markdown(ui.swatch_strip(colours), unsafe_allow_html=True)
        for colour in colours:
            c1, c2 = st.columns([9, 1])
            verdict, why = colour.verdict(skin)
            note_line = f"<br>{colour.note}" if colour.note else ""
            c1.markdown(
                f'<div class="step" style="border-left-color:{colour.hex}">'
                f'<div class="hd"><div class="pieces">'
                f'<span class="chip" style="background:{colour.hex}"></span>'
                f'{colour.name}</div><div class="cost">{colour.hex}</div></div>'
                f'<div class="why"><span class="badge {VERDICT_BADGE[verdict]}">{verdict}</span> '
                f'{why}<br>{colour.family}, lightness {colour.light:.2f} &middot; '
                f'{", ".join(colour.allowed)} &middot; {colour.season_line}'
                f'{note_line}</div></div>',
                unsafe_allow_html=True)
            if c2.button("Drop", key=f"pdrop-{colour.id}", type="secondary"):
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


def colour_catalogue_view(palette: Palette) -> None:
    """Every colour with a name, on its own page."""
    st.markdown(ui.CSS, unsafe_allow_html=True)
    mine = {c.hex.upper(): c for c in palette.colours}
    st.markdown(
        '<div class="masthead"><h1>Colour <em>catalogue</em></h1>'
        f'<div class="sub">{len(COLOUR_NAMES)} named colours &middot; '
        f'{len(palette.colours)} in the palette</div></div>', unsafe_allow_html=True)

    extras = [c for c in palette.colours if c.name not in COLOUR_NAMES]
    if extras:
        ui.eyebrow("Yours, named by you")
        ui.table([{
            "": f'<span class="chip" style="background:{c.hex}"></span>',
            "Name": c.name, "Hex": c.hex, "Reads as": c.family,
            "Role": c.role, "Seasons": c.season_line,
        } for c in extras])

    for group, rows in NAMED_COLOURS.items():
        ui.eyebrow(group)
        st.markdown(
            '<div style="display:flex;border:1px solid var(--line)">'
            + "".join(f'<div style="flex:1;background:{h};height:3.2rem" '
                      f'title="{n} {h}"></div>' for n, h in rows)
            + "</div>", unsafe_allow_html=True)
        ui.table([{
            "": f'<span class="chip" style="background:{h}"></span>',
            "Name": n, "Hex": h, "Reads as": pal_mod.hue_name(h),
            "Lightness": f"{pal_mod.lightness(h):.2f}",
            "In the palette": (f"yes &middot; {mine[h.upper()].role}"
                               if h.upper() in mine else "—"),
        } for n, h in rows], numeric=("Lightness",))

    st.markdown('<div class="answer-nav"><a href="./" target="_self">Back to the app</a>'
                '</div>', unsafe_allow_html=True)


def harmony_panel(palette: Palette, skin: str) -> None:
    ui.eyebrow("Steal a harmony")
    ui.blurb(
        "The wheel put to work. Pick a colour and take its neighbours: analogous "
        "sits either side, complementary is opposite. Chroma and lightness are "
        "pulled back into wearable range on the way out, because a mathematically "
        "perfect complement at full saturation is a traffic cone."
    )
    c1, c2 = st.columns([1, 3])
    base = c1.color_picker("Base", palette.colours[0].hex if palette.colours else "#C19A6B",
                           key="harm-base")
    c2.markdown(f'<div class="look-cap">Neighbours of {base}, reads as '
                f'{pal_mod.hue_name(base)}</div>', unsafe_allow_html=True)

    for scheme, swatches in pal_mod.harmonies(base).items():
        columns = st.columns([2] + [1] * len(swatches) * 2)
        columns[0].markdown(f'<div class="look-cap">{scheme}</div>', unsafe_allow_html=True)
        for n, swatch in enumerate(swatches):
            verdict, _ = pal_mod.warmth(swatch, skin)
            columns[1 + n * 2].markdown(
                f'<div style="background:{swatch};height:2rem;border:1px solid var(--line)" '
                f'title="{swatch} · {verdict}"></div>', unsafe_allow_html=True)
            taken = palette.has(swatch)
            if columns[2 + n * 2].button("In" if taken else "Add",
                                         key=f"harm-{scheme}-{n}", disabled=taken,
                                         type="secondary"):
                palette.add(Colour(name=pal_mod.hue_name(swatch).title(), hex=swatch,
                                   role=ACCENT if pal_mod.chroma(swatch) > 0.4 else GROUND))
                palette.save()
                st.rerun()


def rules_panel(palette: Palette) -> None:
    ui.eyebrow("Which colour goes on which garment")
    if not palette.colours:
        ui.empty("Add some colours first.")
        return
    ui.blurb(
        "The grid is the rule. A colour ticked for Bottom is a trouser colour and "
        "will never be offered as a shirt. This is what stops the combinations "
        "below from proposing cream trousers under a chocolate shirt."
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
        st.info(f"Nothing is allowed on: {', '.join(gaps)}. "
                "Combinations need a colour for Top, Bottom and Shoes at minimum.")


def combination_panel(palette: Palette, skin: str) -> None:
    ui.eyebrow("What actually goes together")
    counts = pal_mod.coverage(palette)
    if not all(counts[c] for c in ("Top", "Bottom", "Shoes")):
        ui.empty("Needs at least one colour allowed on Top, Bottom and Shoes.")
        return

    c1, c2, c3 = st.columns([1, 1, 2])
    season = c1.selectbox("Season", ["All year", *SEASONS], key="comb-season")
    with_coat = c2.toggle("Include a coat", key="comb-coat")
    minimum = c3.slider("Minimum score", 0, 100, 55, step=5, key="comb-min")
    season = "" if season == "All year" else season
    counts = pal_mod.coverage(palette, season)
    if not all(counts[c] for c in ("Top", "Bottom", "Shoes")):
        ui.empty(f"Nothing for {season.lower() or 'that'} in one of the slots. "
                 "Widen the seasons on some colours.")
        return
    total = (counts["Top"] * counts["Bottom"] * counts["Shoes"]
             * (counts["Outerwear"] if with_coat else 1))
    st.markdown(f'<div class="look-cap">{total:,} recipes scored, best first. Every one '
                f'is enumerated, so nothing plausible is missed and nothing implausible '
                f'gets a free pass.</div>', unsafe_allow_html=True)

    found = pal_mod.combinations(palette, with_outerwear=with_coat, skin_hex=skin,
                                 limit=15, minimum=minimum, season=season)
    if not found:
        ui.empty("Nothing clears that score. Lower it, or widen the grid above.")
        return

    for combination in found:
        badge = ("ok" if combination.score >= 80 else
                 "want" if combination.score >= 65 else "no")
        pieces = "".join(
            f'<div style="flex:1"><div style="background:{c.hex};height:3.2rem;'
            f'border:1px solid var(--line)"></div>'
            f'<div class="look-cap">{slot}<br>{c.name}</div></div>'
            for slot, c in combination.pieces.items())
        good = "".join(f"<br>+ {r}" for r in combination.reasons)
        bad = "".join(f"<br>&minus; {f}" for f in combination.faults)
        st.markdown(
            f'<div class="step"><div class="hd"><div class="pieces">'
            f'<span class="badge {badge}">{combination.verdict}</span> '
            f'{combination.name}</div><div class="cost">{combination.score}</div></div>'
            f'<div style="display:flex;gap:.5rem;margin:.7rem 0 .2rem">{pieces}</div>'
            f'<div class="why">{(good + bad).lstrip("<br>")}</div></div>',
            unsafe_allow_html=True)


# --- 5. outfit generator ------------------------------------------------------

def item_picker(label: str, options: list[Item], key: str, multi: bool = False):
    """A searchable box over inventory. Streamlit's select boxes filter as you type."""
    ids = [i.id for i in options]
    labels = {i.id: i.label for i in options}
    if multi:
        return st.multiselect(label, ids, default=[], format_func=lambda i: labels[i], key=key)
    chosen = st.selectbox(label, [None, *ids], format_func=lambda i: labels.get(i, "—"), key=key)
    return [chosen] if chosen else []


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
            name = c1.text_input("Name", placeholder="Camel wool overcoat")
            garment = c2.selectbox("Garment", GARMENTS, key="asp-garment")
            grade = c3.selectbox("Grade", GRADES, key="asp-grade")
            c4, c5, c6 = st.columns([2, 1, 2])
            colour = c4.selectbox("Colour", ["", *COLOUR_NAMES], key="asp-colour")
            colour_hex = hex_for(colour) if colour else "#CCCCCC"
            c5.markdown(f'<div class="look-cap">Swatch</div><div style="height:2.1rem;'
                        f'background:{colour_hex};border:1px solid var(--line)"></div>',
                        unsafe_allow_html=True)
            fabric = c6.selectbox("Fabric", FABRIC_OPTIONS, key="asp-fabric")
            fit = st.selectbox("Fit", FITS, key="asp-fit")
            if st.form_submit_button("Add as wanted") and name.strip():
                inventory.add(Item(
                    name=name.strip(), garment=garment, category=inv_mod.category_for(garment),
                    colour=colour, colour_hex=colour_hex, grade=grade, fit=fit,
                    fabric="" if fabric == NONE else fabric,
                    status=ASPIRATIONAL,
                ))
                inventory.save()
                st.rerun()

    wearable_items = [i for i in inventory.items if i.status != RETIRED]
    if not wearable_items:
        ui.empty("Nothing to dress him in. Add pieces in the Wardrobe Inventory tab first.")
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

    photos = [Path(i.photo) for i in items if i.has_photo]
    missing_now = [i for i in items if not i.owned]
    cost_note = (f"{len(missing_now)} piece(s) still to find"
                 if missing_now else "every piece already owned")
    st.markdown(
        f'<div class="look-cap">{len(items)} pieces &middot; {len(photos)} with photos '
        f'&middot; {cost_note}</div>', unsafe_allow_html=True)

    ui.eyebrow("The shot")
    c1, c2, c3 = st.columns([2, 2, 1])
    shot = c1.selectbox("Framing", list(SHOTS), key="gen-shot")
    background = c2.selectbox("Background", list(BACKGROUNDS), key="gen-bg")
    count = c3.number_input("Variations", 1, 4, 1, key="gen-count")
    c4, c5 = st.columns([2, 2])
    name = c4.text_input("Outfit name", placeholder="Saturday lunch, Fulham Road")
    tag_choice = c5.multiselect("Tags", outfits.all_tags(), key="gen-tags")
    extra = st.text_input("Extra direction", placeholder="Sleeves rolled twice. Overcast daylight.")
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
        with st.spinner(f"Dressing {profile.subject.name}…"):
            try:
                # Not `paths`: that name is the module, and binding it here would
                # make it local for the whole function and break paths.looks() above.
                written = generate_images(
                    prompt,
                    out_prefix=paths.looks() / f"{stamp}-{slug(title)}",
                    reference_images=[portrait, *photos[:4]],
                    count=int(count),
                    settings=Settings.from_env(),
                )
            except GEMINI_ERRORS as exc:
                st.error(str(exc))
                return
        outfits.add(Outfit(
            name=title, item_ids=[i.id for i in items], tags=list(tag_choice),
            images=[str(w) for w in written], notes=extra, prompt=prompt,
        ))
        outfits.save()
        st.success(f"Saved as “{title}”. It is in the Outfit Gallery.")


# --- 6. outfit gallery --------------------------------------------------------

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
    query = f1.text_input("Search", "", key="gal-q")
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
        ui.empty("No image")

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
                                    placeholder="rainy Tuesday")
            outfit.notes = st.text_area("Notes", outfit.notes, height=68, key=f"onote-{outfit.id}")
            s1, s2 = st.columns(2)
            if s1.form_submit_button("Save"):
                if new_tag.strip():
                    outfit.tags = sorted(set(outfit.tags) | {new_tag.strip().lower()})
                outfits.update(outfit)
                outfits.save()
                st.rerun()
            if s2.form_submit_button("Delete"):
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

    values, estimated = body.resolved(profile.subject.height_cm, profile.subject.build)
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
        build=profile.subject.build, length_style=length_style,
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
            f"{len(plan.broken)} outfit(s) left out of the plan because money cannot fix "
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
            f'<div class="cost">{step.size} piece(s)</div></div>'
            f'<div class="why">Unlocks: {unlocked}<br>'
            f'{step.cumulative_bought} garment(s) found so far, '
            f'{step.cumulative_unlocked} outfit(s) unlocked</div></div>',
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
        c1, c2 = st.columns([5, 1])
        c1.markdown(
            f'<div class="look-cap">{l.item.name or l.item.garment} &middot; '
            f'in {l.appearances} blocked outfit(s)</div>', unsafe_allow_html=True)
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
        "Prove it works, fill it with something realistic to play with, then put it "
        "back exactly as it was. Every check runs in a throwaway directory of its own, "
        "so running them cannot touch this wardrobe even if a check is wrong."
    )
    where = paths.home().resolve()
    st.markdown(
        f'<div class="look-cap">Data lives in <b>{where}</b>'
        f'{" · scratch directory" if paths.is_scratch() else ""}</div>',
        unsafe_allow_html=True)

    checks_panel()
    sample_panel()
    reset_panel()
    snapshots_panel()


def checks_panel() -> None:
    ui.eyebrow("Checks")
    offline = [g for g in check_mod.GROUPS if g != check_mod.LIVE]
    c1, c2 = st.columns([3, 1])
    groups = c1.multiselect("Groups", offline, default=offline, key="chk-groups")
    live = c2.toggle("Include live Gemini", key="chk-live",
                     help="Two real calls to Vertex AI: one for text, one for an image. "
                          "Slow, and it costs money.")
    if st.button("Run checks", type="primary"):
        wanted = list(groups) + ([check_mod.LIVE] if live else [])
        with st.spinner("Running…"):
            st.session_state["check_result"] = check_mod.run(wanted, live=live)

    result = st.session_state.get("check_result")
    if not result:
        return

    ui.stats([
        ("Passed", f"{result.passed}/{len(result.checks)}"),
        ("Failed", str(len(result.failed))),
        ("Seconds", f"{result.seconds:g}"),
    ], brass_first=result.ok)
    if result.ok:
        st.success(f"All {len(result.checks)} checks passed.")
    else:
        st.error(f"{len(result.failed)} check(s) failed.")

    for group, group_checks in result.by_group().items():
        rows = [{
            "": '<span class="badge ok">pass</span>' if c.passed
                else '<span class="badge no">fail</span>',
            "Check": c.name,
            "Result": c.detail,
            "Time": f"{c.seconds:.2f}s",
        } for c in group_checks]
        st.markdown(f'<div class="look-cap">{group}</div>', unsafe_allow_html=True)
        ui.table(rows, numeric=("Time",))

    for failure in result.failed:
        with st.expander(f"Traceback · {failure.name}"):
            st.code(failure.trace or failure.detail, language=None)


def sample_panel() -> None:
    ui.eyebrow("Sample data")
    counts = (f"{len(seed_mod.ITEMS)} items, {len(seed_mod.LOOKS)} outfits, "
              f"{len(seed_mod.ANSWERS)} answers, {len(seed_mod.PRINCIPLES)} principles")
    ui.blurb(
        f"Fills the wardrobe with {counts}, arranged so the shopping maths has "
        "something real to chew on: three outfits blocked by the same two garments, "
        "one blocked by a single expensive coat. A snapshot is taken first."
    )
    if st.button("Fill with sample data"):
        reset_mod.snapshot()
        added = seed_mod.seed_all()
        st.success("Added " + ", ".join(f"{v} {k}" for k, v in added.items())
                   + ". A snapshot was taken first.")
        st.rerun()


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
    if not taken:
        ui.empty("No snapshots yet. One is taken automatically before anything is cleared.")
        return
    for snap in taken[:12]:
        c1, c2, c3 = st.columns([4, 1, 1])
        c1.markdown(
            f'<div class="look-cap">{snap.label} &middot; {snap.size} &middot; '
            f'{", ".join(paths.DATA.get(k, k).lower() for k in snap.keys)}</div>',
            unsafe_allow_html=True)
        if c2.button("Restore", key=f"res-{snap.path.name}", type="secondary"):
            restored = reset_mod.restore(snap)
            st.success(f"Restored {len(restored)} item(s) from {snap.label}.")
            st.rerun()
        if c3.button("Delete", key=f"del-{snap.path.name}", type="secondary"):
            reset_mod.forget(snap)
            st.rerun()


# --- 7. body measurements -----------------------------------------------------

def body_tab(profile: Profile) -> None:
    ui.blurb(
        "Two different kinds of number, and confusing them is most of why clothes do "
        "not fit. A **UK size** is what a shop prints on a label: a jacket marked 38, "
        "a shirt with a 15.5 inch collar, a shoe marked 9. It is a name, not a length, "
        "and it means something different in every shop. A **measurement** is what a "
        "tape reads, and in here every one of them is in centimetres, on this tab and "
        "on every product page.\n\nSo: sizes stay in whatever the label says, "
        "measurements are always cm, and the tables below turn the second into the "
        "first. A blazer measuring 106 cm round the chest means the same thing "
        "everywhere; a jacket labelled 38 does not."
    )
    measurements_panel(profile)
    size_targets_panel(profile)


# --- 8. where to buy ----------------------------------------------------------

def where_to_buy_tab(inventory: Inventory) -> None:
    plan = sourcing.Plan.load()
    ui.blurb(
        "Which shops each kind of garment comes from, and on what terms. A route "
        "states only the constraints it cares about, on three optional axes: grade, "
        "fabric and fit. It matches only if the garment satisfies every one of them, "
        "and where several match, the one stating the most wins. A route stating "
        "nothing is simply the default for its type."
    )

    garments = list(GARMENTS)
    ui.stats([
        ("Routes", str(len(plan.routes))),
        ("Types covered", f"{len(plan.covered())} of {len(garments)}"),
        ("Shops in use", str(len({s for r in plan.routes for s in r.stores}))),
    ], brass_first=True)

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

    add_route_panel(plan)

    ui.eyebrow("The plan")
    for garment, routes in plan.by_garment().items():
        st.markdown(f'<div class="look-cap">{garment}</div>', unsafe_allow_html=True)
        for route in routes:
            route_editor(plan, route)

    empty_types = plan.uncovered(garments)
    if empty_types:
        with st.expander(f"No route at all · {len(empty_types)} garment types"):
            ui.blurb("Not all of these need one. A watch and a pair of sandals can "
                     "reasonably be bought wherever they turn up.")
            st.markdown(f'<div class="look-cap">{", ".join(empty_types)}</div>',
                        unsafe_allow_html=True)

    with st.expander("Start again"):
        ui.blurb("Throws away every edit and reloads the plan the app ships with.")
        if st.button("Restore the default plan", type="secondary"):
            plan.restore_defaults()
            st.rerun()


def route_editor(plan: sourcing.Plan, route: sourcing.Route) -> None:
    shops = " or ".join(r.name for r in route.retailers) or "no shop set"
    matched = ", ".join(f"{k.lower()} {v}" for k, v in route.constraints.items()) or "any"
    terms = route.terms or "no conditions"
    with st.expander(f"{route.label or route.garment}  ·  {shops}  ·  {matched}"):
        with st.form(f"route-{route.id or route.label}"):
            c1, c2 = st.columns([2, 1])
            route.label = c1.text_input("Name it", route.label, key=f"rl-{route.id}")
            route.garment = c2.selectbox(
                "Garment", GARMENTS,
                index=GARMENTS.index(route.garment) if route.garment in GARMENTS else 0,
                key=f"rg-{route.id}")

            route.stores = st.multiselect(
                "Shops, in the order you would try them", list(retailers.BY_ID),
                default=[s for s in route.stores if s in retailers.BY_ID],
                format_func=lambda i: f"{retailers.BY_ID[i].name} · {retailers.BY_ID[i].kind}",
                key=f"rs-{route.id}")

            st.markdown('<div class="look-cap">Match on, all optional. Leave every one '
                        'blank to make this the default for the garment.</div>',
                        unsafe_allow_html=True)
            m1, m2, m3, m4 = st.columns(4)
            route.grade = m1.selectbox(
                "Grade", GRADES, index=GRADES.index(route.grade) if route.grade in GRADES else 0,
                key=f"rgr-{route.id}")
            fabrics = ["", *FABRIC_OPTIONS[1:]]
            route.fabric = m2.selectbox(
                "Exact fabric", fabrics,
                index=fabrics.index(route.fabric) if route.fabric in fabrics else 0,
                key=f"rf-{route.id}")
            families = ["", *FABRICS]
            route.family = m3.selectbox(
                "Fabric family", families,
                index=families.index(route.family) if route.family in families else 0,
                key=f"rfam-{route.id}",
                help="One line covering a whole family, so Wool catches flannel, "
                     "worsted and hopsack at once.")
            route.fit = m4.selectbox(
                "Fit", FITS, index=FITS.index(route.fit) if route.fit in FITS else 0,
                key=f"rfit-{route.id}")

            t1, t2 = st.columns(2)
            route.condition = t1.text_input("Condition", route.condition,
                                            placeholder="Very Good condition or above",
                                            key=f"rc-{route.id}")
            route.timing = t2.text_input("Timing", route.timing,
                                         placeholder="wait for the sale",
                                         key=f"rt-{route.id}")
            route.spec = st.text_input("Insist on", route.spec,
                                       placeholder="100% cotton, 200 gsm or heavier",
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
                plan.remove(route.id)
                plan.save()
                st.rerun()
        st.markdown(f'<div class="look-cap">Currently: {shops} · {terms}</div>',
                    unsafe_allow_html=True)


def add_route_panel(plan: sourcing.Plan) -> None:
    with st.expander("Add a route"):
        with st.form("add-route", clear_on_submit=True):
            c1, c2 = st.columns([2, 1])
            label = c1.text_input("Name it", placeholder="Loafers")
            garment = c2.selectbox("Garment", GARMENTS, key="ar-garment")
            stores = st.multiselect(
                "Shops, in the order you would try them", list(retailers.BY_ID),
                format_func=lambda i: f"{retailers.BY_ID[i].name} · {retailers.BY_ID[i].kind}",
                key="ar-stores")
            m1, m2, m3, m4 = st.columns(4)
            grade = m1.selectbox("Grade", GRADES, key="ar-grade")
            fabric = m2.selectbox("Exact fabric", ["", *FABRIC_OPTIONS[1:]], key="ar-fabric")
            family = m3.selectbox("Fabric family", ["", *FABRICS], key="ar-family")
            fit = m4.selectbox("Fit", FITS, key="ar-fit")
            t1, t2 = st.columns(2)
            condition = t1.text_input("Condition", placeholder="Very Good condition or above")
            timing = t2.text_input("Timing", placeholder="wait for the sale")
            spec = st.text_input("Insist on", placeholder="Goodyear welted")
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


# --- 9. shopping guide --------------------------------------------------------

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
        f'<div class="look-cap">{len(shown)} piece(s)'
        f'{f" · {len(missing_art)} without a photograph yet" if missing_art else ""}</div>',
        unsafe_allow_html=True)

    if not shown:
        ui.empty("Nothing starred yet. Star the pieces you actually intend to buy.")
        return

    for chunk in (shown[i:i + 2] for i in range(0, len(shown), 2)):
        for column, item in zip(st.columns(2, gap="large"), chunk):
            with column:
                product_card(profile, item, inventory, principles, plan)


def product_card(profile: Profile, item: Item, inventory: Inventory,
                 principles: Principles, plan: "sourcing.Plan") -> None:
    flag = "look secondhand" if item.garment in retailers.RARELY_WORN else ""
    shot = ui.product_shot(Path(item.shop_photo) if item.shop_photo else None, flag)
    sizes = shop_mod.size_line(profile, item)
    detail = " · ".join(b for b in (item.fabric, item.colour) if b)
    st.markdown(
        f'<div class="product">{shot}<div class="body">'
        f'<div class="nm">{item.name or item.garment}</div>'
        f'<div class="kind">{item.garment}{" · " + detail if detail else ""}</div>'
        f'<div class="size">{sizes or "no size target for this garment"}</div>'
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


def item_view(profile: Profile, item_id: str) -> None:
    """One garment on its own page, in its own browser tab."""
    st.markdown(ui.CSS, unsafe_allow_html=True)
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
    detail = " · ".join(b for b in (item.garment, item.grade, item.fit,
                                    item.fabric, item.colour) if b)
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

    ui.eyebrow("Where to buy it")
    route = sourcing.route_for(item, sourcing.Plan.load())
    if route:
        terms = "".join(
            f'<div class="term"><b>{label}</b> {value}</div>'
            for label, value in (("Condition", route.condition), ("Timing", route.timing),
                                 ("Insist on", route.spec)) if value)
        links = " ".join(
            f'<a href="{shop.url(retailers.query_for(item))}" target="_blank" '
            f'rel="noopener">{shop.name} &#8599;</a>' for shop in route.retailers)
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

    ui.eyebrow("Other options" if route else "Ranked options")
    ui.blurb(
        "Ranked for this garment. The pieces worn least go to the resale sites first, "
        "because those are the ones that turn up there barely worn; the ones worn "
        "constantly are bought new, because a used one has little life left in it."
    )
    for suggestion in retailers.suggest(item, limit=8):
        st.markdown(
            f'<div class="buy"><div class="hd"><div class="who">{suggestion.retailer.name}'
            f' <span class="kind">{suggestion.retailer.kind}</span></div>'
            f'<a href="{suggestion.url}" target="_blank" rel="noopener">Search &#8599;</a></div>'
            f'<div class="why">{suggestion.reason}.<br>{suggestion.retailer.note}</div></div>',
            unsafe_allow_html=True)

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
