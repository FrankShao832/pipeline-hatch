"""The environment a launcher injects into a DCC — one implementation.

Extracted from ``MainWindow._launch_dcc`` (2026-10-25) so the settings preview and
the real launch cannot drift: the launcher calls :func:`build_env_context`, and
any read-only consumer (settings panel, diagnostics, tests) calls the same
function.

Two axes, per ``docs/VOCABULARY.md``:

* ``DEPARTMENT`` / ``PIPELINE_DEPARTMENT`` — the department that owns the work;
* ``DCC`` / ``PIPELINE_DCC`` — the application that opens it.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

_log = logging.getLogger(__name__)

#: ``$DEV`` subdirectories whose per-show folders are created on demand.
DEV_SUBDIRS: tuple[str, ...] = ("cache", "assets", "renders")


def compute_dev_root(root_path: str) -> str:
    """Return ``$DEV`` for a project root (``<dev>/projects/y_pipeline_projects``).

    The layout contract is two levels: ``<dev>/projects/<root-name>``. It is
    implicit — a different depth silently yields a wrong ``$DEV`` — which is why
    the settings diagnostics flag a missing ``$DEV`` rather than trusting it.

    Args:
        root_path: Projects root, e.g. ``/Volumes/Development/projects/y_pipeline_projects``.

    Returns:
        ``<dev>`` path, or ``""`` when *root_path* is empty.
    """
    return os.path.dirname(os.path.dirname(root_path)) if root_path else ""


def build_env_context(
    *,
    root_path: str,
    publish_root_path: str,
    project: str,
    sequence: str,
    shot: str,
    department: str,
    dcc: str,
    user: str | None = None,
) -> dict[str, str]:
    """Build the environment context passed to a DCC launch.

    Keys with an empty value are still returned: the DCC layer filters by the
    ``dcc.yaml`` whitelist, and a missing key there is silently skipped — an
    empty string at least shows up in the settings preview.

    Args:
        root_path: Projects root for the show.
        publish_root_path: Publish root for the show.
        project: Show name.
        sequence: Sequence name.
        shot: Shot name.
        department: Department token (``fx`` / ``comp`` / ...).
        dcc: Application key (``maya`` / ``houdini`` / ``nuke`` / ...).
        user: Username override; defaults to ``$USER``.

    Returns:
        A flat ``{name: value}`` mapping.
    """
    dev_root = compute_dev_root(root_path)

    def under(*parts: str) -> str:
        return os.path.join(dev_root, *parts) if dev_root else ""

    return {
        "DCC": dcc,
        "DEPARTMENT": department,
        "CACHE_ROOT": under("cache", project),
        # Dev data root: every sibling root derives from it
        # ($DEV/{projects,publish,cache,assets,renders,tools}).
        "DEV": dev_root,
        "ASSET_ROOT": under("assets", project),
        "RENDER_ROOT": under("renders", project),
        # Houdini's bundled python has no pyyaml, so publisher.yaml cannot
        # load there — the launcher enables the publisher DB mode via env.
        "PUBLISHER_ENABLE_DATABASE": "true",
        "PROJECT_ROOT": root_path,
        "PUBLISH_ROOT": publish_root_path,
        "SHOW": project,
        "SEQ": sequence,
        "SHOT": shot,
        # New PIPELINE_* naming (primary source for the publisher)
        "PIPELINE_PROJECT": project,
        "PIPELINE_SEQUENCE": sequence,
        "PIPELINE_SHOT": shot,
        "PIPELINE_DEPARTMENT": department,
        "PIPELINE_USER": user or os.environ.get("USER", "artist"),
        "PIPELINE_DCC": dcc,
    }


def store_path_default() -> Path:
    """``<config dir>/env.yaml`` — where the override store lives."""
    from launcher.core.config_manager import config_manager

    return Path(config_manager.config_dir) / "env.yaml"


def resolve_env(
    ctx: dict[str, str],
    store_path: str | Path | None = None,
    expander=None,
) -> tuple[list, dict[str, str]]:
    """The environment a launch really injects: *ctx* with the store on top.

    ``build_env_context`` produces the derived layer (what follows from the
    context). This function layers ``config/env.yaml`` over it, in the scope
    order the whole tool uses, and returns both halves because two different
    readers need different halves:

    * the **launch** needs only the final mapping (a child process sees values);
    * the **settings preview** needs the entries as well, to show which layer
      won and which values it beat (``ResolvedEntry.source`` / ``shadowed``).

    Args:
        ctx: The derived context (``SHOW``/``SEQ``/``DEPARTMENT``/``DCC``/…).
        store_path: Override store. Defaults to ``<config dir>/env.yaml``.
        expander: ``(value, ctx) -> str`` for ``${VAR}`` expansion. Defaults to
            ``ConfigManager.expand_value``, i.e. the same expansion the rest of
            the launcher applies; the file keeps the placeholder, resolution
            expands it (decision D2).

    Returns:
        ``(entries, values)`` where ``values`` is a plain ``{name: value}``
        mapping suitable for ``subprocess.Popen(env=…)``.

    A store that exists but does not parse is **logged and ignored**: a broken
    override file must not stop somebody from opening their DCC. The settings
    panel reports it as ``E_ENV_STORE``, which is where a human will look.
    """
    from launcher.core.env_resolver import resolve
    from launcher.core.env_store import EnvConfig, EnvStoreError

    path = Path(store_path) if store_path is not None else store_path_default()

    store = None
    try:
        store = EnvConfig.load(path)
    except EnvStoreError as exc:
        _log.warning("Ignoring unusable override store %s: %s", path, exc)

    entries = resolve(
        ctx, store,
        show=ctx.get("SHOW", ""),
        dcc=ctx.get("DCC", ""),
        department=ctx.get("DEPARTMENT", ""),
    )

    if expander is None:
        from launcher.core.config_manager import config_manager

        expander = lambda value, context: config_manager.expand_value(  # noqa: E731
            value, extra=context)

    values: dict[str, str] = {}
    for entry in entries:
        if entry.source == "derived":
            values[entry.name] = entry.value
            continue
        try:
            values[entry.name] = expander(entry.value, ctx)
        except Exception:                       # a bad placeholder is not fatal
            values[entry.name] = entry.value
    return entries, values


def merge_env_store(
    ctx: dict[str, str],
    store_path: str | Path | None = None,
    expander=None,
) -> dict[str, str]:
    """Convenience wrapper: just the ``{name: value}`` a launch would inject."""
    return resolve_env(ctx, store_path, expander)[1]
