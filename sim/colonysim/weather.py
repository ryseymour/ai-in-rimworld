"""The calendar, the seasons, and the weather on the roads.

Four things follow from one year:

* **The land works to a calendar.** Each season multiplies what the land gives,
  and the four multipliers for a good average to exactly one -- so a year makes
  what the land always made, but it arrives in autumn rather than evenly. That
  is where harvest gluts and winter scarcity come from, and every price in the
  sim is a function of what is on the shelves, so prices move with them without
  anything being told to.
* **Weather is a property of the day, not of a place.** One sky over the whole
  map. It comes in spells of a few days rather than flickering, and it is drawn
  from the season's own table: blizzards are a winter thing, mud a spring one.
* **A road's own grade is what shelters it.** Weather slows a route in
  proportion to how poor the road is, and shuts it outright below a grade that
  the weather names. A foot path through the trees is impassable in the snow
  the paved trunk road merely slows down -- which makes paving a route the
  thing that buys a colony a winter economy.
* **The forecast is knowable.** Weather is generated forward and then fixed, so
  asking what day 40 looks like on day 35 gives the answer day 40 will actually
  have. Deliberately certain: a trader here is wrong about markets and wrong
  about wolves, and making it wrong about the sky as well would only blur what
  the seasons are doing. Noise belongs on top of this, not inside it.

Nothing in here imports the roads or the economy. It takes a road grade as a
number and gives back a multiplier, which is the whole of its interface to the
rest of the sim.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .goods import GOOD_NAMES

#: Days in a season, and so sixty in a year. Short enough that a run of a
#: couple of hundred days is several years and the cycle is visible, long
#: enough that a caravan's round trip is a small part of one.
SEASON_DAYS = 15

#: How much of the weather a road of each tier keeps off itself: no road, foot
#: path, dirt road, paved. The one table that decides whether weather is a flat
#: tax on trade or a reason to build roads.
TIER_SHELTER = (0.0, 0.15, 0.55, 0.85)


def shelter(grade: float) -> float:
    """How much weather a road of this grade keeps off, 0 to 1.

    `grade` is a mean tier along a route, so it is usually fractional: a route
    that is paved at one end and a path at the other sits between the two.
    """
    grade = max(0.0, min(float(len(TIER_SHELTER) - 1), grade))
    low = int(grade)
    if low >= len(TIER_SHELTER) - 1:
        return TIER_SHELTER[-1]
    return TIER_SHELTER[low] + (TIER_SHELTER[low + 1] - TIER_SHELTER[low]) * (grade - low)


@dataclass(frozen=True)
class Weather:
    """One day's sky.

    `severity` is what it does to travel before the road shelters any of it;
    `shuts_below` is the road grade under which it simply stops traffic, and
    zero for weather that never closes anything.
    """

    name: str
    severity: float
    shuts_below: float = 0.0
    #: Longest run of days this weather holds for once it sets in.
    spell: int = 3
    glyph: str = " "

    def exposure(self, grade: float) -> float:
        """The share of this weather a road of this grade actually wears."""
        return 1.0 - shelter(grade)

    def slowdown(self, grade: float) -> float:
        """Multiplier on how long a day's travel takes on a road this good.

        One is unhindered. Two means a caravan covers half a day's ground.
        """
        return 1.0 + self.severity * self.exposure(grade)

    def shuts(self, grade: float) -> bool:
        """Whether a road this poor is closed today."""
        return self.shuts_below > 0.0 and grade < self.shuts_below

    @property
    def is_fair(self) -> bool:
        return self.severity <= 0.0

    def describe(self, grade: float | None = None) -> str:
        if grade is None:
            return self.name
        if self.shuts(grade):
            return f"{self.name}, road shut"
        slow = self.slowdown(grade)
        if slow < 1.05:
            return self.name
        return f"{self.name}, {slow:.1f}x slower"


CLEAR = Weather("clear", severity=0.0, spell=4, glyph=".")
RAIN = Weather("rain", severity=0.45, spell=3, glyph="'")
MUD = Weather("mud", severity=0.70, spell=3, glyph=",")
HEAT = Weather("heat", severity=0.30, spell=3, glyph="-")
#: Snow only slows: a foot path in it takes the better part of two days to
#: walk a day of. Storms shut a bare track and nothing better, and a blizzard
#: shuts anything short of a well-worn dirt road -- so the roads a colony has
#: actually worn in are the ones it still trades over in winter, and closures
#: are a handful of days a year rather than a season of them.
STORM = Weather("storm", severity=1.10, shuts_below=1.20, spell=2, glyph="*")
SNOW = Weather("snow", severity=0.85, spell=3, glyph="#")
BLIZZARD = Weather("blizzard", severity=1.60, shuts_below=1.75, spell=2, glyph="%")

WEATHERS = {
    w.name: w for w in (CLEAR, RAIN, MUD, HEAT, STORM, SNOW, BLIZZARD)
}


@dataclass(frozen=True)
class Season:
    """A quarter of the year: what the land gives, and what the sky does.

    `growth` is per good, and the four seasons' values for any one good average
    to exactly 1.0 -- see `test_weather.py`. A year therefore produces what the
    land would have produced anyway; the seasons only decide when.
    """

    name: str
    growth: dict[str, float]
    #: Weather name to relative weight. Drawn from fresh at the end of each
    #: spell, so a season's character is how often each kind turns up.
    sky: dict[str, float]

    def yields(self, good: str) -> float:
        return self.growth.get(good, 1.0)


SPRING = Season(
    name="spring",
    growth={"food": 0.80, "wood": 1.05, "stone": 1.00, "cloth": 1.10, "tools": 0.95},
    sky={"clear": 0.35, "rain": 0.30, "mud": 0.20, "storm": 0.10, "snow": 0.05},
)
SUMMER = Season(
    name="summer",
    growth={"food": 1.20, "wood": 1.15, "stone": 1.30, "cloth": 1.30, "tools": 1.00},
    sky={"clear": 0.50, "heat": 0.25, "rain": 0.18, "storm": 0.07},
)
AUTUMN = Season(
    name="autumn",
    growth={"food": 1.80, "wood": 1.20, "stone": 1.15, "cloth": 1.25, "tools": 1.00},
    sky={"clear": 0.28, "rain": 0.32, "storm": 0.25, "mud": 0.10, "snow": 0.05},
)
WINTER = Season(
    name="winter",
    growth={"food": 0.20, "wood": 0.60, "stone": 0.55, "cloth": 0.35, "tools": 1.05},
    sky={"snow": 0.40, "clear": 0.22, "blizzard": 0.16, "storm": 0.14, "rain": 0.08},
)

SEASONS = (SPRING, SUMMER, AUTUMN, WINTER)
YEAR_DAYS = SEASON_DAYS * len(SEASONS)


@dataclass(frozen=True)
class Date:
    """A day, said the way a colony would say it."""

    day: int
    year: int
    season: Season
    day_of_season: int

    @property
    def name(self) -> str:
        return self.season.name

    @property
    def part(self) -> str:
        """Early, mid or late: enough to know whether winter is coming."""
        third = self.day_of_season / SEASON_DAYS
        return "early" if third <= 1 / 3 else "mid" if third <= 2 / 3 else "late"

    def __str__(self) -> str:
        return f"{self.part} {self.season.name}, year {self.year}"


def date_of(day: int) -> Date:
    """Day zero is the first day of the first spring."""
    day_of_year = day % YEAR_DAYS
    return Date(
        day=day,
        year=day // YEAR_DAYS + 1,
        season=SEASONS[day_of_year // SEASON_DAYS],
        day_of_season=day_of_year % SEASON_DAYS + 1,
    )


def season_of(day: int) -> Season:
    return date_of(day).season


#: How far ahead anyone bothers looking. A week is about a caravan's round
#: trip, which is the horizon a decision to set out actually spans.
FORECAST_DAYS = 7
#: How far ahead a colony plans its granary: one whole season, so "the season
#: ahead" is the next one for the whole of the current one. Filling the store
#: for winter is a thing a village does through autumn, not in its last week.
SEASON_AHEAD = SEASON_DAYS
#: Guard on working out how long a journey will take when the road keeps
#: shutting: past this multiple of the plain travel time, the answer is "it
#: isn't happening" rather than a longer and longer number.
MAX_DELAY = 5.0


@dataclass
class Climate:
    """The year over one world: its calendar, and the weather it has had.

    Weather is generated forward a spell at a time and then never changes, so
    the sequence is a property of the seed and the day and nothing else. Same
    seed, same year. Asking about a day that has not happened generates up to
    it, which is exactly what makes a forecast possible and exact.
    """

    seed: int = 0
    #: One entry per day from day zero. Grown on demand, never rewritten.
    _sky: list[Weather] = field(default_factory=list)
    _rng: random.Random | None = None

    def __post_init__(self) -> None:
        if self._rng is None:
            self._rng = random.Random(self.seed ^ 0x5EA5)

    # ------------------------------------------------------------- calendar
    def date(self, day: int) -> Date:
        return date_of(day)

    def season(self, day: int) -> Season:
        return season_of(day)

    def growth(self, day: int) -> dict[str, float]:
        """Today's multiplier on the land's output, per good."""
        return season_of(day).growth

    def coming_season(self, day: int, within: int = SEASON_AHEAD) -> Season:
        """The season a colony is about to be in.

        A full season ahead by default, so through the whole of autumn this
        says winter. That is what makes "lay in stores" a decision with a date
        on it rather than a mood that arrives too late to act on.
        """
        return season_of(day + within)

    # -------------------------------------------------------------- the sky
    def on(self, day: int) -> Weather:
        """The weather on a day, generating forward to it if need be."""
        day = max(0, day)
        assert self._rng is not None
        while len(self._sky) <= day:
            weather = self._draw(len(self._sky))
            self._sky.extend([weather] * self._rng.randint(1, weather.spell))
        return self._sky[day]

    def _draw(self, day: int) -> Weather:
        assert self._rng is not None
        sky = season_of(day).sky
        roll = self._rng.random() * sum(sky.values())
        for name, weight in sorted(sky.items()):
            roll -= weight
            if roll <= 0.0:
                return WEATHERS[name]
        return CLEAR

    def forecast(self, day: int, days: int = FORECAST_DAYS) -> tuple[Weather, ...]:
        """Today and the next few days, in order."""
        return tuple(self.on(day + ahead) for ahead in range(days))

    def outlook(self, day: int, grade: float = 1.0, days: int = FORECAST_DAYS) -> str:
        """The week ahead in one line, for a brief or a panel.

        Says the thing a trader needs -- what it is doing now, and how many of
        the coming days a road this good is shut for -- rather than listing
        seven skies.
        """
        ahead = self.forecast(day, days)
        shut = sum(1 for weather in ahead[1:] if weather.shuts(grade))
        worst = max(ahead[1:], key=lambda w: w.severity, default=CLEAR)
        line = f"{ahead[0].describe(grade)}"
        if shut:
            line += f"; {shut} of the next {len(ahead) - 1} days shut by {worst.name}"
        elif not worst.is_fair:
            line += f"; {worst.name} coming"
        else:
            line += "; fair ahead"
        return line

    # ------------------------------------------------------------- journeys
    def shut_today(self, day: int, grade: float) -> bool:
        return self.on(day).shuts(grade)

    def progress(self, day: int, grade: float) -> float:
        """How much of a day's travel a caravan gets done on this day.

        Zero when the road is shut: it sits the weather out rather than
        arriving late, which is what makes a closed route a closed route.
        """
        weather = self.on(day)
        if weather.shuts(grade):
            return 0.0
        return 1.0 / weather.slowdown(grade)

    def journey_days(self, day: int, plain_days: float, grade: float) -> float:
        """How long a journey of `plain_days` will really take, setting out on
        `day` into the forecast.

        This is the number a trader should be deciding on: the road as it is,
        walked through the sky that is coming. Capped, so a route the weather
        has simply closed reports a number that will lose to any open one
        rather than an ever-growing estimate.
        """
        if plain_days <= 0:
            return 0.0
        limit = plain_days * MAX_DELAY
        done = 0.0
        elapsed = 0.0
        while done < plain_days and elapsed < limit:
            elapsed += 1.0
            done += self.progress(day + int(elapsed), grade)
        return max(1.0, min(elapsed, limit))


def seasonal_totals() -> dict[str, float]:
    """Each good's growth summed over the year, for tests and for the reader.

    Every entry is `len(SEASONS)`, which is the invariant that keeps a world
    calibrated for a year's consumption still calibrated once there are
    seasons in it.
    """
    return {
        good: sum(season.yields(good) for season in SEASONS) for good in GOOD_NAMES
    }
