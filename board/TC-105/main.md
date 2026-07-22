---
key: "TC-105"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p1"
summary: "Отсутствие чувствительных данных (cookie/session/токены/локальные пути) в logcat при представительном smoke-прогоне"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:security", "risk:R-15", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-22T22:54:43Z"
updated: "2026-07-22T22:54:43Z"
archived: false
resolution: "done"
---

# Отсутствие чувствительных данных (cookie/session/токены/локальные пути) в logcat при представительном smoke-прогоне

_Спроецировано из `test-cases/security/TC-105.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-105 — Скан logcat на утечку чувствительных данных при smoke

## Предусловия
- Приложение установлено, данные очищены (`pm clear`).
- `logcat` очищен (`adb logcat -c`) непосредственно перед началом сценария —
  скан не должен ловить хвост от предыдущих прогонов (тот же приём, что
  TC-098).

## Сценарий (Given-When-Then)

**Given** приложение запущено с чистыми данными, `logcat` очищен

**When** пользователь проходит представительный smoke-путь, задействующий
типичные операции с данными: запуск → Browse (AO3-страница) → простановка
рейтинга на существующей засеянной работе → Settings → экспорт бэкапа через
SAF (переиспользовать шаги существующих P0/P1-кейсов TC-001/TC-006/TC-007/
TC-021 — тот же приём, что TC-098, не изобретать новый маршрут)

**Then** захваченный за время прогона `logcat` (`adb logcat -d`) НЕ содержит
строк с cookie/сессионными данными (`Cookie:`, `Set-Cookie:`)
**And** НЕ содержит строк с признаками токенов/сессионных идентификаторов
(`session_id=`, `token=`, `Authorization:`)
**And** НЕ содержит полных локальных путей приложения в прикладных (не
системных диагностических) строках лога (`/data/data/com.example.ao3_wrapper/`,
`/data/user/0/com.example.ao3_wrapper/`) — с оговоркой testability gap ниже
про отличение прикладной утечки от штатного системного шума

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Паттерны скана | `Cookie:`, `Set-Cookie:`, `session_id=`, `token=`, `Authorization:`, `/data/data/com.example.ao3_wrapper/`, `/data/user/0/com.example.ao3_wrapper/` |
| Источник | `adb logcat -d` (полный буфер с момента `adb logcat -c`) |
| Пакет | `com.example.ao3_wrapper` |

## Заметки для автоматизации
- Блокера нет: `framework/core/adb.py` уже несёт `logcat_clear()`/`logcat_dump()`
  (используются TC-098 и `core/reporting.py`) — переиспользовать буквально те
  же примитивы; smoke-путь переиспользует шаги TC-001/006/007/021 (bottombar
  nav, rating, backup export), не изобретать новый маршрут (тот же приём, что
  TC-098).
- **Testability gap (best-effort, как явно названо в docs/01-test-strategy.md
  §9 area E4).** Отличение ПРИКЛАДНОЙ утечки (напр. случайно залогированное
  значение cookie/токена в отладочном `Log.d`) от ШТАТНОГО системного шума
  (ART/PackageManager/WebView сами упоминают путь пакета приложения в
  диагностических целях — это НЕ утечка) — вопрос дизайна матчера, требующий
  калибровки на реальном прогоне; список паттернов выше — стартовая гипотеза,
  не исчерпывающий и не окончательно откалиброванный набор. Отсутствие
  совпадений в ОДНОМ прогоне доказывает «не замечено в ЭТОМ прогоне», не
  «приложение никогда не логирует чувствительные данные» — тот же класс
  оговорки, что testability gap ANR-детекции в TC-098.
- Пути `/data/data/...`/`/data/user/0/...` МОГУТ легитимно встречаться в
  СИСТЕМНЫХ строках (не относящихся к пользовательским данным) — если
  калибровка на реальном прогоне покажет избыточный шум от системных
  компонентов, test-automator вправе сузить матчер до строк с тегом
  приложения (`AO3`/имя пакета в теге лога) вместо полнотекстового скана
  всего буфера; решение операционализации — за test-automator, задокументировать
  в тесте.
- **Операционализация калибровки (test-automator, живой прогон emulator-5554,
  2026-07-22):** полнотекстовый скан ВСЕГО буфера дал 3 ложных срабатывания за
  2 итерации калибровки, все — системный шум, не прикладная утечка: (1)
  `token=` совпал со строкой `WindowManagerShell`/`WindowManager` ДРУГОГО
  процесса (`system_server`, `token=WCT{...}` — Android WindowContainerToken,
  не сессионный токен); (2)/(3) даже в пределах PID приложения
  `/data/user/0/<pkg>/...` совпал с ДВУМЯ отдельными Chromium/WebView-
  внутренними тегами — `cr_VariationsUtils: Failed reading seed file
  ".../app_webview/variations_seed..."` (тег с префиксом `cr_`, конвенция
  Chromium-логов) и `chromium: [ERROR:simple_file_enumerator.cc(21)] opendir
  .../cache/WebView/Default/HTTP Cache/Code Cache/...: No such file or
  directory` (тег буквально `chromium`, другая конвенция того же движка) — оба
  про СОБСТВЕННЫЕ служебные файлы/директории WebView (variations seed —
  публичная A/B-конфигурация; HTTP Cache/Code Cache — дисковый кэш движка), не
  пользовательские данные; прикладные теги этого приложения —
  `DownloadRepo`/`Converters` (см. `Log.d(TAG, ...)` в app-under-test), ни
  один не совпадает ни с одним исключённым. Матчер сужен до строк {PID
  приложения (`adb shell pidof <pkg>`, `logcat --pid=`)} \ {Chromium-
  внутренние теги: префикс `cr_` ИЛИ буквально `chromium`}
  (`framework/steps/security_steps.py::assert_logcat_has_no_sensitive_data`) —
  список sensitive-паттернов НЕ сужен, тестируется на этом же наборе.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Область НЕ комбинаторная (скан на конкретных паттернах за один прогон) — строка `Инвариант:` не требуется

## Ревью автотеста (F1, test-reviewer, 2026-07-22)

Вердикт: **Пройдено** (Approved → Automated, `automation_status: active`).
- **Архитектура (C1):** `arch_check.py` 0/0, ALLOWLIST пуст; logcat-примитивы — `core/adb`
  (`logcat -c`/`-d`, переиспользованы из TC-098), smoke-путь — через `app_steps`/`rating_steps`/
  `library_steps`/`saf_steps`; `sleep` нет.
- **Traceability:** `@allure.id("TC-105")` == id; маркеры `p1`+`live` (priority P1, режим live —
  smoke-путь грузит живой AO3, replay не заявлен); `automated_by` резолвится.
- **Смысл / финальный матчер (перепроверен сам):** скан ищет sensitive-паттерны
  (`Cookie:`/`Set-Cookie:`/`session_id=`/`token=`/`Authorization:`) и полные локальные пути
  приложения; матчер сужен до строк процесса приложения (по PID) МИНУС Chromium-внутренние теги
  (`cr_*` ИЛИ буквально `chromium`). Сужение НЕ переузкое: список sensitive-паттернов НЕ сужен;
  исключены ровно два калиброванных класса СИСТЕМНОГО шума WebView-движка (variations_seed,
  HTTP/Code Cache — служебные файлы движка, не пользовательские данные), прикладные теги
  приложения (`DownloadRepo`/`Converters`) под исключение не попадают. Область не комбинаторная.
- **Фикстуры:** `placeholder_seeded_work` (сидинг до сессии Appium), `logcat_smoke_backup_workspace`
  удаляет `tc105_...json` до и после, `logcat -c` в начале сценария (не ловит хвост прошлых прогонов).
- **Независимый зелёный прогон:** `Invoke-Pytest tests/test_security_logcat.py` → 1 passed (47s);
  финально 7 passed.
- **Красная проба (2026-07-22T22:54:43Z):** временно `_is_chromium_internal_tag` → `return False`
  (снятие исключения Chromium-тегов, `security_steps.py`) → `test_logcat_has_no_sensitive_data...`
  FAILED, осмысленно: «logcat … содержит полный локальный путь приложения:
  ['/data/user/0/com.example.ao3_wrapper/']». Проба одновременно подтверждает, что (а) детект
  внутренних путей несущий и (б) калибровка `cr_`/`chromium` реально нагружена (без неё системный
  шум движка даёт ложное срабатывание). Порча откачена (Edit-revert), финальный прогон зелёный.
