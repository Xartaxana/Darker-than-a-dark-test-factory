---
key: "AT-BUG-032"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p2"
summary: "restart_app_via_adb / adb.force_stop не наблюдают реальную смерть процесса — TC-025 и test_reading_ux.py (персистентность через рестарт) не отличают холодный старт от no-op"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-025", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-31T01:05:00Z"
updated: "2026-07-31T01:05:00Z"
archived: false
resolution: null
---

# restart_app_via_adb / adb.force_stop не наблюдают реальную смерть процесса — TC-025 и test_reading_ux.py (персистентность через рестарт) не отличают холодный старт от no-op

_Спроецировано из `bugs/AT-BUG-032.md` (источник правды).
Статус в нашей машине: **Open**._

# AT-BUG-032 — restart_app_via_adb не доказывает, что процесс реально был убит

## Окружение
Долг тестовой системы (`type: test_debt`, `debt_kind: missing_evidence`). Не зависит от сборки приложения — фикс целиком во `framework/`.

## Суть долга

`framework/steps/app_steps.py:401-411` (`restart_app_via_adb`):
```python
adb.force_stop()
adb.shell(f"am start -W -n {settings.APP_PACKAGE}/{settings.APP_ACTIVITY}", timeout=settings.ADB_LAUNCH_TIMEOUT)
```
`adb.force_stop()` = `shell(f"am force-stop {_PKG}")` (`framework/core/adb.py:45-46`); `shell()` возвращает только `.stdout`, returncode/stderr отброшены (`adb.py:37-42`). Ни здесь, ни в вызывающих тестах никто не читает `adb.pidof_app()` (`adb.py:189-193`, уже существует) до/после рестарта.

**Конкретный сценарий поломки:** force-stop тихо не срабатывает (device busy/permission/отвал adb) → приложение остаётся живым и на переднем плане → `am start -W` без `-d` на живой `singleTask`-Activity доставляет component-intent РАБОТАЮЩЕМУ инстансу (эмпирически подтверждено этим же репозиторием, `adb.py:296-303`: `TotalTime: 0` + `Warning: Activity not started, intent has been delivered to currently running top-most instance.`) → `MainActivity.onNewIntent` сбрасывает `deepLinkHandled`, но `dataString` пуст → поведение приложения не отличается от «ничего не произошло». Тесты, проверяющие только СОСТОЯНИЕ (вкладки/URL из prefs, значение тумблера), это состояние и так не меняется — они проходят зелёным, не проверив заявленный сценарий «холодный старт».

## Затронутые вызывающие (по критик-трассировке TC-134, 2026-07-31)

1. **`framework/tests/test_tabs.py:253` (TC-025, персистентность вкладок через рестарт)** — дыра того же класса: при no-op вкладки остаются в живой памяти, тест зелёный без проверки персистентности через реальную смерть процесса.
2. **`framework/tests/test_reading_ux.py:455`** — дыра того же класса: комментарий теста утверждает «значение тумблера пережило смерть процесса», но живой процесс отдаст то же значение из памяти без всякой персистентности.
3. **НЕ затронуты** (для справки, чтобы не перепроверять зря): `framework/tests/test_compatibility.py:129` — перед рестартом `app_steps.clean_state()` → `adb.clear_app_data()` (returncode проверяется, AT-BUG-026 B2), `pm clear` сам убивает процесс — холодный старт гарантирован структурно; `framework/steps/perf_steps.py:33` (`measure_cold_start`, TC-096) — та же защита + `parse_am_start_metrics` падает без `TotalTime`.

## Критерий готовности (Fixed)

- `restart_app_via_adb` (или обёртка над ним) доказывает смену pid: `adb.pidof_app()` до (assert not None — «убивать нечего») и после (assert not None и != pid до — «force-stop не сработал»). Проверка — шагом в `app_steps.py` (тесты не импортируют `framework.core`, `scripts/arch_check.py`), не разбросана по вызывающим тестам поодиночке — иначе класс повторится в следующем новом тесте.
- `test_tabs.py::test_tabs_persist_url_and_scroll_after_restart` (TC-025) и `test_reading_ux.py` (соответствующий тест на строке ~455) переведены на укреплённую версию, перепрогнаны зелёными.
- Исключающий прогон приложен: временная подмена `force_stop` на no-op показывает содержательное падение новой pid-проверки, затем откатывается.
- Smoke без регресса.

## Анализ

Тот же класс дефекта, что B2/B3 у TC-131/TC-133 (вакуумно-зелёный негатив / стимул без позитивного контроля), но в уже существующем с TC-025 примитиве, не в новом коде — обнаружен только сейчас при третьем ревью подряд той же поверхности (двух свежих кейсов, TC-133/TC-134). Приоритет minor: реальные отказы force-stop на стабильном локальном эмуляторе редки, но при возникновении дают ложно-зелёный прогон дважды (TC-025 и test_reading_ux), а не честный красный.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**2026-07-31T01:05:00Z — Lead (Sonnet, координатор /qa-loop), заведение бага:**
Классовый долг вскрыт критиком при ревью TC-134 (attempt 1, rejected по B1 — новый тест на том же примитиве не отличает kill+relaunch от no-op). Фикс TC-134 самого нового теста — отдельным точечным диспатчем (не расширяет этот баг, использует локальную обёртку `restart_app_via_adb_asserting_new_process`, предложенную критиком). Этот баг — про УЖЕ существующие TC-025/test_reading_ux, вне скоупа диспатча TC-134 (правило D-0037 — не расширять scope исполнителя). Диспетчеризация по правилу B4 (`state/rules.yaml` «Устранить test debt») — следующим проходом /qa-loop.
