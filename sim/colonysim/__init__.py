"""The colony simulation: world, roads, storage, currency, trade, stewards,
people and the wild.

See `../wiki/design-inter-colony-trade.md` for the design this implements.
"""
from __future__ import annotations

from .goods import GOODS, Good
from .money import SILVER, Currency, Purse
from .people import caravans_allowed, food_cover
from .roads import RoadNetwork, Route, generate_roads, road_links, road_overlay
from .simulation import Simulation, build_simulation
from .steward import Link, NetworkView, Steward, merchant
from .storage import Colony, MarketView, Policy, Storage
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
    "Link",
    "MarketView",
    "NetworkView",
    "Payment",
    "Policy",
    "Purse",
    "RoadNetwork",
    "Route",
    "Settlement",
    "Simulation",
    "Species",
    "Steward",
    "Storage",
    "Terrain",
    "Wilds",
    "World",
    "build_simulation",
    "caravans_allowed",
    "food_cover",
    "generate_roads",
    "merchant",
    "road_links",
    "road_overlay",
    "generate_terrain",
    "generate_world",
    "populate",
    "settle",
]
