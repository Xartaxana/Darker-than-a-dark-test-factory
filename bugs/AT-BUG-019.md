---
id: AT-BUG-019
title: "navigation.py::_find_pill фильтр \"WebView\" not in class не исключает a11y-потомков WebView — риск клика по ссылке/чекбоксу СТРАНИЦЫ вместо нативной ручки-пилюли"
type: test_debt
debt_kind: weak_locator
severity: minor
status: Open
found_in: "test-maintainer (AT-BUG-016, B4, попытка 3, 2026-07-19): при диагностике второй причины нестабильности TC-040 обнаружено, что framework/screens/navigation.py::_find_pill (используется ensure_visible()/_expand_pill() перед КАЖДЫМ open_tab) фильтрует кандидатов на \"нижнюю ручку-пилюлю\" только по literal-проверке `\"WebView\" not in (e.get_attribute(\"class\") or \"\")` — но виртуальные accessibility-узлы ВНУТРИ живого android.webkit.WebView (ссылки/чекбоксы/кнопки самой веб-страницы) экспонируются UiAutomator2 с классами android.view.View/android.widget.TextView/android.widget.Button/android.widget.CheckBox — ни один из них НЕ содержит строку \"WebView\", и потому НЕ отфильтровывается. Если на текущей странице есть кликабельный WebView-элемент с bounds.y БОЛЬШЕ, чем у нативной пилюли (напр. страница без ожидаемого CSS-скрытия дропдаунов/форм рендерится развёрнуто и аномально высоко), _find_pill выбирает и КЛИКАЕТ по нему вместо пилюли — реальная live-навигация внутри WebView, после которой нативная панель навигации больше не открывается тем же путём (наблюдался конкретный инстанс на sort_filter_form.mitm — клик по <a href=\"/people/search\">, см. bugs/AT-BUG-016.md «Обсуждение» запись 2026-07-19T01:52:53Z за полным разбором и воспроизведением)."
fixed_in: ""
last_seen_in: ""
test_cases: ["TC-040"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-07-19T01:52:53Z"
updated: "2026-07-19T01:52:53Z"
reopen_count: 0
dispute_count: 0
awaiting: none
lock: ""
---

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

## Обсуждение

**2026-07-19T01:52:53Z — test-maintainer (found_in AT-BUG-016, B4,
попытка 3):** заведено по явному указанию workflow test-maintainer (новый
блокер, обнаруженный в ходе починки, отличный от самого долга — carve-out
test_debt, не расширяя scope своей починки). Инстанс на `sort_filter_form.mitm`
уже закрыт локально (восстановление CSS); этот баг — про САМ механизм
`_find_pill`, который остаётся латентно хрупким для ЛЮБОЙ другой страницы с
аналогичной геометрией. Не пытался чинить `_find_pill` сам — решение о
диспатче (кому и когда) за Lead/test-strategist.
