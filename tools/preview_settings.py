#!/usr/bin/env python3
"""Dev preview harness — open the Settings UI without the launcher shell.

Built for the UI-first phase (plan v1.1): every page card (T07–T15) can be
inspected in one second, against fixture data, without touching DB or config.

Usage (from the project root, or anywhere — the repo root is derived from this
file, so no machine path is hard-coded):

    ./env/bin/python tools/preview_settings.py
    ./env/bin/python tools/preview_settings.py --page env
    ./env/bin/python tools/preview_settings.py --source empty
    ./env/bin/python tools/preview_settings.py --source errors
    ./env/bin/python tools/preview_settings.py --screenshot /tmp/shell.png   # headless render then exit

Nothing here is imported by the application; deleting this file cannot break it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from launcher.ui.fakes import FakeSettingsDataSource  # noqa: E402
from launcher.ui.settings_window import NAV_ITEMS, SettingsWindow  # noqa: E402

PAGES = tuple(item.lower() for item in NAV_ITEMS)   # projects / environment / preflight


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview the Settings UI.")
    parser.add_argument("--source", default="rich", choices=FakeSettingsDataSource.MODES,
                        help="fixture mode: rich | empty | errors (default: rich)")
    parser.add_argument("--page", default="projects",
                        choices=[p for p in PAGES] + ["env"],
                        help="which page to open first (default: projects)")
    parser.add_argument("--screenshot", metavar="PATH",
                        help="render offscreen to PATH and exit (no window)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Pipeline Hatch — Settings Preview")

    window = SettingsWindow(data_source=FakeSettingsDataSource(args.source))
    page = "environment" if args.page == "env" else args.page
    window.nav.setCurrentRow(PAGES.index(page))

    if args.screenshot:
        window.show()
        app.processEvents()
        window.grab().save(args.screenshot)
        print(f"saved {args.screenshot}  ({window.width()}x{window.height()}, "
              f"page={page}, source={args.source})")
        return 0

    window.show()
    window.raise_()
    window.activateWindow()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
