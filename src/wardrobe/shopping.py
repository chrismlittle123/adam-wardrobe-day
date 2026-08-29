"""What to buy next, worked out rather than guessed.

The question "which missing garment would do the most good" is set cover. Each
loved outfit is a set that needs covering, and each unowned garment covers part
of several sets. Optimal set cover is NP-hard, so this uses the standard greedy:
repeatedly take the bundle that completes the most outfits per garment bought.
Greedy is within a known factor of optimal and, more usefully here, its reasoning
can be read line by line and argued with.

There is deliberately no money in this. Almost everything worth buying comes off
a secondhand listing, so the price is unknown until the thing appears, and a plan
built on invented prices would rank on fiction. What can be known is how many
garments a plan asks him to find, and that is what it minimises.

The unit matters. Scoring one garment at a time looks reasonable and behaves
badly: an outfit missing two pieces is completed by neither alone, so both score
zero and the plan stalls. So each candidate here is a *bundle*, the full set of
pieces still missing from one blocked outfit, and the winner each round is the
bundle completing the most outfits per garment. Buying a bundle often completes
other outfits for free, whenever their missing pieces are a subset of it, and
that is counted.
"""

from __future__ import annotations

from .text import plural

from dataclasses import dataclass, field

from .inventory import ASPIRATIONAL, Inventory, Item
from .outfits import Outfit, Outfits, wearability


@dataclass
class Leverage:
    """One unowned garment, scored independently of any purchase order."""

    item: Item
    appearances: int          # still-blocked outfits containing it
    solo_unlocks: int         # outfits where it is the ONLY thing missing
    outfit_names: list[str] = field(default_factory=list)


@dataclass
class Step:
    """One purchase: every piece still missing from one blocked outfit."""

    items: list[Item] = field(default_factory=list)
    target: Outfit | None = None       # the outfit this bundle was chosen for
    unlocked: list[Outfit] = field(default_factory=list)
    cumulative_bought: int = 0
    cumulative_unlocked: int = 0

    @property
    def size(self) -> int:
        return len(self.items)

    @property
    def rule(self) -> str:
        n = len(self.unlocked)
        return f"{plural(self.size, 'piece')} unlock {plural(n, 'outfit')}"


@dataclass
class Plan:
    wearable_now: list[Outfit] = field(default_factory=list)
    blocked: list[Outfit] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    still_blocked: list[Outfit] = field(default_factory=list)
    leverage: list[Leverage] = field(default_factory=list)
    # Outfits nothing can fix: a piece in them was deleted or retired.
    broken: list[Outfit] = field(default_factory=list)

    @property
    def to_find(self) -> int:
        """How many garments the whole plan asks him to track down."""
        return sum(s.size for s in self.steps)

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
    """Ids in this outfit still to be bought.

    Only wanted pieces count. A retired garment is also "not owned", but nobody
    should be told to go and buy back something they got rid of, and a deleted
    one cannot be bought at all.
    """
    return {
        i.id for i in inventory.resolve(outfit.item_ids)
        if i.status == ASPIRATIONAL and i.id not in acquired
    }


def _usable(outfits_list: list[Outfit], inventory: Inventory) -> tuple[list[Outfit], list[Outfit]]:
    """Split into outfits money can help with, and outfits it cannot."""
    broken = [o for o in outfits_list if wearability(o, inventory).broken]
    broken_ids = {o.id for o in broken}
    return [o for o in outfits_list if o.id not in broken_ids], broken


def item_leverage(
    outfits: Outfits, inventory: Inventory, *, loved_only: bool = True
) -> list[Leverage]:
    """Score every unowned garment against the outfits it appears in.

    Order-independent, so this is the honest "which pieces matter" table, as
    opposed to the plan, which depends on what you buy first.
    """
    considered = outfits.loved() if loved_only else outfits.outfits
    considered, _ = _usable(considered, inventory)
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
        key=lambda r: (-r.solo_unlocks, -r.appearances, r.item.name or r.item.garment),
    )


def purchase_plan(
    outfits: Outfits,
    inventory: Inventory,
    *,
    loved_only: bool = True,
    max_steps: int = 40,
) -> Plan:
    """Greedy set cover, one blocked outfit's missing pieces per round."""
    considered = outfits.loved() if loved_only else outfits.outfits
    considered, broken = _usable(considered, inventory)
    wearable_now = [o for o in considered if not _missing_ids(o, inventory, set())]
    blocked = [o for o in considered if _missing_ids(o, inventory, set())]

    plan = Plan(
        broken=broken,
        wearable_now=wearable_now,
        blocked=blocked,
        leverage=item_leverage(outfits, inventory, loved_only=loved_only),
    )

    acquired: set[str] = set()
    remaining = list(blocked)
    bought = 0

    while remaining and len(plan.steps) < max_steps:
        best: tuple[float, int, Outfit, set[str], list[Outfit]] | None = None

        for outfit in remaining:
            bundle = _missing_ids(outfit, inventory, acquired)
            if not bundle:
                continue
            # Anything else whose remaining gap is covered by this bundle comes free.
            unlocked = [o for o in remaining if _missing_ids(o, inventory, acquired) <= bundle]
            ratio = len(unlocked) / len(bundle)
            key = (-ratio, len(bundle))
            if best is None or key < (-best[0], best[1]):
                best = (ratio, len(bundle), outfit, bundle, unlocked)

        if best is None:
            break

        _, _, target, bundle, unlocked = best
        items = [i for i in (inventory.by_id(x) for x in bundle) if i]
        items.sort(key=lambda i: i.name or i.garment)

        acquired |= bundle
        bought += len(bundle)
        unlocked_ids = {o.id for o in unlocked}
        remaining = [o for o in remaining if o.id not in unlocked_ids]

        plan.steps.append(Step(
            items=items,
            target=target,
            unlocked=unlocked,
            cumulative_bought=bought,
            cumulative_unlocked=sum(len(s.unlocked) for s in plan.steps) + len(unlocked),
        ))

    plan.still_blocked = remaining
    return plan


def wardrobe_counts(inventory: Inventory) -> dict[str, int]:
    wanted = [i for i in inventory.items if i.status == "aspirational"]
    return {
        "owned": sum(1 for i in inventory.items if i.owned),
        "wanted": len(wanted),
        "starred": sum(1 for i in wanted if i.starred),
    }
