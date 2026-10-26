# Pipeline Hatch

A configuration-driven DCC (Digital Content Creation) application launcher for VFX/animation pipelines. Built with PySide6.

> **Current Version:** 2.0.0  
> **Status:** Beta — actively developed

---

## Features

- 🚀 **Launch DCC Applications** — Maya, Houdini, Nuke with proper environment setup
- ⚙️ **Configuration-Driven** — All DCC paths, flags, and environment variables defined in YAML
- 🖥️ **Cross-Platform** — macOS, Linux, and Windows support
- 📁 **Project Browser** — Browse project, sequence, shot, and file hierarchies
- 🔄 **Auto-Refresh** — File system watcher automatically updates file lists
- 📝 **Logging** — Rotating file logs with console output
- 🏷️ **Department-First** — the department owns the work folder and the
  `DEPARTMENT` env var; the DCC only decides which application opens it
- 🧪 **Fully Tested** — 171 unit tests covering all core modules

---

## Quick Start

### Prerequisites

- Python 3.10 or later
- PySide6
- PyYAML

### Installation

```bash
# Clone the repository
git clone https://github.com/FrankShao832/pipeline-hatch.git
cd pipeline-hatch

# Install with pip (recommended)
pip install -e .

# Or with dev dependencies (for testing)
pip install -e ".[dev]"

# Or install dependencies manually
pip install -r requirements.txt
```

### Running

```bash
# Run the launcher
pipeline-hatch

# Or from a checkout, without installing (both forms work)
python -m launcher.main
python launcher/main.py
```

### Desktop launch (thin shell)

Double-clickable shells live in `launcher/` and delegate to
`launcher/launch.py`, which runs **the current working tree** (installed
`pipeline-hatch` entry point first, `env/bin/python -m launcher.main`
otherwise). They replace the packaged `Pipeline Hatch.app`: a PyInstaller bundle
ships an explicit `config/` whitelist, so new config files never reach it until
it is rebuilt.

```bash
python3 launcher/launch.py --print-command    # show what would run, no GUI

cp -R "launcher/macos/Pipeline Hatch.app" ~/Applications/           # macOS
cp "launcher/linux/Pipeline Hatch.desktop" ~/.local/share/applications/   # Linux
# Windows: launcher/windows/PipelineHatch.bat (edit the LAUNCHER= path)
```

See `launcher/README.md` for resolution order and the one machine-specific path
each shell keeps.

---

## Vocabulary (department vs DCC)

Two axes, never interchangeable — full version in
[`docs/VOCABULARY.md`](docs/VOCABULARY.md):

| Axis | What it decides | Where it lives |
|:--|:--|:--|
| **department** (`fx` / `comp` / `lighting` / `model` / …) | who owns the work: folder, approvals, farm pool, version counters | path segment, `DEPARTMENT`, database column |
| **dcc** (`maya` / `houdini` / `nuke` / `katana`) | which application opens it | launch target, file extensions, command flags, provenance |

Work folders are department-named. A department that runs several applications
nests the application inside it:

```
<project_root>/<show>/<seq>/<shot>/<department>             # e.g. …/cy_city_0010/comp
<project_root>/<show>/<seq>/<shot>/<department>/<dcc>        # e.g. …/demo_shot/fx/houdini
```

The launcher starts with **Select your department** unset: a work folder is only
resolved once a department is chosen. The DCC alone is not enough, and
app-named folders such as `<shot>/nuke` are kept only as a legacy fallback for
trees that have not been migrated.

See also `docs/VOCABULARY.md` for the six rules (a dcc name never carries data
identity; version counters are scoped to department + publish type; …).

---

## Configuration

### DCC Settings (`config/dcc.yaml`)

Define DCC applications with their paths, flags, and environment variables:

```yaml
dcc:
  maya:
    name: "Maya"
    role: "maya"
    app_name: "Maya.app"
    executable: "/Applications/Autodesk/maya2026/Maya.app/Contents/MacOS/Maya"
    flags:
      file: "-file"
      project: "-proj"

  houdini:
    name: "Houdini"
    role: "houdini"
    app_name: "Houdini FX 20.5.613.app"
    ...

  nuke:
    name: "Nuke"
    role: "nuke"
    app_name: "Nuke16.0v3.app"
    ...

pipeline:
  # Canonical department vocabulary — the data axis (names the work folder).
  departments:
    - model
    - rig
    - anim
    - layout
    - fx
    - lighting
    - comp
  env_vars:
    - DCC                 # application to launch (maya/houdini/nuke/katana)
    - DEPARTMENT          # department that owns the work (fx/comp/…)
    - CACHE_ROOT
    - PROJECT_ROOT
    - PUBLISH_ROOT
    - SHOW
    - SEQ
    - SHOT
    # PIPELINE_* mirrors — the publisher's primary source
    - PIPELINE_PROJECT
    - PIPELINE_SEQUENCE
    - PIPELINE_SHOT
    - PIPELINE_DEPARTMENT
    - PIPELINE_DCC
    - PIPELINE_USER
    # dev data root and its sibling roots
    - DEV
    - ASSET_ROOT
    - RENDER_ROOT
```

`ROLE` was renamed to `DCC` on 2026-09-08; `DEPARTMENT` is the second axis and
is what names the shot work folder.

### Project Settings (`config/projects.yaml`)

Define project roots and publish paths:

```yaml
projects:
  - name: "Demo"
    root: "${DEV}/projects/y_pipeline_projects"
    publish_root: "${DEV}/projects/y_pipeline_publish"
    enabled: true
```

---

## Project Structure

```
pipeline-hatch/
├── config/                    # YAML configuration files
│   ├── dcc.yaml              # DCC application settings
│   └── projects.yaml         # Project list and paths
├── docs/
│   └── VOCABULARY.md         # Department vs DCC, path templates, rules
├── launcher/
│   ├── main.py               # Application entry point
│   ├── launch.py             # Stdlib desktop launcher (no Qt import)
│   ├── core/                 # Core logic layer
│   │   ├── config_manager.py # YAML config loader (singleton)
│   │   └── dcc_manager.py    # DCC factory (singleton)
│   ├── dcc/                  # DCC implementations
│   │   ├── base_dcc.py       # Abstract base class
│   │   ├── dcc_maya.py       # Maya implementation
│   │   ├── dcc_houdini.py    # Houdini implementation
│   │   └── dcc_nuke.py       # Nuke implementation
│   ├── ui/                   # User interface
│   │   ├── main_window.py    # Main application window
│   │   ├── settings_window.py# Settings panel (three columns)
│   │   ├── viewmodels.py     # Scope-ordered env view-models
│   │   ├── fakes.py          # Fixture data source for the settings panel
│   │   ├── widgets/          # Department/DCC selectors, trees, badges
│   │   └── imgs/             # Icons and images
│   └── utils/
│       └── logger.py         # Logging module
├── tests/                    # Unit tests (171 tests)
│   ├── test_config.py        # ConfigManager + shipped dcc.yaml guards
│   ├── test_dcc.py           # DCC command building / launch cwd
│   ├── test_main_window*.py  # Window wiring, launch, settings, workdirs
│   ├── test_department_selector.py
│   ├── test_workdir_resolution.py
│   └── …                     # view-models, entry point, desktop launcher
└── plan/                     # Development plans
```

---

## Development

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=launcher --cov-report=term-missing

# Run specific test file
pytest tests/test_config.py -v
```

### Type Checking

```bash
pyright
```

### Architecture

The application follows a clean three-layer architecture:

```
┌─────────────────────────────────────┐
│            UI Layer                  │
│  main_window.py / settings_window.py│
│  (layout, events, user interaction) │
├──────────────────┬──────────────────┤
│   Core Layer     │   DCC Layer      │
│  config_manager  │  base_dcc.py     │
│  dcc_manager     │  dcc_maya.py     │
│  (logic, API)    │  (implementation)│
└──────────────────┴──────────────────┘
```

**Design Patterns:**
- **Singleton** — ConfigManager, DCCManager, Logger
- **Factory** — DCCManager.get_dcc() creates DCC instances by role
- **Template Method** — BaseDCC defines build_command() interface
- **Configuration-Driven** — All settings in YAML, no hardcoded paths

---

## License

MIT License — see [LICENSE](LICENSE) for details.
