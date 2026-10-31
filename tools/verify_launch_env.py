#!/usr/bin/env python3
"""Prove the injection inside a real DCC — not in a preview, in the process.

The launcher's promise is "the DCC opens with this show's environment". A
settings panel can only *claim* that; this script checks it where it counts:

1. build the context exactly the way ``MainWindow._launch_dcc`` does
   (``build_env_context`` → ``merge_env_store`` → ``DCC.prepare_environment``);
2. run a probe script inside the DCC's own interpreter (mayapy / hython / Nuke
   in terminal mode) with that env and that cwd;
3. print what the DCC process can actually see.

Usage:

    ./env/bin/python tools/verify_launch_env.py --dcc maya   --project CyberPunk -d fx
    ./env/bin/python tools/verify_launch_env.py --dcc houdini --project CyberPunk -d fx
    ./env/bin/python tools/verify_launch_env.py --dcc nuke   --project RainPool -d comp
    ./env/bin/python tools/verify_launch_env.py --dcc maya --launch   # also open the GUI

``--launch`` additionally starts the real GUI application with the same env —
that is the button the video presses; the probe is the receipt.

Nothing here is imported by the application.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROBE_KEYS = ("SHOW", "SEQ", "SHOT", "DEPARTMENT", "DCC", "OCIO", "FPS",
              "PROJECT_ROOT", "PUBLISH_ROOT", "ASSET_ROOT", "CACHE_ROOT",
              "RENDER_ROOT", "JOB", "PIPELINE_PROJECT", "PIPELINE_DEPARTMENT")

PROBE = '''
import json, os, sys
keys = %r
report = {k: os.environ.get(k) for k in keys}
report["cwd"] = os.getcwd()
report["python"] = sys.version.split()[0]
report["executable"] = sys.executable
print("PROBE" + json.dumps(report))
'''


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dcc", required=True, choices=("maya", "houdini", "nuke"))
    parser.add_argument("--project", default="CyberPunk")
    parser.add_argument("-d", "--department", default="fx")
    parser.add_argument("--seq", default="")
    parser.add_argument("--shot", default="")
    parser.add_argument("--store", default=None,
                        help="override store (default: <config dir>/env.yaml)")
    parser.add_argument("--launch", action="store_true",
                        help="also start the GUI application with the same env")
    return parser.parse_args(argv)


def interpreter(dcc_name: str, dcc) -> list[str]:
    """The command prefix that runs *python inside* the given DCC."""
    executable = dcc.executable or ""
    if dcc_name == "maya":
        candidate = Path(executable).with_name("mayapy")
        return [str(candidate)] if candidate.exists() else []
    if dcc_name == "houdini":
        # Two layouts exist in the wild: Frameworks inside the .app bundle, and
        # a sibling Frameworks next to it (this machine's 20.5/21.0 installs).
        # Walk up from the executable and take the FIRST hit, so the hython we
        # probe belongs to the same version the launcher would open.
        path = Path(executable)
        for depth in range(0, 5):
            try:
                base = path.parents[depth]
            except IndexError:
                break
            for sub in ("Frameworks", "Contents/Frameworks"):
                hits = sorted(glob.glob(str(base / sub / "Houdini.framework"
                                            / "Versions" / "*" / "Resources"
                                            / "bin" / "hython")))
                if hits:
                    return [hits[-1]]
        return []
    if dcc_name == "nuke":
        return [executable, "-t"] if executable else []
    return []


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    from launcher.core.launch_env import (build_env_context, merge_env_store,
                                          resolve_env)
    from launcher.core.dcc_manager import dcc_manager
    from launcher.ui.real_source import RealSettingsDataSource

    source = RealSettingsDataSource(env_store_path=args.store)
    row = next((r for r in source.projects() if r.name == args.project), None)
    if row is None:
        print(f"unknown project: {args.project}", file=sys.stderr)
        return 2

    # seq/shot: use the disk, the same way the panel's preview samples them.
    seqs = sorted(p.name for p in Path(row.root, row.name).glob("*") if p.is_dir())
    seq = args.seq or (seqs[0] if seqs else "")
    shots = sorted(p.name for p in Path(row.root, row.name, seq).glob("*")
                   if p.is_dir()) if seq else []
    shot = args.shot or (shots[0] if shots else "")

    ctx = build_env_context(
        root_path=row.root, publish_root_path=row.publish_root,
        project=row.name, sequence=seq, shot=shot,
        department=args.department, dcc=args.dcc,
    )
    entries, values = resolve_env(ctx, source.env_store_path)
    ctx = values
    if args.dcc == "houdini" and shot:
        ctx["JOB"] = ""                      # the GUI sets it from the hip path

    dcc = dcc_manager.get_dcc(args.dcc)
    if dcc is None:
        print(f"DCC not configured: {args.dcc}", file=sys.stderr)
        return 2
    env = os.environ.copy()
    env.update(dcc.prepare_environment(**ctx))
    cwd = dcc.launch_cwd(str(Path(row.root, row.name, seq, shot)))

    overrides = [e for e in entries if e.source != "derived"]
    print(f"context      {row.name} · {args.department} · {args.dcc} · {seq}/{shot}")
    print(f"store        {source.env_store_path}"
          + ("" if source.env_store_path.exists() else "  (missing — all derived)"))
    print(f"overrides    {len(overrides)}"
          + (": " + ", ".join(f"{e.name}[{e.source}]" for e in overrides)
             if overrides else ""))
    print(f"cwd          {cwd or '(inherit)'}")
    print()

    prefix = interpreter(args.dcc, dcc)
    if not prefix:
        print(f"! no interpreter found for {args.dcc} "
              f"(looked next to {dcc.executable})", file=sys.stderr)
        return 3

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(PROBE % (list(PROBE_KEYS),))
        probe_path = handle.name
    if args.dcc == "nuke":
        command = prefix + [probe_path]
    else:
        command = prefix + [probe_path]

    print(f"probe        {' '.join(command)}")
    result = subprocess.run(command, env=env, cwd=cwd, capture_output=True,
                            text=True, timeout=180)
    line = next((l for l in result.stdout.splitlines() if l.startswith("PROBE")), "")
    if not line:
        print(result.stdout[-2000:], result.stderr[-2000:], sep="\n", file=sys.stderr)
        print("! the DCC interpreter did not answer", file=sys.stderr)
        return 4
    report = json.loads(line[len("PROBE"):])
    print(f"\nwhat {args.dcc} sees ({report['python']}):")
    for key in PROBE_KEYS:
        value = report.get(key)
        if value is None:
            continue
        print(f"  {key:22s} {value}")
    print(f"  {'cwd':22s} {report['cwd']}")

    if args.launch:
        gui = [dcc.executable] + (["--nukex"] if args.dcc == "nuke" else [])
        print(f"\nlaunching         {' '.join(gui)}")
        subprocess.Popen(gui, env=env, cwd=cwd)
    os.unlink(probe_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
