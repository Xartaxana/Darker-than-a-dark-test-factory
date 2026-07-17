---
key: "AT-BUG-005"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p1"
summary: "SAF file/folder picker не автоматизируется штатными Appium-локаторами — блокирует TC-021 (P0, backup/restore) и часть download/backup-кейсов"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-021", "test_case:TC-038", "test_case:TC-039", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-18T00:20:00Z"
updated: "2026-07-18T00:20:00Z"
archived: false
resolution: "done"
---

# SAF file/folder picker не автоматизируется штатными Appium-локаторами — блокирует TC-021 (P0, backup/restore) и часть download/backup-кейсов

_Спроецировано из `bugs/AT-BUG-005.md` (источник правды).
Статус в нашей машине: **Verified**._

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
| 2026-07-17/18 | framework HEAD (fixed_in commit, не переустанавливалась в этой сессии — device-инвариантный test_debt) | Полный `Invoke-Pytest -m p0 -v` (19 selected, включает TC-021 `test_backup_restore.py`) | `19 passed, 41 deselected in 585.00s (0:09:44)`, `PYTEST_EXIT=0` — TC-021 PASSED первым в списке (5%), ни одного failed/error | Verified |

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

**2026-07-14T21:00:00Z — test-maintainer (повторная попытка финального
инкремента, сверка пункта 3 «Smoke без регресса», переход Open→Fixed СНОВА
НЕ выполнен — падает «что-то другое», не тот же класс):**

Контекст: с прошлой попытки (запись выше, 13:37:03Z) `bugs/AT-BUG-009.md`
получил инкремент 1 (timeout-обёртка `adb.py`/`mitm.py`, `ADB_SHELL_TIMEOUT`/
`ADB_TRANSFER_TIMEOUT` в `settings.py`) — полный p0 после него ещё не
гонялся. Прогнала: `Start-Emulator` (обычный буд) → `Get-Device` →
`emulator-5554`; `Start-Appium`; `Install-App` (`app-debug.apk` текущего
HEAD); `Invoke-Pytest -m p0` — **collected 46 items / 27 deselected / 19
selected** → **16 passed, 3 errors**, `16 passed, 27 deselected, 3 errors
in 644.99s (0:10:44)`, `PYTEST_EXIT=1`.

Сверка с матрицей задачи:
- НЕ `19/19 passed` — переход Open→Fixed не применяется.
- НЕ «TC-013 снова падает тем же классом»: прошлый раз (13:37:03Z) TC-013
  падал `FAILED` В ТЕЛЕ теста (`ReadTimeoutError` внутри
  `browser_steps.open_listing`→`driver.get`, после rerun-гейта
  AT-BUG-007). В этот раз TC-013 падает `ERROR` НА SETUP (фикстура
  `seeded_library`→`seed_db.ensure_db_initialized`→`adb.shell("am start
  -W ...")`→`TimeoutError` из обёртки `core/adb.py::_run()`, добавленной
  самим инкрементом 1 AT-BUG-009) — другой класс исключения, другая фаза,
  другой код. Плюс ДВА других теста (`test_rating.py::
  test_rate_work_from_work_page_panel[SAVE-placeholder_seeded_work0]` и
  `[READ-placeholder_seeded_work2]`) упали ТЕМ ЖЕ новым классом — TC-013
  больше не единственная жертва.
- → Это ветка «Падает что-то другое»: статус НЕ меняю (остаётся `Open`),
  полная диагностика внесена в `bugs/AT-BUG-009.md` (запись «наблюдение
  №3», та же дата) — область (adb-timeout/p0-стабильность) прямо
  принадлежит открытому test_debt-багу AT-BUG-009, дублирующий бag не
  завожу (Grep bugs/ выполнен, покрывающий Open test_debt уже есть).
  SAF/backup-область этого бага (`documents_ui.py`/`saf_steps.py`/
  `test_backup_restore.py`) НЕ участвует ни в одном из трёх падений —
  регресс не вызван изменениями AT-BUG-005, но формально критерий «smoke
  без регресса» этим прогоном СНОВА не выполнен, теперь по причине,
  находящейся вне поля зрения AT-BUG-005 (домен AT-BUG-009).

Полный traceback трёх ошибок, диагностика на месте (`pidof`, тайминги
adb, ручной повтор `am start -W`) и разбор корня (архитектурный пробел
стыка ретрая `ensure_db_initialized` с новой обёрткой `adb.shell()`) — в
`bugs/AT-BUG-009.md`, не дублирую здесь. Не чиню (scope этого прохода
явно исключает правки `framework/`, D-0037; и правка обёртки/ретрая — не
SAF/backup-область этого бага).

`python scripts/arch_check.py` (без правок кода в этом ходе, контрольный
прогон) — `ошибок 0, предупреждений 0`. `app-under-test/` не тронут.
Правки этого хода — только `bugs/AT-BUG-005.md` (эта запись) и
`bugs/AT-BUG-009.md` (наблюдение №3); ни один framework-файл не менялся.
Эмулятор/Appium погашены после завершения, `Get-Device` → `NO DEVICE`
подтверждено отдельным вызовом.

**2026-07-14T22:15:00Z — test-automator (TC-038 автоматизирован; новая
находка в OpenDocumentTree-поверхности — flaky, не блокирует, но
документируется по правилу 9 CLAUDE.md):**

`framework/tests/test_downloads.py::
test_change_download_folder_triggers_silent_scan_and_relinks_orphan_file`
реализован по инфраструктуре инкремента 1 (`saf_steps.saf_pick_folder` без
изменения контракта) и зелёный 3/3 подряд (41.59s/44.14s/41.85s,
`PYTEST_EXIT=0` во всех). Заметка «SAF picker — без обходного пути не
автоматизируем» в TC-038.md снята (устарела, см. правку кейса) — блокер
закрыт этим же инкрементом AT-BUG-005, как и предсказано записью
«Классовая полнота» выше.

**Новая находка (flaky, не блокер для TC-038, но затрагивает КЛАСС «повторный
вызов OpenDocumentTree на тот же subpath»):** при отладке нестабильности (см.
ниже) обнаружено, что `DocumentsUIScreen.reset_to_root()` (`tap` по
`_root_breadcrumb_segment`, `instance(0)` breadcrumb'а) может БЕСКОНЕЧНО
таймаутить (`EC.element_to_be_clickable` никогда не становится true), когда
OpenDocumentTree на СТАРТЕ открывается СРАЗУ в ТОЙ ЖЕ подпапке, что была
подтверждена (ALLOW) на непосредственно предыдущем вызове picker'а ЭТИМ ЖЕ
тестовым процессом (т.е. «текущая цель совпадает с последней подтверждённой
папкой предыдущего вызова»). В этом состоянии живое дерево показывает
корневой сегмент breadcrumb'а (`text="Android SDK built for x86_64"`,
`instance(0)`) с атрибутом `enabled="false"` (остальные сегменты и сама
кнопка USE THIS FOLDER — `enabled="true"`, экран полностью прогружен, не
транзиентная загрузка) — `BaseScreen.tap` ждёт именно `is_enabled()`
(см. докстринг `_root_breadcrumb_segment` про `element_to_be_clickable`),
поэтому таймаут гарантирован, а не случаен, ПОКА держится это состояние.

Воспроизведено ДЕТЕРМИНИРОВАННО дважды подряд на двух РАЗНЫХ тестах при
запуске `-k <тот же тест>` back-to-back (без промежуточного запуска других
SAF-сценариев):
1. Мой новый тест (2-й прогон сразу после 1-го зелёного, subpath
   `Download/tc038_orphan_relink` неизменный) — упал на `reset_to_root()`.
2. УЖЕ ПРИНЯТАЯ проба `test_saf_infra_probe.py::test_saf_pick_download_folder`
   (subpath `Download/at_bug_005_saf_probe`, тоже неизменный) — упала ТЕМ ЖЕ
   способом при запуске `-k folder` дважды подряд (её штатный regression-прогон
   `Invoke-Pytest tests/test_saf_infra_probe.py -v`, где folder-проба всегда
   ОДНА в процессе после export/import-проб на CreateDocument/GetContent,
   НЕ реплицирует — 3/3 зелёных, см. ниже; условие требует именно ПОВТОРНОГО
   вызова OpenDocumentTree на тот же subpath в БЛИЗКОМ по времени соседнем
   процессе). Это подтверждает: находка КЛАССОВАЯ (сама поверхность
   OpenDocumentTree/`reset_to_root`), не специфична для TC-038 — уже
   принятая, ранее «зелёная N/N» инфраструктура несёт тот же изъян,
   вероятно ранее не пойманный из-за недетерминированного тайминга
   (гипотеза: воспроизводится, когда процесс `com.android.documentsui`
   не был убит/вытеснен системой между двумя соседними вызовами и донёс
   закешированное состояние breadcrumb-адаптера; между более разнесёнными
   по времени прогонами process, видимо, успевает быть переиспользован
   системой заново — что и объясняет прежние «2/2»/«3/3» заявленные
   прогоны этой же пробы).

**Обход на уровне теста (НЕ фикс инфраструктуры):** `orphan_download_relink_seeded`
(`test_downloads.py`) генерирует УНИКАЛЬНОЕ имя подпапки на КАЖДЫЙ вызов
(`uuid4().hex[:10]`-суффикс, не константа) — гарантирует, что цель текущего
прогона никогда не совпадает с последней подтверждённой папкой предыдущего,
ломая единственное известное условие репродукции. С этим обходом TC-038
зелёный 3/3 подряд (см. выше), включая прогон сразу-после-прогона (тот же
паттерн, что воспроизвёл баг до обхода). Существующая проба
`test_saf_infra_probe.py` НЕ переведена на уникальные имена (её subpath
константа `_PROBE_SUBFOLDER` — вне owns этого прохода, правка чужого уже
принятого файла не требовалась для DoD TC-038); её штатный regression-прогон
(все три пробы одним процессом) 3/3 зелёный без изменений
(115.35s/112.80s/108.12s, `PYTEST_EXIT=0` во всех) — воспроизводится только
при изолированном `-k folder` дважды подряд, что не входит в её обычный
паттерн запуска.

**Классовая полнота (правило 9 CLAUDE.md):** находка распространяется на
ЛЮБОЙ будущий вызов `saf_pick_folder` с фиксированным (не уникальным)
subpath, повторяемый в БЛИЗКОМ по времени соседнем pytest-процессе —
кандидаты на будущий ремонт: (а) `documents_ui.reset_to_root()` — сделать
устойчивым к `enabled="false"` корневого сегмента (например, ждать смены
атрибута с более длинным таймаутом ПЕРЕД `tap`, или падать явной ошибкой с
диагностикой вместо голого таймута `element_to_be_clickable`, или
альтернативный путь навигации, не зависящий от корневого сегмента); (б)
`saf_probe_workspace`/аналоги — рассмотреть тот же приём уникальных имён,
если проба когда-нибудь начнёт запускаться изолированно/повторно в CI.
Критерий готовности (Fixed) этого бага НЕ расширяю (SAF picker
автоматизируется штатно — по-прежнему верно, TC-021 и TC-038 оба зелёные);
находка — уточнение «Анализа», не новый пункт критерия. Статус бага
(`Open`, по независимой причине — smoke-регресс AT-BUG-009, см. запись
21:00:00Z) не меняю.

Witness: `Invoke-Pytest tests/test_downloads.py -k orphan -v` — 3 прогона
подряд (`1 passed in 41.59s` / `44.14s` / `41.85s`, `PYTEST_EXIT=0` во всех,
включая один прогон, упавший НЕ по этой находке, а по известному
AT-BUG-009 (`adb shell am start -W` timeout в `ensure_db_initialized`,
согласно спеке задачи — перезапущен без правок `seed_db.py`));
`Invoke-Pytest tests/test_saf_infra_probe.py -v` — 3 прогона подряд
(`3 passed in 115.35s` / `112.80s` / `108.12s`, `PYTEST_EXIT=0` во всех,
regression без изменений файла); `python scripts/arch_check.py` —
`ошибок 0, предупреждений 0`. `app-under-test/` не тронут. Правки этого
хода вне `bugs/`: `framework/tests/test_downloads.py` (новый тест +
фикстура), `framework/steps/settings_steps.py` (диалог «Scan complete» —
по образцу `backup_steps.py`), `framework/core/adb.py` (`push_external` —
аналог `push_app_file` для публичного `/sdcard`), `framework/data/works.py`
(`ORPHAN_RELINK_TARGET`), `test-cases/downloads/TC-038.md`,
`state/traceability.md`.

**2026-07-15T13:35:00Z — test-automator (TC-039 автоматизирован; новая
находка в OpenDocumentTree-поверхности — race, не flaky-таймаут как выше, но
тот же класс «поведение `setDownloadFolderUri` за пределами задокументированного
на момент инкремента 1»):**

`framework/tests/test_downloads.py::test_restore_folds_orphan_scan_into_single_dialog`
реализован по инфраструктуре инкремента 1 (`saf_steps.saf_pick_folder`,
`saf_pick_file` без изменения контракта) и зелёный 3/3 подряд
(58.88s/51.26s/56.36s, `PYTEST_EXIT=0` во всех).

**Новая находка (race, не блокер для TC-039 — обойдена на уровне теста, но
затрагивает КЛАСС «файл кладётся в SAF-папку вокруг момента её выбора»):**
`SettingsViewModel.setDownloadFolderUri` (`SettingsScreen.kt:523-529`) САМА
синхронна (обновляет `uiState`/prefs/`downloadRepo.customFolderUri` в теле
функции), но запускаемый ею `scanForDownloads(silent=true)` работает
АСИНХРОННО (`viewModelScope.launch(Dispatchers.IO)`) — тап ALLOW в SAF-пикере
(и, соответственно, возврат `saf_steps.saf_pick_folder`) НЕ гарантирует, что
эта корутина уже прошлась по каталогу. Если положить целевой orphan-файл в
папку ДО её выбора и рассчитывать (как для TC-038, где это штатно и
безопасно) на синхронность скана — для TC-039 это ломает сценарий: работа с
тем же `ao3Id` из backup ЕЩЁ НЕ существует в Room на момент этого скана
(Given кейса — Library пуста), поэтому скан ДОБАВЛЯЕТ пустую stub-строку
(`existing == null -> added++`) РАНЬШЕ, чем Restore успевает импортировать
работу из backup, — и `importFromUri` видит `ao3Id in existingIds`,
ПРОПУСКАЯ работу как дубликат. Воспроизведено ДЕТЕРМИНИРОВАННО на первом же
прогоне этого теста: диалог показал «Restored 0 works, 0 filters (1 works
already existed).» вместо ожидаемого объединённого «Restored 1 works, 0
filters. Also relinked 1 and added 0 downloaded file(s).» — не редкий флейк,
а прямое следствие того, что тест изначально клал файл ПОСЛЕ `saf_pick_folder`
без какой-либо синхронизации с этой асинхронной корутиной (тот же незримый
разрыв, только в другую сторону: скан «догнал» размещение файла быстрее, чем
ожидалось).

**Обход на уровне теста (НЕ фикс инфраструктуры):** `restore_scan_workspace`
кладёт в подпапку ЗАРАНЕЕ decoy-файл с ЧУЖИМ `ao3Id` (не участвующим ни в
backup, ни в assert'ах). Раз decoy найден (`totalFound=1`), диалог «Scan
complete» появляется НЕСМОТРЯ на `silent=true` (подавляется только ветка
«ничего не найдено») — сам факт появления и закрытия этого диалога в тесте
детерминированно доказывает, что асинхронная корутина скана уже отработала;
ТОЛЬКО ПОСЛЕ этого в ту же папку кладётся настоящий orphan-файл
(`app_steps.place_file_in_download_folder`), для которого гонки уже нет —
следующий скан того же `ao3Id` запускает исключительно Restore
(`importFromUri`, синхронно внутри своей корутины импорта, никакой
параллельной корутины рядом). Подробности и код — докстринги
`restore_scan_workspace`/`place_file_in_download_folder` в
`framework/tests/test_downloads.py`/`framework/steps/app_steps.py`.

**Классовая полнота (правило 9 CLAUDE.md):** находка распространяется на
ЛЮБОЙ будущий сценарий, где тест кладёт файл в SAF-папку загрузок РЯДОМ по
времени с самим `saf_pick_folder` И этот файл должен быть НЕ найден этим
конкретным сканом (в отличие от TC-038, где файл ДОЛЖЕН быть найден именно
сканом при выборе папки — там синхронности не требуется, любой исход скана
уже корректен). Кандидат на будущий ремонт инфраструктуры: `saf_pick_folder`
могла бы сама дожидаться завершения `setDownloadFolderUri`'s scan через
общий наблюдаемый сигнал (например, опциональный параметр «дождаться Idle/Done
на `scanDownloadsState` перед возвратом») — не сделано в этом проходе (D-0037,
чужая уже принятая инфраструктура, доработка не требовалась для DoD TC-039;
decoy-приём на уровне теста самодостаточен). Критерий готовности (Fixed) этого
бага НЕ расширяю (SAF picker автоматизируется штатно — по-прежнему верно,
TC-021/TC-038/TC-039 все зелёные); находка — уточнение «Анализа». Статус бага
(`Open`, по независимой причине — smoke-регресс AT-BUG-009, см. запись
21:00:00Z 2026-07-14) не меняю.

Witness: `Invoke-Pytest tests/test_downloads.py -k
test_restore_folds_orphan_scan_into_single_dialog -v` — 3 прогона подряд
(`1 passed in 58.88s` / `51.26s` / `56.36s`, `PYTEST_EXIT=0` во всех);
`Invoke-Pytest tests/test_downloads.py -v` (полный regression файла, 5/5) —
`5 passed in 216.47s`, `PYTEST_EXIT=0`; `Invoke-Pytest
tests/test_saf_infra_probe.py -v` — `3 passed in 113.39s`, `PYTEST_EXIT=0`
(regression без изменений файла); `Invoke-Pytest tests/test_backup_restore.py
-v` — `1 passed in 63.56s`, `PYTEST_EXIT=0` (regression без изменений файла);
`python scripts/arch_check.py` — `ошибок 0, предупреждений 0`.
`app-under-test/` не тронут. Правки этого хода вне `bugs/`:
`framework/tests/test_downloads.py` (новый тест + фикстура),
`framework/steps/app_steps.py` (`place_file_in_download_folder`),
`framework/steps/settings_steps.py` (`assert_no_scan_complete_dialog`),
`framework/data/works.py` (`RESTORE_SCAN_TARGET`),
`test-cases/downloads/TC-039.md`, `state/traceability.md`.

**2026-07-17T18:35:00Z — test-maintainer (повторная попытка финального
пункта критерия «Smoke без регресса», попытка сорвана tooling-инцидентом
этой сессии — НЕ env AO3, НЕ новое падение теста, статус НЕ меняю):**

Контекст: единственный оставшийся пункт критерия Fixed — «Smoke без
регресса» (полный `-m p0`). Известный на момент диспатча блокер (ESC-001,
resolved) — mitm-CA стирается любым `adb reboot` без переустановки;
`Install-MitmCA` вызывается только из `Start-Emulator -WritableSystem`.

Среда поднята КАНОНИЧЕСКИ и корректно (полный порядок, каждый шаг сверен
позитивно):
- `Start-Emulator -WritableSystem` → буд прошёл, `Install-MitmCA` внутри
  него отработал: `CA hash = c8750f0d`, `store=134 apex=134`, `CA visible
  in apex store: OK` — CA подтверждена присутствующей (не как в ESC-001).
- `Get-Device` → `emulator-5554`; `Start-Appium` → `Appium started and
  ready on :4723`; `Install-App` → `Performing Streamed Install` /
  `Success`.

Запустила `Invoke-Pytest -m p0 -v` (`collected 55 items / 36 deselected /
19 selected`) через Bash-тул с `run_in_background: true` (канонический
способ ожидания долгого прогона по правилам оркестрации — foreground
не влезает в лимит тула 600000ms, исторический хронометраж этого же
прогона в этом баге/AT-BUG-009 — 575s..1782s). Вывод job начал писаться
нормально (заголовок pytest, `collected...selected`, старт первого теста
`tests/test_backup_restore.py::test_backup_clear_restore_returns_original_data`),
затем БЕЗ дальнейшего прогресса.

**Прямая проверка по требованию оператора (не по памяти о состоянии job,
факты, не пересказ):**
- `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` (и повторно
  расширенный поиск по ВСЕМ процессам с `CommandLine -match 'pytest'`) —
  **ни одного процесса с pytest/venv-python в командной строке НЕ
  найдено.** Позитивный контроль пройден: тот же вызов надёжно показывает
  другие реальные процессы (agent-dispatch, board_server, сами
  диагностические bash/powershell) — метод рабочий, находка не промах
  вызова.
- Хвост файла вывода job (`ba5r14okp.output`) — те же 12 строк, что и
  сразу после старта: `PYTEST_EXIT` НЕ появился, дальше первого теста
  прогон не продвинулся.
- При этом `emulator.exe`/`qemu-system-x86_64.exe`/`node.exe` (Appium) —
  ЖИВЫ и не имеют отношения к падению: сама среда (эмулятор, CA, Appium)
  оставалась исправной, погибнул именно процесс pytest этой сессии.

**Вывод: процесс pytest умер/исчез без exit-кода и без вывода дальше
первого теста — попытка сорвана tooling-инцидентом Bash-оркестрации ЭТОЙ
сессии** (фоновый процесс, запущенный `run_in_background`, не пережил
между-вызовный сброс состояния шелла — см. известное свойство среды
«Agent threads always have their cwd reset between bash calls»; здесь,
похоже, было потеряно не только cwd, но и сам фоновый процесс). Это НЕ
находка о состоянии AO3-окружения (эмулятор/Appium/CA — все живы и
корректны, весь бринг-ап отработал штатно) и НЕ новое падение теста
(TC-013/AT-BUG-009 из предыдущих попыток здесь ни при чём — прогон не
дошёл даже до второго теста из 19). Витнеса по критерию «Smoke без
регресса» НЕТ — ни PASS, ни FAIL по существу, только оборванный прогон
без результата. Не выдаю ложного «ещё идёт» без доказательства (прямое
указание оператора) и не переношу дело на память о предыдущем состоянии.

Не завожу новый test_debt-баг: это не задокументированный класс дефекта
`framework/`/`scripts/` AO3 (эмулятор/CA/Appium — все в порядке,
воспроизвести на стороне тестового окружения нечем), а инцидент
оркестрации самой этой рабочей сессии (Bash-тул харнесса, вне
`D:\AO3_tests`) — не тот периметр, что покрывают `bugs/AT-BUG-*`
(test-system debt данного репозитория). Докладываю как факт в отчёте
задачи; эскалация/детектор — на усмотрение Lead/оператора вне мандата
test-maintainer.

Cleanup: `adb emu kill` (эмулятор погашен), `Stop-NodeProcesses` (Appium
погашен), `Get-Device` → `NO DEVICE` подтверждено. `python
scripts/arch_check.py` не гонялся в этом ходе (правки в `framework/` не
вносились). `app-under-test/` не тронут. Правки этого хода — только
`bugs/AT-BUG-005.md` (эта запись + снятие лока). Статус бага НЕ меняю —
остаётся `Open`; критерий «Smoke без регресса» по-прежнему не
подтверждён ни в одну, ни в другую сторону. Следующая попытка —
рекомендую гнать смок foreground-частями (по файлам/маркерам) или
надёжнее контролировать выживание фонового процесса, прежде чем снова
полагаться на единый `-m p0` в фоне.

**2026-07-17T18:52:00Z — test-maintainer (attempt 2 финального пункта критерия
«Smoke без регресса» — ЗАКРЫТО, Open→Fixed):**

Контекст: попытка 1 этого диспатча (запись 18:35:00Z выше) сорвалась
tooling-инцидентом — фоновый pytest-процесс, запущенный `run_in_background`,
исчез без exit-кода после старта первого теста; среда (эмулятор/CA/Appium)
была поднята корректно и не была причиной. В этот раз — тот же канонический
бринг-ап, тот же способ запуска (`run_in_background: true`), но с честным
периодическим мониторингом реальным процессом (не памятью о состоянии job).

Бринг-ап (каждый шаг сверен позитивно):
- `Start-Emulator -WritableSystem` → буд прошёл, `Install-MitmCA` внутри —
  `CA hash = c8750f0d`, `store=134 apex=134`, `CA visible in apex store: OK`.
- `Get-Device` → `emulator-5554`; `Start-Appium` → `Appium started and ready
  on :4723`; `Install-App` → `Performing Streamed Install` / `Success`.

Запуск: `Invoke-Pytest -m p0 -v` через Bash `run_in_background: true`,
вывод редиректился в файл scratchpad-директории этой сессии (не путать со
служебным `.output`-файлом харнесса — при явном `>`-редиректе харнессный
файл остаётся пустым, это не признак зависания, проверено чтением
СВОЕГО файла редиректа). Позитивный контроль сразу после старта:
`Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where
CommandLine -match 'pytest'` — два процесса с `-m pytest -m p0 -v` в
командной строке, оба живы. Через 5 минут — повторная проверка: процессы
живы, файл вывода вырос до 9/19 тестов (42%, все PASSED) — реальный
прогресс, не мёртвый job. Дождалась нотификации о завершении фоновой
задачи (без ручного sleep-поллинга сверх одной контрольной точки).

**Witness (полный вывод):** `collected 55 items / 36 deselected / 19
selected` → все 19 PASSED (`test_backup_restore`, `test_library` x2,
`test_rating` x5, `test_smoke` x7 включая
`test_seeded_work_appears_in_correct_tab` x5, `test_visibility`
`test_disliked_hidden_on_listing[listing_basic.mitm]`) — **`19 passed, 36
deselected in 618.73s (0:10:18)`, `PYTEST_EXIT=0`.** Ни одного failed/error;
TC-013 (`test_disliked_hidden_on_listing`, ранее флаковавший по
AT-BUG-007/AT-BUG-009) — зелёный в этом прогоне. TC-021
(`test_backup_restore.py`) — зелёный, первым в списке (5%).

Сверка по всем трём пунктам критерия готовности (Fixed):
1. Способ автоматизации SAF picker найден и задокументирован как
   переиспользуемые step/fixture (`documents_ui.py`/`saf_steps.py`) —
   подтверждено инкрементом 1 (2026-07-09/14).
2. TC-021 зелёный (`test_backup_restore.py`) — подтверждено
   test-automator'ом (2026-07-14) и повторно этим прогоном.
3. Smoke без регресса — **подтверждено этим прогоном**: `19/19 passed`,
   `PYTEST_EXIT=0`, ни один из известных независимых блокеров
   (AT-BUG-009 adb-timeout, TC-013 нестабильность) не проявился.

Все три пункта критерия выполнены. Перевожу `Open → Fixed`
(guard-переход test-maintainer по `type: test_debt`,
`schemas/transitions.yaml:65-66` — сверено перед переходом). Верификация
(`Fixed → Verified`) — за fix-verifier; сборку приложения ждать не нужно
(долг тестовой системы, фикс во `framework/`).

Cleanup: `adb emu kill` (эмулятор погашен), `Stop-NodeProcesses` (Appium
погашен), `Get-Device` → `NO DEVICE` подтверждено отдельным вызовом.
`python scripts/arch_check.py` — правки этого хода ограничены `bugs/
AT-BUG-005.md` (frontmatter + эта запись, снятие лока), `framework/` не
трогала — прогон не требуется по существу, но выполнен контрольно:
`ошибок 0, предупреждений 0`. `app-under-test/` не тронут.

**2026-07-15T14:00:00Z — bug-reporter (заведение app_bug на основе находки test-automator):**
Классовая находка async-race из записи test-automator выше (момент между `saf_pick_folder`
и импортом из backup, когда async-скан папки успевает создать stub-запись в Room для уже
существующего ao3Id) выписана в отдельный баг приложения `BUG-011` с severity minor.
Это app_bug, не test_debt: поведение `SettingsViewModel.setDownloadFolderUri` + `importFromUri`
живёт в коде приложения, не в инфраструктуре тестов (хотя находка поймана при автоматизации TC-039).
Обратная ссылка и перекрёстная трассировка в `BUG-011.md`.

**2026-07-18T00:20:00Z — fix-verifier (D1, независимая верификация, Fixed → Verified):**

Одна консолидированная device-сессия для 7 связанных D1-задач (одна и та же
`fix-verifier:2026-07-17T21:02:01` лок-метка на всех). Бринг-ап:
`Start-Emulator -WritableSystem` (снапшот-буд реально упёрся в таймаут и
автофолбэк на `-no-snapshot-load` сработал живьём — независимое
подтверждение AT-BUG-012 см. там же), `CA hash c8750f0d, store=134
apex=134`; `Install-App` сразу после — `Success` без race (независимое
подтверждение AT-BUG-013); `Start-Appium` — ready на :4723.

Полный `Invoke-Pytest -m p0 -v`: **`19 passed, 41 deselected in 585.00s
(0:09:44)`, `PYTEST_EXIT=0`.** `tests/test_backup_restore.py::
test_backup_clear_restore_returns_original_data` (TC-021) — PASSED,
первым в порядке (5%). Все три пункта критерия готовности (обход SAF
задокументирован и на месте, TC-021 зелёный, smoke без регресса)
подтверждены независимо этим прогоном.

`python scripts/arch_check.py` → `ошибок 0, предупреждений 0`.
`app-under-test/` не тронут. Правки этого хода — только `bugs/
AT-BUG-005.md` (frontmatter + эта запись, снятие лока).

Статус переведён `Fixed → Verified`. Среда (эмулятор+Appium), поднятая
для консолидированной верификации всех 7 багов, погашена в конце сессии
(`adb emu kill`, `Stop-NodeProcesses`); зомби-процессы `emulator.exe`/
`qemu-system-x86_64.exe` отсутствуют, подтверждено `Get-CimInstance`.
