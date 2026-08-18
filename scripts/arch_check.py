"""arch_check — статические проверки архитектуры тест-фреймворка (docs/08 §4 C1).

Конвенция слоёв (framework/README.md, docs/02): tests -> steps -> screens/web ->
core. Слой tests/ — только шаги (steps) + assert, маркеры p0/p1/.../live/replay и
@allure.title. Локаторы (AppiumBy/UiSelector/By/EC) и прямой driver (driver_factory,
низкоуровневые find_element(s)) живут только в screens//web/. До сих пор это была
конвенция из README/докстрингов — здесь она превращается в исполняемую проверку
(docs/08 §4 C1: "Документы требуют tests -> steps -> screens/web -> core, но это
пока конвенция").

Проверяются все framework/tests/**/test_*.py (то же, что видит pytest — python_files
= test_*.py из framework/pytest.ini; conftest.py и __init__.py не тест-модули и не
сканируются, как и в самом pytest).

Правило 1 — NO-LOCATORS-IN-TESTS: тест-модуль не должен:
  - импортировать framework.screens.*, framework.web.*, framework.core.driver_factory,
    framework.core.waits, либо локаторные модули appium/selenium
    (AppiumBy/MobileBy/By/expected_conditions/ui.WebDriverWait);
  - вызывать методы-локаторы напрямую (find_element, find_elements, by_text,
    by_desc, by_text_contains — последние три объявлены в screens/base_screen.py);
  - содержать литеральную строку с "UiSelector(" (скопированный локатор мимо
    screens/), кроме docstring/комментария-строки.

Правило 2 — ALLURE-ID + SUITE MARKER: каждая тест-функция (def test_*, как задаёт
python_functions = test_*/python_classes = Test* в pytest.ini) обязана иметь:
  - декоратор @allure.id(...) (по нему тест-кейс TC-xxx привязывается к автотесту,
    см. test_rating.py/test_library.py);
  - хотя бы один suite-маркер уровня приоритета. Набор suite-маркеров выводится
    динамически из framework/pytest.ini (секция `markers`, имена вида p<N>: p0
    smoke, p1 регрессия, p2 расширенное покрытие, p3 косметика). Маркеры live/
    replay/quarantine — это режим прогона, а не suite, и не считаются.

test_smoke.py устранён (AT-BUG-002, test-debt/B4): импорты screens вынесены за
steps/, все 5 тестов имеют @allure.id. ALLOWLIST ниже содержит известные
исключения ОДНОГО легального класса — «device-free юнит-проба САМОГО
screens-класса» (категория установлена AT-BUG-059; C1 писан против
tests->локаторы мимо steps в ПРОДУКТОВЫХ тестах, а не против тестирования
самого screens-слоя). Каждая запись обязана называть тикет-источник и
обоснование; исключение ВНЕ этого класса — только с отдельным test-debt
тикетом, чей предмет и есть это исключение (решение Lead 2026-08-11 при
добавлении второй записи, AT-BUG-062).

Правило 3 — CASE-RECORDING-CONSISTENCY (mech-case-recording-check,
scratchpad/spec-case-recording-check.md v3): ВТОРАЯ ветвь обхода — test-cases/,
не framework/tests/. Сверяет replay-записи (`.mitm`), названные в секциях
Предусловий/Сценария кейса, с записями, которые реально берёт его
`automated_by`-тест (объединение значений `@pytest.mark.parametrize`, чей
argnames содержит `replay`). Отдельный WARNS-канал (см. `run_recording_rule`/
`run`) — находки не влияют на exit-код, до отдельного решения Lead о промоции
в ERROR по evidence.

Запуск:      python scripts/arch_check.py
Коды выхода: 0 — чисто (WARN/известные исключения допустимы), 1 — есть ERROR.
Только чтение framework/ + test-cases/ — файлы не изменяются, идемпотентен.
"""
from __future__ import annotations

import argparse
import ast
import configparser
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

REPO = Path(__file__).resolve().parents[1]
FRAMEWORK = REPO / "framework"
TESTS_DIR = FRAMEWORK / "tests"
PYTEST_INI = FRAMEWORK / "pytest.ini"
CASES_DIR = REPO / "test-cases"
RECORDING_BUILDER = FRAMEWORK / "data/recording_builder.py"

# --- Правило 1: запрещённые импорты слоя tests/ (см. докстринг модуля) ---
FORBIDDEN_IMPORT_PREFIXES = (
    "framework.screens",
    "framework.web",
    "framework.core.driver_factory",
    "framework.core.waits",
    "appium.webdriver.common.appiumby",
    "appium.webdriver.common.mobileby",
    "selenium.webdriver.common.by",
    "selenium.webdriver.support.expected_conditions",
    "selenium.webdriver.support.ui",
)

# Методы-локаторы: низкоуровневые (driver.find_element(s)) и фабрики screens/base_screen.py.
FORBIDDEN_CALL_ATTRS = {"find_element", "find_elements", "by_text", "by_desc", "by_text_contains"}

LOCATOR_LITERAL_NEEDLE = "UiSelector("

# Известные исключения (test debt, см. докстринг). Ключ: (rel_posix_из_framework, rule_id).
# rule_id — фактические значения Finding.rule по правилам 1-2-3: "locators" | "allure_id" |
# "marker" | "parse" | "recording". Пусто — устраняй причину, не добавляй сюда.
#
# ОТЛИЧИЕ ключа для rule_id="recording" (правило 3, CASE-RECORDING-CONSISTENCY):
# первый элемент кортежа — путь ОТ КОРНЯ РЕПО (например "test-cases/tabs/TC-176.md"),
# НЕ от framework/, как у "locators"/"allure_id" выше (см. спека
# scratchpad/spec-case-recording-check.md v3, раздел ALLOWLIST) — правило 3 обходит
# test-cases/, а не framework/tests/.
ALLOWLIST: set[tuple[str, str]] = {
    # AT-BUG-059 (Lead 2026-08-10): юнит-проба САМОГО BaseScreen (регресс-гвард
    # AT-BUG-048) — импорт screens по существу необходим для тестирования класса
    # screens-слоя; это НЕ обход layering продуктовым тестом (C1 писан против
    # tests->локаторы мимо steps). Перенос невозможен: сканер зеркалит
    # pytest testpaths (инвариант докстринга) — вне tests/ файл выпал бы из
    # штатного прогона.
    ("tests/test_swipe_to_text_settle_unit.py", "locators"),
    # AT-BUG-062 (test-maintainer rework attempt 2, критик-вход opus,
    # 2026-08-11): device-free юнит-проба verification-веток самого
    # `SettingsScreen.enter_rename_name`/`settings_steps.assert_filter_profile_listed`
    # (блокер «новые ветки отказа не исполнены ни разу» — импорт `SettingsScreen`
    # по существу необходим для тестирования конкретно ЭТОГО класса screens-слоя,
    # тот же случай, что AT-BUG-059/test_swipe_to_text_settle_unit.py выше;
    # перенос вне tests/ выпал бы из штатного прогона — тот же инвариант).
    ("tests/test_rename_name_verification_unit.py", "locators"),
    # AT-BUG-082 (test-maintainer rework attempt 2, критик-вход opus,
    # 2026-08-17): device-free юнит-проба `library_steps._poll_files_tab_absent`/
    # `assert_work_not_in_files_tab` мокает `LibraryScreen.has_work` НА УРОВНЕ
    # КЛАССА (не сам новый хелпер) — импорт `LibraryScreen` по существу
    # необходим для мока конкретно ЭТОГО класса screens-слоя, тот же случай,
    # что AT-BUG-059/AT-BUG-062 выше; перенос вне tests/ выпал бы из штатного
    # прогона (тот же инвариант — сканер зеркалит pytest testpaths).
    ("tests/test_library_files_tab_settle_unit.py", "locators"),
}


class Finding:
    __slots__ = ("rel", "rule", "message")

    def __init__(self, rel: str, rule: str, message: str):
        self.rel = rel
        self.rule = rule
        self.message = message


def load_suite_markers(pytest_ini: Path = PYTEST_INI) -> set[str]:
    """Suite-маркеры (p0/p1/...) из framework/pytest.ini — динамически, а не хардкодом.

    live/replay/quarantine и т.п. — режим прогона, не suite, и в набор не входят.
    """
    if not pytest_ini.exists():
        return {"p0", "p1", "p2", "p3"}
    parser = configparser.ConfigParser()
    try:
        parser.read(pytest_ini, encoding="utf-8")
        raw = parser.get("pytest", "markers", fallback="")
    except configparser.Error:
        return {"p0", "p1", "p2", "p3"}
    markers = set()
    for line in raw.splitlines():
        name = line.strip().split(":", 1)[0].strip()
        if re.fullmatch(r"p\d+", name):
            markers.add(name)
    return markers or {"p0", "p1", "p2", "p3"}


def _decorator_dotted(dec: ast.expr) -> str:
    """`@allure.id(...)` -> "allure.id"; `@pytest.mark.p0` -> "pytest.mark.p0"."""
    node = dec
    if isinstance(node, ast.Call):
        node = node.func
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _test_functions(tree: ast.Module) -> list[ast.FunctionDef]:
    """Тест-функции верхнего уровня (`def test_*`) и методы `Test*`-классов —
    то же, что подхватит pytest при python_functions=test_*/python_classes=Test*.
    """
    out: list[ast.FunctionDef] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            out.append(node)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name.startswith("test_"):
                    out.append(sub)
    return out


def _is_docstring_expr(node: ast.stmt) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def _iter_non_docstring_string_constants(tree: ast.Module):
    """ast.Constant(str) по всему модулю, исключая докстринги модуля/функций/классов
    (первый Expr(Constant(str)) в теле блока) — чтобы прозе в докстрингах не триггерить
    LOCATOR_LITERAL_NEEDLE.
    """
    docstring_ids = set()
    blocks = [tree] + [n for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    for block in blocks:
        body = getattr(block, "body", None)
        if body and _is_docstring_expr(body[0]):
            docstring_ids.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstring_ids:
            yield node


def check_locators(tree: ast.Module, rel: str) -> list[Finding]:
    findings: list[Finding] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(alias.name == p or alias.name.startswith(p + ".") for p in FORBIDDEN_IMPORT_PREFIXES):
                    findings.append(Finding(rel, "locators",
                        f"framework/{rel}:{node.lineno}: запрещённый импорт `{alias.name}` в tests/ "
                        f"(локаторы/driver — только в screens/web, см. docs/08 C1)"))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if any(node.module == p or node.module.startswith(p + ".") for p in FORBIDDEN_IMPORT_PREFIXES):
                findings.append(Finding(rel, "locators",
                    f"framework/{rel}:{node.lineno}: запрещённый импорт `from {node.module} import ...` "
                    f"в tests/ (локаторы/driver — только в screens/web, см. docs/08 C1)"))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in FORBIDDEN_CALL_ATTRS:
                findings.append(Finding(rel, "locators",
                    f"framework/{rel}:{node.lineno}: вызов `.{node.func.attr}(...)` — локатор/driver-примитив "
                    f"в tests/, должен быть скрыт за steps/screens (см. docs/08 C1)"))

    for node in _iter_non_docstring_string_constants(tree):
        if LOCATOR_LITERAL_NEEDLE in node.value:
            findings.append(Finding(rel, "locators",
                f"framework/{rel}:{node.lineno}: литеральная строка локатора "
                f"(`{LOCATOR_LITERAL_NEEDLE}...`) в tests/ (см. docs/08 C1)"))

    return findings


def check_allure_and_markers(tree: ast.Module, rel: str, suite_markers: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    for fn in _test_functions(tree):
        dotted = [_decorator_dotted(d) for d in fn.decorator_list]
        if "allure.id" not in dotted:
            findings.append(Finding(rel, "allure_id",
                f"framework/{rel}:{fn.lineno}: тест `{fn.name}` без @allure.id(...) "
                f"— не привязан к тест-кейсу TC-xxx"))
        hit_markers = {d.rsplit(".", 1)[-1] for d in dotted if d.startswith("pytest.mark.")}
        if not (hit_markers & suite_markers):
            findings.append(Finding(rel, "marker",
                f"framework/{rel}:{fn.lineno}: тест `{fn.name}` без suite-маркера "
                f"({'/'.join(sorted(suite_markers))})"))
    return findings


def check_file(path: Path) -> list[Finding]:
    rel = path.relative_to(FRAMEWORK).as_posix()
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        return [Finding(rel, "parse", f"framework/{rel}: не удалось разобрать файл ({exc})")]
    findings = check_locators(tree, rel)
    findings += check_allure_and_markers(tree, rel, load_suite_markers())
    return findings


# --- Правило 3: CASE-RECORDING-CONSISTENCY (см. докстринг модуля + спека
# scratchpad/spec-case-recording-check.md v3). Обход test-cases/, отдельный
# WARNS-канал (см. `run`). ---

_AUTOMATED_BY_RE = re.compile(r'^automated_by:\s*"?(.*?)"?\s*$', re.M)
_MITM_TOKEN_RE = re.compile(r"[\w.-]+\.mitm")
_RB_CONST_TOKEN_RE = re.compile(r"\brb\.([A-Za-z_][A-Za-z0-9_]*)\b")
_BARE_CONST_TOKEN_RE = re.compile(r"\b([A-Z][A-Z0-9_]*_FILENAME)\b")
_SECTION_PREFIXES = ("## Предусловия", "## Сценарий")

# Возвращается `_resolve_test_function`, когда файл automated_by существует, но
# не разбирается (SyntaxError/UnicodeDecodeError) — правило 3 в этом случае молчит:
# ошибку парсинга уже несёт существующий Finding класса "parse" правил 1-2 (тот же
# framework/tests/**/test_*.py обходится обоими правилами) — не дублируем.
#
# ОСТАТОЧНАЯ ДЫРА (Ф1, критик-вход attempt 2, признана и НЕ закрыта в этом ходе):
# если automated_by указывает НА ФАЙЛ ВНЕ глоба test_*.py, который обходят правила
# 1-2 (`TESTS_DIR.rglob("test_*.py")` — например `framework/tests/conftest.py::x`,
# схема test-case.schema.yaml такую форму automated_by не запрещает), то при
# SyntaxError ЭТОГО файла ни правило 1-2 (файл не в их обходе), ни правило 3 (эта
# ветка, молчит намеренно) находки не дадут — молчаливый провал без ERROR/WARN. В
# корпусе такой automated_by не встречается (единственная живая форма — путь на
# test_*.py, см. докстринг модуля/спеку); закрытие — по evidence, не заранее
# (F-11 (в), CLAUDE.md).
_PARSE_ERROR = object()


def _module_string_consts(tree: ast.Module) -> dict[str, str]:
    """Модульные присваивания вида `NAME = "литерал"` — тот же приём для
    framework/data/recording_builder.py и для самого тест-файла (голый `<CONST>`
    резолвится по константам файла, где записан тест — см. спеку)."""
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value.value
    return out


def _load_recording_builder_consts() -> dict[str, str]:
    if not RECORDING_BUILDER.exists():
        return {}
    try:
        tree = ast.parse(RECORDING_BUILDER.read_text(encoding="utf-8"), filename=str(RECORDING_BUILDER))
    except (SyntaxError, UnicodeDecodeError):
        return {}
    return _module_string_consts(tree)


def _scoped_lines(text: str) -> list[tuple[int, str]]:
    """Строки секций `## Предусловия`/`## Сценарий` (префиксное совпадение
    заголовка — суффиксы вроде `## Предусловия — БЛОКЕР (…)` тоже считаются).
    Секция обрывается СЛЕДУЮЩИМ заголовком `## ` (ровно 2 `#`); `### `-подсекции
    (3+ `#`) заголовком верхнего уровня не являются и секцию не обрывают."""
    out: list[tuple[int, str]] = []
    keep = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.startswith("## "):
            keep = line.startswith(_SECTION_PREFIXES)
            continue
        if keep:
            out.append((lineno, line))
    return out


def _case_mentions(text: str, rb_consts: dict[str, str]) -> tuple[set[str], int | None]:
    """`mentions` кейса + номер строки ПЕРВОГО упоминания (любого вида), только
    из секций Предусловий/Сценария (нарратив прочих секций не сверяется)."""
    mentions: set[str] = set()
    first_line: int | None = None
    for lineno, line in _scoped_lines(text):
        hit = False
        for tok in _MITM_TOKEN_RE.findall(line):
            norm = tok.lstrip(".-")
            if len(norm) > len(".mitm"):  # пустое/голое имя (напр. голый `.mitm`) отбрасывается
                mentions.add(norm)
                hit = True
        for name in _RB_CONST_TOKEN_RE.findall(line):
            if name in rb_consts:
                mentions.add(rb_consts[name])
                hit = True
        for name in _BARE_CONST_TOKEN_RE.findall(line):
            if name in rb_consts:
                mentions.add(rb_consts[name])
                hit = True
        if hit and first_line is None:
            first_line = lineno
    return mentions, first_line


def _split_automated_by(automated_by: str) -> tuple[str, list[str]] | None:
    """`<путь>::<функция>` (единственная живая форма) и `<путь>::Class::method`/
    `...[param]`-суффикс (на вырост, спекуляция — см. спеку)."""
    without_param = automated_by.split("[", 1)[0]
    parts = without_param.split("::")
    if len(parts) < 2 or not parts[0] or not all(parts[1:]):
        return None
    return parts[0], parts[1:]


def _resolve_test_function(rel_path: str, name_parts: list[str]):
    """`(fn, tree)` тест-функции; `None` — automated_by не разрешается;
    `_PARSE_ERROR` — файл есть, но не разбирается (см. докстринг `_PARSE_ERROR`)."""
    fpath = REPO / rel_path
    if not fpath.exists():
        return None
    try:
        tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=str(fpath))
    except (SyntaxError, UnicodeDecodeError):
        return _PARSE_ERROR

    if len(name_parts) == 1:
        (func_name,) = name_parts
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                return node, tree
        return None
    if len(name_parts) == 2:
        class_name, func_name = name_parts
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == func_name:
                        return sub, tree
        return None
    return None  # форма с >2 сегментов после "::" не поддерживается


def _resolve_param_value(node: ast.expr, module_consts: dict[str, str], rb_consts: dict[str, str]) -> tuple[str | None, str | None]:
    """`(значение, None)` при успехе, `(None, причина)` при неразрешимом узле —
    НИКОГДА не бросает исключение (Ф1: произвольный узел -> находка, не падение)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, None
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "rb":
        if node.attr in rb_consts:
            return rb_consts[node.attr], None
        return None, f"rb.{node.attr} не резолвится по recording_builder.py"
    if isinstance(node, ast.Name):
        if node.id in module_consts:
            return module_consts[node.id], None
        return None, f"{node.id} не резолвится по модульным константам тест-файла"
    return None, "неразрешимый узел параметризации"


def _collect_recordings(fn, module_consts: dict[str, str], rb_consts: dict[str, str]) -> tuple[set[str], list[str]]:
    """Объединение значений replay из ВСЕХ `@pytest.mark.parametrize`, чей
    argnames содержит `replay` (позиционный резолв мульти-argnames и
    `pytest.param`, `indirect=` на резолв не влияет — см. спеку)."""
    recordings: set[str] = set()
    unresolved: list[str] = []
    for dec in fn.decorator_list:
        if not isinstance(dec, ast.Call) or _decorator_dotted(dec) != "pytest.mark.parametrize":
            continue
        if not dec.args:
            # Ф5 (fail-closed, критик-вход attempt 2, Lead: kwargs не резолвим —
            # формы `parametrize(argnames=..., argvalues=...)` в корпусе нет):
            # позиционных args нет, argnames переданы именованно — не знаем, содержит
            # ли он "replay", молчаливый пропуск был бы дырой, кладём находку.
            unresolved.append("parametrize вызван с именованными аргументами (argnames=/argvalues=) — не резолвится")
            continue
        argnames_node = dec.args[0]
        names: list[str] | None = None
        if isinstance(argnames_node, ast.Constant) and isinstance(argnames_node.value, str):
            names = [n.strip() for n in argnames_node.value.split(",")]
        elif isinstance(argnames_node, (ast.List, ast.Tuple)):
            collected: list[str] = []
            for el in argnames_node.elts:
                if isinstance(el, ast.Constant) and isinstance(el.value, str):
                    collected.append(el.value.strip())
                else:
                    collected = []
                    break
            names = collected or None
        if not names or "replay" not in names:
            continue
        idx = names.index("replay")
        if len(dec.args) < 2 or not isinstance(dec.args[1], (ast.List, ast.Tuple)):
            unresolved.append("значения parametrize не литерал списка/кортежа")
            continue
        for row in dec.args[1].elts:
            if isinstance(row, ast.Call) and _decorator_dotted(row) == "pytest.param":
                if idx >= len(row.args):
                    unresolved.append("pytest.param без позиционного аргумента replay")
                    continue
                value_node = row.args[idx]
            elif len(names) == 1:
                value_node = row
            elif isinstance(row, (ast.Tuple, ast.List)):
                if idx >= len(row.elts):
                    unresolved.append("индекс replay вне диапазона строки параметризации")
                    continue
                value_node = row.elts[idx]
            else:
                unresolved.append("строка параметризации не кортеж/список/pytest.param")
                continue
            value, err = _resolve_param_value(value_node, module_consts, rb_consts)
            if err:
                unresolved.append(err)
            else:
                recordings.add(value)
    return recordings, unresolved


def _process_case(path: Path, rb_consts: dict[str, str]) -> Finding | None:
    """Один вердикт на кейс (ветви — см. спеку, порядок явный): mentions=∅ ->
    молчание ВСЕГДА (веха 1, до любых прочих проверок); иначе automated_by
    не разрешается / неразрешимая параметризация / recordings⊄mentions
    (лишние записи) / mentions без recordings без live (кейс называет,
    тест не берёт) / чисто."""
    rel = path.relative_to(REPO).as_posix()
    text = path.read_text(encoding="utf-8")
    m = _AUTOMATED_BY_RE.search(text)
    automated_by = m.group(1).strip() if m else ""
    if not automated_by:
        return None
    ab_line = text[: m.start()].count("\n") + 1

    mentions, mention_line = _case_mentions(text, rb_consts)
    if not mentions:
        return None  # ветвь 1: правило молчит всегда

    split = _split_automated_by(automated_by)
    resolved = _resolve_test_function(*split) if split else None
    if split is None or resolved is None:
        return Finding(rel, "recording",
            f"{rel}:{ab_line}: automated_by `{automated_by}` не разрешается — "
            f"сверка невозможна (кейс называет {sorted(mentions)})")
    if resolved is _PARSE_ERROR:
        return None  # существующий Finding класса parse правил 1-2 уже покрывает файл

    fn, tree = resolved
    module_consts = _module_string_consts(tree)
    recordings, unresolved = _collect_recordings(fn, module_consts, rb_consts)
    func_label = automated_by.split("[", 1)[0]

    if unresolved:
        return Finding(rel, "recording",
            f"{rel}:{ab_line}: неразрешимая параметризация replay в `{func_label}` "
            f"({'; '.join(unresolved)}) — кейс называет {sorted(mentions)}")

    if recordings and not recordings <= mentions:
        return Finding(rel, "recording",
            f"{rel}:{ab_line}: тест `{func_label}` берёт записи {sorted(recordings)}, "
            f"кейс их не называет (кейс называет {sorted(mentions)})")

    is_live = any(_decorator_dotted(d) == "pytest.mark.live" for d in fn.decorator_list)
    if not recordings and not is_live:
        line = mention_line if mention_line is not None else ab_line
        return Finding(rel, "recording",
            f"{rel}:{line}: кейс называет replay-записи {sorted(mentions)}, "
            f"тест `{func_label}` replay не берёт")

    return None  # ветвь 4: чисто (в т.ч. надмножество mentions)


def run_recording_rule() -> list[Finding]:
    """Правило 3 по test-cases/ (см. докстринг блока выше). Всегда WARNS —
    вызывающая сторона (`run`) не кладёт находки в errors."""
    if not CASES_DIR.exists():
        return []
    rb_consts = _load_recording_builder_consts()
    findings: list[Finding] = []
    for path in sorted(CASES_DIR.rglob("*.md")):
        finding = _process_case(path, rb_consts)
        if finding is not None:
            findings.append(finding)
    return findings


def run() -> tuple[list[str], list[str]]:
    """Возвращает (errors, warns). WARN — известные исключения из ALLOWLIST (правила
    1-2) либо ЛЮБАЯ находка правила 3 (см. `run_recording_rule` — отдельный
    warns-канал, exit-код не меняется)."""
    errors: list[str] = []
    warns: list[str] = []
    if not TESTS_DIR.exists():
        errors.append(f"framework/tests не найден по пути {TESTS_DIR}")
    else:
        for path in sorted(TESTS_DIR.rglob("test_*.py")):
            for finding in check_file(path):
                key = (finding.rel, finding.rule)
                if key in ALLOWLIST:
                    warns.append(f"{finding.message} [известное исключение — test-debt, см. ALLOWLIST]")
                else:
                    errors.append(finding.message)

    # Правило 3 (ВТОРАЯ ветвь обхода, test-cases/) — независима от TESTS_DIR;
    # ВСЕГДА warns, никогда errors (Б7).
    for finding in run_recording_rule():
        key = (finding.rel, finding.rule)
        message = f"rule3: {finding.message}"
        if key in ALLOWLIST:
            warns.append(f"{message} [известное исключение — см. ALLOWLIST]")
        else:
            warns.append(message)

    return errors, warns


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Статический чек архитектуры тест-фреймворка (docs/08 C1): "
                    "запрет driver/локаторов в tests/, обязательные allure.id и suite-маркер")
    parser.add_argument("--no-warns", action="store_true", help="не печатать WARN")
    args = parser.parse_args(argv)

    errors, warns = run()
    for e in errors:
        print(f"  [ERROR] {e}")
    if not args.no_warns:
        for w in warns:
            print(f"  [WARN] {w}")
    print(f"arch_check: ошибок {len(errors)}, предупреждений {len(warns)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
