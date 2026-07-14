---
id: AT-BUG-005
title: "SAF file/folder picker не автоматизируется штатными Appium-локаторами — блокирует TC-021 (P0, backup/restore) и часть download/backup-кейсов"
type: test_debt
debt_kind: missing_fixture
severity: major
status: Open
found_in: "test-designer при проектировании TC-021 (2026-07-02); подтверждено оператором как известный блокер (docs/HANDOFF.md 'Открытые хвосты', до 2026-07-09 не было заведено как bug-артефакт)"
fixed_in: ""
last_seen_in: ""
test_cases: ["TC-021"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-07-09T11:30:00Z"
updated: "2026-07-14T13:37:03Z"
reopen_count: 0
dispute_count: 0
awaiting: none
lock: ""
---

# AT-BUG-005 — SAF picker не автоматизируется штатно

## Окружение
- Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
  `debt_kind: missing_fixture`). Известен с проектирования TC-021
  (2026-07-02), до сих пор жил только как заметка в теле кейса и упоминание
  в `docs/HANDOFF.md` («Открытые хвосты») — не был заведён как отслеживаемый
  bug-артефакт, поэтому не виден правилу «Устранить test debt» (B4) и
  конвейеру вообще.

## Суть долга

`test-cases/backup/TC-021.md` (P0, area backup, risk R-01 — «Backup →
Clear all ratings → Restore возвращает исходные данные») требует
взаимодействия с системным Storage Access Framework (SAF) file picker для
выбора файла экспорта/импорта бэкапа. SAF picker — системный UI (Files app /
DocumentsUI), обычно НЕ автоматизируется напрямую через стандартные
Appium-локаторы приложения (другой process/package, нестабильные
resource-id между версиями Android/OEM).

Из «Заметки для автоматизации» TC-021: нужно уточнить, есть ли уже готовый
обходной путь (intent-подмена / известный стабильный путь через системный
Files app) — до появления обхода кейс не автоматизируется штатно.

Заблокирован: TC-021 (P0, backup). Потенциально тот же блокер актуален для
любых будущих download/backup-кейсов, где пользователь явно выбирает файл/
папку через системный picker (не просто чтение файла по известному пути
через adb push, как уже сделано в TC-034/035/036 — там SAF не участвует).

## Критерий готовности (Fixed)

- Найден и задокументирован способ автоматизации SAF picker (intent-подмена
  через `ACTION_CREATE_DOCUMENT`/`ACTION_OPEN_DOCUMENT` с заранее известным
  URI, ИЛИ стабильный путь через `UiAutomator2`/`UiScrollable` по системному
  Files app, ИЛИ иной обход) — зафиксирован как переиспользуемый
  step/fixture во `framework/`.
- TC-021 доведён до зелёного прогона с использованием найденного обхода.
- Smoke без регресса.

## Анализ

Класс «механизм не автоматизируется штатно» — не механизм отсутствует
(как в AT-BUG-004, где replay был спайкнут, но не подключён), а сам
системный компонент вне периметра приложения. Требует разведки (scout)
перед реализацией: есть ли в экосистеме Appium/UiAutomator2 готовый паттерн
для SAF на API 34, прежде чем test-maintainer/test-automator берётся за
фикстуру. Чинит фабрика по правилу «Устранить test debt» (B4); Fixed не
ждёт сборку приложения.

## Спека фикса (Lead, 2026-07-09; DoD будущего диспатча test-maintainer)

Основание — принятая scout-разведка (журнал 12:43:54, след сверен Lead'ом):

- Приложение использует `ActivityResultContracts`, не сырые интенты:
  `CreateDocument("application/json")` — экспорт бэкапа, SettingsScreen.kt:617,
  дефолтное имя `ao3_backup_$date.json`; `GetContent()` — импорт, :613;
  `OpenDocumentTree()` — папка загрузок, :597, с
  `takePersistableUriPermission`.
- Готовых обходов SAF и кросс-пакетных хелперов во framework/ нет;
  activate_app-паттерн для СВОЕГО пакета есть в app_steps.py:65-66.
- TC-038 — тот же класс блокера (OpenDocumentTree).

**Выбранный путь: прохождение системного DocumentsUI той же
UiAutomator2-сессией.** Intent-подмена отвергнута: контракты зашиты в код
приложения, подмена потребовала бы правок app-under-test (запрещено).
UiAutomator2 видит все пакеты, DocumentsUI (`com.android.documentsui` на
AOSP API 34) — классические View, не Compose: стандартные локаторы и
scroll-паттерны применимы.

**Состав работы:**

1. Page object `framework/screens/documents_ui.py` — три поверхности
   DocumentsUI: (а) диалог сохранения CreateDocument (поле имени файла,
   кнопка SAVE); (б) браузер файлов GetContent (список документов,
   навигация по каталогам, roots-drawer); (в) выбор папки OpenDocumentTree
   (кнопка «USE THIS FOLDER» + системный confirm ALLOW).
2. Steps `framework/steps/saf_steps.py`:
   `saf_save_document(filename: str | None)` — подтвердить (опционально
   переименовав) и сохранить; `saf_pick_file(display_name)` — выбрать файл;
   `saf_pick_folder(subpath: str | None)` — выбрать папку и подтвердить
   доступ.
3. Локаторы выводить ИЗ ЖИВОГО ДЕРЕВА (`python scripts/ui_snapshot.py` при
   открытом пикере): DocumentsUI — не наш код, «места рендера» в репо нет,
   поэтому первый шаг локаторной дисциплины пропускается по определению;
   скриншот — последний резерв. Искать по resource-id
   `com.android.documentsui:id/*` и `android:id/*`, НЕ по координатам и НЕ
   по индексам.
4. Детерминизм: тестовые файлы/каталоги готовить заранее adb-шеллом
   (`/sdcard/Download` или `/sdcard/Documents`), teardown удаляет созданное
   (и файлы экспорта тоже). Проверить и задокументировать в докстринге
   steps: сбрасывается ли persisted URI-грант (`takePersistableUriPermission`)
   существующим `pm clear` в фикстурах — если нет, описать способ сброса.
5. Ловушки: стартовый каталог DocumentsUI недетерминирован (последний
   использованный) — навигацию начинать с явного выбора root'а; первое
   открытие бывает медленным — ждать элементов через wait_for, не sleep.

**DoD инкремента (проверяемый):** probe-тест
`framework/tests/test_saf_infra_probe.py` (по образцу
`test_replay_infra_probe.py` — доказательство пригодности инфраструктуры,
НЕ автоматизация кейса): (1) экспорт — пройти CreateDocument-пикер, файл
существует (adb ls) и содержит валидный JSON; (2) импорт — пройти
GetContent-пикер на созданном файле, приложение приняло данные; (3) выбор
папки через OpenDocumentTree отработал. Все три зелёные 2 прогона подряд;
smoke без регресса; app-under-test не тронут; arch_check 0/0. Автоматизация
самого TC-021 — НЕ в этом инкременте (это test-automator после снятия
блокера; полный критерий Fixed закрывается после неё).

**Требование к среде:** эмулятор свободен (probe гоняет живую
Appium-сессию) — диспатчить после завершения текущих device-работ.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**2026-07-09T11:30:00Z — Lead (заведение бага, ответ на вопрос оператора):**
SAF-блокер существовал только как заметка в TC-021 и строка в HANDOFF —
не был виден конвейеру. Заведён явным test_debt-багом по аналогии с
AT-BUG-004 (правило 9 CLAUDE.md: находка, не заведённая как отслеживаемый
артефакт, — сама по себе нарушение, если оставлена молча). Диспатч по B4 —
следующим проходом; рекомендую начать со scout-разведки существующих
паттернов обхода SAF в Appium-экосистеме, прежде чем тратить ярус
test-maintainer/test-automator.

**2026-07-09T17:05:00Z — Lead (Fable):** scout-разведка выполнена и принята
(журнал 12:43:54); по её итогам написана «Спека фикса» (секция выше) —
путь через DocumentsUI той же UiAutomator2-сессией, intent-подмена
отвергнута (потребовала бы правок app-under-test). Диспатч test-maintainer
по спеке — как только эмулятор освободится от текущих device-работ
(fix-verifier at-bug-004-verify).

**2026-07-09T20:23:00Z — test-maintainer (инкремент 1 инфраструктуры SAF):**
Реализовано по спеке выше. Локаторы DocumentsUI выведены с живого дерева
(`python scripts/ui_snapshot.py` на открытом пикере, emulator-5554) на всех
трёх поверхностях — по `resource-id` (`com.android.documentsui:id/*` /
`android:id/*`), без координат/индексов, за одним документированным
исключением (`DocumentsUIScreen._root_breadcrumb_segment` — первый сегмент
breadcrumb'а, обоснование см. докстринг: имя root'а на OpenDocumentTree —
имя устройства/AVD, недетерминировано между хостами, drawer там отсутствует
вовсе на single-root устройстве).

Находки при разведке (важны для test-automator при сборке TC-021):
- САМ каталог "Download" (и другие стандартные top-level директории верхнего
  уровня — DCIM/Pictures/...) через `OpenDocumentTree` выбрать НЕЛЬЗЯ:
  системная защита приватности блокирует кнопку USE THIS FOLDER («Can't use
  this folder, to protect your privacy, choose another folder») — нужна
  ВЛОЖЕННАЯ подпапка.
- Экспериментально подтверждено: `pm clear <pkg>` (уже используется в
  `clean_app`) сбрасывает persisted URI permission grant на стороне ОС
  (`adb shell dumpsys activity permissions` — грант исчезает сразу после
  `pm clear`, до него был виден). Отдельный отзыв гранта в teardown не нужен.
- Возврат из внешней Activity (DocumentsUI) сбрасывает scroll-позицию экрана
  Settings на верх — `assert_download_folder_label` докручивает заново.

Классовая полнота (правило 9 CLAUDE.md): блокер AT-BUG-005 — не только TC-021.
`saf_steps.saf_pick_folder` (OpenDocumentTree-поверхность) устроен по
`subpath`, не завязан на конкретный кейс — он ЗАКРЫВАЕТ и блокер TC-038 (тот
же класс, «выбор папки загрузок через системный picker», см. «Анализ» выше)
БЕЗ отдельной доработки: test-automator может переиспользовать её напрямую
при автоматизации TC-038, как и TC-021.

Состав: `framework/screens/documents_ui.py`, `framework/steps/saf_steps.py`,
`framework/tests/test_saf_infra_probe.py` (три пробы: CreateDocument-экспорт,
GetContent-импорт, OpenDocumentTree-выбор папки) — все новые файлы,
`app-under-test/` не тронут. Witness: `python -m pytest tests/test_saf_infra_probe.py -v`
(framework/.venv, `AO3_MODE=live`) — 2 прогона подряд, `3 passed` в обоих
(106–107s), `PYTEST_EXIT=0`; `python scripts/arch_check.py` — `ошибок 0,
предупреждений 0`. Smoke (`Invoke-Pytest -m p0`) — НЕ прогнан до конца:
дважды подряд зависал на `tests/test_rating.py::test_rate_work_from_work_page_panel[READ-...]`
(живой AO3), процесс приложения не находился (`pidof` пуст) при
`ResumedActivity` всё ещё указывающей на него, фокус WM — на launcher; оба
раза дерево процессов убито вручную (первый раз — Lead, второй — я, по его
явному указанию не крутить цикл третий раз). Это симптом другого класса
(нестабильность `test_rating.py`/эмулятора на живом AO3, файл не тронут этим
инкрементом, пересечения с SAF-путями нет) — не блокирует Fixed этого
инкремента, но требует отдельного разбора (кандидат на новый test_debt/
quarantine, не на этот баг). Полный критерий Fixed (зелёный TC-021) —
следующий инкремент, статус осознанно оставлен Open.

**2026-07-09T20:44:00Z — test-maintainer (инкремент 1, attempt 2, после
ДОРАБОТАТЬ critic):** Блокер устранён. `saf_probe_workspace`
(`test_saf_infra_probe.py`) держал `mkdir` подпапки ДО общего try/finally, а
`_adb_push` — в собственном отдельном try/finally, который чистил только
локальный temp-файл; если `mkdir` отрабатывал, а push падал ДО yield,
device-уборка (`finally` на :98-101 в старой версии) не выполнялась вовсе —
тот же класс, что AT-BUG-004 инкремент 2 (teardown обязан покрывать ЛЮБУЮ
точку отказа setup, не только yield). Исправлено по образцу `replay`
(`conftest.py`): единственный `try` оборачивает mkdir + push + yield,
единственный `finally` безусловно чистит temp-файл и все три device-цели.
Докстрин фикстуры больше не только ссылается на паттерн `replay`, а
воспроизводит его структуру дословно.

Доказательство закрытия блокера: временная (не закоммиченная) инъекция
отказа в `_adb_push` — `raise RuntimeError(...)` перед вызовом `adb push`,
`mkdir` подпапки успевал отработать до неё. Прогон
`test_saf_export_via_create_document` упал на setup с этим исключением
(`ERROR at setup ... RuntimeError: TEMP FAULT INJECTION`), после чего
`adb shell ls -la /sdcard/Download/` — `total 0` (подпапка НЕ утекла). Инъекция
сразу же убрана (`git diff` подтверждает отсутствие следов).

Дополнительно (некритичные замечания critic):
- Добавлена строка о классовой полноте выше («Классовая полнота»):
  `saf_pick_folder` без доработки закрывает и блокер TC-038.
- Докстринг `DocumentsUIScreen._root_breadcrumb_segment` уточнён: тап
  срабатывает не «несмотря на clickable=false», а потому что
  `BaseScreen.tap` ждёт `EC.element_to_be_clickable`, которое в Selenium
  проверяет `is_displayed()`/`is_enabled()`, а не атрибут `clickable`
  accessibility-дерева (сверено по исходнику
  `selenium/webdriver/support/expected_conditions.py`); Android-сторона —
  отдельный факт (обработчик клика на itemView реагирует на touch
  независимо от значения атрибута).

Witness (attempt 2): `Invoke-Pytest tests/test_saf_infra_probe.py -v` — 2
прогона подряд, `3 passed in 114.38s` и `3 passed in 112.12s`, `PYTEST_EXIT=0`
в обоих; `/sdcard/Download` пуст после каждого. `python scripts/arch_check.py`
— `ошибок 0, предупреждений 0`. Smoke не гонялся по указанию Lead (зависание
диагностировано critic'ом как непричастное этому диффу). Статус бага остаётся
Open (без изменений критерия).

**2026-07-14T12:10:00Z — test-automator (TC-021 автоматизирован, последний
пункт критерия Fixed закрыт):** `framework/tests/test_backup_restore.py::
test_backup_clear_restore_returns_original_data` реализован по инфраструктуре
инкремента 1 (`documents_ui.py`/`saf_steps.py` без изменения контракта —
только обратно-совместимые добавления, см. ниже) и зелёный 3/3 подряд
(58.60s/57.64s/59.38s, `PYTEST_EXIT=0` во всех). Полное покрытие полей: 5 работ
(по одной на рейтинг) с непустыми comment/tags через `seed_with_comment`;
Backup → Clear all ratings → Restore из того же файла; проверка диалогов
результата с точным текстом counts, присутствия в вкладках Library и полного
совпадения rating/comment/tags/fandom/word_count через прямое чтение Room
(`framework/data/seed_db.py::read_work_ratings`, новая функция — обходит
локале-зависимое форматирование числа word_count в тексте карточки Library).

Доработка инфраструктуры (обратно совместимая, найдена при сборке TC-021, не
покрыта тремя пробами инкремента 1, т.к. пробы каждая открывают Settings ровно
один раз с холодного старта): `saf_steps.open_settings_scrolled_to` внутри
вызывает `app_steps.wait_ui_ready` (ищет `android.webkit.WebView`) — WebView
существует в дереве ТОЛЬКО на вкладке Browse (`framework/screens/
navigation.py`), поэтому повторный вызов этой функции, пока уже открыт
Settings (TC-021: между «Clear all ratings» и «Restore» нужно вернуться в
Settings и докрутиться заново), гарантированно таймаутит — на вкладке
Settings/Library WebView в дереве нет. Аналогично `SettingsScreen.is_loaded()`
(ищет заголовок "Theme" — самую верхнюю секцию экрана) не находит его, если
текущая позиция уже проскроллена вниз. Добавлена `saf_steps.
rescroll_settings_to` — тот же скролл до текста, но без обеих проверок
«свежего» открытия; плюс `BaseScreen.swipe_up_to_text` (обратное направление
свайпа) — после «Clear all ratings» (Compose-диалог, скролл НЕ сбрасывается,
в отличие от возврата из внешней DocumentsUI Activity) нужно вернуться к
«Restore», расположенному ВЫШЕ текущей позиции, а исходный `swipe_to_text`
скроллит только вниз. Обе доработки не меняют поведение существующих трёх
проб (`open_settings_scrolled_to`/`saf_save_document`/`saf_pick_file`
сохранили старую сигнатуру с обратно совместимыми опциональными
параметрами/новыми отдельными функциями) — regression-прогон
`test_saf_infra_probe.py` подтверждает: 3/3 без изменений.

Witness: `Invoke-Pytest tests/test_backup_restore.py -v` — 3 прогона подряд
(`1 passed in 58.60s` / `57.64s` / `59.38s`, `PYTEST_EXIT=0` во всех);
`Invoke-Pytest tests/test_saf_infra_probe.py -v` — `3 passed in 107.32s`,
`PYTEST_EXIT=0` (regression без изменений); `python scripts/arch_check.py` —
`ошибок 0, предупреждений 0`. `app-under-test/` не тронут.

Последний открытый пункт критерия Fixed («TC-021 доведён до зелёного
прогона») закрыт этим инкрементом. Статус бага НЕ меняю (Open→Fixed —
переход test-maintainer/Lead по D-0037/матрице «Роль ≠ ярус», не входит в
мандат test-automator) — оформляется отдельно.

**2026-07-14T13:37:03Z — test-maintainer (финальный инкремент, сверка
критерия Fixed, переход Open→Fixed НЕ выполнен):**

Сверка по пунктам критерия готовности:
1. «Найден и задокументирован способ автоматизации SAF picker ... зафиксирован
   как переиспользуемый step/fixture во `framework/`» — ПОДТВЕРЖДЕНО.
   `framework/screens/documents_ui.py`, `framework/steps/saf_steps.py`
   существуют (`Test-Path` — оба `True`), приняты инкрементом 1/attempt 2 с
   critic-входом (см. записи выше).
2. «TC-021 доведён до зелёного прогона с использованием найденного обхода» —
   ПОДТВЕРЖДЕНО. `framework/tests/test_backup_restore.py` существует, витнес
   test-automator'а (3/3 зелёных, 58.60s/57.64s/59.38s, `PYTEST_EXIT=0`) принят
   Lead'ом (журнал tc021-automation, 11:18).
3. «Smoke без регресса» — НЕ ПОДТВЕРЖДЕНО. `test_backup_restore.py` несёт
   `@pytest.mark.p0` (проверено чтением файла) — состав smoke ФАКТИЧЕСКИ
   изменился после прогона fix-verifier'а 10:50 (тогда TC-021 ещё не было в
   дереве), поэтому опереться на тот прогон нельзя (задача явно требовала
   собственного `-m p0` в этом случае). Прогнала сама: эмулятор поднят
   (`Start-Emulator`), Appium поднят (`Start-Appium`), `app-debug.apk`
   переустановлен (`Install-App`), `Invoke-Pytest -m p0` — **collected 41 items
   / 22 deselected / 19 selected** (18 прежних + TC-021, подтверждает
   расширение состава) → **18 passed, 1 failed** (`tests/test_visibility.py::
   test_disliked_hidden_on_listing[listing_basic.mitm]`, TC-013,
   `1 failed, 18 passed, 22 deselected, 1 rerun in 1525.73s (0:25:25)`,
   `PYTEST_EXIT=1`). Падение — `urllib3.exceptions.ReadTimeoutError:
   HTTPConnectionPool(host='127.0.0.1', port=4723): Read timed out. (read
   timeout=120)` внутри `browser_steps.open_listing` → `driver.get(url)`, ПОСЛЕ
   отработавшего ретрая таймаут-гейта AT-BUG-007 (`R` → повтор → тот же класс).
   `TC-021`/SAF-инфраструктура НЕ участвуют в этом падении (другой файл, другая
   область — `test_visibility.py`, replay-фикстура); значит регресс НЕ вызван
   изменениями этого бага, но формально критерий «smoke без регресса» этим
   прогоном не выполнен. По прямому указанию задачи («если p0-прогон вскроет
   регресс — не чинить: верни result: failed, статус бага не меняй») —
   **переход Open→Fixed НЕ выполняю**, статус остаётся `Open`.

Новый блокер заведён отдельным test_debt-багом `bugs/AT-BUG-009.md`
(`debt_kind: flaky_test`, единичное наблюдение, TC-013/`test_visibility.py`,
не пересекается с SAF/backup-областью этого бага) — без него находка не
попадёт в очередь B4 (правило 9 CLAUDE.md). Дальнейший разбор — за Lead
(диспетчеризация нового бага) и/или test-designer (решение о карантине TC-013,
если флаки подтвердится системным).

Прочее по DoD этого прохода: `python scripts/arch_check.py` — `ошибок 0,
предупреждений 0`. Эмулятор, поднятый мной для этой проверки, погашен после
завершения (`taskkill` дерева процессов эмулятора/Appium; `Get-Device` →
`NO DEVICE` подтверждено отдельным вызовом ниже в отчёте задачи).
`app-under-test/` не тронут; правки этого хода — только `bugs/AT-BUG-005.md` и
новый `bugs/AT-BUG-009.md`.
