---
id: AT-BUG-047
title: "Гонка «wait_ui_ready → немедленная WebView-навигация»: стартовая загрузка Home ещё в полёте, chromedriver теряет цель (`cannot determine loading status from no such window`) — 27 call sites, экземпляр TC-043 в RUN-20260803-2012"
type: test_debt
debt_kind: flaky_test
severity: major
status: Open
found_in: "framework commit e42eb8bb (тестируемая сборка приложения 1.10 (versionCode 11), build 6455af0c — от сборки НЕ зависит)"
fixed_in: ""
last_seen_in: "RUN-20260803-2012 (2026-08-03)"
test_cases: ["TC-043"]
runs: ["RUN-20260803-2012"]
duplicates: []
regression_of: ""
status_since: "2026-08-03T20:35:00Z"
updated: "2026-08-03T20:35:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
gitlab_issue: ""
---

# AT-BUG-047 — недостаточный барьер `wait_ui_ready` перед немедленной WebView-навигацией (класс, рецидив после TC-057)

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`), поверхность
целиком в `framework/` — `framework/steps/app_steps.py:96-102` (`wait_ui_ready`)
и 27 call sites в `framework/tests/`. От сборки приложения не зависит.
Эмулятор `ao3_test_api34` (emulator-5554), API 34, replay-режим, Appium 3.5.2,
WebView 113.0.5672.136.

## Суть долга

`app_steps.wait_ui_ready` (докстринг честен: «Ждёт отрисовки нативной оболочки
(WebView-контейнер в дереве) — без ожидания контента AO3») НЕ дожидается
оседания стартовой загрузки домашней вкладки. Когда следующий же шаг теста
переключается в WEBVIEW-контекст и навигирует (`browser_steps.open_listing` →
`contexts.in_webview` + `core.navigate.navigate` → `driver.get`), стартовая
загрузка Home может быть ещё в полёте — chromedriver теряет цель и падает:

```
selenium.common.exceptions.WebDriverException: Message: unknown error:
cannot determine loading status from no such window
  (Session info: chrome=113.0.5672.136)
```

Тест при этом уходит в allure-статус **broken** (не failed) — падение до
первого содержательного ассерта.

Это **рецидив уже диагностированного класса**: ровно та же сигнатура и тот же
механизм разобраны в `test-cases/browser/TC-057.md` (раздел ревью, 2026-07-17):
там `wait_ui_ready` заменён на `wait_app_ready` (`BrowserScreen.wait_ao3_loaded`,
барьер по фактическому `current_url`), после чего гонка ушла. Фикс тогда
применили ТОЧЕЧНО — к одному тесту, класс по остальным call sites не прошли.

Экземпляр этого прогона: `framework/tests/test_rating_listing.py:149-153`
(TC-043) — `app_steps.wait_ui_ready(driver)` и следующей строкой
`browser_steps.open_listing(...)`.

## Шаги воспроизведения (Given-When-Then)

**Given** холодный старт приложения после `clean_state` (стартовая вкладка Home
начинает грузиться), устройство под нагрузкой (длинный прогон, медленные кадры)
**When** тест выполняет `app_steps.wait_ui_ready(driver)` и СРАЗУ
`browser_steps.open_listing(driver, ...)`
**Then (ожидалось)** WebView навигирует на replay-листинг, тест доходит до
ассертов
**Actual (фактически)** `WebDriverException: cannot determine loading status
from no such window` внутри `navigate` — тест broken за ~3 секунды

## Частота

1 из 1 в RUN-20260803-2012 (полный regression, 165 тестов, TC-043 упал).
**0 из 3 при изолированном перезапуске** (2026-08-03, дословный вывод — в
триаж-разделе `runs/RUN-20260803-2012.md`): гонка проявляется под нагрузкой
длинного прогона, детерминированного репро на свободной машине нет. Прецедент
TC-057 (2026-07-17) воспроизводился детерминированно — там навигация шла на
ЖИВОЙ AO3 (медленнее), здесь replay успевает чаще.

## Артефакты

- Allure result: `framework/allure-results/d2e400a6-8c43-43c8-b3b4-d631c006b1d5-result.json`
- Скриншот падения: `framework/allure-results/b650e507-4921-4bc1-81fd-57c3ff9c28d9-attachment.png`
  (страница AO3 на середине загрузки: шапка отрисована, тело пустое)
- Page source: `framework/allure-results/a45427ad-b7a1-448a-aa44-a50dc114008f-attachment.xml`
- Logcat: `framework/allure-results/c7c45d49-128e-4340-9090-90360b4a33ab-attachment.txt`
  — ключевые строки момента падения:
  `19:25:49.213 ActivityManager: Start proc 31832:com.android.webview:sandboxed_process0`
  (WebView-процесс ещё только стартует) и
  `19:25:49.653 OpenGLRenderer: Davey! duration=3229ms` (кадр 3.2 с — устройство
  под нагрузкой). Ни crash, ни ANR, ни FATAL — приложение живо.
- Контекст драйвера на момент снимка: `context=NATIVE_APP`
  (`69980e4f-cbc0-4cb7-a8ff-ac99b353550f-attachment.txt`).

## Анализ (failure-analyst)

Почему это долг ТЕСТОВОЙ системы, а не приложения/среды:

1. Падение — в клиенте автоматизации (chromedriver ↔ WebView), а не в
   содержательном ассерте; приложение в logcat живо (нет FATAL/ANR/crash).
2. Сборка приложения не менялась с 2026-06-28 (`state/app-under-test.yaml`,
   `source_commit 63f6aac3`) — APP_CHANGED/APP_BUG исключены механически.
3. Соседние по времени тесты прогона (индексы 79 и 81 таймлайна: 21:25:11 и
   21:26:12) прошли зелёными на том же эмуляторе — эмулятор/прокси/сеть в
   порядке, ENV_ISSUE не подтверждается (`Get-Device → DEVICE: emulator-5554`,
   `recoveries 0/2`).
4. Механизм и фикс уже описаны в репозитории для TC-057 — причина установлена, а
   не «неизвестная нестабильность»: барьер теста слабее, чем требует следующий
   шаг.

Почему rerun-политика не помогла: `framework/pytest.ini` перезапускает только
`--only-rerun ReadTimeoutError|MaxRetryError`; `WebDriverException` этого класса
в фильтр не входит (и не должен входить вслепую — правильнее убрать гонку).

## Критерий готовности (Fixed)

- [ ] Класс, а не экземпляр: пройти по всем 27 call sites «`wait_ui_ready` →
      немедленная WebView-навигация» и закрыть гонку. Инвентарь на момент
      заведения (`framework/tests/`): `test_rating_listing.py` — 10,
      `canary/test_ao3_selectors.py` — 8, `test_visibility.py` — 4,
      `test_settings.py` — 2, `test_compatibility.py`, `test_replay_infra_probe.py`,
      `test_side_panel.py` — по 1.
- [ ] Предпочтительная форма — не правка 27 тестов по одному, а барьер В САМОМ
      входе в WebView: `contexts.in_webview`/`core.navigate.navigate` дожидается
      оседания текущей загрузки (или `open_listing`/`open_work_page` делают это
      сами), чтобы новый тест не мог унаследовать гонку. Точечная замена
      `wait_ui_ready → wait_app_ready` по образцу TC-057 — допустимый минимум, но
      она уже один раз не удержала класс.
- [ ] Не заменять ожидание `sleep`'ом и не расширять `--only-rerun` на
      `WebDriverException` (это маскировка, а не фикс).
- [ ] Красная проба: показать гонку под искусственной задержкой стартовой
      загрузки (например, throttling replay-ответа Home) — ДО фикса тест broken с
      той же сигнатурой, ПОСЛЕ — зелёный.
- [ ] 3 зелёных прогона подряд TC-043 изолированно + зелёный `test_rating_listing.py`
      и `test_visibility.py` целиком.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**[failure-analyst @ 2026-08-03T20:35:00Z]** Заведён по вердикту `TEST_BUG`
падения TC-043 в `runs/RUN-20260803-2012.md`. Собрат по классу «ожидание слабее,
чем требует следующий шаг» — `AT-BUG-048` (свайп-поиск в Settings), заведён тем
же ходом; общего кода у них нет, объединять фикс не требуется.
