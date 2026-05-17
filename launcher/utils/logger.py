"""Logging module for pipeline launcher.

Provides centralized logging with file rotation and multiple output handlers.
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


# Log levels
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR


class Logger:
    """Central logging manager for the application."""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if Logger._initialized:
            return

        self._setup_logging()
        Logger._initialized = True

    def _setup_logging(self):
        """Setup logging configuration."""
        # Create logs directory
        log_dir = Path(__file__).parent.parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)

        # Create logger
        self._logger = logging.getLogger("pipeline_launcher")
        self._logger.setLevel(logging.DEBUG)

        # Prevent duplicate handlers
        if self._logger.handlers:
            return

        # Console handler (INFO level)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)

        # File handler (DEBUG level, rotated)
        file_handler = RotatingFileHandler(
            log_dir / "launcher.log",
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)

        # Add handlers
        self._logger.addHandler(console_handler)
        self._logger.addHandler(file_handler)

    def debug(self, message: str):
        """Log debug message."""
        self._logger.debug(message)

    def info(self, message: str):
        """Log info message."""
        self._logger.info(message)

    def warning(self, message: str):
        """Log warning message."""
        self._logger.warning(message)

    def error(self, message: str, exc_info: bool = False):
        """Log error message.

        Args:
            message: Error message.
            exc_info: If True, include exception stack trace.
        """
        self._logger.error(message, exc_info=exc_info)

    def critical(self, message: str, exc_info: bool = False):
        """Log critical message."""
        self._logger.critical(message, exc_info=exc_info)


# Singleton instance
logger = Logger()


# Convenience functions
def get_logger() -> Logger:
    """Get the logger instance."""
    return logger


def log_startup():
    """Log application startup."""
    from launcher import __version__
    logger.info(f"Pipeline Launcher v{__version__} started")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Platform: {sys.platform}")


def log_shutdown():
    """Log application shutdown."""
    logger.info("Pipeline Launcher shut down")


def log_dcc_launch(role: str, command: list, success: bool, error: str = None):
    """Log DCC launch attempt.

    Args:
        role: DCC role (maya, houdini, nuke).
        command: Command that was executed.
        success: Whether launch succeeded.
        error: Error message if failed.
    """
    if success:
        logger.info(f"DCC launched: {role}")
        logger.debug(f"Command: {' '.join(command)}")
    else:
        logger.error(f"DCC launch failed: {role} - {error}")
        logger.debug(f"Command: {' '.join(command)}")


def log_config_loaded(config_name: str, item_count: int = None):
    """Log configuration loaded.

    Args:
        config_name: Name of the configuration file.
        item_count: Number of items loaded (optional).
    """
    if item_count is not None:
        logger.info(f"Config loaded: {config_name} ({item_count} items)")
    else:
        logger.info(f"Config loaded: {config_name}")


def log_error(context: str, exception: Exception):
    """Log error with context.

    Args:
        context: Where the error occurred.
        exception: The exception that was raised.
    """
    logger.error(f"Error in {context}: {str(exception)}", exc_info=True)