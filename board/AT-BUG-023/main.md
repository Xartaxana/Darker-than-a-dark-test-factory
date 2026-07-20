---
key: "AT-BUG-023"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p0"
summary: "2 P0 canary tests не запускаются: отсутствуют фикстуры disliked_work_with_comment_seeded и disliked_work_with_custom_tag_seeded в conftest.py"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-075", "test_case:TC-077", "sev:critical"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-20T00:00:00Z"
updated: "2026-07-20T00:00:00Z"
archived: false
resolution: null
---

# 2 P0 canary tests не запускаются: отсутствуют фикстуры disliked_work_with_comment_seeded и disliked_work_with_custom_tag_seeded в conftest.py

_Спроецировано из `bugs/AT-BUG-023.md` (источник правды).
Статус в нашей машине: **Open**._

# AT-BUG-023 — Отсутствуют фикстуры для replay-тестов Note и Tag кнопок

## Окружение
Долг тестовой системы (`type: test_debt`, `debt_kind: missing_fixture`). Две фикстуры, требуемые тестами TC-075 и TC-077, не определены в `framework/tests/conftest.py`, что полностью блокирует запуск обоих P0 canary-тестов.

## Суть долга

Две функции в `framework/tests/canary/test_ao3_selectors.py` требуют фикстуры, которые отсутствуют:

1. **TC-075** (`test_note_button_present_iff_comment_replay`, строка 221):
   - Требует фикстуру `disliked_work_with_comment_seeded`
   - Ожидает объект работы `DISLIKED` с засеянным комментарием "TC-075 seeded comment"
   - Сигнатура: `def test_note_button_present_iff_comment_replay(disliked_work_with_comment_seeded, replay, driver):`

2. **TC-077** (`test_tag_button_present_iff_custom_tag_replay`, строка 286):
   - Требует фикстуру `disliked_work_with_custom_tag_seeded`
   - Ожидает объект работы `DISLIKED` с засеянным личным тегом вне её AO3-тегов
   - Сигнатура: `def test_tag_button_present_iff_custom_tag_replay(disliked_work_with_custom_tag_seeded, replay, driver):`

Обе фикстуры должны следовать паттерну существующих фикстур в `conftest.py`:
- `loved_work_seeded()` (строка 68) — LOVED с рейтингом SAVE
- `note_work_seeded()` (строка 329) — READ с рейтингом LIKE и комментарием
- `disliked_work_with_tags_seeded()` (строка 293) — DISLIKED с рейтингом DISLIKE и тегами

Требуемые фикстуры должны использовать `app_steps.seed_with_comment()` и `W.DISLIKED` (900000005) по образцу существующих.

## Частота
**Всегда** — оба теста падают при каждом запуске, на этапе setup.

## Артефакты

Ошибка при запуске тестов (setup-фаза):
```
fixture 'disliked_work_with_comment_seeded' not found
fixture 'disliked_work_with_custom_tag_seeded' not found
```

Оба теста имеют маркеры `@pytest.mark.p0` (smoke suite) и `@pytest.mark.replay`, что делает их частью регрессионного прогона на каждой сборке. Полное отсутствие фикстур означает полный отказ обоих тестов до их создания.

## Критерий готовности (Fixed)

- В `framework/tests/conftest.py` добавлены две новые фикстуры:
  1. `disliked_work_with_comment_seeded()` — возвращает `W.DISLIKED` с рейтингом `DISLIKE` и комментарием (обновлённое или оригинальное значение). Сидинг через `app_steps.seed_with_comment([(W.DISLIKED, "DISLIKE", "<comment_text>", None)])` до создания сессии Appium (соблюдение порядка как в `loved_work_seeded`/`note_work_seeded`).
  2. `disliked_work_with_custom_tag_seeded()` — возвращает `W.DISLIKED` с рейтингом `DISLIKE` и личным тегом, заведомо отсутствующим в `listing_basic.mitm`. Сидинг через `app_steps.seed_with_comment([(W.DISLIKED, "DISLIKE", None, json.dumps([...]))])`.

- Оба теста проходят зелёным:
  - `Invoke-Pytest tests/canary/test_ao3_selectors.py::test_note_button_present_iff_comment_replay -v` → PASSED
  - `Invoke-Pytest tests/canary/test_ao3_selectors.py::test_tag_button_present_iff_custom_tag_replay -v` → PASSED

- Smoke-регрессия на TC-067..083 без отказа (оба новых теста встраиваются в существующий batch C, `@pytest.mark.p0`-набор).

## Анализ

Долг «фикстуры декларированы в кейсе, но не реализованы в коде». Обе фикстуры являются вариациями работы `DISLIKED` с разными атрибутами (comment vs. tag), следуя паттерну `disliked_work_with_tags_seeded()` (строка 293), которая уже определена и работает. Объём фикса минимален — две фикстуры по ~5 строк каждая, переиспользование существующего `seed_with_comment()` и `W.DISLIKED`.

Тесты TC-075 и TC-077 относятся к canary-suite (R-02: контракт селекторов bridge), входят в P0 smoke (marked `@pytest.mark.p0`) и гоняются на каждой сборке. Отсутствие фикстур делает это полным отказом регрессии на область bridge-инъекции note и tag кнопок, хотя механизм (фикстура replay + `listing_basic.mitm`) уже готов.

Фикс не требует изменений в `app-under-test/` и не ждёт новую сборку (test_debt, лежит целиком в фреймворке).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**[qa @ 2026-07-20T00:00:00Z]** Заведена очередь на две отсутствующие фикстуры, найденные при регрессионном прогоне canary suite (test-automator). Оба теста падают на setup-фазе с ошибкой fixture not found. Фикстуры должны быть реализованы по образцу `disliked_work_with_tags_seeded` и аналогичных в `conftest.py`, используя `seed_with_comment()` для сидинга `W.DISLIKED` с соответствующим комментарием и тегом.

Awaiting dev.

## Чек-лист качества (bug-reporter)
- [x] Проверены дубликаты: фикстуры не упоминаются в других открытых багах
- [x] Репро-шаги воспроизводят проблему: оба теста падают на setup при запуске без фикстур
- [x] Severity обоснована влиянием: 2 P0 canary-теста полностью неexecutable, блокирует регрессию DOM-контракта bridge
- [x] Приложена точная версия: регрессионный прогон framework/tests/canary/test_ao3_selectors.py
- [x] Ни одно изменение не внесено в app-under-test/
