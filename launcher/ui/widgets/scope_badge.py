"""Scope badges for the settings UI (plan D-E: small palette, no theme system).

Five scopes, four semantic colours plus violet for the rare ``department`` layer.
Rendering is plain HTML/strings — no custom painting, no dependency on a design
token module (the launcher does not have one yet).
"""

from __future__ import annotations

BADGE_COLORS: dict[str, str] = {
    "derived": "#8b94a3",      # grey  — computed by the launcher itself
    "global": "#3b82f6",       # blue  — machine/studio wide
    "show": "#10b981",         # green — per production
    "dcc": "#f59e0b",          # amber — per application
    "department": "#a855f7",   # violet — per department
}
_FALLBACK_COLOR = "#8b94a3"


def badge_color(scope: str) -> str:
    """Return the hex colour for a scope name."""
    return BADGE_COLORS.get(scope, _FALLBACK_COLOR)


def badge_text(scope: str, key: str = "") -> str:
    """Return the plain-text badge, e.g. ``[show:CyberPunk]``."""
    return f"[{scope}:{key}]" if key else f"[{scope}]"


def badge_html(scope: str, key: str = "") -> str:
    """Return the HTML badge, e.g. ``<span …>[global]</span>``."""
    return (
        f'<span style="color:{badge_color(scope)};'
        f' font-size:11px;">{badge_text(scope, key)}</span>'
    )


def badge_qss(scope: str) -> str:
    """Return a stylesheet fragment colouring a widget like its scope badge."""
    return f"color: {badge_color(scope)};"
