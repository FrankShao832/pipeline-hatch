"""Label styles shared by the three settings columns.

The three column titles have to read as peers, so the size lives in one constant
instead of three modules: ``Preflight`` had already drifted to 15px while
``Resolved Environment`` and ``Project`` sat at the 12px application default,
which is what a duplicated literal buys you. 18px = 1.5x that common default.
"""

from __future__ import annotations

COLUMN_TITLE_QSS = "font-size: 18px; font-weight: bold;"
