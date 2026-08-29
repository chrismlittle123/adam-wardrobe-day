"""The test suite, runnable from the app as well as from pytest.

Every check runs inside a throwaway WARDROBE_HOME, so running the whole suite
cannot touch the real wardrobe even if a check is wrong. The live group is the
exception worth knowing about: it calls Vertex AI for real, costs money, and is
off unless asked for.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
import time
import traceback
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

APP_FILE = Path(__file__).with_name("app.py")

DATA, FIT, INVENTORY, QUESTIONS, COLOUR, MATHS, SHOP, PROMPTS, APP, LIVE = (
    "Data", "Fit engine", "Inventory", "Questionnaire", "Colour",
    "Shopping maths", "Shop", "Prompts", "App", "Live Gemini",
)
GROUPS: tuple[str, ...] = (DATA, FIT, INVENTORY, QUESTIONS, COLOUR, MATHS, SHOP,
                           PROMPTS, APP, LIVE)


@dataclass
class Check:
    name: str
    group: str
    passed: bool = False
    detail: str = ""
    seconds: float = 0.0
    trace: str = ""


@dataclass
class Result:
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    @property
    def ok(self) -> bool:
        return not self.failed

    @property
    def seconds(self) -> float:
        return round(sum(c.seconds for c in self.checks), 2)

    def by_group(self) -> dict[str, list[Check]]:
        out: dict[str, list[Check]] = {}
        for check in self.checks:
            out.setdefault(check.group, []).append(check)
        return out


@contextlib.contextmanager
def scratch_home(seed_profile: bool = True) -> Iterator[Path]:
    """A disposable WARDROBE_HOME. The real subject profile is copied in so the
    checks run against his actual proportions rather than invented ones."""
    previous = os.environ.get(paths.ENV_VAR)
    directory = Path(tempfile.mkdtemp(prefix="wardrobe-check-"))
    os.environ[paths.ENV_VAR] = str(directory)
    try:
        real_profile = Path(previous or ".") / "profile.toml"
        if seed_profile and real_profile.is_file():
            shutil.copy(real_profile, directory / "profile.toml")
        yield directory
    finally:
        if previous is None:
            os.environ.pop(paths.ENV_VAR, None)
        else:
            os.environ[paths.ENV_VAR] = previous
        shutil.rmtree(directory, ignore_errors=True)


def _near(a: float, b: float, tolerance: float = 0.05) -> bool:
    return abs(a - b) <= tolerance


# --- Data ---------------------------------------------------------------------

def check_paths_isolated() -> str:
    for key in paths.DATA:
        target = paths.resolve(key)
        assert paths.home() in target.parents or target.parent == paths.home() or \
            str(target).startswith(str(paths.home())), f"{key} escapes the home directory"
    return f"{len(paths.DATA)} paths, all under {paths.home().name}"


def check_profile_round_trip() -> str:
    from .profile import Profile
    p = Profile.load()
    assert p.subject.height_cm, "no height on the subject"
    assert p.subject.height_metric == f"{p.subject.height_cm / 100:.2f} m"
    p.subject.name, p.measurements.chest = "Round Trip", 97.5
    p.save()
    again = Profile.load()
    assert again.subject.name == "Round Trip"
    assert again.measurements.chest == 97.5, "measurement lost on save"
    return f"{again.subject.height_metric}, chest survived the write"


def check_answers_round_trip() -> str:
    from .philosophy import Answers
    a = Answers.load()
    a.values["says_what"] = "  padded  "
    a.values["blank"] = "   "
    a.save()
    again = Answers.load()
    assert again.get("says_what") == "padded", "whitespace not trimmed"
    assert "blank" not in again.values, "empty answer was kept"
    return f"{len(again.values)} stored, blanks dropped"


def check_inventory_round_trip() -> str:
    from .inventory import Inventory, Item
    inv = Inventory.load()
    item = inv.add(Item(name="Test blazer", garment="Blazer",
                        sizes={"chest": '38"', "length": "Regular"}, price=0))
    inv.save()
    again = Inventory.load()
    back = again.by_id(item.id)
    assert back and back.sizes == {"chest": '38"', "length": "Regular"}, "sizes lost"
    assert again.unique_id("Test blazer") == "test-blazer-2", "id collision not handled"
    return f"sizes survived, id {back.id}"


def check_outfits_round_trip() -> str:
    from .outfits import Outfit, Outfits
    o = Outfits.load()
    fit = o.add(Outfit(name="Test look", item_ids=["a", "b"], tags=["work"], loved=True))
    o.save()
    again = Outfits.load()
    back = again.by_id(fit.id)
    assert back and back.loved and back.tags == ["work"], "outfit fields lost"
    assert back.created, "no created timestamp"
    return f"{back.id}, tagged and loved"


def check_principles_round_trip() -> str:
    from .principles import Principle, Principles, parse
    p = Principles.load()
    p.add(Principle(text="Keep volume in one place.", reason="Because.", group="Silhouette"))
    p.save()
    assert len(Principles.load().principles) == 1
    parsed = parse("- Colour | Two bases, one accent. | Everything combines.\nnoise line")
    assert len(parsed) == 1 and parsed[0].group == "Colour", "parser took the noise line"
    return "stored and parsed, noise ignored"


# --- Fit engine ---------------------------------------------------------------

def check_body_measurement_set() -> str:
    """Exactly the ten a man can take on himself, plus the three derived for him."""
    from .fitspec import CRITICAL, HOW_TO_MEASURE, Body, LABELS
    wanted = {"chest", "waist", "shoulder", "bicep", "wrist", "sleeve",
              "inseam", "outseam", "hip", "neck"}
    fields = set(Body().__dataclass_fields__)
    assert fields == wanted, f"body fields drifted: {fields ^ wanted}"
    assert set(HOW_TO_MEASURE) == wanted, "the form asks for a different set"
    assert set(CRITICAL) == wanted, "critical set drifted"
    assert "seat" not in fields and LABELS["hip"] == "Hip", "seat was not renamed to hip"
    assert all(HOW_TO_MEASURE[k].strip() for k in wanted), "a measurement has no instructions"

    values, estimated = Body(chest=96.8).resolved(176, "lean athletic")
    for derived in ("thigh", "knee", "ankle"):
        assert derived in values and derived in estimated, f"{derived} not derived"
    assert "chest" not in estimated, "a measured value was marked estimated"
    return f"{len(wanted)} measured, {len(values) - len(wanted)} derived, hip not seat"


def check_body_estimate() -> str:
    from .fitspec import estimate
    body = estimate(176, "very lean and athletic")
    assert 90 <= body["chest"] <= 100, f"chest estimate off: {body['chest']}"
    assert 70 <= body["waist"] <= 82, f"waist estimate off: {body['waist']}"
    assert body["waist"] < body["chest"], "waist not smaller than chest"
    assert 42 <= body["shoulder"] <= 48, f"shoulder off: {body['shoulder']}"
    assert 75 <= body["inseam"] <= 85, f"inseam off: {body['inseam']}"
    assert 88 <= body["hip"] <= 100, f"hip off: {body['hip']}"
    return f"chest {body['chest']}, waist {body['waist']}, hip {body['hip']}, inseam {body['inseam']}"


def check_ease_applied() -> str:
    from .fitspec import Body, EASE, target_spec
    body = Body(chest=96, waist=78, shoulder=45, sleeve=61, inseam=80, hip=94, neck=38)
    targets = {t.key: t for t in target_spec("Shirt", body, 176, fit="Regular")}
    expected = 96 + EASE["Shirt"]["Regular"]["chest"]
    assert _near(targets["chest"].value, expected), \
        f"shirt chest {targets['chest'].value} != body 96 + ease {EASE['Shirt']['Regular']['chest']}"
    assert not targets["chest"].estimated, "measured chest marked as estimated"
    return f"shirt chest {targets['chest'].value} = 96 + {EASE['Shirt']['Regular']['chest']}"


def check_cuff_allowance() -> str:
    from .fitspec import Body, target_spec
    body = Body(chest=96, waist=78, shoulder=45, sleeve=61, hip=94)
    blazer = {t.key: t.value for t in target_spec("Blazer", body, 176)}
    shirt = {t.key: t.value for t in target_spec("Shirt", body, 176)}
    assert blazer["sleeve"] < shirt["sleeve"], "blazer sleeve not shortened for cuff"
    assert _near(shirt["sleeve"] - blazer["sleeve"], 1.5), "cuff allowance is not 1.5 cm"
    return f"blazer {blazer['sleeve']} vs shirt {shirt['sleeve']}, 1.5 cm of cuff"


def check_break_and_flat() -> str:
    from .fitspec import Body, target_spec
    body = Body(inseam=80, waist=78, hip=94)
    no_break = {t.key: t.value for t in target_spec("Trousers", body, 176, trouser_break="No break")}
    full = {t.key: t.value for t in target_spec("Trousers", body, 176, trouser_break="Full break")}
    assert full["inseam"] > no_break["inseam"], "break does not lengthen the inseam"
    assert _near(full["inseam"] - no_break["inseam"], 6.0), "break range wrong"
    chest = next(t for t in target_spec("Shirt", body, 176) if t.key == "chest")
    assert _near(chest.flat, chest.value / 2), "flat is not half the round measure"
    return f"no break {no_break['inseam']}, full {full['inseam']}; flat = round / 2"


def check_build_matching() -> str:
    """A build reading "very lean and athletic" must not be treated as plain lean.

    The two rows differ by 3 cm of chest, which is most of a jacket size.
    """
    from .fitspec import BUILD_FACTORS, _build_key, estimate
    assert _build_key("very lean and athletic, narrow waist") == "lean athletic", \
        "'lean and athletic' fell through to a single-word row"
    assert _build_key("lean") == "lean" and _build_key("athletic") == "athletic"
    assert _build_key("solid") == "solid" and _build_key("") == "athletic"
    for key in ("lean", "lean athletic", "athletic", "average", "solid"):
        assert key in BUILD_FACTORS, f"{key} has no factors"
    both = estimate(176, "very lean and athletic")
    just_lean = estimate(176, "lean")
    assert both["chest"] > just_lean["chest"], "athletic chest not applied"
    assert _near(both["waist"], just_lean["waist"]), "lean waist not applied"
    return f"lean-athletic chest {both['chest']} with a lean waist {both['waist']}"


def check_estimated_flag() -> str:
    from .fitspec import Body, target_spec
    body = Body(chest=96)   # chest measured, everything else not
    targets = {t.key: t for t in target_spec("Shirt", body, 176)}
    assert not targets["chest"].estimated, "measured chest flagged as estimated"
    assert targets["waist"].estimated, "unmeasured waist not flagged"
    return "measured and estimated told apart correctly"


# --- Inventory ----------------------------------------------------------------

def check_pattern_removed() -> str:
    from .inventory import Item
    assert "pattern" not in Item().__dataclass_fields__, "the pattern field is back"
    described = Item(name="X", colour="olive", fabric="linen", garment="Overshirt").describe()
    assert described == "olive linen overshirt", f"describe() changed shape: {described!r}"
    return f"no pattern field; describe() gives {described!r}"


def check_fabric_list() -> str:
    """Fabric is a fixed list, and the sample data uses names from it."""
    from .inventory import FABRICS, FABRIC_OPTIONS, NONE, fabric_family
    from .seed import ITEMS
    flat = [f for group in FABRICS.values() for f in group]
    assert len(flat) == len(set(flat)), "a fabric appears in two families"
    assert FABRIC_OPTIONS[0] == NONE, "no blank option"
    assert list(FABRIC_OPTIONS[1:]) == sorted(FABRIC_OPTIONS[1:]), "fabrics not alphabetical"
    assert len(FABRIC_OPTIONS) > 30, "the list is too thin to cover a wardrobe"
    assert fabric_family("Wool flannel") == "Wool", "family lookup broken"
    unknown = [row[4] for row in ITEMS if row[4] and row[4] not in FABRIC_OPTIONS]
    assert not unknown, f"sample data uses fabrics not on the list: {unknown}"
    return f"{len(flat)} fabrics across {len(FABRICS)} families, sample data conforms"


def check_alphabetical() -> str:
    from .inventory import CATEGORIES, GARMENTS
    assert list(GARMENTS) == sorted(GARMENTS), "garments not alphabetical"
    assert list(CATEGORIES) == sorted(CATEGORIES), "categories not alphabetical"
    for name, group in CATEGORIES.items():
        assert list(group) == sorted(group), f"{name} not alphabetical"
    return f"{len(GARMENTS)} garments, {len(CATEGORIES)} categories, all sorted"


def check_size_schemes() -> str:
    from .inventory import GARMENTS, size_scheme
    keyed = {}
    for garment in GARMENTS:
        scheme = size_scheme(garment)
        keys = [f.key for f in scheme]
        assert len(keys) == len(set(keys)), f"{garment} has duplicate size keys"
        keyed[garment] = keys
    assert "collar" in keyed["Shirt"], "a shirt is sized by its collar"
    assert "chest" in keyed["Blazer"] and "length" in keyed["Blazer"], "blazer needs chest and length"
    assert {"waist", "leg"} <= set(keyed["Trousers"]), "trousers need waist and leg"
    assert {"uk", "eu", "us"} <= set(keyed["Loafers"]), "shoes need all three systems"
    assert keyed["Bag"] == [], "a bag has no size"
    return "shirt/blazer/trouser/shoe schemes all distinct"


def check_trouser_spec_survives_derived() -> str:
    """Not asking for thigh, knee and ankle must not cost the trouser its leg opening."""
    from .fitspec import Body, target_spec
    targets = {t.key: t for t in target_spec("Trousers", Body(waist=78, hip=94, inseam=80), 176)}
    for key in ("waist", "hip", "thigh", "knee", "ankle", "rise", "inseam", "outseam"):
        assert key in targets, f"trouser spec lost {key}"
    assert not targets["waist"].estimated and targets["ankle"].estimated, \
        "measured and derived not distinguished"
    assert targets["ankle"].value > 0, "leg opening came out empty"
    return f"leg opening {targets['ankle'].value} cm, derived, spec complete"


def check_size_pruning() -> str:
    """Re-classifying a garment must not leave the old scheme's sizes behind."""
    from .inventory import Inventory, Item
    inventory = Inventory.load()
    item = inventory.add(Item(name="Was a shirt", garment="Shirt",
                              sizes={"collar": '15.5"', "alpha": "M", "cut": "—"}))
    inventory.save()
    assert "cut" not in Inventory.load().by_id(item.id).sizes, "placeholder value kept"

    item.garment = "Trousers"
    item.sizes["waist"] = '31"'
    inventory.update(item)
    inventory.save()
    after = Inventory.load().by_id(item.id)
    assert "collar" not in after.sizes, f"stale shirt sizes survived: {after.sizes}"
    assert after.sizes.get("waist") == '31"', "the new size was lost"
    return f"collar dropped on re-classification, left with {after.sizes}"


def check_photo_limits() -> str:
    """Uploads are bounded and re-encoded, or a phone photo ends up in the repo."""
    import io as _io

    from PIL import Image

    from .inventory import MAX_UPLOAD_BYTES, save_photo

    class Upload:
        def __init__(self, name, data):
            self.name, self._data = name, data

        def getvalue(self):
            return self._data

    buffer = _io.BytesIO()
    Image.new("RGB", (4000, 3000), (200, 120, 90)).save(buffer, "PNG")
    stored = Path(save_photo("huge", Upload("huge.png", buffer.getvalue())))
    assert stored.is_file(), "nothing written"
    assert stored.stat().st_size < 1_000_000, \
        f"stored photo is {stored.stat().st_size / 1024:.0f} KB, not downscaled"
    with Image.open(stored) as written:
        assert max(written.size) <= 1600, f"not resized: {written.size}"

    try:
        save_photo("bomb", Upload("bomb.png", b"\x89PNG" + b"\x00" * (MAX_UPLOAD_BYTES + 1)))
    except ValueError as exc:
        assert "limit" in str(exc).lower(), f"unhelpful refusal: {exc}"
    else:
        raise AssertionError("an oversized upload was accepted")

    try:
        save_photo("junk", Upload("junk.png", b"this is not an image"))
    except ValueError:
        pass
    else:
        raise AssertionError("a non-image was accepted")
    return f"4000px re-encoded to {stored.stat().st_size // 1024} KB; oversize and junk refused"


def check_size_line_and_category() -> str:
    from .inventory import Item, category_for
    item = Item(garment="Blazer", sizes={"chest": '38"', "length": "Regular", "cut": "—",
                                          "bogus": "x"})
    line = item.size_line()
    assert "Chest 38" in line and "Regular" in line, "size line missing real values"
    assert "—" not in line and "bogus" not in line, "size line shows placeholders or junk"
    assert category_for("Blazer") == "Outerwear" and category_for("Loafers") == "Shoes"
    return line


# --- Questionnaire ------------------------------------------------------------

def check_principles_batching() -> str:
    """Suggestions come five at a time and are told what is already kept."""
    from .philosophy import Answers
    from .principles import BATCH, TARGET, Principle, build_prompt
    from .profile import Profile
    from .seed import seed_answers
    assert BATCH == 5 and TARGET == 10, f"batch/target drifted: {BATCH}/{TARGET}"
    kept = [Principle(text="Keep the volume in one place.", reason="Because.", group="Silhouette")]
    prompt = build_prompt(Profile.load(), seed_answers(), "", BATCH, kept)
    assert "exactly 5" in prompt, "the batch size never reaches the model"
    assert "Keep the volume in one place." in prompt, "kept principles not sent"
    assert "Do not repeat any of these" in prompt, "no instruction to avoid repeats"
    assert "suggestions, not a finished set" in prompt, "framed as a finished set"
    fresh = build_prompt(Profile.load(), seed_answers(), "", BATCH, [])
    assert "already kept" not in fresh, "empty kept list still sends a block"
    return f"{BATCH} at a time towards {TARGET}, previous keeps excluded"


def check_question_bank() -> str:
    from .questions import ALL_QUESTIONS, SECTIONS
    ids = [q.id for q in ALL_QUESTIONS]
    assert len(ids) == len(set(ids)), "duplicate question ids"
    assert all(q.prompt.strip() for q in ALL_QUESTIONS), "a question has no prompt"
    assert not hasattr(ALL_QUESTIONS[0], "core"), "the core concept is back"
    assert all(s.questions for s in SECTIONS), "an empty section survives"
    return f"{len(ids)} questions across {len(SECTIONS)} sections, ids unique"


def check_points_round_trip() -> str:
    from .questions import BY_ID, format_points, parse_points
    question = BY_ID["priorities"]
    scores = {"Practicality": 4, "Comfort": 5, "Aesthetics": 9, "Cost": 2}
    line = format_points(scores)
    assert parse_points(line, question.buckets) == scores, "points did not survive the round trip"
    assert sum(parse_points("", question.buckets).values()) == 0, "empty should parse to zeros"
    assert parse_points("Aesthetics 9", question.buckets)["Comfort"] == 0, "missing bucket not zero"
    return f"{line} -> parsed back exactly"


# --- Colour -------------------------------------------------------------------

def _palette():
    from .palette import ACCENT, Colour, FIELD, GROUND, LEATHER, Palette
    palette = Palette()
    for name, hex_code, role in (
        ("Cream", "#F2E9D8", FIELD), ("Ecru", "#E8DFC8", FIELD), ("Pale blue", "#BFD3E6", FIELD),
        ("Navy", "#26303F", GROUND), ("Mid grey", "#7A7A78", GROUND),
        ("Olive", "#6B6B47", GROUND), ("Camel", "#C19A6B", GROUND),
        ("Chocolate", "#6B4426", LEATHER), ("Chestnut", "#8B5A2B", LEATHER),
        ("Rust", "#8E3B2E", ACCENT),
    ):
        palette.add(Colour(name=name, hex=hex_code, role=role))
    return palette


def check_colour_arithmetic() -> str:
    """Hue, lightness and the round trip through hex."""
    from .palette import contrast, from_hsl, hsl, hue_distance, hue_name, lightness, to_hex, to_rgb
    assert to_hex(to_rgb("#C58466")).upper() == "#C58466", "hex round trip lost precision"
    assert hsl("#FFFFFF")[2] == 1.0 and hsl("#000000")[2] == 0.0, "lightness poles wrong"
    assert lightness("#F2E9D8") > lightness("#26303F"), "cream is not lighter than navy"
    assert _near(contrast("#FFFFFF", "#000000"), 1.0), "maximum contrast is not 1"
    assert _near(contrast("#26303F", "#26303F"), 0.0), "a colour contrasts with itself"
    assert hue_distance("#FF0000", "#00FF00") == 120, "hue distance wrong"
    assert hue_distance("#FF0000", "#FF0000") == 0, "a hue differs from itself"
    assert hue_name("#7A7A78") == "grey", "flat grey not named grey"
    assert hue_name("#6B4426") == "brown", "chocolate should be brown, not a wheel sector"
    assert hue_name("#C19A6B") != "brown", "camel is too light to be brown"
    assert hue_name("#26303F") == "blue", "navy must read as blue, not a colour-wheel sector"
    assert hue_name("#6B6B47") == "olive", "olive must read as olive"
    assert hue_name("#8E3B2E") == "red" and hue_name("#8B5A2B") == "brown", \
        "rust and chestnut are not being told apart"
    assert from_hsl(0, 1, 0.5).upper() == "#FF0000", "hsl to hex wrong"
    return "hex round trips, contrast poles at 0 and 1, grey and brown named"


def check_warmth_against_skin() -> str:
    """The verdicts have to match what is actually true of warm skin."""
    from .palette import warmth
    skin = "#C58466"
    assert warmth("#C19A6B", skin)[0] == "harmonious", "camel should sit in his family"
    assert warmth("#6B4426", skin)[0] == "harmonious", "chocolate should sit in his family"
    assert warmth("#26303F", skin)[0] == "flattering", "navy should flatter by contrast"
    # A warm off-white is harmonious rather than flattering; only a truly neutral
    # one goes through the desaturated branch.
    assert warmth("#F8F4EC", skin)[0] == "harmonious", "warm off-white should sit in his family"
    assert warmth("#FAFAFA", skin)[0] == "flattering", "neutral off-white should lift warm skin"
    assert warmth("#7A7A78", skin)[0] == "careful", "flat grey should be flagged"
    assert all(warmth(h, skin)[1] for h in ("#C19A6B", "#26303F", "#7A7A78")), \
        "a verdict came back with no reason"
    return "camel harmonious, navy flattering, flat grey flagged"


def check_harmonies_are_wearable() -> str:
    """Neighbours off the wheel, pulled back into clothes."""
    from .palette import chroma, harmonies, hue_distance
    base = "#C19A6B"
    schemes = harmonies(base)
    for wanted in ("Analogous", "Complementary", "Triadic", "Shades"):
        assert wanted in schemes, f"{wanted} missing"
    complement = schemes["Complementary"][0]
    assert 150 <= hue_distance(base, complement) <= 210, "complement is not opposite"
    for name, swatches in schemes.items():
        for swatch in swatches:
            assert chroma(swatch) <= 0.60, f"{name} returned a traffic cone: {swatch}"
    assert len(schemes["Analogous"]) == 2, "analogous should give both sides"
    return f"{len(schemes)} schemes, all under 0.60 chroma"


def check_combination_scoring() -> str:
    """The scorer must prefer real outfits and reject muddy ones."""
    from .palette import combinations, coverage, score_combination
    palette = _palette()
    counts = coverage(palette)
    assert counts["Top"] and counts["Bottom"] and counts["Shoes"], "roles gave no coverage"

    best = combinations(palette, limit=5)
    assert best, "nothing scored at all"
    top = best[0]
    assert top.score >= 90, f"the best recipe only scored {top.score}"
    assert {"Top", "Bottom", "Shoes"} == set(top.pieces), "a slot is missing"
    assert top.reasons, "a perfect score with nothing to say for itself"

    def by_name(name):
        return next(c for c in palette.colours if c.name == name)

    muddy = score_combination({"Top": by_name("Rust"), "Bottom": by_name("Olive"),
                               "Shoes": by_name("Chocolate")})
    assert muddy.score < 55, f"rust on olive scored {muddy.score}, it should not"
    assert any("one garment" in f for f in muddy.faults), "the muddy fault was not named"

    classic = score_combination({"Top": by_name("Cream"), "Bottom": by_name("Navy"),
                                 "Shoes": by_name("Chocolate")})
    assert classic.score > muddy.score + 30, "cream/navy/brown is not beating rust on olive"
    assert classic.verdict == "wear it", f"the safest outfit in menswear got {classic.verdict}"
    return f"best {top.score} ({top.name}); rust on olive {muddy.score}"


def check_colour_rules_are_obeyed() -> str:
    """A colour not ticked for a category must never appear in that slot."""
    from .palette import combinations, score_combination
    palette = _palette()
    navy = next(c for c in palette.colours if c.name == "Navy")
    navy.categories = ["Bottom"]
    cream = next(c for c in palette.colours if c.name == "Cream")
    cream.categories = ["Top"]

    for combination in combinations(palette, limit=40, minimum=0):
        assert combination.pieces["Top"].id != navy.id, "navy appeared as a top"
        assert combination.pieces["Bottom"].id != cream.id, "cream appeared as a bottom"
    assert palette.for_category("Bottom"), "the grid removed every trouser colour"
    assert navy not in palette.for_category("Top"), "for_category ignores the grid"
    return "the grid is obeyed; navy never a top, cream never a bottom"


def check_palette_round_trip() -> str:
    from .palette import Colour, GROUND, Palette
    palette = Palette()
    palette.add(Colour(name="Navy", hex="#26303F", role=GROUND, note="flannel only"))
    palette.patterns = ["Herringbone", "Gingham"]
    palette.save()
    again = Palette.load()
    assert len(again.colours) == 1 and again.colours[0].note == "flannel only", "colour lost"
    assert again.patterns == ["Herringbone", "Gingham"], "patterns lost"
    assert again.colours[0].allowed, "a colour with no categories got no role defaults"
    assert again.has("#26303f"), "hex matching is case sensitive"
    return f"{again.path.name} round trips with notes and patterns"


# --- Shopping maths -----------------------------------------------------------

def _seeded():
    from .inventory import Inventory
    from .outfits import Outfits
    from .seed import seed_all
    seed_all()
    return Inventory.load(), Outfits.load()


def check_plan_shape() -> str:
    from .shopping import purchase_plan
    inventory, outfits = _seeded()
    plan = purchase_plan(outfits, inventory)
    assert len(plan.wearable_now) == 1, f"expected 1 wearable, got {len(plan.wearable_now)}"
    assert len(plan.blocked) == 4, f"expected 4 blocked, got {len(plan.blocked)}"
    first = {i.name for i in plan.steps[0].items}
    assert first == {"Grey flannel trousers", "Brown suede loafers"}, \
        f"greedy picked the wrong opening bundle: {first}"
    assert len(plan.steps[0].unlocked) == 3, "opening bundle should unlock three outfits"
    assert not plan.still_blocked, "plan left outfits blocked with no budget"
    return (f"opens with 2 pieces unlocking 3 outfits, "
            f"£{plan.total_cost:.0f} total for {plan.outfits_unlocked}")


def check_plan_arithmetic() -> str:
    from .shopping import purchase_plan
    inventory, outfits = _seeded()
    plan = purchase_plan(outfits, inventory)
    running = 0.0
    unlocked = 0
    for step in plan.steps:
        running = round(running + step.price, 2)
        unlocked += len(step.unlocked)
        assert _near(step.cumulative_cost, running), \
            f"running total drifted: {step.cumulative_cost} vs {running}"
        assert step.cumulative_unlocked == unlocked, "unlock count drifted"
        assert _near(step.cost_per_outfit or 0, round(running / unlocked, 2)), "cost per outfit wrong"
    assert _near(plan.total_cost, running), "plan total does not match its steps"
    return f"every running total checks out, £{running:.0f} over {len(plan.steps)} steps"


def check_plan_never_buys_owned() -> str:
    from .shopping import purchase_plan
    inventory, outfits = _seeded()
    plan = purchase_plan(outfits, inventory)
    bought = [i for i in plan.items_to_buy if i.owned]
    assert not bought, f"plan wants to buy things already owned: {[i.name for i in bought]}"
    ids = [i.id for i in plan.items_to_buy]
    assert len(ids) == len(set(ids)), "plan buys the same piece twice"
    return f"{len(ids)} pieces, none owned, none duplicated"


def check_budget_filters_not_halts() -> str:
    from .shopping import purchase_plan
    inventory, outfits = _seeded()
    full = purchase_plan(outfits, inventory)
    tight = purchase_plan(outfits, inventory, budget=300.0)
    assert full.total_cost > 300, "the fixture is too cheap to test a budget"
    assert tight.total_cost <= 300, f"budget exceeded: £{tight.total_cost}"
    # The point of the rewrite: a budget below the best bundle must still buy the
    # best affordable one rather than giving up.
    assert tight.skipped_for_budget, "nothing reported as unaffordable"
    # £300 cannot reach any bundle here, so the plan must say how far short it
    # falls rather than returning an empty result that reads as a crash.
    assert tight.shortfall_items, "no cheapest-bundle advice when nothing is affordable"
    assert tight.shortfall > 0, "shortfall not quantified"
    # A budget that can reach a bundle must actually buy it.
    reachable = purchase_plan(outfits, inventory, budget=400.0)
    assert reachable.steps, "an affordable budget still bought nothing"
    assert reachable.total_cost <= 400, "affordable plan exceeded its budget"
    assert reachable.outfits_unlocked >= 1, "affordable plan unlocked nothing"
    return (f"£300 is £{tight.shortfall:.0f} short of the cheapest bundle; "
            f"£400 buys £{reachable.total_cost:.0f} and unlocks {reachable.outfits_unlocked}")


def check_leverage() -> str:
    from .shopping import item_leverage
    inventory, outfits = _seeded()
    rows = {r.item.name: r for r in item_leverage(outfits, inventory)}
    coat = rows["Camel wool overcoat"]
    assert coat.solo_unlocks == 1, "the coat is the only thing missing from the rain outfit"
    flannels = rows["Grey flannel trousers"]
    assert flannels.appearances == 3, f"flannels appear in 3 blocked outfits, got {flannels.appearances}"
    assert flannels.solo_unlocks == 0, "flannels alone finish nothing"
    assert all(r.item.status != "owned" for r in rows.values()), "an owned item leaked in"
    return f"coat finishes 1 alone; flannels block 3 but finish none"


def check_deleted_garment_breaks_outfit() -> str:
    """Deleting a garment must break its outfits loudly, not silently.

    Resolving a dangling id away would make an outfit report itself wearable the
    moment one of its pieces was deleted, which is the opposite of true.
    """
    from .inventory import Inventory
    from .outfits import Outfits, wearability
    inventory, outfits = _seeded()
    rain = next(o for o in outfits.outfits if o.name.startswith("Rain"))
    coat = next(i for i in inventory.items if i.name == "Camel wool overcoat")
    assert not wearability(rain, inventory).wearable, "fixture outfit should start blocked"

    inventory.remove(coat.id)
    inventory.save()
    after = wearability(rain, Inventory.load())
    assert not after.wearable, "outfit became wearable when its coat was deleted"
    assert after.dangling == [coat.id], f"dangling id not reported: {after.dangling}"
    assert after.broken and "deleted" in after.fault, "fault not explained"

    touched = outfits.forget_item(coat.id)
    assert rain.id in {o.id for o in touched}, "cascade missed the outfit"
    assert coat.id not in rain.item_ids, "id survived the cascade"
    return f"deletion detected, {len(touched)} outfit(s) cleaned up"


def check_retired_never_bought() -> str:
    """A retired garment is not owned, but nobody should be told to buy it back."""
    from .inventory import Inventory, RETIRED
    from .shopping import item_leverage, purchase_plan
    inventory, outfits = _seeded()
    loafers = next(i for i in inventory.items if i.name == "Brown suede loafers")
    loafers.status = RETIRED
    inventory.update(loafers)
    inventory.save()

    inventory, outfits = Inventory.load(), outfits
    plan = purchase_plan(outfits, inventory)
    names = {i.name for i in plan.items_to_buy}
    assert "Brown suede loafers" not in names, "plan wants to re-buy a retired garment"
    assert plan.broken, "outfits containing a retired piece were not flagged"
    assert all(r.item.status != RETIRED for r in plan.leverage), "retired piece in the leverage table"
    assert all(o not in plan.blocked for o in plan.broken), "a broken outfit is also counted as blocked"
    return f"{len(plan.broken)} outfit(s) flagged as broken, none plan a retired piece"


def check_empty_outfit_not_wearable() -> str:
    """An outfit with nothing in it must not count towards "wearable now"."""
    from .inventory import Inventory
    from .outfits import Outfit, Outfits, wearability
    from .shopping import purchase_plan
    inventory, outfits = _seeded()
    blank = outfits.add(Outfit(name="Nothing at all", item_ids=[], loved=True))
    outfits.save()
    w = wearability(blank, inventory)
    assert not w.wearable, "an empty outfit reported itself wearable"
    assert w.broken and "no garments" in w.fault, "empty outfit not explained"
    plan = purchase_plan(Outfits.load(), inventory)
    assert blank.id not in {o.id for o in plan.wearable_now}, "empty outfit inflated the count"
    assert blank.id in {o.id for o in plan.broken}, "empty outfit not flagged as broken"
    return "empty outfit excluded from wearable and flagged"


def check_wearability() -> str:
    from .outfits import wearability
    inventory, outfits = _seeded()
    saturday = next(o for o in outfits.outfits if o.name.startswith("Saturday"))
    dinner = next(o for o in outfits.outfits if o.name.startswith("Dinner"))
    assert wearability(saturday, inventory).wearable, "Saturday should be wearable now"
    w = wearability(dinner, inventory)
    assert not w.wearable and len(w.missing) == 2, "Dinner should be blocked by two pieces"
    assert _near(w.to_buy, sum(m.price for m in w.missing)), "to-buy total wrong"
    return f"Saturday wearable; Dinner blocked by 2, £{w.to_buy:.0f} to fix"


# --- Prompts ------------------------------------------------------------------

def check_subject_in_prompt() -> str:
    from .profile import Profile
    from .prompts import build_prompt
    profile = Profile.load()
    text = build_prompt(profile, "navy shirt")
    assert profile.subject.height_metric in text, "height missing from the prompt"
    assert profile.subject.skin_tone_hex in text, "skin tone hex missing"
    assert "not elongate" in text.lower() or "do not elongate" in text.lower(), \
        "the proportion instruction is gone"
    return f"height, {profile.subject.skin_tone_hex} and the proportion guard all present"


def check_outfit_prompt() -> str:
    from .profile import Profile
    from .prompts import build_outfit_prompt
    garments = ["cream cotton shirt", "grey flannel trousers", "brown suede loafers"]
    with_photos = build_outfit_prompt(Profile.load(), garments, photo_count=2,
                                      principles="- Keep volume in one place.")
    without = build_outfit_prompt(Profile.load(), garments, photo_count=0)
    for g in garments:
        assert g in with_photos, f"{g} missing from the prompt"
    assert "Reference image 1 is the man" in with_photos, "photo roles not explained"
    assert "Reference image 1" not in without, "photo note appears with no photos"
    assert "Keep volume in one place" in with_photos, "principles not carried through"
    return "garments, photo roles and principles all carried through"


def check_guide_prompt() -> str:
    from .philosophy import Answers, build_guide_prompt, unanswered
    from .profile import Profile
    from .seed import seed_answers
    answers = seed_answers()
    text = build_guide_prompt(Profile.load(), answers)
    assert "Practicality 4" in text, "the points allocation never reaches the guide"
    for probe in ("Grey hoodie", "Mastroianni", "swim on the thigh"):
        assert probe in text, f"{probe!r} never reached the prompt"
    assert not unanswered(answers), "seed left questions unanswered"
    return f"{len(text):,} characters, all 24 answers carried"


# --- Shop ---------------------------------------------------------------------

def check_secondhand_rule() -> str:
    """At or over the threshold goes secondhand first; under it does not.

    Asserted from the constant rather than a literal, so moving the line moves
    the test with it and only the two sides of it are ever hard-coded.
    """
    from .inventory import Item
    from .retailers import SECONDHAND, SECONDHAND_THRESHOLD, suggest

    coat = Item(name="Camel wool overcoat", garment="Overcoat", colour="camel",
                fabric="Wool melton", price=420)
    top = suggest(coat, limit=3)
    assert top[0].retailer.name == "Vinted", f"Vinted did not lead: {top[0].retailer.name}"
    assert all(s.retailer.kind == SECONDHAND for s in top), \
        "a £420 coat should put secondhand in every top slot"
    assert "worn rarely" in top[0].reason, "the rarely-worn reason was not given"

    tee = Item(name="White tee", garment="T-shirt", colour="white",
               fabric="Cotton jersey", price=25)
    cheap = suggest(tee, limit=3)
    assert all(s.retailer.kind != SECONDHAND for s in cheap), \
        "a £25 tee should not send him secondhand"

    # The line moved to £50, so a mid-price knit now crosses it and a cheap one
    # still does not. Both sides get asserted or the threshold is untested.
    knit = Item(name="Merino crew", garment="Knitwear", colour="navy", price=55)
    assert suggest(knit, limit=1)[0].retailer.kind == SECONDHAND, \
        "£55 is over the line and should go secondhand first"
    polo = Item(name="Piqué polo", garment="Polo", colour="ecru", price=40)
    assert suggest(polo, limit=1)[0].retailer.kind != SECONDHAND, \
        "£40 is under the line and should stay retail"

    edge = Item(name="Knit", garment="Knitwear", colour="navy", price=SECONDHAND_THRESHOLD)
    assert suggest(edge, limit=1)[0].retailer.kind == SECONDHAND, \
        f"exactly £{SECONDHAND_THRESHOLD:.0f} should still go secondhand first"
    return (f"line at £{SECONDHAND_THRESHOLD:.0f}: £420 coat and £55 knit go secondhand, "
            f"£40 polo and £25 tee stay retail")


def check_retailer_catalogue() -> str:
    """Every retailer is reachable, sane and buildable into a search link."""
    from .inventory import GARMENTS, Item
    from .retailers import KINDS, RETAILERS, query_for

    ids = [r.id for r in RETAILERS]
    assert len(ids) == len(set(ids)), "duplicate retailer id"
    for r in RETAILERS:
        assert r.kind in KINDS, f"{r.name} has an unknown kind {r.kind}"
        assert "{q}" in r.search, f"{r.name} has no query placeholder"
        assert r.price_low < r.price_high, f"{r.name} has an inverted price band"
        assert r.strengths, f"{r.name} sells nothing"
        assert r.url("linen blazer").startswith("https://"), f"{r.name} built a bad url"
        assert " " not in r.url("linen blazer"), f"{r.name} did not escape the query"
    for named in ("Vinted", "H&M", "Uniqlo", "Zara", "Next", "Moss", "Clarks",
                  "Mango", "Base London"):
        assert any(r.name == named for r in RETAILERS), f"{named} is missing"

    coverable = {g for r in RETAILERS for g in r.strengths}
    unsold = [g for g in GARMENTS if g not in coverable]
    assert not unsold, f"no retailer sells: {unsold}"
    assert query_for(Item(garment="Blazer", colour="navy", fabric="Linen")) == "navy Linen Blazer"
    return f"{len(RETAILERS)} retailers across {len(KINDS)} kinds, every garment covered"


def check_tactics() -> str:
    """The cheap-buying tactics have to be specific to the garment."""
    from .inventory import Item
    from .retailers import tactics

    coat = Item(name="Camel overcoat", garment="Overcoat", colour="camel", price=420,
                sizes={"chest": '38"'})
    names = [t.name for t in tactics(coat)]
    assert "Save the Vinted search" in names, "no saved search for an expensive coat"
    assert "Buy it out of season" in names, "no seasonal timing for a coat"
    detail = " ".join(t.detail for t in tactics(coat))
    assert "February" in detail, "the coat's cheap month is not named"
    assert '38"' in detail, "his size never reaches the alert advice"
    assert "£252" in detail, "no walk-away price computed"

    tee = Item(name="Tee", garment="T-shirt", price=25)
    assert "Save the Vinted search" not in [t.name for t in tactics(tee)], \
        "a £25 tee should not be worth a saved search"
    return f"{len(names)} tactics for the coat, size and season both specific"


def check_sourcing_routes() -> str:
    """His plan, and the disambiguation it depends on.

    A heavyweight tee and a plain tee are both "T-shirt" and come from different
    shops, so the keyword match is the load-bearing part. If it breaks, every
    shirt goes to the same place and the plan is decoration.
    """
    from .inventory import GARMENTS, Item
    from .retailers import BY_ID
    from .sourcing import BY_GARMENT, ROUTES, route_for, uncovered

    for route in ROUTES:
        assert route.stores, f"{route.label} names no shop"
        assert all(i in BY_ID for i in route.stores), \
            f"{route.label} points at a retailer that does not exist: {route.stores}"
        assert route.garment in GARMENTS, f"{route.label} is for an unknown garment"
        assert route.retailers, f"{route.label} resolved to nothing"

    def where(name, garment, fabric="", colour=""):
        found = route_for(Item(name=name, garment=garment, fabric=fabric, colour=colour))
        return found.where if found else None

    assert where("Heavyweight boxy tee", "T-shirt") == "Asos or Next", "heavyweight tee misrouted"
    assert where("Plain white tee", "T-shirt") == "Uniqlo", "plain tee misrouted"
    assert where("White oxford shirt", "Shirt", "Oxford cotton") == "Charles Tyrwhitt", \
        "dress shirt misrouted"
    assert where("Ecru shirt", "Shirt", "Linen") == "Mango", "linen shirt misrouted"
    assert where("Knit polo", "Polo", "Merino wool") == "Mango", "knitted polo misrouted"
    assert where("Piqué polo", "Polo", "Cotton piqué") == "Uniqlo", "plain polo misrouted"
    assert where("Adidas Samba", "Trainers", "Suede") != "Vinted", "branded trainer sent to Vinted"
    assert where("White leather trainers", "Trainers", "Calf leather") == "Vinted", \
        "smart trainers not routed to Vinted"

    smart = route_for(Item(name="White leather trainers", garment="Trainers"))
    assert "New with tags" in smart.condition, "the new-with-tags condition was lost"
    blazer = route_for(Item(name="Navy blazer", garment="Blazer"))
    assert "Very Good" in blazer.condition, "the Very Good condition was lost"
    heavy = route_for(Item(name="Heavy tee", garment="T-shirt"))
    assert "200 gsm" in heavy.spec, "the gsm specification was lost"

    # A garment with only a keyword route and no default must return nothing
    # rather than being quietly forced down the wrong one.
    assert route_for(Item(name="Grey flannel trousers", garment="Trousers",
                          fabric="Wool flannel")) is None, \
        "a wool trouser was pushed down the linen route"
    assert "Loafers" in uncovered(GARMENTS), "a known gap stopped being reported"
    return (f"{len(ROUTES)} routes over {len(BY_GARMENT)} garment types; "
            f"tee, shirt, polo and trainer splits all land")


def check_product_prompts() -> str:
    """The product shot must ask for the garment alone, and the copy for his size."""
    from .inventory import Item
    from .profile import Profile
    from .shop import copy_prompt, photo_prompt, size_line, to_buy
    from .seed import seed_all

    item = Item(id="camel", name="Camel wool overcoat", garment="Overcoat",
                colour="camel", fabric="Wool melton", price=420, status="aspirational")
    shot = photo_prompt(item)
    for phrase in ("camel", "Wool melton", "overcoat", "no person", "seamless pure white"):
        assert phrase in shot, f"{phrase!r} missing from the product shot prompt"
    assert "ghost mannequin" in shot.lower(), "no ghost mannequin instruction"

    profile = Profile.load()
    words = copy_prompt(profile, item)
    assert "Wool melton" in words and "£420" in words, "the garment did not reach the copy"
    assert profile.subject.height_metric in words, "his proportions did not reach the copy"
    assert "Chest:" in words, "the size targets did not reach the copy"
    assert size_line(profile, item), "no size line for a coat"

    seed_all()
    from .inventory import Inventory
    listed = to_buy(Inventory.load())
    assert listed and all(i.status == "aspirational" for i in listed), "the list is not wanted-only"
    assert listed == sorted(listed, key=lambda i: (-i.price, i.name)), "list not dearest first"
    return f"{len(listed)} on the list, prompts carry cloth, price and size"


# --- App ----------------------------------------------------------------------

def _render():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(APP_FILE), default_timeout=180).run()
    if app.exception:
        raise AssertionError(str(app.exception[0].value))
    return app


def check_app_renders_empty() -> str:
    app = _render()
    labels = [t.label for t in app.tabs]
    numbered = [l for l in labels if l[0].isdigit()]
    assert len(numbered) == 8, f"expected 8 numbered tabs, got {numbered}"
    assert [l[0] for l in numbered] == list("12345678"), f"tabs out of order: {numbered}"
    assert "Colour" in numbered[3], f"Colour is not the fourth tab: {numbered[3]}"
    assert "Body Measurements" in numbered[6], "body measurements did not get its own tab"
    assert "Shopping" in numbered[7], "shopping guide is not last"
    assert any("Diagnostics" in l for l in labels), "the diagnostics tab is missing"
    return f"{len(labels)} tabs: " + " · ".join(labels)


def check_app_renders_seeded() -> str:
    _seeded()
    from .seed import seed_answers, seed_principles
    seed_answers()
    seed_principles()
    app = _render()
    page = "\n".join(m.value for m in app.markdown)
    for probe in ("Grey flannel trousers", "Saturday, Fulham Road", "Keep the volume",
                  "Every missing piece"):
        assert probe in page, f"{probe!r} never made it onto the page"
    assert len(app.button) > 20, "the seeded page has suspiciously few controls"
    return f"{len(app.button)} controls, inventory, outfits, principles and plan all rendered"


def check_diagnostics_renders() -> str:
    """The panel that clears data must itself render, or the escape hatch is gone."""
    from . import reset
    _seeded()
    reset.snapshot()
    app = _render()
    page = "\n".join(m.value for m in app.markdown)
    assert "Data lives in" in page, "the diagnostics tab did not draw"
    labels = [c.label for c in app.checkbox]
    assert any("I am sure" in l for l in labels), "the confirmation checkbox is missing"
    assert any("Wardrobe inventory" in l for l in labels), "reset checkboxes missing"
    buttons = [b.label for b in app.button]
    for wanted in ("Run checks", "Fill with sample data", "Clear selected", "Restore"):
        assert wanted in buttons, f"the {wanted!r} button is missing"
    return f"{len(labels)} reset checkboxes, confirmation and restore present"


def check_snapshots_do_not_collide() -> str:
    """Two wipes inside the same second must not share a directory."""
    from . import reset
    _seeded()
    first = reset.snapshot(["inventory"])
    second = reset.snapshot(["outfits"])
    assert first and second, "snapshot returned nothing"
    assert first.path != second.path, "the second snapshot overwrote the first"
    assert len(reset.snapshots()) >= 2, "only one snapshot is listed"
    assert first.keys == ["inventory"] and second.keys == ["outfits"], "keys got mixed up"
    return f"{first.path.name} and {second.path.name} kept apart"


def check_no_module_shadowing() -> str:
    """No function may bind a name it also imports at module level.

    Python decides a name is local for the whole function body, so
    `paths = generate_images(...)` at the bottom breaks `paths.looks()` at the
    top with an UnboundLocalError. That killed the outfit generator outright and
    nothing caught it, because rendering a page never runs the click handler.
    """
    import ast as _ast

    offences: list[str] = []
    for source in sorted(Path(__file__).parent.glob("*.py")):
        tree = _ast.parse(source.read_text())
        imported = {a.asname or a.name.split(".")[0] for n in _ast.walk(tree)
                    if isinstance(n, (_ast.Import, _ast.ImportFrom)) for a in n.names}
        for fn in [n for n in _ast.walk(tree)
                   if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))]:
            bound = {t.id for node in _ast.walk(fn) if isinstance(node, _ast.Assign)
                     for t in node.targets if isinstance(t, _ast.Name)}
            for name in sorted(bound & imported):
                offences.append(f"{source.name}:{fn.lineno} {fn.name}() shadows {name!r}")
    assert not offences, "; ".join(offences)
    return "no function shadows an imported name"


def check_generate_button_runs() -> str:
    """Press the button, not just draw it.

    Image generation is stubbed, so this costs nothing and still exercises the
    whole handler: prompt assembly, path resolution, writing the file, and
    saving the outfit.
    """
    from streamlit.testing.v1 import AppTest

    from . import gemini_image
    from .inventory import Inventory
    from .outfits import Outfits

    inventory, _ = _seeded()
    made: dict[str, object] = {}

    def stub(prompt, *, out_prefix, reference_images=None, count=1, settings=None):
        from PIL import Image as _Image
        out_prefix.parent.mkdir(parents=True, exist_ok=True)
        written = []
        for n in range(count):
            target = out_prefix.with_name(f"{out_prefix.name}{'' if count == 1 else f'-{n}'}.png")
            _Image.new("RGB", (64, 96), (200, 150, 120)).save(target, "PNG")
            written.append(target)
        made.update(prompt=prompt, refs=list(reference_images or []))
        return written

    real = gemini_image.generate_images
    gemini_image.generate_images = stub
    try:
        app = AppTest.from_file(str(APP_FILE), default_timeout=180).run()
        if app.exception:
            raise AssertionError(f"render failed: {app.exception[0].value}")

        def widget(collection, key):
            return next((w for w in collection if getattr(w, "key", None) == key), None)

        top = widget(app.selectbox, "pick-Top")
        bottom = widget(app.selectbox, "pick-Bottom")
        assert top and bottom, "the item pickers are missing"
        tee = next(i for i in inventory.items if i.name == "White cotton tee")
        jeans = next(i for i in inventory.items if i.name == "Dark indigo jeans")
        app = top.set_value(tee.id).run()
        app = widget(app.selectbox, "pick-Bottom").set_value(jeans.id).run()
        if app.exception:
            raise AssertionError(f"selecting items failed: {app.exception[0].value}")

        button = next((b for b in app.button if b.label == "Generate look"), None)
        assert button, "the Generate look button is missing once pieces are chosen"
        app = button.click().run()
        if app.exception:
            raise AssertionError(f"clicking Generate raised: {app.exception[0].value}")
    finally:
        gemini_image.generate_images = real

    assert made.get("prompt"), "the handler never reached image generation"
    assert "white cotton t-shirt" in made["prompt"].lower() or "white" in made["prompt"].lower(), \
        "the chosen garments never reached the prompt"
    assert len(made["refs"]) >= 1, "the portrait was not passed as a reference"
    saved = Outfits.load().outfits
    assert saved, "the generated outfit was not saved"
    latest = saved[-1]
    assert latest.images and Path(latest.images[0]).is_file(), "no image recorded on the outfit"
    assert {tee.id, jeans.id} <= set(latest.item_ids), "the outfit lost its pieces"
    return f"clicked through, saved “{latest.name}” with {len(latest.images)} image(s)"


def check_unreadable_image_does_not_crash() -> str:
    """A corrupt look must degrade to a placeholder, not take the page down."""
    from streamlit.testing.v1 import AppTest

    from .outfits import Outfit, Outfits
    inventory, outfits = _seeded()
    broken = paths.looks() / "corrupt.png"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_bytes(b"definitely not a png")
    tee = next(i for i in inventory.items if i.name == "White cotton tee")
    outfits.add(Outfit(name="Corrupt look", item_ids=[tee.id], images=[str(broken)]))
    outfits.save()

    app = AppTest.from_file(str(APP_FILE), default_timeout=180).run()
    assert not app.exception, f"one bad image killed the render: {app.exception[0].value}"
    page = "\n".join(m.value for m in app.markdown)
    assert "could not be read" in page, "no placeholder shown for the corrupt image"
    return "corrupt image degraded to a placeholder, page still rendered"


def check_answer_view_opens() -> str:
    """A saved answer must render as its own page, reached by ?answer=<id>."""
    from streamlit.testing.v1 import AppTest

    from .seed import seed_answers
    seed_answers()

    app = AppTest.from_file(str(APP_FILE), default_timeout=180)
    app.query_params["answer"] = "says_what"
    app = app.run()
    assert not app.exception, f"the answer view raised: {app.exception[0].value}"
    page = "\n".join(m.value for m in app.markdown)
    assert "competent and senior" in page, "the answer itself is missing"
    assert "answer-q" in page, "the question was not rendered as the heading"
    assert not app.tabs, "the standalone view drew the whole app instead"
    assert "?answer=all" in page, "no link back to the full list"

    every = AppTest.from_file(str(APP_FILE), default_timeout=180)
    every.query_params["answer"] = "all"
    every = every.run()
    assert not every.exception, f"the index raised: {every.exception[0].value}"
    index = "\n".join(m.value for m in every.markdown)
    assert index.count("?answer=") >= 20, "the index is not linking every answer"

    normal = AppTest.from_file(str(APP_FILE), default_timeout=180).run()
    assert normal.tabs, "the app stopped drawing tabs without a query param"
    return "single answer, index, and the app itself all render"


def check_item_page_opens() -> str:
    """A garment must open as its own page, with the shop links on it."""
    from streamlit.testing.v1 import AppTest

    from .inventory import Inventory
    _seeded()
    coat = next(i for i in Inventory.load().items if i.name == "Camel wool overcoat")

    app = AppTest.from_file(str(APP_FILE), default_timeout=180)
    app.query_params["item"] = coat.id
    app = app.run()
    assert not app.exception, f"the item page raised: {app.exception[0].value}"
    page = "\n".join(m.value for m in app.markdown)
    assert not app.tabs, "the item page drew the whole app instead"
    assert "Camel wool overcoat" in page, "the garment name is missing"
    assert "vinted.co.uk" in page, "no Vinted link on an expensive coat"
    assert "Where to buy it" in page, "the retailer section is missing"
    assert "your plan" in page, "the sourcing route did not reach the product page"
    assert "Very Good" in page, "the Vinted condition did not reach the product page"
    assert "How to get it cheaply" in page, "the tactics section is missing"
    assert "Outfits waiting on it" in page, "the outfits section is missing"
    assert "Rain on the King" in page, "the outfit using this coat is not listed"

    missing = AppTest.from_file(str(APP_FILE), default_timeout=180)
    missing.query_params["item"] = "no-such-garment"
    missing = missing.run()
    assert not missing.exception, "an unknown id crashed the page"
    assert "No garment with the id" in "\n".join(m.value for m in missing.markdown), \
        "an unknown id did not explain itself"
    return "product page renders with retailers, tactics and its outfits"


def check_reset_round_trip() -> str:
    from .inventory import Inventory
    from . import reset
    _seeded()
    before = reset.present()
    assert "inventory" in before and "outfits" in before, "seed did not land"
    snap, removed = reset.wipe(list(paths.DEFAULT_CLEAR))
    assert snap, "wipe took no snapshot"
    assert not Inventory.load().items, "inventory survived the wipe"
    assert paths.profile().exists(), "the wipe took the subject profile with it"
    restored = reset.restore(reset.snapshots()[0])
    assert len(Inventory.load().items) == 15, "restore did not bring the items back"
    return f"wiped {len(removed)}, restored {len(restored)}, profile untouched throughout"


# --- Live ---------------------------------------------------------------------

def check_live_text() -> str:
    from .gemini_text import generate_text
    reply = generate_text("Reply with exactly the word: BELLISSIMO", temperature=0.0)
    assert "BELLISSIMO" in reply.upper(), f"unexpected reply: {reply[:120]}"
    return f"Vertex AI answered, {len(reply)} characters"


def check_live_image() -> str:
    from .gemini_image import Settings, generate_images
    from .profile import Profile
    from .prompts import build_outfit_prompt
    profile = Profile.load()
    portrait = profile.photo("neutral")
    assert portrait, "no reference portrait to generate from"
    prompt = build_outfit_prompt(
        profile, ["plain white cotton t-shirt", "dark indigo jeans"],
        shot="Upper body", background="White studio")
    written = generate_images(prompt, out_prefix=paths.looks() / "livecheck",
                              reference_images=[portrait], count=1,
                              settings=Settings.from_env())
    assert written and written[0].is_file(), "no image file written"
    size = written[0].stat().st_size
    assert size > 50_000, f"image suspiciously small: {size} bytes"
    return f"{written[0].name}, {size / 1024:.0f} KB"


CHECKS: tuple[tuple[str, str, Callable[[], str]], ...] = (
    (DATA, "Paths stay inside the home directory", check_paths_isolated),
    (DATA, "Subject profile survives a save", check_profile_round_trip),
    (DATA, "Answers trim blanks on save", check_answers_round_trip),
    (DATA, "Item sizes survive a save", check_inventory_round_trip),
    (DATA, "Outfits keep tags and love", check_outfits_round_trip),
    (DATA, "Principles store and parse", check_principles_round_trip),
    (FIT, "Body is the ten takeable measurements", check_body_measurement_set),
    (FIT, "Body estimate is anatomically sane", check_body_estimate),
    (FIT, "Trouser spec keeps its leg opening", check_trouser_spec_survives_derived),
    (FIT, "Ease is added to the body measurement", check_ease_applied),
    (FIT, "Blazer sleeve leaves cuff showing", check_cuff_allowance),
    (FIT, "Trouser break and flat measurements", check_break_and_flat),
    (FIT, "Estimated and measured told apart", check_estimated_flag),
    (FIT, "Lean and athletic is not read as lean", check_build_matching),
    (INVENTORY, "Pattern is gone from items", check_pattern_removed),
    (INVENTORY, "Fabric comes from a fixed list", check_fabric_list),
    (INVENTORY, "Garments and categories alphabetical", check_alphabetical),
    (INVENTORY, "Each garment has its own size scheme", check_size_schemes),
    (INVENTORY, "Size line hides blanks and junk", check_size_line_and_category),
    (INVENTORY, "Stale sizes pruned on re-classification", check_size_pruning),
    (INVENTORY, "Photo uploads are bounded and downscaled", check_photo_limits),
    (QUESTIONS, "Principles come in batches of five", check_principles_batching),
    (QUESTIONS, "Question bank is well formed", check_question_bank),
    (QUESTIONS, "Point allocation round trips", check_points_round_trip),
    (COLOUR, "Colour arithmetic is sound", check_colour_arithmetic),
    (COLOUR, "Warmth verdicts match his skin", check_warmth_against_skin),
    (COLOUR, "Harmonies come back wearable", check_harmonies_are_wearable),
    (COLOUR, "Combinations prefer real outfits", check_combination_scoring),
    (COLOUR, "The colour grid is obeyed", check_colour_rules_are_obeyed),
    (COLOUR, "Palette round trips with patterns", check_palette_round_trip),
    (SHOP, "The secondhand line is respected both ways", check_secondhand_rule),
    (SHOP, "Retailer catalogue is sound", check_retailer_catalogue),
    (SHOP, "Cheap-buying tactics are specific", check_tactics),
    (SHOP, "The sourcing plan routes each garment", check_sourcing_routes),
    (SHOP, "Product prompts carry cloth, price and size", check_product_prompts),
    (MATHS, "Plan opens with the best bundle", check_plan_shape),
    (MATHS, "Running totals are arithmetically right", check_plan_arithmetic),
    (MATHS, "Plan never buys what he owns", check_plan_never_buys_owned),
    (MATHS, "A budget filters rather than halts", check_budget_filters_not_halts),
    (MATHS, "Leverage counts appearances and solo unlocks", check_leverage),
    (MATHS, "Wearability splits owned from to-buy", check_wearability),
    (MATHS, "An empty outfit is not wearable", check_empty_outfit_not_wearable),
    (MATHS, "Deleting a garment breaks its outfits", check_deleted_garment_breaks_outfit),
    (MATHS, "Retired pieces are never bought back", check_retired_never_bought),
    (PROMPTS, "Subject reaches the image prompt", check_subject_in_prompt),
    (PROMPTS, "Outfit prompt carries garments and photo roles", check_outfit_prompt),
    (PROMPTS, "Guide prompt carries every answer", check_guide_prompt),
    (APP, "All tabs render empty", check_app_renders_empty),
    (APP, "All tabs render with a full wardrobe", check_app_renders_seeded),
    (APP, "Diagnostics panels render", check_diagnostics_renders),
    (APP, "No function shadows an imported module", check_no_module_shadowing),
    (APP, "Generate look actually runs when clicked", check_generate_button_runs),
    (APP, "An unreadable image does not crash the page", check_unreadable_image_does_not_crash),
    (APP, "A saved answer opens on its own page", check_answer_view_opens),
    (APP, "A garment opens on its own product page", check_item_page_opens),
    (APP, "Wipe and restore round trip", check_reset_round_trip),
    (APP, "Snapshots in the same second stay apart", check_snapshots_do_not_collide),
    (LIVE, "Gemini returns text", check_live_text),
    (LIVE, "Gemini returns an image", check_live_image),
)


def run(groups: list[str] | None = None, *, live: bool = False,
        on_result: Callable[[Check], None] | None = None) -> Result:
    """Run the suite. Each check gets a fresh scratch home of its own, so one
    check cannot leave state that makes the next one pass or fail."""
    wanted = set(groups) if groups else set(GROUPS) - {LIVE}
    if live:
        wanted.add(LIVE)
    result = Result()
    for group, name, fn in CHECKS:
        if group not in wanted:
            continue
        check = Check(name=name, group=group)
        started = time.perf_counter()
        try:
            with scratch_home():
                check.detail = fn()
            check.passed = True
        except Exception as exc:
            check.detail = f"{type(exc).__name__}: {exc}"
            check.trace = traceback.format_exc()
        check.seconds = round(time.perf_counter() - started, 2)
        result.checks.append(check)
        if on_result:
            on_result(check)
    return result
