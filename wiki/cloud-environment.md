# Cloud Environment: what Claude's remote session can and cannot do

Recorded 2026-09-08 from direct probes. Re-check when the environment or network policy changes.

## The session

- Runs in Anthropic's cloud container (environment "Default", kind `anthropic_cloud`). Not on the user's machine. It cannot launch programs, see the screen, or read files on the user's computer.
- The container is ephemeral. Anything not pushed to GitHub is lost when the session is reclaimed. Setup must be re-runnable from scripts (`tools/cloud/setup.sh`).
- Resources seen: 4 CPUs, 15 GB RAM, ~30 GB writable disk. No GPU.
- `Xvfb`, Mesa `llvmpipe`, and ImageMagick install fine via apt, so a windowed Unity game can run on a virtual display with software rendering and be screenshotted.
- .NET 8 SDK installs via apt (`dotnet-sdk-8.0`). Python 3.11, Node 22, `uv`, and Chromium/Playwright are preinstalled.

## Network (egress proxy, org policy)

| Destination | Reachable | Notes |
|---|---|---|
| nuget.org, pypi.org, npm | yes | Package installs work. RimRef and Harmony come from nuget. |
| api.github.com (repo-scoped endpoints) | yes | Only for repos attached to the session. Account-level calls like creating a repo return 403 by design. |
| objects.githubusercontent.com | yes | **GitHub Release assets download.** This is the route for large private files such as the game build. |
| github.com web pages | no (400/403) | Raw web fetches fail; git operations go through the session's git proxy and work. |
| dot.net, builds.dotnet.microsoft.com | no | Use apt instead. |
| Steam (steampowered.com, steamcdn) | no | SteamCMD is impossible here. |
| GOG | no | |
| drive.google.com, drive.usercontent.google.com | no | Google Drive MCP tools exist but return file content as base64 into the conversation, unusable for large files. |
| rimworldwiki.com, ludeon.com, steamcommunity.com, arxiv.org | no | Research agents worked from search snippets for these. |

## GitHub

- The session's git token and the GitHub MCP server are both scoped to attached repositories. Neither can create a repository; the user creates it at github.com/new and grants the Claude GitHub App access, then `add_repo` attaches it.
- Pushing from the local clone works normally once attached.

## Ways for Claude to observe a test run

1. **Telemetry branch (works today).** `airim serve --publish` commits the live log and state summary to the `telemetry` branch every 30 s. Claude polls with a scheduled reminder. Latency about one minute. No screen.
2. **Run the game in the container (set up, untested).** The RimWorld Linux build uploaded as a GitHub Release asset; `tools/cloud/setup.sh` and `tools/cloud/run.sh` start it under Xvfb with the dev `-quicktest` colony; Claude screenshots the display and reads the logs directly. Full involvement, low frame rate.
3. **Session webhook.** `watch_url` gives an inbound URL, but it rejects unsigned posts (401); only the artifact service can sign. Not usable from the orchestrator.
4. **Local Claude Code session on the user's machine.** Can launch the real game and take screenshots. Coordinate with this session through the repo.

## Lessons

- Probe reachability with `curl -sS -o /dev/null -w "%{http_code}"` before planning around a host. `000` plus a CONNECT 403 means policy-blocked.
- Global CLI flags for `airim` go before the subcommand (`airim --http-port 7600 replay ...`).
- Keep everything re-creatable from the repo. The tarball backup was a stopgap before the repo existed.
