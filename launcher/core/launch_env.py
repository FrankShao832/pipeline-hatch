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

import os

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
