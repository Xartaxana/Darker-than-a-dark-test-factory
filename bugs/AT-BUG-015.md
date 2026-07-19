---
id: AT-BUG-015
title: "TC-047 scroll-preservation assert недобит — WebView scrollY на Browse root не даёт устойчивого ненулевого значения после scrollTo (нужна диагностика)"
type: test_debt
debt_kind: missing_evidence
severity: minor
status: Verified
found_in: "test-maintainer (хозяйство-3, C4-ретрофит TC-047 дыра «сохранность скролла», 2026-07-18): попытка добавить assert сохранности window.scrollY WebView до/после переключения темы упёрлась в нестабильное поведение scrollTo на живой странице archiveofourown.org (Browse root) — assert не добит в рамках диспатча (правило 9/новый блокер CLAUDE.md test-maintainer)."
fixed_in: "framework/steps/browser_steps.py (open_stable_tall_page), framework/tests/test_settings.py (assert сохранности scroll в test_theme_dark_applies_instantly_without_recreating_activity, допуск 2px)"
last_seen_in: ""
test_cases: ["TC-047"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-07-19T01:10:00Z"
updated: "2026-07-19T01:10:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
lock: ""
---

# AT-BUG-015 — TC-047 scroll-preservation assert не добит (нужна диагностика WebView scrollY)

## Окружение
- Не зависит от сборки приложения в узком смысле (не app-under-test код
  меняется), но зависит от живой страницы archiveofourown.org (`@pytest.mark.live`,
  TC-047) — не воспроизводится device-free.
- Обнаружено при доработке `framework/tests/test_settings.py::
  test_theme_dark_applies_instantly_without_recreating_activity` (C4-ретрофит
  дыры «сохранность скролла» в TC-047, докладной диспатч «хозяйство-3»,
  2026-07-18).

## Суть долга

TC-047 (`test-cases/settings/TC-047.md`) заявляет инвариант «URL И позиция
прокрутки страницы Browse после переключения темы совпадают со значениями до
переключения» — но текущий автотест assert'ит только URL. Попытка закрыть эту
часть добавлением `browser_steps.scroll_webview_to`/`get_webview_scroll_y`
(execute_script `window.scrollTo`/`window.scrollY` через `contexts.in_webview`,
уже добавлены в `framework/steps/browser_steps.py` — инфраструктура рабочая,
пригодна для повторного использования) и вызовом в теле теста дала 2
последовательных FAIL на устройстве:

1. Первая попытка (`window.scrollTo(0, 900)` без `behavior`): `scrollY` читался
   как `0` сразу после вызова — гипотеза: CSS `scroll-behavior: smooth` на
   странице анимирует переход вместо мгновенного прыжка (тот же класс, что уже
   решён в `ao3_bridge.js` через `behavior: 'instant'` для `scrollBy`).
2. Вторая попытка (добавлен `behavior: 'instant'` + поллинг `scrollY > 0` до
   5с) — TimeoutException: `scrollY` так и не стал `>0` за 5 секунд. Это уже
   НЕ объясняется одной только анимацией — вероятные гипотезы (ни одна не
   проверена под давлением времени хода):
   - страница-Given (Browse root = `archiveofourown.org` без пути) недостаточно
     высокая на использованном экране эмулятора (короче `innerHeight`) —
     `scrollTo` тогда легитимно клампится к 0, и assert на этой Given-странице
     в принципе некорректен (нужна страница с заведомо большим контентом,
     например листинг/поиск, — но тогда меняется Given кейса);
   - `contexts.in_webview()` переключается на НЕ тот WEBVIEW-контекст (несколько
     вкладок/контекстов, `contexts.webview_name` берёт первый попавшийся, а не
     гарантированно активную вкладку) — scrollTo/scrollY читаются с разных
     контекстов;
   - тайминг: `wait_app_ready` подтверждает только смену URL, но контент может
     ещё довёрстываться (высота растёт после), первый вызов `scrollTo` мог
     попасть на промежуточное состояние DOM.
   Диагностический ad hoc скрипт (сравнение `document.body.scrollHeight` /
   `window.innerHeight` / `scrollY` до и после `scrollTo`) не довёл до конца —
   упёрся в отдельную проблему окружения самого скрипта (сессия Appium не
   дождалась WebView после ручного `create_driver`, вероятно из-за отсутствия
   `clean_app`-подготовки, которую несёт штатная фикстура) — сам live-вопрос
   («что реально происходит со scrollY на этой странице») остался без ответа.

Ассерт **не замаскирован** — вместо ослабления или удаления диагноза целиком
откачен ход к последней зелёной версии теста (URL-only, как было до
диспатча); инфраструктура шагов оставлена (не используется, не мешает).

## Критерий готовности (Fixed)

- Диагностирована фактическая причина (одна из гипотез выше подтверждена
  измерением на устройстве — например, distinct scrollHeight/innerHeight лог,
  или список `driver.contexts` в момент вызова).
- `test_theme_dark_applies_instantly_without_recreating_activity` расширен
  рабочим assert'ом сохранности scroll-позиции (используя уже добавленные
  `browser_steps.scroll_webview_to`/`get_webview_scroll_y` или их доработанную
  версию), падение которого содержательно (не таймаут по неверной причине).
- 3 зелёных прогона подряд на устройстве.
- `test-cases/settings/TC-047.md` — заметка «дыра закрыта» с датой и ссылкой
  на фактический assert.

## Анализ

Класс — «недостающая evidence о поведении живой страницы» (`missing_evidence`):
сам факт «скролл сохраняется» не опровергнут и не подтверждён, просто не
инструментирован до конца в рамках одного хода. P1-кейс (TC-047), но
non-blocking для остальных 3 дыр «хозяйство-3» (TC-027/048/049 закрыты
независимо и зелены).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-07-19 | source_commit 63f6aac3b1ea1dfad82f68b8196aa6cf56f41853, version_code 11 (test_debt — сборка приложения не менялась, B4) | `tests/test_settings.py` целиком x2 + целевой `test_theme_dark_applies_instantly_without_recreating_activity` отдельно x1 (emulator-5554) | run1: `6 passed, 1 skipped in 247.26s`, `PYTEST_EXIT=0`; run2: `6 passed, 1 skipped in 244.13s`, `PYTEST_EXIT=0`; целевой отдельно: `1 passed in 47.79s`, `PYTEST_EXIT=0`. Единственный skip — известный TC-020 (Clear all ratings, APP_BUG/TEST_BUG под вопросом, не связан с этим долгом) | Fixed → Verified |

## Обсуждение

**2026-07-18T02:40:00Z — test-maintainer, диспатч «хозяйство-3»
(docs/09-improvement-plan.md:106-109, Этап 4 п.4):** заведено по прямому
указанию Lead в статус-проверке («job умер? проверь измерением») — после
второго FAIL (TimeoutException на поллинге scrollY) принял решение не
ретраить третий раз в том же ходе (правило 6 CLAUDE.md, класс «2 отклонённые
попытки на одном ярусе»), откатил рискованный assert к последней зелёной
версии и завёл этот test_debt вместо заметки в теле кейса (правило 9
CLAUDE.md, прецеденты AT-BUG-004/005/006/010: заметка без артефакта невидима
правилу B4). Инфраструктура (`browser_steps.scroll_webview_to`/
`get_webview_scroll_y`) оставлена в дереве — переиспользуема для фикса этого
долга, не мешает существующим тестам (не вызывается ниоткуда, кроме этого
файла — не участвует ни в одном текущем прогоне).

**2026-07-18T (позже), test-maintainer — фикс.** Диагностика измерением
(3 раунда, `Invoke-Pytest` с ad hoc диагностическими тестами, удалены после
хода) на устройстве (emulator-5554):
1. Гипотеза 1 (Given-страница недостаточно высокая) — ПОДТВЕРЖДЕНА: Browse
   root (`archiveofourown.org`) даёт `document.body.scrollHeight=427` при
   `window.innerHeight=798` — `scrollTo` там легитимно клампится к 0,
   стабильно (замер сразу и через 2с — идентичен). Гипотеза 3 (тайминг) тем
   самым опровергнута для этой страницы — дело не в довёрстке.
2. Промежуточная попытка — сменить Given на живой листинг `{HOME_URL}/works`
   (`scrollHeight=11030`, scrollTo сработал) — вскрыла ВТОРОЙ, более глубокий
   эффект: переключение темы реально триггерит `reload()` WebView (см.
   TC-048), а листинг «последних обновлённых работ» time-sensitive — между
   двумя загрузками (~10с) контент на живом archiveofourown.org успел
   измениться (`scrollHeight` 11030 -> 12731), из-за чего `scrollY` после
   reload честно уехал (899 -> 930). Это волатильность выбранной страницы,
   не баг приложения.
3. Финальный Given — статическая страница `{HOME_URL}/tos`
   (`browser_steps.open_stable_tall_page`): `reload()` всё ещё происходит, но
   контент практически не меняется (`scrollHeight` 9768 -> 9769), `scrollY`
   совпадает с точностью <1px (899.8 -> 900.6).

Assert добавлен в `test_theme_dark_applies_instantly_without_recreating_activity`
(`framework/tests/test_settings.py`) с допуском 2px (компенсирует усечение
дробной части `int(scrollY)` в `get_webview_scroll_y`). 3/3 PASS подряд
(`Invoke-Pytest tests/test_settings.py::
test_theme_dark_applies_instantly_without_recreating_activity`,
emulator-5554). `test-cases/settings/TC-047.md` дополнен закрывающей
заметкой. Гипотеза 2 (не тот WEBVIEW-контекст) не проверялась отдельно — в
этом сценарии открыта ровно одна вкладка/один WEBVIEW-контекст (см.
`driver.contexts` в диагностических логах: всегда `['NATIVE_APP',
'WEBVIEW_com.example.ao3_wrapper']`), поэтому неприменима к этому кейсу.

**2026-07-19T01:10:00Z — fix-verifier, Fixed → Verified.** Окружение поднято
штатно (`Start-Emulator`/`Install-App`/`Start-Appium`, emulator-5554), сборка
не менялась относительно `found_in`/`fixed_in` (test_debt, B4 не триггерит
новую сборку приложения — `source_commit
63f6aac3b1ea1dfad82f68b8196aa6cf56f41853`, `version_code 11`, тот же коммит,
что был на момент фикса). Прогнано согласно брифу: `tests/test_settings.py`
целиком дважды подряд (проверка стабильности, не только целевого assert) +
отдельно целевой тест ещё раз:
- run1 (`Invoke-Pytest tests/test_settings.py -q`): `6 passed, 1 skipped in
  247.26s (0:04:07)`, `PYTEST_EXIT=0`.
- run2 (тот же прогон повторно): `6 passed, 1 skipped in 244.13s (0:04:04)`,
  `PYTEST_EXIT=0`.
- целевой отдельно (`Invoke-Pytest
  tests/test_settings.py::test_theme_dark_applies_instantly_without_recreating_activity
  -q`): `1 passed in 47.79s`, `PYTEST_EXIT=0`.

Единственный skip в обоих полных прогонах — известный, задокументированный
(TC-020 «Clear all ratings» reload-неопределённость, не связан с этим долгом,
не про scroll-preservation). Фикс диагностирует и устраняет реальную причину
(Given-страница Browse root легитимно клампила scrollTo к 0 из-за недостаточной
высоты контента — не маскировка, а замена Given на статическую высокую страницу
`open_stable_tall_page` + допуск 2px под усечение `int(scrollY)`), не симптом.
3 зелёных прогона (2 полных + 1 целевой) стабильны, без флейка. Вердикт:
**Verified**. Лок снят.

Дефекты-собратья: не замечено — класс закрыт целиком в рамках этого долга;
инфраструктура `browser_steps.scroll_webview_to`/`get_webview_scroll_y`
теперь используется по назначению, аналогичных недобитых scroll-assert'ов в
других файлах не встречено в ходе этой проверки.
