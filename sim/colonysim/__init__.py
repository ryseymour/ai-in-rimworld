"""The colony simulation: world, roads, storage, currency, trade, stewards,
haggling, people and the wild.

See `../wiki/design-inter-colony-trade.md` for the design this implements.
"""
from __future__ import annotations

from .crafting import Workshop, armed_strength, armoury, work_day
from .goods import CRAFTED_GOOD_NAMES, GOOD_NAMES, GOODS, RAW_GOOD_NAMES, Good
from .hunting import hunt
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
from .recipes import RECIPES, STATIONS, Recipe, Station
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
    "CRAFTED_GOOD_NAMES",
    "GOODS",
    "GOOD_NAMES",
    "HOST",
    "RAW_GOOD_NAMES",
    "RECIPES",
    "SILVER",
    "STATIONS",
    "TRADER",
    "WOLVES",
    "Caravan",
    "Colony",
    "Currency",
    "Den",
    "Encounter",
    "Good",
    "Haggle",
    "Link",
    "MarketView",
    "Move",
    "NetworkView",
    "Payment",
    "Policy",
    "Purse",
    "Recipe",
    "RoadNetwork",
    "Route",
    "Seat",
    "Settlement",
    "Simulation",
    "Speakers",
    "Species",
    "Station",
    "Steward",
    "Storage",
    "Terrain",
    "Wilds",
    "Workshop",
    "World",
    "armed_strength",
    "armoury",
    "bargain",
    "build_simulation",
    "caravans_allowed",
    "food_cover",
    "generate_roads",
    "generate_terrain",
    "generate_world",
    "hunt",
    "merchant",
    "negotiate",
    "open_haggle",
    "populate",
    "road_links",
    "road_overlay",
    "settle",
    "work_day",
]

