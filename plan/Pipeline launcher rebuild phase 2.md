# Pipeline Launcher Rebuild Phase 2

**Date:** 2026-05-16
**Status:** In Progress

---

## Overview

Phase 2 focuses on **code quality and testing**. The primary goals are:
1. Writing comprehensive unit tests for all core modules
2. Establishing testing patterns and best practices
3. Ensuring code reliability for future development

---

## Test Architecture

### Test Structure

```
tests/
├── __init__.py
├── test_config.py           # ConfigManager tests
├── test_dcc_manager.py      # DCCManager tests
└── test_dcc.py             # DCC implementation tests
```

### Testing Framework

- **Framework:** pytest
- **Python:** 3.11
- **Coverage:** Unit tests for all non-UI components

---

## Test Design Logic

### 1. Singleton Reset Pattern

**Problem:** Singleton classes maintain state between tests, causing interference.

**Solution:** Use `autouse=True` fixtures to reset singleton state:

```python
@pytest.fixture(autouse=True)
def setup(self):
    """Reset singleton instances before each test."""
    ConfigManager._instance = None
    ConfigManager._config_cache = {}
    DCCManager._instance = None
    DCCManager._dcc_cache = {}
    yield  # Test runs here, cleanup after
```

**Why:**
- Each test starts with a clean state
- Tests are independent and can run in any order
- No false positives from cached data

### 2. Fixture-Based Configuration

**Problem:** Repeating config dictionaries in every test.

**Solution:** Use pytest fixtures:

```python
@pytest.fixture
def maya_config(self):
    """Sample Maya configuration."""
    return {
        "name": "Maya",
        "role": "maya",
        "executable": "/Applications/...",
        ...
    }

def test_properties(self, maya_config):
    maya = MayaDCC(maya_config)
    assert maya.name == "Maya"
```

**Benefits:**
- Single source of truth for test data
- Easy to modify for different test scenarios
- Clear separation of test data vs test logic

### 3. Platform-Aware Testing

**Problem:** Tests may behave differently on macOS vs Linux vs Windows.

**Solution:** Use `platform.system()` for conditional assertions:

```python
def test_build_command(self, config):
    maya = MayaDCC(config)
    cmd = maya.build_command(project_path="/test")

    if platform.system() == "Darwin":
        assert "open" in cmd
        assert "-a" in cmd
    else:
        assert cmd[0] == config["executable"]
```

**Why:**
- DCC launch behavior differs by platform
- `open -a` works on macOS, direct execution on Linux/Windows
- Tests remain valid across environments

---

## Test Inventory

### ConfigManager Tests (`test_config.py`)

| Test | Purpose | Technique |
|------|---------|-----------|
| `test_singleton_pattern` | Verify singleton behavior | Check object identity (`is`) |
| `test_load_dcc_config` | Verify DCC YAML loads correctly | Assert keys exist |
| `test_load_projects_config` | Verify projects YAML loads | Assert keys exist |
| `test_get_project_list` | Verify project list parsing | Assert list structure and content |
| `test_get_dcc_by_role` | Verify role-based lookup | Assert config matches role |
| `test_get_dcc_by_invalid_role` | Verify graceful handling of invalid role | Assert returns `None` |
| `test_config_caching` | Verify caching mechanism | Check object identity (`is`) |
| `test_reload_clears_cache` | Verify reload clears cache | Load, reload, load again, compare |
| `test_dcc_config_structure` | Verify all DCCs have required fields | Loop and assert each field |
| `test_pipeline_env_vars` | Verify env vars loaded from config | Assert key presence |

### DCCManager Tests (`test_dcc_manager.py`)

| Test | Purpose | Technique |
|------|---------|-----------|
| `test_singleton_pattern` | Verify singleton behavior | Check object identity |
| `test_get_available_dccs` | Verify DCC list completeness | Assert all roles present |
| `test_get_dcc_maya/houdini/nuke` | Verify DCC instantiation | Assert properties correct |
| `test_get_dcc_invalid_role` | Verify error handling | Assert returns `None` |
| `test_dcc_caching` | Verify DCC instances cached | Check object identity |
| `test_dcc_instance_reload` | Verify reload creates new instances | Check object inequality |
| `test_list_all_configured_dccs` | Verify all DCCs listed | Assert dict contains all |
| `test_case_insensitive_role` | Verify case-insensitive lookup | Test lower/upper/mixed case |

### DCC Implementation Tests (`test_dcc.py`)

**MayaDCC:**

| Test | Purpose | Technique |
|------|---------|-----------|
| `test_properties` | Verify config mapping | Assert property values |
| `test_build_command_with_file` | Verify file launch command | Assert command structure |
| `test_build_command_with_project` | Verify project launch command | Assert command structure |
| `test_build_command_empty` | Verify minimal command | Assert non-empty |
| `test_prepare_environment` | Verify env var merging | Assert keys and values |

**HoudiniDCC:**

| Test | Purpose | Technique |
|------|---------|-----------|
| `test_properties` | Verify config mapping | Assert property values |
| `test_build_command_with_file` | Verify file launch | Assert command structure |
| `test_prepare_environment` | Verify JOB var set | Assert JOB key present |

**NukeDCC:**

| Test | Purpose | Technique |
|------|---------|-----------|
| `test_properties` | Verify config mapping | Assert property values |
| `test_build_command_nukex_mode` | Verify NukeX flag | Assert `--nukex` present |
| `test_build_command_with_file` | Verify file launch | Assert file path present |
| `test_prepare_environment` | Verify env var merging | Assert keys present |

**BaseDCC:**

| Test | Purpose | Technique |
|------|---------|-----------|
| `test_parse_env_file_nonexistent` | Verify graceful handling | Assert empty dict |
| `test_executable_exists` | Verify method callable | Assert callable |
| `test_get_pipeline_env_keys` | Verify env keys loaded | Assert list not empty |

---

## Writing Techniques

### 1. Arrange-Act-Assert (AAA) Pattern

```python
def test_example(self):
    # Arrange - Set up test data
    config = {"name": "Test", "role": "test"}

    # Act - Perform the action
    result = some_function(config)

    # Assert - Verify the result
    assert result == expected_value
```

### 2. Descriptive Test Names

**Pattern:** `test_<unit>_<scenario>_<expected_behavior>`

```python
# Good
test_get_dcc_by_invalid_role_returns_none
test_build_command_with_file_includes_file_path

# Avoid
test_dcc_1
test_command_2
```

### 3. Single Responsibility

Each test should verify one behavior:

```python
# Good - One assertion per concern
def test_build_command_with_file(self):
    cmd = dcc.build_command(file_path="/test.ma")
    assert "/test.ma" in cmd

# Bad - Multiple concerns
def test_build_command_complex(self):
    cmd = dcc.build_command(file_path="/test.ma")
    # Checking multiple things
    assert "open" in cmd
    assert "-a" in cmd
    assert "Maya" in cmd
    assert "/test.ma" in cmd
    assert "--args" in cmd
```

### 4. Test Isolation

Tests should not depend on each other:

```python
# Bad - Dependency on previous test
def test_second(self):
    value = self.shared_state  # Fragile!

# Good - Independent setup
def test_second(self):
    config = self.fixture["config"]
    result = function(config)
    assert result == expected
```

### 5. Descriptive Fixtures

```python
@pytest.fixture
def valid_maya_config(self):
    """Return a valid Maya configuration for testing."""
    return {
        "name": "Maya",
        "role": "maya",
        "executable": "/Applications/.../Maya",
        "app_name": "Maya2025.app"
    }

@pytest.fixture
def invalid_config(self):
    """Return an invalid configuration for error testing."""
    return {
        "name": "",
        "role": "invalid"
    }
```

---

## Test Execution

### Running All Tests

```bash
pytest tests/ -v
```

### Running Specific Test File

```bash
pytest tests/test_config.py -v
```

### Running with Coverage

```bash
pytest tests/ --cov=launcher --cov-report=term-missing
```

---

## Current Test Results

```
============================= test session starts ==============================
platform darwin -- Python 3.11.13, pytest-9.0.3

tests/test_config.py        10 passed  ✅
tests/test_dcc.py           13 passed  ✅
tests/test_dcc_manager.py   12 passed  ✅

============================== 35 passed in 0.10s ==============================
```

---

## Future Testing Needs

### Phase 3+ Considerations

| Component | Test Type | Priority |
|-----------|-----------|----------|
| **UI Components** | Integration tests | Medium |
| **MainWindow** | Widget interaction tests | Medium |
| **SettingsPanel** | Dialog behavior tests | Medium |
| **File System Operations** | Mock tests | Low |
| **Environment Variable Propagation** | Integration tests | Medium |

### Testing Best Practices for Future

1. **Mock external dependencies** - Use `unittest.mock` for file system, subprocess
2. **UI testing** - Use `pytest-qt` for PySide6 widget testing
3. **Integration tests** - Test actual DCC launch with mock executables
4. **CI/CD** - Run tests on every commit with GitHub Actions

---

## Notes

- Tests are platform-agnostic where possible
- Singleton reset is crucial for test isolation
- Fixture reuse reduces code duplication
- Descriptive names improve test maintainability