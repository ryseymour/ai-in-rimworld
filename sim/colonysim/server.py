"""Serve the running world in a browser.

    python -m colonysim.server
    open http://127.0.0.1:7700

Standard library only: no framework, no build step, nothing to install. The
page asks for the terrain once, then polls for the state that changes.
"""
from __future__ import annotations

import argparse
import errno
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .goods import GOOD_NAMES
from .reputation import describe
from .simulation import build_simulation
from .terrain import FOREST_LEVEL, ROUGH_LEVEL, WATER_LEVEL
from .trade import OUTBOUND

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Colony trade</title>
<style>
  :root {
    --bg: #14161a; --panel: #1c1f25; --line: #2b2f37;
    --text: #e6e8ec; --dim: #99a0ad; --accent: #e0a458;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 14px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }
  header {
    display: flex; gap: 20px; align-items: center; flex-wrap: wrap;
    padding: 12px 16px; border-bottom: 1px solid var(--line);
  }
  h1 { font-size: 15px; margin: 0; font-weight: 600; letter-spacing: .02em; }
  .stat { color: var(--dim); }
  .stat b { color: var(--text); font-weight: 600; }
  button, input[type=range] { font: inherit; }
  button {
    background: var(--panel); color: var(--text); border: 1px solid var(--line);
    border-radius: 6px; padding: 4px 12px; cursor: pointer;
  }
  button:hover { border-color: var(--accent); }
  main { display: flex; gap: 16px; padding: 16px; align-items: flex-start; flex-wrap: wrap; }
  canvas { background: #0e1013; border: 1px solid var(--line); border-radius: 8px; max-width: 100%; }
  aside { flex: 1 1 340px; min-width: 300px; display: flex; flex-direction: column; gap: 16px; }
  section { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; }
  h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .08em;
       color: var(--dim); margin: 0 0 8px; font-weight: 600; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: right; color: var(--dim); font-weight: 500; padding: 2px 0 6px; }
  th:first-child, td:first-child { text-align: left; }
  td { text-align: right; padding: 2px 0; }
  .hungry { color: #e06c5a; }
  .route { display: flex; justify-content: space-between; gap: 10px; padding: 3px 0; }
  .route span:last-child { color: var(--dim); text-align: right; }
  .empty { color: var(--dim); }
  .steward { padding: 4px 0; border-top: 1px solid var(--line); }
  .steward:first-child { border-top: 0; }
  .steward .who { display: flex; justify-content: space-between; gap: 10px; }
  .steward .note { color: var(--dim); font-size: 12px; }
  .up { color: #e0a458; }
  .down { color: #7fb3d5; }
  .standing { display: flex; justify-content: space-between; gap: 10px; padding: 3px 0; }
  .standing .note { color: var(--dim); font-size: 12px; }
  .trusts { color: #7fbf8f; }
  .distrusts { color: #e06c5a; }
</style>
</head>
<body>
<header>
  <h1>Colony trade</h1>
  <span class="stat">day <b id="day">-</b></span>
  <span class="stat"><b id="flight">-</b> on the road</span>
  <span class="stat"><b id="people">-</b> people</span>
  <span class="stat"><b id="journeys">-</b> journeys</span>
  <span class="stat"><b id="met">-</b> met in the wild</span>
  <span class="stat"><b id="refusals">-</b> turned away</span>
  <button id="pause">pause</button>
  <span class="stat">speed
    <input id="speed" type="range" min="1" max="20" value="4">
    <b id="speedval">4</b>/s
  </span>
</header>
<main>
  <canvas id="map"></canvas>
  <aside>
    <section><h2>Caravans</h2><div id="caravans"></div></section>
    <section><h2>Storage</h2><div id="colonies"></div></section>
    <section><h2>Stewards</h2><div id="stewards"></div></section>
    <section><h2>Standing</h2><div id="standing"></div></section>
  </aside>
</main>
<script>
const TILE = 9;
const COLOR = { water: "#16304d", plains: "#4a6b3c", forest: "#26492f", rough: "#5c564c" };
const ROAD = { 1: "#6d6048", 2: "#9a8460", 3: "#c4ad84" };
const DEN = { wolves: "#8d6b9c", bears: "#a35f4a" };
let world = null;

const canvas = document.getElementById("map");
const ctx = canvas.getContext("2d");

async function loadWorld() {
  world = await (await fetch("world")).json();
  canvas.width = world.width * TILE;
  canvas.height = world.height * TILE;
}

function drawBase() {
  for (let y = 0; y < world.height; y++) {
    for (let x = 0; x < world.width; x++) {
      ctx.fillStyle = COLOR[world.kinds[y * world.width + x]];
      ctx.fillRect(x * TILE, y * TILE, TILE, TILE);
    }
  }
}

function draw(state) {
  drawBase();

  for (const [x, y, tier] of state.roads) {
    ctx.fillStyle = ROAD[tier] || ROAD[1];
    ctx.fillRect(x * TILE + 1, y * TILE + 1, TILE - 2, TILE - 2);
  }

  // Dens under everything else: the country a road runs through, not a thing
  // sitting on the road. Radius follows the pack's strength.
  for (const [x, y, species, strength] of state.dens || []) {
    const cx = x * TILE + TILE / 2, cy = y * TILE + TILE / 2;
    ctx.beginPath();
    ctx.arc(cx, cy, TILE * (0.6 + 1.6 * strength), 0, Math.PI * 2);
    ctx.fillStyle = DEN[species] || DEN.wolves;
    ctx.globalAlpha = 0.16 + 0.24 * strength;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.beginPath();
    ctx.arc(cx, cy, TILE * 0.3, 0, Math.PI * 2);
    ctx.fillStyle = DEN[species] || DEN.wolves;
    ctx.fill();
  }

  ctx.font = "600 11px ui-monospace, Menlo, monospace";
  ctx.textAlign = "center";
  for (const s of world.settlements) {
    const cx = s.x * TILE + TILE / 2, cy = s.y * TILE + TILE / 2;
    ctx.beginPath();
    ctx.arc(cx, cy, TILE * 0.72, 0, Math.PI * 2);
    ctx.fillStyle = "#e6e8ec";
    ctx.fill();
    ctx.fillStyle = "#14161a";
    ctx.fillText(String(s.id), cx, cy + 4);
    ctx.fillStyle = "#c9cdd6";
    ctx.fillText(s.name, cx, cy - TILE);
  }

  for (const c of state.caravans) {
    const cx = c.x * TILE + TILE / 2, cy = c.y * TILE + TILE / 2;
    ctx.beginPath();
    ctx.arc(cx, cy, TILE * 0.5, 0, Math.PI * 2);
    ctx.fillStyle = c.outbound ? "#e0a458" : "#7fb3d5";
    ctx.fill();
    if (c.escorted) {          // a ring of guards around the cart
      ctx.beginPath();
      ctx.arc(cx, cy, TILE * 0.8, 0, Math.PI * 2);
      ctx.strokeStyle = "#e6e8ec";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
  }
}

function panels(state) {
  document.getElementById("day").textContent = state.day;
  document.getElementById("flight").textContent = state.caravans.length;
  document.getElementById("people").textContent = state.people;
  document.getElementById("journeys").textContent = state.journeys;
  document.getElementById("met").textContent = state.met;
  document.getElementById("refusals").textContent = state.refusals;

  const routes = document.getElementById("caravans");
  routes.innerHTML = state.caravans.length
    ? state.caravans.map(c =>
        `<div class="route"><span>${c.home} ${c.outbound ? "&rarr;" : "&larr;"} ${c.destination}` +
        `${c.escorted ? " (guarded)" : ""}</span>` +
        `<span>${c.cargo || "empty"}</span></div>`).join("")
    : '<div class="empty">none on the road</div>';

  const stewards = document.getElementById("stewards");
  stewards.innerHTML = (state.stewards || []).length
    ? state.stewards.map(s => {
        const prices = s.prices.length
          ? s.prices.map(p =>
              `<span class="${p.at > 1 ? "up" : "down"}">${p.good} &times;${p.at.toFixed(2)}</span>`
            ).join(", ")
          : '<span class="empty">prices as they come</span>';
        const note = [s.holding, s.working].filter(Boolean).join(" &middot; ");
        return `<div class="steward"><div class="who"><span>${s.name}</span>` +
               `<span>${prices}</span></div>` +
               (note ? `<div class="note">${note}</div>` : "") +
               (s.note ? `<div class="note">${s.note}</div>` : "") + "</div>";
      }).join("")
    : '<div class="empty">nobody is minding the shop</div>';

  const standing = document.getElementById("standing");
  standing.innerHTML = (state.standing || []).length
    ? state.standing.map(r => {
        const tone = r.at > 0.2 ? "trusts" : r.at < -0.2 ? "distrusts" : "";
        return `<div class="standing"><span>${r.from} &rarr; ${r.to}</span>` +
               `<span class="${tone}">${r.word} ${r.at > 0 ? "+" : ""}${r.at.toFixed(2)}</span></div>` +
               (r.note ? `<div class="note">${r.note}</div>` : "");
      }).join("")
    : '<div class="empty">everyone is still a stranger</div>';

  const head = "<tr><th>colony</th><th>people</th>" +
    state.goods.map(g => `<th>${g}</th>`).join("") + "<th>coin</th></tr>";
  const rows = state.colonies.map(c => {
    // An arrow only where the colony has actually moved off its founding
    // size, so a steady village reads as steady rather than as noise.
    const trend = c.trend > 0 ? '<span class="up">&uarr;</span>'
                : c.trend < 0 ? '<span class="down">&darr;</span>' : "";
    return `<tr class="${c.hungry ? "hungry" : ""}"><td>${c.name}</td>` +
      `<td>${c.people}${trend}</td>` +
      c.stock.map(v => `<td>${v}</td>`).join("") + `<td>${c.coin}</td></tr>`;
  }).join("");
  document.getElementById("colonies").innerHTML = `<table>${head}${rows}</table>`;
}

async function tick() {
  try {
    const state = await (await fetch("state")).json();
    draw(state);
    panels(state);
  } catch (e) { /* server stopped; keep the last frame */ }
}

const pause = document.getElementById("pause");
pause.onclick = async () => {
  const state = await (await fetch("control?toggle=1")).json();
  pause.textContent = state.paused ? "resume" : "pause";
};

const speed = document.getElementById("speed");
speed.oninput = () => {
  document.getElementById("speedval").textContent = speed.value;
  fetch("control?speed=" + speed.value);
};

loadWorld().then(() => { tick(); setInterval(tick, 120); });
</script>
</body>
</html>
"""


class Clock:
    """Advances the world on wall-clock time, so every browser watching sees
    the same day and no day is run twice."""

    def __init__(self, sim, days_per_second: float, limit: int) -> None:
        self.sim = sim
        self.days_per_second = days_per_second
        self.limit = limit
        self.paused = False
        self.last = time.monotonic()

    def catch_up(self) -> None:
        now = time.monotonic()
        if self.paused or self.days_per_second <= 0:
            self.last = now
            return
        due = int((now - self.last) * self.days_per_second)
        if due <= 0:
            return
        self.last = now
        for _ in range(min(due, 20)):  # never block the request on a long catch-up
            if self.limit and self.sim.day >= self.limit:
                break
            self.sim.step_day()


def world_payload(sim) -> dict:
    terrain = sim.world.terrain
    kinds = [
        terrain.kind(x, y) for y in range(terrain.height) for x in range(terrain.width)
    ]
    return {
        "width": terrain.width,
        "height": terrain.height,
        "kinds": kinds,
        "settlements": [
            {"id": s.id, "name": s.name, "x": s.x, "y": s.y} for s in sim.world.settlements
        ],
        "thresholds": {"water": WATER_LEVEL, "forest": FOREST_LEVEL, "rough": ROUGH_LEVEL},
    }


def cargo_text(cargo: dict[str, float]) -> str:
    carried = sorted(((q, g) for g, q in cargo.items() if q >= 0.5), reverse=True)
    return ", ".join(f"{q:.0f} {g}" for q, g in carried[:3])


def steward_payload(sim) -> list[dict]:
    """What each steward has done to its colony, for the panel beside the map.

    Only what it actually changed: a steward leaving its prices alone should
    look like a steward leaving its prices alone, not a wall of 1.00x.
    """
    out = []
    for steward in sim.stewards:
        stance = steward.stance()
        out.append(
            {
                "name": steward.name,
                "prices": [
                    {"good": good, "at": at} for good, at in stance["markup"].items()
                ],
                "holding": ", ".join(
                    f"{good} kept {steward.colony.reserve_days(good):.0f}d"
                    for good in stance["reserve"]
                ),
                "working": ", ".join(
                    f"{good} work {at:.2f}x" for good, at in stance["focus"].items()
                ),
                "note": steward.log[-1] if steward.log else "",
            }
        )
    return out


#: Rows in the standing panel. The worst-regarded pairs are the interesting
#: ones, and a six-colony world has thirty pairs, which is a wall rather than
#: a panel.
STANDING_ROWS = 8


def standing_payload(sim) -> list[dict]:
    """What colonies make of each other, worst first.

    One row per opinion anyone actually holds, with the last thing that moved
    it -- so the panel says who is unwelcome where, and why.
    """
    rows = []
    for a, b, standing in sim.standings()[:STANDING_ROWS]:
        remarks = sim.colonies[a].reputation.about(b)
        rows.append(
            {
                "from": sim.colonies[a].name,
                "to": sim.colonies[b].name,
                "at": round(standing, 2),
                "word": describe(standing),
                "note": remarks[-1].detail if remarks else "",
            }
        )
    return rows


def _trend(colony) -> int:
    """+1 for a colony that has grown, -1 for one that has lost people."""
    return 1 if colony.growth >= 1.0 else -1 if colony.growth <= -1.0 else 0


def state_payload(sim) -> dict:
    hungry = set(sim.hungry_colonies())
    caravans = []
    for caravan in sorted(sim.caravans, key=lambda c: c.id):
        spot = caravan.position
        if spot is None:
            continue
        caravans.append(
            {
                "id": caravan.id,
                "x": spot[0],
                "y": spot[1],
                "home": sim.colonies[caravan.home].name,
                "destination": sim.colonies[caravan.destination].name,
                "outbound": caravan.state == OUTBOUND,
                "escorted": caravan.escorted,
                "cargo": cargo_text(caravan.cargo),
            }
        )
    return {
        "day": sim.day,
        "journeys": sim.journeys,
        "goods": list(GOOD_NAMES),
        "roads": [[x, y, tile.tier] for (x, y), tile in sim.network.tiles.items()],
        # Dens are state, not world: packs thin where traffic passes and grow
        # back where it does not, so the map has to keep up.
        "dens": [
            [den.x, den.y, den.species, round(den.strength, 2)]
            for den in (sim.wilds.dens if sim.wilds else ())
            if den.strength > 0.0
        ],
        "met": sim.meetings,
        "people": round(sim.population()),
        "raided": sim.raids,
        "stewards": steward_payload(sim),
        "standing": standing_payload(sim),
        "refusals": sim.refusals,
        "caravans": caravans,
        "colonies": [
            {
                "name": c.name,
                "people": round(c.population),
                # Which way the colony has gone since it was founded, not which
                # way it went today: population moves by fractions of a person
                # a day, so a daily reading would only ever flicker.
                "trend": _trend(c),
                "stock": [round(c.storage.get(g)) for g in GOOD_NAMES],
                "coin": round(c.purse.amount),
                "hungry": c.name in hungry,
            }
            for c in sim.colonies
        ],
    }


def make_handler(clock: Clock):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: dict) -> None:
            self._send(json.dumps(payload).encode(), "application/json")

        def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
            route = urlparse(self.path)
            path = route.path.strip("/")
            query = parse_qs(route.query)

            if path in ("", "index.html"):
                self._send(PAGE.encode(), "text/html; charset=utf-8")
            elif path == "world":
                self._json(world_payload(clock.sim))
            elif path == "state":
                clock.catch_up()
                self._json(state_payload(clock.sim))
            elif path == "control":
                if "toggle" in query:
                    clock.paused = not clock.paused
                    clock.last = time.monotonic()
                if "speed" in query:
                    clock.days_per_second = max(0.0, float(query["speed"][0]))
                    clock.last = time.monotonic()
                self._json({"paused": clock.paused, "speed": clock.days_per_second})
            else:
                self.send_error(404)

        def log_message(self, *args) -> None:
            """Quiet: one line per poll would bury the address we printed."""

    return Handler


#: How many ports to try before giving up. The default is a popular number and
#: something else of yours may already be sitting on it.
PORT_ATTEMPTS = 10


def serve_somewhere(host: str, port: int, handler) -> ThreadingHTTPServer | None:
    """Bind the first free port at or above `port`, or None if none is free."""
    for candidate in range(port, port + PORT_ATTEMPTS):
        try:
            return ThreadingHTTPServer((host, candidate), handler)
        except OSError as exc:
            if exc.errno not in (errno.EADDRINUSE, errno.EACCES):
                raise
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Serve the trading world in a browser.")
    ap.add_argument("--port", type=int, default=7700)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--seed", type=int, default=23)
    ap.add_argument("--width", type=int, default=90)
    ap.add_argument("--height", type=int, default=45)
    ap.add_argument("--settlements", type=int, default=3)
    ap.add_argument(
        "--no-stewards",
        action="store_true",
        help="leave every colony trading on bare scarcity",
    )
    ap.add_argument("--speed", type=float, default=4.0, help="days per second")
    ap.add_argument("--days", type=int, default=0, help="stop after N days (0 = forever)")
    args = ap.parse_args()

    sim = build_simulation(
        args.seed,
        args.settlements,
        args.width,
        args.height,
        stewards=not args.no_stewards,
    )
    clock = Clock(sim, args.speed, args.days)
    server = serve_somewhere(args.host, args.port, make_handler(clock))
    if server is None:
        print(
            f"ports {args.port} to {args.port + PORT_ATTEMPTS - 1} on {args.host} are "
            f"all busy. Free one, or choose another with --port."
        )
        raise SystemExit(1)

    port = server.server_address[1]
    if port != args.port:
        print(f"port {args.port} was busy, so this is on {port} instead.")
    print(f"colony trade running at http://{args.host}:{port}")
    print("ctrl-c to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
