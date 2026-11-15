"""In-memory fixture data source for UI-first development (plan v1.1 D-Q).

Lets the whole settings UI be built, demoed and tested before any real backend
exists. Swapping to production is a one-line change in ``main_window``:
``SettingsWindow(data_source=RealDataSource(...))``.

Three fixture modes (plan §4, G3):
    rich   — 3 projects, 12 env rows, 26 resolved rows, 1 warning
    empty  — nothing (verifies empty states)
    errors — 2 errors + 1 warning, and ``projects()`` raises (DB-down behaviour)

This module is a fixture, NOT a domain implementation: its ``validate_project``
checks are deliberately shallow. Never use it as the source of truth.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .viewmodels import (
    SHOT_STATUS_DUPLICATE,
    SHOT_STATUS_EXISTS,
    SHOT_STATUS_NEW,
    ApplySummary,
    DiagnosticRow,
    EnvRow,
    ProjectRow,
    ResolvedRow,
    ScaffoldPlanRow,
    ShotPlanRow,
    classify_shots,
    shot_name_problem,
)

_ALL_DCCS: tuple[str, ...] = ("maya", "houdini", "nuke", "katana")

# (name, value, scope, scope_key, enabled, secret, description, injected_to)
_ENV_FIXTURES: tuple[tuple[str, str, str, str, bool, bool, str, tuple[str, ...]], ...] = (
    ("OCIO", "/Volumes/Development/tools/ocio/aces_1.3.ocio",
     "global", "", True, False, "OCIO config for every DCC", ()),
    ("ACES_CONFIG", "/Volumes/Development/tools/ocio/aces_1.3.ocio",
     "global", "", True, False, "OCIO config path alias", ()),
    ("HOUDINI_PATH", "${DEV}/tools/houdini/&",
     "global", "", True, False, "Houdini tool path", ()),
    ("NUKE_PATH", "${DEV}/tools/nuke/&",
     "global", "", False, False, "Nuke tool path (disabled)", ()),
    ("SG_API_TOKEN", "s3cr3t-token",
     "global", "", True, True, "ShotGrid token (secret, local.yaml only)",
     ("maya", "houdini")),
    ("DCC", "houdini", "derived", "", True, False, "Application role", _ALL_DCCS),
    ("PROJECT_ROOT", "/Volumes/Development/projects/y_pipeline_projects",
     "derived", "", True, False, "Projects container", _ALL_DCCS),
    ("PUBLISH_ROOT", "/Volumes/Development/projects/y_pipeline_publish",
     "derived", "", True, False, "Publish root", _ALL_DCCS),
    ("SHOW", "CyberPunk", "derived", "", True, False, "Current show", _ALL_DCCS),
    ("JOB", "/Volumes/Development/projects/y_pipeline_projects/CyberPunk",
     "dcc", "houdini", True, False, "Houdini project dir (D-H exception)",
     ("houdini",)),
    ("OCIO", "/Volumes/Development/tools/ocio/aces_cg.ocio",
     "show", "CyberPunk", True, False, "CyberPunk override of OCIO", ()),
    ("HOUDINI_PATH", "${DEV}/tools/houdini/cyberpunk/&",
     "show", "CyberPunk", True, False, "CyberPunk houdini tools", ()),
)


#: Same two decisions the real show skeleton seeds (``env_store.SHOW_SKELETON``).
#: Duplicated as data on purpose: the UI layer must not import ``launcher.core``.
_SHOW_SKELETON_FIXTURE: tuple[tuple[str, str, str], ...] = (
    ("OCIO", "${DEV}/color/aces_cg.ocio", "ACES CG colour configuration for this show"),
    ("FPS", "24", "Frame rate the show is authored at"),
)


def _project_fixtures() -> tuple[ProjectRow, ...]:
    return (
        ProjectRow(
            name="CyberPunk",
            root="/Volumes/Development/projects/y_pipeline_projects",
            publish_root="/Volumes/Development/projects/y_pipeline_publish",
            seqs=3, shots=18, env_show_count=2,
            scaffold_state="complete", scaffold_missing=0,
        ),
        ProjectRow(
            name="DragonLand",
            root="/Volumes/Development/projects/y_pipeline_projects",
            publish_root="/Volumes/Development/projects/y_pipeline_publish",
            seqs=2, shots=12, env_show_count=0,
            scaffold_state="missing", scaffold_missing=2,
        ),
        ProjectRow(
            name="SpaceOdyssey",
            root="/mnt/unmounted/pipeline_projects",
            publish_root="/mnt/unmounted/pipeline_publish",
            seqs=2, shots=7, env_show_count=0,
            scaffold_state="n/a", scaffold_missing=0,
        ),
    )


class FakeSettingsDataSource:
    """Fixture implementation of :class:`SettingsDataSource`."""

    MODES: tuple[str, ...] = ("rich", "empty", "errors")

    def __init__(self, mode: str = "rich") -> None:
        if mode not in self.MODES:
            raise ValueError(f"unknown fixture mode: {mode!r}")
        self.mode = mode
        self._repaired: set[str] = set()
        self._created: list[ProjectRow] = []
        self._added_shots: dict[str, set[str]] = {}
        #: Shots created at runtime are untouched, so they can be renamed; the
        #: fixture's own shots stand in for work in progress and cannot.
        self._empty_shots: set[str] = set()
        self._env_backups: list[list[EnvRow]] = []
        self._env: list[EnvRow] = [] if mode == "empty" else [
            EnvRow(name=n, value=v, scope=s, scope_key=k, enabled=e,
                   secret=sec, description=d, injected_to=inj)
            for (n, v, s, k, e, sec, d, inj) in _ENV_FIXTURES
        ]

    # -- Projects ---------------------------------------------------------

    def projects(self) -> list[ProjectRow]:
        if self.mode == "errors":
            raise RuntimeError("database unavailable (fixture)")
        if self.mode == "empty":
            return list(self._created)
        return list(_project_fixtures()) + list(self._created)

    def _fixture_row(self, name: str) -> ProjectRow | None:
        """The fixture row for *name*, without going through ``projects()``.

        ``projects()`` raises in ``errors`` mode on purpose; the plan still has
        to describe *something* so the planner-facing calls stay total.
        """
        for row in list(_project_fixtures()) + list(self._created):
            if row.name == name:
                return row
        return None

    def scaffold_plan(self, name: str) -> list[ScaffoldPlanRow]:
        """Skeleton plan whose ``exists`` flags agree with the project's state.

        Consistency matters here: the panel renders ✓/✗ straight from these
        flags, so a "complete" project whose plan claims every folder is missing
        would show a red verdict for a healthy show (and vice versa after a
        repair). A repaired project therefore flips to all-exists.
        """
        dev = "/Volumes/Development"
        root = f"{dev}/projects/y_pipeline_projects"
        publish = f"{dev}/projects/y_pipeline_publish"
        row = self._fixture_row(name)
        state = row.scaffold_state if row is not None else "n/a"
        repaired = name in self._repaired
        exists = repaired or state == "complete"

        rows = [
            ScaffoldPlanRow(path=f"{root}/{name}", group="required", required=True,
                            exists=exists),
            ScaffoldPlanRow(path=f"{publish}/{name}", group="required", required=True,
                            exists=exists),
        ]
        if row is None:
            # A project that does not exist yet has no sequences to list. The
            # real backend plans exactly this shape (2 roots + 3 dev folders),
            # and the New Project preview quotes the count — a fixture that
            # invented extra folders would make the demo promise more than the
            # pipeline creates.
            for sub in ("cache", "assets", "renders"):
                rows.append(ScaffoldPlanRow(
                    path=f"{dev}/{sub}/{name}", group="dev_root", required=False,
                    exists=False))
            return rows
        for seq in ("seq001", "seq002"):
            rows.append(ScaffoldPlanRow(
                path=f"{root}/{name}/{seq}", group="sequences", required=False,
                exists=exists))
            for shot in ("sh010", "sh020"):
                rows.append(ScaffoldPlanRow(
                    path=f"{root}/{name}/{seq}/{shot}", group="sequences",
                    required=False, exists=exists))
        for sub in ("cache", "assets", "renders"):
            rows.append(ScaffoldPlanRow(
                path=f"{dev}/{sub}/{name}", group="dev_root", required=False,
                exists=exists))
        return rows

    def repair(self, name: str, dry_run: bool) -> ApplySummary:
        """Pretend to apply the skeleton; idempotent on the second call."""
        if name in self._repaired:
            return ApplySummary(skipped=tuple(r.path for r in self.scaffold_plan(name)))
        missing = [r.path for r in self.scaffold_plan(name) if not r.exists]
        if not dry_run:
            self._repaired.add(name)
        return ApplySummary(created=tuple(missing))

    def validate_project(self, name: str, root: str,
                         publish_root: str) -> list[DiagnosticRow]:
        out: list[DiagnosticRow] = []
        if not name or not name[0].isalpha() or not name.replace("_", "").isalnum():
            out.append(DiagnosticRow("error", "E_NAME",
                                     f"Invalid project name: {name!r}",
                                     "Must start with a letter; letters, digits "
                                     "and underscores only.", target=name))
        if not root.startswith("/"):
            out.append(DiagnosticRow("error", "E_PATHREL",
                                     "Root path must be absolute.",
                                     "Use Browse to pick a directory.", target=name))
        if publish_root and publish_root == root:
            out.append(DiagnosticRow("error", "E_PATHREL",
                                     "Publish root must differ from root.",
                                     "Pick a separate publish volume.", target=name))
        return out

    def create_project(self, name: str, root: str, publish_root: str,
                       options: dict[str, Any], dry_run: bool) -> ApplySummary:
        plan = self.scaffold_plan(name)
        created = tuple(r.path for r in plan if not r.exists)
        # Mirrors the real backend's show skeleton (card C8): the count is a
        # fixture, but it is the same number the real store would write, or the
        # demo's summary would disagree with the pipeline's.
        env_written = len(_SHOW_SKELETON_FIXTURE)
        if dry_run:
            return ApplySummary(created=created, env_written=env_written)
        self._repaired.add(name)
        self._env_backups.append(list(self._env))
        self._env.extend(
            EnvRow(name=n, value=v, scope="show", scope_key=name, description=d)
            for n, v, d in _SHOW_SKELETON_FIXTURE)
        self._created.append(ProjectRow(
            name=name, root=root, publish_root=publish_root,
            seqs=len(options.get("seqs", []) or []),
            shots=int(options.get("shots_per_seq", 0) or 0),
            env_show_count=env_written, scaffold_state="complete", scaffold_missing=0,
        ))
        return ApplySummary(created=created, env_written=env_written)

    # -- Shots -------------------------------------------------------------
    #
    # The fixture answers from a set of paths instead of the filesystem, but it
    # classifies with the very same ``classify_shots`` the real source uses —
    # a fixture that reimplemented the rules would let the dialog's badges pass
    # tests while disagreeing with the pipeline.

    def _shot_root(self, name: str) -> str:
        return f"/Volumes/Development/projects/y_pipeline_projects/{name}"

    def _existing_shot_paths(self, name: str) -> set[str]:
        """Paths that "exist" in the fixture, following each project's state.

        ``complete`` (or repaired) projects have two sequences with two shots
        each, mirroring :meth:`scaffold_plan`; anything added at runtime is kept.
        """
        row = self._fixture_row(name)
        complete = name in self._repaired or (
            row is not None and row.scaffold_state == "complete")
        root = self._shot_root(name)
        paths: set[str] = set()
        if complete:
            for seq in ("seq001", "seq002"):
                paths.add(f"{root}/{seq}")
                for shot in ("sh010", "sh020"):
                    paths.add(f"{root}/{seq}/{shot}")
        paths |= self._added_shots.get(name, set())
        return paths

    def sequences(self, name: str) -> list[str]:
        root = self._shot_root(name) + "/"
        return sorted({p[len(root):] for p in self._existing_shot_paths(name)
                       if p.startswith(root) and "/" not in p[len(root):]})

    def shots(self, name: str, sequence: str) -> list[str]:
        root = f"{self._shot_root(name)}/{sequence}/"
        return sorted({p[len(root):] for p in self._existing_shot_paths(name)
                       if p.startswith(root) and "/" not in p[len(root):]})

    def plan_shots(self, name: str,
                   entries: Sequence[tuple[str, str]]) -> tuple[ShotPlanRow, ...]:
        root = self._shot_root(name)
        existing = self._existing_shot_paths(name)

        def path_for(sequence: str, shot: str) -> str:
            return f"{root}/{sequence}/{shot}" if shot else f"{root}/{sequence}"

        return classify_shots(entries, path_for, lambda p: p in existing)

    def add_shots(self, name: str, entries: Sequence[tuple[str, str]],
                  dry_run: bool) -> ApplySummary:
        rows = self.plan_shots(name, entries)
        invalid = [r for r in rows if r.blocks]
        if invalid:
            return ApplySummary(
                errors=tuple((f"{r.sequence or '?'}/{r.shot or '?'}", r.message)
                             for r in invalid),
                diagnostics=tuple(
                    DiagnosticRow("error", "E_SHOTNAME",
                                  f"{r.sequence}/{r.shot}: {r.message}",
                                  "A shot name is one path segment: no '/', no "
                                  "leading '.', no spaces.", target=r.shot)
                    for r in invalid),
            )
        created = tuple(r.path for r in rows if r.status == SHOT_STATUS_NEW)
        skipped = tuple(r.path for r in rows
                        if r.status in (SHOT_STATUS_EXISTS, SHOT_STATUS_DUPLICATE))
        if dry_run:
            return ApplySummary(created=created, skipped=skipped)
        bucket = self._added_shots.setdefault(name, set())
        bucket.update(created)
        self._empty_shots.update(created)
        # The sequence folder appears with its first shot, never on its own.
        bucket.update({p.rsplit("/", 1)[0] for p in created})
        return ApplySummary(created=created, skipped=skipped)

    def rename_shot(self, name: str, sequence: str, shot: str,
                    new_name: str, dry_run: bool) -> ApplySummary:
        root = self._shot_root(name)
        old_path = f"{root}/{sequence}/{shot}"
        new_name = (new_name or "").strip()
        new_path = f"{root}/{sequence}/{new_name}"
        existing = self._existing_shot_paths(name)

        def fail(code: str, message: str) -> ApplySummary:
            return ApplySummary(
                errors=((shot, message),),
                diagnostics=(DiagnosticRow("error", code, message,
                                           "Only an untouched shot can be renamed.",
                                           target=shot),))

        if old_path not in existing:
            return fail("E_NO_SHOT", f"Shot folder is gone: {old_path}")
        if old_path not in self._empty_shots:
            return fail("E_NOT_EMPTY", f"{sequence}/{shot} already has files in it")
        problem = shot_name_problem(new_name)
        if problem:
            return fail("E_NAME", f"Invalid name: {problem}")
        if new_name == shot:
            return fail("E_SAME", "That is the current name")
        if new_path in existing:
            return fail("E_EXISTS", f"{sequence}/{new_name} already exists")
        if dry_run:
            return ApplySummary(created=(new_path,))
        bucket = self._added_shots.setdefault(name, set())
        bucket.discard(old_path)
        bucket.add(new_path)
        self._empty_shots.discard(old_path)
        self._empty_shots.add(new_path)
        return ApplySummary(created=(new_path,))

    # -- Environment ------------------------------------------------------

    def env_rows(self) -> list[EnvRow]:
        return list(self._env)

    def save_env_row(self, row: EnvRow) -> list[DiagnosticRow]:
        key = (row.name, row.scope, row.scope_key)
        # Snapshot before mutating: one backup per write, like the real store.
        self._env_backups.append(list(self._env))
        for idx, existing in enumerate(self._env):
            if (existing.name, existing.scope, existing.scope_key) == key:
                self._env[idx] = row
                return []
        self._env.append(row)
        return []

    def has_env_backup(self) -> bool:
        """Fixture mirror of the real store's ``.bak`` presence."""
        return bool(self._env_backups)

    def revert_env(self) -> list[DiagnosticRow]:
        """Restore the rows captured before the last save (idempotent)."""
        if not self._env_backups:
            return [DiagnosticRow(
                "warn", "W_NO_BACKUP", "Nothing to revert to",
                "The first edit creates a backup next to env.yaml.",
                target="env.yaml")]
        self._env = list(self._env_backups[-1])
        return []

    def delete_env_row(self, name: str, scope: str,
                       scope_key: str) -> list[DiagnosticRow]:
        self._env = [
            r for r in self._env
            if (r.name, r.scope, r.scope_key) != (name, scope, scope_key)
        ]
        return []

    def dcc_roles(self) -> tuple[str, ...]:
        """Fixture DCC roles (same three the app ships)."""
        return ("maya", "houdini", "nuke")

    def departments(self) -> tuple[str, ...]:
        """Fixture departments (the reduced three from the old config)."""
        return ("fx", "comp", "lighting")

    def resolved(self, show: str, dcc: str,
                 department: str) -> list[ResolvedRow]:
        """26 rows: the 19 injected keys plus OCIO-family extras."""
        if not show or self.mode == "empty":
            return []
        dev = "/Volumes/Development"
        root = f"{dev}/projects/y_pipeline_projects"
        publish = f"{dev}/projects/y_pipeline_publish"
        # Never invent a department: an unset context must show an empty
        # DEPARTMENT, otherwise the preview claims a value nobody chose.
        dept = department or ""
        base: tuple[tuple[str, str, str], ...] = (
            ("DCC", dcc or "houdini", "derived"),
            ("DEPARTMENT", dept, "derived"),
            ("CACHE_ROOT", f"{dev}/cache/{show}", "derived"),
            ("DEV", dev, "derived"),
            ("ASSET_ROOT", f"{dev}/assets/{show}", "derived"),
            ("RENDER_ROOT", f"{dev}/renders/{show}", "derived"),
            ("PUBLISHER_ENABLE_DATABASE", "true", "derived"),
            ("PROJECT_ROOT", root, "derived"),
            ("PUBLISH_ROOT", publish, "derived"),
            ("SHOW", show, "derived"),
            ("SEQ", "seq001", "derived"),
            ("SHOT", "sh010", "derived"),
            ("PIPELINE_PROJECT", show, "derived"),
            ("PIPELINE_SEQUENCE", "seq001", "derived"),
            ("PIPELINE_SHOT", "sh010", "derived"),
            ("PIPELINE_DEPARTMENT", dept, "derived"),
            ("PIPELINE_USER", "frank", "derived"),
            ("PIPELINE_DCC", dcc or "houdini", "derived"),
            ("JOB", f"{root}/{show}", "dcc"),
            ("PIPELINE_PUBLISHER", f"{dev}/tools/pipeline/pipeline_publisher", "dcc"),
        )
        rows = [ResolvedRow(name=n, value=v, source=s) for (n, v, s) in base]
        rows.extend([
            ResolvedRow("OCIO", f"{dev}/tools/ocio/aces_cg.ocio", "show",
                        shadowed=(("global", f"{dev}/tools/ocio/aces_1.3.ocio"),)),
            ResolvedRow("HOUDINI_PATH", f"{dev}/tools/houdini/{show.lower()}/&", "show",
                        shadowed=(("global", f"{dev}/tools/houdini/&"),)),
            ResolvedRow("ACES_CONFIG", f"{dev}/tools/ocio/aces_1.3.ocio", "global"),
            ResolvedRow("NUKE_PATH", f"{dev}/tools/nuke/&", "global"),
            ResolvedRow("SG_API_TOKEN", "s3cr3t-token", "global"),
            ResolvedRow("PYTHONPATH", f"{dev}/tools/pipeline/lib", "global"),
        ])
        return rows

    def diagnostics(self) -> list[DiagnosticRow]:
        if self.mode == "errors":
            return [
                DiagnosticRow("error", "E_NAME", "Duplicate project name: Demo",
                              "Choose another name.", target="Demo"),
                DiagnosticRow("error", "W_PATH", "RENDER_ROOT does not exist.",
                              "Check $DEV mounts.", target="RENDER_ROOT"),
                DiagnosticRow("warn", "W_KEY_NOT_INJECTED",
                              "HOUDINI_PATH is not in pipeline.env_vars.",
                              "Add it to config/dcc.yaml.", target="HOUDINI_PATH"),
            ]
        if self.mode == "empty":
            return []
        return [
            DiagnosticRow("warn", "W_KEY_NOT_INJECTED",
                          "HOUDINI_PATH is not in pipeline.env_vars, so DCCs "
                          "will not receive it.",
                          "Add the key to config/dcc.yaml: pipeline.env_vars.",
                          target="HOUDINI_PATH"),
        ]
