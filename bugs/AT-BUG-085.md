---
id: AT-BUG-085
title: "assert_comment_collapsed_with_text читает RatingOverlay.comment_expanded() сразу после save_note() без settle — TC-115 красный в полном test_downloads.py (структурно не связан с AT-BUG-082 fix)"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Verified
found_in: "test-maintainer, AT-BUG-082 rework regression pass (test_downloads.py, run 1/2, 2026-08-17)"
fixed_in: "test-maintainer, 2026-08-20, framework/steps/rating_steps.py::_poll_comment_collapsed (settle+hold опрос, TC-115)"
last_seen_in: "run 1/2, tests/test_downloads.py::test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload (TC-115), 2026-08-17"
test_cases: ["TC-115"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-20T04:08:00Z"
updated: "2026-08-20T04:08:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: "Локализация (живое чтение RatingOverlay.kt): переключение
  showComment НЕ анимировано (ни animateColorAsState, ни AnimatedVisibility
  на этой ветке) — гонка не с анимацией, а с recomposition/layout-лагом под
  нагрузкой (тот же класс, что WARNING _settle_tab_switch в AT-BUG-082).
  Применён settle+hold опрос (_poll_comment_collapsed, framework/steps/
  rating_steps.py) — тот же двухфазный приём, что library_steps._poll_tab_
  absent (AT-BUG-082/083), на другом UI-механизме этого модуля. Сиблинг-аудит
  (D-0043): assert_note_overlay_expanded_with_text/assert_overlay_still_open
  — оба ПОЗИТИВНЫЕ опросы присутствия (is_present сам ждёт появления), не
  подвержены классу гонки — оставлены без изменений (докстринг-пометка
  добавлена). Найден (НЕ починен, вне мандата) третий аналог того же класса:
  rating_steps.assert_chip_absent (Then-негация сразу после tap_selected_chip,
  test_rating_listing.py:363-366) — доложен координатору, не в scope этого
  фикса. Красная проба: device-free юнит (framework/tests/
  test_rating_comment_collapse_settle_unit.py, 6 проб — транзитный
  ложный позитив не маскирует реальное отсутствие/присутствие, докоммитная
  одноразовая семантика детерминированно падает на том же сценарии, реальная
  regression не маскируется, поздняя regression ловится hold-фазой) +
  живой revert-цикл байтовой копией (CLAUDE.md п.8): pre-fix полный прогон
  test_downloads.py упал с ДРУГИМ классом отказа (device/DB instability —
  sqlite3 'no such table: work_ratings', InvalidElementStateException,
  TC-115 ERROR at setup — окружение деградировало ДО того, как дошло до
  целевого assert; НЕ используется как witness самого AT-BUG-085, честно
  зафиксировано как inconclusive). Живой регресс с фиксом: TC-115 изолированно
  2/2 PASSED (152.95s, 150.34s); полный test_downloads.py 2/2 PASSED
  (17 passed, 2076.21s и 2018.30s) — оба прогона включают TC-115. python -m
  pytest scripts/tests -q: 1704 passed, 1 skipped. arch_check.py: 0 ошибок
  (новый unit-файл в ALLOWLIST). validate_frontmatter.py: 0 ошибок."
known_issue: "false"
blocked_reason: ""
lock: ""
gitlab_issue: ""
---

# AT-BUG-085 — `assert_comment_collapsed_with_text` гонится с recomposition-лагом `RatingOverlay` (НЕ анимацией — опровергнуто фиксом, см. «Обсуждение»), TC-115 красный только в полном `test_downloads.py`

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`), поверхность —
`framework/steps/rating_steps.py::assert_comment_collapsed_with_text`/
`add_note_via_listing_overlay` (`RatingOverlay.comment_expanded()`,
`framework/screens/*` — экран рейтинг-overlay). Эмулятор `emulator-5554`, API 34,
replay (`listing_basic.mitm`).

## Обнаружено

ПОПУТНО при regression-верификации rework-фикса `AT-BUG-082` (критик-вход,
Б1-Б4) — НЕ относится к самому фиксу, см. «Анализ». Прогон 1/2 полного
`Invoke-Pytest tests/test_downloads.py -q` (после Б1-Б4 правок
`library_steps.py`/`library_screen.py`/`waits.py`): `1 failed, 16 passed in
2028.65s`, единственное падение — `test_edit_note_on_already_saved_work_via_
listing_overlay_does_not_redownload` (TC-115):

```
rating_steps.add_note_via_listing_overlay(driver, "re-save-note")
...
>       rating_steps.assert_comment_collapsed_with_text(driver, "re-save-note")
tests\test_downloads.py:399:
...
    assert not overlay.comment_expanded(), (
        "поле комментария должно свернуться в компактное превью, а не остаться развёрнутым"
    )
E   AssertionError: поле комментария должно свернуться в компактное превью, а не осталось развёрнутым
steps\rating_steps.py:301: AssertionError
```

`assert_comment_collapsed_with_text` вызывает `overlay.comment_expanded()`
СРАЗУ после `add_note_via_listing_overlay` (которая тапает «Save note» и
возвращает управление немедленно) — ни одного settle-опроса/ожидания
collapse-анимации поля комментария между тапом и чтением. TC-112 (сам
предмет `AT-BUG-082`) в ЭТОМ ЖЕ прогоне прошёл штатно — фикс подтверждён;
это ДРУГОЙ, структурно не связанный дефект того же класса «Then читает
раньше, чем UI-состояние устаканилось» (тот же класс, что `AT-BUG-081`/
`AT-BUG-082`, но в ТРЕТЬЕМ слое — collapse-анимация `RatingOverlay`, не
Room-запись и не `HorizontalPager`).

## Анализ (предварительный, не входит в мандат AT-BUG-082)

Не расширяю scope AT-BUG-082 починкой этого — другой модуль
(`rating_steps.py`/`RatingOverlay`, не `library_steps.py`/`LibraryScreen`),
другой UI-механизм (comment-collapse превью, не Pager-таб или Room-запись).
Каузальный вклад изменений AT-BUG-082 (Б1-Б4: `LibraryScreen.open_tab`
settle, `_poll_files_tab_absent` hold-фаза) в ЭТО падение **НЕ исключён и НЕ
подтверждён** (правило 14) — не делался исключающий прогон (например, тот
же TC-115 изолированно на пред-Б1-Б4 дереве). Структурно вклад маловероятен:
падение — в совершенно другой подсистеме (`RatingOverlay`/Browse-навигация),
через много ПОСЛЕДУЮЩИХ шагов ПОСЛЕ единственного места в этом тесте, где
исполняется изменённый код (`assert_work_in_tab` на строке 27, вызывающая
`open_tab_for_rating("SAVE")` — `LibraryScreen._settle_tab_switch`,
Captured log call этого падения РЕАЛЬНО зафиксировал WARNING «вкладка
'FAVORITE' не устаканилась за 2.0s бюджета» на ЭТОМ шаге — см. ниже), но
временная/state-связь между тем WARNING'ом и итоговым падением на
СОВЕРШЕННО ДРУГОМ шаге теста (после навигации Browse, открытия листинга,
тапа Rate-кнопки, раскрытия/сохранения комментария) не установлена и не
похожа на причинную по механизму (разные подсистемы, разделены множеством
промежуточных UI-действий).

Отдельное наблюдение (не по мандату этого бага, для будущей калибровки
`_TAB_SWITCH_SETTLE_TIMEOUT`): Captured log call этого падения содержит

```
WARNING framework.screens.library_screen:library_screen.py:87 AT-BUG-082 Б4
(LibraryScreen._settle_tab_switch): вкладка 'FAVORITE' не устаканилась за
2.0s бюджета (visible-text fingerprint продолжал меняться) — следующее
чтение может застать переходное состояние HorizontalPager'а
```

— т.е. `poll_until_stable` (новый примитив Б2/Б3 rework) НЕ сошёлся за
`_TAB_SWITCH_SETTLE_TIMEOUT=2.0s` на вкладке FAVORITE в этом конкретном
прогоне (нагруженная серия, 7-й тест по счёту). Само по себе это НЕ вызвало
видимого немедленного провала (следующий шаг того же теста,
`assert_download_icon_shown`, прошёл штатно) — оставлено как диагностика
(Б4 — не молчаливое проглатывание), не заведено отдельным багом: пока
недостаточно данных отличить «систематически недостаточный бюджет» от
«однократный выброс под нагрузкой» (нужно больше прогонов/сигналов).

## Критерий готовности (Fixed)

- [x] Локализовать причину (что именно НЕ ждёт `add_note_via_listing_overlay`/
      `assert_comment_collapsed_with_text` — collapse-анимация Compose,
      async-запись Room, JS-мост `applyRatings`, или комбинация). **Результат:**
      ни то, ни другое — `RatingMenu` (`RatingOverlay.kt`) переключает
      `showComment` простым Compose `if/else`, БЕЗ `animateColorAsState`/
      `AnimatedVisibility`; гонка — с recomposition/measure/layout-лагом ПЕРЕД
      тем, как новое дерево отражается в accessibility snapshot под нагрузкой
      (та же природа, что WARNING `_settle_tab_switch` AT-BUG-082). Async Room/
      JS-мост не на критическом пути этого чтения — `showComment=false`
      выставляется синхронно в обработчике клика.
- [x] Применить settle/hold-опрос по образцу `AT-BUG-081`/`AT-BUG-082`
      (`_poll_ratings_marker`/`_poll_files_tab_absent`) к
      `assert_comment_collapsed_with_text` (и, если тот же паттерн, к
      сиблингам `assert_note_overlay_expanded_with_text`/
      `assert_overlay_still_open`, если они читают немедленно после
      действия). **Результат:** новый `_poll_comment_collapsed`
      (`framework/steps/rating_steps.py`, settle+hold, аналог
      `library_steps._poll_tab_absent`). Оба названных сиблинга проверены —
      ПОЗИТИВНЫЕ опросы присутствия (`is_present` сам ждёт появления), не
      подвержены этому классу гонки, оставлены без изменений (докстринг-пометка
      добавлена). Найден (не в мандате, доложен) третий аналог: `assert_chip_
      absent` (та же негация сразу после действия, `test_rating_listing.py:363-
      366`) — НЕ починен, за пределами scope этого бага.
- [~] Красная проба на РЕАЛЬНОМ pre-fix коде (git checkout байтовой копией) +
      device-free различающий unit-тест. **Результат (частичный — см. пометку
      `[~]`, критик-гейт О5, 2026-08-20):** device-free `framework/tests/
      test_rating_comment_collapse_settle_unit.py` (6 проб) выполнен и
      различает старую/новую семантику — см. «Обсуждение». Живой revert-цикл
      байтовой копией на РЕАЛЬНОМ pre-fix коде дал device/DB-instability, НЕ
      чистый witness самого бага (см. «Обсуждение», честно зафиксировано как
      inconclusive, не выдаётся за красную пробу) — вторая половина пункта
      (живая красная проба на pre-fix коде) фактически не достигнута.
- [x] Живой регресс: TC-115 (и в идеале весь `test_downloads.py`) зелёный
      минимум 2 раза подряд. **Результат:** TC-115 изолированно 2/2 PASSED;
      полный `test_downloads.py` ТАКЖЕ 2/2 PASSED (17/17 каждый раз), плюс
      независимый живой прогон критик-гейта (163.42s, PYTEST_EXIT=0).
      Критерий формально выполнен; причинность фикса им НЕ доказывается
      (критик-гейт О6, 2026-08-20) — баг был найден в run 1/2 исходного
      2-прогонного регресс-пасса AT-BUG-082, значит pre-fix код в ЕГО run 2/2
      уже был зелёным (флейк по определению непостоянен). Несущее
      доказательство фикса — структурное (доказанная чтением кода семантика
      `is_present`, см. выше) + различающие юнит-пробы 2/5/6, не сам факт
      зелёных прогонов.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-20 | app-under-test HEAD `fdd3f72884105d1453448e0c9a7f2b109588b182` (2026-08-19T19:12:30+02:00), APK `versionName=dev-local versionCode=12` (`app-under-test/app/build/outputs/apk/debug/output-metadata.json`) | TC-115 (`tests/test_downloads.py::test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload`) изолированно, живой Appium; device-free `tests/test_rating_comment_collapse_settle_unit.py` (6 проб, батч с AT-BUG-083) | TC-115 — `1 passed in 163.29s`; device-free 6/6 PASSED (в составе общего батча `11 passed in 3.82s`) | Verified |

## Обсуждение

**[test-maintainer @ 2026-08-17T08:25:19Z]** Заведён ПОПУТНО при 2-прогонной
регресс-верификации `AT-BUG-082` rework (Б1-Б4 фикс `library_steps.py`/
`library_screen.py`/`waits.py` подтверждён на этом же прогоне — TC-112
прошёл штатно). Прогон 1/2 упал на TC-115, СОВЕРШЕННО ДРУГОМ тесте/модуле
(`rating_steps.py`/`RatingOverlay`, не `library_steps.py`/`LibraryScreen`) —
не расширяю scope AT-BUG-082 починкой этого. Доклад + баг, диспетчеризация
фикса — за Lead/очередь B4.

**[test-maintainer @ 2026-08-20T03:22:31Z]** B4-фикс закрыт.

Локализация (живое чтение `ui/components/RatingOverlay.kt`, `RatingMenu`):
переключение `showComment` НЕ анимировано ни `animateColorAsState`, ни
`AnimatedVisibility` — простой Compose `if (!showComment && comment.isNot
Blank()) {...превью...} else {TextButton("Hide note"/"Add a note")}`. Гонка —
НЕ с длительностью анимации (первичная гипотеза «collapse-анимация» не
подтвердилась кодом), а с задержкой recomposition/measure/layout ПЕРЕД тем,
как новое дерево реально отражается в accessibility snapshot под нагрузкой
полного прогона `test_downloads.py` (тот же класс задержки, что WARNING
`LibraryScreen._settle_tab_switch` в AT-BUG-082 наблюдении). Механика race:
`comment_expanded()` → `BaseScreen.is_present(by_text("Hide note"))` ждёт
ПОЯВЛЕНИЯ узла, но возвращает `True` НЕМЕДЛЕННО на первом снимке, если узел
ещё присутствует — не ждёт ИСЧЕЗНОВЕНИЯ; `not comment_expanded()` мог упасть
мгновенно, без единого шанса на устаканивание.

Фикс: новый `_poll_comment_collapsed` (`framework/steps/rating_steps.py`) —
settle-фаза (до `_COMMENT_COLLAPSE_SETTLE_TIMEOUT=3.0s`, шаг 0.3s, быстрые
чтения по 1s) + hold-фаза (`waits.assert_holds_for`, бюджет 4.0s) — тот же
двухфазный приём, что `library_steps._poll_tab_absent` (AT-BUG-082/083),
применённый к другому UI-механизму. `assert_comment_collapsed_with_text`
теперь делегирует в него вместо одноразового `not overlay.comment_expanded()`.

Сиблинг-аудит (D-0043 «класс, не экземпляр»): `assert_note_overlay_expanded_
with_text`/`assert_overlay_still_open` (названы в критерии готовности) —
проверены, оба читают ПОЗИТИВНО (`is_visible`/`comment_expanded` без
отрицания — `is_present` сам ждёт появления до своего `timeout`), не
подвержены классу этой гонки; оставлены без изменений, докстринг-пометка
добавлена для будущих читателей. При аудите файла найден ТРЕТИЙ аналог —
`rating_steps.assert_chip_absent` (`not chip_visible(...)`, вызывается сразу
после `tap_selected_chip` в `test_rating_listing.py:363/379`, TC-090/091) —
СТРУКТУРНО тот же паттерн (Then-негация присутствия сразу после действия,
меняющего состояние). НЕ почин: вне явного мандата этого бага (названы только
два конкретных сиблинга), нет зафиксированной флакующей истории (в отличие от
TC-115), и правило 2 промпта запрещает самовольное расширение scope. Доложено
координатору как class-аналог для отдельного тикета/решения.

Красная проба: **(1) device-free** — `framework/tests/test_rating_comment_
collapse_settle_unit.py` (6 проб, прямой аналог `test_library_files_tab_
settle_unit.py`/`test_library_tab_settle_unit.py`): транзитный ложный
позитив («Hide note» ещё в дереве 2 чтения, затем уходит) не маскирует
реальное свёрнутое состояние; красная проба воспроизводит СТАРУЮ одноразовую
семантику на ТОЙ ЖЕ мок-последовательности — детерминированно падает (ровно
класс TC-115); реальная persistent-регрессия (comment_expanded ПОСТОЯННО
True) не маскируется — `assert_comment_collapsed_with_text` честно поднимает
`AssertionError`; поздняя регрессия ([False, True, True]) ловится hold-фазой,
settle-only (без hold) её пропускает — все 6 PASSED (witness ниже).
**(2) Живой revert-цикл байтовой копией** (CLAUDE.md п.8 permission hygiene):
`git status --porcelain` до правки был непустым (файл уже нёс фикс на момент
цикла) → откат байтовой копией (не `git checkout`). Временно откачен
`framework/steps/rating_steps.py` до HEAD (`git show HEAD:... > файл`,
porcelain стал пустым — подтверждён точный откат), запущен ПОЛНЫЙ
`test_downloads.py` на pre-fix коде под нагрузкой (та же форма, что
изначально нашла баг) — но прогон упал ДРУГИМ, структурно не связанным
классом отказа (device/DB instability: `sqlite3.OperationalError: no such
table: work_ratings`, `InvalidElementStateException: Unable to perform W3C
actions` в нескольких тестах, TC-115 сам получил ERROR at setup — не дошёл до
целевого assert). Честно зафиксировано как INCONCLUSIVE (окружение
деградировало раньше, чем прогон достиг точки, которую чинит этот баг) — НЕ
используется как witness самого AT-BUG-085, только как телеметрия
нестабильности окружения на длинных прогонах (не заводится отдельным багом —
недостаточно данных отличить «систематическую деградацию» от «однократный
выброс», см. ту же осторожность, что уже была в разделе «Анализ» этого файла
для WARNING `_settle_tab_switch`). Файл восстановлен байтовой копией,
побайтовая сверка (`cmp`) подтвердила идентичность.

Живой регресс (после восстановления фикса, тот же `emulator-5554`):
- `tests/test_downloads.py::test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload`
  (TC-115) изолированно: `1 passed in 152.95s` и `1 passed in 150.34s`
  (2/2 подряд).
- Полный `tests/test_downloads.py`: `17 passed in 2076.21s (0:34:36)` и
  `17 passed in 2018.30s (0:33:38)` (2/2 подряд, ИДЕАЛЬНЫЙ бар DoD — оба
  прогона включают TC-115 в общей нагрузке, воспроизводящей исходное
  падение).

Witness прочих гейтов: `python -m pytest scripts/tests -q` →
`1704 passed, 1 skipped in 60.39s`. `python scripts/arch_check.py` →
`ошибок 0, предупреждений 7` (новый unit-файл добавлен в ALLOWLIST —
`("tests/test_rating_comment_collapse_settle_unit.py", "locators")`,
причина идентична трём существующим записям того же класса). `python
scripts/validate_frontmatter.py` → `ошибок 0, предупреждений 0`.

**[fix-verifier @ 2026-08-20T04:08:00Z] Verified (D1, независимая
верификация).** Среда: тот же живой Appium-подъём (`Start-Appium` →
«Appium started and ready on :4723»), `Install-App` Success,
`emulator-5554` живо весь ход. **Уточнение (критик-гейт D1-батча,
2026-08-20, блокер Б2):** «без деградации» — переоценка; `Start-Appium`
печатает эту строку при ответе ЛЮБОГО сервера на :4723, включая
резидентный (измерено критиком: единственный процесс на хосте, поднят
задолго до этой верификации) — сама строка не отличает свежую сессию от
деградировавшей. Против этого конкретного бага риск низкий: TC-115
подтверждён НЕЗАВИСИМО ТРИЖДЫ (worker 2/2 изолированно + 2/2 полный
файл, критик 1x, этот D1-прогон 1x) с СОГЛАСОВАННЫМ временем исполнения
(~150-163с во всех прогонах) — содержательный сигнал против деградации
именно здесь, а не просто повторение той же недифференцирующей строки.
**Уточнение (критик-гейт О3, rework round 2, 2026-08-20):** деградация
резидентной сессии проявляется НЕ ТОЛЬКО как отказ сессии/`create_driver`
(`NoSuchDriverError`) — `AT-BUG-087` (эта же сессия, этот же проход)
измерил ЕЩЁ ОДНУ форму: ~40% замедление + `TimeoutError` БЕЗ отказа самой
сессии. Вывод по TC-115 это не меняет (согласованные ~150-163с — сигнал
именно ПРОТИВ замедления/деградации в этих конкретных прогонах, независимо
от того, какой формой она могла бы проявиться), но общее утверждение
«проявляется как X, не как Y» было ýже фактического диапазона проявлений.

Device-free: `Invoke-Pytest tests/test_library_tab_settle_unit.py
tests/test_rating_comment_collapse_settle_unit.py -q` →
`11 passed in 3.82s` (6 из них — этот бага, батч с AT-BUG-083).

Живой: `Invoke-Pytest tests/test_downloads.py::test_edit_note_on_
already_saved_work_via_listing_overlay_does_not_redownload -q` (TC-115,
изолированно) → `1 passed in 163.29s`. Полный `test_downloads.py` не
перепрогонял отдельно — уже дважды подтверждён живьём и воркером (2/2
изолированно + 2/2 полный файл), и НЕЗАВИСИМО критиком (163.42s
PASSED) до этой верификации; изолированный прогон TC-115 этим ходом —
ТРЕТЬЕ независимое подтверждение (совпадает по времени выполнения с
критик-гейтом, ~163с — тот же класс сценария, детерминированно).

Причинность фикса подтверждена структурно (см. «Обсуждение»
test-maintainer выше — `is_present` семантика, различающие device-free
пробы), не одним фактом зелёного прогона (тот же класс осторожности,
что критик-гейт уже назвал О6). `test_cases: ["TC-115"]` — замок на
класс не пустой, требование не применяется. `status: Fixed →
Verified`, `known_issue` уже `"false"`, lock снят.
