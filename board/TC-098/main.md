---
key: "TC-098"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Отсутствие FATAL EXCEPTION/ANR в logcat при прогоне P0-smoke"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:performance", "risk:R-12", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-22T00:03:16Z"
updated: "2026-07-22T00:03:16Z"
archived: false
resolution: "done"
---

# Отсутствие FATAL EXCEPTION/ANR в logcat при прогоне P0-smoke

_Спроецировано из `test-cases/performance/TC-098.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-098 — Отсутствие crash/ANR/fatal при smoke-прогоне

## Предусловия
- Приложение установлено, данные очищены (`pm clear`).
- `logcat` очищен (`adb logcat -c`) непосредственно перед началом сценария —
  скан не должен ловить хвост от предыдущих прогонов.

## Сценарий (Given-When-Then)

**Given** приложение запущено с чистыми данными, `logcat` очищен

**When** пользователь проходит представительный smoke-путь: запуск →
Browse (домашняя AO3-страница) → переход на Library → переход на Settings →
простановка рейтинга Loved на существующей засеянной работе (тот же путь,
что уже покрывают существующие P0-кейсы TC-001/TC-006/TC-007 — переиспользовать
их шаги, не изобретать новый маршрут)

**Then** захваченный за время прогона `logcat` (`adb logcat -d`) НЕ содержит
строк `FATAL EXCEPTION` (крах процесса приложения)
**And** НЕ содержит строк `ANR in <package>` (ANR именно этого приложения) —
с оговоркой testability gap ниже

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Паттерны скана | `FATAL EXCEPTION`, `ANR in com.example.ao3_wrapper` |
| Источник | `adb logcat -d` (полный буфер с момента `adb logcat -c`) |
| Пакет | `com.example.ao3_wrapper` |

## Заметки для автоматизации
- Блокера нет: `framework/core/adb.py` уже несёт `logcat_clear()`/`logcat_dump()`
  (используются `core/reporting.py` для артефактов падения) — переиспользовать
  `logcat_clear()` до сценария и `adb.shell("logcat -d -t <N>")` (или
  `logcat_dump` в файл + скан файла) после; парсинг на подстроки — рутинная
  автоматизация.
- **Testability gap (ANR-детект, best-effort) — как явно названо в
  docs/01-test-strategy.md §9 area E2.** Короткий представительный smoke-путь
  может не спровоцировать ANR вовсе (ANR требует устойчивого зависания UI-потока
  >5с, что smoke-путь не гарантирует воспроизвести) — отсутствие строки `ANR in`
  в логе на этом прогоне доказывает лишь «ANR не произошёл в ЭТОМ прогоне», не
  «приложение свободно от ANR-рисков в принципе». Assert на отсутствие `ANR in`
  оставлен в Then (штатно проверяем то, что можем), но полнота детекции ANR —
  gap, не заявлять как исчерпывающую проверку.
- `FATAL EXCEPTION`-часть НЕ testability gap — краш процесса детерминированно
  пишет эту строку в logcat при любом необработанном исключении, полноценно
  drivable.
- **`features` — точная nf-привязка `nf-stability-no-crash-anr`.** Прежние
  приблизительные функциональные привязки (`browse-initial-load`,
  `browse-bottombar-nav`, `rating-overlay-five-options` — широкий набор фич,
  реально задействованных smoke-путём) сняты решением 2026-07-21
  (анти-двойной-зачёт, `docs/01-test-strategy.md` §9): нефункциональная
  область получает собственную запись реестра. Поведенческое покрытие тех
  фич — за их собственными кейсами (в т.ч. TC-002, TC-007), не за этим.

**2026-07-22 — test-automator, реализация:** smoke-путь переиспользует шаги
TC-001 (`app_steps.wait_app_ready`)/TC-006 (`open_tab Library` +
`library_steps.assert_library_loaded`)/TC-002 (`open_tab Settings`)/TC-007
(`rating_steps.open_work_page`+`rate_current_work("SAVE")` на
`placeholder_seeded_work`=`W.LOVED`, тот же приём, что и сам TC-007, без
изобретения нового маршрута). `perf_steps.logcat_clear_before_scenario`
(`adb.logcat_clear()`) до сценария, `perf_steps.assert_no_crash_or_anr`
(`adb shell logcat -d -t 4000`) после — сканирует `FATAL EXCEPTION` и
`ANR in com.example.ao3_wrapper`. 3 зелёных прогона подряд
(`test_no_crash_or_anr_during_smoke_path`, ~42-43s каждый).

## Ревью автотеста

**test-reviewer, 2026-07-22 — вердикт: PASS (`Approved → Automated`,
`automation_status: active`).** Весь чек-лист F1 пройден.

- **Архитектура (C1):** `arch_check.py` — 0 ошибок / 0 предупреждений; не в
  ALLOWLIST. Скан вынесен в `perf_steps.logcat_clear_before_scenario`/
  `assert_no_crash_or_anr` (переиспользуют `adb.logcat_clear`/`adb.shell`); smoke-
  путь собран из существующих шагов TC-001/006/002/007, новых локаторов нет,
  `sleep` нет.
- **Traceability:** `@allure.id("TC-098")` == id; `@pytest.mark.p0` ↔
  `priority: P0`, `@pytest.mark.live` (smoke-путь идёт по живому AO3);
  `automated_by` указывает на существующую функцию.
- **Соответствие кейсу:** assert проверяет суть — `logcat` не содержит `FATAL
  EXCEPTION` и `ANR in com.example.ao3_wrapper` после представительного smoke-
  пути. ANR-часть честно помечена как testability gap (docs/01 §9 area E2:
  короткий путь не гарантирует спровоцировать ANR) — это осознанное ограничение
  области, не ослабление проверки; `FATAL EXCEPTION`-часть полноценно drivable.
- **Фикстуры/flake:** `placeholder_seeded_work` (сидинг placeholder до сессии
  Appium, порядок соблюдён) → `driver`; `logcat -c` перед сценарием исключает
  хвост прошлых прогонов.
- **Независимое воспроизведение (п.6):** собственный зелёный прогон —
  PYTEST_EXIT=0 (в составе модуля, 144s).
- **Красная проба (п.7), 2026-07-22:** порча на уровне сигнатуры краха —
  временно в `logcat_clear_before_scenario` после `logcat -c` инжектирована
  строка `log -p F -t AndroidRuntime "FATAL EXCEPTION: red-probe injected"`.
  `Invoke-Pytest -k no_crash_or_anr` → FAILED: «logcat содержит 'FATAL
  EXCEPTION' за время smoke-прогона — процесс приложения крашнулся». Скан
  поймал сигнатуру. Порча откачена в том же ходе (файл untracked → возвращено
  Edit'ом; дифф чист). Тест умеет падать.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Область НЕ комбинаторная (скан на конкретных паттернах) — строка `Инвариант:` не требуется
