---
key: "TC-189"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p1"
summary: "Фоновая вкладка на локальный файл (открытая с вкладки Files) переживает kill+relaunch с тем же file://-URL"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:library", "risk:R-08", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-10T16:10:49Z"
updated: "2026-08-10T16:10:49Z"
archived: false
resolution: "done"
---

# Фоновая вкладка на локальный файл (открытая с вкладки Files) переживает kill+relaunch с тем же file://-URL

_Спроецировано из `test-cases/library/TC-189.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-189 — Фоновая вкладка на локальный файл переживает kill+relaunch

## Предусловия
- Приложение запущено с чистыми данными.
- Засеяна работа с `downloadPath` через `seed_db.seed_with_download` — файл
  РЕАЛЬНО существует на диске (не удалён).
- Открыт экран Library, активна вкладка Files.

## Сценарий (Given-When-Then)

**Given** на вкладке Files долгим нажатием по карточке скачанной работы через
overlay открыта фоновая вкладка (тот же приём, что TC-174) — persisted
`open_tabs_urls` несёт `file://<downloadPath>` на позиции 1

**When** процесс приложения убит и перезапущен (`restart_app_via_adb_asserting_new_process`,
реальная смерть процесса, не пересоздание Activity)

**Then** после перезапуска `wait_persisted_tab_count(2)` подтверждает, что ОБЕ
вкладки (Home + фоновая) восстановлены
**And** `assert_persisted_tab_url_at(1, <тот же file://-URL>)` — URL
восстановленной вкладки побайтово совпадает с тем, что был ДО перезапуска (не
теряется, не подменяется на `about:blank`/AO3-URL)
**And** при переключении на эту вкладку WebView рендерит содержимое файла (файл
на диске не тронут этим кейсом — судьба вкладки ПОСЛЕ удаления файла — предмет
отдельного TC-190)

**Инвариант:** персистентность вкладок (`saveTabsToPrefs`/восстановление при
старте) одинаково применяется к ЛЮБОЙ схеме URL — `file://` персистится и
восстанавливается тем же кодом, что и `https://` (TC-025), различий по схеме
в коде персистентности нет.

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Вкладка-источник | Files, работа с `downloadPath` |
| URL фоновой вкладки | `file://<downloadPath>` |
| Действие | kill+relaunch |
| Ожидание | та же вкладка, тот же URL, файл рендерится |

## Заметки для автоматизации
- Kill+relaunch — `app_steps.restart_app_via_adb_asserting_new_process`
  (готов, `app_steps.py:569+`), тот же приём, что TC-025/TC-134.
- Сидинг — `seed_db.seed_with_download`, тот же приём, что TC-174.
- Оракулы — persisted-prefs примитивы (`wait_persisted_tab_count`,
  `assert_persisted_tab_url_at`), тот же класс, что TC-173/174/175.
- Рендер после переключения — WEBVIEW-контекст ДОПУСТИМ здесь (в отличие от
  TC-136 и т.п.), т.к. на момент проверки живая вкладка ровно ОДНА активная
  цель переключения — sticky-context класс (AT-BUG-018/022) актуален только
  при чтении content АКТИВНОЙ вкладки, когда живых WebView > 1 и chromedriver
  прилип к чужой; здесь мы явно переключаемся НА эту вкладку перед чтением.
- Не дублирует TC-025 (та проверяет HTTP-URL) и TC-034 (открытие локального
  файла В ПЕРЕДНЕЙ вкладке, без kill/relaunch).
- Блокера автоматизации нет.

## Ревью автотеста (F1, test-reviewer, 2026-08-10)

**Вердикт: PASS** — `Approved → Automated`, `automation_status: active`.

- **Архитектура (C1):** `arch_check.py` — 0 ошибок; kill+relaunch идёт через
  `app_steps.restart_app_via_adb_asserting_new_process` (структурно доказывает
  смену pid — не тихий no-op `am start`), `sleep` нет.
- **Traceability:** `@allure.id("TC-189")`, `@pytest.mark.p1` == `priority: P1`,
  `automated_by` резолвится.
- **Соответствие GWT:** инвариант «персистентность не зависит от схемы URL»
  проверяется свойством: тот же `file://`-URL сверяется ДО и ПОСЛЕ реальной
  смерти процесса (`assert_persisted_tab_url_at(1, expected_url)` по обе стороны
  When) + счёт вкладок 2 после рестарта; ожидание собрано из фактического
  `downloadPath` сидинга, не хардкод.
- **Фикстуры:** `downloaded_work_seeded_with_path` перед `driver` — сидинг до
  Appium-сессии; свои данные, `clean_state()` в setup.
- **Flake-риск:** WEBVIEW-контекст используется только в самом конце и с
  reduce-to-one (`switch_to_tab(1)` + `close_other_tabs`) — sticky-context
  chromedriver'а (AT-BUG-018/022) обойдён корректно; ожидания явные.

**Зелёное воспроизведение (независимое, 1x):**
`Invoke-Pytest tests/test_library_background_open.py -k 'persists_after_kill_relaunch' -q`
→ `1 passed, 3 deselected in 76.27s`, `PYTEST_EXIT=0`.

**Красная проба (мутационная):** порча — ПОСЛЕ-рестартное ожидание подменено на
AO3-URL (`assert_persisted_tab_url_at(1, work.url)`,
`framework/tests/test_library_background_open.py:212`), т.е. симуляция регрессии
«восстановленная вкладка несёт не тот URL». Прогон:
`Invoke-Pytest tests/test_library_background_open.py -k 'at_tab_limit or persists_after_kill_relaunch' -q --no-header --tb=line`
→ `2 failed, 2 deselected in 133.04s`, `PYTEST_EXIT=1`; падение этого теста по
сути порчи: `AssertionError: URL вкладки на позиции 1:
'file:///data/user/0/com.example.ao3_wrapper/files/ao3_test_downloads/900000001.html',
ожидали 'https://archiveofourown.org/works/900000001'` (`app_steps.py:534`) —
после-рестартный оракул читает реальное состояние prefs и различает значения.
Откат — по байтовой копии (CLAUDE.md п.8): до порчи `git status --porcelain -- <файл>`
ПУСТ, blob `5229e0fa00bb06b4b6a9b1e9799d30e978bdeee3`; после отката дословно:
`git status --porcelain -- framework/tests/test_library_background_open.py` →
пустой вывод, `git hash-object` → `5229e0fa00bb06b4b6a9b1e9799d30e978bdeee3`.

**Замечание (не блокирующее):** последний And кейса — «WebView РЕНДЕРИТ
содержимое файла» — реализован только `browser_steps.assert_local_file_opened`
(проверяет схему `current_url`, не факт рендера). Соседний TC-034
(`test_downloads.py:110-111`) на том же примитиве добавляет
`assert_downloaded_page_styled` — доказательство, что DOM реально загрузился.
Рекомендация: добавить такую же вторую строку (или снять клаузу про рендер из
Then). Класс тот же, что замечание 1 в TC-174 — «клауза Then кейса не
реализована ассертом».

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение (URL/счёт/рендер), а не реализацию
- [x] Заголовок сформулирован от ожидаемого поведения
- [x] Указаны приоритет (P1), область (library) и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Блокер автоматизации отсутствует
- [x] Не C4-семьи; строка `Инвариант:` дана для полноты (персистентность не
      зависит от схемы URL)
