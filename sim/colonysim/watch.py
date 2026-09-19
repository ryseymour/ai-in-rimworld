"""Watch trade happen: the map redrawn each day with caravans on the roads.

    python -m colonysim.watch --seed 23 --days 150
"""
from __future__ import annotations

import argparse
import time

from .goods import GOOD_NAMES
from .render import render
from .simulation import build_simulation
from .trade import OUTBOUND

CLEAR = "\033[H\033[J"


def cargo_summary(cargo: dict[str, float]) -> str:
    carried = [(qty, good) for good, qty in cargo.items() if qty >= 0.5]
    if not carried:
        return "empty"
    carried.sort(reverse=True)
    return ", ".join(f"{qty:.0f} {good}" for qty, good in carried[:3])


def frame(sim, width: int) -> str:
    out = [render(sim.world, sim.network, sim.caravans, sim.wilds), ""]
    out.append(
        f"day {sim.day}   {len(sim.caravans)} on the road   "
        f"{sim.journeys} journeys done   {sim.meetings} met in the wild"
    )
    out.append("")

    if sim.caravans:
        out.append("caravans")
        for caravan in sorted(sim.caravans, key=lambda c: c.id):
            home = sim.colonies[caravan.home].name
            dest = sim.colonies[caravan.destination].name
            arrow = "->" if caravan.state == OUTBOUND else "<-"
            line = (
                f"  {home:>11} {arrow} {dest:<11} "
                f"{cargo_summary(caravan.cargo):<34} "
                f"{caravan.purse.amount:>6.0f} coin"
            )
            out.append(line[:width])
    else:
        out.append("caravans: none on the road")
    out.append("")

    out.append(f"  {'colony':<12}" + "".join(f"{g:>9}" for g in GOOD_NAMES) + f"{'coin':>9}")
    for colony, days in zip(sim.colonies, sim.days_of_stock("food")):
        stocks = "".join(f"{colony.storage.get(g):>9.0f}" for g in GOOD_NAMES)
        flag = "  <- out of food" if days < 1 else ""
        out.append(f"  {colony.name:<12}{stocks}{colony.purse.amount:>9.0f}{flag}")

    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Watch caravans trade across the map.")
    ap.add_argument("--seed", type=int, default=23)
    ap.add_argument("--width", type=int, default=90)
    ap.add_argument("--height", type=int, default=32)
    ap.add_argument("--settlements", type=int, default=3)
    ap.add_argument(
        "--no-stewards",
        action="store_true",
        help="leave every colony trading on bare scarcity",
    )
    ap.add_argument("--days", type=int, default=150)
    ap.add_argument("--delay", type=float, default=0.15, help="seconds per day")
    ap.add_argument("--frames", type=int, default=0, help="stop after N days (0 = all)")
    args = ap.parse_args()

    sim = build_simulation(
        args.seed,
        args.settlements,
        args.width,
        args.height,
        stewards=not args.no_stewards,
    )
    limit = args.frames or args.days

    try:
        for _ in range(min(limit, args.days)):
            sim.step_day()
            print(CLEAR + frame(sim, args.width + 20), flush=True)
            if args.delay:
                time.sleep(args.delay)
    except KeyboardInterrupt:
        print()

    print(f"\nstopped on day {sim.day} after {sim.journeys} journeys.")
    print("run `python -m colonysim.demo` for the with-and-without-trade comparison.")


if __name__ == "__main__":
    main()
