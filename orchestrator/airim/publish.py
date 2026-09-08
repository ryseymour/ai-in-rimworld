"""Publish the live session log and a state summary to a git branch.

Lets a remote collaborator (Claude, in another session) follow a test run
by fetching the `telemetry` branch. Runs git in a dedicated worktree so the
main checkout is never touched.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import time
from pathlib import Path

from .bus import EventBus

log = logging.getLogger(__name__)


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=check)


def prepare_worktree(repo: Path, worktree: Path, branch: str = "telemetry") -> None:
    """Create (or reuse) a worktree on an orphan branch for telemetry files."""
    if (worktree / ".git").exists():
        return
    worktree.parent.mkdir(parents=True, exist_ok=True)
    have_remote = _git(repo, "ls-remote", "--heads", "origin", branch, check=False).stdout.strip() != ""
    if have_remote:
        _git(repo, "fetch", "origin", branch)
        _git(repo, "worktree", "add", "-B", branch, str(worktree), f"origin/{branch}")
    else:
        _git(repo, "worktree", "add", "--detach", str(worktree))
        _git(worktree, "checkout", "--orphan", branch)
        _git(worktree, "rm", "-rf", "--quiet", ".", check=False)
        (worktree / "README.md").write_text("Telemetry branch: live logs from test sessions. Auto-committed by `airim serve --publish`.\n")
        _git(worktree, "add", "-A")
        _git(worktree, "commit", "-q", "-m", "Start telemetry branch")


def publish_once(bus: EventBus, worktree: Path, log_path: Path | None) -> bool:
    """Copy the log and state summary into the worktree, commit and push. Returns True if pushed."""
    if log_path and log_path.exists():
        shutil.copyfile(log_path, worktree / "live.jsonl")
    summary = bus.state.snapshot()
    summary["published_at"] = int(time.time())
    (worktree / "state.json").write_text(json.dumps(summary, indent=1))
    _git(worktree, "add", "-A")
    if _git(worktree, "diff", "--cached", "--quiet", check=False).returncode == 0:
        return False
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    counts = bus.state.counts
    msg = f"telemetry {stamp}: {sum(counts.values())} events, {len(bus.state.pawns)} pawns"
    _git(worktree, "commit", "-q", "-m", msg)
    r = _git(worktree, "push", "-u", "origin", "HEAD", check=False)
    if r.returncode != 0:
        log.warning("telemetry push failed: %s", r.stderr.strip()[-300:])
        return False
    return True


async def publish_loop(bus: EventBus, repo: Path, log_path: Path | None, interval: float = 30.0) -> None:
    worktree = repo / "orchestrator" / ".telemetry"
    try:
        prepare_worktree(repo, worktree)
    except subprocess.CalledProcessError as e:
        log.error("could not prepare telemetry worktree: %s", e.stderr)
        return
    log.info("publishing telemetry to branch 'telemetry' every %.0fs", interval)
    while True:
        await asyncio.sleep(interval)
        try:
            if await asyncio.to_thread(publish_once, bus, worktree, log_path):
                log.info("telemetry pushed")
        except Exception as e:  # noqa: BLE001
            log.warning("telemetry publish error: %s", e)
