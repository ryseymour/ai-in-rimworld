"""Generate a world and print it. `python -m colonysim.demo --seed 7`."""
from __future__ import annotations

import argparse

from .render import legend, render
from .roads import generate_roads
from .world import generate_world


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a world and its roads.")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--width", type=int, default=90)
    ap.add_argument("--height", type=int, default=45)
    ap.add_argument("--settlements", type=int, default=6)
    args = ap.parse_args()

    world = generate_world(args.width, args.height, args.settlements, args.seed)
    network = generate_roads(world)
    print(render(world, network))
    print()
    print(legend(world, network))


if __name__ == "__main__":
    main()
