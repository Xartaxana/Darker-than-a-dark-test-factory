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

Известные исключения (test debt, НЕ в скоупе C1 — см. финальный отчёт задачи):
framework/tests/test_smoke.py написан до принятия конвенции: 5 тест-функций без
@allure.id, и test_bottom_nav_switches_screens напрямую импортирует/использует
screens.LibraryScreen.by_text(...) в теле теста вместо steps-слоя. Занесено в
ALLOWLIST ниже с явным комментарием — почини отдельным тикетом (test-debt/B4,
docs/08 §3 B4), не в рамках этого чека.

Запуск:      python scripts/arch_check.py
Коды выхода: 0 — чисто (WARN/известные исключения допустимы), 1 — есть ERROR.
Только чтение framework/ — файлы не изменяются, идемпотентен.
"""
from __future__ import annotations

import argparse
import ast
import configparser
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

REPO = Path(__file__).resolve().parents[1]
FRAMEWORK = REPO / "framework"
TESTS_DIR = FRAMEWORK / "tests"
PYTEST_INI = FRAMEWORK / "pytest.ini"

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
# rule_id: "locators" | "allure_id".
ALLOWLIST: set[tuple[str, str]] = {
    ("tests/test_smoke.py", "locators"),
    ("tests/test_smoke.py", "allure_id"),
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


def run() -> tuple[list[str], list[str]]:
    """Возвращает (errors, warns). WARN — известные исключения из ALLOWLIST."""
    errors: list[str] = []
    warns: list[str] = []
    if not TESTS_DIR.exists():
        errors.append(f"framework/tests не найден по пути {TESTS_DIR}")
        return errors, warns

    for path in sorted(TESTS_DIR.rglob("test_*.py")):
        for finding in check_file(path):
            key = (finding.rel, finding.rule)
            if key in ALLOWLIST:
                warns.append(f"{finding.message} [известное исключение — test-debt, см. ALLOWLIST]")
            else:
                errors.append(finding.message)
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
