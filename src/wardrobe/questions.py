"""The style-guide questionnaire.

Five of these are the spine of the whole thing: what the wardrobe should say,
what is currently saying the wrong thing, what is missing, what looks amazing,
and who he is looking at. Those are marked `spine`.

The rest exist because intent alone does not dress anybody. A man will tell you
his philosophy is Milanese tailoring and then wear the same grey hoodie for four
years, so the audit and life sections ask what actually happens on a Tuesday.
Questions marked `core` are the shorter path; the rest deepen the guide.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    id: str
    prompt: str
    help: str = ""
    placeholder: str = ""
    core: bool = False
    spine: bool = False
    lines: int = 3


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
                core=True, spine=True, lines=5,
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
                core=True, spine=True, lines=5,
            ),
            Question(
                "icons",
                "Any style icons who fit the vibe you're going for?",
                "People, characters, a specific photograph. Say what it is about them.",
                "Marcello Mastroianni. Not the suits, the ease. Also Paul Mescal's tailoring.",
                core=True, spine=True, lines=4,
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
                core=True, spine=True, lines=5,
            ),
            Question(
                "missing",
                "What's missing that could say it?",
                "Guesses are fine. This is the shopping list before it is a shopping list.",
                "A proper overcoat. Trousers that aren't jeans. One good brown shoe.",
                core=True, spine=True, lines=5,
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
            Question(
                "shoes_owned",
                "Every pair of shoes you currently own.",
                "Shoes decide the outfit and everyone forgets to list them.",
                "White leather trainers, black Chelsea boots, running shoes, one dying pair of loafers.",
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
            Question(
                "work_code",
                "What is the dress code where you work, written and unwritten?",
                "The unwritten one is the real one.",
                "",
                core=True, lines=3,
            ),
            Question(
                "climate",
                "Which city, and what is the weather really like?",
                "Layering, rain, and how much of the year is grey.",
                "London. Grey and damp nine months of the year. Two good weeks in June.",
                core=True, lines=3,
            ),
            Question(
                "dreaded",
                "Which recurring occasions do you dread dressing for?",
                "Weddings, work drinks, meeting a partner's family, a nice restaurant.",
                "",
                core=True, lines=3,
            ),
            Question(
                "travel",
                "How much do you travel, and what do you pack?",
                "",
                "",
                lines=3,
            ),
        ),
    ),
    Section(
        "fit",
        "Body and fit",
        "The measurements are on the subject card. This is about how he likes cloth to sit.",
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
            Question(
                "details_fit",
                "Preferences on trouser break, rise, sleeve length, collar?",
                "Skip if you have no idea. The guide will make a recommendation instead.",
                "",
                lines=3,
            ),
        ),
    ),
    Section(
        "colour",
        "Colour and cloth",
        "Warm medium-brown skin with a golden undertone carries warm colour easily and "
        "gets flattened by cold grey. Worth knowing what he already believes.",
        (
            Question(
                "colours_good",
                "Which colours do you feel good in?",
                "",
                "Cream, olive, rust, navy. Anything warm.",
                core=True, lines=3,
            ),
            Question(
                "colours_never",
                "Which colours do you never wear, and why?",
                "",
                "Black near my face. Pastel anything. Cold light grey.",
                core=True, lines=3,
            ),
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
            Question(
                "pattern",
                "How much pattern can you actually live with?",
                "Solid only, subtle texture, stripe, or genuinely loud.",
                "",
                lines=2,
            ),
        ),
    ),
    Section(
        "picture",
        "The rest of the picture",
        "Style is not only cloth. Hair and hardware do half the work.",
        (
            Question(
                "grooming",
                "Hair, beard, glasses: current state and anything you're considering?",
                "",
                "",
                lines=3,
            ),
            Question(
                "jewellery",
                "Jewellery, watch, fragrance, tattoos. What do you wear every day?",
                "The things that never come off should be designed around, not ignored.",
                "Small gold stud, thin gold chain, both always on.",
                core=True, lines=3,
            ),
            Question(
                "outerwear_bags",
                "Coats and bags you own or want.",
                "In London the coat is what people actually see.",
                "",
                lines=3,
            ),
        ),
    ),
    Section(
        "practical",
        "Money and reality",
        "The constraint that decides whether any of this happens.",
        (
            Question(
                "budget",
                "Budget: roughly per piece, and overall for this project?",
                "A number changes the entire recommendation. Ranges are fine.",
                "Up to £200 a piece, more for a coat or shoes. Maybe £2,000 total over six months.",
                core=True, lines=3,
            ),
            Question(
                "buying_philosophy",
                "Few and expensive, or more and cheaper?",
                "",
                "",
                core=True, lines=2,
            ),
            Question(
                "secondhand",
                "Secondhand and vintage: yes, no, or depends?",
                "",
                "",
                lines=2,
            ),
            Question(
                "upkeep",
                "How much ironing, hand-washing and dry-cleaning will you genuinely do?",
                "Answer with what you actually do, not what you intend to do.",
                "None. If it needs ironing it will not be worn.",
                core=True, lines=3,
            ),
            Question(
                "brands",
                "Brands you already trust, and brands you would rather avoid?",
                "",
                "",
                lines=3,
            ),
            Question(
                "deadline",
                "Anything coming up you need to be dressed for?",
                "A wedding, a holiday, a new job. Deadlines set the order of the shopping list.",
                "",
                core=True, lines=3,
            ),
        ),
    ),
)

ALL_QUESTIONS: tuple[Question, ...] = tuple(q for s in SECTIONS for q in s.questions)
BY_ID: dict[str, Question] = {q.id: q for q in ALL_QUESTIONS}


def section_of(question_id: str) -> Section | None:
    return next((s for s in SECTIONS if any(q.id == question_id for q in s.questions)), None)
