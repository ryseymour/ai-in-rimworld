"""An optional adapter: letting a model do the talking at the counter.

Nothing in `colonysim` imports this module, and nothing in it runs unless you
ask for it twice -- once by importing it, once by setting `COLONYSIM_LLM=1` in
the environment. The package stays standard library only and installs with no
dependencies; this file is the worked example of what the negotiation seam is
*for*, and the one place an API key or a network call could ever enter the sim.

    from colonysim.llm import claude_negotiator
    from colonysim import build_simulation

    sim = build_simulation(seed=23, settlements=3)
    for steward in sim.stewards:
        steward.negotiator = claude_negotiator()
    sim.run(30)

Three things make that safe to leave running. The model is asked for one line
per turn, not for a plan -- a negotiation is at most a handful of calls, and
they only happen when a cart actually arrives somewhere. Whatever comes back
goes through `Haggle.play`, which clamps the price, the quantity and the act,
so a bad answer is a bad deal and never a broken world. And every failure --
no key, no package, a timeout, a reply nobody can parse -- falls through to the
scripted `bargain`, so the sim keeps running with a worse negotiator rather
than stopping.

`speaker_from` is the general form: give it anything that turns a prompt into a
line of text and you have a negotiator. That is the hook a player's own UI, a
local model, or a test double plugs into, with no Anthropic API involved.
"""
from __future__ import annotations

import os
import re
from typing import Callable

from .negotiation import (
    ACCEPT,
    COUNTER,
    OPEN,
    WALK,
    Haggle,
    Move,
    Speaker,
    bargain,
)

#: Set this to 1 to let the adapter make calls. Without it every speaker built
#: here is the scripted one, so importing this module changes nothing.
ENV_FLAG = "COLONYSIM_LLM"
#: Sonnet is the right size for this: one short line, a few times a day of
#: simulated time. `claude-opus-5` is the better negotiator if you would rather
#: pay for it; both take the same call.
DEFAULT_MODEL = "claude-sonnet-5"

SYSTEM = """You are a trader in a small pre-industrial colony simulation, \
haggling over one good at a market counter. You are given your own position, \
including a limit you must not cross, and whatever the other side has offered. \
Answer with exactly one line and nothing else:

ACCEPT -- take their standing offer as it is.
WALK -- end it with no deal.
COUNTER <price> <quantity> <one short sentence you say aloud>

Prices are per unit, to two decimals. Never cross your own limit. Keep what \
you say in character: plain, brief, and about this cart and these goods."""


def enabled() -> bool:
    return os.environ.get(ENV_FLAG, "").strip().lower() in ("1", "true", "yes", "on")


def parse_move(text: str, haggle: Haggle, side: str) -> Move | None:
    """Read one line back into a move, or None if it is not one.

    Deliberately forgiving about everything that does not matter -- case,
    leading chatter, a currency symbol -- and strict about the two things that
    do, which are the act and the number. `Haggle.play` does the clamping
    afterwards, so this only has to decide what was meant.
    """
    said = " ".join(str(text or "").split())
    if not said:
        return None
    head = said.upper()
    if head.startswith(ACCEPT.upper()) or head == "YES":
        return Move(side, ACCEPT, 0.0, 0.0, "")
    if head.startswith(WALK.upper()) or head.startswith("NO DEAL"):
        return Move(side, WALK, 0.0, 0.0, "")

    numbers = re.findall(r"-?\d+(?:\.\d+)?", said)
    if not numbers:
        return None
    price = float(numbers[0])
    qty = float(numbers[1]) if len(numbers) > 1 else haggle.seat(side).want
    # Whatever follows the numbers is what was said out loud; if the model
    # answered with bare figures, the move still stands, silently.
    tail = said
    for number in numbers[:2]:
        _, _, tail = tail.partition(number)
    line = tail.strip(" -:,.")
    act = OPEN if haggle.turns(side) == 0 else COUNTER
    return Move(side, act, price, qty, line)


def speaker_from(reply: Callable[[str], str], fallback: Speaker = bargain) -> Speaker:
    """Build a negotiator out of anything that answers a prompt with a line.

    This is the whole adapter: `Haggle.brief(side)` is the prompt, one line
    back is the move, and anything that goes wrong is the scripted negotiator's
    turn instead. A local model, a player at a keyboard and the Claude call
    below are all the same shape.
    """

    def speak(haggle: Haggle, side: str) -> Move:
        try:
            move = parse_move(reply(haggle.brief(side)), haggle, side)
        except Exception:
            move = None
        return move if move is not None else fallback(haggle, side)

    return speak


def claude_reply(model: str = DEFAULT_MODEL, client=None) -> Callable[[str], str]:
    """One prompt in, one line out, through the official Anthropic SDK.

    Imported here rather than at the top of the file so that `pip install
    colonysim` stays dependency-free: if the package is missing, or the flag is
    unset, this raises and `speaker_from` falls back.
    """

    def ask(prompt: str) -> str:
        if not enabled():
            raise RuntimeError(f"{ENV_FLAG} is not set")
        nonlocal client
        if client is None:
            import anthropic  # not a dependency of this package

            client = anthropic.Anthropic()
        response = client.messages.create(
            model=model,
            max_tokens=256,
            system=SYSTEM,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in response.content if block.type == "text"
        )

    return ask


def claude_negotiator(model: str = DEFAULT_MODEL, client=None) -> Speaker:
    """A negotiator that asks Claude what to say. Off unless `COLONYSIM_LLM=1`.

    Hang it on a steward -- `steward.negotiator = claude_negotiator()` -- and
    that colony argues its own corner; leave the others scripted and you can
    watch what the difference is worth in coin.
    """
    return speaker_from(claude_reply(model, client))
