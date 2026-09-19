"""The colony simulation: world, roads, storage, currency, trade and the wild.

See `../wiki/design-inter-colony-trade.md` for the design this implements.
"""
from __future__ import annotations

from .goods import GOODS, Good
from .money import SILVER, Currency, Purse
from .roads import RoadNetwork, Route, generate_roads
from .simulation import Simulation, build_simulation
from .storage import Colony, MarketView, Storage
from .terrain import Terrain, generate_terrain
from .trade import Caravan, Payment, settle
from .wildlife import BEARS, WOLVES, Den, Encounter, Species, Wilds, populate
from .world import Settlement, World, generate_world

__all__ = [
    "BEARS",
    "GOODS",
    "SILVER",
    "WOLVES",
    "Caravan",
    "Colony",
    "Currency",
    "Den",
    "Encounter",
    "Good",
    "MarketView",
    "Payment",
    "Purse",
    "RoadNetwork",
    "Route",
    "Settlement",
    "Simulation",
    "Species",
    "Storage",
    "Terrain",
    "Wilds",
    "World",
    "build_simulation",
    "generate_roads",
    "generate_terrain",
    "generate_world",
    "populate",
    "settle",
]
