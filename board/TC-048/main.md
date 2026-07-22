---
key: "TC-048"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p1"
summary: "WebView dark mode применяется мгновенно вместе с остальным UI (без холодного рестарта)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:settings", "risk:R-11", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-09T11:45:00Z"
updated: "2026-07-09T11:45:00Z"
archived: false
resolution: "done"
---

# WebView dark mode применяется мгновенно вместе с остальным UI (без холодного рестарта)

_Спроецировано из `test-cases/settings/TC-048.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-048 — WebView dark mode применяется мгновенно, без холодного рестарта

## Предусловия
- Приложение запущено с чистыми данными, тема = Light, на вкладке Browse открыта
  страница AO3 (WebView содержимое видно светлым).
- Режим прогона: replay (детерминированная страница AO3) либо live-smoke.

## Сценарий (Given-When-Then)

**Given** приложение в светлой теме, страница AO3 в WebView отображается светлой

**When** пользователь переключает тему на Dark в Settings и возвращается на экран
Browse **без** перезапуска приложения

**Then** содержимое WebView (сама веб-страница AO3) немедленно переходит в тёмную
цветовую схему — так же, как нативные Compose-элементы вокруг него (см. TC-047) —
без необходимости перезапуска приложения

**Инвариант:** применение темы к WebView-контенту мгновенно и СИММЕТРИЧНО в
обоих направлениях перехода (Light→Dark и Dark→Light) — WebView luma
отслеживает текущий `darkTheme` без cold restart, а не только затемняется
однонаправленно.

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Исходная тема | Light |
| Целевая тема | Dark, выбрана без рестарта |

## Заметки для автоматизации
- **2026-07-17 (C4-ретрофит, test-designer) — пробел в покрытии инварианта
  (симметрия направления):** `requirements` этого кейса прямо перечисляют
  ОБА пункта чек-листа CLAUDE.md — «Toggle dark from side panel → pages go
  dark immediately» И «Toggle light → pages go light immediately» — но
  `test_webview_dark_mode_applies_instantly`
  (`framework/tests/test_settings.py:54`) проверяет ТОЛЬКО направление
  Light→Dark (`browser_steps.assert_webview_darkened`); обратное направление
  (Dark→Light) нигде в `framework/` не автоматизировано (grep по репозиторию
  на `assert_webview_light`/аналог — пусто). Симметричность заявленного
  инварианта не доказана. Не блокер (не отсутствующая фикстура/сидинг) —
  design-note в очередь test-automator/test-designer: либо расширить этот
  тест вторым направлением, либо завести отдельный P1-кейс «WebView
  возвращается в light мгновенно»; `test_debt`-багом не заводится.
- **2026-07-18 (C4-ретрофит закрыт, test-maintainer) — дыра закрыта.**
  Тест расширен вторым направлением (не отдельным кейсом): после
  подтверждённого Light→Dark замеряется тёмная luma, тема переключается
  обратно на Light, и `browser_steps.assert_webview_lightened` (новый шаг,
  симметричный `assert_webview_darkened` — тот же поллинг вместо
  одноразового чтения, та же логика LaunchedEffect(darkTheme)/reload())
  ждёт возврата luma заметно выше тёмного baseline. Witness: зелёный
  прогон на устройстве (см. отчёт test-maintainer).
- **Ожидаемый результат по умолчанию — PASS.** Это регрессионный кейс на известную
  хрупкую область (app-under-test/CLAUDE.md: «Dark mode has broken four times»), а не
  заготовленное обнаружение бага. Код уже применяет тему мгновенно: `LaunchedEffect(darkTheme)`
  в BrowserScreen.kt (~151–159) на каждое изменение `darkTheme` пушит `window.ao3SetDark(...)`,
  выставляет FORCE_DARK/ALGORITHMIC_DARKENING и делает `wv.reload()` на всех открытых
  WebView — cold start не требуется. Реальный результат прогона (pass/fail) решает
  триаж, а не предположение, сделанное до прогона.
- Не проверять `applyDarkMode()`/`AppCompatDelegate`/`textZoom` напрямую — только
  наблюдаемый визуальный результат страницы (алгоритмическое затемнение WebView).
- Тайминг: после смены темы страница делает программный `reload()` — дать ожиданию
  время на перерисовку (визуальная проверка тёмного фона после завершения загрузки),
  не проверять пиксель мгновенно в тот же кадр.
- Тема из Settings и из side panel — один и тот же стейт (`SettingsViewModel.themeMode`,
  общий `SharedPreferences` `theme_mode`); тот же наблюдаемый результат с входом через
  side panel покрыт отдельно (см. browser-кейс TC-050), здесь вход — экран Settings.
- Прежняя версия кейса ошибочно ожидала APP_BUG при первом прогоне на основе устаревшей
  строки PROJECT.md «WebView dark mode applies on next cold start». Это прочтение снято:
  PROJECT.md здесь расходится с кодом и CLAUDE.md (зафиксировано в §10 docs/01 как
  находка для владельца продукта); requirements переведены на CLAUDE.md + код.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов

## Ревью автотеста
test-reviewer, 2026-07-09 — **пройдено** (Approved → Automated).
- C1/arch_check: 0 ошибок; локаторы/измерение luma — в screens/ (BrowserScreen),
  шаги — в steps/browser_steps, sleep нет (поллинг через core/waits).
- Traceability: `@allure.id("TC-048")` == id; `@pytest.mark.p1` == P1;
  `automated_by` → существующая функция.
- Соответствие GWT и «Заметкам»: проверяется ИМЕННО WebView-контент, косвенно —
  через наблюдаемую визуальную яркость (`webview_avg_luma`), НЕ через
  `applyDarkMode()`/`AppCompatDelegate`/`textZoom`. `assert_webview_darkened`
  поллит luma до перерисовки после программного `reload()` (LaunchedEffect(darkTheme)),
  а не читает пиксель в тот же кадр — ровно требование заметки по таймингу.
  Ожидаемый исход PASS соблюдён фактическим прогоном, не допущением.
- Фикстуры/данные: `clean_app` до `driver`; baseline снимается после реальной
  загрузки AO3 (`wait_app_ready`). Зависимость от живого AO3 объявлена (тест
  `@live`, не `@replay`) — обращения к живому сайту при заявленном replay нет.
- Flake: явные ожидания (поллинг 20s), порог ratio 0.7 c большим запасом
  (светлая AO3 luma → тёмная).
- Независимый прогон: 3/3 PASS (2026-07-09, emulator-5554).

## Красная проба (red_probe, ретрофит — test-reviewer, 2026-07-22T01:33:11Z)

Режим red-probe-only (только пп.6-7 F1, статус кейса и `automation_status` не менялись).
- **Зелёный (п.6):** `Get-Device` → `DEVICE: emulator-5554`; `Invoke-Pytest
  tests/test_settings.py -k '<3 theme-теста>'` → `3 passed in 121.83s`, `PYTEST_EXIT=0`
  (в т.ч. `test_webview_dark_mode_applies_instantly`).
- **Красная проба (п.7):** порча проверяемого условия — выбор темы Dark в «When» заменён
  на Light (`select_theme(driver, "LIGHT")`), т.е. WebView остаётся светлым. Прогон `-k
  test_webview_dark_mode_applies_instantly --reruns 0` → `FAILED`:
  `TimeoutException: WebView не потемнел относительно baseline=228.5 за 20с`
  (`assert_webview_darkened`, `browser_steps.py:88`) — сообщение указывает на суть
  (WebView не затемнился), это осмысленный wait-assert самого проверяемого условия
  (затемнение), а не мусорный таймаут в постороннем шаге. Порча откачена `git checkout --
  framework/tests/test_settings.py`, дифф файла чист.
