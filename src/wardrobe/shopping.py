"""What to buy next, worked out rather than guessed.

The question "which missing garment would do the most good" is weighted set
cover. Each loved outfit is a set that needs covering; each unowned garment
covers part of several sets; buying it costs money. Optimal weighted set cover
is NP-hard, so this uses the standard greedy: repeatedly take the item with the
best ratio of outfits-completed to price. Greedy is within a known factor of
optimal on this problem and, more usefully here, its reasoning can be read line
by line and argued with.

The unit matters. Scoring one garment at a time looks reasonable and behaves
badly: an outfit missing two pieces is completed by neither alone, so both score
zero and the plan stalls or wanders off after whatever single expensive item
happens to finish something. So each candidate here is a *bundle*, the full set
of pieces still missing from one blocked outfit, and the winner each round is
the bundle with the best outfits-per-pound. Buying a bundle often completes
other outfits for free, whenever their missing pieces are a subset of it, and
that is counted.

A budget does not stop the plan, it filters it: unaffordable bundles are skipped
and the next best affordable one is taken, so a small budget still returns the
best thing it can actually buy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .inventory import Inventory, Item
from .outfits import Outfit, Outfits


@dataclass
class Leverage:
    """One unowned garment, scored independently of any purchase order."""

    item: Item
    appearances: int          # still-blocked outfits containing it
    solo_unlocks: int         # outfits where it is the ONLY thing missing
    outfit_names: list[str] = field(default_factory=list)

    @property
    def price(self) -> float:
        return self.item.price

    @property
    def cost_per_solo_unlock(self) -> float | None:
        return round(self.price / self.solo_unlocks, 2) if self.solo_unlocks else None


@dataclass
class Step:
    """One purchase: every piece still missing from one blocked outfit."""

    items: list[Item] = field(default_factory=list)
    target: Outfit | None = None       # the outfit this bundle was chosen for
    unlocked: list[Outfit] = field(default_factory=list)
    cumulative_cost: float = 0.0
    cumulative_unlocked: int = 0

    @property
    def price(self) -> float:
        return round(sum(i.price for i in self.items), 2)

    @property
    def rule(self) -> str:
        n = len(self.unlocked)
        per = f", £{round(self.price / n)} each" if n and self.price else ""
        return f"{len(self.items)} piece(s) unlock {n} outfit(s){per}"

    @property
    def cost_per_outfit(self) -> float | None:
        n = self.cumulative_unlocked
        return round(self.cumulative_cost / n, 2) if n else None


@dataclass
class Plan:
    wearable_now: list[Outfit] = field(default_factory=list)
    blocked: list[Outfit] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    still_blocked: list[Outfit] = field(default_factory=list)
    leverage: list[Leverage] = field(default_factory=list)
    budget: float | None = None
    skipped_for_budget: list[Outfit] = field(default_factory=list)

    @property
    def total_cost(self) -> float:
        return round(sum(s.price for s in self.steps), 2)

    @property
    def outfits_unlocked(self) -> int:
        return sum(len(s.unlocked) for s in self.steps)

    @property
    def items_to_buy(self) -> list[Item]:
        return [i for s in self.steps for i in s.items]

    @property
    def considered(self) -> int:
        return len(self.wearable_now) + len(self.blocked)


def _missing_ids(outfit: Outfit, inventory: Inventory, acquired: set[str]) -> set[str]:
    """Ids in this outfit that are neither owned nor already bought in the plan."""
    return {
        i.id for i in inventory.resolve(outfit.item_ids)
        if not i.owned and i.id not in acquired
    }


def item_leverage(
    outfits: Outfits, inventory: Inventory, *, loved_only: bool = True
) -> list[Leverage]:
    """Score every unowned garment against the outfits it appears in.

    Order-independent, so this is the honest "which pieces matter" table, as
    opposed to the plan, which depends on what you buy first.
    """
    considered = outfits.loved() if loved_only else outfits.outfits
    blocked = [o for o in considered if _missing_ids(o, inventory, set())]

    rows: dict[str, Leverage] = {}
    for outfit in blocked:
        missing = _missing_ids(outfit, inventory, set())
        for item_id in missing:
            item = inventory.by_id(item_id)
            if not item:
                continue
            row = rows.setdefault(item_id, Leverage(item=item, appearances=0, solo_unlocks=0))
            row.appearances += 1
            row.outfit_names.append(outfit.name or outfit.id)
            if missing == {item_id}:
                row.solo_unlocks += 1

    return sorted(
        rows.values(),
        key=lambda r: (-r.solo_unlocks, -r.appearances, r.price),
    )


def purchase_plan(
    outfits: Outfits,
    inventory: Inventory,
    *,
    loved_only: bool = True,
    budget: float | None = None,
    max_steps: int = 40,
) -> Plan:
    """Greedy weighted set cover, one blocked outfit's missing pieces per round."""
    considered = outfits.loved() if loved_only else outfits.outfits
    wearable_now = [o for o in considered if not _missing_ids(o, inventory, set())]
    blocked = [o for o in considered if _missing_ids(o, inventory, set())]

    plan = Plan(
        wearable_now=wearable_now,
        blocked=blocked,
        leverage=item_leverage(outfits, inventory, loved_only=loved_only),
        budget=budget,
    )

    acquired: set[str] = set()
    remaining = list(blocked)
    spent = 0.0

    while remaining and len(plan.steps) < max_steps:
        best: tuple[float, float, Outfit, set[str], list[Outfit]] | None = None

        for outfit in remaining:
            bundle = _missing_ids(outfit, inventory, acquired)
            if not bundle:
                continue
            cost = round(sum(_price(inventory, i) for i in bundle), 2)
            if budget is not None and spent + cost > budget:
                continue
            # Anything else whose remaining gap is covered by this bundle comes free.
            unlocked = [o for o in remaining if _missing_ids(o, inventory, acquired) <= bundle]
            ratio = len(unlocked) / max(cost, 1.0)
            key = (-ratio, cost)
            if best is None or key < (-best[0], best[1]):
                best = (ratio, cost, outfit, bundle, unlocked)

        if best is None:
            # Everything left is out of budget.
            plan.skipped_for_budget = list(remaining)
            break

        _, cost, target, bundle, unlocked = best
        items = [i for i in (inventory.by_id(x) for x in bundle) if i]
        items.sort(key=lambda i: -i.price)

        acquired |= bundle
        spent = round(spent + cost, 2)
        unlocked_ids = {o.id for o in unlocked}
        remaining = [o for o in remaining if o.id not in unlocked_ids]

        plan.steps.append(Step(
            items=items,
            target=target,
            unlocked=unlocked,
            cumulative_cost=spent,
            cumulative_unlocked=sum(len(s.unlocked) for s in plan.steps) + len(unlocked),
        ))

    plan.still_blocked = remaining
    return plan


def _price(inventory: Inventory, item_id: str) -> float:
    item = inventory.by_id(item_id)
    return item.price if item else 0.0


def wardrobe_value(inventory: Inventory) -> dict[str, float]:
    owned = [i for i in inventory.items if i.owned]
    wanted = [i for i in inventory.items if i.status == "aspirational"]
    starred = [i for i in wanted if i.starred]
    return {
        "owned_value": round(sum(i.price for i in owned), 2),
        "owned_count": len(owned),
        "wanted_value": round(sum(i.price for i in wanted), 2),
        "wanted_count": len(wanted),
        "starred_value": round(sum(i.price for i in starred), 2),
        "starred_count": len(starred),
    }
