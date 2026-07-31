---
key: "TC-134"
project: "AO3"
issueType: "test-case"
status: "tc-awaiting-review"
priority: "p1"
summary: "Kill+relaunch приложения не переоткрывает уже обработанный deep-link"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:tabs", "risk:R-08"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-31T00:51:29Z"
updated: "2026-07-31T00:51:29Z"
archived: false
resolution: null
---

# Kill+relaunch приложения не переоткрывает уже обработанный deep-link

_Спроецировано из `test-cases/tabs/TC-134.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-134 — Kill+relaunch не переоткрывает уже обработанный deep-link

## Предусловия
- Приложение запущено с чистыми данными (`clean_app`).
- Replay-режим, фикстура `tab_markers.mitm`.
- Открыто 3 вкладки: 0 — Home (полностью догружена), 1 и 2 — созданы ДВУМЯ
  предшествующими deep-link'ами (`ao3_tab_marker=1`, `ao3_tab_marker=2`), состояние
  сохранено на диск (сентинел в `open_tabs_urls` подтверждён — тот же приём, что
  TC-025, `wait_tabs_persisted`, учитывающий 500мс debounce `scheduleSave`).

## Сценарий (Given-When-Then)

**Given** открыто 3 вкладки (Home, маркер 1, маркер 2), состояние подтверждённо
записано в SharedPreferences

**When** процесс приложения принудительно убит (`adb shell am force-stop`, реальная
смерть процесса — тот же приём, что TC-025) и запущен заново БЕЗ deep-link intent'а
(`am start -W` на компонент Activity без `-d`)

**Then** после релонча снова 3 вкладки в исходном порядке, URL каждой совпадают с
теми, что были до убийства (персистентность — фон, уже покрыт TC-025 как отдельное
свойство; здесь переиспользуется как предусловие, не переутверждается заново)
**And** ни маркер 1, ни маркер 2 НЕ переоткрываются повторно доп. вкладкой — счёт
остаётся ровно 3, а не 4/5 — `deepLinkHandled` в свежесозданном процессе начинается
со значения `false` (поле объекта Activity, пересоздаётся вместе с процессом), но
`intent.dataString` intent'а релонча пуст (нет `-d`), поэтому `handleDeepLink` не
вызывается вовсе на этом старте

**Инвариант:** холодный старт процесса (после force-stop) БЕЗ intent'а с непустым
`dataString` не добавляет вкладок сверх персистентно восстановленных из
SharedPreferences — отсутствие `deepLinkHandled` (пересозданного в `false`) не
эквивалентно «есть URL для обработки»: обработка deep-link'а требует ОБОИХ условий
(`!deepLinkHandled` И непустой `intent.dataString`), одного `!deepLinkHandled`
недостаточно.

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Вкладок до kill+relaunch | 3 (Home, маркер 1, маркер 2) |
| Способ рестарта | `adb shell am force-stop <package>` + `am start -W -n <package>/<activity>` (без `-d`) |
| Вкладок после kill+relaunch | 3, тот же набор/порядок/URL |

## Заметки для автоматизации
- Рестарт — существующий шаг `app_steps.restart_app_via_adb` (`app_steps.py:189-200`,
  `force_stop` + `am start -W` без `-d`) — уже готов, использовался TC-025 для
  проверки персистентности; здесь переиспользуется как есть, дополнительно
  сверяется ИМЕННО отсутствие лишних вкладок сверх восстановленных.
- Подтверждение реальной записи на диск ДО рестарта — существующий шаг
  `app_steps.wait_tabs_persisted` (опрос `ao3_settings.xml` на сентинел,
  `app_steps.py:170-186`) — обязателен, иначе 500мс debounce `scheduleSave` может
  потерять несохранённое состояние (тот же класс, что TC-025).
- Счёт/набор вкладок — из prefs `open_tabs_urls`, не из иконок TabStrip.
- Различать от TC-133: там процесс НЕ убивается (background/foreground), здесь —
  реальная смерть процесса; оба пути защищены одним и тем же механизмом
  (`deepLinkHandled` + `intent.dataString`), но через разные жизненные циклы —
  раздельные кейсы (один сценарий — один кейс).
- Перед первым deep-link'ом (создание вкладок 1/2 в Given) дождаться загрузки home
  (`app_steps.wait_home_ready_for_deep_link`) — тот же класс гонки, что в
  TC-022..025/131/132/133.

**Фактическое поведение (test-automator, 2026-07-31).** Реализовано
`framework/tests/test_tabs.py::test_kill_relaunch_without_deep_link_keeps_tabs_unchanged`
— переиспользует ГОТОВЫЕ шаги `app_steps.wait_home_ready_for_deep_link`/
`open_deep_link`/`wait_persisted_tab_count`/`assert_persisted_tab_url_at`/
`assert_persisted_marker_count`/`wait_tabs_persisted`/`restart_app_via_adb`/
`wait_ui_ready` (все уже в дереве из TC-025/131/132/133); новых шагов в
`app_steps.py` не добавлено — весь путь уже покрыт. Структура теста —
прямой аналог TC-133 с заменой `send_app_to_background`+
`bring_app_to_foreground_without_deep_link` на `wait_tabs_persisted` (сентинел
на диск перед убийством процесса) + `restart_app_via_adb` (реальная смерть
процесса). Оба класса ложно-зелёного негатива (докстринг диспатча) закрыты:
(1) достижимость эффекта гипотетического бага — красная проба реально
ОТПРАВЛЯЕТ `open_deep_link(marker1_url)` СРАЗУ ПОСЛЕ релонча (не просто
ослабляет ассерт), симулируя баг «релонч почему-то переоткрывает последний
маркер»; тест упал содержательно (`AssertionError: общее число вкладок в
open_tabs_urls: 4, ожидали 3`), порча откачена; (2) позитивный якорь
источника — `expected_total=3` передан в КАЖДЫЙ вызов
`assert_persisted_marker_count` после релонча, набор/порядок 3 URL
зафиксирован через `assert_persisted_tab_url_at` ДО kill+relaunch И ПОСЛЕ.
3 зелёных прогона подряд целевого теста + полный `test_tabs.py` (10 passed,
361.65s, включая 9 существующих тестов, код которых не тронут). `arch_check`
— 0/0. Блокера автоматизации не найдено — чек-лист test-designer
подтверждён.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Блокер автоматизации из заметок — блокера нет (весь путь уже покрыт
      существующими шагами `restart_app_via_adb`/`wait_tabs_persisted`/
      `open_deep_link`, использованными в TC-025)
- [x] Кейс комбинаторной области называет инвариант строкой `Инвариант:`
