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

Three tabs:

- **Studio** — the reference photo and subject card, an outfit brief, and a
  gallery of generated looks. Every prompt carries his real height, build and
  skin tone so the model stops handing a lean 1.76 m man the proportions of a
  runway mannequin.
- **Philosophy** — 40 questions across 8 sections. Intent, taste, an honest
  audit of what actually gets worn, life, fit, colour, grooming, and budget.
  Answers save to `style-answers.toml`.
- **Style guide** — turns those answers into `STYLE-GUIDE.md`: thesis, palette
  with hex codes, silhouette rules, core wardrobe, named uniforms, what to
  retire, and a prioritised shopping list.

Who he is lives in `profile.toml` and feeds every prompt.

## Status

🚧 Early, but the app runs.
