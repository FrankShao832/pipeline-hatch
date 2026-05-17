#!/usr/bin/env python3
"""Pipeline Launcher - Main entry point."""

import sys

from launcher.ui.main_window import MainWindow
from launcher.utils.logger import log_startup, log_shutdown


def main():
    """Initialize and run the application."""
    from PySide6.QtWidgets import QApplication

    # Initialize logging
    log_startup()

    try:
        app = QApplication(sys.argv)
        app.setApplicationName("Y Pipeline")

        window = MainWindow()
        window.show()

        return app.exec()
    except Exception as e:
        from launcher.utils.logger import logger
        logger.error(f"Application error: {e}", exc_info=True)
        raise
    finally:
        log_shutdown()


if __name__ == "__main__":
    sys.exit(main())
