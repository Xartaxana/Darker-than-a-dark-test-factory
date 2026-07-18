---
key: "AT-BUG-016"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p1"
summary: "TC-040 (Save filter dialog) детерминированно крашит qemu-эмулятор (0xc0000005) при переходе в Settings — реальный live-рендер тяжёлой страницы + недождённая пост-save навигация"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-040", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-18T05:35:00Z"
updated: "2026-07-18T05:35:00Z"
archived: false
resolution: null
---

# TC-040 (Save filter dialog) детерминированно крашит qemu-эмулятор (0xc0000005) при переходе в Settings — реальный live-рендер тяжёлой страницы + недождённая пост-save навигация

_Спроецировано из `bugs/AT-BUG-016.md` (источник правды).
Статус в нашей машине: **Open**._

# AT-BUG-016 — TC-040 детерминированно крашит qemu при live-рендере + Settings-переходе

## Окружение
- Хост WHPX-гипервизор (см. environment-setup.md), эмулированный GPU.
- Live-forward сеть: `framework/core/mitm.py` (`server_replay_extra=forward`) —
  суб-ресурсы страницы, не попавшие в `.mitm`-запись, реально уходят в сеть.

## Суть долга

`test_save_filter_profile` (TC-040) грузит `sort_filter_form.mitm` —
запись РЕАЛЬНОЙ тяжёлой страницы `archiveofourown.org/tags/Fluff/works`
(`recording_builder.py:84-85`, `SORT_FILTER_FORM_URL`), чьи внешние
CSS/JS/шрифты/картинки тянутся ЖИВЬЁМ через forward (не самодостаточная
синтетическая фикстура, в отличие от стабильного `listing_basic.mitm`
у сиблинга TC-042). После `confirmSaveFilter` (`BrowserViewModel`)
приложение уходит в ФОНОВУЮ навигацию на live-URL с `work_search[...]`
параметрами (тоже не в `.mitm` → forward → ВТОРАЯ реальная тяжёлая
страница) — тест эту навигацию НЕ дожидается и сразу вызывает
`app_steps.open_tab(driver, "Settings")`, где `_find_pill` дампит ВСЁ
accessibility-дерево (`//*[@clickable]`) поверх WebView, ещё активно
рендерящего live-контент.

Пиковая конкуренция (UiAutomator2 tree-dump + GPU-компоновка живой
страницы) крашит `qemu-system-x86_64.exe` (код исключения `0xc0000005`,
faulting-модуль `unknown` — характерно для падения в
динамически-сгенерированном коде TCG/GPU-эмуляции).

## Эмпирика (critic, 2026-07-18)

- Воспроизведено САМ с ПЕРВОЙ попытки на подтверждённо здоровом свежем
  окружении (`Start-Emulator -WritableSystem` → `Get-Device: DEVICE` →
  `Install-App: Success` → `Start-Appium: ready`).
  `Invoke-Pytest tests/test_filter_profiles.py::test_save_filter_profile -v`
  → `1 failed` за 67.87s, точка падения буквально совпадает с отчётом
  воркера (`navigation.py::_find_pill`, `open_tab("Settings")`,
  `test_filter_profiles.py:130`). Teardown: `adb.exe: no devices/emulators
  found`. Повторный `Get-Device` → `NO DEVICE`.
- Независимая улика: Windows Application Event Log — краш
  `qemu-system-x86_64.exe` в 07:41:57 (код `0xc0000005`), ~35с внутри
  прогона критика — момент, совпадающий с рендером live-страницы при
  навигации в Settings.
- Историческая корреляция (6 крашей `0xc0000005` за 4 дня): оба кластера
  (07-18 сессия test-automator; 07-15 запись `sort_filter_form.mitm`
  через live-WebView при AT-BUG-006 инкремент 2) привязаны к ОДНОЙ и той
  же тяжёлой странице `archiveofourown.org/tags/Fluff/works`.
- Контрольная группа: `test_delete_filter_profile` (TC-042) зелёный 3×
  (07-15/07-17/07-18) на ТОЙ ЖЕ Appium/replay-инфраструктуре, но на
  самодостаточной синтетической `listing_basic.mitm` (без forward,
  без недождённой навигации) — единственная переменная, отличающая
  крашащийся TC-040 от стабильного TC-042, это дизайн самого TC-040
  (реальный live-рендер), не среда как таковая.
- Отклонённая гипотеза: JS DOM-инъекция (`sort_filter_form_page.py`,
  `execute_script` на CSS-hidden форму вместо Selenium `.click()`) —
  НЕ виновник; операции тривиальны, выполняются успешно ДО точки краша
  (`set_word_count_min`/`tap_save_filter_button` проходят, падение
  позже, на открытии Settings).

## Критерий готовности (Fixed)

Один из вариантов (выбор — за координатором/test-designer, D0043 роль
critic ограничена диагнозом):
1. Сделать `sort_filter_form.mitm` самодостаточной (записать/встроить
   суб-ресурсы, чтобы forward не уходил в live), как у стабильных
   синтетических фикстур; и/или записать post-save filtered-URL в
   `.mitm`, чтобы `confirmSaveFilter` не форвардил живьём.
2. Дождаться завершения фоновой навигации ДО `open_tab("Settings")`,
   чтобы tree-dump не совпадал с mid-render живой страницы.
3. Env-митигация (гипотеза, не проверена): `-gpu swiftshader_indirect`
   (софт-рендер) — проверить, переживает ли реальные страницы.

Плюс: `test_save_filter_profile` даёт 3 зелёных прогона подряд на
эмуляторе, TC-041 регрессия зелёная, `automated_by` TC-040 заполнен,
СНЯТ временный `@pytest.mark.skip(reason="AT-BUG-016")` (добавлен
координатором 2026-07-18 как guard против подхвата тестом
regression/p1-прогонами до фикса — находка critic-входа TC-041).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| — | — | — | — | Open, ждёт фикса |

## Обсуждение

**2026-07-18T05:35:00Z — координатор (Lead, Sonnet, критик-вход диагностики
PASS):** заведено по вердикту critic-диагностики (правило 3б CLAUDE.md —
непонятный баг получил critic-вход ДО того, как Lead начал отлаживать сам).
Классификация воркера ("env fail-fast, случайная нестабильность, test_debt
не заводить") отклонена — краш детерминирован, воспроизведён с первой
попытки на здоровом окружении, коррелирует с конкретной живой страницей.
Не смешивается с AT-BUG-006 (сетевой ReadTimeoutError, не краш эмулятора)
и AT-BUG-012/014 (краш НА BOOT снапшота, не mid-test). Гипотеза
JS-инъекции как причины — отклонена по коду и по факту (падение позже
точки JS-вызовов). TC-040 остаётся `Approved`, `automated_by` не
заполнен — правило 14 пропустит его при следующих проходах, пока этот
test_debt открыт (guard правила 14: не покрытые Open test_debt-багом).
TC-041 НЕ затронут (другая фикстура, уже проходил чисто) — доводится
отдельным диспатчем этого же прохода.

Найденная ось для SIBLING_MAP/докладки (не расширено, не подтверждено
дефектом — только названо): поверхность «рендер РЕАЛЬНЫХ live AO3-страниц
в эмуляторном WebView» — кандидаты `browser_steps.py::open_stable_tall_page`
(`/tos`, TC-047/048/049 через AT-BUG-015) и `browser_screen.py` живая
work-страница. Эти сиблинги ЛЕГЧЕ (дожидаются `readyState complete`, нет
конкурентного tree-dump поверх mid-render) — witness их краша нет, ось
называется для будущей точечной проверки координатором, не сканом.
