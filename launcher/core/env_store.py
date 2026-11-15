"""The environment override store — ``config/env.yaml``.

This is the only place where a *hand-authored* environment value lives. The
launcher's derived layer (``launch_env.build_env_context``) computes the values
that follow from the context itself; this store holds the decisions a human
makes on top of it, which is what makes a show's environment reproducible: the
decisions are a file, so they can be reviewed, diffed and reverted.

Layout (D1, 2026-10-29): nested by scope, then by scope key, then by variable
name::

    version: 1
    scopes:
      global:
        "":
          OCIO: {value: "${DEV}/color/aces_cg.ocio"}
      show:
        CyberPunk:
          ASSET_ROOT: {value: "${DEV}/assets2/CyberPunk", description: "…"}
      dcc:
        houdini:
          HOUDINI_PATH: {value: "…"}
      department:
        fx:
          RENDER_ROOT: {value: "…"}

``SCOPES`` is ordered low → high and mirrors ``viewmodels.SCOPE_ORDER`` minus
``derived`` (derived is computed, never stored).

Two behaviours worth knowing before editing this module:

* ``save`` writes the file whole, with its own header comment. Hand-written
  comments inside the file therefore do **not** survive a save — the previous
  bytes are kept in ``env.yaml.bak.<timestamp>`` instead of being preserved
  in place. That is deliberate: one writer, one shape, no comment archaeology.
* Every save is atomic (``.env.yaml.tmp`` then ``os.replace``) and sorted
  (``sort_keys``) so a git diff of the store shows additions and removals
  rather than reorderings.

No Qt, no launcher state: this module knows a path and a mapping, nothing else.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import yaml

#: Bumped when the on-disk shape changes in a way that needs migrating.
STORE_VERSION = 1

#: Low → high. Mirrors ``viewmodels.SCOPE_ORDER`` without ``derived``.
SCOPES: tuple[str, ...] = ("global", "show", "dcc", "department")

#: ``scopes.<scope>`` key used for the scope-less ``global`` layer.
GLOBAL_KEY = ""

HEADER = (
    "# Pipeline Hatch — environment overrides.\n"
    "# Written by the Settings panel; a .bak.<timestamp> copy sits next to this\n"
    "# file after every save. Hand edits are read, but not preserved on save.\n"
)


#: What a brand-new show's environment starts as (card C8).
#:
#: Only the decisions a *project* makes that nothing else can compute: its colour
#: configuration and its frame rate. The path roots (``CACHE_ROOT`` /
#: ``ASSET_ROOT`` / ``RENDER_ROOT`` / ``PROJECT_ROOT`` / ``PUBLISH_ROOT``) are
#: deliberately **absent** even though the plan card listed three of them:
#: :func:`launcher.core.launch_env.build_env_context` already derives them from
#: the launch context, and storing a copy of a computed value creates a second
#: truth that silently wins — the drift this store exists to *expose*, not make.
#:
#: Values use ``${DEV}`` / ``${SHOW}`` and are expanded at resolve time (D2), so
#: one file is true on every machine; a literal ``/Volumes/...`` here would pin
#: the show to one workstation.
SHOW_SKELETON: tuple[tuple[str, str, str], ...] = (
    ("OCIO", "${DEV}/color/aces_cg.ocio",
     "ACES CG colour configuration for this show"),
    ("FPS", "24", "Frame rate the show is authored at"),
)


class EnvStoreError(RuntimeError):
    """The store exists but cannot be trusted (bad YAML, unknown scope, …).

    Raised instead of silently returning an empty store: losing the overrides
    quietly would make a show's environment look derived when it is not.
    """


def _as_text(value: Any) -> str:
    """Coerce a YAML scalar to the string an environment variable would hold."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


@dataclass
class EnvEntry:
    """One stored override."""

    value: str
    description: str = ""
    secret: bool = False

    def is_masked(self, revealed: bool = False) -> bool:
        """True when the value must not be shown as-is."""
        return self.secret and not revealed


@dataclass
class EnvConfig:
    """The whole store: ``scopes[scope][scope_key][name] = EnvEntry``."""

    path: Path
    scopes: dict[str, dict[str, dict[str, EnvEntry]]] = field(default_factory=dict)

    # -- Loading / saving ---------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> "EnvConfig":
        """Read the store.

        A missing file is an **empty store and stays missing on disk** — the
        file appears only once somebody actually writes an override, so a
        freshly cloned repo is not polluted by opening the settings panel.

        Args:
            path: Path of ``env.yaml``.

        Returns:
            The parsed store (empty when the file does not exist).

        Raises:
            EnvStoreError: The file exists but is unreadable or malformed.
        """
        path = Path(path)
        if not path.exists():
            return cls(path=path)
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise EnvStoreError(f"{path.name}: {exc}") from exc
        except OSError as exc:
            raise EnvStoreError(f"{path.name}: {exc}") from exc
        if not isinstance(raw, dict):
            raise EnvStoreError(f"{path.name}: top level must be a mapping")

        scopes: dict[str, dict[str, dict[str, EnvEntry]]] = {}
        for scope, block in (raw.get("scopes") or {}).items():
            if scope not in SCOPES:
                raise EnvStoreError(
                    f"{path.name}: unknown scope {scope!r} "
                    f"(expected one of {', '.join(SCOPES)})")
            if not isinstance(block, dict):
                raise EnvStoreError(f"{path.name}: scopes.{scope} must be a mapping")
            by_key: dict[str, dict[str, EnvEntry]] = {}
            for scope_key, entries in block.items():
                if not isinstance(entries, dict):
                    raise EnvStoreError(
                        f"{path.name}: scopes.{scope}.{scope_key} must be a mapping")
                by_key[_as_text(scope_key)] = {
                    str(name): _entry_from(name, spec)
                    for name, spec in entries.items()
                }
            scopes[scope] = by_key
        return cls(path=path, scopes=scopes)

    def save(self) -> Path | None:
        """Write the store atomically, keeping the previous bytes as a backup.

        Returns:
            Path of the ``.bak`` copy, or ``None`` when there was no file yet.
        """
        text = HEADER + yaml.safe_dump(
            {"version": STORE_VERSION, "scopes": self._serialisable()},
            sort_keys=True,
            default_flow_style=False,
            allow_unicode=True,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)

        backup = None
        if self.path.exists():
            backup = self.path.with_name(
                f"{self.path.name}.bak.{int(time.time() * 1000)}")
            shutil.copy2(self.path, backup)

        tmp = self.path.with_name(f".{self.path.name}.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self.path)
        return backup

    def _serialisable(self) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
        """Plain dicts in a stable order (scope order, then keys)."""
        out: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
        for scope in SCOPES:
            by_key = self.scopes.get(scope)
            if not by_key:
                continue
            out[scope] = {}
            for scope_key in sorted(by_key):
                entries = by_key[scope_key]
                if not entries:
                    continue
                out[scope][scope_key] = {
                    name: _spec(entries[name]) for name in sorted(entries)
                }
        return out

    # -- Reading ------------------------------------------------------------

    def __len__(self) -> int:
        return sum(len(entries)
                   for by_key in self.scopes.values()
                   for entries in by_key.values())

    def get(self, scope: str, scope_key: str, name: str) -> EnvEntry | None:
        """One stored entry, or ``None``."""
        return self.scopes.get(scope, {}).get(scope_key, {}).get(name)

    def layers(self, show: str = "", dcc: str = "",
               department: str = "") -> list[tuple[str, str, dict[str, EnvEntry]]]:
        """The layers that apply to a context, **low → high**, skipped if empty."""
        pairs = (
            ("global", GLOBAL_KEY),
            ("show", show),
            ("dcc", dcc),
            ("department", department),
        )
        out: list[tuple[str, str, dict[str, EnvEntry]]] = []
        for scope, key in pairs:
            entries = self.scopes.get(scope, {}).get(key)
            if entries:
                out.append((scope, key, entries))
        return out

    # -- Writing ------------------------------------------------------------

    def put(self, scope: str, scope_key: str, name: str, value: str,
            description: str = "", secret: bool = False) -> bool:
        """Insert or replace one entry in memory (call :meth:`save` to persist).

        Args:
            scope: One of :data:`SCOPES`.
            scope_key: Project / DCC role / department (``""`` for global).
            name: Variable name.
            value: The value as text.
            description: Optional human note; kept across value edits.
            secret: Marks a value that must be masked in the UI.

        Returns:
            ``True`` when the entry is new, ``False`` when it replaced one.

        Raises:
            EnvStoreError: Unknown scope.
        """
        if scope not in SCOPES:
            raise EnvStoreError(f"unknown scope {scope!r}")
        by_key = self.scopes.setdefault(scope, {}).setdefault(scope_key, {})
        previous = by_key.get(name)
        by_key[name] = EnvEntry(
            value=value,
            description=description or (previous.description if previous else ""),
            secret=secret or (previous.secret if previous else False),
        )
        return previous is None

    def apply_show_skeleton(self, show: str, overwrite: bool = False) -> int:
        """Seed the ``show`` layer with :data:`SHOW_SKELETON`.

        Called when a project is created: the show starts with its two decisions
        already written down, so the environment preview is complete before the
        first edit instead of showing an empty colour slot.

        Args:
            show: Project name (the ``show`` scope key).
            overwrite: Also replace values the show already has. Default
                ``False`` so re-running a repair cannot silently reset an edit
                somebody made on purpose.

        Returns:
            How many entries were written (``0`` when all of them were there).

        Raises:
            EnvStoreError: *show* is empty — a skeleton with no owner would land
                in the ``""`` scope key and leak into every project.
        """
        if not show:
            raise EnvStoreError("apply_show_skeleton: show name is empty")
        written = 0
        for name, value, description in SHOW_SKELETON:
            existing = self.get("show", show, name)
            if existing is not None and not overwrite:
                continue
            self.put("show", show, name, value, description=description)
            written += 1
        return written

    def remove(self, scope: str, scope_key: str, name: str) -> bool:
        """Drop one entry; ``True`` when something was actually there."""
        entries = self.scopes.get(scope, {}).get(scope_key)
        if not entries or name not in entries:
            return False
        del entries[name]
        if not entries:
            self.scopes[scope].pop(scope_key, None)
        if not self.scopes.get(scope):
            self.scopes.pop(scope, None)
        return True

    def __iter__(self) -> Iterator[tuple[str, str, str, EnvEntry]]:
        """``(scope, scope_key, name, entry)`` in scope order, then sorted."""
        for scope in SCOPES:
            for scope_key in sorted(self.scopes.get(scope, {})):
                for name in sorted(self.scopes[scope][scope_key]):
                    yield scope, scope_key, name, self.scopes[scope][scope_key][name]


def _entry_from(name: str, spec: Any) -> EnvEntry:
    """Accept both ``KEY: {value: …}`` and the shorthand ``KEY: …``."""
    if isinstance(spec, dict):
        return EnvEntry(
            value=_as_text(spec.get("value")),
            description=_as_text(spec.get("description")),
            secret=bool(spec.get("secret", False)),
        )
    return EnvEntry(value=_as_text(spec))


def _spec(entry: EnvEntry) -> dict[str, Any]:
    """Serialise one entry, dropping empty optional fields."""
    spec: dict[str, Any] = {"value": entry.value}
    if entry.description:
        spec["description"] = entry.description
    if entry.secret:
        spec["secret"] = True
    return spec
