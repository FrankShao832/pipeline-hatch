#!/usr/bin/env python3
"""Print the environment a launch would inject — the terminal side of the panel.

The settings panel answers "what does this show's launch look like"; this script
answers it in a form a terminal, a CI job or a farm wrapper can consume. Both
read the same two functions (`build_env_context` + the store), so they cannot
disagree about a number.

Usage (repo root is derived from this file; nothing is machine-hard-coded):

    ./env/bin/python tools/print_env.py                       # first usable show
    ./env/bin/python tools/print_env.py --project DragonLand -d fx --dcc houdini
    ./env/bin/python tools/print_env.py --export              # NAME=value only
    ./env/bin/python tools/print_env.py --store /tmp/env.yaml # a specific store

`--export` prints bare `NAME=value` lines, so `eval "$(... --export)"` puts the
same values in the current shell — which is exactly how the video shows the
panel and the terminal agreeing.

Nothing here is imported by the application; deleting this file cannot break it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.ui.real_source import RealSettingsDataSource  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", default="", help="show (default: first usable)")
    parser.add_argument("--seq", default="", help="sequence (default: first on disk)")
    parser.add_argument("--shot", default="", help="shot (default: first on disk)")
    parser.add_argument("-d", "--department", default="", help="department key")
    parser.add_argument("--dcc", default="", help="dcc key (default: first configured)")
    parser.add_argument("--store", default=None,
                        help="override store (default: <config dir>/env.yaml)")
    parser.add_argument("--export", action="store_true",
                        help="print NAME=value lines only")
    parser.add_argument("--wide", action="store_true",
                        help="do not truncate values")
    return parser.parse_args(argv)


def _default_project(source: RealSettingsDataSource) -> str:
    for row in source.projects():
        if row.enabled and row.scaffold_state == "complete":
            return row.name
    rows = list(source.projects())
    return rows[0].name if rows else ""


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    source = RealSettingsDataSource(env_store_path=args.store)

    project = args.project or _default_project(source)
    if not project:
        print("no projects found", file=sys.stderr)
        return 2
    dcc = args.dcc or (source.dcc_roles() or ("",))[0]

    rows = source.resolved(project, dcc, args.department)
    if not rows:
        print(f"could not resolve {project} / {dcc}", file=sys.stderr)
        return 2
    values = {row.name: row.value for row in rows}

    if args.export:
        for name, value in values.items():
            print(f"{name}={value}")
        return 0

    again = values.get("SEQ", "") and values.get("SHOT", "")
    scope = " · ".join(part for part in (project, args.department or "no department",
                                         dcc, f"{values.get('SEQ')}/{values.get('SHOT')}"
                                         if again else "") if part)
    print(f"resolved environment — {scope}")
    print(f"store: {source.env_store_path}"
          + (" (missing: everything below is derived)"
             if not source.env_store_path.exists() else ""))
    print()
    overridden = 0
    width = 120 if args.wide else 46
    for row in rows:
        badge = f"[{row.source}" + (f":{row.scope_key}]" if row.scope_key else "]")
        beaten = (f"  ← beat {len(row.shadowed)}" if row.shadowed else "")
        if row.source != "derived":
            overridden += 1
        value = row.value if len(row.value) <= width else row.value[:width - 1] + "…"
        print(f"{row.name:28s} {value:46s} {badge}{beaten}")

    print()
    print(f"{len(rows)} variable(s) · {overridden} overridden · "
          f"{sum(1 for r in rows if r.shadowed)} shadowing a lower layer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
