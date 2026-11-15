#!/usr/bin/env python3
"""Dev preview harness — open the Settings UI without the launcher shell.

Built for the UI-first phase (plan v1.1): the three columns can be inspected in
one second, against fixture data, without touching DB or config.

Usage (from the project root, or anywhere — the repo root is derived from this
file, so no machine path is hard-coded):

    ./env/bin/python tools/preview_settings.py
    ./env/bin/python tools/preview_settings.py --project DragonLand
    ./env/bin/python tools/preview_settings.py --source empty
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
from launcher.ui.settings_window import SettingsWindow  # noqa: E402
from launcher.ui.viewmodels import SettingsContext  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview the Settings UI.")
    parser.add_argument("--source", default="rich", choices=FakeSettingsDataSource.MODES,
                        help="fixture mode: rich | empty | errors (default: rich)")
    parser.add_argument("--project", default="",
                        help="project to select (default: the first usable one)")
    parser.add_argument("--department", default="",
                        help="department to select (default: unset)")
    parser.add_argument("--dcc", default="",
                        help="DCC to select (default: the first one)")
    parser.add_argument("--dialog", action="store_true",
                        help="render the New Project dialog instead of the window")
    parser.add_argument("--name", default="NewShow",
                        help="project name to type into the New Project dialog")
    parser.add_argument("--screenshot", metavar="PATH",
                        help="render offscreen to PATH and exit (no window)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Pipeline Hatch — Settings Preview")

    data_source = FakeSettingsDataSource(args.source)
    if args.dialog:
        from launcher.ui.widgets.new_project_dialog import NewProjectDialog

        window = NewProjectDialog(data_source, root="/Volumes/Development/projects/"
                                  "y_pipeline_projects",
                                  publish_root="/Volumes/Development/projects/"
                                  "y_pipeline_publish")
        window.name_edit.setText(args.name)
    else:
        window = SettingsWindow(
            data_source=data_source,
            context=SettingsContext(project=args.project, department=args.department,
                                    dcc=args.dcc, seq="seq001", shot="sh010"),
        )

    if args.screenshot:
        window.show()
        app.processEvents()
        window.grab().save(args.screenshot)
        context = getattr(window, "context", None)
        print(f"saved {args.screenshot}  ({window.width()}x{window.height()}, "
              f"project={getattr(context, 'project', args.name) or '-'}, department="
              f"{getattr(context, 'department', '-') or '-'}, dcc="
              f"{getattr(context, 'dcc', '-') or '-'}, source={args.source})")
        return 0

    window.show()
    window.raise_()
    window.activateWindow()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
