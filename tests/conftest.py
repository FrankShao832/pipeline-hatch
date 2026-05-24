"""Shared pytest fixtures for Pipeline Launcher tests."""

from pathlib import Path
import sys

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

# Add launcher to path (same pattern as existing test files)
sys.path.insert(0, str(Path(__file__).parent.parent / "launcher"))


@pytest.fixture(scope="session")
def qapp():
    """Provide a QApplication instance for widget tests.

    Uses singleton pattern: reuses existing application if already
    created (pytest-qt compatibility pattern).
    """
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def clean_settings():
    """Clear QSettings before and after a test to prevent cross-test pollution."""
    settings = QSettings("PipelineDevs", "PipelineLauncher")
    settings.clear()
    settings.sync()
    yield
    settings.clear()
    settings.sync()


@pytest.fixture(autouse=True)
def reset_config_singleton():
    """Reset ConfigManager singleton before each test.

    The ConfigManager uses a singleton pattern and caches config data,
    which can cause test pollution if not reset between tests.
    """
    from launcher.core.config_manager import ConfigManager

    ConfigManager._instance = None
    ConfigManager._config_cache = {}
    yield
    ConfigManager._instance = None
    ConfigManager._config_cache = {}
