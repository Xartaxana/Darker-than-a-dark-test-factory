---
id: AT-BUG-006
title: "Таблица filter_profiles не поддержана в seed_db.py и нет replay-записи формы AO3 Sort&Filter — блокирует автоматизацию батча filter-profiles (TC-040/041/042, P1)"
type: test_debt
debt_kind: missing_fixture
severity: minor
status: Fixed
found_in: "Lead при попытке R14-батча filter-profiles (2026-07-09), после того как settings-батч (TC-047/048/049) прошёл без блокеров; ранее — только заметки в телах TC-040/041/042 (с 2026-07-02), не заведено как bug-артефакт"
fixed_in: "uncommitted at time of writing — framework/data/recordings/sort_filter_form.mitm, framework/tests/test_filter_profiles.py, framework/screens/settings_screen.py, framework/screens/browser_screen.py, framework/steps/settings_steps.py, framework/steps/browser_steps.py, framework/tests/conftest.py (см. Обсуждение инкремента 2026-07-15); commit hash — после приёмки/коммита оркестратором"
last_seen_in: ""
test_cases: ["TC-040", "TC-041", "TC-042"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-07-15T17:20:00Z"
updated: "2026-07-15T17:20:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
lock: ""
---

# AT-BUG-006 — Инфраструктура filter-profiles не доведена (сидинг + replay-запись формы)

## Окружение
- Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
  `debt_kind: missing_fixture`). Известен с проектирования TC-040/041/042
  (2026-07-02) как заметки в телах кейсов; не был заведён как отслеживаемый
  bug-артефакт до попытки автоматизировать батч (2026-07-09) — тот же класс
  пробела, что закрыт для AT-BUG-004/AT-BUG-005 этим же проходом (правило 9).

## Суть долга

Область `filter-profiles` (3 P1-кейса, все `status: Approved`,
`automated_by` пуст) требует двух отсутствующих кусков инфраструктуры:

1. **Таблица `filter_profiles` не поддержана `seed_db.py`.** Скрипт сидинга
   сейчас работает только с `work_ratings` (см. заметку TC-041). Для
   TC-041/TC-042 нужен прямой сидинг записей `FilterProfile` (схема —
   `FilterProfileDao.kt`/`AppDatabase.kt` в app-under-test) в обход UI —
   расширение сидинг-скрипта, аналог того, что уже сделано для
   `work_ratings`.
2. **Нет replay-записи страницы с формой AO3 Sort&Filter в исходной
   разметке.** Для TC-040 нужна запись СТРАНИЦЫ AO3 (search/tag browse) с
   реальной формой Sort&Filter — НЕ синтетической (в отличие от
   `listing_basic.mitm` из AT-BUG-004, где разметка блёрбов реконструирована
   вручную и это было приемлемо: здесь риск в том, что именно реальный DOM
   формы определяет, куда инжектируется кнопка "Save filter" — синтетическая
   реконструкция рискует разойтись с реальной вёрсткой сильнее, чем для
   листинга).

Заблокированы: TC-040 (нужна replay-запись формы), TC-041/TC-042 (нужен
сидинг `filter_profiles`).

## Критерий готовности (Fixed)

- `seed_db.py` (или отдельный модуль) поддерживает прямую вставку записей
  `FilterProfile` (имя, queryString) без прохождения UI.
- Записана и лежит в `framework/data/recordings/` replay-запись страницы
  AO3 с формой Sort & Filter в исходной разметке (или обоснованно принято
  решение писать TC-040 через `recording_builder.py` по образцу
  `listing_basic.mitm`, если реальная запись недостижима/избыточна —
  решение test-designer/Lead, не test-maintainer единолично).
- Хотя бы один из трёх кейсов (TC-041 или TC-042, наименее зависящие от
  формы) доведён до зелёного прогона.
- Smoke без регресса.

## Анализ

Тот же класс, что AT-BUG-004 («механизм есть частично, продукта нет») —
но с двумя РАЗНЫМИ гранями (сидинг новой таблицы + real-DOM replay для
формы), которые стоит разделить на два инкремента при диспатче, а не
требовать одного воркера сразу и то, и другое. Приоритет ниже AT-BUG-004/
AT-BUG-005 (P1-кейсы против P0), severity minor. Fixed не ждёт сборку
приложения.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**2026-07-09T11:30:00Z — Lead (заведение бага, ответ на вопрос оператора):**
Обнаружено при попытке взять filter-profiles вторым R14-батчем сразу после
settings — область пропущена именно из-за этого долга, до сих пор жившего
только заметками в кейсах. Заведён test_debt-багом по аналогии с
AT-BUG-004/AT-BUG-005. Диспатч по B4 — отдельным проходом, после
приоритетных P0-хвостов (AT-BUG-004 остаток, AT-BUG-005).

**2026-07-09T12:00:00Z — test-maintainer (инкремент 1, грань 1 критерия готовности):**
Добавлена поддержка прямой вставки записей `filter_profiles` в
`framework/data/seed_db.py`: внутренняя `_insert_rows_filter_profiles(db, rows)`
(`INSERT OR REPLACE`, схема — точная копия MIGRATION_3_4 в `AppDatabase.kt` /
`FilterProfile.kt`: `id` TEXT PK, `name`/`queryString` TEXT NOT NULL, `timestamp`
INTEGER NOT NULL) и публичная `seed_filter_profiles(profiles: list[tuple[name,
queryString]])` по каркасу `seed()` (force_stop → ensure_db_initialized → pull →
insert → push); `id`/`timestamp` генерируются автоматически (uuid4/now-ms) — ни
TC-041, ни TC-042 не завязаны на конкретный id.

Витнес — device-free юнит-проба `framework/tests/test_seed_filter_profiles_unit.py`
(2 теста: вставка ожидаемых строк + `INSERT OR REPLACE` на дубликате PK) на
временной sqlite-БД с таблицей, созданной по схеме приложения в самом тесте.
Эмулятор в этом инкременте не трогался (был занят параллельным fix-verifier) —
проба переопределяет session-scoped autouse-фикстуру `_ensure_app_installed` из
`conftest.py` локально в модуле (стандартный механизм pytest: fixture в
тестовом файле перекрывает одноимённую из conftest.py), чтобы прогон не дёргал
`adb`. Прогон трижды подряд зелёный (0.08–0.15s, без device-фикстур):
`Invoke-Pytest tests/test_seed_filter_profiles_unit.py` → `2 passed`,
`PYTEST_EXIT=0`. `arch_check`: 0 ошибок/0 предупреждений.

Остаток (грани 2 и 3 критерия готовности не закрыты этим инкрементом): (2)
replay-запись страницы AO3 с формой Sort & Filter в исходной разметке (TC-040) —
отдельный диспатч, recordings/recording_builder не трогались; (3) зелёный
прогон TC-041/TC-042 на устройстве — требует ещё `seed_filter_profiles` в
`app_steps.py`/фикстуру conftest.py по образцу `seeded_library` и сам прогон с
Appium, не входило в скоуп этого инкремента (device не трогался вовсе). Статус
бага остаётся `Open`.

**2026-07-10T16:20:00Z — Lead (Fable), решение по грани 2 («реальная запись vs
recording_builder», развилка из критерия готовности):**
Решение: **реальная запись — первично**, recording_builder — только фолбэк.
Обоснование: предмет TC-040 — инжекция кнопки "Save filter" в реальную вёрстку
формы Sort & Filter; синтетическая реконструкция рискует разойтись именно в том
месте, которое тестируется (в отличие от `listing_basic.mitm`, где разметка
блёрбов — не предмет проверки). Порядок исполнения для будущего диспатча
(инкремент 2, test-maintainer):
1. Записать реальную страницу AO3 (search или tag browse) с формой Sort & Filter
   через mitmdump в режиме записи: `Start-Emulator -WritableSystem` → boot →
   `install-mitm-ca.sh` → прокси гостя `10.0.2.2:8080` (детали — HANDOFF «Как
   поднять окружение»). Запись — в `framework/data/recordings/`.
2. Критерий приёмки записи: в replay-режиме приложение открывает страницу, форма
   присутствует в исходной разметке (сверка по page_source / `ui_snapshot.py`),
   кнопка "Save filter" инжектируется bridge-скриптом.
3. Фолбэк (только если Cloudflare/R-03 не даёт стабильной записи за 2 попытки):
   `recording_builder.py`, но HTML формы берётся из РЕАЛЬНОГО сохранённого DOM
   реальной страницы (а не реконструируется по памяти); факт фолбэка, причина и
   источник DOM фиксируются здесь же в Обсуждении.
Очерёдность — по HANDOFF: после AT-BUG-007 (в работе) и R14 library-батча.

**2026-07-15T17:20:00Z — test-maintainer (инкремент 2, грани 2 и 3 критерия
готовности — ЗАКРЫВАЮТ бага, все 4 пункта критерия готовности выполнены):**

Грань 2 (реальная replay-запись формы Sort & Filter) — реальная запись, фолбэк
НЕ понадобился (стабильно с первой попытки):
- Записана `framework/data/recordings/sort_filter_form.mitm` (184 KiB) —
  реальная страница `https://archiveofourown.org/tags/Fluff/works` (tag-browse,
  соответствует `BrowserViewModel.FILTERABLE_PAGE`), записана через
  `mitmdump -w` в LIVE-режиме (реальный WebView-навигейт через Appium, прокси
  `10.0.2.2:8080`, эмулятор `-writable-system` + `install-mitm-ca.sh`/
  `Install-MitmCA` — по процедуре из решения Lead выше).
- Критерий приёмки записи проверен ДВАЖДЫ, обоими путями:
  (а) в момент самой LIVE-записи: WebView отрисовал реальную форму
  `#work-filters` (найдена по `document.querySelector`), кнопка "Save filter"
  инжектирована bridge-скриптом (`[data-ao3-save-profile]` найден в DOM) — это и
  есть предмет проверки TC-040 (инжекция в РЕАЛЬНУЮ вёрстку формы);
  (б) в REPLAY-режиме (тот же `.mitm`, тот же URL, через тот же WebView/Appium
  round-trip, без live-сети для точного URL): форма `#work-filters` присутствует
  в исходной разметке, кнопка "Save filter" инжектируется — round-trip
  подтверждён `page_source`-проверкой через реальный Appium-сеанс (не только
  offline HTTP-сверкой байтов, хотя она тоже сделана как промежуточный шаг:
  `mitm.start_replay` + сырой HTTP-клиент с ручной brotli-декомпрессией
  (`content-encoding: br`, ответ AO3 сжат) подтвердил `id="work-filters"` и
  `name="commit"` в теле байт-в-байт идентичного recorded-flow).
- Побочная находка (не блокер, для протокола): раскодировать `content-encoding:
  br` вручную понадобилось ТОЛЬКО для offline-сверки сырым `urllib`-клиентом
  (`brotli`-пакет уже в venv как транзитивная зависимость mitmproxy, отдельная
  установка не понадобилась) — сам WebView/chromedriver декодирует brotli
  прозрачно, эта деталь не влияет на тесты через `driver`.

Грань 3 (хотя бы один из TC-041/TC-042 зелёный) — выбран **TC-042** (не TC-041):
- TC-041 требует навигации С параметрами (`applyFilter` в `BrowserViewModel.kt`
  добавляет `work_search[...]` к URL при выборе профиля) — при `server_replay`
  результирующий URL НЕ совпадает ни с одним записанным flow (хэш матчинга —
  scheme+method+path+query+host+port, см. докстринг `recording_builder.py`) и
  уходит на живой AO3 (`server_replay_extra=forward`) — вносит недетерминизм/
  сетевую зависимость в offline по духу replay-тест. TC-042 этой проблемы не
  имеет: и переход в Settings, и раскрытие `FilterPanel` листинга (её текстовые
  пункты выпадашки) — целиком нативные/native-UI операции, listing-URL не
  меняется. Оставлено в очереди (не расширяю scope, D-0037) — либо принять
  live-переход для TC-041, либо расширить `recording_builder.py` записью под
  filtered-URL.
- Реализовано: `framework/tests/conftest.py::two_filter_profiles_seeded`
  (по образцу `seeded_library` — сидинг ДО сессии Appium), локаторы —
  `framework/screens/settings_screen.py::has_filter_profile/delete_filter_profile`
  (Compose IconButton `Rename`/`Delete` НЕ мержит content-desc с clickable-
  родителем — оба "Delete" на экране с одинаковым content-desc, диспамбигуация
  через XPath `following::` от текстового узла с именем профиля, сверено живым
  деревом `scripts/ui_snapshot.py`; секция «Saved AO3 Filters» ниже fold —
  добавлен свайп `swipe_to_text`/`swipe_up_to_text` до проверки, без него
  узлы отсутствуют в дереве вовсе, не просто за экраном) и
  `framework/screens/browser_screen.py::open_filter_dropdown/
  filter_dropdown_has_option` (нативная `FilterPanel` из `BottomBar.kt` — видна
  на ЛЮБОЙ странице, чей URL проходит `FILTERABLE_PAGE`, независимо от
  реальности формы Sort & Filter; используется существующая synthetic-фикстура
  `listing_basic.mitm`, отдельная реальная запись тут не нужна). Шаги — новые
  функции в `framework/steps/settings_steps.py`/`framework/steps/browser_steps.py`.
  Тест — `framework/tests/test_filter_profiles.py::test_delete_filter_profile`
  (`@pytest.mark.p1 @pytest.mark.replay`, `listing_basic.mitm`).
- Витнес: 3 прогона подряд зелёные —
  `Invoke-Pytest tests/test_filter_profiles.py -v` → `1 passed` (84–86s каждый),
  `PYTEST_EXIT=0` все три раза. `test-cases/filter-profiles/TC-042.md`:
  `automated_by: TC-042` (тест), статус кейса остаётся `Approved`.

Смоук без регресса: `Invoke-Pytest -m p0 -v` → **19 passed** (10м36с), включая
`TC-013` (класс AT-BUG-009 не проявился в этом прогоне — наблюдение №4,
позиционно-детерминированный флаки не на каждом прогоне). `arch_check.py` →
0 ошибок/0 предупреждений. `test_seed_filter_profiles_unit.py` (грань 1, файл
не трогался) — по-прежнему `2 passed`, регресса нет.

TC-040 (сам зелёный UI-тест) — не в скоупе этого инкремента (non-goals
диспатча: обязателен только факт успешной записи+верификации, не сам тест);
инфраструктура (`selectors.SAVE_PROFILE_BTN` уже существовал в
`framework/web/selectors.py` до этого инкремента) готова для будущей
автоматизации test-automator'ом при решении о переводе TC-040 в очередь.

**Итог: все 4 пункта критерия готовности закрыты** (сидинг — инкремент 1;
реальная запись+верификация — грань 2 этого инкремента; TC-042 зелёный x3 —
грань 3; смоук без регресса — выше). Статус переведён `Open → Fixed` (мандат
test-maintainer по B4, тот же test_debt-долг с этим же id уже был диспетчирован
дважды/один раз внутри одного бага двумя инкрементами — не новая задача).
Изменения на момент записи ещё НЕ закоммичены (см. `fixed_in`) — commit
hash добавит принимающая сторона после коммита. Таблицу «Верификация» ниже
намеренно не трогаю — по конвенции файла её заполняет fix-verifier.

Замеченный аналог вне owns (докладываю, не чиню — D-0037): в ходе диагностики
окружения этого инкремента дважды воспроизведён крэш `qemu-system-x86_64.exe`
(`0xc0000005`, Application-лог Windows) и серия зависаний Appium
`driver.get()`/`driver.current_context` (120–240с `ReadTimeoutError`) —
установлено экспериментально, что причина не в записи/replay-механике (та же
`.mitm`-запись и обычная навигация приложения без mitm ОБЕ повисали в
деградированном состоянии окружения), а в накопленной деградации сессии
эмулятора+Appium ПОСЛЕ моей же ошибки (случайный параллельный запуск ВТОРОГО
инстанса эмулятора в начале инкремента оставил стэйл-локи
`hardware-qemu.ini.lock`/`multiinstance.lock` в `tools/avd/ao3_test_api34.avd`).
Полный холодный ребут эмулятора (`-no-snapshot-load`, снятие стэйл-локов,
`Stop-NodeProcesses`+`Start-Appium` заново) устранил проблему полностью —
дальше ни одного зависания/крэша до конца инкремента. Новый test_debt-баг НЕ
заведён: это не пре-существующий дефект инфраструктуры, а последствие моей
собственной операционной ошибки (сам себя починил), детектор — сама попытка
воспроизвести на чистом окружении (см. класс F-9/правило 9 CLAUDE.md: чинил
класс — держать стэйл-локи под подозрением при следующем «висит на
wait-for-device»/зависании Appium после незапланированного параллельного
запуска эмулятора). Если кто-то столкнётся с ЭТИМ ЖЕ симптомом БЕЗ
предшествующего параллельного запуска — это уже другой класс, заводить
отдельно.
