"""Юнит-тесты arch_check (scripts/arch_check.py, docs/08 §4 C1).

Синтетические тест-модули строятся в tmp_path (framework/tests/*.py + pytest.ini),
модульные константы arch_check монкипатчатся на них — реальный framework/ репо не
трогается этими тестами (кроме выделенного теста self-check в конце файла).
"""
from __future__ import annotations

import ast
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


def _rule5_warns(warns: list[str]) -> list[str]:
    """warns-строки правила 5 — только ALLOWLIST-гашённые (rule5 — ERROR с Р1,
    критик-раунд round2; см. `_rule5_errors` для основного канала)."""
    return [w for w in warns if w.startswith("rule5:")]


def _rule5_errors(errors: list[str]) -> list[str]:
    """errors-строки правила 5 (rule5 — ERROR с Р1, критик-раунд round2, канал
    `rule5:` в тексте самого ERROR)."""
    return [e for e in errors if e.startswith("rule5:")]


def _rule6_warns(warns: list[str]) -> list[str]:
    """warns-строки правила 6, НАПРАВЛЕНИЕ Б (allure_id_orphan) — остаётся WARN
    (Р1, критик-раунд round2); направление А (automated_by_orphan) — ERROR,
    см. `_rule6_case_side_errors`. Оба канала в тексте несут префикс `rule6:`,
    но т.к. направление А больше не попадает в warns (кроме ALLOWLIST-гашения),
    этот фильтр на практике видит только направление Б."""
    return [w for w in warns if w.startswith("rule6:")]


def _rule6_case_side_errors(errors: list[str]) -> list[str]:
    """errors-строки правила 6, НАПРАВЛЕНИЕ А (automated_by_orphan) — ERROR
    с Р1 (критик-раунд round2), канал `rule6:` в тексте самого ERROR."""
    return [e for e in errors if e.startswith("rule6:")]


def _cases_read_warns(warns: list[str]) -> list[str]:
    """warns-строки канала `cases:` — нечитаемый файл test-cases/ (критик-раунд
    round3, Б1; см. `load_case_frontmatter`). ОПРЕДЕЛЁН ЗДЕСЬ, рядом с
    остальными канальными фильтрами, а не в хвосте файла (критик-раунд round3
    attempt 2, Б2: у пяти соседних каналов real-repo пин есть, у шестого не
    было — хелпер жил НИЖЕ всех `test_real_repo_*` и физически ими не
    звался)."""
    return [w for w in warns if w.startswith("cases:")]


def _case_md_min(case_id: str, priority: str = "P2", automated_by: str = "",
                  title: str | None = None, status: str | None = None) -> str:
    """Минимальный синтетический кейс для правил 5/6 (frontmatter id/priority/
    automated_by, нейтральное тело — без токенов `.mitm`, чтобы правило 3 на этих
    кейсах молчало, ветвь 1 "mentions=пусто"). `priority` вставляется СЫРЫМ (без
    кавычек в f-строке) — позволяет проверять малформед/пустые значения.

    `status` (Б2 критик-раунда round3) вставляется строкой ТОЛЬКО когда передан:
    дефолт `None` = кейс БЕЗ `status:` вовсе — прежнее поведение всех уже
    написанных тестов файла (правила 5/6-А по такому кейсу ГОВОРЯТ: неизвестный
    статус трактуется как рабочий, fail-closed)."""
    title = title or f"Synthetic {case_id}"
    status_line = f"status: {status}\n" if status is not None else ""
    return f'''---
id: {case_id}
title: "{title}"
area: synthetic
priority: {priority}
{status_line}automated_by: "{automated_by}"
---

# {case_id} — synthetic case

## Предусловия
- Нет специальных предусловий (синтетический кейс правил 5/6).

## Сценарий (Given-When-Then)
**Given** синтетическое предусловие
**When** синтетическое действие
**Then** синтетический результат
'''


def _case_md(case_id: str, automated_by: str, precondition_body: str = "- Синтетическое предусловие.",
             scenario_extra: str = "", extra_sections: str = "") -> str:
    """`priority: P0` — синхронизировано с `@pytest.mark.p0`, используемым ВСЕМИ
    синтетическими тест-функциями правила 3 в этом файле (критик-раунд round2:
    правило 5 промотировано до ERROR, Р1 — до этого хода расхождение `P2` vs
    `p0` было безвредным WARN-шумом ЧУЖОГО правила, теперь роняет `errors ==
    []` во ВСЕХ тестах правила 3, использующих этот хелпер, — не дефект самого
    правила 3, а неспециализированность синтетических фикстур под НОВЫЙ ярус
    соседнего правила; было `P2`, ЛЮБОЕ расхождение с `p0` ломает `errors == []`
    одинаково — конкретное число не имеет значения, лишь бы совпадало)."""
    return f'''---
id: {case_id}
title: "Synthetic {case_id}"
area: synthetic
priority: P0
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
    """automated_by не разрешается + mentions≠∅ -> находка «сверка невозможна»
    (правило 3, ВСЕГДА WARN). automated_by, указывающий на несуществующую
    функцию, — ОДНОВРЕМЕННО живой позитив правила 6, направление А
    (`automated_by_orphan`, ERROR с Р1, критик-раунд round2) — ТОТ ЖЕ факт
    (automated_by не резолвится), увиденный ДВУМЯ независимыми правилами;
    не дефект теста/помеха, а честное поведение обоих правил на одном
    источнике — errors ограничен ИМЕННО этой ожидаемой rule6-находкой, ничем
    больше."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-206.md", _case_md(
        "TC-206", "framework/tests/test_does_not_exist.py::test_nope",
        precondition_body="- Открыта replay-запись `listing_basic.mitm`.",
    ))
    errors, warns = ac.run()
    assert len(errors) == 1
    assert errors[0].startswith("rule6:") and "TC-206" in errors[0]
    rule3 = _rule3_warns(warns)
    assert len(rule3) == 1
    assert "TC-206" in rule3[0]
    assert "не разрешается" in rule3[0]


def test_recording_rule_automated_by_unresolvable_without_mentions_is_silent(fw):
    """automated_by не разрешается, но mentions=∅ -> молчание ПРАВИЛА 3 (нечего
    сверять, Р2: шов collectability named-not-covered НЕ аннексируется).
    Правило 6 направление А (ERROR с Р1, критик-раунд round2) на ЭТОТ же
    факт (automated_by не резолвится) молчать не обязано — оно НЕЗАВИСИМАЯ
    проверка того же automated_by, не завязана на mentions; errors ограничен
    именно этой ожидаемой rule6-находкой."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-207.md", _case_md(
        "TC-207", "framework/tests/test_does_not_exist.py::test_nope",
        precondition_body="- Ни одна replay-запись здесь не упоминается.",
    ))
    errors, warns = ac.run()
    assert len(errors) == 1
    assert errors[0].startswith("rule6:") and "TC-207" in errors[0]
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


# --- Правило 4, ВТОРАЯ ФОРМА: wait_until(..., lambda ...: X is None/False) ---
# (живой пропуск TC-197, см. докстринг модуля "ВТОРАЯ ФОРМА")


def test_negative_then_settle_wait_until_is_none_lambda_is_warn(fw):
    """Позитив: живая форма TC-197 (assert_hidden_banner_absent до фикса) —
    `wait_until(driver, lambda d: X.method() is None)` — WARN, method_name из
    вызова на не-константной стороне."""
    _write_steps(fw, "listing_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_hidden_banner_absent(driver, timeout=None):
    wait_until(driver, lambda d: ListingPage(d).hidden_banner_text() is None, timeout=timeout)
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "hidden_banner_text" in rule4[0]
    assert "is None" in rule4[0]
    assert "wait_until" in rule4[0]
    assert "без вердикта" in rule4[0]  # не в NEGATIVE_THEN_SETTLE_BASELINE (fw -> {})


def test_negative_then_settle_wait_until_is_false_lambda_is_warn(fw):
    """Позитив: `is False` — вторая константа формы (не только `is None`)."""
    _write_steps(fw, "checkbox_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_checkbox_cleared(driver):
    wait_until(driver, lambda d: page(d).checkbox_state() is False)
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "checkbox_state" in rule4[0]
    assert "is False" in rule4[0]


def test_negative_then_settle_wait_until_reversed_operand_order_is_warn(fw):
    """`None is X()` — константа СЛЕВА (обратный порядок) — тоже матчится."""
    _write_steps(fw, "reversed_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_gone(driver):
    wait_until(driver, lambda d: None is screen(d).marker())
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "marker" in rule4[0]


def test_negative_then_settle_wait_until_keyword_condition_arg_is_warn(fw):
    """`wait_until(driver, condition=lambda ...)` — предикат именованным
    аргументом (сигнатура `def wait_until(driver, condition, ...)`) — тоже матчится
    (сканируем и `args`, и `keywords`)."""
    _write_steps(fw, "kw_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_gone(driver):
    wait_until(driver, condition=lambda d: screen(d).marker() is None, timeout=5)
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "marker" in rule4[0]


def test_negative_then_settle_wait_until_attribute_call_form_is_warn(fw):
    """`<получатель>.wait_until(...)` — атрибутная форма вызова тоже матчится
    (`_is_wait_until_call` смотрит на `func.attr`, не только на голое имя)."""
    _write_steps(fw, "attr_wait_steps.py", '''from __future__ import annotations


def assert_gone(waiter, driver):
    waiter.wait_until(driver, lambda d: screen(d).marker() is None)
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "marker" in rule4[0]


def test_negative_then_settle_wait_until_boolop_both_sides_is_warn(fw):
    """Б2 (критик-раунд round2), адверсариальная проба 1/6: `BoolOp` с негативной
    формой ПО ОБЕ стороны `and` — голая проверка ВЕРХНЕГО узла (round1,
    `isinstance(arg.body, ast.Compare)`) слепа к этому (`arg.body` — `BoolOp`,
    не `Compare`); DFS (`_iter_negative_wait_candidates`) находит ПЕРВУЮ (левую)."""
    _write_steps(fw, "boolop_both_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_gone(driver):
    wait_until(driver, lambda d: screen(d).banner_text() is None and screen(d).other() is None)
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "banner_text" in rule4[0]


def test_negative_then_settle_wait_until_triple_boolop_is_warn(fw):
    """Б2, адверсариальная проба 2/6: тройной `BoolOp` (`a or b or c`) — та же
    слепота верхнего узла, что и двойной; DFS находит первое (левое) совпадение."""
    _write_steps(fw, "triple_boolop_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_gone(driver):
    wait_until(driver, lambda d: screen(d).a() is None or screen(d).b() is None or screen(d).c() is None)
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "`a(...)" in rule4[0] or "a(..." in rule4[0]


def test_negative_then_settle_wait_until_bool_wrapper_is_warn(fw):
    """Б2, адверсариальная проба 3/6: `bool(...)`-обёртка вокруг `Compare` —
    `arg.body` — `Call`, не `Compare`; голая проверка верхнего узла слепа."""
    _write_steps(fw, "bool_wrapper_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_gone(driver):
    wait_until(driver, lambda d: bool(screen(d).banner_text() is None))
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "banner_text" in rule4[0]


def test_negative_then_settle_wait_until_nested_lambda_is_warn(fw):
    """Б2, адверсариальная проба 4/6: немедленно вызванная вложенная лямбда
    `(lambda e: P(e).x() is None)(d)` — `arg.body` внешней лямбды — `Call`
    вложенной лямбды, `Compare` на глубине 2; DFS находит её."""
    _write_steps(fw, "nested_lambda_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_gone(driver):
    wait_until(driver, lambda d: (lambda e: screen(e).x() is None)(d))
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "x(...)" in rule4[0]


def test_negative_then_settle_wait_until_mixed_positive_negative_boolop_is_warn(fw):
    """Б2, адверсариальная проба 5/6: смесь позитива (`is not None`, НЕ наша
    форма) и негатива (`is None`, наша форма) в одном `BoolOp` — находка ловит
    только негативную часть, позитивная не даёт ложного НЕ-совпадения."""
    _write_steps(fw, "mixed_boolop_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_gone(driver):
    wait_until(driver, lambda d: screen(d).a() is not None and screen(d).b() is None)
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "b(...)" in rule4[0]


def test_negative_then_settle_wait_until_multiple_operators_lambda_is_warn(fw):
    """Б2, адверсариальная проба 6/6: лямбда с несколькими независимыми
    сравнениями/операторами в одном `BoolOp` (`is None`, `==`, `is False`) —
    находится ПЕРВОЕ совпадение нашей формы (`is None`), `==`-сравнение
    (чужая форма) не мешает и не даёт второй находки на тот же wait_until."""
    _write_steps(fw, "multi_ops_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_gone(driver):
    wait_until(driver, lambda d: screen(d).a() is None and other(d).b() == 5 and screen(d).c() is False)
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "a(...)" in rule4[0]


def test_negative_then_settle_wait_until_boolop_no_match_is_silent(fw):
    """Граница Б2: `BoolOp`, где НИ ОДНА сторона не матчит форму (обе — `==`
    или позитивные `is not None`) -> ЗА границей поглотителя, молчание."""
    _write_steps(fw, "boolop_clean_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_ready(driver):
    wait_until(driver, lambda d: screen(d).a() is not None and screen(d).b() == "ok")
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule4_warns(warns) == []


def test_negative_then_settle_wait_until_walrus_key_stable_across_rename(fw, monkeypatch):
    """Замечание (критик-раунд round2): ключ бейзлайна для формы 2 через
    `ast.NamedExpr` (walrus) разворачивается ДО извлечения `method_name` —
    `(v := P(d).x()) is None` и `(w := P(d).x()) is None` (переименованная
    временная переменная) дают ОДИН И ТОТ ЖЕ ключ `method_name="x"`, не
    дрейфующий текст вида `"(v := P(d).x())"`."""
    _write_steps(fw, "walrus_a_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_gone_a(driver):
    wait_until(driver, lambda d: (v := screen(d).x()) is None)
''')
    errors_a, warns_a = ac.run()
    assert errors_a == []
    keys_a = {
        m.group(1) for w in _rule4_warns(warns_a)
        if (m := re.search(r"lambda \.\.\.: (\w+)\(", w))
    }

    monkeypatch.setattr(ac, "NEGATIVE_THEN_SETTLE_BASELINE", {}, raising=True)
    _write_steps(fw, "walrus_a_steps.py", "")  # убираем прежний файл-источник
    (_steps_dir_of(fw) / "walrus_a_steps.py").unlink()
    _write_steps(fw, "walrus_b_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_gone_b(driver):
    wait_until(driver, lambda d: (w := screen(d).x()) is None)
''')
    errors_b, warns_b = ac.run()
    assert errors_b == []
    keys_b = {
        m.group(1) for w in _rule4_warns(warns_b)
        if (m := re.search(r"lambda \.\.\.: (\w+)\(", w))
    }
    assert keys_a == keys_b == {"x"}


def test_negative_then_settle_wait_until_non_call_side_message_has_no_bogus_call_suffix(fw):
    """Замечание (критик-раунд round2, arch_check.py:618 старого кода): не-Call
    сторона сравнения (`P(d).attrname is None`, атрибут, не вызов) раньше давала
    текст `attrname(...)` — несуществующий вызов. Починено: суффикс `(...)`
    печатается ТОЛЬКО когда сторона реально `Call`."""
    _write_steps(fw, "attr_side_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_gone(driver):
    wait_until(driver, lambda d: screen(d).attrname is None)
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "attrname(...)" not in rule4[0]
    assert "attrname is None" in rule4[0]


def test_negative_then_settle_wait_until_boolean_not_form_is_detected(fw):
    """Р3 (критик-раунд round2): форма 3 (`wait_until(..., lambda d: not
    X.method())`) — реализована (round1 сознательно отказался, критик-раунд
    round2 признал отказ неверным: та же неоднозначность УЖЕ штатно
    поглощается NEGATIVE_THEN_SETTLE_BASELINE, как форма 1, — образец
    `assert_blurb_visible`). Без вердикта в бейзлайне — печатается "без вердикта"."""
    _write_steps(fw, "not_form_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_hidden(driver, work_id):
    wait_until(driver, lambda d: not ListingPage(d).is_hidden(work_id))
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "not <получатель>.is_hidden(...)" in rule4[0]
    assert "без вердикта" in rule4[0]


def test_negative_then_settle_wait_until_boolean_not_form_with_verdict_is_gated(fw, monkeypatch):
    """Р3: тот же случай формы 3, но с вердиктом в NEGATIVE_THEN_SETTLE_BASELINE
    (образец `assert_blurb_visible`) — печатается вердикт, не "без вердикта"."""
    monkeypatch.setitem(
        ac.NEGATIVE_THEN_SETTLE_BASELINE,
        ("steps/not_form_verdict_steps.py", "assert_hidden", "is_hidden"),
        "легитимный позитивный Then (пример)",
    )
    _write_steps(fw, "not_form_verdict_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_hidden(driver, work_id):
    wait_until(driver, lambda d: not ListingPage(d).is_hidden(work_id))
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1
    assert "вердикт: легитимный позитивный Then (пример)" in rule4[0]


def test_negative_then_settle_wait_until_boolean_not_form_non_presence_not_matched(fw):
    """Граница формы 3: `not X.method()`, где `method` НЕ матчит предикат
    presence-имени (`NEGATIVE_THEN_METHOD_PATTERN`) -> не находка (та же
    граница, что форма 1 — `test_negative_then_settle_non_presence_method_
    not_matched_by_predicate`)."""
    _write_steps(fw, "not_form_non_presence_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_something(driver, p):
    wait_until(driver, lambda d: not p.exists())
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule4_warns(warns) == []


def test_negative_then_settle_wait_until_equality_form_not_matched(fw):
    """Негатив: легитимная живая форма (readyState=='complete') — сравнение НЕ с
    None/False -> НЕ матчится (это не наш класс дефекта)."""
    _write_steps(fw, "eq_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_ready(driver):
    wait_until(driver, lambda d: d.execute_script("return document.readyState;") == "complete")
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule4_warns(warns) == []



def test_negative_then_settle_wait_until_chained_comparison_not_matched(fw):
    """Граница структурного предиката (М6): РОВНО один оператор `is`. Цепочка
    `a is None is b` (len(ops)==2) — ЗА границей, не матчится."""
    _write_steps(fw, "chained_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_weird(driver, other):
    wait_until(driver, lambda d: screen(d).marker() is None is other)
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule4_warns(warns) == []


def test_negative_then_settle_wait_until_both_sides_constant_not_matched(fw):
    """Граница: обе стороны — None/False-константы (`None is None`) -> нет
    "другой стороны" -> структурно вырожденный случай, не наша форма."""
    _write_steps(fw, "both_const_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_degenerate(driver):
    wait_until(driver, lambda d: None is None)
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule4_warns(warns) == []


def test_negative_then_settle_wait_until_form_is_a_red_probe_for_old_matcher(fw):
    """DoD: красная проба — исходный AST-предикат правила 4 (`ast.Assert(test=
    ast.UnaryOp(op=ast.Not, operand=ast.Call(func=ast.Attribute)))`) НЕ встречается
    в этом источнике ни разу (это `wait_until(...)`, не `assert not ...`) — прямое
    доказательство, что ДО этой правки правило 4 форму TC-197 пропускало бы молча;
    новая ветка (`check_negative_then_settle`, wait_until) её находит."""
    source = '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_hidden_banner_absent(driver, timeout=None):
    wait_until(driver, lambda d: ListingPage(d).hidden_banner_text() is None, timeout=timeout)
'''
    _write_steps(fw, "red_probe_wait_until_steps.py", source)
    tree = ast.parse(source)
    old_form_matches = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assert)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
        and isinstance(node.test.operand, ast.Call)
        and isinstance(node.test.operand.func, ast.Attribute)
    ]
    assert old_form_matches == [], (
        "исходная форма правила 4 (assert not X.method()) неожиданно найдена в "
        "источнике red-probe теста — проба должна доказывать слепоту СТАРОГО "
        "предиката именно к wait_until-форме"
    )
    errors, warns = ac.run()
    assert errors == []
    assert len(_rule4_warns(warns)) == 1


# --- load_case_frontmatter() (общий загрузчик правил 5/6) — BOM/служебные
# файлы (критик-раунд round2, замечания) ---


def test_load_case_frontmatter_bom_prefix_before_id_line_does_not_break_id_regex(fw):
    """Замечание (критик-раунд round2): BOM (`\\ufeff`) ПЕРЕД самой строкой
    `id:` ломал `^id:`-якорь регекса при чтении `encoding="utf-8"` (BOM-байты
    НЕ снимаются этим кодеком, `\\ufeff` остаётся первым символом строки) —
    критик доказал прямой пробой `'\\ufeffid: TC-001'` -> id `None`. Починка —
    `encoding="utf-8-sig"`. Кейс без `---`-fence (минимальный репро критика,
    не обязан отражать факт, что ВСЕ реальные кейсы репозитория начинаются с
    `---`, — регексный дефект общий, не зависит от fence)."""
    cases_dir = _cases_dir_of(fw)
    (cases_dir / "TC-600.md").write_bytes(
        "﻿id: TC-600\npriority: P1\nautomated_by: \"\"\n".encode("utf-8")
    )
    case_frontmatter, read_errors = ac.load_case_frontmatter()
    assert read_errors == []
    assert "TC-600" in case_frontmatter, case_frontmatter
    assert case_frontmatter["TC-600"]["priority"] == "P1"


def test_load_case_frontmatter_skips_readme_and_perturbations(fw):
    """Замечание (критик-раунд round2): README.MD/PERTURBATIONS.MD (регистро-
    независимо) — служебные файлы без frontmatter, пропускаются по имени, тот
    же приём `_SKIP_NAMES`, что scripts/tests/test_automated_by_parity.py.
    Живого вреда не было (единственный такой файл в корпусе и без фильтра
    отсеивался сам — нет `id:`), проба здесь — README.md, у которого ЕСТЬ
    случайно похожая на frontmatter строка `id: TC-999` внутри прозы (без
    фильтра дал бы ложную запись в case_frontmatter)."""
    cases_dir = _cases_dir_of(fw)
    # "id: TC-999" — ЦЕЛАЯ строка (пример YAML-фрагмента в прозе документации);
    # без фильтра по имени файла `^id:`-регекс подхватил бы её как настоящий id.
    (cases_dir / "README.md").write_text(
        "# Справка\n\nПример поля frontmatter:\n\nid: TC-999\n", encoding="utf-8"
    )
    (cases_dir / "PERTURBATIONS.MD").write_text(
        "# Пертурбации\n\nid: TC-998\n", encoding="utf-8"
    )
    _write_case(cases_dir, "TC-601.md", _case_md_min("TC-601", priority="P1"))
    case_frontmatter, read_errors = ac.load_case_frontmatter()
    assert read_errors == []
    assert "TC-999" not in case_frontmatter
    assert "TC-998" not in case_frontmatter
    assert "TC-601" in case_frontmatter


# --- Правило 5: PRIORITY-MARKER-CONSISTENCY (живой пропуск TC-257, докстринг
# модуля "Правило 5") ---


def test_priority_marker_mismatch_is_error(fw):
    """Р1 (критик-раунд round2, 2026-08-25): правило 5 — ERROR, не WARN
    (было WARN, единственное живое расхождение TC-039 починено маркером Р2
    ДО промоции яруса)."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-300.md", _case_md_min("TC-300", priority="P3"))
    _write(fw, "test_priority_mismatch.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-300")
@pytest.mark.p1
def test_something():
    assert True
''')
    errors, warns = ac.run()
    assert _rule5_warns(warns) == []
    rule5 = _rule5_errors(errors)
    assert len(rule5) == 1
    assert "TC-300" in rule5[0]
    assert "`p1`" in rule5[0]
    assert "`P3`" in rule5[0]


def test_priority_marker_mismatch_is_allowlist_gated_and_downgraded_to_warn(fw, monkeypatch):
    """Замечание (критик-раунд round2): ALLOWLIST правила 5 раньше был
    декоративным (обе ветки run() клали находку в warns независимо от
    попадания в ALLOWLIST) — починено на реально исключающий из errors.
    Ключ — ТРЁХэлементный (rel, rule, func_name), т.к. связь тест-файл ->
    находка 1:N (Б1/замечание round2)."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-306.md", _case_md_min("TC-306", priority="P3"))
    _write(fw, "test_priority_allowlisted.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-306")
@pytest.mark.p1
def test_something():
    assert True
''')
    monkeypatch.setattr(
        ac, "ALLOWLIST",
        {("tests/test_priority_allowlisted.py", "priority_marker", "test_something")},
        raising=True,
    )
    errors, warns = ac.run()
    assert _rule5_errors(errors) == []  # реально исключено из errors
    rule5 = _rule5_warns(warns)
    assert len(rule5) == 1
    assert "TC-306" in rule5[0]
    assert "известное исключение" in rule5[0]


def test_priority_marker_allowlist_key_is_per_test_function_not_per_file(fw, monkeypatch):
    """Б1/замечание (критик-раунд round2): ДВУХэлементный ключ (rel, rule)
    гасил бы ВЕСЬ файл — тест демонстрирует, что запись ALLOWLIST на ОДНУ
    тест-функцию НЕ гасит расхождение ВТОРОЙ тест-функции того же файла."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-307.md", _case_md_min("TC-307", priority="P3"))
    _write_case(cases_dir, "TC-308.md", _case_md_min("TC-308", priority="P3"))
    _write(fw, "test_priority_two_funcs.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-307")
@pytest.mark.p1
def test_first():
    assert True


@allure.id("TC-308")
@pytest.mark.p1
def test_second():
    assert True
''')
    monkeypatch.setattr(
        ac, "ALLOWLIST",
        {("tests/test_priority_two_funcs.py", "priority_marker", "test_first")},
        raising=True,
    )
    errors, warns = ac.run()
    rule5_errors = _rule5_errors(errors)
    assert len(rule5_errors) == 1
    assert "TC-308" in rule5_errors[0]  # test_second НЕ погашен записью на test_first
    rule5_warns = _rule5_warns(warns)
    assert len(rule5_warns) == 1
    assert "TC-307" in rule5_warns[0]


def test_priority_marker_match_is_silent(fw):
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-301.md", _case_md_min("TC-301", priority="P1"))
    _write(fw, "test_priority_match.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-301")
@pytest.mark.p1
def test_something():
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule5_warns(warns) == []


def test_priority_marker_case_not_found_is_silent(fw):
    """allure.id теста не резолвится ни к одному кейсу корпуса -> сверка
    невозможна, молчание (НЕ считается "тест без кейса — ошибка")."""
    _write(fw, "test_no_case.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-999")
@pytest.mark.p1
def test_something():
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule5_warns(warns) == []


def test_priority_marker_malformed_priority_is_silent(fw):
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-302.md", _case_md_min("TC-302", priority="TBD"))
    _write(fw, "test_bad_priority.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-302")
@pytest.mark.p1
def test_something():
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule5_warns(warns) == []


def test_priority_marker_zero_suite_markers_is_silent(fw):
    """Граница (М6) снизу: 0 suite-маркеров у теста -> уже ERROR правила 2
    (сверка невозможна без маркера) -> rule5 молчит, не дублирует."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-303.md", _case_md_min("TC-303", priority="P1"))
    _write(fw, "test_zero_markers.py", '''from __future__ import annotations

import allure


@allure.id("TC-303")
def test_something():
    assert True
''')
    errors, warns = ac.run()
    assert any("suite-маркера" in e for e in errors)
    assert _rule5_warns(warns) == []


def test_priority_marker_multiple_suite_markers_is_silent(fw):
    """Граница (М6) сверху: >1 suite-маркеров у одного теста (p0 И p1
    одновременно) — неоднозначно, вне скоупа rule5, молчание."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-304.md", _case_md_min("TC-304", priority="P1"))
    _write(fw, "test_two_markers.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-304")
@pytest.mark.p0
@pytest.mark.p1
def test_something():
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule5_warns(warns) == []


def test_priority_marker_mismatch_is_a_red_probe_for_old_rule2(fw):
    """DoD: красная проба — старое правило 2 (`check_allure_and_markers`, ERROR-tier,
    неизменённый код) видит allure.id и suite-маркер ПО ОТДЕЛЬНОСТИ и проходит
    зелёным на классе TC-257 (p0-маркер при priority P1/иной) — расхождение
    приоритетов ему невидимо в принципе (правило 2 вообще не читает test-cases/).
    Только новое правило 5 его ловит."""
    tree = ast.parse('''from __future__ import annotations

import allure
import pytest


@allure.id("TC-305")
@pytest.mark.p0
def test_something():
    assert True
''')
    old_findings = ac.check_allure_and_markers(tree, "tests/test_red_probe5.py", ac.load_suite_markers())
    assert old_findings == []  # старый гейт (allure.id есть, маркер есть) зелёный

    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-305.md", _case_md_min("TC-305", priority="P2"))
    _write(fw, "test_red_probe5.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-305")
@pytest.mark.p0
def test_something():
    assert True
''')
    errors, warns = ac.run()
    assert _rule5_warns(warns) == []
    rule5 = _rule5_errors(errors)
    assert len(rule5) == 1
    assert "TC-305" in rule5[0]


# --- Правило 6: AUTOMATED-BY-ALLURE-ID-LINK (6 кейсов-сирот TC-207/208/211/213/
# 215/252, докстринг модуля "Правило 6") ---


def test_automated_by_link_case_side_mismatch_is_error(fw):
    """Направление А: automated_by кейса резолвится к тесту, но тест несёт ДРУГОЙ
    allure.id. Р1 (критик-раунд round2, 2026-08-25): направление А — ERROR,
    не WARN (0 живых находок на реальном репо, промоция безопасна)."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-400.md", _case_md_min(
        "TC-400", priority="P1", automated_by="framework/tests/test_ab_mismatch.py::test_something"))
    _write(fw, "test_ab_mismatch.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-999")
@pytest.mark.p1
def test_something():
    assert True
''')
    errors, warns = ac.run()
    assert _rule6_warns(warns) == []
    rule6 = _rule6_case_side_errors(errors)
    assert len(rule6) == 1
    assert "TC-400" in rule6[0]
    assert "TC-999" in rule6[0]


def test_automated_by_link_case_side_no_allure_id_is_error(fw):
    """Направление А: тест, на который резолвится automated_by, вовсе НЕ несёт
    @allure.id(...). Тест САМОГО test_ab_no_id.py тоже даёт ERROR правила 2
    (нет allure.id вовсе) — здесь нас интересует ДОПОЛНИТЕЛЬНЫЙ ERROR правила 6."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-401.md", _case_md_min(
        "TC-401", priority="P1", automated_by="framework/tests/test_ab_no_id.py::test_something"))
    _write(fw, "test_ab_no_id.py", '''from __future__ import annotations

import pytest


@pytest.mark.p1
def test_something():
    assert True
''')
    errors, warns = ac.run()
    assert _rule6_warns(warns) == []
    rule6 = _rule6_case_side_errors(errors)
    assert len(rule6) == 1
    assert "TC-401" in rule6[0]
    assert "не несёт @allure.id" in rule6[0]


def test_automated_by_link_case_side_typo_path_is_error(fw):
    """Адверсариальная проба (DoD): automated_by с опечаткой в пути -> "не
    разрешается" (направление А, ERROR с Р1)."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-402.md", _case_md_min(
        "TC-402", priority="P1",
        automated_by="framework/tests/test_ab_typo_XXXXX.py::test_something"))
    errors, warns = ac.run()
    assert _rule6_warns(warns) == []
    rule6 = _rule6_case_side_errors(errors)
    assert len(rule6) == 1
    assert "TC-402" in rule6[0]
    assert "не разрешается" in rule6[0]


def test_automated_by_link_case_side_allowlist_gated_and_downgraded_to_warn(fw, monkeypatch):
    """Замечание (критик-раунд round2): ALLOWLIST направления А раньше был
    декоративным (обе ветки run() клали находку в warns независимо от
    попадания в ALLOWLIST) — починено на реально исключающий из errors.
    Ключ — двухэлементный (rel, rule): 1:1 (максимум одна находка на кейс),
    без декоративного дефекта правила 5 структурно."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-409.md", _case_md_min(
        "TC-409", priority="P1", automated_by="framework/tests/test_ab_allowlisted.py::test_something"))
    _write(fw, "test_ab_allowlisted.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-999")
@pytest.mark.p1
def test_something():
    assert True
''')
    monkeypatch.setattr(
        ac, "ALLOWLIST",
        {("test-cases/TC-409.md", "automated_by_orphan")},
        raising=True,
    )
    errors, warns = ac.run()
    assert _rule6_case_side_errors(errors) == []  # реально исключено из errors
    rule6 = _rule6_warns(warns)
    assert len(rule6) == 1
    assert "TC-409" in rule6[0]
    assert "известное исключение" in rule6[0]


def test_automated_by_link_case_side_clean_is_silent(fw):
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-403.md", _case_md_min(
        "TC-403", priority="P1", automated_by="framework/tests/test_ab_clean.py::test_something"))
    _write(fw, "test_ab_clean.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-403")
@pytest.mark.p1
def test_something():
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule6_warns(warns) == []


def test_automated_by_link_case_side_empty_automated_by_is_silent(fw):
    """automated_by пуст -> нечего резолвить в направлении А, молчание (не
    дублирует направление Б для этого же кейса)."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-404.md", _case_md_min("TC-404", priority="P1", automated_by=""))
    errors, warns = ac.run()
    assert errors == []
    assert _rule6_warns(warns) == []


def test_automated_by_link_case_side_syntax_error_target_is_silent(fw):
    """Файл, на который резолвится automated_by, не разбирается (SyntaxError) —
    направление А молчит: parse-ERROR уже покрывает файл (правила 1-2), не
    дублируем (тот же приём, что правило 3 — `_PARSE_ERROR`)."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-405.md", _case_md_min(
        "TC-405", priority="P1", automated_by="framework/tests/test_ab_broken.py::test_broken"))
    _write(fw, "test_ab_broken.py", "def test_broken(:\n    pass\n")
    errors, warns = ac.run()
    assert any("не удалось разобрать" in e for e in errors)
    assert _rule6_warns(warns) == []


def test_automated_by_link_test_side_case_empty_is_warn(fw):
    """Направление Б ("и наоборот"): тест несёт allure.id(X), кейс X существует,
    но его automated_by пуст."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-410.md", _case_md_min("TC-410", priority="P1", automated_by=""))
    _write(fw, "test_claims_410.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-410")
@pytest.mark.p1
def test_something():
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    rule6 = _rule6_warns(warns)
    assert len(rule6) == 1
    assert "TC-410" in rule6[0]
    assert "пуст" in rule6[0]


def test_automated_by_link_test_side_duplicate_allure_id_flags_only_mismatched(fw):
    """Адверсариальная проба (DoD): дублирующийся allure.id у двух тестов (живой
    паттерн TC-104/TC-020) — тест, на который указывает automated_by, ЧИСТ; ВТОРОЙ
    тест (тот же allure.id, но automated_by на него не указывает) — находка."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-411.md", _case_md_min(
        "TC-411", priority="P1", automated_by="framework/tests/test_dup.py::test_canonical"))
    _write(fw, "test_dup.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-411")
@pytest.mark.p1
def test_canonical():
    assert True


@allure.id("TC-411")
@pytest.mark.p1
def test_secondary():
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    rule6 = _rule6_warns(warns)
    assert len(rule6) == 1
    assert "test_secondary" in rule6[0]
    assert "указывает на другой тест" in rule6[0]


def test_automated_by_link_test_side_test_without_case_is_silent(fw):
    """Адверсариальная проба (DoD): "тест без кейса" — allure.id ссылается на TC,
    которого нет в корпусе -> вне скоупа правила 6 (докстринг модуля), молчание."""
    _write(fw, "test_orphan_id.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-999999")
@pytest.mark.p1
def test_something():
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule6_warns(warns) == []


def test_automated_by_link_test_side_class_based_qualname_matches(fw):
    """`Test*`-класс: automated_by `путь::Class::method` резолвится к квалифи-
    цированному имени `Class::method` — не ложное расхождение."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-412.md", _case_md_min(
        "TC-412", priority="P1",
        automated_by="framework/tests/test_class_based.py::TestGroup::test_member"))
    _write(fw, "test_class_based.py", '''from __future__ import annotations

import allure
import pytest


class TestGroup:
    @allure.id("TC-412")
    @pytest.mark.p1
    def test_member(self):
        assert True
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule6_warns(warns) == []


def test_automated_by_link_unicode_title_no_crash(fw):
    """Адверсариальная проба (DoD): юникод/кириллица (+эмодзи/спецсимволы) в
    title кейса — не роняет парсинг frontmatter (регексы читают только поля
    id/priority/automated_by, не title)."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-413.md", _case_md_min(
        "TC-413", priority="P1", automated_by="framework/tests/test_unicode.py::test_something",
        title="Юникод-кейс «ёлка» — тест с эмодзи 🎄 и спецсимволами: <>&",
    ))
    _write(fw, "test_unicode.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-413")
@pytest.mark.p1
def test_something():
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule6_warns(warns) == []


def test_automated_by_link_is_a_red_probe_for_old_rule2(fw):
    """DoD: красная проба — старое правило 2 видит allure.id/маркер по отдельности
    и проходит зелёным на живом паттерне-сироте (класс TC-149/150/195/196: тест
    несёт allure.id, automated_by кейса пуст) — связку automated_by<->allure.id
    старый гейт вообще не проверяет (не читает test-cases/). Только новое правило 6
    её ловит."""
    tree = ast.parse('''from __future__ import annotations

import allure
import pytest


@allure.id("TC-414")
@pytest.mark.p1
def test_something():
    assert True
''')
    old_findings = ac.check_allure_and_markers(tree, "tests/test_red_probe6.py", ac.load_suite_markers())
    assert old_findings == []

    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-414.md", _case_md_min("TC-414", priority="P1", automated_by=""))
    _write(fw, "test_red_probe6.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-414")
@pytest.mark.p1
def test_something():
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    rule6 = _rule6_warns(warns)
    assert len(rule6) == 1
    assert "TC-414" in rule6[0]


# --- Самопроверка: реальный framework/ текущего репозитория (не монкипатчено) ---

def test_real_repo_framework_passes():
    """framework/tests/ текущего репозитория проходит чек (с учётом ALLOWLIST test-debt
    в arch_check.py — см. докстринг модуля и финальный отчёт задачи C1).

    ВТОРАЯ строка (критик-раунд round3 attempt 2, Б2) — РЕАЛЬНЫЙ ДЕТЕКТОР
    ОТКАЗА канала `cases:` (F-11 (в) CLAUDE.md: механизм без зарегистрированного
    детектора — пожелание, не механизм). Без неё нечитаемый файл кейса на живом
    репо давал 37 предупреждений вместо 36 при exit 0 и полностью зелёном
    `python -m pytest scripts/tests`, а кейс молча выпадал из правил 3/5/6 —
    двух из них ERROR-ярусных. Канал ОБЯЗАН быть пуст на здоровом корпусе:
    любая его строка означает кейс, по которому гейт не отработал."""
    errors, warns = ac.run()
    assert errors == [], "\n".join(errors)
    assert _cases_read_warns(warns) == [], "\n".join(_cases_read_warns(warns))


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


def test_real_repo_priority_marker_baseline():
    """Правило 5 на реальном репо — Р1 (критик-раунд round2, 2026-08-25):
    ERROR, не WARN. Единственное живое расхождение TC-039 (маркер `p2` при
    priority P3, см. framework/tests/test_downloads.py) починено маркером
    (Р2) ДО этого хода — на реальном репо находок 0. Позитив-контроль:
    зовём `run_priority_marker_rule()` НАПРЯМУЮ (не через `errors == []` из
    `test_real_repo_framework_passes` — та сверка не различает «правило
    молчит, потому что его не вызвали» от «правило вызвано и честно нашло
    0», см. класс Б1/чек калибровки F-30)."""
    findings = ac.run_priority_marker_rule()
    assert findings == [], [(f.rel, f.func_name, f.method_name, f.message) for f in findings]
    _errors, warns = ac.run()
    assert _rule5_warns(warns) == []
    assert _rule5_errors(_errors) == []


def test_real_repo_automated_by_allure_id_link_case_side_baseline():
    """Правило 6, направление А (кейс -> тест) на реальном репо — Р1 (критик-
    раунд round2): ERROR, не WARN. 0 живых находок (6 кейсов-сирот
    TC-207/208/211/213/215/252, названных спекой, исправлены ДО этой
    задачи). Позитив-контроль напрямую (см. довод в test_real_repo_priority_
    marker_baseline выше)."""
    case_frontmatter, read_errors = ac.load_case_frontmatter()
    assert read_errors == [], [f.message for f in read_errors]
    findings = ac.check_automated_by_link_case_side(case_frontmatter)
    assert findings == [], [(f.rel, f.message) for f in findings]
    _errors, warns = ac.run()
    assert _rule6_case_side_errors(_errors) == []


def test_real_repo_automated_by_allure_id_link_test_side_baseline():
    """Бейзлайн направления Б (тест -> кейс, «и наоборот») на реальном репо —
    ОСТАЁТСЯ WARN (Р1). Ключ — Б1 (критик-раунд round2, замечание): кортеж
    `(rel, func_name, method_name)` из `Finding`-объектов НАПРЯМУЮ, НЕ id,
    извлечённый регексом из текста WARN, — связь кейс -> находка у правила 6
    1:N (TC-020/TC-104 несут ПО ДВА теста с одинаковым allure.id, см.
    test_automated_by_link_test_side_duplicate_allure_id_flags_only_
    mismatched; id-only пин слеп ко ВТОРОЙ находке внутри уже пришпиленного
    id, см. test_pin_by_extracted_id_is_blind_to_second_finding_within_
    pinned_id ниже — прямая демонстрация дефекта и починки). Дрейф
    множества — детектор рецидива/новых находок до отдельного решения Lead."""
    case_frontmatter, _read_errors = ac.load_case_frontmatter()
    findings = ac.check_automated_by_link_test_side(case_frontmatter)
    keys = {(f.rel, f.func_name, f.method_name) for f in findings}
    expected = {
        ("tests/canary/test_bridge_init_retry.py", "test_bridge_init_retry_dcl_loading_idempotent", "TC-195"),
        ("tests/canary/test_bridge_init_retry.py", "test_bridge_init_retry_setTimeout_only_path", "TC-196"),
        ("tests/test_accessibility.py", "test_no_interactive_bounds_overlap", "TC-150"),
        ("tests/test_accessibility.py", "test_computed_contrast_holds_wcag_threshold_light_and_dark", "TC-149"),
        ("tests/test_downloads.py", "test_open_downloaded_file_applies_viewport_and_reader_css", "TC-034"),
        ("tests/test_downloads.py", "test_delete_downloaded_file_keeps_rating_row", "TC-035"),
        ("tests/test_downloads.py", "test_delete_work_removes_row_and_file", "TC-036"),
        ("tests/test_security_backup_privacy.py", "test_backup_privacy_saf_export_file_permissions_not_widened", "TC-104"),
        ("tests/test_settings.py", "test_clear_all_ratings_badge_resets_after_reload", "TC-020"),
    }
    assert keys == expected, sorted(keys)

    # то же множество id, что и раньше (не дрейф самого расследования — только
    # пин ключа изменился, Б1) — контроль по ID-множеству, извлечённому из warns
    _errors, warns = ac.run()
    ids = set()
    for w in _rule6_warns(warns):
        m = re.search(r"(TC-\d+)", w)
        assert m, f"не удалось извлечь id кейса из warn-строки правила 6: {w}"
        ids.add(m.group(1))
    assert ids == {
        "TC-020", "TC-034", "TC-035", "TC-036", "TC-104",
        "TC-149", "TC-150", "TC-195", "TC-196",
    }, f"warns правила 6 (полный список): {warns}"


def test_pin_by_extracted_id_is_blind_to_second_finding_within_pinned_id(fw):
    """Б1 (критик-раунд round2): демонстрация лоссовости пина «set из id,
    извлечённого regex'ом из текста WARN» — форма, скопированная с
    test_real_repo_recording_rule_baseline (правило 3, где связь кейс <->
    находка 1:1) на правила 5/6 (связь 1:N — TC-104/TC-020 несут ПО ДВА
    теста). ДВЕ проверки на ОДНОМ и ТОМ ЖЕ множестве находок: (1) id-only пин
    (старая форма) НЕ меняется при добавлении ВТОРОЙ находки внутри уже
    пришпиленного id — критик доказал это симуляцией на реальном репо, здесь
    воспроизведено синтетически; (2) tuple-пин `(rel, func_name, method_name)`
    (починка — см. test_real_repo_automated_by_allure_id_link_test_side_
    baseline) НА ТОМ ЖЕ множестве роняется — новая находка ловится."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-500.md", _case_md_min(
        "TC-500", priority="P1", automated_by="framework/tests/test_ab_canonical.py::test_one"))
    _write(fw, "test_ab_canonical.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-500")
@pytest.mark.p1
def test_one():
    assert True
''')
    _write(fw, "test_ab_second.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-500")
@pytest.mark.p1
def test_two():
    assert True
''')
    case_frontmatter, _read_errors = ac.load_case_frontmatter()
    findings = ac.check_automated_by_link_test_side(case_frontmatter)

    old_style_ids = {re.search(r"(TC-\d+)", f.message).group(1) for f in findings}
    assert old_style_ids == {"TC-500"}  # ОДИН id

    tuple_keys = {(f.rel, f.func_name, f.method_name) for f in findings}
    assert len(tuple_keys) == 1  # одна находка (test_two — единственный мисматч, test_one канонический)

    # ВТОРАЯ находка ВНУТРИ уже пришпиленного id TC-500: третий тест, тот же
    # allure.id, тоже не резолвится через automated_by TC-500.
    _write(fw, "test_ab_third.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-500")
@pytest.mark.p1
def test_three():
    assert True
''')
    case_frontmatter2, _read_errors2 = ac.load_case_frontmatter()
    findings2 = ac.check_automated_by_link_test_side(case_frontmatter2)

    old_style_ids2 = {re.search(r"(TC-\d+)", f.message).group(1) for f in findings2}
    assert old_style_ids2 == {"TC-500"}  # ПИН ПО ID НЕ ИЗМЕНИЛСЯ — дефект воспроизведён (Б1)

    tuple_keys2 = {(f.rel, f.func_name, f.method_name) for f in findings2}
    assert len(tuple_keys2) == 2  # tuple-пин РАСТЁТ — новая находка поймана
    assert tuple_keys2 != tuple_keys  # tuple-пин РОНЯЕТСЯ множеством — починка доказана


# =====================================================================
# Критик-раунд round3 (эскалация на opus-ярус, 2026-08-25) — три блокера
# и пять замечаний. Каждая правка ниже несёт КРАСНУЮ ПРОБУ: тест падал на
# коде ДО починки (Б1 — трассировкой PermissionError/UnicodeDecodeError,
# Б2 — лишним ERROR, замечания 1/2 — ложным попаданием/ложным ERROR).
# =====================================================================

# --- Б1: чтение файла по пути из frontmatter не роняет гейт ---
#
# Класс (правило 9 CLAUDE.md «чини класс, а не экземпляр»): ЧЕТЫРЕ точки
# чтения файла по пути, пришедшему из данных, — `_resolve_test_function`
# (правила 3/6-А), `load_case_frontmatter` (правила 5/6),
# `_parse_framework_file` (правила 1-2/4/5/6-Б) и `_process_case`
# (правило 3; критиком НЕ названа, найдена обходом класса — тот же
# `path.read_text` без охраны). Ни одна не переживала вход, который
# СХЕМА (schemas/test-case.schema.yaml:26, `^$|^framework/tests/.+::.+$`)
# допускает: `framework/tests/canary::test_x` — путь на КАТАЛОГ.

_BROKEN_KINDS = ["directory", "missing", "bad_encoding", "syntax_error", "empty",
                 "dangling_symlink"]


def _materialize_broken(base: Path, name: str, kind: str) -> Path | None:
    """Адверсариальная батарея класса «битый вход» (DoD п.2) — создаёт в `base`
    объект с именем `name` соответствующего класса. `None` — среда не позволяет
    создать (единственный случай: `dangling_symlink` без SeCreateSymbolicLink /
    Developer Mode в Windows; тест в этом случае skip'ается явно)."""
    p = base / name
    if kind == "directory":
        p.mkdir()
    elif kind == "missing":
        pass  # ничего не создаём — путь не существует
    elif kind == "bad_encoding":
        p.write_bytes(b"\xff\xfe\x00\x01\x80\x81 def test_x(): pass\n")
    elif kind == "syntax_error":
        p.write_text("def test_x(:\n    pass\n", encoding="utf-8")
    elif kind == "empty":
        p.write_text("", encoding="utf-8")
    elif kind == "dangling_symlink":
        try:
            p.symlink_to(base / "no_such_target_ever")
        except (OSError, NotImplementedError):
            return None
    else:  # pragma: no cover - защита от опечатки в параметризации
        raise AssertionError(f"неизвестный класс битого входа: {kind}")
    return p


def test_automated_by_pointing_at_directory_is_finding_not_crash(fw):
    """Б1, КРАСНАЯ ПРОБА: `automated_by` на КАТАЛОГ — схемо-легальная строка
    (`^framework/tests/.+::.+$` матчит `framework/tests/canary::test_x`).
    ДО починки `_resolve_test_function` проверял `exists()` (каталог его
    проходит) и ловил только (SyntaxError, UnicodeDecodeError) — `read_text`
    каталога роняет `run()` трассировкой PermissionError. ПОСЛЕ — штатная
    находка «не разрешается» направления А."""
    cases_dir = _cases_dir_of(fw)
    (fw / "canary").mkdir()
    _write_case(cases_dir, "TC-600.md", _case_md_min(
        "TC-600", priority="P1", automated_by="framework/tests/canary::test_x"))
    errors, warns = ac.run()
    rule6 = _rule6_case_side_errors(errors)
    assert len(rule6) == 1, errors
    assert "TC-600" in rule6[0]
    assert "не разрешается" in rule6[0]


def test_unreadable_case_file_is_warn_not_crash(fw):
    """Б1, КРАСНАЯ ПРОБА (вторая точка чтения): нечитаемый файл КЕЙСА
    (каталог с именем `*.md` — `CASES_DIR.rglob("*.md")` его подхватывает,
    `read_text` роняет PermissionError). ПОСЛЕ — WARN канала `cases:`, НЕ
    молчание: молчаливый пропуск оставил бы кейс без единой находки любого
    правила (тот же довод, что D2-F2 у нечитаемого steps-файла)."""
    cases_dir = _cases_dir_of(fw)
    (cases_dir / "TC-601.md").mkdir()
    errors, warns = ac.run()
    assert errors == []
    hits = _cases_read_warns(warns)
    assert len(hits) == 1, warns
    assert "TC-601.md" in hits[0]


def test_directory_named_like_test_module_is_parse_error_not_crash(fw):
    """Б1, КРАСНАЯ ПРОБА (третья точка чтения): каталог с именем `test_*.py`
    внутри framework/tests — `TESTS_DIR.rglob("test_*.py")` его подхватывает,
    `_parse_framework_file` до починки ловил только (SyntaxError,
    UnicodeDecodeError) и падал PermissionError. ПОСЛЕ — обычный parse-ERROR
    правил 1-2."""
    (fw / "test_dir_masquerading.py").mkdir()
    errors, warns = ac.run()
    assert any("не удалось разобрать" in e for e in errors), errors


def test_unreadable_case_file_does_not_crash_recording_rule(fw):
    """Б1, КРАСНАЯ ПРОБА (четвёртая точка чтения — обход класса, правило 9
    CLAUDE.md; критиком не названа): `_process_case` читает тот же файл
    кейса своим `read_text` и роняет `run_recording_rule()` на каталоге
    `*.md`. ПОСЛЕ — молчание правила 3 по нечитаемому файлу (доклад о нём
    принадлежит общему загрузчику, канал `cases:` — не дублируем)."""
    cases_dir = _cases_dir_of(fw)
    (cases_dir / "TC-602.md").mkdir()
    findings = ac.run_recording_rule()
    assert findings == [], [f.message for f in findings]


def test_recording_builder_as_directory_is_not_crash(fw):
    """Б1 attempt 2, КРАСНАЯ ПРОБА (ПЯТАЯ точка чтения — обход класса прошлого
    хода был неполон): `framework/data/recording_builder.py` каталогом.
    `_load_recording_builder_consts` держал прежнюю идиому (`exists()` +
    перехват без `OSError`), и `read_text` каталога ронял `run()` PermissionError
    РАНЬШЕ всех правил — `run()` -> `run_recording_rule()` -> сюда, до первой
    находки правила 3. ПОСЛЕ — пустой словарь констант и штатный проход гейта."""
    rb = _recording_builder_of(fw)
    rb.unlink()
    rb.mkdir()
    _write(fw, "test_rb_dir.py", CLEAN_TEST)
    errors, warns = ac.run()
    assert errors == [], errors
    assert warns == [], warns


@pytest.mark.parametrize("kind", _BROKEN_KINDS)
def test_recording_builder_battery_never_raises(fw, kind):
    """DoD п.2, та же адверсариальная батарея по точке чтения №5."""
    rb = _recording_builder_of(fw)
    rb.unlink()
    if _materialize_broken(rb.parent, rb.name, kind) is None:
        pytest.skip("ОС не даёт создать симлинк без прав (Windows без Developer Mode)")
    errors, warns = ac.run()
    assert isinstance(errors, list) and isinstance(warns, list)


@pytest.mark.parametrize("kind", _BROKEN_KINDS)
def test_resolve_test_function_battery_never_raises(fw, kind):
    """DoD п.2, адверсариальная батарея по точке чтения №1
    (`_resolve_test_function`): каталог / отсутствующий файл / битая
    кодировка / синтаксически неверный python / пустой файл / симлинк в
    никуда. Ожидание по классам: `_PARSE_ERROR` — файл ЕСТЬ, но не
    разбирается; `None` — резолюции нет (файла нет / это не файл / функции
    в нём нет). Исключений не бывает НИ В ОДНОМ классе."""
    if _materialize_broken(fw, "test_battery.py", kind) is None:
        pytest.skip("ОС не даёт создать симлинк без прав (Windows без Developer Mode)")
    result = ac._resolve_test_function("framework/tests/test_battery.py", ["test_x"])
    if kind in ("bad_encoding", "syntax_error"):
        assert result is ac._PARSE_ERROR
    else:
        assert result is None


@pytest.mark.parametrize("kind", _BROKEN_KINDS)
def test_run_never_crashes_on_broken_case_file(fw, kind):
    """DoD п.2, та же батарея по точкам чтения №2/№4 (test-cases/): весь
    `run()` обязан вернуть пару (errors, warns), а не трассировку."""
    cases_dir = _cases_dir_of(fw)
    if _materialize_broken(cases_dir, "TC-603.md", kind) is None:
        pytest.skip("ОС не даёт создать симлинк без прав (Windows без Developer Mode)")
    errors, warns = ac.run()
    assert isinstance(errors, list) and isinstance(warns, list)


@pytest.mark.parametrize("kind", _BROKEN_KINDS)
def test_run_never_crashes_on_broken_framework_test_file(fw, kind):
    """DoD п.2, та же батарея по точке чтения №3 (framework/tests/)."""
    if _materialize_broken(fw, "test_broken_battery.py", kind) is None:
        pytest.skip("ОС не даёт создать симлинк без прав (Windows без Developer Mode)")
    errors, warns = ac.run()
    assert isinstance(errors, list) and isinstance(warns, list)


# --- Б2: ERROR не выводится из кейсов, чей жизненный статус правила не читают ---

_MERGED_CASE_STATUSES = ["Merged", "Draft"]
_WORKING_CASE_STATUSES = ["Review", "Approved", "Automated", "Blocked"]


@pytest.mark.parametrize("status", _MERGED_CASE_STATUSES)
def test_priority_marker_non_working_status_is_silent(fw, status):
    """Б2, КРАСНАЯ ПРОБА (правило 5): кейс вне рабочих статусов (`Merged` —
    терминал, поля окаменели; `Draft` — поля ещё не ратифицированы) НЕ
    порождает ERROR о расхождении маркера. ДО починки `load_case_frontmatter`
    не читал `status` вовсе — `Merged`-кейс с `priority: P1` и живой тест
    `@pytest.mark.p3` давали ERROR5, названный по СЛИТОМУ кейсу."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-620.md", _case_md_min("TC-620", priority="P1", status=status))
    _write(fw, "test_pm_status.py", f'''from __future__ import annotations

import allure
import pytest


@allure.id("TC-620")
@pytest.mark.p3
def test_something():
    assert True
''')
    errors, warns = ac.run()
    assert _rule5_errors(errors) == [], errors
    assert _rule5_warns(warns) == []


@pytest.mark.parametrize("status", _WORKING_CASE_STATUSES)
def test_priority_marker_working_status_is_still_error(fw, status):
    """Б2, обратная сторона: РАБОЧИЕ статусы (`Review`/`Approved`/`Automated`
    — прямое требование спеки; `Blocked` — решение исполнителя, см. отчёт:
    Blocked описывает остановку РАБОТЫ, а не недействительность полей) молчать
    НЕ должны — иначе ветвь молчания стала бы дырой «пометь кейс и расхождение
    исчезнет»."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-621.md", _case_md_min("TC-621", priority="P1", status=status))
    _write(fw, "test_pm_working.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-621")
@pytest.mark.p3
def test_something():
    assert True
''')
    errors, _warns = ac.run()
    rule5 = _rule5_errors(errors)
    assert len(rule5) == 1, errors
    assert "TC-621" in rule5[0]


def test_priority_marker_missing_status_is_still_error(fw):
    """Б2, fail-closed: кейс БЕЗ поля `status` (или с пустым) трактуется как
    рабочий — молчит только ЯВНО названный не-рабочий статус."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-622.md", _case_md_min("TC-622", priority="P1"))
    _write(fw, "test_pm_nostatus.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-622")
@pytest.mark.p3
def test_something():
    assert True
''')
    errors, _warns = ac.run()
    assert len(_rule5_errors(errors)) == 1, errors


@pytest.mark.parametrize("status", _MERGED_CASE_STATUSES)
def test_automated_by_link_case_side_non_working_status_is_silent(fw, status):
    """Б2, КРАСНАЯ ПРОБА (правило 6, направление А): тот же довод, что у
    правила 5 — `automated_by` слитого/недоратифицированного кейса не
    основание для ERROR."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-623.md", _case_md_min(
        "TC-623", priority="P1", status=status,
        automated_by="framework/tests/test_ab_status.py::test_something"))
    _write(fw, "test_ab_status.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-999")
@pytest.mark.p1
def test_something():
    assert True
''')
    errors, _warns = ac.run()
    assert _rule6_case_side_errors(errors) == [], errors


@pytest.mark.parametrize("status", _WORKING_CASE_STATUSES)
def test_automated_by_link_case_side_working_status_is_still_error(fw, status):
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-624.md", _case_md_min(
        "TC-624", priority="P1", status=status,
        automated_by="framework/tests/test_ab_working.py::test_something"))
    _write(fw, "test_ab_working.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-999")
@pytest.mark.p1
def test_something():
    assert True
''')
    errors, _warns = ac.run()
    rule6 = _rule6_case_side_errors(errors)
    assert len(rule6) == 1, errors
    assert "TC-624" in rule6[0]


def test_automated_by_link_test_side_is_status_blind(fw):
    """Б2, ГРАНИЦА ветви молчания: направление Б (тест -> кейс) остаётся WARN
    и статусом НЕ гасится. Довод: его real-repo-пин
    (`test_real_repo_automated_by_allure_id_link_test_side_baseline`) держит
    ровно TC-034/035/036 — СЛИТЫЕ кейсы; гашение по статусу стёрло бы
    детектор дрейфа. Ветвь молчания Б2 объявлена только для правил 5 и 6-А."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-625.md", _case_md_min("TC-625", priority="P1",
                                                     status="Merged", automated_by=""))
    _write(fw, "test_ts_merged.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-625")
@pytest.mark.p1
def test_something():
    assert True
''')
    errors, warns = ac.run()
    assert errors == []
    rule6 = _rule6_warns(warns)
    assert len(rule6) == 1, warns
    assert "TC-625" in rule6[0]


# --- Замечание 1: DFS правила 4 не спускается в comprehension и в лямбды
#     НЕ-предикатных аргументов wait_until ---


def test_negative_then_settle_wait_until_comprehension_condition_not_matched(fw):
    """Замечание 1(а), КРАСНАЯ ПРОБА: условие comprehension — НЕ тело
    предиката. ДО починки DFS спускался в `ifs` и давал находку с
    `method_name='x'` (имя переменной цикла!) — структурно бессмысленный
    ключ бейзлайна."""
    _write_steps(fw, "comp_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_gone(driver):
    wait_until(driver, lambda d: [x for x in screen(d).items() if x is None])
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule4_warns(warns) == [], warns


def test_negative_then_settle_wait_until_generator_element_not_matched(fw):
    """Замечание 1(а), КРАСНАЯ ПРОБА, вторая форма того же класса: элемент
    генератора внутри `any(...)`. ДО починки — находка с `method_name='cell'`."""
    _write_steps(fw, "genexp_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_gone(driver, rows):
    wait_until(driver, lambda d: any(screen(d).cell(i) is None for i in rows))
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule4_warns(warns) == [], warns


def test_negative_then_settle_wait_until_non_predicate_keyword_lambda_not_matched(fw):
    """Замечание 1(б), КРАСНАЯ ПРОБА: предикат `wait_until` — ОДИН конкретный
    аргумент (позиционный №1 либо `condition=`, см. framework/core/waits.py:23).
    ДО починки сканировались ВСЕ `args`/`keywords`, и лямбда в `message=`
    давала находку."""
    _write_steps(fw, "kwlambda_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_gone(driver):
    wait_until(driver, EC.x(), message=lambda d: screen(d).a() is None)
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule4_warns(warns) == [], warns


def test_negative_then_settle_wait_until_non_predicate_positional_lambda_not_matched(fw):
    """Замечание 1(б), КРАСНАЯ ПРОБА, позиционная форма того же класса:
    четвёртый позиционный аргумент (`message`) — тоже не предикат."""
    _write_steps(fw, "poslambda_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_gone(driver):
    wait_until(driver, EC.x(), 5, lambda d: screen(d).a() is None)
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule4_warns(warns) == [], warns


def test_negative_then_settle_wait_until_predicate_arg_still_matched(fw):
    """Замечание 1(б), КОНТРОЛЬ (не красная проба): сужение до предикатного
    аргумента не должно ослепить правило на ЖИВОЙ форме — предикат позиционным
    №1 вместе с лямбдой в `message=` рядом даёт РОВНО ОДНУ находку."""
    _write_steps(fw, "predicate_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_gone(driver):
    wait_until(driver, lambda d: screen(d).banner_visible() is None,
               message=lambda d: screen(d).other() is None)
''')
    errors, warns = ac.run()
    assert errors == []
    rule4 = _rule4_warns(warns)
    assert len(rule4) == 1, warns
    assert "banner_visible" in rule4[0]


def test_negative_then_settle_wait_until_starred_args_are_not_guessed(fw):
    """Замечание 1(б), край: `wait_until(*args)` — позиция предиката не
    вычислима, правило молчит (не гадает по индексу)."""
    _write_steps(fw, "starred_steps.py", '''from __future__ import annotations

from framework.core.waits import wait_until


def assert_gone(driver, args):
    wait_until(*args, lambda d: screen(d).a() is None)
''')
    errors, warns = ac.run()
    assert errors == []
    assert _rule4_warns(warns) == [], warns


# --- Замечание 2: automated_by с вложенной формой `::` читается так же,
#     как механизмом-собратом (scripts/tests/test_automated_by_parity.py) ---


def test_automated_by_class_method_form_resolves(fw):
    """Замечание 2, ПИН (зелёный и до починки): каноничная вложенная форма
    `<путь>::Class::method` резолвится — та же форма, что квалифицированное
    имя `_test_functions_with_qualname`."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-610.md", _case_md_min(
        "TC-610", priority="P1",
        automated_by="framework/tests/test_ab_cls.py::TestGroup::test_in_class"))
    _write(fw, "test_ab_cls.py", '''from __future__ import annotations

import allure
import pytest


class TestGroup:
    @allure.id("TC-610")
    @pytest.mark.p1
    def test_in_class(self):
        assert True
''')
    errors, warns = ac.run()
    assert _rule6_case_side_errors(errors) == [], errors
    assert _rule6_warns(warns) == [], warns


def test_automated_by_deeply_nested_form_resolves_by_last_segment(fw):
    """Замечание 2, КРАСНАЯ ПРОБА: `<путь>::Outer::Inner::method` схемо-легален
    (`^framework/tests/.+::.+$`), механизм-собрат его принимает (`parts[-1]`,
    scripts/tests/test_automated_by_parity.py:82), а `_resolve_test_function`
    до починки возвращал None на >2 сегментах имени -> ERROR6-А. Решение Lead:
    свести к трактовке собрата — два гейта по ОДНОМУ полю обязаны читать его
    одинаково."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-611.md", _case_md_min(
        "TC-611", priority="P1",
        automated_by="framework/tests/test_ab_nested.py::TestOuter::Inner::test_nested"))
    _write(fw, "test_ab_nested.py", '''from __future__ import annotations

import allure
import pytest


class TestOuter:
    class Inner:
        @allure.id("TC-611")
        @pytest.mark.p1
        def test_nested(self):
            assert True
''')
    errors, _warns = ac.run()
    assert _rule6_case_side_errors(errors) == [], errors


def test_automated_by_wrong_intermediate_class_falls_back_to_last_segment(fw):
    """Замечание 2, КРАСНАЯ ПРОБА (вторая форма того же расхождения):
    промежуточный сегмент назван неверно, а функция в файле есть и уникальна.
    Собрат резолвит (ищет `def <parts[-1]>` по всему файлу), arch_check до
    починки давал ERROR6-А «не разрешается»."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-612.md", _case_md_min(
        "TC-612", priority="P1",
        automated_by="framework/tests/test_ab_wrongcls.py::TestNoSuch::test_top"))
    _write(fw, "test_ab_wrongcls.py", '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-612")
@pytest.mark.p1
def test_top():
    assert True
''')
    errors, _warns = ac.run()
    assert _rule6_case_side_errors(errors) == [], errors


_PARITY_TARGET_MODULE = '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-614")
@pytest.mark.p1
def test_target():
    assert True


class TestOuter:
    class Inner:
        @allure.id("TC-614")
        @pytest.mark.p1
        def test_nested(self):
            assert True
'''

_PARITY_SHADOW_MODULE = '''from __future__ import annotations

import allure
import pytest


@allure.id("TC-614")
@pytest.mark.p1
def test_dup():
    assert True


@allure.id("TC-614")
@pytest.mark.p1
def test_dup():  # noqa: F811 — намеренное затенение, предмет пробы
    assert True
'''

# Шесть форм `automated_by` -> ожидаемая РАЗРЕШИМОСТЬ (одна и та же для обоих
# гейтов). Таблица — машинный детектор УТВЕРЖДЕНИЯ О ПАРИТЕТЕ (критик-раунд
# round3 attempt 2, Б3: подвели не решения, а утверждения о полноте — значит
# утверждение обязано иметь детектор, F-11 (в) CLAUDE.md).
_PARITY_FORMS = [
    ("норма", "framework/tests/test_parity_target.py::test_target", True),
    ("опечатка пути", "framework/tests/test_parity_TYPO.py::test_target", False),
    ("опечатка имени", "framework/tests/test_parity_target.py::test_TYPO", False),
    ("неверный промежуточный класс",
     "framework/tests/test_parity_target.py::TestNoSuch::test_target", True),
    ("4 сегмента",
     "framework/tests/test_parity_target.py::TestOuter::Inner::test_nested", True),
    ("shadowing", "framework/tests/test_parity_shadow.py::test_dup", False),
]


@pytest.mark.parametrize("label,automated_by,expect_resolved", _PARITY_FORMS,
                         ids=[f[0] for f in _PARITY_FORMS])
def test_automated_by_parity_with_sibling_gate(fw, label, automated_by, expect_resolved):
    """Б3 attempt 2, КРАСНАЯ ПРОБА на форме `shadowing`: `arch_check` и
    механизм-собрат (`scripts/tests/test_automated_by_parity.py::
    resolve_automated_by`) обязаны читать ОДНО поле `automated_by` одинаково по
    ВСЕМ шести формам. До починки строгая ветка `<путь>::<функция>` возвращала
    ПЕРВОЕ совпадение, не доходя до стража «2+ -> None»: на shadowing arch_check
    молча резолвил ПЕРВОЕ определение и валидировал его `allure.id`, тогда как
    Python исполняет ПОСЛЕДНЕЕ, — не молчание, а неверный ответ; собрат в той же
    форме давал `ok=False`. Остальные пять форм — контроль, что послабление
    замечания 2 не съехало ни в одну сторону."""
    import test_automated_by_parity as parity

    _write(fw, "test_parity_target.py", _PARITY_TARGET_MODULE)
    _write(fw, "test_parity_shadow.py", _PARITY_SHADOW_MODULE)

    split = ac._split_automated_by(automated_by)
    resolved = ac._resolve_test_function(*split) if split else None
    arch_ok = split is not None and resolved is not None and resolved is not ac._PARSE_ERROR

    sibling_ok, sibling_reason = parity.resolve_automated_by(automated_by, ac.REPO)

    assert arch_ok is expect_resolved, f"{label}: arch_check дал {arch_ok}"
    assert sibling_ok is expect_resolved, f"{label}: собрат дал {sibling_ok} ({sibling_reason})"
    assert arch_ok == sibling_ok, f"{label}: гейты разошлись (собрат: {sibling_reason})"


def test_automated_by_shadowed_last_segment_is_unresolved(fw):
    """Замечание 2, ГРАНИЦА послабления (паритет с собратом,
    `resolve_automated_by` -> MISMATCH при 2+ определениях одного имени):
    имя последнего сегмента определено в файле ДВАЖДЫ — резолюция
    неоднозначна, послабление НЕ применяется, находка остаётся."""
    cases_dir = _cases_dir_of(fw)
    _write_case(cases_dir, "TC-613.md", _case_md_min(
        "TC-613", priority="P1",
        automated_by="framework/tests/test_ab_shadow.py::TestNoSuch::test_dup"))
    _write(fw, "test_ab_shadow.py", '''from __future__ import annotations

import allure
import pytest


class TestA:
    @allure.id("TC-613")
    @pytest.mark.p1
    def test_dup(self):
        assert True


class TestB:
    @allure.id("TC-613")
    @pytest.mark.p1
    def test_dup(self):
        assert True
''')
    errors, _warns = ac.run()
    rule6 = _rule6_case_side_errors(errors)
    assert len(rule6) == 1, errors
    assert "не разрешается" in rule6[0]
