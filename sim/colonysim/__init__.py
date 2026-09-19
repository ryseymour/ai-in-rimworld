"""The colony simulation: world, roads, storage, currency, trade, stewards,
haggling, people and the wild.

See `../wiki/design-inter-colony-trade.md` for the design this implements.
"""
from __future__ import annotations

from .goods import GOODS, Good
from .money import SILVER, Currency, Purse
from .negotiation import (
    HOST,
    TRADER,
    Haggle,
    Move,
    Seat,
    Speakers,
    bargain,
    negotiate,
)
from .people import caravans_allowed, food_cover
from .roads import RoadNetwork, Route, generate_roads, road_links, road_overlay
from .simulation import Simulation, build_simulation
from .steward import Link, NetworkView, Steward, merchant
from .storage import Colony, MarketView, Policy, Storage
from .terrain import Terrain, generate_terrain
from .trade import Caravan, Payment, open_haggle, settle
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
    "HOST",
    "Haggle",
    "Link",
    "MarketView",
    "Move",
    "NetworkView",
    "Payment",
    "Policy",
    "Purse",
    "RoadNetwork",
    "Route",
    "Seat",
    "Settlement",
    "Simulation",
    "Speakers",
    "Species",
    "Steward",
    "Storage",
    "TRADER",
    "Terrain",
    "Wilds",
    "World",
    "bargain",
    "build_simulation",
    "caravans_allowed",
    "food_cover",
    "generate_roads",
    "merchant",
    "negotiate",
    "open_haggle",
    "road_links",
    "road_overlay",
    "generate_terrain",
    "generate_world",
    "populate",
    "settle",
]
