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

#: Keys that an override may *technically* win but must not diverge silently.
#:
#: These are the "must not fork" class: colour management, USD and timing decide
#: whether two departments' output can be compared at all, so a show- or
#: department-scope entry on one of them is an event worth showing on screen,
#: not a row buried in a table. Purely a display concern — nothing here changes
#: how the resolver works.
GUARDED_SCOPE_KEYS: frozenset[str] = frozenset({
    "OCIO", "ACES_CONFIG", "OCIO_CONFIG", "OCIO_PATH",
    "USD_VERSION", "PXR_VERSION", "FPS", "COLORSPACE",
})


def scope_rank(scope: str) -> int:
    """Return the precedence rank of a scope name (lower wins)."""
    try:
        return SCOPE_ORDER.index(scope)
    except ValueError:
        return len(SCOPE_ORDER)


@dataclass(frozen=True)
class SettingsContext:
    """What the settings window is looking at: one launch context.

    Snapshotted once from the main window when the settings window opens — the
    main window stays the owner of the real launch context; this is a copy for
    editing and checking.

    ``seq`` / ``shot`` are display-only for now: the override chain does not
    have seq/shot layers yet, so they only tell the user which shot the numbers
    refer to.
    """

    project: str = ""
    seq: str = ""
    shot: str = ""
    dcc: str = ""
    department: str = ""

    @property
    def is_empty(self) -> bool:
        """True when nothing was supplied (no project, DCC or department)."""
        return not (self.project or self.dcc or self.department)

    def summary(self) -> str:
        """``project · department · dcc`` — the one-line provenance string."""
        return " · ".join(part for part in (self.project, self.department, self.dcc) if part)

    def breadcrumb(self) -> str:
        """``project ▸ seq/shot`` — what a launch would open."""
        text = self.project or "(no project)"
        if self.seq or self.shot:
            text += f" ▸ {self.seq or '?'}/{self.shot or '?'}"
        return text


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
    #: Show-scope overrides the creation seeds (``env.yaml``). On a dry run this
    #: is what *would* be written — the plan preview and the real run therefore
    #: quote the same number.
    env_written: int = 0

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
    scope_key: str = ""             # show name / dcc role / department ("" for derived)
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

    # -- Undo ---------------------------------------------------------------
    # Every write keeps the previous bytes as a backup, so the last write can
    # always be taken back without asking the user to remember the old value.
    def has_env_backup(self) -> bool:
        ...

    def revert_env(self) -> list[DiagnosticRow]:
        ...

    def resolved(self, show: str, dcc: str,
                 department: str) -> list[ResolvedRow]:
        ...

    # -- Selection vocabularies -------------------------------------------
    # The preview needs the candidates for its pickers, and the UI is not
    # allowed to read dcc.yaml / the department vocabulary itself.
    def dcc_roles(self) -> tuple[str, ...]:
        ...

    def departments(self) -> tuple[str, ...]:
        ...

    def diagnostics(self) -> list[DiagnosticRow]:
        ...
