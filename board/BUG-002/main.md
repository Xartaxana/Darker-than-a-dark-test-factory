---
key: "BUG-002"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p2"
summary: "test_smoke.py нарушает архитектуру фреймворка: локаторы/импорты screens в tests/, 5 тестов без @allure.id"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-001", "test_case:TC-002", "test_case:TC-003", "test_case:TC-004", "test_case:TC-005", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-07T20:05:00Z"
updated: "2026-07-07T20:05:00Z"
archived: false
resolution: "done"
---

# test_smoke.py нарушает архитектуру фреймворка: локаторы/импорты screens в tests/, 5 тестов без @allure.id

_Спроецировано из `bugs/BUG-002.md` (источник правды).
Статус в нашей машине: **Verified**._

# BUG-002 — test_smoke.py нарушает архитектуру фреймворка (C1)

## Окружение
- Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`),
  найден статическим чеком `scripts/arch_check.py` (C1, docs/08 §4) при внедрении.

## Суть долга

`framework/tests/test_smoke.py` написан до конвенции слоёв (docs/02, docs/08 C1)
и зафиксирован в `ALLOWLIST` внутри `arch_check.py` как известное исключение
(8 [WARN] вместо ошибок). Полный список нарушений:

1. Строка 13: импорт `framework.screens.settings_screen` в tests/ — локаторы и
   screen-объекты должны быть скрыты за steps/.
2. Строка 39: импорт `framework.screens.library_screen` в tests/.
3. Строка 41: вызов `.by_text(...)` — локатор-примитив прямо в теле теста
   (`test_bottom_nav_switches_screens`).
4. Строки 20/30/50/60/74: пять тестов без `@allure.id(...)` — не привязаны к
   тест-кейсам TC-xxx (нет traceability):
   `test_app_launches_and_loads_ao3`, `test_bottom_nav_switches_screens`,
   `test_seeded_work_appears_in_correct_tab`, `test_clear_all_ratings`,
   `test_theme_toggle_stable`.

## Критерий готовности (Fixed)

- Импорты screens и `.by_text` вынесены из tests/ в слой steps (существующие
  step-функции переиспользованы, новые добавлены при нехватке).
- Каждому smoke-тесту сопоставлен TC (существующий или заведённый test-designer'ом)
  и проставлен `@allure.id`.
- Пары `(test_smoke.py, правило)` УДАЛЕНЫ из `ALLOWLIST` в `scripts/arch_check.py`;
  `python scripts/arch_check.py` — 0 ошибок и 0 предупреждений.
- Smoke-suite зелёный 3 прогона подряд (критерий test-maintainer).

## Анализ

Долг заведён при внедрении C1 (arch_check) — не регрессия, а легализация
существовавшего с первых smoke-тестов отступления. Чинит test-maintainer по
правилу «Устранить test debt» (B4); Fixed не ждёт сборку приложения.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-07-07T20:05:00Z | app 1.10/versionCode 11 (com.example.ao3_wrapper, apk_sha256 6455af0c...87544, эмулятор ao3_test_api34); framework: working tree поверх commit 59696df (test_debt-фикс не требует новой сборки приложения, B4) | `python scripts/arch_check.py` (статика) + `pytest framework/tests/test_smoke.py -v` (TC-001..TC-005, live) | arch_check: 0 ошибок, 0 предупреждений (нет импортов `framework.screens.*`/`.by_text` в test_smoke.py, все 5 тестов с `@allure.id`); pytest: 9/9 passed за 219.91s (TC-003 параметризован на 5 кейсов) | Fixed → Verified |

## Обсуждение

**2026-07-07T20:05:00Z — fix-verifier:** Независимая верификация подтверждает фикс.
- Статика: `python scripts/arch_check.py` → `ошибок 0, предупреждений 0`. Прочитан
  `framework/tests/test_smoke.py` целиком — импортов `framework.screens.settings_screen`/
  `library_screen` и вызовов `.by_text(...)` нет, у всех 5 тестов проставлен
  `@allure.id("TC-00{1..5}")`, соответствующий `automated_by` в `test-cases/smoke/TC-00{1..5}.md`.
- Динамика: эмулятор `ao3_test_api34` и Appium (порт 4723) уже были подняты (унаследовано
  от прогона test-maintainer'а) — переиспользованы без пересоздания. Проверена версия
  приложения на устройстве: `versionName=1.10 versionCode=11` — совпадает с
  `state/app-under-test.yaml`. `pytest framework/tests/test_smoke.py -v --alluredir=allure-results-verify`
  (AO3_MODE=live) → `9 passed in 219.91s`, ни одного падения/ретрая.
- Изменения не закоммичены (working tree diff поверх `59696df`) — `fixed_in` указывает
  на diff, не на commit hash; при коммите значение стоит уточнить.
- `app-under-test/` не трогался.
- Вердикт: `status: Fixed → Verified`.

**2026-07-07T19:45:00Z — test-maintainer:** Долг устранён.
- `framework/steps/library_steps.py`: добавлен `assert_library_loaded(driver)`
  (виден таб FAVORITE — та же проверка `by_text("FAVORITE")`/timeout=8, что была
  инлайн в тесте, теперь за `LibraryScreen.has_work`).
- `framework/steps/settings_steps.py`: `assert_settings_loaded` переиспользован в
  `test_theme_toggle_stable` (был инлайн `SettingsScreen(driver).is_loaded()` без
  сообщения об ошибке — теперь тот же чек с assert-сообщением, поведение не менялось).
- `framework/tests/test_smoke.py`: убраны импорты `framework.screens.settings_screen`
  и `framework.screens.library_screen`, убран инлайн-вызов `.by_text(...)`; всем 5
  тестам проставлены `@allure.id("TC-00{1..5}")` по существующей привязке из
  `test-cases/smoke/TC-00{1..5}.md` (`automated_by` уже указывал на эти тесты).
- `scripts/arch_check.py`: `ALLOWLIST` очищен (пары `test_smoke.py`×`locators`/
  `allure_id` удалены), докстринг обновлён. `python scripts/arch_check.py` → 0
  ошибок, 0 предупреждений.
- Прогон `pytest tests/test_smoke.py -v` (live, AO3_MODE=live) — 9/9 зелёных, 3
  раза подряд. Первая попытка прогона (до устоявшегося состояния эмулятора)
  словила транзитный host-level ANR SystemUI («System UI isn't responding»,
  проверено дампом `uiautomator dump`: под WebView приложения всё было отрисовано
  штатно) — не связано с рефакторингом теста и не с app-under-test; после
  дисмисса ANR все последующие прогоны стабильно зелёные.
- `app-under-test/` не трогался.
