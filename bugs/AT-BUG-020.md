---
id: AT-BUG-020
title: "TC-009[READ-work2] детерминированно падает на open_tab(\"Library\") после dismiss_rating_overlay — NoSuchElementError на UiSelector().text(\"Library\")"
type: test_debt
debt_kind: flaky_test
severity: major
status: Open
found_in: "test-automator (canary batch B, 2026-07-19): полный p0-регресс (38 тестов) после автоматизации TC-072..077 дал 3 падения; 2 из них (TC-007[READ], TC-015) не воспроизвелись на изолированном повторе (конкуренция за хост-ресурсы во время 18-минутного марафона), но TC-009[READ-work2] упал СНОВА на том же месте. Отдельный соло-повтор именно этого узла (framework/tests/test_rating_listing.py::test_rate_work_from_listing_overlay[listing_basic.mitm-READ-work2]) — 3/3 FAIL, идентичная точка: TimeoutException/NoSuchElementError на UiSelector().text(\"Library\") сразу после dismiss_rating_overlay. ДЕТЕРМИНИРОВАННО, не флейк по частоте — но затрагивает только эту READ/work2 комбинацию параметризации, остальные 4 параметризации TC-009 (LOVE/LIKE/PENDING/DISLIKE или их аналоги) прошли."
fixed_in: ""
last_seen_in: ""
test_cases: ["TC-009"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-07-19T05:21:48Z"
updated: "2026-07-19T05:21:48Z"
reopen_count: 0
dispute_count: 0
awaiting: none
lock: ""
---

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
