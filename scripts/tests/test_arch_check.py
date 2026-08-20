"""Юнит-тесты arch_check (scripts/arch_check.py, docs/08 §4 C1).

Синтетические тест-модули строятся в tmp_path (framework/tests/*.py + pytest.ini),
модульные константы arch_check монкипатчатся на них — реальный framework/ репо не
трогается этими тестами (кроме выделенного теста self-check в конце файла).
"""
from __future__ import annotations

import re
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
    """Изолированный framework/ в tmp_path: framework/pytest.ini + framework/tests/
    (+ test-cases/ и framework/data/recording_builder.py для правила 3 — Б8:
    доказывает, что боевой test-cases/ репозитория не читается монкипатченными
    тестами, см. test_recording_rule_isolated_from_real_test_cases; + framework/steps/
    для правила 4, см. `_steps_dir_of`)."""
    framework = tmp_path / "framework"
    tests_dir = framework / "tests"
    tests_dir.mkdir(parents=True)
    pytest_ini = framework / "pytest.ini"
    pytest_ini.write_text(PYTEST_INI_TEXT, encoding="utf-8")

    steps_dir = framework / "steps"
    steps_dir.mkdir(parents=True)

    cases_dir = tmp_path / "test-cases"
    cases_dir.mkdir(parents=True)
    recording_builder = framework / "data" / "recording_builder.py"
    recording_builder.parent.mkdir(parents=True, exist_ok=True)
    recording_builder.write_text('"""synthetic recording_builder for tests."""\n', encoding="utf-8")

    monkeypatch.setattr(ac, "REPO", tmp_path, raising=True)
    monkeypatch.setattr(ac, "FRAMEWORK", framework, raising=True)
    monkeypatch.setattr(ac, "TESTS_DIR", tests_dir, raising=True)
    monkeypatch.setattr(ac, "STEPS_DIR", steps_dir, raising=True)
    monkeypatch.setattr(ac, "PYTEST_INI", pytest_ini, raising=True)
    monkeypatch.setattr(ac, "CASES_DIR", cases_dir, raising=True)
    monkeypatch.setattr(ac, "RECORDING_BUILDER", recording_builder, raising=True)
    monkeypatch.setattr(ac, "ALLOWLIST", set(), raising=True)
    monkeypatch.setattr(ac, "NEGATIVE_THEN_SETTLE_BASELINE", {}, raising=True)
    return tests_dir


def _write(tests_dir: Path, name: str, content: str) -> Path:
    p = tests_dir / name
    p.write_text(content, encoding="utf-8")
    return p


def _write_case(cases_dir: Path, name: str, content: str) -> Path:
    p = cases_dir / name
    p.write_text(content, encoding="utf-8")
    return p


def _write_rb_consts(recording_builder: Path, consts_body: str) -> None:
    recording_builder.write_text(
        '"""synthetic recording_builder for tests."""\n' + consts_body, encoding="utf-8"
    )


def _rule3_warns(warns: list[str]) -> list[str]:
    """warns-строки правила 3 (см. `run` — всегда с префиксом токена `rule3:`)."""
    return [w for w in warns if w.startswith("rule3:")]


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


# --- Правило 3: CASE-RECORDING-CONSISTENCY (scratchpad/spec-case-recording-check.md v3) ---


def _cases_dir_of(tests_dir: Path) -> Path:
    """test-cases/ синтетического framework/ (см. fw) — `tests_dir` == .../framework/tests."""
    return tests_dir.parent.parent / "test-cases"


def _recording_builder_of(tests_dir: Path) -> Path:
    return tests_dir.parent / "data" / "recording_builder.py"


def _steps_dir_of(tests_dir: Path) -> Path:
    """framework/steps/ синтетического framework/ (см. fw) — `tests_dir` == .../framework/tests."""
    return tests_dir.parent / "steps"


def _write_steps(tests_dir: Path, name: str, content: str) -> Path:
    p = _steps_dir_of(tests_dir) / name
    p.write_text(content, encoding="utf-8")
    return p


def _rule4_warns(warns: list[str]) -> list[str]:
    """warns-строки правила 4 (см. `run` — всегда с префиксом токена `rule4:`)."""
    return [w for w in warns if w.startswith("rule4:")]


def _case_md(case_id: str, automated_by: str, precondition_body: str = "- Синтетическое предусловие.",
             scenario_extra: str = "", extra_sections: str = "") -> str:
    return f'''---
id: {case_id}
title: "Synthetic {case_id}"
area: synthetic
priority: P2
automated_by: "{automated_by}"
---

# {case_id} — synthetic case

## Предусловия
{precondition_body}

## Сценарий (Given-When-Then)
**Given** синтетическое предусловие{scenario_extra}
**When** синтетическое действие
**Then** синтетический результат
{extra_sections}
'''


REPLAY_TEST_HEADER = '''from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
'''


def test_recording_rule_case_without_sections_is_silent(fw):
    """Кейс без заголовков `## Предусловия`/`## Сценарий` -> mentions=∅ -> молчание,
    даже если в теле встречается токен `.mitm` (нет секции, за которую он бы считался)."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-200.md", '''---
id: TC-200
title: "No sections"
automated_by: "framework/tests/test_no_sections.py::test_no_sections"
---

# TC-200 — no scoped sections at all

## Другое
Здесь встречается `listing_basic.mitm`, но это не Предусловия и не Сценарий.
''')
    _write(fw, "test_no_sections.py", REPLAY_TEST_HEADER + '''

@allure.id("TC-200")
@pytest.mark.p0
def test_no_sections():
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule3_warns(warns) == []


def test_recording_rule_narrative_notes_section_not_scanned(fw):
    """Нарратив в «Заметках для автоматизации» НЕ считается mentions — даже когда
    он единственный источник упоминания `.mitm` в файле."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-201.md", _case_md(
        "TC-201", "framework/tests/test_narrative.py::test_narrative",
        precondition_body="- Приложение запущено с чистыми данными.",
        extra_sections='''
## Заметки для автоматизации
- Обсуждается `listing_basic.mitm`, но это цитата/нарратив, не утверждение кейса.
''',
    ))
    _write(fw, "test_narrative.py", REPLAY_TEST_HEADER + '''

@allure.id("TC-201")
@pytest.mark.p0
def test_narrative():
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule3_warns(warns) == []


def test_recording_rule_mitm_token_normalization(fw):
    """Нормализация токенов `.mitm`: голый `.mitm` и склейка отбрасываются/lstrip'ятся
    (device-free проба самой `_case_mentions`, синтетический текст секции)."""
    text = '''## Предусловия
- Голый токен без имени: `.mitm` — шум, отбрасывается.
- Склейка с ведущими точками: `...work_basic.mitm` -> нормализуется в `work_basic.mitm`.
- Ведущий дефис: `-side_panel.mitm` -> нормализуется в `side_panel.mitm`.
- Обычный токен: `plain_recording.mitm`.

## Сценарий (Given-When-Then)
**Given** ничего дополнительного здесь
'''
    mentions, first_line = ac._case_mentions(text, {})
    assert mentions == {"work_basic.mitm", "side_panel.mitm", "plain_recording.mitm"}
    assert first_line == 3  # первая строка с непустым нормализованным токеном


def test_recording_rule_constant_mentions_rb_and_bare(fw):
    """(б) константные mentions: `rb.<CONST>` и голый `<CONST>_FILENAME`, резолвимые
    по framework/data/recording_builder.py."""
    text = '''## Предусловия
- Через алиас: `rb.LISTING_BASIC_FILENAME`.
- Голым именем константы: `TAB_MARKER_FILENAME`.
- Неизвестная константа игнорируется: `rb.UNKNOWN_FILENAME`, `UNKNOWN_OTHER_FILENAME`.

## Сценарий (Given-When-Then)
**Given** н-п
'''
    rb_consts = {"LISTING_BASIC_FILENAME": "listing_basic.mitm", "TAB_MARKER_FILENAME": "tab_markers.mitm"}
    mentions, _first_line = ac._case_mentions(text, rb_consts)
    assert mentions == {"listing_basic.mitm", "tab_markers.mitm"}


def test_recording_rule_multi_argnames_live_example():
    """Обязательный юнит (спека v3, DoD): живой образец мульти-argnames
    `test_rating_listing.py:30-41` (TC-009) — `parametrize("replay,rating,work", ...,
    indirect=["replay"])`, все 5 строк несут один и тот же `rb.LISTING_BASIC_FILENAME`
    позиционно на индексе 0. Реальный REPO/RECORDING_BUILDER (без монкипатча fw)."""
    resolved = ac._resolve_test_function(
        "framework/tests/test_rating_listing.py",
        ["test_rate_work_from_listing_overlay"],
    )
    assert resolved not in (None, ac._PARSE_ERROR)
    fn, tree = resolved
    module_consts = ac._module_string_consts(tree)
    rb_consts = ac._load_recording_builder_consts()
    recordings, unresolved = ac._collect_recordings(fn, module_consts, rb_consts)
    assert unresolved == []
    assert recordings == {"listing_basic.mitm"}


def test_recording_rule_branch_extra_recording_not_named(fw):
    """Ветвь 2: recordings≠∅ И recordings ⊄ mentions -> находка «тест берёт записи,
    кейс их не называет» (класс TC-175 до фикса)."""
    cases_dir = _cases_dir_of(fw)
    recording_builder = _recording_builder_of(fw)
    _write_rb_consts(recording_builder, 'OTHER_LISTING_FILENAME = "other_listing.mitm"\n')
    _write_case(cases_dir, "TC-202.md", _case_md(
        "TC-202", "framework/tests/test_extra.py::test_extra",
        precondition_body="- Открыта replay-запись `listing_basic.mitm`.",
    ))
    _write(fw, "test_extra.py", REPLAY_TEST_HEADER + '''

@allure.id("TC-202")
@pytest.mark.p0
@pytest.mark.replay
@pytest.mark.parametrize("replay", [rb.OTHER_LISTING_FILENAME], indirect=True)
def test_extra(replay):
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    rule3 = _rule3_warns(warns)
    assert len(rule3) == 1
    assert "TC-202" in rule3[0]
    assert "other_listing.mitm" in rule3[0]
    assert "берёт записи" in rule3[0]


def test_recording_rule_branch_missing_recording(fw):
    """Ветвь 3: mentions≠∅ И recordings=∅ И без `@pytest.mark.live` -> находка «кейс
    называет replay-записи, тест replay не берёт» (класс TC-173/TC-176)."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-203.md", _case_md(
        "TC-203", "framework/tests/test_missing.py::test_missing",
        precondition_body="- Открыта replay-запись `listing_basic.mitm`.",
    ))
    _write(fw, "test_missing.py", REPLAY_TEST_HEADER + '''

@allure.id("TC-203")
@pytest.mark.p0
def test_missing():
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    rule3 = _rule3_warns(warns)
    assert len(rule3) == 1
    assert "TC-203" in rule3[0]
    assert "listing_basic.mitm" in rule3[0]
    assert "тест" in rule3[0] and "не берёт" in rule3[0]


def test_recording_rule_branch_live_exception(fw):
    """`@pytest.mark.live` — легальное исключение из ветви 3 (4 живых кейса:
    TC-057/078/082/118): mentions≠∅, recordings=∅, но live -> чисто."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-204.md", _case_md(
        "TC-204", "framework/tests/test_live.py::test_live",
        precondition_body="- Открыта replay-запись `listing_basic.mitm` (справочно).",
    ))
    _write(fw, "test_live.py", REPLAY_TEST_HEADER + '''

@allure.id("TC-204")
@pytest.mark.p0
@pytest.mark.live
def test_live():
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule3_warns(warns) == []


def test_recording_rule_mentions_superset_is_clean(fw):
    """Ветвь 4: recordings ⊆ mentions (в т.ч. mentions — надмножество) -> чисто."""
    cases_dir = _cases_dir_of(fw)
    recording_builder = _recording_builder_of(fw)
    _write_rb_consts(recording_builder, 'LISTING_BASIC_FILENAME = "listing_basic.mitm"\n')
    _write_case(cases_dir, "TC-205.md", _case_md(
        "TC-205", "framework/tests/test_superset.py::test_superset",
        precondition_body=(
            "- Открыта replay-запись `listing_basic.mitm`.\n"
            "- Исторически также упоминается `legacy_extra.mitm` (надмножество)."
        ),
    ))
    _write(fw, "test_superset.py", REPLAY_TEST_HEADER + '''

@allure.id("TC-205")
@pytest.mark.p0
@pytest.mark.replay
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_superset(replay):
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule3_warns(warns) == []


def test_recording_rule_automated_by_unresolvable_with_mentions_is_finding(fw):
    """automated_by не разрешается + mentions≠∅ -> находка «сверка невозможна»."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-206.md", _case_md(
        "TC-206", "framework/tests/test_does_not_exist.py::test_nope",
        precondition_body="- Открыта replay-запись `listing_basic.mitm`.",
    ))
    errors, warns = ac.run()
    assert errors == []
    rule3 = _rule3_warns(warns)
    assert len(rule3) == 1
    assert "TC-206" in rule3[0]
    assert "не разрешается" in rule3[0]


def test_recording_rule_automated_by_unresolvable_without_mentions_is_silent(fw):
    """automated_by не разрешается, но mentions=∅ -> молчание (нечего сверять, Р2:
    шов collectability named-not-covered НЕ аннексируется)."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-207.md", _case_md(
        "TC-207", "framework/tests/test_does_not_exist.py::test_nope",
        precondition_body="- Ни одна replay-запись здесь не упоминается.",
    ))
    errors, warns = ac.run()
    assert errors == []
    assert _rule3_warns(warns) == []


def test_recording_rule_unresolvable_parametrize_is_finding_not_crash(fw):
    """Строка параметризации не кортеж/список/pytest.param (произвольный узел, здесь —
    вызов функции) -> находка «неразрешимая параметризация», прогон НЕ падает (Ф1)."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-208.md", _case_md(
        "TC-208", "framework/tests/test_bad_param.py::test_bad_param",
        precondition_body="- Открыта replay-запись `listing_basic.mitm`.",
    ))
    _write(fw, "test_bad_param.py", REPLAY_TEST_HEADER + '''

def _make_row():
    return ("listing_basic.mitm", "SAVE")


@allure.id("TC-208")
@pytest.mark.p0
@pytest.mark.replay
@pytest.mark.parametrize("replay,rating", [_make_row()], indirect=["replay"])
def test_bad_param(replay, rating):
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    rule3 = _rule3_warns(warns)
    assert len(rule3) == 1
    assert "TC-208" in rule3[0]
    assert "неразрешимая параметризация" in rule3[0]


def test_recording_rule_pytest_param_multi_argnames_resolves_and_arbitrary_row_is_finding(fw):
    """`pytest.param(v0, v1, …, id=…)` резолвится позиционно в мульти-argnames
    (именованные `id`/`marks` игнорируются); произвольный узел строки в ДРУГОЙ
    строке того же parametrize -> находка, не падение (Ф1)."""
    cases_dir = _cases_dir_of(fw)
    recording_builder = _recording_builder_of(fw)
    _write_rb_consts(recording_builder, 'LISTING_BASIC_FILENAME = "listing_basic.mitm"\n')
    _write_case(cases_dir, "TC-209.md", _case_md(
        "TC-209", "framework/tests/test_param_mix.py::test_param_mix",
        precondition_body="- Открыта replay-запись `listing_basic.mitm`.",
    ))
    _write(fw, "test_param_mix.py", REPLAY_TEST_HEADER + '''

ARBITRARY = object()


@allure.id("TC-209")
@pytest.mark.p0
@pytest.mark.replay
@pytest.mark.parametrize(
    "replay,rating",
    [
        pytest.param(rb.LISTING_BASIC_FILENAME, "SAVE", id="ok", marks=pytest.mark.p0),
        ARBITRARY,
    ],
    indirect=["replay"],
)
def test_param_mix(replay, rating):
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    rule3 = _rule3_warns(warns)
    # ARBITRARY (не кортеж/список/pytest.param) делает всю параметризацию неразрешимой —
    # находка одна на кейс (спец. вердикта), но сам факт находки (не исключение) и есть
    # доказательство: pytest.param-строка была успешно разобрана до этой точки, падения нет.
    assert len(rule3) == 1
    assert "TC-209" in rule3[0]
    assert "неразрешимая параметризация" in rule3[0]


def test_recording_rule_pytest_param_multi_argnames_resolves(fw):
    """Ф1, ПОЛОЖИТЕЛЬНАЯ половина (Б-1, критик-вход attempt 2 — мутационный юнит
    ДОСЛОВНО от критика): весь parametrize состоит ТОЛЬКО из `pytest.param(...)`-строк,
    обе резолвятся позиционно на индексе `replay` (0) до одного и того же
    `rb.LISTING_BASIC_FILENAME`, кейс называет эту же запись -> recordings ⊆ mentions,
    чисто. Смешанный тест выше
    (`test_recording_rule_pytest_param_multi_argnames_resolves_and_arbitrary_row_is_finding`)
    эту половину НЕ доказывает: там ARBITRARY-строка делает parametrize неразрешимым
    ЦЕЛИКОМ, unresolved короткозамыкает вердикт до проверки recordings⊆mentions —
    мутация «убрать ветку pytest.param» (никогда не заходить в `if isinstance(row, ast.Call)
    and _decorator_dotted(row) == "pytest.param"`) выживает В НЁМ (ARBITRARY и так даёт
    unresolved независимо от того, обработан ли pytest.param) и УБИВАЕТСЯ ЗДЕСЬ (без этой
    ветки обе `pytest.param`-строки ушли бы в `elif isinstance(row, (ast.Tuple, ast.List))`
    -> False -> "строка параметризации не кортеж/список/pytest.param" -> находка вместо
    чистого вердикта)."""
    cases_dir = _cases_dir_of(fw)
    recording_builder = _recording_builder_of(fw)
    _write_rb_consts(recording_builder, 'LISTING_BASIC_FILENAME = "listing_basic.mitm"\n')
    _write_case(cases_dir, "TC-212.md", _case_md(
        "TC-212", "framework/tests/test_param_only.py::test_param_only",
        precondition_body="- Открыта replay-запись `listing_basic.mitm`.",
    ))
    _write(fw, "test_param_only.py", REPLAY_TEST_HEADER + '''

@allure.id("TC-212")
@pytest.mark.p0
@pytest.mark.replay
@pytest.mark.parametrize(
    "replay,rating",
    [
        pytest.param(rb.LISTING_BASIC_FILENAME, "SAVE", id="save", marks=pytest.mark.p0),
        pytest.param(rb.LISTING_BASIC_FILENAME, "LIKE", id="like"),
    ],
    indirect=["replay"],
)
def test_param_only(replay, rating):
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule3_warns(warns) == []


def test_recording_rule_suffix_header_and_subsection_scoped(fw):
    """Ф2: суффиксный заголовок `## Предусловия — БЛОКЕР (…)` даёт mentions,
    `### `-подсекция НЕ обрывает секцию (мнение внутри неё считается)."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-210.md", '''---
id: TC-210
title: "Suffix header"
automated_by: "framework/tests/test_suffix_header.py::test_suffix_header"
---

# TC-210 — suffix header + subsection

## Предусловия — БЛОКЕР (заведён test_debt-багом в этом же ходе)
- Общий обзор без упоминания записи.
### Детали блокера
- Открыта replay-запись `listing_basic.mitm` — именно здесь, во вложенной подсекции.

## Сценарий (Given-When-Then)
**Given** синтетическое предусловие
**When** синтетическое действие
**Then** синтетический результат
''')
    _write(fw, "test_suffix_header.py", REPLAY_TEST_HEADER + '''

@allure.id("TC-210")
@pytest.mark.p0
def test_suffix_header():
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    rule3 = _rule3_warns(warns)
    # mentions ПОЙМАН (иначе было бы молчание, ветвь 1) -> recordings=∅, не live -> ветвь 3
    assert len(rule3) == 1
    assert "TC-210" in rule3[0]
    assert "listing_basic.mitm" in rule3[0]


def test_recording_rule_allowlist_gates_and_excludes_from_baseline(fw, monkeypatch):
    """ALLOWLIST(kind="recording", ключ ОТ КОРНЯ РЕПО) гасит находку до WARN с хвостом
    и исключает её из бейзлайн-множества (Ф3) — фильтр без хвоста её не видит."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-211.md", _case_md(
        "TC-211", "framework/tests/test_gated.py::test_gated",
        precondition_body="- Открыта replay-запись `listing_basic.mitm`.",
    ))
    _write(fw, "test_gated.py", REPLAY_TEST_HEADER + '''

@allure.id("TC-211")
@pytest.mark.p0
def test_gated():
    assert True
''')
    monkeypatch.setattr(ac, "ALLOWLIST", {("test-cases/TC-211.md", "recording")}, raising=True)
    errors, warns = ac.run()
    assert errors == []
    rule3 = _rule3_warns(warns)
    assert len(rule3) == 1
    assert "[известное исключение — см. ALLOWLIST]" in rule3[0]
    # бейзлайн-фильтр (тот же приём, что test_real_repo_recording_rule_baseline) —
    # ALLOWLIST-погашенные находки в бейзлайн-множество не входят.
    baseline_like = [w for w in rule3 if "[известное исключение" not in w]
    assert baseline_like == []


def test_recording_rule_isolated_from_real_test_cases(fw):
    """Б8: боевой test-cases/ репозитория НЕ читается при подменённом CASES_DIR —
    синтетический test-cases/ (fw) пуст, реальная единственная боевая находка
    правила 3 (TC-176, см. test_real_repo_recording_rule_baseline) не просачивается."""
    errors, warns = ac.run()
    assert errors == []
    assert _rule3_warns(warns) == []
    assert not any("TC-176" in w for w in warns)


def test_recording_rule_cases_dir_only_patch_isolates_from_real_test_cases(tmp_path, monkeypatch):
    """Ф-2 (критик-вход attempt 2, усиление Б8): патчим ТОЛЬКО `CASES_DIR` — REPO/
    FRAMEWORK/TESTS_DIR/RECORDING_BUILDER остаются БОЕВЫМИ (реальный репозиторий, без
    fw). Пустой синтетический test-cases/ доказывает, что обход правила 3 читает
    именно `CASES_DIR` (а не какой-то захардкоженный путь мимо константы) — боевая
    единственная находка (TC-176) не просачивается."""
    empty_cases_dir = tmp_path / "test-cases"
    empty_cases_dir.mkdir()
    monkeypatch.setattr(ac, "CASES_DIR", empty_cases_dir, raising=True)
    _errors, warns = ac.run()
    assert _rule3_warns(warns) == []
    assert not any("TC-176" in w for w in warns)


def test_recording_rule_syntax_error_target_is_silent(fw):
    """Ф-1 (критик-вход attempt 2): automated_by указывает на файл с SyntaxError ->
    `_resolve_test_function` возвращает `_PARSE_ERROR`, правило 3 молчит (не дублирует
    Finding класса "parse", который для ЭТОГО ЖЕ файла уже несут правила 1-2 — файл
    внутри `TESTS_DIR.rglob("test_*.py")`, см. комментарий у `_PARSE_ERROR` про
    остаточную дыру для automated_by ВНЕ этого глоба)."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-215.md", _case_md(
        "TC-215", "framework/tests/test_broken_syntax.py::test_broken_syntax",
        precondition_body="- Открыта replay-запись `listing_basic.mitm`.",
    ))
    _write(fw, "test_broken_syntax.py", "def test_broken_syntax(:\n    pass\n")
    errors, warns = ac.run()
    # Существующий Finding класса "parse" правил 1-2 уже покрывает ЭТОТ файл как ERROR:
    assert any("не удалось разобрать" in e for e in errors)
    assert _rule3_warns(warns) == []


def test_recording_rule_independent_of_missing_tests_dir(fw, monkeypatch):
    """Ф-3 (критик-вход attempt 2): правило 3 — ВТОРАЯ, НЕЗАВИСИМАЯ ветвь обхода
    (докстринг `run`) — TESTS_DIR отсутствует -> errors содержит «не найден» (ветвь
    правил 1-2), но находка правила 3 всё равно получена (automated_by резолвится
    через REPO, не через TESTS_DIR — обе ветви не veto друг друга)."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-213.md", _case_md(
        "TC-213", "framework/tests/test_missing_tests_dir.py::test_missing_tests_dir",
        precondition_body="- Открыта replay-запись `listing_basic.mitm`.",
    ))
    _write(fw, "test_missing_tests_dir.py", REPLAY_TEST_HEADER + '''

@allure.id("TC-213")
@pytest.mark.p0
def test_missing_tests_dir():
    assert True
''')
    # Ломаем TESTS_DIR ПОСЛЕ записи файла теста — automated_by резолвится по REPO,
    # правило 3 TESTS_DIR вообще не читает.
    monkeypatch.setattr(ac, "TESTS_DIR", fw.parent / "no_such_tests_dir", raising=True)
    errors, warns = ac.run()
    assert any("не найден" in e for e in errors)
    rule3 = _rule3_warns(warns)
    assert len(rule3) == 1
    assert "TC-213" in rule3[0]


def test_recording_rule_parametrize_kwargs_form_is_finding(fw):
    """Ф-5 (критик-вход attempt 2, fail-closed решение Lead): `parametrize(argnames=...,
    argvalues=...)` (ТОЛЬКО именованные аргументы, `dec.args` пуст) в корпусе не
    встречается, но тихий пропуск — дыра (не знаем, содержит ли argnames "replay"
    без резолва kwargs, а kwargs сознательно НЕ резолвим) -> находка «неразрешимая
    параметризация», не молчание."""
    cases_dir = _cases_dir_of(fw)
    recording_builder = _recording_builder_of(fw)
    _write_rb_consts(recording_builder, 'LISTING_BASIC_FILENAME = "listing_basic.mitm"\n')
    _write_case(cases_dir, "TC-214.md", _case_md(
        "TC-214", "framework/tests/test_kwargs_param.py::test_kwargs_param",
        precondition_body="- Открыта replay-запись `listing_basic.mitm`.",
    ))
    _write(fw, "test_kwargs_param.py", REPLAY_TEST_HEADER + '''

@allure.id("TC-214")
@pytest.mark.p0
@pytest.mark.replay
@pytest.mark.parametrize(argnames="replay", argvalues=[rb.LISTING_BASIC_FILENAME], indirect=True)
def test_kwargs_param(replay):
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    rule3 = _rule3_warns(warns)
    assert len(rule3) == 1
    assert "TC-214" in rule3[0]
    assert "неразрешимая параметризация" in rule3[0]


# --- Правило 4: NEGATIVE-THEN-WITHOUT-SETTLE (спека D v2, framework/steps/*.py) ---


def test_negative_then_settle_simple_call_is_warn_not_error(fw):
    """Базовый матч `assert not screen.method(...)` -> WARN (rule4:), errors пуст —
    правило WARN-tier, не ERROR-tier (см. докстринг модуля)."""
    _write_steps(fw, "rating_steps.py", '''from __future__ import annotations


def assert_chip_absent(screen, tag):
    assert not screen.chip_visible(tag), f"chip {tag} still visible"
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "chip_visible" in rule4[0]
    assert "wait_absent" in rule4[0]
    assert "settle" in rule4[0]
    assert "без вердикта" in rule4[0]  # не в NEGATIVE_THEN_SETTLE_BASELINE (fw -> {})


def test_negative_then_settle_receiver_constructor_chain_is_matched(fw):
    """Ф1 (критик-вход): регекс слеп к receiver-вызовам конструктора
    (`Screen(driver).method()`), AST — нет. Живой образец формы —
    settings_steps.py:377/rating_steps.py:497 в реальном репо."""
    _write_steps(fw, "rating_steps.py", '''from __future__ import annotations


def assert_chip_absent(driver, tag, timeout=None):
    assert not RatingOverlay(driver).chip_visible(tag, timeout=timeout), (
        f"chip {tag} still visible"
    )
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "chip_visible" in rule4[0]


def test_negative_then_settle_multiline_assert_matched_at_first_line(fw):
    """Многострочный assert (перенос аргументов — живой образец
    settings_steps.py:377) -> находка на СТРОКЕ САМОГО `assert` (node.lineno),
    не на строке закрывающей скобки/сообщения."""
    _write_steps(fw, "settings_steps.py", '''from __future__ import annotations


def assert_dialog_gone(screen, timeout):
    assert not screen.is_present(
        screen.by_text("Clear all ratings?"), timeout=timeout
    ), "dialog still open, expected Cancel to close it"
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "settings_steps.py:5:" in rule4[0]


def test_negative_then_settle_double_receiver_call_chain_matched(fw):
    """Адверсариальный случай: `assert not a().b().is_present()` (двойной вызов в
    цепочке получателя, внешний метод — presence-примитив, матчит предикат) —
    матч идёт по внешнему `.is_present(...)`, получатель (сколь угодно вложенный)
    не важен для матчера. Внешний метод обязан матчить NEGATIVE_THEN_METHOD_PATTERN
    (D2-B1) — `.c(...)` НЕ матчил бы предикат, потому синтетика подобрана иначе,
    чем в исходной версии этого теста."""
    _write_steps(fw, "chain_steps.py", '''from __future__ import annotations


def assert_chained(a):
    assert not a().b().is_present(), "still there"
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "`.is_present(...)`" in rule4[0] or ".is_present(...)" in rule4[0]


def test_negative_then_settle_non_presence_method_not_matched_by_predicate(fw):
    """Критик-вход D2-B1: БЕЗ предиката `assert not Path(...).exists()`/`.issubset()`/
    `.endswith()` матчились бы голым `ast.Call(func=ast.Attribute)` — предикат
    NEGATIVE_THEN_METHOD_PATTERN их исключает (WARN-текст про presence-примитив для
    них бессмыслен)."""
    _write_steps(fw, "fs_steps.py", '''from __future__ import annotations

from pathlib import Path


def assert_no_stale_marker(root, allowed):
    assert not Path(root, "marker").exists(), "stale marker file present"
    assert not allowed.issubset({"a", "b"}), "unexpected subset"
    assert not root.endswith(".tmp"), "unexpected tmp suffix"
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule4_warns(warns) == []


def test_negative_then_settle_bare_name_not_matched(fw):
    """`assert not flag` (голое имя, НЕ вызов) — вне AST-формы правила, не матчится
    (двухшаговая форма — известная, НЕ закрытая дыра, см. докстринг модуля)."""
    _write_steps(fw, "flag_steps.py", '''from __future__ import annotations


def assert_not_flag(flag):
    assert not flag, "flag still set"
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule4_warns(warns) == []


def test_negative_then_settle_two_step_form_is_the_known_gap(fw):
    """Двухшаговая форма (`present = screen.is_visible(...); assert not present`) —
    признанная НЕ закрытая дыра (докстринг модуля): не матчится, это ожидаемо."""
    _write_steps(fw, "two_step_steps.py", '''from __future__ import annotations


def assert_gone(screen):
    present = screen.is_visible()
    assert not present, "still visible"
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule4_warns(warns) == []


def test_negative_then_settle_syntax_error_file_gets_own_warn_not_silence(fw):
    """Критик-вход D2-F2: файл в framework/steps/ с SyntaxError -> правило 4 НЕ
    падает (Ф1) и НЕ молчит — rule 1-2 "parse"-ERROR его не касается (framework/
    tests — их единственный обход, framework/steps/ вне него), тихий пропуск
    оставил бы файл БЕЗ единой находки любого правила модуля. Вместо этого —
    собственная WARN-находка «steps-файл не разобран»."""
    _write_steps(fw, "broken_steps.py", "def assert_broken(:\n    pass\n")
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "broken_steps.py" in rule4[0]
    assert "не разобран" in rule4[0]
    assert "правило 4" in rule4[0]
    # это не "попадание" правила — вердикт из бейзлайна к нему не примешивается:
    assert "без вердикта" not in rule4[0]
    assert "[вердикт" not in rule4[0]


def test_negative_then_settle_baseline_verdict_is_printed(fw, monkeypatch):
    """Попадание с ключом (rel, func_name, method_name) в NEGATIVE_THEN_SETTLE_
    BASELINE (критик-вход D2-F1 — ключ НЕ lineno) несёт вердикт в тексте WARN, а
    не «без вердикта»."""
    _write_steps(fw, "rating_steps.py", '''from __future__ import annotations


def assert_chip_absent(screen, tag):
    assert not screen.chip_visible(tag), f"chip {tag} still visible"
''')
    monkeypatch.setattr(
        ac, "NEGATIVE_THEN_SETTLE_BASELINE",
        {("steps/rating_steps.py", "assert_chip_absent", "chip_visible"): "тестовый вердикт X"},
        raising=True,
    )
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "тестовый вердикт X" in rule4[0]
    assert "без вердикта" not in rule4[0]


def test_negative_then_settle_baseline_key_is_line_independent(fw, monkeypatch):
    """Критик-вход D2-F1 (прямая проверка): вердикт резолвится по (rel, func_name,
    method_name) НЕЗАВИСИМО от строки — сдвиг ассерта на другую строку (лишняя
    пустая строка перед функцией) не отрывает находку от её бейзлайн-записи."""
    _write_steps(fw, "rating_steps.py", '''from __future__ import annotations



def assert_chip_absent(screen, tag):
    assert not screen.chip_visible(tag), f"chip {tag} still visible"
''')
    monkeypatch.setattr(
        ac, "NEGATIVE_THEN_SETTLE_BASELINE",
        {("steps/rating_steps.py", "assert_chip_absent", "chip_visible"): "тестовый вердикт Y"},
        raising=True,
    )
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "тестовый вердикт Y" in rule4[0]


def test_negative_then_settle_screens_and_tests_dirs_out_of_scope(fw):
    """Скоуп правила 4 — ТОЛЬКО framework/steps/*.py (докстринг модуля): та же
    негативная форма в framework/tests/ не матчится этим правилом (может дать
    находку правила 1-2 по совсем другой причине, но не rule4)."""
    _write(fw, "test_uses_bad_pattern.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-900")
@pytest.mark.p0
def test_ok(screen):
    assert not screen.is_visible(), "still visible"
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule4_warns(warns) == []


# --- Самопроверка: реальный framework/ текущего репозитория (не монкипатчено) ---

def test_real_repo_framework_passes():
    """framework/tests/ текущего репозитория проходит чек (с учётом ALLOWLIST test-debt
    в arch_check.py — см. докстринг модуля и финальный отчёт задачи C1)."""
    errors, _warns = ac.run()
    assert errors == [], "\n".join(errors)


def test_real_repo_recording_rule_baseline():
    """Бейзлайн warns правила 3 на реальном репо (спека v3, замер критика прогоном
    прототипа по 205 md — 1 истинная находка): ровно {TC-176} (истинный рецидив
    класса TC-173, см. bugs/BUG-059.md). Дрейф множества id ломает этот тест — это
    и есть детектор рецидива до промоции правила в ERROR (см. докстринг модуля)."""
    _errors, warns = ac.run()
    baseline_ids = set()
    for w in warns:
        if not w.startswith("rule3:") or "[известное исключение" in w:
            continue
        m = re.search(r"(TC-\d+)", w)
        assert m, f"не удалось извлечь id кейса из warn-строки правила 3: {w}"
        baseline_ids.add(m.group(1))
    assert baseline_ids == {"TC-176"}, f"warns правила 3 (полный список): {warns}"


def test_real_repo_negative_then_settle_baseline():
    """Бейзлайн находок правила 4 на реальном репо (спека D v2, критик-раунд D2):
    множество (rel, func_name, method_name) РОВНО равно ключам
    NEGATIVE_THEN_SETTLE_BASELINE (ключ — критик-вход D2-F1, НЕ lineno: строка
    дрейфует за рефакторингом, func_name/method_name — нет). Считаем находки
    ПРЯМО из `run_negative_then_settle_rule()` (Finding.rel/func_name/method_name),
    а не парсингом текста WARN — func_name в тексте WARN не печатается (только
    file:line + method), только в самом Finding. Дрейф множества (новый негативный
    Then без settle в framework/steps/ БЕЗ записи в NEGATIVE_THEN_SETTLE_BASELINE,
    либо переименование/удаление существующего) ломает этот тест — детектор
    рецидива до отдельного решения Lead о промоции правила в ERROR (образец —
    test_real_repo_recording_rule_baseline выше). НЕ утверждаем численный размер
    множества отдельным assert'ом (D2-F3) — он избыточен над сверкой множеств."""
    findings = ac.run_negative_then_settle_rule()
    hits = [f for f in findings if f.rule == "negative_then_settle"]
    parse_findings = [f for f in findings if f.rule == "negative_then_settle_parse"]
    assert parse_findings == [], \
        f"нечитаемые steps-файлы на реальном репо (неожиданно): {[f.message for f in parse_findings]}"
    keys = {(f.rel, f.func_name, f.method_name) for f in hits}
    assert keys == set(ac.NEGATIVE_THEN_SETTLE_BASELINE.keys()), (
        f"множество попаданий rule4 разошлось с NEGATIVE_THEN_SETTLE_BASELINE.\n"
        f"попадания: {sorted(keys)}\nбейзлайн: {sorted(ac.NEGATIVE_THEN_SETTLE_BASELINE.keys())}"
    )

    # Каждая находка обязана дойти до `run()` с вердиктом (не «без вердикта») —
    # сверка, что бейзлайн-гейт в `run()` действительно резолвит эти же ключи.
    _errors, warns = ac.run()
    rule4 = _rule4_warns(warns)
    assert not any("без вердикта" in w for w in rule4), \
        f"находки rule4 без вердикта в NEGATIVE_THEN_SETTLE_BASELINE: {rule4}"
