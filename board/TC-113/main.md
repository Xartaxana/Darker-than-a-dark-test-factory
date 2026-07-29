---
key: "TC-113"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p1"
summary: "Включение тумблера Auto-download не скачивает задним числом ранее отмеченные Favorite-работы"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:downloads", "risk:R-05", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-29T21:15:00Z"
updated: "2026-07-29T21:15:00Z"
archived: false
resolution: "done"
---

# Включение тумблера Auto-download не скачивает задним числом ранее отмеченные Favorite-работы

_Спроецировано из `test-cases/downloads/TC-113.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-113 — Ретроактивность: включение тумблера не скачивает старые Favorite

## Предусловия
- Работа W засеяна НАПРЯМУЮ в Room (не через UI) с рейтингом SAVE (Favorite) и
  `downloadPath=null` — имитирует «работа была отмечена Favorite ДО того, как
  пользователь включил тумблер» (`app_steps.seed_library([(W.LOVED, "SAVE")])`,
  тот же приём, что `loved_work_seeded`).
- Тумблер «Auto-download favorite works» на момент сидинга выключен (дефолт).

## Сценарий (Given-When-Then)

**Given** работа W уже имеет рейтинг Favorite (SAVE) и не скачана; тумблер
«Auto-download favorite works» выключен

**When** пользователь открывает Settings и включает тумблер «Auto-download saved
works»

**Then** работа W остаётся БЕЗ файла — карточка на вкладке FAVORITE экрана Library
по-прежнему показывает download-иконку (не open-иконку), `downloadPath` не
выставлен
**And** работа W не появляется во вкладке FILES экрана Library
**And** в download-директории приложения не появляется ни одного нового файла —
`download_oracle` не фиксирует скачивание (тест без `@pytest.mark.produces_download`)

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | `W.LOVED`, засеяна с rating=SAVE, downloadPath=null (`seed_library`) |
| Тумблер Auto-download | OFF → ON (переключается в сценарии) |

## Заметки для автоматизации
- Регрессионный замок инварианта, не ловля известного дефекта — `setAutoDownloadSaved`
  (BrowserViewModel.kt:522) синхронно и единолично присваивает `autoDownloadSaved`,
  никакого пересканирования существующих `SAVE`-записей код не делает; владелец уже
  подтвердил это поведение как корректное при репро BUG-014 (см. «Actual»: «При
  включении тумблера: существующие Favorite-работы НЕ скачиваются (корректно)»).
- Шаги: `app_steps.seed_library` (уже существует) → `settings_steps.
  enable_auto_download` (уже существует, используется в TC-032) →
  `settings_steps.assert_auto_download_enabled(driver, True)` (новый шаг,
  добавлен attempt 2 — см. ниже) → переход в Library →
  `library_steps.assert_work_in_tab("SAVE", ...)`/`assert_download_icon_shown`/
  `assert_work_not_in_files_tab` (все уже существуют).
- **Replay ОБЯЗАТЕЛЕН, вопреки первому впечатлению «тумблер включается ПОСЛЕ
  сидинга — сети нет»** (attempt 2 доработки, критик-вход 2026-07-29, тот же
  класс, что заметка TC-112/TC-114/TC-115): сценарий сам по себе действительно не
  делает сетевого вызова (`downloadWork` не вызывается: само включение тумблера
  не триггерит ни одну из трёх точек предиката — нужен явный `applyRating`/
  `savePanelRating`/`onRateWorkRequested`, которого в сценарии нет) — но негативный
  Then проверяет ОТСУТСТВИЕ эффекта ГИПОТЕТИЧЕСКОГО бага (ошибочное
  пересканирование/скачивание при `setAutoDownloadSaved`), а не отсутствие
  штатного поведения. Если бы такой баг существовал, гипотетическое
  нелегитимное скачивание с live-навигацией ушло бы на archiveofourown.org по
  синтетическому `ao3_id` работы `W.LOVED` (900000001), который отдаёт живой
  HTTP 404 — `DownloadRepository` проглатывает `IOException`, и все Then
  (download-иконка/не-в-FILES/`download_oracle`) остались бы истинными
  НЕЗАВИСИМО от того, сработал баг или нет: тест физически не может упасть на
  собственной регрессии (ложно-зелёный). `work_with_download.mitm` (та же
  запись, что TC-032/033/114) несёт РЕАЛЬНУЮ download-транзакцию для `W.LOVED` —
  с этой записью гипотетическое срабатывание завершилось бы настоящим файлом, и
  `download_oracle`/UI-ассерты поймали бы его по-настоящему. Формулировка
  «Replay не требуется» в предыдущей версии этого раздела была неверной и снята
  этой правкой (по образцу обоснования в TC-112.md/TC-114.md).
- **When (включение тумблера) должен быть явно подтверждён** (attempt 2,
  второй блокер критика): `settings_steps.enable_auto_download` тапает тумблер
  УСЛОВНО (только если текущее состояние не совпадает с желаемым) и сам ничего
  не утверждает; остальные Then кейса от состояния тумблера не зависят вовсе —
  без явного assert'а непроизошедший переход OFF→ON тоже дал бы зелёный тест.
  Добавлен шаг `settings_steps.assert_auto_download_enabled(driver, True)`
  (читает `SettingsScreen.is_auto_download_checked`) сразу после
  `enable_auto_download`.
- **Батарея правил-реакций:** это кейс «ретроактивность» (CLAUDE.md, калибровка №4).

## Ревью автотеста (F1, test-reviewer, 2026-07-29)

**Вердикт: PASS** — `Approved -> Automated`, `automation_status: active`.

Чек-лист пройден полностью:
1. Архитектура (C1): `python scripts/arch_check.py` -> «ошибок 0, предупреждений 0»;
   `ALLOWLIST` в `scripts/arch_check.py:80` пуст (исключения «под себя» не добавлялись);
   в `framework/tests/test_downloads.py` нет локаторов/`driver`-конструирования и нет
   `sleep`; шаги — в `steps/` (`app_steps`/`saf_steps`/`settings_steps`/`library_steps`).
2. Traceability: `@allure.id("TC-113")` == id кейса; `@pytest.mark.p1` == `priority: P1`;
   `automated_by` указывает на существующую функцию (собрана и прогнана pytest'ом).
3. Соответствие по смыслу: все три Then кейса реализованы — download-иконка на
   FAVORITE (`assert_download_icon_shown`), отсутствие во вкладке FILES
   (`assert_work_not_in_files_tab`), отсутствие нового файла в download-директории
   (autouse `download_oracle`, теста без `@pytest.mark.produces_download`). When
   подтверждён `settings_steps.assert_auto_download_enabled(driver, True)` (читает
   реальный атрибут `checked`, не тавтология). Кейс не относится к комбинаторным
   областям C4 (фильтры/сортировки/видимость/backup-restore/tabs/темы) — отдельная
   строка «Инвариант:» не требуется.
4. Фикстуры и данные: `loved_work_seeded` (clean_state + seed_library) стоит в
   сигнатуре ДО `driver` — сидинг выполняется до создания Appium-сессии; `replay`
   гарантирует teardown прокси/mitmdump в `finally`; тест не зависит от других тестов.
5. Flake-риск: явные ожидания (`wait_app_ready` перед навигацией в Settings —
   закрытая гонка TC-032/TC-115), replay вместо живого AO3, негативный Then
   дополнительно и независимо страхуется post-снимком `download_oracle` (ловит
   асинхронный «хвост» скачивания, который короткий UI-таймаут мог бы пропустить).
6. Независимое воспроизведение (зелёный): `powershell -NoProfile -ExecutionPolicy
   Bypass -Command ". D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest -k
   test_enabling_auto_download_does_not_retroactively_download_favorites -v"` ->
   `1 passed ... in 44.58s`, `PYTEST_EXIT=0` (эмулятор `emulator-5554`, Get-Device: DEVICE).
7. Красная проба (собственная, не чужой отчёт), witness:
   - Что портил (уровень ДАННЫХ): фикстура `loved_work_seeded`
     (`framework/tests/conftest.py:219`) временно засеивала работу W как УЖЕ
     скачанную — `app_steps.seed_downloaded_work(W.LOVED, "SAVE",
     _DOWNLOADED_WORK_FIXTURE)` вместо `app_steps.seed_library([(W.LOVED, "SAVE")])`.
     Это прямое отрицание сути Then («работа W остаётся БЕЗ файла»).
   - Команда: та же каноническая форма, что в п.6.
   - Результат: `1 failed`, `PYTEST_EXIT=1`; падение содержательное и точно по сути
     порчи — `tests\test_downloads.py:437` -> `steps\library_steps.py:129`:
     `AssertionError: download-иконка не появилась у «A Loved Test Work»`
     (не таймаут, не инфраструктурная ошибка).
   - Откат: `git checkout -- framework/tests/conftest.py` в том же ходе;
     `git status --porcelain` после отката не содержит `framework/` — дифф чист.

Замечаний нет. Тестовый код при ревью не правился (кроме временной порчи п.7,
откачённой в том же ходе).

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Область содержит правило-реакцию — батарея: этот кейс закрывает пункт
      «ретроактивность»
