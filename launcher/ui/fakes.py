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

from typing import Any

from .viewmodels import (
    ApplySummary,
    DiagnosticRow,
    EnvRow,
    ProjectRow,
    ResolvedRow,
    ScaffoldPlanRow,
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

    def scaffold_plan(self, name: str) -> list[ScaffoldPlanRow]:
        root = "/Volumes/Development/projects/y_pipeline_projects"
        publish = "/Volumes/Development/projects/y_pipeline_publish"
        rows = [
            ScaffoldPlanRow(path=f"{root}/{name}", group="required", required=True),
            ScaffoldPlanRow(path=f"{publish}/{name}", group="required", required=True),
        ]
        for seq in ("seq001", "seq002"):
            rows.append(ScaffoldPlanRow(
                path=f"{root}/{name}/{seq}", group="sequences", required=False))
            for shot in ("sh010", "sh020"):
                rows.append(ScaffoldPlanRow(
                    path=f"{root}/{name}/{seq}/{shot}", group="sequences",
                    required=False))
        for sub in ("cache", "assets", "renders"):
            rows.append(ScaffoldPlanRow(
                path=f"{root}/../{sub}/{name}", group="dev_root", required=False))
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
        if dry_run:
            return ApplySummary(created=created)
        self._repaired.add(name)
        self._created.append(ProjectRow(
            name=name, root=root, publish_root=publish_root,
            seqs=len(options.get("seqs", []) or []),
            shots=int(options.get("shots_per_seq", 0) or 0),
            env_show_count=0, scaffold_state="complete", scaffold_missing=0,
        ))
        return ApplySummary(created=created)

    # -- Environment ------------------------------------------------------

    def env_rows(self) -> list[EnvRow]:
        return list(self._env)

    def save_env_row(self, row: EnvRow) -> list[DiagnosticRow]:
        key = (row.name, row.scope, row.scope_key)
        for idx, existing in enumerate(self._env):
            if (existing.name, existing.scope, existing.scope_key) == key:
                self._env[idx] = row
                return []
        self._env.append(row)
        return []

    def delete_env_row(self, name: str, scope: str,
                       scope_key: str) -> list[DiagnosticRow]:
        self._env = [
            r for r in self._env
            if (r.name, r.scope, r.scope_key) != (name, scope, scope_key)
        ]
        return []

    def resolved(self, show: str, dcc: str,
                 department: str) -> list[ResolvedRow]:
        """26 rows: the 19 injected keys plus OCIO-family extras."""
        if not show or self.mode == "empty":
            return []
        dev = "/Volumes/Development"
        root = f"{dev}/projects/y_pipeline_projects"
        publish = f"{dev}/projects/y_pipeline_publish"
        dept = department or "fx"
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
