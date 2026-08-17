---
id: AT-BUG-085
title: "assert_comment_collapsed_with_text читает RatingOverlay.comment_expanded() сразу после save_note() без settle — TC-115 красный в полном test_downloads.py (структурно не связан с AT-BUG-082 fix)"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Open
found_in: "test-maintainer, AT-BUG-082 rework regression pass (test_downloads.py, run 1/2, 2026-08-17)"
fixed_in: ""
last_seen_in: "run 1/2, tests/test_downloads.py::test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload (TC-115), 2026-08-17"
test_cases: ["TC-115"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-17T08:25:19Z"
updated: "2026-08-17T08:25:19Z"
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

# AT-BUG-085 — `assert_comment_collapsed_with_text` гонится с collapse-анимацией `RatingOverlay`, TC-115 красный только в полном `test_downloads.py`

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

- [ ] Локализовать причину (что именно НЕ ждёт `add_note_via_listing_overlay`/
      `assert_comment_collapsed_with_text` — collapse-анимация Compose,
      async-запись Room, JS-мост `applyRatings`, или комбинация).
- [ ] Применить settle/hold-опрос по образцу `AT-BUG-081`/`AT-BUG-082`
      (`_poll_ratings_marker`/`_poll_files_tab_absent`) к
      `assert_comment_collapsed_with_text` (и, если тот же паттерн, к
      сиблингам `assert_note_overlay_expanded_with_text`/
      `assert_overlay_still_open`, если они читают немедленно после
      действия).
- [ ] Красная проба на РЕАЛЬНОМ pre-fix коде (git checkout байтовой копией) +
      device-free различающий unit-тест.
- [ ] Живой регресс: TC-115 (и в идеале весь `test_downloads.py`) зелёный
      минимум 2 раза подряд.

## Обсуждение

**[test-maintainer @ 2026-08-17T08:25:19Z]** Заведён ПОПУТНО при 2-прогонной
регресс-верификации `AT-BUG-082` rework (Б1-Б4 фикс `library_steps.py`/
`library_screen.py`/`waits.py` подтверждён на этом же прогоне — TC-112
прошёл штатно). Прогон 1/2 упал на TC-115, СОВЕРШЕННО ДРУГОМ тесте/модуле
(`rating_steps.py`/`RatingOverlay`, не `library_steps.py`/`LibraryScreen`) —
не расширяю scope AT-BUG-082 починкой этого. Доклад + баг, диспетчеризация
фикса — за Lead/очередь B4.
