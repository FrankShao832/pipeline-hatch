"""Layering the stored overrides over the derived environment.

``launch_env.build_env_context`` answers "what follows from the context"; this
module answers "what did a human decide on top of that". The two are separate on
purpose: the derived layer is computed and can never be wrong in the sense of
being unauthored, while an override is a decision that must be visible, named
and reversible — which is exactly what the ``shadowed`` chain records.

Order is the one the whole tool uses (``viewmodels.SCOPE_ORDER``), low → high::

    derived  <  global  <  show  <  dcc  <  department

so a department-scope entry beats a show-scope entry, and every loser is kept in
``shadowed`` (low → high) instead of being dropped. Nothing here mutates the
store, touches disk or expands ``${VAR}`` — placeholders are expanded by the
caller that knows the process environment (card D2), and a resolver that did it
here would have to know about ``$DEV`` inference too.
"""

from __future__ import annotations

from dataclasses import dataclass

from launcher.core.env_store import EnvConfig

#: What the winner's source looks like when nothing was overridden.
DERIVED = "derived"


@dataclass(frozen=True)
class ResolvedEntry:
    """One variable after layering, with the trail of who it beat."""

    name: str
    value: str
    source: str = DERIVED
    scope_key: str = ""
    shadowed: tuple[tuple[str, str], ...] = ()      # ((scope, value), …) low → high
    description: str = ""

    @property
    def is_shadowed(self) -> bool:
        """True when a lower layer also defined this key."""
        return bool(self.shadowed)

    @property
    def source_label(self) -> str:
        """``derived`` / ``global`` / ``show:CyberPunk`` — the badge the UI shows."""
        if self.source == DERIVED or not self.scope_key:
            return self.source
        return f"{self.source}:{self.scope_key}"


def resolve(derived: dict[str, str],
            config: EnvConfig | None = None,
            *,
            show: str = "",
            dcc: str = "",
            department: str = "") -> list[ResolvedEntry]:
    """Layer the store's overrides over the derived values.

    Args:
        derived: The computed environment (``build_env_context`` output).
        config: The override store, or ``None`` for the pure derived answer.
        show: Project name, matched against the ``show`` scope key.
        dcc: DCC role, matched against the ``dcc`` scope key.
        department: Department token, matched against the ``department`` scope key.

    Returns:
        One entry per variable, sorted by name, each carrying ``source`` and the
        chain of values it shadowed.
    """
    winners: dict[str, ResolvedEntry] = {
        name: ResolvedEntry(name=name, value=value) for name, value in derived.items()
    }

    for scope, scope_key, entries in (config.layers(
            show=show, dcc=dcc, department=department) if config else []):
        for name, entry in entries.items():
            previous = winners.get(name)
            trail = previous.shadowed if previous else ()
            if previous is not None:
                trail = trail + ((previous.source, previous.value),)
            winners[name] = ResolvedEntry(
                name=name,
                value=entry.value,
                source=scope,
                scope_key=scope_key,
                shadowed=trail,
                description=entry.description,
            )

    return sorted(winners.values(), key=lambda row: row.name)


def overrides_only(entries: list[ResolvedEntry]) -> list[ResolvedEntry]:
    """Entries that came from the store (not derived) — the reviewable set."""
    return [entry for entry in entries if entry.source != DERIVED]
