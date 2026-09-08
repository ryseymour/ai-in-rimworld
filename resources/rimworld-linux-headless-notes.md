# Running RimWorld headless on Linux: notes

Collected while building `tools/cloud/`. Verify against the actual build when first run; items marked (assumed) have not been confirmed in this project yet.

## Build layout
- Linux build folder contains `RimWorldLinux` (binary), `RimWorldLinux_Data/` (Unity data, `Managed/Assembly-CSharp.dll`), `Data/` (core defs), `Mods/`, `Version.txt`.
- Config and saves: `~/.config/unity3d/Ludeon Studios/RimWorld by Ludeon Studios/` with `Config/ModsConfig.xml`, `Config/Prefs.xml`, `Saves/`. Player log: same folder's `Player.log` unless `-logfile` is given.

## Useful command-line flags
- Unity standard: `-screen-width W -screen-height H -screen-fullscreen 0`, `-logfile PATH`, `-batchmode` (no rendering; RimWorld's UI needs rendering so avoid), `-popupwindow`.
- RimWorld: `-quicktest` starts a dev test map immediately (assumed to still exist in 1.6; it has been in the game since early versions). `-savedatafolder=PATH` relocates config/saves.

## ModsConfig.xml
```xml
<ModsConfigData>
  <version>1.6.4871 rev...</version>
  <activeMods>
    <li>ludeon.rimworld</li>
    <li>brrainz.harmony</li>
    <li>ryseymour.airim</li>
  </activeMods>
  <knownExpansions />
</ModsConfigData>
```
Package ids are lowercase. Core is `ludeon.rimworld`; DLCs are `ludeon.rimworld.royalty`, `.ideology`, `.biotech`, `.anomaly`, `.odyssey`.

## Harmony without the Workshop
The `Lib.Harmony` NuGet package ships `0Harmony.dll` for net472. A mod folder with that DLL in `Assemblies/` and an `About.xml` using packageId `brrainz.harmony` satisfies the dependency. See `tools/harmony-mod/`.

## Software rendering
`LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe` with Xvfb `-screen 0 1600x900x24`. Unity 2022 wants OpenGL 3.2+; `MESA_GL_VERSION_OVERRIDE=3.3` helps on older Mesa. Expect single-digit FPS on 4 cores; game ticks still run at normal speed unless the frame rate collapses, in which case RimWorld's tick catch-up will keep simulation time roughly right.

## Getting the Linux build
- Steam: Steam console `download_depot 294100 <depot>` or SteamCMD with `+@sSteamCmdForcePlatformType linux` and the owner's login. Depot ids change per release; check SteamDB.
- Ludeon direct-download store purchases and GOG provide Linux builds directly.
- Upload as a GitHub Release asset on the private repo (limit 2 GB per asset) so the cloud container can fetch it via `api.github.com/repos/.../releases/assets/ID` with `Accept: application/octet-stream`.
