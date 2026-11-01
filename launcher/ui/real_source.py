"""Real backend for the settings panel — the existing projects, read live.

Replaces ``FakeSettingsDataSource`` in the running app: the project rows come
from the launcher database (falling back to ``config/projects.yaml`` when the
database is unreachable), the sequence/shot counts and the scaffold state come
from the real project trees on disk, and the environment rows come from
:mod:`launcher.core.launch_env` — the same function the launcher uses to build a
launch environment, so the preview cannot drift from reality — layered with the
stored overrides from ``config/env.yaml`` (:mod:`launcher.core.env_resolver`).

Not implemented yet, and reported as a diagnostic instead of pretending:

* ``delete_env_row`` — removing an override lands with the Environment page
  (plan U7).

Writes to the override store go through :mod:`launcher.core.env_store`, which
keeps the previous bytes as ``env.yaml.bak.<timestamp>`` on every save.

Writes go through the repository and commit explicitly: ``DatabaseManager``
hands out a raw ``Session``, so a ``with`` block closes it without committing
(found the hard way, 2026-10-25).
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from launcher.core.env_resolver import resolve
from launcher.core.env_store import EnvConfig, EnvStoreError
from launcher.core.launch_env import DEV_SUBDIRS, build_env_context, compute_dev_root
from launcher.ui.viewmodels import (
    GUARDED_SCOPE_KEYS,
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

NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

#: Keys the launcher injects that are *not* in the ``dcc.yaml`` whitelist are
#: dropped by the DCC layer. ``JOB`` is the documented exception (Houdini
#: derives it from its own config), see plan D-H.
WHITELIST_EXCEPTIONS: tuple[str, ...] = ("JOB",)

#: Suffix of the one-backup-per-save copies ``EnvConfig.save`` leaves behind.
BACKUP_SUFFIX = ".bak."


def shot_is_empty(path: str) -> bool:
    """True when nothing but hidden files live under *path*.

    ``.DS_Store`` and friends are not work product — Finder makes them just by
    looking at a folder — so they do not disqualify a shot from being renamed.
    Any real file, at any depth, does: that is somebody's work.
    """
    for _root, _dirs, files in os.walk(path):
        if any(not name.startswith(".") for name in files):
            return False
    return True


def _rename_error(code: str, message: str, hint: str, target: str) -> ApplySummary:
    """A refusal, shaped like every other apply result in this module."""
    return ApplySummary(
        errors=((target, message),),
        diagnostics=(DiagnosticRow("error", code, message, hint, target=target),),
    )


def _list_dirs(path: str) -> list[str]:
    """Return the sorted subdirectory names of *path* (``[]`` when missing)."""
    try:
        return sorted(p.name for p in Path(path).iterdir() if p.is_dir())
    except OSError:
        return []


class RealSettingsDataSource:
    """``SettingsDataSource`` backed by the launcher database and the disk."""

    def __init__(self, db: Any = None, config: Any = None,
                 env_store_path: str | Path | None = None) -> None:
        """Store the collaborators lazily.

        Args:
            db: ``DatabaseManager`` instance; resolved on first use when omitted.
            config: ``ConfigManager`` instance; resolved on first use when omitted.
            env_store_path: ``env.yaml`` to read overrides from. Defaults to
                ``<config dir>/env.yaml``; tests point it at a temp file so a
                developer's local overrides cannot change the assertions.
        """
        self._db = db
        self._config = config
        self._env_store_path = env_store_path

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

    @property
    def env_store_path(self) -> Path:
        """The override store this backend reads (and later writes)."""
        if self._env_store_path is not None:
            return Path(self._env_store_path)
        return Path(self.config.config_dir) / "env.yaml"

    def _load_store(self) -> tuple[EnvConfig | None, DiagnosticRow | None]:
        """Read the override store.

        Returns:
            ``(store, None)`` on success — ``(None, diagnostic)`` when the file
            exists but cannot be trusted. A broken store must never look like an
            empty one: the preview would then claim a show's paths are derived
            while its overrides sit unread on disk.
        """
        try:
            return EnvConfig.load(self.env_store_path), None
        except EnvStoreError as exc:
            return None, DiagnosticRow(
                "error", "E_ENV_STORE",
                f"Environment overrides cannot be read: {exc}",
                "Fix config/env.yaml — overrides are ignored until it parses.",
                target="env.yaml",
            )

    def _show_env_counts(self) -> dict[str, int]:
        """How many overrides each show owns (``scopes.show.<show>``).

        Counted from the store rather than guessed, so the project column's
        "N show-scoped var(s)" matches what the resolved preview actually got
        from that layer. An unreadable store counts as zero here — the error
        itself is reported by :meth:`diagnostics` instead of being multiplied
        across every row.
        """
        store, _error = self._load_store()
        if store is None:
            return {}
        return {key: len(entries)
                for key, entries in (store.scopes.get("show") or {}).items()}

    def _expand_stored(self, entries, ctx: dict[str, str]) -> dict[str, str]:
        """Expand ``$VAR`` in store-sourced values, keyed by name.

        Derived values are already absolute (``build_env_context`` builds them
        from the context), so only the stored ones need expanding — and they do,
        because a shared ``env.yaml`` writes ``${DEV}/assets/${SHOW}`` rather than
        one machine's path.
        """
        out: dict[str, str] = {}
        for entry in entries:
            if entry.source == "derived":
                continue
            try:
                out[entry.name] = self.config.expand_value(entry.value, extra=ctx)
            except Exception:
                out[entry.name] = entry.value
        return out

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
        env_counts = self._show_env_counts()
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
                    env_show_count=env_counts.get(row.name, 0),
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
        # The layout contract is two levels (<dev>/projects/<root-name>). A root
        # that shallow yields "/" as $DEV — planning "/cache/<show>" would try to
        # create folders at the filesystem root, so those entries are dropped
        # and validate_project() warns instead of inventing a location.
        dev_root = compute_dev_root(root)
        if dev_root == "/":
            dev_root = ""
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
        if root and compute_dev_root(root) in ("", "/"):
            out.append(DiagnosticRow(
                "warn", "W_DEV",
                f"Cannot derive $DEV from {root}",
                "Expected <dev>/projects/<root-name>; cache/asset/render "
                "folders are skipped for this root.", target=name))
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

        # The show's baseline environment (card C8): seeded in memory now, so the
        # dry run can quote the same number as the real run. A store that cannot
        # be parsed is never rewritten — the project is still created, and the
        # reason shows up in the diagnostics.
        store, store_error = self._load_store()
        env_written = 0
        if store is None:
            diagnostics += (store_error,) if store_error else ()
        else:
            env_written = store.apply_show_skeleton(name)

        if dry_run:
            return ApplySummary(created=tuple(missing),
                                skipped=tuple(p.path for p in plan if p.path and p.exists),
                                diagnostics=diagnostics,
                                env_written=env_written)

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

        if env_written and store is not None:
            try:
                store.save()
            except OSError as exc:
                errors.append(("env.yaml", str(exc)))
                env_written = 0

        return ApplySummary(created=tuple(created),
                            skipped=tuple(p.path for p in plan if p.path and p.exists),
                            errors=tuple(errors), diagnostics=diagnostics,
                            env_written=env_written)

    # -- Shots -------------------------------------------------------------

    def _shot_paths(self, name: str):
        """Return ``(show_path, path_for)`` for the project tree, or ``None``.

        ``path_for(sequence, "")`` answers for the sequence folder itself, which
        is how the plan tells a new sequence from an existing one.
        """
        row = self._find(name)
        if row is None:
            return None
        show_path = os.path.join(row.root, name)

        def path_for(sequence: str, shot: str) -> str:
            if shot:
                return os.path.join(show_path, sequence, shot)
            return os.path.join(show_path, sequence)

        return show_path, path_for

    def sequences(self, name: str) -> list[str]:
        """Sequence folders that already exist for *name* (``[]`` when unknown)."""
        located = self._shot_paths(name)
        if located is None:
            return []
        return _list_dirs(located[0])

    def shots(self, name: str, sequence: str) -> list[str]:
        """Shot folders already inside *sequence* (``[]`` when unknown)."""
        located = self._shot_paths(name)
        if located is None or not sequence:
            return []
        return _list_dirs(os.path.join(located[0], sequence))

    def plan_shots(self, name: str,
                   entries: Sequence[tuple[str, str]]) -> tuple[ShotPlanRow, ...]:
        """Classify an Add Shots batch against the tree on disk (no writes)."""
        located = self._shot_paths(name)
        if located is None:
            return ()
        return classify_shots(entries, located[1], os.path.isdir)

    def add_shots(self, name: str, entries: Sequence[tuple[str, str]],
                  dry_run: bool) -> ApplySummary:
        """Create ``<show>/<seq>/<shot>`` for every row the plan calls new.

        A sequence is only ever created as the parent of a shot (an empty
        sequence folder is noise), an existing shot is skipped rather than
        reported as an error (running the batch twice must be safe), and nothing
        is registered in the database: the folder is an intent, the asset
        library records the fact when something is actually published.
        """
        located = self._shot_paths(name)
        if located is None:
            return ApplySummary(
                errors=((name, "unknown project"),),
                diagnostics=(DiagnosticRow("error", "E_PROJECT",
                                           f"Unknown project: {name}", target=name),),
            )
        show_path, path_for = located
        plan = classify_shots(entries, path_for, os.path.isdir)

        invalid = [row for row in plan if row.blocks]
        if invalid:
            return ApplySummary(
                errors=tuple((f"{r.sequence or '?'}/{r.shot or '?'}", r.message)
                             for r in invalid),
                diagnostics=tuple(
                    DiagnosticRow("error", "E_SHOTNAME",
                                  f"{r.sequence or '?'}/{r.shot or '?'}: {r.message}",
                                  "A shot name is one path segment: no '/', no "
                                  "leading '.', no spaces.", target=r.shot)
                    for r in invalid),
            )

        diagnostics: tuple[DiagnosticRow, ...] = ()
        if not os.path.isdir(show_path):
            diagnostics = (DiagnosticRow(
                "warn", "W_SHOWROOT", f"Project folder is missing: {show_path}",
                "It will be created together with the shots.", target=name),)

        todo = [r.path for r in plan if r.status == SHOT_STATUS_NEW and r.path]
        skipped = [r.path for r in plan
                   if r.status in (SHOT_STATUS_EXISTS, SHOT_STATUS_DUPLICATE) and r.path]
        if dry_run:
            return ApplySummary(created=tuple(todo), skipped=tuple(skipped),
                                diagnostics=diagnostics)

        created: list[str] = []
        errors: list[tuple[str, str]] = []
        for path in todo:
            try:
                os.makedirs(path, exist_ok=True)
                created.append(path)
            except OSError as exc:
                errors.append((path, str(exc)))
        return ApplySummary(created=tuple(created), skipped=tuple(skipped),
                            errors=tuple(errors), diagnostics=diagnostics)

    def rename_shot(self, name: str, sequence: str, shot: str,
                    new_name: str, dry_run: bool) -> ApplySummary:
        """Rename one shot folder — only while nothing has been filed in it.

        Deliberately narrow. An empty shot is a typo to fix; a shot with files in
        it is somebody's work and, past the first publish, a name already written
        into published filenames and into the asset library. "Is it empty?" is
        the whole gate, and it is cheap: empty means nothing was ever published,
        which means there is no asset-library row to go stale.

        A published shot is refused outright rather than half-renamed: the
        folder name can be moved, the name baked into ``shot001_v001.ma`` and
        ``assets.name`` cannot. Fixing a published name is a new shot plus a
        re-publish, not a rename.
        """
        located = self._shot_paths(name)
        if located is None:
            return _rename_error("E_PROJECT", f"Unknown project: {name}",
                                 "Pick a project that exists.", target=name)
        show_path, path_for = located
        old_path = path_for(sequence, shot)
        new_name = (new_name or "").strip()
        new_path = path_for(sequence, new_name) if new_name else ""

        if not os.path.isdir(old_path):
            return _rename_error("E_NO_SHOT", f"Shot folder is gone: {old_path}",
                                 "Refresh the tree — it may have moved.",
                                 target=shot)
        if not shot_is_empty(old_path):
            return _rename_error(
                "E_NOT_EMPTY", f"{sequence}/{shot} already has files in it",
                "Only an untouched shot can be renamed; once work has started "
                "the name is in the files too.", target=shot)

        row = self._find(name)
        publish_path = os.path.join(row.publish_root, name, sequence, shot) \
            if row is not None else ""
        if publish_path and os.path.isdir(publish_path):
            return _rename_error(
                "E_PUBLISHED", f"{sequence}/{shot} already exists on the publish side",
                "Published shots are renamed by publishing under the new name, "
                "not by moving folders.", target=shot)

        problem = shot_name_problem(new_name)
        if problem:
            return _rename_error("E_NAME", f"Invalid name: {problem}",
                                 "One path segment: no '/', no leading '.', no "
                                 "spaces.", target=new_name)
        if new_name == shot:
            return _rename_error("E_SAME", "That is the current name",
                                 "Type a different name.", target=shot)
        if os.path.exists(new_path):
            return _rename_error("E_EXISTS", f"{sequence}/{new_name} already exists",
                                 "Renaming never overwrites an existing shot.",
                                 target=new_name)

        if dry_run:
            return ApplySummary(created=(new_path,))

        try:
            if old_path.lower() == new_path.lower():
                # Case-only rename on a case-insensitive volume: going through a
                # staging name is what actually changes the stored casing.
                staging = old_path + ".renaming"
                os.rename(old_path, staging)
                os.rename(staging, new_path)
            else:
                os.rename(old_path, new_path)
        except OSError as exc:
            return _rename_error("E_RENAME", f"Rename failed: {exc}",
                                 "Check permissions and whether a DCC holds the "
                                 "folder open.", target=shot)
        return ApplySummary(created=(new_path,))

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
            # Never invent a department: an unset context must resolve to an
            # empty DEPARTMENT, or the preview reports a value nobody chose.
            department=department,
            dcc=dcc or (roles[0] if roles else ""),
        )
        return ctx, f"{row.name}/{seq}/{shot}" if seq else row.name

    def env_rows(self) -> list[EnvRow]:
        """One row per variable a launch would inject, for the sample show.

        Derived values first, then whatever ``env.yaml`` puts on top of them: a
        stored row keeps its own ``scope``/``scope_key`` and description, and a
        key that only exists in the store shows up here as a new row (that is how
        a show-scoped ``OCIO`` appears before anything else defines it).
        """
        ctx, sample = self._sample_context()
        if not ctx:
            return []
        store, _error = self._load_store()
        whitelist = self._env_whitelist()
        roles = self._dcc_roles()

        resolved = resolve(
            ctx, store,
            show=ctx.get("SHOW", ""),
            dcc=ctx.get("DCC", ""),
            department=ctx.get("DEPARTMENT", ""),
        )
        expanded = self._expand_stored(resolved, ctx)
        return [
            EnvRow(
                name=entry.name,
                value=expanded.get(entry.name, entry.value),
                scope=entry.source,
                scope_key=entry.scope_key,
                enabled=True,
                description=entry.description or (
                    f"computed at launch for {sample}" if sample
                    else "computed at launch"),
                injected_to=tuple(roles) if entry.name in whitelist else (),
            )
            for entry in resolved
        ]

    def save_env_row(self, row: EnvRow) -> list[DiagnosticRow]:
        """Upsert one override into ``config/env.yaml``.

        Only the ``show`` layer is writable in this version (card C4): the other
        three layers are the same code repeated, and the settings panel always
        has exactly one project in context, so ``show`` is the layer a user can
        mean without being asked.

        Returns:
            Problems worth showing. An empty list means the row was written.

        A store that cannot be parsed is **not** overwritten: an unreadable file
        may hold hand-written overrides, and silently regenerating it would
        delete them without a trace.
        """
        out: list[DiagnosticRow] = []
        name = row.name or ""
        if not name.strip():
            return [DiagnosticRow("error", "E_ENV_NAME", "Variable name is empty.",
                                  "Type a name such as ASSET_ROOT.", target=name)]
        if not NAME_PATTERN.match(name):
            return [DiagnosticRow(
                "error", "E_ENV_NAME", f"Invalid variable name: {name!r}",
                "Letters, digits and underscores; must not start with a digit.",
                target=name)]

        store, error = self._load_store()
        if error is not None:
            return [error]

        ctx, _sample = self._sample_context()
        scope_key = row.scope_key or ctx.get("SHOW", "")
        if not scope_key:
            return [DiagnosticRow(
                "error", "E_ENV_NOSHOW",
                "No project in context, so a show-scoped override has no home.",
                "Select a project in the context bar first.", target=name)]

        whitelist = self._env_whitelist()
        if name not in whitelist and name not in WHITELIST_EXCEPTIONS:
            out.append(DiagnosticRow(
                "warn", "W_WHITELIST",
                f"{name} is not in dcc.yaml: pipeline.env_vars",
                "It is stored, but the DCC layer will drop it at launch.",
                target=name))
        if name in GUARDED_SCOPE_KEYS:
            out.append(DiagnosticRow(
                "warn", "W_GUARDED",
                f"{name} must not diverge between departments",
                "Colour management and timing decide whether two departments' "
                "output can be compared at all.", target=name))

        store.put("show", scope_key, name, row.value,
                  description=row.description, secret=row.secret)
        try:
            store.save()
        except OSError as exc:
            return [DiagnosticRow(
                "error", "E_ENV_WRITE", f"Cannot write {self.env_store_path.name}: {exc}",
                "Check that the config directory is writable.", target=name)]
        return out

    def delete_env_row(self, name: str, scope: str,
                       scope_key: str) -> list[DiagnosticRow]:
        """Read-only for now: no ``env.yaml`` store exists (plan U7)."""
        return [DiagnosticRow(
            "warn", "W_NO_STORE",
            f"Cannot delete {name}: the environment store is not implemented yet",
            "Rows are derived from the launch environment; overrides land in U7.",
            target=name,
        )]

    # -- Undo --------------------------------------------------------------

    def _backup_paths(self) -> list[Path]:
        """Backup copies of the store, oldest → newest.

        ``EnvConfig.save`` writes ``env.yaml.bak.<epoch-ms>`` before replacing
        the file, so the **newest** name is "the store as it was before the last
        write" — that is the one a Revert restores. Millisecond stamps are
        fixed-width, hence a plain name sort is also chronological.
        """
        store = self.env_store_path
        try:
            names = [p for p in store.parent.iterdir()
                     if p.name.startswith(f"{store.name}{BACKUP_SUFFIX}")]
        except OSError:
            return []
        return sorted(names, key=lambda p: p.name)

    def has_env_backup(self) -> bool:
        """True when a Revert has something to restore (drives the button)."""
        return bool(self._backup_paths())

    def revert_env(self) -> list[DiagnosticRow]:
        """Restore ``env.yaml`` from the newest backup.

        The backup is *copied* back rather than consumed: restoring is
        idempotent, and throwing the backup away would make a mis-click
        unrecoverable — the exact failure this button exists to undo.

        Returns:
            Problems worth showing. An empty list means the file was restored
            and the next render will show the pre-edit values.
        """
        backups = self._backup_paths()
        if not backups:
            return [DiagnosticRow(
                "warn", "W_NO_BACKUP", "Nothing to revert to",
                "The first edit creates a backup next to env.yaml.",
                target="env.yaml")]
        latest = backups[-1]
        store = self.env_store_path
        try:
            # Same write discipline as a save: stage then replace, so an
            # interrupted revert cannot leave a half-written store behind.
            tmp = store.with_name(f".{store.name}.tmp")
            shutil.copy2(latest, tmp)
            os.replace(tmp, store)
        except OSError as exc:
            return [DiagnosticRow(
                "error", "E_ENV_REVERT", f"Cannot restore {latest.name}: {exc}",
                "Check that the config directory is writable.", target="env.yaml")]
        return []

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
        """The exact environment a launch would produce, resolved for real.

        The scope keys come from the context the rows *actually* describe (the
        sample show/dcc), not from what the caller asked for: when the caller
        names a show this backend does not know, the rows fall back to a real one
        and an override for the unknown name would be a lie.
        """
        ctx, _sample = self._sample_context(show=show, dcc=dcc, department=department)
        if not ctx:
            return []
        store, _error = self._load_store()
        rows = resolve(
            ctx, store,
            show=ctx.get("SHOW", ""),
            dcc=ctx.get("DCC", ""),
            department=ctx.get("DEPARTMENT", ""),
        )
        expanded = self._expand_stored(rows, ctx)
        return [
            ResolvedRow(
                name=entry.name,
                value=expanded.get(entry.name, entry.value),
                source=entry.source,
                scope_key=entry.scope_key,
                shadowed=entry.shadowed,
            )
            for entry in rows
        ]

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

        _store, store_error = self._load_store()
        if store_error is not None:
            out.append(store_error)
        return out
