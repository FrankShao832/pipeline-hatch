"""Department selector behaviour + launch gating (2026-10-25).

The launcher must not assume a department: the selector starts on the
placeholder ``Select your department`` and nothing is loaded or launched until
the artist picks one. The department is the data axis, so "no department" means
"no work folder", not "fall back to fx".
"""

import pytest

from launcher.ui.widgets.department_selector import DepartmentSelectorWidget


@pytest.fixture
def selector(qapp):
    widget = DepartmentSelectorWidget()
    yield widget
    widget.deleteLater()


class TestDepartmentSelector:
    def test_starts_on_the_placeholder(self, selector):
        assert selector.currentText() == "Select your department"
        assert selector.currentIndex() == 0
        assert selector.current_department() == ""

    def test_placeholder_carries_an_empty_value(self, selector):
        assert selector.itemData(0) in (None, "")

    def test_departments_come_from_config(self, selector):
        values = [selector.itemData(i) for i in range(1, selector.count())]
        assert "comp" in values and "fx" in values and "lighting" in values

    def test_choosing_a_department_emits_its_token(self, selector):
        seen = []
        selector.department_changed.connect(seen.append)

        idx = selector.findData("comp")
        assert idx > 0
        selector.setCurrentIndex(idx)

        assert seen == ["comp"]
        assert selector.current_department() == "comp"

    def test_returning_to_the_placeholder_emits_empty(self, selector):
        seen = []
        selector.setCurrentIndex(selector.findData("comp"))
        selector.department_changed.connect(seen.append)

        selector.setCurrentIndex(0)

        assert seen == [""]
        assert selector.current_department() == ""


@pytest.fixture
def window(qapp, monkeypatch):
    monkeypatch.setattr(
        "launcher.ui.widgets.project_tree.ProjectTreeWidget.load_projects",
        lambda self: None,
    )
    from launcher.ui.main_window import MainWindow

    win = MainWindow()
    yield win
    win.close()
    win.deleteLater()


class TestNoDepartment:
    def test_layout_puts_department_left_and_dcc_beside_it(self, window):
        left = window.top_left_layout
        right_widgets = [
            window.top_right_layout.itemAt(i).widget()
            for i in range(window.top_right_layout.count())
        ]

        assert left.itemAt(0).widget() is window.department_menu
        assert left.itemAt(2).widget() is window.role_menu
        assert left.itemAt(1).spacerItem() is not None, "a fixed gap separates them"
        assert window.role_menu not in right_widgets

    def test_no_workdir_is_loaded_without_a_department(self, window, tmp_path, monkeypatch):
        shot = tmp_path / "CyberPunk" / "seq001_city" / "cy_city_0010"
        (shot / "comp").mkdir(parents=True)
        window.root_path = str(tmp_path)
        window.project, window.sequence, window.shot = "CyberPunk", "seq001_city", "cy_city_0010"
        window.department = ""
        messages = []
        monkeypatch.setattr(window, "_show_info", messages.append)

        window._load_files()

        assert window.file_path == ""
        assert messages == [], "browsing without a department must not nag"

    def test_launch_is_blocked_without_a_department(self, window, monkeypatch):
        window.role = "nuke"
        window.department = ""
        messages = []
        monkeypatch.setattr(window, "_show_info", messages.append)
        monkeypatch.setattr(window, "_check_dcc_exists", lambda dcc: True)

        def boom(*args, **kwargs):
            raise AssertionError("must not launch without a department")

        monkeypatch.setattr("launcher.ui.main_window.subprocess", type("S", (), {"Popen": boom}))

        window._launch_dcc()

        assert messages and "department" in messages[0].lower()

    def test_clearing_the_department_clears_the_workdir(self, window, tmp_path):
        shot = tmp_path / "CyberPunk" / "seq001_city" / "cy_city_0010"
        (shot / "comp").mkdir(parents=True)
        window.root_path = str(tmp_path)
        window.project, window.sequence, window.shot = "CyberPunk", "seq001_city", "cy_city_0010"
        window.role = "nuke"

        window._on_department_changed("comp")
        assert window.file_path == str(shot / "comp")

        window._on_department_changed("")
        assert window.file_path == ""
