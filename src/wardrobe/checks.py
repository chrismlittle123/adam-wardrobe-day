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

DATA, FIT, INVENTORY, QUESTIONS, COLOUR, MATHS, SHOP, PROMPTS, APP, LIVE, BROWSER = (
    "Data", "Fit engine", "Inventory", "Questionnaire", "Colour",
    "Shopping maths", "Shop", "Prompts", "App", "Live Gemini", "Browser",
)
GROUPS: tuple[str, ...] = (DATA, FIT, INVENTORY, QUESTIONS, COLOUR, MATHS, SHOP,
                           PROMPTS, APP, LIVE, BROWSER)


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
                        sizes={"chest": "38", "length": "Regular"}))
    inv.save()
    again = Inventory.load()
    back = again.by_id(item.id)
    assert back and back.sizes == {"chest": "38", "length": "Regular"}, "sizes lost"
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


def check_seeding_is_idempotent() -> str:
    """The bug that grew the wardrobe to 247 items and the principles to 142.

    Every seeder appended blindly, so each smoke run piled another copy of the
    sample data on top. Seeding is "make sure this is present", not "add it
    again": running it twice must change nothing.
    """
    from . import seed
    first = seed.seed_all()
    for _ in range(3):
        again = seed.seed_all()
    assert again == first, f"seeding four times grew the data: {first} -> {again}"
    assert all(n > 0 for n in first.values()), f"a seeder produced nothing: {first}"

    # Idempotent is not enough on its own: the answers seeder was a dict update,
    # so it left the count unchanged while overwriting every real answer with the
    # sample. Twenty-four of this wardrobe's own answers went that way, and only
    # git still had them. Anything already written belongs to the owner.
    from .philosophy import Answers
    book = Answers.load()
    mine = dict(book.values)
    assert mine, "the seeder wrote no answers to check against"
    question = sorted(mine)[0]
    book.values[question] = "Words I typed myself."
    book.save()
    seed.seed_answers()
    assert Answers.load().values[question] == "Words I typed myself.", \
        "seeding overwrote an answer that was already written"

    # And a blank one still gets filled, or the seeder is doing nothing at all.
    book = Answers.load()
    book.values[question] = "   "
    book.save()
    seed.seed_answers()
    assert Answers.load().values[question].strip(), "seeding no longer fills a blank"
    return f"stable over four runs at {first['items']} items, {first['principles']} principles"


def check_suggestions_are_separate() -> str:
    """A suggestion is not a principle until it is confirmed.

    It must not be counted, must not appear under a group, and above all must not
    reach the outfit prompts, which are what principles exist to steer.
    """
    from .principles import CONFIRMED, Principle, Principles, SUGGESTED
    p = Principles.load()
    p.add(Principle(text="Buy the shoulder.", reason="It cannot be altered."))
    p.offer([Principle(text="Wear more beige.", reason="No."),
             Principle(text="Buy the shoulder.", reason="Duplicate of a confirmed one.")])
    assert [x.text for x in p.suggested()] == ["Wear more beige."], \
        "offered back a principle that is already confirmed"
    assert len(p.confirmed()) == 1, "a suggestion was counted as confirmed"
    assert "beige" not in p.as_prompt_block(), "an unconfirmed suggestion reached the prompt"
    assert all(x.status == CONFIRMED for g in p.by_group().values() for x in g), \
        "a suggestion showed up under a group"

    p.offer([Principle(text="Only linen.", reason="Summer.")])
    assert [x.text for x in p.suggested()] == ["Only linen."], \
        "generating added to the pending batch instead of replacing it"
    p.confirm(p.suggested()[0].id)
    assert len(p.confirmed()) == 2 and not p.suggested(), "confirm did not move it across"
    p.add(Principle(text="only  linen", reason="said twice"))
    assert len(p.confirmed()) == 2, "add is not idempotent on text"

    # Writing by hand, or seeding, something that is already sitting on the table
    # as a suggestion has to promote it rather than quietly do nothing.
    p.offer([Principle(text="Trousers at the natural waist.", reason="Proportion.")])
    p.add(Principle(text="trousers at the  natural waist", reason="written by hand",
                    status=CONFIRMED))
    assert not p.suggested(), "confirming by hand left the suggestion on the table"
    assert len(p.confirmed()) == 3, "confirming by hand did not promote the suggestion"
    return "suggestions held apart, batch replaced, confirm moves across"


# --- Fit engine ---------------------------------------------------------------

def check_body_measurement_set() -> str:
    """Exactly the ten a man can take on himself, plus the three derived for him."""
    from .fitspec import CRITICAL, HOW_TO_MEASURE, Body, LABELS
    wanted = {"chest", "waist", "shoulder", "bicep", "sleeve",
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
    assert "wrist" not in wanted and "wrist" not in fields, "wrist came back"
    return f"{len(wanted)} measured, {len(values) - len(wanted)} derived, hip not seat"


def check_heic_uploads_are_accepted() -> str:
    """A photograph off an iPhone is a HEIC, and it has to just work.

    Pillow cannot read the format on its own, so an upload straight off a phone
    came back as "not a readable image" with nothing to suggest why. It is
    decoded and re-encoded to JPEG like every other upload, so nothing
    downstream ever meets one.
    """
    import io as _io
    from PIL import Image as _Image
    from .inventory import MAX_EDGE_PX, UPLOAD_FORMATS, save_photo

    for wanted in ("heic", "heif", "png", "jpg", "jpeg", "webp"):
        assert wanted in UPLOAD_FORMATS, f"the uploader no longer accepts {wanted}"

    class Upload:
        def __init__(self, raw: bytes) -> None:
            self._raw = raw

        def getvalue(self) -> bytes:
            return self._raw

    picture = _Image.new("RGB", (1200, 1800), (180, 120, 60))

    import pillow_heif
    buf = _io.BytesIO()
    pillow_heif.from_pillow(picture).save(buf, format="HEIF")
    heic = buf.getvalue()
    assert heic[4:12] == b"ftypheic", "the fixture is not actually a HEIC"

    stored = Path(save_photo("phone-photo", Upload(heic)))
    assert stored.suffix == ".jpg", f"a HEIC was stored as {stored.suffix}"
    reopened = _Image.open(stored)
    assert reopened.format == "JPEG", f"stored as {reopened.format}, not JPEG"
    assert max(reopened.size) <= MAX_EDGE_PX, "a phone photo was not downscaled"

    # The formats that already worked must go on working.
    for fmt, ext in (("PNG", "png"), ("JPEG", "jpg"), ("WEBP", "webp")):
        b = _io.BytesIO()
        picture.save(b, fmt)
        out = Path(save_photo(f"still-{ext}", Upload(b.getvalue())))
        assert _Image.open(out).format == "JPEG", f"{fmt} stopped working"

    # A portrait photo carries its rotation in EXIF. Without honouring it every
    # picture taken on a phone arrives on its side.
    sideways = _Image.new("RGB", (1800, 1200), (60, 90, 120))
    b = _io.BytesIO()
    exif = sideways.getexif()
    exif[274] = 6                      # orientation: rotate 90 clockwise
    sideways.save(b, "JPEG", exif=exif)
    turned = _Image.open(Path(save_photo("sideways", Upload(b.getvalue()))))
    assert turned.height > turned.width, \
        f"the EXIF rotation was ignored; the photo is still {turned.size}"

    # And nonsense is still refused rather than stored.
    try:
        save_photo("junk", Upload(b"definitely not an image"))
    except ValueError:
        pass
    else:
        raise AssertionError("a non-image was accepted")
    return f"HEIC, PNG, JPEG and WEBP all land as JPEG, and EXIF rotation is honoured"


def check_body_fat_is_worked_out() -> str:
    """Body fat comes off the tape now, not off somebody's eye.

    The profile carried a flat 10% that had been guessed once and never
    revisited. His actual waist of 75 and neck of 38, against 178, put him at
    7.9 by the US Navy circumference method.
    """
    import math
    from .fitspec import Body, body_fat_percent
    from .profile import Profile

    got = body_fat_percent(75, 38, 178)
    assert 7.85 < got < 7.95, f"the formula has drifted: {got}"

    # Recomputed longhand, so a typo in the constants cannot pass by matching
    # itself. This is the published Navy equation, metric, for men.
    longhand = 495 / (1.0324 - 0.19077 * math.log10(75 - 38)
                      + 0.15456 * math.log10(178)) - 450
    assert abs(got - longhand) < 1e-9, "the implementation and the equation disagree"

    # It has to move the right way, and by an amount worth measuring for. A
    # centimetre on the waist is about a point of body fat, which is why the
    # number is derived on every read rather than stored and forgotten.
    assert body_fat_percent(78, 38, 178) > got > body_fat_percent(72, 38, 178), \
        "a bigger waist has to read as more fat"
    assert body_fat_percent(75, 36, 178) > got > body_fat_percent(75, 40, 178), \
        "a thicker neck has to read as less fat"
    assert body_fat_percent(76, 38, 178) - got > 0.7, \
        "a centimetre of waist barely registers; the formula is wrong"

    # Nonsense in must raise rather than return a number nobody can question.
    for waist, neck, height in ((38, 75, 178), (38, 38, 178), (75, 38, 0)):
        try:
            body_fat_percent(waist, neck, height)
        except ValueError:
            continue
        raise AssertionError(f"({waist}, {neck}, {height}) should not produce a figure")

    # Missing either measurement means no figure at all, never a silent zero.
    assert Body(waist=75).body_fat(178) is None, "a missing neck produced a number"
    assert Body(neck=38).body_fat(178) is None, "a missing waist produced a number"
    assert Body().body_fat(178) is None, "an empty body produced a number"
    assert abs(Body(waist=75, neck=38).body_fat(178) - got) < 1e-9, "Body disagrees with the formula"

    # And the profile has to agree with its own tape, to the point.
    p = Profile.load()
    stated, worked = p.subject.body_fat_pct, p.measurements.body_fat(p.subject.height_cm)
    if worked is not None:
        assert abs(stated - worked) <= 0.5, \
            f"the profile says {stated}% and the tape says {worked:.1f}%"
    return f"75 cm waist, 38 cm neck, 178 cm tall reads as {got:.1f}%"


def check_arm_length_moves_the_sleeve() -> str:
    """Arm length is asked for, not derived, and it has to reach the targets.

    Every dimension used to come off height alone, which puts everyone of the
    same height at the same reach. It does not work that way: a man with long
    arms spends his life with his wrists out of his sleeves, and no amount of
    getting the chest right fixes it.
    """
    from .fitspec import ARM_FACTORS, estimate, target_spec, Body
    from .profile import Profile

    average = estimate(178, "very lean and athletic")
    long_arms = estimate(178, "very lean and athletic", "long")
    short = estimate(178, "very lean and athletic", "short")
    assert long_arms["sleeve"] > average["sleeve"] > short["sleeve"], \
        "arm length does not order the sleeve estimate"
    assert long_arms["sleeve"] - average["sleeve"] > 2, \
        "a long arm moves the sleeve by less than the width of a cuff"

    # It moves the sleeve and nothing else. A long arm is not a wider one, and
    # it says nothing at all about his chest or his inseam.
    moved = {k for k in average if average[k] != long_arms[k]}
    assert moved == {"sleeve"}, f"arm length also moved {moved - {'sleeve'}}"

    # Unknown or empty text must not throw or silently lengthen anything.
    for text in ("", "   ", "no idea", None):
        assert estimate(178, "athletic", text or "")["sleeve"] == average["sleeve"], \
            f"arm text {text!r} was read as something"

    # And it has to survive the trip into an actual garment target, which is the
    # part that was missed the first time: the estimator knew and the spec did not.
    body = Body()
    plain = next(t.value for t in target_spec("Shirt", body, 178, build="athletic")
                 if t.key == "sleeve")
    reach = next(t.value for t in target_spec("Shirt", body, 178, build="athletic", arms="long")
                 if t.key == "sleeve")
    assert reach > plain, "target_spec ignores arm length"

    assert set(ARM_FACTORS) == {"short", "average", "long"}, "the arm vocabulary changed"
    assert Profile.load().subject.arms in ("", "short", "average", "long"), \
        "the profile records an arm length the engine cannot read"
    return (f"long arms add {long_arms['sleeve'] - average['sleeve']:.1f} cm of sleeve "
            "and touch nothing else")


def check_description_reaches_the_prompt() -> str:
    """What he looks like in prose has to arrive in the image prompt.

    A field nothing reads is a field that rots. The description and the arm
    length are both about proportion, which is exactly what an image model gets
    wrong when it is told only a height.
    """
    from .profile import Profile
    from .prompts import build_outfit_prompt, description_of, physique

    p = Profile.load()
    p.subject.description = "He has the forearms of a man who climbs."
    p.subject.arms = "long"
    p.save()

    p = Profile.load()
    assert description_of(p) == "He has the forearms of a man who climbs.", "description lost on save"
    assert "long arms" in physique(p), "the arm length never reaches the physique line"

    prompt = build_outfit_prompt(p, ["A white shirt"])
    assert "forearms of a man who climbs" in prompt, "the description never reaches the prompt"
    assert "arms are long" in prompt, "the prompt does not tell the model about his reach"
    assert "cuffs must not ride up" in prompt, "the prompt does not say what long arms mean"

    # No description, no empty sentence left behind in the prompt.
    p.subject.description = ""
    p.subject.arms = ""
    p.save()
    bare = build_outfit_prompt(Profile.load(), ["A white shirt"])
    assert "arms are" not in bare and "\n\n\n" not in bare, \
        "an empty description left a hole in the prompt"
    return "description and arm length both reach the prompt, and leave no gap when unset"


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

def check_grade_and_fit_only_where_they_mean_something() -> str:
    """A grade belongs on a top and a fit on anything cut to a shape.

    There is no heavyweight belt and a watch is not cut. Carrying either
    everywhere put two dead boxes on most forms and, worse, let a piece hold a
    value that a sourcing route would go on matching against for ever.
    """
    from .inventory import Inventory, Item, garments, takes_fit, takes_grade, category_for
    from .sourcing import Plan

    graded = [g for g in garments() if takes_grade(g)]
    fitted = [g for g in garments() if takes_fit(g)]
    assert set(graded) == {g for g in garments() if category_for(g) == "Top"}, \
        f"grade is not confined to tops: {sorted(graded)}"
    assert "Blazer" in fitted and "Trousers" in fitted and "Shirt" in fitted, \
        "fit is missing from tops, blazers or trousers"
    for nothing in ("Belt", "Watch", "Bag", "Sunglasses"):
        assert not takes_grade(nothing) and not takes_fit(nothing), \
            f"{nothing} still carries an axis it has no use for"
    assert not takes_grade("Blazer"), "a blazer is not graded"
    assert not takes_fit("Boots"), "a boot is not cut to a fit"

    # A value on a garment that does not carry the axis is dropped on save, or a
    # route keeps matching it long after the form stopped showing it.
    inventory = Inventory.load()
    belt = inventory.add(Item(name="Test belt", garment="Belt",
                              grade="Smart", fit="Slim"))
    inventory.save()
    back = Inventory.load().by_id(belt.id)
    assert not back.grade and not back.fit, \
        f"a belt kept its grade and fit: {back.grade!r} {back.fit!r}"

    tee = inventory.add(Item(name="Test tee", garment="T-shirt",
                             grade="Heavyweight", fit="Relaxed"))
    inventory.save()
    kept = Inventory.load().by_id(tee.id)
    assert kept.grade == "Heavyweight" and kept.fit == "Relaxed", \
        "a top lost the axes it does carry"

    # And a route asking for an axis its garment does not carry can never fire,
    # which the plan page has to be able to name.
    impossible = [r for r in Plan.load().routes
                  if (r.grade and not takes_grade(r.garment))
                  or (r.fit and not takes_fit(r.garment))]
    assert all(r.garment for r in impossible), "an impossible route has no garment"
    return (f"{len(graded)} garments carry a grade, {len(fitted)} a fit; "
            f"{len(impossible)} route(s) now ask for one that is not there")


def check_garment_colour_comes_from_the_catalogue() -> str:
    """A garment's colour is picked from the catalogue, never typed or mixed.

    Free text had already produced chocolate, Chocolate and dark brown, which is
    one colour wearing three names. A free hex picker would do the same thing
    again with numbers instead of words.
    """
    from streamlit.testing.v1 import AppTest

    from .palette import colour_names, hex_for
    from .inventory import Item

    app = AppTest.from_file(str(APP_FILE), default_timeout=180)
    app.query_params["page"] = "inventory"
    app = app.run()
    assert not app.exception, f"the app raised: {app.exception[0].value}"

    boxes = [w for w in app.multiselect if w.label == "Colours"]
    assert boxes, "no colour picker on the inventory form"
    assert not [w for w in app.selectbox if w.label == "Colour"], \
        "the single-colour dropdown is back"
    for box in boxes:
        assert list(box.options) == list(colour_names()), \
            f"the colour list is not the catalogue: {list(box.options)[:4]}"

    page = "\n".join(m.value for m in app.markdown)
    assert "#CCCCCC" not in page, "the placeholder swatch is still on the page"
    assert "Swatch" not in page, "the swatch preview is back"

    # A garment is often more than one colour: a stripe, a check, a contrast
    # collar. The list is the truth and the first is the lead, because the
    # swatch and the prompts want one word.
    striped = Item(name="x", colours=["Navy", "Cream"])
    assert striped.colour == "Navy", "the lead colour is not the first one"
    assert striped.colour_line == "Navy and cream", f"reads as {striped.colour_line!r}"
    assert "cream" in striped.searchable(), "a second colour is not searchable"
    assert Item(name="y", colours=["Navy"]).colour_line == "Navy", "one colour got a conjunction"
    assert Item(name="z").colour_line == "" and Item(name="z").colour == "", \
        "an item with no colour invented one"

    # The hex still follows from the lead, since the cards and the prompts use it.
    item = Item(name="x", colours=["Navy"])
    item.colour_hex = hex_for(item.colour)
    assert item.colour_hex == "#26303F", "the hex no longer follows the name"

    # Every file on disk was written when a garment had one colour. Reading one
    # of those must fold it into the list rather than lose it.
    from .inventory import Inventory
    legacy = paths.inventory()
    legacy.write_text('[[items]]\nid = "old"\nname = "Old shirt"\ncolour = "Olive"\n')
    back = Inventory.load().items[0]
    assert back.colours == ["Olive"], f"a file written before this lost its colour: {back.colours}"
    return (f"colours picked from {len(colour_names())} catalogue names, several at a "
            "time, and old files still read")


def check_pattern_removed() -> str:
    from .inventory import Item
    assert "pattern" not in Item().__dataclass_fields__, "the pattern field is back"
    described = Item(name="X", colours=["olive"], fabric="linen", garment="Overshirt").describe()
    assert described == "olive linen overshirt", f"describe() changed shape: {described!r}"
    return f"no pattern field; describe() gives {described!r}"


def check_uk_sizing() -> str:
    """UK sizes on labels, centimetres for every measurement, and no US shoes.

    The two get confused constantly: a jacket labelled 38 is not 38 of anything a
    tape can find. Everything the fit engine produces is centimetres, everything
    a shop prints is a UK size, and the labels have to say which is which.
    """
    from .fitspec import Body, HOW_TO_MEASURE, LABELS, spec_table, target_spec
    from .inventory import garments, schemes_for, size_scheme

    for garment in garments():
        for spec in size_scheme(garment):
            assert spec.key != "us", f"{garment} still offers a US size"
            assert "cm" not in spec.label.lower(), \
                f"{garment}'s {spec.label} mixes a measurement into a size label"
    labelled = {f.label for g in garments() for s in schemes_for(g)
                for f in size_scheme(g, s)}
    assert not any("EU" in l or "US" in l for l in labelled), \
        "a continental or American size survived"

    # Every measurement the engine produces is centimetres, with no inches in sight.
    rows = spec_table(target_spec("Blazer", Body(chest=96, waist=78, hip=94), 176))
    assert rows, "the blazer spec came back empty"
    for row in rows:
        assert row["Target"].endswith("cm") or "cm" in row["Target"], \
            f"a target is not in centimetres: {row}"
        assert '"' not in row["Target"], f"inches leaked into a measurement: {row}"
    assert all("cm" not in LABELS.get(k, "") for k in HOW_TO_MEASURE), \
        "a body measurement label carries its unit twice"

    # The two numbers for a chest must not be confusable.
    scheme_chest = next(f for f in size_scheme("Blazer") if f.key == "chest")
    target_chest = next(t for t in target_spec("Blazer", Body(chest=96), 176)
                        if t.key == "chest")
    assert scheme_chest.label == "Chest", "the jacket size box is mislabelled"
    assert target_chest.value > 96, "the finished garment does not exceed the body"
    return (f"labels are UK sizes, measurements are cm; a {scheme_chest.options[3]} "
            f"jacket wants {target_chest.value:g} cm round the chest")


def check_fabric_list() -> str:
    """Fabric is a fixed list, and the sample data uses names from it."""
    from .inventory import NONE, fabric_family, fabric_options
    from .vocabulary import current as vocabulary
    from .seed import ITEMS
    flat = list(vocabulary().fabric_names())
    assert len(flat) == len(set(flat)), "a fabric appears in two families"
    assert fabric_options()[0] == NONE, "no blank option"
    assert list(fabric_options()[1:]) == sorted(fabric_options()[1:]), "fabrics not alphabetical"
    assert len(fabric_options()) > 30, "the list is too thin to cover a wardrobe"
    assert fabric_family("Wool flannel") == "Wool", "family lookup broken"
    unknown = [row[4] for row in ITEMS if row[4] and row[4] not in fabric_options()]
    assert not unknown, f"sample data uses fabrics not on the list: {unknown}"
    return f"{len(flat)} fabrics across {len(vocabulary().families())} families, sample data conforms"


def check_dropdowns_are_alphabetical() -> str:
    """Every list of names that fills a dropdown is in alphabetical order.

    Scales are not, and must not be: sorting XS, S, M, L gives L, M, S, XL, XS.
    Nor are the seasons, which have an order of their own. Everything else is a
    list of names with no inherent order, and a person scans those by eye.
    """
    from .inventory import STATUSES, categories, fabric_options, fits, garments, grades
    from .palette import ROLES, SEASONS, colour_names
    from .prompts import BACKGROUNDS, DEFAULT_BACKGROUND, DEFAULT_SHOT, SHOTS
    from .principles import GROUPS
    from .retailers import KINDS
    from .vocabulary import ALPHA, SCHEMES

    lists = {
        "colours": colour_names(), "garments": garments(), "fabrics": fabric_options(),
        "categories": list(categories()), "grades": grades(), "fits": fits(),
        "size schemes": list(SCHEMES), "retailer kinds": KINDS,
        "colour roles": list(ROLES), "principle groups": GROUPS,
        "framings": list(SHOTS), "backgrounds": list(BACKGROUNDS),
        "statuses": STATUSES,
    }
    for label, values in lists.items():
        names = [v for v in values if v and v != "—"]
        assert names == sorted(names), f"{label} is not alphabetical: {names[:5]}"
        blanks = [v for v in values if not v or v == "—"]
        if blanks:
            assert list(values)[0] in ("", "—"), f"{label} does not lead with its blank"

    # Scales keep their own order, or the dropdown becomes nonsense.
    assert list(ALPHA) != sorted(ALPHA), "alpha sizes were alphabetised into gibberish"
    assert ALPHA.index("S") < ALPHA.index("M") < ALPHA.index("L"), "sizes out of order"
    assert list(SEASONS) == ["Spring", "Summer", "Autumn", "Winter"], \
        "the seasons were alphabetised out of the calendar"

    # Sorting must not have changed what a fresh form defaults to.
    assert list(SHOTS)[0] != DEFAULT_SHOT, "this no longer tests anything"
    assert DEFAULT_SHOT in SHOTS and DEFAULT_BACKGROUND in BACKGROUNDS, \
        "the sensible defaults are not in their lists"
    return (f"{len(lists)} name lists alphabetical; sizes and seasons keep their "
            f"own order; defaults still {DEFAULT_SHOT} and {DEFAULT_BACKGROUND}")


def check_alphabetical() -> str:
    from .inventory import categories, garments
    assert list(garments()) == sorted(garments()), "garments not alphabetical"
    groups = categories()
    assert list(groups) == sorted(groups), "categories not alphabetical"
    for name, group in groups.items():
        assert list(group) == sorted(group), f"{name} not alphabetical"
    return f"{len(garments())} garments, {len(groups)} categories, all sorted"


def check_size_schemes() -> str:
    from .inventory import garments, schemes_for, size_scheme
    keyed = {}
    for garment in garments():
        for scheme in schemes_for(garment):
            keys = [f.key for f in size_scheme(garment, scheme)]
            assert len(keys) == len(set(keys)), f"{garment}/{scheme} has duplicate keys"
        keyed[garment] = [f.key for f in size_scheme(garment)]
    assert "collar" in keyed["Shirt"], "a shirt defaults to its collar"
    assert "chest" in keyed["Blazer"] and "length" in keyed["Blazer"], "blazer needs chest and length"
    assert {"waist", "leg"} <= set(keyed["Trousers"]), "trousers default to waist and leg"

    # The point of the rebuild: one garment, several possible labels.
    assert "Alpha" in schemes_for("Trousers"), "a trouser can also be S/M/L"
    assert "Alpha" in schemes_for("Blazer"), "a blazer can also be S/M/L"
    assert [f.key for f in size_scheme("Trousers", "Alpha")] == ["alpha"], \
        "asking for the alpha scheme did not give alpha boxes"
    assert len(schemes_for("T-shirt")) == 1, "a tee only comes one way"
    assert "uk" in keyed["Loafers"], "shoes need a UK size"
    assert not ({"eu", "us"} & set(keyed["Loafers"])), \
        "continental and American sizing do not belong in a UK wardrobe"
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

    # A value the dropdown can no longer offer is stale too, and nobody can
    # correct it through the form because it is not on the list.
    stale = inventory.add(Item(name="Old blazer", garment="Blazer",
                               sizes={"chest": '38"', "length": "Regular"}))
    inventory.save()
    back = Inventory.load().by_id(stale.id)
    assert "chest" not in back.sizes, f"an unselectable value survived: {back.sizes}"
    assert back.sizes.get("length") == "Regular", "a valid value was dropped with it"
    return (f"collar dropped on re-classification; unselectable values dropped too, "
            f"left with {after.sizes}")


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
    item = Item(garment="Blazer", sizes={"chest": "38", "length": "Regular", "cut": "—",
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
    assert not hasattr(ALL_QUESTIONS[0], "placeholder"), \
        "questions carry example answers again"
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
    from .palette import ACCENT, Colour, FIELD, GROUND, Palette
    palette = Palette()
    # Categories are explicit, as they are in the real palette. Left to the role
    # defaults every ground colour becomes a shoe colour and the fixture starts
    # recommending navy trousers with navy shoes.
    for name, hex_code, role, categories in (
        ("Cream", "#F2E9D8", FIELD, ["Top", "Outerwear"]),
        ("Ecru", "#E8DFC8", FIELD, ["Top"]),
        ("Pale blue", "#BFD3E6", FIELD, ["Top"]),
        ("Navy", "#26303F", GROUND, ["Bottom", "Outerwear", "Top"]),
        ("Mid grey", "#7A7A78", GROUND, ["Bottom"]),
        ("Olive", "#6B6B47", GROUND, ["Bottom", "Outerwear"]),
        ("Camel", "#C19A6B", GROUND, ["Outerwear", "Top"]),
        ("Chocolate", "#6B4426", GROUND, ["Shoes", "Accessory"]),
        ("Chestnut", "#8B5A2B", GROUND, ["Shoes", "Accessory"]),
        ("Rust", "#8E3B2E", ACCENT, ["Accessory", "Top"]),
    ):
        palette.add(Colour(name=name, hex=hex_code, role=role, categories=categories))
    return palette


def check_added_garments_get_their_rules() -> str:
    """A garment added after the defaults were built must still get them.

    Sizing scheme, whether it carries a grade, whether it carries a fit: all
    three follow from what the garment is, and defaults() has always worked them
    out from the tables. add_garment did not, so anything added later arrived
    with free-text sizing, no grade and no fit. The hoodie came in that way, and
    every other top is alpha sized and carries both.
    """
    from .vocabulary import (DEFAULT_CATEGORIES, FITTED_CATEGORIES, Garment,
                             GRADED_CATEGORIES, Vocabulary, current)

    assert "Hoodie" in DEFAULT_CATEGORIES["Top"], "the hoodie is not a top"
    live = current()
    hoodie = next((g for g in live.garments if g.name == "Hoodie"), None)
    assert hoodie is not None, "the hoodie is not in the catalogue"
    assert hoodie.schemes == ["Alpha"], f"a hoodie is alpha sized, not {hoodie.schemes}"
    assert hoodie.takes_grade and hoodie.takes_fit, "a hoodie carries a grade and a fit"

    # Every top agrees with every other top, which is what caught this.
    for top in (g for g in live.garments if g.category == "Top"):
        assert top.schemes, f"{top.name} has no sizing scheme"
        assert top.takes_grade, f"{top.name} does not carry a grade"
        assert top.takes_fit, f"{top.name} does not carry a fit"

    # And the rule is applied on add, not just written into the defaults once.
    vocab = Vocabulary.load()
    vocab.add_garment(Garment(name="Cagoule", category="Top"))
    added = next(g for g in vocab.garments if g.name == "Cagoule")
    assert added.schemes == ["Free text"], "an unknown garment lost its fallback scheme"
    assert added.takes_grade is (("Top") in GRADED_CATEGORIES), "grade not applied on add"
    assert added.takes_fit is (("Top") in FITTED_CATEGORIES), "fit not applied on add"

    # A caller that has decided keeps its decision.
    vocab.add_garment(Garment(name="Cape", category="Outerwear", schemes=["One size"]))
    kept = next(g for g in vocab.garments if g.name == "Cape")
    assert kept.schemes == ["One size"], "an explicit scheme was overwritten"
    return f"a hoodie is an alpha-sized top with a grade and a fit, like every other top"


def check_fabric_families() -> str:
    """Every fabric belongs to a family, and the families are about how a cloth
    behaves rather than what it is chemically.

    Viscose is the case that makes the point: a cellulosic rather than a protein
    fibre, filed with the silks because it drapes like one, which is the question
    a wardrobe is actually asking of it.
    """
    from .vocabulary import DEFAULT_FABRICS, current
    vocab = current()
    names = [f.name for f in vocab.fabrics if f.name]
    assert len(names) == len(set(names)), "a fabric is listed twice"
    for fabric in vocab.fabrics:
        if fabric.name:
            assert fabric.family, f"{fabric.name} belongs to no family"
    assert names == sorted(names), "the fabric dropdown is not alphabetical"

    assert "Viscose" in names, "viscose is not offered"
    family = next(f.family for f in vocab.fabrics if f.name == "Viscose")
    assert family == "Silk and fine", f"viscose is filed under {family}"
    for staple in ("Linen", "Merino wool", "Oxford cotton", "Suede", "Silk"):
        assert staple in names, f"{staple} has gone missing"
    defined = sum(len(x) for x in DEFAULT_FABRICS.values())
    assert len(vocab.fabrics) >= defined - 1, \
        f"the catalogue holds {len(vocab.fabrics)} fabrics against {defined} defined"
    return f"{len(names)} fabrics in {len(DEFAULT_FABRICS)} families, viscose with the silks"


def check_named_colours() -> str:
    """The colours live in the catalogue with the other vocabularies, and can be
    added to like any of them."""
    from .palette import (colour_group, colour_hex, colour_names, hex_for,
                          measurable, named_colours)
    from .vocabulary import DEFAULT_COLOURS, UNMEASURABLE_COLOURS
    expected = sum(len(rows) for rows in DEFAULT_COLOURS.values())
    assert len(colour_names()) == expected, \
        f"expected {expected} colours, got {len(colour_names())}"
    assert len(set(colour_names())) == expected, "a colour name appears twice"
    swatches = list(colour_hex().values())
    assert len(set(swatches)) == expected, "two colours share a hex code"

    # Multicolour is in the list because that is where a man looks for it, and
    # held out of every calculation that assumes a single hex. Measuring the
    # placeholder against his skin would pronounce on a garment nobody has seen.
    assert "Multicolour" in colour_names(), "multicolour is not offered"
    assert not measurable("Multicolour"), "the rule is willing to judge multicolour"
    assert all(measurable(n) for n in colour_names() if n not in UNMEASURABLE_COLOURS), \
        "a plain colour was marked unmeasurable"
    assert colour_names() == tuple(sorted(colour_names())), "the dropdown is not alphabetical"

    # A swatch strip is drawn as one continuous band, so the order inside a
    # group is the point of the grouping. It used to be file order, which put
    # anything added later on the end: Green arrived between Moss and Olive in
    # lightness and sat after Bottle.
    from .palette import lightness
    for group, rows in named_colours().items():
        values = [lightness(h) for _, h in rows]
        assert values == sorted(values, reverse=True), \
            f"{group} is not light to dark: {[n for n, _ in rows]}"
    greens = [n for n, _ in named_colours()["Greens"]]
    assert greens.index("Green") == greens.index("Moss") + 1, \
        f"Green is not where its lightness puts it: {greens}"

    # The two most recent additions, and what makes each of them awkward.
    assert "Green" in colour_names(), "the plain green is missing"
    assert hex_for("Green") not in {hex_for(n) for n in colour_names() if n != "Green"}, \
        "Green shares a swatch with another colour"
    for name, code in colour_hex().items():
        assert len(code) == 7 and code.startswith("#"), f"{name} has a malformed hex"
        assert code == code.upper(), f"{name} is not upper case"
        assert colour_group(name), f"{name} belongs to no group"
    assert hex_for("Navy") == "#26303F", "a known colour moved"
    assert hex_for("nonsense") == "#CCCCCC", "an unknown colour has no fallback"
    for essential in ("White", "Cream", "Navy", "Charcoal", "Olive", "Camel",
                      "Chocolate", "Black", "Burgundy", "Oxblood"):
        assert essential in colour_hex(), f"{essential} is missing"

    # The list is data now, so an addition has to show up everywhere at once.
    from .vocabulary import NamedColour, Vocabulary
    vocab = Vocabulary.load()
    vocab.add_colour(NamedColour(name="Adam green", hex="#3F5E3A", group="Greens"))
    vocab.save()
    assert "Adam green" in colour_names(), "an added colour is not visible"
    assert measurable("Adam green"), "a newly added colour must be measurable"
    assert hex_for("Adam green") == "#3F5E3A", "the added colour has no swatch"
    assert colour_group("Adam green") == "Greens", "it landed in no group"
    assert "Adam green" in [n for n, _ in named_colours()["Greens"]], \
        "it is not in its group's list"
    Vocabulary.load().restore_defaults()
    assert "Adam green" not in colour_names(), "restoring did not undo it"
    return (f"{len(colour_names())} colours across {len(named_colours())} groups, "
            "all distinct, and addable")


def check_seasons() -> str:
    """Four palettes out of one, and a colour with no season is worn all year."""
    from .palette import ACCENT, Colour, GROUND, Palette, SEASONS, coverage

    palette = _palette()
    for colour in palette.colours:
        assert colour.wears == SEASONS, "a colour with no seasons is not all-year"
        assert colour.season_line == "all year", "the all-year label is wrong"

    summer = next(c for c in palette.colours if c.name == "Cream")
    summer.seasons = ["Spring", "Summer"]
    winter = next(c for c in palette.colours if c.name == "Olive")
    winter.seasons = ["Autumn", "Winter"]

    assert summer.in_season("Summer") and not summer.in_season("Winter"), "season test wrong"
    assert summer.season_line == "Spring, Summer", f"label wrong: {summer.season_line}"
    assert summer in palette.for_season("Summer"), "not in its own season"
    assert summer not in palette.for_season("Winter"), "leaked into the wrong season"
    assert winter in palette.for_season("Winter"), "the winter colour is missing"

    every = palette.by_season()
    assert set(every) == set(SEASONS), "a season is missing from the breakdown"
    always = next(c for c in palette.colours if c.name == "Navy")
    assert all(always in every[s] for s in SEASONS), "an all-year colour missed a season"

    # A seasonal palette has to be usable, which means having something for each
    # slot. A season with no trouser colour is a mood board.
    summer_cover = coverage(palette, "Summer")
    all_cover = coverage(palette)
    assert summer_cover["Top"] <= all_cover["Top"], "a season has more than the whole"
    assert sum(summer_cover.values()) < sum(all_cover.values()), \
        "restricting to a season changed nothing"
    return (f"{len(SEASONS)} palettes; summer holds {len(palette.for_season('Summer'))} "
            f"of {len(palette.colours)} colours")


def check_roles() -> str:
    """Three roles, and every garment slot reachable from one of them.

    A role is the whole reason a palette is more than a list: navy as the ground
    under everything is a different garment from navy next to the face. If a slot
    no role can reach, a seasonal palette can have a hole nobody can fill.
    """
    from .palette import (ACCENT, CATEGORIES, Colour, FIELD, GROUND, ROLES,
                          ROLE_CATEGORIES, Palette, coverage)

    assert set(ROLES) == {GROUND, FIELD, ACCENT}, f"roles drifted: {list(ROLES)}"
    assert "Leather" not in ROLES, "the leather role came back"
    assert all(ROLES[r].strip() for r in ROLES), "a role has no explanation"

    reachable = {c for role in ROLES for c in ROLE_CATEGORIES[role]}
    assert set(CATEGORIES) <= reachable, \
        f"no role can be worn on: {sorted(set(CATEGORIES) - reachable)}"
    assert "Shoes" in ROLE_CATEGORIES[GROUND], "no role can be worn on the feet"

    # A colour with no categories of its own falls back to its role's, so a
    # palette is usable the moment colours are added, without filling in a grid.
    palette = Palette()
    palette.add(Colour(name="Navy", hex="#26303F", role=GROUND))
    palette.add(Colour(name="Cream", hex="#F2E9D8", role=FIELD))
    covered = coverage(palette)
    assert covered["Bottom"] and covered["Top"] and covered["Shoes"], \
        f"role defaults leave slots empty: {covered}"
    return f"{len(ROLES)} roles reaching all {len(CATEGORIES)} slots"


def check_colour_arithmetic() -> str:
    """Hue, lightness and the round trip through hex."""
    from .palette import from_hsl, hsl, hue_name, lightness, to_hex, to_rgb
    assert to_hex(to_rgb("#A0583C")).upper() == "#A0583C", "hex round trip lost precision"
    assert hsl("#FFFFFF")[2] == 1.0 and hsl("#000000")[2] == 0.0, "lightness poles wrong"
    assert lightness("#F2E9D8") > lightness("#26303F"), "cream is not lighter than navy"
    assert hue_name("#7A7A78") == "grey", "flat grey not named grey"
    assert hue_name("#6B4426") == "brown", "chocolate should be brown, not a wheel sector"
    assert hue_name("#C19A6B") != "brown", "camel is too light to be brown"
    assert hue_name("#26303F") == "blue", "navy must read as blue, not a colour-wheel sector"
    assert hue_name("#6B6B47") == "olive", "olive must read as olive"
    assert hue_name("#8E3B2E") == "red" and hue_name("#8B5A2B") == "brown", \
        "rust and chestnut are not being told apart"
    assert from_hsl(0, 1, 0.5).upper() == "#FF0000", "hsl to hex wrong"
    return "hex round trips, lightness poles at 0 and 1, grey and brown named"


def check_the_one_rule() -> str:
    """A colour worn on top must sit far enough from his skin. That is the whole
    engine now.

    There used to be a warmth verdict here as well, grading colours harmonious or
    flattering or careful by how many degrees round the hue wheel they sat from
    him. Nobody asked for it and it was never observed, only invented. It is gone,
    and so is the middle band it sat next to: the rule is a yes or a no.
    """
    from .palette import (Colour, DEFAULT_SKIN, NEAR_THE_FACE, Palette, TOO_CLOSE,
                          blurs_at_the_collar, breaks_the_rule, clears_the_face,
                          face_rule, skin_distance, to_lab)
    from .profile import Profile
    skin = DEFAULT_SKIN
    assert Profile.load().subject.skin_tone_hex == skin, \
        "the profile and the engine disagree about his skin"

    # Distance is measured in CIELAB, where a step of a given size looks the same
    # size wherever it is taken. A colour compared with itself is zero.
    assert skin_distance(skin, skin) < 0.001, "a colour differs from itself"
    assert to_lab("#000000")[0] < 1 and to_lab("#FFFFFF")[0] > 99, "the L axis is wrong"
    assert skin_distance("#FFFFFF", skin) > skin_distance("#C19A6B", skin), \
        "white should be further from him than camel"

    too_close = ("#B5613F", "#8E3B2E", "#7E5835", "#6B4426")   # terracotta rust tobacco chocolate
    clear = ("#6E2C33", "#C19A6B", "#F2E9D8", "#26303F", "#0F4C9E", "#0F7B5F")
    for hex_code in too_close:
        assert blurs_at_the_collar(hex_code, skin), f"{hex_code} should read as more of him"
        assert not face_rule(hex_code, skin)[0], f"{hex_code} passed the rule it breaks"
        assert "more of him" in face_rule(hex_code, skin)[1], "the failure does not explain itself"
    for hex_code in clear:
        assert clears_the_face(hex_code, skin), f"{hex_code} should clear his face"
        assert face_rule(hex_code, skin)[0], f"{hex_code} failed the rule it passes"

    # Burgundy is the one that matters. Hue and lightness taken separately banned
    # it, and it is a good colour on brown skin, so it is the regression case.
    assert clears_the_face("#6E2C33", skin), "burgundy must not be banned"
    assert skin_distance("#6E2C33", skin) > skin_distance("#6B4426", skin), \
        "burgundy should sit further off him than chocolate"

    # The rule only bites where it applies. The same colour is fine on a shoe.
    palette = Palette(colours=[
        Colour(id="terracotta", name="Terracotta", hex="#B5613F", categories=["Top"]),
        Colour(id="chocolate", name="Chocolate", hex="#6B4426", categories=["Shoes"]),
        Colour(id="navy", name="Navy", hex="#26303F", categories=["Top"]),
    ])
    named = [c.name for c in breaks_the_rule(palette, skin)]
    assert named == ["Terracotta"], f"the rule bit the wrong colours: {named}"
    assert NEAR_THE_FACE == ("Top",), "the rule has quietly changed scope"

    # A colour just under the line must not round up to the threshold on the page
    # and read as "20, under the 20 minimum".
    from .palette import distance_line
    near_miss = "#962D2D"   # 19.9995 from him: breaks the rule, rounds to 20
    assert TOO_CLOSE - 1 < skin_distance(near_miss, skin) < TOO_CLOSE, \
        "the near-miss fixture no longer sits just under the line"
    # The number printed must always agree with the yes or the no beside it, at
    # every hex, not just at the fixture.
    import re as _re
    for hex_code in (near_miss, "#B5613F", "#6E2C33", "#26303F", skin, "#FFFFFF"):
        passes, why = face_rule(hex_code, skin)
        shown = float(_re.match(r"[\d.]+", why).group())
        assert shown == float(distance_line(hex_code, skin)), "two roundings disagree"
        assert (shown >= TOO_CLOSE) == passes, \
            f"{hex_code} shows {shown} beside a verdict of {passes}"
    assert not face_rule(near_miss, skin)[0], "the near miss should break the rule"

    # No verdict machinery survives.
    import wardrobe.palette as module
    for gone in ("warmth", "reads_against_skin", "separation_reason", "hue_distance",
                 "CLEARLY_APART", "HUE_GAP", "VALUE_GAP"):
        assert not hasattr(module, gone), f"{gone} came back"
    return (f"one rule at {TOO_CLOSE:.0f}: terracotta {skin_distance('#B5613F', skin):.0f} "
            f"breaks it, burgundy {skin_distance('#6E2C33', skin):.0f} clears it")


def check_palette_round_trip() -> str:
    from .palette import Colour, GROUND, Palette
    palette = Palette()
    palette.add(Colour(name="Navy", hex="#26303F", role=GROUND, note="flannel only"))
    palette.save()
    again = Palette.load()
    assert len(again.colours) == 1 and again.colours[0].note == "flannel only", "colour lost"
    assert not hasattr(again, "patterns"), "the pattern list came back"
    assert again.colours[0].allowed, "a colour with no categories got no role defaults"
    assert again.has("#26303f"), "hex matching is case sensitive"
    return f"{again.path.name} round trips with its notes and roles"


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
    assert not plan.still_blocked, "the plan left outfits blocked"
    return (f"opens with 2 pieces unlocking 3 outfits, "
            f"{plan.to_find} garments for {plan.outfits_unlocked}")


def check_plan_arithmetic() -> str:
    """The running counts have to add up, or the plan is describing another plan."""
    from .shopping import purchase_plan
    inventory, outfits = _seeded()
    plan = purchase_plan(outfits, inventory)
    bought = unlocked = 0
    for step in plan.steps:
        bought += step.size
        unlocked += len(step.unlocked)
        assert step.cumulative_bought == bought, \
            f"garment count drifted: {step.cumulative_bought} vs {bought}"
        assert step.cumulative_unlocked == unlocked, "unlock count drifted"
        assert step.size == len(step.items), "step size does not match its items"
    assert plan.to_find == bought, "the plan total does not match its steps"
    return f"{bought} garments over {len(plan.steps)} steps, every running count checks out"


def check_plan_never_buys_owned() -> str:
    from .shopping import purchase_plan
    inventory, outfits = _seeded()
    plan = purchase_plan(outfits, inventory)
    bought = [i for i in plan.items_to_buy if i.owned]
    assert not bought, f"plan wants to buy things already owned: {[i.name for i in bought]}"
    ids = [i.id for i in plan.items_to_buy]
    assert len(ids) == len(set(ids)), "plan buys the same piece twice"
    return f"{len(ids)} pieces, none owned, none duplicated"


def check_plan_prefers_fewer_garments() -> str:
    """With no money in it, the greedy must minimise garments found, not pounds."""
    from .shopping import purchase_plan
    inventory, outfits = _seeded()
    plan = purchase_plan(outfits, inventory)

    first = plan.steps[0]
    ratios = [len(s.unlocked) / s.size for s in plan.steps]
    assert ratios[0] == max(ratios), \
        f"the best outfits-per-garment bundle was not taken first: {ratios}"
    assert first.size == 2 and len(first.unlocked) == 3, \
        f"expected 2 pieces unlocking 3, got {first.size} unlocking {len(first.unlocked)}"
    assert plan.to_find == sum(s.size for s in plan.steps), "to_find disagrees with the steps"
    assert plan.to_find < sum(len(w.missing) for w in
                              (__import__("wardrobe.outfits", fromlist=["x"]).wearability(o, inventory)
                               for o in plan.blocked)), \
        "the plan buys as many garments as doing every outfit separately would"
    assert not hasattr(plan, "total_cost"), "a cost figure survived on the plan"
    return f"{plan.to_find} garments unlock {plan.outfits_unlocked} outfits, best ratio first"


def check_leverage() -> str:
    from .shopping import item_leverage
    inventory, outfits = _seeded()
    rows = {r.item.name: r for r in item_leverage(outfits, inventory)}
    assert not hasattr(next(iter(rows.values())), "price"), "leverage still carries a price"
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
    assert not hasattr(w, "to_buy"), "a cost figure survived on wearability"
    assert {m.garment for m in w.missing} == {"Trousers", "Loafers"}, \
        f"the wrong pieces are missing: {[m.name for m in w.missing]}"
    return f"Saturday wearable; Dinner blocked by {len(w.missing)}"


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
    pieces = ["cream cotton shirt", "grey flannel trousers", "brown suede loafers"]
    with_photos = build_outfit_prompt(Profile.load(), pieces, photo_count=2,
                                      principles="- Keep volume in one place.")
    without = build_outfit_prompt(Profile.load(), pieces, photo_count=0)
    for g in pieces:
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
    """Rarely-worn garments go secondhand first; things worn out do not.

    This used to be a price threshold. Prices were the wrong handle: almost
    everything comes off a listing where the price is unknown until it appears,
    so the rule now keys on how often the garment is worn, which is knowable.
    """
    from .inventory import Item
    from .retailers import RARELY_WORN, SECONDHAND, WORN_OUT, suggest

    coat = Item(name="Camel wool overcoat", garment="Overcoat", colours=["Camel"],
                fabric="Wool melton")
    top = suggest(coat, limit=3)
    assert top[0].retailer.name == "Vinted", f"Vinted did not lead: {top[0].retailer.name}"
    assert top[0].retailer.kind == SECONDHAND, \
        "an overcoat should lead with a resale site"
    assert "worn seldom" in top[0].reason, "the rarely-worn reason was not given"

    for garment in ("Blazer", "Derbies", "Boots", "Suit", "Loafers"):
        assert garment in RARELY_WORN, f"{garment} should go secondhand first"
        assert suggest(Item(name="x", garment=garment), limit=1)[0].retailer.kind == SECONDHAND, \
            f"{garment} did not lead with a resale site"

    tee = suggest(Item(name="White tee", garment="T-shirt", colours=["White"]), limit=3)
    assert all(s.retailer.kind != SECONDHAND for s in tee), \
        "a tee is worn out, so it should be bought new"
    every = suggest(Item(name="x", garment="T-shirt"), limit=99)
    resale = [s for s in every if s.retailer.kind == SECONDHAND]
    assert resale, "no resale site sells a t-shirt at all"
    assert every[0].retailer.kind != SECONDHAND, \
        "a resale site led for something that wears out"
    assert "little life left" in resale[0].reason, "the worn-out reason was never given"
    assert "T-shirt" in WORN_OUT and "Jeans" in WORN_OUT, "the consumables set shrank"
    return (f"{len(RARELY_WORN)} garments go secondhand first, "
            f"{len(WORN_OUT)} are bought new; no prices involved")


def check_catalogue_is_editable() -> str:
    """The shops are data too, and a route survives one being deleted."""
    from .inventory import Item
    from .retailers import Catalogue, DEFAULT_RETAILERS, Retailer, suggest
    from .sourcing import Plan

    fresh = Catalogue.load()
    assert not fresh.path.is_file(), "loading wrote a file it should not have"
    assert len(fresh.retailers) == len(DEFAULT_RETAILERS), "defaults did not load"
    assert all(r.id for r in fresh.retailers), "a shop loaded without an id"

    fresh.add(Retailer(name="Percival", kind="Online", strengths=["Knitwear"],
                       price_low=60, price_high=300, search="https://x/?q={q}"))
    fresh.save()
    again = Catalogue.load()
    assert again.by_id("percival"), "the added shop was lost"
    assert again.by_id("percival") in again.sells("Knitwear"), "it sells nothing"

    # A route naming a deleted shop must drop it, not raise.
    plan = Plan.load()
    route = next(r for r in plan.routes if "vinted" in r.stores)
    before = len(route.shops(again))
    again.remove("vinted")
    again.save()
    after = Catalogue.load()
    assert route.shops(after) != route.shops(again) or before > len(route.shops(after)) \
        or "vinted" not in [s.id for s in route.shops(after)], \
        "a deleted shop still resolves on the route"
    assert all(s.id != "vinted" for s in route.shops(after)), "the deleted shop survived"
    assert route.where_in(after) != "", "the route lost its label entirely"

    assert not any(s.retailer.id == "vinted" for s in
                   suggest(Item(name="x", garment="Overcoat"), limit=9, catalogue=after)), \
        "a deleted shop is still being suggested"

    restored = Catalogue.load().restore_defaults()
    assert len(restored.retailers) == len(DEFAULT_RETAILERS), "restore did not"
    assert restored.by_id("vinted"), "restoring did not bring Vinted back"
    return f"{len(DEFAULT_RETAILERS)} defaults; add, edit, delete and restore all persist"


def check_retailer_catalogue() -> str:
    """Every retailer is reachable, sane and buildable into a search link."""
    from .inventory import garments, Item
    from .retailers import Catalogue, KINDS, query_for

    RETAILERS = Catalogue.load().retailers
    ids = [r.id for r in RETAILERS]
    assert len(ids) == len(set(ids)), "duplicate retailer id"
    for r in RETAILERS:
        assert r.kind in KINDS, f"{r.name} has an unknown kind {r.kind}"
        assert "{q}" in r.search, f"{r.name} has no query placeholder"
        assert r.price_low < r.price_high, f"{r.name} has an inverted price band"
        assert r.strengths, f"{r.name} sells nothing"
        assert r.url("linen blazer").startswith("https://"), f"{r.name} built a bad url"
        assert " " not in r.url("linen blazer"), f"{r.name} did not escape the query"
    # Six he uses, not forty he does not. A shop in the list he has never walked
    # into makes the plan unfollowable.
    assert len(RETAILERS) <= 8, f"the catalogue has grown back to {len(RETAILERS)}"
    for named in ("Vinted", "Uniqlo", "Marks and Spencer", "Mango", "Next",
                  "Charles Tyrwhitt"):
        assert any(r.name == named for r in RETAILERS), f"{named} is missing"
    assert any(r.kind == "Secondhand" for r in RETAILERS), \
        "nothing secondhand, so the rarely-worn rule has nowhere to send him"

    coverable = {g for r in RETAILERS for g in r.strengths}
    unsold = [g for g in garments() if g not in coverable]
    assert not unsold, f"no retailer sells: {unsold}"
    assert query_for(Item(garment="Blazer", colours=["navy"], fabric="Linen")) == "navy Linen Blazer"
    return f"{len(RETAILERS)} retailers across {len(KINDS)} kinds, every garment covered"


def check_tactics() -> str:
    """The cheap-buying tactics have to be specific to the garment."""
    from .inventory import Item
    from .retailers import tactics

    coat = Item(name="Camel overcoat", garment="Overcoat", colours=["Camel"],
                sizes={"chest": "38"})
    names = [t.name for t in tactics(coat)]
    assert "Save the Vinted search" in names, "no saved search for a rarely-worn coat"
    assert "Buy it out of season" in names, "no seasonal timing for a coat"
    detail = " ".join(t.detail for t in tactics(coat))
    assert "February" in detail, "the coat's cheap month is not named"
    assert "38" in detail, "his size never reaches the alert advice"
    assert "£" not in detail, "a price crept back into the advice"

    tee = Item(name="Tee", garment="T-shirt")
    assert "Save the Vinted search" not in [t.name for t in tactics(tee)], \
        "a tee is worn out, so it is not worth a saved search"
    return f"{len(names)} tactics for the coat, size and season both specific"


def check_sourcing_routes() -> str:
    """His plan, and the three axes it selects on.

    Grade, fabric and fit are what make a route precise. If the matching breaks,
    every shirt goes to the same shop and the plan is decoration.
    """
    from .inventory import fits, garments, grades, Item
    from .retailers import Catalogue
    from .sourcing import Plan, route_for, uncovered, why

    plan = Plan.load()
    catalogue = Catalogue.load()
    known = catalogue.lookup()
    ROUTES = plan.routes

    for route in ROUTES:
        assert route.stores, f"{route.label} names no shop"
        assert all(i in known for i in route.stores), \
            f"{route.label} points at a retailer that does not exist"
        assert route.garment in garments(), f"{route.label} is for an unknown garment"
        assert not route.grade or route.grade in grades(), f"{route.label} has an unknown grade"
        assert not route.fit or route.fit in fits(), f"{route.label} has an unknown fit"
        assert not (route.fabric and route.family), \
            f"{route.label} constrains both an exact fabric and a family"

    def where(garment, grade="", fabric="", fit=""):
        found = route_for(Item(name="x", garment=garment, grade=grade,
                               fabric=fabric, fit=fit))
        return found.where if found else None

    assert where("T-shirt", grade="Heavyweight") == "Next", "heavyweight tee misrouted"
    assert where("T-shirt") == "Uniqlo", "the plain tee default did not apply"
    assert where("Shirt", grade="Dress", fabric="Oxford cotton") == "Charles Tyrwhitt", \
        "dress shirt misrouted"
    assert where("Shirt", fabric="Linen") == "Mango", "linen shirt misrouted"
    assert where("Trousers", fabric="Wool flannel") == "Marks and Spencer or Next", \
        "wool trousers misrouted"
    assert where("Trousers", fabric="Worsted wool") == "Marks and Spencer or Next", \
        "the family match does not cover the whole family"
    assert where("Trousers", fabric="Linen") == "Mango", "the wool route swallowed the linen one"
    assert where("Polo", grade="Knitted") == "Mango", "knitted polo misrouted"
    assert where("Polo") == "Uniqlo", "the plain polo default did not apply"
    # Trainers stopped carrying a grade, so one route covers them and the
    # condition does the work a second route used to.
    assert where("Trainers") == "Vinted", "trainers misrouted"

    # Nothing is inferred from spelling any more: a garment named "heavyweight"
    # but graded plain must follow its grade, not its name.
    misnamed = Item(name="heavyweight boxy tee", garment="T-shirt", grade="Everyday")
    assert route_for(misnamed).where == "Uniqlo", "the name overrode the grade"

    # The most constrained match wins, and an unconstrained route is the default.
    dress = route_for(Item(name="x", garment="Shirt", grade="Dress"))
    assert dress.precision == 1 and "grade" in why(Item(name="x", garment="Shirt",
                                                        grade="Dress"), dress), \
        "the route did not explain what it matched on"

    # A type whose routes all state constraints must return nothing when none
    # hold, rather than being pushed down the nearest one.
    assert route_for(Item(name="x", garment="Trousers", fabric="Cotton twill")) is None, \
        "an unmatched trouser was pushed down a route it does not belong to"
    assert "Loafers" in uncovered(garments()), "a known gap stopped being reported"
    return (f"{len(ROUTES)} routes over {len(plan.covered())} types, selected on grade, "
            f"fabric and fit; name no longer decides anything")


def check_plan_is_editable() -> str:
    """The plan is data, not a constant: it round trips and it can be changed."""
    from .inventory import garments, Item
    from .sourcing import DEFAULT_ROUTES, Plan, Route, route_for

    fresh = Plan.load()
    assert not fresh.path.is_file(), "loading wrote a file it should not have"
    assert len(fresh.routes) == len(DEFAULT_ROUTES), "defaults did not load"
    assert route_for(Item(name="x", garment="Loafers"), fresh) is None, \
        "the fixture already covers loafers, so this proves nothing"

    fresh.add(Route(label="Loafers", garment="Loafers", stores=["vinted"],
                    condition="Very Good condition or above"))
    fresh.save()
    again = Plan.load()
    assert again.path.is_file(), "save wrote nothing"
    assert len(again.routes) == len(DEFAULT_ROUTES) + 1, "the added route was lost"
    added = route_for(Item(name="x", garment="Loafers"), again)
    assert added and added.where == "Vinted", "the added route does not resolve"
    assert "Very Good" in added.condition, "the condition did not survive the round trip"
    assert all(r.id for r in again.routes), "a route was saved without an id"
    # Ids key the edit widgets, so duplicates take the whole page down.
    ids = [r.id for r in again.routes]
    assert len(ids) == len(set(ids)), f"duplicate route ids: {ids}"
    assert all(r.id for r in Plan.load().routes), "loaded defaults carry no id"

    # Editing an existing route must take effect, not be shadowed by the default.
    tee = next(r for r in again.routes if r.garment == "T-shirt" and not r.grade)
    tee.stores = ["marks"]
    again.save()
    assert route_for(Item(name="x", garment="T-shirt"), Plan.load()).where == \
        "Marks and Spencer", "editing a route had no effect"

    edited = Plan.load()
    edited.remove(added.id)
    edited.save()
    assert route_for(Item(name="x", garment="Loafers"), Plan.load()) is None, \
        "a deleted route still resolves"

    restored = Plan.load().restore_defaults()
    assert len(restored.routes) == len(DEFAULT_ROUTES), "restoring defaults did not"
    assert route_for(Item(name="x", garment="T-shirt"), restored).where == "Uniqlo", \
        "restoring did not undo the edit"
    assert "Loafers" in restored.uncovered(garments()), "coverage is not recomputed"
    return f"{len(DEFAULT_ROUTES)} defaults; add, edit, delete and restore all persist"


def check_restaging_uses_the_photograph() -> str:
    """An uploaded photograph is the subject, not a hint.

    Left on the description-led prompt the model treats the photograph as
    inspiration and produces a nicer garment than the one he owns, which is the
    one thing a wardrobe inventory must never do.
    """
    import io as _io

    from PIL import Image

    from . import shop as shop_mod
    from .inventory import Inventory, Item, save_photo

    class Upload:
        def __init__(self, name, data):
            self.name, self._data = name, data

        def getvalue(self):
            return self._data

    buffer = _io.BytesIO()
    Image.new("RGB", (900, 1200), (240, 233, 216)).save(buffer, "PNG")

    inventory = Inventory.load()
    item = inventory.add(Item(name="Cream camp-collar shirt", garment="Shirt",
                              colours=["Cream"], fabric="Cotton poplin",
                              description="Gold chain-stitch trim on the collar"))
    described = shop_mod.photo_prompt(item)
    assert not item.has_photo, "the fixture already has a photograph"

    item.photo = save_photo(item.id, Upload("shirt.png", buffer.getvalue()))
    inventory.save()
    restaged = shop_mod.restage_prompt(item)
    assert restaged != described, "the two prompts are the same"
    for phrase in ("EXACT GARMENT", "not a new garment", "same piece",
                   "Discard the background", "Cream", "Cotton poplin"):
        assert phrase in restaged, f"{phrase!r} missing from the restaging prompt"
    assert "chain-stitch" in restaged, "his own description did not survive"
    assert "seamless pure white" in restaged and "no person" in restaged, \
        "the restaging prompt lost the presentation rules"
    assert "Do not tidy it" in restaged, "nothing stops the model improving the garment"

    # And the right prompt must actually be the one that goes out.
    seen: dict[str, object] = {}

    def stub(prompt, *, out_prefix, reference_images=None, count=1, settings=None):
        seen["prompt"], seen["refs"] = prompt, list(reference_images or [])
        out_prefix.parent.mkdir(parents=True, exist_ok=True)
        target = out_prefix.with_suffix(".png")
        Image.new("RGB", (64, 96), (200, 150, 120)).save(target, "PNG")
        return [target]

    real = shop_mod.generate_images
    shop_mod.generate_images = stub
    try:
        shop_mod.generate_photo(item)
        assert "EXACT GARMENT" in seen["prompt"], "a photographed garment was described, not restaged"
        assert seen["refs"] == [Path(item.photo)], "the photograph was not sent as a reference"

        bare = Item(name="Camel overcoat", garment="Overcoat", colours=["Camel"])
        shop_mod.generate_photo(bare)
        assert "EXACT GARMENT" not in seen["prompt"], "a garment with no photo was restaged"
        assert not seen["refs"], "a reference was sent for a garment with no photograph"
    finally:
        shop_mod.generate_images = real
    return "photographed garments are restaged from the photo, the rest drawn from words"


def check_example_links() -> str:
    """A wanted piece can carry one specific thing online, and a sale rule."""
    from streamlit.testing.v1 import AppTest

    from .inventory import Inventory, Item
    from .retailers import Catalogue, match_url
    from .sourcing import Plan

    catalogue = Catalogue.load()
    assert match_url("https://www.uniqlo.com/uk/en/products/E1", catalogue).name == "Uniqlo", \
        "a Uniqlo link is not recognised as Uniqlo"
    assert match_url("https://shop.mango.com/gb/en/p/1", catalogue).name == "Mango", \
        "a subdomain is not matched to its shop"
    assert match_url("https://example.com/x", catalogue) is None, "an unknown host matched"
    assert match_url("not a url", catalogue) is None, "a non-url matched"

    inventory, _ = _seeded()
    trousers = next(i for i in inventory.items if i.name == "Grey flannel trousers")
    trousers.link = "https://www.uniqlo.com/uk/en/products/E459576-000"
    trousers.wait_for_sale = True
    inventory.update(trousers)
    inventory.save()

    back = Inventory.load().by_id(trousers.id)
    assert back.has_link and back.link_host == "uniqlo.com", \
        f"the link did not survive: {back.link!r}"
    assert back.wait_for_sale, "the sale rule did not survive"
    assert not Item(link="uniqlo.com/x").has_link, "a bare host counts as a link"
    assert Item(link="").link_host == "", "an empty link has a host"

    page = AppTest.from_file(str(APP_FILE), default_timeout=180)
    page.query_params["item"] = trousers.id
    page = page.run()
    assert not page.exception, f"the product page raised: {page.exception[0].value}"
    body = "\n".join(m.value for m in page.markdown)
    assert "One online" in body, "the saved example is not shown"
    assert back.link in body, "the link itself is missing"
    assert "Uniqlo" in body, "the page does not say which shop the link goes to"
    assert "Only reduced" in body or "only reduced" in body, \
        "the sale rule is not shown on the page"
    return f"a {back.link_host} link kept on a wanted piece, marked only-reduced"


def check_product_prompts() -> str:
    """The product shot must ask for the garment alone, and the copy for his size."""
    from .inventory import Item
    from .profile import Profile
    from .shop import copy_prompt, photo_prompt, size_line, to_buy
    from .seed import seed_all

    item = Item(id="camel", name="Camel wool overcoat", garment="Overcoat",
                colours=["Camel"], fabric="Wool melton", status="aspirational")
    shot = photo_prompt(item)
    for phrase in ("Camel", "Wool melton", "overcoat", "no person", "seamless pure white"):
        assert phrase in shot, f"{phrase!r} missing from the product shot prompt"
    assert "ghost mannequin" in shot.lower(), "no ghost mannequin instruction"

    profile = Profile.load()
    words = copy_prompt(profile, item)
    assert "Wool melton" in words, "the garment did not reach the copy"
    assert "£" not in words, "a price crept into the product copy"
    assert profile.subject.height_metric in words, "his proportions did not reach the copy"
    assert "Chest:" in words, "the size targets did not reach the copy"
    assert size_line(profile, item), "no size line for a coat"

    seed_all()
    from .inventory import Inventory
    listed = to_buy(Inventory.load())
    assert listed and all(i.status == "aspirational" for i in listed), "the list is not wanted-only"
    assert listed == sorted(listed, key=lambda i: (not i.starred, i.name or i.garment)), \
        "list not starred-first then alphabetical"
    return f"{len(listed)} on the list, prompts carry cloth, price and size"


# --- Guide revisions -------------------------------------------------------

def check_guide_edit_and_versions() -> str:
    """Hand edits write, and never lose what they replaced."""
    from . import paths, revisions
    paths.guide().write_text("# Style Guide\n\n## The thesis\n\nOriginal words.\n")

    revisions.save_edit("# Style Guide\n\n## The thesis\n\nEdited by hand.")
    assert "Edited by hand" in paths.guide().read_text(), "the edit did not write"
    history = revisions.versions()
    assert len(history) == 1, f"the replaced version was not kept: {len(history)}"
    assert "Original words" in history[0].path.read_text(), "the wrong version was kept"

    revisions.save_edit("# Style Guide\n\n## The thesis\n\nEdited by hand.")
    assert len(revisions.versions()) == 1, "an identical save made a pointless version"

    revisions.restore(history[0])
    assert "Original words" in paths.guide().read_text(), "restore did not put it back"
    assert len(revisions.versions()) == 2, "restoring did not keep the current version"
    return f"edit, dedupe, restore; {len(revisions.versions())} versions kept"


# --- App ----------------------------------------------------------------------

def _render(page: str = ""):
    """Render one page of the app. Empty means whichever the app opens on.

    The app used to draw all ten tabs on every run, so any check could read any
    tab's markdown by accident. It renders one page now, which is faster and
    honest, but it means a check has to say which page it is talking about.
    """
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(APP_FILE), default_timeout=180)
    if page:
        app.query_params["page"] = page
    app = app.run()
    if app.exception:
        raise AssertionError(f"{page or 'the opening page'} raised: {app.exception[0].value}")
    return app


def _every_page():
    """Every page rendered, as {slug: all its markdown}."""
    import importlib
    pages = importlib.import_module("wardrobe.app").PAGES
    return {slug: "\n".join(m.value for m in _render(slug).markdown) for slug, _ in pages}


def check_a_look_is_checked_before_it_is_kept() -> str:
    """A generated look is shown back to Gemini and rejected if it is not him.

    An image model asked for a man in named clothes on white will usually give
    you one and occasionally give you a different man in a kitchen. Nothing
    downstream can tell: a PNG is a PNG. So each picture goes back with the
    references it was built from and is asked three questions, and a failure is
    corrected rather than kept.

    The judging itself needs the network. What is checked here is the reading of
    the verdict, what the correction says, and that the loop stops.
    """
    from unittest.mock import patch
    from . import verify

    passed = verify._read('{"face":{"ok":true,"why":"same man"},'
                          '"background":{"ok":true,"why":"empty white"},'
                          '"garments":{"ok":true,"why":"as photographed"}}')
    assert passed.ok and not passed.failures, "a clean verdict was read as a failure"

    # Anything unclear is a failure, and the reason survives to the page.
    mixed = verify._read('prose first {"face":{"ok":false,"why":"a different man"},'
                         '"background":{"ok":false,"why":"a kitchen"},'
                         '"garments":{"ok":true,"why":"fine"}} and after')
    assert not mixed.ok, "a picture of a different man passed"
    assert mixed.failures == ["face", "background"], f"read {mixed.failures}"
    assert "different man" in mixed.summary() and "kitchen" in mixed.summary(), \
        "the reason for rejecting it was lost"

    # A missing key is a failure, never a silent pass.
    assert not verify._read("{}").ok, "an empty verdict passed"
    try:
        verify._read("no json here at all")
    except Exception:
        pass
    else:
        raise AssertionError("unreadable judging was treated as a pass")

    # The correction names only what was wrong, or the model is told to redo
    # the parts that were already right.
    fix = mixed.correction("plain seamless pure white, empty")
    assert "face is wrong" in fix.lower() and "background is wrong" in fix.lower()
    assert "garments are wrong" not in fix.lower(), "it was told to change what was right"
    assert "no furniture" in fix and "no visible floor" in fix, \
        "the correction does not say what an empty background means"
    # A contact shadow under the feet is what a studio photograph looks like.
    # Forbidding it made the check unpassable on a standing full-length shot.
    assert "contact shadow directly under his feet is fine" in fix, \
        "the correction still forbids the shadow every studio photograph has"
    # The positions must be stated, and stated correctly: the picture being
    # corrected goes first, so the man is the second image.
    assert "SECOND image is the man" in fix, "the correction does not say where the man is"
    assert "reference image 1 is the man" not in fix.lower(), \
        "the correction points at the failed picture for the face"

    only_clothes = verify._read('{"face":{"ok":true,"why":""},'
                                '"background":{"ok":true,"why":""},'
                                '"garments":{"ok":false,"why":"wrong coat"}}')
    fix = only_clothes.correction()
    assert "garments are wrong" in fix.lower() and "face is wrong" not in fix.lower(), \
        "a clothing failure asked for the face to be redrawn"

    # The loop: it corrects, it stops, and it hands back nothing rather than a
    # picture that never passed.
    drawn: list[Path] = []

    def draw(prompt, *, out_prefix, reference_images=None, count=1, settings=None):
        from PIL import Image as _Image
        out_prefix.parent.mkdir(parents=True, exist_ok=True)
        target = out_prefix.with_suffix(".png")
        _Image.new("RGB", (24, 32), (200, 200, 200)).save(target, "PNG")
        drawn.append(target)
        return [target]

    verdicts = iter([mixed, mixed, passed])
    with patch.object(verify, "generate_images", draw), \
         patch.object(verify, "inspect", lambda *a, **k: next(verdicts)):
        picture, history = verify.ensure(
            "a look", out_prefix=paths.looks() / "probe",
            portrait=paths.looks() / "probe.png", garment_photos=[],
            garments=["A shirt"], attempts=3)
    assert picture is not None, "a picture that finally passed was thrown away"
    assert len(history) == 3, f"the loop ran {len(history)} times, not 3"
    assert history[-1].report.ok and history[0].corrected is False, "history is wrong"
    assert history[1].corrected and history[2].corrected, "corrections not marked"

    never = iter([mixed] * 9)
    with patch.object(verify, "generate_images", draw), \
         patch.object(verify, "inspect", lambda *a, **k: next(never)):
        picture, history = verify.ensure(
            "a look", out_prefix=paths.looks() / "probe2",
            portrait=paths.looks() / "probe.png", garment_photos=[],
            garments=["A shirt"], attempts=3)
    assert picture is None, "a look that never passed was handed back anyway"
    assert len(history) == 3, f"the loop did not stop: {len(history)} attempts"
    return "verdict read, correction names only the failures, loop corrects then stops"


def check_every_garment_is_shown_to_the_model() -> str:
    """The pieces of an outfit go to the image model as pictures, not as words.

    They always did, but only the uploaded photograph counted, so a garment that
    had been drawn rather than photographed contributed nothing and the model
    invented it. The generated shot is the better reference anyway: the garment
    alone on white, where the original usually has a bedroom in it.

    And the ordering function that decides what to drop when there are too many
    was written, imported, and never called. Both generators used a plain list
    in item order instead, so which piece got dropped was arbitrary.
    """
    from .inventory import Inventory, Item
    from .outfits import CARRIES_THE_LOOK, REFERENCE_LIMIT, reference_items, reference_photos

    inventory, _ = _seeded()

    # A garment with only a drawn shot must still be shown.
    drawn = paths.products() / "drawn.png"
    drawn.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image as _Image
    _Image.new("RGB", (40, 60), (200, 200, 200)).save(drawn, "PNG")
    only_drawn = Item(name="Drawn only", garment="Shirt", category="Top",
                      product_photo=str(drawn))
    assert only_drawn.has_reference, "a garment with only a catalogue shot is invisible"
    assert only_drawn.reference_photo == drawn, "the catalogue shot is not used"

    # With both, the catalogue shot wins: it is the garment on white and nothing else.
    shot = paths.photos() / "snap.jpg"
    shot.parent.mkdir(parents=True, exist_ok=True)
    _Image.new("RGB", (40, 60), (90, 60, 40)).save(shot, "JPEG")
    both = Item(name="Both", garment="Shirt", category="Top",
                photo=str(shot), product_photo=str(drawn))
    assert both.reference_photo == drawn, "the bedroom photograph beat the catalogue shot"

    # Nothing at all means nothing, never a path that is not there.
    assert Item(name="Bare", garment="Shirt").reference_photo is None, \
        "a garment with no picture produced one"
    assert Item(name="Ghost", garment="Shirt", photo="/nowhere.jpg").reference_photo is None, \
        "a path that does not exist was offered as a reference"

    # The ones that carry the look go first, and what will not fit is returned
    # rather than quietly discarded.
    made = [Item(name=c, garment="Shirt", category=c, product_photo=str(drawn))
            for c in ("Accessory", "Shoes", "Top", "Outerwear", "Bottom",
                      "Accessory", "Accessory")]
    shown, dropped = reference_items(made)
    assert len(shown) == REFERENCE_LIMIT, f"showed {len(shown)}, not {REFERENCE_LIMIT}"
    assert [i.category for i in shown[:4]] == ["Outerwear", "Top", "Bottom", "Shoes"], \
        f"the pieces that carry the look are not first: {[i.category for i in shown]}"
    assert dropped and all(i.category == "Accessory" for i in dropped), \
        f"something other than an accessory was dropped: {[i.category for i in dropped]}"
    assert len(shown) + len(dropped) == len(made), "a garment vanished between the two halves"
    assert set(CARRIES_THE_LOOK) >= {"Outerwear", "Top", "Bottom", "Shoes"}, \
        "the ordering no longer covers the pieces that carry a look"

    # Under the limit, nothing is dropped and every piece is shown.
    few = made[:3]
    shown, dropped = reference_items(few)
    assert not dropped and len(shown) == 3, "a small outfit lost a piece"
    assert reference_photos(few) == [i.reference_photo for i in shown], \
        "the paths and the items disagree"

    # The function is actually called now, by both generators.
    source = APP_FILE.read_text()
    assert "reference_items(items)" in source, "the generator does not use the ordering"
    assert "reference_photos(items)" in source, "the variation panel does not use the ordering"
    assert "photos[:4]" not in source, "a generator still re-slices the references itself"
    assert "for i in items if i.has_photo" not in source, \
        "a generator still looks only at uploaded photographs"
    return (f"every piece with a picture is shown, up to {REFERENCE_LIMIT}, "
            "catalogue shot first, and what will not fit is named")


def check_changing_garment_changes_the_form() -> str:
    """Pick a different garment and the form beneath must follow it.

    The sizing scheme is a keyed Streamlit widget, so it kept its own value
    across a rerun. Almost every garment also allows Alpha, so changing a shirt
    to a trouser left the box still saying Alpha and still asking for one alpha
    size: the form looked frozen. Shoes hid it, because they allow a single
    scheme and so draw no box at all.
    """
    from streamlit.testing.v1 import AppTest
    inventory, _ = _seeded()
    item = next(i for i in inventory.items if i.garment == "Shirt")
    # The bug needs the scheme the two garments share. A shirt labelled by its
    # collar switches to a trouser cleanly by accident, because "Collar and
    # sleeve" is not a trouser scheme and the fallback picks the right one. It
    # is a shirt labelled M that goes wrong, because M is a trouser size too.
    item.scheme = "Alpha"
    inventory.update(item)
    inventory.save()
    key = f"e-{item.id}"

    app = AppTest.from_file(str(APP_FILE), default_timeout=180)
    app.query_params["page"] = "inventory"
    app = app.run()
    assert not app.exception, f"the inventory raised: {app.exception[0].value}"

    def boxes(page) -> set[str]:
        keys = [w.key for w in page.selectbox if w.key and w.key.startswith(key)]
        keys += [w.key for w in page.text_input if w.key and w.key.startswith(key)]
        return {k.split(f"{key}-s-")[1] for k in keys if k.startswith(f"{key}-s-")}

    def choose(page, garment):
        return next(w for w in page.selectbox if w.key == f"{key}-garment") \
            .set_value(garment).run()

    wanted = {
        "Trousers": {"waist", "leg"},
        "Blazer": {"chest", "length"},
        "Derbies": {"uk", "width"},
        "T-shirt": {"alpha"},
        "Shirt": {"collar", "sleeve"},
    }
    for garment, expected in wanted.items():
        app = choose(app, garment)
        assert not app.exception, f"choosing {garment} raised: {app.exception[0].value}"
        got = boxes(app)
        assert got == expected, f"{garment} asks for {sorted(got)}, wanted {sorted(expected)}"

    # The overlap that caused it: both allow Alpha, and the shirt's scheme must
    # not survive into the trouser.
    from .vocabulary import current
    catalogue = current()
    shirt = next(g for g in catalogue.garments if g.name == "Shirt")
    trouser = next(g for g in catalogue.garments if g.name == "Trousers")
    assert "Alpha" in shirt.schemes and "Alpha" in trouser.schemes, \
        "the overlap this guards against has gone; the check needs rethinking"
    assert shirt.schemes[0] != trouser.schemes[0], "the two now share a first scheme"

    app = choose(app, "Trousers")
    scheme = next(w for w in app.selectbox if w.key == f"{key}-scheme")
    assert scheme.value == trouser.schemes[0], \
        f"a trouser opened as {scheme.value!r}, not {trouser.schemes[0]!r}"
    return "garment drives the scheme and the size boxes, across five garments"


def check_no_widget_fights_its_own_key() -> str:
    """A keyed text box must not also be handed a constant default.

    `st.text_input("Search", "", key="inv-q")` re-applies that empty string on
    every rerun, so what you typed was thrown away before the filter ever saw
    it: the wardrobe search accepted a word, reran, and still said 25 of 25.
    It was invisible to the suite because AppTest sets a widget's value directly
    and never goes through the default at all.

    A default that is computed is fine, and sometimes necessary: the palette form
    fills the name from whichever colour was picked. It is the constant that
    fights the key, because it can never be anything but what it was.
    """
    import ast as _ast

    # Only the text widgets. st.number_input takes the minimum second and the
    # value fourth, so reading args[1] there flags every bounded number on the
    # page, and a number with a constant default is usually what was meant.
    WIDGETS = {"text_input", "text_area"}
    # A keyed selection widget must not also be told which option to select.
    # The navigation carried both and Streamlit settled the argument with an
    # extra rerun that aborted the script partway, so a search box further down
    # the page lost what had been typed into it. Reaching the wardrobe by
    # clicking the navigation left its search unable to hold a word; reaching it
    # by URL was fine, which is why it looked intermittent.
    SELECTORS = {"radio", "selectbox", "multiselect", "select_slider"}
    offences: list[str] = []
    for source in sorted(Path(__file__).parent.glob("*.py")):
        tree = _ast.parse(source.read_text())
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.Call):
                continue
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if name not in WIDGETS:
                continue
            keyed = any(k.arg == "key" for k in node.keywords)
            if not keyed:
                continue
            given = node.args[1] if len(node.args) > 1 else next(
                (k.value for k in node.keywords if k.arg == "value"), None)
            if isinstance(given, _ast.Constant) and given.value in ("", None, 0):
                offences.append(f"{source.name}:{node.lineno}")

    # The navigation only. A form field given both a key and the item's current
    # value is fine: a form does not rerun per widget, so the two never argue.
    # It is the navigation that reruns on every click, and it carried both.
    import wardrobe.app as _app
    source = _ast.parse(Path(_app.__file__).read_text())
    nav = next(n for n in _ast.walk(source)
               if isinstance(n, _ast.FunctionDef) and n.name == "navigation")
    for node in _ast.walk(nav):
        if isinstance(node, _ast.Call) and getattr(node.func, "attr", "") == "radio":
            named = {k.arg for k in node.keywords}
            assert "key" in named, "the navigation radio lost its key"
            assert "index" not in named, (
                "the navigation radio carries both a key and an index; Streamlit "
                "settles that with an extra rerun that aborts the script partway, "
                "and a search box further down the page loses what was typed")
            assert "on_change" not in named, (
                "the navigation writes the URL from a callback again; that reruns "
                "the script before the page body is drawn")
            break
    else:
        raise AssertionError("the navigation no longer draws a radio")

    # The address bar is synced after the page body has drawn, not while the
    # sidebar is drawing. Writing it early reruns the script before the widgets
    # below exist and Streamlit discards their state.
    body = Path(_app.__file__).read_text()
    assert "remember_page()" in body, "the URL is no longer kept in step with the page"
    assert body.index("draw[here]()") < body.index("    remember_page()\n"), \
        "the URL is written before the page is drawn"
    assert not offences, (
        "keyed widgets handed a constant default, which wipes what is typed: "
        + ", ".join(offences))

    # And the thing it broke, end to end, on the page it broke on.
    from streamlit.testing.v1 import AppTest
    inventory, _ = _seeded()
    target = inventory.items[0]
    word = (target.name or target.garment).split()[0]

    app = AppTest.from_file(str(APP_FILE), default_timeout=180)
    app.query_params["page"] = "inventory"
    app = app.run()
    assert not app.exception, f"the inventory raised: {app.exception[0].value}"
    box = next((w for w in app.text_input if w.key == "inv-q"), None)
    assert box is not None, "the wardrobe search box has gone"
    searched = box.set_value(word).run()
    assert not searched.exception, f"searching raised: {searched.exception[0].value}"
    assert next(w for w in searched.text_input if w.key == "inv-q").value == word, \
        "the search box did not keep what was typed"

    # What the box holds after typing is the whole of it. If a constant default
    # is re-applied on the rerun this is empty, the filter sees nothing, and the
    # page reports every garment as a match. Counting rendered cards was tried
    # and measures nothing: the seeded scratch home draws no grid at all.
    kept = next(w for w in searched.text_input if w.key == "inv-q").value
    assert kept == word, f"the search box held {kept!r} after typing {word!r}"

    filtered = inventory.filter(query=word)
    assert 0 < len(filtered) < len(inventory.items), \
        f"the fixture word {word!r} does not narrow anything, so this proves little"
    return (f"no keyed widget carries a constant default, and the box keeps "
            f"{word!r}, which narrows {len(inventory.items)} to {len(filtered)}")


def check_no_page_is_a_dead_end() -> str:
    """Every page can be left without editing the URL.

    The standalone views draw no sidebar, because they were built for a second
    monitor on the assumption they would always open in a new tab. Opened in the
    same one they had no navigation at all: the only way out was a small link at
    the foot of the page, and the answers index did not have even that. The way
    back also went to the front page, so returning from a garment did not put
    you in the wardrobe.
    """
    import importlib
    from streamlit.testing.v1 import AppTest
    app_mod = importlib.reload(importlib.import_module("wardrobe.app"))
    from .inventory import Inventory, Item
    from .outfits import Outfit, Outfits

    inventory, outfits = _seeded()
    item = inventory.items[0]
    outfit = outfits.outfits[0]

    views = {
        "item": item.id, "outfit": outfit.id, "garments": "all",
        "colours": "all", "shops": "all", "answer": "all",
    }
    for view, value in views.items():
        page = AppTest.from_file(str(APP_FILE), default_timeout=180)
        page.query_params[view] = value
        page = page.run()
        assert not page.exception, f"?{view}={value} raised: {page.exception[0].value}"
        body = "\n".join(m.value for m in page.markdown)
        assert "way-home" in body, f"?{view}={value} has no way back into the app"
        home = app_mod.HOME_FOR[view]
        assert f"./?page={home}" in body, \
            f"?{view}={value} does not return you to {home}"
        assert not [r for r in page.radio if r.label == "Section"], \
            f"?{view}={value} drew the app navigation as well"

    # Coming back from a garment lands in the wardrobe, not on the front page.
    assert app_mod.HOME_FOR["item"] == "inventory", "a garment does not lead back to the wardrobe"
    assert app_mod.HOME_FOR["outfit"] == "gallery", "an outfit does not lead back to the gallery"
    assert app_mod.HOME_FOR["colours"] == "colour", "the colours do not lead back to colour"

    # A link may say where it came from, and that wins.
    page = AppTest.from_file(str(APP_FILE), default_timeout=180)
    page.query_params["colours"] = "all"
    page.query_params["from"] = "shop"
    page = page.run()
    body = "\n".join(m.value for m in page.markdown)
    assert "./?page=shop" in body, "a stated origin was ignored"

    # And a nonsense origin falls back rather than producing a broken link.
    page = AppTest.from_file(str(APP_FILE), default_timeout=180)
    page.query_params["colours"] = "all"
    page.query_params["from"] = "not-a-page"
    page = page.run()
    body = "\n".join(m.value for m in page.markdown)
    assert "./?page=colour" in body, "a bad origin was not ignored"
    return f"{len(views)} standalone views, each with a way back to the page that owns it"


def check_page_survives_a_rerun() -> str:
    """Saving something must leave you where you were.

    Streamlit tabs reset to the first one on every rerun, so every save, drop and
    confirm bounced you back to the Style Guide from wherever you actually were.
    The page lives in the query string now, so a rerun keeps it and so does a
    browser refresh.
    """
    import importlib
    from streamlit.testing.v1 import AppTest
    app_mod = importlib.reload(importlib.import_module("wardrobe.app"))
    from .principles import Principle, Principles

    slugs = [slug for slug, _ in app_mod.PAGES]
    assert app_mod.current_page.__module__ == "wardrobe.app"

    book = Principles.load()
    book.add(Principle(text="Buy the shoulder.", reason="It cannot be altered."))
    book.offer([Principle(text="Wear more beige.", reason="No.")])
    book.save()

    page = AppTest.from_file(str(APP_FILE), default_timeout=180)
    page.query_params["page"] = "principles"
    page = page.run()
    assert not page.exception, f"the principles page raised: {page.exception[0].value}"

    binned = next(b for b in page.button if b.key == "bin-wear-more-beige")
    page = binned.click().run()
    assert not page.exception, f"binning raised: {page.exception[0].value}"
    landed = page.query_params["page"]
    landed = landed[-1] if isinstance(landed, list) else landed
    assert landed == "principles", f"a rerun moved us to {landed!r}"
    assert any("Principles" in m.value for m in page.markdown), \
        "the rerun drew a different page"

    # A refresh is a fresh run carrying only the URL, which is exactly this.
    again = AppTest.from_file(str(APP_FILE), default_timeout=180)
    again.query_params["page"] = "colour"
    again = again.run()
    assert any("Colour" in m.value for m in again.markdown), "a refresh lost the page"

    # An unknown or missing page falls back rather than raising.
    for junk in ("", "not-a-page", "1 · Style Guide"):
        stray = AppTest.from_file(str(APP_FILE), default_timeout=180)
        stray.query_params["page"] = junk
        stray = stray.run()
        assert not stray.exception, f"page={junk!r} raised: {stray.exception[0].value}"

    # Only one page renders now, which is the other half of the fix.
    everything = AppTest.from_file(str(APP_FILE), default_timeout=180)
    everything.query_params["page"] = "colour"
    everything = everything.run()
    body = "\n".join(m.value for m in everything.markdown)
    assert "Wardrobe Inventory" not in body, "the colour page also drew the inventory"
    return f"{len(slugs)} pages, the URL keeps the place through a rerun and a refresh"


def check_meter_never_overflows() -> str:
    """A target is not a limit, and the bar must not run off the page.

    Fourteen principles against a target of ten drew a fill 140% wide, which
    overshot the track and read as a rendering fault rather than as progress.
    """
    import re as _re
    from unittest.mock import patch
    from . import ui

    drawn: list[str] = []
    with patch.object(ui.st, "markdown", lambda html, **k: drawn.append(html)):
        for done, total in ((0, 10), (3, 10), (10, 10), (14, 10), (1, 0)):
            ui.meter(done, total, "Kept")
    widths = [float(m) for html in drawn
              for m in _re.findall(r"width:([\d.]+)%", html)]
    assert len(widths) == 5, f"the meter stopped drawing a fill: {widths}"
    assert max(widths) <= 100, f"the bar ran past the end of its track: {widths}"
    assert widths[:3] == [0.0, 30.0, 100.0], f"the bar stopped tracking: {widths[:3]}"
    assert "past the 10 aimed for" in drawn[3], "over target reads as 14 of 10"
    assert "of 10" in drawn[1] and "past" not in drawn[1], "under target reads wrong"
    assert widths[4] == 0.0, "a total of zero divided by zero"
    return "bar caps at 100%, and past the target says so instead of overflowing"


def check_no_shrugging_plurals() -> str:
    """No user-facing string may say "piece(s)".

    It appeared in nineteen places. The code always knew the count and still
    would not commit to a word, which is the written equivalent of a shrug.
    """
    import re as _re
    offences: list[str] = []
    for source in sorted(Path(__file__).parent.glob("*.py")):
        if source.name in ("checks.py", "text.py"):
            continue   # these two talk about the hack rather than commit it
        for n, line in enumerate(source.read_text().splitlines(), 1):
            if _re.search(r"\w\(s\)", line):
                offences.append(f"{source.name}:{n}: {line.strip()[:60]}")
    assert not offences, "strings that shrug at the plural: " + "; ".join(offences)

    from .text import count_of, plural
    assert plural(1, "piece") == "1 piece" and plural(2, "piece") == "2 pieces"
    assert plural(0, "piece") == "0 pieces", "zero takes the plural"
    assert plural(1, "foot", "feet") == "1 foot" and plural(3, "foot", "feet") == "3 feet"
    assert count_of(1, "outfit") == "outfit" and count_of(4, "outfit") == "outfits"
    return "no string shrugs at a plural; 1 piece, 2 pieces, 3 feet"


def check_nothing_looks_wrong() -> str:
    """Open every page in a real browser and look at it.

    The two style regressions that shipped were not broken selectors. Both
    matched something; they matched the wrong thing. Streamlit dropped
    data-baseweb, so four blocks silently stopped applying. And
    `[role="tablist"] + div`, written meaning "the highlight bar under the
    tabs", is the tab panel: it painted the whole garment catalogue brass.

    Reading the stylesheet cannot catch either. This drives Chromium instead,
    and fails on a page that raises, on text left in the framework's own font,
    on a page that scrolls sideways, and on any panel larger than a quarter of
    the screen painted one of the accent colours.
    """
    from . import browser
    with browser.server() as url:
        faults = browser.sweep(url)
    if faults:
        lines = [f"{view}: {'; '.join(bad)}" for view, bad in faults.items()]
        raise AssertionError("the app looks wrong on " + " | ".join(lines))
    return f"{len(browser.VIEWS)} views: no flooded panels, no unstyled text, no sideways scroll"


def check_no_dead_style_hooks() -> str:
    """Every selector in the stylesheet must hook onto something Streamlit emits.

    Streamlit moved its widgets off BaseWeb's data-baseweb attributes and onto
    data-testid. Three whole blocks of this stylesheet quietly stopped matching
    anything: the select and input boxes reverted to framework grey, and the
    sub-tabs drifted back to sentence-case body text. Nothing failed, it just
    slowly got uglier, which is the worst way for a bug to behave.

    A browser is the only thing that can prove a selector matches, and this suite
    does not run one. So this is the cheap half: no rule may lean on the attribute
    Streamlit has abandoned. WARDROBE_BROWSER=1 runs the other half.
    """
    import re as _re
    from . import ui
    sheets = {"CSS": ui.CSS, "SHOP_CSS": ui.SHOP_CSS}
    dead: list[str] = []
    for name, sheet in sheets.items():
        for line in sheet.splitlines():
            rule = line.split("{")[0].strip()
            if not rule or rule.startswith(("/*", "*", "@")):
                continue
            # data-baseweb survives only on tab-highlight, kept as a fallback
            # beside a live data-testid rule in the same selector list.
            if "data-baseweb" in rule and "data-testid" not in rule:
                dead.append(f"{name}: {rule[:70]}")
    assert not dead, "selectors leaning on the abandoned attribute: " + "; ".join(dead)

    # Hiding the toolbar wholesale takes the sidebar's way back with it: the
    # button that reopens a collapsed sidebar is a child of that toolbar, so
    # display:none on the bar left no route back short of reloading the page.
    for line in ui.CSS.splitlines():
        rule, _, body = line.partition("{")
        if '[data-testid="stToolbar"]' in rule and "stExpandSidebarButton" not in rule:
            assert "display: none" not in body, \
                "hiding the whole toolbar also hides the button that reopens the sidebar"
    assert '[data-testid="stExpandSidebarButton"]' in ui.CSS, \
        "nothing keeps the reopen-sidebar button visible"

    # Rerun and Clear cache live in the hamburger. Hiding it left no way to
    # clear a cache when the page looked stale, which is the same mistake as
    # hiding the whole toolbar.
    for line in ui.CSS.splitlines():
        rule, _, body = line.partition("{")
        if '[data-testid="stMainMenu"]' in rule and "display: none" in body:
            raise AssertionError("hiding the main menu also hides Rerun and Clear cache")

    # The hooks the layout actually depends on, spelled once so a rename is loud.
    for needed in ('[data-testid="stTab"]', '[data-testid="stSelectbox"]',
                   '[data-testid="stTextInputRootElement"]', '[data-testid="stAlertContainer"]',
                   '[data-testid="stRadioOption"]', '[data-testid="stSidebar"]',
                   '[data-testid="stExpandSidebarButton"]'):
        assert needed in ui.CSS, f"the stylesheet no longer targets {needed}"

    styled = len([l for l in ui.CSS.splitlines() if l.strip().endswith("{")])
    return f"{styled} rules, none leaning on data-baseweb, every widget hook present"


def check_no_prefilled_hints() -> str:
    """No text box suggests what to type in it.

    A placeholder in an empty box reads as content until you look twice, and a
    worked example in a questionnaire answers the question for the person who is
    supposed to be answering it.
    """
    import ast as _ast

    offences: list[str] = []
    for source in sorted(Path(__file__).parent.glob("*.py")):
        tree = _ast.parse(source.read_text())
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Call) and any(
                    kw.arg == "placeholder" for kw in node.keywords):
                offences.append(f"{source.name}:{node.lineno}")
    assert not offences, "text boxes with prefilled hints: " + ", ".join(offences)
    return "no box in the app suggests its own answer"


def check_typography() -> str:
    """Four faces, one job each, and every rule says which job it is doing.

    Mono used to carry labels, values and captions at once, which is why
    everything small looked the same weight and nothing told you what it was.
    Naming the roles is what stops that happening again by accident.
    """
    import re as _re

    from . import ui

    css = ui.CSS + ui.SHOP_CSS
    roles = {"display": "Bodoni Moda", "chrome": "Jost",
             "prose": "IBM Plex Sans", "data": "IBM Plex Mono"}

    for role, face in roles.items():
        assert f"--{role}:" in css, f"the {role} face is not defined"
        assert face in css.split(f"--{role}:", 1)[1].split(";", 1)[0], \
            f"--{role} is not set to {face}"
        assert f"var(--{role})" in css, f"nothing uses --{role}"

    # Every declaration goes through a role. A literal face name in a rule is a
    # rule that has quietly opted out of the system.
    literal = [line.strip() for line in css.splitlines()
               if "font-family" in line and "var(--" not in line]
    assert not literal, f"rules naming a face directly: {literal}"

    for fetched in ("Bodoni+Moda", "Jost", "IBM+Plex+Sans", "IBM+Plex+Mono"):
        assert fetched in css, f"{fetched} is never fetched"
    for gone in ("Karla", "Helvetica", "Arial", "Inter:"):
        assert gone not in css, f"{gone} lingers in the stylesheet"

    # Exactly one serif, and it is only ever a title.
    serif_rules = [b for b in _re.findall(r"\{([^{}]*)\}", css)
                   if "var(--display)" in b]
    assert serif_rules, "the serif is used nowhere"
    assert "var(--display)" not in css.split(".stTextArea", 1)[-1].split("}", 1)[0], \
        "the serif crept into a text input"

    # Headers take the serif; small furniture takes the geometric.
    for header in (".masthead h1", ".eyebrow", ".guide-body h1", ".guide-body h2",
                   ".docket .name", ".item .nm", ".answer-q", ".route-card .who"):
        block = css.split(header, 1)[1].split("}", 1)[0] if header in css else ""
        assert "var(--display)" in block, f"{header} is not set in the serif"
    for furniture in (".badge", ".look-cap", ".stat .k"):
        block = css.split(furniture, 1)[1].split("}", 1)[0] if furniture in css else ""
        assert "var(--chrome)" in block, f"{furniture} is not set in the chrome face"
    for figures in (".docket dd", ".tbl", ".stCode"):
        block = css.split(figures, 1)[1].split("}", 1)[0] if figures in css else ""
        assert "var(--data)" in block, f"{figures} is not monospaced"

    # Small text sits above boxes. With no bottom margin it presses against the
    # expander below it and reads as part of the box rather than a label on it.
    caption = css.split(".look-cap {", 1)[1].split("}", 1)[0]
    assert "margin-bottom" in caption, "small captions have no space beneath them"
    assert ":last-child" in css.split(".look-cap {", 1)[1][:600], \
        "the last caption in a card still pads the card"

    counts = {role: css.count(f"var(--{role})") for role in roles}
    assert all(counts.values()), f"a role is unused: {counts}"
    return " · ".join(f"{r} {n}" for r, n in counts.items())


def check_app_renders_empty() -> str:
    """Every page draws on an empty wardrobe, and the running order is the one
    the app is arguing for."""
    import importlib
    pages = importlib.import_module("wardrobe.app").PAGES
    titles = [title for _, title in pages]
    assert len(pages) == 11, f"expected ten pages and the workshop, got {len(pages)}"
    assert titles[1] == "Garment Catalogue", f"the dictionary is not second: {titles[1]}"
    assert titles[2] == "Wardrobe Inventory", "inventory does not follow the dictionary"
    assert titles[4] == "Colour", f"Colour is not the fifth page: {titles[4]}"
    # Where to Buy comes before Body Measurements: the shops decide the size
    # vocabulary, and the measurements only say which word to pick.
    assert titles[7] == "Where to Buy", "the shops do not come before the sizes"
    assert titles[8] == "Body Measurements", "body measurements did not get its own page"
    assert titles[9] == "Shopping Guide", "shopping guide is not the tenth"
    assert titles[10] == "Diagnostics", "the workshop is not last"
    for slug, title in pages:
        body = "\n".join(m.value for m in _render(slug).markdown)
        assert title in body, f"the {title} page does not name itself"
    return f"{len(pages)} pages all render empty: " + " · ".join(titles)


def check_app_renders_seeded() -> str:
    _seeded()
    from .seed import seed_answers, seed_principles
    seed_answers()
    seed_principles()
    from . import paths as _paths
    _paths.guide().write_text("# Style Guide\n\n## The thesis\n\nQuiet clothes.\n")
    body = _every_page()
    # Each probe has to appear on the page that owns it, not merely somewhere.
    for slug, probe in (("inventory", "Grey flannel trousers"),
                        ("gallery", "Saturday, Fulham Road"),
                        ("principles", "Keep the volume"),
                        ("shop", "Every missing piece"),
                        ("style-guide", "The thesis")):
        assert probe in body[slug], f"{probe!r} never made it onto the {slug} page"
    controls = len(_render("inventory").button)
    assert controls > 10, f"the seeded inventory has suspiciously few controls: {controls}"
    return f"{len(body)} pages rendered seeded, each probe on the page that owns it"


def check_diagnostics_renders() -> str:
    """The panel that clears data must itself render, or the escape hatch is gone.

    The checks and the sample seeder used to live on this tab and have gone: a
    button that runs the suite against the live wardrobe is a foot-gun, and they
    belong at a terminal where they run against a throwaway copy.
    """
    from . import reset
    _seeded()
    reset.snapshot()
    app = _render("diagnostics")
    page = "\n".join(m.value for m in app.markdown)
    assert "Data lives in" in page, "the diagnostics tab did not draw"
    labels = [c.label for c in app.checkbox]
    assert any("I am sure" in l for l in labels), "the confirmation checkbox is missing"
    assert any("Wardrobe inventory" in l for l in labels), "reset checkboxes missing"
    buttons = [b.label for b in app.button]
    for wanted in ("Clear selected", "Restore"):
        assert wanted in buttons, f"the {wanted!r} button is missing"
    for gone in ("Run checks", "Fill with sample data"):
        assert gone not in buttons, f"{gone!r} is back on the front end"
    assert "wardrobe-check" in page, "the tab does not say where the checks went"
    return f"{len(labels)} reset checkboxes, confirmation and restore; no test buttons"


def check_every_deletion_is_snapshotted() -> str:
    """Nothing may delete without leaving a copy first.

    Found by counting: the app had eleven destructive actions and exactly one of
    them took a snapshot. Deleting an item, an outfit, a route, a shop, a colour
    or a principle all destroyed data with no way back.
    """
    import ast as _ast

    source = (Path(__file__).parent / "app.py").read_text()
    tree = _ast.parse(source)
    lines = source.splitlines()

    destructive = []
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.Call) or not isinstance(node.func, _ast.Attribute):
            continue
        if node.func.attr in ("remove", "remove_garment", "remove_fabric",
                              "restore_defaults"):
            owner = getattr(node.func.value, "id", "")
            if owner in ("inventory", "outfits", "principles", "palette", "plan",
                         "catalogue", "vocab"):
                destructive.append(node.lineno)

    assert destructive, "no destructive calls found, so this check proves nothing"
    unguarded = []
    for line in destructive:
        window = "\n".join(lines[max(0, line - 8):line])
        if "reset_mod.before(" not in window:
            unguarded.append(f"{line}: {lines[line - 1].strip()}")
    assert not unguarded, "deletions with no snapshot first: " + "; ".join(unguarded)
    return f"{len(destructive)} destructive calls, every one snapshotted first"


def check_snapshot_store() -> str:
    """Reasons, targeting, selective restore, and a store that does not grow forever."""
    from . import paths, reset
    from .inventory import Inventory
    from .outfits import Outfits
    _seeded()
    paths.looks().mkdir(parents=True, exist_ok=True)
    (paths.looks() / "big.png").write_bytes(b"x" * 400_000)

    snap = reset.before("before deleting Camel wool overcoat", "inventory", "outfits")
    assert snap, "before() took nothing"
    assert snap.reason == "before deleting Camel wool overcoat", "the reason was lost"
    assert set(snap.keys) == {"inventory", "outfits"}, f"wrong keys: {snap.keys}"
    assert "looks" not in snap.keys, "a targeted snapshot swept in the image directory"
    assert snap.bytes < 200_000, f"targeted snapshot is {snap.bytes} bytes"
    assert "inventory" in snap.what and "outfit" in snap.what, "the summary is unhelpful"

    inventory = Inventory.load()
    before_count = len(inventory.items)
    inventory.remove(inventory.items[-1].id)
    inventory.save()
    outfits = Outfits.load()
    outfits.remove(outfits.outfits[0].id)
    outfits.save()

    # Restoring one part must leave the other alone.
    reset.restore(snap, ["inventory"])
    assert len(Inventory.load().items) == before_count, "selective restore did not work"
    assert len(Outfits.load().outfits) == len(outfits.outfits), \
        "restoring the inventory also restored the outfits"

    # And restoring is itself snapshotted, so a wrong restore is recoverable.
    assert any("before restoring" in s.reason for s in reset.snapshots()), \
        "restoring left no way back"

    reloaded = next(s for s in reset.snapshots() if s.reason == snap.reason)
    assert reloaded.keys == snap.keys, "the manifest did not survive a reload"

    # The store is capped.
    for n in range(reset.KEEP + 5):
        reset.before(f"filler {n}", "inventory")
    assert len(reset.snapshots()) <= reset.KEEP, \
        f"the store grew past its limit: {len(reset.snapshots())}"
    assert reset.store_size().endswith(("KB", "MB")), "the store size is unreadable"
    return (f"reasons kept, {snap.bytes // 1024} KB targeted not "
            f"{400_000 // 1024} KB, selective restore, capped at {reset.KEEP}")


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

    # The click path runs through verify now: it draws, judges, and corrects.
    # Stubbing gemini_image alone no longer intercepts it, and leaving the judge
    # unstubbed would put a real network call in the offline suite.
    from . import verify as verify_mod
    from .verify import Report

    def passes(*_args, **_kwargs) -> Report:
        judged["count"] += 1
        return Report(face=True, background=True, garments=True,
                      notes={"face": "same man", "background": "empty white",
                             "garments": "as photographed"})

    judged = {"count": 0}
    real = gemini_image.generate_images
    real_draw, real_judge = verify_mod.generate_images, verify_mod.inspect
    gemini_image.generate_images = stub
    verify_mod.generate_images = stub
    verify_mod.inspect = passes
    try:
        app = AppTest.from_file(str(APP_FILE), default_timeout=180)
        app.query_params["page"] = "generator"
        app = app.run()
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
        verify_mod.generate_images, verify_mod.inspect = real_draw, real_judge

    assert made.get("prompt"), "the handler never reached image generation"
    assert judged["count"] >= 1, "the look was saved without being checked"
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

    app = AppTest.from_file(str(APP_FILE), default_timeout=180)
    app.query_params["page"] = "gallery"
    app = app.run()
    assert not app.exception, f"one bad image killed the render: {app.exception[0].value}"
    page = "\n".join(m.value for m in app.markdown)
    assert "could not be read" in page, "no placeholder shown for the corrupt image"
    return "corrupt image degraded to a placeholder, page still rendered"


def check_scheme_list_has_no_duplicates() -> str:
    """No scheme may be another with an optional field taken away.

    There was a "Chest" as well as a "Chest and length", and the same for collar
    and waist. The second field was already optional, so the shorter one was the
    longer one with a box left blank: three concepts for nothing.
    """
    from .vocabulary import SCHEMES, SCHEME_ALIASES, Vocabulary, Garment

    keys = {name: {f.key for f in fields} for name, fields in SCHEMES.items()}
    for name, fields in keys.items():
        for other, others in keys.items():
            if name != other and fields and fields < others:
                optional = all(f.options and f.options[0] == "—"
                               for f in SCHEMES[other] if f.key in others - fields)
                assert not optional, (
                    f"{name} is {other} with an optional field removed, "
                    "which is the same scheme twice")

    for gone, survivor in SCHEME_ALIASES.items():
        assert gone not in SCHEMES, f"{gone} was merged away and is back"
        assert survivor in SCHEMES, f"{gone} points at a scheme that does not exist"

    # A catalogue written before the merge must still resolve.
    vocab = Vocabulary.load()
    vocab.garments.append(Garment(name="Cardigan", category="Top",
                                  schemes=["Chest", "Alpha"]))
    vocab.save()
    assert Vocabulary.load().schemes_for("Cardigan") == ("Chest and length", "Alpha"), \
        "an old scheme name did not migrate on load"
    return f"{len(SCHEMES)} schemes, none a duplicate of another, old names migrate"


def check_word_lists_are_guarded() -> str:
    """Removing a fit or a grade must not silently orphan the pieces using it."""
    from . import vocabulary as v
    from .inventory import Inventory, grades

    inventory, _ = _seeded()
    vocab = v.Vocabulary.load()
    in_use = {i.grade for i in inventory.items if i.grade}
    assert in_use, "the fixture has no graded pieces, so this proves nothing"

    # The page must be able to tell used from unused, or it cannot warn.
    counts = {g: sum(1 for i in inventory.items if i.grade == g) for g in vocab.grades if g}
    assert any(counts.values()), "no grade is counted as used"
    assert set(in_use) <= set(counts), "a grade in use is not counted"

    # And the orphan case has to be detectable after the fact. The grade is
    # picked from what the fixture actually uses, so trimming the sample data
    # cannot quietly turn this into a test of nothing.
    doomed = next(g for g, n in counts.items() if n)
    vocab.grades = [g for g in vocab.grades if g != doomed]
    vocab.save()
    orphaned = [i for i in Inventory.load().items if i.grade and i.grade not in grades()]
    assert orphaned, f"removing {doomed}, which {counts[doomed]} pieces use, left nothing"
    assert all(i.grade == doomed for i in orphaned), "the wrong pieces were orphaned"
    return (f"{len(counts)} grades counted against the wardrobe; "
            f"removing one in use leaves {len(orphaned)} detectable orphans")


def check_garment_catalogue() -> str:
    """The vocabularies are data, and the app reads them as they are now.

    They used to be module constants, so an edit would not show up until the
    process restarted. Everything downstream asks for the list on each rerun.
    """
    from streamlit.testing.v1 import AppTest

    from . import vocabulary
    from .inventory import categories, fabric_options, fits, garments, grades, size_scheme

    vocab = vocabulary.Vocabulary.load()
    assert not vocab.path.is_file(), "loading wrote a file it should not have"
    before = len(garments())
    assert before == len(vocab.garments), "the lookup disagrees with the file"
    assert "Blazer" in garments() and "Wool flannel" in fabric_options()

    vocab.add_garment(vocabulary.Garment(name="Cardigan", category="Top",
                                        schemes=["Alpha", "Chest and length"]))
    vocab.add_fabric(vocabulary.Fabric(name="Cotton lyocell", family="Cotton"))
    vocab.fits = ["", "Slim", "Regular", "Relaxed", "Oversized", "Cropped"]
    vocab.grades = ["", "Everyday", "Dress", "Souvenir"]
    vocab.save()

    # The cache keys on the file's timestamp, so an edit must be visible at once.
    assert "Cardigan" in garments(), "an added garment is not visible to the app"
    assert len(garments()) == before + 1, "the count did not move"
    assert "Cotton lyocell" in fabric_options(), "an added fabric is not visible"
    assert "Cropped" in fits() and "Souvenir" in grades(), "fits and grades did not move"
    assert "Cardigan" in categories()["Top"], "the new garment landed in no category"
    assert [f.label for f in size_scheme("Cardigan")] == ["Size"], \
        f"the new garment got the wrong scheme: {[f.label for f in size_scheme('Cardigan')]}"
    assert [f.label for f in size_scheme("Cardigan", "Chest and length")] == \
        ["Chest", "Length"], "the alternative scheme is not reachable"

    vocabulary.Vocabulary.load().restore_defaults()
    assert "Cardigan" not in garments(), "restoring defaults did not undo the edit"
    assert len(garments()) == before, "the count did not come back"

    # It is a page of the app, and also a page of its own for a second monitor.
    inside = AppTest.from_file(str(APP_FILE), default_timeout=180)
    inside.query_params["page"] = "garments"
    inside = inside.run()
    assert not inside.exception, f"the app raised: {inside.exception[0].value}"
    assert any("Garment Catalogue" in m.value for m in inside.markdown), \
        "the dictionary is not a page of the app"

    page = AppTest.from_file(str(APP_FILE), default_timeout=180)
    page.query_params["garments"] = "all"
    page = page.run()
    assert not page.exception, f"the garment catalogue raised: {page.exception[0].value}"
    # "No tabs" used to stand in for "not the whole app". The catalogue has its
    # own sections now, so the test has to say what it actually means.
    assert not [r for r in page.radio if r.label == "Section"], \
        "the standalone catalogue drew the app navigation"
    # Garment names sit in expander labels, not markdown, so both are read.
    body = "\n".join(
        [m.value for m in page.markdown]
        + [getattr(e, "label", "") for e in page.get("expander") or []]
        + [t.label for t in page.tabs]
    )
    for word in ("Blazer", "Grade", "Fit", "Garments", "Fabrics", "Colours"):
        assert word in body, f"{word} is missing from the catalogue"
    assert len(page.tabs) >= 4, "the catalogue is not split into sections"
    # Editing sits behind a toggle, so browsing is compact: the add forms are
    # not on the page until asked for.
    toggles = [t.label for t in page.toggle]
    assert "Change the garments" in toggles, "no way to reveal the garment editor"
    assert "Change the fabrics" in toggles, "no way to reveal the fabric editor"
    assert "Save fits and grades" not in [b.label for b in page.button], \
        "the free-text boxes are back"

    opened = AppTest.from_file(str(APP_FILE), default_timeout=180)
    opened.query_params["garments"] = "all"
    opened = opened.run()
    next(t for t in opened.toggle if t.label == "Change the garments").set_value(True)
    next(t for t in opened.toggle if t.label == "Change the fabrics").set_value(True)
    opened = opened.run()
    assert not opened.exception, f"opening the editors raised: {opened.exception[0].value}"
    buttons = [b.label for b in opened.button]
    assert "Add garment" in buttons and "Add fabric" in buttons, "no way to add"
    assert buttons.count("Add") >= 2, "no way to add a fit or a grade"
    assert any("Remove from the catalogue" in b for b in buttons), "no way to remove"
    return (f"{before} garments, {len(vocab.fabrics)} fabrics; tab 2 and a page "
            f"of its own, edits visible at once")


def check_shop_catalogue_opens() -> str:
    """The retailer catalogue is a page of its own, and it can be edited there."""
    from streamlit.testing.v1 import AppTest

    from .retailers import Catalogue
    catalogue = Catalogue.load()

    app = AppTest.from_file(str(APP_FILE), default_timeout=180)
    app.query_params["shops"] = "all"
    app = app.run()
    assert not app.exception, f"the shop catalogue raised: {app.exception[0].value}"
    assert not app.tabs, "the catalogue drew the whole app instead"
    page = "\n".join(m.value for m in app.markdown)
    for name in ("Vinted", "Uniqlo", "Mango", "Charles Tyrwhitt"):
        assert name in page, f"{name} is missing from the catalogue"
    import re as _re
    assert _re.search(r"\b\d+ routes?\b", page), \
        "the catalogue does not say how many routes name each shop"
    assert "route(s)" not in page, "the (s) plural hack is back"
    buttons = [b.label for b in app.button]
    assert "Add to the catalogue" in buttons, "no way to add a shop"
    assert any("Remove from the catalogue" in b for b in buttons), "no way to remove one"
    assert "Restore the default catalogue" in buttons, "no way back"
    return f"{len(catalogue.retailers)} shops, addable and removable, on their own page"


def check_colour_catalogue_opens() -> str:
    """The catalogue is a page of its own, and every colour on it has a name."""
    from streamlit.testing.v1 import AppTest

    from .palette import Colour, Palette, colour_names
    from .seed import seed_palette
    palette = seed_palette()
    palette.add(Colour(name="Adam's green", hex="#3F5E3A", role="Accent"))
    palette.save()

    app = AppTest.from_file(str(APP_FILE), default_timeout=180)
    app.query_params["colours"] = "all"
    app = app.run()
    assert not app.exception, f"the catalogue raised: {app.exception[0].value}"
    assert not app.tabs, "the catalogue drew the whole app instead"
    page = "\n".join(m.value for m in app.markdown)
    for name in ("Oxblood", "Petrol", "Cognac", "Navy"):
        assert name in page, f"{name} is missing from the catalogue"
    assert "Adam's green" in page, "a hand-named colour is missing"
    assert page.count("#") > len(colour_names()), "hex codes are not being shown"
    assert "In the palette" in page, "the catalogue does not say what is already used"
    return f"{len(colour_names())} named colours plus the hand-named ones, on their own page"


def check_outfit_page_and_comparison() -> str:
    """An outfit opens on its own page, varies from its own settings, and two
    can be put side by side with the difference named."""
    from streamlit.testing.v1 import AppTest

    from PIL import Image

    from .inventory import Inventory
    from .outfits import Outfit, Outfits, compare
    inventory, outfits = _seeded()

    def shot(name):
        target = paths.looks() / name
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 96), (190, 160, 130)).save(target, "PNG")
        return str(target)

    base = outfits.outfits[0]
    base.shot, base.background, base.extra = "Full length", "White studio", "sleeves rolled"
    base.images = [shot("base.png")]
    outfits.update(base)
    polo = next(i for i in inventory.items if i.name == "Ecru knit polo")
    child = outfits.add(Outfit(
        name=f"{base.name}, again", item_ids=[*base.item_ids[:-1], polo.id],
        images=[shot("child.png")], parent=base.id, shot="Three quarter",
        background="White studio", extra="sleeves rolled"))
    outfits.save()

    change = compare(base, child, inventory)
    assert not change.identical, "the comparison found no difference"
    assert polo.id in {i.id for i in change.added}, "the added piece was not spotted"
    assert change.removed, "the dropped piece was not spotted"
    assert any(s[0] == "Framing" for s in change.settings), "the changed framing was missed"
    assert not any(s[0] == "Background" for s in change.settings), \
        "an unchanged setting was reported as changed"
    assert {o.id for o in outfits.family(child)} == {base.id, child.id}, \
        "the family did not gather both"

    page = AppTest.from_file(str(APP_FILE), default_timeout=180)
    page.query_params["outfit"] = base.id
    page = page.run()
    assert not page.exception, f"the outfit page raised: {page.exception[0].value}"
    assert not page.tabs, "the outfit page drew the whole app"
    body = "\n".join(m.value for m in page.markdown)
    assert base.name in body, "the outfit name is missing"
    assert "Make a variation" in body, "there is no way to vary it"
    assert "The family" in body, "the family is not shown"
    assert "Full length" in body, "the settings it was generated with are not shown"
    labels = [w.label for w in page.selectbox]
    assert "Framing" in labels and "Compare this one with" in labels, \
        "the variation form did not preload"
    framing = next(w for w in page.selectbox if w.label == "Framing")
    assert framing.value == "Full length", \
        f"the variation started from the wrong framing: {framing.value}"

    side = AppTest.from_file(str(APP_FILE), default_timeout=180)
    side.query_params["compare"] = f"{base.id},{child.id}"
    side = side.run()
    assert not side.exception, f"the comparison raised: {side.exception[0].value}"
    assert not side.tabs, "the comparison drew the whole app"
    both = "\n".join(m.value for m in side.markdown)
    assert "What changed" in both, "the comparison does not say what changed"
    assert "Ecru knit polo" in both, "the added piece is not named"
    assert "Three quarter" in both, "the changed setting is not named"
    assert both.count("badge ok") or "new" in both, "the new piece is not marked"

    missing = AppTest.from_file(str(APP_FILE), default_timeout=180)
    missing.query_params["compare"] = base.id
    missing = missing.run()
    assert not missing.exception, "one id crashed the comparison"
    assert "Needs two outfits" in "\n".join(m.value for m in missing.markdown), \
        "a half comparison did not explain itself"
    return f"page, variation form preloaded, and a side by side saying: {change.summary}"


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
    assert [r for r in normal.radio if r.label == "Section"], \
        "the app stopped drawing its navigation without a query param"
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
    assert "Matched on" in page, "the page does not say why this route was chosen"
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
    (DATA, "Seeding twice changes nothing", check_seeding_is_idempotent),
    (DATA, "Suggestions are held apart from confirmed", check_suggestions_are_separate),
    (FIT, "Body is the ten takeable measurements", check_body_measurement_set),
    (FIT, "Body estimate is anatomically sane", check_body_estimate),
    (INVENTORY, "Phone photos upload as HEIC", check_heic_uploads_are_accepted),
    (FIT, "Body fat is worked out, not guessed", check_body_fat_is_worked_out),
    (FIT, "Arm length moves the sleeve", check_arm_length_moves_the_sleeve),
    (FIT, "Trouser spec keeps its leg opening", check_trouser_spec_survives_derived),
    (FIT, "Ease is added to the body measurement", check_ease_applied),
    (FIT, "Blazer sleeve leaves cuff showing", check_cuff_allowance),
    (FIT, "Trouser break and flat measurements", check_break_and_flat),
    (FIT, "Estimated and measured told apart", check_estimated_flag),
    (FIT, "Lean and athletic is not read as lean", check_build_matching),
    (INVENTORY, "Grade and fit only where they mean something",
     check_grade_and_fit_only_where_they_mean_something),
    (INVENTORY, "Garment colour comes from the catalogue",
     check_garment_colour_comes_from_the_catalogue),
    (INVENTORY, "Pattern is gone from items", check_pattern_removed),
    (INVENTORY, "Fabric comes from a fixed list", check_fabric_list),
    (INVENTORY, "UK sizes on labels, centimetres for measurements", check_uk_sizing),
    (INVENTORY, "Garments and categories alphabetical", check_alphabetical),
    (INVENTORY, "Every name dropdown is alphabetical", check_dropdowns_are_alphabetical),
    (INVENTORY, "Each garment has its own size scheme", check_size_schemes),
    (INVENTORY, "Size line hides blanks and junk", check_size_line_and_category),
    (INVENTORY, "Stale sizes pruned on re-classification", check_size_pruning),
    (INVENTORY, "Photo uploads are bounded and downscaled", check_photo_limits),
    (QUESTIONS, "Principles come in batches of five", check_principles_batching),
    (QUESTIONS, "Question bank is well formed", check_question_bank),
    (QUESTIONS, "Point allocation round trips", check_points_round_trip),
    (COLOUR, "Fifty named colours, all distinct", check_named_colours),
    (DATA, "An added garment gets its rules", check_added_garments_get_their_rules),
    (DATA, "Fabrics are filed by how they behave", check_fabric_families),
    (COLOUR, "Three roles, shoes exempt by slot", check_roles),
    (COLOUR, "Four seasonal palettes out of one", check_seasons),
    (COLOUR, "Colour arithmetic is sound", check_colour_arithmetic),
    (COLOUR, "Top colour must clear his skin", check_the_one_rule),
    (COLOUR, "Palette round trips", check_palette_round_trip),
    (SHOP, "The secondhand line is respected both ways", check_secondhand_rule),
    (SHOP, "Retailer catalogue is sound", check_retailer_catalogue),
    (SHOP, "The catalogue is editable and persists", check_catalogue_is_editable),
    (SHOP, "Cheap-buying tactics are specific", check_tactics),
    (SHOP, "The sourcing plan routes each garment", check_sourcing_routes),
    (SHOP, "The plan is editable and persists", check_plan_is_editable),
    (SHOP, "An uploaded photo is restaged, not described", check_restaging_uses_the_photograph),
    (SHOP, "A wanted piece keeps a link and a sale rule", check_example_links),
    (SHOP, "Product prompts carry cloth, price and size", check_product_prompts),
    (MATHS, "Plan opens with the best bundle", check_plan_shape),
    (MATHS, "Running totals are arithmetically right", check_plan_arithmetic),
    (MATHS, "Plan never buys what he owns", check_plan_never_buys_owned),
    (MATHS, "The plan minimises garments to find", check_plan_prefers_fewer_garments),
    (MATHS, "Leverage counts appearances and solo unlocks", check_leverage),
    (MATHS, "Wearability splits owned from to-buy", check_wearability),
    (MATHS, "An empty outfit is not wearable", check_empty_outfit_not_wearable),
    (MATHS, "Deleting a garment breaks its outfits", check_deleted_garment_breaks_outfit),
    (MATHS, "Retired pieces are never bought back", check_retired_never_bought),
    (PROMPTS, "His description reaches the prompt", check_description_reaches_the_prompt),
    (PROMPTS, "Subject reaches the image prompt", check_subject_in_prompt),
    (PROMPTS, "Outfit prompt carries garments and photo roles", check_outfit_prompt),
    (PROMPTS, "Guide prompt carries every answer", check_guide_prompt),
    (APP, "No text box prefills a suggestion", check_no_prefilled_hints),
    (APP, "No dead style hooks", check_no_dead_style_hooks),
    (BROWSER, "Every page looks right in a browser", check_nothing_looks_wrong),
    (APP, "The meter never overflows", check_meter_never_overflows),
    (APP, "Nothing shrugs at a plural", check_no_shrugging_plurals),
    (APP, "Typography is one system, not three", check_typography),
    (APP, "All tabs render empty", check_app_renders_empty),
    (APP, "A rerun leaves you on the same page", check_page_survives_a_rerun),
    (PROMPTS, "Every garment is shown to the model", check_every_garment_is_shown_to_the_model),
    (PROMPTS, "A look is checked before it is kept", check_a_look_is_checked_before_it_is_kept),
    (APP, "Choosing a garment reshapes the form", check_changing_garment_changes_the_form),
    (APP, "No widget fights its own key", check_no_widget_fights_its_own_key),
    (APP, "No page is a dead end", check_no_page_is_a_dead_end),
    (APP, "All tabs render with a full wardrobe", check_app_renders_seeded),
    (APP, "Diagnostics panels render", check_diagnostics_renders),
    (APP, "No function shadows an imported module", check_no_module_shadowing),
    (APP, "Generate look actually runs when clicked", check_generate_button_runs),
    (APP, "An unreadable image does not crash the page", check_unreadable_image_does_not_crash),
    (APP, "Guide edits keep what they replace", check_guide_edit_and_versions),
    (APP, "The colour catalogue opens on its own page", check_colour_catalogue_opens),
    (APP, "The retailer catalogue opens and edits", check_shop_catalogue_opens),
    (INVENTORY, "The garment catalogue is editable data", check_garment_catalogue),
    (INVENTORY, "No size scheme duplicates another", check_scheme_list_has_no_duplicates),
    (INVENTORY, "Fits and grades know what uses them", check_word_lists_are_guarded),
    (APP, "An outfit opens, varies and compares", check_outfit_page_and_comparison),
    (APP, "A saved answer opens on its own page", check_answer_view_opens),
    (APP, "A garment opens on its own product page", check_item_page_opens),
    (APP, "Wipe and restore round trip", check_reset_round_trip),
    (APP, "Every deletion is snapshotted first", check_every_deletion_is_snapshotted),
    (APP, "The backup store keeps reasons and restores in part", check_snapshot_store),
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
