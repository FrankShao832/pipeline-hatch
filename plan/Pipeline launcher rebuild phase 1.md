# Pipeline Launcher Rebuild Phase 1

**Date:** 2026-05-16
**Status:** Completed

---

## Overview

This document summarizes the work completed during Phase 1 of the Pipeline Launcher rebuild. The primary goal was to upgrade from PySide2 to PySide6 and implement a configuration-driven architecture for launching DCC (Digital Content Creation) applications.

---

## Key Achievements

### 1. PySide2 → PySide6 Migration

**Changes:**
- Updated all imports from `PySide2` to `PySide6`
- Replaced deprecated `exec_()` with `exec()`
- Updated enum access patterns (e.g., `Qt.AlignLeft` → `Qt.AlignmentFlag.AlignLeft`)
- Fixed `QMessageBox.Ok` → `QMessageBox.StandardButton.Ok`

**Files Modified:**
- `launcher/main.py`
- `launcher/ui/main_window.py`
- `launcher/ui/settings_window.py`

### 2. Configuration-Driven Architecture

**New Files Created:**

| File | Purpose |
|------|---------|
| `config/dcc.yaml` | DCC software configuration (paths, app names, flags) |
| `config/projects.yaml` | Project list and default paths |
| `launcher/core/config_manager.py` | YAML configuration loader (singleton) |
| `launcher/core/dcc_manager.py` | DCC factory and manager (singleton) |
| `launcher/dcc/base_dcc.py` | Abstract DCC base class |
| `launcher/dcc/dcc_maya.py` | Maya-specific implementation |
| `launcher/dcc/dcc_houdini.py` | Houdini-specific implementation |
| `launcher/dcc/dcc_nuke.py` | Nuke-specific implementation |

**Configuration Structure:**

```yaml
# config/dcc.yaml
dcc:
  maya:
    name: "Maya"
    role: "maya"
    app_name: "Maya2025.app"
    executable: "/Applications/Autodesk/maya2025/..."
    env_file: "/Users/frank/Library/.../Maya.env"
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

### 3. DCC Launch Implementation

**Architecture:**

```
MainWindow.launch_dcc()
       │
       ▼
┌─────────────────────────────────────────┐
│            DCCManager                   │
│  - Singleton pattern                    │
│  - get_dcc(role) -> BaseDCC              │
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│           BaseDCC (Abstract)            │
│  - build_command()                      │
│  - prepare_environment()                │
│  - parse_env_file()                    │
└─────────────────────────────────────────┘
       │
       ▼
   MayaDCC / HoudiniDCC / NukeDCC
```

**Environment Variable Handling:**

All pipeline environment variables are now loaded from `config/dcc.yaml`:

```python
# config/dcc.yaml defines:
pipeline:
  env_vars:
    - ROLE
    - PROJECT_ROOT
    - PUBLISH_ROOT
    - SHOW
    - SEQ
    - SHOT

# Code uses:
for key in self.get_pipeline_env_keys():
    if key in kwargs:
        env[key] = str(kwargs[key])
```

### 4. macOS App Launch Fix

**Problem:** Direct execution of DCC executables blocked by macOS Gatekeeper.

**Solution:** Use `open -a` command for GUI app launching.

```python
# Before (blocked)
cmd = ["/Applications/Nuke.../Nuke16.0v3", "--nukex"]

# After (works)
cmd = ["open", "-a", "Nuke16.0v3.app", "--args", "--nukex"]
```

**App Names (from config):**
- Maya: `Maya2025.app`
- Houdini: `Houdini FX 20.5.613.app`
- Nuke: `Nuke16.0v3.app`

### 5. Code Cleanup

**Deleted Empty Files:**
- `core/project_manager.py` (empty)
- `core/launch_tool.py` (empty)
- `utils/path_utils.py` (empty)
- `utils/validators.py` (empty)
- `utils/logging.py` (empty)
- `ui/widgets/project_tree.py` (empty)
- `ui/widgets/file_tree.py` (empty)
- `ui/widgets/` (empty directory)

**Refactored Files:**
- `launcher/ui/main_window.py` - Removed hardcoded DCC logic, now uses `dcc_manager`
- `launcher/ui/settings_window.py` - Improved structure and docstrings
- `launcher/main.py` - Cleaned up imports and added shebang

---

## Architecture Summary

```
launcher/
├── main.py                  # Entry point
├── core/
│   ├── __init__.py
│   ├── config_manager.py   # YAML config loader (singleton)
│   └── dcc_manager.py      # DCC factory (singleton)
├── dcc/
│   ├── __init__.py
│   ├── base_dcc.py         # Abstract base class
│   ├── dcc_maya.py         # Maya implementation
│   ├── dcc_houdini.py      # Houdini implementation
│   └── dcc_nuke.py         # Nuke implementation
├── ui/
│   ├── __init__.py
│   ├── main_window.py      # Main UI
│   ├── settings_window.py  # Settings dialog
│   └── imgs/
│       └── Settings.png
└── utils/
    └── __init__.py

config/
├── dcc.yaml                # DCC configuration
└── projects.yaml           # Project list
```

---

## Design Patterns Used

| Pattern | Implementation | Purpose |
|---------|---------------|---------|
| **Singleton** | `ConfigManager`, `DCCManager` | Global access, single instance |
| **Factory** | `DCCManager.get_dcc()` | Create DCC instances by role |
| **Template Method** | `BaseDCC.build_command()` | Abstract interface for DCCs |
| **Configuration-Driven** | All DCC settings in YAML | Easy modification, no code changes |

---

## Benefits

1. **No Hardcoded Paths** - All paths configurable via YAML
2. **Extensible** - Add new DCC by creating class + config entry
3. **Maintainable** - UI logic separated from DCC launch logic
4. **Testable** - DCC classes can be unit tested independently
5. **macOS Compatible** - Works with Gatekeeper via `open -a`

---

## Phase 1 Commit Summary

```
[dev_branch] Switch to yaml config for launching dcc logic

21 files changed, 728 insertions(+), 170 deletions(-)

+ config/dcc.yaml
+ config/projects.yaml
+ launcher/core/config_manager.py
+ launcher/core/dcc_manager.py
+ launcher/dcc/base_dcc.py
+ launcher/dcc/dcc_maya.py
+ launcher/dcc/dcc_houdini.py
+ launcher/dcc/dcc_nuke.py
- Removed empty placeholder files
```

---

## Future Work (Phase 2+)

### Potential Improvements

1. **Settings Persistence** - Save user preferences to JSON/SQLite
2. **DCC Health Check** - Verify executables exist before launch
3. **Error Handling** - Better error messages and logging
4. **Project Filtering** - Filter projects by enabled status
5. **Recent Files** - Track recently opened files
6. **Custom DCC Paths** - Allow per-project DCC overrides
7. **Environment Editor** - GUI for editing environment variables

### Scalability Considerations

| Scenario | Current Approach | Future Option |
|----------|-----------------|---------------|
| Single user | YAML file | ✓ Works |
| Small team (2-5) | Shared YAML in repo | Dropbox/Git sync |
| Large team (10+) | SQLite database | PostgreSQL + central server |

---

## Notes

- DCC app names (`Maya2025.app`, `Houdini FX 20.5.613.app`, `Nuke16.0v3.app`) are macOS-specific
- Configuration loading uses singleton pattern to avoid repeated file reads
- Pipeline environment variables are defined once in config and used by all DCCs
- `open -a` command bypasses Gatekeeper restrictions on macOS