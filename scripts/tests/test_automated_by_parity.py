"""Parity-тест: `automated_by` каждого test-case реально резолвится в
существующую функцию (класс AT-BUG-022 «деливерабл-дрейф», сиблинг-находка
critic 2026-07-21: заявленный `automated_by` дважды указывал на функцию,
которой ещё не было в дереве — F1-гейт test-reviewer это не ловит
структурно, ловится только внимательностью человека).

Формат поля (сверено по факту на всех test-cases/**/*.md репозитория,
2026-07-21): везде ровно один разделитель `path::func` — `путь/до/файла.py::
имя_функции`. Классов/вложенных `::`-сегментов в реальных данных нет; чтобы
не додумывать несуществующий формат (правило 1 роли builder), парсер берёт
ПЕРВЫЙ сегмент как путь и ПОСЛЕДНИЙ как имя функции для поиска — это
честно обобщает текущий формат на случай `path::Class::method`, если он
появится, не требуя отдельной ветки логики.

Резолюция — статическая (regex `def <func>` в файле), не импорт: сравнимо
со стилем validate_frontmatter.py (без исполнения кода репозитория) и с
test_rules_agent_parity.py (парсинг файлов, не импорт модулей фреймворка).

Проверялось на дублирование (F-34, до написания): grep "automated_by" по
scripts/ — совпадения только в board_sync.py (produkt колонки борды по
ФАКТУ ПРИСУТСТВИЯ поля, не по резолюции) и в самих юнит-тестах вокруг них
(test_board_sync.py и т.д.); validate_frontmatter.py проверяет schema/enum/
required-поля, но не резолюцию значения `automated_by` в реальный код.
Аналога этому тесту в scripts/ на момент написания нет.
"""
from __future__ import annotations

import re
from pathlib import Path

import board_sync as bs

REPO = bs.REPO
TEST_CASES_DIR = REPO / "test-cases"

_SKIP_NAMES = {"README.MD", "PERTURBATIONS.MD"}


def _iter_test_case_files(base: Path):
    for md in sorted(base.rglob("*.md")):
        if md.name.upper() in _SKIP_NAMES:
            continue
        yield md


def _iter_automated_by(base: Path):
    """Yield (rel_path, automated_by) для каждого test-case с непустым
    `automated_by`. Пустая/отсутствующая строка — легальный "не
    автоматизирован" кейс (см. test-cases/performance/TC-096..099.md,
    test-cases/settings/TC-020.md), пропускается тихо — это НЕ находка."""
    for md in _iter_test_case_files(base):
        meta, _body = bs._parse_frontmatter(md.read_text(encoding="utf-8", errors="replace"))
        automated_by = str(meta.get("automated_by") or "").strip()
        if not automated_by:
            continue
        # relative_to(base.parent), не жёстко REPO: тест переиспользует эту
        # функцию и на tmp_path-синтетике (red probe) — там "base" не лежит
        # под REPO, а base.parent даёт стабильный корень в обоих случаях
        # (реальный вызов: base=TEST_CASES_DIR, base.parent=REPO — то же
        # значение, что раньше).
        yield md.relative_to(base.parent).as_posix(), automated_by


def resolve_automated_by(automated_by: str, repo: Path) -> tuple[bool, str]:
    """(ok, reason). reason пуст при ok=True. Статический regex-поиск
    `def <func>(` (учитывает `async def`, отступ — методы классов) —
    не импорт: framework/tests/*.py тянет фикстуры appium/adb, которые
    здесь недоступны и не нужны для проверки самого факта резолюции."""
    parts = automated_by.split("::")
    if len(parts) < 2:
        return False, f"нет разделителя `::` в `{automated_by}`"
    rel_path, func_name = parts[0], parts[-1]
    file_path = repo / rel_path
    if not file_path.is_file():
        return False, f"файл не существует: {rel_path}"
    text = file_path.read_text(encoding="utf-8", errors="replace")
    pattern = rf"^\s*(?:async\s+)?def\s+{re.escape(func_name)}\s*\("
    if not re.search(pattern, text, re.MULTILINE):
        return False, f"`def {func_name}` не найдено в {rel_path}"
    return True, ""


def collect_mismatches(base: Path, repo: Path) -> list[tuple[str, str, str]]:
    """[(rel_test_case_path, automated_by, reason)] по всем несовпадениям."""
    mismatches = []
    for rel, automated_by in _iter_automated_by(base):
        ok, reason = resolve_automated_by(automated_by, repo)
        if not ok:
            mismatches.append((rel, automated_by, reason))
    return mismatches


def test_automated_by_resolves_to_existing_function():
    """Каждый непустой `automated_by` реального test-cases/**/*.md обязан
    указывать на файл и функцию, которые реально существуют в дереве."""
    mismatches = collect_mismatches(TEST_CASES_DIR, REPO)
    assert not mismatches, (
        "automated_by не резолвится в существующую функцию (класс "
        f"AT-BUG-022 деливерабл-дрейф): {mismatches}"
    )


def test_iter_automated_by_nonempty():
    """Защита от vacuous pass (тот же класс, что N1(а) в
    test_rules_agent_parity.py): если сбор automated_by когда-либо молча
    вернёт пусто (дрейф структуры frontmatter/glob), проверка выше стала бы
    тривиально зелёной, ничего не проверяя."""
    found = list(_iter_automated_by(TEST_CASES_DIR))
    assert found, (
        "ни один test-case не дал непустой automated_by — дрейф структуры "
        "frontmatter или glob, parity-тест рискует vacuous pass"
    )


def test_resolve_automated_by_positive_control():
    """F-34: позитивный контроль формы поиска — заведомо существующая
    функция обязана резолвиться, иначе сам regex/путь сломан, а не данные."""
    ok, reason = resolve_automated_by(
        "framework/tests/test_smoke.py::test_app_launches_and_loads_ao3", REPO)
    assert ok, f"позитивный контроль не прошёл: {reason}"


def test_resolve_automated_by_missing_file_is_mismatch():
    """Красная проба: путь на несуществующий файл — mismatch, не тихий OK."""
    ok, reason = resolve_automated_by(
        "framework/tests/test_definitely_missing_xyz.py::test_whatever", REPO)
    assert not ok
    assert "не существует" in reason


def test_resolve_automated_by_missing_function_is_mismatch(tmp_path):
    """Красная проба: файл существует, но функции с таким именем в нём нет —
    отдельный подкласс от «файла нет» (это и есть подкласс AT-BUG-022:
    automated_by указывал на функцию, которой ещё не было, при том что файл
    теста уже существовал)."""
    fake_file = tmp_path / "test_fake.py"
    fake_file.write_text("def test_other_thing():\n    pass\n", encoding="utf-8")
    ok, reason = resolve_automated_by(
        "test_fake.py::test_function_never_written", tmp_path)
    assert not ok
    assert "не найдено" in reason


def test_resolve_automated_by_finds_async_and_indented_def(tmp_path):
    """Регресс на форму regex: async def и def-метод класса (отступ) —
    честное обобщение под возможный `path::Class::method`, см. docstring
    модуля."""
    fake_file = tmp_path / "test_fake2.py"
    fake_file.write_text(
        "class Foo:\n    def test_method(self):\n        pass\n\n"
        "async def test_async_thing():\n    pass\n",
        encoding="utf-8",
    )
    ok_method, _ = resolve_automated_by("test_fake2.py::Foo::test_method", tmp_path)
    ok_async, _ = resolve_automated_by("test_fake2.py::test_async_thing", tmp_path)
    assert ok_method
    assert ok_async


def test_collect_mismatches_red_probe_on_synthetic_test_case(tmp_path):
    """Красная проба верхнего уровня: синтетический test-case с automated_by
    на несуществующую функцию — collect_mismatches обязан его найти. Не
    трогает реальные test-cases/ (отдельный tmp_path-каталог)."""
    tc_dir = tmp_path / "test-cases" / "fake-area"
    tc_dir.mkdir(parents=True)
    (tc_dir / "TC-999.md").write_text(
        "---\nid: TC-999\ntitle: Synthetic\nautomated_by: "
        '"framework/tests/test_nope.py::test_ghost_function"\n---\n\n# TC-999\n',
        encoding="utf-8",
    )
    mismatches = collect_mismatches(tmp_path / "test-cases", REPO)
    assert len(mismatches) == 1
    rel, automated_by, reason = mismatches[0]
    assert rel.endswith("TC-999.md")
    assert "test_ghost_function" in automated_by
    assert "не существует" in reason


def test_iter_skips_empty_automated_by(tmp_path):
    """Пустой automated_by (не автоматизировано) — легальный пропуск, не
    находка (test-cases/performance/TC-096..099.md — реальный пример)."""
    tc_dir = tmp_path / "test-cases" / "fake-area"
    tc_dir.mkdir(parents=True)
    (tc_dir / "TC-998.md").write_text(
        '---\nid: TC-998\ntitle: Synthetic\nautomated_by: ""\n---\n\n# TC-998\n',
        encoding="utf-8",
    )
    found = list(_iter_automated_by(tc_dir))
    assert found == []


def test_iter_skips_readme_and_perturbations(tmp_path):
    """README.md/PERTURBATIONS.md — служебные файлы области без frontmatter
    (та же конвенция, что validate_frontmatter.py AREAS-скан)."""
    tc_dir = tmp_path / "test-cases" / "fake-area"
    tc_dir.mkdir(parents=True)
    (tc_dir / "README.md").write_text("# просто справка, без frontmatter\n", encoding="utf-8")
    # Не должно упасть на отсутствии frontmatter — файл пропускается целиком.
    found = list(_iter_automated_by(tc_dir))
    assert found == []
