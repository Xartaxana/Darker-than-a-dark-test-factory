"""Юнит-тесты arch_check (scripts/arch_check.py, docs/08 §4 C1).

Синтетические тест-модули строятся в tmp_path (framework/tests/*.py + pytest.ini),
модульные константы arch_check монкипатчатся на них — реальный framework/ репо не
трогается этими тестами (кроме выделенного теста self-check в конце файла).
"""
from __future__ import annotations

from pathlib import Path

import pytest

import arch_check as ac

PYTEST_INI_TEXT = """[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    p0: smoke
    p1: regression
    p2: extended
    p3: cosmetic
    live: requires live site
    replay: requires replay proxy
    quarantine: unstable, out of gate
"""


@pytest.fixture()
def fw(tmp_path, monkeypatch):
    """Изолированный framework/ в tmp_path: framework/pytest.ini + framework/tests/."""
    framework = tmp_path / "framework"
    tests_dir = framework / "tests"
    tests_dir.mkdir(parents=True)
    pytest_ini = framework / "pytest.ini"
    pytest_ini.write_text(PYTEST_INI_TEXT, encoding="utf-8")

    monkeypatch.setattr(ac, "REPO", tmp_path, raising=True)
    monkeypatch.setattr(ac, "FRAMEWORK", framework, raising=True)
    monkeypatch.setattr(ac, "TESTS_DIR", tests_dir, raising=True)
    monkeypatch.setattr(ac, "PYTEST_INI", pytest_ini, raising=True)
    monkeypatch.setattr(ac, "ALLOWLIST", set(), raising=True)
    return tests_dir


def _write(tests_dir: Path, name: str, content: str) -> Path:
    p = tests_dir / name
    p.write_text(content, encoding="utf-8")
    return p


CLEAN_TEST = '''"""Чистый тест-модуль — только steps + assert, allure.id + маркер есть."""
from __future__ import annotations

import allure
import pytest

from framework.steps import app_steps


@allure.id("TC-001")
@allure.title("Пример чистого теста")
@pytest.mark.p0
def test_clean_example(driver):
    app_steps.wait_ui_ready(driver)
    assert True
'''


def test_clean_file_passes(fw):
    _write(fw, "test_clean.py", CLEAN_TEST)
    errors, warns = ac.run()
    assert errors == []
    assert warns == []


def test_forbidden_import_of_screens_is_error(fw):
    _write(fw, "test_bad_import.py", '''from __future__ import annotations

import allure
import pytest

from framework.screens.library_screen import LibraryScreen


@allure.id("TC-002")
@pytest.mark.p0
def test_uses_screen_directly(driver):
    lib = LibraryScreen(driver)
    assert lib
''')
    errors, _warns = ac.run()
    assert any("запрещённый импорт" in e and "framework.screens.library_screen" in e for e in errors)
    assert any("test_bad_import.py" in e for e in errors)


def test_forbidden_appiumby_import_is_error(fw):
    _write(fw, "test_bad_appium.py", '''from __future__ import annotations

import allure
import pytest
from appium.webdriver.common.appiumby import AppiumBy


@allure.id("TC-003")
@pytest.mark.p0
def test_uses_appiumby(driver):
    assert AppiumBy.ANDROID_UIAUTOMATOR
''')
    errors, _warns = ac.run()
    assert any("appium.webdriver.common.appiumby" in e for e in errors)


def test_locator_factory_call_is_error(fw):
    _write(fw, "test_bad_call.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-004")
@pytest.mark.p0
def test_calls_by_text(screen):
    assert screen.by_text("FAVORITE")
''')
    errors, _warns = ac.run()
    assert any(".by_text(...)" in e for e in errors)


def test_driver_find_element_call_is_error(fw):
    _write(fw, "test_bad_find.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-005")
@pytest.mark.p0
def test_calls_find_element(driver):
    assert driver.find_element("id", "x")
''')
    errors, _warns = ac.run()
    assert any(".find_element(...)" in e for e in errors)


def test_literal_uiselector_string_is_error(fw):
    _write(fw, "test_bad_literal.py", '''from __future__ import annotations

import allure
import pytest

LOCATOR = "new UiSelector().text(\\'x\\')"


@allure.id("TC-006")
@pytest.mark.p0
def test_uses_literal_locator():
    assert LOCATOR
''')
    errors, _warns = ac.run()
    assert any("UiSelector(" in e and "литеральная строка" in e for e in errors)


def test_uiselector_mention_in_docstring_is_not_flagged(fw):
    """Прозаическое упоминание в докстринге — не литеральный локатор в коде."""
    _write(fw, "test_docstring_mention.py", '''"""Этот модуль не должен содержать строк вида UiSelector( — пример из ревью."""
from __future__ import annotations

import allure
import pytest


@allure.id("TC-007")
@pytest.mark.p0
def test_ok():
    """Тоже упоминает UiSelector( в докстринге функции, но это не код."""
    assert True
''')
    errors, _warns = ac.run()
    assert not any("литеральная строка" in e for e in errors)


def test_missing_allure_id_is_error(fw):
    _write(fw, "test_no_id.py", '''from __future__ import annotations

import pytest


@pytest.mark.p0
def test_without_allure_id():
    assert True
''')
    errors, _warns = ac.run()
    assert any("test_without_allure_id" in e and "allure.id" in e for e in errors)


def test_missing_suite_marker_is_error(fw):
    _write(fw, "test_no_marker.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-008")
@pytest.mark.live
def test_without_suite_marker():
    assert True
''')
    errors, _warns = ac.run()
    assert any("test_without_suite_marker" in e and "suite-маркера" in e for e in errors)
    # live — не suite-маркер, сам по себе не закрывает требование
    assert any("p0/p1/p2/p3" in e for e in errors)


def test_parametrize_and_multiple_markers_ok(fw):
    """Параметризованный тест с p1 + live — маркер найден среди нескольких декораторов."""
    _write(fw, "test_parametrized.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-009")
@pytest.mark.p1
@pytest.mark.live
@pytest.mark.parametrize("x", [1, 2])
def test_parametrized(x):
    assert x
''')
    errors, _warns = ac.run()
    assert errors == []


def test_class_based_test_is_scanned(fw):
    _write(fw, "test_in_class.py", '''from __future__ import annotations

import pytest


class TestGroup:
    def test_missing_everything(self):
        assert True
''')
    errors, _warns = ac.run()
    assert any("test_missing_everything" in e and "allure.id" in e for e in errors)
    assert any("test_missing_everything" in e and "suite-маркера" in e for e in errors)


def test_conftest_and_init_are_not_scanned(fw):
    """conftest.py/__init__.py — не тест-модули (python_files=test_*.py), не сканируются,
    даже если бы там были driver/локаторы."""
    _write(fw, "conftest.py", '''from __future__ import annotations

from appium.webdriver.common.appiumby import AppiumBy


def helper():
    return AppiumBy.ANDROID_UIAUTOMATOR
''')
    _write(fw, "__init__.py", "")
    errors, warns = ac.run()
    assert errors == []
    assert warns == []


def test_allowlisted_violation_downgrades_to_warn(fw, monkeypatch):
    monkeypatch.setattr(ac, "ALLOWLIST", {("tests/test_known_bad.py", "locators")}, raising=True)
    _write(fw, "test_known_bad.py", '''from __future__ import annotations

import allure
import pytest

from framework.screens.library_screen import LibraryScreen


@allure.id("TC-010")
@pytest.mark.p0
def test_uses_screen_directly(driver):
    lib = LibraryScreen(driver)
    assert lib
''')
    errors, warns = ac.run()
    assert errors == []
    assert any("известное исключение" in w for w in warns)


def test_load_suite_markers_from_pytest_ini(fw):
    assert ac.load_suite_markers() == {"p0", "p1", "p2", "p3"}


def test_load_suite_markers_missing_ini_falls_back(tmp_path):
    missing = tmp_path / "no_such.ini"
    assert ac.load_suite_markers(missing) == {"p0", "p1", "p2", "p3"}


def test_unparseable_file_reports_parse_error(fw):
    _write(fw, "test_broken.py", "def test_x(:\n    pass\n")
    errors, _warns = ac.run()
    assert any("не удалось разобрать" in e for e in errors)


def test_main_returns_0_on_clean_repo(fw, capsys):
    _write(fw, "test_clean.py", CLEAN_TEST)
    code = ac.main([])
    out = capsys.readouterr().out
    assert code == 0
    assert "ошибок 0" in out


def test_main_returns_1_on_violation(fw, capsys):
    _write(fw, "test_no_id.py", '''from __future__ import annotations

import pytest


@pytest.mark.p0
def test_without_allure_id():
    assert True
''')
    code = ac.main([])
    out = capsys.readouterr().out
    assert code == 1
    assert "[ERROR]" in out


def test_main_no_warns_flag_hides_warnings(fw, monkeypatch, capsys):
    monkeypatch.setattr(ac, "ALLOWLIST", {("tests/test_known_bad.py", "allure_id")}, raising=True)
    _write(fw, "test_known_bad.py", '''from __future__ import annotations

import pytest


@pytest.mark.p0
def test_without_allure_id():
    assert True
''')
    code = ac.main(["--no-warns"])
    out = capsys.readouterr().out
    assert code == 0
    assert "[WARN]" not in out


# --- Самопроверка: реальный framework/ текущего репозитория (не монкипатчено) ---

def test_real_repo_framework_passes():
    """framework/tests/ текущего репозитория проходит чек (с учётом ALLOWLIST test-debt
    в arch_check.py — см. докстринг модуля и финальный отчёт задачи C1)."""
    errors, _warns = ac.run()
    assert errors == [], "\n".join(errors)
