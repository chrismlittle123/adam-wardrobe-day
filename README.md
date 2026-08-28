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

1. **Style Guide** — 39 questions across 8 sections: intent, taste, an honest
   audit of what actually gets worn, life, fit, colour, grooming, budget.
   Answers land in `style-answers.toml` and synthesise into `STYLE-GUIDE.md`.
2. **Wardrobe Inventory** — every piece, owned or merely wanted, with photos,
   size labels and finished garment measurements. Photograph anything words
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

## Status

🚧 Early. The app runs; the wardrobe is empty until someone fills it in.
