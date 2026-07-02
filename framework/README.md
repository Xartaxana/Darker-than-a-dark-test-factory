# AO3 Reader — тестовый фреймворк

Black-box UI-автотесты приложения ao3-wrapper. Стек: **Appium 2/3 + UiAutomator2 +
Python/pytest + Allure**, mitmproxy (replay, в доводке). Архитектура — docs/02.

## Запуск

```powershell
. D:\AO3_tests\scripts\env.ps1          # JAVA_HOME/ANDROID_HOME/PATH
. D:\AO3_tests\scripts\tasks.ps1        # раннеры
Start-Emulator ; Start-Appium ; Install-App
Invoke-Smoke                            # pytest -m p0
Show-Report                             # allure serve
```

Appium обязан быть запущен с флагом:
`--allow-insecure uiautomator2:chromedriver_autodownload` (WebView Chrome 113 —
chromedriver докачивается автоматически). `Start-Appium` уже это делает.

## Структура (слои, сверху вниз)

| Слой | Назначение |
|---|---|
| `tests/` | Только шаги + assert. Маркеры `p0/p1/live/replay`, `@allure.title` |
| `steps/` | Бизнес-шаги в Given-When-Then (единственный слой с `allure.step`) |
| `screens/` | Screen Objects нативного Compose (локаторы — только здесь) |
| `web/` | Page Objects DOM внутри WebView; `selectors.py` зеркалит `ao3_bridge.js` |
| `data/` | Реестр работ + сидинг Room (`seed_db.py`, без обращения к AO3) |
| `core/` | driver/waits/adb/contexts/reporting/mitm — не знает о приложении |
| `config/` | settings + capabilities (env-driven) |

## Что уже покрыто (P0 smoke, 9 тестов)

- Запуск и указание WebView на AO3 (live).
- Нижняя навигация Browse/Library/Settings.
- Засеянная работа попадает в свою вкладку Library (5 рейтингов, через сидинг Room).
- Clear all ratings очищает библиотеку.
- Переключение тем Light/Dark/System без краша.

Полный прогон ~3.5 мин на AVD, дважды подряд 9/9 зелёные.

## Важные факты об UI приложения (сверено с исходниками + живым UI)

- **Нижняя навигация скрыта на вкладке Browse** за нижней ручкой-пилюлей; `BottomNav`
  раскрывает её автоматически (`screens/navigation.py`).
- **Вкладки Library — в ВЕРХНЕМ регистре**: `FAVORITE/KUDOSED/READ/PENDING/DISLIKED/FILES`.
- **Расхождение с PROJECT.md**: карта приложения обещает вкладки «Loved/Liked/Downloads»,
  а фактические подписи — «Favorite/Kudosed/Files». Кандидат в баги документации —
  передано test-designer (см. docs/03).
- **Панель инструментов Browser — вертикальная слева** (настройка PanelSide.LEFT).
- **Cloudflare bot-check** периодически показывается на старте (риск R-03) — smoke это
  не ломает: тесты навигации/Library/Settings опираются на нативный UI и сидинг, а не
  на контент AO3.
- Кнопка «Clear…» с юникод-многоточием; клик в Compose висит на родителе — см.
  `settings_screen.open_clear_all_dialog`.

## Конвенции

- Никаких `sleep` — только `core/waits`.
- Один локатор — одно место (screen/page-объект).
- **Вывод локатора: код → дерево → скриншот.** Сначала исходники приложения, причём
  место рендера, а не определение строки (`tab.label.uppercase()` в LibraryScreen.kt:207
  и `AnimatedVisibility` в BottomBar.kt:99 — примеры того, что теряется при чтении
  только enum'ов). Затем верификация по живому page_source: семантика Compose ≠ код
  (клик на родителе, безымянные View, UiScrollable не видит Compose-скролл).
  Скриншот — последнее средство.
- Состояние теста задаётся фикстурами (`clean_app`/`seeded_library`), порядок тестов не важен.
- Артефакты падения (скриншот, page source, logcat, контекст/URL) крепятся к Allure
  автоматически (`core/reporting` + хук в `conftest`).
