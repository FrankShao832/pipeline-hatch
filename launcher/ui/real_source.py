"""Real backend for the settings panel — the existing projects, read live.

Replaces ``FakeSettingsDataSource`` in the running app: the project rows come
from the launcher database (falling back to ``config/projects.yaml`` when the
database is unreachable), the sequence/shot counts and the scaffold state come
from the real project trees on disk, and the environment rows come from
:mod:`launcher.core.launch_env` — the same function the launcher uses to build a
launch environment, so the preview cannot drift from reality.

Not implemented yet, and reported as a diagnostic instead of pretending:

* ``save_env_row`` / ``delete_env_row`` — there is no ``env.yaml`` store yet
  (plan U7), so the Environment page is read-only.

Writes go through the repository and commit explicitly: ``DatabaseManager``
hands out a raw ``Session``, so a ``with`` block closes it without committing
(found the hard way, 2026-10-25).
"""

from __future__ import annotations

import os
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from launcher.core.launch_env import DEV_SUBDIRS, build_env_context, compute_dev_root
from launcher.ui.viewmodels import (
    ApplySummary,
    DiagnosticRow,
    EnvRow,
    ProjectRow,
    ResolvedRow,
    ScaffoldPlanRow,
)

NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

#: Keys the launcher injects that are *not* in the ``dcc.yaml`` whitelist are
#: dropped by the DCC layer. ``JOB`` is the documented exception (Houdini
#: derives it from its own config), see plan D-H.
WHITELIST_EXCEPTIONS: tuple[str, ...] = ("JOB",)


def _list_dirs(path: str) -> list[str]:
    """Return the sorted subdirectory names of *path* (``[]`` when missing)."""
    try:
        return sorted(p.name for p in Path(path).iterdir() if p.is_dir())
    except OSError:
        return []


class RealSettingsDataSource:
    """``SettingsDataSource`` backed by the launcher database and the disk."""

    def __init__(self, db: Any = None, config: Any = None) -> None:
        """Store the collaborators lazily.

        Args:
            db: ``DatabaseManager`` instance; resolved on first use when omitted.
            config: ``ConfigManager`` instance; resolved on first use when omitted.
        """
        self._db = db
        self._config = config

    # -- Collaborators -----------------------------------------------------

    @property
    def db(self) -> Any:
        if self._db is None:
            from launcher.database.database import DatabaseManager

            self._db = DatabaseManager()
        return self._db

    @property
    def config(self) -> Any:
        if self._config is None:
            from launcher.core.config_manager import config_manager

            self._config = config_manager
        return self._config

    # -- Config helpers ----------------------------------------------------

    def _dcc_roles(self) -> tuple[str, ...]:
        """Return the configured DCC keys (``maya`` / ``houdini`` / ...)."""
        try:
            return tuple((self.config.get_dcc_config() or {}).get("dcc", {}).keys())
        except Exception:
            return ()

    def _env_whitelist(self) -> tuple[str, ...]:
        """Return ``dcc.yaml: pipeline.env_vars`` — the keys a DCC receives."""
        try:
            pipeline = (self.config.get_dcc_config() or {}).get("pipeline", {}) or {}
            return tuple(pipeline.get("env_vars") or ())
        except Exception:
            return ()

    # -- Projects ----------------------------------------------------------

    def _db_rows(self) -> list[ProjectRow] | None:
        """Read projects from the database (``None`` when it is unavailable)."""
        try:
            if not self.db.is_connected:
                return None
            from launcher.database.repository import ProjectRepo

            with self.db.get_session() as session:
                rows = [
                    ProjectRow(
                        name=p.name,
                        root=p.root_path,
                        publish_root=p.publish_root,
                        enabled=bool(p.enabled),
                        source="db",
                    )
                    for p in ProjectRepo(session).list_projects()
                ]
            return rows
        except Exception:
            return None

    def _yaml_rows(self) -> list[ProjectRow]:
        """Read the YAML project list (``config/projects.yaml``)."""
        try:
            rows = []
            for proj in self.config.get_project_list():
                name = proj.get("name") or ""
                if not name:
                    continue
                rows.append(
                    ProjectRow(
                        name=name,
                        root=proj.get("root", ""),
                        publish_root=proj.get("publish_root", ""),
                        enabled=bool(proj.get("enabled", True)),
                        source="yaml",
                    )
                )
            return rows
        except Exception:
            return []

    def _merged_rows(self) -> list[ProjectRow]:
        """Database rows first, then YAML-only rows the database does not know."""
        rows = self._db_rows()
        if rows is None:
            return self._yaml_rows()
        known = {r.name for r in rows}
        return rows + [r for r in self._yaml_rows() if r.name not in known]

    def _find(self, name: str) -> ProjectRow | None:
        for row in self._merged_rows():
            if row.name == name:
                return row
        return None

    def _count_tree(self, project_dir: str) -> tuple[int, int]:
        """Return ``(sequences, shots)`` counted from the project tree."""
        seqs = _list_dirs(project_dir)
        shots = sum(len(_list_dirs(os.path.join(project_dir, seq))) for seq in seqs)
        return len(seqs), shots

    def projects(self) -> list[ProjectRow]:
        """Every configured project with disk stats and scaffold state."""
        out: list[ProjectRow] = []
        for row in self._merged_rows():
            project_dir = os.path.join(row.root, row.name)
            seqs, shots = self._count_tree(project_dir)
            plan = self.scaffold_plan(row.name)
            missing = [p for p in plan if p.required and not p.exists]
            out.append(
                replace(
                    row,
                    seqs=seqs,
                    shots=shots,
                    env_show_count=0,      # no show-scoped env store yet (U7)
                    scaffold_state="complete" if not missing else "missing",
                    scaffold_missing=len(missing),
                )
            )
        return out

    # -- Scaffold ----------------------------------------------------------

    def _plan_for(self, name: str, root: str, publish_root: str) -> list[ScaffoldPlanRow]:
        """Build the skeleton plan for one project at the given roots."""
        rows = [
            ScaffoldPlanRow(
                path=os.path.join(root, name), group="required", required=True,
                exists=os.path.isdir(os.path.join(root, name)),
            ),
            ScaffoldPlanRow(
                path=os.path.join(publish_root, name), group="required", required=True,
                exists=os.path.isdir(os.path.join(publish_root, name)),
            ),
        ]
        dev_root = compute_dev_root(root)
        for sub in DEV_SUBDIRS:
            path = os.path.join(dev_root, sub, name) if dev_root else ""
            rows.append(
                ScaffoldPlanRow(path=path, group="dev_root", required=False,
                                exists=bool(path) and os.path.isdir(path))
            )
        # Existing sequences are listed so the page can show, not create, them.
        for seq in _list_dirs(os.path.join(root, name)):
            rows.append(
                ScaffoldPlanRow(path=os.path.join(root, name, seq),
                                group="sequences", required=False, exists=True)
            )
        return rows

    def scaffold_plan(self, name: str) -> list[ScaffoldPlanRow]:
        """Return the skeleton plan for *name* (``[]`` when the project is unknown)."""
        row = self._find(name)
        if row is None:
            return []
        return self._plan_for(name, row.root, row.publish_root)

    def repair(self, name: str, dry_run: bool) -> ApplySummary:
        """Create the missing skeleton directories; idempotent by construction."""
        row = self._find(name)
        if row is None:
            return ApplySummary(
                errors=((name, "unknown project"),),
                diagnostics=(DiagnosticRow("error", "E_PROJECT",
                                           f"Unknown project: {name}", target=name),),
            )
        created: list[str] = []
        skipped: list[str] = []
        errors: list[tuple[str, str]] = []
        for item in self._plan_for(name, row.root, row.publish_root):
            if not item.path:
                continue
            if os.path.isdir(item.path):
                skipped.append(item.path)
                continue
            if dry_run:
                created.append(item.path)
                continue
            try:
                os.makedirs(item.path, exist_ok=True)
                created.append(item.path)
            except OSError as exc:
                errors.append((item.path, str(exc)))
        return ApplySummary(created=tuple(created), skipped=tuple(skipped),
                            errors=tuple(errors))

    def validate_project(self, name: str, root: str,
                         publish_root: str) -> list[DiagnosticRow]:
        """Validate a name/root pair before it is written."""
        out: list[DiagnosticRow] = []
        if not NAME_PATTERN.match(name or ""):
            out.append(DiagnosticRow(
                "error", "E_NAME", f"Invalid project name: {name!r}",
                "Must start with a letter; letters, digits and underscores only.",
                target=name,
            ))
        for label, path in (("root", root), ("publish root", publish_root)):
            if not path or not path.startswith("/"):
                out.append(DiagnosticRow(
                    "error", "E_PATHREL", f"{label.capitalize()} must be absolute: {path!r}",
                    target=name,
                ))
        existing = self._find(name)
        if existing is not None and existing.root != root:
            out.append(DiagnosticRow(
                "error", "E_DUP", f"Project {name!r} already exists at {existing.root}",
                "Pick another name or edit the existing row.", target=name,
            ))
        if root and not os.path.isdir(os.path.join(root, name)):
            out.append(DiagnosticRow(
                "warn", "W_ROOT", f"Work folder does not exist: {os.path.join(root, name)}",
                "Repair scaffold will create it.", target=name,
            ))
        if publish_root and not os.path.isdir(os.path.join(publish_root, name)):
            out.append(DiagnosticRow(
                "warn", "W_PUB", f"Publish folder does not exist: {os.path.join(publish_root, name)}",
                "Repair scaffold will create it.", target=name,
            ))
        return out

    def create_project(self, name: str, root: str, publish_root: str,
                       options: dict[str, Any], dry_run: bool) -> ApplySummary:
        """Create the database row and the skeleton (nothing else).

        ``options`` is accepted for the wizard's benefit; ``sequences`` is the
        only key honoured so far (a list of names to pre-create).
        """
        diagnostics = tuple(self.validate_project(name, root, publish_root))
        blocking = [d for d in diagnostics if d.level == "error"]
        if blocking:
            return ApplySummary(errors=((name, blocking[0].message),),
                                diagnostics=diagnostics)

        plan = self._plan_for(name, root, publish_root)
        for seq in options.get("sequences", ()) or ():
            plan.append(ScaffoldPlanRow(path=os.path.join(root, name, str(seq)),
                                        group="sequences", required=False,
                                        exists=os.path.isdir(os.path.join(root, name, str(seq)))))
        missing = [p.path for p in plan if p.path and not p.exists]
        if dry_run:
            return ApplySummary(created=tuple(missing),
                                skipped=tuple(p.path for p in plan if p.path and p.exists),
                                diagnostics=diagnostics)

        created: list[str] = []
        errors: list[tuple[str, str]] = []
        for path in missing:
            try:
                os.makedirs(path, exist_ok=True)
                created.append(path)
            except OSError as exc:
                errors.append((path, str(exc)))

        try:
            from launcher.database.repository import ProjectRepo

            session = self.db.get_session()
            try:
                ProjectRepo(session).create(name=name, root_path=root,
                                            publish_root=publish_root)
                session.commit()          # raw Session: closing does not commit
            finally:
                session.close()
        except Exception as exc:
            errors.append((name, f"database: {exc}"))

        return ApplySummary(created=tuple(created),
                            skipped=tuple(p.path for p in plan if p.path and p.exists),
                            errors=tuple(errors), diagnostics=diagnostics)

    # -- Environment -------------------------------------------------------

    def _sample_context(self, show: str = "", dcc: str = "",
                        department: str = "") -> tuple[dict[str, str], str]:
        """Build a real env context for *show*, picking a sample seq/shot.

        The launch environment depends on the shot, so a show-level preview has
        to choose one; the first sequence/shot on disk is used and its name is
        returned so the caller can label the rows honestly.
        """
        row = self._find(show) if show else None
        if row is None:
            enabled = [r for r in self.projects() if r.enabled]
            row = enabled[0] if enabled else None
        if row is None:
            return {}, ""

        project_dir = os.path.join(row.root, row.name)
        seqs = _list_dirs(project_dir)
        seq = seqs[0] if seqs else ""
        shots = _list_dirs(os.path.join(project_dir, seq)) if seq else []
        shot = shots[0] if shots else ""
        roles = self._dcc_roles()
        ctx = build_env_context(
            root_path=row.root,
            publish_root_path=row.publish_root,
            project=row.name,
            sequence=seq,
            shot=shot,
            department=department or "fx",
            dcc=dcc or (roles[0] if roles else ""),
        )
        return ctx, f"{row.name}/{seq}/{shot}" if seq else row.name

    def env_rows(self) -> list[EnvRow]:
        """One row per injected variable, computed from the first enabled show.

        There is no ``env.yaml`` store yet, so every row is ``derived``: the
        value a launch would inject, not something a user can edit here.
        """
        ctx, sample = self._sample_context()
        whitelist = self._env_whitelist()
        roles = self._dcc_roles()
        return [
            EnvRow(
                name=name,
                value=value,
                scope="derived",
                enabled=True,
                description=f"computed at launch for {sample}" if sample else
                            "computed at launch",
                injected_to=tuple(roles) if name in whitelist else (),
            )
            for name, value in sorted(ctx.items())
        ]

    def save_env_row(self, row: EnvRow) -> list[DiagnosticRow]:
        """Read-only for now: no ``env.yaml`` store exists (plan U7)."""
        return [DiagnosticRow(
            "warn", "W_NO_STORE",
            f"Cannot edit {row.name}: the environment store is not implemented yet",
            "Rows are derived from the launch environment; overrides land in U7.",
            target=row.name,
        )]

    def delete_env_row(self, name: str, scope: str,
                       scope_key: str) -> list[DiagnosticRow]:
        """Read-only for now: no ``env.yaml`` store exists (plan U7)."""
        return [DiagnosticRow(
            "warn", "W_NO_STORE",
            f"Cannot delete {name}: the environment store is not implemented yet",
            "Rows are derived from the launch environment; overrides land in U7.",
            target=name,
        )]

    def dcc_roles(self) -> tuple[str, ...]:
        """Configured DCC keys (``dcc.yaml: dcc``)."""
        return self._dcc_roles()

    def departments(self) -> tuple[str, ...]:
        """Canonical department vocabulary (``dcc.yaml: pipeline.departments``)."""
        try:
            pipeline = (self.config.get_dcc_config() or {}).get("pipeline", {}) or {}
            depts = tuple(pipeline.get("departments") or ())
        except Exception:
            depts = ()
        return depts or ("fx", "comp", "lighting")

    def resolved(self, show: str, dcc: str,
                 department: str) -> list[ResolvedRow]:
        """The exact environment a launch would produce, resolved for real."""
        ctx, _sample = self._sample_context(show=show, dcc=dcc, department=department)
        return [ResolvedRow(name=name, value=value, source="derived")
                for name, value in sorted(ctx.items())]

    def diagnostics(self) -> list[DiagnosticRow]:
        """Real problems: unreachable database, missing folders, whitelist drift."""
        out: list[DiagnosticRow] = []
        if self._db_rows() is None:
            out.append(DiagnosticRow(
                "error", "E_DB", "Launcher database is unreachable",
                "Project rows fall back to config/projects.yaml.", target="database",
            ))

        for row in self.projects():
            if not os.path.isdir(os.path.join(row.root, row.name)):
                out.append(DiagnosticRow(
                    "warn", "W_PATH", f"{row.name}: work folder missing",
                    os.path.join(row.root, row.name), target=row.name,
                ))
            if not os.path.isdir(os.path.join(row.publish_root, row.name)):
                out.append(DiagnosticRow(
                    "warn", "W_PUBLISH", f"{row.name}: publish folder missing",
                    os.path.join(row.publish_root, row.name), target=row.name,
                ))

        ctx, _sample = self._sample_context()
        if ctx:
            whitelist = set(self._env_whitelist())
            keys = set(ctx)
            for name in sorted(keys - whitelist):
                if name in WHITELIST_EXCEPTIONS:
                    continue
                out.append(DiagnosticRow(
                    "warn", "W_WHITELIST",
                    f"{name} is injected but not in dcc.yaml: pipeline.env_vars",
                    "prepare_environment drops keys outside the whitelist.",
                    target=name,
                ))
            for name in sorted(whitelist - keys):
                out.append(DiagnosticRow(
                    "info", "I_UNFILLED",
                    f"{name} is whitelisted but never filled",
                    "The DCC layer skips missing keys silently.", target=name,
                ))
            dev_root = compute_dev_root(str(self._find(_sample.split("/")[0]).root
                                            if _sample else ""))
            if dev_root and not os.path.isdir(dev_root):
                out.append(DiagnosticRow(
                    "warn", "W_DEV", f"$DEV does not exist: {dev_root}",
                    "CACHE/ASSET/RENDER roots point outside the disk.", target="DEV",
                ))
        return out
