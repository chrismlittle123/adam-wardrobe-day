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
   `STYLE-GUIDE.md`, which is then read or edited by hand.

   The guide is a draft, not a delivery. **Read** renders it and **Edit** gives
   you the raw markdown. Every save keeps the version it replaced, and any of
   them can be restored, so nothing here can lose an afternoon.
2. **Wardrobe Inventory** — every piece, owned or merely wanted, with photos
   restaged onto white the moment they are uploaded, so a wardrobe photographed
   on a bedroom floor still reads as a wardrobe worth browsing
   and sizes in whatever scheme that garment actually uses: a collar for a
   shirt, chest and a length letter for a jacket, waist and leg for trousers,
   three disagreeing national systems for a shoe. Only wanted pieces carry a
   price, since what an owned garment cost is sunk. Photograph anything words
   cannot pin down: "green jacket" gives a different jacket every time.
3. **Principles** — short checkable rules, about ten of them. The model offers
   five suggestions at a time and you keep the ones that ring true; each round
   is told what you already kept so it goes somewhere new. Hand-written ones
   sit alongside. All of them are fed into every generated look.
4. **Colour** — the palette as a set of roles rather than a list. Ground, Field
   and Accent, each with the garments it is allowed on and the seasons it is worn
   in, which gives four palettes out of one. Every colour carries a name, taken
   from a catalogue of fifty or given by hand, and the catalogue opens in its own
   tab. Harmonies are stolen off the wheel with one click, and a grid says which
   colour goes on which garment. Then every
   recipe the grid permits is enumerated and scored, best first, filterable by
   season, with its reasoning printed next to it.
5. **Outfit Generator** — assemble a look from the wardrobe, or invent a piece
   you do not own yet. Item photos ride along as references so the generated
   image shows *that* jacket.
6. **Outfit Gallery** — tag, search, love. Each outfit shows its cost split
   between what is already owned and what is still to buy.
7. **Body Measurements** — ten measurements, all takeable on yourself with a tape
   and a mirror, and the finished garment dimensions derived from them.
8. **Where to Buy** — the sourcing plan, editable. Which shops each garment type
   comes from, what to match on, and on what terms. Add, edit and delete routes,
   or restore the defaults. The retailer catalogue opens in its own tab, where
   shops can be added, edited or dropped; a route naming a shop that is later
   deleted simply loses it rather than breaking.
9. **Shopping Guide** — a shop. Each wanted piece is a product card with a
   generated catalogue photograph, its price and the size to look for. Open one
   and it fills a browser tab: the cloth, the cut, what to check before buying,
   how that garment usually goes wrong, the finished measurements on his body,
   the outfits waiting on it, where to buy it, and how not to pay retail.

### The sourcing plan

`sourcing.py` holds the decisions rather than the ranking, editable on the
Where to Buy page and stored in `sourcing.toml`: heavyweight tees from
Asos or Next at 200 gsm, plain ones from Uniqlo in supima; blazers, jackets,
dress shoes, boots and overcoats from Vinted in Very Good condition or above;
dress shirts from Charles Tyrwhitt on sale, linen from Mango; chinos, jeans,
overshirts and plain polos from Uniqlo; jumpers from M&S or Uniqlo; smart
trainers from Vinted new with tags only, branded ones from the brand's own sale;
suits from M&S and then altered.

A route is finer-grained than a garment type, which is the hard part: a
heavyweight tee and a plain tee are both "T-shirt" and come from different shops,
as do a dress shirt and a linen one. So a route is selected on three optional
axes rather than by guessing at words in a name:

- **Grade** — what kind of thing it is within its type: Heavyweight, Dress,
  Smart, Knitted, Branded, Everyday.
- **Fabric** — either an exact cloth (`Oxford cotton`) or a whole family
  (`Wool`), so one line covers flannel, worsted and hopsack at once.
- **Fit** — Slim, Regular, Relaxed, Oversized.

A route states only the constraints it cares about and matches only if the
garment satisfies every one of them. Among matching routes the one stating the
most wins, so a route with none is the type's default. A garment matching nothing
says so rather than being pushed down the nearest line, and the product page
prints which constraints put it where it went.

### Where to buy, and how not to pay retail

Anything from **£50 goes secondhand first**. Not out of thrift, but because
the garments that cost that much are the ones worn least: a blazer worn twenty
times a year spends most of its life in a wardrobe whether it was bought new or
not, and Vinted is full of them barely worn. Below that line the sum flips, and a
£20 t-shirt is bought new from whoever cuts it well.

36 UK retailers are ranked per garment and price: Vinted, eBay, Vestiaire and
Watchfinder for secondhand; Uniqlo, Zara, H&M, Mango, COS, Arket, Massimo Dutti,
Next and M&S on the high street; Moss, Suitsupply and Charles Tyrwhitt for
tailoring; Clarks, Base London, Loake, Grenson and Solovair for shoes. Each comes
with its reason and a working search link.

Then the tactics, which are the actual strategy: save the Vinted search with your
size in it, wishlist rather than buy so the discount comes to you, buy out of
season (a coat is cheapest in February, linen in late August), and set a
walk-away price before a sale email arrives.

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

### Sizing, UK

Two different kinds of number, and confusing them is most of why clothes do not
fit. A **UK size** is what a shop prints on a label: a jacket marked 38, a shirt
with a 15.5 inch collar, a shoe marked 9. It is a name, not a length, and it
means something different in every shop. A **measurement** is what a tape reads,
and every one of them in this app is centimetres.

So sizes stay in whatever unit the label uses, measurements are always cm, and
the Body Measurements tab turns the second into the first. EU sizes sit alongside
the UK ones only because half of Vinted is listed in them; US sizes are gone.

### The fit engine

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
