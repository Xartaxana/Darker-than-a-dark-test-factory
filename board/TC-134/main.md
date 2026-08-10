---
key: "TC-134"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p1"
summary: "Kill+relaunch приложения не переоткрывает уже обработанный deep-link"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:tabs", "risk:R-08", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-10T10:18:15Z"
updated: "2026-08-10T10:18:15Z"
archived: false
resolution: "done"
---

# Kill+relaunch приложения не переоткрывает уже обработанный deep-link

_Спроецировано из `test-cases/tabs/TC-134.md` (источник правды).
Статус в нашей машине: **Automated**._

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
- Рестарт — шаг `app_steps.restart_app_via_adb_asserting_new_process`
  (`app_steps.py:465-489`; критик-блокер B1, attempt 2) — оборачивает
  `app_steps.restart_app_via_adb` (`app_steps.py:451-462`, `force_stop` +
  `am start -W` без `-d`, использовался TC-025 для проверки персистентности) и
  ДОКАЗЫВАЕТ реальную смерть процесса сравнением pid ДО/ПОСЛЕ (`adb.pidof_app()`
  не совпадает) — без этого тихий отказ `force_stop` (`adb.shell` отбрасывает
  returncode) неотличим от штатного kill+relaunch, все Then читали бы
  неизменившееся состояние живого процесса. Дополнительно сверяется ИМЕННО
  отсутствие лишних вкладок сверх восстановленных.
- Подтверждение реальной записи на диск ДО рестарта — существующий шаг
  `app_steps.wait_tabs_persisted` (опрос `ao3_settings.xml` на сентинел,
  `app_steps.py:250-266`) — обязателен, иначе 500мс debounce `scheduleSave` может
  потерять несохранённое состояние (тот же класс, что TC-025).
- Счёт/набор вкладок — из prefs `open_tabs_urls`, не из иконок TabStrip.
- Различать от TC-133: там процесс НЕ убивается (background/foreground), здесь —
  реальная смерть процесса; оба пути защищены одним и тем же механизмом
  (`deepLinkHandled` + `intent.dataString`), но через разные жизненные циклы —
  раздельные кейсы (один сценарий — один кейс).
- Перед первым deep-link'ом (создание вкладок 1/2 в Given) дождаться загрузки home
  (`app_steps.wait_home_ready_for_deep_link`) — тот же класс гонки, что в
  TC-022..025/131/132/133.

**Фактическое поведение (test-automator, 2026-07-31, attempt 2 — после
critic-блокера B1).** Реализовано
`framework/tests/test_tabs.py::test_kill_relaunch_without_deep_link_keeps_tabs_unchanged`
— переиспользует ГОТОВЫЕ шаги `app_steps.wait_home_ready_for_deep_link`/
`open_deep_link`/`wait_persisted_tab_count`/`assert_persisted_tab_url_at`/
`assert_persisted_marker_count`/`wait_tabs_persisted`/`wait_ui_ready` (все уже
в дереве из TC-025/131/132/133). Добавлен новый шаг `app_steps.py`:
`restart_app_via_adb_asserting_new_process(driver)` — оборачивает существующий
`restart_app_via_adb`, снимает `adb.pidof_app()` ДО и ПОСЛЕ и требует, чтобы
pid ИЗМЕНИЛСЯ (обратная семантика к TC-133 `assert_app_pid_unchanged`,
которая требует НЕИЗМЕННОСТИ pid — переиспользовать её было бы некорректно).

Critic-блокер B1 (attempt 2): у When (force-stop + релонч) не было НИ ОДНОЙ
наблюдаемой — `restart_app_via_adb` вызывает `adb.force_stop()` ->
`adb.shell()`, returncode отбрасывается молча; тихий отказ force-stop (device
busy/permission/отвал adb) оставляет процесс живым, и `am start -W` без `-d`
на уже переднюю `singleTask`-Activity лишь доставляет пустой intent через
`onNewIntent` — все Then читали бы неизменившееся состояние ОДИНАКОВО
зелёным что при реальной смерти процесса, что при её отсутствии, не различив
эти два пути. Закрыто сверкой pid НА НЕРАВЕНСТВО до/после — доказывает
именно смерть+пересоздание процесса, а не просто «релонч отработал».

Оба класса ложно-зелёного негатива (докстринг диспатча) по-прежнему закрыты:
(1) достижимость эффекта гипотетического бага — красная проба реально
ОТПРАВЛЯЕТ `open_deep_link(marker1_url)` СРАЗУ ПОСЛЕ релонча (не просто
ослабляет ассерт), симулируя баг «релонч почему-то переоткрывает последний
маркер»; тест упал содержательно (`AssertionError: общее число вкладок в
open_tabs_urls: 4, ожидали 3`), порча откачена; (2) позитивный якорь
источника — `expected_total=3` передан в КАЖДЫЙ вызов
`assert_persisted_marker_count` после релонча, набор/порядок 3 URL
зафиксирован через `assert_persisted_tab_url_at` ДО kill+relaunch И ПОСЛЕ.

3 зелёных прогона подряд целевого теста (PYTEST_EXIT=0 каждый). Негативный
контроль на самом B1-фиксе (attempt 2 DoD): временная подмена
`restart_app_via_adb_asserting_new_process` — `force_stop()` пропущен, тело
свёрнуто к голому `am start -W` (симулирует тихий отказ force-stop) — новая
pid-проверка поймала это содержательно (`AssertionError: pid не изменился
(23865) — am force-stop процесс НЕ убил...`), порча откачена. Красная проба
B2 (переоткрытие маркера, из attempt 1) перепрогнана после фикса — по-прежнему
падает содержательно (`AssertionError: общее число вкладок в open_tabs_urls:
4, ожидали 3`), не переделывалась. Полный `test_tabs.py` — фактическое число
passed зафиксировано в отчёте агента отдельно. `arch_check` — 0/0.
`validate_frontmatter` — 0/0. Блокера автоматизации не найдено — чек-лист
test-designer подтверждён.

## Ревью автотеста (F1, test-reviewer, 2026-07-31T18:12:23Z) — ПРОЙДЕНО

Ревью батчем 5 кейсов области tabs (TC-131..135, один файл
`framework/tests/test_tabs.py`). Общий witness батча (Get-Device →
`DEVICE: emulator-5554`; `Invoke-Pytest tests/test_tabs.py -v` → **11 passed
in 391.91s, PYTEST_EXIT=0**, включая регресс старых TC-022..026/084;
`arch_check` 0/0 при пустом ALLOWLIST; `validate_frontmatter` 0/0) записан в
`test-cases/tabs/TC-131.md` и не дублируется здесь.

**По этому кейсу.**
- Traceability: `@allure.id("TC-134")` == id кейса; `@pytest.mark.p1` ==
  `priority: P1`; `automated_by` указывает на существующую
  `test_kill_relaunch_without_deep_link_keeps_tabs_unchanged`
  (`test_tabs.py:576`).
- Соответствие по смыслу (п.3): инвариант «холодный старт без непустого
  `dataString` не добавляет вкладок сверх восстановленных» проверяется как
  свойство множества (3 вкладки, URL по позициям, ровно по 1 вхождению каждого
  маркера) с якорем `expected_total=3` в каждом чтении; персистентность не
  переутверждается, а обеспечивается предварительным `wait_tabs_persisted` с
  Gson-эскейпом `=` → `=` (учтён 500мс debounce `scheduleSave` — иначе
  force-stop потерял бы состояние и тест мерил бы не то).
- When наблюдаем: `restart_app_via_adb_asserting_new_process`
  (`app_steps.py:465-520`) требует СМЕНЫ pid — семантика обратная TC-133, и
  переиспользование чужого ассерта корректно отклонено автором. Тихий отказ
  `force_stop` (returncode `adb.shell` отбрасывается) больше не выдаёт себя за
  kill+relaunch.
- Красная проба (п.7): оба заявленных автором текста сверены с фактическими
  ассертами дословно — `AssertionError: общее число вкладок в open_tabs_urls:
  4, ожидали 3` == `app_steps.py:350-354`; `pid не изменился (23865) — am
  force-stop процесс НЕ убил…` == `app_steps.py:516-520`. Порча «реально
  отправить deep-link после релонча» содержательна (бьёт в эффект
  гипотетического бага, а не ослабляет ассерт). Собственная красная проба
  батча (TC-135) уронила общий prefs-оракул, используемый и здесь.
- Флейк-риск (п.5): `am start -W` + `wait_ui_ready` + опрашивающие проверки
  prefs, фиксированных пауз нет; живой AO3 не используется.
- Полезный побочный факт этого инкремента: тот же класс дыры был закрыт и у
  старых вызывающих `restart_app_via_adb` (TC-025, TC-125) единой точкой в
  `app_steps.py` — фикс класса, а не экземпляра (AT-BUG-032); остаток по
  `test_compatibility.py:129` честно назван в докстринге и стоит в очереди.

Не блокирующие замечания батча (мёртвая диагностика
`wait_persisted_tab_count`, `app_steps.py:311-328`) — в
`test-cases/tabs/TC-131.md`; касаются общего шага и этого кейса тоже.

## Карантин снят (test-maintainer, AT-BUG-055, 2026-08-10T10:18:15Z)

`automation_status: quarantined -> active`. Причина карантина (RUN-20260804-1624:
`AssertionError: позиция 0 вне диапазона: всего вкладок в prefs 0` сразу после
успешного `wait_persisted_tab_count`) устранена у ИСТОЧНИКА, не замаскирована:
`_read_tabs_prefs_raw`/`_parse_persisted_tabs`/`wait_tabs_persisted`
(`framework/steps/app_steps.py`) теперь честно читают `ao3_settings.xml` через
новый `adb.run_as_file_or_raise` (`framework/core/adb.py`, echo-sentinel RC —
тот же приём, что закрыл AT-BUG-044/045) и явно кидают `RuntimeError` вместо
молчаливого `""`/`[]` на отвалившемся/неоднозначном `run-as`; ассерт по-прежнему
проверяет то же самое (позицию/URL вкладки), не ослаблен. Полный разбор класса,
красная проба и witness — `bugs/AT-BUG-055.md`.

Изолированный перепрогон ЭТОГО кейса — 3/3 зелёных подряд (`Invoke-Pytest
tests/test_tabs.py -k test_kill_relaunch_without_deep_link_keeps_tabs_unchanged`,
каждый `1 passed, 12 deselected`, `PYTEST_EXIT=0`), плюс полный
`test_tabs.py` (13/13 passed) — witness дословно в `bugs/AT-BUG-055.md`.

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
