"""The colony simulation: world, roads, storage, currency, trade, stewards,
haggling, people, reputation, the wild, and the year over all of it.

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
from .reputation import Remark, Reputation
from .roads import (
    RoadNetwork,
    Route,
    generate_roads,
    journey_grade,
    road_links,
    road_overlay,
    route_grade,
)
from .simulation import SeasonTally, Simulation, build_simulation
from .steward import Link, NetworkView, Steward, merchant
from .storage import Colony, MarketView, Policy, Storage
from .terrain import Terrain, generate_terrain
from .trade import Caravan, Payment, open_haggle, settle
from .weather import (
    SEASON_DAYS,
    SEASONS,
    YEAR_DAYS,
    Climate,
    Date,
    Season,
    Weather,
    date_of,
    season_of,
)
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
    "Climate",
    "Colony",
    "Currency",
    "Date",
    "Den",
    "Encounter",
    "GOODS",
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
    "Remark",
    "Reputation",
    "RoadNetwork",
    "Route",
    "SEASONS",
    "SEASON_DAYS",
    "Season",
    "SeasonTally",
    "Seat",
    "Settlement",
    "Simulation",
    "Speakers",
    "Species",
    "Station",
    "Steward",
    "Storage",
    "Terrain",
    "WOLVES",
    "Weather",
    "Wilds",
    "Workshop",
    "World",
    "YEAR_DAYS",
    "armed_strength",
    "armoury",
    "bargain",
    "build_simulation",
    "caravans_allowed",
    "date_of",
    "food_cover",
    "generate_roads",
    "generate_terrain",
    "generate_world",
    "hunt",
    "journey_grade",
    "merchant",
    "negotiate",
    "open_haggle",
    "populate",
    "road_links",
    "road_overlay",
    "route_grade",
    "season_of",
    "settle",
    "work_day",
]

