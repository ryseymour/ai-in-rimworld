# Running the game in a cloud container

For test sessions where Claude drives the game itself. Needs the RimWorld **Linux** build uploaded as a GitHub Release asset on this repo (private repo, so it stays private).

1. `tools/cloud/setup.sh <asset id or url>` installs Xvfb + Mesa, builds the mod, downloads and unpacks the game, symlinks Harmony and AiRim into `Mods/`, and writes `ModsConfig.xml` and `Prefs.xml` (dev mode on, windowed 1600x900, sound off).
2. `QUICKTEST=1 PUBLISH=1 tools/cloud/run.sh` starts the orchestrator and the game on display :99 with a dev quicktest colony.
3. `tools/cloud/shot.sh` grabs a screenshot; `~/rimworld-logs/player.log` is the Unity log.

Rendering is llvmpipe software GL, so expect low frame rates. That's fine: the point is the event stream, not the picture.
