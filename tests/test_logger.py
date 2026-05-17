"""Tests for logger module."""

import pytest
from pathlib import Path
import sys
import logging

# Add launcher to path
sys.path.insert(0, str(Path(__file__).parent.parent / "launcher"))

from launcher.utils.logger import (
    Logger, logger, get_logger, log_startup, log_shutdown
)


class TestLogger:
    """Test suite for Logger."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton instance before each test."""
        Logger._instance = None
        Logger._initialized = False
        yield

    def test_singleton_pattern(self):
        """Test that Logger is a singleton."""
        log1 = Logger()
        log2 = Logger()
        assert log1 is log2

    def test_get_logger_returns_singleton(self):
        """Test that get_logger returns singleton."""
        lg1 = get_logger()
        lg2 = get_logger()
        assert lg1 is lg2

    def test_logger_has_levels(self):
        """Test logger has expected methods."""
        log = get_logger()
        assert hasattr(log, 'debug')
        assert hasattr(log, 'info')
        assert hasattr(log, 'warning')
        assert hasattr(log, 'error')
        assert hasattr(log, 'critical')

    def test_log_methods_exist(self):
        """Test that log directory creation doesn't raise errors."""
        log = get_logger()
        # Just verify the logger has internal logger with handlers
        assert hasattr(log, '_logger')
        assert len(log._logger.handlers) >= 1

    def test_methods_accept_strings(self):
        """Test that log methods accept string arguments."""
        log = get_logger()

        # Should not raise any exceptions
        log.debug("Debug message")
        log.info("Info message")
        log.warning("Warning message")
        log.error("Error message")
        log.critical("Critical message")

    def test_log_startup(self):
        """Test startup logging function."""
        # Should not raise
        log_startup()

    def test_log_shutdown(self):
        """Test shutdown logging function."""
        # Should not raise
        log_shutdown()

    def test_error_with_exception_info(self):
        """Test error logging with exception info."""
        log = get_logger()

        try:
            raise ValueError("Test error")
        except ValueError:
            # Should not raise, even with exc_info
            log.error("Test error", exc_info=True)


class TestLogFunctions:
    """Test suite for convenience log functions."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton instance before each test."""
        Logger._instance = None
        Logger._initialized = False
        yield

    def test_log_dcc_launch_success(self):
        """Test logging successful DCC launch."""
        from launcher.utils.logger import log_dcc_launch

        # Should not raise
        log_dcc_launch(
            role="maya",
            command=["open", "-a", "Maya2025.app"],
            success=True
        )

    def test_log_dcc_launch_failure(self):
        """Test logging failed DCC launch."""
        from launcher.utils.logger import log_dcc_launch

        # Should not raise
        log_dcc_launch(
            role="maya",
            command=["open", "-a", "Maya2025.app"],
            success=False,
            error="Application not found"
        )

    def test_log_config_loaded(self):
        """Test logging config loaded."""
        from launcher.utils.logger import log_config_loaded

        # Should not raise
        log_config_loaded("dcc.yaml", 3)

    def test_log_error(self):
        """Test logging error with context."""
        from launcher.utils.logger import log_error

        try:
            raise RuntimeError("Test exception")
        except RuntimeError as e:
            # Should not raise
            log_error("test_context", e)