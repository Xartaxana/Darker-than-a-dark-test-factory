# 02 — Архитектура тестового фреймворка

## 1. Стек

| Компонент | Выбор | Обоснование |
|---|---|---|
| Драйвер | **Appium 2 + UiAutomator2** | Black-box (не требует изменений приложения), единственный зрелый стек для гибрида Compose + WebView |
| Язык/раннер | **Python 3.12 + pytest** | Богатая экосистема фикстур/плагинов, быстрая итерация для агентов (нет компиляции), читаемые тесты |
| Отчёты | **Allure** (allure-pytest) | Шаги = Given/When/Then, вложения (скриншот, logcat, page source) на падение, история прогонов |
| Сетевая заглушка | **mitmproxy** (record/replay) | Детерминированная регрессия без живого AO3 (см. docs/01 §4) |
| Устройство | Android Emulator (AVD API 34, образ без Google Play — root для CA) | Управляется из CLI агентами |
| BDD-слой | Нет pytest-bdd; GWT выражается через `allure.step` в слое steps | Меньше магии и склейки строк — проще поддерживать агентам; связь с тест-кейсами через ID |

Альтернатива (осознанно отклонена): Maestro — прост, но YAML не даёт слоистой
архитектуры и сложной логики; Espresso/Compose-test — требует кода в репозитории
приложения.

Доступ к WebView-контенту: debug-сборка Android автоматически включает WebView
remote debugging → Appium может переключаться в контекст `WEBVIEW_com.example.ao3_wrapper`
(через chromedriver) и работать с DOM селекторами. Проверяется в Фазе 0; fallback —
работа с WebView через accessibility tree (UiAutomator2 видит текст ссылок и работ).

## 2. Слои (снизу вверх)

```
framework/
├── config/                      # СЛОЙ КОНФИГУРАЦИИ
│   ├── capabilities.py          #   Appium capabilities, appPackage/appActivity
│   ├── settings.py              #   env-переменные: режим live|replay, таймауты, пути
│   └── suites/                  #   профили наборов: smoke.txt, regression.txt, canary.txt
├── core/                        # СЛОЙ ЯДРА (ничего не знает о приложении)
│   ├── driver_factory.py        #   создание/закрытие сессии Appium
│   ├── waits.py                 #   явные ожидания; sleep запрещён конвенцией
│   ├── adb.py                   #   pm clear, install, push/pull, logcat, screencap
│   ├── contexts.py              #   переключение NATIVE_APP ↔ WEBVIEW_*
│   ├── mitm.py                  #   старт/стоп mitmproxy record/replay
│   └── reporting.py             #   allure-хуки: скриншот+logcat+page source при падении
├── screens/                     # СЛОЙ ЭКРАНОВ — Screen Object (нативный Compose)
│   ├── base_screen.py           #   базовые операции, локаторная дисциплина
│   ├── browser_screen.py        #   WebView-контейнер, bottom pill, rating panel
│   ├── tab_strip.py             #   компонент: табы, new tab, swipe-close, undo snackbar
│   ├── rating_overlay.py        #   компонент: bottom-sheet рейтинга + comment editor
│   ├── filter_panel.py          #   компонент: панель фильтр-профилей
│   ├── library_screen.py        #   вкладки, карточки, filter sheet, sort dropdown, long-press
│   └── settings_screen.py       #   темы, тумблеры, backup/restore, scan, clear
├── web/                         # СЛОЙ WEB-СТРАНИЦ — Page Object (DOM внутри WebView)
│   ├── base_page.py
│   ├── listing_page.py          #   блёрбы li.work.blurb, Rate/Note кнопки, бейджи, видимость
│   ├── work_page.py             #   /works/{id}, заголовок, download-ссылка
│   └── search_form_page.py      #   Sort & Filter форма + инжектированная Save filter
├── steps/                       # СЛОЙ БИЗНЕС-ШАГОВ (единственный слой с allure.step)
│   ├── rating_steps.py          #   rate_work_from_page(), rate_work_from_listing(), ...
│   ├── library_steps.py         #   open_tab(), apply_filters(), delete_work(), ...
│   ├── tabs_steps.py            #   open_in_background(), close_and_undo(), ...
│   ├── download_steps.py        #   download_from_library(), open_downloaded(), ...
│   ├── settings_steps.py        #   backup_to_file(), restore_from_file(), ...
│   └── app_steps.py             #   fresh_install(), restart(), clear_data(), seed_state()
├── data/                        # СЛОЙ ДАННЫХ
│   ├── builders.py              #   BackupJsonBuilder (version 2 и legacy bare-array)
│   ├── works.py                 #   реестр эталонных работ из записей (id, title, words)
│   ├── recordings/              #   mitmproxy-дампы страниц AO3 (версионируются)
│   └── seeds/                   #   готовые backup-JSON для сидинга состояний Library
├── tests/                       # СЛОЙ ТЕСТОВ (только steps + asserts, никаких локаторов)
│   ├── conftest.py              #   фикстуры: driver, чистое приложение, seeded_library, mitm
│   ├── test_rating.py
│   ├── test_visibility_filtering.py
│   ├── test_tabs.py
│   ├── test_library.py
│   ├── test_downloads.py
│   ├── test_filter_profiles.py
│   ├── test_settings_backup.py
│   ├── test_error_handling.py
│   └── canary/test_ao3_selectors.py   # live-канарейки контракта bridge
└── pytest.ini / requirements.txt / Makefile (или tasks.ps1)
```

## 3. Правила зависимостей между слоями

```
tests → steps → screens|web → core → config
data — используется tests/steps; никого не импортирует из верхних слоёв
```

- **tests** не содержат локаторов и обращений к driver; только шаги и assert'ы.
- **steps** — единственное место `allure.step("Given/When/Then ...")`; без assert'ов
  UI-состояния допустимы только «проверочные» шаги, возвращающие значения.
- **screens/web** не содержат assert'ов и знания о сценариях; один локатор объявлен
  ровно в одном месте.
- **core** ничего не знает о приложении (переиспользуем в других проектах).

## 4. Ключевые конвенции (enforce'ит агент test-automator и ревью)

1. **Связь с тест-кейсами:** каждый тест помечен `@allure.id("TC-042")` +
   `@pytest.mark.p0|p1|p2`. Покрытие — генерируемая проекция из этих меток и
   frontmatter `features` кейса (`scripts/coverage_map.py` →
   `state/coverage-map.md`); справочник фич приложения, к которым привязан
   `features`, — рукописный `docs/feature-registry.yaml`.
2. **Независимость:** каждый тест стартует из известного состояния — фикстура
   `clean_app` (pm clear) или `seeded_library(seed_name)` (restore backup-JSON через
   UI либо `run-as` push БД на debug-сборке). Порядок тестов не важен, xdist-совместимо.
3. **Никаких sleep** — только `waits.py` (условие + таймаут из config).
4. **Retry** только в live-режиме и только через pytest-rerunfailures с маркером
   `@pytest.mark.live`; в replay ретраев нет — флак должен чиниться.
5. **Артефакты падения** прикрепляются автоматически (reporting.py): скриншот,
   последние 200 строк logcat, page source активного контекста, URL активного таба.
6. **Локаторная дисциплина:** для Compose — content-desc > text > XPath по иерархии
   (в этом порядке предпочтения); для DOM — селекторы, зеркалящие `ao3_bridge.js`
   (см. PROJECT.md §Fragility note), собранные в одном модуле `web/selectors.py`.
7. **Один сценарий — один тест.** Параметризация для однотипных проверок
   (5 рейтингов, 5 сортировок) через `pytest.mark.parametrize`.

## 5. Управление приложением и окружением

- APK собирается из исходников приложения (`gradlew assembleDebug`) без каких-либо
  правок; версия и хэш сборки фиксируются в `state/app-under-test.yaml`.
- Скрипты `Makefile`/`tasks.ps1`: `make emulator`, `make install APK=...`,
  `make smoke`, `make regression`, `make canary`, `make report`.
- Прогон = одна команда → exit code + Allure-каталог + машиночитаемый
  `runs/RUN-<timestamp>/results.json` (для агентов).

## 6. Точки расширения

- Новый экран приложения → новый файл в `screens/` + шаги + тесты; слои не меняются.
- Реальное устройство вместо AVD → только `config/capabilities.py`.
- Смена репортёра/трекера багов → изолировано в `core/reporting.py` и агенте bug-reporter.
