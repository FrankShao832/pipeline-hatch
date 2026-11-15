"""Tests for override layering (execution card C2).

These pin the one property the whole feature exists for: a value that wins is
named, and the value it beat is still readable. A resolver that silently
overwrote would satisfy every "does it launch" test and still make the preview
lie about where a path came from.
"""

from launcher.core.env_resolver import (
    DERIVED,
    ResolvedEntry,
    overrides_only,
    resolve,
)
from launcher.core.env_store import GLOBAL_KEY, EnvConfig

DERIVED_ENV = {
    "ASSET_ROOT": "/derived/assets/CyberPunk",
    "DEV": "/derived",
    "SHOW": "CyberPunk",
}


def _store(tmp_path):
    return EnvConfig.load(tmp_path / "env.yaml")


def test_no_store_is_pure_derived(tmp_path):
    rows = resolve(DERIVED_ENV)
    assert [row.name for row in rows] == ["ASSET_ROOT", "DEV", "SHOW"]
    assert all(row.source == DERIVED for row in rows)
    assert all(not row.is_shadowed for row in rows)
    assert all(row.source_label == "derived" for row in rows)


def test_a_show_override_wins_and_keeps_the_derived_value(tmp_path):
    store = _store(tmp_path)
    store.put("show", "CyberPunk", "ASSET_ROOT", "/show/assets",
              description="hand-placed")
    rows = {row.name: row for row in resolve(DERIVED_ENV, store, show="CyberPunk")}
    won = rows["ASSET_ROOT"]
    assert won.value == "/show/assets"
    assert won.source == "show"
    assert won.source_label == "show:CyberPunk"
    assert won.shadowed == ((DERIVED, "/derived/assets/CyberPunk"),)
    assert won.description == "hand-placed"


def test_four_layers_leave_a_trail_of_three_losers(tmp_path):
    store = _store(tmp_path)
    store.put("global", GLOBAL_KEY, "ASSET_ROOT", "/global/assets")
    store.put("show", "CyberPunk", "ASSET_ROOT", "/show/assets")
    store.put("dcc", "maya", "ASSET_ROOT", "/dcc/assets")
    store.put("department", "fx", "ASSET_ROOT", "/dept/assets")

    rows = {row.name: row for row in resolve(
        DERIVED_ENV, store, show="CyberPunk", dcc="maya", department="fx")}

    assert rows["ASSET_ROOT"].value == "/dept/assets"
    assert rows["ASSET_ROOT"].source_label == "department:fx"
    assert rows["ASSET_ROOT"].shadowed == (
        (DERIVED, "/derived/assets/CyberPunk"),
        ("global", "/global/assets"),
        ("show", "/show/assets"),
        ("dcc", "/dcc/assets"),
    )
    assert len(rows["ASSET_ROOT"].shadowed) == 4


def test_scope_key_must_match_the_context(tmp_path):
    store = _store(tmp_path)
    store.put("show", "DragonLand", "ASSET_ROOT", "/other/assets")
    store.put("dcc", "houdini", "ASSET_ROOT", "/houdini/assets")
    rows = {row.name: row for row in resolve(
        DERIVED_ENV, store, show="CyberPunk", dcc="maya")}
    assert rows["ASSET_ROOT"].value == "/derived/assets/CyberPunk"
    assert rows["ASSET_ROOT"].source == DERIVED


def test_global_applies_without_a_key(tmp_path):
    store = _store(tmp_path)
    store.put("global", GLOBAL_KEY, "OCIO", "/color/aces_cg.ocio")
    rows = {row.name: row for row in resolve(DERIVED_ENV, store, show="CyberPunk")}
    assert rows["OCIO"].value == "/color/aces_cg.ocio"
    assert rows["OCIO"].source_label == "global"


def test_an_override_for_an_unknown_key_appears_as_a_new_row(tmp_path):
    store = _store(tmp_path)
    store.put("show", "CyberPunk", "OCIO", "/color/aces_cg.ocio")
    rows = {row.name: row for row in resolve(DERIVED_ENV, store, show="CyberPunk")}
    assert set(rows) == {"ASSET_ROOT", "DEV", "SHOW", "OCIO"}
    assert rows["OCIO"].shadowed == ()


def test_rows_are_sorted_by_name(tmp_path):
    store = _store(tmp_path)
    store.put("show", "CyberPunk", "AAA", "1")
    names = [row.name for row in resolve(DERIVED_ENV, store, show="CyberPunk")]
    assert names == sorted(names)


def test_overrides_only_drops_the_computed_rows(tmp_path):
    store = _store(tmp_path)
    store.put("show", "CyberPunk", "ASSET_ROOT", "/show/assets")
    store.put("show", "CyberPunk", "OCIO", "/color/x.ocio")
    rows = resolve(DERIVED_ENV, store, show="CyberPunk")
    assert [row.name for row in overrides_only(rows)] == ["ASSET_ROOT", "OCIO"]


def test_resolved_entry_is_hashable_so_it_can_be_compared():
    a = ResolvedEntry(name="K", value="1")
    b = ResolvedEntry(name="K", value="1")
    assert a == b
    assert {a, b} == {a}


def test_resolve_does_not_mutate_the_derived_dict_or_the_store(tmp_path):
    derived = dict(DERIVED_ENV)
    store = _store(tmp_path)
    store.put("show", "CyberPunk", "ASSET_ROOT", "/show/assets")
    resolve(derived, store, show="CyberPunk")
    assert derived == DERIVED_ENV
    assert store.get("show", "CyberPunk", "ASSET_ROOT").value == "/show/assets"
