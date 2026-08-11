---
id: AT-BUG-059
title: "arch_check C1: юнит-тест импортирует framework.screens.base_screen в недопустимой локации (запрет docs/08 C1)"
type: test_debt
debt_kind: broken_environment
severity: minor
status: Verified
found_in: "framework commit 1ff003d"
fixed_in: "9247929 (ALLOWLIST arch_check, применил Lead по рекомендации test-maintainer)"
last_seen_in: ""
test_cases: []
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-11T00:02:00Z"
updated: "2026-08-11T00:02:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
---

# AT-BUG-059 — Импорт framework.screens.base_screen в юнит-тесте нарушает arch_check C1

## Окружение
- Файл: `framework/tests/test_swipe_to_text_settle_unit.py`
- Коммит: 1ff003d (юнит для фикса AT-BUG-048)
- Правило: docs/08 §C1 — локаторы и driver доступны только в `screens/`, не в `tests/`

## Проблема
Файл импортирует framework.screens:

```python
from framework.screens import base_screen
from framework.screens.base_screen import BaseScreen
```

Это нарушает arch_check C1, которое запрещает прямые импорты модулей с локаторами в пакет `tests/`. Правило введено для:
- Разделения ответственности (tests содержат логику шагов, не селекторов)
- Облегчения рефакторинга локаторов (изменения в screens/ не требуют правок в tests/)

## Контекст
Юнит-тест `test_swipe_to_text_settle_unit.py` — device-free проба фикса AT-BUG-048. Файл импортирует BaseScreen ДЛЯ НУЖД ТЕСТА (потестировать сам BaseScreen, а не через шаги), что делает этот импорт по существу обоснованным.

## Кандидаты фикса (решает test-maintainer / Lead)

1. **ALLOWLIST-исключение arch_check C1** — добавить явное исключение для этого файла:
   - Плюс: сохраняет тест на месте
   - Минус: требует документирования причины исключения в scripts/arch_check.py или docs/08

2. **Перенос юнит-теста в разрешённую локацию** — переместить тест в `framework/screens/tests/` (если такая директория есть) или в `framework/tests/unit-screens/`:
   - Плюс: сохраняет архитектурное правило без исключений
   - Минус: возможно, требует пересоздания фикстур

**Не требуется:** изменение самого кода AT-BUG-048 фикса (он в screens/ и arch_check ему не мешает).

## Верификация
| Дата | Версия сборки | Решение | Статус |
|---|---|---|---|
| 2026-08-10 | framework commit `9247929` (ALLOWLIST-исключение `("tests/test_swipe_to_text_settle_unit.py", "locators")` в `scripts/arch_check.py`, внёс Lead по рекомендации test-maintainer, см. Обсуждение) | ALLOWLIST-исключение (кандидат 1) | Fixed |
| 2026-08-11 | framework HEAD `d70f17e` (потомок fix-коммита `9247929`, `git log -1 -- scripts/arch_check.py` подтверждает `9247929` как последнюю правку файла) | Документная верификация (test_debt/broken_environment, устройство не требуется): `python scripts/arch_check.py` → `[WARN] framework/tests/test_swipe_to_text_settle_unit.py:43 ...` / `:44 ...` (обе строки дословно совпадают с зафиксированными в реплике test-maintainer 2026-08-10T13:40:00Z), `arch_check: ошибок 0, предупреждений 2`. `Invoke-Pytest tests/test_swipe_to_text_settle_unit.py -q` → `.....` (5 dots), `5 passed in 0.09s`, `PYTEST_EXIT=0`. `test_cases: []` — carve-out test_debt/broken_environment (DoD бага не содержит отдельной демонстрации сверх этих двух команд — они и есть DoD, буквально исполнены живым прогоном). | Verified |

## Обсуждение

**[test-maintainer @ 2026-08-10T13:25:00Z]** Исследовал оба кандидата (перенос — мой ярус;
ALLOWLIST — только предложение, правку `scripts/arch_check.py` не вношу, механизм за Lead).
**Вывод: кандидат 2 (перенос) структурно невозможен без потери покрытия, кандидат 1
(ALLOWLIST) — правильный путь.** Обоснование:

1. `arch_check.py` сканирует `TESTS_DIR.rglob("test_*.py")`, где `TESTS_DIR = framework/tests`
   — РЕКУРСИВНО, включая любые поддиректории (`framework/tests/canary/` тоже сканируется и
   тоже под запретом C1 — проверил `test_ao3_selectors.py`/`test_tap_zone_guard.py` там).
   `pytest.ini` (`testpaths = tests`, `python_files = test_*.py`) даёт РОВНО ТОТ ЖЕ набор файлов
   — это не совпадение, а декларированный инвариант в самом докстринге `arch_check.py`
   (строка 11: «то же, что видит pytest»). Следствие: **любая поддиректория внутри
   `framework/tests/` одинаково видна и pytest'у (по умолчанию), и arch_check** — переноса
   «в разрешённую локацию внутри tests/» не существует в принципе, оба кандидата в теле бага
   (`framework/screens/tests/`, `framework/tests/unit-screens/`) я проверил: второй остаётся
   под `TESTS_DIR.rglob` и ничего не даёт, первый — единственный вариант вне дерева tests/.
2. Перенос ЗА пределы `framework/tests/` (напр. `framework/screens/tests/`) действительно
   выводит файл из-под `arch_check` (у него сканируется только `TESTS_DIR`), но при этом
   выпадает из `testpaths = tests` — голый `Invoke-Pytest` (полный regression/CI-прогон)
   ПЕРЕСТАНЕТ подбирать этот файл по умолчанию. Чтобы вернуть его в постоянный прогон, нужно
   расширять `pytest.ini` (`testpaths`) — это не в `owns` этого диспатча (только
   `framework/tests/*`), и само по себе является правкой конвенции «что входит в regression
   по умолчанию» для всех будущих сессий — тот же класс машинной проверки, что и
   `arch_check.py`, я его тоже не трогаю без решения Lead. Без этой правки перенос молча
   вынимает регресс-гвард AT-BUG-048 из дерева, которое реально гоняется — это прямо
   противоречит цели файла («новый device-free регресс-гвард добавлен в дерево ПОСТОЯННО»,
   AT-BUG-048 чеклист).
3. Проверил конвенцию по прецеденту: `grep` по `framework/tests/**` на прямой импорт
   `framework.screens`/`framework.web` — единственное совпадение это сам файл. Три соседних
   «unit»-файла того же семейства (`test_wait_memory_settled_diagnostics_unit.py`,
   `test_assert_filter_profile_count_diagnostics_unit.py`,
   `test_wait_persisted_tab_count_diagnostics_unit.py`) тестируют функции `steps/`/`core/adb`
   МОНКИПАТЧЕМ, не заходя в `screens/` — они в принципе другого класса (юнит шага/утилиты, не
   юнит самого Screen Object). Прецедента «юнит слоя screens/, легально живущий в
   `framework/tests/`» в репо нет — это первый файл такого типа, конфликт с C1 не «забытый
   случай», а структурный: C1 писался для функциональных тестов (`tests -> steps -> screens`,
   запрет писателю продуктового теста обходить `steps` и лезть в локаторы напрямую, см. docs/08
   C1), а не для юнит-пробы самого `screens`-слоя, которой ИМЕННО НУЖНО импортировать
   тестируемый класс.
4. Не пытался обойти проверку синтаксически (например, `importlib.import_module` вместо
   `from framework.screens import ...`) — это была бы маскировка причины (запрещено моей
   ролью), а не починка: физический факт остаётся «tests/ содержит модуль, тестирующий
   screens/» — тот же смысл, что и запрещённый импорт, просто невидимый AST-чекеру.

**Рекомендация: ALLOWLIST-исключение в `scripts/arch_check.py`.** Конкретно — ключ
`("tests/test_swipe_to_text_settle_unit.py", "locators")` в `ALLOWLIST` (docstring модуля уже
описывает этот механизм: «известные исключения — test-debt, см. ALLOWLIST»; AT-BUG-059 — тот
самый «отдельный test-debt тикет», который докстринг требует для нового исключения, строка 34
`scripts/arch_check.py`). Рядом стоит обосновать в самом файле, почему это исключение отличается
от продуктовых тестов: «юнит-проба самого BaseScreen (AT-BUG-048) — импорт по существу
необходим для тестирования класса screens-слоя, не обход layering продуктовым тестом».

Задачу возвращаю (лок снят, статус Open не менян — фикс не внесён). Дифф не создавался
(не трогал ни `framework/tests/*`, ни `scripts/arch_check.py`, ни `bugs/AT-BUG-048.md` — правка
путей файла AT-BUG-048 не нужна, файл остаётся на месте).

**[test-maintainer @ 2026-08-10T13:40:00Z]** Fixed. Lead внёс ALLOWLIST-исключение
`("tests/test_swipe_to_text_settle_unit.py", "locators")` в `scripts/arch_check.py` коммитом
`9247929` (по рекомендации из предыдущей реплики). Закрываю жизненный цикл своим witness (не
пересказ Lead'а):
- `python scripts/arch_check.py` →
  ```
  [WARN] framework/tests/test_swipe_to_text_settle_unit.py:43: запрещённый импорт `from framework.screens import ...` в tests/ (локаторы/driver — только в screens/web, см. docs/08 C1) [известное исключение — test-debt, см. ALLOWLIST]
  [WARN] framework/tests/test_swipe_to_text_settle_unit.py:44: запрещённый импорт `from framework.screens.base_screen import ...` в tests/ (локаторы/driver — только в screens/web, см. docs/08 C1) [известное исключение — test-debt, см. ALLOWLIST]
  arch_check: ошибок 0, предупреждений 2
  ```
  (было: ошибок 2, предупреждений 0 — теперь оба нарушения C1 переведены в известное
  WARN-исключение, EXIT=0).
- `powershell -NoProfile -ExecutionPolicy Bypass -Command ". D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest tests/test_swipe_to_text_settle_unit.py -q"` →
  `.....` (5 dots), `5 passed in 0.08s`, `PYTEST_EXIT=0` — файл не трогался, остался на месте
  (`framework/tests/test_swipe_to_text_settle_unit.py`), все 5 сценариев регресс-гварда
  AT-BUG-048 по-прежнему зелёные.

Файл не переносился (никакого диффа в `framework/tests/*` этой сессией — предыдущая реплика
это уже фиксировала). `status: Open → Fixed`. Лок не переустанавливался (был уже снят
предыдущей репликой).

**[fix-verifier @ 2026-08-11T00:02:00Z]** Верификация mode=verify (D1). `test_cases: []` —
штатный carve-out для `type: test_debt` в инфраструктуре (docs/06, прецеденты AT-BUG-007/011/
012/013/014/017/025/027/031): у долга «ALLOWLIST-исключение arch_check» привязываемых TC не
существует в принципе. Замена — DoD-демонстрация из тела бага исполнена буквально живым
прогоном (не чтением/пересказом кода): обе команды DoD прогнаны сейчас на HEAD `d70f17e`
(потомок fix-коммита `9247929`, сверено `git log -1 -- scripts/arch_check.py`), вывод дословно
совпал с ожидаемым по DoD и с зафиксированным в реплике test-maintainer 2026-08-10. Устройство
не требовалось (test_debt/broken_environment, документная верификация). `status: Fixed →
Verified`, `known_issue` уже `"false"` (изменений не требует).

## Чек-лист качества
- [x] Проверено нарушение правила (docs/08 C1 и arch_check вывод)
- [x] Обоснована необходимость (тест нуждается в прямом импорте для проверки BaseScreen)
- [x] Предложены два кандидата фикса без самостоятельного исполнения (по конвенции bug-reporter)
- [x] Ни одно изменение не внесено в код
