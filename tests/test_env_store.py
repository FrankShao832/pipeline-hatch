"""Tests for the environment override store (execution card C1).

The store decides what a show's environment *is* beyond the derived defaults, so
these tests pin the properties that make it reviewable: a missing file stays
missing, an unreadable file fails loudly instead of looking empty, saves are
sorted (stable diffs) and atomic, and the previous bytes are recoverable.
"""

import pytest

from launcher.core.env_store import (
    GLOBAL_KEY,
    SCOPES,
    EnvConfig,
    EnvStoreError,
)


def _write(path, text):
    """Write a fixture store, creating its parent directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_file_is_an_empty_store_and_stays_missing(tmp_path):
    path = tmp_path / "env.yaml"
    config = EnvConfig.load(path)
    assert len(config) == 0
    assert list(config) == []
    # Nothing is created by merely looking: a fresh clone stays clean.
    assert not path.exists()


def test_put_then_save_round_trips(tmp_path):
    path = tmp_path / "env.yaml"
    config = EnvConfig.load(path)
    assert config.put("show", "CyberPunk", "ASSET_ROOT", "/x/assets",
                      description="show-specific") is True
    config.save()

    again = EnvConfig.load(path)
    entry = again.get("show", "CyberPunk", "ASSET_ROOT")
    assert entry is not None
    assert entry.value == "/x/assets"
    assert entry.description == "show-specific"


def test_second_put_reports_an_update_and_keeps_the_description(tmp_path):
    config = EnvConfig.load(tmp_path / "env.yaml")
    config.put("show", "CyberPunk", "OCIO", "old.ocio", description="why it forked")
    assert config.put("show", "CyberPunk", "OCIO", "new.ocio") is False
    entry = config.get("show", "CyberPunk", "OCIO")
    assert entry.value == "new.ocio"
    assert entry.description == "why it forked"


def test_first_save_has_no_backup_and_the_second_does(tmp_path):
    path = tmp_path / "env.yaml"
    config = EnvConfig.load(path)
    config.put("show", "S", "K", "one")
    assert config.save() is None                       # nothing existed to keep

    config.put("show", "S", "K", "two")
    backup = config.save()
    assert backup is not None and backup.exists()
    assert backup.name.startswith("env.yaml.bak.")
    # The backup is a real store, not a byte copy we cannot parse.
    assert EnvConfig.load(backup).get("show", "S", "K").value == "one"
    assert EnvConfig.load(path).get("show", "S", "K").value == "two"


def test_saves_are_sorted_so_a_diff_shows_changes_not_reorderings(tmp_path):
    path = tmp_path / "env.yaml"
    config = EnvConfig.load(path)
    config.put("show", "Zed", "ZZZ_LAST", "1")
    config.put("show", "Zed", "AAA_FIRST", "2")
    config.put("show", "Alpha", "MID", "3")
    config.save()
    text = path.read_text(encoding="utf-8")
    assert text.index("AAA_FIRST") < text.index("ZZZ_LAST")
    assert text.index("Alpha") < text.index("Zed")


def test_save_creates_the_parent_directory(tmp_path):
    path = tmp_path / "config" / "env.yaml"
    config = EnvConfig.load(path)
    config.put("global", GLOBAL_KEY, "OCIO", "x")
    config.save()
    assert path.exists()


def test_corrupt_yaml_raises_instead_of_looking_empty(tmp_path):
    path = _write(tmp_path / "env.yaml", "scopes: [unclosed\n")
    with pytest.raises(EnvStoreError):
        EnvConfig.load(path)


def test_non_mapping_top_level_raises(tmp_path):
    path = _write(tmp_path / "env.yaml", "- a\n- b\n")
    with pytest.raises(EnvStoreError):
        EnvConfig.load(path)


def test_unknown_scope_raises(tmp_path):
    path = _write(tmp_path / "env.yaml",
                  "scopes:\n  shot:\n    s010:\n      K: {value: '1'}\n")
    with pytest.raises(EnvStoreError):
        EnvConfig.load(path)


def test_every_scope_is_accepted(tmp_path):
    path = tmp_path / "env.yaml"
    config = EnvConfig.load(path)
    for scope in SCOPES:
        config.put(scope, "key" if scope != "global" else GLOBAL_KEY,
                   f"{scope.upper()}_VAR", scope)
    config.save()
    assert len(EnvConfig.load(path)) == len(SCOPES)


def test_put_with_an_unknown_scope_raises(tmp_path):
    config = EnvConfig.load(tmp_path / "env.yaml")
    with pytest.raises(EnvStoreError):
        config.put("shot", "s010", "K", "1")


def test_layers_run_low_to_high_and_skip_empty_layers(tmp_path):
    config = EnvConfig.load(tmp_path / "env.yaml")
    config.put("department", "fx", "K", "department")
    config.put("global", GLOBAL_KEY, "K", "global")
    config.put("show", "CyberPunk", "K", "show")
    layers = config.layers(show="CyberPunk", dcc="maya", department="fx")
    assert [scope for scope, _key, _entries in layers] == [
        "global", "show", "department",
    ]


def test_layers_ignore_other_scope_keys(tmp_path):
    config = EnvConfig.load(tmp_path / "env.yaml")
    config.put("show", "OtherShow", "K", "1")
    config.put("dcc", "houdini", "K", "2")
    assert config.layers(show="CyberPunk", dcc="maya") == []


def test_shorthand_scalar_is_accepted(tmp_path):
    path = _write(tmp_path / "env.yaml",
                  "scopes:\n  show:\n    S:\n      K: plain-value\n")
    entry = EnvConfig.load(path).get("show", "S", "K")
    assert entry.value == "plain-value"
    assert entry.description == ""


def test_booleans_and_floats_become_environment_text(tmp_path):
    path = _write(
        tmp_path / "env.yaml",
        "scopes:\n  show:\n    S:\n"
        "      FLAG: {value: true}\n"
        "      FPS: {value: 24.0}\n"
        "      NOTHING: {value: null}\n",
    )
    config = EnvConfig.load(path)
    assert config.get("show", "S", "FLAG").value == "true"
    assert config.get("show", "S", "FPS").value == "24.0"
    assert config.get("show", "S", "NOTHING").value == ""


def test_secret_is_masked_until_revealed(tmp_path):
    config = EnvConfig.load(tmp_path / "env.yaml")
    config.put("show", "S", "TOKEN", "abc", secret=True)
    entry = config.get("show", "S", "TOKEN")
    assert entry.is_masked() is True
    assert entry.is_masked(revealed=True) is False


def test_remove_takes_the_empty_parents_with_it(tmp_path):
    config = EnvConfig.load(tmp_path / "env.yaml")
    config.put("show", "S", "K", "1")
    assert config.remove("show", "S", "K") is True
    assert config.remove("show", "S", "K") is False
    assert len(config) == 0
    assert config.scopes == {}


def test_iteration_order_is_scope_then_key_then_name(tmp_path):
    config = EnvConfig.load(tmp_path / "env.yaml")
    config.put("department", "fx", "K", "1")
    config.put("global", GLOBAL_KEY, "K", "1")
    config.put("show", "Zed", "B", "1")
    config.put("show", "Zed", "A", "1")
    config.put("show", "Alpha", "A", "1")
    assert [(scope, key, name) for scope, key, name, _e in config] == [
        ("global", "", "K"),
        ("show", "Alpha", "A"),
        ("show", "Zed", "A"),
        ("show", "Zed", "B"),
        ("department", "fx", "K"),
    ]


def test_two_entry_shapes_load_and_save_identically(tmp_path):
    """``KEY: value`` and ``KEY: {value: value}`` must not fork the file format."""
    shorthand = EnvConfig.load(_write(
        tmp_path / "a" / "env.yaml",
        "scopes:\n  show:\n    S:\n      K: v\n"))
    explicit = EnvConfig.load(_write(
        tmp_path / "b" / "env.yaml",
        "scopes:\n  show:\n    S:\n      K: {value: v}\n"))
    assert shorthand.get("show", "S", "K") == explicit.get("show", "S", "K")

    shorthand.save()
    explicit.save()

    def body(path):
        return path.read_text(encoding="utf-8").split("scopes:", 1)[1]

    assert body(tmp_path / "a" / "env.yaml") == body(tmp_path / "b" / "env.yaml")


# -- Card C8: the show skeleton -------------------------------------------

from launcher.core.env_store import SHOW_SKELETON  # noqa: E402


def test_show_skeleton_holds_only_what_nothing_else_computes():
    """The roots are derived at launch; storing them would fork the truth.

    Pinning the *names* keeps a future 'let us also seed ASSET_ROOT' out of the
    file: ``build_env_context`` already owns those, and an override would win
    over it without anybody editing that layer.
    """
    names = {name for name, _value, _description in SHOW_SKELETON}
    assert names == {"OCIO", "FPS"}
    assert not names & {"CACHE_ROOT", "ASSET_ROOT", "RENDER_ROOT",
                        "PROJECT_ROOT", "PUBLISH_ROOT", "SHOW"}


def test_show_skeleton_values_are_machine_independent():
    """Bottom line #6 / D2: ``${DEV}`` and ``${SHOW}``, never a real path."""
    for _name, value, _description in SHOW_SKELETON:
        assert "/Volumes/" not in value
        assert not value.startswith("/")


def test_apply_show_skeleton_seeds_the_show_layer(tmp_path):
    path = tmp_path / "env.yaml"
    config = EnvConfig.load(path)

    assert config.apply_show_skeleton("NewShow") == len(SHOW_SKELETON)
    config.save()

    stored = EnvConfig.load(path)
    assert stored.get("show", "NewShow", "OCIO").value == "${DEV}/color/aces_cg.ocio"
    assert stored.get("show", "NewShow", "FPS").value == "24"
    # The literal placeholder survives the round trip: expansion happens at
    # resolve time, so the file stays readable on any machine.
    assert "${DEV}" in path.read_text(encoding="utf-8")
    # Nothing lands at global or with an empty scope key.
    assert list(stored.scopes) == ["show"]


def test_apply_show_skeleton_is_idempotent(tmp_path):
    config = EnvConfig.load(tmp_path / "env.yaml")

    config.apply_show_skeleton("NewShow")

    assert config.apply_show_skeleton("NewShow") == 0
    assert len(config) == len(SHOW_SKELETON)


def test_apply_show_skeleton_keeps_a_deliberate_edit(tmp_path):
    config = EnvConfig.load(tmp_path / "env.yaml")
    config.put("show", "NewShow", "FPS", "25", description="PAL show")

    assert config.apply_show_skeleton("NewShow") == 1     # only OCIO was missing
    assert config.get("show", "NewShow", "FPS").value == "25"


def test_apply_show_skeleton_can_overwrite_on_request(tmp_path):
    config = EnvConfig.load(tmp_path / "env.yaml")
    config.put("show", "NewShow", "FPS", "25")

    assert config.apply_show_skeleton("NewShow", overwrite=True) == len(SHOW_SKELETON)
    assert config.get("show", "NewShow", "FPS").value == "24"


def test_apply_show_skeleton_refuses_an_empty_show(tmp_path):
    config = EnvConfig.load(tmp_path / "env.yaml")

    with pytest.raises(EnvStoreError):
        config.apply_show_skeleton("")
