---
id: AT-BUG-090
title: "assert_chip_absent — негативный Then сразу после tap_selected_chip/reopen_listing_overlay без settle/hold (4-й член класса AT-BUG-081/082/083/085), TC-091 — превентивный тикет"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Open
found_in: "test-maintainer, AT-BUG-085 фикс, D-0043 сиблинг-аудит (state/escalations.md, запись AT-BUG-085-CHIP-ABSENT-CLASS-SIBLING, 2026-08-20T03:22:31Z); заведён Lead-решением по эскалации (превентивно, класс доказан трижды)"
fixed_in: ""
last_seen_in: ""
test_cases: ["TC-091"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-20T11:52:04Z"
updated: "2026-08-20T11:52:04Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
gitlab_issue: ""
---

# AT-BUG-090 — `assert_chip_absent` читает `chip_visible` сразу после стейт-меняющего действия без settle/hold (превентивный, TC-091)

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`), поверхность —
`framework/steps/rating_steps.py::assert_chip_absent`, вызывается из
`framework/tests/test_rating_listing.py` (TC-091,
`test_tap_selected_chip_removes_tag`).

## Статус: ПРЕВЕНТИВНЫЙ

**Красных прогонов ПОКА нет.** Этот тикет заведён НЕ по факту наблюдаемого
флейка (в отличие от AT-BUG-085, где TC-115 реально упал в живом прогоне), а
превентивно — решением Lead по эскалации `AT-BUG-085-CHIP-ABSENT-CLASS-SIBLING`
(`state/escalations.md:2590`, 2026-08-20T03:22:31Z): класс дефекта («негативный
Then одноразовым `is_present`-примитивом короткого замыкания сразу после
стейт-меняющего действия, без settle/hold-опроса») уже доказан ТРИЖДЫ на
СОСЕДНИХ примитивах того же модуля/семейства модулей —

1. **AT-BUG-081** — `_poll_ratings_marker` (`library_steps.py`/родственный модуль),
2. **AT-BUG-082/083** — `_poll_files_tab_absent`/`_poll_tab_absent`
   (`library_steps.py`, `HorizontalPager`-переходы),
3. **AT-BUG-085** — `_poll_comment_collapsed` (`rating_steps.py`, ЭТОТ ЖЕ файл,
   комментарий-превью `RatingOverlay`),

— и `assert_chip_absent` (chip-виджет `RatingOverlay`, тот же composable-семья,
что комментарий AT-BUG-085) структурно идентичен ПРЕ-фикс форме
`assert_comment_collapsed_with_text` из AT-BUG-085: `not <примитив
короткого замыкания>(...)` сразу после действия, меняющего состояние
(`tap_selected_chip` — удаление тега; `reopen_listing_overlay` — закрытие/
переоткрытие bottom-sheet), без единого settle-чтения между действием и
чтением. Механизм риска идентичен AT-BUG-085 (`BaseScreen.is_present` ждёт
ПОЯВЛЕНИЯ узла, но возвращает `True` немедленно на первом снимке, если узел
ещё присутствует — не ждёт ИСЧЕЗНОВЕНИЯ) — см. `rating_steps.py:311-358`
(докстринг `_poll_comment_collapsed`/блок-комментарий класса).

## Суть долга

`framework/steps/rating_steps.py::assert_chip_absent` (текущая реализация):

```python
@allure.step("Then чип «{tag}» отсутствует среди тегов overlay")
def assert_chip_absent(driver, tag: str, timeout: int = 3):
    assert not RatingOverlay(driver).chip_visible(tag, timeout=timeout), (
        f"чип «{tag}» неожиданно присутствует среди тегов overlay"
    )
```

`chip_visible(...)` — тот же класс примитива, что был у `comment_expanded()`
до фикса AT-BUG-085: `is_present`-опрос, ждущий ПОЯВЛЕНИЯ узла до `timeout`,
но возвращающий `True` немедленно на первом снимке без ожидания
ИСЧЕЗНОВЕНИЯ. `not chip_visible(...)` вызывается СРАЗУ после
`tap_selected_chip` (удаление тега — стейт-меняющее действие) или
`reopen_listing_overlay` (закрытие+переоткрытие bottom-sheet, тоже
стейт-меняющее) — ни settle-, ни hold-фазы между действием и чтением нет.

## Адрес (СТРОГО, критик-гейт О7 AT-BUG-085, 2026-08-20 — адрес сверен по
фактическому файлу этим тикетом, номера НЕ уехали)

Сверено чтением `framework/tests/test_rating_listing.py` (2026-08-20,
`test_tap_selected_chip_removes_tag`, TC-091):

- **`framework/tests/test_rating_listing.py:366`**:
  ```python
  rating_steps.assert_chip_absent(driver, "Angst")
  ```
  — сразу ПОСЛЕ `rating_steps.tap_selected_chip(driver, "Angst")` (строка 363).
  Принадлежит классу — чинить.
- **`framework/tests/test_rating_listing.py:379`**:
  ```python
  rating_steps.assert_chip_absent(driver, "Angst")
  ```
  — сразу ПОСЛЕ `rating_steps.reopen_listing_overlay(driver, work.ao3_id)`
  (строка 377) + `rating_steps.open_tags_section(driver)` (строка 378).
  Принадлежит классу — чинить.

**НЕ ЧИНИТЬ `framework/tests/test_rating_listing.py:324`** (TC-090,
`test_add_freeform_tag_persists`):
```python
rating_steps.assert_chip_absent(driver, tag)
```
Эта строка — часть **Given**, ДО каких-либо стейт-меняющих действий этого
теста (тег `"spoiler-test"` ещё ни разу не добавлялся на чистом состоянии —
проверка «тега точно нет в начале», не «тег только что исчез после
действия»). Классу «Then сразу после действия без settle» НЕ принадлежит —
критик-гейт О7 AT-BUG-085 явно исключил эту строку из адреса, сверено
дословно тем же ходом.

## Направление фикса

По образцу `_poll_comment_collapsed` (AT-BUG-085, `rating_steps.py:359-408`) —
settle+hold опрос вместо одноразового чтения: settle-фаза (короткий поллинг,
пока `chip_visible` не сойдётся к `False`, ограниченный таймаутом) + hold-фаза
(`waits.assert_holds_for`-подобный бюджет, подтверждающий, что чип НЕ
перепоявляется обратно). Альтернативно — примитив `base_screen.wait_absent`
(если он уже покрывает нужную семантику ожидания исчезновения узла;
`framework/screens/base_screen.py` содержит `wait_absent` — сверить
сигнатуру перед выбором между copy-paste `_poll_comment_collapsed`-паттерна и
переиспользованием существующего примитива).

## Критерий готовности (Fixed)

- [ ] Негативный ассерт `assert_chip_absent` переведён на settle/hold-полл
      (или эквивалентный `wait_absent`), а не одноразовое
      `not chip_visible(...)`.
- [ ] Юнит-пин (device-free), различающий старую одноразовую семантику от
      новой settle/hold — по образцу `test_rating_comment_collapse_settle_
      unit.py` (AT-BUG-085).
- [ ] `framework/tests/test_rating_listing.py:324` (TC-090, Given) НЕ
      затронут.
- [ ] TC-091 зелёный (живой прогон), регресс не хуже baseline.
- [ ] Сиблинг-аудит по D-0043: остальные негативные `assert_*` в
      `rating_steps.py` уже проверены AT-BUG-085 (`assert_note_overlay_
      expanded_with_text`/`assert_overlay_still_open` — позитивные опросы,
      вне класса); повторная сверка не обязательна, если фикс не касается
      других функций файла.

## Верификация (заполняет fix-verifier)

| Дата | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|
| — | — | — | Open, ждёт разбора |

## Обсуждение

**[builder @ 2026-08-20T11:52:04Z]** Заведён по прямому решению Lead
(state/escalations.md, запись `AT-BUG-085-CHIP-ABSENT-CLASS-SIBLING`,
2026-08-20T03:22:31Z: «завести test_debt-тикет ПРЕВЕНТИВНО»). Статус
превентивный подтверждён явно в тексте («Статус: ПРЕВЕНТИВНЫЙ» выше) —
красных прогонов TC-091 не зафиксировано ни в одном известном run-артефакте
на момент заведения тикета. Адрес (`:366`/`:379`, НЕ `:324`) сверен построчным
чтением фактического `framework/tests/test_rating_listing.py` этим же
ходом — номера строк совпадают с критик-гейтом О7 AT-BUG-085 дословно, не
уехали. Awaiting: none.

## Чек-лист качества

- [x] Проверены дубликаты среди открытых AT-BUG-* (`bugs/AT-BUG-*.md`,
      status != Verified/Rejected) — новый экземпляр класса, не дубликат
      AT-BUG-081/082/083/085 (разные адреса кода)
- [x] Точная позиция в коде сверена чтением файла: `:366` и `:379`
      (принадлежат классу), `:324` явно исключён (Given, TC-090)
- [x] Severity обоснована — превентивный долг, красных прогонов нет,
      механизм риска идентичен трижды уже доказанному классу
- [x] Сиблинги AT-BUG-081/082/083/085 и класс дефекта идентифицированы
- [x] Направление фикса приложено (settle/hold-полл по образцу
      `_poll_comment_collapsed`/`wait_absent`)
- [x] Ни одного изменения в тестовой системе не внесено; только анализ
- [x] Долг-класс определён (негативный Then без settle/hold, flaky_test)
