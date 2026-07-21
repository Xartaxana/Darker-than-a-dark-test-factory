---
key: "AT-BUG-023"
project: "AO3"
issueType: "bug"
status: "bug-verified"
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
created: "2026-07-21T16:20:00Z"
updated: "2026-07-21T16:20:00Z"
archived: false
resolution: "done"
---

# 2 P0 canary tests не запускаются: отсутствуют фикстуры disliked_work_with_comment_seeded и disliked_work_with_custom_tag_seeded в conftest.py

_Спроецировано из `bugs/AT-BUG-023.md` (источник правды).
Статус в нашей машине: **Verified**._

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
| 2026-07-21 (test-maintainer, реализация + само-верификация до D1) | app-under-test не менялся (test_debt, фикстуры добавлены в `framework/tests/conftest.py`) | TC-075 (`test_note_button_present_iff_comment_replay`), TC-077 (`test_tag_button_present_iff_custom_tag_replay`) — целевые; полный `test_ao3_selectors.py` (18 тестов) — регресс-контроль | Прогон 1 (целевые 2 теста, `Invoke-Pytest tests/canary/test_ao3_selectors.py::test_note_button_present_iff_comment_replay tests/canary/test_ao3_selectors.py::test_tag_button_present_iff_custom_tag_replay -v`): `2 passed in 56.62s`, `PYTEST_EXIT=0`. Прогон 2 (полный файл, тем же эмулятором): первые 12 тестов (включая TC-075/077 live+replay) `PASSED`, затем batch C (TC-078..083) упал на известном env-классе AT-BUG-021 (qemu-краш/device-not-found под `swiftshader_indirect` на тяжёлой Sort&Filter live-странице) — подтверждено `Get-Device: NO DEVICE`; TC-075/077 сама фикстура тут не при чём (падение до них не долетело). Прогон 3 (после `Start-Emulator -WritableSystem -Gpu host` + `Install-MitmCA` + `Install-App`, документированная в AT-BUG-021 config-митигация, БЕЗ правок кода): полный `test_ao3_selectors.py` — `18 passed in 409.50s`, `PYTEST_EXIT=0`, включая TC-075/077. Итого TC-075/TC-077 зелёные в 3 независимых прогонах подряд (целевой + 2× полный файл), регресса по остальным 16 тестам нет | **Fixed** (ждёт D1-верификацию fix-verifier — test_debt, сборку приложения ждать не нужно) |
| 2026-07-21T16:20:00Z (fix-verifier, mode=verify, независимая верификация) | framework @ `1666078` (коммит `f2cc7a7` содержит фикстуры в `framework/tests/conftest.py`, независимо подтверждено `git log` + `grep` строк 315/326 ДО прогонов) | TC-075/TC-077 (целевые, изолированно); полный `test_ao3_selectors.py` (18 тестов) — регресс-контроль, дважды (дефолтный GPU и с `-Gpu host`) | Прогон 1 (целевые): `2 passed in 53.53s`, `PYTEST_EXIT=0`. Прогон 2 (полный файл, дефолтный `swiftshader_indirect`, БЕЗ `-Gpu host`): TC-066..079 (14 тестов, включая TC-075/077) все PASSED, затем эмулятор упал mid-run на TC-080 (тот же класс AT-BUG-021, `Get-Device` → `NO DEVICE` подтверждено) — `1 failed, 14 passed, 3 errors in 401.55s`, `PYTEST_EXIT=1`; падение НЕ связано с фикстурами этого бага (TC-080..083 их не используют). Прогон 3 (перезапуск `Start-Emulator -WritableSystem -Gpu host` + `Install-MitmCA` + `Install-App` + `Start-Appium`, config-митигация AT-BUG-021, без правок кода): полный `test_ao3_selectors.py` — `18 passed in 356.77s`, `PYTEST_EXIT=0`, включая весь batch C (TC-078..083). Оба целевых теста зелёные в 2 независимых прогонах (изолированный + полный), регресс TC-067..083 чист под известной config-митигацией | **Verified** |

## Обсуждение

**[fix-verifier @ 2026-07-21T16:20:00Z] mode=verify, Fixed → Verified.**
Независимо подтверждено ДО прогонов: `grep -n "disliked_work_with_comment_seeded\|
disliked_work_with_custom_tag_seeded" framework/tests/conftest.py` — обе фикстуры
реально в файле (строки 315 и 326), `git log --oneline -- framework/tests/
conftest.py` показывает коммит `f2cc7a7 AT-BUG-023: добавлены фикстуры
conftest.py для TC-075/TC-077` — фактически закоммичено, не unstaged.
Прочитано тело обеих фикстур: `disliked_work_with_comment_seeded` сидит
`W.DISLIKED`/DISLIKE с комментарием "TC-075 seeded comment";
`disliked_work_with_custom_tag_seeded` сидит `W.DISLIKED`/DISLIKE с тегом
`["tc077-custom-tag"]` — соответствует заявленному в «Критерии готовности».

Окружение: `Start-Emulator -WritableSystem -Gpu host` (CA переустановлен) →
`Install-App` → `Start-Appium`.

Прогон 1 (целевые тесты): `Invoke-Pytest tests/canary/test_ao3_selectors.py::
test_note_button_present_iff_comment_replay tests/canary/test_ao3_selectors.py::
test_tag_button_present_iff_custom_tag_replay -v` — **2 passed in 53.53s**,
`PYTEST_EXIT=0`.

Прогон 2 (полный `test_ao3_selectors.py`, 18 тестов, дефолтный GPU-бэкенд
`swiftshader_indirect`, без `-Gpu host`): TC-066..079 (14 тестов) все PASSED
(включая TC-075/077), затем эмулятор упал mid-run на TC-080
(`test_exclude_main_pairing_checkbox_availability_live`, тяжёлая live-страница
Sort&Filter) с сигнатурой `WebDriverException: disconnected: not connected to
DevTools` → `adb: device 'emulator-5554' not found` для всех дальнейших
действий — подтверждено `Get-Device` → `NO DEVICE`. Это ТОТ ЖЕ уже
задокументированный класс `bugs/AT-BUG-021.md` (Verified, `debt_kind:
broken_environment`, config-митигация `-Gpu host`) — не новый долг этого бага
и не относится к фикстурам TC-075/077 (упавшие TC-080/081/082/083 их не
используют). Итог прогона 2: `1 failed, 14 passed, 3 errors in 401.55s`,
`PYTEST_EXIT=1` — зафиксировано честно, не скрыто.

Прогон 3 (перезапуск `Start-Emulator -WritableSystem -Gpu host` +
`Install-MitmCA` + `Install-App` + `Start-Appium`, документированная
config-митигация AT-BUG-021, БЕЗ правок кода): полный `test_ao3_selectors.py`
— **18 passed in 356.77s**, `PYTEST_EXIT=0`, включая TC-075/077 и весь batch C
(TC-078..083). Критерий готовности «smoke-регрессия на TC-067..083 (batch C
p0) без отказа» подтверждён под задокументированной config-митигацией
известного env-долга (не под дефолтным GPU-бэкендом, который сам является
отдельным, уже верифицированным долгом AT-BUG-021 — смешивать их в вердикт
этого бага не нужно).

Оба целевых теста PASSED в 2 независимых прогонах (изолированный + полный
регресс), обе фикстуры реально в `conftest.py` и закоммичены, регресс TC-067..
083 чист под известной митигацией. **Вердикт: Fixed → Verified.**

**Дефект-собрат (не новый баг, для внимания):** тот же класс, что фиксировал
test-maintainer в этом же баге — smoke-регрессия batch C систематически
зависит от применения `-Gpu host`; если это не задокументировано как
обязательный шаг канонического прогона `test_ao3_selectors.py` (а не только
как факт в AT-BUG-021), стоит явно пометить в `docs/environment-setup.md`/
README фреймворка, что регресс canary-suite ПОЛНОСТЬЮ (включая batch C)
требует `-Gpu host` — иначе каждый следующий прогонщик наткнётся на тот же
env-класс заново и потратит цикл на диагностику уже решённой проблемы.

Lock снят.

**[qa @ 2026-07-20T00:00:00Z]** Заведена очередь на две отсутствующие фикстуры, найденные при регрессионном прогоне canary suite (test-automator). Оба теста падают на setup-фазе с ошибкой fixture not found. Фикстуры должны быть реализованы по образцу `disliked_work_with_tags_seeded` и аналогичных в `conftest.py`, используя `seed_with_comment()` для сидинга `W.DISLIKED` с соответствующим комментарием и тегом.

Awaiting dev.

**[test-maintainer @ 2026-07-21T09:30:00Z]** Долг устранён. Добавлены две
фикстуры в `framework/tests/conftest.py` (после `disliked_work_with_tags_seeded`,
строка ~314): `disliked_work_with_comment_seeded()` — `W.DISLIKED` с рейтингом
DISLIKE и комментарием "TC-075 seeded comment" через `seed_with_comment()`;
`disliked_work_with_custom_tag_seeded()` — `W.DISLIKED` с рейтингом DISLIKE и
личным тегом `["tc077-custom-tag"]`, заведомо отсутствующим среди AO3-тегов
карточки `listing_basic.mitm`. Обе минимальны (~5 строк тела каждая),
переиспользуют существующий `seed_with_comment()`/`W.DISLIKED`, без изменений
в `app-under-test/`. TC-075/TC-077 зелёные (см. таблицу «Верификация»); попутно
обнаружен НЕ вызванный этой правкой env-сбой batch C (device died mid-run под
дефолтным `-gpu swiftshader_indirect`) — это уже задокументированный
AT-BUG-021 (Verified, config-mitigation `-gpu host`), не новый долг; регресс-
прогон после применения этой известной митигации показал полный `18 passed`.
`status: Open → Fixed` (guard `{type: test_debt}`, B4, `test-maintainer`
разрешён по `schemas/transitions.yaml`). Lock снят. TC-075.md/TC-077.md статус
не менялся (вне скоупа — automated_by уже проставлен ранее тест-дизайнером/
ревьюером, см. test-cases).

## Чек-лист качества (bug-reporter)
- [x] Проверены дубликаты: фикстуры не упоминаются в других открытых багах
- [x] Репро-шаги воспроизводят проблему: оба теста падают на setup при запуске без фикстур
- [x] Severity обоснована влиянием: 2 P0 canary-теста полностью неexecutable, блокирует регрессию DOM-контракта bridge
- [x] Приложена точная версия: регрессионный прогон framework/tests/canary/test_ao3_selectors.py
- [x] Ни одно изменение не внесено в app-under-test/
