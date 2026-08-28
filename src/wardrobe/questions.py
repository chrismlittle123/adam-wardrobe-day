"""The style-guide questionnaire.

Intent alone does not dress anybody. A man will tell you his philosophy is
Milanese tailoring and then wear the same grey hoodie for four years, so the
audit section asks what actually happens on a Tuesday rather than what he
believes on a Sunday. Questions marked `core` are the shorter path; the rest
deepen the guide.

Most questions take prose. One takes a budget of points, because asking someone
to rank practicality against beauty in a sentence gets you "both, really", and
making him spend a fixed twenty forces the trade-off into the open.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TEXT, POINTS = "text", "points"


@dataclass(frozen=True)
class Question:
    id: str
    prompt: str
    help: str = ""
    placeholder: str = ""
    core: bool = False
    lines: int = 3
    kind: str = TEXT
    buckets: tuple[str, ...] = ()
    points_total: int = 20


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    blurb: str
    questions: tuple[Question, ...]


SECTIONS: tuple[Section, ...] = (
    Section(
        "intent",
        "Intent",
        "What the clothes are meant to say, and to whom.",
        (
            Question(
                "says_what",
                "What do you want your wardrobe to say about you, and in which contexts?",
                "Split it by context if it changes: work, dinner, a date, a Sunday.",
                "At work: competent and unbothered. On a Saturday: like I have a life.",
                core=True, lines=5,
            ),
            Question(
                "never_look_like",
                "What do you never want to look like?",
                "The most useful question here. Naming the ditch keeps you out of it.",
                "Trying too hard. A finance man on his day off. Anything that looks like a costume.",
                core=True, lines=4,
            ),
            Question(
                "three_words",
                "Three words a stranger should use about you after meeting you.",
                "Not aspirational nouns. Adjectives someone would actually say out loud.",
                "Easy, sharp, warm.",
                core=True, lines=2,
            ),
            Question(
                "audience",
                "Whose opinion actually matters to you here?",
                "Be honest. Colleagues, strangers, a specific person, only yourself.",
                "",
                lines=2,
            ),
        ),
    ),
    Section(
        "taste",
        "Taste",
        "What he finds beautiful, regardless of whether he can pull it off yet.",
        (
            Question(
                "vibes_love",
                "What styles or vibes do you personally think look amazing?",
                "On anyone. Doesn't have to be realistic for you.",
                "Late-90s Milanese, soft-shouldered, unstructured. Also 70s tennis club.",
                core=True, lines=5,
            ),
            Question(
                "icons",
                "Any style icons who fit the vibe you're going for?",
                "People, characters, a specific photograph. Say what it is about them.",
                "Marcello Mastroianni. Not the suits, the ease. Also Paul Mescal's tailoring.",
                core=True, lines=4,
            ),
            Question(
                "stolen_outfit",
                "Describe one specific outfit you saw on someone else and wanted.",
                "A real one you remember. Detail matters more than accuracy.",
                "Man on the 22 bus: brown suede blouson, white tee, grey flannel trousers.",
                lines=4,
            ),
            Question(
                "world",
                "Which films, cities, eras or scenes are you drawn to?",
                "The mood board behind the mood board.",
                "Rome 1962. Wong Kar-wai. Old Italian football away kits.",
                lines=3,
            ),
            Question(
                "try_hard",
                "What do you find try-hard, dated, or just bad?",
                "Be rude. It sharpens everything else.",
                "Skinny jeans. Statement trainers. Anything with a big logo.",
                core=True, lines=3,
            ),
        ),
    ),
    Section(
        "audit",
        "The honest audit",
        "What is actually in the wardrobe and what actually gets worn. The gap between "
        "these two answers is the whole project.",
        (
            Question(
                "wrong_signal",
                "What's in your wardrobe that isn't saying what you want it to say?",
                "Name specific garments, not categories.",
                "The three black going-out shirts. A puffer that makes me look square.",
                core=True, lines=5,
            ),
            Question(
                "missing",
                "What's missing that could say it?",
                "Guesses are fine. This is the shopping list before it is a shopping list.",
                "A proper overcoat. Trousers that aren't jeans. One good brown shoe.",
                core=True, lines=5,
            ),
            Question(
                "actually_wear",
                "What do you actually reach for 80% of the time?",
                "The real wardrobe, not the aspirational one.",
                "Same three tees, dark jeans, white trainers. Every day.",
                core=True, lines=4,
            ),
            Question(
                "never_worn",
                "What have you bought and never worn? Why not?",
                "The why is the useful half. It predicts the next mistake.",
                "A patterned shirt. Bought it excited, felt like a costume the second I put it on.",
                core=True, lines=4,
            ),
            Question(
                "default_outfit",
                "Your 'can't be bothered' outfit, exactly as worn.",
                "The one that happens when you are late and it is raining.",
                "",
                lines=3,
            ),
            Question(
                "felt_great",
                "The last time you felt genuinely great in what you were wearing: what was it?",
                "Garment by garment if you can remember. This is the target.",
                "",
                core=True, lines=4,
            ),
            Question(
                "keepers",
                "Which pieces do you love and want to build around?",
                "The wardrobe gets built outwards from these, so be precise.",
                "The cream camp-collar shirt. A pair of mid-grey trousers that fit perfectly.",
                core=True, lines=4,
            ),
        ),
    ),
    Section(
        "life",
        "Life",
        "Where the clothes actually go. A wardrobe is built out of Tuesdays.",
        (
            Question(
                "normal_week",
                "Walk through a normal week. Where are you, and what are you doing?",
                "Office days, home days, gym, dinners, weekends. Rough proportions.",
                "Three days in the office, two at home, gym four times, dinner out twice a week.",
                core=True, lines=5,
            ),
        ),
    ),
    Section(
        "fit",
        "Body and fit",
        "The measurements live in the Shopping Guide. This is about how he likes cloth to sit.",
        (
            Question(
                "fit_preference",
                "How do you like things to fit?",
                "Close, relaxed, structured, soft. Where on your body does it matter most?",
                "Relaxed through the leg, close on the shoulder. Never tight on the arm.",
                core=True, lines=4,
            ),
            Question(
                "flatter",
                "What do you want clothes to do for your shape?",
                "Anything you want emphasised, anything you would rather they left alone.",
                "",
                core=True, lines=3,
            ),
            Question(
                "fit_problems",
                "Which fit problems do you keep hitting?",
                "The reason half the wardrobe does not get worn.",
                "Trousers fit the waist and swim on the thigh. Shirt sleeves always too long.",
                core=True, lines=4,
            ),
        ),
    ),
    Section(
        "colour",
        "Colour and cloth",
        "Warm medium-brown skin with a golden undertone carries warm colour easily and "
        "gets flattened by cold grey.",
        (
            Question(
                "palette_width",
                "Tight repeatable palette, or do you want range?",
                "A tight palette means everything combines. Range means more decisions daily.",
                "",
                core=True, lines=2,
            ),
            Question(
                "fabrics",
                "Fabrics you love, and fabrics you can't stand?",
                "Wool itch, synthetics, linen that creases, anything that needs babying.",
                "",
                lines=3,
            ),
        ),
    ),
    Section(
        "practical",
        "Money and reality",
        "The constraints that decide whether any of this happens.",
        (
            Question(
                "priorities",
                "You have 20 points. Spend them across practicality, comfort, aesthetics "
                "and cost, by how much each one matters to you.",
                "They must add up to 20, so something has to lose. That is the point: it "
                "settles every later argument between the beautiful thing and the sensible one.",
                core=True,
                kind=POINTS,
                buckets=("Practicality", "Comfort", "Aesthetics", "Cost"),
                points_total=20,
            ),
            Question(
                "upkeep",
                "How much ironing, hand-washing and dry-cleaning will you genuinely do?",
                "Answer with what you actually do, not what you intend to do.",
                "None. If it needs ironing it will not be worn.",
                core=True, lines=3,
            ),
        ),
    ),
)

ALL_QUESTIONS: tuple[Question, ...] = tuple(q for s in SECTIONS for q in s.questions)
BY_ID: dict[str, Question] = {q.id: q for q in ALL_QUESTIONS}


def section_of(question_id: str) -> Section | None:
    return next((s for s in SECTIONS if any(q.id == question_id for q in s.questions)), None)


# --- point questions ----------------------------------------------------------

def format_points(scores: dict[str, int]) -> str:
    """Store as readable prose so the file stays legible and the guide prompt
    can read it without a special case."""
    return ", ".join(f"{bucket} {value}" for bucket, value in scores.items())


def parse_points(answer: str, buckets: tuple[str, ...]) -> dict[str, int]:
    """Read the stored line back into the widget. Missing buckets come back zero."""
    found = {m.group(1).lower(): int(m.group(2))
             for m in re.finditer(r"([A-Za-z]+)\s*[:=]?\s*(\d+)", answer or "")}
    return {bucket: found.get(bucket.lower(), 0) for bucket in buckets}
