# Desktop shells — Pipeline Hatch

Thin, per-platform wrappers around `launch.py` (plan U1.5 ③). They exist so a
double-click runs **the current working tree**, not a packaged snapshot.

```
launcher/launch.py                         # all the logic, stdlib only
launcher/macos/Pipeline Hatch.app/         # macOS bundle (Info.plist + MacOS/pipeline-hatch)
launcher/linux/Pipeline Hatch.desktop      # Linux desktop entry
launcher/windows/PipelineHatch.bat         # Windows batch shell
```

## Why not PyInstaller

`Pipeline Hatch.spec` ships an explicit `datas` whitelist and
`ConfigManager` reads shared YAML from `sys._MEIPASS/config` when frozen, so any
new config file (for example `config/env.yaml`) silently fails to appear in the
bundle until it is re-packaged. A rebuild also costs ~2 minutes per iteration.
The thin shell trades a 114 MB self-contained bundle for "always current code"
during development.

## Resolution order (`launch.py`)

1. `env/bin/pipeline-hatch` (console entry point) — **only if its shebang
   interpreter actually exists**. Project envs get copied between machines, so
   `env/bin/*` may still point at a dead path (e.g. the retired `/Volumes/Dev`);
   such an entry point is skipped instead of failing.
2. `env/bin/python -m launcher.main` — works without `pip install -e .`.
3. No env / no interpreter → GUI alert (osascript · zenity · MessageBox) plus a
   stderr line, non-zero exit.

Unix replaces the launcher process with `os.execv`, so no stray python lingers;
Windows spawns and relays the exit code.

Verify without opening the GUI:

```bash
python3 launcher/launch.py --print-command
# root: /Volumes/Development/tools/pipeline/pipeline_hatch
# cmd:  /Volumes/Development/tools/pipeline/pipeline_hatch/env/bin/python -m launcher.main
```

## Install

**macOS** — copy the bundle (it keeps an absolute path to the repo, so the repo
can stay anywhere):

```bash
cp -R "launcher/macos/Pipeline Hatch.app" ~/Applications/
open ~/Applications/"Pipeline Hatch.app"        # GUI
"$HOME/Applications/Pipeline Hatch.app/Contents/MacOS/pipeline-hatch" --print-command
```

**Linux** — copy the desktop entry and fix `Exec=` if the clone is not at
`/srv/share/dev/tools/pipeline/pipeline_hatch`. Keep the repo icon by adding
`Icon=/srv/share/dev/tools/pipeline/pipeline_hatch/launcher/ui/imgs/pipeline_hatch_icon.png`;
back up any pre-existing entry first (`*.bak.<timestamp>`).

```bash
cp "launcher/linux/Pipeline Hatch.desktop" ~/.local/share/applications/
update-desktop-database ~/.local/share/applications 2>/dev/null || true
```

Verified on `frank-mint` (Linux Mint, `/srv/share/dev/...`, Python 3.12):
`Exec=` line runs end to end and the GUI start degrades cleanly when Postgres is
down (offline/YAML mode). Desktop copies of the shortcut may need
`gio set <file> metadata::trusted true` before Cinnamon lets you double-click.

**Windows** — edit `LAUNCHER=` in `PipelineHatch.bat` to the clone path and
double-click it (or copy it to the Desktop). `%~dp0..\launch.py` is used when
the fallback path does not exist, i.e. running the `.bat` in place works.

## Maintenance

Each shell carries exactly **one** machine-specific value (the `LAUNCHER=` /
`Exec=` path). Everything else is derived — keep it that way, and keep
`launch.py` free of absolute paths.
