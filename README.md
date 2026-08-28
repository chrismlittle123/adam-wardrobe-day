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
3. **Principles** — a dozen short checkable rules, generated from the answers
   and hand-editable. Fed into every generated look.
4. **Outfit Generator** — assemble a look from the wardrobe, or invent a piece
   you do not own yet. Item photos ride along as references so the generated
   image shows *that* jacket.
5. **Outfit Gallery** — tag, search, love. Each outfit shows its cost split
   between what is already owned and what is still to buy.
6. **Shopping Guide** — body measurements and the finished garment dimensions
   derived from them, then a purchase plan.

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
uv run wardrobe-check              # 36 checks, a couple of seconds
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
