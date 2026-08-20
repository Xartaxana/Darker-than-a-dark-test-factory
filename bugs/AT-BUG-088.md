---
id: AT-BUG-088
title: "Три settings-prefs Then-хелпера (assert_theme_mode_pref/assert_auto_apply_filter_pref/assert_font_size_step_pref) читают через голый adb.run_as — rc/stderr отбрасываются, отказ adb неотличим от несовпадения значения (AT-BUG-055 класс, живой remnant после AT-BUG-086)"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Open
found_in: "критик-гейт B4 AT-BUG-086, 2026-08-20"
fixed_in: ""
last_seen_in: ""
test_cases: ["TC-005", "TC-181", "TC-050", "TC-051"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-20T06:00:00Z"
updated: "2026-08-20T06:00:00Z"
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

# AT-BUG-088 — settings-prefs Then-хелперы слепы к отказу adb (rc/stderr не проверяются), живой remnant класса AT-BUG-055

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`), поверхность —
`framework/steps/settings_steps.py::_poll_settings_prefs` (единая точка чтения
после фикса AT-BUG-086) и три вызывающих Then-хелпера: `assert_theme_mode_pref`,
`assert_auto_apply_filter_pref`, `assert_font_size_step_pref`.

## Обнаружено

Критик-гейт B4 AT-BUG-086 (2026-08-20): фикс AT-BUG-086 добавил settle-опрос
поверх `adb.run_as("cat shared_prefs/ao3_settings.xml")`, но чтение осталось
"голым" — rc/stderr отбрасываются, только stdout сверяется подстрокой. Тот же
класс дыры, что `AT-BUG-055` уже нашёл и назвал для ЭТИХ ЖЕ ТРЁХ функций
(`assert_theme_mode_pref`/`assert_font_size_step_pref`, «кандидат для отдельного
B4-прохода, не блокер»), но НЕ завёл живым тикетом — только прозой внутри уже
`Verified`-артефакта. `AT-BUG-086` (уходящий в `Verified`) повторил ту же
прозаическую отсылку вместо тикета. Живого `Open`-артефакта под класс не было
(сверено поиском по `bugs/*.md`), поэтому remnant решено завести отдельно и
явно, а не третий раз оставить прозой в терминальном статусе.

Соседний оракул `app_steps._read_tabs_prefs_raw` уже переведён на
`adb.run_as_file_or_raise` фиксом `AT-BUG-055` — это референс-паттерн для
фикса здесь.

**Дополнительный аргумент чинить не откладывая бесконечно** (критик-гейт
AT-BUG-086, Б3): после AT-BUG-086 появилась ЕДИНАЯ точка чтения
(`_poll_settings_prefs`) — правка теперь локальна (один вызов внутри одной
функции, а не три места), и текущий полл слегка ухудшает диагностику: мёртвый
adb-транспорт теперь 3 секунды крутится в цикле и падает как «theme_mode !=
SYSTEM в SharedPreferences: ''», то есть отказ adb выдаётся за дефект продукта
под видом settle-таймаута.

## Критерий готовности (Fixed)

- [ ] `_poll_settings_prefs` переведён на `adb.run_as_file_or_raise` (или
      эквивалент, различающий «rc!=0/пустой stdout от adb» и «файл прочитан,
      но искомое значение ещё не появилось») — по образцу
      `app_steps._read_tabs_prefs_raw` (референс AT-BUG-055).
- [ ] Различающий unit-тест: adb-отказ (rc!=0/exception) даёт отдельное
      сообщение об ошибке, отличное от settle-таймаута по значению.
- [ ] Живой регресс: TC-005/TC-181/TC-050/TC-051 (или минимум TC-005 +
      test_smoke.py) зелёный минимум 2 раза подряд после правки.

## Обсуждение

**[координатор @ 2026-08-20T06:00:00Z]** Заведён по прямому предписанию
критик-гейта B4 AT-BUG-086 (блокер Б3): остаток класса AT-BUG-055 на тех же
трёх функциях был задекларирован только прозой внутри терминальных
артефактов (AT-BUG-055 Verified, затем AT-BUG-086 повторил) — без живого
Open-носителя находка теряется при каждой приёмке. Не чиню сам этим ходом
(правило 8а — лимит диспатчей прохода 4 близок к исчерпанию; B4-очередь
подберёт следующим проходом первым кандидатом).
