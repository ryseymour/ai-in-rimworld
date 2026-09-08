import subprocess
from pathlib import Path

from airim.bus import EventBus
from airim.publish import prepare_worktree, publish_once
from airim.replay import replay
from airim.state import ColonyState

FIX = Path(__file__).parent / "fixtures" / "sample.jsonl"


def _git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, text=True, capture_output=True, check=True).stdout


async def test_publish_round_trip(tmp_path):
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", "-q", str(remote))
    repo = tmp_path / "repo"
    _git(tmp_path, "init", "-q", str(repo))
    _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
    (repo / "README.md").write_text("x")
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "-u", "origin", "HEAD")

    wt = repo / "orchestrator" / ".telemetry"
    prepare_worktree(repo, wt)
    _git(wt, "config", "user.email", "t@t"); _git(wt, "config", "user.name", "t")

    log = tmp_path / "live.jsonl"
    bus = EventBus(ColonyState(), log)
    await replay(bus, FIX, speed=0)
    bus.close()

    assert publish_once(bus, wt, log) is True
    assert publish_once(bus, wt, log) is False  # nothing new -> no commit

    heads = _git(repo, "ls-remote", "--heads", "origin")
    assert "refs/heads/telemetry" in heads
    files = _git(wt, "ls-tree", "--name-only", "HEAD").split()
    assert {"live.jsonl", "state.json", "README.md"} <= set(files)
    # main branch untouched
    assert "live.jsonl" not in _git(repo, "ls-tree", "--name-only", "HEAD")
