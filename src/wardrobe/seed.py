"""A realistic wardrobe to test against.

Not lorem ipsum. The items are sized in each garment's own scheme, the outfits
overlap the way real outfits do, and the wanted pieces are arranged so the
shopping plan has something interesting to chew on: two outfits blocked by the
same pair of garments, one blocked by a single expensive coat. If the maths is
wrong, this data shows it.
"""

from __future__ import annotations

from .inventory import ASPIRATIONAL, Inventory, Item, category_for
from .outfits import Outfit, Outfits
from .philosophy import Answers
from .principles import CONFIRMED as prin_mod_CONFIRMED, Principle, Principles

# name, garment, colour, hex, fabric, sizes, wanted, grade, fit
# name, garment, colour, hex, fabric, sizes, wanted, grade, fit
ITEMS: tuple[tuple, ...] = (
    ("White cotton tee", "T-shirt", "white", "#F4F2ED", "Cotton jersey",
     {"alpha": "M"}, False, "Everyday", "Regular"),
    ("Cream camp-collar shirt", "Shirt", "cream", "#F2E9D8", "Cotton poplin",
     {"collar": '15.5"', "alpha": "M"}, False, "", "Regular"),
    ("Pale blue oxford", "Shirt", "pale blue", "#BFD3E6", "Oxford cotton",
     {"collar": '15.5"', "alpha": "M"}, False, "Dress", "Regular"),
    ("Dark indigo jeans", "Jeans", "indigo", "#2B3A4F", "Selvedge denim",
     {"waist": '31"', "leg": '32"'}, False, "Everyday", "Slim"),
    ("Navy merino crewneck", "Knitwear", "navy", "#26303F", "Merino wool",
     {"alpha": "M"}, False, "Everyday", "Regular"),
    ("White leather trainers", "Trainers", "white", "#EDEAE3", "Calf leather",
     {"uk": "9", "eu": "43", "width": "Standard"}, False, "Smart", "Regular"),
    ("Black Chelsea boots", "Boots", "black", "#1B1918", "Calf leather",
     {"uk": "9", "eu": "43", "width": "Standard"}, False, "Smart", "Regular"),
    ("Navy hopsack blazer", "Blazer", "navy", "#232C3B", "Wool hopsack",
     {"chest": "38", "length": "Regular", "eu": "48"}, False, "Smart", "Slim"),
    ("Steel dive watch", "Watch", "steel", "#9AA0A6", "", {"case": "40mm"}, False, "", ""),
    ("Brown leather belt", "Belt", "chocolate", "#5A3A22", "Calf leather",
     {"waist": '32"', "alpha": "M"}, False, "", ""),
    ("Grey flannel trousers", "Trousers", "mid grey", "#7A7A78", "Wool flannel",
     {"waist": '31"', "leg": '32"'}, True, "Smart", "Regular"),
    ("Brown suede loafers", "Loafers", "chocolate", "#6B4426", "Suede",
     {"uk": "9", "eu": "43", "width": "Standard"}, True, "Smart", "Regular"),
    ("Camel wool overcoat", "Overcoat", "camel", "#C19A6B", "Wool melton",
     {"chest": "38", "length": "Regular", "eu": "48"}, True, "Smart", "Regular"),
    ("Olive linen overshirt", "Overshirt", "olive", "#6B6B47", "Linen",
     {"alpha": "M"}, True, "Everyday", "Relaxed"),
    ("Ecru knit polo", "Polo", "ecru", "#E8DFC8", "Merino wool",
     {"alpha": "M"}, True, "Knitted", "Regular"),
)

# name, item names, tags, loved
LOOKS: tuple[tuple, ...] = (
    ("Saturday, Fulham Road", ("White cotton tee", "Dark indigo jeans",
                               "White leather trainers", "Steel dive watch"),
     ("weekend", "casual"), True),
    ("Office Tuesday", ("Pale blue oxford", "Grey flannel trousers",
                        "Brown suede loafers", "Brown leather belt"),
     ("work", "smart"), True),
    ("Dinner at Da Mario", ("Navy merino crewneck", "Grey flannel trousers",
                            "Brown suede loafers", "Steel dive watch"),
     ("dinner", "evening"), True),
    ("Rain on the King's Road", ("White cotton tee", "Dark indigo jeans",
                                 "Black Chelsea boots", "Camel wool overcoat"),
     ("rain", "winter"), True),
    ("Summer lunch", ("Cream camp-collar shirt", "Grey flannel trousers",
                      "Brown suede loafers"), ("summer", "weekend"), True),
    ("Blazer, no tie", ("Pale blue oxford", "Navy hopsack blazer",
                        "Dark indigo jeans", "Black Chelsea boots"),
     ("smart", "evening"), False),
)

ANSWERS: dict[str, str] = {
    "says_what": "At work: competent and senior without looking like I am trying to be. "
                 "Weekends: like I have a life outside a laptop.",
    "never_look_like": "Trying too hard. A finance man on his day off. Anything that reads "
                       "as a costume the second I walk into a room.",
    "three_words": "Easy, sharp, warm.",
    "audience": "Mostly myself, then the people I have dinner with. Not colleagues.",
    "vibes_love": "Late-90s Milanese: soft shoulder, unstructured, nothing stiff. Also 70s "
                  "tennis club, that ecru and forest green thing.",
    "icons": "Marcello Mastroianni, but the ease rather than the suits. Paul Mescal when he "
             "gets the trousers right.",
    "stolen_outfit": "Man outside a cafe on Marylebone High Street: brown suede blouson, "
                     "white tee, grey flannel trousers, brown loafers. That was it.",
    "world": "Rome 1962. Wong Kar-wai interiors. Old Italian football away kits.",
    "try_hard": "Skinny jeans. Statement trainers. Big logos. Black shirts on a night out.",
    "wrong_signal": "Three black going-out shirts from about 2019. A boxy navy puffer that "
                    "makes me look square. Two pairs of grey marl joggers I wear in public.",
    "missing": "A proper overcoat. Trousers that are not jeans. One good brown shoe.",
    "actually_wear": "The same three tees, the dark jeans, the white trainers. Every single day.",
    "never_worn": "A patterned short-sleeve shirt. Bought it excited, put it on once, felt "
                  "like I was in fancy dress.",
    "default_outfit": "Grey hoodie, dark jeans, white trainers, and I leave the house angry.",
    "felt_great": "A wedding in Puglia. Cream linen shirt, stone trousers, brown suede shoes. "
                  "I did not think about what I was wearing once all day.",
    "keepers": "The cream camp-collar shirt. The navy hopsack blazer. The dark indigo jeans.",
    "normal_week": "Three days in the office, two at home. Gym four mornings. Dinner out twice "
                   "a week, usually somewhere unfussy. One proper night out a fortnight.",
    "fit_preference": "Relaxed through the leg, close on the shoulder. Never tight on the arm.",
    "flatter": "Happy to show the shoulders. Would rather nothing clung to the middle.",
    "fit_problems": "Trousers fit the waist and swim on the thigh. Shirt sleeves always two "
                    "centimetres too long. Jackets pull across the back.",
    "palette_width": "Tight. I want to stop thinking about it in the morning.",
    "fabrics": "Love wool, linen, heavy cotton. Cannot stand anything shiny or synthetic.",
    "priorities": "Practicality 4, Comfort 5, Aesthetics 9, Cost 2",
    "upkeep": "Almost none. If it needs ironing it will not get worn, that is just true.",
}

PRINCIPLES: tuple[tuple[str, str, str], ...] = (
    ("Silhouette", "Keep the volume in one place only.",
     "At 1.80 m, loose on top and loose below reads as swamped rather than relaxed."),
    ("Silhouette", "Buy the shoulder, alter everything else.",
     "A shoulder seam cannot be moved; a sleeve and a waist can, cheaply."),
    ("Colour", "Build every outfit from two base colours and at most one accent.",
     "A tight palette means anything in the wardrobe combines without thinking."),
    ("Colour", "Keep black away from your face.",
     "Warm medium-brown skin with a golden undertone goes flat against it; cream and "
     "navy do the opposite."),
    ("Fabric", "Choose cloth with visible texture over cloth with a pattern.",
     "Texture reads as considered at three metres, pattern reads as effort."),
    ("Proportion", "Let the trouser touch the shoe once and stop.",
     "A quarter break is the difference between tailored and borrowed."),
    ("Restraint", "One thing at a time may be interesting.",
     "If the overcoat is the event, the rest of the outfit is scenery."),
    ("Occasion", "Dress one notch above the room, never two.",
     "One notch reads as self-respect, two reads as a costume."),
)


# A starting palette, arranged by role rather than by preference, so the colour
# page has something with real structure in it. Two leathers and no more: any
# wardrobe that needs three has a problem somewhere else.
# name, hex, role, categories, seasons ("" means all year)
COLOURS: tuple[tuple[str, str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("Cream", "#F2E9D8", "Field", ("Top", "Outerwear"), ("Spring", "Summer")),
    ("Ecru", "#E8DFC8", "Field", ("Top",), ("Spring", "Summer")),
    ("White", "#F6F4EF", "Field", ("Top",), ()),
    ("Pale blue", "#BFD3E6", "Field", ("Top",), ("Spring", "Summer")),
    ("Oatmeal", "#DDD3C0", "Field", ("Top", "Outerwear"), ("Autumn", "Winter")),
    ("Navy", "#26303F", "Ground", ("Bottom", "Outerwear", "Top"), ()),
    ("Charcoal", "#3C3B3A", "Ground", ("Bottom", "Outerwear"), ("Autumn", "Winter")),
    ("Mid grey", "#7A7A78", "Ground", ("Bottom",), ()),
    ("Olive", "#5F6146", "Ground", ("Bottom", "Outerwear"), ("Autumn", "Winter")),
    ("Camel", "#C19A6B", "Ground", ("Outerwear", "Top"), ("Autumn", "Winter")),
    ("Stone", "#C9BCA4", "Ground", ("Bottom",), ("Spring", "Summer")),
    ("Chocolate", "#6B4426", "Ground", ("Shoes", "Accessory"), ()),
    ("Chestnut", "#8B5A2B", "Ground", ("Shoes", "Accessory"), ()),
    ("Rust", "#8E3B2E", "Accent", ("Accessory", "Top"), ("Autumn",)),
    ("Burgundy", "#6E2C33", "Accent", ("Accessory",), ("Autumn", "Winter")),
    ("Terracotta", "#B5613F", "Accent", ("Accessory", "Top"), ("Spring", "Summer")),
)

def seed_palette(palette=None):
    from .palette import Colour, Palette
    palette = palette if palette is not None else Palette.load()
    held = {c.hex.lower() for c in palette.colours}
    for name, hex_code, role, categories, seasons in COLOURS:
        if hex_code.lower() in held:
            continue
        held.add(hex_code.lower())
        palette.add(Colour(name=name, hex=hex_code, role=role,
                           categories=list(categories), seasons=list(seasons)))
    palette.save()
    return palette


def seed_inventory(inventory: Inventory | None = None) -> Inventory:
    inventory = inventory if inventory is not None else Inventory.load()
    held = {i.name for i in inventory.items}
    for name, garment, colour, hex_code, fabric, sizes, wanted, grade, fit in ITEMS:
        if name in held:
            continue
        held.add(name)
        inventory.add(Item(
            name=name, garment=garment, category=category_for(garment),
            colours=[colour] if colour else [], colour_hex=hex_code, fabric=fabric, sizes=dict(sizes),
            status=ASPIRATIONAL if wanted else "owned", grade=grade, fit=fit,
        ))
    inventory.save()
    return inventory


def seed_outfits(inventory: Inventory, outfits: Outfits | None = None) -> Outfits:
    outfits = outfits if outfits is not None else Outfits.load()
    by_name = {i.name: i.id for i in inventory.items}
    held = {o.name for o in outfits.outfits}
    for name, item_names, tags, loved in LOOKS:
        if name in held:
            continue
        held.add(name)
        ids = [by_name[n] for n in item_names if n in by_name]
        outfits.add(Outfit(name=name, item_ids=ids, tags=list(tags), loved=loved))
    outfits.save()
    return outfits


def seed_answers(answers: Answers | None = None) -> Answers:
    """Fill the blanks only.

    This one used to be a straight dict update, so seeding a wardrobe that
    already had real answers in it overwrote every one of them with the sample.
    That is exactly what happened to this wardrobe: twenty-four answers in the
    owner's own words were replaced by the fixture, and only git had them.
    An answer already written is his; the sample is for empty boxes.
    """
    answers = answers if answers is not None else Answers.load()
    for question, sample in ANSWERS.items():
        if not str(answers.values.get(question, "")).strip():
            answers.values[question] = sample
    answers.save()
    return answers


def seed_principles(principles: Principles | None = None) -> Principles:
    principles = principles if principles is not None else Principles.load()
    for group, text, reason in PRINCIPLES:
        principles.add(Principle(text=text, reason=reason, group=group,
                                 status=prin_mod_CONFIRMED))
    principles.save()
    return principles


def seed_all() -> dict[str, int]:
    """Fill everything, idempotently. Running it twice is a no-op: every seeder
    skips a row it already holds, matching on name (items, outfits, principles)
    or hex (colours). It used to append blindly, which quietly grew the wardrobe
    to 247 items and the principles to 142 over seventeen smoke runs."""
    inventory = seed_inventory()
    outfits = seed_outfits(inventory)
    answers = seed_answers()
    principles = seed_principles()
    palette = seed_palette()
    return {
        "items": len(inventory.items),
        "outfits": len(outfits.outfits),
        "answers": len(answers.values),
        "principles": len(principles.principles),
        "colours": len(palette.colours),
    }
