---
key: "AT-BUG-019"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p2"
summary: "navigation.py::_find_pill фильтр \"WebView\" not in class не исключает a11y-потомков WebView — риск клика по ссылке/чекбоксу СТРАНИЦЫ вместо нативной ручки-пилюли"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-040", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-20T01:09:55Z"
updated: "2026-07-20T01:09:55Z"
archived: false
resolution: "done"
---

# navigation.py::_find_pill фильтр "WebView" not in class не исключает a11y-потомков WebView — риск клика по ссылке/чекбоксу СТРАНИЦЫ вместо нативной ручки-пилюли

_Спроецировано из `bugs/AT-BUG-019.md` (источник правды).
Статус в нашей машине: **Verified**._

# AT-BUG-019 — `_find_pill` не исключает a11y-потомков WebView (латентный риск мискклика)

## Окружение
- Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`),
  `framework/screens/navigation.py` — общий для ВСЕХ тестов, использующих
  `BottomNav.open/ensure_visible/go_browse/go_library/go_settings`
  (`app_steps.open_tab`).

## Суть долга

`_find_pill()` (`framework/screens/navigation.py`) находит «самый нижний
кликабельный не-WebView View» так:

```python
els = d.find_elements(AppiumBy.XPATH, '//*[@clickable="true"]')
cand = [e for e in els if "WebView" not in (e.get_attribute("class") or "")]
return max(cand, key=lambda e: e.rect["y"]) if cand else self._NONE_FOUND
```

Фильтр исключает только элементы, чей ОБЪЯВЛЕННЫЙ класс буквально содержит
подстроку `"WebView"` (т.е. сам контейнер `android.webkit.WebView`). Но
UiAutomator2 экспонирует ВНУТРЕННЕЕ содержимое WebView (ссылки, чекбоксы,
кнопки самой веб-страницы) как ОТДЕЛЬНЫЕ accessibility-узлы с классами вроде
`android.view.View`/`android.widget.TextView`/`android.widget.Button` —
неотличимыми по имени класса от настоящих нативных Compose-элементов. Если
на экране в данный момент есть кликабельный WebView-элемент с `bounds.y`
БОЛЬШЕ, чем у нативной ручки-пилюли (напр. страница временно/аномально
высокая — вырезана скрывающая CSS, ещё не осел layout, или просто
объективно длинный контент ниже видимой пилюли), `_find_pill` выберет И
КЛИКНЕТ по нему вместо пилюли.

## Конкретный воспроизведённый инстанс (AT-BUG-016)

`sort_filter_form.mitm` (self-contained truncation первой live-страницы
AO3, `bugs/AT-BUG-016.md`) на промежуточном этапе фикса не содержал CSS,
скрывающую `.narrow-hidden`/`.dropdown .menu` — форма `#work-filters` и
выпадающие подменю хедера рендерились развёрнуто. `_find_pill`, вызванный
из `ensure_visible()` перед `open_tab("Settings")`, выбрал `<a
href="/people/search">People</a>` (виртуальный узел `android.view.View`
внутри WebView) вместо нативной пилюли и кликнул по нему — реальная
live-навигация увела WebView, `Settings` больше не находился (`TimeoutException`
на `open_tab`, устройство при этом ЖИВО — `Get-Device: DEVICE`). В
AT-BUG-016 инстанс закрыт МЕСТНЫМ восстановлением CSS-скрытия (не
трогает `_find_pill`) — сам механизм-риск остаётся.

## Почему не пофикшено в рамках AT-BUG-016 (B4)

`_find_pill` — общий framework-механизм, используемый ВСЕМИ тестами через
`open_tab`; правка его фильтра — шире узкого скоупа одной фикстуры
(D-0043/правило 9 CLAUDE.md: чинить класс, но с более широким blast radius
— решение о диспатче за координатором/Lead, не расширяю scope сам,
D-0037).

## Критерий готовности (Fixed)

`_find_pill` надёжно исключает a11y-потомков WebView, а не только сам
контейнер — напр. проверкой родительской цепочки (`e` не является
descendant узла с классом, содержащим `"WebView"`) вместо literal-проверки
собственного класса `e`. После фикса — контрольный сценарий: страница с
кликабельным элементом ВНУТРИ WebView, чей `bounds.y` больше пилюли (можно
воспроизвести временным снятием CSS-скрытия на любой self-contained
фикстуре), не должна давать клика внутрь WebView.

## Верификация (заполняет test-maintainer / fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-07-19 (test-maintainer, B4) | app-under-test не менялся (test_debt, device-free фикс) | Контрольный сценарий AT-BUG-019 (temp, не в дереве): `sort_filter_form.mitm` с восстановленным AT-BUG-016 CSS-риском (inline `<style>`, скрывающий `.narrow-hidden`/`.dropdown .menu`, снят у обоих flow `/tags/Fluff/works`), `open_tab("Browse")` → `open_sort_filter_form` → `open_tab("Settings")` | ДО фикса (оригинальный `_find_pill`, literal-проверка): `PYTEST_EXIT=1`, `TimeoutException` на `tap(by_text("Settings"))` — `_find_pill` кликнул по a11y-узлу ВНУТРИ WebView, нативный Settings не открылся (буквально тот же класс отказа, что исходный инстанс AT-BUG-016). ПОСЛЕ фикса (`_PILL_CANDIDATES_XPATH`, исключение по цепочке предков): `PYTEST_EXIT=0`, `1 passed` — ×2 подряд (29.34s/29.01s), нативный Settings открылся (заголовок «Theme» виден без скролла) | Риск воспроизведён ДО и устранён ПОСЛЕ на одном и том же контрольном сценарии |
| 2026-07-19 (test-maintainer, B4) | app-under-test не менялся | p0-подмножество, использующее `open_tab` на Browse/Library/Settings: `framework/tests/test_smoke.py` целиком (TC-001..005, 9 тестов, `test_bottom_nav_switches_screens`/`test_clear_all_ratings`/`test_theme_toggle_stable` — прямые потребители `_find_pill` через `open_tab`) | 3 прогона подряд каноническим `Invoke-Pytest tests/test_smoke.py -v`, `Get-Device: DEVICE` до каждого: `9 passed in 221.78s` / `9 passed in 228.57s` / `9 passed in 228.69s`, все `PYTEST_EXIT=0` | Регресс p0-подмножества зелёный 3/3, эмулятор жив на всех сверках |
| 2026-07-20 (fix-verifier, D1, независимый прогон) | app-under-test не менялся (test_debt, device-free фикс; сборка новее `found_in` не требуется — правило rules.yaml «Верифицировать исправленный баг» для `type: test_debt`) | TC-040 (`framework/tests/test_filter_profiles.py::test_save_filter_profile`, прямой потребитель `open_tab`/`_find_pill`) + весь `test_filter_profiles.py` (3 теста) + минимальный smoke вокруг области: `test_smoke.py` (9 тестов, все три вкладки через `open_tab`) | `Invoke-Pytest tests/test_filter_profiles.py -v`: `3 passed in 167.72s`, `PYTEST_EXIT=0`; `Invoke-Pytest tests/test_smoke.py -v`: `9 passed in 246.49s`, `PYTEST_EXIT=0`. `Get-Device: DEVICE: emulator-5554` перед каждым прогоном | **Verified** — TC-040 и p0-смок вокруг `_find_pill` зелёные, фикс держится независимым прогоном |

Контрольный сценарий (временные файлы `framework/tests/test_at019_control_tmp.py`
и `framework/data/recordings/sort_filter_form_at019_control.mitm`, копия
`sort_filter_form.mitm` с вырезанным AT-BUG-016 inline `<style>` в обоих
`/tags/Fluff/works` flow) удалены после верификации — не часть дерева, не
трогали сам `sort_filter_form.mitm` (TC-040 не затронут). Фикс
(`framework/screens/navigation.py`): `_find_pill` больше не собирает ВСЕ
`@clickable="true"` и не фильтрует их питоном по СОБСТВЕННОМУ классу
кандидата — вместо этого XPath-предикат `_PILL_CANDIDATES_XPATH` сразу
исключает узлы, у которых `android.webkit.WebView` есть СРЕДИ ПРЕДКОВ
(`not(ancestor-or-self::*[contains(@class,"WebView")])`) — a11y-потомки
живой веб-страницы (ссылки/чекбоксы/кнопки) отсекаются по месту в дереве,
а не по имени собственного класса.

## Обсуждение

**2026-07-19T01:52:53Z — test-maintainer (found_in AT-BUG-016, B4,
попытка 3):** заведено по явному указанию workflow test-maintainer (новый
блокер, обнаруженный в ходе починки, отличный от самого долга — carve-out
test_debt, не расширяя scope своей починки). Инстанс на `sort_filter_form.mitm`
уже закрыт локально (восстановление CSS); этот баг — про САМ механизм
`_find_pill`, который остаётся латентно хрупким для ЛЮБОЙ другой страницы с
аналогичной геометрией. Не пытался чинить `_find_pill` сам — решение о
диспатче (кому и когда) за Lead/test-strategist.

**2026-07-19T14:41:00Z — test-maintainer (B4, лок test-maintainer:2026-07-19T14:07:00Z,
ЗАКРЫЛА долг):** правка по критерию готовности из самого бага —
`_find_pill` теперь исключает a11y-потомков WebView по цепочке ПРЕДКОВ
(`_PILL_CANDIDATES_XPATH`), а не по literal-проверке собственного класса
кандидата. Контрольный сценарий подтвердил РОВНО описанный в баге риск:
на self-contained фикстуре с намеренно снятым CSS-скрытием (тот же приём,
что был у `sort_filter_form.mitm` в промежуточном состоянии AT-BUG-016) ДО
фикса `_find_pill` детерминированно кликал внутрь WebView и ронял
`open_tab("Settings")` таймаутом; ПОСЛЕ фикса — тот же сценарий зелёный
дважды подряд. p0-подмножество `test_smoke.py` (прямой потребитель
`open_tab`/`_find_pill` на всех трёх вкладках) — зелёное 3/3 прогона
подряд, эмулятор жив на каждой Get-Device-сверке. Полный регресс не
запускался (DoD прямо разрешает: узкий framework-хелпер, blast radius
покрыт p0-подмножеством).

**Sibling класса D-0043 (правка критик-входа, координатор):** отчёт
воркера ошибочно утверждал «аналогичных находок не обнаружено».
`framework/screens/browser_screen.py:427-429` (`find_link_a11y_node_by_text`)
собирает тот же `//*[@clickable="true"]` и фильтрует литеральным
`"WebView" in cls` по СОБСТВЕННОМУ классу без учёта предков — структурно
та же идиома, что была слабой в `_find_pill`; код уже сам это
документирует (`browser_screen.py:421-423`, «тот же класс риска, что
navigation.py::_find_pill, AT-BUG-019»). Sibling СУЩЕСТВУЕТ, но
НАМЕРЕННО не подлежит фиксу AT-BUG-019: `find_link_a11y_node_by_text`
ищет ССЫЛКИ СТРАНИЦЫ ВНУТРИ WebView (отбор по точному
`contentDescription == text`) — ancestor-исключение вырезало бы ровно
то, что метод должен находить. Литеральный класс-фильтр здесь корректно
отсекает только сам контейнер `android.webkit.WebView`, оставляя
потомков — обратная потребность к `_find_pill`. Класс-фикс кода полон,
третьего дампа `@clickable="true"` без учёта предков в
`framework/screens/`/`framework/web/` нет.

`status`: `Open → Fixed` (guard-переход `{type: test_debt}`
`schemas/transitions.yaml`, test-maintainer — легальный актор). `lock`
снят.

**2026-07-20T01:09:55Z — fix-verifier (D1, независимая верификация,
лок `fix-verifier:2026-07-20T00:46:50Z`):** прогнан на актуальном дереве
(app-under-test не менялся — `type: test_debt`, D1 не ждёт новую сборку
для этого класса). Эмулятор `ao3_test_api34` поднят заново
(`Start-Emulator -WritableSystem`, CA переустановлен), `Get-Device:
DEVICE: emulator-5554` до каждого прогона. TC-040
(`test_save_filter_profile`) — `PASSED` в составе
`framework/tests/test_filter_profiles.py` (`3 passed in 167.72s`,
`PYTEST_EXIT=0`). Минимальный smoke вокруг области (`_find_pill` —
общий код-путь ВСЕХ `open_tab`): `framework/tests/test_smoke.py`
целиком — `9 passed in 246.49s`, `PYTEST_EXIT=0`. Дополнительно
попутно (в рамках диспатча по AT-BUG-020, тот же фикс, `duplicates`)
прогнан `framework/tests/test_rating_listing.py` целиком (`12 passed
in 371.76s`, включая TC-009[READ-work2] — тоже потребитель
`_find_pill`) — регресса нет ни на одном из двух независимых сценариев
экспозиции риска (`sort_filter_form.mitm`/TC-040 и
`listing_basic.mitm`/TC-009). Sibling из предыдущей находки
(`browser_screen.py::find_link_a11y_node_by_text`) не тронут этим
прогоном — уже задокументирован как НЕ подлежащий фиксу (обратная
семантика метода), новых аналогов не замечено. `status: Fixed →
Verified`. `lock` снят.
