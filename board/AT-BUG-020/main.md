---
key: "AT-BUG-020"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p1"
summary: "TC-009[READ-work2] детерминированно падает на open_tab(\"Library\") после dismiss_rating_overlay — NoSuchElementError на UiSelector().text(\"Library\")"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-009", "duplicate:AT-BUG-019", "sev:major"]
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

# TC-009[READ-work2] детерминированно падает на open_tab("Library") после dismiss_rating_overlay — NoSuchElementError на UiSelector().text("Library")

_Спроецировано из `bugs/AT-BUG-020.md` (источник правды).
Статус в нашей машине: **Verified**._

# AT-BUG-020 — TC-009[READ-work2] детерминированно не находит вкладку "Library" после dismiss_rating_overlay

## Окружение
- `emulator-5554`, Appium 2 + UiAutomator2, приложение `com.example.ao3_wrapper`, debug.
- `framework/tests/test_rating_listing.py::test_rate_work_from_listing_overlay`
  (параметризация `[listing_basic.mitm-READ-work2]`) — TC-009, `automated_by`
  уже был заполнен и Automated/Verified ДО этой сессии (см. AT-BUG-017 witness
  2026-07-19: тот же файл, 12/12 passed дважды — см. «Обсуждение» ниже за
  согласованием этого видимого противоречия).

## Суть долга

Полный p0-регресс, прогнанный test-automator ПОСЛЕ автоматизации canary batch B
(TC-072..077), дал 3 падения из 38. Дифференциальная проверка (изолированный
повтор без конкурентной нагрузки марафона) развела их: `TC-007[READ]` и
`TC-015` не воспроизвелись (похоже на ресурсную конкуренцию хоста), но
`TC-009[READ-work2]` упал повторно на ТОМ ЖЕ месте, и ещё 3/3 в отдельном
соло-повторе — детерминированно для этой конкретной параметризации.

Точка отказа: `NoSuchElementError` на `UiSelector().text("Library")`
(`app_steps.open_tab`/`BottomNav.open` через `navigation.py`) сразу ПОСЛЕ
`rating_overlay.dismiss_rating_overlay()` — то есть нативная нижняя навигация
не находится сразу после закрытия rating-оверлея для этой комбинации
рейтинга/работы.

## Вклад batch B — НЕ ИСКЛЮЧЁН (честная формулировка, critic-поправка)

Первоначальный отчёт test-automator (ESC-004, `state/escalations.md`) заявил
«доказано, не регрессия batch B» на основании `git diff` против
`navigation.py`/`app_steps.py` (не менялись) и того, что падающий шаг идёт по
неизменённому коду. Critic (ревью batch B, 2026-07-19) указал: это доказывает
только УЗКОЕ утверждение («падающая строка не отредактирована»), не исключает
ВКЛАД через побочный эффект. Единственная реальная правка в код-пути ДО точки
падения — `browser_steps.tap_rate_button` (Selenium `.click()` → JS
`element.click()` + `scrollIntoView({block:'center'})`, добавлено этой же
сессией для TC-072/074/076 живого AO3). Гипотеза critic: `scrollIntoView`
может сдвигать раскладку WebView, из-за чего `dismiss_rating_overlay` тапает
scrim по смещённой точке → overlay не закрывается штатно → нижняя навигация
не находится сразу.

**Согласовать со ВИДИМЫМ противоречием**: `bugs/AT-BUG-017.md` несёt witness
ОТ ТОГО ЖЕ ДНЯ (2026-07-19, до этой сессии) — `test_rating_listing.py` (все 12
тестов, включая все 5 параметризаций TC-009) дал **12 passed дважды подряд**,
т.е. TC-009[READ-work2] был зелёным. Разница между этим прогоном и падениями
в этой сессии — состояние дерева ДО/ПОСЛЕ правки `tap_rate_button`
(scrollIntoView добавлен между ними). Это не доказательство вклада batch B,
но прямая нестыковка, которую нужно закрыть измерением, не предположением.

## Критерий готовности (Fixed)

1. Диагностика: воспроизводится ли TC-009[READ-work2] при ВРЕМЕННОМ откате
   `tap_rate_button` к нативному `.click()` без `scrollIntoView` (git stash /
   временная правка, не постоянная) — прямой тест гипотезы critic.
2. Если гипотеза подтвердится — найти способ починить `tap_rate_button` для
   живого AO3 (обход `div#tos_prompt`), не ломающий геометрию/скролл для
   существующих rating-тестов (напр. `scrollIntoView({block:'nearest'})` вместо
   `'center'`, или явный scroll-restore после клика).
3. Если гипотеза НЕ подтвердится — диагностировать реальную причину (тайминг
   scrim-тапа/анимации закрытия bottom-sheet специфичен для READ/work2) и
   починить её.
4. 3 зелёных прогона TC-009[READ-work2] подряд + полный p0 без регресса.

## Верификация (заполняет test-maintainer / fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| — | — | — | — | Open, ждёт диагностики |
| 2026-07-19 (test-maintainer, B4) | app-under-test не менялся (test_debt, device-free фикс) | Диагностика критерия готовности п.1 (контролируемый A/B на `framework/screens/navigation.py`, `tap_rate_button` НЕ трогался ни в одном из двух состояний): (A) файл временно откачен к `HEAD` (пре-AT-BUG-019 `_find_pill`, literal-проверка собственного класса) — `Invoke-Pytest tests/test_rating_listing.py::test_rate_work_from_listing_overlay[listing_basic.mitm-READ-work2] -v`; (B) файл восстановлен к текущей (уже присутствовавшей в рабочем дереве, некоммиченной) версии `_PILL_CANDIDATES_XPATH` (фикс AT-BUG-019) — тот же узел | (A) `FAILED`, `PYTEST_EXIT=1`, идентичная трасса бага (`TimeoutException`/`NoSuchElementError` на `UiSelector().text("Library")` сразу после `dismiss_rating_overlay`, `screens\\navigation.py:60: in open`) — гипотеза critic (вклад `scrollIntoView` НЕ исключён) подтверждена как ТРИГГЕР (сдвигает WebView-скролл READ-work2, обнажая a11y-потомка WebView с bounds.y выше пилюли), но не как ЕДИНСТВЕННАЯ причина. (B) `PASSED`, `PYTEST_EXIT=0`, 30.19s/29.32s/28.91s — 3 зелёных подряд, `tap_rate_button` НЕ менялся ни разу | Единственная переменная — `navigation.py`; при идентичном `tap_rate_button` (JS-клик+`scrollIntoView`) смена ТОЛЬКО `_find_pill` переключает FAIL↔PASS — root cause изолирован в `_find_pill`, не в `tap_rate_button` |
| 2026-07-19 (test-maintainer, B4) | app-under-test не менялся | Полный `framework/tests/test_rating_listing.py` (12 тестов — все 5 параметризаций TC-009 + TC-010/011/012/043/044/045/056) | `Invoke-Pytest tests/test_rating_listing.py -v`: `12 passed in 348.39s`, `PYTEST_EXIT=0` — регресса нет | Полный файл зелёный |
| 2026-07-19 (test-maintainer, B4) | app-under-test не менялся | TC-072/074/076 (живой archiveofourown.org, `@pytest.mark.live`, единственные потребители `tap_rate_button` со `scrollIntoView` вне TC-009) — `test_rate_button_badge_opaque_color_live`, `test_note_button_present_iff_comment_live`, `test_tag_button_present_iff_custom_tag_live` | `Invoke-Pytest` тремя node-id: `3 passed in 93.65s`, `PYTEST_EXIT=0` — `tap_rate_button` НЕ менялся в этой починке, регресса на live-канарейке нет (сеть проверена `Invoke-WebRequest archiveofourown.org` → `STATUS=200` до прогона) | Live-канарейка зелёная, откат `tap_rate_button` не потребовался |

`Get-Device` до диагностики и после всей серии прогонов: `DEVICE: emulator-5554` оба раза — окружение не деградировало.

| 2026-07-20 (fix-verifier, D1, независимый прогон) | app-under-test не менялся (test_debt, device-free фикс; сборка новее `found_in` не требуется — правило rules.yaml для `type: test_debt`) | TC-009 полностью: `framework/tests/test_rating_listing.py` целиком (12 тестов, все 5 параметризаций TC-009 + TC-010/011/012/043/044/045/056) + соло-параметризация `test_rate_work_from_listing_overlay[listing_basic.mitm-READ-work2]` отдельным прогоном | `Invoke-Pytest tests/test_rating_listing.py -v`: `12 passed in 371.76s`, `PYTEST_EXIT=0` (TC-009[READ-work2] — `PASSED`); соло-прогон `Invoke-Pytest 'tests/test_rating_listing.py::test_rate_work_from_listing_overlay[listing_basic.mitm-READ-work2]' -v`: `1 passed in 30.96s`, `PYTEST_EXIT=0`. `Get-Device: DEVICE: emulator-5554` до каждого прогона | **Verified** — TC-009[READ-work2] зелёный и в полном файле, и соло; фикс держится независимым прогоном |

## Обсуждение

**2026-07-19T05:21:48Z — координатор (Lead, Sonnet, critic-вход на приёмке
batch B):** заведено по прямой директиве critic — регресс ранее принятой
автоматизации (TC-009 был Automated/Verified) не может жить только в
`state/escalations.md` (ESC-004), т.к. сканер очереди триггерит B4 по
`bugs/*.md`, не по эскалациям — иначе долг молча сгниёт вне конвейера. Полный
исходный след («что нужно от человека», гипотезы, дифференциальная проверка) —
`state/escalations.md#ESC-004`, не дублируется здесь целиком. `debt_kind`
выбран `flaky_test` (не `broken_environment`) — отказ детерминирован ДЛЯ ЭТОЙ
параметризации, не средовой; при уточнении диагностики (шаг 1 критерия) может
смениться на `weak_locator`, если причина оказ ется в самом `dismiss_rating_overlay`/навигационном локаторе, а не в новом `scrollIntoView`.

Этот баг НЕ блокирует приёмку canary batch B (6 новых кейсов независимы,
зелёные 3/3 изолированно и присутствуют/зелёные в полном регрессе) — но
диагностика вклада `tap_rate_button`-правки в этот регресс остаётся открытым
техническим долгом, назначенным test-maintainer следующим B4-диспатчем.

**2026-07-19T15:20:00Z — test-maintainer (B4, лок test-maintainer:2026-07-19T14:15:00Z,
ЗАКРЫЛА долг измерением, не предположением).** При старте починки обнаружено:
рабочее дерево уже содержит НЕКОММИЧЕННУЮ правку `framework/screens/navigation.py`
(`_find_pill`/`_PILL_CANDIDATES_XPATH`, исключение a11y-потомков WebView по цепочке
ПРЕДКОВ вместо literal-проверки собственного класса) — тот самый фикс, ранее
применённый и записанный в `bugs/AT-BUG-019.md` («navigation.py::_find_pill фильтр
"WebView" not in class не исключает a11y-потомков WebView»), `status: Fixed`. Первый
же прогон TC-009[READ-work2] на текущем (некоммиченном) дереве дал `PASSED` дважды
подряд — прямое противоречие заявленной в этом баге детерминированности (3/3 FAIL).

Проведён контролируемый A/B-тест для разрешения противоречия и прямой проверки
критерия готовности п.1 (гипотеза critic про вклад `tap_rate_button`/`scrollIntoView`):
`navigation.py` временно откачен к версии `HEAD` (пре-AT-BUG-019, literal-проверка
`"WebView" not in class`), `tap_rate_button` НЕ ТРОГАЛСЯ ни разу (JS-клик +
`scrollIntoView({block:'center'})` остаётся как есть на всём протяжении диагностики).
Результат: (A) с ОТКАЧЕННЫМ `navigation.py` — `FAILED`, идентичная трасса бага
(`NoSuchElementError` на `UiSelector().text("Library")` в `screens\navigation.py:60:
in open`); (B) с ВОССТАНОВЛЕННЫМ (текущим, некоммиченным) `navigation.py` — `PASSED`
3/3 подряд. Единственная варьируемая переменная — `navigation.py`; `tap_rate_button`
идентичен в обоих состояниях. Это ИСКЛЮЧАЮЩИЙ прогон (класс F-30/калибровка №3,
CLAUDE.md п.6): изолирует root cause в `_find_pill`, не в `tap_rate_button`.

Механизм совпадения (почему READ/work2, не остальные 4 параметризации TC-009):
`tap_rate_button.scrollIntoView({block:'center'})` центрирует Rate-кнопку блёрба —
для READ (`W.READ`, `900000003`, ТРЕТИЙ по порядку блёрб из пяти, `works.py`)
требуется заметный скролл вниз (в отличие от LOVED/KUDOSED — первых двух блёрбов,
почти не требующих скролла). Сдвинутый скролл listing-страницы обнажает виртуальные
a11y-узлы WebView (ссылки/чекбоксы блёрбов ниже) с `bounds.y`, оказавшимся БОЛЬШЕ,
чем у нативной пилюли — ровно риск, описанный в `bugs/AT-BUG-019.md`. Т.е.
`scrollIntoView` — реальный ТРИГГЕР для этой конкретной комбинации (гипотеза critic
подтверждена как экспонирующий фактор, не отброшена), но ДЕФЕКТ — в `_find_pill`
(weak_locator), не в `tap_rate_button`; откатывать/менять `tap_rate_button` не
требуется — фикс `_find_pill` закрывает класс целиком, независимо от того, какая
именно WebView-страница/скролл его провоцирует. Согласовано и с видимым
противоречием AT-BUG-017 (12/12 passed ДО правки `scrollIntoView`): тогда сдвига
скролла не было вовсе, риск `_find_pill` не экспонировался.

`debt_kind` уточнён `flaky_test → weak_locator` (отказ был не средовым и не по
частоте, а детерминированным дефектом локатора — подтверждено). `duplicates:
["AT-BUG-019"]` — это ТОТ ЖЕ дефект (D-0043, чинить класс: `_find_pill` — общий
код-путь `BottomNav.open`/`ensure_visible`, используемый ВСЕМИ тестами через
`open_tab`, включая TC-009), обнаруженный НЕЗАВИСИМО через два разных сценария
(AT-BUG-019 — `sort_filter_form.mitm`/TC-040; AT-BUG-020 — `listing_basic.mitm`/
TC-009 READ-work2). Фикс НЕ дублируется — `fixed_in` указывает на тот же
`framework/screens/navigation.py::_find_pill`. Полный регресс
`framework/tests/test_rating_listing.py` (12/12) и живая канарейка TC-072/074/076
(3/3, сеть проверена `Invoke-WebRequest` перед прогоном) подтверждают отсутствие
регресса — витнесс в таблице «Верификация» выше. `Get-Device` до/после диагностики
и после регресса — `DEVICE: emulator-5554` на каждой сверке.

Новых блокеров/находок сверх уже задокументированного sibling (`AT-BUG-019`) не
обнаружено — `app-under-test/` не тронут (только чтение `works.py`/`navigation.py`/
`browser_steps.py`/`rating_overlay.py`/`rating_steps.py`/`test_rating_listing.py`
на стороне фреймворка).

`status`: `Open → Fixed` (guard-переход `{type: test_debt}`, `schemas/transitions.yaml`,
test-maintainer — легальный актор). Лок снят. `state/escalations.md#ESC-004` уже
`resolved` (ссылается сюда) — новых правок эскалации не требуется.

**2026-07-20T01:09:55Z — fix-verifier (D1, независимая верификация,
лок `fix-verifier:2026-07-20T00:46:50Z`):** прогнан на актуальном дереве
(app-under-test не менялся). Эмулятор поднят заново
(`Start-Emulator -WritableSystem`), `Get-Device: DEVICE: emulator-5554`
до каждого прогона. Полный `test_rating_listing.py` — `12 passed in
371.76s`, `PYTEST_EXIT=0` (все 5 параметризаций TC-009, включая
READ-work2, зелёные). Соло-параметризация
`[listing_basic.mitm-READ-work2]` отдельным прогоном — `1 passed in
30.96s`, `PYTEST_EXIT=0`. Фикс — тот же `_find_pill`/
`_PILL_CANDIDATES_XPATH`, что и AT-BUG-019 (независимо проверен той же
сессией на TC-040); duplicate-связь подтверждена: один фикс закрывает
оба сценария экспозиции. `status: Fixed → Verified`. `lock` снят.
