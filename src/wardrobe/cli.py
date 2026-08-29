"""Command line front doors: `uv run wardrobe-check`, `uv run wardrobe-reset`."""

from __future__ import annotations

import argparse
import sys

from . import checks, paths, reset, seed


def check(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wardrobe-check", description="Run the check suite.")
    parser.add_argument("--live", action="store_true",
                        help="also call Vertex AI for real (slow, costs money)")
    parser.add_argument("--browser", action="store_true",
                        help="also open every page in Chromium and look at it (slow)")
    parser.add_argument("--group", action="append", choices=list(checks.GROUPS),
                        help="only this group; repeatable")
    args = parser.parse_args(argv)

    def line(c: checks.Check) -> None:
        mark = "\033[32m✓\033[0m" if c.passed else "\033[31m✗\033[0m"
        print(f" {mark} {c.group:15} {c.name:46} {c.seconds:5.2f}s  {c.detail[:70]}")

    groups = list(args.group or [])
    if args.browser and not groups:
        groups = [g for g in checks.GROUPS if g != checks.LIVE]
    elif args.browser:
        groups.append(checks.BROWSER)
    result = checks.run(groups or None, live=args.live, on_result=line)
    print(f"\n{result.passed}/{len(result.checks)} passed in {result.seconds}s")
    for failure in result.failed:
        print(f"\n--- {failure.name} ---\n{failure.trace or failure.detail}")
    return 0 if result.ok else 1


def clear(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wardrobe-reset",
        description="Clear wardrobe data. A snapshot is taken first, always.")
    parser.add_argument("--all", action="store_true",
                        help="include the subject profile, which is otherwise kept")
    parser.add_argument("--seed", action="store_true", help="refill with sample data afterwards")
    parser.add_argument("--yes", action="store_true", help="do not ask")
    args = parser.parse_args(argv)

    here = reset.present()
    if not here:
        print("Nothing stored. Already back where you started.")
        return 0
    keys = [k for k in (paths.DATA if args.all else paths.DEFAULT_CLEAR) if k in here]
    print(f"About to clear, from {paths.home().resolve()}:")
    for key in keys:
        print(f"  {paths.DATA[key]:24} {here[key]}")
    if not args.yes and input("\nProceed? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Left alone.")
        return 1

    snap, removed = reset.wipe(keys)
    print(f"Cleared {len(removed)}. Snapshot at {snap.path}" if snap else "Cleared.")
    if args.seed:
        print("Reseeded:", seed.seed_all())
    return 0


if __name__ == "__main__":
    sys.exit(check())
