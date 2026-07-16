---
key: "TC-021"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Backup → Clear all ratings → Restore возвращает исходные данные"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:backup", "risk:R-01", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-14T21:40:00Z"
updated: "2026-07-14T21:40:00Z"
archived: false
resolution: "done"
---

# Backup → Clear all ratings → Restore возвращает исходные данные

_Спроецировано из `test-cases/backup/TC-021.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-021 — Backup → Clear → Restore возвращает данные

## Предусловия
- Приложение запущено, в Room засеяны работы с разнообразными полями
  (`framework/data/works.py::ALL`, по одной на каждый из 5 рейтингов, включая
  `comment`, `tags`, `fandom`, `word_count` где применимо через сидинг с
  расширенными полями — см. заметку про доработку `seed_db.py`).
- В Room засеян ≥1 сохранённый filter-профиль (`seed_db.seed_filter_profiles`) —
  формат бэкапа несёт `filterProfiles` наравне с `works` (см. «Проверяемые
  данные»).
- SAF file picker доступен (эмулятор с файловым провайдером, путь для экспорта
  подготовлен заранее).

## Сценарий (Given-When-Then)

**Given** приложение запущено, в библиотеке есть засеянные работы с рейтингами,
комментариями и тегами, и сохранён ≥1 filter-профиль (фильтр-поиск)

**When** пользователь в Settings выполняет «Back up data», выбирает файл через SAF,
дожидается результата
**And** затем выполняет «Clear all ratings» и подтверждает диалог
**And** затем выполняет «Restore from backup», выбирает тот же файл

**Then** после Restore появляется `AlertDialog` с результатом (counts, без ошибки)
**And** количество работ в Library по каждой рейтинговой вкладке совпадает с
исходным (до Clear)
**And** для каждой восстановленной работы поля rating, comment, tags, fandom,
word_count совпадают с исходными значениями до Backup
**And** сохранённый filter-профиль присутствует после Restore с теми же
name/queryString, что были до Backup — без потери и без дублирования

**Инвариант:** множество восстановленных строк == множеству исходных (ничего не
потеряно, не добавлено, не задублировано) по объединению {поля работы} ∪
{filterProfiles} — round-trip `restore(backup(S)) == S` обязан сохранять ОБА
множества из формата бэкапа, не только `works`.

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работы | `framework/data/works.py::ALL` (5 работ), дополненные comment/tags при сидинге |
| Filter-профиль | 1 профиль (name + queryString), засеян `seed_db.seed_filter_profiles` |
| Формат бэкапа | `{"version":2,"works":[…],"filterProfiles":[…]}` |

## Заметки для автоматизации

**2026-07-14 (доработка по ревью, замечание 1) — test-automator:** закрыт
единственный блокирующий пункт ревью (см. «## Ревью автотеста» ниже) — строка
`Инвариант:` добавлена в тело кейса (по формулировке ревьюера, скоуп решён
Lead: `filterProfiles` включены, не вынесены), GWT/«Проверяемые данные»
дополнены. Тест расширен: 1 filter-профиль засеян через
`seed_db.seed_filter_profiles` (обёртка `app_steps.seed_filter_profiles`) ДО
Appium-сессии, наравне с работами; после Restore — прямое чтение Room
(`seed_db.read_filter_profiles()`, новая функция по образцу
`read_work_ratings()`; `backup_steps.assert_filter_profiles_match`, сверка по
(name, queryString), не по внутреннему `id`). Диалоги: «Backup created» → «...1
filters.» (то, что было в Room на момент экспорта); «Backup restored» → «...0
filters.» — ОЖИДАЕМО, не пробел: `confirmClearAll()` вызывает только
`workDao.deleteAll()` (`RatingRepository.clearAllRatings`), `filter_profiles`
этим шагом не трогается, поэтому на Restore профиль уже присутствует в Room и
корректно пропускается как дубликат по `id` (см. докстринг
`test_backup_restore.py` — подробный разбор). Round-trip-инвариант (множество
профилей после == множеству до, без потери/дублирования) проверяется Room-
сверкой, не текстом диалога. 3 зелёных прогона подряд, регресс
`test_saf_infra_probe.py` (3/3) и `test_seed_filter_profiles_unit.py` без
изменений, `arch_check` 0 ошибок/0 предупреждений. `review: changes_requested`
снято — кейс уходит на повторное ревью штатно.

**2026-07-14 — test-automator (кейс автоматизирован, статус остаётся Approved до
ревью):** SAF-блокер снят (`bugs/AT-BUG-005.md`, инкремент 1 — page object
`framework/screens/documents_ui.py` + steps `framework/steps/saf_steps.py`).
Реализовано `framework/tests/test_backup_restore.py::
test_backup_clear_restore_returns_original_data` — полное покрытие: 5 работ (по
одной на рейтинг) засеяны через `seed_with_comment` с непустыми comment/tags
(заметка ниже про недостающую поддержку в `seed_db.py` устарела — функция уже
существует), Backup через CreateDocument picker → Clear all ratings → Restore
через GetContent picker из того же файла. Проверки: диалоги «Backup created»/
«Backup restored» с точным текстом counts; присутствие каждой работы в своей
вкладке Library; ПОЛНОЕ совпадение rating/comment/tags/fandom/word_count —
через прямое чтение Room (`seed_db.read_work_ratings()`, новая функция), а не
через текст карточки (обходит локале-зависимое форматирование числа word_count
в UI). 3 зелёных прогона подряд, без регресса `test_saf_infra_probe.py` (3/3),
`arch_check` 0/0.

Старые заметки ниже — исторические (оставлены для контекста, не отражают
текущее состояние):
- ~~SAF file picker обычно не UI-автоматизируем~~ — снято, см. выше.
- Restore выполняется в то же приложение сразу после Clear — тот же файл должен
  быть доступен по стабильному URI (не временный кэш, который мог быть очищен).
  Подтверждено: `/sdcard/Download/<файл>` персистентен между SAF-раундами в
  рамках теста.
- ~~`seed_db.py` не заполняет comment/tags~~ — устарело, `seed_with_comment`
  уже поддерживает оба поля (используется в этом автотесте).
- Restore также должен запускать `scanForOrphanedDownloads()` и сворачивать
  результат в тот же диалог — эта часть относится к P1-области downloads
  (§9 P1, "auto-триггер после Restore") и не проверяется этим кейсом; при
  необходимости оформить отдельным P1-кейсом позже.

## Ревью автотеста

**test-reviewer, 2026-07-14 (повторное ревью после доработки) — вердикт: `Approved → Automated`, `automation_status: active`. Единственное блокирующее замечание первого круга закрыто ПО СУЩЕСТВУ.**

Проверка отработки прежнего замечания (не формальной):
- **Инвариант C4 добавлен как СВОЙСТВО, не пример** (тело кейса, строки 45-48): «множество восстановленных строк == множеству исходных … по объединению {поля работы} ∪ {filterProfiles}», round-trip `restore(backup(S)) == S` для ОБОИХ множеств формата бэкапа. GWT и таблица «Проверяемые данные» дополнены filter-профилем и форматом `{version, works, filterProfiles}`.
- **Покрытие `filterProfiles` реализовано, не заглушка**: 1 профиль засеян `app_steps.seed_filter_profiles` (обёртка `seed_db.seed_filter_profiles`) ДО Appium-сессии, наравне с работами; сверка после Restore — прямым чтением Room (`seed_db.read_filter_profiles()` + `backup_steps.assert_filter_profiles_match`, сверка по (name, queryString), не по внутреннему `id`). Оба assert'а инвариантные: `assert_restored_fields_match` (len + exact ao3Id-set + полное совпадение полей) и `assert_filter_profiles_match` (len + отсортированное равенство списков) проверяют «ничего не потеряно/не добавлено/не задублировано», а не единичный пример.
- **Расхождение диалогов «1 filters» (Backup created) vs «0 filters» (Restored) разобрано корректно**: `confirmClearAll()` → `workDao.deleteAll()` не трогает `filter_profiles`, поэтому на Restore профиль уже в Room и штатно пропускается как дубликат по `id`; счётчики диалогов считают разные величины (экспортировано vs импортировано-НОВЫХ). Инвариант проверяется Room-сверкой, НЕ текстом диалога — сужения свойства нет.

Чек-лист F1:
- **Независимое воспроизведение (п.6)**: `Invoke-Pytest tests/test_backup_restore.py -v` → `1 passed in 62.25s`, `PYTEST_EXIT=0` (эмулятор поднят и погашен ревьюером сам; без flake AT-BUG-009 в этом прогоне; `Get-Device` → `NO DEVICE` по завершении).
- **Архитектура (п.1)**: `python scripts/arch_check.py` → `ошибок 0, предупреждений 0`; ALLOWLIST пуст (файл не добавлен «под себя»). В `tests/` нет driver/локаторов; `adb.shell` только в фикстуре-workspace; шаги в `steps/`, экраны в `screens/`; `sleep` отсутствует.
- **Traceability (п.2)**: `@allure.id("TC-021")` == id; `@pytest.mark.p0` ↔ `priority: P0`; `automated_by` указывает на существующую функцию.
- **Фикстуры/данные (п.4)**: сидинг ДО `driver` (порядок фикстур верный); два шага сидинга композируются корректно — `seed_filter_profiles` пуллит ТЕКУЩУЮ БД (уже с работами) через `_pull_baseline`, вставляет профиль, пушит обратно; работы не затираются. `backup_file_workspace` — try/finally вокруг ВСЕГО (включая setup), чистит SAF-файл на `/sdcard/Download`, который `pm clear` не трогает: любая точка отказа setup покрыта уборкой. `clean_state()` в начале.
- **Flake (п.5)**: ожидания через `is_present`/`wait` с timeout; нет `sleep`; нет обращения к живому AO3.

Замечаний нет. C4-ретрофит остальных комбинаторных кейсов уже в очереди (docs/09, коммит 7a6c9fa) — нового собрата-дефекта (D-0043) в рамках этого ревью не обнаружено; класс покрыт очередью ретрофита.

---

**test-reviewer, 2026-07-14 (первый круг) — вердикт: `changes_requested` (чек-лист F1 п.3, дизайн кейса). Статус остаётся `Approved`.**

Что проверено и в порядке:
- Независимое воспроизведение: `Invoke-Pytest tests/test_backup_restore.py -v` → `1 passed in 64.80s`, `PYTEST_EXIT=0` (эмулятор поднят и погашен ревьюером сам, `Get-Device` → `NO DEVICE`).
- Архитектура (п.1): `python scripts/arch_check.py` — `ошибок 0, предупреждений 0`; ALLOWLIST пуст (файл не добавлен «под себя»). Локаторы/driver в тесте отсутствуют, `adb.shell` только в фикстуре-workspace.
- Traceability (п.2): `@allure.id("TC-021")` == id; `@pytest.mark.p0` ↔ `priority: P0`; `automated_by` указывает на существующую функцию.
- Фикстуры/flake (п.4-5): порядок фикстур верный (`backup_restore_seeded`/`backup_file_workspace` до `driver` — сидинг до Appium-сессии); `backup_file_workspace` покрывает teardown-ом любую точку отказа setup (try/finally вокруг всего, чистит SAF-файл на `/sdcard/Download`, который `pm clear` не трогает); ожидания через `wait`/`is_present`, `sleep` нет; тест не ходит на живой AO3. Сверка полей через прямое чтение Room (`backup_steps.assert_restored_fields_match` — полный набор ao3Id + все поля) честная, не «элемент существует».

### Блокирующее замечание (единственное)

1. **[п.3 — комбинаторная область без строки инварианта]** TC-021 — кейс области **backup/restore** (сохранность round-trip), которая в чек-листе ревью прямо названа комбинаторной, требующей строки `Инвариант: …` (C4). Такой строки в кейсе НЕТ (ср. эталон `test-cases/settings/TC-059.md:41`). Следствие не косметическое: свойство «`restore(backup(S)) == S`» молча сужено до подмножества состояния.
   - Конкретный пробел: формат бэкапа (frontmatter `requirements` и таблица «Проверяемые данные», строка 44) — `{"version":2,"works":[…],"filterProfiles":[…]}`, но и GWT (строки 34-38), и тест покрывают round-trip ТОЛЬКО `works`: `framework/tests/test_backup_restore.py:94` и `:114` фиксируют «Backed up 5 works, **0 filters**» / «Restored 5 works, **0 filters**». Сохранность `filterProfiles` не проверяется ни разу, хотя `framework/data/seed_db.py::seed_filter_profiles` уже существует (используется TC-041/042).
   - Что сделать: (а) добавить в тело кейса строку `Инвариант: …`, называющую сохранность как СВОЙСТВО — множество восстановленных строк == множество исходных (ничего не потеряно/не добавлено/не задублировано) по объединению {поля работы} ∪ {filterProfiles}; (б) расширить тест: засеять ≥1 `filterProfile`, проверить его выживание после Restore (counts «N filters» + сверка через Room), ЛИБО явно вынести `filterProfiles` из скоупа кейса с обоснованием. Маршрут: дизайн кейса (строка инварианта, скоуп) — test-designer; доработка теста — test-automator.

Замечаний к слою кода нет — assert'ы works честные (полная Room-сверка). Замечание — в незадекларированном инварианте и вытекающем непокрытии `filterProfiles`.

**Lead (Fable), 2026-07-14 — решение по скоупу для доработки (развилка из замечания 1(б)):**
`filterProfiles` ВКЛЮЧИТЬ в скоуп TC-021, не выносить: формат бэкапа несёт их
явно (`requirements`), сидинг `seed_db.seed_filter_profiles` уже существует
(AT-BUG-006 инкремент 1), цена расширения мала, а область P0. Доработчик
(test-automator по правилу «Доработать автотест по ревью»): (а) добавить строку
`Инвариант:` в тело кейса по формулировке замечания 1 — множество
восстановленных строк == множеству исходных по объединению {поля работы} ∪
{filterProfiles}; поправить GWT/«Проверяемые данные» соответственно; (б)
засеять ≥1 профиль, проверить counts «N filters» в обоих диалогах и Room-сверку
профиля после Restore; (в) удалить `review: changes_requested` → кейс уходит на
повторное ревью штатно. Дизайн-вход test-designer НЕ требуется: скоуп решён
этой записью, формулировка инварианта дана ревьюером.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
