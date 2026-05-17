#!/usr/bin/env python3
"""Pipeline Launcher - Main entry point."""

import sys

from launcher.ui.main_window import MainWindow


def main():
    """Initialize and run the application."""
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("Y Pipeline")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
