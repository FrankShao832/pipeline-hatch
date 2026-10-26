"""View-model contract between the settings UI and its data sources.

Iron rule (plan v1.1 §1 G1): the UI layer may import **only** this module for
data shapes. Nothing here may depend on a GUI toolkit, a YAML reader, an ORM or
the core/database packages — all of that belongs behind ``SettingsDataSource``.

Backends convert their own objects (ORM rows, EnvVar, Diagnostic, ...) into these
frozen dataclasses. UI never sees a dict or an ORM instance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

# Canonical orders — UI sorting and badge rendering depend on them.
SCOPE_ORDER: tuple[str, ...] = ("derived", "global", "show", "dcc", "department")
SCAFFOLD_STATES: tuple[str, ...] = ("complete", "missing", "n/a")
LEVELS: tuple[str, ...] = ("error", "warn", "info")


def scope_rank(scope: str) -> int:
    """Return the precedence rank of a scope name (lower wins)."""
    try:
        return SCOPE_ORDER.index(scope)
    except ValueError:
        return len(SCOPE_ORDER)


@dataclass(frozen=True)
class DiagnosticRow:
    """One problem surfaced to the user."""

    level: str                      # "error" | "warn" | "info"
    code: str                       # E_NAME / W_PATH / ...
    message: str
    hint: str = ""
    target: str = ""                # variable name or project name, for jump-to

    def sort_key(self) -> tuple[int, str, str]:
        """Sort errors before warnings before info, then by code."""
        rank = LEVELS.index(self.level) if self.level in LEVELS else len(LEVELS)
        return (rank, self.code, self.target)


@dataclass(frozen=True)
class ProjectRow:
    """One project as shown in the Projects table."""

    name: str
    root: str
    publish_root: str
    seqs: int = 0
    shots: int = 0
    env_show_count: int = 0         # D-F: enabled vars with scope=show & scope_key==name
    scaffold_state: str = "n/a"     # "complete" | "missing" | "n/a"  (D-G)
    scaffold_missing: int = 0       # required dirs only
    enabled: bool = True
    source: str = "db"              # "db" | "yaml"


@dataclass(frozen=True)
class ScaffoldPlanRow:
    """One directory in the New Project / Repair plan preview."""

    path: str
    group: str                      # "required" | "sequences" | "dev_root"
    required: bool = False
    exists: bool = False


@dataclass(frozen=True)
class ApplySummary:
    """Result of creating or repairing a workspace skeleton."""

    created: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    errors: tuple[tuple[str, str], ...] = ()        # (path, reason)
    diagnostics: tuple[DiagnosticRow, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors and not any(d.level == "error" for d in self.diagnostics)

    def counts(self) -> tuple[int, int, int]:
        return (len(self.created), len(self.skipped), len(self.errors))


@dataclass(frozen=True)
class EnvRow:
    """One environment variable entry as shown in the Environment page."""

    name: str
    value: str
    scope: str                      # SCOPE_ORDER member
    scope_key: str = ""             # show / dcc role / department
    enabled: bool = True
    secret: bool = False
    description: str = ""
    # DCC roles that actually receive this key. Empty tuple = not in the
    # dcc.yaml whitelist (rendered as "not in whitelist"; JOB is the D-H exception).
    injected_to: tuple[str, ...] = ()

    def is_masked(self, revealed: bool = False) -> bool:
        return self.secret and not revealed


@dataclass(frozen=True)
class ResolvedRow:
    """One line of the Resolved Environment preview."""

    name: str
    value: str
    source: str                     # SCOPE_ORDER member that won
    shadowed: tuple[tuple[str, str], ...] = ()      # ((scope, value), ...) low→high

    @property
    def is_shadowed(self) -> bool:
        return bool(self.shadowed)


@runtime_checkable
class SettingsDataSource(Protocol):
    """Everything the settings UI needs. Implementations: Fake* and Real*."""

    # -- Projects ---------------------------------------------------------
    def projects(self) -> list[ProjectRow]:
        ...

    def scaffold_plan(self, name: str) -> list[ScaffoldPlanRow]:
        ...

    def repair(self, name: str, dry_run: bool) -> ApplySummary:
        ...

    def validate_project(self, name: str, root: str,
                         publish_root: str) -> list[DiagnosticRow]:
        ...

    def create_project(self, name: str, root: str, publish_root: str,
                       options: dict[str, Any], dry_run: bool) -> ApplySummary:
        ...

    # -- Environment ------------------------------------------------------
    def env_rows(self) -> list[EnvRow]:
        ...

    def save_env_row(self, row: EnvRow) -> list[DiagnosticRow]:
        ...

    def delete_env_row(self, name: str, scope: str,
                       scope_key: str) -> list[DiagnosticRow]:
        ...

    def resolved(self, show: str, dcc: str,
                 department: str) -> list[ResolvedRow]:
        ...

    def diagnostics(self) -> list[DiagnosticRow]:
        ...
