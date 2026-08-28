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
    checks as check_mod, fitspec, inventory as inv_mod, paths,
    principles as prin_mod, reset as reset_mod, seed as seed_mod, shopping, ui,
)
from wardrobe.gemini_image import GeminiImageError, Settings, generate_images
from wardrobe.gemini_text import GeminiTextError
from wardrobe.inventory import (
    ASPIRATIONAL, CATEGORIES, GARMENTS, NONE, OWNED, RETIRED, STATUSES,
    Inventory, Item, size_scheme,
)
from wardrobe.outfits import Outfit, Outfits, describe_outfit, reference_photos, wearability
from wardrobe.philosophy import Answers, build_guide_prompt, synthesise_guide
from wardrobe.principles import GROUPS, Principle, Principles
from wardrobe.profile import Profile
from wardrobe.prompts import BACKGROUNDS, SHOTS, build_outfit_prompt
from wardrobe.questions import POINTS, SECTIONS, Question, format_points, parse_points

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
        "1 · Style Guide", "2 · Wardrobe Inventory", "3 · Principles",
        "4 · Outfit Generator", "5 · Outfit Gallery", "6 · Shopping Guide",
        "⚙ Diagnostics",
    ])
    with tabs[0]:
        style_guide_tab(profile, answers)
    with tabs[1]:
        inventory_tab(profile, inventory, outfits)
    with tabs[2]:
        principles_tab(profile, answers, principles)
    with tabs[3]:
        generator_tab(profile, inventory, outfits, principles)
    with tabs[4]:
        gallery_tab(inventory, outfits)
    with tabs[5]:
        shopping_tab(profile, inventory, outfits)
    with tabs[6]:
        diagnostics_tab()


def sidebar(profile: Profile, inventory: Inventory, outfits: Outfits) -> None:
    with st.sidebar:
        photo = profile.photo("neutral")
        if photo:
            ui.plate(photo, photo.name, width=380)
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
        row("Measured", f"{len(measured)} of 16" if measured else "none yet"),
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

    ui.eyebrow("The guide")
    total_done, total_all = answers.progress()
    left, right = st.columns([3, 1], gap="large")
    with left:
        if total_done == 0:
            ui.empty("Nothing to build from yet. Answer a few questions above.")
        elif total_done < 8:
            st.warning(f"Only {total_done} answers. The guide will be thin and mostly gaps.")
    with right:
        build = st.button("Build style guide", type="primary", disabled=total_done == 0)

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

    if paths.guide().is_file():
        markdown = paths.guide().read_text()
        when = dt.datetime.fromtimestamp(paths.guide().stat().st_mtime)
        st.markdown(
            f'<div class="look-cap">{paths.guide()} &middot; {when:%d %b %H:%M} '
            f'&middot; {len(markdown.split())} words</div>', unsafe_allow_html=True)
        st.download_button("Download markdown", markdown, paths.guide().name, "text/markdown")
        st.markdown(f'<div class="guide-body">\n\n{markdown}\n\n</div>', unsafe_allow_html=True)


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
    boxes exist, the status decides whether a price is asked for. Inside a
    Streamlit form neither would take effect until submit, so they sit above it.
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
    item.colour = c1.text_input("Colour", item.colour, key=f"{key}-colour",
                                placeholder="chocolate brown")
    item.colour_hex = c2.color_picker("Swatch", item.colour_hex, key=f"{key}-hex")
    item.fabric = c3.text_input("Fabric", item.fabric, key=f"{key}-fabric",
                                placeholder="brushed cotton twill")
    c4, c5 = st.columns([1, 1])
    item.pattern = c4.text_input("Pattern", item.pattern, key=f"{key}-pattern")
    if status == ASPIRATIONAL:
        item.price = c5.number_input(
            "Estimated price £", 0.0, 100000.0, float(item.price), step=10.0,
            key=f"{key}-price",
            help="What you expect to pay. The shopping plan spends this number.")
    else:
        item.price = 0.0

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
    value = shopping.wardrobe_value(inventory)
    ui.stats([
        ("Owned", str(counts[OWNED])),
        ("Wanted", str(counts[ASPIRATIONAL])),
        ("Retired", str(counts[RETIRED])),
        ("Owned value", ui.money(value["owned_value"])),
        ("Wanted value", ui.money(value["wanted_value"])),
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

    for chunk in (found[i:i + 3] for i in range(0, len(found), 3)):
        for col, item in zip(st.columns(3, gap="medium"), chunk):
            with col:
                item_card(item, inventory, outfits)


def item_card(item: Item, inventory: Inventory, outfits: Outfits) -> None:
    if item.has_photo:
        ui.plate(Path(item.photo), width=420)
    else:
        st.markdown(f'<div class="swatch" style="background:{item.colour_hex}"></div>',
                    unsafe_allow_html=True)

    badge = {OWNED: "", ASPIRATIONAL: '<span class="badge want">wanted</span>',
             RETIRED: '<span class="badge">retired</span>'}[item.status]
    detail = " · ".join(b for b in [item.garment, item.colour, item.fabric] if b)
    sizes = item.size_line()
    price = (f'<br><span class="price">{ui.money(item.price)}</span> estimated'
             if item.status == ASPIRATIONAL and item.price else "")
    st.markdown(
        f'<div class="item"><div class="top"><div class="nm">{item.name or item.garment}</div>'
        f'{badge}</div><div class="meta">{detail}'
        f'{"<br>" + sizes if sizes else ""}{price}</div></div>',
        unsafe_allow_html=True,
    )

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
        "dozen lines you hold in your head while putting an outfit together. Every "
        "principle has to be checkable: you should be able to look at an outfit and "
        "say whether it obeys or breaks it. They are fed into every generated look."
    )

    left, right = st.columns([3, 1], gap="large")
    with right:
        count = st.number_input("How many", 6, 20, 12, key="prin-count")
        generate = st.button("Generate principles", type="primary")
    with left:
        if principles.principles:
            st.markdown(f'<div class="look-cap">{len(principles.principles)} principles &middot; '
                        f'{principles.path}</div>', unsafe_allow_html=True)
        else:
            ui.empty("No principles yet. Generate a set from the questionnaire, "
                     "or write them by hand below.")

    if generate:
        guide = paths.guide().read_text() if paths.guide().is_file() else ""
        with st.spinner("Thinking…"):
            try:
                fresh = prin_mod.generate(profile, answers, guide, int(count))
            except (ValueError, *GEMINI_ERRORS) as exc:
                st.error(str(exc))
                return
        principles.principles = []
        for p in fresh:
            principles.add(p)
        principles.save()
        st.rerun()

    for group, group_principles in principles.by_group().items():
        ui.eyebrow(group)
        for p in group_principles:
            c1, c2 = st.columns([9, 1])
            c1.markdown(
                f'<div class="step"><div class="pieces">{p.text}</div>'
                f'<div class="why">{p.reason}</div></div>', unsafe_allow_html=True)
            if c2.button("Drop", key=f"drop-{p.id}", type="secondary"):
                principles.remove(p.id)
                principles.save()
                st.rerun()

    with st.expander("Write one by hand"):
        with st.form("add-principle", clear_on_submit=True):
            text = st.text_input("Instruction", placeholder="Keep volume in one place only.")
            reason = st.text_input("Reason", placeholder="Volume top and bottom reads as swamped.")
            group = st.selectbox("Group", GROUPS)
            if st.form_submit_button("Add principle") and text.strip():
                principles.add(Principle(text=text.strip(), reason=reason.strip(), group=group))
                principles.save()
                st.rerun()


# --- 4. outfit generator ------------------------------------------------------

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
            price = c3.number_input("Estimated price £", 0.0, 100000.0, 0.0, step=10.0,
                                    key="asp-price")
            c4, c5, c6 = st.columns([2, 1, 2])
            colour = c4.text_input("Colour", placeholder="camel")
            colour_hex = c5.color_picker("Swatch", "#C19A6B", key="asp-hex")
            fabric = c6.text_input("Fabric", placeholder="wool melton")
            if st.form_submit_button("Add as wanted") and name.strip():
                inventory.add(Item(
                    name=name.strip(), garment=garment, category=inv_mod.category_for(garment),
                    colour=colour, colour_hex=colour_hex, fabric=fabric,
                    status=ASPIRATIONAL, price=price,
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
    cost_note = (f"{len(missing_now)} piece(s) not owned, "
                 f"{ui.money(sum(i.price for i in missing_now))} to buy"
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
                paths = generate_images(
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
            images=[str(p) for p in paths], notes=extra, prompt=prompt,
        ))
        outfits.save()
        st.success(f"Saved as “{title}”. It is in the Outfit Gallery.")


# --- 5. outfit gallery --------------------------------------------------------

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
        ("To buy, all outfits", ui.money(sum(
            i.price for i in {m.id: m for w in all_costs for m in w.missing}.values()))),
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

    for chunk in (found[i:i + 3] for i in range(0, len(found), 3)):
        for col, outfit in zip(st.columns(3, gap="medium"), chunk):
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
        f'<div class="meta">{pieces}<br>'
        f'<span class="price">{ui.money(w.total)}</span> total &middot; '
        f'owned {ui.money(w.owned_value)} &middot; to buy {ui.money(w.to_buy)}</div>'
        f'<div style="margin-top:.5rem">{tag_line}</div></div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([1, 1])
    if c1.button("♥ Loved" if outfit.loved else "♡ Love", key=f"love-{outfit.id}",
                 type="primary" if outfit.loved else "secondary"):
        outfit.loved = not outfit.loved
        outfits.update(outfit)
        outfits.save()
        st.rerun()

    with c2.expander("Edit"):
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
            ", ".join(f"{m.name} {ui.money(m.price)}" for m in w.missing) + "</div>",
            unsafe_allow_html=True)


# --- 6. shopping guide --------------------------------------------------------

def shopping_tab(profile: Profile, inventory: Inventory, outfits: Outfits) -> None:
    ui.blurb(
        "Two halves. First the sizes, because buying online without finished garment "
        "measurements is a coin toss. Then the plan, worked out from the outfits you "
        "loved rather than from taste."
    )

    measurements_panel(profile)
    size_targets_panel(profile)
    plan_panel(inventory, outfits)


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
    ui.meter(len(body.measured()), 16, "Measured")

    with st.expander("Take the measurements", expanded=bool(missing) and not body.measured()):
        with st.form("measurements"):
            names = [f for f in fitspec.HOW_TO_MEASURE]
            cols = st.columns(3)
            for n, dim in enumerate(names):
                label = fitspec.LABELS.get(dim, dim.replace("_", " ").title())
                setattr(body, dim, cols[n % 3].number_input(
                    label + (" ★" if dim in fitspec.CRITICAL else ""),
                    0.0, 300.0, float(getattr(body, dim, 0)), step=0.5,
                    help=fitspec.HOW_TO_MEASURE[dim], key=f"bm-{dim}"))
            body.shoe_eu = st.number_input("Shoe EU", 0.0, 60.0, float(body.shoe_eu), step=0.5,
                                           key="bm-shoe")
            if st.form_submit_button("Save measurements"):
                profile.save()
                st.rerun()

    values, estimated = body.resolved(profile.subject.height_cm, profile.subject.build)
    rows = [{
        "Dimension": fitspec.LABELS.get(k, k.replace("_", " ").title()),
        "Value": f'{v:g} cm' if k != "shoe_eu" else f"EU {v:g}",
        "Source": '<span class="est">estimated</span>' if k in estimated else "measured",
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
        "Garment, round": f'{t.value:g} cm' + (' <span class="est">*</span>' if t.estimated else ""),
        "Measured flat": f"{t.flat:g} cm" if t.flat else "—",
        "Derived from": t.note,
    } for t in targets]
    ui.table(rows, numeric=("Garment, round", "Measured flat"))
    st.markdown(
        '<div class="look-cap">Round is the full circumference. Flat is what a shop\'s '
        'size chart usually quotes, laid flat and measured across, so it is half the '
        'round figure. <span class="est">*</span> means the number rests on an '
        'estimated body measurement.</div>', unsafe_allow_html=True)


def plan_panel(inventory: Inventory, outfits: Outfits) -> None:
    ui.eyebrow("What to buy next")

    loved = outfits.loved()
    if not loved:
        ui.empty("No loved outfits yet. Love a few in the gallery and the plan will "
                 "build itself from them.")

    c1, c2, c3 = st.columns([1, 1, 2])
    loved_only = c1.toggle("Loved outfits only", value=True, key="sh-loved")
    use_budget = c2.toggle("Cap the budget", key="sh-usebudget")
    budget = c3.number_input("Budget £", 0.0, 100000.0, 1000.0, step=50.0,
                             key="sh-budget") if use_budget else None

    plan = shopping.purchase_plan(outfits, inventory, loved_only=loved_only, budget=budget)
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
        ("Total", ui.money(plan.total_cost)),
        ("Per outfit", ui.money(plan.total_cost / plan.outfits_unlocked)
         if plan.outfits_unlocked else "—"),
    ], brass_first=True)

    for n, step in enumerate(plan.steps, 1):
        pieces = ", ".join(i.name or i.garment for i in step.items)
        unlocked = ", ".join(o.name for o in step.unlocked) or "nothing on its own"
        st.markdown(
            f'<div class="step"><div class="hd"><div><span class="n">{n}</span> '
            f'<span class="pieces">{pieces}</span></div>'
            f'<div class="cost">{ui.money(step.price)}</div></div>'
            f'<div class="why">Unlocks: {unlocked}<br>'
            f'Running total {ui.money(step.cumulative_cost)} for '
            f'{step.cumulative_unlocked} outfit(s), {ui.money(step.cost_per_outfit or 0)} each'
            f'</div></div>', unsafe_allow_html=True)

    if plan.shortfall_items:
        pieces = " + ".join(i.name or i.garment for i in plan.shortfall_items)
        st.info(
            f"Nothing completes an outfit within this budget. The cheapest that would is "
            f"**{pieces}** at {ui.money(plan.shortfall_cost)}, so you are "
            f"{ui.money(plan.shortfall)} short."
        )
    elif plan.skipped_for_budget:
        st.info(f"Out of budget: {', '.join(o.name for o in plan.skipped_for_budget)}.")
    elif plan.still_blocked:
        st.info(f"Still blocked: {', '.join(o.name for o in plan.still_blocked)}.")

    with st.expander("How this is worked out"):
        st.markdown(
            "Each blocked outfit gives a *bundle*: the pieces still missing from it. "
            "Each round takes the bundle with the best outfits-per-pound, and any other "
            "outfit whose gap is a subset of that bundle unlocks for free. Repeat until "
            "nothing is blocked.\n\n"
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
        "Price": ui.money(l.price) if l.price else "—",
        "In blocked outfits": str(l.appearances),
        "Finishes alone": str(l.solo_unlocks),
        "Outfits": ", ".join(l.outfit_names[:4]),
    } for l in plan.leverage]
    ui.table(rows, numeric=("Price", "In blocked outfits", "Finishes alone"))

    ui.eyebrow("Star what you will actually buy")
    starred_total = 0.0
    for l in plan.leverage:
        c1, c2 = st.columns([5, 1])
        c1.markdown(
            f'<div class="look-cap">{l.item.name or l.item.garment} &middot; '
            f'{ui.money(l.price) if l.price else "no price"} &middot; '
            f'in {l.appearances} blocked outfit(s)</div>', unsafe_allow_html=True)
        label = "★ Starred" if l.item.starred else "☆ Star"
        if c2.button(label, key=f"star-{l.item.id}",
                     type="primary" if l.item.starred else "secondary"):
            l.item.starred = not l.item.starred
            inventory.update(l.item)
            inventory.save()
            st.rerun()
        if l.item.starred:
            starred_total += l.price
    if starred_total:
        st.markdown(f'<div class="look-cap">Starred total: '
                    f'<b>{ui.money(starred_total)}</b></div>', unsafe_allow_html=True)


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


def main() -> int:
    """Console-script entry point: `uv run wardrobe-app`."""
    import sys

    from streamlit.web import cli as stcli

    sys.argv = ["streamlit", "run", str(Path(__file__).resolve()),
                "--server.port", "8501", "--server.headless", "true"]
    return stcli.main()


if __name__ == "__main__":
    render()
