# Adam Wardrobe Day

A little project to help my friend Adam level up his wardrobe. 👔

## What is this?

This repo is home base for figuring out, tracking, and improving Adam's
wardrobe — from taking stock of what he already owns to planning outfits,
building a shopping list, and nailing down a style that actually works for him.

## Goals

- **Inventory** — catalog what's currently in the closet (and what needs to go)
- **Style direction** — define the look(s) Adam is going for
- **Gap analysis** — figure out what's missing to make outfits work
- **Shopping list** — prioritized buys with budget in mind
- **Outfit ideas** — reliable combinations for different occasions

## Structure

Still early days. As the project grows, expect folders/files for:

- `inventory/` — current wardrobe items
- `outfits/` — curated combinations
- `shopping/` — wishlist and priorities
- `notes/` — style references, measurements, preferences

## The app

```bash
uv run wardrobe-app          # http://localhost:8501
```

Six tabs, in the order the work happens.

1. **Style Guide** — 24 questions across 7 sections: intent, taste, an honest
   audit of what actually gets worn, life, fit, colour, and one question that
   makes him spend 20 points across practicality, comfort, aesthetics and cost.
   That allocation becomes the tie-breaker whenever two recommendations
   conflict. Answers land in `style-answers.toml` and synthesise into
   `STYLE-GUIDE.md`.
2. **Wardrobe Inventory** — every piece, owned or merely wanted, with photos
   and sizes in whatever scheme that garment actually uses: a collar for a
   shirt, chest and a length letter for a jacket, waist and leg for trousers,
   three disagreeing national systems for a shoe. Only wanted pieces carry a
   price, since what an owned garment cost is sunk. Photograph anything words
   cannot pin down: "green jacket" gives a different jacket every time.
3. **Principles** — short checkable rules, about ten of them. The model offers
   five suggestions at a time and you keep the ones that ring true; each round
   is told what you already kept so it goes somewhere new. Hand-written ones
   sit alongside. All of them are fed into every generated look.
4. **Colour** — the palette as a set of roles rather than a list. Ground, Field,
   Accent, Leather, each with the garments it is allowed on. A hue wheel plots
   the palette against his actual skin tone, harmonies are stolen off the wheel
   with one click, patterns are picked from a list, and a grid says which colour
   goes on which garment. Then every recipe the grid permits is enumerated and
   scored, best first, with its reasoning printed next to it.
5. **Outfit Generator** — assemble a look from the wardrobe, or invent a piece
   you do not own yet. Item photos ride along as references so the generated
   image shows *that* jacket.
6. **Outfit Gallery** — tag, search, love. Each outfit shows its cost split
   between what is already owned and what is still to buy.
7. **Shopping Guide** — ten body measurements, all takeable on yourself with a
   tape and a mirror, then the finished garment dimensions derived from them,
   then a purchase plan.

### The colour maths

Coordination is two measurable things. **Value contrast**: a top and a bottom
within 0.10 of each other in lightness read as one garment whatever their hues.
**Temperature**: where a hue sits relative to his skin at `#C58466`. Near it is
harmonious, the far side flatters by contrast (which is why navy suits everyone),
and the near-miss between them is where sallow greens live.

Colours are named the way cloth is described, not the way a colour wheel divides.
Equal 30° sectors put navy in "cyan" and olive in "amber"; brown and olive and
cream never fall out of a wheel at all, because they are dark or pale warm tints
rather than hues.

### The shopping maths

A loved outfit is *blocked* by exactly the pieces in it he does not own, so
"what should I buy" is weighted set cover. Each round takes the bundle of
pieces missing from one blocked outfit with the best outfits-per-pound; any
other outfit whose gap is a subset of that bundle unlocks for free.

Bundles rather than single garments, because an outfit missing two pieces is
completed by neither alone: a per-item greedy scores both zero and stalls. A
budget filters rather than halts, so a small budget still returns the best
thing it can actually buy. It is greedy, so it approximates; every step shows
its arithmetic.

### Sizing

`fitspec.py` separates body measurements from garment measurements and keeps
ease tabulated per garment and per fit. A size label means nothing across two
brands; a shirt measuring 106 cm round the chest means the same everywhere.
Unmeasured dimensions are estimated from height and build and always marked as
estimates.

Who he is lives in `profile.toml` and feeds every prompt.

## Checking it works

```bash
uv run wardrobe-check              # 51 checks, a couple of seconds
uv run wardrobe-check --live       # plus two real Vertex AI calls
uv run pytest                      # the same checks, from CI
uv run wardrobe-reset --yes        # clear the data, snapshot taken first
uv run wardrobe-reset --yes --seed # clear, then refill with sample data
```

Or the **Diagnostics** tab in the app: run the checks, fill the wardrobe with
realistic sample data, then clear it and put everything back.

Every check runs inside a throwaway `WARDROBE_HOME`, so running the suite cannot
touch the real wardrobe even if a check is wrong. `WARDROBE_HOME` is what makes
that possible: every path in the app resolves through `paths.py`, which resolves
through that variable.

Clearing is reversible. Anything deleted is copied into
`.wardrobe-backups/<timestamp>/` first, and any snapshot can be restored whole.
The subject profile is left out of the default selection, because his height and
skin tone are not test data.

## Status

🚧 Early. The app runs; the wardrobe is empty until someone fills it in.
