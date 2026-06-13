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
- 🧪 **Fully Tested** — 55+ unit tests covering all core modules

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

# Or directly
python launcher/main.py
```

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
  env_vars:
    - ROLE
    - PROJECT_ROOT
    - PUBLISH_ROOT
    - SHOW
    - SEQ
    - SHOT
```

### Project Settings (`config/projects.yaml`)

Define project roots and publish paths:

```yaml
projects:
  - name: "Demo"
    root: "/Volumes/Projects/y_pipeline_projects"
    publish_root: "/Volumes/Projects/y_pipeline_publish"
    enabled: true
```

---

## Project Structure

```
pipeline-hatch/
├── config/                    # YAML configuration files
│   ├── dcc.yaml              # DCC application settings
│   └── projects.yaml         # Project list and paths
├── launcher/
│   ├── main.py               # Application entry point
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
│   │   ├── settings_window.py# Settings dialog
│   │   └── imgs/             # Icons and images
│   └── utils/
│       └── logger.py         # Logging module
├── tests/                    # Unit tests (55+ tests)
│   ├── test_config.py        # ConfigManager tests
│   ├── test_dcc.py           # DCC implementation tests
│   ├── test_dcc_manager.py   # DCCManager tests
│   └── test_logger.py        # Logger tests
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
