"""Migrate the project work trees to the agreed vocabulary (2026-10-25).

Rule (see ``pipeline_hatch/docs/VOCABULARY.md``): a department is the data axis,
a DCC never is a data segment. Existing shots are app-named (``<shot>/nuke``);
this script renames them to the department shape:

* single-application shot, ``nuke`` only   ->  ``<shot>/comp``      (no nesting)
* multi-application shot                   ->  ``<shot>/<dept>/<dcc>``
  (``houdini`` -> ``fx/houdini``, ``nuke`` -> ``comp/nuke``,
   ``maya`` -> ``anim/maya``)

Every move is written to a TSV manifest first, so the whole migration can be
reverted by feeding the manifest back in reverse. Never deletes anything.

    python3 plan/migrate_disk_vocab.py --dry-run
    python3 plan/migrate_disk_vocab.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path("/Volumes/Development/projects/y_pipeline_projects")
MANIFEST = Path(__file__).with_name("disk_vocab_migration_20261025.tsv")

DCC_TOKENS = {"nuke", "maya", "houdini", "katana"}
DEPARTMENTS = {"model", "rig", "anim", "layout", "fx", "lighting", "comp"}

# A single-app tree gets the department directly, without a redundant dcc level.
SINGLE_DCC_TO_DEPT = {"nuke": "comp"}

# A multi-app shot nests the dcc inside the department.
MULTI_DCC_TO_DEPT = {
    "houdini": "fx",
    "nuke": "comp",
    "maya": "anim",
    "katana": "lighting",
}


def shot_dirs(root: Path) -> list[Path]:
    """Return every directory that holds app-named children (any depth).

    The trees are not uniformly deep (``Test/test_project/seq001/shot001`` sits
    one level lower than the seeded shows), so shots are found by shape — a
    folder is shot-like when it contains a ``nuke`` / ``maya`` / ``houdini`` /
    ``katana`` child — instead of by a fixed depth.
    """
    shots = []
    for dirpath, dirnames, _ in os.walk(root):
        if any(name in DCC_TOKENS for name in dirnames):
            shots.append(Path(dirpath))
    return sorted(shots)


def plan_moves(root: Path) -> list[tuple[str, Path, Path]]:
    """Build the (action, src, dst) plan for every shot under *root*."""
    plan: list[tuple[str, Path, Path]] = []
    for shot in shot_dirs(root):
        if shot.name in DEPARTMENTS:
            continue  # a dcc nested inside a department is the correct shape
        children = sorted(p for p in shot.iterdir() if p.is_dir())
        dcc_dirs = [p for p in children if p.name in DCC_TOKENS]
        dept_dirs = [p for p in children if p.name in DEPARTMENTS]
        if not dcc_dirs:
            continue

        if len(dcc_dirs) == 1 and not dept_dirs:
            dcc = dcc_dirs[0]
            dept = SINGLE_DCC_TO_DEPT.get(dcc.name)
            if not dept:
                plan.append(("SKIP", dcc, dcc))
                continue
            plan.append(("rename", dcc, shot / dept))
        else:
            for dcc in dcc_dirs:
                dept = MULTI_DCC_TO_DEPT.get(dcc.name)
                if not dept:
                    plan.append(("SKIP", dcc, dcc))
                    continue
                plan.append(("nest", dcc, shot / dept / dcc.name))
    return plan


def count_files(path: Path) -> int:
    return sum(1 for p in path.rglob("*") if p.is_file() and p.name != ".DS_Store")


def apply_plan(plan: list[tuple[str, Path, Path]], manifest: Path) -> None:
    """Execute the plan, recording every move in *manifest* before doing it."""
    rows = ["# action\tsrc\tdst"]
    done = []
    for action, src, dst in plan:
        if action == "SKIP":
            print(f"  SKIP    {src}  (no department mapping)")
            continue
        if not src.exists():
            print(f"  SKIP    {src}  (source gone)")
            continue
        if dst.exists():
            print(f"  SKIP    {dst}  (destination already exists)")
            continue
        rows.append(f"{action}\t{src}\t{dst}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.rename(src, dst)
        done.append((action, src, dst))
        print(f"  {action:<7} {src.relative_to(ROOT)}  ->  {dst.relative_to(ROOT)}")
    manifest.write_text("\n".join(rows) + "\n")
    print(f"\n{len(done)} move(s) applied · manifest: {manifest}")


def report(root: Path) -> int:
    """Flag any app-named folder that is not nested inside a department.

    ``fx/houdini`` is correct (department outside, dcc inside); ``shot/nuke``
    is not, because the parent is the shot itself rather than a department.
    """
    bad = []
    for dirpath, dirnames, _ in os.walk(root):
        for name in dirnames:
            if name in DCC_TOKENS and Path(dirpath).name not in DEPARTMENTS:
                bad.append(Path(dirpath) / name)
    print("\n--- compliance check")
    if not bad:
        print("  every app-named folder sits inside a department")
        return 0
    for path in bad:
        print(f"  violates: {path.relative_to(root)}  (parent {path.parent.name!r} is not a department)")
    return len(bad)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--root", default=str(ROOT))
    args = ap.parse_args()
    root = Path(args.root)

    if not (args.dry_run or args.apply):
        ap.error("pass --dry-run or --apply")

    plan = plan_moves(root)
    print(f"--- plan ({len(plan)} item(s))")
    for action, src, dst in plan:
        try:
            rel_src = src.relative_to(root)
        except ValueError:
            rel_src = src
        try:
            rel_dst = dst.relative_to(root)
        except ValueError:
            rel_dst = dst
        print(f"  {action:<7} {rel_src}  ->  {rel_dst}   [{count_files(src)} file(s)]")

    if args.dry_run:
        report(root)
        print("\ndry run — nothing moved")
        return 0

    print("\n--- applying")
    apply_plan(plan, MANIFEST)
    return report(root)


if __name__ == "__main__":
    sys.exit(main())
