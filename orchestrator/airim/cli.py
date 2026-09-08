"""Command line entry point."""
from __future__ import annotations

import argparse
import asyncio
import logging
import time
from pathlib import Path

from . import dashboard, publish, receiver, replay
from .bus import EventBus
from .state import ColonyState


def _log_path(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    return root / time.strftime("session-%Y%m%d-%H%M%S.jsonl")


async def run_serve(args: argparse.Namespace) -> None:
    log_path = None if args.no_log else _log_path(Path(args.log_dir))
    bus = EventBus(ColonyState(), log_path)
    await receiver.serve(bus, args.host, args.mod_port)
    await dashboard.serve(bus, args.host, args.http_port)
    if args.publish:
        repo = Path(__file__).resolve().parents[2]
        asyncio.create_task(publish.publish_loop(bus, repo, log_path, args.publish_interval))
    try:
        await asyncio.Event().wait()
    finally:
        bus.close()


async def run_replay(args: argparse.Namespace) -> None:
    bus = EventBus(ColonyState())
    await dashboard.serve(bus, args.host, args.http_port)
    await replay.replay(bus, Path(args.log), args.speed, args.loop)
    if args.hold:
        await asyncio.Event().wait()


def main() -> None:
    ap = argparse.ArgumentParser(prog="airim")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--http-port", type=int, default=7600)
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="listen for the mod and serve the dashboard")
    s.add_argument("--mod-port", type=int, default=7601)
    s.add_argument("--log-dir", default="logs")
    s.add_argument("--no-log", action="store_true")
    s.add_argument("--publish", action="store_true", help="push live log + state to the 'telemetry' git branch")
    s.add_argument("--publish-interval", type=float, default=30.0)

    r = sub.add_parser("replay", help="replay a recorded log into the dashboard")
    r.add_argument("log")
    r.add_argument("--speed", type=float, default=10.0)
    r.add_argument("--loop", action="store_true")
    r.add_argument("--hold", action="store_true", help="keep serving after the log ends")

    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(run_serve(args) if args.cmd == "serve" else run_replay(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
