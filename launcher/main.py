#!/usr/bin/env python3
"""Pipeline Launcher - Main entry point."""

import getpass
import sys
from types import SimpleNamespace
from typing import Optional

from launcher.ui.main_window import MainWindow
from launcher.utils.logger import log_startup, log_shutdown
from launcher.database.database import DatabaseManager
from launcher.database.repository import UserRepo


def _make_offline_user():
    """Create a minimal user-like object from the OS username.

    Used when the database is unavailable so the UI can still
    display the current user's name instead of just 'Offline Mode'.
    """
    username = getpass.getuser()
    return SimpleNamespace(
        username=username,
        display_name=username.capitalize(),
        role="offline",
    )


def _init_database() -> tuple[bool, Optional[object]]:
    """Initialize database connection and detect/create the current user.

    Returns:
        Tuple of (db_connected, user_object_or_None).
    """
    db = DatabaseManager()
    connected = db.connect()

    if not connected:
        from launcher.utils.logger import logger
        logger.warning("Database unavailable — running in offline (YAML) mode")
        return False, _make_offline_user()

    # Create tables if they don't exist (idempotent)
    db.init_db()

    # Detect or create the current system user
    username = getpass.getuser()
    try:
        with db.get_session() as session:
            repo = UserRepo(session)
            user = repo.get_or_create(
                username=username,
                display_name=username.capitalize(),
                role="admin",  # Default role; can be changed later
            )
            repo.update_last_login(username)
            from launcher.utils.logger import logger
            logger.info(f"User detected: {user.username} [{user.role}]")
            return True, user
    except Exception as exc:
        from launcher.utils.logger import logger
        logger.warning(f"User detection failed: {exc} — running in offline mode")
        return True, None


def main():
    """Initialize and run the application."""
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from pathlib import Path

    # Initialize logging
    log_startup()

    # Initialize database (graceful fallback on failure)
    _db_connected, user = _init_database()

    try:
        app = QApplication(sys.argv)
        app.setApplicationName("Y Pipeline")

        # Set application window icon from bundled .icns
        icon_path = Path(__file__).parent / "ui" / "imgs" / "pipeline_hatch.icns"
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))

        window = MainWindow(user=user)
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
